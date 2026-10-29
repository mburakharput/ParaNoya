import os
import unittest
from unittest.mock import Mock, patch

from update_process_exit import wait_for_pid_exit

class WaitForExitTests(unittest.TestCase):
    def test_exited_process(self):
        opener = Mock(return_value=42)
        waiter = Mock(return_value=0)
        closer = Mock()
        with patch("update_process_exit.os.name", "nt"):
            self.assertTrue(wait_for_pid_exit(12345, timeout_seconds=2,
                opener=opener, waiter=waiter, closer=closer))
        waiter.assert_called_once_with(42, 2000)
        closer.assert_called_once_with(42)

    def test_running_process_times_out(self):
        closer = Mock()
        with patch("update_process_exit.os.name", "nt"):
            self.assertFalse(wait_for_pid_exit(12345, opener=lambda pid: 42,
                waiter=lambda handle, timeout: 0x102, closer=closer))
        closer.assert_called_once_with(42)

    def test_missing_process_handle_fails_closed(self):
        waiter = Mock()
        with patch("update_process_exit.os.name", "nt"):
            self.assertFalse(wait_for_pid_exit(12345, opener=lambda pid: None,
                waiter=waiter, closer=Mock()))
        waiter.assert_not_called()

    def test_invalid_pid_rejected(self):
        with patch("update_process_exit.os.name", "nt"):
            for pid in [0, -1, "5", os.getpid()]:
                with self.subTest(pid=pid), self.assertRaises(ValueError):
                    wait_for_pid_exit(pid, opener=Mock(), waiter=Mock(), closer=Mock())

    def test_wait_errors_close_handle(self):
        closer = Mock()
        with patch("update_process_exit.os.name", "nt"):
            with self.assertRaises(RuntimeError):
                wait_for_pid_exit(12345, opener=lambda pid: 42,
                    waiter=Mock(side_effect=RuntimeError("WinAPI failure")), closer=closer)
        closer.assert_called_once_with(42)

if __name__ == "__main__":
    unittest.main()
