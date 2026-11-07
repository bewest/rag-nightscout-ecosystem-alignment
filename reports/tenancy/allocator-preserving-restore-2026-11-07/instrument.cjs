'use strict';
// Independent SQL feasibility probe, not a product restore or lifecycle fence.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const root = process.env.APP_SOURCE;
require(root + '/lib/storage/tenant-scope').setTenancyMode('multi');
const {Client} = require(root + '/node_modules/pg');
const connect = require(root + '/lib/storage/postgres-connection');
const writer = require(root + '/lib/storage/postgres-entries-write');
const catalog = require(root + '/migrations/candidates/postgres-entries-v1.json');
const A='11111111-1111-4111-8111-111111111111', B='22222222-2222-4222-8222-222222222222';
let admin, app, n=0;
const observations=[];
async function q(sql, values) { return (await admin.query(sql, values)).rows; }
async function rows(schema, tenant) { return q(`SELECT e.tenant_id,e.doc,e.id_kind,e.insertion_ordinal::text AS insertion_ordinal FROM ${schema}.entries e WHERE e.tenant_id=$1 ORDER BY e.insertion_ordinal`,[tenant]); }
async function sequence(schema) {
 const [binding]=await q(`SELECT pg_get_serial_sequence('${schema}.entries','insertion_ordinal') AS name`);
 const [meta]=await q('SELECT c.oid::text, s.seqincrement::text, s.seqcache::text, s.seqcycle FROM pg_class c JOIN pg_sequence s ON s.seqrelid=c.oid WHERE c.oid=$1::regclass',[binding.name]);
 const [state]=await q(`SELECT last_value::text,is_called FROM ${binding.name}`);
 return {...binding,...meta,...state};
}
async function fixture() {
 const schema='probe'+(++n); await q(`CREATE SCHEMA ${schema}`); await q(`SET search_path TO ${schema}`);
 for(const migration of catalog.migrations) for(const sql of migration.up) await q(sql);
 await q(`GRANT USAGE ON SCHEMA ${schema} TO probe_app`);
 await q(`GRANT SELECT,INSERT,UPDATE,DELETE ON ${schema}.entries TO probe_app`);
 await q(`GRANT USAGE ON ALL SEQUENCES IN SCHEMA ${schema} TO probe_app`);
 const port=writer({connection:app, table:schema+'.entries'});
 const put=async(tenant,id)=>app.withTenant(tenant,()=>port.insertOne({_id:id,type:'sgv',sgv:100,identifier:id},{normalize:false}));
 await put(A,'a1'); await put(B,'b1'); await put(A,'a2');
 const artifact={tenant:A,table:schema+'.entries',sequence:await sequence(schema),rows:await rows(schema,A)};
 const priorB=await rows(schema,B); await q(`DELETE FROM ${schema}.entries WHERE tenant_id=$1`,[A]);
 return {schema,port,put,artifact,priorB};
}
function refuse(code){throw Object.assign(new Error(code),{code});}
async function restore(f,artifact,{skipFloor=false,interrupt=false}={}) {
 const live=await sequence(f.schema);
 if(artifact.table!==f.schema+'.entries'||artifact.sequence.oid!==live.oid||artifact.sequence.name!==live.name)refuse('ALLOCATOR_BINDING_REFUSED');
 if(live.seqcache!=='1'||live.seqincrement!=='1'||live.seqcycle||!live.is_called)refuse('ALLOCATOR_SEMANTICS_REFUSED');
 const floor=artifact.rows.reduce((v,r)=>BigInt(r.insertion_ordinal)>v?BigInt(r.insertion_ordinal):v,0n);
 if(!skipFloor&&floor>BigInt(live.last_value))refuse('ARTIFACT_FLOOR_NOT_COVERED');
 if((await rows(f.schema,A)).length)refuse('TARGET_NOT_EMPTY');
 await q('BEGIN');
 try{
  for(let i=0;i<artifact.rows.length;i++){
   const r=artifact.rows[i];
   await q(`INSERT INTO ${f.schema}.entries(tenant_id,id_kind,doc,insertion_ordinal) OVERRIDING SYSTEM VALUE VALUES($1,$2,$3::jsonb,$4)`,[A,r.id_kind,JSON.stringify(r.doc),r.insertion_ordinal]);
   if(i===0){await f.put(B,'b_during'); if(interrupt)throw new Error('INJECTED_AFTER_FIRST_ROW');}
  }
  await q('COMMIT');
 }catch(e){await q('ROLLBACK');throw e;}
 return {before:live,after:await sequence(f.schema)};
}
function exactB(f, now) { const ids=new Set(f.priorB.map(r=>r.doc._id));assert.deepEqual(now.filter(r=>ids.has(r.doc._id)),f.priorB,'PRIOR_B_CHANGED'); }
async function ordinary(label){
 const f=await fixture();await f.put(B,'b_before');f.priorB=await rows(f.schema,B);const before=await sequence(f.schema);
 const result=await restore(f,f.artifact);assert.deepEqual(await rows(f.schema,A),f.artifact.rows);
 // Exactly one B insertion during restore advances allocator by one. Explicit A restore consumes none.
 assert.equal(BigInt(result.after.last_value),BigInt(result.before.last_value)+1n);
 await f.put(A,'a_after');await f.put(B,'b_after');
 const ar=await rows(f.schema,A),br=await rows(f.schema,B);exactB(f,br);
 assert.equal(ar.at(-1).doc._id,'a_after');assert.deepEqual(br.map(r=>r.doc._id),['b1','b_before','b_during','b_after']);
 observations.push({label,verdict:'PASS',A:ar.map(r=>({id:r.doc._id,ordinal:r.insertion_ordinal})),B:br.map(r=>({id:r.doc._id,ordinal:r.insertion_ordinal})),allocatorBefore:before.last_value,allocatorAfterRestore:result.after.last_value,originalBExact:true,allocatorMaintenanceStatements:0});
}
async function refusal(kind){const f=await fixture();const artifact=structuredClone(f.artifact);
 if(kind==='high-floor')for(const r of artifact.rows)r.insertion_ordinal=String(BigInt(r.insertion_ordinal)+1000n);
 else artifact.sequence.oid=String(BigInt(artifact.sequence.oid)+1n);
 const before=await sequence(f.schema), b=await rows(f.schema,B);
 await assert.rejects(()=>restore(f,artifact),e=>e.code===(kind==='high-floor'?'ARTIFACT_FLOOR_NOT_COVERED':'ALLOCATOR_BINDING_REFUSED'));
 assert.deepEqual(await sequence(f.schema),before);assert.deepEqual(await rows(f.schema,A),[]);assert.deepEqual(await rows(f.schema,B),b);
 observations.push({label:kind,verdict:'EXPECTED_REFUSAL',zeroAEffects:true,sequenceUnchanged:true,BUnchanged:true});
}
async function main(){
 admin=new Client({connectionString:process.env.PROBE_ADMIN,application_name:'owned-feasibility-admin'});await admin.connect();
 await q(`CREATE ROLE probe_app LOGIN PASSWORD '${process.env.PROBE_PASSWORD}' NOSUPERUSER NOBYPASSRLS`);
 app=await connect({connectionString:process.env.PROBE_APP,max:1,application_name:'owned-feasibility-app'});
 const [version]=await q('SELECT version() AS version'); observations.push({version:version.version,sourceHead:process.env.SOURCE_HEAD,scope:'entries SQL feasibility; controlled A fixture quiescence; no serving fence'});
 await ordinary('ordinary');await refusal('high-floor');await refusal('wrong-binding');
 {const f=await fixture();const before=await sequence(f.schema);await assert.rejects(()=>restore(f,f.artifact,{interrupt:true}),/INJECTED_AFTER_FIRST_ROW/);assert.deepEqual(await rows(f.schema,A),[]);const br=await rows(f.schema,B);exactB(f,br);assert.equal(br.at(-1).doc._id,'b_during');assert.equal(BigInt((await sequence(f.schema)).last_value),BigInt(before.last_value)+1n);observations.push({label:'interrupted-restore',verdict:'PASS',allARowsRolledBack:true,concurrentBCommitted:true});}
 {const f=await fixture();const artifact=structuredClone(f.artifact);for(const r of artifact.rows)r.insertion_ordinal=String(BigInt(r.insertion_ordinal)+1000n);await restore(f,artifact,{skipFloor:true});await f.put(A,'a_after');const ar=await rows(f.schema,A);assert.notEqual(ar.at(-1).doc._id,'a_after');observations.push({label:'floor-guard-removed',verdict:'EXPECTED_SEMANTIC_RED',symptom:'new A insertion sorts before restored old A rows',A:ar.map(r=>({id:r.doc._id,ordinal:r.insertion_ordinal}))});}
 {const f=await fixture();await restore(f,f.artifact);await q(`UPDATE ${f.schema}.entries SET doc=doc||'{"notes":"CONTROL_CORRUPTION"}'::jsonb WHERE tenant_id=$1`,[B]);assert.throws(()=>exactB(f,[]));const now=await rows(f.schema,B);assert.throws(()=>exactB(f,now),/PRIOR_B_CHANGED/);observations.push({label:'foreign-row-corruption',verdict:'EXPECTED_SEMANTIC_RED',symptom:'independent exact prior-B comparison rejects changed stored document'});}
 // Separate alternative hypothesis: preserve relative order while deliberately allocating fresh private ordinals.
 {const f=await fixture();const artifact=structuredClone(f.artifact);for(const r of artifact.rows)r.insertion_ordinal=String(BigInt(r.insertion_ordinal)+1000n);await f.put(B,'b_before');f.priorB=await rows(f.schema,B);
  const sorted=[...artifact.rows].sort((a,b)=>BigInt(a.insertion_ordinal)<BigInt(b.insertion_ordinal)?-1:1);
  await q('BEGIN');try{for(let i=0;i<sorted.length;i++){const r=sorted[i];await q(`INSERT INTO ${f.schema}.entries(tenant_id,id_kind,doc) VALUES($1,$2,$3::jsonb)`,[A,r.id_kind,JSON.stringify(r.doc)]);if(i===0)await f.put(B,'b_during');}await q('COMMIT');}catch(e){await q('ROLLBACK');throw e;}
  const ar=await rows(f.schema,A);assert.deepEqual(ar.map(r=>r.doc),sorted.map(r=>r.doc));assert.notDeepEqual(ar.map(r=>r.insertion_ordinal),sorted.map(r=>r.insertion_ordinal));await f.put(A,'a_after');await f.put(B,'b_after');const br=await rows(f.schema,B);exactB(f,br);assert.equal((await rows(f.schema,A)).at(-1).doc._id,'a_after');observations.push({label:'fresh-private-ordinals-alternative',verdict:'PASS_PROPOSAL_ONLY',publicDocumentValuesAndRelativeOrderPreserved:true,originalRawOrdinalsPreserved:false,originalBExact:true,A:ar.map(r=>({id:r.doc._id,ordinal:r.insertion_ordinal})),artifactOrdinals:sorted.map(r=>r.insertion_ordinal),B:br.map(r=>({id:r.doc._id,ordinal:r.insertion_ordinal}))});
 }
 await ordinary('fresh-restoration');
}
main().then(()=>{fs.writeFileSync(process.env.PROBE_OUT,JSON.stringify({completed:true,observations},null,2));}).catch(e=>{fs.writeFileSync(process.env.PROBE_OUT,JSON.stringify({completed:false,observations,error:{message:e.message,code:e.code}},null,2));process.exitCode=1;}).finally(async()=>{if(app)await app.end();if(admin)await admin.end();});
