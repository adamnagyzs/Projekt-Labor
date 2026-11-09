from uuid import UUID

from leltariv_contracts.assets import STATUS_LABELS
from leltariv_contracts.inventory import ComparisonOut
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from leltariv_client.dialogs import AssetDetailDialog
from leltariv_client.worker import Worker


def _id_item(inventory_number: str | None, asset_id: UUID) -> QTableWidgetItem:
    """A leltárszám cellája; az eszköz azonosítóját is hordozza a dupla kattintáshoz."""
    item = QTableWidgetItem(inventory_number or "-")
    item.setData(Qt.ItemDataRole.UserRole, asset_id)
    return item


class ComparisonPage(QWidget):
    def __init__(self, api, token, parent=None):
        super().__init__(parent)
        self.api = api
        self.token = token
        self._current_comparison = None
        self._latest_load = None

        layout = QVBoxLayout(self)

        # Fejléc: Időszakválasztó, Körzetválasztó, Frissítés gomb
        filter_layout = QHBoxLayout()
        self.period_combo = QComboBox()
        self.period_combo.currentIndexChanged.connect(self.on_selection_changed)

        self.zone_combo = QComboBox()
        self.zone_combo.currentIndexChanged.connect(self.on_selection_changed)

        self.btn_refresh = QPushButton("Frissítés")
        self.btn_refresh.clicked.connect(self.load_comparison)

        filter_layout.addWidget(QLabel("Időszak:"))
        filter_layout.addWidget(self.period_combo, 2)
        filter_layout.addWidget(QLabel("Körzet:"))
        filter_layout.addWidget(self.zone_combo, 1)
        filter_layout.addWidget(self.btn_refresh)
        layout.addLayout(filter_layout)

        # Összesítő sáv és Progress Bar
        self.summary_label = QLabel("Válassz időszakot és körzetet...")
        layout.addWidget(self.summary_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addLayout(layout_progress := QHBoxLayout())
        layout_progress.addWidget(self.progress_bar)

        self.closed_badge_label = QLabel("")
        self.closed_badge_label.setStyleSheet("color: red; font-weight: bold;")
        layout_progress.addWidget(self.closed_badge_label)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red;")
        layout.addWidget(self.error_label)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tab_missing = QTableWidget(0, 4)
        self.tab_missing.setHorizontalHeaderLabels(
            ["Leltárszám", "Megnevezés", "Elvárt", "Előkerült máshol"]
        )
        self.tab_missing.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tab_missing.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tab_missing.doubleClicked.connect(
            lambda idx: self.on_row_double_clicked(idx, "MISSING")
        )
        self.tabs.addTab(self.tab_missing, "Hiányzik (0)")

        self.tab_partial_surplus = QTableWidget(0, 7)
        self.tab_partial_surplus.setHorizontalHeaderLabels(
            ["Leltárszám", "Megnevezés", "Állapot", "Elvárt", "Talált", "Eltérés", "Helyiség"]
        )
        self.tab_partial_surplus.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tab_partial_surplus.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tab_partial_surplus.doubleClicked.connect(
            lambda idx: self.on_row_double_clicked(idx, "PARTIAL_SURPLUS")
        )
        self.tabs.addTab(self.tab_partial_surplus, "Részleges és többlet (0)")

        self.tab_found = QTableWidget(0, 5)
        self.tab_found.setHorizontalHeaderLabels(
            ["Leltárszám", "Megnevezés", "Talált", "Ellenőrzés", "Helyiség"]
        )
        self.tab_found.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tab_found.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tab_found.doubleClicked.connect(lambda idx: self.on_row_double_clicked(idx, "FOUND"))
        self.tabs.addTab(self.tab_found, "Megtalált (0)")

        self.tab_foreign = QTableWidget(0, 5)
        self.tab_foreign.setHorizontalHeaderLabels(
            ["Leltárszám", "Megnevezés", "Saját körzet", "Darab", "Helyiség"]
        )
        self.tab_foreign.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tab_foreign.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabs.addTab(self.tab_foreign, "Más körzetből (0)")

        self.tab_unknown = QTableWidget(0, 3)
        self.tab_unknown.setHorizontalHeaderLabels(["Kód", "Darab", "Helyiség"])
        self.tab_unknown.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tab_unknown.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabs.addTab(self.tab_unknown, "Ismeretlen kód (0)")

        # Fejlécek kitöltése adatokkal
        for t in (
            self.tab_missing,
            self.tab_partial_surplus,
            self.tab_found,
            self.tab_foreign,
            self.tab_unknown,
        ):
            t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # Kezdeti metaadat betöltés
        self.load_metadata()

    def load_metadata(self):
        # Időszakok lekérése
        w_per = Worker(self.api.get_periods, self.token)
        w_per.signals.finished.connect(self.on_periods_loaded)
        w_per.signals.error.connect(self.on_error)
        QThreadPool.globalInstance().start(w_per)

        # Körzetek lekérése
        w_zon = Worker(self.api.get_zones, self.token)
        w_zon.signals.finished.connect(self.on_zones_loaded)
        w_zon.signals.error.connect(self.on_error)
        QThreadPool.globalInstance().start(w_zon)

    def on_periods_loaded(self, periods):
        self.period_combo.blockSignals(True)
        self.period_combo.clear()
        active_idx = 0
        for idx, p in enumerate(periods):
            state_text = "aktív" if p.state == "ACTIVE" else "lezárt"
            label = f"{p.name} ({state_text})"
            self.period_combo.addItem(label, p)
            if p.state == "ACTIVE":
                active_idx = idx
        self.period_combo.blockSignals(False)
        if periods:
            self.period_combo.setCurrentIndex(active_idx)
            self.load_comparison()

    def on_zones_loaded(self, zones):
        self.zone_combo.blockSignals(True)
        self.zone_combo.clear()
        for z in zones:
            self.zone_combo.addItem(f"{z.code} · {z.name}", z.code)
        self.zone_combo.blockSignals(False)
        if zones:
            self.load_comparison()

    def on_selection_changed(self):
        self.load_comparison()

    def load_comparison(self):
        period_item = self.period_combo.currentData()
        zone_code = self.zone_combo.currentData()
        if not period_item or not zone_code:
            return

        self.error_label.setText("")
        self.summary_label.setText("Adatok betöltése folyamatban...")

        worker = Worker(self.api.get_comparison, self.token, period_item.id, zone_code)
        worker.signals.finished.connect(self.on_comparison_loaded)
        worker.signals.error.connect(self.on_error)
        self._latest_load = worker.signals
        QThreadPool.globalInstance().start(worker)

    def on_comparison_loaded(self, comparison: ComparisonOut):
        if self.sender() is not self._latest_load:
            return

        self._current_comparison = comparison
        sum_data = comparison.summary
        text = (
            f"Nyilvántartott: {sum_data.expected_assets} · "
            f"Megtalált: {sum_data.found} (ebből a főeszköz alapján: {sum_data.inherited}) · "
            f"Részleges: {sum_data.partial} · "
            f"Hiányzik: {sum_data.missing} · "
            f"Többlet: {sum_data.surplus} · "
            f"Más körzetből: {sum_data.foreign} · "
            f"Ismeretlen kód: {sum_data.unknown}"
        )
        self.summary_label.setText(text)
        self.progress_bar.setValue(int(sum_data.progress_percent))

        if comparison.period.state == "CLOSED":
            self.closed_badge_label.setText("Lezárt időszak, az eredménye végleges.")
        else:
            self.closed_badge_label.setText("")

        # Sorbarendezés a szerződés szerint: MISSING, PARTIAL, SURPLUS, FOUND
        missing_rows = [r for r in comparison.rows if r.category == "MISSING"]
        partial_surplus_rows = [r for r in comparison.rows if r.category in ("PARTIAL", "SURPLUS")]
        found_rows = [r for r in comparison.rows if r.category == "FOUND"]

        # 1. Fül: Hiányzik
        self.tab_missing.setUpdatesEnabled(False)
        self.tab_missing.setRowCount(len(missing_rows))
        for r_idx, row in enumerate(missing_rows):
            self.tab_missing.setItem(r_idx, 0, _id_item(row.asset.inventory_number, row.asset.id))
            self.tab_missing.setItem(r_idx, 1, QTableWidgetItem(row.asset.name))
            self.tab_missing.setItem(r_idx, 2, QTableWidgetItem(str(row.expected)))
            self.tab_missing.setItem(r_idx, 3, QTableWidgetItem(row.found_in_zone or "-"))
        self.tab_missing.setUpdatesEnabled(True)
        self.tabs.setTabText(0, f"Hiányzik ({len(missing_rows)})")

        # 2. Fül: Részleges és többlet
        self.tab_partial_surplus.setUpdatesEnabled(False)
        self.tab_partial_surplus.setRowCount(len(partial_surplus_rows))
        for r_idx, row in enumerate(partial_surplus_rows):
            diff_str = f"+{row.difference}" if row.difference > 0 else str(row.difference)
            status_text = STATUS_LABELS.get(row.status, row.status)
            self.tab_partial_surplus.setItem(
                r_idx, 0, _id_item(row.asset.inventory_number, row.asset.id)
            )
            self.tab_partial_surplus.setItem(r_idx, 1, QTableWidgetItem(row.asset.name))
            self.tab_partial_surplus.setItem(r_idx, 2, QTableWidgetItem(status_text))
            self.tab_partial_surplus.setItem(r_idx, 3, QTableWidgetItem(str(row.expected)))
            self.tab_partial_surplus.setItem(r_idx, 4, QTableWidgetItem(str(row.counted)))
            self.tab_partial_surplus.setItem(r_idx, 5, QTableWidgetItem(diff_str))
            self.tab_partial_surplus.setItem(r_idx, 6, QTableWidgetItem(row.room or "-"))
        self.tab_partial_surplus.setUpdatesEnabled(True)
        self.tabs.setTabText(1, f"Részleges és többlet ({len(partial_surplus_rows)})")

        # 3. Fül: Megtalált
        self.tab_found.setUpdatesEnabled(False)
        self.tab_found.setRowCount(len(found_rows))
        for r_idx, row in enumerate(found_rows):
            ver_text = "közvetlen" if row.verification == "DIRECT" else "főeszköz alapján"
            self.tab_found.setItem(r_idx, 0, _id_item(row.asset.inventory_number, row.asset.id))
            self.tab_found.setItem(r_idx, 1, QTableWidgetItem(row.asset.name))
            self.tab_found.setItem(r_idx, 2, QTableWidgetItem(str(row.counted)))
            self.tab_found.setItem(r_idx, 3, QTableWidgetItem(ver_text))
            self.tab_found.setItem(r_idx, 4, QTableWidgetItem(row.room or "-"))
        self.tab_found.setUpdatesEnabled(True)
        self.tabs.setTabText(2, f"Megtalált ({len(found_rows)})")

        # 4. Fül: Más körzetből
        self.tab_foreign.setUpdatesEnabled(False)
        self.tab_foreign.setRowCount(len(comparison.foreign))
        for r_idx, f in enumerate(comparison.foreign):
            self.tab_foreign.setItem(r_idx, 0, _id_item(f.asset.inventory_number, f.asset.id))
            self.tab_foreign.setItem(r_idx, 1, QTableWidgetItem(f.asset.name))
            self.tab_foreign.setItem(r_idx, 2, QTableWidgetItem(f.home_zone_code))
            self.tab_foreign.setItem(r_idx, 3, QTableWidgetItem(str(f.quantity)))
            self.tab_foreign.setItem(r_idx, 4, QTableWidgetItem(f.room or "-"))
        self.tab_foreign.setUpdatesEnabled(True)
        self.tabs.setTabText(3, f"Más körzetből ({len(comparison.foreign)})")

        # 5. Fül: Ismeretlen kód
        self.tab_unknown.setUpdatesEnabled(False)
        self.tab_unknown.setRowCount(len(comparison.unknown))
        for r_idx, u in enumerate(comparison.unknown):
            self.tab_unknown.setItem(r_idx, 0, QTableWidgetItem(u.raw_code))
            self.tab_unknown.setItem(r_idx, 1, QTableWidgetItem(str(u.quantity)))
            self.tab_unknown.setItem(r_idx, 2, QTableWidgetItem(u.room or "-"))
        self.tab_unknown.setUpdatesEnabled(True)
        self.tabs.setTabText(4, f"Ismeretlen kód ({len(comparison.unknown)})")

    def on_row_double_clicked(self, index, category_hint: str):
        table = self.tabs.currentWidget()
        if not isinstance(table, QTableWidget):
            return
        item = table.item(index.row(), 0)
        if not item:
            return
        asset_id = item.data(Qt.ItemDataRole.UserRole)
        if asset_id and isinstance(asset_id, UUID):
            dlg = AssetDetailDialog(self.api, self.token, asset_id, self)
            dlg.exec()

    def on_error(self, err_msg: str):
        self.error_label.setText(err_msg)
        self.summary_label.setText("Hiba történt az adatok betöltésekor.")
