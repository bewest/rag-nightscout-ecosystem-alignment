"""Strict deadline controls run the actual generated completion poller; no app actors."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import adapter as a
from probe import generate

PORT = r"""
const vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(process.argv[1],'utf8');
const start=source.indexOf('  const poller = (async () => {');
const end=source.indexOf('  const writers = [];',start);
if(start<0||end<0)throw Error('GENERATED_POLLER_ANCHOR');
async function run(startMs,queryMs,ready){
 let now=startMs;const e={tenant:'synthetic',date:1,sent:0,sentMono:0,acked:1,stamp:null,evaluatedAt:null};
 const context={Date:{now:()=>now},performance:{now:()=>now},polling:false,evalPending:[e],evalLatencies:[],evalMissed:[],completionSource:{},args:{runid:'synthetic'},
 oracleCost:{queries:0,bytes:0,elapsedMs:0,missing:0,durablePendingPeak:0},Buffer,Map,Set,PER:1,tenants:[{id:'synthetic'}],viewers:[1],pending:new Map(),
 psqlAsync:async()=>{now+=queryMs;return JSON.stringify({tenant:'synthetic',stamp:'1'});},
 completionOracle:{query:()=>'',assessDurable:()=>({ready:true}),assess:()=>({ready,code:ready?'READY':'M7_COMPLETION_CLIENT'})},
 lag:{observe(){}},sleep:async(ms)=>{now+=ms;}};
 const result=vm.runInNewContext(source.slice(start,end)+'\n poller.then(()=>({evaluatedAt:evalPending[0].evaluatedAt,completion:evalPending[0].completion,missed:evalMissed.length,queries:oracleCost.queries,latencies:evalLatencies}));',context,{timeout:1000});
 return await result;
}
(async()=>console.log(JSON.stringify({within:await run(117000,1000,true),late:await run(119000,2000,true),exactBoundary:await run(119000,1000,true),missing:await run(118000,1000,false),atDeadline:await run(120000,0,true)})))().catch(e=>{console.error(e);process.exitCode=1;});
"""

class CompletionDeadline(unittest.TestCase):
 def test_actual_generated_poller_strict_120_seconds(self):
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/'probe.js';generate(a.ROOT,target)
   proc=subprocess.run(['node','-e',PORT,str(target)],capture_output=True,text=True,timeout=5)
   self.assertEqual(proc.returncode,0,proc.stderr)
   cases=json.loads(proc.stdout)
   self.assertEqual(cases['within']['evaluatedAt'],118000)
   self.assertEqual(cases['within']['missed'],0)
   self.assertIsNone(cases['late']['evaluatedAt'],'late SQL completion credited past strict120s')
   self.assertFalse(cases['late']['completion']['ready'])
   self.assertEqual(cases['late']['completion']['code'],'M7_COMPLETION_DEADLINE')
   self.assertEqual(cases['late']['missed'],1)
   self.assertIsNone(cases['exactBoundary']['evaluatedAt'])
   self.assertEqual(cases['exactBoundary']['completion']['code'],'M7_COMPLETION_DEADLINE')
   self.assertIsNone(cases['missing']['evaluatedAt'])
   self.assertEqual(cases['missing']['missed'],1)
   self.assertEqual(cases['atDeadline']['queries'],0)
   self.assertEqual(cases['atDeadline']['missed'],1)

if __name__=='__main__':unittest.main()
