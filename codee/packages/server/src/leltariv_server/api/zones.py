from typing import Annotated

from fastapi import APIRouter, Depends, Header
from leltariv_contracts.zones import ZoneOut
from leltariv_infrastructure.db.models import AppUser, InventoryZone
from leltariv_infrastructure.db.session import get_db_session
from sqlalchemy import select
from sqlalchemy.orm import Session

from leltariv_server.services.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["zones"])


def require_current_user(
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_db_session),  # noqa: B008
) -> AppUser:
    return get_current_user(authorization, session)


@router.get(
    "/zones",
    response_model=list[ZoneOut],
    summary="Leltárkörzetek lekérdezése",
)
def list_zones(
    _current_user: AppUser = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> list[ZoneOut]:
    """A tokennel elérhető leltárkörzetek listája."""
    zones = session.scalars(select(InventoryZone).order_by(InventoryZone.code)).all()

    return [
        ZoneOut(
            id=zone.id,
            code=zone.code,
            name=zone.name or zone.code,
        )
        for zone in zones
    ]
