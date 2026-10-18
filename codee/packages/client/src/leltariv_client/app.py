import json
import math
import os
import sys
from pathlib import Path

import qdarktheme
from leltariv_contracts.auth import LoginRequest
from PySide6.QtCore import QAbstractTableModel, QSortFilterProxyModel, Qt, QThreadPool
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from leltariv_client.api import HttpApiClient
from leltariv_client.dialogs import AssetDetailDialog
from leltariv_client.pages.rooms import RoomsPage
from leltariv_client.pages.scanning import ScanningPage
from leltariv_client.worker import Worker

#: hány sor jöjjön egy lapon. A szerver 100-ban maximálja.
PAGE_SIZE = 50

#: jobbra igazított oszlopok (mennyiség) — a darabszámok így olvashatók össze
NUMERIC_COLUMNS = frozenset({5})

#: tabuláris számjegyekkel szedett oszlopok: eszközszám, alszám, leltárszám, mennyiség
MONOSPACE_COLUMNS = frozenset({0, 1, 3, 5})


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
        self.headers = [
            "Eszközszám",
            "Alszám",
            "Megnevezés",
            "Leltárszám",
            "Körzet",
            "Mennyiség",
            "Aktiválva",
            "Gyári szám",
            "Típus",
            "Felelős",
        ]

    def data(self, index, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self._data[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            vals = [
                item.asset_number,
                str(item.sub_number),
                item.name,
                item.inventory_number or "-",
                item.zone_code,
                str(item.quantity),
                str(item.activated_on) if item.activated_on else "-",
                item.serial_number or "-",
                item.asset_type or "",
                item.responsible or "",
            ]
            return vals[col]

        if role == Qt.ItemDataRole.TextAlignmentRole and col in NUMERIC_COLUMNS:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.FontRole and col in MONOSPACE_COLUMNS:
            font = QFont("Consolas" if sys.platform == "win32" else "Monospace")
            font.setStyleHint(QFont.StyleHint.Monospace)
            return font
        return None

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self.headers)

    def headerData(self, section, orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None

    def item_at(self, row: int):
        return self._data[row]

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
        saved_url = "http://127.0.0.1:8000"
        saved_email = ""
        if self.config_path.exists():
            try:
                conf = json.loads(self.config_path.read_text())
                saved_url = conf.get("url", saved_url)
                saved_email = conf.get("email", saved_email)
            except (OSError, ValueError):
                pass

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
        self.config_path.write_text(
            json.dumps({"url": self.url_input.text(), "email": self.email_input.text()})
        )


class MainWindow(QMainWindow):
    def __init__(self, api, token, user_name, role):
        super().__init__()
        self.api = api
        self.token = token
        self.current_page = 1
        self.setWindowTitle("Leltárív Kliens")
        self.resize(1024, 768)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        h_layout = QHBoxLayout(main_widget)

        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(200)
        for item in [
            "Áttekintés",
            "Eszközök",
            "Leltározás",
            "Helyiségek",
            "Riportok",
            "Adminisztráció",
        ]:
            self.nav_list.addItem(item)

        self.nav_list.setCurrentRow(1)
        h_layout.addWidget(self.nav_list)

        v_layout = QVBoxLayout()
        header_label = QLabel(f"Bejelentkezve: {user_name} ({role})")
        header_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        v_layout.addWidget(header_label)

        self.stack = QStackedWidget()
        self.asset_page = self.create_asset_page()
        self.stack.addWidget(
            QLabel(
                "Fejlesztés alatt...",
                alignment=Qt.AlignmentFlag.AlignCenter,
            )
        )
        self.stack.addWidget(self.asset_page)
        self.stack.addWidget(ScanningPage(api, token))
        self.stack.addWidget(RoomsPage(api, token))
        self.stack.setCurrentIndex(1)
        v_layout.addWidget(self.stack)
        h_layout.addLayout(v_layout)

        self.nav_list.currentRowChanged.connect(self.on_nav_changed)

        self.load_zones()
        self.load_metadata()

    def on_nav_changed(self, i: int):
        # 1 = Eszközök, 2 = Leltározás, 3 = Helyiségek; a többi 0
        if i == 1:
            self.stack.setCurrentIndex(1)
        elif i == 2:
            self.stack.setCurrentIndex(2)
        elif i == 3:
            self.stack.setCurrentIndex(3)
        else:
            self.stack.setCurrentIndex(0)

    def create_asset_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        filter_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Keresés...")
        self.search_input.textChanged.connect(self.trigger_search)

        self.search_field = QComboBox()
        for label, value in (
            ("Mindenhol", "mind"),
            ("Megnevezés", "nev"),
            ("Leltárszám", "LELTARSZAM"),
            ("Eszközszám", "ESZKOZSZAM"),
            ("Gyári szám", "GYARI_SZAM"),
        ):
            self.search_field.addItem(label, value)
        self.search_field.currentIndexChanged.connect(self.trigger_search)

        self.zone_combo = QComboBox()
        self.zone_combo.addItem("Mind")
        self.zone_combo.currentTextChanged.connect(self.on_zone_changed)

        # Új szűrők: Típus, Helyiség, Felelős
        self.type_combo = QComboBox()
        self.type_combo.addItem("Mind", None)
        self.type_combo.currentIndexChanged.connect(self.trigger_search)

        self.room_combo = QComboBox()
        self.room_combo.addItem("Mind", None)
        self.room_combo.setEnabled(False)
        self.room_combo.currentIndexChanged.connect(self.trigger_search)

        self.person_combo = QComboBox()
        self.person_combo.addItem("Mind", None)
        self.person_combo.currentIndexChanged.connect(self.trigger_search)

        self.main_only_cb = QCheckBox("Csak főeszközök")
        self.multi_only_cb = QCheckBox("Csak többdarabos")
        self.main_only_cb.toggled.connect(self.trigger_search)
        self.multi_only_cb.toggled.connect(self.trigger_search)

        filter_layout.addWidget(QLabel("Körzet:"))
        filter_layout.addWidget(self.zone_combo)
        filter_layout.addWidget(QLabel("Helyiség:"))
        filter_layout.addWidget(self.room_combo)
        filter_layout.addWidget(QLabel("Típus:"))
        filter_layout.addWidget(self.type_combo)
        filter_layout.addWidget(QLabel("Felelős:"))
        filter_layout.addWidget(self.person_combo)
        filter_layout.addWidget(self.main_only_cb)
        filter_layout.addWidget(self.multi_only_cb)
        filter_layout.addWidget(self.search_field)
        filter_layout.addWidget(self.search_input)
        layout.addLayout(filter_layout)

        self.table = QTableView()
        self.model = AssetTableModel()

        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)

        self.table.setModel(self.proxy_model)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        footer = QHBoxLayout()
        self.status_label = QLabel("Adatok betöltése folyamatban...")
        self.prev_button = QPushButton("← Előző")
        self.next_button = QPushButton("Következő →")
        self.prev_button.clicked.connect(self.go_previous_page)
        self.next_button.clicked.connect(self.go_next_page)
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)

        footer.addWidget(self.status_label)
        footer.addStretch()
        footer.addWidget(self.prev_button)
        footer.addWidget(self.next_button)
        layout.addLayout(footer)

        self.table.doubleClicked.connect(self.on_row_double_clicked)
        return page

    def on_zone_changed(self):
        zone_code = self.zone_combo.currentText()
        self.room_combo.clear()
        self.room_combo.addItem("Mind", None)
        if zone_code == "Mind" or not zone_code:
            self.room_combo.setEnabled(False)
        else:
            self.room_combo.setEnabled(True)
            self.load_rooms(zone_code)
        self.trigger_search()

    def trigger_search(self):
        self.current_page = 1
        self.load_page()

    def on_row_double_clicked(self, index):
        source_index = self.proxy_model.mapToSource(index)
        item = self.model.item_at(source_index.row())
        dlg = AssetDetailDialog(self.api, self.token, item.id, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_page()

    def go_previous_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_page()

    def go_next_page(self):
        self.current_page += 1
        self.load_page()

    def load_page(self):
        self.status_label.setText("Adatok betöltése folyamatban...")
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)

        zone = self.zone_combo.currentText()
        asset_type_id = self.type_combo.currentData()
        room_id = self.room_combo.currentData()
        person_id = self.person_combo.currentData()

        worker = Worker(
            self.api.get_assets,
            self.token,
            zone if zone != "Mind" else None,
            self.search_input.text(),
            self.current_page,
            PAGE_SIZE,
            self.main_only_cb.isChecked(),
            self.multi_only_cb.isChecked(),
            self.search_field.currentData(),
            asset_type_id=asset_type_id,
            room_id=room_id,
            person_id=person_id,
        )
        worker.signals.finished.connect(self.on_assets_loaded)
        worker.signals.error.connect(self.on_error)
        self.latest_load = worker.signals
        QThreadPool.globalInstance().start(worker)

    def load_zones(self):
        worker = Worker(self.api.get_zones, self.token)
        worker.signals.finished.connect(self.on_zones_loaded)
        worker.signals.error.connect(self.on_error)
        QThreadPool.globalInstance().start(worker)

    def load_metadata(self):
        # Típusok betöltése
        t_worker = Worker(self.api.get_asset_types, self.token)
        t_worker.signals.finished.connect(self.on_asset_types_loaded)
        QThreadPool.globalInstance().start(t_worker)

        # Felelősök betöltése
        p_worker = Worker(self.api.get_persons, self.token)
        p_worker.signals.finished.connect(self.on_persons_loaded)
        QThreadPool.globalInstance().start(p_worker)

    def load_rooms(self, zone_code: str):
        worker = Worker(self.api.get_rooms, self.token, zone_code)
        worker.signals.finished.connect(self.on_rooms_loaded)
        QThreadPool.globalInstance().start(worker)

    def on_zones_loaded(self, zones):
        for z in zones:
            self.zone_combo.addItem(z.code)

    def on_asset_types_loaded(self, types):
        for t in types:
            self.type_combo.addItem(t.name, t.id)

    def on_persons_loaded(self, persons):
        for p in persons:
            self.person_combo.addItem(p.name, p.id)

    def on_rooms_loaded(self, rooms):
        for r in rooms:
            self.room_combo.addItem(r.label, r.id)

    def on_assets_loaded(self, page_data):
        if self.sender() is not self.latest_load:
            return
        self.model.update_data(page_data.items)

        shown = len(page_data.items)
        total = page_data.total
        last_page = max(1, math.ceil(total / page_data.page_size))

        if total == 0:
            self.status_label.setText("Nincs találat.")
        else:
            first_row = (page_data.page - 1) * page_data.page_size + 1
            self.status_label.setText(
                f"{first_row}–{first_row + shown - 1}. sor a(z) {total}-ből"
                f"  ·  {page_data.page}. oldal / {last_page}"
            )

        self.prev_button.setEnabled(page_data.page > 1)
        self.next_button.setEnabled(page_data.page < last_page)

    def on_error(self, err_msg):
        QMessageBox.critical(self, "Hiba", f"Hálózati hiba történt:\n{err_msg}")
        self.status_label.setText("Hiba az adatok betöltésekor.")
        self.prev_button.setEnabled(self.current_page > 1)
        self.next_button.setEnabled(True)


def main():
    app = QApplication(sys.argv)
    qdarktheme.setup_theme("auto")

    dialog = LoginDialog()
    while dialog.exec() == QDialog.DialogCode.Accepted:
        dialog.save_config()
        api = HttpApiClient(dialog.url_input.text())
        try:
            req = LoginRequest(email=dialog.email_input.text(), password=dialog.pwd_input.text())
            resp = api.login(req)
        except Exception as e:
            QMessageBox.critical(dialog, "Belépési hiba", str(e))
            dialog.pwd_input.clear()
            dialog.pwd_input.setFocus()
            continue

        window = MainWindow(api, resp.access_token, resp.display_name, resp.role)
        window.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
