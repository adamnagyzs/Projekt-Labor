"""Adminisztráció: SAP-lista importja és az adatbázis pillanatképei."""

from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from leltariv_client.worker import Worker


class AdminPage(QWidget):
    #: import vagy visszatöltés után: az eszközlistát újra kell tölteni
    data_changed = Signal()

    def __init__(self, api, token: str, parent=None):
        super().__init__(parent)
        self.api = api
        self.token = token

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("<b>Excel-import</b>"))
        layout.addWidget(
            QLabel(
                "SAP-eszközlista (XLSX) betöltése. A már meglévő eszközök változatlanok "
                "maradnak, előtte automatikusan pillanatkép készül."
            )
        )
        self.import_button = QPushButton("SAP-lista importálása…")
        layout.addWidget(self.import_button, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(QLabel("<b>Pillanatképek</b>"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Fájl", "Mentve", "Méret"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

        row = QHBoxLayout()
        self.label_input = QLineEdit()
        self.label_input.setMaxLength(40)
        self.label_input.setPlaceholderText("Megjegyzés (nem kötelező)")
        self.save_button = QPushButton("Pillanatkép mentése")
        self.restore_button = QPushButton("Kijelölt visszatöltése…")
        row.addWidget(self.label_input)
        row.addWidget(self.save_button)
        row.addStretch()
        row.addWidget(self.restore_button)
        layout.addLayout(row)

        self.status_label = QLabel()
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status_label)

        self.import_button.clicked.connect(self._import)
        self.save_button.clicked.connect(self._save)
        self.label_input.returnPressed.connect(self._save)
        self.restore_button.clicked.connect(self._restore)

        self._load_snapshots()

    def _set_busy(self, busy: bool, message: str = "") -> None:
        for widget in (self.import_button, self.save_button, self.restore_button):
            widget.setEnabled(not busy)
        if message:
            self.status_label.setText(message)

    @Slot()
    def _load_snapshots(self) -> None:
        self._run(self.api.get_snapshots, self.token, on_done=self._on_snapshots_loaded)

    @Slot(object)
    def _on_snapshots_loaded(self, snapshots) -> None:
        self.table.setRowCount(len(snapshots))
        for index, snapshot in enumerate(snapshots):
            saved = snapshot.created_at.astimezone().strftime("%Y.%m.%d. %H:%M:%S")
            size = f"{snapshot.size_bytes / 1024 / 1024:.1f} MB"
            for column, value in enumerate((snapshot.file_name, saved, size)):
                self.table.setItem(index, column, QTableWidgetItem(value))

    @Slot()
    def _import(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self, "SAP-lista kiválasztása", "", "Excel-munkafüzet (*.xlsx *.XLSX)"
        )
        if not file_name:
            return
        self._set_busy(True, f"Importálás folyamatban: {Path(file_name).name}…")
        self._run(self.api.import_xlsx, self.token, Path(file_name), on_done=self._on_imported)

    @Slot(object)
    def _on_imported(self, result) -> None:
        lines = [
            f"{result.file_name}: {result.rows_read} sor, {result.rows_ok} új eszköz, "
            f"{result.rows_skipped} már megvolt, {result.rows_failed} hibás.",
            f"Az import előtti állapot: {result.snapshot}",
            *result.errors,
        ]
        self._set_busy(False, "\n".join(lines))
        self._load_snapshots()
        self.data_changed.emit()

    @Slot()
    def _save(self) -> None:
        self._set_busy(True, "Pillanatkép mentése…")
        label = self.label_input.text().strip() or None
        self._run(self.api.create_snapshot, self.token, label, on_done=self._on_saved)

    @Slot(object)
    def _on_saved(self, snapshot) -> None:
        self.label_input.clear()
        self._set_busy(False, f"Mentve: {snapshot.file_name}")
        self._load_snapshots()

    @Slot()
    def _restore(self) -> None:
        item = self.table.item(self.table.currentRow(), 0)
        if item is None or not item.isSelected():
            self.status_label.setText("Válassz ki egy pillanatképet a listából.")
            return
        file_name = item.text()

        answer = QMessageBox.question(
            self,
            "Visszatöltés",
            f"A teljes adatbázis visszaáll erre az állapotra:\n{file_name}\n\n"
            "Ami azóta történt (beolvasások, felelősök, importok), eltűnik. "
            "Előtte a mostani állapotról automatikusan pillanatkép készül.\n\nFolytatod?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True, f"Visszatöltés folyamatban: {file_name}…")
        self._run(self.api.restore_snapshot, self.token, file_name, on_done=self._on_restored)

    @Slot(object)
    def _on_restored(self, result) -> None:
        self._set_busy(
            False,
            f"Visszatöltve: {result.file_name} ({result.rows.get('asset', 0)} eszköz).\n"
            f"A visszatöltés előtti állapot: {result.backup}",
        )
        self._load_snapshots()
        self.data_changed.emit()

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._set_busy(False, message)

    def _run(self, fn, *args, on_done) -> None:
        worker = Worker(fn, *args)
        worker.signals.finished.connect(on_done)
        worker.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(worker)
