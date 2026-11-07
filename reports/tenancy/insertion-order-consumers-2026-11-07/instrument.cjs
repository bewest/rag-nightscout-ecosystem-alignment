'use strict';
const fs=require('node:fs'), assert=require('node:assert/strict');
const root=process.env.APP_SOURCE;
const {Client}=require(root+'/node_modules/pg');
const connect=require(root+'/lib/storage/postgres-connection');
const scope=require(root+'/lib/storage/tenant-scope');scope.setTenancyMode('multi');
const reads=require(root+'/lib/server/storage-reads');
const profile=require(root+'/lib/server/tenant-app/profile');
const entries=require(root+'/lib/server/tenant-app/entries');
const profileCatalog=require(root+'/migrations/candidates/postgres-profile-socket-order-v1.json');
const entriesCatalog=require(root+'/migrations/candidates/postgres-entries-v1.json');
const A='11111111-1111-4111-8111-111111111111';
let admin,app;
const observations=[],readQueries=[];
async function q(sql,values){return(await admin.query(sql,values)).rows;}
async function prepare(schema,catalog){
 await q(`CREATE SCHEMA ${schema}`);await q(`SET search_path TO ${schema}`);
 for(const m of catalog.migrations)for(const sql of m.up)await q(sql);
 await q(`GRANT USAGE ON SCHEMA ${schema} TO probe_app`);await q(`GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA ${schema} TO probe_app`);await q(`GRANT USAGE ON ALL SEQUENCES IN SCHEMA ${schema} TO probe_app`);
}
async function reseed(schema,table,docs,ordinals){
 await q('BEGIN');try{await q(`DELETE FROM ${schema}.${table} WHERE tenant_id=$1`,[A]);
  for(let i=0;i<docs.length;i++)await q(`INSERT INTO ${schema}.${table}(tenant_id,id_kind,doc,insertion_ordinal) OVERRIDING SYSTEM VALUE VALUES($1,'string',$2::jsonb,$3)`,[A,JSON.stringify(docs[i]),ordinals[i]]);
  await q('COMMIT');
 }catch(e){await q('ROLLBACK');throw e;}
}
async function main(){
 admin=new Client({connectionString:process.env.PROBE_ADMIN,application_name:'owned-consumer-admin'});await admin.connect();
 await q(`CREATE ROLE probe_app LOGIN PASSWORD '${process.env.PROBE_PASSWORD}' NOSUPERUSER NOBYPASSRLS`);
 app=await connect({connectionString:process.env.PROBE_APP,max:1,application_name:'owned-consumer-app'});
 const query=app.query;app.query=function(sql,values){readQueries.push(sql);return query.call(app,sql,values);};
 await prepare('consumer_profile',profileCatalog);await prepare('consumer_entries',entriesCatalog);
 const p=profile({connection:app,table:'consumer_profile.profile',source:'socket',naturalOrder:true});
 const e=entries({connection:app,table:'consumer_entries.entries',source:'v1/internal'});
 const pdocs=[{_id:'z-first',NSCLIENT_ID:'synthetic',startDate:'2026-11-06',store:{Synthetic:{dia:3}}},{_id:'a-second',NSCLIENT_ID:'synthetic',startDate:'2026-11-06',store:{Synthetic:{dia:9}}}];
 const edocs=[{_id:'e-old',identifier:'entry-old',type:'sgv',sgv:100,date:1000},{_id:'e-new',identifier:'entry-new',type:'sgv',sgv:110,date:2000}];
 const selectProfile=()=>app.withTenant(A,()=>reads.findOne(p.storage,{NSCLIENT_ID:'synthetic'}));
 const selectEntries=()=>app.withTenant(A,()=>reads.list(e.storage,{}, {sort:{date:-1},count:10}));
 await reseed('consumer_profile','profile',pdocs,[1,2]);await reseed('consumer_entries','entries',edocs,[1,2]);
 const baselineP=await selectProfile(),baselineE=await selectEntries();assert.deepEqual(baselineP,pdocs[0]);assert.deepEqual(baselineE,edocs.toReversed());
 observations.push({phase:'baseline',profileSelected:baselineP,entriesDateSorted:baselineE});
 await reseed('consumer_profile','profile',pdocs,[100,200]);await reseed('consumer_entries','entries',edocs,[100,200]);
 const renumberP=await selectProfile(),renumberE=await selectEntries();assert.deepEqual(renumberP,baselineP);assert.deepEqual(renumberE,baselineE);
 observations.push({phase:'renumber-preserving-order',verdict:'PASS',rawOrdinals:[100,200],profileSelected:renumberP,entriesDateSorted:renumberE,publicDocumentsExactlyEqual:true});
 await reseed('consumer_profile','profile',pdocs,[200,100]);await reseed('consumer_entries','entries',edocs,[200,100]);
 const reverseP=await selectProfile(),reverseE=await selectEntries();assert.deepEqual(reverseP,pdocs[1]);assert.throws(()=>assert.deepEqual(reverseP,baselineP),{code:'ERR_ASSERTION'});assert.deepEqual(reverseE,baselineE);
 observations.push({phase:'reverse-order-control',verdict:'EXPECTED_SEMANTIC_RED_PROFILE',rawOrdinals:[200,100],profileSelected:reverseP,changedProfileIDAndStore:true,entriesDateSorted:reverseE,explicitDateReaderUnaffected:true});
 await reseed('consumer_profile','profile',pdocs,[1,2]);await reseed('consumer_entries','entries',edocs,[1,2]);
 const restoredP=await selectProfile(),restoredE=await selectEntries();assert.deepEqual(restoredP,baselineP);assert.deepEqual(restoredE,baselineE);
 assert(readQueries.some(sql=>sql.includes('consumer_profile')&&sql.includes('ORDER BY insertion_ordinal ASC')&&sql.includes('LIMIT')));
 assert(readQueries.some(sql=>sql.includes('consumer_entries')&&sql.includes('ORDER BY')&&sql.includes('DESC')&&!sql.includes('ORDER BY insertion_ordinal')));
 for(const doc of [baselineP,renumberP,reverseP,restoredP,...restoredE])assert(!Object.hasOwn(doc,'insertion_ordinal'));
 const [version]=await q('SELECT version() AS version');
 observations.push({phase:'fresh-restoration',verdict:'PASS',profileSelected:restoredP,entriesDateSorted:restoredE,privateOrdinalNotReturned:true});
 observations.push({sourceHead:process.env.SOURCE_HEAD,version:version.version,readQueries});
}
main().then(()=>fs.writeFileSync(process.env.PROBE_OUT,JSON.stringify({completed:true,scope:'Actual server consumer reads on native PG; not HTTP or mobile binary execution',observations},null,2))).catch(error=>{fs.writeFileSync(process.env.PROBE_OUT,JSON.stringify({completed:false,observations,error:{message:error.message,code:error.code}},null,2));process.exitCode=1;}).finally(async()=>{if(app)await app.end();if(admin)await admin.end();});
