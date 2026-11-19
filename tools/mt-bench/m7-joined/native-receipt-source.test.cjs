'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const source=require('./native-receipt-source.cjs'),oracle=require('./completed-oracle.cjs'),observation=require('./native-observation.cjs');
const original=require('./native-observation-fixture.cjs');
const copy=x=>JSON.parse(JSON.stringify(x));
const root=process.env.M7_NATIVE_RECEIPT_CORE;
function fixture(core=root){
 const f=copy(original),e=f.evaluator;
 const binding={namespace:e.postgres.namespaces.checkpoint,lifecycleNamespace:e.trustedWorker.activity,consumer:e.consumer,source:f.row.native.actualSource,generation:e.pgstream.generation};
 const selected=require(path.join(core,'lib/tenant-lifecycle/native-selection')).create(binding);
 const inputs={evaluator:e,realtime:f.realtime,operation:{namespace:binding.lifecycleNamespace,nativeSelection:binding},checkpoints:[{namespace:binding.namespace,consumer:binding.consumer+'-completed',digest:selected.contractDigest}]};
 const receipt=source.capture(core,inputs);
 f.config=oracle.source(e,f.realtime,f.binding,receipt);f.row.reader=f.config.binding;f.row.typed.contractDigest=selected.contractDigest;
 return {...f,inputs,receipt,selected};
}
test('historical native and non-native source configs keep their contract',()=>{
 assert.equal(oracle.assess(original.row,original.witness,original.clients,2,original.config).ready,true);
 const e=copy(original.evaluator);e.pgstream={};
 const config=oracle.source(e,original.realtime,original.binding);
 assert.equal(config.native,undefined);
 const fs=require('node:fs'),os=require('node:os'),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'legacy-receipt-state-'));
 try{for(const [role,value]of [['evaluator',e],['realtime',original.realtime]]){fs.mkdirSync(path.join(tmp,role));fs.writeFileSync(path.join(tmp,role,'config.json'),JSON.stringify(value));}assert.equal(source.captureFiles('/unused-core',tmp),null);}finally{fs.rmSync(tmp,{recursive:true,force:true});}
});
test('selected shipping native API drives clinical and durable readers',{skip:!root},()=>{
 const f=fixture();
 assert.equal(oracle.assess(f.row,f.witness,f.clients,2,f.config).ready,true);
 assert.equal(oracle.progressSnapshot([f.row],f.config,[f.row.tenant]).rows.length,1);
 assert.equal(f.config.native.receipt.contractDigest,f.selected.contractDigest);
 assert.notEqual(f.config.binding.nativeConfigurationSha256,original.config.binding.nativeConfigurationSha256);
});
test('existing exported state files produce the same source receipt',{skip:!root},()=>{
 const fs=require('node:fs'),os=require('node:os'),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'native-receipt-state-')),f=fixture();
 try{
  for(const [name,value] of Object.entries({'evaluator/config.json':f.inputs.evaluator,'realtime/config.json':f.inputs.realtime,'evaluator/operation.json':f.inputs.operation,'admin/config.json':{provisioning:{checkpoints:f.inputs.checkpoints}}})){
   fs.mkdirSync(path.dirname(path.join(tmp,name)),{recursive:true});fs.writeFileSync(path.join(tmp,name),JSON.stringify(value),{mode:0o600});
  }
  assert.deepEqual(source.captureFiles(root,tmp),f.receipt);
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
});
test('current selected source cannot be downgraded by dropping its operation declaration',{skip:!root},()=>{
 const f=fixture();delete f.inputs.operation.nativeSelection;
 assert.throws(()=>source.capture(root,f.inputs),/M7_COMPLETION_RECEIPT_SOURCE/);
});
test('foreign and malformed actual declarations or provisioning plans refuse',{skip:!root},()=>{
 const f=fixture();
 for(const alter of [x=>x.operation.nativeSelection.consumer='evaluator-foreign',x=>x.operation.nativeSelection.source.slot='foreign_slot',x=>x.operation.nativeSelection.generation='b'.repeat(32),x=>x.operation.nativeSelection.namespace='foreign_checkpoint',x=>x.operation.nativeSelection.lifecycleNamespace='foreign_control',x=>x.operation.nativeSelection.source.timeline=0,x=>x.checkpoints[0].digest='9'.repeat(64),x=>x.checkpoints.push(copy(x.checkpoints[0]))]){
  const bad=copy(f.inputs);alter(bad);assert.throws(()=>source.capture(root,bad));
 }
 assert.equal(source.capture(root,f.inputs).contractDigest,f.receipt.contractDigest);
});
test('current typed reader rejects legacy and foreign row contracts then restores',{skip:!root},()=>{
 const f=fixture();
 for(const digest of [original.row.typed.contractDigest,'9'.repeat(64),'invalid']){
  const bad=copy(f.row);bad.typed.contractDigest=digest;
  assert.equal(oracle.assess(bad,f.witness,f.clients,2,f.config).code,'M7_COMPLETION_TYPED_STATE');
  assert.throws(()=>oracle.progressSnapshot([bad],f.config,[bad.tenant]),/M7_COMPLETION_TYPED_STATE/);
 }
 assert.equal(oracle.assess(f.row,f.witness,f.clients,2,f.config).ready,true);
});
test('receipt selection and digest are bound to source documents and reader hash',{skip:!root},()=>{
 const f=fixture();
 for(const alter of [x=>delete x.native.receipt,x=>x.native.receipt.contractDigest='9'.repeat(64),x=>x.native.receipt.selection.binding.consumer='evaluator-foreign',x=>x.native.receipt.selection.binding.source.slot='foreign_slot']){
  const bad=copy(f.config);alter(bad);assert.throws(()=>oracle.prepare(bad));
 }
 const e=copy(f.evaluator);e.pageSize=123;
 assert.throws(()=>oracle.source(e,f.realtime,f.binding,f.receipt),/M7_COMPLETION_NATIVE_RECEIPT/);
 const bad=copy(f.row);bad.native.actualSource.system_id='456';bad.native.stream.source_identity.system_id='456';
 assert.equal(oracle.assess(bad,f.witness,f.clients,2,f.config).code,'M7_COMPLETION_NATIVE_SOURCE');
 assert.equal(observation.snapshot(f.row,f.config).source.system_id,f.row.native.actualSource.system_id);
});
test('legacy selected source uses its own API digest, not current codec constants',{skip:!process.env.M7_NATIVE_RECEIPT_LEGACY_CORE},()=>{
 const f=fixture(process.env.M7_NATIVE_RECEIPT_LEGACY_CORE);
 assert.equal(f.receipt.contractDigest,original.row.typed.contractDigest);
 assert.equal(oracle.assess(f.row,f.witness,f.clients,2,f.config).ready,true);
});
