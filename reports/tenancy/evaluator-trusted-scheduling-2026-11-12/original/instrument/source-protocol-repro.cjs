'use strict';
const assert=require('node:assert/strict'),root=process.env.NS_CORE_WORKTREE+'/';
const f=require(root+'tests/fixtures/operation-window-runtime-protocol')(),errors=[],A='11111111-1111-4111-8111-111111111111';
(async()=>{
 await f.window.ready();
 const window={run:async(...args)=>{try{return await f.window.run(...args);}catch(error){errors.push(error.code||error.message);throw error;}},current:tenant=>f.window.current(tenant)};
 const result=()=>({checkpoint:1,signature:{stamp:1,deleted:0},emitted:[],requested:[],properties:{},due:{dueAt:Date.now()+10,reason:'focused-scheduler',slow:[]}});
 const runtime=await require(root+'lib/server/serve/evaluator-runtime')({tenants:[A],readCurrent:async()=>({tenant:A,identity:'a'.repeat(64)}),create:async()=>({evaluate:async()=>result(),evaluateTime:async()=>result(),close(){}}),operationWindow:window,recoveryIntervalMs:10000,timeIntervalMs:10000,schedule:()=>({}),cancel(){}});
 try{await new Promise(resolve=>setTimeout(resolve,60));const tenant=runtime.health().tenants[0];console.log(JSON.stringify({code:tenant.code,cycles:tenant.cycles,errors}));assert(errors.includes('LIFECYCLE_WINDOW_SCOPE_INVALID'));}
 finally{await runtime.close();await f.window.close();}
})().catch(error=>{console.error(JSON.stringify({code:error.code||error.name,message:error.message}));process.exitCode=1;});
