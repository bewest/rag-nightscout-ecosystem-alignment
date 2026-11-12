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
    def test_role_roster_is_derived_from_actual_role_commands(self):
        self.assertEqual(adapter.service_roster({'services':{'api':{'command':['node','entrypoint.js','api']},'api-4':{'command':['node','entrypoint.js','api']},'rt-special':{'command':['node','entrypoint.js','realtime']},'feed-reader':{'command':['node','entrypoint.js','feed-reader']}}}),['api','api-4','rt-special'])

if __name__=='__main__':unittest.main()
