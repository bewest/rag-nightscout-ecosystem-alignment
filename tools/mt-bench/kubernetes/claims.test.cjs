'use strict';
const assert=require('node:assert/strict'),path=require('node:path'),{createHash}=require('node:crypto');
const o=require('../m7-joined/completed-oracle.cjs');
// claims loads its existing source oracle from argv, exactly like operator use.
process.argv[2]=path.join(__dirname,'../m7-joined/completed-oracle.cjs');
const {assess}=require('./claims.cjs');
const a='11111111-1111-4111-8111-111111111111',b='22222222-2222-4222-8222-222222222222';
const binding={kind:'evaluator-work-v2',pair:{core:'1'.repeat(40),deploy:'2'.repeat(40)},imageId:'sha256:'+'3'.repeat(64),instrument:'4'.repeat(64)};
const config=o.source({pgstream:{},consumer:'evaluator-sample',postgres:{namespaces:{clock:'synthetic_clock',checkpoint:'synthetic_checkpoint',entries:'synthetic_entries'}}},{completedOutput:{namespace:'synthetic_checkpoint',consumer:'evaluator-sample'}},binding);
function witness(tenant,i){
 const doc={_id:'synthetic-'+i,date:123456789+i,sgv:123+i},sgv={_id:doc._id,mills:doc.date,mgdl:doc.sgv};
 const observed=['1',null,null,null,null,null];
 return {tenant,date:doc.date,stamp:'1',clientObservations:[{socket:i,connects:1,sgv}],rawRow:{tenant,stamp:'1',reader:binding,stored:[doc],
  typed:{version:2,contractDigest:createHash('sha256').update(JSON.stringify(['evaluator-work-v2','synthetic_checkpoint','evaluator-sample'])).digest('hex'),observed,completed:observed,identity:'5'.repeat(64),digest:'6'.repeat(64),revision:'1',generation:null,enabled:true,arrayBounds:true,bodyMetadataAbsent:true},
  state:{kind:'evaluator-work-v2',observed:{clock:'1'},completed:{clock:'1'},output:{tenant,identity:'5'.repeat(64),inputCheckpoint:'1',outputRevision:1,contentDigest:'6'.repeat(64),restoreGeneration:null,
    result:{properties:{bgnow:{mean:doc.sgv,last:doc.sgv,mills:doc.date,sgvs:[sgv]}}},frame:{sgvs:[sgv]}}}}};
}
const value={completion:config,tenants:[{id:a},{id:b}],clients:2,probe:{completedOutput:{witnesses:[witness(a,0),witness(b,1)]},kubernetesFrames:{overflow:false,rows:[{tenant:a,ids:['synthetic-0']},{tenant:b,ids:['synthetic-1']}]}}};
const green=()=>assert.equal(assess(value).verdict,'PASS');green();
for(const [name,mutate,code] of [
 ['clinical omitted',v=>delete v.probe.completedOutput,/K8S_CLINICAL_UNMEASURED/],
 ['raw SQL omitted',v=>delete v.probe.completedOutput.witnesses[0].rawRow,/K8S_CLINICAL_UNMEASURED/],
 ['accepted but not stored',v=>v.probe.completedOutput.witnesses[0].rawRow.stored=[],/M7_COMPLETION_STORED/],
 ['wrong clinical mean',v=>v.probe.completedOutput.witnesses[0].rawRow.state.output.result.properties.bgnow.mean=1,/M7_COMPLETION_BG_NOW/],
 ['client frame omitted',v=>v.probe.completedOutput.witnesses[0].clientObservations=[],/M7_COMPLETION_CLIENT/],
 ['foreign client content',v=>v.probe.completedOutput.witnesses[0].clientObservations[0].sgv._id='foreign',/M7_COMPLETION_CLIENT/],
 ['changed reader kind',v=>v.probe.completedOutput.witnesses[0].rawRow.reader.kind='evaluator-work-v1',/M7_COMPLETION_READER_MISMATCH/],
 ['lost observation',v=>delete v.probe.kubernetesFrames,/K8S_ISOLATION_UNMEASURED/],
 ['capture overflow',v=>v.probe.kubernetesFrames.overflow=true,/K8S_ISOLATION_UNMEASURED/],
 ['foreign tenant frame',v=>v.probe.kubernetesFrames.rows[0].ids.push('synthetic-1'),/K8S_CROSS_TENANT_FRAME/]
]){
 // JSON cloning separates source binding, raw SQL and client observations,
 // just as independent captured files do; shared references must not hide a break.
 const broken=JSON.parse(JSON.stringify(value));mutate(broken);assert.throws(()=>assess(broken),code,name);green();
 console.log('RED_RESTORED',name,code.source);
}
console.log('PASS raw SQL -> existing typed clinical/stored/frame oracle; no live database or cluster');

for(const clients of [0,1]){
 const sparse=JSON.parse(JSON.stringify(value));sparse.clients=clients;
 sparse.probe.completedOutput.witnesses.forEach((w,i)=>{if(i>=clients)w.clientObservations=[];});
 sparse.probe.kubernetesFrames.rows=sparse.probe.kubernetesFrames.rows.slice(0,clients);
 const result=assess(sparse);assert.equal(result.verdict,'PASS');
 assert.equal(result.clientFrameCoverage.witnessesWithoutViewers,2-clients);
 const broken=JSON.parse(JSON.stringify(sparse));broken.probe.completedOutput.witnesses[1].rawRow.stored=[];
 assert.throws(()=>assess(broken),/M7_COMPLETION_STORED/);
 assert.equal(assess(sparse).verdict,'PASS');
 console.log('RED_RESTORED unviewed tenant storage required, clients='+clients);
}

const delayed=JSON.parse(JSON.stringify(value));
const lateWitness=delayed.probe.completedOutput.witnesses[0];
Object.assign(lateWitness,{clientProofVersion:3,expectedSockets:[0],sentMono:0,
  clinicalTiming:{verdict:'PASS',acceptedMono:10,acceptanceToCompletionMs:120001}});
Object.assign(lateWitness.clientObservations[0],{atMono:20,transportId:'synthetic-transport'});
assert.equal(assess(delayed).verdict,'UNMEASURED');
lateWitness.clinicalTiming.acceptanceToCompletionLowerMs=120000;
assert.throws(()=>assess(delayed),/K8S_CLINICAL_DEADLINE/);
lateWitness.clinicalTiming.acceptanceToCompletionLowerMs=0;
lateWitness.clinicalTiming.acceptanceToCompletionMs=119999;
assert.equal(assess(delayed).verdict,'PASS');
lateWitness.clientObservations[0].atMono=120010;
assert.throws(()=>assess(delayed),/K8S_CLINICAL_DEADLINE/);
console.log('RED_RESTORED late first read UNMEASURED, proven late durable and frame at 120s refused');
