"""Signed fixture integration: no real publisher key, network or installation."""
from contextlib import ExitStack
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from nacl.signing import SigningKey
from central_updates import check,UpdateError
from verified_download import download_verified
from update_handoff import prepare_handoff
from update_runner import execute_after_exit


class SignedFlowTests(unittest.TestCase):
    def exercise(self,tamper=False):
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            root=Path(temp);install=root/'Programs'/'ParaNoya';install.mkdir(parents=True)
            app=install/'ParaNoya.exe';app.write_bytes(b'installed fixture')
            (install/'unins000.exe').write_bytes(b'uninstaller fixture')
            data=root/'AileFinans';data.mkdir();db=data/'ailefinans.db';db.write_bytes(b'untouched finance sentinel')
            signer=SigningKey.generate();payload=b'signed fixture, never executed'
            name='ParaNoya-2.0.0-Windows-x64-Setup.exe'
            base='https://github.com/mburakharput/uygulama-guncellemeleri/releases/download/ParaNoya-v2.0.0/'
            record=dict(schema=1,app='ParaNoya',version='2.0.0',tag='ParaNoya-v2.0.0',name=name,size=len(payload),sha256=hashlib.sha256(payload).hexdigest())
            manifest=json.dumps(record).encode('ascii');signature=signer.sign(manifest).signature.hex().encode('ascii')
            config=dict(repository='mburakharput/uygulama-guncellemeleri',version='1.0.0',updates_enabled=True,tag_prefix='ParaNoya-v',signing_public_key=signer.verify_key.encode().hex())
            releases=[dict(tag_name='ParaNoya-v2.0.0',assets=[dict(name=name,state='uploaded',browser_download_url=base+name,digest='sha256:'+record['sha256'],size=len(payload)),dict(name='ParaNoya-2.0.0-manifest.json',state='uploaded',browser_download_url=base+'ParaNoya-2.0.0-manifest.json'),dict(name='ParaNoya-2.0.0-manifest.json.sig',state='uploaded',browser_download_url=base+'ParaNoya-2.0.0-manifest.json.sig')])]
            stack.enter_context(patch('central_updates.urlopen',return_value=io.BytesIO(json.dumps(releases).encode())))
            stack.enter_context(patch('central_updates._read_small',side_effect=lambda url:signature if url.endswith('.sig') else manifest))
            stack.enter_context(patch('verified_download._open',return_value=io.BytesIO(payload)))
            stack.enter_context(patch('update_install_preflight.load_config',return_value=config))
            stack.enter_context(patch('update_runner.load_config',return_value=config))
            stack.enter_context(patch('finance_core.DB_DIR',data))
            stack.enter_context(patch.dict(os.environ,{'LOCALAPPDATA':str(root)}))
            item=check(config);path=download_verified(config,item)
            try:
                plan=prepare_handoff(path,item,explicitly_confirmed=True,executable=app,frozen=True)
                if tamper:path.write_bytes(b'corrupt')
                events=[]
                def run(command):
                    events.append('install');self.assertIn('/PARANOYAUPDATE',command);return 0
                call=lambda:execute_after_exit(plan,item,confirmed=True,executable=app,
                    wait_for_exit=lambda:events.append('exit') or True,run_installer=run,
                    restart_application=lambda _:events.append('restart'))
                if tamper:
                    with self.assertRaises(UpdateError):call()
                    self.assertEqual(events,['exit'])
                else:
                    self.assertTrue(call());self.assertEqual(events,['exit','install','restart'])
                self.assertEqual(db.read_bytes(),b'untouched finance sentinel')
            finally:path.unlink();path.parent.rmdir()
    def test_signed_check_download_handoff_install_restart(self):self.exercise()
    def test_tampering_after_handoff_blocks_installer(self):self.exercise(tamper=True)
