"""Check that both Windows executables contain an actual icon resource."""
import ctypes
from pathlib import Path
import sys

def verify(paths):
    extract = ctypes.windll.shell32.ExtractIconExW
    extract.argtypes = [ctypes.c_wchar_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
    extract.restype = ctypes.c_uint
    for value in paths:
        path = Path(value).resolve()
        assert path.is_file(), path
        count = extract(str(path), -1, None, None, 0)
        assert count > 0, f'No icon resource in {path.name}'
        print(f'{path.name}: {count} icon resource(s) verified')

if __name__ == '__main__':
    verify(sys.argv[1:])
