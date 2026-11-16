'use strict';
// All values are from the single probe process performance.now clock. A SQL
// snapshot lies between invocation and response; never subtract a server clock.
function observe(witness,result,start,end){
 if(!Number.isFinite(witness.sentMono)||!Number.isFinite(start)||!Number.isFinite(end)||end<start||start<witness.sentMono)throw Error('M7_LAG_CLOCK');
 if(witness.durableObservation)return;
 if(result.ready){witness.durableObservation={lowerMs:Math.max(0,(witness.lastNegativeMono??witness.sentMono)-witness.sentMono),upperMs:end-witness.sentMono,queryMs:end-start,...result};}
 else if(['M7_COMPLETION_PENDING','M7_COMPLETION_OUTPUT_CLOCK','M7_COMPLETION_FRAME','M7_COMPLETION_BG_NOW'].includes(result.code))witness.lastNegativeMono=start;
 // Missing rows, invalid typing and failed queries establish no negative bound.
}
function stats(values){const a=[...values].sort((a,b)=>a-b),pct=p=>a.length?a[Math.min(a.length-1,Math.ceil(a.length*p)-1)]:null;return {n:a.length,p50:pct(.5),p95:pct(.95),p99:pct(.99),max:a.length?a[a.length-1]:null};}
function summary(witnesses,pending,cost){
 const samples=witnesses.map(w=>{const p=pending.get(w.tenant+':'+w.date);return {tenant:w.tenant,date:w.date,sentMono:w.sentMono,accepted:w.acked!==null,refused:w.evaluatedAt===-1,durable:w.durableObservation??null,clientFrames:[...(p?.clientFrames?.values()||[])].filter(f=>w.durableObservation&&f.sgv._id===w.durableObservation.storedId).map(f=>({socket:f.socket,requestToFrameMs:f.atMono-w.sentMono,storedId:f.sgv._id}))};});
 return {kind:'request-to-durable-observation-v1',clock:'single probe performance.now; SQL invocation/response brackets',scope:'sparse synthetic probe writes; ordinary REST workload and all-roster progress are separate',executorLag:'UNMEASURED: see evaluator duration intervals',samples,witnesses:samples.length,distinctTenants:new Set(samples.map(s=>s.tenant)).size,missing:samples.filter(s=>!s.durable).length,pendingAccepted:samples.filter(s=>s.accepted&&!s.durable).length,refused:samples.filter(s=>s.refused).length,drain:{perWriteObservationBudgetMs:120000,finalSettlementDelayMs:10000,endMono:cost.observationEndMono??null},durableLowerMs:stats(samples.filter(s=>s.durable).map(s=>s.durable.lowerMs)),durableUpperMs:stats(samples.filter(s=>s.durable).map(s=>s.durable.upperMs)),matchedClientMs:stats(samples.flatMap(s=>s.clientFrames.map(f=>f.requestToFrameMs))),collector:cost};
}
module.exports={observe,summary};
