"""Exact discovery inputs through the existing CLI, generators and readers.

These are offline plans and synthetic ports, never source/capacity acceptance.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import adapter as a
import contract
import driver_accounting as driver
import driver_shards
import evaluator_progress as progress
import run_configuration as configuration
import viewer_plan
import workload
import workload_inputs as inputs
import discovery_counts
from probe import generate as probe
from test_run_configuration import config


class NumericContract(unittest.TestCase):
    def test_authored_probe_ledger_survives_receipt_actor_and_reader(self):
        config_ = self.selected()
        config_['prepare']['probe-every-ms']=800
        selected={'maxWrites':120000,'maxBytes':8*1024*1024}
        with patch.object(a,'instrument',return_value={'sha256':'d'*64}):
            with self.assertRaisesRegex(RuntimeError,'M7_PROBE_LEDGER_WINDOW'):configuration.resolve(config_)
            config_['prepare']['probe-ledger']=json.dumps(selected)
            result=configuration.resolve(config_)
        cadence=result['configuration']['cadence']
        self.assertEqual(cadence['probeLedger'],selected)
        config_bound=result['configuration']
        manifest={**config_bound,'instrument':{'sha256':'d'*64},'runConfiguration':config_bound}
        proof=result['diagnosticReceiptTemplate']
        contract.discovery_authorization(manifest,proof)
        with self.assertRaisesRegex(RuntimeError,'WORKLOAD_BUDGET_BOUND_RECEIPT_REQUIRED'):
            contract.discovery_authorization(manifest,{'version':1})
        # Without the budget a version-1 receipt still cannot authorize a writer-driven run.
        omitted={**manifest,'cadence':{k:v for k,v in cadence.items() if k!='probeLedger'}}
        with self.assertRaisesRegex(RuntimeError,'WRITER_CONFIGURATION_REQUIRED'):
            contract.discovery_authorization(omitted,{'version':1})
        changed={**manifest,'cadence':{**cadence,'probeLedger':{**selected,'maxWrites':120001}}}
        with self.assertRaisesRegex(RuntimeError,'DIAGNOSTIC_CONFIGURATION_MISMATCH'):
            contract.discovery_authorization(changed,proof)
        env=inputs.probe_ledger_env(cadence)
        script="""const opts={ids:['tenant-a'],runId:'synthetic',persist(){}};
