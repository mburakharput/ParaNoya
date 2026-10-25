import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch

from central_updates import UpdateError
from update_runner import execute_after_exit

class PostExitRunnerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = pathlib.Path(temp.name)
        self.installer = root / "ParaNoya-1.2.5.4-Windows-x64-Setup.exe"
        self.installer.write_bytes(b"test fixture")
        self.app = root / "ParaNoya.exe"
        self.app.write_bytes(b"test fixture")
        self.plan = {
            "installer": str(self.installer.resolve()),
            "restart_executable": str(self.app.resolve()),
            "arguments": ["/NORESTART", "/NOCLOSEAPPLICATIONS"],
            "execute": False, "requires_app_exit": True,
            "requires_installer_ui": True
        }
        self.item = {"version": "1.2.5.4"}
        self.config = patch("update_runner.load_config", return_value={"updates_enabled": True})
        self.windows = patch("update_runner.os.name", "nt")
        self.verifier = patch("update_runner.prepare_handoff", return_value=self.plan)
        for p in (self.config, self.windows, self.verifier):
            p.start()
            self.addCleanup(p.stop)
        self.run = Mock(return_value=0)
        self.restart = Mock()

    def invoke(self, **kwargs):
        args = {"confirmed": True, "wait_for_exit": lambda: True,
                "run_installer": self.run, "restart_application": self.restart}
        args.update(kwargs)
        return execute_after_exit(self.plan, self.item, **args)

    def test_successful_exit_then_install_then_restart(self):
        self.assertTrue(self.invoke())
        self.run.assert_called_once()
        self.restart.assert_called_once_with(str(self.app.resolve()))

    def test_denied_confirmation_never_starts(self):
        with self.assertRaises(UpdateError):
            self.invoke(confirmed=False)
        self.run.assert_not_called()

    def test_windows_pid_waiter_connected(self):
        with patch("update_runner.wait_for_pid_exit", return_value=True) as wait:
            self.assertTrue(self.invoke(wait_for_exit=None, app_pid=2345))
            wait.assert_called_once_with(2345)

    def test_windows_pid_timeout_blocks_install(self):
        with patch("update_runner.wait_for_pid_exit", return_value=False):
            with self.assertRaises(UpdateError):
                self.invoke(wait_for_exit=None, app_pid=2345)
        self.run.assert_not_called()

    def test_invalid_pid_blocks_install(self):
        with self.assertRaises(UpdateError):
            self.invoke(wait_for_exit=None, app_pid=0)
        self.run.assert_not_called()

    def test_app_still_open_never_starts(self):
        with self.assertRaises(UpdateError):
            self.invoke(wait_for_exit=lambda: False)
        self.run.assert_not_called()

    def test_installer_failure_never_restarts(self):
        self.run.return_value = 5
        with self.assertRaises(UpdateError):
            self.invoke()
        self.restart.assert_not_called()

    def test_publisher_verification_failure_blocks_execution(self):
        with patch("update_runner.prepare_handoff", side_effect=UpdateError("signature invalid")):
            with self.assertRaises(UpdateError):
                self.invoke()
        self.run.assert_not_called()

    def test_tampered_plan_rejected(self):
        with patch("update_runner.prepare_handoff", return_value={**self.plan, "execute": True}):
            with self.assertRaises(UpdateError):
                self.invoke()
        self.run.assert_not_called()

    def test_waiter_exception_does_not_start_installer(self):
        def no_access():
            raise OSError("cannot inspect target process")
        with self.assertRaises(OSError):
            self.invoke(wait_for_exit=no_access)
        self.run.assert_not_called()
        self.restart.assert_not_called()

    def test_reverification_after_exit_before_install(self):
        events = []
        with patch("update_runner.prepare_handoff", side_effect=lambda *a, **kw: (events.append("verify"), self.plan)[1]):
            self.invoke(wait_for_exit=lambda: events.append("exit") or True,
                        run_installer=lambda cmd: events.append("install") or 0,
                        restart_application=lambda executable: events.append("restart"))
        self.assertEqual(events, ["exit", "verify", "install", "restart"])

    def test_disabled_updates_block_execution(self):
        with patch("update_runner.load_config", return_value={"updates_enabled": False}):
            with self.assertRaises(UpdateError):
                self.invoke()
        self.run.assert_not_called()

if __name__ == "__main__":
    unittest.main()
