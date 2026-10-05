"""A beolvasó képernyő: munkamenet indítása, kódok beolvasása, visszajelzés.

A vonalkódolvasó billentyűzetként viselkedik: karaktereket ad le, majd Entert. Ebből
következik a képernyő három szabálya:

- Enterre a mező azonnal kiürül, hogy a következő kód ne fűződjön az előzőhöz;
- egyszerre egy kérés van úton, a közben érkező kódok sorba állnak, így gyors
  olvasásnál sem vész el és nem cserélődik fel kód;
- a fókusz mindig visszamegy a mezőre, mert az olvasó oda gépel, ahol a fókusz van.
"""

from collections import deque

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from leltariv_client.simulator import ReaderSimulator
from leltariv_client.worker import Worker

#: ennyi beolvasás látszik a listában
RECENT_LIMIT = 10

#: eredmény -> (felirat, világos háttér, sötét háttér). Színnel egyedül jelezni
#: akadálymentességi hiba, ezért a felirat mindig ott van mellette.
FEEDBACK = {
    "FOUND": ("RENDBEN", "#d7f5dd", "#1e4d2b"),
    "FOREIGN_ZONE": ("IDEGEN KÖRZET", "#dde6ff", "#23336b"),
    "UNKNOWN_CODE": ("ISMERETLEN KÓD", "#ffd9d9", "#6b2323"),
    "ERROR": ("HIBA", "#e4e4e4", "#3a3a3a"),
}


