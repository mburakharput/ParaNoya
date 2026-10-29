"""Prepare a conservative installer handoff plan; never run any process."""
from pathlib import Path
from central_updates import UpdateError
from update_install_preflight import check_install_preflight
from installed_app import install_options

def prepare_handoff(installer, item, *, explicitly_confirmed=False, **preflight_kwargs):
    if explicitly_confirmed is not True:
        raise UpdateError("Güncelleme için kullanıcı onayı gerekli")
    install_dir = check_install_preflight(installer, item, **preflight_kwargs)
    path = Path(installer).resolve()
    scope,elevate=install_options(install_dir)
    if not path.is_file():
        raise UpdateError("Kurulum dosyası bulunamadı")
    # This is a plan only, not execution. Closing the app and launching
    # the installer require a separately audited handoff implementation.
    return {
        "installer": str(path),
        "install_dir": str(install_dir),
        "arguments": [
            "/NORESTART", "/NOCLOSEAPPLICATIONS", "/PARANOYAUPDATE",
            "/DIR=" + str(install_dir),
            "/ALLUSERS" if scope=='machine' else "/CURRENTUSER",
        ],
        "restart_executable": str(install_dir / "ParaNoya.exe"),
        "execute": False,
        "requires_app_exit": True,
        "requires_installer_ui": True,
        "requires_elevation": elevate,
    }
