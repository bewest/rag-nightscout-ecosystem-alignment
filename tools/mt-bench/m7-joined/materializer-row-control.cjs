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
async function receipt(core,data,receiver,failCommit=false,options={}){
 const api=require(path.join(core,'lib/storage/clinical-stream-state.js')),sql=options.sql||require(path.join(core,'lib/storage/clinical-stream-sql.js'));
 const original=options.saved||api.empty();
 const digest='a'.repeat(64),logs=[];let commit,committed=null,staged,settled=false,released=false,checkpoint=original.floor??0;
 const barrier=new Promise(resolve=>{commit=resolve;});
 const client={release(){released=true;},async query(text,values){
  logs.push(text.startsWith('SELECT')?'SELECT':text.startsWith('UPDATE')?'UPDATE':text);
  if(text.startsWith('SELECT')){const saved=restore(original);if(text.includes("projection->0)-'rows'"))delete saved.rows;return {rows:[{projection:[saved],contract_digest:digest,checkpoint:String(original.floor)}]};}
  if(text.startsWith('UPDATE')){staged=JSON.parse(values[2]);if(text.includes('(projection->0)||'))staged=[{...restore(original),...staged[0]}];if(text.includes('checkpoint=$5'))checkpoint=values[4];return {rowCount:1};}
  if(text==='COMMIT'){await barrier;if(failCommit)throw Error('COMMIT_REFUSED');committed=restore(staged);return {command:'COMMIT'};}
  return {};
 }};
 const config=require('./materializer-default-control.cjs').fixture(),routes=require(path.join(core,'lib/pgstream/evaluator.js')).routes(config);
 let clinicalCalls=0;
 const receive=receiver.create({routes,store:{},onInput:()=>{clinicalCalls++;return new Promise(()=>{});},onSchema:async()=>{},clinical:{accept:(tenant,event,domain)=>sql.accept({pool:{connect:async()=>client},observeBackend:async()=>{},table:'synthetic_checkpoint.tenant_consumer_checkpoint',consumer:'evaluator-test',tenant,data:event,domain,snapshotDigest:digest,...limits,...(options.maxBytes?{maxBytes:options.maxBytes}:{}),...(options.maxRows?{maxRows:options.maxRows}:{})})}});
 const input={Data:{...data,schema:config.namespaces.entries}};
 const pending=receive(input).then(value=>{settled=true;return value;});
 try{
  for(let turn=0;turn<100&&!logs.includes('COMMIT');turn++)await Promise.resolve();
  assert(logs.includes('COMMIT'),'RECEIPT_DID_NOT_REACH_COMMIT');
  assert.equal(settled,false,'RAW_ACK_BEFORE_COMMIT');commit();
  if(failCommit){await assert.rejects(pending,/COMMIT_REFUSED/);assert(logs.includes('ROLLBACK'),'FAILED_COMMIT_NOT_ROLLED_BACK');assert.equal(committed,null);}
  else{await pending;if(options.expectGap){assert.equal(committed[0].gap,'bytes','GAP_MARKER_NOT_DURABLE');assert.equal(checkpoint,original.floor,'GAP_ADVANCED_CLINICAL_COVERAGE');assert(Array.isArray(committed[0].rows)&&committed[0].rows.length===0,'GAP_CACHE_NOT_EVICTED');assert.equal(committed[0].rowCount,undefined,'GAP_SQL_RETAINED_OLD_CACHE_METADATA');assert.equal(committed[0].rowBytes,undefined,'GAP_SQL_RETAINED_OLD_CACHE_METADATA');assert.equal(committed[0].last,data.lsn,'GAP_POSITION_LOST');}else assert.equal(committed[0].staged.length,1,'RAW_PAYLOAD_NOT_DURABLE');assert.equal(committed[0].ready,false,'RAW_RECEIPT_IS_NOT_BOOTSTRAP');}
  assert.equal(released,true,'RECEIPT_CONNECTION_LEAK');assert.equal(clinicalCalls,0,'RAW_RECEIPT_RAN_CLINICAL_IO');
 }finally{commit();await pending.catch(()=>{});}
}
async function dueCoverage(core,start){
 start=start||require(path.join(core,'lib/server/serve/evaluator-runtime.js'));
 const tenant='11111111-1111-4111-8111-111111111111',identity='a'.repeat(64);let input=1,retained=0,revision=0;const commits=[];
 const value=()=>({checkpoint:retained,properties:{synthetic:retained},emitted:[],requested:[],signature:{stamp:retained,deleted:0}});
 const service=await start({tenants:[tenant],readCurrent:async()=>({tenant,identity}),create:async()=>({evaluate:async()=>{retained=input;return value();},evaluateTime:async()=>value(),close(){}}),durable:{begin:async()=>({clock:String(input)}),complete:async(tenant,current)=>{
  commits.push({observed:current.observed.clock,computed:current.result.checkpoint});return {pendingAt:Number(current.observed.clock)<input?1:null,changed:true,output:{tenant,identity,outputRevision:++revision,contentDigest:'b'.repeat(64),inputCheckpoint:current.result.checkpoint,result:current.result}};
 }},recoveryIntervalMs:1000,timeIntervalMs:1000,schedule:()=>({}),cancel(){},setTimer:()=>({}),clearTimer(){}});
 try{
  await service.acquire(tenant);input=2;await service.tick(tenant);
  for(const c of commits)assert(Number(c.observed)<=c.computed,'TIME_COMPLETED_UNCOMPUTED_INPUT');
  await service.acquire(tenant);assert.equal(commits.at(-1).observed,'2');assert.equal(commits.at(-1).computed,2);
 }finally{await service.close();}
}
async function invalidBootstrap(core,factory){
 const scope=require(path.join(core,'lib/storage/tenant-scope.js')),mode=scope.getTenancyMode();factory=factory||require(path.join(core,'lib/storage/postgres-durable-replay.js'));let pages=0,saved;
 const row={domain:'entries',id_kind:'string',doc:{_id:'synthetic-invalid',isValid:false,extension:{preserve:true}},stamp:null,ordinal:null,storage_bytes:123};
 const connection={snapshotTransaction:fn=>fn(),async query(text,values){
  if(text.includes('FOR UPDATE'))return {rows:[{checkpoint:'0',projection:null,contract_digest:null}]};
  if(text.includes('evaluator-change-signature'))return {rows:[{stamp:'0',deleted:'0'}]};
  if(text.includes('SELECT count(*)'))return {rows:[{row_count:'1',document_bytes:'100'}]};
  if(text.includes('information_schema.columns'))return {rows:[]};
  if(text.startsWith('UPDATE ')){saved=JSON.parse(values[3])[0];return {rowCount:1};}
  if(text.startsWith('SELECT domain,id_kind'))return {rows:pages++?[]:[restore(row)]};throw Error('UNEXPECTED_BOOTSTRAP_SQL');
 }};
 const replay=factory({connection,checkpointTable:'synthetic_checkpoint.tenant_consumer_checkpoint',clockTable:'synthetic_clock.tenant_write_clock',domains:{entries:'synthetic_entries.entries'},consumer:'evaluator-test',projectionVersion:'synthetic-v1',pageSize:2,maxRows:10,stream:true});
 scope.setTenancyMode('multi');
 try{await scope.withTenant('11111111-1111-4111-8111-111111111111',async()=>{
  const output=await replay.reconcile({maxRows:10,maxBytes:1048576,signature:true});
  assert.equal(output.stats.dataSize,123,'BOOTSTRAP_INVALID_STORAGE_BYTES_LOST');assert.equal(output.rows.length,0,'INVALID_ROW_VISIBLE');
  assert.deepEqual(saved.rows[0].doc.extension,{preserve:true},'BOOTSTRAP_INVALID_HISTORY_LOST');
 });}finally{scope.setTenancyMode(mode);}
}
async function schedulerFairness(core,start){
 start=start||require(path.join(core,'lib/pgstream/activity-scheduler.js')).start;
 let releaseA,enteredA,released=false,total=0,maxTotal=0,maxTenant=0;const active=new Map(),timers=[],runs=[];
 const held=new Promise(resolve=>{releaseA=resolve;}),entered=new Promise(resolve=>{enteredA=resolve;});
 const service=start({store:{nextDue:async()=>null,work:async()=>[],deliveries:async()=>[]},scan:async()=>{},concurrency:2,
  setTimer(fn,delay){const timer={fn,delay,unref(){}};timers.push(timer);return timer;},clearTimer(timer){const i=timers.indexOf(timer);if(i>=0)timers.splice(i,1);},
  run:async tenant=>{total++;active.set(tenant,(active.get(tenant)||0)+1);maxTotal=Math.max(maxTotal,total);maxTenant=Math.max(maxTenant,active.get(tenant));runs.push({tenant,released});try{if(tenant==='A'){enteredA();await held;}}finally{total--;active.set(tenant,active.get(tenant)-1);}},send:async()=>{}});
 async function flush(){for(let turn=0;turn<20;turn++){for(const timer of timers.splice(0))timer.fn();await new Promise(resolve=>setImmediate(resolve));}}
 try{
  service.wake('A');timers.shift().fn();await entered;service.wake('A');service.wake('B');await flush();
  assert(runs.some(r=>r.tenant==='B'&&!r.released),'IDLE_SLOT_MUST_RUN_NEIGHBOR_BEFORE_HELD_A_RELEASE');
  assert.equal(maxTenant,1,'CLINICAL_TENANT_EXECUTED_CONCURRENTLY');assert(maxTotal<=2,'CLINICAL_CONCURRENCY_EXCEEDED');
  released=true;releaseA();await flush();await service.drain();
  assert.equal(runs.filter(r=>r.tenant==='A').length,2,'NEW_INPUT_DURING_EVALUATION_LOST');
 }finally{released=true;releaseA();await flush();await service.drain();await service.close();}
}
async function schedulerRetry(core,start){
 start=start||require(path.join(core,'lib/pgstream/activity-scheduler.js')).start;let now=100;const timers=[],runs=[];
 const service=start({store:{nextDue:async()=>null,work:async()=>[],deliveries:async()=>[]},scan:async()=>{},concurrency:2,now:()=>now,
  setTimer(fn,delay){const timer={fn,at:now+delay,unref(){}};timers.push(timer);return timer;},clearTimer(timer){const i=timers.indexOf(timer);if(i>=0)timers.splice(i,1);},
  run:async tenant=>{runs.push({tenant,now});if(tenant==='A')throw Error('SYNTHETIC_POISON');},send:async()=>{}});
 async function flush(){for(let turn=0;turn<20;turn++){for(const timer of timers.filter(t=>t.at<=now)){timers.splice(timers.indexOf(timer),1);timer.fn();}await new Promise(resolve=>setImmediate(resolve));}}
 try{
  service.wake('A');await flush();const before=runs.filter(r=>r.tenant==='A').length;assert.equal(before,1,'INITIAL_RETRY_NOT_BOUNDED');
  service.wake('B');await flush();assert(runs.some(r=>r.tenant==='B'),'RETRY_BLOCKS_NEIGHBOR');
  assert.equal(runs.filter(r=>r.tenant==='A').length,before,'NEIGHBOR_INPUT_AMPLIFIES_POISON_RETRY');
  now=1099;await flush();assert.equal(runs.filter(r=>r.tenant==='A').length,before,'POISON_RETRY_TOO_EARLY');
  now=1100;await flush();assert.equal(runs.filter(r=>r.tenant==='A').length,before+1,'DUE_RETRY_LOST');
  service.wake('A');await flush();assert.equal(runs.filter(r=>r.tenant==='A').length,before+2,'TARGETED_NEW_INPUT_STUCK_BEHIND_RETRY');
 }finally{await service.close();}
}
async function schedulerRecovery(core,start){
 start=start||require(path.join(core,'lib/pgstream/activity-scheduler.js')).start;
 let releaseA,enteredA;const held=new Promise(resolve=>{releaseA=resolve;}),entered=new Promise(resolve=>{enteredA=resolve;}),timers=[],runs=[];
 const pending=new Map(Array.from({length:129},(_,i)=>{const tenant=String(i).padStart(3,'0');return [tenant,{tenant,pendingAt:1}];}));
 const service=start({store:{nextDue:async()=>null,work:async(limit,{after,exclude=[]})=>[...pending.values()].filter(r=>(!after||r.tenant>after)&&!exclude.includes(r.tenant)).slice(0,limit),deliveries:async()=>[]},scan:async()=>{},concurrency:2,
  setTimer(fn,delay){const timer={fn,delay,unref(){}};timers.push(timer);return timer;},clearTimer(timer){const i=timers.indexOf(timer);if(i>=0)timers.splice(i,1);},run:async tenant=>{runs.push(tenant);if(tenant==='000'){enteredA();await held;}pending.delete(tenant);},send:async()=>{}});
 async function flush(){for(let turn=0;turn<50;turn++){for(const timer of timers.splice(0))timer.fn();await new Promise(resolve=>setImmediate(resolve));}}
 const recovering=service.recover();
 try{await entered;await flush();assert(runs.includes('128'),'RECOVERY_PAGE_STARVED_BY_HELD_EARLIER_TENANT');}
 finally{releaseA();await recovering;await flush();await service.close();}
}
function gapCoverage(api,event){
 const row={domain:'entries',document:{_id:'retained-synthetic',sgv:100,extension:'x'.repeat(1000)},ordinal:null,storageBytes:100};
 const saved=api.bootstrap(null,{checkpoint:1,signature:{stamp:1,deleted:0},rows:[row]},limits),bytes=Buffer.byteLength(JSON.stringify(saved));
 const local={maxRows:1,maxBytes:bytes},metadata={...saved};delete metadata.rows;
 api.bound(saved,local);api.bound(metadata,local);
 assert.throws(()=>api.bound(metadata,{...local,maxBytes:bytes-1}),/CLINICAL_STREAM_BYTE_BOUND/,'METADATA_BYTE_BOUND_UNDERESTIMATED');
 let gap=api.recoverableGap(saved,'CLINICAL_STREAM_BYTE_BOUND',event.lsn,local);
 assert.equal(gap.ready,false,'GAP_MARKED_CLINICALLY_READY');assert(gap.floor===undefined||gap.floor===1,'GAP_ADVANCED_CLINICAL_COVERAGE');assert.equal(gap.rows.length,0,'GAP_CACHE_NOT_EVICTED');api.bound(gap,local);
 assert.throws(()=>api.output(restore(gap)),/CLINICAL_STREAM_BOOTSTRAP_REQUIRED/,'GAP_OUTPUT_VISIBLE');
 gap=api.stage(restore(gap),api.eventOf('entries',event),local);assert.equal(gap.staged.length,0,'GAP_RETAINS_OVERSIZE_COHORT');
 gap=api.seal(gap,{xid:event.xid,lsn:event.lsn,floor:2,deleted:0},local);assert(gap.floor===undefined||gap.floor===1,'GAP_SEAL_ADVANCED_CLINICAL_COVERAGE');
 assert.throws(()=>api.bootstrap(gap,{checkpoint:2,signature:{stamp:2,deleted:0},rows:[row,{...row,document:{_id:'other'}}]},local),/CLINICAL_STREAM_ROW_BOUND/,'OVERSIZE_BOOTSTRAP_MUST_REFUSE');
 assert.equal(gap.gap,'bytes','FAILED_BOOTSTRAP_ERASED_GAP');
 const restored=api.bootstrap(gap,{checkpoint:3,signature:{stamp:3,deleted:0},rows:[]},local);
 assert.equal(restored.gap,undefined,'SUCCESSFUL_BOOTSTRAP_RETAINS_GAP');assert.equal(api.output(restored).checkpoint,3);
 assert.throws(()=>api.recoverableGap(saved,'CLINICAL_STREAM_IDENTITY',event.lsn,local),/CLINICAL_STREAM_GAP_REASON/,'MALFORMED_EVENT_MUST_NOT_BECOME_GAP');
 return {saved,maxBytes:bytes,maxRows:1,expectGap:true};
}
async function migrationCompatibility(core,inspect){
 const catalogue=require(path.join(core,'lib/migrations/catalogue.js'));inspect=inspect||require(path.join(core,'lib/migrations/postgres-check.js')).inspect;
 const isSize=file=>file.operation?.kind==='clinical-storage-size-v1';
 const rows=files=>files.map(({name,checksum})=>({name,checksum})).sort((a,b)=>a.name.localeCompare(b.name));
 async function check(files,applied){return inspect(async sql=>({rows:sql.includes('to_regclass')?[{present:true}]:restore(applied)}),{files,table:'"synthetic".schema_migrations'});}
 for(const domain of ['treatments','profile','devicestatus']){
  const standardRaw=require(path.join(core,'migrations/candidates/postgres-'+domain+'-v1.json')),orderedRaw=require(path.join(core,'migrations/candidates/postgres-'+domain+'-socket-order-v1.json'));
  const standard=catalogue.validateCatalogue(standardRaw),ordered=catalogue.validateCatalogue(orderedRaw),size=ordered.find(isSize),ordinary=ordered.filter(f=>!isSize(f));
  const names=new Set(standard.map(f=>f.name)),upgrade=await check(ordered,rows(standard));
  assert.deepEqual(upgrade.pending,ordered.filter(f=>!names.has(f.name)).map(f=>f.name),'SIZE_TAIL_SKIPS_ORDINARY_UPGRADE');
  assert.equal(standard.find(isSize).name,size.name,'STANDARD_ORDERED_SIZE_TAIL_DIFFERS');
  assert.deepEqual((await check(ordered,rows(ordinary))).pending,[size.name],'OLD_ORDERED_SIZE_UPGRADE_LOST');
  assert.equal((await check(ordered,rows(ordered))).current,true,'COMPLETE_ORDERED_LEDGER_REFUSED');
  const drift=rows(ordered);drift.at(-1).checksum='0'.repeat(64);
  await assert.rejects(check(ordered,drift),e=>e.code==='MIG_DRIFT','SIZE_CHECKSUM_DRIFT_ACCEPTED');
  await assert.rejects(check(ordered,[...rows(ordinary),{name:'0098_synthetic_unknown',checksum:'0'.repeat(64)}]),e=>e.code==='MIG_UNKNOWN','UNKNOWN_TAIL_ACCEPTED');
  await assert.rejects(check(ordered,rows([ordinary[0],ordinary[2],size])),e=>e.code==='MIG_HISTORY','ORDINARY_HISTORY_GAP_ACCEPTED');
  await assert.rejects(check(ordered,rows([size])),e=>e.code==='MIG_HISTORY','SIZE_WITHOUT_BASE_HISTORY_ACCEPTED');
  const duplicate=rows(ordered);duplicate.push(restore(duplicate.at(-1)));
  await assert.rejects(check(ordered,duplicate),e=>e.code==='MIG_HISTORY','DUPLICATE_HISTORY_ACCEPTED');
  const forged=restore(orderedRaw),tail=forged.migrations.find(isSize);tail.up.push('SELECT 1');tail.checksum=catalogue.checksum(tail.up);
  assert.throws(()=>catalogue.validateCatalogue(forged),e=>e.code==='MIG_OPERATION_SQL','UNREVIEWED_TYPED_TAIL_ACCEPTED');
 }
}
async function schedulerDueRefresh(core,start){
 start=start||require(path.join(core,'lib/pgstream/activity-scheduler.js')).start;
 let release,finishRemaining,lookups=0,inFlight=0,maxInFlight=0;const hold=new Promise(resolve=>{release=resolve;}),remaining=new Promise(resolve=>{finishRemaining=resolve;}),due=new Map(),timers=new Set(),runs=[];
 const service=start({concurrency:2,now:()=>0,
  store:{async nextDue({exclude=[]}={}){lookups++;inFlight++;maxInFlight=Math.max(maxInFlight,inFlight);const at=Math.min(...[...due].filter(([tenant])=>!exclude.includes(tenant)).map(([,at])=>at),Infinity);try{await hold;return at===Infinity?null:at;}finally{inFlight--;}}},
  scan:async()=>{},run:async tenant=>{if(tenant!=='A')await remaining;runs.push(tenant);due.set(tenant,tenant==='A'?300:tenant==='B'?100:200);},send:async()=>{},
  setTimer(fn,delay){const timer={fn,delay,unref(){}};timers.add(timer);return timer;},clearTimer:timer=>timers.delete(timer)});
 const initializing=service.initialize(['A','B','C']);
 try{
  for(let turn=0;turn<100&&!lookups;turn++)await new Promise(resolve=>setImmediate(resolve));
  assert(lookups,'DUE_LOOKUP_DID_NOT_START');finishRemaining();
  for(let turn=0;turn<100&&runs.length!==3;turn++)await new Promise(resolve=>setImmediate(resolve));
  assert.equal(runs.length,3,'HELD_DUE_QUERY_BLOCKS_CLINICAL_NEIGHBOR');
  // A's first query captured300 while B/C were active. Their subsequent
  // completions owe an earlier100; one dirty follow-up must reconstruct it.
  release();await initializing;for(let turn=0;turn<10;turn++)await new Promise(resolve=>setImmediate(resolve));
  assert([...timers].some(timer=>timer.delay===100),'HELD_DUE_QUERY_LOST_EARLIER_COMPLETION');
  assert.equal(maxInFlight,1,'DUE_REFRESH_QUERY_AMPLIFICATION');
  assert(lookups<=2,'DUE_REFRESH_QUERY_AMPLIFICATION');
  return {completed:runs.length,nextDueCalls:lookups,maxInFlight,earliestDelay:100};
 }finally{finishRemaining();release();await initializing;await service.close();}
}
async function schedulerDueRefreshFinalizer(core,start){
 start=start||require(path.join(core,'lib/pgstream/activity-scheduler.js')).start;
 let service,lookups=0,queued=false;const timers=new Set();
 service=start({store:{nextDue:async({exclude})=>{lookups++;return exclude.includes('A')?500:300;}},
  scan:async()=>{},run:async()=>{},send:async()=>{},now:()=>0,
  setTimer(fn,delay){const timer={fn,delay,unref(){}};timers.add(timer);
   // Deliver a real public scheduler action at the microtask boundary between
   // finishing the query loop and settling any chained Promise finalizer.
   if(!queued){queued=true;queueMicrotask(()=>service.removeTenant('A'));}return timer;},
  clearTimer:timer=>timers.delete(timer)});
 try{
  await service.drain();for(let turn=0;turn<10;turn++)await Promise.resolve();
  assert([...timers].some(timer=>timer.delay===500),'SETTLED_DUE_FLIGHT_LOST_NEIGHBOR_TIMER');
  assert.equal(lookups,2,'SETTLED_DUE_FLIGHT_DID_NOT_REFRESH');
  return {nextDueCalls:lookups,remainingTenantDue:500};
 }finally{await service.close();}
}
async function run(core,capture){
 const file=path.join(core,'lib/storage/clinical-stream-state.js'),source=fs.readFileSync(file,'utf8'),events=fs.readFileSync(capture,'utf8').trim().split('\n').map(JSON.parse);
 const api=require(file),result=exercise(api,events),controls=[];
 const gapOptions=gapCoverage(api,events[0]);
 await migrationCompatibility(core);
 const inspectFile=path.join(core,'lib/migrations/postgres-check.js'),inspectSource=fs.readFileSync(inspectFile,'utf8'),tail='const size = file =>';assert.equal(inspectSource.split(tail).length,2,'MIGRATION_ABLATION_SOURCE_MISMATCH');
 const strictPrefix={exports:{}};vm.runInThisContext('(function(require,module,exports){'+inspectSource.replace(tail,'const size = file => false &&')+'\n})',{filename:inspectFile})(createRequire(inspectFile),strictPrefix,strictPrefix.exports);
 await assert.rejects(migrationCompatibility(core,strictPrefix.exports.inspect),e=>e.code==='MIG_HISTORY');await migrationCompatibility(core);controls.push('independent-size-tail-prefix');
 result.properties.push('bounded durable GAP/bootstrap','full/metadata byte parity');
 const undercount='(state.rowBytes??2)+8';assert.equal(source.split(undercount).length,2,'BYTE_ABLATION_SOURCE_MISMATCH');
 const shortBound={exports:{}};vm.runInThisContext('(function(require,module,exports){'+source.replace(undercount,'(state.rowBytes??2)+7')+'\n})',{filename:file})(createRequire(file),shortBound,shortBound.exports);
 assert.throws(()=>gapCoverage(shortBound.exports,events[0]),/METADATA_BYTE_BOUND_UNDERESTIMATED/);gapCoverage(api,events[0]);controls.push('metadata-byte-undercount');
 const gapReady='ready:false,gap:code===';assert.equal(source.split(gapReady).length,2,'GAP_ABLATION_SOURCE_MISMATCH');
 const readyGap={exports:{}};vm.runInThisContext('(function(require,module,exports){'+source.replace(gapReady,'ready:true,gap:code===')+'\n})',{filename:file})(createRequire(file),readyGap,readyGap.exports);
 assert.throws(()=>gapCoverage(readyGap.exports,events[0]),/GAP_MARKED_CLINICALLY_READY/);gapCoverage(api,events[0]);controls.push('GAP-marked-clinical-ready');
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
 await schedulerFairness(core);
 const schedulerFile=path.join(core,'lib/pgstream/activity-scheduler.js'),schedulerSource=fs.readFileSync(schedulerFile,'utf8');
 result.dueRefresh=await schedulerDueRefresh(core);
 const sharing='if(dueFlight){dueAgain=true;return dueFlight;}';assert.equal(schedulerSource.split(sharing).length,2,'DUE_REFRESH_ABLATION_SOURCE_MISMATCH');
 for(const[name,replacement,symptom]of [
  ['due-query-not-shared','',/DUE_REFRESH_QUERY_AMPLIFICATION/],
  ['due-query-loses-earlier-completion','if(dueFlight){return dueFlight;}',/HELD_DUE_QUERY_LOST_EARLIER_COMPLETION/]
 ]){
  const broken={exports:{}};vm.runInThisContext('(function(require,module,exports){'+schedulerSource.replace(sharing,replacement)+'\n})',{filename:schedulerFile})(createRequire(schedulerFile),broken,broken.exports);
  await assert.rejects(schedulerDueRefresh(core,broken.exports.start),symptom);await schedulerDueRefresh(core);controls.push(name);
 }
 result.dueSettlement=await schedulerDueRefreshFinalizer(core);
 const release='   }finally{dueFlight=null;}\n  });';assert.equal(schedulerSource.split(release).length,2,'DUE_SETTLEMENT_ABLATION_SOURCE_MISMATCH');
 const lateRelease={exports:{}};vm.runInThisContext('(function(require,module,exports){'+schedulerSource.replace(release,'   }finally{/* release postponed */}\n  }).finally(()=>{dueFlight=null;});')+'\n})',{filename:schedulerFile})(createRequire(schedulerFile),lateRelease,lateRelease.exports);
 await assert.rejects(schedulerDueRefreshFinalizer(core,lateRelease.exports.start),/SETTLED_DUE_FLIGHT_LOST_NEIGHBOR_TIMER/);await schedulerDueRefreshFinalizer(core);controls.push('settled-due-flight-loses-neighbor-timer');
 const pumpEnd='   await due();';assert.equal(schedulerSource.split(pumpEnd).length,2,'SCHEDULER_ABLATION_SOURCE_MISMATCH');
 const barrier={exports:{}};vm.runInThisContext('(function(require,module,exports){'+schedulerSource.replace(pumpEnd,'   await Promise.allSettled([...active.values()]);await due();')+'\n})',{filename:schedulerFile})(createRequire(schedulerFile),barrier,barrier.exports);
 await assert.rejects(schedulerFairness(core,barrier.exports.start),/IDLE_SLOT_MUST_RUN_NEIGHBOR_BEFORE_HELD_A_RELEASE/);await schedulerFairness(core);controls.push('held-tenant-batch-barrier');
 await schedulerRetry(core);
 const targeted='excluded.delete(tenant);retryAt.delete(tenant);enqueue';assert.equal(schedulerSource.split(targeted).length,2,'RETRY_ABLATION_SOURCE_MISMATCH');
 const amplified={exports:{}};vm.runInThisContext('(function(require,module,exports){'+schedulerSource.replace(targeted,'excluded.delete(tenant);retryAt.clear();enqueue')+'\n})',{filename:schedulerFile})(createRequire(schedulerFile),amplified,amplified.exports);
 await assert.rejects(schedulerRetry(core,amplified.exports.start),/NEIGHBOR_INPUT_AMPLIFIES_POISON_RETRY/);await schedulerRetry(core);controls.push('neighbor-clears-poison-backoff');
 await schedulerRecovery(core);
 const paging='await drain({wait:false});';assert.equal(schedulerSource.split(paging).length,2,'RECOVERY_ABLATION_SOURCE_MISMATCH');
 const blockedPage={exports:{}};vm.runInThisContext('(function(require,module,exports){'+schedulerSource.replace(paging,'await drain();')+'\n})',{filename:schedulerFile})(createRequire(schedulerFile),blockedPage,blockedPage.exports);
 await assert.rejects(schedulerRecovery(core,blockedPage.exports.start),/RECOVERY_PAGE_STARVED_BY_HELD_EARLIER_TENANT/);await schedulerRecovery(core);controls.push('held-first-recovery-page');
 await invalidBootstrap(core);
 const replayFile=path.join(core,'lib/storage/postgres-durable-replay.js'),replaySource=fs.readFileSync(replayFile,'utf8');
 const filter='if (stream || row.doc.isValid !== false)';assert.equal(replaySource.split(filter).length,2,'BOOTSTRAP_ABLATION_SOURCE_MISMATCH');
 const filtered={exports:{}};vm.runInThisContext('(function(require,module,exports){'+replaySource.replace(filter,'if (row.doc.isValid !== false)')+'\n})',{filename:replayFile})(createRequire(replayFile),filtered,filtered.exports);
 await assert.rejects(invalidBootstrap(core,filtered.exports),/BOOTSTRAP_INVALID_STORAGE_BYTES_LOST/);await invalidBootstrap(core);controls.push('bootstrap-drops-invalid-history');
 await dueCoverage(core);
 const runtimeFile=path.join(core,'lib/server/serve/evaluator-runtime.js'),runtimeSource=fs.readFileSync(runtimeFile,'utf8');
 const guard='if (!acquisition && canonical(observed) !== canonical(state.covered)) acquisition = true;';assert.equal(runtimeSource.split(guard).length,2,'TIME_ABLATION_SOURCE_MISMATCH');
 const staleTime={exports:{}};vm.runInThisContext('(function(require,module,exports){'+runtimeSource.replace(guard,'/* omitted coverage guard */')+'\n})',{filename:runtimeFile})(createRequire(runtimeFile),staleTime,staleTime.exports);
 await assert.rejects(dueCoverage(core,staleTime.exports),/TIME_COMPLETED_UNCOMPUTED_INPUT/);await dueCoverage(core);controls.push('TIME-completes-uncomputed-input');
 const receiverFile=path.join(core,'lib/pgstream/receiver.js'),receiverSource=fs.readFileSync(receiverFile,'utf8'),receiver=require(receiverFile);
 await receipt(core,events[0],receiver);await receipt(core,events[0],receiver,true);
 await receipt(core,events[0],receiver,false,gapOptions);
 const sqlFile=path.join(core,'lib/storage/clinical-stream-sql.js'),sqlSource=fs.readFileSync(sqlFile,'utf8'),update='const update=await client.query';assert.equal(sqlSource.split(update).length,2,'GAP_SQL_ABLATION_SOURCE_MISMATCH');
 const retainedRows={exports:{}};vm.runInThisContext('(function(require,module,exports){'+sqlSource.replace(update,'if(next.gap)delete next.rows;'+update)+'\n})',{filename:sqlFile})(createRequire(sqlFile),retainedRows,retainedRows.exports);
 await assert.rejects(receipt(core,events[0],receiver,false,{...gapOptions,sql:retainedRows.exports}),/GAP_CACHE_NOT_EVICTED/);await receipt(core,events[0],receiver,false,gapOptions);
 const mergeGuard='domain&&saved&&!next.gap';assert.equal(sqlSource.split(mergeGuard).length,2,'GAP_SQL_REPLACE_ABLATION_SOURCE_MISMATCH');
 const mergedGap={exports:{}};vm.runInThisContext('(function(require,module,exports){'+sqlSource.replace(mergeGuard,'domain&&saved')+'\n})',{filename:sqlFile})(createRequire(sqlFile),mergedGap,mergedGap.exports);
 await assert.rejects(receipt(core,events[0],receiver,false,{...gapOptions,sql:mergedGap.exports}),/GAP_SQL_RETAINED_OLD_CACHE_METADATA/);await receipt(core,events[0],receiver,false,gapOptions);controls.push('GAP-SQL-does-not-replace-cache');
 const from='await clinical.accept(row.tenant_id,data,route.domain,store);';assert.equal(receiverSource.split(from).length,2,'RECEIPT_ABLATION_SOURCE_MISMATCH');
 const broken={exports:{}};vm.runInThisContext('(function(require,module,exports){'+receiverSource.replace(from,'clinical.accept(row.tenant_id,data,route.domain,store);')+'\n})',{filename:receiverFile})(createRequire(receiverFile),broken,broken.exports);
 await assert.rejects(receipt(core,events[0],broken.exports),/RAW_ACK_BEFORE_COMMIT/);await receipt(core,events[0],receiver);controls.push('raw-ACK-before-commit');
 return {verdict:'PASS',scope:'actual-module state/native payloads and mocked SQL commit boundary; deployed recovery unmeasured',...result,controls};
}
module.exports={run,exercise,dueCoverage,migrationCompatibility,schedulerDueRefresh,schedulerDueRefreshFinalizer};
if(require.main===module){(async()=>{if(process.argv.length!==4)throw Error('Usage: node materializer-row-control.cjs APP_WORKTREE DECODER_JSONL');console.log(JSON.stringify(await run(path.resolve(process.argv[2]),path.resolve(process.argv[3]))));})().catch(error=>{console.error(error.stack);process.exitCode=1;});}
