'use strict';
const assert=require('node:assert/strict'),{createHash}=require('node:crypto');
const root=process.env.M7_PRODUCER_CORE;assert(root,'M7_PRODUCER_CORE_REQUIRED');const producer=require(root+'/lib/tenant-notifications/producer-state'),contract=require(root+'/lib/tenant-notifications/contract');
const bounds={maxRows:100,maxBytes:100000,maxPayloadBytes:10000},t0=Date.UTC(2026,10,12,12),repeatMs=60000;
const urgent={kind:'notify',level:2,title:'Synthetic urgent',message:'Synthetic unchanged',plugin:{name:'synthetic'},group:'default'};
const digest=v=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
function cycle(at,{eligible=true,identity='same-config',requested=[urgent],content='same'}={}){return {identity,eligible,contentDigest:digest(content),inputCheckpoint:1,result:{now:at,requested}};}
function run(steps,selectedRepeatMs=repeatMs){let state=null,revision=0;return steps.map(step=>{const at=t0+step.dt;const previous=step.preserveDeadline&&state?{...state,repeatAt:t0+repeatMs}:state;const c=cycle(at,step);const result=producer.reduce({...bounds,previous,cycle:c,acks:step.acks||[],at,revision:++revision,repeatMs:selectedRepeatMs,reset:c.eligible===true&&!!previous&&previous.clinicalIdentity!==c.identity});state=result.state;return {dt:step.dt,eligible:c.eligible,identity:c.identity,output:state.output,repeatAtDelta:state.repeatAt===undefined?null:state.repeatAt-t0,alarmsDigest:digest(state.alarms),effects:state.effects.map(e=>({origin:e.origin,clear:!!e.payload.clear,effectIdentity:contract.effectIdentity(e.payload)})),state};});}
const cases={
 preservedDeadlineControl:run([{dt:0},{dt:1000,eligible:false},{dt:4438,preserveDeadline:true}]),
 dueAfterGap:run([{dt:0},{dt:1000,eligible:false},{dt:60000}]),
 repeatOff:run([{dt:0},{dt:1000,eligible:false},{dt:4438},{dt:60000}],null),
 unavailableBeforeFirstOutput:run([{dt:0,eligible:false},{dt:1000}]),
 normalThenRealarm:run([{dt:0},{dt:1000,requested:[],content:'normal'},{dt:2000}]),
 sameContentNoGap:run([{dt:0},{dt:4438}]),
 transientIneligible:run([{dt:0},{dt:1000,eligible:false},{dt:4438}]),
 genuineRepeatBoundary:run([{dt:0},{dt:59999},{dt:60000},{dt:60001}]),
 changedConfiguration:run([{dt:0},{dt:1000,eligible:false},{dt:4438,identity:'new-config'}]),
 normalEmptyOutput:run([{dt:0},{dt:1000,requested:[],content:'normal'},{dt:4438,requested:[],content:'normal'}]),
 ackDuringIneligible:run([{dt:0},{dt:1000,eligible:false,acks:[{group:'default',level:2,ackedAt:t0+1000,expiresAt:t0+31000}]},{dt:4438,acks:[{group:'default',level:2,ackedAt:t0+1000,expiresAt:t0+31000}]}])
};
const gap=cases.transientIneligible,none=cases.sameContentNoGap,due=cases.genuineRepeatBoundary;
assert.equal(cases.preservedDeadlineControl[0].effects[0].origin,cases.preservedDeadlineControl[2].effects[0].origin);assert.equal(cases.preservedDeadlineControl[2].repeatAtDelta,60000);
assert.notEqual(cases.dueAfterGap[0].effects[0].origin,cases.dueAfterGap[2].effects[0].origin);assert.equal(cases.dueAfterGap[2].repeatAtDelta,120000);
assert.notEqual(cases.normalThenRealarm[0].effects[0].origin,cases.normalThenRealarm[2].effects[0].origin);
assert.notEqual(gap[2].effects[0].origin,contract.digest(JSON.stringify(['producer-transition-v2',['repeat',gap[2].output,null],0])));
assert.equal(cases.dueAfterGap[2].effects[0].origin,contract.digest(JSON.stringify(['producer-transition-v2',['repeat',cases.dueAfterGap[2].output,t0+60000],0])));
assert(cases.repeatOff.every(row=>row.repeatAtDelta===null));assert(cases.repeatOff.every(row=>row.effects[0].origin===cases.repeatOff[0].effects[0].origin));
assert.equal(cases.unavailableBeforeFirstOutput[0].repeatAtDelta,null);assert.equal(cases.unavailableBeforeFirstOutput[0].effects.length,0);
assert.equal(none[0].effects[0].origin,none[1].effects[0].origin);
assert.equal(gap[1].repeatAtDelta,60000);assert.deepEqual(gap[0].output,gap[1].output);assert.equal(gap[0].alarmsDigest,gap[1].alarmsDigest);
assert.equal(gap[0].effects[0].origin,gap[2].effects[0].origin);assert.equal(gap[0].effects[0].effectIdentity,gap[2].effects[0].effectIdentity);assert.equal(gap[2].repeatAtDelta,60000);
assert.equal(due[0].effects[0].origin,due[1].effects[0].origin);assert.notEqual(due[1].effects[0].origin,due[2].effects[0].origin);assert.equal(due[2].effects[0].origin,due[3].effects[0].origin);
assert.equal(cases.normalEmptyOutput[1].effects[0].origin,cases.normalEmptyOutput[2].effects[0].origin);
assert.equal(cases.ackDuringIneligible[1].effects[0].origin,cases.ackDuringIneligible[2].effects[0].origin);
assert.equal(cases.changedConfiguration[2].state.clinicalIdentity,'new-config');assert.notEqual(cases.changedConfiguration[0].effects[0].origin,cases.changedConfiguration[2].effects[0].origin);
assert(cases.normalEmptyOutput[1].effects.every(e=>e.clear));assert(cases.ackDuringIneligible[1].effects.every(e=>e.clear));assert(cases.ackDuringIneligible[2].effects.every(e=>e.clear));
const clean=Object.fromEntries(Object.entries(cases).map(([name,rows])=>[name,rows.map(({state,...row})=>row)]));
const publication=JSON.stringify({source:process.env.M7_PRODUCER_COMMIT,scope:'actual source reducer plus shipping private notifications; synthetic in-memory, not native durable/ownership reproduction',cases:clean},null,2);require('node:fs').writeFileSync(process.env.M7_PRODUCER_OUTPUT,publication+'\n');console.log(publication);