class ScanningPage(QWidget):
    def __init__(self, api, token, parent=None):
        super().__init__(parent)
        self.api = api
        self.token = token
        self.zone_codes: list[str] = []
        self.session = None
        self.pending: deque[str] = deque()
        #: az úton lévő kérés (munkamenet, kód); None, ha nincs
        self.in_flight = None

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_start_panel())
        self.stack.addWidget(self._build_scan_panel())
        QVBoxLayout(self).addWidget(self.stack)

        self._run(self.api.get_zones, self.token, on_done=self._on_zones_loaded)

    # --- felépítés ---------------------------------------------------------------

    def _build_start_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("Melyik körzetet leltározod?"))
        self.zone_combo = QComboBox()
        layout.addWidget(self.zone_combo)
        self.start_button = QPushButton("Leltározás indítása")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_session)
        layout.addWidget(self.start_button)
        self.start_error = QLabel()
        self.start_error.setWordWrap(True)
        layout.addWidget(self.start_error)
        layout.addStretch()
        return panel

    def _build_scan_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        header = QHBoxLayout()
        self.header_label = QLabel()
        self.header_label.setFont(QFont(self.font().family(), 14, QFont.Weight.Bold))
        self.finish_button = QPushButton("Befejezés")
        self.finish_button.clicked.connect(self.finish_session)
        header.addWidget(self.header_label)
        header.addStretch()
        header.addWidget(self.finish_button)
        layout.addLayout(header)

        self.scan_input = QLineEdit()
        self.scan_input.setPlaceholderText("Olvasd be a kódot, vagy írd be és nyomj Entert")
        self.scan_input.setFont(QFont(self.font().family(), 18))
        self.scan_input.returnPressed.connect(self.on_enter)
        layout.addWidget(self.scan_input)

        self.feedback = QLabel("Várom az első kódot.")
        self.feedback.setWordWrap(True)
        self.feedback.setMinimumHeight(64)
        self.feedback.setFont(QFont(self.font().family(), 13))
        layout.addWidget(self.feedback)

        lower = QHBoxLayout()
        self.recent = QListWidget()
        lower.addWidget(self.recent, stretch=2)
        self.simulator = ReaderSimulator(self.scan_input, self.on_enter)
        lower.addWidget(self.simulator, stretch=1)
        layout.addLayout(lower)
        return panel

    # --- munkamenet --------------------------------------------------------------

    def _on_zones_loaded(self, zones) -> None:
        self.zone_codes = [zone.code for zone in zones]
        self.zone_combo.addItems(self.zone_codes)
        self.start_button.setEnabled(bool(self.zone_codes))

    def start_session(self) -> None:
        self.start_button.setEnabled(False)
        self.start_error.clear()
        zone = self.zone_combo.currentText()
        self._run(
            self.api.start_session,
            self.token,
            zone,
            on_done=self._on_session_started,
            on_error=self._on_session_failed,
        )

    def _on_session_started(self, session) -> None:
        self.session = session
        self.pending.clear()
        self.recent.clear()
        self.header_label.setText(f"{session.zone_code} · {session.period_name}")
        self._show_feedback("", "Várom az első kódot.")
        other = next((code for code in self.zone_codes if code != session.zone_code), None)
        self.simulator.load(self.api, self.token, session.zone_code, other)
        self.start_button.setEnabled(True)
        self.stack.setCurrentIndex(1)
        self.scan_input.setFocus()

    def _on_session_failed(self, message: str) -> None:
        # A 409 „Nincs nyitott leltári időszak." mondata szó szerint jelenik meg.
        self.start_error.setText(message)
        self.start_button.setEnabled(True)

    def finish_session(self) -> None:
        self.session = None
        self.pending.clear()
        self.stack.setCurrentIndex(0)

    # --- beolvasás ---------------------------------------------------------------

    def on_enter(self) -> None:
        code = self.scan_input.text().strip()
        self.scan_input.clear()
        self.scan_input.setFocus()
        if code and self.session is not None:
            self.pending.append(code)
            self._send_next()

    @property
    def busy(self) -> bool:
        return self.in_flight is not None

    def _send_next(self) -> None:
        if self.busy or not self.pending or self.session is None:
            return
        code = self.pending.popleft()
        self.in_flight = (self.session, code)
        # Kötött metódus kell, nem lambda: csak így fut a válasz a felületi szálon.
        self._run(
            self.api.post_scan,
            self.token,
            self.session.id,
            code,
            on_done=self._on_scan_done,
            on_error=self._on_scan_failed,
        )

    def _finish_request(self) -> str | None:
        """Lezárja az úton lévő kérést; a kódot adja vissza, ha a munkamenet még él."""
        assert self.in_flight is not None
        session, code = self.in_flight
        self.in_flight = None
        return code if session is self.session else None

    def _on_scan_done(self, scan) -> None:
        if self._finish_request() is not None:
            self._show_feedback(scan.result, scan.message)
            self._add_recent(f"{FEEDBACK[scan.result][0]}  ·  {scan.raw_code}  ·  {scan.message}")
        self._send_next()

    def _on_scan_failed(self, message: str) -> None:
        code = self._finish_request()
        if code is not None:
            self._show_feedback("ERROR", f"A(z) {code} kód nem ment át: {message}")
            self._add_recent(f"HIBA  ·  {code}  ·  {message}")
        self._send_next()

    # --- megjelenítés ------------------------------------------------------------

    def _show_feedback(self, result: str, message: str) -> None:
        if result not in FEEDBACK:
            self.feedback.setText(message)
            self.feedback.setStyleSheet("")
            return
        label, light, dark = FEEDBACK[result]
        is_dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
        self.feedback.setText(f"<b>{label}</b><br>{message}")
        self.feedback.setStyleSheet(
            f"background: {dark if is_dark else light}; padding: 10px; border-radius: 6px;"
        )
        self.scan_input.setFocus()

    def _add_recent(self, line: str) -> None:
        self.recent.insertItem(0, line)
        while self.recent.count() > RECENT_LIMIT:
            self.recent.takeItem(self.recent.count() - 1)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.session is not None:
            self.scan_input.setFocus()

    def _run(self, fn, *args, on_done, on_error=None) -> None:
        worker = Worker(fn, *args)
        worker.signals.finished.connect(on_done)
        worker.signals.error.connect(on_error or self._on_session_failed)
        QThreadPool.globalInstance().start(worker)
