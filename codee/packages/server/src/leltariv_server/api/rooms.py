"""Helyiségek közös megjelenítési segédfüggvényei."""

from leltariv_infrastructure.db.models import Room


def room_label(room: Room) -> str:
    """Ajtószám, illetve megadott név esetén „ajtószám · név” címke."""
    room_number = room.room_number or ""
    if room.name:
        return f"{room_number} · {room.name}"
    return room_number
