import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from central_updates import UpdateError
from update_agent import write_request,load_request,run_request,main
from update_process_exit import wait_for_pid_exit


class UpdateAgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='paranoya-verified-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.source=self.root/'source-helper.bin';self.source.write_bytes(b'synthetic helper; never run')
        self.installer=self.root/'ParaNoya-9.0.0-Windows-x64-Setup.exe';self.installer.write_bytes(b'synthetic setup')
        self.plan={'installer':str(self.installer),'execute':False}
    def request(self):
        return write_request(self.installer,{'version':'9.0.0'},self.plan,confirmed=True,app_pid=12345,helper_source=self.source)
    def test_request_needs_explicit_consent(self):
        with self.assertRaises(UpdateError):write_request(self.installer,{},self.plan,app_pid=12345,helper_source=self.source)
        self.assertFalse((self.root/'ParaNoyaUpdater.exe').exists())
    def test_request_roundtrip_and_no_overwrite(self):
        path,helper=self.request();_,payload=load_request(path)
        self.assertEqual(payload['plan'],self.plan);self.assertEqual(helper.read_bytes(),self.source.read_bytes())
        with self.assertRaises(UpdateError):self.request()
    def test_request_must_be_in_verified_folder(self):
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaises(UpdateError):load_request(Path(other)/'update-request.json')
    def test_tampered_installer_location_is_rejected(self):
        path,_=self.request();payload=json.loads(path.read_text());payload['plan']['installer']=str(self.root.parent/'other.exe')
        path.write_text(json.dumps(payload))
        with self.assertRaises(UpdateError):load_request(path)
    def test_duplicate_request_fields_rejected(self):
        path,_=self.request();path.write_text('{"schema":1,"schema":1}')
        with self.assertRaises(ValueError):load_request(path)
    def test_preflight_failure_cannot_wait_or_install(self):
        path,_=self.request()
        with patch.dict(os.environ,{'LOCALAPPDATA':str(self.root)}),patch('update_agent.prepare_handoff',side_effect=UpdateError('signature')),patch('update_agent.execute_after_exit') as runner:
            with self.assertRaises(UpdateError):run_request(path)
            runner.assert_not_called()
    def test_changed_plan_cannot_execute(self):
        path,_=self.request()
        with patch.dict(os.environ,{'LOCALAPPDATA':str(self.root)}),patch('update_agent.prepare_handoff',return_value={**self.plan,'execute':True}),patch('update_agent.execute_after_exit') as runner:
            with self.assertRaises(UpdateError):run_request(path)
            runner.assert_not_called()
    def test_missing_process_path_never_sends_ready(self):
        ready=Mock();closer=Mock();waiter=Mock()
        self.assertFalse(wait_for_pid_exit(12345,opener=lambda _:42,waiter=waiter,closer=closer,
            expected_executable=self.root/'ParaNoya.exe',process_path=lambda _:None,on_ready=ready))
        ready.assert_not_called();waiter.assert_not_called();closer.assert_called_once_with(42)
    def test_ready_only_after_process_identity_validation(self):
        events=[];app=self.root/'ParaNoya.exe'
        self.assertTrue(wait_for_pid_exit(12345,opener=lambda _:42,waiter=lambda *args:events.append('wait') or 0,
            closer=lambda _:events.append('close'),expected_executable=app,process_path=lambda _:str(app),on_ready=lambda:events.append('ready')))
        self.assertEqual(events,['ready','wait','close'])
    def test_helper_selftest_has_no_installer_side_effect(self):
        with patch('update_agent.run_request') as run:
            self.assertEqual(main(['--self-test']),0);run.assert_not_called()
