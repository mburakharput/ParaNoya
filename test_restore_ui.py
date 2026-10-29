import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock,patch
from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication,QWidget,QMessageBox
from ailefinans import App


class RestoreConsentTests(TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def host(self):
        host=QWidget();host.close=Mock();self.addCleanup(host.deleteLater)
        return host

    def test_declined_restore_never_closes_or_schedules_replacement(self):
        host=self.host()
        with patch('ailefinans.QFileDialog.getOpenFileName',return_value=('synthetic.zip','')),patch('backup_manager.verify_backup') as verify,patch('ailefinans.QMessageBox.question',return_value=QMessageBox.StandardButton.No):
            App.restore_from_backup(host)
        verify.assert_called_once_with('synthetic.zip')
        host.close.assert_not_called();self.assertFalse(hasattr(host,'_pending_restore'))

    def test_invalid_backup_never_prompts_or_closes(self):
        host=self.host()
        with patch('ailefinans.QFileDialog.getOpenFileName',return_value=('synthetic.zip','')),patch('backup_manager.verify_backup',side_effect=ValueError('synthetic failure')),patch('ailefinans.QMessageBox.question') as question,patch('ailefinans.QMessageBox.warning'):
            App.restore_from_backup(host)
        question.assert_not_called();host.close.assert_not_called()

    def test_confirmed_restore_schedules_work_after_window_closes(self):
        host=self.host()
        with patch('ailefinans.QFileDialog.getOpenFileName',return_value=('synthetic.zip','')),patch('backup_manager.verify_backup'),patch('ailefinans.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes),patch('backup_manager.restore_backup') as restore:
            App.restore_from_backup(host)
        self.assertEqual(host._pending_restore,'synthetic.zip');host.close.assert_called_once()
        restore.assert_not_called();self.assertFalse(host.isEnabled())

    def test_second_application_lock_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'synthetic.lock');first=QLockFile(path);second=QLockFile(path)
            self.assertTrue(first.tryLock(0))
            try:self.assertFalse(second.tryLock(0))
            finally:first.unlock()
