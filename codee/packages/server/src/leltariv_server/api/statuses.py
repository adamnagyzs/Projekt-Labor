"""Eszközállapot váltása az állapotnaplón keresztül."""

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from leltariv_contracts.assets import AssetStatus, StatusChangeCreate, StatusChangeOut
from leltariv_infrastructure.db.models import AppUser, Asset, AssetStatusChange
from leltariv_infrastructure.db.session import get_db_session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from leltariv_server.dependencies import require_current_user

router = APIRouter(prefix="/api/v1", tags=["statuses"])


@router.patch(
    "/assets/{asset_id}/status",
    response_model=StatusChangeOut,
    status_code=status.HTTP_200_OK,
    summary="Eszköz állapotának váltása indoklással",
)
def change_asset_status(
    asset_id: UUID,
    request: StatusChangeCreate,
    current_user: AppUser = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> StatusChangeOut:
    if current_user.role == "OLVASO":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Állapotot csak leltározó vagy rendszergazda válthat.",
        )

    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Az eszköz nem található.",
        )

    change = AssetStatusChange(
        asset_id=asset.id,
        old_status=asset.status,
        new_status=request.status,
        reason=request.reason.strip(),
        changed_by=current_user.id,
    )
    session.add(change)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Az eszköz már ebben az állapotban van, vagy közben valaki módosította.",
        ) from error

    session.refresh(change)
    return StatusChangeOut(
        id=change.id,
        asset_id=change.asset_id,
        old_status=cast(AssetStatus, change.old_status),
        new_status=cast(AssetStatus, change.new_status),
        reason=change.reason,
        changed_at=change.changed_at,
        changed_by=current_user.display_name,
    )
