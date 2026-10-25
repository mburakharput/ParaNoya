"""Tests for the opt-in ParaNoya download worker, with no network or installation."""
import unittest
from unittest.mock import patch

from central_update_ui import DownloadWorker

class DownloadWorkerTests(unittest.TestCase):
    def test_download_returns_verified_path(self):
        config={"updates_enabled": True}
        item={"version": "1.2.5.4"}
        worker=DownloadWorker(config,item)
        events=[]
        worker.completed.connect(lambda path,error: events.append((path,error)))
        with patch("central_update_ui.download_verified", return_value="C:/temp/setup.exe") as download:
            worker.run()
        download.assert_called_once_with(config,item)
        self.assertEqual(events,[("C:/temp/setup.exe","")])

    def test_download_failure_is_reported_without_execution(self):
        worker=DownloadWorker({"updates_enabled": True},{"version": "1.2.5.4"})
        events=[]
        worker.completed.connect(lambda path,error: events.append((path,error)))
        with patch("central_update_ui.download_verified", side_effect=RuntimeError("invalid signature")):
            worker.run()
        self.assertEqual(events,[(None,"invalid signature")])

if __name__=="__main__":
    unittest.main()
