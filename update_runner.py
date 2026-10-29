"""Opt-in updater worker for a future audited app-exit handoff.

Not imported or called by the ParaNoya GUI. Updates stay disabled in release-config.
The signed installer must have been checked by prepare_handoff before this worker is used.
"""
import os
from pathlib import Path
import subprocess
import sys

from central_updates import UpdateError, load_config
from update_handoff import prepare_handoff
from update_process_exit import wait_for_pid_exit


def execute_after_exit(plan, item, *, confirmed=False, app_pid=None, wait_for_exit=None, run_installer=None,
                       restart_application=None, executable=None):
    """Run a previously authenticated installer ONLY after the old app has exited.

    Injection parameters permit deterministic unit tests without launching software.
    Real caller must supply an OS-specific app-exit wait callback.
    """
    if confirmed is not True:
        raise UpdateError("Kurulum için kullanıcı onayı gerekiyor")
    if load_config().get("updates_enabled") is not True:
        raise UpdateError("Otomatik güncelleme henüz etkin değil")
    if os.name != "nt":
        raise UpdateError("Yalnızca Windows yüklemeleri desteklenir")
    if not isinstance(plan, dict) or plan.get("execute") is not False:
        raise UpdateError("Güvenilir kurulum planı bulunamadı")
    if plan.get("requires_app_exit") is not True or plan.get("requires_installer_ui") is not True:
        raise UpdateError("Kurulum güvenlik koşulları eksik")
    if wait_for_exit is None:
        if type(app_pid) is not int or app_pid <= 0:
            raise UpdateError("Uygulamanın işlem numarası geçersiz")
        wait_for_exit = lambda: wait_for_pid_exit(app_pid)
    if not callable(wait_for_exit):
        raise UpdateError("Uygulama kapanış doğrulaması sağlanmadı")
    installer = Path(plan["installer"]).resolve()
    installed_app = Path(plan["restart_executable"]).resolve()
    args = plan["arguments"]
    if (not installer.is_file() or not isinstance(args, list)
            or not all(isinstance(arg, str) for arg in args)
            or any(arg.upper() in ("/SILENT", "/VERYSILENT", "/SUPPRESSMSGBOXES") for arg in args)):
        raise UpdateError("Kurulum planı uygun değil")
    if not wait_for_exit():
        raise UpdateError("ParaNoya henüz kapanmadı; kurulum iptal edildi")
    # Reject altered plans and authenticate the publisher + bytes once more at use time.
    preflight = {"executable": executable, "frozen": True} if executable is not None else {}
    verified = prepare_handoff(installer, item, explicitly_confirmed=True, **preflight)
    if plan != verified:
        raise UpdateError("Kurulum planı doğrulanmış bilgilerle eşleşmiyor")
    runner = run_installer or _run_installer
    result = runner([str(installer), *args])
    if result != 0:
        raise UpdateError(f"Kurulum başarısız: çıkış kodu {result}")
    if not installed_app.is_file():
        raise UpdateError("Kurulumdan sonra uygulama bulunamadı")
    restarter = restart_application or _restart_application
    restarter(str(installed_app))
    return True


def _run_installer(command):
    # Installer GUI is visible; no shell expansion or user-provided shell text.
    return subprocess.run(command, shell=False, check=False).returncode


def _restart_application(executable):
    subprocess.Popen([executable], shell=False, close_fds=True)
