from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from leltariv_contracts.inventory import ScanCreate, ScanOut, SessionCreate, SessionOut
from leltariv_domain.normalization import normalize_code
from leltariv_domain.scanning import CodeMatch, resolve, scan_message
from leltariv_infrastructure.db.models import (
    AppUser,
    Asset,
    AssetCode,
    InventoryPeriod,
    InventorySession,
    InventoryZone,
    Scan,
)
from leltariv_infrastructure.db.session import get_db_session
from sqlalchemy import select
from sqlalchemy.orm import Session

from leltariv_server.api.assets import asset_list_item, primary_inventory_numbers
from leltariv_server.dependencies import require_current_user

router = APIRouter(prefix="/api/v1", tags=["inventory"])


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

    started_at = datetime.now(UTC)
    inventory_session = InventorySession(
        period_id=period.id,
        zone_id=zone.id,
        user_id=current_user.id,
        started_at=started_at,
    )
    session.add(inventory_session)
    session.commit()
    session.refresh(inventory_session)

    return SessionOut(
        id=inventory_session.id,
        zone_code=zone.code,
        period_name=period.name or "",
        started_at=inventory_session.started_at or started_at,
    )


@router.post(
    "/sessions/{session_id}/scans",
    response_model=ScanOut,
    status_code=status.HTTP_201_CREATED,
    summary="Beolvasott kód rögzítése",
)
def create_scan(
    session_id: UUID,
    request: ScanCreate,
    current_user: AppUser = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> ScanOut:
    inventory_session = session.get(InventorySession, session_id)
    if inventory_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A megadott munkamenet nem található.",
        )

    active_zone = session.get(InventoryZone, inventory_session.zone_id)
    if active_zone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A munkamenet körzete nem található.",
        )

    normalized_code = normalize_code(request.raw_code)

    match_rows = session.execute(
        select(AssetCode.asset_id, InventoryZone.code)
        .join(InventoryZone, AssetCode.zone_id == InventoryZone.id)
        .where(AssetCode.code_normalized == normalized_code)
    ).all()

    matches = [
        CodeMatch(asset_id=asset_id, zone_code=zone_code) for asset_id, zone_code in match_rows
    ]

    result, asset_id = resolve(matches, active_zone.code)

    asset: Asset | None = None
    asset_zone_code: str | None = None
    if asset_id is not None:
        asset = session.get(Asset, asset_id)
        if asset is not None and asset.zone_id is not None:
            asset_zone = session.get(InventoryZone, asset.zone_id)
            asset_zone_code = asset_zone.code if asset_zone is not None else None

    scan = Scan(
        session_id=inventory_session.id,
        asset_id=asset_id,
        raw_code=request.raw_code,
        code_normalized=normalized_code,
        result=result,
        scanned_by=current_user.id,
    )
    session.add(scan)
    session.commit()
    session.refresh(scan)

    asset_out = None
    if asset is not None:
        primary_codes = primary_inventory_numbers(session, [asset.id])
        asset_out = asset_list_item(asset, asset_zone_code, primary_codes)

    return ScanOut(
        id=scan.id,
        raw_code=scan.raw_code,
        result=result,
        scanned_at=scan.scanned_at,
        asset=asset_out,
        message=scan_message(
            result,
            raw_code=request.raw_code,
            asset_name=asset.name if asset is not None else None,
            asset_zone_code=asset_zone_code,
        ),
    )
