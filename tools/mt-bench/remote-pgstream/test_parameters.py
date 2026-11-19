"""Offline tests of the actual controller-facing helper/CLI seams."""
import unittest
raise unittest.SkipTest('NOT-RUNNABLE: tools/mt-bench/remote-pgstream imports harness modules deleted on 2026-11-19; see tools/mt-bench/remote-pgstream/README.md')
import copy,json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import cell,generator,protocol,producer,transport as t
import importlib.util
_fixture_spec=importlib.util.spec_from_file_location('remote_contract_fixtures',Path(__file__).with_name('test_contract.py'))
_fixtures=importlib.util.module_from_spec(_fixture_spec);_fixture_spec.loader.exec_module(_fixtures)
selected,config=_fixtures.selected,_fixtures.config

def extended(tenants=3000,rate=180,duration=600,concurrency=4):
    b=selected();b.update(tenants=tenants,expiresAt=time.time()+10000,pair={'core':t.CORE,'deploy':t.PRIMER_DEPLOY},imageId=t.PRIMER_APP)
    b['workload']={'cadence':{**t.CADENCE,'loadSeconds':duration,'offeredRps':rate},'primerConcurrency':concurrency,
                   'resourcePlan':{'reference':'root-file-plan/synthetic','tenants':tenants,'logicalPollingClients':2*tenants,
                                   'hosts':{'sut':{'providerId':'synthetic-sut','cpuCores':16,'ramBytes':64000000000},'driver':{'providerId':'synthetic-driver','cpuCores':4,'ramBytes':16000000000}}}}
    return b

def prep_args(b,root):
    root=Path(root);receipt=root/'receipt.json';binding=root/'binding.json'
    binding.write_text(json.dumps(b));receipt.write_text(json.dumps({'status':'AUTHORIZED_DIAGNOSTIC','remoteProfile':b['profile'],'remoteTransport':b['transport'],'remoteExtensionSha256':b['sourceSha256'],'completionContract':'evaluator-work-v2','remoteWorkload':b.get('workload')}))
    c=b['workload']['cadence'];args=['prepare','--binding',str(binding),'--cell',str(root/'cell'),'--core-repo',str(root/'core'),'--core-commit',b['pair']['core'],'--deploy-repo',str(root/'deploy'),'--deploy-commit',b['pair']['deploy'],'--image',b['imageId'],'--postgres-image',t.POSTGRES,'--receipt',str(receipt),'--completion-contract','evaluator-work-v2','--profile','pgstream-sample','--run-purpose','discovery','--tenants',str(b['tenants']),'--replicas','1','--warmup-seconds','10','--idle-seconds','30','--load-seconds',str(c['loadSeconds']),'--accel','1','--hot-factor','1','--sampler-interval','2','--offered-rps',str(c['offeredRps']),'--primer-concurrency',str(b['workload']['primerConcurrency'])]
    return args

