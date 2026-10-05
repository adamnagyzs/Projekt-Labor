from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QDialog,
    QHeaderView,
    QLabel,
    QListWidget,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from leltariv_client.worker import Worker


class AssetDetailDialog(QDialog):
    """Egy eszköz adatlapja a kódjaival és a tartozékaival."""

    def __init__(self, api, token, asset_id, parent=None):
        super().__init__(parent)
        self.api = api
        self.token = token
        self.loaded_accessories = []

        self.setWindowTitle("Eszköz adatlapja")
        self.resize(500, 500)

        layout = QVBoxLayout(self)
        self.info_label = QLabel("Adatok betöltése folyamatban...")
        layout.addWidget(self.info_label)

        self.codes_table = QTableWidget(0, 3)
        self.codes_table.setHorizontalHeaderLabels(["Kód", "Típus", "Elsődleges"])
        self.codes_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(QLabel("Kódok:"))
        layout.addWidget(self.codes_table)

        self.accessories_list = QListWidget()
        self.accessories_list.itemDoubleClicked.connect(self.on_accessory_double_clicked)
        layout.addWidget(QLabel("Tartozékok (dupla kattintással megnyitható):"))
        layout.addWidget(self.accessories_list)

        worker = Worker(self.api.get_asset, self.token, asset_id)
        worker.signals.finished.connect(self.on_loaded)
        worker.signals.error.connect(self.on_error)
        QThreadPool.globalInstance().start(worker)

    def on_loaded(self, detail):
        self.info_label.setText(
            f"Név: {detail.name}\n"
            f"Eszközszám: {detail.asset_number}/{detail.sub_number}\n"
            f"Körzet: {detail.zone_code} | Mennyiség: {detail.quantity}\n"
            f"Gyári szám: {detail.serial_number or '-'}\n"
            f"Aktiválva: {detail.activated_on or '-'}\n"
            f"Típus: {detail.asset_type or '-'}"
        )

        self.codes_table.setRowCount(len(detail.codes))
        for row, code in enumerate(detail.codes):
            self.codes_table.setItem(row, 0, QTableWidgetItem(code.code))
            self.codes_table.setItem(row, 1, QTableWidgetItem(code.code_type))
            self.codes_table.setItem(row, 2, QTableWidgetItem("igen" if code.is_primary else ""))

        self.loaded_accessories = detail.accessories
        if not self.loaded_accessories:
            self.accessories_list.addItem("Nincs tartozéka.")
        for acc in self.loaded_accessories:
            self.accessories_list.addItem(f"{acc.asset_number}/{acc.sub_number} – {acc.name}")

    def on_error(self, err_msg):
        self.info_label.setText("Hiba történt a betöltés során.")
        QMessageBox.critical(self, "Hiba", f"Nem sikerült betölteni az adatlapot:\n{err_msg}")

    def on_accessory_double_clicked(self, item):
        row = self.accessories_list.row(item)
        if row < len(self.loaded_accessories):
            acc_id = self.loaded_accessories[row].id
            AssetDetailDialog(self.api, self.token, acc_id, self.parent()).exec()
