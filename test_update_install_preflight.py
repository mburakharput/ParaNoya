import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from central_updates import UpdateError
from update_install_preflight import check_install_preflight

@unittest.skipUnless(os.name == "nt", "Windows installer layout")
class InstalledUpdatePreflightTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.base = Path(self.root.name)
        self.install = self.base / "LocalAppData" / "Programs" / "ParaNoya"
        self.install.mkdir(parents=True)
        (self.install / "unins000.exe").write_bytes(b"fake uninstaller")
        self.exe = self.install / "ParaNoya.exe"
        self.exe.write_bytes(b"fake installed app")
        self.payload = b"test setup payload"
        self.installer = self.base / "ParaNoya-1.2.5.4-Windows-x64-Setup.exe"
        self.installer.write_bytes(self.payload)
        self.item = dict(name=self.installer.name, size=len(self.payload),
                         sha256=hashlib.sha256(self.payload).hexdigest())
        self.patcher = patch("update_install_preflight.load_config", return_value={"updates_enabled": True})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def check(self, **changes):
        args=dict(executable=self.exe, local_app_data=self.base / "LocalAppData",
                  finance_data_dir=self.base / "AileFinans", frozen=True)
        args.update(changes)
        return check_install_preflight(self.installer, self.item, **args)

    def test_accepts_expected_install_layout_without_data_changes(self):
        data = self.base / "AileFinans"
        data.mkdir()
        db = data / "ailefinans.db"
        db.write_bytes(b"do not touch")
        self.assertEqual(self.check(), self.install)
        self.assertEqual(db.read_bytes(), b"do not touch")

    def test_rejects_data_inside_installed_app(self):
        with self.assertRaises(UpdateError):
            self.check(finance_data_dir=self.install / "user-data")

    def test_rejects_portable_copy(self):
        with self.assertRaises(UpdateError):
            self.check(executable=self.base / "ParaNoya.exe")

    def test_rejects_hash_mismatch(self):
        self.installer.write_bytes(b"changed installer")
        with self.assertRaises(UpdateError):
            self.check()

    def test_rejects_without_uninstaller(self):
        (self.install / "unins000.exe").unlink()
        with self.assertRaises(UpdateError):
            self.check()

    def test_disabled_feature_cannot_install(self):
        with patch("update_install_preflight.load_config", return_value={"updates_enabled": False}):
            with self.assertRaises(UpdateError):
                self.check()

if __name__ == "__main__":
    unittest.main()