class Parameters(unittest.TestCase):
    def test_explicit_supported_cohorts_require_exact_resource_plan(self):
        for n in protocol.SUPPORTED_COHORTS:
            b=extended(n);self.assertEqual(protocol.binding(b)['tenants'],n)
        for edit in (lambda b:b.update(tenants=2000),lambda b:b.pop('workload'),lambda b:b['workload']['resourcePlan'].update(tenants=1000),lambda b:b['workload']['resourcePlan'].update(logicalPollingClients=1),lambda b:b['workload']['resourcePlan']['hosts']['driver'].update(providerId='synthetic-sut'),lambda b:b['workload']['resourcePlan']['hosts']['sut'].update(cpuCores=float('nan')),lambda b:b['workload']['resourcePlan']['hosts']['sut'].update(ramBytes=True)):
            b=extended();edit(b)
            with self.assertRaises(RuntimeError):protocol.binding(b)
    def test_workload_and_deadline_mutations_refuse(self):
        for edit in (lambda b:b['workload']['cadence'].update(offeredRps=0),lambda b:b['workload']['cadence'].update(offeredRps=True),lambda b:b['workload']['cadence'].update(offeredRps=float('inf')),lambda b:b['workload']['cadence'].update(loadSeconds=3601),lambda b:b['workload']['cadence'].update(hotFactor=10),lambda b:b['workload']['cadence'].update(restart=True),lambda b:b['workload'].update(primerConcurrency=0)):
            b=extended();edit(b)
            with self.assertRaises(RuntimeError):protocol.binding(b)
    def test_only_two_source_pairs_and_legacy_concurrency_refusal(self):
        b=extended();protocol.binding(b)
        b['pair']['deploy']=t.DEPLOY;b['imageId']=t.APP
        with self.assertRaisesRegex(RuntimeError,'UNSUPPORTED_SOURCE'):protocol.binding(b)
        b['workload']['primerConcurrency']=1;protocol.binding(b)
        for image in (t.PRIMER_APP,'sha256:'+'a'*64):
            with self.assertRaisesRegex(RuntimeError,'QUALIFIED_SOURCE'):protocol.binding({**b,'imageId':image})
    def test_repaired_source_requires_exact_image_and_v2_before_prepare(self):
        b=extended(3000,180,310,2);b.update(pair={'core':t.REPAIRED_CORE,'deploy':t.PRIMER_DEPLOY},imageId=t.REPAIRED_APP);protocol.binding(b)
        for image in (t.PRIMER_APP,t.APP):
            with self.assertRaisesRegex(RuntimeError,'QUALIFIED_SOURCE'):protocol.binding({**b,'imageId':image})
        with tempfile.TemporaryDirectory()as tmp:
            args=prep_args(b,tmp)
            with patch.object(sys,'argv',['cell.py',*args]),patch.object(cell.app.a,'prepare')as prepare,patch.object(cell.app,'record_prepared_binding'):
                cell.main();self.assertEqual(prepare.call_args.args[0].completion_contract,'evaluator-work-v2')
            args[args.index('--completion-contract')+1]='evaluator-work-v1'
            with patch.object(sys,'argv',['cell.py',*args]),patch.object(cell.app.a,'prepare')as prepare:
                with self.assertRaisesRegex(RuntimeError,'REPAIRED_COMPLETION_V2_REQUIRED'):cell.main()
                prepare.assert_not_called()
    def test_expired_cleanup_binding_keeps_metadata_validation(self):
        b=extended();protocol.binding(b, b['expiresAt']-541)
        with tempfile.TemporaryDirectory()as tmp:
            args=prep_args({**b,'expiresAt':time.time()+600},tmp)
            with patch.object(sys,'argv',['cell.py',*args]),patch.object(cell.app.a,'prepare')as prepare:
                with self.assertRaisesRegex(RuntimeError,'DURATION_OUTSIDE_ENVELOPE'):cell.main()
                prepare.assert_not_called()
    def test_actual_cli_matches_bound_prepare_values(self):
        b=extended(5000,240,420,8)
        with tempfile.TemporaryDirectory()as tmp:
            args=prep_args(b,tmp)
            with patch.object(sys,'argv',['cell.py',*args]),patch.object(cell.app.a,'prepare')as prepare,patch.object(cell.app,'record_prepared_binding')as record:
                cell.main();m=prepare.call_args.args[0];self.assertEqual(m.tenants,5000);self.assertEqual(m.primer_concurrency,8);self.assertEqual(cell.app.a.cadence_options(m),b['workload']['cadence']);record.assert_called_once()
    def test_actual_cli_missing_rate_duration_cohort_concurrency_refuses_before_prepare(self):
        for flag in ('--offered-rps','--load-seconds','--tenants','--primer-concurrency'):
            with self.subTest(flag=flag),tempfile.TemporaryDirectory()as tmp:
                args=prep_args(extended(),tmp);i=args.index(flag)
                if flag=='--tenants':args[i+1]='1000'
                elif flag=='--load-seconds':args[i+1]='310'
                else:del args[i:i+2]
                with patch.object(sys,'argv',['cell.py',*args]),patch.object(cell.app.a,'prepare')as prepare:
                    with self.assertRaisesRegex(RuntimeError,'REMOTE_PREPARE_PROFILE_REQUIRED'):cell.main()
                    prepare.assert_not_called()
    def test_changed_receipt_workload_refuses_before_prepare(self):
        b=extended()
        with tempfile.TemporaryDirectory()as tmp:
            args=prep_args(b,tmp);p=Path(tmp)/'receipt.json';v=json.loads(p.read_text());v['remoteWorkload']['cadence']['offeredRps']=120;p.write_text(json.dumps(v))
            with patch.object(sys,'argv',['cell.py',*args]),patch.object(cell.app.a,'prepare')as prepare:
                with self.assertRaisesRegex(RuntimeError,'AUTHORIZATION'):cell.main()
                prepare.assert_not_called()
    def test_actual_generator_and_producer_commands_forward_values(self):
        b=extended(10000,240,420,8);descriptor={'trafficRunId':'synthetic-run','settingsFingerprint':'a'*64};probe,k6=generator.traffic_commands('/synthetic',b,descriptor,'synthetic-k6',123)
        for flag,value in (('--window','420'),('--per','2'),('--probeEvery','300000'),('--restart','0')):self.assertEqual(probe[probe.index(flag)+1],value)
        for value in ('DURATION=420','OFFERED_RPS=240','ACCEL=1','HOT_FACTOR=1'):self.assertIn(value,k6)
        plan=producer.deployment_plan(config(),True,8);prime=next(args for name,scope,args in plan if name=='prime');self.assertEqual(prime[-2:],['--concurrency','8'])
        legacy=selected();probe,k6=generator.traffic_commands('/synthetic',legacy,descriptor,'synthetic-k6',123);self.assertIn('DURATION=310',k6);self.assertFalse(any('OFFERED_RPS='in str(x)for x in k6))
    def test_cell_manifest_cannot_change_extended_parameters(self):
        b=extended();m=dict(pair=b['pair'],imageId=b['imageId'],postgresImageId=t.POSTGRES,profile='pgstream-sample',runPurpose='discovery',tenants=b['tenants'],replicas=1,cadence=b['workload']['cadence'],primerConcurrency=4)
        t.cell_contract(m,b)
        for key,value in (('cadence',t.CADENCE),('tenants',1000),('primerConcurrency',1)):
            with self.assertRaises(RuntimeError):t.cell_contract({**m,key:value},b)

if __name__=='__main__':unittest.main()
