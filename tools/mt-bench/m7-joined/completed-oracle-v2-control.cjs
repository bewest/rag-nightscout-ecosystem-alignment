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
// Completed output carries the client frame, not a second raw clinical projection.
const noRawRows=structuredClone(row);delete noRawRows.state.output.rows;
assert.equal(assess(noRawRows).ready,true,'correct frame and durable coverage need no raw rows');
assert.equal(o.assessDurable(noRawRows,witness,config).ready,true);
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
 ['missing clinical frame',r=>delete r.state.output.frame,'FRAME'],
 ['missing frame SGVs',r=>r.state.output.frame.sgvs=[],'FRAME'],
 ['wrong frame identity',r=>r.state.output.frame.sgvs[0]._id='wrong-synthetic-id','FRAME'],
 ['wrong frame time',r=>r.state.output.frame.sgvs[0].mills+=1,'FRAME'],
 ['wrong frame value',r=>r.state.output.frame.sgvs[0].mgdl+=1,'FRAME'],
 ['wrong clinical mean',r=>r.state.output.result.properties.bgnow.mean=124,'BG_NOW'],
 ['missing persisted write',r=>r.stored=[],'STORED']]){
 const broken=structuredClone(noRawRows);mutate(broken);const result=assess(broken);assert.equal(result.ready,false,name);assert.equal(result.code,'M7_COMPLETION_'+code,name);console.log('EXPECTED_RED',name,result.code);green();
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
const needle="!typedState(row,config,true)";
assert.equal(text.split(needle).length,2,'EXACT_ACCESSOR_ABLATION_TARGET');
const altered={exports:{}};Function('require','module',text.replace(needle,'false'))(require,altered);
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
// Runtime 1646f004 work-state.admit installs revision 0, null identity/digest,
// null output and exact six-slot floors; observe can advance inputs first.
const initial=structuredClone(row);
Object.assign(initial.typed,{observed:['0',null,null,null,null,null],completed:Array(6).fill(null),identity:null,digest:null,revision:'0',generation:null});
Object.assign(initial.state,{observed:{clock:'0'},completed:{},output:null});initial.stamp='0';
assert.deepEqual(o.progressSnapshot([initial],config,[tenant]).rows[0].completed,{});
assert.equal(assess(initial).ready,false,'INITIAL_IS_NOT_COMPLETED_CLINICAL_OUTPUT');
for(const observed of [{},{bootstrap:'0'},{clock:'0',settings:'3'}]){
 const pending=structuredClone(initial);pending.state.observed=observed;
 pending.typed.observed=['clock','settings','policy','activity','lifecycle','bootstrap'].map(k=>observed[k]??null);
 assert.deepEqual(o.progressSnapshot([pending],config,[tenant]).rows[0].observed,observed);
 assert.equal(o.assessDurable(pending,witness,config).ready,false);
}
for(const mutate of [
 r=>r.typed.contractDigest='0'.repeat(64),r=>r.typed.revision='1',r=>r.typed.identity='5'.repeat(64),
 r=>r.typed.generation='1',r=>r.typed.observed[0]=0,r=>r.typed.observed.pop(),
 r=>{r.typed.completed[0]='0';r.state.completed.clock='0';},r=>r.state.output={},
 r=>r.typed.arrayBounds=false,r=>r.typed.bodyMetadataAbsent=false,
 r=>r.typed.enabled=false,r=>r.typed.version=1,r=>r.state.observed.clock='00'
]){
 const bad=structuredClone(initial);mutate(bad);
 assert.throws(()=>o.progressSnapshot([bad],config,[tenant]),error=>{
  assert.equal(error.message,'M7_COMPLETION_TYPED_STATE');
  assert.equal(error.completionDiagnostic.rowIndex,0);
  assert(Object.values(error.completionDiagnostic.predicates).every(v=>typeof v==='boolean'));
  assert.equal(JSON.stringify(error.completionDiagnostic).includes(tenant),false);return true;
 });
 assert.equal(o.progressSnapshot([initial],config,[tenant]).rows[0].outputRevision,'0');
}
const partial=structuredClone(row);partial.typed.completed=[null,null,null,null,null,'17'];partial.state.completed={bootstrap:'17'};
assert.deepEqual(o.progressSnapshot([partial],config,[tenant]).rows[0].completed,{bootstrap:'17'});
assert.equal(o.assessDurable(partial,witness,config).ready,false);
assert(progressQuery.includes("jsonb_typeof(c.projection->0->'output') IN ('object','null')"),'SCALAR_OR_ABSENT_BODY_MUST_NOT_LOOK_INITIAL');
// Reintroduce the old completed-only reader: the canonical startup criterion
// fails with the historical error, then the actual implementation restores it.
const completedOnlyNeedle='typedState(row,config,true)';assert.equal(text.split(completedOnlyNeedle).length,2,'EXACT_INITIAL_ACCESSOR_ABLATION_TARGET');
const oldReader={exports:{}};Function('require','module',text.replace(completedOnlyNeedle,'typedState(row,config)'))(require,oldReader);
const initialCriterion=api=>assert.equal(api.progressSnapshot([initial],config,[tenant]).rows[0].outputRevision,'0');
initialCriterion(o);assert.throws(()=>initialCriterion(oldReader.exports),/M7_COMPLETION_TYPED_STATE/);initialCriterion(o);
console.log('RESTORED_GREEN canonical initial/partial/pending metadata, corrupt floors/output refused, completed-only regression red; no clinical completion manufactured');
// Optional exact archived runtime module: no database, no replacement reader.
if(process.env.M7_COMPLETION_WORK_STATE){
 const work=require(process.env.M7_COMPLETION_WORK_STATE);let values;
 const client={async query(sql,args){
  if(sql.startsWith('WITH locked'))return {rows:[{admitted:{tenant,projection:null,contract_digest:row.typed.contractDigest,work_version:0,has_output:false}}]};
  if(sql.startsWith('UPDATE'))values=args;return {command:sql==='COMMIT'?'COMMIT':undefined};
 },release(){}};
 (async()=>{
  await work.admit({pool:{connect:async()=>client},observeBackend:async()=>{},table:ns.checkpoint+'.tenant_consumer_checkpoint',consumer:config.consumer,digest:row.typed.contractDigest,legacyDigest:'legacy',tenants:[tenant]});
  const state=work.state({work_version:2,work_observed:values[3],work_completed:values[4],work_observed_at:values[5],work_pending_at:values[6],work_due_at:values[7],work_enabled:values[9],work_activity_enabled:values[10],work_lifecycle_enabled:values[11]});
  const actual=structuredClone(initial);actual.state={kind:state.kind,observed:state.observed,completed:state.completed,output:null};
  Object.assign(actual.typed,{observed:values[3],completed:values[4],identity:values[12],digest:values[13],revision:String(values[14]),generation:values[15],enabled:values[9]});
  assert.deepEqual(actual.state.observed,{});assert.deepEqual(actual.state.completed,{});
  assert.equal(o.progressSnapshot([actual],config,[tenant]).rows[0].outputRevision,'0');
  assert.equal(o.assessDurable(actual,witness,config).ready,false);
  assert.throws(()=>oldReader.exports.progressSnapshot([actual],config,[tenant]),/M7_COMPLETION_TYPED_STATE/);
  console.log('RESTORED_GREEN actual pinned work-state.admit/state -> progressSnapshot; injected SQL boundary, native SQL UNMEASURED');
 })().catch(error=>{console.error(error);process.exitCode=1;});
}
