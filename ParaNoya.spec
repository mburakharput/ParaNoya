from pathlib import Path
root = Path(SPECPATH)
a = Analysis([str(root / 'ailefinans.py')], pathex=[str(root)],
    binaries=[], datas=[(str(root / 'assets' / 'paranoya_mascot.png'), 'assets'),
                         (str(root / 'assets' / 'chevron-down.svg'), 'assets'),
                         (str(root / 'assets' / 'banks' / 'ziraatdinamik.png'), 'assets/banks'),
                         (str(root / 'release-config.json'), '.')],
    hiddenimports=['PySide6.QtSvg', 'PySide6.QtSvgWidgets', 'packaging_smoke', 'pymupdf', 'openpyxl'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'tkinter'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ParaNoya',
    debug=False, strip=False, upx=False, console=False, icon=str(root / 'assets' / 'paranoya.ico'))

# The helper is one-file and copied to the verified temporary directory before
# launch, so the installer can replace every installed file without locking it.
u = Analysis([str(root / 'update_agent.py')], pathex=[str(root)], binaries=[],
    datas=[(str(root / 'release-config.json'), '.')], hiddenimports=['nacl.signing'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PySide6','PyQt5','PyQt6','PySide2','tkinter'], noarchive=False)
upyz = PYZ(u.pure)
updater = EXE(upyz, u.scripts, u.binaries, u.datas, [], name='ParaNoyaUpdater',
    debug=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, updater, a.binaries, a.datas, strip=False, upx=False, name='ParaNoya')
