"""ParaNoya manual update check UI. No installation action or finance database access."""
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QMessageBox

from central_updates import check, load_config, UpdateError


class CheckWorker(QObject):
    completed = Signal(object, str)

    def run(self):
        try:
            result = check()
            self.completed.emit(result, "")
        except Exception as exc:
            self.completed.emit(None, str(exc))


class UpdateCheckController(QObject):
    def __init__(self, parent, button):
        super().__init__(parent)
        self.parent_window = parent
        self.button = button
        self.thread = None
        self.worker = None

    def start(self):
        if self.thread is not None:
            return
        try:
            config = load_config()
        except (OSError, ValueError, UpdateError):
            QMessageBox.information(self.parent_window, "ParaNoya güncellemeleri",
                                    "Güncelleme hizmeti bu geliştirme sürümünde henüz etkin değil.")
            return
        if not config["updates_enabled"]:
            QMessageBox.information(self.parent_window, "ParaNoya güncellemeleri",
                                    "Güvenli güncelleme sistemi hazırlanıyor. Şimdilik yeni sürümler GitHub üzerinden yayımlanıyor.")
            return
        self.button.setEnabled(False)
        self.button.setText("↻  Denetleniyor…")
        thread = QThread(self)
        worker = CheckWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._finish)
        worker.completed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._cleanup)
        self.thread, self.worker = thread, worker
        thread.start()

    def _cleanup(self):
        self.thread = None
        self.worker = None

    def _finish(self, result, error):
        self.button.setEnabled(True)
        self.button.setText("↻  Güncellemeleri denetle")
        if error:
            QMessageBox.warning(self.parent_window, "Güncelleme denetlenemedi", error)
        elif result:
            QMessageBox.information(
                self.parent_window, "Yeni sürüm bulundu",
                f"ParaNoya {result['version']} doğrulandı. Kurulum işlemi henüz etkin değil.",
            )
        else:
            QMessageBox.information(self.parent_window, "ParaNoya güncellemeleri",
                                    "Şu anda doğrulanmış daha yeni bir sürüm bulunmuyor.")
