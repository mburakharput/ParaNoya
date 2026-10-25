from pathlib import Path
root = Path(SPECPATH)
a = Analysis([str(root / 'ailefinans.py')], pathex=[str(root)],
    binaries=[], datas=[(str(root / 'assets' / 'paranoya_mascot.png'), 'assets'),
                         (str(root / 'assets' / 'chevron-down.svg'), 'assets')],
    hiddenimports=['PySide6.QtSvg', 'PySide6.QtSvgWidgets', 'packaging_smoke', 'pymupdf', 'openpyxl'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'tkinter'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ParaNoya',
    debug=False, strip=False, upx=False, console=False, icon=str(root / 'assets' / 'paranoya.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ParaNoya')
