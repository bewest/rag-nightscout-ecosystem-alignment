"""Preparation consumes the same finite window; orchestration never leases actors."""
import json
import sys
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import adapter as a
import runner


class OrdinaryBounded(unittest.TestCase):

    def test_full_noinstall_resource_vault_config_is_expressible(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config.json'
            options={'core-repo':'/synthetic/core','core-commit':'a'*40,'deploy-repo':'/synthetic/deploy','deploy-commit':'b'*40,
                     'image':'sha256:'+'c'*64,'receipt':'/synthetic/receipt','tenants':2,'replicas':1,'profile':'pgstream-sample','run-purpose':'discovery',
                     'completion-contract':'evaluator-work-v2','static-workers':1,
                     'fixture-project':'synthetic','backend-subnet':'10.248.226.0/24','edge-subnet':'10.248.227.0/24',
                     'load-seconds':30,
                     'generator-dependencies':'/synthetic/deps','generator-dependency-receipt':'/synthetic/original.json',
                     'generator-dependency-receipt-sha256':'d'*64,'generator-dependency-preparation':'/synthetic/preparation.json',
                     'generator-dependency-preparation-sha256':'e'*64,'generator-dependency-preparation-head':'f'*40}
            config={'version':1,'helperHead':'synthetic-head','prepare':options,'k6Image':'sha256:'+'1'*64,'workSeconds':1500,'cleanupSeconds':300}
            with patch.object(a,'git',return_value='synthetic-head'),patch.object(runner.os,'cpu_count',return_value=8):
                for seconds in (1500,3600,10800,10801,86400):
                    with self.subTest(workSeconds=seconds):
                        config['workSeconds']=seconds;a.write(path,config)
                        read,argv=runner.load_config(path)
                        self.assertEqual(read,config)
                for seconds in (301,600,3600):
                    self.assertEqual(runner.validate_config({**config, 'cleanupSeconds':seconds})[0]['cleanupSeconds'], seconds)
                for field,values in {'workSeconds':(29,86401,float('inf'),float('nan'),True),
                                     'cleanupSeconds':(29,3601,float('inf'),True)}.items():
                    for value in values:
                        with self.subTest(field=field,value=value):
                            with self.assertRaisesRegex(RuntimeError,'M7_RUNNER_FINITE_LIMIT'):
                                runner.validate_config({**config,field:value})
            self.assertEqual(argv[argv.index('--generator-dependency-receipt-sha256')+1],'d'*64)
            self.assertEqual(argv[argv.index('--generator-dependency-preparation-sha256')+1],'e'*64)
            # Accepted key grammar still delegates option names to the actual parser.
            options['unknown-1-option']='no';a.write(path,config)
            with patch.object(a,'git',return_value='synthetic-head'),patch.object(runner.os,'cpu_count',return_value=8),patch.object(sys,'stderr'):
                with self.assertRaises(SystemExit):runner.load_config(path)

    def test_fresh_constructor_records_qualified_copy_and_vault_before_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            args=SimpleNamespace(core_repo='/synthetic/core',deploy_repo='/synthetic/deploy',core_commit='a'*40,deploy_commit='b'*40,
                image='image',tenants=2,replicas=1,quiet_load=3,freeze='/synthetic/receipt',profile='pgstream-sample',run_purpose='discovery',
                completion_contract='evaluator-work-v2',static_workers=1,
                dependency_qualification={'qualified':'original-provenance'})
            def git(repo,*argv):
                self.assertEqual(argv[:3],('worktree','add','--detach'))
                (d/'core/deploy/multitenant').mkdir(parents=True)
            def command(argv,**kw):
                if str(argv[0])=='tar':
                    for name in ('commission-restore.js','publish-primer.js'):(d/'core/deploy/multitenant'/name).touch()
                return b''
            def setup(directory,m):
                self.assertEqual(m['dependencyReuse'],args.dependency_qualification)
                self.assertEqual(a.document(d/'owner.json')['dependencyReuse'],args.dependency_qualification)
                raise RuntimeError('STOP_BEFORE_PRODUCT_PREPARATION')
            with patch.object(a,'fixture_project',return_value='synthetic'),patch.object(a,'port',return_value=1234),patch.object(a,'cadence_options',return_value={}),patch.object(a,'frozen'),patch.object(a,'inventory',return_value={}),patch.object(a,'host_identity',return_value='synthetic'),patch.object(a,'resources',return_value=[]),patch.object(a,'git',side_effect=git),patch.object(a,'command',side_effect=command),patch.object(a,'setup_generator',side_effect=setup):
                with self.assertRaisesRegex(RuntimeError,'STOP_BEFORE_PRODUCT_PREPARATION'):a.prepare_staged(args,d,{'sha256':'f'*64})

    def test_preparation_guard_precedes_first_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'point';events=[]
            def arm(directory,config):
                events.append('guard')
                a.write(directory/'execution.json',{'startedAt':100,'stopWorkAt':1600,'cleanupAt':1900})
            def stage(directory,name,args):
                self.assertTrue((directory/'execution.json').exists())
                events.append(name)
            source=Path(tmp)/'config.json';a.write(source,{'workSeconds':1500,'prepare':{}})
            with patch.object(runner,'validate_config',return_value=({'workSeconds':1500},[])),patch.object(runner,'preflight_receipt'),patch.object(runner,'arm_window',side_effect=arm),patch.object(runner,'stage',side_effect=stage):
                runner.prepare(source,root)
            # Source/plan admission now runs before seeding for ordinary runners too.
            # This fixture isolates guard ordering after receipt admission.
            self.assertEqual(events,['guard','prepare','source-preflight'])
            self.assertEqual(a.document(root/'execution.json')['startedAt'],100)

    def test_execution_uses_preparation_deadline_and_refuses_expiration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a.write(root/'config.json',{})
            config={'workSeconds':3600,'cleanupSeconds':300}
            state={'owner':'synthetic','startedAt':100,'stopWorkAt':3700,'cleanupAt':4000,
                   'includesPreparation':True,'configSha256':a.digest(root/'config.json')}
            a.write(root/'execution.json',state);a.write(root/'guard-ready.json',{'owner':'synthetic'})
            with patch.object(runner,'guard_alive',return_value=True),patch.object(runner.time,'time',return_value=1500):
                self.assertEqual(runner.execution_window(root,config),state)
            with patch.object(runner,'guard_alive',return_value=True),patch.object(runner.time,'time',return_value=3700):
                with self.assertRaisesRegex(RuntimeError,'WORK_DEADLINE'):runner.execution_window(root,config)
            for field in ('stopWorkAt','cleanupAt'):
                a.write(root/'execution.json',{**state,field:state[field]+100})
                with patch.object(runner,'guard_alive',return_value=True),patch.object(runner.time,'time',return_value=1500):
                    with self.assertRaisesRegex(RuntimeError,'WINDOW_CHANGED'):runner.execution_window(root,config)
            a.write(root/'execution.json',state)
            with patch.object(runner.subprocess,'Popen') as launch:
                with self.assertRaisesRegex(RuntimeError,'WINDOW_EXISTS'):runner.arm_window(root,config)
                launch.assert_not_called()

    def test_guard_starts_cleanup_at_work_deadline_not_absence_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            a.write(root/'execution.json',{'owner':'synthetic','stopWorkAt':100,'cleanupAt':400})
            def cleanup(directory,reason):
                a.write(directory/'cleanup.json',{'reason':reason})
            with patch.object(runner.time,'time',return_value=101),patch.object(runner.time,'sleep',side_effect=AssertionError('GUARD_WAITED_PAST_WORK_DEADLINE')),patch.object(runner,'cleanup',side_effect=cleanup) as called:
                runner.guard(root)
            called.assert_called_once_with(root,'FINITE_DEADLINE')

    def test_cleanup_commands_share_original_absence_budget_and_expire_before_launch(self):
        with a.command_deadline(100),patch.object(a.time,'time',return_value=97):
            self.assertEqual(a.remaining_seconds(120),3)
            with patch.object(a.subprocess,'run',return_value=type('Result',(),{'returncode':0,'stdout':b'','stderr':b''})()) as run:
                a.command(['synthetic'],timeout=120)
                self.assertEqual(run.call_args.kwargs['timeout'],3)
        with a.command_deadline(100),patch.object(a.time,'time',return_value=100),patch.object(a.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'COMMAND_DEADLINE'):a.command(['synthetic'])
            run.assert_not_called()
        self.assertIsNone(a._COMMAND_DEADLINE.get())


if __name__=='__main__':unittest.main()
