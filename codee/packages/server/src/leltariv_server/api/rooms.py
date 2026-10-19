"""Helyiségek végpontjai és közös megjelenítési segédfüggvénye."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from leltariv_contracts.rooms import RoomCreate, RoomOut
from leltariv_infrastructure.db.models import InventoryZone, Room
from leltariv_infrastructure.db.session import get_db_session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from leltariv_server.dependencies import require_current_user

router = APIRouter(prefix="/api/v1", tags=["rooms"])


def room_label(room: Room) -> str:
    """Ajtószám, illetve megadott név esetén „ajtószám · név” címke."""
    room_number = room.room_number or ""
    if room.name:
        return f"{room_number} · {room.name}"
    return room_number


def room_out(room: Room, zone_code: str) -> RoomOut:
    """Adatbázis-helyiségből a válaszmodellnek megfelelő objektumot épít."""
    return RoomOut(
        id=room.id,
        zone_code=zone_code,
        room_number=room.room_number or "",
        name=room.name,
        label=room_label(room),
    )


@router.get(
    "/rooms",
    response_model=list[RoomOut],
    summary="Egy körzet helyiségeinek lekérdezése ajtószám szerint",
)
def list_rooms(
    zone: str = Query(description="A körzet kódja, például: 262."),
    _current_user: object = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> list[RoomOut]:
    inventory_zone = session.scalar(select(InventoryZone).where(InventoryZone.code == zone))

    if inventory_zone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A megadott körzet nem található.",
        )

    rooms = session.scalars(
        select(Room).where(Room.zone_id == inventory_zone.id).order_by(Room.room_number, Room.id)
    ).all()

    return [room_out(room, inventory_zone.code) for room in rooms]


@router.post(
    "/rooms",
    response_model=RoomOut,
    status_code=status.HTTP_201_CREATED,
    summary="Új helyiség létrehozása egy körzetben",
)
def create_room(
    payload: RoomCreate,
    _current_user: object = Depends(require_current_user),  # noqa: B008
    session: Session = Depends(get_db_session),  # noqa: B008
) -> RoomOut:
    inventory_zone = session.scalar(
        select(InventoryZone).where(InventoryZone.code == payload.zone_code)
    )

    if inventory_zone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A megadott körzet nem található.",
        )

    room_number = payload.room_number.strip()

    if not room_number:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Az ajtószám nem lehet üres.",
        )

    name = payload.name.strip() if payload.name is not None else None

    room = Room(
        zone_id=inventory_zone.id,
        room_number=room_number,
        name=name or None,
    )
    session.add(room)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()

        if getattr(exc.orig, "sqlstate", None) != "23505":
            raise

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ebben a körzetben már van ilyen helyiség.",
        ) from exc

    session.refresh(room)

    return room_out(room, inventory_zone.code)
