'use strict';
const assert=require('node:assert/strict');
const root='<owned-review>/core-53a8/';
const runtimeFactory=require(root+'lib/server/serve/evaluator-runtime'),coordinate=require(root+'lib/server/serve/evaluator-consumers').coordinate,inspection=require(root+'lib/server/serve/evaluator-inspection');
(async()=>{
 const ids=Array.from({length:10000},(_,i)=>'00000000-0000-4000-8000-'+String(i).padStart(12,'0'));
 let reads=0,gets=0,iterations=0,currentReads=0;
 const runtime=await runtimeFactory({tenants:ids,readCurrent:async tenant=>({tenant,identity:'a'.repeat(64)}),create:async()=>({evaluate:async()=>({checkpoint:0,signature:{stamp:0,deleted:0},properties:{},due:{dueAt:Infinity,reason:'none',slow:[]}}),close(){}}),recoveryIntervalMs:10000,timeIntervalMs:10000,schedule:()=>({}),cancel(){}});
 const store=Object.fromEntries(['consume','enqueue','due','begin','dispatch','finish','receipts'].map(k=>[k,async()=>{throw Error('UNEXPECTED_STORE_WORK');}]));
 const consumers=coordinate({tenants:ids,route:'review',current:()=>{currentReads++;return null;},currentConfig:async()=>null,isCurrent:async()=>true,store,reader:{read:async()=>[],allows:async()=>true},adapter:{id:'review',send(){throw Error('UNEXPECTED_HANDOFF');}},now:Date.now,maxRows:10,maxBytes:10000,maxPayloadBytes:1000,maxInflight:1,attemptTimeoutMs:1000,retryDelayMs:1000,pollIntervalMs:10000,retryIntervalMs:10000,schedule:()=>({}),cancel(){}});
 const original={};for(const key of ['keys','values','entries',Symbol.iterator,'get'])original[key]=Map.prototype[key];
 const config=new Map(ids.map(id=>[id,true]));
 const inspect=inspection({tenants:config,runtime,consumers,gate:{inspect:async()=>{reads++;return{configured:{ordinal:0},gate:{eligible:true,reason:null},owner:()=>0,admits:()=>true};}},startup:{health(){throw Error('FULL_STARTUP_SCAN');}},registry:{stats(){throw Error('FULL_REGISTRY_SCAN');}}});
 try{
  for(const key of ['keys','values','entries',Symbol.iterator])Map.prototype[key]=function(...args){if(this.size>=10000){iterations++;throw Error('FULL_SOURCE_MAP_ITERATION');}return original[key].apply(this,args);};
  Map.prototype.get=function(...args){if(this.size>=10000)gets++;return original.get.apply(this,args);};
  const empty=await inspect({tenants:[]});assert.equal(empty.tenants.length,0);assert.equal(gets,0);assert.equal(currentReads,0);
  const selected=await inspect({tenants:ids.slice(-128)});assert.equal(selected.tenants.length,128);assert.equal(gets,256);assert.equal(currentReads,128);assert.equal(iterations,0);
  assert.throws(()=>runtime.health(),/FULL_SOURCE_MAP_ITERATION/);assert.throws(()=>consumers.health(),/FULL_SOURCE_MAP_ITERATION/);await assert.rejects(inspect({}),/FULL_SOURCE_MAP_ITERATION/);
  console.log(JSON.stringify({source:'53a8ad725049e6bdacdd903ea8bd759c64781c8d',configuredTenants:10000,selectedRows:128,selectedMapGets:gets,selectedCurrentReads:currentReads,metadataGateReads:reads,fullScanControlRefusals:iterations,selectedPathFullIterations:0,scope:'actual runtime/consumer/inspection; synthetic components, no native PG'}));
 }finally{for(const key of Reflect.ownKeys(original))Map.prototype[key]=original[key];await consumers.close();await runtime.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
