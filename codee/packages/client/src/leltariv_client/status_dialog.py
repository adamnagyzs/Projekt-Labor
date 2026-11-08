"""Eszközállapot módosítása kötelező indoklással."""

from typing import Protocol, cast
from uuid import UUID

from leltariv_contracts.assets import STATUS_LABELS, AssetStatus, StatusChangeOut
from PySide6.QtCore import Qt, QThreadPool, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from leltariv_client.worker import Worker


class _StatusApi(Protocol):
    def change_asset_status(
        self, token: str, asset_id: UUID, status: AssetStatus, reason: str
    ) -> StatusChangeOut: ...


class StatusDialog(QDialog):
    def __init__(
        self,
        api: _StatusApi,
        token: str,
        asset_id: UUID,
        current_status: AssetStatus,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.api = api
        self.token = token
        self.asset_id = asset_id
        self.current_status = current_status
        self.result_change: StatusChangeOut | None = None
        self._saving = False

        self.setWindowTitle("Állapot módosítása")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.status_combo = QComboBox()
        for status, label in STATUS_LABELS.items():
            self.status_combo.addItem(label, status)
        self.status_combo.setCurrentIndex(self.status_combo.findData(current_status))
        form.addRow("Állapot", self.status_combo)

        self.reason_input = QLineEdit()
        self.reason_input.setMaxLength(500)
        self.reason_input.setPlaceholderText("Pl. selejtezési jegyzőkönyv száma")
        form.addRow("Indoklás", self.reason_input)

        self.error_label = QLabel()
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        self.save_button = QPushButton("Mentés")
        self.save_button.setDefault(True)
        self.cancel_button = QPushButton("Mégse")
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.status_combo.currentIndexChanged.connect(self._update_save)
        self.reason_input.textChanged.connect(self._update_save)
        self.save_button.clicked.connect(self._save)
        self.cancel_button.clicked.connect(self.reject)
        self._update_save()

    @Slot()
    def _update_save(self) -> None:
        self.save_button.setEnabled(
            not self._saving
            and self.status_combo.currentIndex() >= 0
            and self.status_combo.currentData() != self.current_status
            and bool(self.reason_input.text().strip())
        )

    def _set_saving(self, saving: bool) -> None:
        self._saving = saving
        self.status_combo.setEnabled(not saving)
        self.reason_input.setEnabled(not saving)
        self.cancel_button.setEnabled(not saving)
        self._update_save()

    @Slot()
    def _save(self) -> None:
        if not self.save_button.isEnabled():
            return

        status = cast(AssetStatus, self.status_combo.currentData())
        reason = self.reason_input.text().strip()
        self.error_label.clear()
        self._set_saving(True)
        worker = Worker(self.api.change_asset_status, self.token, self.asset_id, status, reason)
        worker.signals.finished.connect(self._on_saved)
        worker.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _on_saved(self, result: StatusChangeOut) -> None:
        self.result_change = result
        self._set_saving(False)
        self.accept()

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self.error_label.setText(message)
        self._set_saving(False)

    def reject(self) -> None:
        if not self._saving:
            super().reject()
