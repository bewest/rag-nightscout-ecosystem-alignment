import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parent))
import adapter
from contract import *
from probe import generate
from workload import generate as generate_workload
import campaign
from reduce import measurements

A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'
from profile_provenance import identity,selection
PROFILE=identity({'schema':1,'sha256':'f'*64,'sourceCommit':'a'*40,'sourceBlobs':{}},selection(),{'services':{'api':{},'vault':{'command':['vault','server']},'realtime':{},'evaluator':{}}})
OBS={'verdict':'PASS','observations':1,'invalid':0,'mismatch':0}

class Contract(unittest.TestCase):
    def setUp(self):
        self.tenants=[{'id':A,'host':'a.example.test','token':uuid.uuid4().hex}, {'id':B,'host':'b.example.test','token':uuid.uuid4().hex}]
        self.metrics={'writes_ok':{'count':4}, f'writes_ok{{tenant:{A}}}':{'count':2},f'writes_ok{{tenant:{B}}}':{'values':{'count':2}},'writes_ok{kind:entries}':{'count':2},'writes_ok{kind:devicestatus}':{'count':2}}
        self.stored={A:{'entries':1,'devicestatus':1},B:{'entries':1,'devicestatus':1}}
    def test_independent_accepted_and_domain_oracle_break_restore(self):
        self.assertEqual(oracle(self.stored,self.metrics,{},self.tenants,True)['verdict'],'GREEN')
        self.stored[A]['entries']=0
        self.assertEqual(oracle(self.stored,self.metrics,{},self.tenants,True)['verdict'],'RED')
        self.stored[A]['entries']=1
        self.assertEqual(oracle(self.stored,self.metrics,{},self.tenants,True)['verdict'],'GREEN')
        # Aggregate tenant totals alone would miss swapped domain counts.
        self.stored[A]={'entries':2,'devicestatus':0}
        self.assertEqual(oracle(self.stored,self.metrics,{},self.tenants,True)['verdict'],'RED')
    def test_empty_uncertain_and_unknown_tenant_are_never_capacity_green(self):
        with self.assertRaisesRegex(RuntimeError,'NO_ACCEPTED'):oracle({}, {}, {}, self.tenants)
        self.metrics[f'writes_uncertain{{tenant:{A}}}']={'count':1}
        self.assertEqual(oracle(self.stored,self.metrics,{},self.tenants,True)['verdict'],'RED')
        with self.assertRaisesRegex(RuntimeError,'TENANT_SCOPE'):oracle({'other':{}},self.metrics,{},self.tenants)
    def test_primer_requires_new_data_token_contract_and_exact_roster(self):
        rows=[{**row,'dataToken':row['token']} for row in self.tenants]
        self.assertEqual(len(tenant_projection({'version':1,'tenants':rows},2)),2)
        del rows[0]['dataToken']
        with self.assertRaisesRegex(RuntimeError,'DATA_TOKEN_REQUIRED'):tenant_projection({'version':1,'tenants':rows},2)
        with self.assertRaisesRegex(RuntimeError,'COUNT'):tenant_projection({'version':1,'tenants':[]},2)
    def test_source_pair_and_ownership_controls(self):
        labels_match({'org.opencontainers.image.revision':'a'*40,'org.nightscout.deploy.revision':'b'*40},'a'*40,'b'*40)
        with self.assertRaisesRegex(RuntimeError,'DEPLOY_MISMATCH'):labels_match({'org.opencontainers.image.revision':'a'*40},'a'*40,'b'*40)
        owned({'Config':{'Labels':{OWNER:'ours'}}},'ours')
        with self.assertRaisesRegex(RuntimeError,'NOT_OWNED'):owned({'Config':{'Labels':{OWNER:'peer'}}},'ours')
        serving_mounts({'services':{'api':{'volumes':[{'target':'/run/ns-config'}]}}})
        with self.assertRaisesRegex(RuntimeError,'SOURCE_MOUNT_REFUSED'):serving_mounts({'services':{'api':{'volumes':[{'target':'/opt/app/lib'}]}}})
    def test_campaign_requires_all_counts_and_replica_cells_with_same_pair(self):
        pair={'core':'a'*40,'deploy':'b'*40};row={'pair':pair,'hostIdentity':'d'*64,'instrument':'c'*64,'verdict':'PASS','imageId':'sha256:'+'e'*64,'measurements':{'complete':True},'profileSelection':PROFILE,'settingsFingerprintObservation':OBS}
        document={'profileSelection':PROFILE,'version':1,'kind':'m7-joined-capacity','pair':pair,'instrument':'c'*64,'imageId':'sha256:'+'e'*64,'hostIdentity':'d'*64,'cells':[{**row,'tenants':n,'replicas':a} for a in REPLICAS for n in COUNTS]}
        self.assertTrue(campaign_check(document));broken=copy.deepcopy(document);broken['cells'].pop()
        with self.assertRaisesRegex(RuntimeError,'MISSING_CELL'):campaign_check(broken)
        broken=copy.deepcopy(document);broken['cells'][0]['pair']={**pair,'core':'d'*40}
        with self.assertRaisesRegex(RuntimeError,'MIXED_SOURCE'):campaign_check(broken)
    def test_probe_adaptation_is_explicit_syntax_checked_and_removes_lease_proxy(self):
        with tempfile.TemporaryDirectory(prefix='m7-probe-test-') as scratch:
            file=Path(scratch)/'probe.js';record=generate(adapter.ROOT,file);source=file.read_text()
            self.assertNotIn('tenant_lifecycle_operations',source)
            self.assertIn('runtimeAcquisitionObservation',source);self.assertIn('M7_RESTART_ROLES',source)
            self.assertIn('hotTenantWriteToFrameMs',source);self.assertIn('M7_ESTABLISHED_SOCKETS_INCOMPLETE',source)
            self.assertIn("require('./restart.cjs').restart",source)
            self.assertEqual(record['adaptedSha256'],digest(file))
            subprocess.run(['node','--check',str(file)],check=True,capture_output=True)
    def test_current_deterministic_workload_and_functional_refusal_counter(self):
        with tempfile.TemporaryDirectory(prefix='m7-workload-test-') as scratch:
            file=Path(scratch)/'workload.js';generate_workload(adapter.ROOT,file)
            tenants=Path(scratch)/'tenants.json';tenants.write_text(json.dumps(self.tenants))
            calls=json.loads(subprocess.check_output(['node',str(adapter.HERE/'workload-shapes.cjs'),str(file),str(tenants)],env=adapter.runtime_env({'M7_FIXTURE_REFUSE_READS':'1'})))
            self.assertEqual(len([r for r in calls if r.get('counter')=='responses_refused']),8)
            dates=[r['body'][0]['date'] for r in calls if r.get('method')=='POST' and isinstance(r.get('body'),list) and '/entries?' in r['url']]
            self.assertEqual(dates,[1800000000000,1800000150000])
    def test_replica_ladder_never_overrides_functional_block_and_requires_ceiling_evidence(self):
        with tempfile.TemporaryDirectory(prefix='m7-ladder-test-') as scratch:
            root=Path(scratch);master={'pair':{'core':'a'*40,'deploy':'b'*40},'instrument':'c'*64,'hostIdentity':'d'*64}
            campaign.authorize_profile(1,master,root,None)
            with self.assertRaisesRegex(RuntimeError,'FIRST_PROFILE'):campaign.authorize_profile(2,master,root,None)
            prior={'status':'FAIL','failureClass':'diagnosis-required'};adapter.write(root/'profile-1.json',prior)
            with self.assertRaisesRegex(RuntimeError,'NEEDS_DIAGNOSIS'):campaign.authorize_profile(2,master,root,None)
            receipt={**master,'kind':'measured-profile-ceiling','classification':'performance','profileArtifactSha256':digest(root/'profile-1.json'),'diagnosisEvidenceSha256':'e'*64}
            adapter.write(root/'receipt.json',receipt);campaign.authorize_profile(2,master,root,root/'receipt.json')
            master['functionalBlock']=True
            with self.assertRaisesRegex(RuntimeError,'GLOBAL_FUNCTIONAL_BLOCK'):campaign.authorize_profile(2,master,root,root/'receipt.json')
            self.assertEqual(campaign.failure_class('M7_ORACLE_CLIENT_TOTAL_MISMATCH'),'functional-block')
    def test_resource_reducer_distinguishes_missing_samples_and_process_rss_from_heap(self):
        with tempfile.TemporaryDirectory(prefix='m7-reduce-test-') as scratch:
            root=Path(scratch)
            for name in ('idle-disabled','idle','load'):
                folder=root/name;folder.mkdir()
                for edge,at,cpu,calls in [('before',1,1000000,1),('after',3,2000000,3)]:
                    adapter.write(folder/(edge+'-cgroups.json'),{'at':at,'roles':{'api':{'id':'same','cgroup':'usage_usec '+str(cpu)+'\n1024\nanon 512\n','processRssKiB':'PID COMMAND RSS\n1 node 100'}}})
                    (folder/(edge+'-pg-role.tsv')).write_text('role\t'+str(calls)+'\t'+str(calls*10)+'\n')
                if name!='idle-disabled':
                    (folder/'docker-stats.tsv').write_text('t\tcontainer\tcpu_pct\tmem\n2\towned-api-1\t50%\t1MiB / 1GiB\n')
                    (folder/'pg-activity.tsv').write_text('t\trole\tstate\twait_event_type\twait_event\tn\n2\trole\tidle\tClient\tClientRead\t1\n')
            shapes={name:{'med':1,'p(95)':2,'p(99)':3,'count':1} for name in ('w_sgv','w_devicestatus','w_treatments_v3','r_sgv','r_devicestatus','r_treatments','r_status')}
            adapter.write(root/'load/k6-summary.json',{'metrics':{'http_req_duration{shape:'+name+'}':value for name,value in shapes.items()}})
            value=measurements(root,{'project':'owned','tenants':2})
            self.assertTrue(value['complete']);self.assertEqual(value['windows']['load']['roles']['api']['cpuCoresMean'],.5)
            self.assertEqual(value['windows']['load']['roles']['api']['dockerMemoryBytesMax'],1024**2)
            (root/'idle/docker-stats.tsv').write_text('t\tcontainer\tcpu_pct\tmem\n')
            self.assertFalse(measurements(root,{'project':'owned','tenants':2})['complete'])
    def test_shipping_deployment_orders_commission_api_prime_publish_before_remaining_roles(self):
        config={'services':{name:{'command':['node','entrypoint.js',role]} for name,role in [('api','api'),('api-2','api'),('realtime','realtime'),('evaluator','evaluator'),('tenant-admin','tenant-admin')]}}
        plan=adapter.deployment_plan(config)
        self.assertEqual([row[0] for row in plan],['infrastructure','bootstrap','admin-feed','provision','commission','apis','prime','publish-primer','remaining-roles'])
        self.assertNotIn('realtime',next(r[2] for r in plan if r[0]=='apis'))
        self.assertIn('commission-restore.js',' '.join(next(r[2] for r in plan if r[0]=='commission')))
        self.assertEqual(next(r[1] for r in plan if r[0]=='publish-primer'),'local')
    def test_remote_pilot_is_distinct_and_does_not_skip_750(self):
        pair={'core':'a'*40,'deploy':'b'*40};row={'pair':pair,'hostIdentity':'d'*64,'instrument':'c'*64,'imageId':'sha256:'+'e'*64,'verdict':'PASS','measurements':{'complete':True},'profileSelection':PROFILE,'settingsFingerprintObservation':OBS,'profile':'remote-pilot','replicas':1}
        doc={'profileSelection':PROFILE,'profileReplicas':1,'kind':'m7-joined-remote-pilot','pair':pair,'instrument':'c'*64,'hostIdentity':'d'*64,'imageId':row['imageId'],'cells':[{**row,'tenants':n} for n in PILOT_COUNTS]}
        self.assertTrue(pilot_check(doc));doc['cells'].pop(1)
        with self.assertRaisesRegex(RuntimeError,'MISSING_CELL'):pilot_check(doc)
        self.assertEqual(CADENCE['remote-pilot']['accel'],1);self.assertEqual(CADENCE['remote-pilot']['loadSeconds'],300)
    def test_pilot_orchestrator_routes_explicit_counts_and_profile_without_duplicate_args(self):
        with tempfile.TemporaryDirectory(prefix='m7-orchestrator-test-') as scratch:
            root=Path(scratch);seen=[];pair={'core':'a'*40,'deploy':'b'*40};master={'pair':pair,'instrument':'c'*64,'hostIdentity':'d'*64,'cells':[]}
            args=SimpleNamespace(mode='pilot',replicas=None,ceiling_receipt=None,k6_image='not-run')
            def prepare(options):
                seen.append((options.tenants,options.replicas,options.profile));folder=Path(options.directory);folder.mkdir();adapter.write(folder/'owner.json',{})
            def run(folder,manifest,image):adapter.write(folder/'summary.json',{'pair':pair,'hostIdentity':'d'*64,'imageId':'sha256:'+'e'*64,'instrument':'c'*64,'profileSelection':PROFILE})
            with patch.object(adapter,'prepare',prepare),patch.object(adapter,'load',lambda folder:(Path(folder),{})),patch.object(adapter,'deploy'),patch.object(adapter,'run',run),patch.object(adapter,'down'):
                campaign.ladder(args,1,root,master)
            self.assertEqual(seen,[(500,1,'remote-pilot'),(750,1,'remote-pilot'),(1000,1,'remote-pilot')])
    def test_owned_host_job_cannot_kill_a_reused_identity(self):
        with tempfile.TemporaryDirectory(prefix='m7-job-test-') as scratch:
            process=subprocess.Popen(['sleep','30'],start_new_session=True);file=Path(scratch)/'job.json'
            try:
                adapter.job_record(file,process,'ours',True);value=adapter.document(file);bad={**value,'startTicks':'wrong'};adapter.write(file,bad)
                with self.assertRaisesRegex(RuntimeError,'IDENTITY_CHANGED'):adapter.stop_job(file,'ours')
                self.assertIsNone(process.poll());adapter.write(file,value);adapter.stop_job(file,'ours');self.assertIsNotNone(process.wait(timeout=2));adapter.stop_job(file,'ours')
            finally:
                if process.poll() is None:process.terminate();process.wait(timeout=2)
    def test_diagnostic_authorization_is_not_full_acceptance_and_cannot_unlock_capacity(self):
        m={'profile':'fresh-image-diagnostic','pair':{'core':'a'*40,'deploy':'b'*40},'instrument':{'sha256':'c'*64},'tenants':2,'replicas':2}
        receipt={'kind':'joined-diagnostic','status':'AUTHORIZED_DIAGNOSTIC','pair':m['pair'],'instrument':'c'*64,'limits':{'tenants':10,'apiReplicas':2,'trafficSeconds':180}}
        self.assertEqual(receipt_scope(m,receipt,'build')['kind'],'diagnostic-only')
        self.assertEqual(receipt_scope(m,receipt,'diagnose')['trafficSeconds'],180)
        with self.assertRaisesRegex(RuntimeError,'CANNOT_RUN_CAPACITY'):receipt_scope(m,receipt,'run')
        for profile in ('capacity','remote-pilot'):
            with self.assertRaisesRegex(RuntimeError,'FROZEN_ACCEPTANCE_REQUIRED'):receipt_scope({**m,'profile':profile},receipt,'run')
        with self.assertRaisesRegex(RuntimeError,'LIMIT_INVALID'):receipt_scope({**m,'tenants':11},receipt,'deploy')
        with self.assertRaisesRegex(RuntimeError,'LIMIT_INVALID'):receipt_scope(m,{**receipt,'limits':{**receipt['limits'],'trafficSeconds':181}},'diagnose')
        with self.assertRaisesRegex(RuntimeError,'RECEIPT_REQUIRED'):receipt_scope(m,{**receipt,'status':'PASS'},'deploy')
    def test_diagnostic_result_cannot_satisfy_full_or_pilot_verdict(self):
        doc={'kind':'m7-joined-fresh-image-diagnostic','pair':{'core':'a'*40,'deploy':'b'*40},'instrument':'c'*64,'hostIdentity':'d'*64,'imageId':'sha256:'+'e'*64,'tenants':2,'replicas':2,'verdict':'PASS','checks':{key:True for key in DIAGNOSTIC_CHECKS},'acceptedWrites':2,'dataHttpRequests':8,'httpAccountingVersion':2,'criterionHttpRequests':8,'physicalHttpRequests':8,'warmProbeHttpRequests':0,'trailRecords':8,'trailBytes':2000,'trafficDeadlineSeconds':180,'oracle':'GREEN','oracleControl':{'baseline':'GREEN','broken':'RED','restored':'GREEN'},'fullAcceptance':'NOT_RUN','capacity':'NO-MEASUREMENT'}
        self.assertTrue(diagnostic_check(doc))
        for values in ({'physicalHttpRequests':9},{'criterionHttpRequests':7},{'warmProbeHttpRequests':513},{'trailBytes':262145},{'httpAccountingVersion':1},{'warmProbeHttpRequests':True,'physicalHttpRequests':9,'trailRecords':9}):
            with self.assertRaisesRegex(RuntimeError,'HTTP_ACCOUNTING_REQUIRED'):diagnostic_check({**doc,**values})
        with self.assertRaisesRegex(RuntimeError,'SUMMARY_SHAPE'):campaign_check(doc)
        with self.assertRaisesRegex(RuntimeError,'PILOT_SHAPE'):pilot_check(doc)
        with self.assertRaisesRegex(RuntimeError,'NOT_PASSING'):diagnostic_check({**doc,'checks':{'stockRecovery':False}})
    def test_private_command_failure_capture_precedes_prepared_state_and_never_leaks_public_error(self):
        with tempfile.TemporaryDirectory(prefix='m7-private-command-test-') as scratch:
            root=Path(scratch)
            with adapter.private_commands(root/'prepare-commands'):
                with self.assertRaises(RuntimeError) as failure:
                    adapter.command([sys.executable,'-c',"import sys;print('PRIVATE_ONLY_STDOUT');print('PRIVATE_ONLY_STDERR',file=sys.stderr);sys.exit(7)"],phase='product-prepare')
            self.assertTrue(str(failure.exception).startswith('M7_COMMAND_FAILED:'))
            self.assertNotIn('PRIVATE_ONLY',str(failure.exception))
            metadata=list((root/'prepare-commands').glob('*.json'));self.assertEqual(len(metadata),1)
            value=adapter.document(metadata[0]);self.assertEqual(value['phase'],'product-prepare');self.assertEqual(value['returncode'],7)
            for key,marker in [('stdout','PRIVATE_ONLY_STDOUT'),('stderr','PRIVATE_ONLY_STDERR')]:
                file=root/'prepare-commands'/value[key];self.assertIn(marker,file.read_text());self.assertEqual(file.stat().st_mode&0o777,0o600)
            self.assertFalse((root/'owner.json').exists())
    def test_diagnostic_failure_receipt_preserves_only_safe_instrument_code(self):
        with tempfile.TemporaryDirectory(prefix='m7-failure-code-') as scratch:
            out=Path(scratch)
            self.assertEqual(adapter.diagnostic_observed_code(out),'M7_DIAGNOSTIC_CLIENT_REFUSED')
            adapter.write(out/'diagnostic-observations.json',{'failureCode':'M7_DIAGNOSTIC_HTTP_REFUSED'})
            self.assertEqual(adapter.diagnostic_observed_code(out),'M7_DIAGNOSTIC_HTTP_REFUSED')
            for value in [{'failureCode':'M7_DIAGNOSTIC_HTTP_REFUSED private'}, {'failureCode':'TENANT_WARMING'}, [], {'failureCode':42}]:
                adapter.write(out/'diagnostic-observations.json',value)
                self.assertEqual(adapter.diagnostic_observed_code(out),'M7_DIAGNOSTIC_CLIENT_REFUSED')
    def test_generator_missing_actual_client_refuses_before_workload(self):
        with tempfile.TemporaryDirectory(prefix='m7-missing-client-') as scratch:
            root=Path(scratch);(root/'dependencies').mkdir();(root/'dependencies/package.json').write_text('{}')
            with adapter.private_commands(root/'private'):
                with self.assertRaisesRegex(RuntimeError,'M7_COMMAND_FAILED'):
                    adapter.generator_client(root,adapter.generator_tools())
            raw=''.join(file.read_text() for file in (root/'private').glob('*.stderr'))
            self.assertIn("Cannot find module 'socket.io-client'",raw)
    def test_role_roster_is_derived_from_actual_role_commands(self):
        self.assertEqual(adapter.service_roster({'services':{'api':{'command':['node','entrypoint.js','api']},'api-4':{'command':['node','entrypoint.js','api']},'rt-special':{'command':['node','entrypoint.js','realtime']},'feed-reader':{'command':['node','entrypoint.js','feed-reader']}}}),['api','api-4','rt-special'])

if __name__=='__main__':unittest.main()
