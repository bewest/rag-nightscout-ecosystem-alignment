'use strict';
// Recording protocol/client budget only; not native PG or durable adapter proof.
const assert=require('node:assert/strict'),{AsyncResource}=require('node:async_hooks');
const root='<owned-review>/core-53a8/';
const create=require(root+'lib/tenant-lifecycle/operation-window').create;
let occupied=false,connects=0,maxOccupied=0;const waiting=[];
const fixture=require(root+'tests/fixtures/operation-window-runtime-protocol')({},options=>{
 const raw=options.pool.connect;
 options.pool.connect=async()=>{
  if(occupied)await new Promise(resolve=>waiting.push(resolve));else occupied=true;
  connects++;maxOccupied=Math.max(maxOccupied,occupied?1:0);const client=await raw();
  if(!client.wrapped){const release=client.release;client.release=(...args)=>{release(...args);const next=waiting.shift();if(next)next();else occupied=false;};client.wrapped=true;}
  return client;
 };
 return create(options);
});
const A='11111111-1111-4111-8111-111111111111';
(async()=>{
 await fixture.window.ready();let nested=false;const before=connects;
 await fixture.window.run(A,async()=>{await fixture.window.run(A,async()=>{assert(fixture.window.current(A));nested=true;});});
 assert(nested);assert.equal(connects-before,1);
 const background=new AsyncResource('OwnedEvaluatorReviewRevision');const jobs=[];let handoffs=0;
 const result=()=>({checkpoint:1,signature:{stamp:1,deleted:0},emitted:[],requested:[],properties:{},due:{dueAt:Infinity,reason:'none',slow:[]}});
 const runtime=await Promise.race([require(process.env.M7_EVALUATOR_RUNTIME_MODULE || root+'lib/server/serve/evaluator-runtime')({tenants:[A],readCurrent:async()=>({tenant:A,identity:'a'.repeat(64)}),create:async()=>({evaluate:async()=>result(),evaluateTime:async()=>result(),close(){}}),operationWindow:fixture.window,jobContext:require(root+'lib/server/serve/evaluator-job-context').create('clinical'),recoveryIntervalMs:10000,timeIntervalMs:10000,schedule:()=>({}),cancel(){},onRevision(){
  const job=background.runInAsyncScope(()=>fixture.window.run(A,async()=>{assert(fixture.window.current(A));handoffs++;}));jobs.push(job);return job;
 }}),new Promise((_,reject)=>setTimeout(()=>reject(Error('PARENT_CHILD_POOL_ONE_DEADLOCK')),500))]);
 await Promise.all(jobs);
 await Promise.race([fixture.window.run(A,async()=>{
  if(process.env.M7_COALESCED_MODE==='independent'){
    background.runInAsyncScope(()=>runtime.tick(A)).catch(()=>{});
    await Promise.resolve();
    await runtime.acquire(A);
  }else{await Promise.all([runtime.acquire(A),runtime.wake(A)]);}
 }),new Promise((_,reject)=>setTimeout(()=>reject(Error('COALESCED_ACTIVE_PARENT_POOL_ONE_DEADLOCK')),500))]);
 console.log('COALESCED_ACTIVE_PARENT_COMPLETED '+(process.env.M7_COALESCED_MODE||'inline'));
 await runtime.close();await fixture.window.close();background.emitDestroy();
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
