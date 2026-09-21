import sys
import os
import json
from pathlib import Path
import qdarktheme
import qtawesome as qta
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QDialog, QLineEdit, QPushButton, QLabel, QStackedWidget, QListWidget,
    QTableView, QComboBox, QHeaderView, QMessageBox, QProgressDialog
)
from PySide6.QtCore import Qt, QAbstractTableModel, QSortFilterProxyModel, QThreadPool
from PySide6.QtGui import QFont, QIcon

from leltariv_contracts.auth import LoginRequest
from leltariv_client.api import FakeApiClient
from leltariv_client.worker import Worker

def get_config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".config"
    config_dir = base / "Leltariv"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"

class AssetTableModel(QAbstractTableModel):
    def __init__(self, data=None):
        super().__init__()
        self._data = data or []
        self.headers = ["Eszközszám", "Alszám", "Megnevezés", "Leltárszám", "Körzet", "Mennyiség", "Aktiválva", "Gyári szám"]

    def data(self, index, role):
        if not index.isValid(): return None
        item = self._data[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            vals = [item.asset_number, str(item.sub_number), item.name, item.inventory_number or "-", 
                    item.zone_code, str(item.quantity), str(item.activated_on) if item.activated_on else "-", item.serial_number or "-"]
            return vals[col]
            
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in [5]:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                
        if role == Qt.ItemDataRole.FontRole:
            if col in [0, 1, 3, 5]:
                font = QFont("Consolas" if sys.platform == "win32" else "Monospace")
                font.setStyleHint(QFont.StyleHint.Monospace)
                return font
        return None

    def rowCount(self, index=None): return len(self._data)
    def columnCount(self, index=None): return len(self.headers)
    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None

    def update_data(self, new_data):
        self.beginResetModel()
        self._data = new_data
        self.endResetModel()

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Leltárív - Bejelentkezés")
        self.setFixedSize(350, 250)
        
        self.config_path = get_config_path()
        saved_url = "http://localhost:8000"
        saved_email = ""
        if self.config_path.exists():
            try:
                conf = json.loads(self.config_path.read_text())
                saved_url = conf.get("url", saved_url)
                saved_email = conf.get("email", saved_email)
            except: pass

        layout = QVBoxLayout(self)
        self.url_input = QLineEdit(saved_url)
        self.email_input = QLineEdit(saved_email)
        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)

        layout.addWidget(QLabel("Szerver címe:"))
        layout.addWidget(self.url_input)
        layout.addWidget(QLabel("E-mail:"))
        layout.addWidget(self.email_input)
        layout.addWidget(QLabel("Jelszó:"))
        layout.addWidget(self.pwd_input)

        self.btn = QPushButton("Bejelentkezés")
        self.btn.clicked.connect(self.accept)
        layout.addWidget(self.btn)

    def save_config(self):
        self.config_path.write_text(json.dumps({"url": self.url_input.text(), "email": self.email_input.text()}))

class MainWindow(QMainWindow):
    def __init__(self, api, token, user_name, role):
        super().__init__()
        self.api = api
        self.token = token
        self.setWindowTitle("Leltárív Kliens")
        self.resize(1024, 768)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        h_layout = QHBoxLayout(main_widget)

        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(200)
        for item in ["Áttekintés", "Eszközök", "Leltározás", "Helyiségek", "Riportok", "Adminisztráció"]:
            self.nav_list.addItem(item)
        
        self.nav_list.setCurrentRow(1)
        h_layout.addWidget(self.nav_list)

        v_layout = QVBoxLayout()
        header_label = QLabel(f"Bejelentkezve: {user_name} ({role})")
        header_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        v_layout.addWidget(header_label)

        self.stack = QStackedWidget()
        self.asset_page = self.create_asset_page()
        self.stack.addWidget(QLabel("Fejlesztés alatt... (Válaszd az Eszközök menüt)", alignment=Qt.AlignmentFlag.AlignCenter))
        self.stack.addWidget(self.asset_page)
        self.stack.setCurrentIndex(1)
        v_layout.addWidget(self.stack)
        h_layout.addLayout(v_layout)

        self.nav_list.currentRowChanged.connect(lambda i: self.stack.setCurrentIndex(1 if i == 1 else 0))

        self.load_zones()

    def create_asset_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        
        filter_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Keresés név alapján...")
        self.search_input.textChanged.connect(self.trigger_search)
        
        self.zone_combo = QComboBox()
        self.zone_combo.addItem("Mind")
        self.zone_combo.currentTextChanged.connect(self.trigger_search)
        
        filter_layout.addWidget(self.zone_combo)
        filter_layout.addWidget(self.search_input)
        layout.addLayout(filter_layout)

        self.table = QTableView()
        self.model = AssetTableModel()
        
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterKeyColumn(2)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        
        self.table.setModel(self.proxy_model)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        
        self.status_label = QLabel("Adatok betöltése folyamatban...")
        layout.addWidget(self.status_label)
        return page

    def trigger_search(self):
        self.status_label.setText("Adatok betöltése folyamatban...")
        
        self.proxy_model.setFilterWildcard(f"*{self.search_input.text()}*")
        
        zone = self.zone_combo.currentText()
        worker = Worker(self.api.get_assets, self.token, zone if zone != "Mind" else None, self.search_input.text(), 1, 50)
        worker.signals.finished.connect(self.on_assets_loaded)
        worker.signals.error.connect(self.on_error)
        QThreadPool.globalInstance().start(worker)

    def load_zones(self):
        worker = Worker(self.api.get_zones, self.token)
        worker.signals.finished.connect(self.on_zones_loaded)
        worker.signals.error.connect(self.on_error)
        QThreadPool.globalInstance().start(worker)

    def on_zones_loaded(self, zones):
        for z in zones:
            self.zone_combo.addItem(z.code)
        self.trigger_search()

    def on_assets_loaded(self, page_data):
        self.model.update_data(page_data.items)
        self.status_label.setText(f"Megjelenítve: {len(page_data.items)} / {page_data.total} sor (Szerverről)")

    def on_error(self, err_msg):
        QMessageBox.critical(self, "Hiba", f"Hálózati hiba történt:\n{err_msg}")
        self.status_label.setText("Hiba az adatok betöltésekor.")

def main():
    app = QApplication(sys.argv)
    qdarktheme.setup_theme("auto")
    
    dialog = LoginDialog()
    if dialog.exec() == QDialog.DialogCode.Accepted:
        dialog.save_config()
        api = FakeApiClient(dialog.url_input.text())
        
        req = LoginRequest(email=dialog.email_input.text(), password=dialog.pwd_input.text())
        try:
            resp = api.login(req) 
            window = MainWindow(api, resp.access_token, resp.display_name, resp.role)
            window.show()
            sys.exit(app.exec())
        except Exception as e:
            QMessageBox.critical(None, "Belépési hiba", str(e))

if __name__ == "__main__":
    main()