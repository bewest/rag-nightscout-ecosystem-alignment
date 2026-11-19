"""Normal native profile/transport paths retain generous authored inputs offline."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_adapter import fixture, k, iso
import test_toolchain
import test_matrix
import toolchain
import workload_runtime
import execute
from workloads import profile


class NumericContract(unittest.TestCase):
    def test_native_probe_budget_and_child_environment_are_bound(self):
        p=self.selected();w=p['workload'];w['probeEveryMs']=800
        with self.assertRaisesRegex(ValueError,'WORKLOAD_PROBE_LEDGER_WINDOW'):profile.validate(p)
        budget={'maxWrites':120000,'maxBytes':8388608};w['probeLedger']=budget
        self.assertEqual(profile.validate(p)['workload']['probeLedger'],budget)
        config={'workload':w,'driver':{'dependencies':'deps'},'completion':{}}
        with patch.dict(execute.os.environ,{'M7_PROBE_LEDGER':'ambient'}):
            self.assertEqual(json.loads(execute.environment(config,Path('/tmp'))['M7_PROBE_LEDGER']),budget)
            self.assertNotIn('M7_PROBE_LEDGER',execute.environment({**config,'workload':{}},Path('/tmp')))
        with self.assertRaisesRegex(ValueError,'WORKLOAD_PROBE_LEDGER_BUDGET'):
            profile.validate({**p,'workload':{**w,'probeLedger':None}})

    def selected(self):
        p=profile.read(profile.HERE/'small.json')
        p['population'].update(provisionedTenants=12001,ordinaryRosterTenants=12001,hotFactor=32)
        p['workload'].update(loadSeconds=90000,logicalPollingClients=80001,hotFactor=32,
                             jwtSetupConcurrency=128,probeEveryMs=300000)
        p['phases']['workSeconds']=92000
        return p

    def test_profile_describe_dry_and_compose_projection_keep_authored_values(self):
        p=self.selected();model=profile.describe(p)
        self.assertEqual(model['workload']['hotFactor'],32)
        with tempfile.TemporaryDirectory() as tmp:
            output=profile.dry(p,Path(tmp)/'dry')
            dry=json.loads(output.read_text())
            self.assertEqual((dry['environment']['HOT_FACTOR'],dry['profile']['workload']['jwtSetupConcurrency']),('32',128))
            self.assertEqual(len(json.loads((output.parent/'tenants.json').read_text())),12001)
            self.assertEqual(dry['runtime'],'NOT_RUN')
        m=test_toolchain.Toolchain().manifest();m['profile']=copy.deepcopy(p);m['profile'].pop('referencePins')
        selected=dict(coreCommit='1'*40,deployCommit='2'*40,localImageId='sha256:'+'6'*64,sourceAcceptance='PENDING')
        with patch.object(toolchain.frozen,'source',return_value=selected):
            local=toolchain.local(m,dict(prepare={}))
        self.assertEqual((local['prepare']['tenants'],local['prepare']['hot-factor'],
                          local['prepare']['jwt-setup-concurrency'],local['prepare']['load-seconds']),
                         (12001,32,128,90000))

    def test_normal_transport_roster_validation_keeps_exact_rendered_population(self):
        c,inv,render,_=fixture();c['tenants']=12001;c['workload']=self.selected()['workload']
        template=copy.deepcopy(render[1]['spec']['template'])
        bootstrap=copy.deepcopy(template['spec']['containers'][0]);bootstrap.update(name='bootstrap',env=[{'name':'NS_DEMO_TENANTS','value':'12001'}])
        template['spec']['initContainers']=[bootstrap]
        job={'kind':'Job','apiVersion':'batch/v1','metadata':copy.deepcopy(render[1]['metadata']),
             'spec':{'template':template}}
        job['metadata']['name']='provision';render.append(job)
        k.validate(c,inv,render)
        bootstrap['env'][0]['value']='10000'
        with self.assertRaisesRegex(k.Refused,'DIAGNOSTIC_TENANTS_CHANGED'):k.validate(c,inv,render)
        bootstrap['env'][0]['value']='12001';k.validate(c,inv,render)

    def test_environment_identity_and_ledger_budget_refuse_without_resizing(self):
        w=self.selected()['workload']
        for hot in (11,32):
            workload_runtime.validate({**w,'hotFactor':hot},k.need,12001)
        env=workload_runtime.environment(w,{},k.need)
        self.assertNotIn('JWT_SETUP_CONCURRENCY',env)
        self.assertNotIn('JWT_SETUP_CONCURRENCY',workload_runtime.environment(w,{'JWT_SETUP_CONCURRENCY':'1'},k.need))
        for field,bad,code in [('logicalPollingClients',True,'WORKLOAD_VIEWERS'),
            ('loadSeconds',float('inf'),'WORKLOAD_LOAD_SECONDS'),
            ('hotFactor',0,'WORKLOAD_HOT_FACTOR'),('jwtSetupConcurrency',True,'WORKLOAD_JWT_SETUP_CONCURRENCY'),
            ('probeEveryMs',1,'WORKLOAD_PROBE_LEDGER_WINDOW')]:
            with self.subTest(field=field),self.assertRaisesRegex(k.Refused,code):
                workload_runtime.validate({**w,field:bad},k.need,12001)

    def test_cleanup_profile_transport_and_released_allocation_accept_longer_window(self):
        p=self.selected();p['phases']['cleanupSeconds']=7200;profile.validate(p)
        c,inv,render,_=fixture()
        work=k.timestamp(c['deadlines']['workUntil']);c['deadlines']['cleanupUntil']=iso(work+7200)
        k.validate(c,inv,render)
        c['deadlines']['cleanupUntil']=iso(work+workload_runtime.workload_inputs.MAX_SECONDS+1)
        with self.assertRaisesRegex(k.Refused,'CLEANUP_WINDOW'):k.validate(c,inv,render)
        matrix=test_matrix.Matrix();matrix.setUp()
        try:
            matrix.a['cleanupUntil']=iso(k.timestamp(matrix.a['workUntil'])+7200);matrix.release()
            test_matrix.m.allocation(matrix.value,matrix.entries)
            matrix.a['cleanupUntil']=iso(k.timestamp(matrix.a['workUntil'])+workload_runtime.workload_inputs.MAX_SECONDS+1)
            matrix.release()
            with self.assertRaisesRegex(k.Refused,'MATRIX_ALLOCATION_DEADLINE'):
                test_matrix.m.allocation(matrix.value,matrix.entries)
        finally:matrix.doCleanups()

    def test_native_configured_partition_plan_is_exact(self):
        c,_,_,_=fixture();c['tenants']=12001;c['workload']=self.selected()['workload']
        c['workload'].update(driverShards=32,driverPlan={'version':1,'observer':'summary-v1',
            'scenarios':{name:{} for name in workload_runtime.SHAPES}})
        workload_runtime.validate(c['workload'],k.need,c['tenants'])
        import driver_accounting as driver
        plans=driver.expected_plans(workload_runtime.driver_manifest(c))
        self.assertEqual(len(plans),32);self.assertEqual(sum(p['tenants'] for p in plans),12001)
        self.assertTrue(all(p['driverHeadroom']==2 for p in plans))
        for bad in (0,True,12002):
            with self.assertRaisesRegex(k.Refused,'DRIVER_SHARDS'):
                workload_runtime.validate({**c['workload'],'driverShards':bad},k.need,c['tenants'])


if __name__=='__main__':unittest.main()
