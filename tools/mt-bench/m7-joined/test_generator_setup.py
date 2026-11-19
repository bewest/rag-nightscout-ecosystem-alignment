"""Local launch contracts; no Docker or application resources are needed."""
import ast
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import adapter
import discovery


class SetupConcurrency(unittest.TestCase):
    def manifest(self, value=None):
        m = {'project':'synthetic','owner':'a'*32,'port':12345,
             'settingsFingerprint':{'sha256':'f'*64},'cadence':{'loadSeconds':2,'accel':1,'hotFactor':10}}
        if value is not None:m['jwtSetupConcurrency']=value
        return m

    def test_invalid_manifest_values_refuse_before_launch(self):
        for value in (0,65,-1,'16',16.0,True):
            with self.assertRaisesRegex(RuntimeError,'M7_JWT_SETUP_CONCURRENCY_INVALID'):
                adapter.k6_tenants(Path('/tmp/synthetic'),self.manifest(value))

    def test_prepare_records_selection_and_keeps_cadence_unchanged(self):
        args=SimpleNamespace(core_commit='a'*40,deploy_commit='b'*40,core_repo='/tmp/core',deploy_repo='/tmp/deploy',image='synthetic',tenants=6,replicas=1,quiet_load=3,freeze='/tmp/freeze',profile='capacity',jwt_setup_concurrency=16)
        captured=[]
        class Stop(Exception):pass
        def capture(path,m):captured.append(m);raise Stop()
        before={k:dict(v) for k,v in adapter.CADENCE.items()}
        with patch.object(adapter,'port',return_value=12345),patch.object(adapter,'inventory',return_value={}),patch.object(adapter,'host_identity',return_value='synthetic'),patch.object(adapter,'write',side_effect=capture):
            with self.assertRaises(Stop):adapter.prepare_staged(args,Path('/tmp/synthetic'),{})
        self.assertEqual(captured[0]['jwtSetupConcurrency'],16)
        self.assertEqual(adapter.CADENCE,before)

    def test_prepare_cli_defaults_serial_and_refuses_out_of_range(self):
        args=['prepare','--directory','/tmp/new','--core-repo','/tmp/core','--core-commit','a'*40,'--deploy-repo','/tmp/deploy','--deploy-commit','b'*40,'--image','synthetic','--freeze','/tmp/freeze','--tenants','500','--replicas','1']
        self.assertEqual(adapter.parser().parse_args(args).jwt_setup_concurrency,1)
        self.assertEqual(adapter.parser().parse_args(args+['--jwt-setup-concurrency','16']).jwt_setup_concurrency,16)
        class Captured(Exception):pass
        with patch.object(adapter,'port',return_value=12345),patch.object(adapter,'inventory',return_value={}),patch.object(adapter,'host_identity',return_value='synthetic'),patch.object(adapter,'write',side_effect=Captured) as publication:
            for purpose, value in [('acceptance',65),('discovery',0),('discovery',2**53)]:
                parsed=adapter.parser().parse_args(args+['--run-purpose',purpose,'--jwt-setup-concurrency',str(value)])
                with self.assertRaisesRegex(RuntimeError,'M7_JWT_SETUP_CONCURRENCY_INVALID'):
                    adapter.prepare_staged(parsed,Path('/tmp/synthetic'),{})
            publication.assert_not_called()
            discovery_args=adapter.parser().parse_args(args+['--run-purpose','discovery','--jwt-setup-concurrency','65'])
            with self.assertRaises(Captured):
                adapter.prepare_staged(discovery_args,Path('/tmp/synthetic'),{})
            self.assertEqual(publication.call_args.args[1]['jwtSetupConcurrency'],65)




if __name__=='__main__':unittest.main()
