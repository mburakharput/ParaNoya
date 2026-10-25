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
            self.completed.emit(str(download_verified(self.config, self.item)), "")
        except Exception as exc:
            self.completed.emit(None, str(exc))


class UpdateCheckController(QObject):
    def __init__(self, parent, button):
        super().__init__(parent)
        self.parent_window = parent
        self.button = button
        self.thread = None
        self.worker = None
        self.download_thread = None
        self.download_worker = None

    def start(self):
        if self.thread is not None or self.download_thread is not None:
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
            reply = QMessageBox.question(
                self.parent_window, "İmzalı güncelleme bulundu",
                f"ParaNoya {result['version']} doğrulandı.\\n"
                "Kurulum paketini güvenli biçimde indirmek ister misiniz?\\n"
                "İndirme uygulamayı kapatmaz ve kurulumu başlatmaz.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    config = load_config()
                    if config["updates_enabled"] is not True:
                        raise UpdateError("Güncelleme indirmeleri etkin değil")
                except (OSError, ValueError, UpdateError) as exc:
                    QMessageBox.warning(self.parent_window, "İndirme başlatılamadı", str(exc))
                    return
                self._download(config, result)
        else:
            QMessageBox.information(self.parent_window, "ParaNoya güncellemeleri",
                                    "Şu anda doğrulanmış daha yeni bir sürüm bulunmuyor.")

    def _download(self, config, result):
        if self.download_thread is not None:
            return
        self.button.setEnabled(False)
        self.button.setText("↻  Doğrulanmış paket indiriliyor…")
        thread = QThread(self)
        worker = DownloadWorker(config, result)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._download_done)
        worker.completed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._download_cleanup)
        self.download_thread, self.download_worker = thread, worker
        thread.start()

    def _download_cleanup(self):
        self.download_thread = None
        self.download_worker = None

    def _download_done(self, path, error):
        self.button.setEnabled(True)
        self.button.setText("↻  Güncellemeleri denetle")
        if error:
            QMessageBox.warning(self.parent_window, "Güvenli indirme başarısız", error)
        else:
            QMessageBox.information(
                self.parent_window, "Güvenli indirme tamamlandı",
                "İmzalı kurulum paketi doğrulandı ve indirildi.\\n"
                "Otomatik kurulum henüz etkin değil.\\n"
                f"Dosya: {path}",
            )
