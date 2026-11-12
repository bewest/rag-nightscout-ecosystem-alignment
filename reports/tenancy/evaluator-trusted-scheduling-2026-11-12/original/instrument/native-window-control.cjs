'use strict';
// Diagnostic lower-port only: actual window admission/marker and SELECT 1.
const fs=require('node:fs'),assert=require('node:assert/strict'),{AsyncResource}=require('node:async_hooks'),{Pool}=require('/opt/app/node_modules/pg');
const selected=JSON.parse(fs.readFileSync('/run/ns-window-control.json','utf8'));
const connect=require('/opt/app/lib/storage/postgres-connection');
async function main(){
 require('/opt/app/lib/storage/tenant-scope').setTenancyMode('multi');
 const pool=new Pool({connectionString:selected.lifetimeUrl,max:2});
 const window=require('/opt/app/lib/tenant-lifecycle/operation-window').create({namespace:selected.namespace,lockRule:'tenant-id-sha256-v1',pool});let release,lower;
 try{
  await window.ready();release=connect.installOperationWindow(window);
  lower=await connect({connectionString:selected.connectionString,max:1});
  for(const tenant of selected.tenants){await window.run(tenant,()=>lower.withTenant(tenant,()=>lower.query('SELECT 1')));}
  if(process.argv[2]){
   const mode=process.argv[2];assert(['scheduler','neutral-timer-control'].includes(mode));
   const errors=[],jobs=new AsyncResource('evaluator-native-diagnostic');
   const wrapped={run:async(...args)=>{try{return await window.run(...args);}catch(error){errors.push(error.code||error.message);throw error;}},current:tenant=>window.current(tenant)};
   const result=()=>({checkpoint:1,signature:{stamp:1,deleted:0},emitted:[],requested:[],properties:{},due:{dueAt:Date.now()+10,reason:'native-scheduler-control',slow:[]}});
   const evaluate=()=>lower.withTenant(selected.tenants[0],async()=>{await lower.query('SELECT 1');return result();});
   const runtime=await require('/opt/app/lib/server/serve/evaluator-runtime')({tenants:[selected.tenants[0]],readCurrent:async()=>({tenant:selected.tenants[0],identity:'a'.repeat(64)}),create:async()=>({evaluate,evaluateTime:evaluate,close(){}}),operationWindow:wrapped,recoveryIntervalMs:10000,timeIntervalMs:10000,schedule:()=>({}),cancel(){},...(mode==='neutral-timer-control'?{setTimer:(fn,ms)=>setTimeout(()=>jobs.runInAsyncScope(fn),ms)}:{})});
   try{
    await new Promise(resolve=>setTimeout(resolve,70));const state=runtime.health().tenants[0];
    if(mode==='scheduler')assert(errors.includes('LIFECYCLE_WINDOW_SCOPE_INVALID'));else{assert.equal(errors.length,0);assert(state.cycles>1);}
    console.log(JSON.stringify({outcome:mode==='scheduler'?'reproduced':'counterfactual-pass',code:state.code,cycles:state.cycles,errors}));
   }finally{await runtime.close();jobs.emitDestroy();}
   if(mode==='neutral-timer-control'){
    let late;const observed=new Promise(resolve=>{late=resolve;});let executed=false;
    await window.run(selected.tenants[0],async()=>{setTimeout(()=>window.run(selected.tenants[0],()=>{executed=true;}).then(()=>late('accepted'),error=>late(error.code)),10);});
    assert.equal(await observed,'LIFECYCLE_WINDOW_SCOPE_INVALID');assert.equal(executed,false);console.log('LATE_APPLICATION_SCOPE_REFUSED');
   }
  }else console.log(JSON.stringify({outcome:'window-admitted',tenants:selected.tenants.length}));
 }finally{await lower?.end();release?.();await window.close();await pool.end();}
}
main().catch(error=>{console.error(JSON.stringify({code:/^[A-Z0-9_]+$/.test(error.code||'')?error.code:error.name,message:/^[A-Za-z0-9 _:.-]{1,160}$/.test(error.message||'')?error.message:null}));process.exitCode=1;});
