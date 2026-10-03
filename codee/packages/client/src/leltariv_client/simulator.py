import random
from typing import Callable
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QPushButton, QLineEdit
from PySide6.QtCore import QTimer, QThreadPool
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
        self.type_timer.setInterval(15) # 15ms egy karakter
        self.type_timer.timeout.connect(self._type_next_char)
        
        self.current_code_to_type = ""
        self.typing_index = 0

    def load(self, api, token: str, active_zone: str, other_zone: str | None) -> None:
        self.active_codes = []
        self.other_codes = []
        
        # Aktív körzet betöltése
        w_active = Worker(api.get_assets, token, active_zone, "", 1, 50)
        w_active.signals.finished.connect(self._on_active_loaded)
        w_active.signals.error.connect(lambda e: print("Szimulátor hiba (aktív):", e))
        QThreadPool.globalInstance().start(w_active)
        
        # Idegen körzet betöltése, ha van
        if other_zone:
            w_other = Worker(api.get_assets, token, other_zone, "", 1, 50)
            w_other.signals.finished.connect(self._on_other_loaded)
            w_other.signals.error.connect(lambda e: print("Szimulátor hiba (idegen):", e))
            QThreadPool.globalInstance().start(w_other)
        
        self.btn_invalid.setEnabled(True)

    def _on_active_loaded(self, page_data):
        self.active_codes = [item.inventory_number for item in page_data.items if item.inventory_number]
        if self.active_codes:
            self.btn_valid.setEnabled(True)

    def _on_other_loaded(self, page_data):
        self.other_codes = [item.inventory_number for item in page_data.items if item.inventory_number]
        if self.other_codes:
            self.btn_foreign.setEnabled(True)

    def _simulate_valid(self):
        if self.active_codes:
            self._start_typing(random.choice(self.active_codes))

    def _simulate_foreign(self):
        if self.other_codes:
            # A fake API esetében hogy működjön az 1-essel kezdődés elve is tesztelésnél
            code = random.choice(self.other_codes)
            if not code.startswith("1"):
                code = "1" + code 
            self._start_typing(code)

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
            self.on_enter() # Végpont hívása (Enter szimulálása)
            
            # Gombok visszaállítása
            self.btn_valid.setEnabled(len(self.active_codes) > 0)
            self.btn_foreign.setEnabled(len(self.other_codes) > 0)
            self.btn_invalid.setEnabled(True)