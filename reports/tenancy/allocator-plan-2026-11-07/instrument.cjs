'use strict';
// Source-only until plan.json pins root-reviewed committed planner source.
const fs=require('node:fs'),assert=require('node:assert/strict');
const root=process.env.APP_SOURCE;
const {Client}=require(root+'/node_modules/pg');
const connect=require(root+'/lib/storage/postgres-connection');
require(root+'/lib/storage/tenant-scope').setTenancyMode('multi');
const moduleLifecycle=require(root+'/lib/tenant-lifecycle');
const artifacts=require(root+'/lib/tenant-lifecycle/artifact');
const candidate=require(root+'/migrations/candidates/postgres-entries-v1.json');
const codes=JSON.parse(process.env.PROBE_CODES);
const lifecycle=moduleLifecycle.createLifecycle({catalogues:[{kind:'entries',candidate,tables:['entries']}]});
const A='11111111-1111-4111-8111-111111111111',B='22222222-2222-4222-8222-222222222222';
const namespaces={entries:'planner_entries'};
const observations=[],queries=[];let admin,planner,sequenceName;
async function q(sql,values){return(await admin.query(sql,values)).rows;}
async function physical(){
 const rows=await q('SELECT * FROM planner_entries.entries ORDER BY tenant_id,id_kind,"_id" COLLATE "C"');
 const ledger=await q('SELECT * FROM planner_entries.schema_migrations ORDER BY name COLLATE "C"');
 const [counter]=await q(`SELECT last_value::text,log_cnt::text,is_called FROM ${sequenceName}`);
 const [metadata]=await q('SELECT seqtypid::text,seqstart::text,seqincrement::text,seqmax::text,seqmin::text,seqcache::text,seqcycle FROM pg_sequence WHERE seqrelid=$1::regclass',[sequenceName]);
 return {rows,ledger,counter,metadata};
}
function highArtifact(original){
 const catalogues=original.manifest.catalogues.map(c=>({...c,tables:c.tables.map(t=>({...t,rows:original.tables[c.kind+'.'+t.table].map(row=>({...row,insertion_ordinal:String(BigInt(row.insertion_ordinal)+1000n)}))}))}));
 return artifacts.buildArtifact({tenant:A,sourceCommit:process.env.SOURCE_HEAD,exportedAt:1700000000000,catalogues});
}
async function invoke(artifact){return lifecycle.planAllocatorPreservingImport(planner,artifact,{tenant:A,namespaces});}
async function ordinary(label,artifact){const before=await physical(),result=await invoke(artifact);assert.equal(result.advisory,true);assert.equal(result.authorized,false);const after=await physical();assert.deepEqual(after,before);observations.push({label,verdict:'PASS',result,allTenantRowsLedgerAndSequenceUnchanged:true,physicalBefore:before,physicalAfter:after});}
async function refusal(label,artifact,expected){const before=await physical();let actual;await assert.rejects(()=>invoke(artifact),e=>{actual=e.code;return e.code===expected;});const after=await physical();assert.deepEqual(after,before);observations.push({label,verdict:'EXPECTED_REFUSAL',expected,actual,allTenantRowsLedgerAndSequenceUnchanged:true,physicalBefore:before,physicalAfter:after});}
async function main(){
 assert.equal(typeof lifecycle.planAllocatorPreservingImport,'function','FROZEN_PLANNER_API_MISMATCH');
 admin=new Client({connectionString:process.env.PROBE_ADMIN,application_name:'owned-planner-admin'});await admin.connect();
 await q(`CREATE ROLE probe_app LOGIN PASSWORD '${process.env.PROBE_PASSWORD}' NOSUPERUSER NOBYPASSRLS`);
 await q('CREATE SCHEMA planner_entries');await q('SET search_path TO planner_entries');
 await q('CREATE TABLE schema_migrations(name text PRIMARY KEY,checksum text NOT NULL)');
 for(const m of candidate.migrations){for(const sql of m.up)await q(sql);await q('INSERT INTO schema_migrations(name,checksum) VALUES($1,$2)',[m.name,m.checksum]);}
 for(const [tenant,id] of [[A,'a-one'],[B,'b-current'],[A,'a-two']])await q('INSERT INTO entries(tenant_id,id_kind,doc) VALUES($1,\'string\',$2::jsonb)',[tenant,JSON.stringify({_id:id,identifier:id,type:'sgv',date:1000,sgv:100})]);
 const [binding]=await q("SELECT pg_get_serial_sequence('planner_entries.entries','insertion_ordinal') AS name");sequenceName=binding.name;
 await q('GRANT USAGE ON SCHEMA planner_entries TO probe_app');await q('GRANT SELECT ON planner_entries.entries,planner_entries.schema_migrations TO probe_app');await q(`GRANT SELECT ON SEQUENCE ${sequenceName} TO probe_app`);
 planner=await connect({connectionString:process.env.PROBE_APP,max:1,application_name:'owned-planner-readonly'});
 const query=planner.query;planner.query=function(sql,values){queries.push(sql);return query.call(planner,sql,values);};
 const artifact=await lifecycle.exportTenant(planner,{tenant:A,namespaces,sourceCommit:process.env.SOURCE_HEAD,now:()=>1700000000000});
 await q('DELETE FROM planner_entries.entries WHERE tenant_id=$1',[A]);
 const [privileges]=await q(`SELECT has_table_privilege('probe_app','planner_entries.entries','INSERT,UPDATE,DELETE,TRUNCATE') AS table_write,
 has_sequence_privilege('probe_app',$1,'SELECT') AS sequence_select,has_sequence_privilege('probe_app',$1,'USAGE') AS sequence_usage,has_sequence_privilege('probe_app',$1,'UPDATE') AS sequence_update`,[sequenceName]);
 assert.deepEqual(privileges,{table_write:false,sequence_select:true,sequence_usage:false,sequence_update:false});
 observations.push({sourceHead:process.env.SOURCE_HEAD,scope:'Read-only advisory planner; entries-only actual schema/ledger/artifact; no restore or serving admission',privileges});
 await ordinary('ordinary-covered-live-floor',artifact);
 await refusal('uncovered-artifact-floor',highArtifact(artifact),codes.uncoveredFloor);
 await q(`GRANT UPDATE ON SEQUENCE ${sequenceName} TO probe_app`);await refusal('unsafe-sequence-setter',artifact,codes.unsafeSetter);await q(`REVOKE UPDATE ON SEQUENCE ${sequenceName} FROM probe_app`);await ordinary('fresh-after-privilege-restoration',artifact);
 await q(`ALTER SEQUENCE ${sequenceName} CACHE 8`);await refusal('unsupported-cache-fixture',artifact,codes.unsupportedCache);await q(`ALTER SEQUENCE ${sequenceName} CACHE 1`);await ordinary('fresh-after-cache-restoration',artifact);
 const beforeImport=await physical();let importCode;await assert.rejects(()=>lifecycle.importArtifact(planner,artifact,{tenant:A,namespaces}),e=>{importCode=e.code;return e.code==='LIFECYCLE_IDENTITY_IMPORT_UNSUPPORTED';});assert.deepEqual(await physical(),beforeImport);observations.push({label:'production-identity-import-still-refuses',actual:importCode,allTenantRowsLedgerAndSequenceUnchanged:true});
 const [version]=await q('SELECT version() AS version');observations.push({version:version.version,queries});
}
main().then(()=>fs.writeFileSync(process.env.PROBE_OUT,JSON.stringify({completed:true,observations},null,2))).catch(error=>{fs.writeFileSync(process.env.PROBE_OUT,JSON.stringify({completed:false,observations,error:{message:error.message,code:error.code}},null,2));process.exitCode=1;}).finally(async()=>{if(planner)await planner.end();if(admin)await admin.end();});