const create=require('./probe-accounting.cjs').create;
function load(ledger){for(let n=0;n<100001;n++)ledger.settle(ledger.begin('tenant-a'),200);}
try{load(create(opts));throw Error('MISSING_CONTROL');}catch(error){if(error.message!=='M7_PROBE_LEDGER_WRITE_BUDGET')throw error;}
const ledger=create({...opts,budget:JSON.parse(process.env.M7_PROBE_LEDGER)});
load(ledger); ledger.close(); console.log(JSON.stringify(ledger.snapshot()));
"""
        raw=subprocess.check_output(['node','-e',script],cwd=a.HERE,env={**os.environ,**env},timeout=12)
        with tempfile.TemporaryDirectory() as directory:
            area=Path(directory)
            path=area/'probe-accounting.json'
            path.write_bytes(raw)
            args=(a,area,'synthetic',{'tenant-a'})
            for wrong in (None,{**selected,'maxBytes':32},{**selected,'maxWrites':100001}):
                with self.assertRaisesRegex(RuntimeError,'M7_PROBE_COUNTS_METADATA'):
                    discovery_counts.probe_metadata(*args,probe_ledger=wrong)
            ledger,_=discovery_counts.probe_metadata(*args,probe_ledger=selected)
            self.assertEqual(ledger['attempts'],100001)
            self.assertEqual(ledger['byTenant']['tenant-a']['accepted'],100001)
            self.assertTrue(ledger['admissionsClosed'])

    def test_startup_and_progress_windows_are_authored_facts(self):
        value=self.selected(); windows={'composeReadySeconds':2400,'stageSeconds':3600,'evaluatorReadySeconds':2700}
        budget={'maxQueriesPerPhase':2048,'maxBytesPerPhase':134217728}
        value['prepare'].update({'startup-windows':json.dumps(windows),'evaluator-progress-budget':json.dumps(budget)})
        with patch.object(a,'instrument',return_value={'sha256':'d'*64}):
            resolved=configuration.resolve(value)
        self.assertEqual(resolved['startupWindows']['composeReadySeconds'],{'seconds':2400,'origin':'authored'})
        self.assertEqual(resolved['configuration']['cadence']['evaluatorProgressBudget'],budget)
        for field in ('startupWindows','evaluatorProgressBudget'):
            with self.assertRaisesRegex(RuntimeError,'WORKLOAD_BUDGET_BOUND_RECEIPT_REQUIRED'):
                contract.discovery_authorization({'cadence':{field:resolved['configuration']['cadence'][field]}},{'version':1})
        plan=a.deployment_plan({'services':{}},pgstream=True,compose_ready_seconds=2400)
        for _,_,options in plan:
            if '--wait-timeout' in options:
                self.assertEqual(options[options.index('--wait-timeout')+1],'2400')

    def selected(self):
        value = config()
        value.update(tier='discovery', workSeconds=92000)
        value['prepare'].update({'tenants':12001, 'logical-polling-clients':80001,
            'load-seconds':90000, 'hot-factor':32, 'jwt-setup-concurrency':128,
            'setup-seconds':1000, 'drain-seconds':120, 'warmup-seconds':1,
            'idle-seconds':1, 'probe-every-ms':300000})
        return value

    def test_normal_cli_receipt_projection_preserves_inputs_and_actual_budgets(self):
        value = self.selected()
        with patch.object(a,'instrument',return_value={'sha256':'d'*64}):
            resolved = configuration.resolve(value)
            r = resolved['configuration']; receipt = resolved['diagnosticReceiptTemplate']
            self.assertEqual((r['tenants'], r['jwtSetupConcurrency']), (12001,128))
            self.assertEqual({k:r['cadence'][k] for k in ('loadSeconds','hotFactor','logicalPollingClients')},
                dict(loadSeconds=90000,hotFactor=32,logicalPollingClients=80001))
            self.assertEqual(resolved['workSeconds'],92000)
            manifest={**r,'instrument':{'sha256':'d'*64},'runConfiguration':r}
            receipt['status']='AUTHORIZED_DIAGNOSTIC'
            contract.receipt_scope(manifest,receipt,'run')
            broken=copy.deepcopy(receipt);broken['limits']['tenants']-=1
            with self.assertRaisesRegex(RuntimeError,'M7_DIAGNOSTIC_LIMIT_INVALID'):
                contract.receipt_scope(manifest,broken,'run')
            broken=copy.deepcopy(receipt);broken['imageId']='sha256:'+'0'*64
            with self.assertRaisesRegex(RuntimeError,'M7_DIAGNOSTIC_IDENTITY_MISMATCH'):
                contract.receipt_scope(manifest,broken,'run')
            value['workSeconds']=90000
            with self.assertRaisesRegex(RuntimeError,'M7_RUNNER_WORK_WINDOW'):
                configuration.resolve(value)

    def test_invalid_numbers_and_real_array_duration_boundaries_still_refuse(self):
        for bad in (True,False,0,-1,1.5,float('nan'),float('inf'),2**32):
            self.assertFalse(inputs.tenants(bad),repr(bad))
        for bad in (True,False,-1,1.5,float('nan'),float('inf'),2**32):
            self.assertFalse(inputs.polling_clients(bad),repr(bad))
        for bad in (True,False,0,-1,1.5,float('nan'),float('inf'),inputs.MAX_SECONDS+1):
            self.assertFalse(inputs.seconds(bad),repr(bad))
        for bad in (True,False,0,-1,1.5,float('nan'),float('inf'),2**53):
            with self.assertRaisesRegex(RuntimeError,'JWT_SETUP_CONCURRENCY_INVALID'):
                a.jwt_setup_concurrency(bad,discovery=True)
        self.assertTrue(inputs.population_fits(12001,32))
        self.assertFalse(inputs.population_fits(2**32-1,2))
        self.assertFalse(inputs.probe_fits_ledger(1,90000))
        with self.assertRaisesRegex(RuntimeError,'JWT_SETUP_CONCURRENCY_INVALID'):
            a.jwt_setup_concurrency(128)

    def test_larger_viewer_bindings_and_progress_roster_are_read_exactly(self):
        manifest={'tenants':2,'cadence':{'logicalPollingClients':80001}}
        roster=[{'id':'a'},{'id':'b'}]
        self.assertEqual(viewer_plan.counts(manifest,roster),{'a':40001,'b':40000})
        bindings=[{'socket':i,'tenant':'a' if i<40001 else 'b'} for i in range(80001)]
        p={'viewerBindings':bindings,'prime':{'sockets':80001,'primed':80001},
           'window':{'sockets':80001,'connectedAtEnd':80001,'writes':{'failed':0,'ok':2},
                     'expectedFrames':80001,'deliveredFrames':80001}}
        self.assertEqual(viewer_plan.check(manifest,roster,p,{'a':1,'b':1})['verdict'],'PASS')
        p['viewerBindings'][-1]['tenant']='foreign'
        with self.assertRaisesRegex(RuntimeError,'M7_VIEWER_BINDINGS'):
            viewer_plan.check(manifest,roster,p,{'a':1,'b':1})
        ids=[f'00000000-0000-4000-8000-{i:012x}' for i in range(12001)]
        progress.validate_ids(ids)
        with self.assertRaisesRegex(progress.Refused,'M7_EVALUATOR_PROGRESS_QUERY_BOUND'):
            progress._round_view(['a','b','c','d'],ids,lambda *args:self.fail('before fetch'))

    def test_configured_capture_overrides_and_large_window(self):
        cfg={'version':1,'observer':'scheduling-v1',
             'maxTraceBytes':1024**3,'maxTraceRows':6000000,'scenarios':{'r_sgv':{}}}
        m={'tenants':12001,'cadence':{'loadSeconds':90000,'hotFactor':32,
                                   'offeredRps':20,'driverPlan':cfg}}
        plan=driver.expected_plans(m)[0]
        self.assertEqual(plan['population'],12001)
        self.assertEqual(plan['scenarios']['r_sgv']['durationSeconds'],90000)

    def test_real_workload_large_roster_hot_weight_and_duration(self):
        script=r'''
const fs=require('fs'),vm=require('vm');const [file]=process.argv.slice(1);
const c={__ENV:{HOT_FACTOR:'32',ACCEL:'1',DURATION:'90000',SHAPES:'w_treatments_v3',OFFERED_RPS:'20'},console:{log(){}},Counter:class{add(){}},
 SharedArray:function(_,fn){return fn()},open:()=>JSON.stringify(Array.from({length:129},(_,i)=>({id:i,token:'synthetic',host:'synthetic.invalid',jwt:'synthetic-jwt'})))};
const s=fs.readFileSync(file,'utf8').replace(/^import .*;$/gm,'').replace(/^export /gm,'');
console.log(JSON.stringify(vm.runInNewContext(s+'\n({setup:setup(),weight,options});',c)));
'''
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'workload.js';workload.generate(a.ROOT,file)
            value=json.loads(subprocess.run(['node','-e',script,str(file)],capture_output=True,text=True,check=True).stdout)
            self.assertEqual((value.get('setup'),value['weight']),(None,160))
            self.assertEqual(value['options']['scenarios']['w_treatments_v3']['duration'],'90000s')

    def test_generated_probe_and_accounting_accept_larger_declarations(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'probe.js';probe(a.ROOT,file)
            port=(a.HERE/'discovery-probe-control.cjs').read_text().split('(async()=>{\n  const source=')[0]
            port=port.replace('foreign=false}={}','foreign=false,clients}={}')
            port=port.replace("'--per','2'","...(clients===undefined?[]:['--clients',String(clients)]),'--per','2'")
            port+="\n(async()=>{const s=fs.readFileSync(process.argv[2],'utf8');const v=await run(s,{clients:80001});assert.equal(v.code,0);assert(!v.out.hardFailure);await assert.rejects(run(s,{clients:4294967296}),/M7_VIEWER_TOTAL_RANGE/);console.log('LARGE_VIEWERS_EXACT_NO_ACTORS');})().catch(e=>{console.error(e);process.exitCode=1});"
            result=subprocess.run(['node','-e',port,'unused',str(file)],cwd=a.HERE,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            code="const a=require('./probe-accounting.cjs');const ids=Array.from({length:12001},(_,i)=>'tenant-'+i);const l=a.create({ids,runId:'synthetic',persist(){}});const n=l.begin(ids.at(-1));l.settle(n,200);l.close();if(l.snapshot().attempts!==1)throw Error('COUNT');"
            subprocess.run(['node','-e',code],cwd=a.HERE,check=True)

    def test_cleanup_socket_and_partition_overrides_follow_normal_cli(self):
        value=self.selected();value['cleanupSeconds']=7200
        value['prepare'].update({'tenants':1000,'sockets-per-tenant':16,'driver-shards':32,
            'driver-plan':json.dumps({'version':1,'observer':'summary-v1',
                'scenarios':{name:{} for name in driver.SHAPES}})})
        del value['prepare']['logical-polling-clients']
        with patch.object(a,'instrument',return_value={'sha256':'d'*64}):
            r=configuration.resolve(value)
            self.assertEqual(r['cleanupSeconds'],7200)
            selected=r['configuration'];self.assertEqual(viewer_plan.total(selected),16000)
            plans=driver.expected_plans(selected);self.assertEqual(len(plans),32)
            self.assertEqual(sum(p['tenants'] for p in plans),1000)
            receipt=r['diagnosticReceiptTemplate'];receipt['status']='AUTHORIZED_DIAGNOSTIC'
            manifest={**selected,'instrument':{'sha256':'d'*64},'runConfiguration':selected}
            contract.receipt_scope(manifest,receipt,'run')
            rows=driver_shards.plan(1000,32,20,32)
            self.assertAlmostEqual(sum(row['offeredRps'] for row in rows),20)
            script=driver_shards.script(rows,dict(environment=[driver.configured_environment(selected,i)
                for i in range(32)],observer='summary-v1'))
            self.assertEqual(script.count('k6 run --quiet'),32)
            subprocess.run(['sh','-n','-c',script],check=True)
            for key,bad in [('driver-shards',1001),('sockets-per-tenant',2**32)]:
                broken=copy.deepcopy(value);broken['prepare'][key]=bad
                with self.assertRaises(RuntimeError):configuration.resolve(broken)
            for bad in (29,True,float('inf'),inputs.MAX_SECONDS+1):
                broken=copy.deepcopy(value);broken['cleanupSeconds']=bad
                with self.assertRaisesRegex(RuntimeError,'M7_RUNNER_FINITE_LIMIT'):configuration.resolve(broken)

    def test_implicit_viewer_total_cannot_overflow_and_acceptance_ranges_stay_exact(self):
        value=self.selected();value['prepare']['sockets-per-tenant']=2**32-1
        del value['prepare']['logical-polling-clients']
        with patch.object(a,'instrument',return_value={'sha256':'d'*64}):
            with self.assertRaisesRegex(RuntimeError,'M7_VIEWER_TOTAL_RANGE'):configuration.resolve(value)
        args=a.parser().parse_args(['prepare','--directory','/tmp/synthetic','--core-repo','/tmp/core',
            '--core-commit','a'*40,'--deploy-repo','/tmp/deploy','--deploy-commit','b'*40,
            '--image','synthetic','--freeze','/tmp/synthetic','--profile','pgstream-sample',
            '--run-purpose','acceptance','--tenants','1000','--replicas','1','--sockets-per-tenant','16'])
        with self.assertRaisesRegex(RuntimeError,'M7_SAMPLE_KNOB_RANGE:socketsPerTenant'):a.cadence_options(args)
        args.sockets_per_tenant=2;args.driver_shards=32
        with self.assertRaisesRegex(RuntimeError,'M7_SAMPLE_KNOB_RANGE:driverShards'):a.cadence_options(args)


if __name__=='__main__':unittest.main()
