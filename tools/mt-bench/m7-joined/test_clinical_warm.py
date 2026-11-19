"""Read-only synthetic controls for the warm-adjusted clinical observation."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import adapter
import clinical_warm as warm
import outcome_gate
from probe import generate
from test_preload_convergence import A, B, R, S, frame


def point(path, start, end, *, acquisitions, terminal=False, runtime=R, generation=1001):
    value = frame(code=None if acquisitions else 'EVALUATOR_STARTING',
                  acquisitions=acquisitions, runtime=runtime)
    for row in value['view']['tenants']:
        row['progress']['generation'] = generation
    warm.record(path, {'evaluator': json.dumps(value).encode()}, ['evaluator'], [A, B],
                start, end, terminal=terminal)


class ClinicalWarm(unittest.TestCase):
    def test_forward_progress_preserves_first_warm_and_rewinds_break_continuity(self):
        for generation, acquisitions in [(1001, 3), (1003, 1)]:
            with self.subTest(generation=generation, acquisitions=acquisitions), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / warm.FILE
                point(path, 0, 10, acquisitions=0)
                point(path, 20, 30, acquisitions=1)
                point(path, 40, 50, acquisitions=2, generation=1002)
                result = warm.coverage(path, [A, B])
                self.assertEqual(result['coverage']['WARM'], 2)
                self.assertEqual(result['byTenant'][A]['warmByMs'], 30)
                point(path, 60, 70, acquisitions=acquisitions, generation=generation)
                self.assertEqual(warm.coverage(path, [A, B])['coverage']['UNMEASURED'], 2)

    def test_never_warm_requires_terminal_owner_credit_and_stable_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / warm.FILE
            point(path, 0, 10, acquisitions=0)
            self.assertEqual(warm.coverage(path, [A, B])['coverage']['UNMEASURED'], 2)
            point(path, 130000, 130100, acquisitions=0, terminal=True)
            self.assertEqual(warm.coverage(path, [A, B])['coverage']['NEVER_WARM'], 2)
            point(path, 130500, 131000, acquisitions=1, terminal=True)
            result = warm.coverage(path, [A, B])
            self.assertEqual(result['byTenant'][A],
                             {'status':'WARM','warmAfterMs':130000,'warmByMs':131000})
            point(path, 140000, 140200, acquisitions=0, runtime=S, terminal=True)
            self.assertEqual(warm.coverage(path, [A, B])['coverage']['UNMEASURED'], 2)
            print('cold without terminal UNMEASURED; terminal zero FAIL; qualified warm PASS; reset UNMEASURED')

    def test_adjusted_deadline_on_generated_compose_and_kubernetes_probes(self):
        # Both generators, the real poller, acceptance clock and semantic
        # client proof run against offline clocked SQL and socket replies.
        code = r"""
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(process.argv[1],'utf8'),path=require('node:path');
const timing=require(path.join(path.dirname(process.argv[1]),'clinical-timing.cjs'));
const lag=require(path.join(path.dirname(process.argv[1]),'durable-lag.cjs'));
const client=require(path.join(path.dirname(process.argv[1]),'client-delivery.cjs'));
const begin=source.indexOf('  const poller = (async () => {'),end=source.indexOf('  const writers = [];',begin);
assert(begin>0 && end>begin);
assert(source.includes('e.acceptedHostMs=Number(process.hrtime.bigint())/1e6'));
assert(source.includes('e.clinicalTiming=timing.assess('));
assert(source.includes('lag.summary(evalPending,pending,oracleCost,clinicalWarm?timing:null)'));
assert.deepEqual(lag.summary([],new Map(),{},timing).drain,{
  clinicalDeadlineMs:120000,contract:timing.contract,finalSettlementDelayMs:10000,endMono:null
});
assert.equal(lag.summary([],new Map(),{}).drain.perWriteObservationBudgetMs,120000);
async function exercise(row,accept,frameAt,readyAt,available=true,tail=false) {
 const file=process.argv[1]+'.warm';fs.writeFileSync(file,JSON.stringify({contract:timing.contract,byTenant:{a:row}}));
 const clinicalWarm=timing.source(file),doc={_id:'x',date:1,sgv:101};
 const callback={socket:0,connects:1,transportId:'s',atMono:frameAt,sgv:{_id:'x',mills:1,mgdl:101}};
 let now=readyAt-500;
 const e={warmClinical:true,clientProofVersion:3,expectedSockets:[0],tenant:'a',date:1,sent:0,sentMono:0,
  acked:accept,acceptedMono:accept,acceptedHostMs:accept,stamp:null,evaluatedAt:null};
 let needSeen=false;
 if(tail) {
   clinicalWarm.inTail=()=>true;
   clinicalWarm.timeLeftMs=()=>readyAt+1000-now;
   clinicalWarm.needsObservation=()=>{needSeen=true;return true && clinicalWarm.timeLeftMs()>0;};
 }
 const ctx={signalDir:path.dirname(process.argv[1]),Date:{now:()=>now},performance:{now:()=>now},polling:!tail,evalPending:[e],evalLatencies:[],evalMissed:[],
  completionSource:{},args:{runid:'synthetic'},oracleCost:{queries:0,bytes:0,elapsedMs:0,missing:0,durablePendingPeak:0},
  Buffer,Map,Set,PER:1,tenants:[{id:'a'}],viewers:[1],pending:new Map([['a:1',{clientFrames:new Map([[0,callback]])}]]),
  psqlAsync:async()=>{now+=500;
    if(tail && now===readyAt) {
      row={coldThroughMs:readyAt-500,warmByMs:readyAt};
      fs.writeFileSync(file,JSON.stringify({contract:timing.contract,byTenant:{a:row}}));
    }
    return available?JSON.stringify({tenant:'a',stamp:'1'}):'';},
  completionOracle:{query:()=>'',assessDurable:()=>({ready:true,storedId:'x',storedSgv:101}),
   assess:(row,witness,clients,n)=>client.assess(clients,n,doc,witness)},
  lag,timing,clinicalWarm,sleep:async ms=>{ctx.polling=false;now+=ms;}};
 await vm.runInNewContext(source.slice(begin,end)+'\n poller',ctx);
 if(tail)assert(needSeen && e.evaluatedAt!==null);
 return timing.assess(e,[callback],row);
}
(async()=>{
 const pre={coldThroughMs:125000,warmByMs:135000};
 const ready={coldThroughMs:null,warmByMs:1000};
 let result=await exercise(ready,2000,124000,132000);
 assert.equal(result.verdict,'FAIL');assert.equal(result.code,'M7_COMPLETION_DEADLINE');
 result=await exercise(pre,2000,124000,132000);
 assert.equal(result.verdict,'PASS');assert(result.preWarmDeadlineMiss);
 assert.equal(result.acceptanceToCompletionMs,130000);assert.deepEqual(result.acceptanceToFrameMs,[122000]);
 assert.equal((await exercise(undefined,2000,124000,132000)).verdict,'UNMEASURED');
 assert.equal((await exercise({coldThroughMs:10000,warmByMs:200000},2000,124000,132000)).verdict,'UNMEASURED');
 assert.equal((await exercise(ready,2000,124000,132000,false)).verdict,'UNMEASURED');
 result=await exercise(ready,8000,7000,125000);assert.equal(result.verdict,'PASS');
 assert.deepEqual(result.acceptanceToFrameMs,[-1000]);
 result=await exercise({coldThroughMs:125000,warmByMs:null},2000,124000,132000,true,true);
 assert.equal(result.verdict,'PASS');assert(result.preWarmDeadlineMiss);
 console.log(JSON.stringify({coldAfterWriterStops:'PASS',postWarm:'FAIL',coldNominalMiss:'PASS',durableMs:130000,frameMs:122000,
    missingTelemetry:'UNMEASURED',transitionOverlap:'UNMEASURED',missingSQL:'UNMEASURED',frameBeforeAckMs:-1000}));
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'compose.cjs'
            generate(adapter.ROOT, target)
            script = """import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()/'tools/mt-bench/kubernetes'))
import kube_adapter
kube_adapter.generate_probe(Path(sys.argv[1]))
"""
            kubernetes = Path(tmp) / 'kubernetes.cjs'
            subprocess.run(['python3','-c',script,str(kubernetes)],cwd=adapter.ROOT,check=True)
            for path in (target, kubernetes):
                result = subprocess.run(['node','-e',code,str(path)],capture_output=True,text=True,timeout=8)
                self.assertEqual(result.returncode, 0, result.stderr)
                print(path.name, result.stdout.strip())

    def test_cold_tail_requests_real_controller_refresh_after_writer_join(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = directory / warm.FILE
            now = warm.now_ms()
            point(path, now-2, now-1, acquisitions=0)
            script = r"""
const path=require('node:path'),timing=require(process.argv[1]),dir=process.argv[2],tenant=process.argv[3];
const source=timing.source(path.join(dir,'clinical-warm.private.json'),dir);
const accepted=Number(process.hrtime.bigint())/1e6-125000;
const event={tenant,warmClinical:true,acceptedHostMs:accepted,acceptedMono:0,sentMono:-10,expectedSockets:[]};
const interval=setInterval(()=>{
 source.refresh();
 if(!source.inTail())return;
 const row=source.row(tenant);
 if(!Number.isFinite(row?.warmByMs)){
   if(!timing.shouldPoll(event,row,false,125000,source) || !source.needsObservation([event]))
     throw Error('cold witness dropped after ordinary writer joined');
   return;
 }
 clearInterval(interval);
 event.semantic={ready:true};event.durableObservation={upperMs:125020,storedSgv:101,storedId:'x'};
 const result=timing.assess(event,[],row);
 console.log(JSON.stringify({verdict:result.verdict,miss:result.preWarmDeadlineMiss}));
},10);
"""
            process = subprocess.Popen(['node','-e',script,str(adapter.HERE/'clinical-timing.cjs'),
                                        str(directory),A], stdout=subprocess.PIPE, text=True)
            calls = []
            def capture(index, remaining):
                calls.append(index)
                self.assertGreater(remaining,0)
                point(path,warm.now_ms(),warm.now_ms(),acquisitions=1)
                return {'queries':1}
            try:
                self.assertEqual(warm.wait_for_probe(process, 4, directory, capture), 0)
                result=json.loads(process.stdout.read())
                self.assertEqual(result, {'verdict':'PASS','miss':True})
                self.assertEqual(calls,[0])
                print('independent controller refresh after writer join:', result)
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=2)
                process.stdout.close()

    def test_legacy_packet_keeps_its_verdict(self):
        old = {'verdict':'FAIL', 'witnesses':[{'tenant':A,'ready':False}]}
        self.assertEqual(outcome_gate.sampled_oracle(old)['verdict'], 'FAIL')
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(outcome_gate.warm_component(Path(tmp), [A], {'completedOutput':old}))


if __name__ == '__main__':
    unittest.main()
