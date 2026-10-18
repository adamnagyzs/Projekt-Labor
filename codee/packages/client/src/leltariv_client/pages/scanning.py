"""A beolvasó képernyő: munkamenet, helyiség, darabszám, beolvasás, visszavonás, lezárás.

A vonalkódolvasó billentyűzetként viselkedik: karaktereket ad le, majd Entert. Ebből
következik a képernyő szabályai:

- Enterre a mező azonnal kiürül, hogy a következő kód ne fűződjön az előzőhöz;
- egyszerre egy kérés van úton, a közben érkező kódok sorba állnak, így gyors
  olvasásnál sem vész el és nem cserélődik fel kód;
- a sorba a kód a darabszámmal és a helyiséggel együtt kerül, abban a pillanatban,
  amikor az Enter jött: a később átállított helyiség nem íródhat rá a még úton lévő kódra;
- a visszavonás ugyanazon a soron megy át, különben megelőzhetné azt, amit visszavon;
- a fókusz mindig visszamegy a mezőre, mert az olvasó oda gépel, ahol a fókusz van.
"""

from collections import deque
from dataclasses import dataclass
from uuid import UUID

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QFont, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
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
    "SURPLUS": ("TÖBBLET", "#ffe2c2", "#6b4116"),
    "FOREIGN_ZONE": ("IDEGEN KÖRZET", "#dde6ff", "#23336b"),
    "UNKNOWN_CODE": ("ISMERETLEN KÓD", "#ffd9d9", "#6b2323"),
    "UNDONE": ("VISSZAVONVA", "#e4e4e4", "#3a3a3a"),
    "ERROR": ("HIBA", "#e4e4e4", "#3a3a3a"),
}

#: a listaelemben ezen a szerepen ül a beolvasás azonosítója, amíg vissza nem vonják
SCAN_ID_ROLE = Qt.ItemDataRole.UserRole


@dataclass(frozen=True)
class ScanRequest:
    code: str
    quantity: int
    room_id: UUID | None


@dataclass(frozen=True)
class UndoRequest:
    scan_id: UUID
    item: QListWidgetItem


