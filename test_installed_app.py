import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from central_updates import UpdateError
from installed_app import registration,trusted_install_folder,install_options
from update_handoff import prepare_handoff
from update_runner import _run_installer


class InstallationDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.folder=self.root/'Program Files'/'ParaNoya';self.folder.mkdir(parents=True)
        self.exe=self.folder/'ParaNoya.exe';self.exe.write_bytes(b'synthetic')
        (self.folder/'unins000.exe').write_bytes(b'synthetic')
        self.record={'DisplayName':'ParaNoya','InstallLocation':str(self.folder),'UninstallString':'"'+str(self.folder/'unins000.exe')+'"','scope':'machine'}
        self.reg=patch('installed_app._registrations',return_value=[self.record]);self.reg.start();self.addCleanup(self.reg.stop)

    def test_registered_program_files_install_accepted(self):
        self.assertEqual(trusted_install_folder(self.exe,self.root/'Local'),self.folder.resolve())
        self.assertEqual(install_options(self.folder),('machine',True))

    def test_previous_inno_display_name_with_version_is_accepted(self):
        for display in ('ParaNoya 1.2.5.6','ParaNoya version 1.2.5.7','ParaNoya sürüm 1.2.5.6'):
            with self.subTest(display=display),patch('installed_app._registrations',return_value=[{**self.record,'DisplayName':display}]):
                self.assertEqual(trusted_install_folder(self.exe,self.root/'Local'),self.folder.resolve())

    def test_custom_per_user_folder_keeps_scope(self):
        self.record['scope']='user'
        with patch.dict(os.environ,{'ProgramFiles':str(self.root/'Program Files')}):
            self.assertEqual(install_options(self.folder),('user',True))
        with patch.dict(os.environ,{'ProgramFiles':str(self.root/'Different'),'ProgramW6432':str(self.root/'Different'),'ProgramFiles(x86)':str(self.root/'Different')}):
            self.assertEqual(install_options(self.folder),('user',False))

    def test_portable_copy_with_uninstaller_but_no_registration_refused(self):
        with patch('installed_app._registrations',return_value=[]),self.assertRaises(UpdateError):
            trusted_install_folder(self.exe,self.root/'Local')

    def test_wrong_product_or_uninstaller_not_trusted(self):
        for field,value in [('DisplayName','Different app'),('UninstallString','"other.exe"'),('InstallLocation',str(self.root/'Different'))]:
            with self.subTest(field=field),patch('installed_app._registrations',return_value=[{**self.record,field:value}]),self.assertRaises(UpdateError):
                trusted_install_folder(self.exe,self.root/'Local')

    def test_missing_uninstaller_rejected(self):
        (self.folder/'unins000.exe').unlink()
        with self.assertRaises(UpdateError):trusted_install_folder(self.exe,self.root/'Local')

    def test_conflicting_scopes_rejected(self):
        with patch('installed_app._registrations',return_value=[self.record,{**self.record,'scope':'user'}]),self.assertRaises(UpdateError):
            registration(self.folder)

    def test_duplicate_registry_views_do_not_create_ambiguity(self):
        with patch('installed_app._registrations',return_value=[self.record,self.record]):
            self.assertEqual(registration(self.folder)['scope'],'machine')

    def test_handoff_preserves_path_and_machine_scope(self):
        setup=self.root/'synthetic.exe';setup.write_bytes(b'never executed')
        with patch('update_handoff.check_install_preflight',return_value=self.folder):
            plan=prepare_handoff(setup,{},explicitly_confirmed=True)
        self.assertIn('/DIR='+str(self.folder),plan['arguments'])
        self.assertIn('/ALLUSERS',plan['arguments']);self.assertTrue(plan['requires_elevation'])
        self.assertEqual(plan['restart_executable'],str(self.exe))

    def test_elevation_applies_only_to_installer(self):
        with patch('windows_elevation.run_elevated',return_value=0) as elevated,patch('update_runner.subprocess.run') as regular:
            self.assertEqual(_run_installer(['synthetic.exe','/ALLUSERS'],elevate=True,item={'sha256':'fixture','size':1}),0)
        elevated.assert_called_once_with(['synthetic.exe','/ALLUSERS'],sha256='fixture',size=1);regular.assert_not_called()

    def test_regular_user_install_does_not_elevate(self):
        with patch('windows_elevation.run_elevated') as elevated,patch('update_runner.subprocess.run',return_value=Mock(returncode=0)):
            self.assertEqual(_run_installer(['synthetic.exe'],elevate=False),0)
        elevated.assert_not_called()


@unittest.skipUnless(os.name=='nt','Windows UAC API')
class ElevationApiTests(unittest.TestCase):
    def test_windows_handle_waited_and_closed_with_quoted_arguments(self):
        import ctypes
        from windows_elevation import run_elevated
        shell=Mock();kernel=Mock();seen=[]
        def launch(pointer):
            info=pointer._obj;seen.append((info.lpVerb,info.lpFile,info.lpParameters));info.hProcess=123
            return True
        shell.ShellExecuteExW.side_effect=launch;kernel.WaitForSingleObject.return_value=0
        def exit_code(handle,pointer):pointer._obj.value=0;return True
        kernel.GetExitCodeProcess.side_effect=exit_code
        from contextlib import nullcontext
        with patch('windows_elevation.locked_installer',return_value=nullcontext()),patch('windows_elevation.ctypes.WinDLL',side_effect=[shell,kernel]):
            self.assertEqual(run_elevated(['C:\\Synthetic Path\\setup.exe','/DIR=C:\\Program Files\\ParaNoya'],sha256='fixture',size=1),0)
        self.assertEqual(seen[0][0],'runas');self.assertIn('"/DIR=C:\\Program Files\\ParaNoya"',seen[0][2])
        kernel.CloseHandle.assert_called_once_with(123)

    def test_declined_uac_returns_cancel_without_waiting(self):
        from windows_elevation import run_elevated
        shell=Mock();kernel=Mock();shell.ShellExecuteExW.return_value=False
        from contextlib import nullcontext
        with patch('windows_elevation.locked_installer',return_value=nullcontext()),patch('windows_elevation.ctypes.WinDLL',side_effect=[shell,kernel]),patch('windows_elevation.ctypes.get_last_error',return_value=1223):
            self.assertEqual(run_elevated(['synthetic.exe'],sha256='fixture',size=1),1223)
        kernel.WaitForSingleObject.assert_not_called();kernel.CloseHandle.assert_not_called()

    def test_installer_cannot_be_written_or_deleted_while_locked(self):
        import hashlib
        from windows_file_lock import locked_installer
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'synthetic.exe';path.write_bytes(b'never executed')
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            with locked_installer(path,digest,len(b'never executed')):
                with self.assertRaises(PermissionError):path.write_bytes(b'changed')
                with self.assertRaises(PermissionError):path.unlink()
            path.unlink()

    def test_changed_installer_never_reaches_uac(self):
        from windows_elevation import run_elevated
        with patch('windows_elevation.locked_installer',side_effect=UpdateError('changed')),patch('windows_elevation._launch') as launch:
            with self.assertRaises(UpdateError):run_elevated(['synthetic.exe'],sha256='fixture',size=1)
        launch.assert_not_called()
