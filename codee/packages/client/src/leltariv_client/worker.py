import traceback
from typing import Callable, Any
from PySide6.QtCore import QRunnable, Slot, Signal, QObject

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
            self.signals.finished.emit(result)
        except Exception as e:
            traceback.print_exc()
            self.signals.error.emit(str(e))