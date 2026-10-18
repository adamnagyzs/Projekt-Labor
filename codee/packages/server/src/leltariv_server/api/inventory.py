from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from leltariv_contracts.inventory import ScanCreate, ScanOut, SessionCreate, SessionOut
from leltariv_domain.normalization import normalize_code
from leltariv_domain.scanning import (
    CodeMatch,
    count_result,
    resolve,
    scan_message,
    undo_message,
)
from leltariv_infrastructure.db.models import (
    AppUser,
    Asset,
    AssetCode,
    InventoryPeriod,
    InventorySession,
    InventoryZone,
    Room,
    Scan,
)
from leltariv_infrastructure.db.session import get_db_session
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from leltariv_server.api.assets import asset_list_item, primary_inventory_numbers
from leltariv_server.api.rooms import room_label
from leltariv_server.dependencies import require_current_user

router = APIRouter(prefix="/api/v1", tags=["inventory"])

#: ezek az eredmények számítanak bele a beolvasott darabba; az idegen körzetes nem
COUNTED_RESULTS = ("FOUND", "SURPLUS")


def session_out(
    inventory_session: InventorySession, zone_code: str, period_name: str
) -> SessionOut:
    return SessionOut(
        id=inventory_session.id,
        zone_code=zone_code,
        period_name=period_name,
        started_at=inventory_session.started_at or datetime.now(UTC),
        closed_at=inventory_session.closed_at,
    )


def open_session(session: Session, session_id: UUID) -> InventorySession:
    """A munkamenet, amibe még lehet írni; különben 404 vagy 409.

    A lezárást az adatbázis trigger is őrzi, ez itt az olvasható hibaüzenetért van.
    """
    inventory_session = session.get(InventorySession, session_id)
    if inventory_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A megadott munkamenet nem található.",
        )
    if inventory_session.closed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A munkamenet le van zárva.",
        )
    return inventory_session


def counted_in_period(session: Session, asset_id: UUID, period_id: UUID) -> int:
    """Az eszköz beolvasott darabja az időszakban; a visszavonások negatív sora levonódik."""
    total = session.scalar(
        select(func.coalesce(func.sum(Scan.quantity_delta), 0))
        .join(InventorySession, Scan.session_id == InventorySession.id)
        .where(
            Scan.asset_id == asset_id,
            Scan.result.in_(COUNTED_RESULTS),
            InventorySession.period_id == period_id,
        )
    )
    return int(total or 0)


def scan_response(
    session: Session,
    scan: Scan,
    *,
    message: str,
    expected: int | None = None,
    counted: int | None = None,
) -> ScanOut:
    asset_out = None
    if scan.asset_id is not None:
        row = session.execute(
            select(Asset, InventoryZone.code)
            .join(InventoryZone, Asset.zone_id == InventoryZone.id, isouter=True)
            .where(Asset.id == scan.asset_id)
        ).one()
        asset, asset_zone_code = row
        asset_out = asset_list_item(
            asset, asset_zone_code, primary_inventory_numbers(session, [asset.id])
        )

    room = session.get(Room, scan.room_id) if scan.room_id is not None else None

    return ScanOut(
        id=scan.id,
        raw_code=scan.raw_code,
        result=scan.result,  # type: ignore[arg-type]
        scanned_at=scan.scanned_at,
        asset=asset_out,
        message=message,
        quantity=scan.quantity_delta,
        room=room_label(room) if room is not None else None,
        expected=expected,
        counted=counted,
        compensates_scan_id=scan.compensates_scan_id,
    )


@router.post(
    "/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Leltározási munkamenet indítása",
)
def create_session(
    request: SessionCreate,
    current_user: AppUser = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> SessionOut:
    zone = session.scalar(select(InventoryZone).where(InventoryZone.code == request.zone_code))
    if zone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A megadott körzet nem található.",
        )

    period = session.scalar(select(InventoryPeriod).where(InventoryPeriod.state == "ACTIVE"))
    if period is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nincs nyitott leltári időszak.",
        )

    inventory_session = InventorySession(
        period_id=period.id,
        zone_id=zone.id,
        user_id=current_user.id,
        started_at=datetime.now(UTC),
    )
    session.add(inventory_session)
    session.commit()
    session.refresh(inventory_session)

    return session_out(inventory_session, zone.code, period.name or "")


