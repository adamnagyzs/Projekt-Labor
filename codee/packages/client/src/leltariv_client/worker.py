import contextlib
import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)


class Worker(QRunnable):
    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            traceback.print_exc()
            self._emit(self.signals.error, str(e))
        else:
            self._emit(self.signals.finished, result)

    @staticmethod
    def _emit(signal: Any, value: object) -> None:
        # Ha a kérés közben bezárták az ablakot vagy kiléptek a programból, a jelzés Qt-oldali
        # objektuma már nem létezik; a választ ilyenkor nincs kinek megmutatni.
        with contextlib.suppress(RuntimeError):
            signal.emit(value)
