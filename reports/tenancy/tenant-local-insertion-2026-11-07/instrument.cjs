'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict');
const {AsyncResource}=require('node:async_hooks');
// Independent B request begins outside every A tenant/transaction context.
const independentRequest=new AsyncResource('owned-B-request');
const root=process.env.APP_SOURCE, plan=JSON.parse(process.env.PROBE_PLAN);
const {Client}=require(root+'/node_modules/pg');
const connect=require(root+'/lib/storage/postgres-connection');
const scope=require(root+'/lib/storage/tenant-scope');scope.setTenancyMode('multi');
const writer=require(root+'/lib/storage/postgres-entries-write');
const reads=require(root+'/lib/server/storage-reads');
const profile=require(root+'/lib/server/tenant-app/profile');
const builder=require(root+'/lib/tenant-lifecycle/tenant-insertion-sql');
const A='11111111-1111-4111-8111-111111111111',B='22222222-2222-4222-8222-222222222222';
const paths={entries:'postgres-entries-v1',food:'postgres-food-v1',treatments:'postgres-treatments-socket-order-v1',devicestatus:'postgres-devicestatus-socket-order-v1',profile:'postgres-profile-socket-order-v1'};
const cases=[],observations=[];let admin,app,restoreApp;
async function q(sql,v){return(await admin.query(sql,v)).rows;}
const table=f=>f.ns+'.'+f.domain,counter=f=>f.ns+'.tenant_insertion_ordinal';
async function rows(f,t){return q(`SELECT tenant_id,id_kind,doc,insertion_ordinal::text AS insertion_ordinal FROM ${table(f)} e ${t?'WHERE tenant_id=$1':''} ORDER BY tenant_id,e.insertion_ordinal`,t?[t]:[]);}
async function counters(f){return q(`SELECT tenant_id,last_ordinal::text FROM ${counter(f)} ORDER BY tenant_id`);}
async function floor(f,t){return (await q(`SELECT last_ordinal::text FROM ${counter(f)} WHERE tenant_id=$1`,[t]))[0]?.last_ordinal;}
async function op(t,fn,role){await q('BEGIN');try{if(role)await q('SET LOCAL ROLE '+role);await q("SELECT set_config('app.current_tenant_id',$1,true)",[t]);const r=await fn();await q('COMMIT');return r;}catch(e){await q('ROLLBACK');throw e;}}
function doc(id,domain){return domain==='profile'?{_id:id,NSCLIENT_ID:'synthetic',startDate:'2026-11-06',store:{Synthetic:{dia:id.includes('second')?9:3}}}:{_id:id,identifier:id,type:'sgv',date:1000,sgv:100};}
async function put(f,t,id){return app.withTenant(t,()=>f.port.insertOne(doc(id,f.domain),{normalize:false}));}
async function independentPut(f,t,id){return independentRequest.runInAsyncScope(()=>put(f,t,id));}
async function profileRead(f){const p=profile({connection:app,table:table(f),source:'socket',naturalOrder:true});return app.withTenant(A,()=>reads.findOne(p.storage,{NSCLIENT_ID:'synthetic'}));}
async function prepare(domain){
 const ns='local_'+domain,candidate=require(root+'/migrations/candidates/'+paths[domain]+'.json'),sql=builder.build({namespace:ns,domain});
 await q(`CREATE SCHEMA ${ns}`);await q(`SET search_path TO ${ns}`);for(const m of candidate.migrations)for(const s of m.up)await q(s);
 const f={domain,ns,sql};
 for(const [t,id] of [[A,domain==='profile'?'z-first':'a-first'],[B,'b-current'],[A,domain==='profile'?'a-second':'a-second']])await q(`INSERT INTO ${table(f)}(tenant_id,id_kind,doc) VALUES($1,'string',$2::jsonb)`,[t,JSON.stringify(doc(id,domain))]);
 const before=await rows(f);
 await q('BEGIN');try{for(const s of sql.up)await q(s);await q('COMMIT');}catch(e){await q('ROLLBACK');throw e;}
 assert.deepEqual(await rows(f),before,'CONVERSION_CHANGED_POPULATED_ROWS');
 const seq=await q('SELECT sequencename FROM pg_sequences WHERE schemaname=$1',[ns]);assert.deepEqual(seq,[],'GLOBAL_SEQUENCE_REMAINS');
 const [identity]=await q("SELECT attidentity FROM pg_attribute WHERE attrelid=$1::regclass AND attname='insertion_ordinal'",[table(f)]);assert.equal(identity.attidentity,'');
 const [security]=await q("SELECT c.relrowsecurity,c.relforcerowsecurity,p.prosecdef FROM pg_class c CROSS JOIN pg_proc p WHERE c.oid=$1::regclass AND p.oid=$2::regprocedure",[counter(f),ns+'.allocate_tenant_insertion_ordinal()']);assert.deepEqual(security,{relrowsecurity:true,relforcerowsecurity:true,prosecdef:false});
 for(const role of ['probe_app','probe_restore']){await q(`GRANT USAGE ON SCHEMA ${ns} TO ${role}`);await q(`GRANT SELECT ON ${table(f)} TO ${role}`);for(const s of role==='probe_restore'?sql.restoreGrants(role):sql.servingGrants(role))await q(s);await q(sql.verifyGrants(role,{restore:role==='probe_restore'}));}
 f.port=writer({connection:app,table:table(f)});cases.push(f);
 observations.push({phase:'populated-conversion',domain,rowsExact:true,identityRemoved:true,globalSequences:seq,security,counters:await counters(f)});
}
async function ordinary(f){
 const before=BigInt(await floor(f,A));await put(f,A,'a-ordinary');assert.equal(await floor(f,A),String(before+1n));
 const beforeRollback=await counters(f),beforeRows=await rows(f);await assert.rejects(()=>app.withTenant(A,async()=>{await f.port.insertOne(doc('a-rollback',f.domain),{normalize:false});throw new Error('INJECTED_ROLLBACK');}),/INJECTED_ROLLBACK/);assert.deepEqual(await counters(f),beforeRollback);assert.deepEqual(await rows(f),beforeRows);
 await put(f,A,'a-after-rollback');assert.equal(await floor(f,A),String(before+2n));
 const beforeExplicit=await rows(f),beforeCounter=await counters(f);let explicitCode;
 await assert.rejects(()=>app.withTenant(A,()=>app.query(`INSERT INTO ${table(f)}(tenant_id,id_kind,doc,insertion_ordinal) VALUES($1,'string',$2::jsonb,999)`,[A,JSON.stringify(doc('a-explicit',f.domain))])),e=>{explicitCode=e.code;return e.code==='42501';});assert.deepEqual(await rows(f),beforeExplicit);assert.deepEqual(await counters(f),beforeCounter);
 let bindingCode;await assert.rejects(()=>app.withTenant(A,()=>app.query(`INSERT INTO ${table(f)}(tenant_id,id_kind,doc) VALUES($1,'string',$2::jsonb)`,[B,JSON.stringify(doc('foreign',f.domain))])),e=>{bindingCode=e.message;return /TENANT_ORDINAL_BINDING_REQUIRED/.test(e.message);});assert.deepEqual(await rows(f),beforeExplicit);assert.deepEqual(await counters(f),beforeCounter);
 let immutable;await assert.rejects(()=>op(A,()=>q(`UPDATE ${table(f)} SET insertion_ordinal=999 WHERE tenant_id=$1 AND doc->>'_id'=$2`,[A,'a-ordinary'])),e=>{immutable=e.message;return /TENANT_ORDINAL_IMMUTABLE/.test(e.message);});assert.deepEqual(await rows(f),beforeExplicit);
 observations.push({phase:'ordinary-rollback-acl-binding',domain:f.domain,counterRollbackExact:true,rowsRollbackExact:true,ordinaryExplicitOrdinalRefused:explicitCode,foreignBindingRefused:bindingCode,ordinalUpdateRefused:immutable});
}
async function concurrency(f){
 let heldResolve,release;const held=new Promise(r=>heldResolve=r),released=new Promise(r=>release=r);let firstPid,secondPid,secondStarted;const entered=new Promise(r=>secondStarted=r);
 const first=app.withTenant(A,async()=>{firstPid=(await app.query('SELECT pg_backend_pid() AS pid')).rows[0].pid;await f.port.insertOne(doc('a-held',f.domain),{normalize:false});heldResolve();await released;});
 await held;const second=app.withTenant(A,async()=>{secondPid=(await app.query('SELECT pg_backend_pid() AS pid')).rows[0].pid;secondStarted();await f.port.insertOne(doc('a-competing',f.domain),{normalize:false});});await entered;
 let witnessed=false;try{
 for(let i=0;i<100;i++){const [r]=await q('SELECT $1::int=ANY(pg_blocking_pids($2)) AS blocked',[firstPid,secondPid]);if(r.blocked){witnessed=true;break;}await new Promise(r=>setTimeout(r,10));}assert(witnessed,'EXACT_A_BLOCKER_NOT_OBSERVED');
 const bBefore=BigInt(await floor(f,B));await put(f,B,'b-while-a-held');assert.equal(await floor(f,B),String(bBefore+1n));const [still]=await q('SELECT $1::int=ANY(pg_blocking_pids($2)) AS blocked',[firstPid,secondPid]);assert(still.blocked,'A_NOT_HELD_DURING_B_COMMIT');
 observations.push({phase:'same-A-serializes-B-progresses',domain:f.domain,exactBlockerObserved:true,BCommittedWhileAHeld:true,globalPause:false});
 }finally{release();await Promise.all([first,second]);}
 const ar=await rows(f,A);assert(ar.findIndex(r=>r.doc._id==='a-held')<ar.findIndex(r=>r.doc._id==='a-competing'));
}
async function restore(f){
 const artifact=await rows(f,A),originalCounter=await floor(f,A),beforeB=await rows(f,B),counterB=await floor(f,B);
 await op(A,async()=>{await q(`DELETE FROM ${table(f)} WHERE tenant_id=$1`,[A]);await q(`DELETE FROM ${counter(f)} WHERE tenant_id=$1`,[A]);});
 const putRestoreRow=r=>restoreApp.query(`INSERT INTO ${table(f)}(tenant_id,id_kind,doc,insertion_ordinal) VALUES($1,$2,$3::jsonb,$4)`,[A,r.id_kind,JSON.stringify(r.doc),r.insertion_ordinal]);
 await assert.rejects(()=>restoreApp.withTenant(A,async()=>{await restoreApp.query(`INSERT INTO ${counter(f)}(tenant_id,last_ordinal) VALUES($1,$2)`,[A,originalCounter]);await putRestoreRow(artifact[0]);await independentPut(f,B,'b-during-interrupted-restore');throw new Error('RESTORE_INTERRUPTED');}),/RESTORE_INTERRUPTED/);
 assert.deepEqual(await rows(f,A),[]);assert.equal(await floor(f,A),undefined);const afterInterruptedB=await rows(f,B);assert.deepEqual(afterInterruptedB.slice(0,-1),beforeB);assert.equal(afterInterruptedB.at(-1).doc._id,'b-during-interrupted-restore');assert.equal(await floor(f,B),String(BigInt(counterB)+1n));
 await restoreApp.withTenant(A,async()=>{await restoreApp.query(`INSERT INTO ${counter(f)}(tenant_id,last_ordinal) VALUES($1,$2)`,[A,originalCounter]);for(let i=0;i<artifact.length;i++){await putRestoreRow(artifact[i]);if(i===0)await independentPut(f,B,'b-during-successful-restore');}});
 assert.deepEqual(await rows(f,A),artifact);assert.equal(await floor(f,A),originalCounter);const afterB=await rows(f,B);assert.deepEqual(afterB.slice(0,-1),afterInterruptedB);assert.equal(afterB.at(-1).doc._id,'b-during-successful-restore');assert.equal(await floor(f,B),String(BigInt(counterB)+2n));await put(f,A,'a-after-restore');assert.equal((await rows(f,A)).at(-1).doc._id,'a-after-restore');assert.deepEqual(await rows(f,B),afterB);
 observations.push({phase:'A-rows-counter-restore',domain:f.domain,restrictedRestoreConnection:true,counterRestoredBeforeRows:true,rowsAndCounterExact:true,BPreexistingRowsExact:true,BCommitsDuringInterruptedAndSuccessfulRestore:true,BAppendCount:2,BCounterIncrement:2,interruptedRestoreRolledBack:true,nextASortsLast:true,sharedAllocatorMaintenance:false});
}
async function controls(f){
 await q('CREATE ROLE probe_inherited NOLOGIN');await q(`GRANT INSERT(insertion_ordinal) ON ${table(f)} TO probe_inherited`);await q('GRANT probe_inherited TO probe_app');let inherited;
 await assert.rejects(()=>q(f.sql.verifyGrants('probe_app',{restore:false})),e=>{inherited=e.message;return /TENANT_ORDINAL_EXPLICIT_INSERT_UNSAFE/.test(e.message);});await q('REVOKE probe_inherited FROM probe_app');await q(f.sql.verifyGrants('probe_app',{restore:false}));
 const priorRows=await rows(f),priorCounter=await counters(f),priorB=await rows(f,B);let brokenOrder;
 await assert.rejects(()=>app.withTenant(A,async()=>{await app.query(`UPDATE ${counter(f)} SET last_ordinal=1 WHERE tenant_id=$1`,[A]);await f.port.insertOne(doc('a-counter-corruption',f.domain),{normalize:false});brokenOrder=(await app.query(`SELECT doc->>'_id' AS id,insertion_ordinal::text FROM ${table(f)} e WHERE tenant_id=$1 ORDER BY e.insertion_ordinal`,[A])).rows;assert.throws(()=>assert.equal(brokenOrder.at(-1).id,'a-counter-corruption'),{code:'ERR_ASSERTION'});assert.equal(brokenOrder[1].id,'a-counter-corruption');throw new Error('EXPECTED_COUNTER_CONTROL_ROLLBACK');}),/EXPECTED_COUNTER_CONTROL_ROLLBACK/);
 assert.deepEqual(await rows(f),priorRows);assert.deepEqual(await counters(f),priorCounter);assert.deepEqual(await rows(f,B),priorB);await put(f,A,'a-fresh-control-restoration');assert.equal((await rows(f,A)).at(-1).doc._id,'a-fresh-control-restoration');assert.deepEqual(await rows(f,B),priorB);
 observations.push({phase:'control-restoration',domain:f.domain,inheritedGrantVerifierRefused:inherited,ownCounterCorruptionExpectedNewLastRed:true,brokenOrder,controlRollbackRestoresAllTenantRowsAndCounters:true,BExact:true,freshOrdinaryRestored:true});
}
async function main(){
 admin=new Client({connectionString:process.env.PROBE_ADMIN,application_name:'owned-local-counter-admin'});await admin.connect();
 for(const role of ['probe_app','probe_restore'])await q(`CREATE ROLE ${role} LOGIN PASSWORD '${process.env.PROBE_PASSWORD}' NOSUPERUSER NOBYPASSRLS`);
 app=await connect({connectionString:process.env.PROBE_APP,max:3,statement_timeout:5000,application_name:'owned-local-counter-app'});
 restoreApp=await connect({connectionString:process.env.PROBE_APP.replace('//probe_app:','//probe_restore:'),max:1,statement_timeout:5000,application_name:'owned-local-counter-restore'});
 for(const domain of builder.DOMAINS)await prepare(domain);
 const p=cases.find(f=>f.domain==='profile');const initialProfile=await profileRead(p);assert.equal(initialProfile._id,'z-first');
 for(const f of cases){await ordinary(f);await restore(f);}
 await restoreApp.end();restoreApp=null;await concurrency(cases[0]);await controls(cases[0]);assert.deepEqual(await profileRead(p),initialProfile);observations.push({phase:'actual-profile-first-match',documentExactlyPreserved:true,selected:initialProfile});
 const [version]=await q('SELECT version() AS version');observations.push({sourceHead:process.env.SOURCE_HEAD,version:version.version,scope:'Standalone source SQL builder native proof; no runtime/default/lifecycle integration'});
}
main().then(()=>fs.writeFileSync(process.env.PROBE_OUT,JSON.stringify({completed:true,observations},null,2))).catch(e=>{fs.writeFileSync(process.env.PROBE_OUT,JSON.stringify({completed:false,observations,error:{message:e.message,code:e.code}},null,2));process.exitCode=1;}).finally(async()=>{if(restoreApp)await restoreApp.end();if(app)await app.end();if(admin)await admin.end();});
