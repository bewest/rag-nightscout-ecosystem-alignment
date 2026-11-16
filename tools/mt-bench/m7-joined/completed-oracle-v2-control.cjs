 'use strict';
const assert=require('node:assert/strict'),{createHash}=require('node:crypto'),o=require('./completed-oracle.cjs');
const ns={clock:'synthetic_clock',checkpoint:'synthetic_checkpoint',entries:'synthetic_entries'};
const selected={kind:'evaluator-work-v2',pair:{core:'1'.repeat(40),deploy:'2'.repeat(40)},imageId:'sha256:'+'3'.repeat(64),instrument:'4'.repeat(64)};
const config=o.source({pgstream:{},consumer:'evaluator-sample',postgres:{namespaces:ns}},{completedOutput:{namespace:ns.checkpoint,consumer:'evaluator-sample'}},selected);
const tenant='11111111-1111-4111-8111-111111111111',doc={_id:'synthetic-id',date:123456789,sgv:123};
const sgv={_id:doc._id,mills:doc.date,mgdl:doc.sgv},witness={tenant,date:doc.date,stamp:'9007199254740993'};
const observed=['9007199254740993','9223372036854775807','0','8',null,'17'];
const map=values=>Object.fromEntries(['clock','settings','policy','activity','lifecycle','bootstrap'].flatMap((k,i)=>values[i]===null?[]:[[k,values[i]]]));
const row={tenant,stamp:witness.stamp,reader:selected,stored:[doc],typed:{version:2,contractDigest:createHash('sha256').update(JSON.stringify(['evaluator-work-v2',ns.checkpoint,'evaluator-sample'])).digest('hex'),observed,completed:observed,identity:'5'.repeat(64),digest:'6'.repeat(64),revision:'9007199254740991',generation:null,enabled:true,arrayBounds:true,bodyMetadataAbsent:true},state:{kind:'evaluator-work-v2',observed:map(observed),completed:map(observed),output:{tenant,identity:'5'.repeat(64),inputCheckpoint:witness.stamp,outputRevision:Number.MAX_SAFE_INTEGER,contentDigest:'6'.repeat(64),restoreGeneration:null,result:{properties:{bgnow:{mean:doc.sgv,last:doc.sgv,mills:doc.date,sgvs:[sgv]}}},rows:[{domain:'entries',doc}],frame:{sgvs:[sgv]}}}};
const clients=[{socket:0,connects:1,sgv},{socket:1,connects:1,sgv}];
const assess=value=>o.assess(value,witness,clients,2,config),green=()=>assert.equal(assess(row).ready,true);
green();
assert.equal(o.assess(row,witness,[],2,config).code,'M7_COMPLETION_CLIENT');
assert.equal(o.assessDurable(row,witness,config).ready,true);
const missingStored=structuredClone(row);missingStored.stored=[];
assert.equal(o.assessDurable(missingStored,witness,config).code,'M7_COMPLETION_STORED');
for(const [name,mutate,code]of [
 ['missing binding',r=>delete r.reader,'READER_MISMATCH'],
 ['wrong source',r=>r.reader.pair.core='7'.repeat(40),'READER_MISMATCH'],
 ['reader downgrade',r=>r.reader.kind='evaluator-work-v1','READER_MISMATCH'],
 ['wrong row kind',r=>r.state.kind='evaluator-work-v1','READER_MISMATCH'],
 ['wrong work version',r=>r.typed.version=0,'TYPED_STATE'],
 ['wrong contract digest',r=>r.typed.contractDigest='0'.repeat(64),'TYPED_STATE'],
 ['numeric bigint precision loss',r=>r.typed.observed[0]=Number(witness.stamp),'TYPED_STATE'],
 ['bigint overflow',r=>r.typed.observed[1]='9223372036854775808','TYPED_STATE'],
 ['source order swapped',r=>{[r.typed.observed[0],r.typed.observed[1]]=[r.typed.observed[1],r.typed.observed[0]];},'TYPED_STATE'],
 ['missing array slot',r=>r.typed.observed.pop(),'TYPED_STATE'],
 ['null converted to zero',r=>r.state.observed.lifecycle='0','TYPED_STATE'],
 ['completed ahead',r=>{r.typed.completed=[...r.typed.completed];r.typed.completed[3]='9';r.state.completed.activity='9';},'TYPED_STATE'],
 ['missing metadata',r=>delete r.typed.digest,'TYPED_STATE'],
 ['unsafe output revision',r=>{r.typed.revision='9007199254740992';r.state.output.outputRevision=9007199254740992;},'TYPED_STATE'],
 ['numeric restore generation',r=>{r.typed.generation=1;r.state.output.restoreGeneration=1;},'TYPED_STATE'],
 ['zero restore generation',r=>{r.typed.generation='0';r.state.output.restoreGeneration='0';},'TYPED_STATE'],
 ['duplicate mutable metadata',r=>r.typed.bodyMetadataAbsent=false,'TYPED_STATE'],
 ['noncanonical array lower bound',r=>r.typed.arrayBounds=false,'TYPED_STATE'],
 ['disabled work',r=>r.typed.enabled=false,'TYPED_STATE'],
 ['missing body',r=>r.state.output=null,'TYPED_STATE'],
 ['wrong clinical mean',r=>r.state.output.result.properties.bgnow.mean=124,'BG_NOW'],
 ['missing persisted write',r=>r.stored=[],'STORED']]){
 const broken=structuredClone(row);mutate(broken);const result=assess(broken);assert.equal(result.ready,false,name);assert.equal(result.code,'M7_COMPLETION_'+code,name);console.log('EXPECTED_RED',name,result.code);green();
}
const restored=structuredClone(row);restored.typed.generation='9223372036854775807';restored.state.output.restoreGeneration=restored.typed.generation;assert.equal(assess(restored).ready,true);
const query=o.query(config,[tenant],'synthetic-run');
assert.match(query,/c.work_observed\[1\]::text/);assert.match(query,/c.work_completed\[6\]::text/);assert.match(query,/c.output_revision::text/);assert.match(query,/c.output_restore_generation::text/);assert.match(query,/c.work_observed::text\[\]/);assert.match(query,/c.work_version/);assert.match(query,/c.contract_digest/);assert.match(query,/c.projection->0->'output'/);
assert.doesNotMatch(query,/\b(UPDATE|INSERT|DELETE|ALTER|CREATE)\b/);
assert.throws(()=>o.source({},{},selected),/COMPLETION_SOURCE/);
assert.throws(()=>o.query({...config,kind:'evaluator-work-v1'},[tenant],'synthetic-run'),/READER_MISMATCH/);
assert.throws(()=>o.query({...config,binding:{...selected,extra:"'"}},[tenant],'synthetic-run'),/BINDING/);
console.log('RESTORED_GREEN exact v2 strings/null/order/metadata and original clinical witness; SQL shape only, native SQL NOT RUN');
const metadata=()=>o.progressSnapshot([row],config,[tenant]);
assert.deepEqual(metadata().rows[0].observed,row.state.observed);
assert.equal(metadata().rows[0].writerClock,witness.stamp);
assert.deepEqual(Object.keys(metadata().rows[0]).sort(),['tenant','writerClock','observed','completed','outputRevision','restoreGeneration'].sort());
for(const [mutate,code] of [
 [r=>r.typed.contractDigest='0'.repeat(64),'TYPED_STATE'],
 [r=>r.reader.pair.core='0'.repeat(40),'READER_MISMATCH'],
 [r=>r.state.output.tenant='22222222-2222-4222-8222-222222222222','TYPED_STATE'],
 [r=>r.stamp=Number(r.stamp),'OPPORTUNITY_CLOCK'],
 [r=>r.stamp='1','OPPORTUNITY_CLOCK']
]){const bad=structuredClone(row);mutate(bad);assert.throws(()=>o.progressSnapshot([bad],config,[tenant]),new RegExp(code));metadata();}
assert.throws(()=>o.progressSnapshot([],config,[tenant]),/COVERAGE/);
assert.throws(()=>o.progressSnapshot([row,row],config,[tenant,tenant]),/COVERAGE/);
// Remove the actual accessor's strict typed-state call: the wrong-digest
// expected-refusal criterion must go red, then the original export restores it.
const fs=require('node:fs'),text=fs.readFileSync(require.resolve('./completed-oracle.cjs'),'utf8');
const needle="if(!typedState(row,config,chosen))fail('M7_COMPLETION_TYPED_STATE');";
assert.equal(text.split(needle).length,2,'EXACT_ACCESSOR_ABLATION_TARGET');
const altered={exports:{}};Function('require','module',text.replace(needle,''))(require,altered);
const badDigest=structuredClone(row);badDigest.typed.contractDigest='0'.repeat(64);
const rejectsBad=api=>assert.throws(()=>api.progressSnapshot([badDigest],config,[tenant]),/TYPED_STATE/);
rejectsBad(o);assert.throws(()=>rejectsBad(altered.exports),assert.AssertionError);rejectsBad(o);metadata();
console.log('RESTORED_GREEN read-only opportunity accessor exact metadata/reader/int64/roster and actual typed-validator ablation; native collection NOT RUN');
const progressQuery=o.progressQuery(config,[tenant]);
assert(progressQuery.startsWith('SELECT '));assert(!/\b(UPDATE|INSERT|DELETE|ALTER|CREATE)\b/.test(progressQuery));
assert(!progressQuery.includes('jsonb_agg(e.doc)'));
assert(!progressQuery.includes("THEN (c.projection->0->'output')"));
assert(progressQuery.includes("jsonb_build_object('tenant',c.projection->0->'output'->'tenant')"));
assert(progressQuery.includes('c.work_observed::text[]')&&progressQuery.includes('c.work_completed::text[]'));
const metadataOnly=structuredClone(row);metadataOnly.stored=[];
for(const key of ['inputCheckpoint','result','rows','frame'])delete metadataOnly.state.output[key];
assert.equal(o.progressSnapshot([metadataOnly],config,[tenant]).rows[0].writerClock,witness.stamp);
assert.equal(o.assess(metadataOnly,witness,clients,2,config).ready,false,'METADATA_IS_NOT_CLINICAL_EQUIVALENCE');
console.log('RESTORED_GREEN metadata-only same-SELECT query retains typed fences and does not qualify clinical witness');
