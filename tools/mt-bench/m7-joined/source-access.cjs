"use strict";
// Same private listener/client boundary and hard limits as evaluator-progress.
// One selected read observes runtime-wide source counters, not clinical data.
(async()=>{
 const uuid=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
 const integer=(n,max)=>Number.isSafeInteger(n)&&n>=1&&n<=max;
 if(!Array.isArray(M7_SOURCE_IDS)||!integer(M7_SOURCE_IDS.length,128)||new Set(M7_SOURCE_IDS).size!==M7_SOURCE_IDS.length||M7_SOURCE_IDS.some(x=>typeof x!=="string"||!uuid.test(x))||!integer(M7_SOURCE_QUERY_BUDGET,1)||!integer(M7_SOURCE_BYTE_BUDGET,1048576))throw Error("M7_SOURCE_ACCESS_SELECTOR");
 const deadline=Date.now()+15000,watchdog=setTimeout(()=>process.exit(1),16000);
 try {
  const values=require("./deploy/multitenant/service-environment").read();
  const keys=["NS_SERVE_INTERNAL_HOST","NS_SERVE_INTERNAL_PORT","NS_SERVE_INTERNAL_SOCKET","NS_SERVE_INTERNAL_SHUTDOWN_TIMEOUT_MS","XDG_RUNTIME_DIR"];
  const environment=Object.fromEntries(keys.filter(key=>Object.hasOwn(values,key)).map(key=>[key,values[key]]));
  const own=require("./lib/server/internal-api/listener-config").resolve(["evaluator"],environment);
  const client=require("./lib/server/internal-api/clients").evaluatorInspection(own.peer("evaluator",{maxBytes:1048576,timeoutMs:5000}));
  if(Date.now()>=deadline)throw Error("M7_SOURCE_ACCESS_DEADLINE");
  const view=await client.inspectEvaluator({tenants:M7_SOURCE_IDS,diagnostics:"source-access-v1"});
  if(Date.now()>=deadline||view?.kind!=="evaluator"||typeof view.runtimeId!=="string"||!uuid.test(view.runtimeId))throw Error("M7_SOURCE_ACCESS_RUNTIME");
  const line=JSON.stringify({selected:M7_SOURCE_IDS,runtimeId:view.runtimeId,sourceAccess:view.diagnostics?.sourceAccess,observedAt:Date.now()})+"\n";
  if(Buffer.byteLength(line)>M7_SOURCE_BYTE_BUDGET)throw Error("M7_SOURCE_ACCESS_BYTE_BOUND");
  if(!process.stdout.write(line))await new Promise((resolve,reject)=>{const done=()=>{process.stdout.removeListener("error",failed);resolve();};const failed=error=>{process.stdout.removeListener("drain",done);reject(error);};process.stdout.once("drain",done);process.stdout.once("error",failed);});
 } finally {clearTimeout(watchdog);}
})().catch(()=>{process.stderr.write("M7_SOURCE_ACCESS_UNAVAILABLE\n");process.exitCode=1;});
