# A pytest-qt qtbot metódusai tipizálatlanok; a kliens többi részéhez hasonlóan itt sem strict.
# pyright: reportUnknownMemberType=false

import threading
from datetime import UTC, datetime
from uuid import UUID, uuid4

from leltariv_client.pages.scanning import ScanningPage
from leltariv_contracts.assets import AssetPage
from leltariv_contracts.inventory import ScanOut, ScanResult, SessionOut
from leltariv_contracts.rooms import RoomOut
from leltariv_contracts.zones import ZoneOut
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

ROOM_A = RoomOut(id=uuid4(), zone_code="261", room_number="I-101", label="I-101")
ROOM_B = RoomOut(id=uuid4(), zone_code="261", room_number="I-217", label="I-217")


class CountingApi:
    """Álkliens: feljegyzi, milyen kérések mentek ki, és a választ vissza is tudja tartani."""

    def __init__(self, result: ScanResult = "UNKNOWN_CODE") -> None:
        self.result: ScanResult = result
        #: (kód, darab, helyiség) beolvasásonként, ("undo", scan_id) visszavonásonként
        self.sent: list[tuple[object, ...]] = []
        self.closed = False
        self.release = threading.Event()
        self.release.set()

    def get_zones(self, token: str) -> list[ZoneOut]:
        return [ZoneOut(id=1, code="261", name="A"), ZoneOut(id=2, code="262", name="B")]

    def get_assets(self, *args: object) -> AssetPage:
        return AssetPage(items=[], total=0, page=1, page_size=50)

    def get_rooms(self, token: str, zone_code: str) -> list[RoomOut]:
        return [ROOM_A, ROOM_B]

    def start_session(self, token: str, zone_code: str) -> SessionOut:
        return SessionOut(
            id=uuid4(), zone_code=zone_code, period_name="2026. évi leltár", started_at=now()
        )

    def post_scan(
        self,
        token: str,
        session_id: UUID,
        raw_code: str,
        quantity: int = 1,
        room_id: UUID | None = None,
    ) -> ScanOut:
        self.release.wait(timeout=5)
        self.sent.append((raw_code, quantity, room_id))
        return ScanOut(
            id=uuid4(),
            raw_code=raw_code,
            result=self.result,
            scanned_at=now(),
            message=f"Válasz: {raw_code}.",
            quantity=quantity,
        )

    def undo_scan(self, token: str, session_id: UUID, scan_id: UUID) -> ScanOut:
        self.release.wait(timeout=5)
        self.sent.append(("undo", scan_id))
        return ScanOut(
            id=uuid4(),
            raw_code="x",
            result=self.result,
            scanned_at=now(),
            message="Visszavonva: x, 1 db.",
            quantity=-1,
            compensates_scan_id=scan_id,
        )

    def close_session(self, token: str, session_id: UUID) -> SessionOut:
        self.closed = True
        return SessionOut(
            id=session_id,
            zone_code="261",
            period_name="2026. évi leltár",
            started_at=now(),
            closed_at=now(),
        )


def now() -> datetime:
    return datetime.now(UTC)


def started_page(qtbot: QtBot, api: CountingApi) -> ScanningPage:
    page = ScanningPage(api, "token")
    qtbot.addWidget(page)
    page.show()
    qtbot.waitUntil(lambda: page.start_button.isEnabled())
    qtbot.mouseClick(page.start_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: page.session is not None)
    qtbot.waitUntil(lambda: page.room_combo.count() == 3)
    return page


def scan(qtbot: QtBot, page: ScanningPage, code: str) -> None:
    qtbot.keyClicks(page.scan_input, code)
    qtbot.keyClick(page.scan_input, Qt.Key.Key_Return)


def test_enter_sends_once_and_clears_field(qtbot: QtBot) -> None:
    api = CountingApi()
    page = started_page(qtbot, api)

    scan(qtbot, page, " 032268 ")

    assert page.scan_input.text() == ""
    qtbot.waitUntil(lambda: page.recent.count() == 1)
    assert api.sent == [("032268", 1, None)]
    assert page.scan_input.hasFocus()


def test_fast_codes_go_out_in_order(qtbot: QtBot) -> None:
    api = CountingApi()
    page = started_page(qtbot, api)
    api.release.clear()  # az első kérés úton marad, a többi sorba áll

    for code in ("111", "222", "333"):
        scan(qtbot, page, code)

    assert [request.code for request in page.pending] == ["222", "333"]  # type: ignore[union-attr]
    api.release.set()
    qtbot.waitUntil(lambda: page.recent.count() == 3)
    assert [sent[0] for sent in api.sent] == ["111", "222", "333"]


def test_empty_enter_is_dropped(qtbot: QtBot) -> None:
    api = CountingApi()
    page = started_page(qtbot, api)

    scan(qtbot, page, "   ")

    assert not page.busy
    assert api.sent == []


def test_room_change_does_not_rewrite_queued_codes(qtbot: QtBot) -> None:
    api = CountingApi()
    page = started_page(qtbot, api)
    api.release.clear()

    page.room_combo.setCurrentIndex(1)  # I-101
    scan(qtbot, page, "111")  # úton
    scan(qtbot, page, "222")  # sorban, még az I-101-gyel
    page.room_combo.setCurrentIndex(2)  # átállás az I-217-re
    scan(qtbot, page, "333")

    api.release.set()
    qtbot.waitUntil(lambda: len(api.sent) == 3)
    assert api.sent == [("111", 1, ROOM_A.id), ("222", 1, ROOM_A.id), ("333", 1, ROOM_B.id)]


def test_quantity_is_sent_and_resets(qtbot: QtBot) -> None:
    api = CountingApi()
    page = started_page(qtbot, api)

    page.quantity_input.setValue(27)
    scan(qtbot, page, "024540")

    assert page.quantity_input.value() == 1
    qtbot.waitUntil(lambda: len(api.sent) == 1)
    assert api.sent == [("024540", 27, None)]


def test_surplus_gets_its_own_label(qtbot: QtBot) -> None:
    api = CountingApi(result="SURPLUS")
    page = started_page(qtbot, api)

    scan(qtbot, page, "024540")

    qtbot.waitUntil(lambda: page.recent.count() == 1)
    assert "TÖBBLET" in page.feedback.text()


def test_undo_waits_behind_queued_scans(qtbot: QtBot) -> None:
    api = CountingApi(result="FOUND")
    page = started_page(qtbot, api)
    scan(qtbot, page, "000")
    qtbot.waitUntil(lambda: page.recent.count() == 1)
    page.recent.setCurrentRow(0)
    first_id = page.recent.item(0).data(Qt.ItemDataRole.UserRole)

    api.release.clear()
    scan(qtbot, page, "111")  # úton
    scan(qtbot, page, "222")  # sorban
    page.undo_selected()  # a 222 mögé áll, nem előzi meg

    api.release.set()
    qtbot.waitUntil(lambda: len(api.sent) == 4)
    assert [sent[0] for sent in api.sent] == ["000", "111", "222", "undo"]
    assert api.sent[3] == ("undo", first_id)


def test_finish_closes_after_queue_drains(qtbot: QtBot) -> None:
    api = CountingApi()
    page = started_page(qtbot, api)
    api.release.clear()
    scan(qtbot, page, "111")

    page.finish_session()
    assert not api.closed  # a 111 még úton van

    api.release.set()
    qtbot.waitUntil(lambda: page.session is None)
    assert api.closed
    assert [sent[0] for sent in api.sent] == ["111"]
