from dataclasses import dataclass

from leltariv_client.pages.rooms import RoomsPage
from pytestqt.qtbot import QtBot


@dataclass(frozen=True)
class DemoZone:
    code: str
    name: str


@dataclass(frozen=True)
class DemoRoom:
    room_number: str
    name: str | None


class RoomsTestApi:
    def __init__(self) -> None:
        self.rooms: dict[str, list[DemoRoom]] = {
            "261": [],
            "262": [
                DemoRoom(room_number="G-210", name="Labor"),
            ],
        }

    def get_zones(self, token: str) -> list[DemoZone]:
        return [
            DemoZone(code="261", name="Leltárkörzet 261"),
            DemoZone(code="262", name="Leltárkörzet 262"),
        ]

    def get_rooms(self, token: str, zone_code: str) -> list[DemoRoom]:
        return list(self.rooms[zone_code])

    def create_room(
        self,
        token: str,
        zone_code: str,
        room_number: str,
        name: str | None,
    ) -> DemoRoom:
        if any(room.room_number == room_number for room in self.rooms[zone_code]):
            raise ValueError("Ebben a körzetben már van ilyen helyiség.")

        room = DemoRoom(room_number=room_number, name=name)
        self.rooms[zone_code].append(room)
        return room


def open_262(qtbot: QtBot) -> RoomsPage:
    page = RoomsPage(RoomsTestApi(), "test-token")
    qtbot.addWidget(page)
    page.show()

    qtbot.waitUntil(lambda: page.zone_combo.count() == 2 and page.zone_combo.isEnabled())

    index = page.zone_combo.findData("262")
    assert index >= 0
    page.zone_combo.setCurrentIndex(index)

    qtbot.waitUntil(lambda: page.add_button.isEnabled() and page.table.rowCount() == 1)
    return page


def cell_text(page: RoomsPage, row: int, column: int) -> str:
    item = page.table.item(row, column)
    assert item is not None, f"Hiányzó táblázatcella: {row}, {column}"
    return item.text()


def test_rooms_are_loaded_for_selected_zone(qtbot: QtBot) -> None:
    page = open_262(qtbot)

    assert cell_text(page, 0, 0) == "G-210"
    assert cell_text(page, 0, 1) == "Labor"


def test_create_room_reloads_table_and_clears_inputs(qtbot: QtBot) -> None:
    page = open_262(qtbot)
    page.room_number_input.setText("G-105")
    page.name_input.setText("Tárgyaló")
    page.add_button.click()

    qtbot.waitUntil(lambda: page.add_button.isEnabled() and page.table.rowCount() == 2)

    assert cell_text(page, 0, 0) == "G-105"
    assert cell_text(page, 0, 1) == "Tárgyaló"
    assert page.room_number_input.text() == ""
    assert page.name_input.text() == ""


def test_duplicate_room_displays_error_and_keeps_inputs(
    qtbot: QtBot,
) -> None:
    page = open_262(qtbot)
    page.room_number_input.setText("G-210")
    page.name_input.setText("Másik labor")
    page.add_button.click()

    qtbot.waitUntil(lambda: bool(page.error_label.text()))

    assert page.error_label.text() == ("Ebben a körzetben már van ilyen helyiség.")
    assert page.room_number_input.text() == "G-210"
    assert page.name_input.text() == "Másik labor"
    assert page.table.rowCount() == 1


def test_empty_room_number_is_rejected(qtbot: QtBot) -> None:
    page = open_262(qtbot)
    page.room_number_input.setText("   ")
    page.add_button.click()

    assert page.error_label.text() == "Az ajtószám megadása kötelező."
    assert page.table.rowCount() == 1