@router.post(
    "/sessions/{session_id}/scans",
    response_model=ScanOut,
    status_code=status.HTTP_201_CREATED,
    summary="Beolvasott kód rögzítése darabszámmal és helyiséggel",
)
def create_scan(
    session_id: UUID,
    request: ScanCreate,
    current_user: AppUser = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> ScanOut:
    inventory_session = open_session(session, session_id)
    active_zone = session.get(InventoryZone, inventory_session.zone_id)
    if active_zone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A munkamenet körzete nem található.",
        )

    if request.room_id is not None:
        room = session.get(Room, request.room_id)
        if room is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="A helyiség nem található.",
            )
        if room.zone_id != inventory_session.zone_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A helyiség nem ebben a körzetben van.",
            )

    normalized_code = normalize_code(request.raw_code)
    match_rows = session.execute(
        select(AssetCode.asset_id, InventoryZone.code)
        .join(InventoryZone, AssetCode.zone_id == InventoryZone.id)
        .where(AssetCode.code_normalized == normalized_code)
    ).all()
    matches = [CodeMatch(asset_id=asset_id, zone_code=code) for asset_id, code in match_rows]
    result, asset_id = resolve(matches, active_zone.code)

    asset = session.get(Asset, asset_id) if asset_id is not None else None
    asset_zone_code = None
    if asset is not None and asset.zone_id is not None:
        asset_zone = session.get(InventoryZone, asset.zone_id)
        asset_zone_code = asset_zone.code if asset_zone is not None else None

    # A darabszám csak a saját körzetben számít: ott dől el, megvan-e minden, vagy több van.
    expected = counted = None
    if result == "FOUND" and asset is not None:
        counted_before = counted_in_period(session, asset.id, inventory_session.period_id)
        result = count_result(asset.quantity, counted_before, request.quantity)
        expected, counted = asset.quantity, counted_before + request.quantity

    scan = Scan(
        session_id=inventory_session.id,
        asset_id=asset_id,
        raw_code=request.raw_code,
        code_normalized=normalized_code,
        result=result,
        quantity_delta=request.quantity,
        room_id=request.room_id,
        scanned_by=current_user.id,
    )
    session.add(scan)
    session.commit()
    session.refresh(scan)

    return scan_response(
        session,
        scan,
        message=scan_message(
            result,
            raw_code=request.raw_code,
            asset_name=asset.name if asset is not None else None,
            asset_zone_code=asset_zone_code,
            expected=expected,
            counted=counted,
        ),
        expected=expected,
        counted=counted,
    )


@router.post(
    "/sessions/{session_id}/scans/{scan_id}/undo",
    response_model=ScanOut,
    status_code=status.HTTP_201_CREATED,
    summary="Téves beolvasás visszavonása kiegyenlítő bejegyzéssel",
)
def undo_scan(
    session_id: UUID,
    scan_id: UUID,
    current_user: AppUser = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> ScanOut:
    inventory_session = open_session(session, session_id)

    original = session.get(Scan, scan_id)
    if original is None or original.session_id != inventory_session.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A beolvasás ebben a munkamenetben nem található.",
        )
    if original.compensates_scan_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Visszavonást nem lehet visszavonni.",
        )

    compensation = Scan(
        session_id=original.session_id,
        asset_id=original.asset_id,
        raw_code=original.raw_code,
        code_normalized=original.code_normalized,
        result=original.result,
        quantity_delta=-original.quantity_delta,
        room_id=original.room_id,
        scanned_by=current_user.id,
        compensates_scan_id=original.id,
    )
    session.add(compensation)
    try:
        session.commit()
    except IntegrityError as error:
        # Az egyedi megkötés dönt, nem egy előzetes lekérdezés: két gyors kattintásnál is.
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ezt a beolvasást már visszavontad.",
        ) from error
    session.refresh(compensation)

    expected = counted = None
    if compensation.asset_id is not None and compensation.result in COUNTED_RESULTS:
        asset = session.get(Asset, compensation.asset_id)
        expected = asset.quantity if asset is not None else None
        counted = counted_in_period(session, compensation.asset_id, inventory_session.period_id)

    return scan_response(
        session,
        compensation,
        message=undo_message(original.raw_code, original.quantity_delta),
        expected=expected,
        counted=counted,
    )


@router.post(
    "/sessions/{session_id}/close",
    response_model=SessionOut,
    summary="Munkamenet lezárása; utána nem fogad beolvasást",
)
def close_session(
    session_id: UUID,
    _current_user: AppUser = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> SessionOut:
    inventory_session = session.get(InventorySession, session_id)
    if inventory_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A megadott munkamenet nem található.",
        )
    if inventory_session.closed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A munkamenet már le van zárva.",
        )

    inventory_session.closed_at = datetime.now(UTC)
    session.commit()

    zone = session.get(InventoryZone, inventory_session.zone_id)
    period = session.get(InventoryPeriod, inventory_session.period_id)
    return session_out(
        inventory_session,
        zone.code if zone is not None else "",
        (period.name or "") if period is not None else "",
    )
