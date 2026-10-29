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
        self.stage = tempfile.TemporaryDirectory(prefix="paranoya-verified-")
        self.addCleanup(self.stage.cleanup)
        self.installer = Path(self.stage.name) / "ParaNoya-1.2.5.4-Windows-x64-Setup.exe"
        self.installer.write_bytes(self.payload)
        self.item = dict(name=self.installer.name, version="1.2.5.4", size=len(self.payload),
                         sha256=hashlib.sha256(self.payload).hexdigest())
        self.patcher = patch("update_install_preflight.load_config", return_value={"updates_enabled": True, "version": "1.2.5.3"})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.auth_patcher = patch("update_install_preflight.authenticate_candidate", return_value=True)
        self.auth_patcher.start()
        self.addCleanup(self.auth_patcher.stop)

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
        self.assertEqual(self.check().resolve(), self.install.resolve())
        self.assertEqual(db.read_bytes(), b"do not touch")

    def test_failed_signature_preserves_finance_database(self):
        data = self.base / "AileFinans"
        data.mkdir()
        db = data / "ailefinans.db"
        original = b"important user finances"
        db.write_bytes(original)
        with patch("update_install_preflight.authenticate_candidate",
                   side_effect=UpdateError("publisher signature invalid")):
            with self.assertRaises(UpdateError):
                self.check()
        self.assertEqual(db.read_bytes(), original)
        self.assertTrue(self.exe.is_file())

    def test_failed_hash_preserves_finance_database(self):
        data = self.base / "AileFinans"
        data.mkdir()
        db = data / "ailefinans.db"
        original = b"important user finances"
        db.write_bytes(original)
        self.installer.write_bytes(b"tampered setup")
        with self.assertRaises(UpdateError):
            self.check()
        self.assertEqual(db.read_bytes(), original)
        self.assertTrue(self.exe.is_file())

    def test_rejects_data_inside_installed_app(self):
        with self.assertRaises(UpdateError):
            self.check(finance_data_dir=self.install / "user-data")

    def test_rejects_portable_copy(self):
        with self.assertRaises(UpdateError):
            self.check(executable=self.base / "ParaNoya.exe")

    def test_rejects_nonhex_digest(self):
        with self.assertRaises(UpdateError):
            check_install_preflight(self.installer, {**self.item, "sha256": "z" * 64},
                executable=self.exe, local_app_data=self.base / "LocalAppData",
                finance_data_dir=self.base / "AileFinans", frozen=True)

    def test_rejects_hash_mismatch(self):
        self.installer.write_bytes(b"changed installer")
        with self.assertRaises(UpdateError):
            self.check()

    def test_rejects_without_uninstaller(self):
        (self.install / "unins000.exe").unlink()
        with self.assertRaises(UpdateError):
            self.check()

    def test_rejects_invalid_publisher_signature(self):
        with patch("update_install_preflight.authenticate_candidate",
                   side_effect=UpdateError("İmza geçersiz")):
            with self.assertRaises(UpdateError):
                self.check()

    def test_rejects_installer_outside_verified_directory(self):
        other = self.base / self.installer.name
        other.write_bytes(self.payload)
        with self.assertRaises(UpdateError):
            check_install_preflight(other, self.item,
                executable=self.exe, local_app_data=self.base / "LocalAppData",
                finance_data_dir=self.base / "AileFinans", frozen=True)

    def test_rejects_downgrade(self):
        with self.assertRaises(UpdateError):
            check_install_preflight(self.installer, {**self.item, "version": "1.2.5.2"},
                executable=self.exe, local_app_data=self.base / "LocalAppData",
                finance_data_dir=self.base / "AileFinans", frozen=True)

    def test_rejects_same_version(self):
        with self.assertRaises(UpdateError):
            check_install_preflight(self.installer, {**self.item, "version": "1.2.5.3"},
                executable=self.exe, local_app_data=self.base / "LocalAppData",
                finance_data_dir=self.base / "AileFinans", frozen=True)

    def test_disabled_feature_cannot_install(self):
        with patch("update_install_preflight.load_config", return_value={"updates_enabled": False, "version": "1.2.5.3"}):
            with self.assertRaises(UpdateError):
                self.check()

if __name__ == "__main__":
    unittest.main()
