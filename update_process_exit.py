"""Windows-only check that an existing application process has exited.

This module neither terminates processes nor launches installers.
"""
import os
import time


def wait_for_pid_exit(pid, *, timeout_seconds=120, opener=None, waiter=None, closer=None):
    if os.name != "nt":
        raise RuntimeError("Windows required")
    if type(pid) is not int or pid <= 0 or pid == os.getpid():
        raise ValueError("Invalid target PID")
    if not 1 <= timeout_seconds <= 600:
        raise ValueError("Invalid timeout")
    if opener is None or waiter is None or closer is None:
        import ctypes
        kernel = ctypes.windll.kernel32
        from ctypes import wintypes
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        opener = lambda target: kernel.OpenProcess(0x00100000, False, target)
        waiter = lambda handle, timeout: kernel.WaitForSingleObject(handle, timeout)
        closer = kernel.CloseHandle
    handle = opener(pid)
    if not handle:
        # No access or PID disappeared. Fail closed, rather than guessing.
        return False
    try:
        # WAIT_OBJECT_0 is 0. WAIT_TIMEOUT is 0x102.
        result = waiter(handle, int(timeout_seconds * 1000))
        return result == 0
    finally:
        closer(handle)
