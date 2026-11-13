'use strict';
// Injected into one exact-custody evaluator child. The only effect is the fixed
// inspection RPC. It neither loads worker admission nor constructs a PG client.
const UUID=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const need=(ok)=>{if(!ok)throw Error('NATIVE_EVALUATOR_FETCH_REFUSED');};
async function fetchInspection(spec,load=require,write=line=>process.stdout.write(line)){
 need(spec&&['byteBudget,ids,queryBudget','byteBudget,diagnostics,ids,queryBudget'].includes(Object.keys(spec).sort().join(',')));
 need(Array.isArray(spec.ids)&&spec.ids.length===16&&new Set(spec.ids).size===16&&spec.ids.every(x=>typeof x==='string'&&UUID.test(x)));
 need(spec.diagnostics===undefined||['clinical-result-v1','change-feed-v1'].includes(spec.diagnostics));
 need(spec.queryBudget===1&&Number.isSafeInteger(spec.byteBudget)&&spec.byteBudget>=4096&&spec.byteBudget<=1048576);
 need(!process.env.NODE_OPTIONS&&!process.env.NODE_PATH&&!process.env.LD_PRELOAD);
 const metadata=load('./deploy/multitenant/service-environment'),values=metadata.read();
 // Partition parsing reads its own configuration but no database. Keep that
 // object private; only listener metadata is copied into the child environment.
 const partition=load('./lib/server/serve/evaluator-config').partitionFor(values);
 const keys=['NS_SERVE_INTERNAL_HOST','NS_SERVE_INTERNAL_PORT','NS_SERVE_INTERNAL_SOCKET','NS_SERVE_INTERNAL_SHUTDOWN_TIMEOUT_MS','XDG_RUNTIME_DIR'];
 const environment=Object.fromEntries(keys.filter(k=>Object.hasOwn(values,k)).map(k=>[k,values[k]]));
 const own=load('./lib/server/internal-api/listener-config').resolve(['evaluator'],environment);
 const client=load('./lib/server/internal-api/clients').evaluatorInspection(own.peer('evaluator',{maxBytes:spec.byteBudget-1024,timeoutMs:5000}));
 const view=await client.inspectEvaluator({tenants:spec.ids,...(spec.diagnostics?{diagnostics:spec.diagnostics}:{})});
 const line=JSON.stringify({selected:spec.ids,view,selfOrdinal:partition.partitioned?partition.ordinal:0,selfMode:partition.partitioned?'partitioned':'standalone',observedAt:Date.now()})+'\n';
 need(Buffer.byteLength(line)<=spec.byteBudget);await write(line);
}
module.exports={fetchInspection};
if(Object.hasOwn(globalThis,'M7_NATIVE_FETCH_SPEC')){
 const timer=setTimeout(()=>process.exit(1),7000);
 fetchInspection(globalThis.M7_NATIVE_FETCH_SPEC).catch(()=>{process.stderr.write('NATIVE_EVALUATOR_FETCH_REFUSED\n');process.exitCode=1;}).finally(()=>clearTimeout(timer));
}
