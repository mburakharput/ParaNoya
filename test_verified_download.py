import hashlib
import io
import unittest
from unittest.mock import patch

from central_updates import UpdateError
from verified_download import download_verified, _validate_url

class VerifiedDownloadTests(unittest.TestCase):
    def setUp(self):
        self.payload = b"synthetic installer bytes; not executable"
        self.version = "1.2.5.4"
        self.name = "ParaNoya-1.2.5.4-Windows-x64-Setup.exe"
        self.base = "https://github.com/mburakharput/uygulama-guncellemeleri/releases/download/ParaNoya-v1.2.5.4/"
        self.item = {
            "version": self.version, "name": self.name,
            "url": self.base + self.name,
            "size": len(self.payload),
            "sha256": hashlib.sha256(self.payload).hexdigest(),
        }
        self.config = {
            "repository": "mburakharput/uygulama-guncellemeleri",
            "updates_enabled": True,
        }

    def test_disabled_never_downloads(self):
        with patch("verified_download.authenticate_candidate") as auth:
            with self.assertRaises(UpdateError):
                download_verified({**self.config, "updates_enabled": False}, self.item)
            auth.assert_not_called()

    def test_reject_bad_url_before_network(self):
        with patch("verified_download.authenticate_candidate") as auth:
            with self.assertRaises(UpdateError):
                download_verified(self.config, {**self.item, "url": "https://evil.example/setup.exe"})
            auth.assert_not_called()

    def test_reject_untrusted_redirect(self):
        with self.assertRaises(UpdateError):
            _validate_url("http://github.com/a")
        with self.assertRaises(UpdateError):
            _validate_url("https://evil.example/a")

    def test_authentication_must_succeed_before_download(self):
        with patch("verified_download.authenticate_candidate", side_effect=UpdateError("unsigned")):
            with patch("verified_download._open") as opener:
                with self.assertRaises(UpdateError):
                    download_verified(self.config, self.item)
                opener.assert_not_called()

    def test_verified_download_never_executes(self):
        with patch("verified_download.authenticate_candidate", return_value=self.item), patch(
            "verified_download._open", return_value=io.BytesIO(self.payload)
        ):
            path = download_verified(self.config, self.item)
            try:
                self.assertEqual(path.read_bytes(), self.payload)
                self.assertEqual(path.name, self.name)
            finally:
                path.unlink()
                path.parent.rmdir()

    def test_corrupt_data_rejected_and_deleted(self):
        with patch("verified_download.authenticate_candidate", return_value=self.item), patch(
            "verified_download._open", return_value=io.BytesIO(b"x"*len(self.payload))
        ):
            with self.assertRaises(UpdateError):
                download_verified(self.config, self.item)

if __name__ == "__main__":
    unittest.main()
