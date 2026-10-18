import pytest
from leltariv_infrastructure.db.models import Room
from leltariv_server.api.rooms import room_label


@pytest.mark.parametrize(
    ("room_number", "name", "expected"),
    [
        ("G-210", "Labor", "G-210 · Labor"),
        ("I-101", "Iroda", "I-101 · Iroda"),
        ("G-012", "Műhely", "G-012 · Műhely"),
        ("G-105", None, "G-105"),
        ("G-105", "", "G-105"),
    ],
)
def test_room_label(
    room_number: str,
    name: str | None,
    expected: str,
) -> None:
    room = Room(
        zone_id=1,
        room_number=room_number,
        name=name,
    )

    assert room_label(room) == expected
