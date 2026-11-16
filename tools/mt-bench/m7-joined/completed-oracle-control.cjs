'use strict';
const assert=require('node:assert/strict'),o=require('./completed-oracle.cjs');
const tenant='11111111-1111-4111-8111-111111111111',doc={_id:'synthetic-id',date:123456789,sgv:123};
const sgv={_id:doc._id,mills:doc.date,mgdl:doc.sgv};
const witness={tenant,date:doc.date,stamp:'9007199254740993'};
const row={tenant,stamp:witness.stamp,stored:[doc],state:{kind:'evaluator-work-v1',observed:{clock:witness.stamp},completed:{clock:witness.stamp},output:{tenant,inputCheckpoint:witness.stamp,outputRevision:3,contentDigest:'a'.repeat(64),result:{properties:{bgnow:{mean:doc.sgv,last:doc.sgv,mills:doc.date,sgvs:[sgv]}}},rows:[{domain:'entries',doc}],frame:{sgvs:[sgv]}}}};
const selected={kind:'evaluator-work-v1',pair:{core:'1'.repeat(40),deploy:'2'.repeat(40)},imageId:'sha256:'+'3'.repeat(64),instrument:'4'.repeat(64)};
const source=o.source({pgstream:{},consumer:'evaluator-sample',postgres:{namespaces:{clock:'sample_clock',checkpoint:'sample_checkpoint',entries:'sample_entries'}}},{completedOutput:{namespace:'sample_checkpoint',consumer:'evaluator-sample'}},selected);
row.reader=selected;
const clients=[{socket:0,connects:1,sgv},{socket:1,connects:1,sgv}];
const green=()=>assert.equal(o.assess(row,witness,clients,2,source).ready,true);
green();
for(const [name,mutate] of [
 ['pending completion',x=>x.state.completed.clock='9007199254740992'],
 ['wrong tenant',x=>x.state.output.tenant='22222222-2222-4222-8222-222222222222'],
 ['missing stored write',x=>x.stored=[]],
 ['missing clinical frame',x=>delete x.state.output.frame],
 ['wrong durable glucose',x=>x.state.output.frame.sgvs[0].mgdl=124],
 ['wrong clinical BG-now mean',x=>x.state.output.result.properties.bgnow.mean=124],
 ['missing durable output',x=>x.state.output=null]]){
 const broken=structuredClone(row);mutate(broken);assert.equal(o.assess(broken,witness,clients,2,source).ready,false,name);console.log('EXPECTED_RED',name);green();
}
for(const [name,bad]of [['dropped client output',clients.slice(0,1)],['wrong client identity',clients.map(c=>({...c,sgv:{...c.sgv,_id:'other'}}))],['reconnected client',clients.map(c=>({...c,connects:2}))]]){
 assert.equal(o.assess(row,witness,bad,2,source).ready,false,name);console.log('EXPECTED_RED',name);green();
}

assert.match(o.query(source,[tenant],'synthetic-run'),/evaluator-sample-completed/);
assert.throws(()=>o.query(source,[tenant],"bad'"),/SELECTOR/);
console.log('RESTORED_GREEN durable completion/stored/output/client model; no SQL or runtime run');
