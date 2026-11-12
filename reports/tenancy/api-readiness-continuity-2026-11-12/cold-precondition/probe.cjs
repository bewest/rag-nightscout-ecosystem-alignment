'use strict';
// Source-only startup component protocol. No HTTP server/DB/Vault/restore.
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs'),crypto=require('node:crypto'),cp=require('node:child_process');
const core='<workspace>/externals/work/crm-evaluator-idle-opportunity-20261112';
assert.equal(cp.execFileSync('git',['-C',core,'rev-parse','HEAD'],{encoding:'utf8'}).trim(),'2d0ae0354a38b4a88f43bc2ae5ec60c085058f64');
const startup=require(path.join(core,'lib/server/serve/tenant-startup')),readiness=require(path.join(core,'lib/server/serve/pool-config')).tenantReadiness({});assert.equal(readiness,'serve');
const A='11111111-1111-4111-8111-111111111111',B='22222222-2222-4222-8222-222222222222';
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return{promise,resolve};};
const registry1=new Set(),registry2=new Set(),oneB=deferred(),twoB=deferred(),oneA=deferred(),calls=[];
const options=registry=>({readiness,accept:tenant=>registry.has(tenant),drainedLog(){},alert(){}});
const api1=startup.create([][Symbol.iterator](),undefined,async tenant=>{calls.push(['api1',tenant]);await(tenant===A?oneA:oneB).promise;},options(registry1));
const api2=startup.create([][Symbol.iterator](),undefined,async tenant=>{calls.push(['api2',tenant]);await twoB.promise;},options(registry2));
const warming=error=>error.code==='TENANT_WARMING'&&error.retryAfter===5;
(async()=>{const observations=[];
 try{
  await Promise.all([api1.warm(),api2.warm()]);assert.equal(api1.health().ready,true);assert.equal(api2.health().ready,true);assert.equal(api2.health().configured,0);
  registry1.add(B);await assert.rejects(api1.admit(B),warming);oneB.resolve();await api1.drained();await api1.admit(B);
  for(let n=0;n<10;n++){assert.equal(api2.health().ready,true);assert.equal(api2.health().configured,0);}assert.equal(calls.filter(row=>row[0]==='api2').length,0);
  const naive=api1.health().ready&&api2.health().ready;assert.equal(naive,true);assert.equal(api1.isReady(B),true);assert.equal(api2.isReady(B),false);
  observations.push({stage:'before-restore-both-global-ready',api1:api1.health(),api2:api2.health(),tupleWarm:{api1B:true,api2B:false}});
  registry2.add(B);await assert.rejects(api2.admit(B),warming); // no restore/invalidation has happened
  observations.push({stage:'api2-first-B-admission',code:'TENANT_WARMING',retryAfter:5,api2:api2.health()});
  assert.throws(()=>assert.ok(api1.isReady(B)&&api2.isReady(B),'GLOBAL_READY_DOES_NOT_PROVE_ALL_TUPLES'),/GLOBAL_READY_DOES_NOT_PROVE_ALL_TUPLES/);
  twoB.resolve();await api2.drained();await Promise.all([api1.admit(B),api2.admit(B)]);assert.ok(api1.isReady(B)&&api2.isReady(B));
  registry1.add(A);api1.invalidateTenant(A); // selected invalidation only; this is NOT a real restore
  await Promise.all([api1.admit(B),api2.admit(B)]);assert.ok(api1.isReady(B)&&api2.isReady(B));oneA.resolve();await api1.drained();
  observations.push({stage:'exact-tuple-barrier-and-selected-A-invalidation',api1B:api1.isReady(B),api2B:api2.isReady(B),allAdmissionsPassed:true});
  const files=['lib/server/serve/tenant-startup.js','lib/server/serve/preview-api.js','lib/server/serve/registry-tenants.js','lib/server/tenant-app/index.js','lib/server/serve/pool-config.js'];
  const result={scope:'SOURCE_COMPONENT_ONLY; no HTTP/SQL/Vault/native restore; original failed-run cause unclassified',source:'2d0ae0354a38b4a88f43bc2ae5ec60c085058f64',files:Object.fromEntries(files.map(file=>[file,crypto.createHash('sha256').update(fs.readFileSync(path.join(core,file))).digest('hex')])),observations,initializations:calls.length,verdict:'POSSIBLE_MECHANISM_REPRODUCED',naiveGlobalReadyControl:'RED: cold B refusal despite both global ready',exactTupleBarrier:'GREEN',unrelatedAInvalidation:'B stays warm'};
  fs.writeFileSync(path.join(__dirname,'result.json'),JSON.stringify(result,null,2)+'\n',{mode:0o600});console.log(JSON.stringify({verdict:result.verdict,naiveGlobalReadyControl:result.naiveGlobalReadyControl,exactTupleBarrier:result.exactTupleBarrier,unrelatedAInvalidation:result.unrelatedAInvalidation,initializations:calls.length}));
 }finally{oneA.resolve();oneB.resolve();twoB.resolve();await Promise.all([api1.drained(),api2.drained()]);api1.close();api2.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
