"""Safety checks for staged central-update configuration (no network or installer execution)."""
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent


class CentralUpdateConfigTests(unittest.TestCase):
    def test_staged_settings_are_safe(self):
        data = json.loads((ROOT / "release-config.json").read_text(encoding="utf-8"))
        self.assertEqual(data["repository"], "mburakharput/uygulama-guncellemeleri")
        self.assertEqual(data["asset_prefix"], "ParaNoya")
        self.assertEqual(data["tag_prefix"], "ParaNoya-v")
        self.assertEqual(data["install_scope"], "user")
        self.assertIs(data["updates_enabled"], True)
        self.assertEqual(data['signing_public_key'],'4585f8d6c538c825e7972b103d4bb26969d5c25c59030bb4d387e72f89a3a90e')

    def test_version_matches_installer(self):
        data = json.loads((ROOT / "release-config.json").read_text(encoding="utf-8"))
        installer = (ROOT / "installer" / "ParaNoya.iss").read_text(encoding="utf-8")
        found = re.search(r'#define AppVersion "([0-9]+(?:\.[0-9]+){2,3})"', installer)
        self.assertIsNotNone(found)
        self.assertEqual(data["version"], found.group(1))


if __name__ == "__main__":
    unittest.main()
