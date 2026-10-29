"""Consent-driven signed updates with background work and safe process handoff."""
import json
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime
from PySide6.QtCore import QObject,QThread,Signal,QTimer
from PySide6.QtWidgets import QMessageBox,QDialog
from central_updates import load_config,UpdateError
from central_update_ui import CheckWorker,DownloadWorker
from update_handoff import prepare_handoff
from update_agent import write_request


class PrepareWorker(QObject):
    completed=Signal(object,str)
    def __init__(self,installer,item):
        super().__init__();self.installer=installer;self.item=item
    def run(self):
        try:
            plan=prepare_handoff(self.installer,self.item,explicitly_confirmed=True)
            from finance_core import DB_DIR
            from backup_manager import make_backup,verify_backup
            local=os.environ.get('LOCALAPPDATA')
            if not local:raise UpdateError('Yedek klasörü belirlenemedi')
            backup=Path(local)/'ParaNoya'/'UpdateBackups'/('before-'+load_config()['version']+'-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.zip')
            make_backup(DB_DIR,backup);verify_backup(backup)
            request,helper=write_request(self.installer,self.item,plan,confirmed=True,app_pid=os.getpid())
            self.completed.emit({'request':str(request),'helper':str(helper),'backup':str(backup)},'')
        except Exception as exc:self.completed.emit(None,str(exc))


class UpdateCheckController(QObject):
    def __init__(self,parent,button):
        super().__init__(parent)
        self.parent_window=parent;self.button=button;self._threads=set()
        self._close_pending=False;self._handoff_started=False
        self._process=None;self._request=None;self._deadline=0
        self._timer=QTimer(self);self._timer.setInterval(200);self._timer.timeout.connect(self._poll_helper)
        self.item=None

    @property
    def is_busy(self):return bool(self._threads or self._timer.isActive())

    def _has_form(self):
        host=self.parent_window
        current=host.stack.currentWidget() if hasattr(host,'stack') else None
        return isinstance(current,QDialog) or getattr(host,'inline_page',None) is not None

    def start(self):
        if self.is_busy:return
        if self._has_form():
            QMessageBox.information(self.parent_window,'Açık işlem formu','Önce açık formu kaydedin veya iptal edin.');return
        try:
            if load_config()['updates_enabled'] is not True:raise UpdateError('Güncelleme hizmeti bu sürümde kapalı')
        except (OSError,ValueError,UpdateError) as exc:
            QMessageBox.warning(self.parent_window,'Güncelleme ayarları',str(exc));return
        self._start(CheckWorker(),self._checked,'Güncellemeler denetleniyor…')

    def _start(self,worker,callback,label):
        self.button.setEnabled(False);self.button.setText(label)
        thread=QThread(self);worker.moveToThread(thread);self._threads.add(thread)
        result=[]
        worker.completed.connect(lambda value,error:result.append((value,error)))
        worker.completed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        thread.started.connect(worker.run)
        def finished():
            self._threads.discard(thread);thread.deleteLater()
            if self._close_pending:
                self.parent_window.setEnabled(True)
                if not self._threads:self.parent_window.close()
                return
            self.button.setEnabled(True);self.button.setText('↻  Güncellemeleri denetle')
            callback(*(result[0] if result else (None,'Güncelleme işi tamamlanamadı')))
        thread.finished.connect(finished)
        thread._worker=worker
        thread.start()

    def _checked(self,item,error):
        if error:
            QMessageBox.warning(self.parent_window,'Güncelleme denetlenemedi',error);return
        if not item:
            QMessageBox.information(self.parent_window,'ParaNoya güncellemeleri','Daha yeni, imzası doğrulanmış bir sürüm bulunmuyor.');return
        self.item=item
        if QMessageBox.question(self.parent_window,'Yeni sürüm bulundu',
                f"ParaNoya {item['version']} yayıncı imzasıyla doğrulandı.\nKurulum paketini indirmek ister misiniz?",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:
            self._start(DownloadWorker(load_config(),item),self._download_done,'Güncelleme indiriliyor…')

    def _download_done(self,path,error):
        if error:
            QMessageBox.warning(self.parent_window,'İndirme başarısız',error);return
        if self._has_form():
            QMessageBox.information(self.parent_window,'Açık işlem formu','Paket indirildi. Açık formu kapattıktan sonra güncellemeyi yeniden başlatın.');return
        if QMessageBox.question(self.parent_window,'Güncellemeyi kur',
                'Kurulum dosyasının imzası, boyutu ve özeti doğrulandı.\n'
                'Finans verilerinin yedeği alındıktan sonra ParaNoya kapanacak ve kurulum açılacak.\n'
                'Şimdi güncellemek istiyor musunuz?',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        self.parent_window.setEnabled(False)
        self._start(PrepareWorker(path,self.item),self._prepared,'Yedek alınıyor, güncelleme hazırlanıyor…')

    def _prepared(self,result,error):
        if error:
            self.parent_window.setEnabled(True)
            QMessageBox.warning(self.parent_window,'Güncelleme başlatılmadı',error);return
        self._request=Path(result['request'])
        try:
            self._process=subprocess.Popen([result['helper'],'--request',str(self._request)],
                shell=False,close_fds=True,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.DETACHED_PROCESS)
        except OSError as exc:
            self.parent_window.setEnabled(True)
            QMessageBox.warning(self.parent_window,'Güncelleme yardımcısı açılamadı',str(exc));return
        self.button.setText('Kuruluma geçiliyor…');self._deadline=time.monotonic()+90;self._timer.start()

    def _poll_helper(self):
        folder=self._request.parent;ready=folder/'update-ready.json'
        if ready.is_file():
            try:
                state=json.loads(ready.read_text(encoding='utf-8'))
                if state!={'helper_pid':self._process.pid,'app_pid':os.getpid()}:raise UpdateError('Yardımcı işlem doğrulanamadı')
            except (OSError,ValueError,UpdateError) as exc:
                self._cancel_handoff(str(exc));return
            self._timer.stop();self._handoff_started=True;self.parent_window.close();return
        if self._process.poll() is not None or time.monotonic()>self._deadline:
            message='Güncelleme yardımcısı hazır olamadı; uygulama açık kaldı.'
            error=folder/'update-error.txt'
            if error.is_file():message=error.read_text(encoding='utf-8')[:2000]
            self._cancel_handoff(message)

    def _cancel_handoff(self,message=None):
        self._timer.stop()
        if self._request:(self._request.parent/'update-cancelled').touch(exist_ok=True)
        if self._process and self._process.poll() is None:self._process.terminate()
        self.parent_window.setEnabled(True);self.button.setEnabled(True);self.button.setText('↻  Güncellemeleri denetle')
        if message:QMessageBox.warning(self.parent_window,'Güncelleme başlatılmadı',message)

    def request_close(self):
        if self._threads:
            self._close_pending=True
            for thread in self._threads:thread.requestInterruption()
            return True
        if self._timer.isActive() and not self._handoff_started:self._cancel_handoff()
        return False
