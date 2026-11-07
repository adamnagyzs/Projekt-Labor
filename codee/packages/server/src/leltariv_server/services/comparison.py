"""A leltár összehasonlítása: egy időszak és egy körzet nyilvántartása a naplóval szemben.

Minden szám a beolvasási naplóból számolt, tárolt összeg nincs, ezért a lezárt időszak
eredménye később is ugyanígy jön ki. A szabályokat (besorolás, tartozék, korábbi állapot)
a `leltariv_domain.comparison` tartja; itt csak az adatgyűjtés van.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from leltariv_contracts.inventory import (
    ComparisonOut,
    ComparisonRow,
    ComparisonSummary,
    ForeignFind,
    PeriodOut,
    PeriodState,
    UnknownCode,
)
from leltariv_domain.comparison import (
    CATEGORY_ORDER,
    AssetStatus,
    StatusChange,
    classify,
    expected_quantity,
    progress_percent,
    status_at,
)
from leltariv_infrastructure.db.models import (
    Asset,
    AssetStatusChange,
    InventoryPeriod,
    InventorySession,
    InventoryZone,
    Room,
    Scan,
)
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from leltariv_server.api.assets import (
    asset_list_item,
    primary_inventory_numbers,
    types_and_responsibles,
)
from leltariv_server.api.rooms import room_label

#: ezek az eredmények számítanak bele a beolvasott darabba (ugyanaz, mint a beolvasásnál)
COUNTED_RESULTS = ("FOUND", "SURPLUS")


def period_out(period: InventoryPeriod) -> PeriodOut:
    return PeriodOut(
        id=period.id,
        name=period.name or "",
        year=period.year,
        state=cast(PeriodState, period.state),
        opened_at=period.opened_at,
        closed_at=period.closed_at,
    )


def in_period(period_id: UUID) -> ColumnElement[bool]:
    """Feltétel: a beolvasás az időszak valamelyik munkamenetében történt."""
    return Scan.session_id.in_(
        select(InventorySession.id).where(InventorySession.period_id == period_id)
    )


def last_rooms(
    session: Session, period_id: UUID, *conditions: ColumnElement[bool]
) -> dict[UUID | str, str]:
    """Kulcsonként (eszköz vagy kód) a helyiség, ahol az időszakban utoljára beolvasták.

    A visszavonó sor és a visszavont sor nem helymegállapítás.
    """
    undone = select(Scan.compensates_scan_id).where(Scan.compensates_scan_id.is_not(None))
    rows = session.execute(
        select(Scan.asset_id, Scan.code_normalized, Room)
        .join(Room, Scan.room_id == Room.id)
        .where(
            in_period(period_id),
            Scan.compensates_scan_id.is_(None),
            Scan.id.not_in(undone),
            *conditions,
        )
        .order_by(Scan.scanned_at)
    ).all()
    rooms: dict[UUID | str, str] = {}
    for asset_id, code, room in rows:
        rooms[asset_id if asset_id is not None else code] = room_label(room)
    return rooms


def build_comparison(
    session: Session, period: InventoryPeriod, zone: InventoryZone
) -> ComparisonOut:
    # Lezárt időszaknál a lezárás pillanatának állapota számít, nem a mai.
    as_of = period.closed_at or datetime.now(UTC)

    assets = session.scalars(
        select(Asset)
        .where(
            Asset.zone_id == zone.id,
            or_(Asset.created_at.is_(None), Asset.created_at <= as_of),
        )
        .order_by(Asset.asset_number, Asset.sub_number)
    ).all()

    changes: dict[UUID, list[StatusChange]] = defaultdict(list)
    for change in session.scalars(
        select(AssetStatusChange)
        .join(Asset, AssetStatusChange.asset_id == Asset.id)
        .where(Asset.zone_id == zone.id)
    ):
        changes[change.asset_id].append(
            StatusChange(
                changed_at=change.changed_at,
                old_status=cast(AssetStatus, change.old_status),
                new_status=cast(AssetStatus, change.new_status),
            )
        )

    # Eszközönként a beolvasott darab az időszakban, bármelyik körzet munkamenetéből.
    counted: dict[UUID, int] = {
        asset_id: int(total)
        for asset_id, total in session.execute(
            select(Scan.asset_id, func.sum(Scan.quantity_delta))
            .where(
                in_period(period.id),
                Scan.asset_id.is_not(None),
                Scan.result.in_(COUNTED_RESULTS),
            )
            .group_by(Scan.asset_id)
        )
    }

    # Ennek a körzetnek az eszközei, amelyek egy másik körzetben kerültek elő.
    found_elsewhere: dict[UUID, str] = {
        asset_id: code
        for asset_id, code in session.execute(
            select(Scan.asset_id, InventoryZone.code)
            .join(InventorySession, Scan.session_id == InventorySession.id)
            .join(InventoryZone, InventorySession.zone_id == InventoryZone.id)
            .join(Asset, Scan.asset_id == Asset.id)
            .where(
                InventorySession.period_id == period.id,
                Scan.result == "FOREIGN_ZONE",
                Asset.zone_id == zone.id,
            )
            .group_by(Scan.asset_id, InventoryZone.code)
            .having(func.sum(Scan.quantity_delta) > 0)
        )
    }

    rooms = last_rooms(session, period.id)

    ids = [asset.id for asset in assets]
    primary_codes = primary_inventory_numbers(session, ids)
    labels = types_and_responsibles(session, ids)

    rows: list[ComparisonRow] = []
    for asset in assets:
        status = status_at(cast(AssetStatus, asset.status), changes[asset.id], as_of)
        expected = expected_quantity(status, asset.quantity)
        got = counted.get(asset.id, 0)
        if expected == 0 and got == 0:
            continue  # nem aktív és nem is került elő: nem része a leltárnak
        parent_got = counted.get(asset.parent_asset_id) if asset.parent_asset_id else None
        category, verification = classify(expected, got, parent_got)
        rows.append(
            ComparisonRow(
                asset=asset_list_item(asset, zone.code, primary_codes, labels),
                status=status,
                expected=expected,
                counted=got,
                difference=got - expected,
                category=category,
                verification=verification,
                room=rooms.get(asset.id),
                found_in_zone=found_elsewhere.get(asset.id) if got == 0 else None,
            )
        )
    rows.sort(
        key=lambda row: (
            CATEGORY_ORDER[row.category],
            row.asset.asset_number,
            row.asset.sub_number,
        )
    )

    foreign = foreign_finds(session, period, zone, rooms)
    unknown = unknown_codes(session, period, zone)

    expected_rows = [row for row in rows if row.expected > 0]
    missing = sum(row.category == "MISSING" for row in rows)
    summary = ComparisonSummary(
        expected_assets=len(expected_rows),
        found=sum(row.category == "FOUND" for row in rows),
        inherited=sum(row.verification == "INHERITED" for row in rows),
        partial=sum(row.category == "PARTIAL" for row in rows),
        missing=missing,
        surplus=sum(row.category == "SURPLUS" for row in rows),
        foreign=len(foreign),
        unknown=len(unknown),
        progress_percent=progress_percent(len(expected_rows), missing),
    )
    return ComparisonOut(
        period=period_out(period),
        zone_code=zone.code,
        summary=summary,
        rows=rows,
        foreign=foreign,
        unknown=unknown,
    )


def zone_sessions(period_id: UUID, zone_id: int) -> ColumnElement[bool]:
    """Feltétel: a beolvasás ennek a körzetnek egy munkamenetében történt az időszakban."""
    return Scan.session_id.in_(
        select(InventorySession.id).where(
            InventorySession.period_id == period_id,
            InventorySession.zone_id == zone_id,
        )
    )


def foreign_finds(
    session: Session,
    period: InventoryPeriod,
    zone: InventoryZone,
    rooms: dict[UUID | str, str],
) -> list[ForeignFind]:
    """Más körzet eszközei, amelyek itt kerültek elő; a visszavonás levonódik."""
    totals = session.execute(
        select(Scan.asset_id, func.sum(Scan.quantity_delta))
        .where(
            zone_sessions(period.id, zone.id),
            Scan.result == "FOREIGN_ZONE",
            Scan.asset_id.is_not(None),
        )
        .group_by(Scan.asset_id)
        .having(func.sum(Scan.quantity_delta) > 0)
    ).all()
    if not totals:
        return []

    quantities = {asset_id: int(total) for asset_id, total in totals}
    found = session.execute(
        select(Asset, InventoryZone.code)
        .join(InventoryZone, Asset.zone_id == InventoryZone.id, isouter=True)
        .where(Asset.id.in_(quantities))
        .order_by(Asset.asset_number, Asset.sub_number)
    ).all()
    primary_codes = primary_inventory_numbers(session, list(quantities))
    labels = types_and_responsibles(session, list(quantities))
    return [
        ForeignFind(
            asset=asset_list_item(asset, home_code, primary_codes, labels),
            home_zone_code=home_code or "",
            quantity=quantities[asset.id],
            room=rooms.get(asset.id),
        )
        for asset, home_code in found
    ]


def unknown_codes(
    session: Session, period: InventoryPeriod, zone: InventoryZone
) -> list[UnknownCode]:
    """Kódok eszköz nélkül: ismeretlen, vagy több idegen körzetben is szereplő kód."""
    no_asset = (Scan.result == "UNKNOWN_CODE") | (
        (Scan.result == "FOREIGN_ZONE") & Scan.asset_id.is_(None)
    )
    totals = session.execute(
        select(Scan.code_normalized, func.min(Scan.raw_code), func.sum(Scan.quantity_delta))
        .where(zone_sessions(period.id, zone.id), no_asset)
        .group_by(Scan.code_normalized)
        .having(func.sum(Scan.quantity_delta) > 0)
        .order_by(Scan.code_normalized)
    ).all()
    rooms = last_rooms(session, period.id, zone_sessions(period.id, zone.id), no_asset)
    return [
        UnknownCode(raw_code=raw_code, quantity=int(total), room=rooms.get(code))
        for code, raw_code, total in totals
    ]
