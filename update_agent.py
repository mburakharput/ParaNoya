"""Independent frozen update helper. Never reads or writes finance databases.

Copied outside the install directory before use; signed metadata and installer
bytes are checked again after the old application exits. Only explicit GUI
consent can create a handoff request.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from central_updates import UpdateError
from signed_release import _no_duplicate_keys
from update_handoff import prepare_handoff
from update_runner import execute_after_exit
from update_process_exit import wait_for_pid_exit


def launcher_pid():
    # A one-file PyInstaller executable has a waiting bootloader parent. Popen
    # returns that parent's PID, while this Python code runs in its child.
    return os.getppid() if getattr(sys, 'frozen', False) else os.getpid()


def validate_request_path(request):
    original=Path(request).absolute()
    if any(p.is_symlink() for p in (original,*original.parents)):
        raise UpdateError('Güncelleme isteği bağlantı içeriyor')
    path=original.resolve()
    if (path.name!='update-request.json' or not path.parent.name.startswith('paranoya-verified-')
            or path.parent.parent!=Path(tempfile.gettempdir()).resolve()):
        raise UpdateError('Güncelleme isteği güvenli klasörde değil')
    return path


def write_request(installer, item, plan, *, confirmed=False, app_pid=None, helper_source=None):
    if confirmed is not True:raise UpdateError('Kurulum onayı gerekli')
    if type(app_pid) is not int or app_pid<=0:raise UpdateError('İşlem numarası geçersiz')
    path=validate_request_path(Path(installer).parent/'update-request.json')
    helper=Path(helper_source or Path(sys.executable).with_name('ParaNoyaUpdater.exe'))
    if not helper.is_file() or helper.is_symlink():raise UpdateError('Güncelleme yardımcısı bulunamadı; kurulumu yenileyin')
    target=path.parent/'ParaNoyaUpdater.exe'
    if target.exists():raise UpdateError('Güncelleme yardımcısı hedefi zaten var')
    with helper.open('rb') as source,target.open('xb') as output:
        shutil.copyfileobj(source,output)
    payload={'schema':1,'confirmed':True,'app_pid':app_pid,'item':item,'plan':plan}
    try:
        with path.open('x',encoding='utf-8') as output:json.dump(payload,output,ensure_ascii=True)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return path,target


def load_request(request):
    path=validate_request_path(request)
    with path.open('rb') as source:raw=source.read(32*1024+1)
    if len(raw)>32*1024:raise UpdateError('Güncelleme isteği çok büyük')
    payload=json.loads(raw,object_pairs_hook=_no_duplicate_keys)
    if (set(payload)!={'schema','confirmed','app_pid','item','plan'}
            or type(payload['schema']) is not int or payload['schema']!=1
            or payload['confirmed'] is not True or type(payload['app_pid']) is not int
            or payload['app_pid']<=0 or not isinstance(payload['item'],dict)
            or not isinstance(payload['plan'],dict)):
        raise UpdateError('Güncelleme isteği geçersiz')
    if Path(payload['plan'].get('installer','')).resolve().parent!=path.parent:
        raise UpdateError('Kurulum ve istek aynı klasörde olmalı')
    return path,payload


def run_request(request):
    path,payload=load_request(request)
    local=os.environ.get('LOCALAPPDATA')
    if not local:raise UpdateError('Kullanıcı kurulum klasörü bulunamadı')
    # The GUI's path is untrusted until prepare_handoff verifies the pinned
    # Windows installation record and the actual running process identity.
    executable=Path(payload['plan'].get('restart_executable',''))
    expected=prepare_handoff(payload['plan']['installer'],payload['item'],
        explicitly_confirmed=True,executable=executable,frozen=True)
    if payload['plan']!=expected:raise UpdateError('Güncelleme planı değiştirilmiş')
    exited=False
    def ready():
        if (path.parent/'update-cancelled').exists():raise UpdateError('Güncelleme iptal edildi')
        partial=path.parent/'update-ready.partial'
        with partial.open('x',encoding='utf-8') as output:
            json.dump({'helper_pid':launcher_pid(),'app_pid':payload['app_pid']},output)
        os.replace(partial,path.parent/'update-ready.json')
    def wait():
        nonlocal exited
        exited=wait_for_pid_exit(payload['app_pid'],on_ready=ready,expected_executable=executable)
        return exited
    try:
        return execute_after_exit(expected,payload['item'],confirmed=True,
            app_pid=payload['app_pid'],wait_for_exit=wait,executable=executable)
    except Exception:
        # A cancelled/failed setup must not leave the user without the application.
        # If the old process never exited, never open a second instance.
        if exited and executable.is_file():
            subprocess.Popen([str(executable)],shell=False,close_fds=True)
        raise


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--request')
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--self-test-report')
    args=parser.parse_args(argv)
    if args.self_test:
        from central_updates import load_config
        load_config()
        from nacl.signing import VerifyKey
        VerifyKey(bytes.fromhex(load_config()['signing_public_key']))
        if args.self_test_report:
            with Path(args.self_test_report).open('x',encoding='utf-8') as output:
                json.dump({'launcher_pid':launcher_pid(),'ok':True},output)
        return 0
    if not args.request:parser.error('--request gerekli')
    try:
        run_request(args.request)
        return 0
    except Exception as exc:
        try:
            path=validate_request_path(args.request)
            (path.parent/'update-error.txt').write_text(str(exc),encoding='utf-8')
            # Before readiness the still-running GUI reports the error itself.
            if (path.parent/'update-ready.json').exists():
                import ctypes
                ctypes.windll.user32.MessageBoxW(None,str(exc),'ParaNoya güncellemesi tamamlanamadı',0x10)
        except Exception:pass
        return 1


if __name__=='__main__':
    sys.exit(main())
