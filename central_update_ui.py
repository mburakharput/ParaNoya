"""ParaNoya manual update check UI. No installation action or finance database access."""
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QMessageBox

from central_updates import check, load_config, UpdateError
from verified_download import download_verified


class CheckWorker(QObject):
    completed = Signal(object, str)

    def run(self):
        try:
            result = check()
            self.completed.emit(result, "")
        except Exception as exc:
            self.completed.emit(None, str(exc))


class DownloadWorker(QObject):
    completed = Signal(object, str)

    def __init__(self, config, item):
        super().__init__()
        self.config = config
        self.item = item

    def run(self):
        try:
            self.completed.emit(str(download_verified(self.config, self.item,
                cancelled=QThread.currentThread().isInterruptionRequested)), "")
        except Exception as exc:
            self.completed.emit(None, str(exc))


