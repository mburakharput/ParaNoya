"""Prevent installer replacement during the UAC prompt and elevated execution."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import re
from pathlib import Path
from central_updates import UpdateError


@contextmanager
def locked_installer(path,sha256,size):
    if type(size) is not int or not 0<size<=2*1024**3 or not isinstance(sha256,str) or not re.fullmatch('[0-9a-f]{64}',sha256):
        raise UpdateError('İmzalı kurulum bilgisi geçersiz')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
    handle=kernel.CreateFileW(str(path),0x80000000,1,None,3,0x80,None)
    if handle in (None,ctypes.c_void_p(-1).value):raise ctypes.WinError(ctypes.get_last_error())
    try:
        digest=hashlib.sha256();count=0
        with Path(path).open('rb') as source:
            while chunk:=source.read(1024*1024):
                digest.update(chunk);count+=len(chunk)
                if count>size:raise UpdateError('Kurulum dosyası boyutu değişmiş')
        if type(size) is not int or count!=size or digest.hexdigest()!=sha256:
            raise UpdateError('Kurulum yönetici onayından önce değişmiş; başlatılmadı')
        yield
    finally:kernel.CloseHandle(handle)
