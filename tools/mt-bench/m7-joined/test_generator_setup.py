"""Local launch contracts; no Docker or application resources are needed."""
import ast
import json
import tempfile
import campaign
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

    def direct_command(self, m):
        # Evaluate the actual argv expression passed to command(), without
        # launching the surrounding stack/probe/evaluator machinery.
        tree=ast.parse(Path(adapter.__file__).read_text())
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.Call)
                  and isinstance(n.func,ast.Name) and n.func.id=='command' and n.args
                  and isinstance(n.args[0],ast.List) and len(n.args[0].elts)>2
                  and all(isinstance(x,ast.Constant) for x in n.args[0].elts[:3])
                  and [x.value for x in n.args[0].elts[:3]]==['docker','run','--rm'])
        scope={**vars(adapter),'d':Path('/tmp/synthetic'),'out':Path('/tmp/synthetic/load'),'m':m,'k6_id':'pinned-image','runid':'synthetic'}
        return eval(compile(ast.Expression(node.args[0]),'<actual local k6 argv>','eval'),scope)

    def test_default_and_explicit_selection_reach_both_local_launchers(self):
        for value,expected in [(None,1),(1,1),(16,16),(64,64)]:
            m=self.manifest(value)
            for argv in (self.direct_command(m), discovery.k6_command(adapter,Path('/tmp/synthetic'),m,'pinned-image','synthetic')):
                env=[argv[i+1] for i,x in enumerate(argv[:-1]) if x=='-e']
                self.assertEqual([x for x in env if x.startswith('JWT_SETUP_CONCURRENCY=')],['JWT_SETUP_CONCURRENCY='+str(expected)])
                self.assertIn('ACCEL=1',env)
                self.assertIn('DURATION=2',env)

    def test_invalid_manifest_values_refuse_before_launch(self):
        for value in (0,65,-1,'16',16.0,True):
            with self.assertRaisesRegex(RuntimeError,'M7_JWT_SETUP_CONCURRENCY_INVALID'):
                discovery.k6_command(adapter,Path('/tmp/synthetic'),self.manifest(value),'image','run')

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


    def test_campaign_cli_records_selection_and_refuses_changed_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign'
            argv=['campaign.py','ladder','--work',str(root),'--core-repo','/tmp/core','--core-commit','a'*40,'--deploy-repo','/tmp/deploy','--deploy-commit','b'*40,'--image','synthetic','--freeze','/tmp/freeze','--k6-image','pinned-image','--replicas','1','--jwt-setup-concurrency','16']
            with patch.object(adapter,'instrument',return_value={'sha256':'f'*64}),patch.object(adapter,'inventory',return_value={}),patch.object(campaign,'host_identity',return_value='synthetic'),patch.object(campaign,'ladder') as ladder,patch('sys.argv',argv),patch('builtins.print'):
                campaign.main()
                self.assertEqual(ladder.call_args[0][0].jwt_setup_concurrency,16)
                self.assertEqual(json.loads((root/'campaign.json').read_text())['jwtSetupConcurrency'],16)
                campaign.main()
                with patch('sys.argv',argv[:-1]+['1']):
                    with self.assertRaisesRegex(RuntimeError,'M7_CAMPAIGN_IDENTITY_CHANGED'):campaign.main()
                legacy=json.loads((root/'campaign.json').read_text());legacy.pop('jwtSetupConcurrency');(root/'campaign.json').write_text(json.dumps(legacy))
                with patch('sys.argv',argv[:-1]+['1']):campaign.main()
                with self.assertRaisesRegex(RuntimeError,'M7_CAMPAIGN_IDENTITY_CHANGED'):campaign.main()


if __name__=='__main__':unittest.main()
