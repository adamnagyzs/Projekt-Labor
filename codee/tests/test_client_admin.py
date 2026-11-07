from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from leltariv_client.pages.admin import AdminPage
from leltariv_contracts.admin import RestoreResult, SnapshotOut
from leltariv_contracts.inventory import PeriodOut
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot


class AdminTestApi:
    def __init__(self) -> None:
        self.snapshots = [
            SnapshotOut(
                file_name="2026-10-20_10-00-00_kezdo.json",
                created_at=datetime(2026, 10, 20, 8, 0, tzinfo=UTC),
                size_bytes=3 * 1024 * 1024,
            )
        ]
        self.restored: list[str] = []
        self.periods = [
            PeriodOut(
                id=uuid4(),
                name="2026. évi leltár",
                year=2026,
                state="ACTIVE",
                opened_at=datetime(2026, 9, 9, 8, 0, tzinfo=UTC),
            )
        ]

    def get_periods(self, token: str) -> list[PeriodOut]:
        return list(self.periods)

    def close_period(self, token: str, period_id: UUID) -> PeriodOut:
        closed = self.periods[0].model_copy(
            update={"state": "CLOSED", "closed_at": datetime(2026, 11, 7, tzinfo=UTC)}
        )
        self.periods[0] = closed
        return closed

    def create_period(self, token: str, name: str, year: int) -> PeriodOut:
        period = PeriodOut(id=uuid4(), name=name, year=year, state="ACTIVE")
        self.periods.insert(0, period)
        return period

    def get_snapshots(self, token: str) -> list[SnapshotOut]:
        return list(self.snapshots)

    def create_snapshot(self, token: str, label: str | None) -> SnapshotOut:
        snapshot = SnapshotOut(
            file_name=f"2026-10-20_11-00-00_{label}.json",
            created_at=datetime(2026, 10, 20, 9, 0, tzinfo=UTC),
            size_bytes=1024,
        )
        self.snapshots.insert(0, snapshot)
        return snapshot

    def restore_snapshot(self, token: str, file_name: str) -> RestoreResult:
        self.restored.append(file_name)
        return RestoreResult(
            file_name=file_name, rows={"asset": 3620}, backup="2026-10-20_12-00-00.json"
        )


def open_page(qtbot: QtBot) -> tuple[AdminPage, AdminTestApi]:
    api = AdminTestApi()
    page = AdminPage(api, "test-token")
    qtbot.addWidget(page)
    qtbot.waitUntil(lambda: page.table.rowCount() == 1)
    return page, api


def test_snapshots_are_listed(qtbot: QtBot) -> None:
    page, _ = open_page(qtbot)

    item = page.table.item(0, 0)
    assert item is not None
    assert item.text() == "2026-10-20_10-00-00_kezdo.json"


def test_save_adds_snapshot_to_list(qtbot: QtBot) -> None:
    page, _ = open_page(qtbot)
    page.label_input.setText("proba")
    page.save_button.click()

    qtbot.waitUntil(lambda: page.table.rowCount() == 2)
    assert page.label_input.text() == ""
    assert "proba" in page.status_label.text()


def answer_no(*_args: object) -> QMessageBox.StandardButton:
    return QMessageBox.StandardButton.No


def answer_yes(*_args: object) -> QMessageBox.StandardButton:
    return QMessageBox.StandardButton.Yes


def test_restore_needs_selection(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    page, api = open_page(qtbot)
    monkeypatch.setattr(QMessageBox, "question", answer_yes)

    page.restore_button.click()

    assert api.restored == []
    assert "Válassz" in page.status_label.text()


def test_restore_needs_confirmation(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    page, api = open_page(qtbot)
    page.table.selectRow(0)

    monkeypatch.setattr(QMessageBox, "question", answer_no)
    page.restore_button.click()
    assert api.restored == []

    monkeypatch.setattr(QMessageBox, "question", answer_yes)
    with qtbot.waitSignal(page.data_changed):
        page.restore_button.click()
    assert api.restored == ["2026-10-20_10-00-00_kezdo.json"]


def test_active_period_can_be_closed_then_a_new_one_opened(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    page, api = open_page(qtbot)
    qtbot.waitUntil(lambda: page.close_period_button.isEnabled())
    assert "Aktív: 2026. évi leltár" in page.period_label.text()
    assert not page.open_period_button.isEnabled()

    monkeypatch.setattr(QMessageBox, "question", answer_no)
    page.close_period_button.click()
    assert api.periods[0].state == "ACTIVE"

    monkeypatch.setattr(QMessageBox, "question", answer_yes)
    page.close_period_button.click()
    qtbot.waitUntil(lambda: page.open_period_button.isEnabled())
    assert api.periods[0].state == "CLOSED"
    assert "Nincs aktív időszak" in page.period_label.text()

    # üres névnél az évből képzett név
    page.period_year_input.setValue(2027)
    page.open_period_button.click()
    qtbot.waitUntil(lambda: page.close_period_button.isEnabled())
    assert api.periods[0].name == "2027. évi leltár"
    assert "Aktív: 2027. évi leltár" in page.period_label.text()
