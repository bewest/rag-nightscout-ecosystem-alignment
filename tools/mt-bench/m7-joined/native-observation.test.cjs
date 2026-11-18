"use strict";
const test=require('node:test'),assert=require('node:assert/strict'),oracle=require('./completed-oracle.cjs'),native=require('./native-observation.cjs');
const {config,row,witness,clients,evaluator,realtime,binding}=require('./native-observation-fixture.cjs');
const tenant=row.tenant;
const assess=(r=row,w=witness)=>oracle.assess(r,w,clients,2,config),green=()=>assert.equal(assess().ready,true);
test('native coverage is independent of public stamp and retained output floor',()=>{green();const result=assess();assert.equal(result.completedInputFloor,'2');assert.equal(result.outputInputFloor,'1');assert.equal(result.outputRevision,1);assert.equal(result.nativeCoverage.acceptedPosition,'0/200');assert.equal(result.observedClock,undefined);});
for(const [name,change,code]of [
 ['missing native',r=>delete r.native,'NATIVE_STATE'],['copied input rows',r=>r.native.compact=false,'NATIVE_STATE'],['wrong source system',r=>r.native.stream.source_identity={...r.native.stream.source_identity,system_id:'2'},'NATIVE_SOURCE'],
 ['wrong restore',r=>r.native.currentRestore='2','NATIVE_SOURCE'],['wrong generation',r=>r.native.stream.generation='b'.repeat(32)+':1','NATIVE_SOURCE'],['floor mismatch',r=>r.native.persistedFloor='1','NATIVE_STATE'],
 ['unsafe floor',r=>r.native.inputFloor=r.native.persistedFloor='9007199254740992','NATIVE_STATE'],['bad native position',r=>r.native.stream.accepted_position='9007199254740993','NATIVE_POSITION'],
 ['raw coverage loss',r=>r.native.raw.base='5','NATIVE_RAW'],['old clinical coverage',r=>{r.state.completed={bootstrap:'1'};r.typed.completed=[null,null,null,null,null,'1'];},'PENDING'],
 ['old completed row',r=>r.typed.inputFloor='1','OUTPUT_CLOCK'],['wrong retained floor pair',r=>r.state.output.result.checkpoint=0,'OUTPUT_CLOCK'],['output ahead',r=>{r.state.output.result.checkpoint=3;r.state.output.inputCheckpoint=3;},'OUTPUT_CLOCK'],
 ['stale output restore',r=>{r.state.output.restoreGeneration='2';r.typed.generation='2';},'NATIVE_FENCE'],['wrong reader config',r=>r.reader.nativeConfigurationSha256='0'.repeat(64),'READER_MISMATCH'],
 ['missing marker',r=>r.stored=[],'STORED'],['wrong clinical frame',r=>r.state.output.frame.sgvs[0].mgdl=99,'FRAME']
])test(name+' refuses; restoration passes',()=>{const bad=structuredClone(row);change(bad);assert.equal(assess(bad).code,'M7_COMPLETION_'+code);green();});
test('explicit invalidation supplies no accepted coverage until identity returns',()=>{const invalid=structuredClone(row);invalid.native.stream=null;assert.equal(assess(invalid).code,'M7_COMPLETION_NATIVE_INVALIDATED');assert.throws(()=>oracle.progressSnapshot([invalid],config,[tenant]),/NATIVE_INVALIDATED/);green();});
test('freeze accepted target while later input remains pending',()=>{const newer=structuredClone(row);newer.native.inputFloor=newer.native.persistedFloor='3';newer.state.observed={bootstrap:'3'};newer.typed.observed=[null,null,null,null,null,'3'];const target={...witness,nativeTarget:native.snapshot(row,config)};assert.equal(assess(newer,target).ready,true);assert.equal(assess(newer).code,'M7_COMPLETION_PENDING');const wrong=structuredClone(target);wrong.nativeTarget.generation='b'.repeat(32)+':1';assert.equal(assess(newer,wrong).code,'M7_COMPLETION_NATIVE_FENCE');green();});
test('metadata observes source, due, pending and raw identity without copied cache/body',()=>{const metadata=oracle.progressSnapshot([row],config,[tenant]);assert.equal(metadata.rows[0].pendingAt,null);assert.equal(metadata.rows[0].dueAt,10000);assert.deepEqual(metadata.rows[0].native,native.progress(row,config));const query=oracle.progressQuery(config,[tenant]);assert(query.startsWith('SELECT '));assert(query.includes('pg_control_system()'));assert(query.includes('i.checkpoint::text'));assert(query.includes('c.checkpoint::text'));assert(query.includes('work_pending_at::text'));assert(!query.includes('jsonb_agg(e.doc)'));assert(!query.includes("THEN (c.projection->0->'output')"));});
test('mandatory native configuration cannot silently downgrade to clock reader',()=>{const bad=structuredClone(config);delete bad.native;assert.throws(()=>oracle.prepare(bad),/NATIVE_BINDING/);assert.throws(()=>oracle.source({...evaluator,pgstream:{...evaluator.pgstream,recovery:null}},realtime,binding),/NATIVE_SOURCE/);const changed=structuredClone(config);changed.native.slot='other';assert.throws(()=>oracle.prepare(changed),/NATIVE_BINDING/);});
test('actual native source validator ablation defeats the wrong-source criterion',()=>{
 const fs=require('node:fs'),source=fs.readFileSync(require.resolve('./native-observation.cjs'),'utf8'),needle='canonical(s.source_identity)!==canonical(v.actualSource)';
 assert.equal(source.split(needle).length,2);const mod={exports:{}};Function('require','module',source.replace(needle,'false'))(require,mod);
 const bad=structuredClone(row);bad.native.stream.source_identity={...bad.native.stream.source_identity,system_id:'2'};
 const rejects=api=>assert.throws(()=>api.snapshot(bad,config),/NATIVE_SOURCE/);
 rejects(native);assert.throws(()=>rejects(mod.exports),assert.AssertionError);rejects(native);green();
});

