"""Felelős személyek és az eszköz felelősének váltása."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from leltariv_contracts.assets import AssetDetail, PersonOut, ResponsibleSet
from leltariv_infrastructure.db.models import AppUser, Asset, AssetResponsible, Person
from leltariv_infrastructure.db.session import get_db_session
from sqlalchemy import select
from sqlalchemy.orm import Session

from leltariv_server.api.assets import asset_detail
from leltariv_server.dependencies import require_current_user

router = APIRouter(prefix="/api/v1", tags=["persons"])


@router.get(
    "/persons",
    response_model=list[PersonOut],
    summary="Felelős személyek név szerint",
)
def list_persons(
    _current_user: object = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> list[PersonOut]:
    persons = session.scalars(select(Person).order_by(Person.name)).all()
    return [PersonOut(id=p.id, name=p.name, org_unit=p.org_unit) for p in persons]


@router.put(
    "/assets/{asset_id}/responsible",
    response_model=AssetDetail,
    summary="Eszköz felelősének váltása; a régi kapcsolat lezárul, nem íródik felül",
)
def set_responsible(
    asset_id: UUID,
    payload: ResponsibleSet,
    current_user: AppUser = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> AssetDetail:
    if session.get(Asset, asset_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A megadott eszköz nem található.",
        )
    if session.get(Person, payload.person_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A megadott személy nem található.",
        )

    current = session.scalar(
        select(AssetResponsible).where(
            AssetResponsible.asset_id == asset_id,
            AssetResponsible.valid_to.is_(None),
        )
    )
    if current is not None and current.person_id == payload.person_id:
        return asset_detail(session, asset_id)

    # Egy commitban: a régi sor lezárul, az új megnyílik. Ha közben más is váltott, a
    # részleges egyedi index miatt a második nyitott sor nem jöhet létre.
    now = datetime.now(UTC)
    if current is not None:
        current.valid_to = now
        session.flush()
    session.add(
        AssetResponsible(
            asset_id=asset_id,
            person_id=payload.person_id,
            valid_from=now,
            assigned_by=current_user.id,
        )
    )
    session.commit()

    return asset_detail(session, asset_id)
