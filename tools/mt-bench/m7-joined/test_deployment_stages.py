"""Execute a failing stage child: entry and refusal survive before teardown."""
import contextlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import adapter


class DeploymentStages(unittest.TestCase):
    def run_failed_deploy(self, root):
        adapter.write(root/'frozen.compose.json', {'services': {}})
        manifest={'generator':{'servingImageId':'synthetic-image'}, 'tenants':2}
        plan=[('apis','compose',[]),('prime','compose',[]),('remaining-roles','compose',[])]
        called=[]
        def compose(directory, *args, file, timeout, **options):
            name=plan[len(called)][0];called.append(name)
            # The controlled child reads the actual persisted entry before it
            # exits. No later role can hide a missing primer entry.
            program="import json,sys;v=json.load(open(sys.argv[1]));assert v[-1]['status']=='STARTED';print('synthetic startup '+v[-1]['name'],flush=True);sys.exit(17 if v[-1]['name']=='prime' else 0)"
            return adapter.command([sys.executable,'-c',program,root/'deployment-stages.json'],file=file,timeout=timeout,**options)
        patches={'frozen':lambda *a:None,'experiment_host':lambda *a:None,'verify':lambda *a:None,
                 'image':lambda *a:'synthetic-image','verify_generator':lambda *a:None,
                 'deployment_plan':lambda *a,**k:plan,'compose':compose}
        with contextlib.ExitStack() as stack:
            for name, replacement in patches.items():stack.enter_context(patch.object(adapter,name,replacement))
            with self.assertRaisesRegex(RuntimeError,'M7_COMMAND_FAILED') as refusal:
                adapter.deploy(root,manifest)
        self.assertEqual(refusal.exception.returncode,17)
        self.assertEqual(called,['apis','prime'])
        return adapter.document(root/'deployment-stages.json')

    def test_failing_primer_records_entry_elapsed_first_error_and_stops_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);rows=self.run_failed_deploy(root)
            self.assertEqual([(r['name'],r['status']) for r in rows],[('apis','SUCCEEDED'),('prime','FAILED')])
            self.assertEqual(rows[-1]['firstError'],{'code':'M7_COMMAND_FAILED','failureType':'RuntimeError','returncode':17})
            for row in rows:
                self.assertGreater(row['seconds'],0)
                self.assertGreaterEqual(row['finishedAt'],row['startedAt'])
            self.assertIn('synthetic startup prime',(root/'prime.log').read_text())
            self.assertFalse((root/'deployment.json').exists())
            self.assertFalse((root/'remaining-roles.log').exists())
            self.assertEqual((root/'deployment-stages.json').stat().st_mode&0o777,0o600)

    def test_post_command_failure_and_untrusted_message_stay_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);rows=[]
            with self.assertRaisesRegex(ValueError,'PRIVATE_VALUE'):
                with adapter.deployment_stage(root,rows,'prime'):
                    raise ValueError('PRIVATE_VALUE http://example.test/secret')
            self.assertEqual(rows[-1]['status'],'FAILED')
            self.assertEqual(rows[-1]['firstError']['code'],'M7_DEPLOYMENT_STAGE_FAILED')
            self.assertNotIn('PRIVATE_VALUE',(root/'deployment-stages.json').read_text())
            self.assertNotIn('example.test',(root/'deployment-stages.json').read_text())

    def test_platform_refusal_retains_only_classified_observation_and_original_error(self):
        expected = {'status':'OBSERVED', 'targetRole':'api', 'checkPhase':'OPERATION_READINESS',
                    'causeCode':'LIFECYCLE_WINDOW_SCHEMA_UNSAFE'}
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for reply, result in [(json.dumps(expected), expected),
                                  (RuntimeError('secret text'), {'status':'UNMEASURED','reason':'DIAGNOSTIC_READ_FAILED'})]:
                rows = []
                primary = RuntimeError('M7_COMMAND_FAILED:docker')
                primary.returncode = 1
                with patch.object(adapter, 'compose', side_effect=[reply]) as read:
                    with self.assertRaises(RuntimeError) as caught:
                        with adapter.deployment_stage(d, rows, 'platform-verify'):
                            raise primary
                self.assertIs(caught.exception, primary)
                read.assert_called_once()
                self.assertEqual(read.call_args.args, (d,'exec','-T','--workdir','/opt/app','admin','node','-'))
                self.assertEqual(read.call_args.kwargs['timeout'], 5)
                record = adapter.document(d/'deployment-stages.json')[-1]
                self.assertEqual(record['verificationDiagnostic'], result)
                self.assertEqual(record['firstError']['returncode'], 1)
                self.assertNotIn('secret text', json.dumps(record))
            with patch.object(adapter, 'compose') as read:
                with adapter.deployment_stage(d, [], 'platform-verify'):
                    pass
                read.assert_not_called()

    def test_primary_failure_survives_receipt_write_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=[];real=adapter.write
            def write(path,value):
                if value[-1]['status']!='STARTED':raise OSError('synthetic receipt failure')
                real(path,value)
            with patch.object(adapter,'write',write),self.assertRaisesRegex(RuntimeError,'M7_SYNTHETIC_PRIMARY'):
                with adapter.deployment_stage(Path(tmp),rows,'prime'):
                    raise RuntimeError('M7_SYNTHETIC_PRIMARY')


class PlatformStartupSelection(unittest.TestCase):
    def test_new_plan_verifies_before_api_and_prime_old_plan_unchanged(self):
        config={'services':{'api':{'command':['node','api']},'evaluator':{'command':['node','evaluator']},'realtime':{'command':['node','realtime']}}}
        old=adapter.deployment_plan(config,True)
        selected=adapter.deployment_plan(config,True,platform_verification=True)
        self.assertEqual([row for row in selected if row[0]!='platform-verify'],old)
        names=[row[0] for row in selected]
        self.assertLess(names.index('commission'),names.index('platform-verify'))
        self.assertLess(names.index('platform-verify'),names.index('apis'))
        self.assertLess(names.index('apis'),names.index('prime'))
        self.assertLess(names.index('prime'),names.index('remaining-roles'))

    def test_selection_requires_new_source_and_explicit_hashed_readiness(self):
        from copy import deepcopy
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);m={};config={'services':{k:{'environment':{}} for k in ('api','evaluator','realtime')}}
            adapter.platform_startup_config(config,root,m)
            self.assertEqual(m,{})
            with self.assertRaisesRegex(RuntimeError,'CAPABILITY_MISSING'):adapter.platform_startup_config(config,root,m,'serve')
            helper=root/'core/deploy/multitenant/platform-startup.js';helper.parent.mkdir(parents=True);helper.write_text('synthetic committed capability')
            with self.assertRaisesRegex(RuntimeError,'READINESS_REQUIRED'):adapter.platform_startup_config(config,root,m)
            adapter.platform_startup_config(config,root,m,'serve')
            self.assertEqual(m['tenantReadiness'],'serve')
            self.assertEqual(m['platformStartup']['helperSha256'],adapter.digest(helper))
            adapter.platform_startup_config(config,root,m,verify=True)
            for broken in ('mode','helper'):
                if broken=='mode':
                    changed=deepcopy(config);changed['services']['api']['environment']['NS_TENANT_READINESS']='all'
                    with self.assertRaisesRegex(RuntimeError,'READINESS_CHANGED'):adapter.platform_startup_config(changed,root,m,verify=True)
                else:
                    helper.write_text('changed source')
                    with self.assertRaisesRegex(RuntimeError,'STARTUP_CHANGED'):adapter.platform_startup_config(config,root,m,verify=True)


if __name__=='__main__':unittest.main()