class ScanningPage(QWidget):
    def __init__(self, api, token, parent=None):
        super().__init__(parent)
        self.api = api
        self.token = token
        self.zone_codes: list[str] = []
        self.session = None
        self.pending: deque[ScanRequest | UndoRequest] = deque()
        #: az úton lévő kérés (munkamenet, kérés); None, ha nincs
        self.in_flight = None
        #: a Befejezést megnyomták: a sor kiürülése után lezárjuk a munkamenetet
        self.closing = False

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_start_panel())
        self.stack.addWidget(self._build_scan_panel())
        QVBoxLayout(self).addWidget(self.stack)

        undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        undo_shortcut.activated.connect(self.undo_selected)

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
        self.room_combo = QComboBox()
        self.room_combo.setMinimumWidth(180)
        self.room_combo.activated.connect(lambda _index: self.scan_input.setFocus())
        self.finish_button = QPushButton("Befejezés")
        self.finish_button.clicked.connect(self.finish_session)
        header.addWidget(self.header_label)
        header.addStretch()
        header.addWidget(QLabel("Helyiség:"))
        header.addWidget(self.room_combo)
        header.addWidget(self.finish_button)
        layout.addLayout(header)

        input_row = QHBoxLayout()
        self.scan_input = QLineEdit()
        self.scan_input.setPlaceholderText("Olvasd be a kódot, vagy írd be és nyomj Entert")
        self.scan_input.setFont(QFont(self.font().family(), 18))
        self.scan_input.returnPressed.connect(self.on_enter)
        # A darabszámot a beolvasás előtt lehet megadni, így az olvasó Entere után nem kell
        # még egy ablak. Minden beolvasás után visszaáll 1-re.
        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(1, 9999)
        self.quantity_input.setSuffix(" db")
        self.quantity_input.setFont(QFont(self.font().family(), 14))
        self.quantity_input.editingFinished.connect(self.scan_input.setFocus)
        input_row.addWidget(self.scan_input, stretch=1)
        input_row.addWidget(self.quantity_input)
        layout.addLayout(input_row)

        self.feedback = QLabel("Várom az első kódot.")
        self.feedback.setWordWrap(True)
        self.feedback.setMinimumHeight(64)
        self.feedback.setFont(QFont(self.font().family(), 13))
        layout.addWidget(self.feedback)

        lower = QHBoxLayout()
        recent_column = QVBoxLayout()
        self.recent = QListWidget()
        self.undo_button = QPushButton("Visszavonás (Ctrl+Z)")
        self.undo_button.clicked.connect(self.undo_selected)
        recent_column.addWidget(self.recent)
        recent_column.addWidget(self.undo_button, alignment=Qt.AlignmentFlag.AlignLeft)
        lower.addLayout(recent_column, stretch=2)
        self.simulator = ReaderSimulator(self.scan_input, self.on_enter)
        lower.addWidget(self.simulator, stretch=1, alignment=Qt.AlignmentFlag.AlignTop)
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
        self.closing = False
        self.pending.clear()
        self.recent.clear()
        self.quantity_input.setValue(1)
        self.room_combo.clear()
        self.room_combo.addItem("— nincs megadva —", None)
        self.header_label.setText(f"{session.zone_code} · {session.period_name}")
        self._set_inputs_enabled(True)
        self._show_feedback("", "Várom az első kódot.")
        other = next((code for code in self.zone_codes if code != session.zone_code), None)
        self.simulator.load(self.api, self.token, session.zone_code, other)
        self._run(
            self.api.get_rooms,
            self.token,
            session.zone_code,
            on_done=self._on_rooms_loaded,
            on_error=self._on_rooms_failed,
        )
        self.start_button.setEnabled(True)
        self.stack.setCurrentIndex(1)
        self.scan_input.setFocus()

    def _on_rooms_loaded(self, rooms) -> None:
        for room in rooms:
            self.room_combo.addItem(room.label, room.id)

    def _on_rooms_failed(self, message: str) -> None:
        # Helyiség nélkül is lehet leltározni; a hiba ne állítsa meg a beolvasást.
        self._show_feedback("ERROR", f"A helyiségek nem töltődtek be: {message}")

    def _on_session_failed(self, message: str) -> None:
        # A 409 „Nincs nyitott leltári időszak." mondata szó szerint jelenik meg.
        self.start_error.setText(message)
        self.start_button.setEnabled(True)

    def finish_session(self) -> None:
        if self.session is None:
            return
        self.closing = True
        self._set_inputs_enabled(False)
        self._show_feedback("", "Lezárás: megvárom a még úton lévő beolvasásokat…")
        self._close_if_idle()

    def _close_if_idle(self) -> None:
        if not self.closing or self.busy or self.pending or self.session is None:
            return
        self._run(
            self.api.close_session,
            self.token,
            self.session.id,
            on_done=self._on_session_closed,
            on_error=self._on_close_failed,
        )

    def _on_session_closed(self, _session) -> None:
        self.session = None
        self.closing = False
        self.pending.clear()
        self.stack.setCurrentIndex(0)

    def _on_close_failed(self, message: str) -> None:
        self.closing = False
        self._set_inputs_enabled(True)
        self._show_feedback("ERROR", f"A munkamenet nem zárult le: {message}")

    def _set_inputs_enabled(self, enabled: bool) -> None:
        for widget in (
            self.scan_input,
            self.quantity_input,
            self.room_combo,
            self.undo_button,
            self.finish_button,
        ):
            widget.setEnabled(enabled)

    # --- beolvasás és visszavonás --------------------------------------------------

    def on_enter(self) -> None:
        code = self.scan_input.text().strip()
        self.scan_input.clear()
        self.scan_input.setFocus()
        if not code or self.session is None or self.closing:
            return
        # Pillanatkép: a darabszám és a helyiség most dől el, nem a küldéskor.
        self.pending.append(
            ScanRequest(code, self.quantity_input.value(), self.room_combo.currentData())
        )
        self.quantity_input.setValue(1)
        self._send_next()

    def undo_selected(self) -> None:
        if self.session is None or self.closing:
            return
        # Kijelölés nélkül a legutóbbi beolvasás; ha az már visszavont vagy hiba, nincs mit tenni.
        item = (self.recent.currentItem() or self.recent.item(0)) if self.recent.count() else None
        scan_id = item.data(SCAN_ID_ROLE) if item else None
        if not item or scan_id is None:
            self._show_feedback("", "Nincs visszavonható beolvasás kijelölve.")
            return
        # Ne lehessen ugyanazt kétszer sorba állítani; a szerver amúgy 409-et adna.
        item.setData(SCAN_ID_ROLE, None)
        self.pending.append(UndoRequest(scan_id, item))
        self._send_next()

    @property
    def busy(self) -> bool:
        return self.in_flight is not None

    def _send_next(self) -> None:
        if self.busy or self.session is None:
            return
        if not self.pending:
            self._close_if_idle()
            return
        request = self.pending.popleft()
        self.in_flight = (self.session, request)
        # Kötött metódus kell, nem lambda: csak így fut a válasz a felületi szálon.
        if isinstance(request, ScanRequest):
            self._run(
                self.api.post_scan,
                self.token,
                self.session.id,
                request.code,
                request.quantity,
                request.room_id,
                on_done=self._on_scan_done,
                on_error=self._on_request_failed,
            )
        else:
            self._run(
                self.api.undo_scan,
                self.token,
                self.session.id,
                request.scan_id,
                on_done=self._on_undo_done,
                on_error=self._on_request_failed,
            )

    def _finish_request(self) -> ScanRequest | UndoRequest | None:
        """Lezárja az úton lévő kérést; a kérést adja vissza, ha a munkamenet még él."""
        assert self.in_flight is not None
        session, request = self.in_flight
        self.in_flight = None
        return request if session is self.session else None

    def _on_scan_done(self, scan) -> None:
        if self._finish_request() is not None:
            self._show_feedback(scan.result, scan.message)
            self._add_recent(scan, f"{FEEDBACK[scan.result][0]}  ·  {scan.raw_code}")
        self._send_next()

    def _on_undo_done(self, scan) -> None:
        request = self._finish_request()
        if isinstance(request, UndoRequest):
            font = request.item.font()
            font.setStrikeOut(True)
            request.item.setFont(font)
            self._show_feedback("UNDONE", scan.message)
            self._add_recent(None, f"VISSZAVONVA  ·  {scan.raw_code}  ·  {scan.message}")
        self._send_next()

    def _on_request_failed(self, message: str) -> None:
        request = self._finish_request()
        if isinstance(request, ScanRequest):
            self._show_feedback("ERROR", f"A(z) {request.code} kód nem ment át: {message}")
            self._add_recent(None, f"HIBA  ·  {request.code}  ·  {message}")
        elif isinstance(request, UndoRequest):
            self._show_feedback("ERROR", f"A visszavonás nem sikerült: {message}")
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

    def _add_recent(self, scan, prefix: str) -> None:
        text = prefix if scan is None else f"{prefix}  ·  {scan.message}"
        if scan is not None and scan.room:
            text += f"  ·  {scan.room}"
        item = QListWidgetItem(text)
        if scan is not None:
            item.setData(SCAN_ID_ROLE, scan.id)
        self.recent.insertItem(0, item)
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
