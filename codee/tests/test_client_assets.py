# A pytest-qt qtbot metódusai tipizálatlanok; a kliens többi részéhez hasonlóan itt sem strict.
# pyright: reportUnknownMemberType=false

import threading
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from leltariv_client.app import MainWindow
from leltariv_client.dialogs import AssetDetailDialog
from leltariv_contracts.assets import (
    AssetDetail,
    AssetListItem,
    AssetPage,
    AssetTypeOut,
    PersonOut,
)
from leltariv_contracts.inventory import SessionOut
from leltariv_contracts.rooms import RoomOut
from leltariv_contracts.zones import ZoneOut
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

ASSET_ID = uuid4()
ANNA = PersonOut(id=uuid4(), name="Teszt Anna")
BELA = PersonOut(id=uuid4(), name="Teszt Béla")


class FakeApi:
    """Álkliens az eszközlistához és az adatlaphoz; a személyek válaszát vissza is tudja tartani."""

    def __init__(self) -> None:
        self.types = [AssetTypeOut(id=1, name="Bútor"), AssetTypeOut(id=2, name="Egyéb")]
        self.responsible: PersonOut | None = ANNA
        self.asset_type_id = 1
        self.persons_release = threading.Event()
        self.persons_release.set()
        self.saved_types: list[int] = []
        self.saved_persons: list[UUID] = []

    def get_zones(self, token: str) -> list[ZoneOut]:
        return [ZoneOut(id=1, code="262", name="B")]

    def get_rooms(self, token: str, zone_code: str) -> list[RoomOut]:
        return []

    def get_asset_types(self, token: str) -> list[AssetTypeOut]:
        return list(self.types)

    def create_asset_type(self, token: str, name: str) -> AssetTypeOut:
        new = AssetTypeOut(id=len(self.types) + 1, name=name)
        self.types.append(new)
        return new

    def get_persons(self, token: str) -> list[PersonOut]:
        self.persons_release.wait(timeout=5)
        # mindig új objektumok, ahogy a szerver válaszából
        return [PersonOut.model_validate(p.model_dump()) for p in (ANNA, BELA)]

    def get_assets(self, *args: object, **kwargs: object) -> AssetPage:
        item = AssetListItem(
            id=ASSET_ID, asset_number="1", sub_number=0, name="Szék", zone_code="262"
        )
        return AssetPage(items=[item], total=1, page=1, page_size=50)

    def get_asset(self, token: str, asset_id: UUID) -> AssetDetail:
        type_name = next(t.name for t in self.types if t.id == self.asset_type_id)
        responsible = (
            PersonOut.model_validate(self.responsible.model_dump()) if self.responsible else None
        )
        return AssetDetail(
            id=asset_id,
            asset_number="1",
            sub_number=0,
            name="Szék",
            zone_code="262",
            quantity=1,
            asset_type=type_name,
            asset_type_id=self.asset_type_id,
            responsible=responsible,
            codes=[],
            accessories=[],
        )

    def set_asset_type(self, token: str, asset_id: UUID, asset_type_id: int) -> AssetDetail:
        self.saved_types.append(asset_type_id)
        self.asset_type_id = asset_type_id
        return self.get_asset(token, asset_id)

    def set_responsible(self, token: str, asset_id: UUID, person_id: UUID) -> AssetDetail:
        self.saved_persons.append(person_id)
        self.responsible = next(p for p in (ANNA, BELA) if p.id == person_id)
        return self.get_asset(token, asset_id)

    def start_session(self, token: str, zone_code: str) -> SessionOut:
        return SessionOut(
            id=uuid4(), zone_code=zone_code, period_name="2026", started_at=datetime.now(UTC)
        )


@pytest.fixture(autouse=True)
def no_message_boxes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    shown: list[str] = []

    def record(*args: object, **_kwargs: object) -> None:
        shown.append(str(args[2]))

    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, record)
    return shown


def open_dialog(qtbot: QtBot, api: FakeApi) -> AssetDetailDialog:
    dialog = AssetDetailDialog(api, "token", ASSET_ID)
    qtbot.addWidget(dialog)
    dialog.show()
    return dialog


def test_list_loads_after_login_without_touching_filters(qtbot: QtBot) -> None:
    window = MainWindow(FakeApi(), "token", "Teszt", "ADMIN")
    qtbot.addWidget(window)

    qtbot.waitUntil(lambda: window.model.rowCount() == 1)


def test_detail_shows_current_responsible_even_if_persons_arrive_late(qtbot: QtBot) -> None:
    api = FakeApi()
    api.persons_release.clear()  # az adatlap előbb ér vissza, mint a személyek
    dialog = open_dialog(qtbot, api)
    qtbot.waitUntil(lambda: dialog.current_detail is not None)

    api.persons_release.set()
    qtbot.waitUntil(lambda: dialog.resp_combo.count() == 3)
    assert dialog.resp_combo.currentText() == "Teszt Anna"
    assert dialog.type_combo.currentText() == "Bútor"


def test_saving_responsible_keeps_dialog_open(qtbot: QtBot) -> None:
    api = FakeApi()
    dialog = open_dialog(qtbot, api)
    qtbot.waitUntil(lambda: dialog.resp_combo.currentText() == "Teszt Anna")

    dialog.resp_combo.setCurrentIndex(dialog.resp_combo.findText("Teszt Béla"))
    dialog.save_responsible()

    qtbot.waitUntil(lambda: api.saved_persons == [BELA.id])
    qtbot.waitUntil(lambda: dialog.saved)
    assert dialog.isVisible()
    assert dialog.resp_combo.currentText() == "Teszt Béla"


def test_new_type_is_selected_and_saved(qtbot: QtBot) -> None:
    api = FakeApi()
    dialog = open_dialog(qtbot, api)
    qtbot.waitUntil(lambda: dialog.current_detail is not None)

    new_type = api.create_asset_type("token", "Laborpad")
    dialog.on_new_type_created(new_type)

    qtbot.waitUntil(lambda: api.saved_types == [new_type.id])
    qtbot.waitUntil(lambda: dialog.type_combo.currentText() == "Laborpad")
