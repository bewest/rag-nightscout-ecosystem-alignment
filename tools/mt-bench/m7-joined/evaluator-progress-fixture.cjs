'use strict';
// Actual product window/runtime/inspection with a recording SQL protocol port.
// Synthetic only; neither native PostgreSQL nor clinical-output proof.
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs'),vm=require('node:vm');
const root=process.env.M7_PROGRESS_CORE;if(!root)throw Error('M7_PROGRESS_CORE_REQUIRED');
const A='11111111-1111-4111-8111-111111111111';
(async()=>{
 const f=require(path.join(root,'tests/fixtures/operation-window-runtime-protocol'))();
 const jobs=require(path.join(root,'lib/server/serve/evaluator-job-context')).create('clinical');
 const timers=[];let componentCalls=0;
 const env=require(path.join(root,'lib/server/tenant-app/environment'))({settings:{enable:['pump']},extendedSettings:{pump:{warnClock:1/7}}});
 const result=()=>{const at=Date.now(),due=require(path.join(root,'lib/data/evaluator-due')).nextDue({env,ddata:{devicestatus:[{mills:at,pump:{clock:new Date(at).toISOString()}}]},result:{requested:[]},at});assert(Number.isFinite(due.dueAt)&&!Number.isInteger(due.dueAt));return{checkpoint:1,signature:{stamp:1,deleted:0},emitted:[],requested:[],properties:{},due};};
 const runtime=await require(path.join(root,'lib/server/serve/evaluator-runtime'))({tenants:[A],operationWindow:f.window,jobContext:jobs,readCurrent:async()=>({tenant:A,identity:'a'.repeat(64)}),create:async()=>({evaluate:async()=>{componentCalls++;return result();},evaluateTime:async()=>{componentCalls++;return result();},close(){}}),recoveryIntervalMs:10000,timeIntervalMs:10000,schedule:()=>({}),cancel(){},setTimer:fn=>{const timer={fn};timers.push(timer);return timer;},clearTimer(){}});
 const inspect=require(path.join(root,'lib/server/serve/evaluator-inspection'))({tenants:new Map([[A,{}]]),runtime,gate:{inspect:async()=>({configured:{ordinal:0,mode:'standalone'},gate:{eligible:true,reason:null},owner:()=>0,admits:()=>true})},startup:{health(){throw Error('UNBOUNDED_STARTUP_READ');}}});
 try{
  await runtime.acquire(A);
  const frames=[];
  for(let step=0;step<3;step++){
   if(step && process.env.M7_PROGRESS_STOPPED!=='1'){
    const before=runtime.health([A]).tenants[0].progress.completedTimeCycles;timers.at(-1).fn();
    for(let n=0;n<100&&runtime.health([A]).tenants[0].progress.completedTimeCycles===before;n++)await new Promise(r=>setTimeout(r,1));
    assert(runtime.health([A]).tenants[0].progress.completedTimeCycles>before);
   }
   const before={calls:componentCalls,sql:f.log.length};let view;
   for(let n=0;n<100;n++)view=await inspect({tenants:[A]});
   assert.deepEqual({calls:componentCalls,sql:f.log.length},before,'INSPECTION_CHANGED_WORK');
   const lines=[];
   const helper=fs.readFileSync(path.join(__dirname,'evaluator-progress.cjs'),'utf8');
   const execute=vm.runInNewContext('const M7_PROGRESS_IDS='+JSON.stringify([A])+';const M7_PROGRESS_QUERY_BUDGET=1;const M7_PROGRESS_BYTE_BUDGET=1048576;\n'+helper,{
    Date,Buffer,Error,Promise,setTimeout,clearTimeout,
    process:{stdout:{write:line=>{lines.push(line);return true;}},stderr:{write:line=>{throw Error(line);}},exit:()=>{throw Error('HELPER_EXIT');}},
    require:name=>{
     if(name==='./deploy/multitenant/load-env')return {};
     if(name==='./lib/server/serve/evaluator-config')return{partitionFor:()=>({partitioned:false})};
     if(name==='./lib/server/internal-api/listener-config')return{resolve:()=>({peer:(_name,limits)=>{assert.equal(limits.maxBytes,1048576);return limits;}})};
     if(name==='./lib/server/internal-api/clients')return{evaluatorInspection:()=>({inspectEvaluator:inspect})};
     throw Error('UNEXPECTED_HELPER_REQUIRE');
    }
   });
   await execute;assert.equal(lines.length,1);frames.push(JSON.parse(lines[0]));
  }
  process.stdout.write(frames.map(v=>JSON.stringify(v)).join('\n')+'\n');
 }finally{await runtime.close();await f.window.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
