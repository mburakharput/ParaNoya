"""Discover only this app's pinned Inno Setup registration; never scan user data."""
import os
from pathlib import Path
from central_updates import UpdateError

UNINSTALL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{22874636-8296-42A7-8E61-56C5242C838F}_is1'


def _registrations():
    import winreg
    records=[]
    for hive,scope in ((winreg.HKEY_CURRENT_USER,'user'),(winreg.HKEY_LOCAL_MACHINE,'machine')):
        for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive,UNINSTALL_KEY,0,winreg.KEY_READ|view) as key:
                    values={name:winreg.QueryValueEx(key,name)[0] for name in ('DisplayName','InstallLocation','UninstallString')}
                    records.append(dict(values,scope=scope))
            except OSError:continue
    return records


def registration(folder):
    folder=Path(folder).resolve();matches={}
    for record in _registrations():
        if record.get('DisplayName')!='ParaNoya':continue
        location=record.get('InstallLocation');uninstall=record.get('UninstallString')
        if not isinstance(location,str) or not isinstance(uninstall,str) or not location:continue
        location=Path(os.path.expandvars(location)).resolve()
        # UninstallString, unlike QuietUninstallString, is the quoted executable.
        if location!=folder or uninstall.strip().strip('"').casefold()!=str(folder/'unins000.exe').casefold():continue
        matches[record['scope']]=record
    if len(matches)>1:raise UpdateError('Kurulum kapsamı belirsiz; kurulumu elle onarın')
    return next(iter(matches.values()),None)


def trusted_install_folder(executable,local_app_data):
    original=Path(executable).absolute()
    if any(p.is_symlink() for p in (original,*original.parents)):
        raise UpdateError('Uygulama yolu bağlantı içeriyor')
    executable=original.resolve();folder=executable.parent
    default=(Path(local_app_data)/'Programs'/'ParaNoya').resolve()
    if executable.name.casefold()!='paranoya.exe' or not executable.is_file():
        raise UpdateError('Kurulu uygulama dosyası bulunamadı')
    if folder!=default and registration(folder) is None:
        raise UpdateError('Mevcut kurulum Windows kurulum kaydından doğrulanamadı')
    if not (folder/'unins000.exe').is_file():
        raise UpdateError('Mevcut kurulumun kaldırma kaydı yok')
    return folder


def install_options(folder):
    folder=Path(folder).resolve();record=registration(folder)
    scope=record['scope'] if record else 'user'
    protected=any(Path(base).resolve()==folder or Path(base).resolve() in folder.parents
                  for name in ('ProgramFiles','ProgramW6432','ProgramFiles(x86)')
                  if (base:=os.environ.get(name)))
    return scope,scope=='machine' or protected
