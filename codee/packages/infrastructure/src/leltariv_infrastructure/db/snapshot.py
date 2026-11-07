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

from sqlalchemy import Column, Connection, Integer, insert, select, text
from sqlalchemy.orm import Session

from leltariv_infrastructure.db.base import Base

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

    A visszatöltés a teljes állapotot cseréli, a naplókat is, ezért megkerüli a történetet
    őrző triggereket (append-only napló, nem törölhető eszköz, lezárt időszak). A TRUNCATE
    eleve nem soronkénti, a betöltés idejére pedig a saját triggereinket kikapcsoljuk; az
    idegen kulcsok ellenőrzése közben is él. Az ALTER TABLE tranzakciós: hiba esetén a
    triggerek a visszagörgetéssel együtt visszakapcsolnak. A hívó előtte mindig
    pillanatképet ment a mostani állapotról.
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
    for table in tables:
        session.execute(text(f"ALTER TABLE {table.name} DISABLE TRIGGER USER"))

    counts: dict[str, int] = {}
    for table in tables:
        columns: dict[str, Column[Any]] = {column.name: column for column in table.columns}
        rows = [
            {name: from_json(columns[name], value) for name, value in row.items()}
            for row in data["tables"].get(table.name, [])
        ]
        # Önmagára hivatkozó tábla (tartozék, visszavonás): a hivatkozott sor menjen előbb.
        self_refs = [fk.parent.name for fk in table.foreign_keys if fk.column.table is table]
        rows.sort(key=lambda r: any(r[name] is not None for name in self_refs))
        if rows:
            session.execute(insert(table), rows)
        counts[table.name] = len(rows)

    for table in tables:
        session.execute(text(f"ALTER TABLE {table.name} ENABLE TRIGGER USER"))

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
