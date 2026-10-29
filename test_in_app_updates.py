import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QWidget,QPushButton,QMessageBox,QStackedWidget,QDialog
from PySide6.QtCore import QObject,Signal,QEventLoop,QTimer
from in_app_updates import UpdateCheckController,PrepareWorker
from finance_core import migrate


class Host(QWidget):
    def __init__(self):
        super().__init__();self.closed=0;self.stack=QStackedWidget(self);self.stack.addWidget(QWidget())
    def close(self):self.closed+=1;return True


class InAppUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.host=Host();self.button=QPushButton(self.host);self.controller=UpdateCheckController(self.host,self.button)
        self.addCleanup(self.host.deleteLater)
    def test_open_form_blocks_update_check(self):
        self.host.stack.addWidget(QDialog());self.host.stack.setCurrentIndex(1)
        with patch('in_app_updates.QMessageBox.information'),patch.object(self.controller,'_start') as start:
            self.controller.start();start.assert_not_called()
    def test_declined_download_does_not_start_worker(self):
        with patch('in_app_updates.QMessageBox.question',return_value=QMessageBox.StandardButton.No),patch.object(self.controller,'_start') as start:
            self.controller._checked({'version':'9.0.0'},'');start.assert_not_called()
    def test_declined_install_preserves_running_app(self):
        with patch('in_app_updates.QMessageBox.question',return_value=QMessageBox.StandardButton.No),patch.object(self.controller,'_start') as start:
            self.controller._download_done('synthetic.exe','');start.assert_not_called()
        self.assertEqual(self.host.closed,0);self.assertTrue(self.host.isEnabled())
    def test_prepare_error_keeps_app_open_and_enabled(self):
        self.host.setEnabled(False)
        with patch('in_app_updates.QMessageBox.warning'):
            self.controller._prepared(None,'backup failed')
        self.assertEqual(self.host.closed,0);self.assertTrue(self.host.isEnabled())
    def test_helper_ready_must_match_both_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.controller._request=root/'update-request.json'
            self.controller._process=Mock(pid=12345);self.controller._process.poll.return_value=None
            (root/'update-ready.json').write_text(json.dumps({'helper_pid':99999,'app_pid':os.getpid()}))
            with patch('in_app_updates.QMessageBox.warning'):self.controller._poll_helper()
            self.assertEqual(self.host.closed,0);self.controller._process.terminate.assert_called_once()
    def test_matching_handshake_closes_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.controller._request=root/'update-request.json';self.controller._process=Mock(pid=12345)
            (root/'update-ready.json').write_text(json.dumps({'helper_pid':12345,'app_pid':os.getpid()}))
            self.controller._poll_helper();self.assertEqual(self.host.closed,1)
    def test_thread_finishes_before_result_callback(self):
        class Worker(QObject):
            completed=Signal(object,str)
            def run(self):self.completed.emit('ok','')
        loop=QEventLoop();values=[]
        def done(*result):values.append((result,self.controller.is_busy));loop.quit()
        self.controller._start(Worker(),done,'test')
        QTimer.singleShot(3000,loop.quit);loop.exec()
        self.assertEqual(values,[(('ok',''),False)])
    def test_closing_during_work_suppresses_result_dialog(self):
        class Worker(QObject):
            completed=Signal(object,str)
            def run(self):self.completed.emit(None,'cancelled')
        loop=QEventLoop();callback=Mock()
        self.controller._start(Worker(),callback,'test');self.assertTrue(self.controller.request_close())
        timer=QTimer();timer.timeout.connect(lambda:loop.quit() if not self.controller.is_busy else None);timer.start(10)
        QTimer.singleShot(3000,loop.quit);loop.exec();timer.stop()
        callback.assert_not_called();self.assertEqual(self.host.closed,1)
    def test_failed_backup_never_creates_handoff_request(self):
        worker=PrepareWorker('synthetic.exe',{});results=[];worker.completed.connect(lambda *args:results.append(args))
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'LOCALAPPDATA':tmp}),patch('in_app_updates.prepare_handoff',return_value={}),patch('backup_manager.make_backup',side_effect=OSError('disk full')),patch('in_app_updates.write_request') as request:
            worker.run();request.assert_not_called()
        self.assertIn('disk full',results[0][1])
    def test_backup_is_verified_and_original_database_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'finance';data.mkdir();migrate(data/'ailefinans.db')
            original=(data/'ailefinans.db').read_bytes();results=[]
            worker=PrepareWorker('synthetic.exe',{});worker.completed.connect(lambda *args:results.append(args))
            with patch.dict(os.environ,{'LOCALAPPDATA':str(root/'local')}),patch('finance_core.DB_DIR',data),patch('in_app_updates.prepare_handoff',return_value={}),patch('in_app_updates.write_request',return_value=(root/'request',root/'helper')):
                worker.run()
            self.assertEqual(results[0][1],'');self.assertTrue(Path(results[0][0]['backup']).is_file())
            self.assertEqual((data/'ailefinans.db').read_bytes(),original)