test('snapshot boundary reset keeps source-bound accepted coverage separate',()=>{
 const target={...witness,nativeTarget:native.snapshot(row,config)},reset=structuredClone(row);
 reset.native.stream.snapshot_position='0/0';reset.native.stream.accepted_position='0/300';
 reset.native.inputFloor=reset.native.persistedFloor='3';reset.state.observed={bootstrap:'3'};reset.typed.observed=[null,null,null,null,null,'3'];
 assert.equal(assess(reset,target).ready,true);assert.equal(assess(reset).code,'M7_COMPLETION_PENDING');
 const regressed=structuredClone(reset);regressed.native.stream.accepted_position='0/100';assert.equal(assess(regressed,target).code,'M7_COMPLETION_NATIVE_FENCE');
 const absent=structuredClone(reset);absent.native.stream.accepted_position=null;assert.equal(assess(absent,target).code,'M7_COMPLETION_NATIVE_FENCE');
 const badTarget=structuredClone(target);badTarget.nativeTarget.snapshotPosition='invalid';assert.equal(assess(reset,badTarget).code,'M7_COMPLETION_NATIVE_POSITION');
 assert.equal(assess(reset,target).ready,true);green();
});
test('accepted coverage fence omission makes the regression criterion red; restoration passes',()=>{
 const fs=require('node:fs'),source=fs.readFileSync(require.resolve('./native-observation.cjs'),'utf8'),needle='target.acceptedPosition!==null&&(value.acceptedPosition===null||position(value.acceptedPosition)<position(target.acceptedPosition))';
 assert.equal(source.split(needle).length,2);const mod={exports:{}};Function('require','module',source.replace(needle,'false'))(require,mod);
 const target={...witness,nativeTarget:native.snapshot(row,config)},bad=structuredClone(row);bad.native.stream.snapshot_position='0/0';bad.native.stream.accepted_position='0/100';
 const rejects=api=>assert.equal(api.assess(bad,target,config).code,'M7_COMPLETION_NATIVE_FENCE');
 rejects(native);assert.throws(()=>rejects(mod.exports),assert.AssertionError);rejects(native);green();
});

test('native receipt cutover digest is read as the contract; a malformed digest refuses',()=>{
 const cut=structuredClone(row);cut.typed.contractDigest='c'.repeat(64);assert.equal(assess(cut).ready,true);
 const bad=structuredClone(row);bad.typed.contractDigest='not-a-digest';assert.equal(assess(bad).code,'M7_COMPLETION_TYPED_STATE');green();
});
