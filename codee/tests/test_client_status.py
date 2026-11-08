from datetime import UTC, datetime
from uuid import UUID, uuid4

from leltariv_client.status_dialog import StatusDialog
from leltariv_contracts.assets import STATUS_LABELS, AssetStatus, StatusChangeOut
from pytestqt.qtbot import QtBot


class StatusTestApi:
    def __init__(self, error: str | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, UUID, AssetStatus, str]] = []

    def change_asset_status(
        self, token: str, asset_id: UUID, status: AssetStatus, reason: str
    ) -> StatusChangeOut:
        self.calls.append((token, asset_id, status, reason))
        if self.error is not None:
            raise ValueError(self.error)
        return StatusChangeOut(
            id=uuid4(),
            asset_id=asset_id,
            old_status="ACTIVE",
            new_status=status,
            reason=reason,
            changed_at=datetime.now(UTC),
        )


def test_save_starts_disabled_with_current_status_selected(qtbot: QtBot) -> None:
    dialog = StatusDialog(StatusTestApi(), "test-token", uuid4(), "LOST")
    qtbot.addWidget(dialog)

    assert dialog.status_combo.currentData() == "LOST"
    assert dialog.status_combo.count() == len(STATUS_LABELS)
    for status, label in STATUS_LABELS.items():
        index = dialog.status_combo.findData(status)
        assert index >= 0
        assert dialog.status_combo.itemText(index) == label
    assert dialog.reason_input.maxLength() == 500
    assert not dialog.save_button.isEnabled()


def test_save_sends_changed_status_and_reason(qtbot: QtBot) -> None:
    api = StatusTestApi()
    asset_id = uuid4()
    dialog = StatusDialog(api, "test-token", asset_id, "ACTIVE")
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.reason_input.setText("Teszt indoklás")
    assert not dialog.save_button.isEnabled()
    dialog.reason_input.setText("  ")
    dialog.status_combo.setCurrentIndex(dialog.status_combo.findData("SCRAPPED"))
    assert not dialog.save_button.isEnabled()
    dialog.reason_input.setText("  Teszt indoklás  ")
    assert dialog.save_button.isEnabled()

    with qtbot.waitSignal(dialog.accepted):
        dialog.save_button.click()

    assert api.calls == [("test-token", asset_id, "SCRAPPED", "Teszt indoklás")]
    assert dialog.result_change is not None
    assert dialog.result_change.new_status == "SCRAPPED"
    assert not dialog.isVisible()


def test_save_error_is_shown_and_dialog_stays_open(qtbot: QtBot) -> None:
    message = "Az eszköz állapota időközben megváltozott."
    dialog = StatusDialog(StatusTestApi(error=message), "test-token", uuid4(), "ACTIVE")
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.status_combo.setCurrentIndex(dialog.status_combo.findData("SCRAPPED"))
    dialog.reason_input.setText("Teszt indoklás")
    dialog.save_button.click()

    qtbot.waitUntil(lambda: dialog.error_label.text() == message)

    assert dialog.error_label.isVisible()
    assert dialog.isVisible()
    assert dialog.save_button.isEnabled()
    assert dialog.result_change is None
