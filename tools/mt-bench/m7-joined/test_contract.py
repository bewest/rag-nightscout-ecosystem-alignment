import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import adapter
from contract import *
from probe import generate
from workload import generate as generate_workload
import campaign
from reduce import measurements

A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'

class Contract(unittest.TestCase):
    def setUp(self):
        self.tenants=[{'id':A,'host':'a.example.test','token':'synthetic-test-only'}, {'id':B,'host':'b.example.test','token':'synthetic-test-only'}]
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
        pair={'core':'a'*40,'deploy':'b'*40};row={'pair':pair,'instrument':'c'*64,'verdict':'PASS','imageId':'sha256:'+'e'*64,'measurements':{'complete':True}}
        document={'version':1,'kind':'m7-joined-capacity','pair':pair,'instrument':'c'*64,'imageId':'sha256:'+'e'*64,'cells':[{**row,'tenants':n,'replicas':a} for a in REPLICAS for n in COUNTS]}
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
            self.assertEqual(record['adaptedSha256'],digest(file))
            subprocess.run(['node','--check',str(file)],check=True,capture_output=True)
    def test_current_deterministic_workload_and_functional_refusal_counter(self):
        with tempfile.TemporaryDirectory(prefix='m7-workload-test-') as scratch:
            file=Path(scratch)/'workload.js';generate_workload(adapter.ROOT,file)
            tenants=Path(scratch)/'tenants.json';tenants.write_text(json.dumps(self.tenants))
            calls=json.loads(subprocess.check_output(['node',str(adapter.HERE/'workload-shapes.cjs'),str(file),str(tenants)],env=adapter.runtime_env({'M7_FIXTURE_REFUSE_READS':'1'})))
            self.assertEqual(len([r for r in calls if r.get('counter')=='responses_refused']),8)
            dates=[r['body'][0]['date'] for r in calls if r.get('method')=='POST' and isinstance(r.get('body'),list) and r['url'].endswith('token=synthetic-test-only') and '/entries?' in r['url']]
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
            self.assertEqual(value['windows']['load']['roles']['api']['rssBytesMax'],1024**2)
            (root/'idle/docker-stats.tsv').write_text('t\tcontainer\tcpu_pct\tmem\n')
            self.assertFalse(measurements(root,{'project':'owned','tenants':2})['complete'])
    def test_role_roster_is_derived_from_actual_role_commands(self):
        self.assertEqual(adapter.service_roster({'services':{'api':{'command':['node','entrypoint.js','api']},'api-4':{'command':['node','entrypoint.js','api']},'rt-special':{'command':['node','entrypoint.js','realtime']},'feed-reader':{'command':['node','entrypoint.js','feed-reader']}}}),['api','api-4','rt-special'])

if __name__=='__main__':unittest.main()
