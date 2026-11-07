from datetime import UTC, datetime

import pytest
from leltariv_client.pages.admin import AdminPage
from leltariv_contracts.admin import RestoreResult, SnapshotOut
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
