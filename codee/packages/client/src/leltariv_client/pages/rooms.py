"""Helyiségek listázása és felvétele, háttérszálon futó API-hívásokkal."""

from PySide6.QtCore import Qt, QThreadPool, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from leltariv_client.worker import Worker


class RoomsPage(QWidget):
    def __init__(self, api, token: str, parent=None):
        super().__init__(parent)
        self.api = api
        self.token = token
        self._busy = False

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Helyiségek"))

        self.zone_combo = QComboBox()
        self.zone_combo.setAccessibleName("Leltárkörzet")
        layout.addWidget(self.zone_combo)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Ajtószám", "Megnevezés"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        form = QFormLayout()
        self.room_number_input = QLineEdit()
        self.room_number_input.setMaxLength(30)
        form.addRow("Ajtószám:", self.room_number_input)

        self.name_input = QLineEdit()
        self.name_input.setMaxLength(100)
        form.addRow("Megnevezés:", self.name_input)
        layout.addLayout(form)

        self.add_button = QPushButton("Hozzáadás")
        layout.addWidget(self.add_button)

        self.error_label = QLabel()
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        self.zone_combo.currentIndexChanged.connect(self._load_rooms)
        self.add_button.clicked.connect(self._create_room)
        self.room_number_input.returnPressed.connect(self._create_room)
        self.name_input.returnPressed.connect(self._create_room)

        self._set_busy(True)
        self._run(
            self.api.get_zones,
            self.token,
            on_done=self._on_zones_loaded,
        )

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        has_zone = self.zone_combo.currentIndex() >= 0
        self.zone_combo.setEnabled(not busy and self.zone_combo.count() > 0)
        self.room_number_input.setEnabled(not busy and has_zone)
        self.name_input.setEnabled(not busy and has_zone)
        self.add_button.setEnabled(not busy and has_zone)

    @Slot(object)
    def _on_zones_loaded(self, zones) -> None:
        self.zone_combo.blockSignals(True)
        self.zone_combo.clear()
        for zone in zones:
            self.zone_combo.addItem(f"{zone.code} · {zone.name}", zone.code)
        self.zone_combo.blockSignals(False)

        self._set_busy(False)
        if self.zone_combo.count():
            self._load_rooms()
        else:
            self.error_label.setText("Nincs választható leltárkörzet.")

    @Slot()
    def _load_rooms(self) -> None:
        if self._busy:
            return

        zone_code = self.zone_combo.currentData()
        if zone_code is None:
            return

        self.error_label.clear()
        self.table.setRowCount(0)
        self._set_busy(True)
        self._run(
            self.api.get_rooms,
            self.token,
            zone_code,
            on_done=self._on_rooms_loaded,
        )

    @Slot(object)
    def _on_rooms_loaded(self, rooms) -> None:
        ordered = sorted(rooms, key=lambda room: room.room_number)
        self.table.setRowCount(len(ordered))
        for row_index, room in enumerate(ordered):
            self.table.setItem(row_index, 0, QTableWidgetItem(room.room_number))
            self.table.setItem(row_index, 1, QTableWidgetItem(room.name or ""))
        self._set_busy(False)

    @Slot()
    def _create_room(self) -> None:
        if self._busy:
            return

        zone_code = self.zone_combo.currentData()
        if zone_code is None:
            return

        room_number = self.room_number_input.text().strip()
        name = self.name_input.text().strip() or None

        self.error_label.clear()
        if not room_number:
            self.error_label.setText("Az ajtószám megadása kötelező.")
            self.room_number_input.setFocus()
            return

        self._set_busy(True)
        self._run(
            self.api.create_room,
            self.token,
            zone_code,
            room_number,
            name,
            on_done=self._on_room_created,
        )

    @Slot(object)
    def _on_room_created(self, room) -> None:
        self.room_number_input.clear()
        self.name_input.clear()
        self._set_busy(False)
        self._load_rooms()

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self.error_label.setText(message)
        self._set_busy(False)

    def _run(self, fn, *args, on_done) -> None:
        worker = Worker(fn, *args)
        worker.signals.finished.connect(on_done)
        worker.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(worker)
