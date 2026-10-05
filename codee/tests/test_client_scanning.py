# A pytest-qt qtbot metódusai tipizálatlanok; a kliens többi részéhez hasonlóan itt sem strict.
# pyright: reportUnknownMemberType=false

import threading
from datetime import UTC, datetime
from uuid import UUID, uuid4

from leltariv_client.pages.scanning import ScanningPage
from leltariv_contracts.assets import AssetPage
from leltariv_contracts.inventory import ScanOut, SessionOut
from leltariv_contracts.zones import ZoneOut
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot


class CountingApi:
    """Álkliens: feljegyzi, milyen kódok mentek ki, és a beolvasást vissza is tudja tartani."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.release = threading.Event()
        self.release.set()

    def get_zones(self, token: str) -> list[ZoneOut]:
        return [ZoneOut(id=1, code="261", name="A"), ZoneOut(id=2, code="262", name="B")]

    def get_assets(self, *args: object) -> AssetPage:
        return AssetPage(items=[], total=0, page=1, page_size=50)

    def start_session(self, token: str, zone_code: str) -> SessionOut:
        return SessionOut(
            id=uuid4(), zone_code=zone_code, period_name="2026. évi leltár", started_at=now()
        )

    def post_scan(self, token: str, session_id: UUID, raw_code: str) -> ScanOut:
        self.release.wait(timeout=5)
        self.sent.append(raw_code)
        return ScanOut(
            id=uuid4(),
            raw_code=raw_code,
            result="UNKNOWN_CODE",
            scanned_at=now(),
            message=f"Ismeretlen kód: {raw_code}.",
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
    return page


def test_enter_sends_once_and_clears_field(qtbot: QtBot) -> None:
    api = CountingApi()
    page = started_page(qtbot, api)

    qtbot.keyClicks(page.scan_input, " 032268 ")
    qtbot.keyClick(page.scan_input, Qt.Key.Key_Return)

    assert page.scan_input.text() == ""
    qtbot.waitUntil(lambda: page.recent.count() == 1)
    assert api.sent == ["032268"]
    assert page.scan_input.hasFocus()


def test_fast_codes_go_out_in_order(qtbot: QtBot) -> None:
    api = CountingApi()
    page = started_page(qtbot, api)
    api.release.clear()  # az első kérés úton marad, a többi sorba áll

    for code in ("111", "222", "333"):
        qtbot.keyClicks(page.scan_input, code)
        qtbot.keyClick(page.scan_input, Qt.Key.Key_Return)

    assert list(page.pending) == ["222", "333"]
    api.release.set()
    qtbot.waitUntil(lambda: page.recent.count() == 3)
    assert api.sent == ["111", "222", "333"]


def test_empty_enter_is_dropped(qtbot: QtBot) -> None:
    api = CountingApi()
    page = started_page(qtbot, api)

    qtbot.keyClicks(page.scan_input, "   ")
    qtbot.keyClick(page.scan_input, Qt.Key.Key_Return)

    assert not page.busy
    assert api.sent == []
