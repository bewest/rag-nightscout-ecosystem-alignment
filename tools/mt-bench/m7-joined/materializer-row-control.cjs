'use strict';
// Apply retained synthetic wal2json payloads to the actual shipping state module.
// No database/listener; this does not certify SQL commit/ACK or deployed recovery.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createRequire}=require('node:module');
const limits={maxRows:256,maxBytes:1048576};
const restore=value=>JSON.parse(JSON.stringify(value));
function exercise(api,events){
 const groups=[...events.reduce((map,e)=>{if(!map.has(e.xid))map.set(e.xid,[]);map.get(e.xid).push(e);return map;},new Map()).values()].slice(0,4);
 assert.deepEqual(groups.map(g=>g[0].action),['I','U','U','D']);
 const first=groups.map(g=>g[0]),nativeDoc=JSON.parse(first[0].columns.find(c=>c.name==='doc').value);
 assert.equal(typeof nativeDoc.extension,'string');assert(nativeDoc.extension.length>8192,'NATIVE_TOAST_FIXTURE');
 assert(!first[1].columns.some(c=>c.name==='doc'),'NATIVE_UNCHANGED_TOAST_FIXTURE');
 assert(first[3].identity.some(c=>c.name==='_id'),'NATIVE_DELETE_IDENTITY');
 let saved=api.bootstrap(null,{checkpoint:0,signature:{stamp:0,deleted:0},rows:[]},limits);
 for(const[index,group]of groups.entries()){
  const before=api.output(saved);
  for(const data of group){
   const event=api.eventOf('entries',data);saved=api.stage(saved,event,limits);
   assert.deepEqual(api.output(saved),before,'UNSEALED_COHORT_VISIBLE');
   assert.deepEqual(api.stage(restore(saved),event,limits),saved,'REDELIVERY_NOT_IDEMPOTENT');
  }
  const data=group[group.length-1];
  saved=api.seal(restore(saved),{xid:data.xid,lsn:data.lsn,floor:index+1,deleted:data.action==='D'?index+1:0},limits);
  const output=api.output(restore(saved)),rows=output.rows;
  if(data.action==='D'){assert.equal(rows.length,0,'DELETE_NOT_APPLIED');assert.equal(output.stats.dataSize,0,'DELETED_STATS_RETAINED');}
  else{
   assert.equal(rows.length,1,'NATIVE_ROW_LOST');
   assert.equal(rows[0].document.extension,nativeDoc.extension,'EXTENSION_LOST');
   assert.equal(rows[0].document.sgv,index===2?101:100,'WRONG_CLINICAL_VALUE');
   assert.equal(rows[0].ordinal,index?2:1,'TOAST_ORDINAL_LOST');
   const bytes=data.columns.find(c=>c.name==='storage_bytes');
   assert(bytes,'NATIVE_STORAGE_PROJECTION_FIXTURE');assert.equal(output.stats.dataSize,Number(bytes.value),'STORAGE_PROJECTION_LOST');
  }
 }
 // Independently hold two committed transactions. A seal must apply only its
 // own cohort, and a snapshot floor must not erase a later staged cohort.
 const one=restore(first[0]),two=restore(first[0]);
 one.xid=10001;one.lsn='0/10000000';two.xid=10002;two.lsn='0/10000100';
 const secondDoc=JSON.parse(two.columns.find(c=>c.name==='doc').value);secondDoc._id='second';two.columns.find(c=>c.name==='doc').value=JSON.stringify(secondDoc);two.columns.find(c=>c.name==='_id').value='second';
 let mixed=api.bootstrap(null,{checkpoint:10,signature:{stamp:10,deleted:0},rows:[]},limits);
 mixed=api.stage(mixed,api.eventOf('entries',one),limits);mixed=api.stage(mixed,api.eventOf('entries',two),limits);
 mixed=api.seal(restore(mixed),{xid:one.xid,lsn:'0/10000080',floor:11,deleted:0},limits);
 assert.deepEqual(api.output(mixed).rows.map(r=>r.document._id),['synthetic'],'CROSS_XID_PARTIAL_COHORT');
 mixed=api.bootstrap(restore(mixed),{checkpoint:11,signature:{stamp:11,deleted:0},rows:mixed.rows.map(row=>({domain:row.domain,document:row.doc,ordinal:row.ordinal,storageBytes:row.storageBytes}))},limits);
 mixed=api.seal(restore(mixed),{xid:two.xid,lsn:'0/10000180',floor:12,deleted:0},limits);
 assert.deepEqual(api.output(mixed).rows.map(r=>r.document._id).sort(),['second','synthetic'],'BOOTSTRAP_LOST_FUTURE_COHORT');
 const copies=events.filter(e=>e.action==='I'&&e.columns.some(c=>c.name==='doc'&&typeof c.value==='string'&&JSON.parse(c.value)._id.startsWith('copy-')));
 assert.equal(copies.length,8,'NATIVE_COPY_FIXTURE');assert.equal(new Set(copies.map(e=>e.lsn)).size,1,'NATIVE_EQUAL_LSN_FIXTURE');
 let bulk=api.bootstrap(null,{checkpoint:0,signature:{stamp:0,deleted:0},rows:[]},limits);
 for(const data of copies){const event=api.eventOf('entries',data);bulk=restore(api.stage(bulk,event,limits));assert.equal(api.output(bulk).rows.length,0,'COPY_PARTIAL_VISIBLE');}
 assert.equal(bulk.staged.length,8,'EQUAL_LSN_ROWS_LOST');
 for(const data of events.filter(e=>e.xid===copies[0].xid&&e.action!=='I'))bulk=api.stage(bulk,api.eventOf('entries',data),limits);
 bulk=api.seal(bulk,{xid:copies[0].xid,lsn:copies[0].lsn,floor:1,deleted:0},limits);
 assert.deepEqual(api.output(bulk).rows.map(r=>r.document._id).sort(),Array.from({length:8},(_,i)=>'copy-'+i),'EQUAL_LSN_ROWS_LOST');
 return {nativeActions:first.map(e=>e.action),properties:['durable-serialization boundary','unsealed invisible','duplicate idempotence','omitted TOAST retained','extension preserved','identity delete','XID isolation','snapshot retains later cohort','native COPY equal-LSN rows']};
}
async function receipt(core,data,receiver,failCommit=false){
 const api=require(path.join(core,'lib/storage/clinical-stream-state.js')),sql=require(path.join(core,'lib/storage/clinical-stream-sql.js'));
 const digest='a'.repeat(64),logs=[];let commit,committed=null,staged,settled=false,released=false;
 const barrier=new Promise(resolve=>{commit=resolve;});
 const client={release(){released=true;},async query(text,values){
  logs.push(text.startsWith('SELECT')?'SELECT':text.startsWith('UPDATE')?'UPDATE':text);
  if(text.startsWith('SELECT'))return {rows:[{projection:[api.empty()],contract_digest:digest}]};
  if(text.startsWith('UPDATE')){staged=JSON.parse(values[2]);return {rowCount:1};}
  if(text==='COMMIT'){await barrier;if(failCommit)throw Error('COMMIT_REFUSED');committed=restore(staged);return {command:'COMMIT'};}
  return {};
 }};
 const config=require('./materializer-default-control.cjs').fixture(),routes=require(path.join(core,'lib/pgstream/evaluator.js')).routes(config);
 let clinicalCalls=0;
 const receive=receiver.create({routes,store:{},onInput:()=>{clinicalCalls++;return new Promise(()=>{});},onSchema:async()=>{},clinical:{accept:(tenant,event,domain)=>sql.accept({pool:{connect:async()=>client},observeBackend:async()=>{},table:'synthetic_checkpoint.tenant_consumer_checkpoint',consumer:'evaluator-test',tenant,data:event,domain,snapshotDigest:digest,...limits})}});
 const input={Data:{...data,schema:config.namespaces.entries}};
 const pending=receive(input).then(value=>{settled=true;return value;});
 try{
  for(let turn=0;turn<100&&!logs.includes('COMMIT');turn++)await Promise.resolve();
  assert(logs.includes('COMMIT'),'RECEIPT_DID_NOT_REACH_COMMIT');
  assert.equal(settled,false,'RAW_ACK_BEFORE_COMMIT');commit();
  if(failCommit){await assert.rejects(pending,/COMMIT_REFUSED/);assert(logs.includes('ROLLBACK'),'FAILED_COMMIT_NOT_ROLLED_BACK');assert.equal(committed,null);}
  else{await pending;assert.equal(committed[0].staged.length,1,'RAW_PAYLOAD_NOT_DURABLE');assert.equal(committed[0].ready,false,'RAW_RECEIPT_IS_NOT_BOOTSTRAP');}
  assert.equal(released,true,'RECEIPT_CONNECTION_LEAK');assert.equal(clinicalCalls,0,'RAW_RECEIPT_RAN_CLINICAL_IO');
 }finally{commit();await pending.catch(()=>{});}
}
async function run(core,capture){
 const file=path.join(core,'lib/storage/clinical-stream-state.js'),source=fs.readFileSync(file,'utf8'),events=fs.readFileSync(capture,'utf8').trim().split('\n').map(JSON.parse);
 const api=require(file),result=exercise(api,events),controls=[];
 for(const[name,from,to,symptom]of [
  ['equal-LSN-drop','at<position(state.last)','at<=position(state.last)',/EQUAL_LSN_ROWS_LOST/],
  ['lost-deletes','state.staged.push(event);',"if(event.action!=='D')state.staged.push(event);",/DELETE_NOT_APPLIED/],
  ['cross-XID-cohort','const cohort=state.staged.filter(e=>e.xid===transaction);','const cohort=state.staged;',/CROSS_XID_PARTIAL_COHORT/]
 ]){
  assert.equal(source.split(from).length,2,'ABLATION_SOURCE_MISMATCH:'+name);
  const module={exports:{}};
  vm.runInThisContext('(function(require,module,exports){'+source.replace(from,to)+'\n})',{filename:file})(createRequire(file),module,module.exports);
  assert.throws(()=>exercise(module.exports,events),symptom,'ABLATION_DID_NOT_DETECT:'+name);
  exercise(api,events);controls.push(name);
 }
 const receiverFile=path.join(core,'lib/pgstream/receiver.js'),receiverSource=fs.readFileSync(receiverFile,'utf8'),receiver=require(receiverFile);
 await receipt(core,events[0],receiver);await receipt(core,events[0],receiver,true);
 const from='await clinical.accept(row.tenant_id,data,route.domain,store);';assert.equal(receiverSource.split(from).length,2,'RECEIPT_ABLATION_SOURCE_MISMATCH');
 const broken={exports:{}};vm.runInThisContext('(function(require,module,exports){'+receiverSource.replace(from,'clinical.accept(row.tenant_id,data,route.domain,store);')+'\n})',{filename:receiverFile})(createRequire(receiverFile),broken,broken.exports);
 await assert.rejects(receipt(core,events[0],broken.exports),/RAW_ACK_BEFORE_COMMIT/);await receipt(core,events[0],receiver);controls.push('raw-ACK-before-commit');
 return {verdict:'PASS',scope:'actual-module state/native payloads and mocked SQL commit boundary; deployed recovery unmeasured',...result,controls};
}
module.exports={run,exercise};
if(require.main===module){(async()=>{if(process.argv.length!==4)throw Error('Usage: node materializer-row-control.cjs APP_WORKTREE DECODER_JSONL');console.log(JSON.stringify(await run(path.resolve(process.argv[2]),path.resolve(process.argv[3]))));})().catch(error=>{console.error(error.stack);process.exitCode=1;});}
