'use strict';
require('/opt/app/deploy/multitenant/load-env');
const assert=require('node:assert/strict'),fs=require('node:fs');
const clients=require('/opt/app/lib/server/internal-api/clients');
const operator=require('/opt/app/deploy/multitenant/restore'),config=operator.loadConfig();
const peers=config.control.participants.filter(row=>row.roles.includes('evaluator'));
async function inspect(){return Promise.all(peers.map(async peer=>({id:peer.id,...await clients.evaluatorInspection(peer.endpoint).inspectEvaluator({})})));}
async function wait(fn){const end=Date.now()+12000;while(Date.now()<end){const result=await fn();if(result)return result;await new Promise(resolve=>setTimeout(resolve,50));}throw Object.assign(new Error(),{code:'EVALUATOR_BINDING_WAIT_EXPIRED'});}
async function main(){
 const mode=process.argv[2];
 if(mode==='invalidate-loop'){
  const http=require('node:http'),original=http.request,traces=[];
  http.request=function(options,callback){return original.call(this,options,response=>{traces.push({peer:config.control.participants.find(peer=>peer.endpoint.socketPath===options.socketPath)?.id||'unknown',operation:options.path,status:response.statusCode,at:Date.now()});callback(response);});};
  const db=new(require('/opt/app/node_modules/pg').Client)({connectionString:process.env.NS_OPERATOR_PG});await db.connect();let cohort,pin;
  try{
   await db.query('BEGIN');await db.query("SELECT set_config('app.current_tenant_id',$1,true)",[config.tenants[0].id]);
   const state=(await db.query('SELECT phase FROM '+config.control.namespace+'.tenant_lifecycle_windows WHERE tenant_id=$1',[config.tenants[0].id])).rows[0];assert.equal(state.phase,'suspended');await db.query('ROLLBACK');
   const module=require('/opt/app/lib/server/serve/operation-cohort');cohort=await module.createRemote({namespace:config.control.namespace,tenants:operator.cohortTenants(config),participants:config.control.participants});
   pin=await module.pin(cohort,config.tenants[0].id,{client:db});
   for(let index=0;index<10;index++){await module.invalidate(cohort,config.tenants[0].id);await new Promise(resolve=>setTimeout(resolve,100));}
   console.log(JSON.stringify({outcome:'invalidated',rounds:10,requests:traces.length,non200:traces.filter(row=>row.status!==200)}));
  }catch(error){console.log(JSON.stringify({outcome:'refused',code:error.code||error.message,traces}));throw error;}
  finally{if(pin)await require('/opt/app/lib/server/serve/operation-cohort').releasePin(pin);await cohort?.close();await db.end();http.request=original;}return;
 }

 if(mode==='inspect'){console.log(JSON.stringify(await inspect()));return;}
 if(mode==='census'){
  assert.equal(peers.length,3);
  const db=new(require('/opt/app/node_modules/pg').Client)({connectionString:process.env.NS_OPERATOR_PG});await db.connect();let cohort,pin;
  try{
   const module=require('/opt/app/lib/server/serve/operation-cohort');
   cohort=await module.createRemote({namespace:config.control.namespace,tenants:operator.cohortTenants(config),participants:config.control.participants});
   pin=await module.pin(cohort,config.tenants[0].id,{client:db});await module.assertComplete(cohort,config.tenants[0].id,{client:db});
   console.log(JSON.stringify({outcome:'complete',evaluators:peers.length}));
  }finally{if(pin)await require('/opt/app/lib/server/serve/operation-cohort').releasePin(pin);await cohort?.close();await db.end();}return;
 }
 if(mode==='duplicate'){
  const selected=JSON.parse(fs.readFileSync('/run/ns-pool-control.json','utf8'));
  const member=await require('/opt/app/lib/pool-membership').member({kind:'evaluator',partitioned:true,ordinal:1,leaseMs:30000,connectionString:selected.connectionString,namespace:selected.namespace});
  try{
   await member.register();
   await wait(async()=>{const rows=await inspect();return rows.every(row=>!row.gate.eligible&&row.gate.reason==='POOL_DUPLICATE_ORDINAL'&&row.tenants.every(tenant=>!tenant.admitted));});
   console.log(JSON.stringify({outcome:'refused',reason:'POOL_DUPLICATE_ORDINAL',members:peers.length}));
  }finally{await member.close();}
  await wait(async()=>{const rows=await inspect();return rows.every(row=>row.gate.eligible);});return;
 }
 throw Object.assign(new Error(),{code:'EVALUATOR_BINDING_MODE_REFUSED'});
}
main().catch(error=>{console.error(JSON.stringify({code:/^[A-Z0-9_]+$/.test(error.code||'')?error.code:'EVALUATOR_BINDING_PROBE_REFUSED'}));process.exitCode=1;});
