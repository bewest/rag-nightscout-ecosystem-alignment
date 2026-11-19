'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const file = process.argv[2];
const source = fs.readFileSync(file, 'utf8');
const directory = path.dirname(file);
const timing = require(path.join(directory, 'clinical-timing.cjs'));
const lag = require(path.join(directory, 'durable-lag.cjs'));
const start = source.indexOf('  const poller = (async () => {');
const end = source.indexOf('  const writers = [];', start);
assert(start > 0 && end > start);
assert(source.includes('e.acceptedMono=r.responseMono'));
assert.equal(timing.contract, 'clinical-deadline-from-acceptance-v1');

async function exercise({durableAt, frameAt, prior=false, unavailable=false, foreign=false, queryMs=0}) {
  const accepted = 8000;
  let now = accepted;
  const witness = {tenant:'a', date:1, sentMono:0, sent:0, acceptedMono:accepted,
    acked:accepted, stamp:null, expectedSockets:[0], evaluatedAt:null};
  const frame = {socket:0, connects:1, transportId:'viewer', atMono:frameAt, sgv:{_id:'entry', mills:1, mgdl:100}};
  const frames = new Map();
  const result = () => now >= durableAt ? {ready:true, storedId:'entry', storedSgv:100} :
    {ready:false, code:'M7_COMPLETION_PENDING'};
  const context = {Date:{now:()=>now}, performance:{now:()=>now}, polling:false,
    evalPending:[witness], evalMissed:[], evalLatencies:[], out:{}, completionSource:{}, timing, lag,
    signalDir:directory, discovery:true, args:{runid:'synthetic'}, Buffer, Math, Map, Set,
    oracleCost:{queries:0, bytes:0, elapsedMs:0, missing:0, durablePendingPeak:0},
    tenants:[{id:'a'}], viewers:[1], pending:new Map([['a:1',{clientFrames:frames}]]),
    psqlAsync:async()=>{
      if(unavailable) throw Error('M7_PROBE_SQL_OBSERVATION_UNAVAILABLE');
      now+=queryMs;
      if(now >= frameAt) frames.set(0,frame);
      const row=JSON.stringify({tenant:'a',stamp:prior?'2':'1'});
      return foreign ? row+'\n'+JSON.stringify({tenant:'b',stamp:'1'}) : row;
    },
    completionOracle:{query:()=>'', assessDurable:result,
      assess:()=>result().ready && !frames.size ? {ready:false,code:'M7_COMPLETION_CLIENT',clientFailure:'M7_CLIENT_COUNT'} : result()},
    sleep:async ms=>{now+=ms;}};
  await vm.runInNewContext(source.slice(start, end)+'\npoller',context);
  return timing.assess(witness,[...frames.values()]);
}
(async()=>{
  for(const prior of [false,true]){
    const missing=await exercise({durableAt:Infinity,frameAt:7000,prior});
    assert.equal(missing.verdict,'FAIL');
    assert.equal(missing.code,'M7_COMPLETION_DEADLINE');
  }
  const justInTime=await exercise({durableAt:127000,frameAt:7000});
  assert.equal(justInTime.verdict,'PASS');
  assert.equal(justInTime.acceptanceToCompletionMs,119000);
  assert.deepEqual(justInTime.acceptanceToFrameMs,[-1000]);
  const boundary=await exercise({durableAt:128000,frameAt:8000});
  assert.equal(boundary.verdict,'UNMEASURED');
  const crossing=await exercise({durableAt:128000,frameAt:8000,queryMs:1500});
  assert.equal(crossing.verdict,'UNMEASURED');
  assert(crossing.acceptanceToCompletionLowerMs<120000 && crossing.acceptanceToCompletionMs>=120000);
  const timedFrame=await exercise({durableAt:8000,frameAt:128000});
  assert.equal(timedFrame.code,'M7_COMPLETION_DEADLINE');
  const missingFrame=await exercise({durableAt:10000,frameAt:Infinity});
  assert.equal(missingFrame.code,'M7_COMPLETION_DEADLINE');
  const lost=await exercise({durableAt:Infinity,frameAt:Infinity,unavailable:true});
  assert.equal(lost.verdict,'UNMEASURED');
  const foreign=await exercise({durableAt:8000,frameAt:8000,foreign:true});
  assert.equal(foreign.verdict,'FAIL');
  assert.equal(foreign.code,'M7_COMPLETION_FOREIGN_TENANT');
  console.log(path.basename(file)+' missing output (first/subsequent) FAIL, 119s PASS, missing frame FAIL, missing SQL UNMEASURED, foreign SQL row FAIL');
})().catch(e=>{console.error(e);process.exitCode=1;});
