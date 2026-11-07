'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{isDeepStrictEqual:same}=require('node:util');
module.exports=({directory,result,configuration,control})=>{
 const row=JSON.parse(fs.readFileSync(path.join(directory,'actual-consumer-handoff.json')));assert.equal(result.status,1);assert.deepEqual(row.cleanupErrors,[]);assert(/^ERR_ASSERTION$/m.test(fs.readFileSync(path.join(directory,'native.log'),'utf8')));
 const label=control.oracle==='retry-identity'?'CONSUMER_UNCERTAIN_SAME_ID':'CONSUMER_COLD_ACK_CLEAR_INTENT_MISSING';assert.deepEqual(row.semanticFailure,{name:'AssertionError',code:'ERR_ASSERTION',message:label});
 if(control.oracle==='retry-identity'){
  const {first,retry,rows}=row.retryPhysical;assert.equal(first.tenant,configuration.tenant);assert.equal(retry.tenant,first.tenant);assert(first.responseLost===true&&retry.attempt>=2);assert(first.result.accepted===true&&retry.result.accepted===true);
  for(const key of ['origin','config_identity','dedup_key'])assert.equal(first.durable[key],retry.durable[key]);assert.deepEqual(first.notification,retry.notification);assert.equal(first.id,first.durable.request_id);assert.equal(retry.durable.request_id,first.durable.request_id);assert.notEqual(retry.id,first.id,'CONTROL_MUST_REALLY_REPLACE_TRANSPORT_UUID');assert(rows.some(x=>x.request_id===first.id&&same(x.payload,first.notification)));
 }else{
  assert.equal(control.oracle,'cold-clear-intent');const p=row.coldAckPhysical;assert(Number(p.producer.revision)>Number(p.beforeRevision));assert.deepEqual(p.suppressed.map(x=>x.alarm_level).sort(),[1,2]);
  const keys=p.suppressed.map(x=>JSON.stringify([x.alarm_group,x.alarm_level,Number(x.acked_at),Number(x.expires_at)]));assert.deepEqual(p.ackKeys,keys);assert(keys.every(k=>p.producer.producer.acks.includes(k)),'CONTROL_REQUIRES_COMMITTED_ACK_CONSUMPTION');
  assert.equal(p.cold.last.find(x=>x.tenant===configuration.tenant)?.value,null);assert.equal(p.cold.health.tenants.find(x=>x.tenant===configuration.tenant)?.code,'EVALUATOR_ACQUISITION_REFUSED');assert.equal(p.cold.sourceHead,configuration.sourceHead);assert.notEqual(p.cold.pid,row.warmEvaluatorPid);
  const effects=p.producer.producer.effects.filter(x=>x.payload.clear===true);assert(effects.length>0,'CONTROL_MUST_PRESERVE_REAL_CLEAR_EFFECT');assert(!p.rows.some(x=>!p.beforeAckRequestIds.includes(x.request_id)&&x.payload.clear===true&&effects.some(e=>e.origin===x.origin&&same(e.payload,x.payload))),'CONTROL_MUST_OMIT_PHYSICAL_CLEAR_REQUEST');
 }
};
