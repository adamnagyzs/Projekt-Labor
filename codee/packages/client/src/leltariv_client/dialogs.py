from uuid import UUID
from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from leltariv_client.worker import Worker


class AssetDetailDialog(QDialog):
    """Egy eszköz adatlapja a kódjaival, tartozékaival, típusával és felelősével."""

    def __init__(self, api, token, asset_id, parent=None):
        super().__init__(parent)
        self.api = api
        self.token = token
        self.asset_id = asset_id
        self.loaded_accessories = []
        self.current_detail = None

        self.setWindowTitle("Eszköz adatlapja")
        self.resize(550, 650)

        layout = QVBoxLayout(self)
        self.info_label = QLabel("Adatok betöltése folyamatban...")
        layout.addWidget(self.info_label)

        room_layout = QHBoxLayout()
        room_layout.addWidget(QLabel("<b>Helyiség (aktív):</b>"))
        self.lbl_room = QLabel("még nem olvasták be")
        room_layout.addWidget(self.lbl_room)
        room_layout.addStretch()
        layout.addLayout(room_layout)

        type_layout = QHBoxLayout()
        self.type_combo = QComboBox()
        self.btn_save_type = QPushButton("Típus mentése")
        self.btn_save_type.clicked.connect(self.save_asset_type)
        self.btn_new_type = QPushButton("Új típus…")
        self.btn_new_type.clicked.connect(self.create_new_type)
        type_layout.addWidget(QLabel("Típus:"))
        type_layout.addWidget(self.type_combo, 1)
        type_layout.addWidget(self.btn_save_type)
        type_layout.addWidget(self.btn_new_type)
        layout.addLayout(type_layout)

        resp_layout = QHBoxLayout()
        self.resp_combo = QComboBox()
        self.btn_save_resp = QPushButton("Felelős mentése")
        self.btn_save_resp.clicked.connect(self.save_responsible)
        resp_layout.addWidget(QLabel("Felelős:"))
        resp_layout.addWidget(self.resp_combo, 1)
        resp_layout.addWidget(self.btn_save_resp)
        layout.addLayout(resp_layout)

        self.codes_table = QTableWidget(0, 3)
        self.codes_table.setHorizontalHeaderLabels(["Kód", "Típus", "Elsődleges"])
        self.codes_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(QLabel("Kódok:"))
        layout.addWidget(self.codes_table)

        self.accessories_list = QListWidget()
        self.accessories_list.itemDoubleClicked.connect(self.on_accessory_double_clicked)
        layout.addWidget(QLabel("Tartozékok (dupla kattintással megnyitható):"))
        layout.addWidget(self.accessories_list)

        btn_close = QPushButton("Bezárás")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

        self.load_metadata_and_asset()

    def load_metadata_and_asset(self):
        """Betölti a legördülőkhöz szükséges listákat a háttérben."""
        w_types = Worker(self.api.get_asset_types, self.token)
        w_types.signals.finished.connect(self.on_types_loaded)
        w_types.signals.error.connect(self.on_error)
        QThreadPool.globalInstance().start(w_types)

        w_persons = Worker(self.api.get_persons, self.token)
        w_persons.signals.finished.connect(self.on_persons_loaded)
        w_persons.signals.error.connect(self.on_error)
        QThreadPool.globalInstance().start(w_persons)

    def load_asset_details(self):
        worker = Worker(self.api.get_asset, self.token, self.asset_id)
        worker.signals.finished.connect(self.on_loaded)
        worker.signals.error.connect(self.on_error)
        QThreadPool.globalInstance().start(worker)

    def on_types_loaded(self, types):
        self.type_combo.clear()
        for t in types:
            self.type_combo.addItem(t.name, t.id)
        # Ha a típusok megvannak, betöltjük az eszközt is
        self.load_asset_details()

    def on_persons_loaded(self, persons):
        self.resp_combo.clear()
        self.resp_combo.addItem("— nincs —", None)
        for p in persons:
            self.resp_combo.addItem(p.name, p.id)

    def on_loaded(self, detail):
        self.current_detail = detail
        self.info_label.setText(
            f"Név: {detail.name}\n"
            f"Eszközszám: {detail.asset_number}/{detail.sub_number}\n"
            f"Körzet: {detail.zone_code} | Mennyiség: {detail.quantity}\n"
            f"Gyári szám: {detail.serial_number or '-'}\n"
            f"Aktiválva: {detail.activated_on or '-'}"
        )

        # Helyiség beállítása
        if getattr(detail, "room", None):
            self.lbl_room.setText(detail.room)
        else:
            self.lbl_room.setText("még nem olvasták be")

        # Típus kiválasztása a comboboxban
        type_id = getattr(detail, "asset_type_id", None)
        if type_id is not None:
            idx = self.type_combo.findData(type_id)
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)

        # Felelős kiválasztása a comboboxban
        responsible_obj = getattr(detail, "responsible", None)
        if responsible_obj is not None and hasattr(responsible_obj, "id"):
            idx = self.resp_combo.findData(responsible_obj.id)
            if idx >= 0:
                self.resp_combo.setCurrentIndex(idx)
        else:
            self.resp_combo.setCurrentIndex(0)

        self.codes_table.setRowCount(len(detail.codes))
        for row, code in enumerate(detail.codes):
            self.codes_table.setItem(row, 0, QTableWidgetItem(code.code))
            self.codes_table.setItem(row, 1, QTableWidgetItem(code.code_type))
            self.codes_table.setItem(row, 2, QTableWidgetItem("igen" if code.is_primary else ""))

        self.loaded_accessories = detail.accessories
        self.accessories_list.clear()
        if not self.loaded_accessories:
            self.accessories_list.addItem("Nincs tartozéka.")
        for acc in self.loaded_accessories:
            self.accessories_list.addItem(f"{acc.asset_number}/{acc.sub_number} – {acc.name}")

    def save_asset_type(self):
        selected_type_id = self.type_combo.currentData()
        if selected_type_id is None:
            return
        worker = Worker(self.api.set_asset_type, self.token, self.asset_id, selected_type_id)
        worker.signals.finished.connect(self.on_type_saved)
        worker.signals.error.connect(self.on_error)
        QThreadPool.globalInstance().start(worker)

    def on_type_saved(self, updated_detail):
        QMessageBox.information(self, "Siker", "A típus sikeresen mentve.")
        self.on_loaded(updated_detail)
        self.accept()  # Jelzi a hívónak, hogy frissíteni kell a listát

    def create_new_type(self):
        text, ok = QInputDialog.getText(self, "Új típus felvétele", "Add meg az új típust:")
        if ok and text.strip():
            worker = Worker(self.api.create_asset_type, self.token, text.strip())
            worker.signals.finished.connect(self.on_new_type_created)
            worker.signals.error.connect(self.on_error)
            QThreadPool.globalInstance().start(worker)

    def on_new_type_created(self, new_type):
        # Újratöltjük a típusokat, és beállítjuk az újat
        def refresh_types(types):
            self.type_combo.clear()
            for t in types:
                self.type_combo.addItem(t.name, t.id)
            idx = self.type_combo.findData(new_type.id)
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
            self.save_asset_type()

        worker = Worker(self.api.get_asset_types, self.token)
        worker.signals.finished.connect(refresh_types)
        QThreadPool.globalInstance().start(worker)

    def save_responsible(self):
        selected_person_id = self.resp_combo.currentData()
        if selected_person_id is None:
            QMessageBox.warning(self, "Figyelmeztetés", "Kérlek válassz ki egy felelőst!")
            return
        worker = Worker(self.api.set_responsible, self.token, self.asset_id, selected_person_id)
        worker.signals.finished.connect(self.on_resp_saved)
        worker.signals.error.connect(self.on_error)
        QThreadPool.globalInstance().start(worker)

    def on_resp_saved(self, updated_detail):
        QMessageBox.information(self, "Siker", "A felelős sikeresen mentve.")
        self.on_loaded(updated_detail)
        self.accept()

    def on_error(self, err_msg):
        self.info_label.setText("Hiba történt a művelet során.")
        QMessageBox.critical(self, "Hiba", err_msg)

    def on_accessory_double_clicked(self, item):
        row = self.accessories_list.row(item)
        if row < len(self.loaded_accessories):
            acc_id = self.loaded_accessories[row].id
            AssetDetailDialog(self.api, self.token, acc_id, self.parent()).exec()