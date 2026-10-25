import unittest
from central_updates import load_config, check, candidate, UpdateError

class CentralDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_feature_disabled_and_no_network(self):
        self.assertIsNone(check(self.config))

    def test_no_unsigned_or_missing_installer(self):
        release = {"tag_name": "ParaNoya-v1.2.5.4", "assets": []}
        self.assertIsNone(candidate(self.config, release))

    def test_reject_old_version(self):
        self.assertIsNone(candidate(self.config, {"tag_name": "ParaNoya-v1.2.5.3"}))

    def test_reject_unsafe_url(self):
        release = {"tag_name": "ParaNoya-v1.2.5.4", "assets": [
            {"name": "ParaNoya-1.2.5.4-Windows-x64-Setup.exe", "state": "uploaded",
             "browser_download_url": "https://evil.example/setup.exe", "digest": "sha256:" + "0"*64}]}
        with self.assertRaises(UpdateError):
            candidate(self.config, release)

    def test_valid_metadata_is_not_an_install_authorization(self):
        release = {"tag_name": "ParaNoya-v1.2.5.4", "assets": [
            {"name": "ParaNoya-1.2.5.4-Windows-x64-Setup.exe", "state": "uploaded",
             "browser_download_url": "https://github.com/mburakharput/uygulama-guncellemeleri/releases/download/ParaNoya-v1.2.5.4/ParaNoya-1.2.5.4-Windows-x64-Setup.exe",
             "digest": "sha256:" + "a"*64}]}
        item = candidate(self.config, release)
        self.assertEqual(item["version"], "1.2.5.4")
        self.assertNotIn("install", item)

if __name__ == "__main__":
    unittest.main()
