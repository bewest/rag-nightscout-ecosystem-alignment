"""Configured clocks reach the real generators and remain below the outer cutoff."""
import contextlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import adapter as a
import discovery as d
import phase_windows as windows
from probe import generate as probe
from workload import generate as workload
import test_discovery as discovery_fixtures
from test_workload_init import JS as WORKLOAD_PORT


class PhaseWindows(unittest.TestCase):
    def test_clock_overrides_and_identity_refusals(self):
        m={'owner':'synthetic','cadence':{'setupSeconds':900,'drainSeconds':600}}
        value=windows.start(m,0,0)
        self.assertEqual(windows.remaining(value,'setup',400_000_000_000),500)
        value['drainStartedMonoNs']=500_000_000_000
        self.assertEqual(windows.drain_seconds(m,value,700_000_000_000),400)
        self.assertEqual(value['selectedClinicalDeadlineSeconds'],120)
        for bad in (0,-1,True,1.5,float('inf'),windows.MAX_SECONDS+1):
            with self.subTest(bad=bad),self.assertRaisesRegex(RuntimeError,'M7_PHASE_WINDOW_INVALID:setupSeconds'):
                windows.selection({'setupSeconds':bad})
        with self.assertRaisesRegex(RuntimeError,'WINDOW_EXHAUSTED:drain'):
            windows.drain_seconds(m,value,1_100_000_000_000)
        with self.assertRaisesRegex(RuntimeError,'DRAIN_IDENTITY'):
            windows.drain_seconds({**m,'owner':'foreign'},value,700_000_000_000)
        self.assertEqual(windows.drain_seconds({'cadence':{}},{},0),60)

    def test_generated_jwt_setup_override_default_and_break_restore(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'workload.js';workload(a.ROOT,file);source=file.read_text()
            script=WORKLOAD_PORT.replace("__ENV:{BASE_URL:","__ENV:{...(process.argv[3]===undefined?{}:{M7_SETUP_SECONDS:process.argv[3],M7_SETUP_UNTIL_MS:String(Date.now()+900000)}),BASE_URL:")
            def run(seconds=None):
                args=['node','-e',script,str(file),'0',*([str(seconds)] if seconds is not None else [])]
                return subprocess.run(args,capture_output=True,text=True,timeout=10)
            self.assertEqual(json.loads(run().stdout)['options']['setupTimeout'],'300s')
            def criterion():
                self.assertEqual(json.loads(run(900).stdout)['options']['setupTimeout'],'900s','AUTHORED_SETUP_NOT_APPLIED')
            criterion()
            file.write_text(source.replace("options.setupTimeout = seconds + 's';","options.setupTimeout = '300s';"))
            with self.assertRaisesRegex(AssertionError,'AUTHORED_SETUP_NOT_APPLIED'):criterion()
            file.write_text(source);criterion()
            for bad in ('0','-1','true','1.5','Infinity'):
                result=run(bad);self.assertNotEqual(result.returncode,0)
                self.assertIn('M7_PHASE_WINDOW_INVALID:setupSeconds',result.stderr)

    def test_generated_probe_setup_override_and_legacy_materializer_anchor(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'probe.js';probe(a.ROOT,file);source=file.read_text()
            self.assertEqual(source.count('Date.now() - t0 < 300000'),1)
            port=(a.HERE/'discovery-probe-control.cjs').read_text().split('(async()=>{\n  const source=')[0]
            port=port.replace("foreign=false}={}","foreign=false,setupSeconds}={}")
            port=port.replace("'--per','2'","...(setupSeconds===undefined?[]:['--setupSeconds',String(setupSeconds)]),'--per','2'")
            port += "\n(async()=>{const s=fs.readFileSync(process.argv[2],'utf8');console.log(JSON.stringify({old:(await run(s,{exchange:200})).out.prime,custom:(await run(s,{exchange:200,setupSeconds:900})).out.prime}));})().catch(e=>{console.error(e);process.exitCode=1});"
            def measure():
                result=subprocess.run(['node','-e',port,'unused',str(file)],cwd=a.HERE,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)
            def criterion():
                result=measure();self.assertGreaterEqual(result['custom']['ms'],899000,'AUTHORED_PROBE_SETUP_NOT_APPLIED')
                self.assertGreaterEqual(result['old']['ms'],300000);self.assertLess(result['old']['ms'],301000)
            criterion()
            predicate='(args.setupSeconds===undefined ? Date.now() - t0 < 300000 : performance.now()-setupStartedMono<setupSeconds*1000)'
            self.assertEqual(source.count(predicate),1)
            file.write_text(source.replace(predicate,'Date.now() - t0 < 300000'))
            with self.assertRaisesRegex(AssertionError,'AUTHORED_PROBE_SETUP_NOT_APPLIED'):criterion()
            file.write_text(source);criterion()

    def test_setup_cutoff_covers_driver_initialization_and_response_delay(self):
        port=r"""
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(process.argv[1],'utf8').replace(/^import .*;$/gm,'').replace(/export (const|function) /g,'$1 ');
function run(before,delay){
 let now=1000000,requests=0,timeout;
 class Clock extends Date{static now(){return now;}}
 const c={Date:Clock,__VU:0,__ENV:{BASE_URL:'http://synthetic.invalid',TENANTS_FILE:'unused',RUN_ID:'synthetic',
 RUN_START:'1800000000000',DURATION:'1',ACCEL:'1',HOT_FACTOR:'1',OFFERED_RPS:'1',SHAPES:'w_treatments_v3',M7_SETUP_SECONDS:'900',M7_SETUP_UNTIL_MS:'1900000'},
 console:{log(){}},sha256:()=>'',SharedArray:function(n,f){return f();},
 open:()=>JSON.stringify([{id:'a',host:'a.invalid',token:'synthetic'}]),
 exec:{scenario:{iterationInTest:0}},Counter:class{add(){}},http:{expectedStatuses:()=>null,
 get(url,params){requests++;timeout=params.timeout;now+=delay;return{status:200,body:'{"token":"synthetic"}'};}}};
 vm.createContext(c);vm.runInContext(source,c);now+=before;
 try{vm.runInContext('setup()',c);return{status:'PASS',requests,timeout};}
 catch(error){return{status:error.message,requests,timeout};}
}
console.log(JSON.stringify({lateInit:run(900001,0),lateResponse:run(890000,10001),within:run(600000,1)}));
"""
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'workload.js';workload(a.ROOT,file);source=file.read_text()
            def criterion():
                value=subprocess.run(['node','-e',port,str(file)],capture_output=True,text=True,timeout=5)
                self.assertEqual(value.returncode,0,value.stderr);x=json.loads(value.stdout)
                self.assertEqual(x['lateInit']['requests'],0)
                self.assertEqual(x['lateInit']['status'],'M7_PHASE_WINDOW_EXHAUSTED:setup')
                self.assertEqual(x['lateResponse']['timeout'],'10000ms')
                self.assertEqual(x['lateResponse']['status'],'M7_PHASE_WINDOW_EXHAUSTED:setup','LATE_JWT_SETUP_CREDITED')
                self.assertEqual(x['within']['status'],'PASS')
            criterion()
            file.write_text(source.replace('setupRemainingMs();',';'))
            with self.assertRaises(AssertionError):criterion()
            file.write_text(source);criterion()

    def launch_window(self,outer_seconds):
        fixture=discovery_fixtures.Discovery();self.addCleanup(fixture.doCleanups);folder,m=fixture.setup()
        m.update(project='owned',port=1234,restartRoles=['api'],generator={'tools':{'node':{'path':'node'}}})
        m['cadence'].update(setupSeconds=900,drainSeconds=600)
        a.write(folder/'tenants.private.json',[{'id':'a'},{'id':'b'}])
        now=[0];calls={};record=d.Record(a,folder,m)
        class Process:
            pid=12345;returncode=0
            def poll(self):return None
            def wait(self,timeout):calls.setdefault('waits',[]).append(timeout);return 0
        def popen(argv,**kwargs):
            calls['probe']=argv;(folder/'load/.window').touch();now[0]=150_000_000_000;return Process()
        def command(argv,**kwargs):
            calls['k6']=argv;calls['timeout']=kwargs['timeout']
            a.write(folder/'load/k6-summary.json',{'metrics':{}});now[0]=200_000_000_000
        @contextlib.contextmanager
        def ctx(*args):yield
        with contextlib.ExitStack() as stack:
            for name in ('psql','job_record','stop_job','quiet','assert_owned','phase_snapshot'):
                stack.enter_context(patch.object(a,name))
            for name in ('sampling','loadgen_process','observe_progress'):
                stack.enter_context(patch.object(a,name,ctx))
            stack.enter_context(patch.object(a,'progress_services',return_value=['evaluator']))
            stack.enter_context(patch.object(a,'progress_attribution',return_value={}))
            stack.enter_context(patch.object(a.subprocess,'Popen',side_effect=popen))
            stack.enter_context(patch.object(a,'command',side_effect=command))
            stack.enter_context(patch.object(a,'stored',return_value={}))
            stack.enter_context(patch.object(d.time,'monotonic_ns',side_effect=lambda:now[0]))
            with a.command_deadline(a.time.time()+outer_seconds):d.discovery_load(a,folder,m,'k6',record)
        return calls,m,a.document(folder/'load/phase-windows.json')

    def test_real_discovery_launch_shares_setup_and_post_writer_drain_clocks(self):
        calls,m,captured=self.launch_window(2000)
        self.assertEqual(calls['probe'][calls['probe'].index('--setupSeconds')+1],'900')
        self.assertIn('M7_SETUP_SECONDS=750',calls['k6'])
        self.assertAlmostEqual(calls['timeout'],1085,delta=.1)
        self.assertEqual(calls['waits'][0],600)
        self.assertEqual(windows.drain_seconds(m,captured,350_000_000_000),450)
        bounded,_,_=self.launch_window(3)
        self.assertLessEqual(bounded['timeout'],3)
        self.assertLessEqual(bounded['waits'][0],3)
        setup=int(next(x.split('=')[1] for x in bounded['k6'] if x.startswith('M7_SETUP_SECONDS=')))
        self.assertGreaterEqual(setup,1);self.assertLessEqual(setup,3)

    def test_observer_budgets_follow_window_and_population_and_can_be_overridden(self):
        defaults={'version':1,'maxRounds':16,'maxQueries':1024,'maxBytes':67108864,'roundSeconds':20}
        policy,interval=windows.observation_policy({'drainSeconds':600},600,238,100000000,defaults)
        self.assertGreater(policy['maxRounds'],16)
        self.assertGreaterEqual(policy['maxQueries'],policy['maxRounds']*238)
        self.assertGreaterEqual(policy['maxBytes'],policy['maxRounds']*100000000)
        self.assertEqual(interval,5)
        chosen={'maxRounds':1000,'maxQueries':50000,'maxBytes':20000000000,'roundSeconds':60,'intervalSeconds':30}
        override,interval=windows.observation_policy({'drainSeconds':600,'drainObservation':chosen},600,238,100000000,defaults)
        self.assertEqual({k:override[k] for k in chosen if k!='intervalSeconds'}, {k:v for k,v in chosen.items() if k!='intervalSeconds'})
        self.assertEqual(interval,30)
        for value in ({'unknown':1},{'maxQueries':0},{'maxRounds':True},{'intervalSeconds':float('inf')}):
            with self.assertRaisesRegex(RuntimeError,'M7_DRAIN_OBSERVER_'):windows.observation_override(value)
        cadence={'drainObservation':{'sqlMaxBytes':64*1024*1024,'roundSeconds':90}}
        policy,_=windows.observation_policy(cadence,120,80,100000000,defaults)
        self.assertNotIn('sqlMaxBytes',policy)
        self.assertEqual(policy['roundSeconds'],90)
        self.assertEqual(windows.observation_sql_bytes(cadence,1),64*1024*1024)


if __name__=='__main__':unittest.main()
