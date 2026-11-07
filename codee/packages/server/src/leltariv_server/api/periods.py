"""Leltári időszakok: nyitás, lezárás, és egy időszak összehasonlítása körzetenként.

A szabályokat az adatbázis tartja (egy aktív időszak, a lezárt végleges, lezárt
időszakba nem kerül munkamenet). A végpont a megkötés hibájából ad 409-et, előzetes
ellenőrzés nélkül, így két egyidejű kérésnél is helyes.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from leltariv_contracts.inventory import ComparisonOut, PeriodCreate, PeriodOut
from leltariv_infrastructure.db.models import (
    AppUser,
    InventoryPeriod,
    InventorySession,
    InventoryZone,
)
from leltariv_infrastructure.db.session import get_db_session
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from leltariv_server.dependencies import require_admin, require_current_user
from leltariv_server.services.comparison import build_comparison, period_out

router = APIRouter(prefix="/api/v1", tags=["periods"])


def get_period(session: Session, period_id: UUID) -> InventoryPeriod:
    period = session.get(InventoryPeriod, period_id)
    if period is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A leltári időszak nem található.",
        )
    return period


@router.get(
    "/periods",
    response_model=list[PeriodOut],
    summary="A leltári időszakok, a legújabb elöl",
)
def list_periods(
    _current_user: AppUser = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> list[PeriodOut]:
    periods = session.scalars(
        select(InventoryPeriod).order_by(InventoryPeriod.opened_at.desc().nulls_last())
    ).all()
    return [period_out(period) for period in periods]


@router.post(
    "/periods",
    response_model=PeriodOut,
    status_code=status.HTTP_201_CREATED,
    summary="Új leltári időszak nyitása (csak ha nincs másik aktív)",
)
def create_period(
    request: PeriodCreate,
    _admin: AppUser = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> PeriodOut:
    period = InventoryPeriod(
        name=request.name.strip(),
        year=request.year,
        state="ACTIVE",
        opened_at=datetime.now(UTC),
    )
    session.add(period)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Már van aktív leltári időszak; előbb azt zárd le.",
        ) from error
    session.refresh(period)
    return period_out(period)


@router.post(
    "/periods/{period_id}/close",
    response_model=PeriodOut,
    summary="Az időszak lezárása; a nyitott munkamenetei is lezárulnak",
)
def close_period(
    period_id: UUID,
    _admin: AppUser = Depends(require_admin),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> PeriodOut:
    period = get_period(session, period_id)
    if period.state != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Csak aktív időszak zárható le.",
        )

    now = datetime.now(UTC)
    session.execute(
        update(InventorySession)
        .where(InventorySession.period_id == period.id, InventorySession.closed_at.is_(None))
        .values(closed_at=now)
    )
    period.state = "CLOSED"
    period.closed_at = now
    try:
        session.commit()
    except IntegrityError as error:
        # Közben nyílt egy munkamenet, vagy valaki más már lezárta: a trigger megállít.
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Az időszakot közben módosították; próbáld újra.",
        ) from error
    session.refresh(period)
    return period_out(period)


@router.get(
    "/periods/{period_id}/comparison",
    response_model=ComparisonOut,
    summary="Nyilvántartás és leltár összevetése egy körzetben",
)
def get_comparison(
    period_id: UUID,
    zone_code: str = Query(min_length=1),
    _current_user: AppUser = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> ComparisonOut:
    period = get_period(session, period_id)
    zone = session.scalar(select(InventoryZone).where(InventoryZone.code == zone_code))
    if zone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A megadott körzet nem található.",
        )
    return build_comparison(session, period, zone)
