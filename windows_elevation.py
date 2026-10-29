"""Launch only the previously verified installer, with visible Windows UAC."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
from windows_file_lock import locked_installer


def run_elevated(command, *, sha256, size):
    with locked_installer(command[0],sha256,size):
        return _launch(command)


def _launch(command):
    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_=[('cbSize',wintypes.DWORD),('fMask',ctypes.c_ulong),('hwnd',wintypes.HWND),
                  ('lpVerb',wintypes.LPCWSTR),('lpFile',wintypes.LPCWSTR),('lpParameters',wintypes.LPCWSTR),
                  ('lpDirectory',wintypes.LPCWSTR),('nShow',ctypes.c_int),('hInstApp',wintypes.HINSTANCE),
                  ('lpIDList',ctypes.c_void_p),('lpClass',wintypes.LPCWSTR),('hkeyClass',wintypes.HKEY),
                  ('dwHotKey',wintypes.DWORD),('hIcon',wintypes.HANDLE),('hProcess',wintypes.HANDLE)]
    shell=ctypes.WinDLL('shell32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    shell.ShellExecuteExW.argtypes=[ctypes.POINTER(SHELLEXECUTEINFOW)];shell.ShellExecuteExW.restype=wintypes.BOOL
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)];kernel.GetExitCodeProcess.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
    info=SHELLEXECUTEINFOW();info.cbSize=ctypes.sizeof(info);info.fMask=0x40|0x100
    info.lpVerb='runas';info.lpFile=command[0];info.lpParameters=subprocess.list2cmdline(command[1:])
    info.lpDirectory=str(Path(command[0]).parent);info.nShow=1
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        code=ctypes.get_last_error()
        if code==1223:return code
        raise ctypes.WinError(code)
    if not info.hProcess:raise RuntimeError('Kurulum işlem tanıtıcısı alınamadı')
    try:
        if kernel.WaitForSingleObject(info.hProcess,0xffffffff)!=0:raise RuntimeError('Kurulum beklenemedi')
        result=wintypes.DWORD()
        if not kernel.GetExitCodeProcess(info.hProcess,ctypes.byref(result)):raise ctypes.WinError(ctypes.get_last_error())
        return result.value
    finally:kernel.CloseHandle(info.hProcess)
