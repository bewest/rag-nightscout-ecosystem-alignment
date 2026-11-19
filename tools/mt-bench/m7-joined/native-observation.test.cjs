"use strict";
const test=require('node:test'),assert=require('node:assert/strict'),oracle=require('./completed-oracle.cjs'),native=require('./native-observation.cjs');
const {config,row,witness,clients,evaluator,realtime,binding}=require('./native-observation-fixture.cjs');
const tenant=row.tenant;
const assess=(r=row,w=witness)=>oracle.assess(r,w,clients,2,config),green=()=>assert.equal(assess().ready,true);
test('native lifecycle codec and domain refuse legacy or incompatible typed receipts',()=>{
 const {createHash}=require('node:crypto'),digest=fields=>createHash('sha256').update(JSON.stringify(fields)).digest('hex');
 const fields=['evaluator-work-v2','synthetic_checkpoint','evaluator-sample'];
 for(const value of [digest(fields),digest([...fields,'unsupported-codec','positive-int8-complete-pair-max-4611686018427387902-v1']),digest([...fields,'canonical-maintenance-active-plus2-v1','unsupported-domain'])]){
  const bad=structuredClone(row);bad.typed.contractDigest=value;
  assert.equal(assess(bad).code,'M7_COMPLETION_TYPED_STATE');
  green();
 }
 const corrupt=structuredClone(row);corrupt.typed.completed[5]='3';
 assert.equal(assess(corrupt).code,'M7_COMPLETION_TYPED_STATE');green();
});
test('legacy clock receipts retain their exact contract and refuse the native digest',()=>{
 const {createHash}=require('node:crypto'),legacy=structuredClone(config);delete legacy.native;
 const value=structuredClone(row);value.reader=legacy.binding;
 Object.assign(value.typed,{contractDigest:createHash('sha256').update(JSON.stringify(['evaluator-work-v2','synthetic_checkpoint','evaluator-sample'])).digest('hex'),observed:[witness.stamp,null,null,null,null,null],completed:[witness.stamp,null,null,null,null,null]});
 Object.assign(value.state,{observed:{clock:witness.stamp},completed:{clock:witness.stamp}});value.state.output.inputCheckpoint=witness.stamp;
 const legacyAssess=()=>oracle.assess(value,witness,clients,2,legacy);
 assert.equal(legacyAssess().ready,true);
 const saved=value.typed.contractDigest;value.typed.contractDigest=row.typed.contractDigest;
 assert.equal(legacyAssess().code,'M7_COMPLETION_TYPED_STATE');value.typed.contractDigest=saved;assert.equal(legacyAssess().ready,true);
});
test('native receipt agrees with the pinned source selection module',{skip:!process.env.M7_COMPLETION_NATIVE_SELECTION},()=>{
 const selection=require(process.env.M7_COMPLETION_NATIVE_SELECTION);
 for(const suffix of ['', '_other']){
  const e=structuredClone(evaluator),r=structuredClone(realtime);e.postgres.namespaces.checkpoint+=suffix;e.consumer+=suffix;
  Object.assign(r.completedOutput,{namespace:e.postgres.namespaces.checkpoint,consumer:e.consumer});
  const selected=oracle.source(e,r,binding),actual=selection.create({namespace:selected.checkpoint,lifecycleNamespace:selected.native.lifecycle,consumer:selected.native.inputConsumer,generation:selected.native.generation,source:row.native.actualSource});
  assert.equal(oracle.expectedContractDigest(selected),actual.contractDigest);
  const value=structuredClone(row);value.reader=selected.binding;value.typed.contractDigest=actual.contractDigest;
  assert.equal(oracle.assess(value,witness,clients,2,selected).ready,true);
 }
 const bad=structuredClone(config);delete bad.native;assert.throws(()=>oracle.expectedContractDigest(bad),/NATIVE_BINDING/);
});
test('restoring the legacy-only digest calculation rejects the current native receipt',()=>{
 const fs=require('node:fs'),source=fs.readFileSync(require.resolve('./completed-oracle.cjs'),'utf8'),needle="if(config.native)fields.push('canonical-maintenance-active-plus2-v1','positive-int8-complete-pair-max-4611686018427387902-v1');";
 assert.equal(source.split(needle).length,2);const mod={exports:{}};Function('require','module',source.replace(needle,''))(require,mod);
 const criterion=api=>assert.equal(api.assess(row,witness,clients,2,config).ready,true);
 criterion(oracle);assert.throws(()=>criterion(mod.exports),assert.AssertionError);assert.equal(mod.exports.assess(row,witness,clients,2,config).code,'M7_COMPLETION_TYPED_STATE');criterion(oracle);
});
test('native coverage is independent of public stamp and retained output floor',()=>{green();const result=assess();assert.equal(result.completedInputFloor,'2');assert.equal(result.outputInputFloor,'1');assert.equal(result.outputRevision,1);assert.equal(result.nativeCoverage.acceptedPosition,'0/200');assert.equal(result.observedClock,undefined);});
for(const [name,change,code]of [
 ['missing native',r=>delete r.native,'NATIVE_STATE'],['copied input rows',r=>r.native.compact=false,'NATIVE_STATE'],['wrong source system',r=>r.native.stream.source_identity={...r.native.stream.source_identity,system_id:'2'},'NATIVE_SOURCE'],
 ['wrong restore',r=>r.native.currentRestore='2','NATIVE_SOURCE'],['wrong generation',r=>r.native.stream.generation='b'.repeat(32)+':1','NATIVE_SOURCE'],['floor mismatch',r=>r.native.persistedFloor='1','NATIVE_STATE'],
 ['unsafe floor',r=>r.native.inputFloor=r.native.persistedFloor='9007199254740992','NATIVE_STATE'],['bad native position',r=>r.native.stream.accepted_position='9007199254740993','NATIVE_POSITION'],
 ['raw coverage loss',r=>r.native.raw.base='5','NATIVE_RAW'],['old clinical coverage',r=>{r.state.completed={bootstrap:'1'};r.typed.completed=[null,null,null,null,null,'1'];},'PENDING'],
 ['old completed row',r=>r.typed.inputFloor='1','OUTPUT_CLOCK'],['wrong retained floor pair',r=>r.state.output.result.checkpoint=0,'OUTPUT_CLOCK'],['output ahead',r=>{r.state.output.result.checkpoint=3;r.state.output.inputCheckpoint=3;},'OUTPUT_CLOCK'],
 ['stale output restore',r=>{r.state.output.restoreGeneration='2';r.typed.generation='2';},'NATIVE_FENCE'],['wrong reader kind',r=>r.reader.kind='evaluator-work-v1','READER_MISMATCH'],
 ['missing marker',r=>r.stored=[],'STORED'],['wrong clinical frame',r=>r.state.output.frame.sgvs[0].mgdl=99,'FRAME']
])test(name+' refuses; restoration passes',()=>{const bad=structuredClone(row);change(bad);assert.equal(assess(bad).code,'M7_COMPLETION_'+code);green();});
test('explicit invalidation supplies no accepted coverage until identity returns',()=>{const invalid=structuredClone(row);invalid.native.stream=null;assert.equal(assess(invalid).code,'M7_COMPLETION_NATIVE_INVALIDATED');green();});
test('freeze accepted target while later input remains pending',()=>{const newer=structuredClone(row);newer.native.inputFloor=newer.native.persistedFloor='3';newer.state.observed={bootstrap:'3'};newer.typed.observed=[null,null,null,null,null,'3'];const target={...witness,nativeTarget:native.snapshot(row,config)};assert.equal(assess(newer,target).ready,true);assert.equal(assess(newer).code,'M7_COMPLETION_PENDING');const wrong=structuredClone(target);wrong.nativeTarget.generation='b'.repeat(32)+':1';assert.equal(assess(newer,wrong).code,'M7_COMPLETION_NATIVE_FENCE');green();});
test('native source refuses an incomplete pgstream configuration',()=>{assert.throws(()=>oracle.source({...evaluator,pgstream:{...evaluator.pgstream,recovery:null}},realtime,binding),/NATIVE_SOURCE/);});
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

