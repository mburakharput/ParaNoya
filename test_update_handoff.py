import pathlib
import tempfile
import unittest
from unittest.mock import patch

from central_updates import UpdateError
from update_handoff import prepare_handoff

class HandoffPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.install_dir = pathlib.Path(self.tmp.name) / "Programs" / "ParaNoya"
        self.install_dir.mkdir(parents=True)
        self.setup = pathlib.Path(self.tmp.name) / "ParaNoya-1.2.5.4-Windows-x64-Setup.exe"
        self.setup.write_bytes(b"synthetic")

    def test_confirmation_required_before_preflight(self):
        with patch("update_handoff.check_install_preflight") as preflight:
            with self.assertRaises(UpdateError):
                prepare_handoff(self.setup, {"version": "1.2.5.4"})
            preflight.assert_not_called()

    def test_prepared_plan_does_not_execute(self):
        with patch("update_handoff.check_install_preflight", return_value=self.install_dir):
            result = prepare_handoff(self.setup, {"version": "1.2.5.4"}, explicitly_confirmed=True)
        self.assertIs(result["execute"], False)
        self.assertEqual(result["restart_executable"], str(self.install_dir / "ParaNoya.exe"))
        self.assertIn("/NOCLOSEAPPLICATIONS", result["arguments"])
        self.assertTrue(result["requires_app_exit"])
        self.assertTrue(result["requires_installer_ui"])
        self.assertNotIn("/SILENT", result["arguments"])
        self.assertNotIn("/SUPPRESSMSGBOXES", result["arguments"])
        self.assertIn("/DIR=" + str(self.install_dir), result["arguments"])

    def test_preflight_failure_prevents_plan(self):
        with patch("update_handoff.check_install_preflight", side_effect=UpdateError("unsafe")):
            with self.assertRaises(UpdateError):
                prepare_handoff(self.setup, {"version": "1.2.5.4"}, explicitly_confirmed=True)

if __name__ == "__main__":
    unittest.main()
