'use strict';
// Native discriminator only: no clinical write or tenant reopening. The held
// constructor has an actual PG backend but has not published its identity yet.
const assert=require('node:assert/strict'),fs=require('node:fs');
const {Pool}=require('/opt/app/node_modules/pg');
const connection=require('/opt/app/lib/storage/postgres-connection');
async function main(){
 const selected=JSON.parse(fs.readFileSync('/run/ns-constructor-control.json','utf8'));
 const pool=new Pool({connectionString:selected.lifetimeUrl,max:2});
 const window=require('/opt/app/lib/tenant-lifecycle/operation-window').create({namespace:selected.namespace,lockRule:'tenant-id-sha256-v1',pool});
 await window.ready();const releaseWindow=connection.installOperationWindow(window);
 let baseline,pending,release;
 const gate=new Promise(resolve=>{release=resolve;});let held;const entered=new Promise(resolve=>{held=resolve;});
 const original=Pool.prototype.connect;
 try{
  baseline=await connection({connectionString:selected.readerUrl,application_name:'cohort-baseline',max:1});
  const before=connection.cohortDatastore(window);assert.deepEqual(before,window.datastore);
  Pool.prototype.connect=async function(...args){const client=await original.apply(this,args);if(this.options.application_name==='cohort-pending'){held();await gate;}return client;};
  pending=connection({connectionString:selected.readerUrl,application_name:'cohort-pending',max:1});
  await entered;
  assert.throws(()=>connection.cohortDatastore(window),/PostgreSQL cohort datastore unavailable/);
  console.log('REPRODUCED_NATIVE pendingConstructor actualBackend identityUnpublished datastoreSnapshotRefused');
  release();const candidate=await pending;pending=null;await candidate.end();
  assert.deepEqual(connection.cohortDatastore(window),before);
  console.log('RESTORED_NATIVE constructorAdmitted sameDatastore snapshotAvailable');
 }finally{release();Pool.prototype.connect=original;if(pending)await(await pending).end();await baseline?.end();releaseWindow();await window.close();await pool.end();}
}
main().catch(error=>{console.error(JSON.stringify({code:/^[A-Z0-9_]+$/.test(error.code||'')?error.code:error.name}));process.exitCode=1;});
