from pathlib import Path
import subprocess
import tempfile
import unittest
import adapter as a
from probe import generate
class DurableProbe(unittest.TestCase):
 def test_actual_generated_poller_splits_durable_and_client(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'probe.js';generate(a.ROOT,p);s=p.read_text()
   self.assertIn('date, sentMono:p.sentMono, tenant: t.id',s)
   block=s[s.index('        const ids=[...new Set(open.map'):s.index('      }else if (open.length) {')]
   script="""const vm=require('node:vm'),assert=require('node:assert/strict');const lag=require(process.argv[1]);const e={tenant:'a',date:1,acked:1,stamp:null,sentMono:10,evaluatedAt:null};let at=20;const ctx={performance:{now:()=>at+=10},open:[e],psqlAsync:async()=>JSON.stringify({tenant:'a',stamp:'1'}),completionOracle:{query:()=>'',assessDurable:()=>({ready:true,storedId:'id'}),assess:()=>({ready:false,code:'M7_COMPLETION_CLIENT'})},completionSource:{},args:{runid:'run'},oracleCost:{queries:0,bytes:0,elapsedMs:0,missing:0,durablePendingPeak:0},pending:new Map(),viewers:[2],tenants:[{id:"a"}],PER:2,lag,Buffer,Date,evalLatencies:[]};(async()=>{await vm.runInNewContext('(async()=>{'+process.argv[2]+'})()',ctx);assert(e.durableObservation);assert.equal(e.evaluatedAt,null);assert.equal(ctx.oracleCost.queries,1);assert.equal(e.durableObservation.upperMs,30);console.log('durable before client PASS');})().catch(e=>{console.error(e);process.exit(1)});"""
   r=subprocess.run(['node','-e',script,str(p.with_name('durable-lag.cjs')),block],capture_output=True,text=True,timeout=5)
   self.assertEqual(r.returncode,0,r.stderr)
   subprocess.run(['node','--check',str(p)],check=True,capture_output=True)
 def test_actual_generated_hook_keeps_first_frame_and_requires_exact_id(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'probe.js';generate(a.ROOT,p)
   hook=next(line for line in p.read_text().splitlines() if 'proof.clientFrames' in line)
   script="""const vm=require('node:vm'),assert=require('node:assert/strict'),lag=require(process.argv[1]);
const socket={},proof={seen:new Set(),latencies:[],sent:0},pending=new Map([['a:1',proof]]);let now=20;
const context={clinicalTimeline:null,pending,t:{id:'a'},s:socket,sockets:[socket],completionSource:{},performance:{now:()=>now},frame:{sgvs:[{_id:'stored',mills:1,mgdl:123}]},at:0};socket.connects=1;
vm.runInNewContext(process.argv[2],context);now=70;vm.runInNewContext(process.argv[2],context);
assert.equal(proof.clientFrames.get(socket).atMono,20,'later broadcast overwrote first observation');
context.frame={sgvs:[{_id:'wrong',mills:1,mgdl:999}]};now=90;vm.runInNewContext(process.argv[2],context);
const witness={tenant:'a',date:1,sentMono:10,acked:1,durableObservation:{storedId:'stored'}};
let result=lag.summary([witness],pending,{});assert.equal(result.matchedClientMs.n,1);assert.equal(result.matchedClientMs.max,10);assert.equal(proof.clientFrames.get(socket).connects,1);assert.equal(proof.clientFrames.get(socket).sgv.mgdl,123);
proof.clientFrames=new Map();proof.seen=new Set();vm.runInNewContext(process.argv[2],context);
result=lag.summary([witness],pending,{});assert.equal(result.matchedClientMs.n,0,'wrong identity satisfied delivery join');
console.log('first frame and exact identity PASS');"""
   r=subprocess.run(['node','-e',script,str(p.with_name('durable-lag.cjs')),hook],capture_output=True,text=True,timeout=5)
   self.assertEqual(r.returncode,0,r.stderr)
if __name__=='__main__':unittest.main()
