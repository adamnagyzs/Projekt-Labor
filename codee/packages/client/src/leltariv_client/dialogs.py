from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTableWidget, 
                               QTableWidgetItem, QListWidget, QHeaderView, QMessageBox)
from PySide6.QtCore import QThreadPool, Qt
from leltariv_client.worker import Worker

class AssetDetailDialog(QDialog):
    def __init__(self, api, token, asset_id, parent=None):
        super().__init__(parent)
        self.api = api
        self.token = token
        self.asset_id = asset_id
        
        self.setWindowTitle("Eszköz adatlapja")
        self.resize(500, 500)
        
        self.layout = QVBoxLayout(self)
        self.info_label = QLabel("Adatok betöltése folyamatban...")
        self.layout.addWidget(self.info_label)
        
        self.codes_table = QTableWidget(0, 2)
        self.codes_table.setHorizontalHeaderLabels(["Kód", "Típus"])
        self.codes_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.layout.addWidget(QLabel("Kódok:"))
        self.layout.addWidget(self.codes_table)
        
        self.accessories_list = QListWidget()
        self.accessories_list.itemDoubleClicked.connect(self.on_accessory_double_clicked)
        self.layout.addWidget(QLabel("Tartozékok (Kattints duplán a megnyitáshoz):"))
        self.layout.addWidget(self.accessories_list)
        
        self.loaded_accessories = []
        self.load_data()

    def load_data(self):
        worker = Worker(self.api.get_asset, self.token, self.asset_id)
        worker.signals.finished.connect(self.on_loaded)
        worker.signals.error.connect(self.on_error)
        QThreadPool.globalInstance().start(worker)

    def on_loaded(self, detail):
        self.info_label.setText(
            f"Név: {detail.name}\n"
            f"Leltárszám: {detail.asset_number}/{detail.sub_number}\n"
            f"Körzet: {detail.zone_code} | Mennyiség: {detail.quantity}\n"
            f"Gyári szám: {detail.serial_number or '-'}\n"
            f"Aktiválva: {detail.activated_on or '-'}\n"
            f"Típus: {detail.asset_type or '-'}"
        )
        
        self.codes_table.setRowCount(len(detail.codes))
        for row, code in enumerate(detail.codes):
            self.codes_table.setItem(row, 0, QTableWidgetItem(code.code))
            self.codes_table.setItem(row, 1, QTableWidgetItem(code.code_type))
            
        self.loaded_accessories = detail.accessories
        for acc in self.loaded_accessories:
            self.accessories_list.addItem(f"{acc.asset_number}/{acc.sub_number} - {acc.name}")

    def on_error(self, err_msg):
        self.info_label.setText("Hiba történt a betöltés során.")
        QMessageBox.critical(self, "Hálózati hiba", f"Nem sikerült betölteni az adatlapot:\n{err_msg}")

    def on_accessory_double_clicked(self, item):
        row = self.accessories_list.row(item)
        acc_id = self.loaded_accessories[row].id
        dialog = AssetDetailDialog(self.api, self.token, acc_id, self.parent())
        dialog.exec()