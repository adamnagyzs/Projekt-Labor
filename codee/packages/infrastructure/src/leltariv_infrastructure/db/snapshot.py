"""Pillanatkép: az adatbázis teljes tartalma egy JSON-dokumentumban, és vissza.

A táblák listája a modellekből jön, tehát egy új tábla magától bekerül. A dokumentum a
séma Alembic-verzióját is tartalmazza: más sémájú adatbázisba nem töltjük vissza, mert
az oszlopok nem feltétlenül egyeznek.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Column, Connection, Integer, insert, select, text, update
from sqlalchemy.orm import Session

from leltariv_infrastructure.db.base import Base
from leltariv_infrastructure.db.models import InventorySession

FORMAT = "leltariv-snapshot"


def schema_revision(connection: Connection | Session) -> str | None:
    return connection.scalar(text("SELECT version_num FROM alembic_version"))


def dump(connection: Connection) -> dict[str, Any]:
    """Minden tábla minden sora. JSON-ba írásnál a `default=str` kezeli a UUID-t, dátumot,
    pénzösszeget; a hívó egy REPEATABLE READ tranzakcióban hívja, hogy a táblák egymáshoz
    illő állapotot mutassanak."""
    tables = {
        table.name: [
            dict(row)
            for row in connection.execute(
                select(table).order_by(*table.primary_key.columns)
            ).mappings()
        ]
        for table in Base.metadata.sorted_tables
    }
    return {
        "format": FORMAT,
        "revision": schema_revision(connection),
        "created_at": datetime.now(UTC).isoformat(),
        "tables": tables,
    }


def from_json(column: Column[Any], value: Any) -> Any:
    """A JSON-ban szövegként tárolt értéket visszaalakítja az oszlop Python-típusára."""
    if value is None:
        return None
    kind = column.type.python_type
    if kind is datetime:
        return datetime.fromisoformat(value)
    if kind is date:
        return date.fromisoformat(value)
    if kind in (UUID, Decimal):
        return kind(value)
    return value


def restore(session: Session, data: dict[str, Any]) -> dict[str, int]:
    """Az adatbázis tartalmát lecseréli a pillanatképére; a commit a hívóé.

    A TRUNCATE szándékosan kerüli meg a `scan` tábla append-only triggerét, ami soronként
    tiltja a törlést: a visszatöltés a teljes állapotot cseréli, a naplót is. Ezért a hívó
    előtte mindig pillanatképet ment a mostani állapotról.
    """
    if data.get("format") != FORMAT:
        raise ValueError("A fájl nem Leltárív-pillanatkép.")
    current = schema_revision(session)
    if data.get("revision") != current:
        raise ValueError(
            f"A pillanatkép más adatbázis-sémához készült ({data.get('revision')}), "
            f"a mostani: {current}."
        )

    tables = Base.metadata.sorted_tables
    session.execute(text(f"TRUNCATE {', '.join(t.name for t in tables)} RESTART IDENTITY"))

    counts: dict[str, int] = {}
    closed_sessions: list[tuple[UUID, datetime]] = []
    for table in tables:
        columns: dict[str, Column[Any]] = {column.name: column for column in table.columns}
        rows = [
            {name: from_json(columns[name], value) for name, value in row.items()}
            for row in data["tables"].get(table.name, [])
        ]
        if table is InventorySession.__table__:
            # Lezárt munkamenetbe a trigger nem enged beolvasást: a lezárás a sorok után jön.
            closed_sessions = [(r["id"], r["closed_at"]) for r in rows if r["closed_at"]]
            rows = [{**r, "closed_at": None} for r in rows]
        # Önmagára hivatkozó tábla (tartozék, visszavonás): a hivatkozott sor menjen előbb.
        self_refs = [fk.parent.name for fk in table.foreign_keys if fk.column.table is table]
        rows.sort(key=lambda r: any(r[name] is not None for name in self_refs))
        if rows:
            session.execute(insert(table), rows)
        counts[table.name] = len(rows)

    for session_id, closed_at in closed_sessions:
        session.execute(
            update(InventorySession)
            .where(InventorySession.id == session_id)
            .values(closed_at=closed_at)
        )

    # Az egész számú azonosítók sorszámlálója a betöltött legnagyobb értéktől folytatódjon.
    for table in tables:
        for column in table.primary_key.columns:
            if isinstance(column.type, Integer):
                session.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{table.name}', '{column.name}'),"
                        f" COALESCE(MAX({column.name}), 1), MAX({column.name}) IS NOT NULL)"
                        f" FROM {table.name}"
                    )
                )
    return counts
