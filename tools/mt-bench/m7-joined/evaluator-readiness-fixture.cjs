'use strict';
const assert=require('node:assert/strict');
const path=require('node:path');const fs=require('node:fs');
const core=process.env.M7_PROGRESS_CORE;
assert(core&&fs.realpathSync(core)===core,'owned exact source path required');
const git=require('node:child_process').execFileSync;
assert.equal(git('git',['-C',core,'rev-parse','HEAD'],{encoding:'utf8'}).trim(),'9db0ce94f072c8f34aab889f0181afa4269a6758');
assert.equal(git('git',['-C',core,'diff','HEAD','--name-only'],{encoding:'utf8'}).trim(),'');
const load=p=>require(path.join(core,p));
const A='11111111-1111-4111-8111-111111111111';
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return{resolve,promise};};
const held=deferred(),entered=deferred();
const fixture=load('tests/fixtures/operation-window-runtime-protocol');
const f=fixture({},config=>{
 const original=config.pool.connect;
 config.pool.connect=async()=>{const client=await original();const query=client.query;client.query=async function(text,...args){if(typeof text==='string'&&text.startsWith('UPDATE "')&&text.includes('tenant_lifecycle_operations')){entered.resolve();await held.promise;}return query.call(this,text,...args);};return client;};
 return load('lib/tenant-lifecycle/operation-window').create(config);
});
const jobs=load('lib/server/serve/evaluator-job-context').create('clinical');
(async()=>{let runtime;try{
 runtime=await load('lib/server/serve/evaluator-runtime')({tenants:[A],operationWindow:f.window,jobContext:jobs,
 readCurrent:async tenant=>({tenant,identity:'a'.repeat(64)}),
 create:async()=>({evaluate:async()=>({checkpoint:0,properties:{synthetic:true}}),evaluateTime:async()=>({checkpoint:0,properties:{synthetic:true}}),close(){}}),
 recoveryIntervalMs:60000,timeIntervalMs:60000,schedule:()=>({}),cancel(){},setTimer:()=>({}),clearTimer(){},boot:'serve',bootConcurrency:1});
 await entered.promise;
 const inspect=load('lib/server/serve/evaluator-inspection')({tenants:new Map([[A,{}]]),runtime,
 gate:{inspect:async()=>({configured:{ordinal:0,mode:'standalone'},gate:{eligible:true,reason:null},owner:()=>0,admits:()=>true})}});
 const frame=async()=>({selected:[A],selfOrdinal:0,selfMode:'standalone',view:await inspect({tenants:[A]})});
 const before=await frame();assert.equal(before.view.tenants[0].ready,true);assert.equal(before.view.tenants[0].progress.completedAcquisitions,0);assert.equal(before.view.tenants[0].progress.lastCompletedAgeMs,null);
 
 held.resolve();for(let i=0;i<100&&runtime.health([A]).tenants[0].progress.completedAcquisitions!==1;i++)await new Promise(r=>setTimeout(r,1));
 const after=await frame();assert.equal(after.view.tenants[0].progress.completedAcquisitions,1);assert.equal(typeof after.view.tenants[0].progress.lastCompletedAgeMs,'number');
 
 console.log(JSON.stringify({protocol:'real scheduler/window/inspection source, recording database protocol; no PG or native proof',before,after,result:'PASS'}));
 }finally{held.resolve();await runtime?.close();await f.window.close();jobs.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
