"use strict";
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
module.exports=({directory,result,configuration})=>{
 const row=JSON.parse(fs.readFileSync(path.join(directory,'actual-consumer-handoff.json')));
 assert.equal(result.status,0,'JOINED_CONSUMER_CLI_STATUS');assert.deepEqual(row.cleanupErrors,[]);
 assert(row.sameIdRetry===true&&row.suppressionStopsDelivery===true,'CONSUMER_SUCCESS_MARKERS');
 const accepted=row.accepted;assert(accepted.state==='accepted'&&accepted.attempt>=2&&!accepted.payload.clear);assert.equal(accepted.receipt,null);
 const same=row.attempts.filter(x=>x.id===accepted.request_id&&!x.notification.clear);assert(same.length>=2);assert.deepEqual(same[0].notification,same[1].notification);assert.deepEqual(same[0].notification,accepted.payload);
 assert(row.events.some(x=>x.recipient==='current'&&x.kind==='urgent_alarm'));assert(!row.events.some(x=>x.recipient==='stale'&&x.kind==='urgent_alarm'));
 assert.deepEqual(row.suppressed.map(x=>x.alarm_level).sort(),[1,2]);for(const x of row.suppressed)assert(Number(x.expires_at)>Number(x.acked_at));
 assert(Array.isArray(row.coldPackets)&&row.coldPackets.length===configuration.coldAcquisition.entryCount);
 const ids=row.coldPackets.map(x=>x.packet.data._id);assert.equal(new Set(ids).size,ids.length);assert(ids.every(id=>row.coldPhysicalRows.some(x=>x.doc._id===id)),'COLD_CANONICAL_PHYSICAL_PACKETS');
 const retry=row.retryPhysical;assert.equal(retry.first.id,retry.retry.id);assert.equal(retry.first.id,retry.first.durable.request_id);assert.deepEqual(retry.first.notification,retry.retry.notification);assert(row.coldAckPhysical.producer.producer.acks.length>=2);
 const before=row.coldBeforeAck,after=row.coldAfterAck;assert.notEqual(before.pid,row.warmEvaluatorPid);assert(before.pid===after.pid&&Number.isSafeInteger(before.pid));assert(after.observedAt>=before.observedAt);
 for(const observed of [before,after]){assert.equal(observed.classification,'actual CLI with disclosed observational getter preload');assert.equal(observed.sourceHead,configuration.sourceHead);assert.equal(observed.phaseId,'joined-consumer-handoff');assert.equal(observed.last.find(x=>x.tenant===configuration.tenant)?.value,null);assert.equal(observed.health.tenants.find(x=>x.tenant===configuration.tenant)?.code,'EVALUATOR_ACQUISITION_REFUSED');}
 assert(row.coldClear.state==='accepted'&&row.coldClear.payload.clear);assert.equal(row.coldClear.receipt,null);assert(!row.beforeAckRequestIds.includes(row.coldClear.request_id));assert(row.events.filter(x=>x.recipient==='current'&&x.kind==='clear_alarm').length>row.beforeAckClearEvents);
};
