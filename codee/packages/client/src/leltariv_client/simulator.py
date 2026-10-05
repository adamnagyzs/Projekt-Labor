"""Vonalkódolvasó-szimulátor: a valódi olvasóhoz hasonlóan karakterenként gépel, majd Enter."""

import random
from collections.abc import Callable

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QGroupBox, QLineEdit, QPushButton, QVBoxLayout

from leltariv_client.worker import Worker


class ReaderSimulator(QGroupBox):
    def __init__(self, target: QLineEdit, on_enter: Callable[[], None], parent=None):
        super().__init__("Olvasó-szimulátor", parent)
        self.target = target
        self.on_enter = on_enter

        self.active_codes = []
        self.other_codes = []

        layout = QVBoxLayout(self)
        self.btn_valid = QPushButton("Érvényes kód")
        self.btn_foreign = QPushButton("Idegen körzet kódja")
        self.btn_invalid = QPushButton("Érvénytelen kód")

        self.btn_valid.setEnabled(False)
        self.btn_foreign.setEnabled(False)
        self.btn_invalid.setEnabled(False)

        layout.addWidget(self.btn_valid)
        layout.addWidget(self.btn_foreign)
        layout.addWidget(self.btn_invalid)

        self.btn_valid.clicked.connect(self._simulate_valid)
        self.btn_foreign.clicked.connect(self._simulate_foreign)
        self.btn_invalid.clicked.connect(self._simulate_invalid)

        self.type_timer = QTimer(self)
        self.type_timer.setInterval(15)  # 15ms egy karakter
        self.type_timer.timeout.connect(self._type_next_char)

        self.current_code_to_type = ""
        self.typing_index = 0

    def load(self, api, token: str, active_zone: str, other_zone: str | None) -> None:
        self.active_codes = []
        self.other_codes = []
        self.btn_valid.setEnabled(False)
        self.btn_foreign.setEnabled(False)
        self.btn_invalid.setEnabled(True)

        def start(zone: str, on_loaded: Callable[[object], None]) -> None:
            worker = Worker(api.get_assets, token, zone, None, 1, 50)
            worker.signals.finished.connect(on_loaded)
            worker.signals.error.connect(lambda e: print("Szimulátor hiba:", e))
            QThreadPool.globalInstance().start(worker)

        # Az idegen körzet csak az aktív után jön, mert a kettő közös kódjait ki kell szűrni.
        def on_active_loaded(page_data) -> None:
            self._on_active_loaded(page_data)
            if other_zone:
                start(other_zone, self._on_other_loaded)

        start(active_zone, on_active_loaded)

    def _on_active_loaded(self, page_data):
        self.active_codes = [i.inventory_number for i in page_data.items if i.inventory_number]
        self.btn_valid.setEnabled(bool(self.active_codes))

    def _on_other_loaded(self, page_data):
        # Ami az aktív körzetben is szerepel (pl. 024540), az ott FOUND lenne, ezért kimarad.
        codes = {i.inventory_number for i in page_data.items if i.inventory_number}
        self.other_codes = sorted(codes - set(self.active_codes))
        self.btn_foreign.setEnabled(bool(self.other_codes))

    def _simulate_valid(self):
        if self.active_codes:
            self._start_typing(random.choice(self.active_codes))

    def _simulate_foreign(self):
        if self.other_codes:
            self._start_typing(random.choice(self.other_codes))

    def _simulate_invalid(self):
        self._start_typing(f"X{random.randint(100000, 999999)}")

    def _start_typing(self, code: str):
        # Gombok tiltása gépelés alatt
        self.btn_valid.setEnabled(False)
        self.btn_foreign.setEnabled(False)
        self.btn_invalid.setEnabled(False)

        self.target.clear()
        self.current_code_to_type = code
        self.typing_index = 0
        self.type_timer.start()

    def _type_next_char(self):
        if self.typing_index < len(self.current_code_to_type):
            self.target.setText(self.target.text() + self.current_code_to_type[self.typing_index])
            self.typing_index += 1
        else:
            self.type_timer.stop()
            self.on_enter()  # Végpont hívása (Enter szimulálása)

            # Gombok visszaállítása
            self.btn_valid.setEnabled(len(self.active_codes) > 0)
            self.btn_foreign.setEnabled(len(self.other_codes) > 0)
            self.btn_invalid.setEnabled(True)
