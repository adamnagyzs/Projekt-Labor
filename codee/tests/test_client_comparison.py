# A pytest-qt qtbot metódusai tipizálatlanok; a kliens többi részéhez hasonlóan itt sem strict.
# pyright: reportUnknownMemberType=false

from datetime import UTC, datetime
from uuid import UUID, uuid4

from leltariv_client.pages.comparison import ComparisonPage
from leltariv_contracts.assets import AssetListItem
from leltariv_contracts.inventory import (
    ComparisonCategory,
    ComparisonOut,
    ComparisonRow,
    ComparisonSummary,
    ForeignFind,
    PeriodOut,
    PeriodState,
    UnknownCode,
    Verification,
)
from leltariv_contracts.zones import ZoneOut
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem
from pytestqt.qtbot import QtBot


def _asset(number: str, name: str, zone: str = "262") -> AssetListItem:
    return AssetListItem(
        id=uuid4(),
        asset_number=number,
        sub_number=0,
        name=name,
        zone_code=zone,
        inventory_number=number,
    )


def _row(
    category: ComparisonCategory,
    expected: int,
    counted: int,
    verification: Verification | None = None,
) -> ComparisonRow:
    return ComparisonRow(
        asset=_asset(f"{category}-1", f"{category} eszköz"),
        status="ACTIVE",
        expected=expected,
        counted=counted,
        difference=counted - expected,
        category=category,
        verification=verification,
    )


class FakeApi:
    """Egy időszak, egy körzet, és minden fülre legalább egy sor."""

    def __init__(self, state: PeriodState = "ACTIVE") -> None:
        self.period = PeriodOut(
            id=uuid4(),
            name="2026. évi leltár",
            year=2026,
            state=state,
            opened_at=datetime.now(UTC),
            closed_at=datetime.now(UTC) if state == "CLOSED" else None,
        )
        self.rows = [
            _row("MISSING", 1, 0),
            _row("PARTIAL", 31, 27, "DIRECT"),
            _row("FOUND", 1, 1, "DIRECT"),
            _row("FOUND", 1, 0, "INHERITED"),
        ]
        self.requested: list[tuple[UUID, str]] = []

    def get_periods(self, token: str) -> list[PeriodOut]:
        return [self.period]

    def get_zones(self, token: str) -> list[ZoneOut]:
        return [ZoneOut(id=1, code="262", name="B")]

    def get_comparison(self, token: str, period_id: UUID, zone_code: str) -> ComparisonOut:
        self.requested.append((period_id, zone_code))
        return ComparisonOut(
            period=self.period,
            zone_code=zone_code,
            summary=ComparisonSummary(
                expected_assets=4,
                found=2,
                inherited=1,
                partial=1,
                missing=1,
                surplus=0,
                foreign=1,
                unknown=1,
                progress_percent=75.0,
            ),
            rows=self.rows,
            foreign=[
                ForeignFind(
                    asset=_asset("005071", "Tábla", "261"), home_zone_code="261", quantity=1
                )
            ],
            unknown=[UnknownCode(raw_code="XYZ-NINCS", quantity=1)],
        )


def test_page_loads_active_period_and_fills_every_tab(qtbot: QtBot) -> None:
    api = FakeApi()
    page = ComparisonPage(api, "token")
    qtbot.addWidget(page)

    qtbot.waitUntil(lambda: "Nyilvántartott: 4" in page.summary_label.text())
    assert api.requested == [(api.period.id, "262")]
    assert [page.tabs.tabText(i) for i in range(page.tabs.count())] == [
        "Hiányzik (1)",
        "Részleges és többlet (1)",
        "Megtalált (2)",
        "Más körzetből (1)",
        "Ismeretlen kód (1)",
    ]
    assert page.progress_bar.value() == 75
    assert page.closed_badge_label.text() == ""


def test_found_tab_marks_accessory_found_by_its_main_asset(qtbot: QtBot) -> None:
    api = FakeApi()
    page = ComparisonPage(api, "token")
    qtbot.addWidget(page)
    qtbot.waitUntil(lambda: page.tab_found.rowCount() == 2)

    def cell(row: int, col: int) -> QTableWidgetItem:
        item = page.tab_found.item(row, col)
        assert item is not None
        return item

    assert [cell(r, 3).text() for r in range(2)] == ["közvetlen", "főeszköz alapján"]
    # a dupla kattintás az eszköz azonosítóját a leltárszám cellájából veszi
    assert cell(0, 0).data(Qt.ItemDataRole.UserRole) == api.rows[2].asset.id


def test_closed_period_shows_that_the_result_is_final(qtbot: QtBot) -> None:
    page = ComparisonPage(FakeApi(state="CLOSED"), "token")
    qtbot.addWidget(page)

    qtbot.waitUntil(lambda: page.closed_badge_label.text() != "")
    assert "végleges" in page.closed_badge_label.text()
