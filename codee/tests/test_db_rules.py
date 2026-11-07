"""Az adatbázis szabályai és az összehasonlítás valódi Postgresen.

Csak akkor fut, ha a `TEST_DATABASE_URL` be van állítva egy migrált adatbázisra (a CI-ban
igen). Minden teszt egy tranzakcióban fut, és a végén visszagörgetjük, ezért a meglévő
adatból semmi nem változik. A végpontokat függvényként hívjuk ugyanezzel a munkamenettel;
a commitjuk csak egy mentési pontot zár le.
Szándékosan nem a `DATABASE_URL`: az a fejlesztői adatbázis, azt teszt nem írhatja.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from leltariv_contracts.inventory import PeriodCreate
from leltariv_infrastructure.db.models import (
    AppUser,
    Asset,
    AssetStatusChange,
    InventoryPeriod,
    InventorySession,
    InventoryZone,
    Room,
    Scan,
)
from leltariv_server.api.history import get_asset_history
from leltariv_server.api.periods import close_period, create_period, get_comparison
from leltariv_server.services.comparison import build_comparison
from sqlalchemy import create_engine, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL nincs beállítva (csak a CI-ban fut)"
)

NOW = datetime.now(UTC)
CREATED = NOW - timedelta(hours=3)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            # Tiszta lap: a meglévő aktív időszakot lezárjuk (a visszagörgetés visszahozza).
            session.execute(
                update(InventorySession)
                .where(InventorySession.closed_at.is_(None))
                .values(closed_at=NOW)
            )
            session.execute(
                update(InventoryPeriod)
                .where(InventoryPeriod.state == "ACTIVE")
                .values(state="CLOSED", closed_at=NOW)
            )
            yield session
        finally:
            session.close()
            transaction.rollback()
    engine.dispose()


@pytest.fixture
def user(db: Session) -> AppUser:
    user = AppUser(display_name="Teszt Admin", role="ADMIN")
    db.add(user)
    db.flush()
    return user


def zone(db: Session) -> InventoryZone:
    item = InventoryZone(code=f"T{uuid4().hex[:6]}")
    db.add(item)
    db.flush()
    return item


def period(db: Session) -> InventoryPeriod:
    item = InventoryPeriod(name="Teszt időszak", year=2026, state="ACTIVE", opened_at=CREATED)
    db.add(item)
    db.flush()
    return item


def asset(db: Session, home: InventoryZone, quantity: int = 1, **fields: object) -> Asset:
    item = Asset(
        asset_number=f"9{uuid4().int % 10**8:08d}",
        sub_number=0,
        name="Tesztszék",
        name_normalized="tesztszek",
        zone_id=home.id,
        quantity=quantity,
        created_at=CREATED,
        **fields,
    )
    db.add(item)
    db.flush()
    return item


def scanner(db: Session, session: InventorySession) -> Callable[..., Scan]:
    def scan(
        target: Asset | None,
        result: str = "FOUND",
        quantity: int = 1,
        code: str = "kod",
        room: Room | None = None,
        undoes: Scan | None = None,
    ) -> Scan:
        item = Scan(
            session_id=session.id,
            asset_id=target.id if target else None,
            raw_code=code,
            code_normalized=code.lower(),
            result=result,
            quantity_delta=-undoes.quantity_delta if undoes else quantity,
            room_id=room.id if room else None,
            compensates_scan_id=undoes.id if undoes else None,
        )
        db.add(item)
        db.flush()
        return item

    return scan


def change_status(
    db: Session, target: Asset, old: str, new: str, at: datetime | None = None
) -> None:
    db.add(
        AssetStatusChange(
            asset_id=target.id,
            old_status=old,
            new_status=new,
            reason="teszt",
            **({"changed_at": at} if at else {}),
        )
    )
    db.flush()
    # az asset.status-t a trigger írta át; a memóriában lévő objektum erről nem tud
    db.expire(target)


def close(db: Session, period: InventoryPeriod, *sessions: InventorySession) -> None:
    """Előbb a munkamenetek, utána az időszak, ahogy a végpont is csinálja.

    Egy flush-ban az ORM a szülőt (időszak) frissítené előbb, azt pedig a trigger nem
    engedi, amíg van nyitott munkamenete.
    """
    at = NOW - timedelta(hours=1)
    for item in sessions:
        item.closed_at = at
    db.flush()
    period.state, period.closed_at = "CLOSED", at
    db.flush()


def test_status_changes_only_through_the_log(db: Session) -> None:
    item = asset(db, zone(db))

    change_status(db, item, "ACTIVE", "SCRAPPED")
    db.refresh(item)
    assert item.status == "SCRAPPED"

    # a napló régi állapota nem a mostani: elbukik
    with pytest.raises(IntegrityError), db.begin_nested():
        change_status(db, item, "ACTIVE", "LOST")
    # közvetlenül nem írható át
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text("UPDATE asset SET status = 'ACTIVE' WHERE id = :id"), {"id": item.id})
    # a napló sora végleges
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text("DELETE FROM asset_status_change WHERE asset_id = :id"), {"id": item.id})
    # az eszköz nem törölhető, csak az állapota változhat
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(text("DELETE FROM asset WHERE id = :id"), {"id": item.id})


def test_period_rules(db: Session) -> None:
    home = zone(db)
    current = period(db)

    with pytest.raises(IntegrityError), db.begin_nested():
        period(db)  # második aktív

    open_session = InventorySession(period_id=current.id, zone_id=home.id, started_at=NOW)
    db.add(open_session)
    db.flush()

    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            update(InventoryPeriod)
            .where(InventoryPeriod.id == current.id)
            .values(state="CLOSED", closed_at=NOW)
        )

    close(db, current, open_session)

    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(InventorySession(period_id=current.id, zone_id=home.id, started_at=NOW))
        db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            update(InventoryPeriod).where(InventoryPeriod.id == current.id).values(name="Más")
        )


def test_comparison(db: Session) -> None:
    here, other = zone(db), zone(db)
    current = period(db)
    work = InventorySession(period_id=current.id, zone_id=here.id, started_at=NOW)
    elsewhere = InventorySession(period_id=current.id, zone_id=other.id, started_at=NOW)
    db.add_all([work, elsewhere])
    db.flush()
    room = Room(zone_id=here.id, room_number="G-210", name="Labor")
    db.add(room)
    db.flush()
    scan, scan_elsewhere = scanner(db, work), scanner(db, elsewhere)

    found = asset(db, here)
    partial = asset(db, here, quantity=30)
    missing = asset(db, here)
    surplus = asset(db, here)
    accessory = asset(db, here, parent_asset_id=found.id)
    scrapped = asset(db, here)
    undone = asset(db, here)
    moved = asset(db, here)
    visitor = asset(db, other)

    scan(found, room=room)
    scan(partial, quantity=27)
    scan(surplus)
    scan(surplus, result="SURPLUS")
    scan(undone, undoes=scan(undone))
    scan_elsewhere(moved, result="FOREIGN_ZONE")
    scan(visitor, result="FOREIGN_ZONE", room=room)
    scan(None, result="UNKNOWN_CODE", code="X1", quantity=2)
    change_status(db, scrapped, "ACTIVE", "SCRAPPED", at=NOW - timedelta(hours=2))

    result = build_comparison(db, current, here)
    rows = {row.asset.id: row for row in result.rows}

    assert rows[found.id].category == "FOUND"
    assert rows[found.id].room == "G-210 · Labor"
    assert (rows[partial.id].category, rows[partial.id].difference) == ("PARTIAL", -3)
    assert rows[missing.id].category == "MISSING"
    assert (rows[surplus.id].category, rows[surplus.id].counted) == ("SURPLUS", 2)
    assert (rows[accessory.id].category, rows[accessory.id].verification) == (
        "FOUND",
        "INHERITED",
    )
    assert scrapped.id not in rows
    assert rows[undone.id].category == "MISSING"
    assert (rows[moved.id].category, rows[moved.id].found_in_zone) == ("MISSING", other.code)
    assert [(f.asset.id, f.home_zone_code, f.room) for f in result.foreign] == [
        (visitor.id, other.code, "G-210 · Labor")
    ]
    assert [(u.raw_code, u.quantity) for u in result.unknown] == [("X1", 2)]
    assert result.rows[0].category == "MISSING"  # a hiány van elöl

    summary = result.summary
    assert (summary.expected_assets, summary.found, summary.inherited) == (7, 2, 1)
    assert (summary.partial, summary.missing, summary.surplus) == (1, 3, 1)
    assert (summary.foreign, summary.unknown, summary.progress_percent) == (1, 1, 57.1)

    # Lezárás után a lezáráskori állapot számít: a később elveszettnek jelölt eszköz a
    # lezárt időszakban továbbra is aktívként hiányzik.
    close(db, current, work, elsewhere)
    change_status(db, missing, "ACTIVE", "LOST")

    closed = {row.asset.id: row for row in build_comparison(db, current, here).rows}
    assert (closed[missing.id].category, closed[missing.id].status) == ("MISSING", "ACTIVE")


def test_period_endpoints(db: Session, user: AppUser) -> None:
    created = create_period(PeriodCreate(name="2027. évi leltár", year=2027), user, db)
    assert created.state == "ACTIVE"

    with pytest.raises(HTTPException) as again:
        create_period(PeriodCreate(name="Még egy", year=2027), user, db)
    assert again.value.status_code == 409

    home = zone(db)
    db.add(InventorySession(period_id=created.id, zone_id=home.id, started_at=NOW))
    db.flush()

    # a nyitott munkamenetet a lezárás maga zárja le
    assert close_period(created.id, user, db).state == "CLOSED"
    with pytest.raises(HTTPException) as twice:
        close_period(created.id, user, db)
    assert twice.value.status_code == 409

    comparison = get_comparison(created.id, home.code, user, db)
    assert comparison.summary.expected_assets == 0


def test_history_endpoint(db: Session, user: AppUser) -> None:
    home = zone(db)
    current = period(db)
    work = InventorySession(period_id=current.id, zone_id=home.id, started_at=NOW)
    db.add(work)
    db.flush()
    item = asset(db, home)
    scan = scanner(db, work)
    scan(item, undoes=scan(item))
    db.add(
        AssetStatusChange(
            asset_id=item.id,
            old_status="ACTIVE",
            new_status="LOST",
            reason="Nem került elő",
            changed_by=user.id,
        )
    )
    db.flush()

    entries = get_asset_history(item.id, user, db)
    assert sorted(entry.kind for entry in entries) == ["CREATED", "SCAN", "STATUS", "UNDO"]
    assert entries[-1].kind == "CREATED"  # a legrégebbi a végén
    status = next(entry for entry in entries if entry.kind == "STATUS")
    assert status.text == "Állapot: Aktív → Elveszett. Indoklás: Nem került elő"
    assert status.by == "Teszt Admin"

    with pytest.raises(HTTPException) as unknown:
        get_asset_history(uuid4(), user, db)
    assert unknown.value.status_code == 404
