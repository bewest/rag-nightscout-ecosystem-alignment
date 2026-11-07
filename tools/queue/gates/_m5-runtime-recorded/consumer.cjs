'use strict';
// Physical component oracle only: actual evaluator/PG/UDS controlled sink,
// synthetic authorized ACK transport; no Socket.IO/current-token/browser claim.
const {isDeepStrictEqual}=require('node:util');
const ensure=(v,m)=>{if(!v)throw new Error(m);},same=(a,b,m)=>ensure(isDeepStrictEqual(a,b),m);
const ordinaryCounts={
 'first-output-before-verdict':1,'committed-before-verdict':1,'unchanged-wake-before-verdict':1,'committed-per-cycle':1,
 'restart-clear-before-verdict':1,'restart-normal-clear':1,'uncertain-before-death':1,'uncertain-restart-before-verdict':1,'uncertain-process-restart':1,
 'control-clear-before-verdict':1,'control-ack-with-failed-clinical':1,'ack-privilege-before-verdict':3,'unsafe-state-before-verdict':1,'ack-state-readonly-and-rls-refusal':1
};
const controlCounts={
 'missing-intent':{'first-output-before-verdict':1},
 'jsonb-admission-churn':{'first-output-before-verdict':1},
 'lost-state':{'restart-clear-before-verdict':1},
 'cold-no-output':{'control-clear-before-verdict':1},
 'jsonb-order':{'first-output-before-verdict':1,'committed-before-verdict':1,'unchanged-wake-before-verdict':1}
};
module.exports=function verifyConsumer(records,control){
 ensure(!control||Object.hasOwn(controlCounts,control),'CONSUMER_UNKNOWN_CONTROL');const required=control?controlCounts[control]:ordinaryCounts;
 const allowed=new Set([...Object.keys(required),'sink-before-accept']);ensure(records.length<=96&&records.every(r=>allowed.has(r.phase)),'CONSUMER_UNKNOWN_OR_EXCESS_PHASE');
 const group=name=>records.filter(r=>r.phase===name),one=name=>{const rs=group(name);ensure(rs.length===1,'CONSUMER_REQUIRED_ONE '+name);return rs[0];};
 for(const [phase,count]of Object.entries(required))ensure(group(phase).length===count,'CONSUMER_REQUIRED_PHASE_COUNT '+phase);
 const sinks=group('sink-before-accept');ensure(sinks.length<=(control?16:64),'CONSUMER_SINK_BOUND');ensure(['missing-intent','jsonb-admission-churn'].includes(control)?sinks.length===0:sinks.length>0,'CONSUMER_SINK_MISSING_OR_UNEXPECTED');
 for(const sink of sinks){ensure(sink.ownRow&&sink.ownRow.request_id===sink.id&&sink.ownRow.tenant_id===sink.tenant&&sink.ownRow.state==='attempting','CONSUMER_INTENT_MUST_PRECEDE_SINK');same(sink.ownRow.payload,sink.notification,'CONSUMER_COMMITTED_PAYLOAD');}
 if(control==='jsonb-admission-churn'){
  const r=one('first-output-before-verdict'),A='11111111-1111-4111-8111-111111111111',B='22222222-2222-4222-8222-222222222222';
  ensure(r.effects.length===0&&r.requests.length===1&&r.state.length===1,'CONSUMER_JSONB_ADMISSION_BOUNDARY');
  const request=r.requests[0],state=r.state[0],producer=state.producer,uuid=v=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(v);
  ensure(request.tenant_id===A&&state.tenant_id===A&&request.consumer==='realtime-joined-native'&&state.consumer===request.consumer&&
   request.state==='cancelled'&&request.attempt===1&&request.accepted_at===null&&request.receipt===null&&request.cleared_at===null&&uuid(request.request_id)&&uuid(request.attempt_token),'CONSUMER_JSONB_CANCELLED_INTENT');
  ensure(Number(state.revision)===3&&producer.effects.length===1&&producer.acks.length===0&&producer.output.length===4&&producer.output[2]===1&&uuid(producer.output[1]),'CONSUMER_JSONB_REVISION_CHURN');
  ensure(producer.effects[0].origin===request.origin&&/^[0-9a-f]{64}$/.test(request.origin)&&state.config_identity===request.config_identity&&
   producer.clinicalIdentity===request.config_identity&&producer.output[0]===request.config_identity,'CONSUMER_JSONB_STABLE_IDENTITY');
  ensure(request.dedup_key==='realtime-cycle:'+require('node:crypto').createHash('sha256').update(request.config_identity).digest('hex')+':'+request.origin,'CONSUMER_JSONB_BOUND_KEY');
  same(producer.effects[0].payload,request.payload,'CONSUMER_JSONB_STABLE_PAYLOAD');
  same(request.payload,{kind:'notify',debug:{lastSGV:50,thresholds:{bgLow:55,bgHigh:260,bgTargetTop:180,bgTargetBottom:80}},group:'default',level:2,title:'Urgent LOW',plugin:{name:'simplealarms'},message:'BG Now: 50 → mg/dl',eventName:'low',pushoverSound:'persistent'},'CONSUMER_JSONB_ACTUAL_CLINICAL_EFFECT');
  ensure(producer.alarms.length===1&&producer.alarms[0].group==='default'&&producer.alarms[0].level===2&&producer.alarms[0].lastAckTime===0&&producer.alarms[0].silenceTime===1800000,'CONSUMER_JSONB_NO_ACK_CAUSE');
  const h=r.health,clinical=h.tenants.find(t=>t.tenant===A),foreign=h.tenants.find(t=>t.tenant===B),consumers=h.consumers,current=consumers.tenants.find(t=>t.tenant===A);
  ensure(h.closed===false&&h.tenants.length===2&&clinical.ready===true&&clinical.code===null&&clinical.identity===request.config_identity&&clinical.outputRevision===1&&clinical.inputCheckpoint===producer.output[3]&&foreign.ready===true,'CONSUMER_JSONB_CURRENT_CLINICAL');
  ensure(consumers.enabled===true&&consumers.closed===false&&consumers.normalPolicy==='realtime-cycle'&&consumers.route===request.consumer&&consumers.tenants.length===2&&
   current.clinicalEligible===true&&current.state==='idle'&&current.code===null&&current.lastHandoffAcceptedAt===null,'CONSUMER_JSONB_NO_HANDOFF');
  same(current.observedIntents,[{id:request.request_id,state:'cancelled'}],'CONSUMER_JSONB_OBSERVED_CANCELLED');
  ensure(Number.isSafeInteger(Number(request.created_at))&&Number(request.created_at)>1e12&&Number(request.attempt_until)>Number(request.created_at)&&Number(request.next_at)>=Number(request.created_at),'CONSUMER_JSONB_ACTUAL_ATTEMPT_EPOCH');
  return;
 }
 if(!control||control==='missing-intent'||control==='jsonb-order'){
  const first=one('first-output-before-verdict');ensure(first.state.length===1&&first.state[0].producer.effects.length>0,'CONSUMER_PRIVATE_STATE_NOT_REACHED');
  if(control==='missing-intent'){ensure(first.effects.length===0&&first.requests.length===0,'CONSUMER_INTENT_ABLATION_NOT_REACHED');return;}
  ensure(first.effects.length===1&&first.requests.length===1,'CONSUMER_FIRST_OUTPUT_PHYSICAL');const effect=first.effects[0],request=first.requests[0];ensure(effect.id===request.request_id&&request.state==='accepted','CONSUMER_FIRST_DURABLE_REQUEST');same(effect.notification,request.payload,'CONSUMER_FIRST_PAYLOAD');
  const committed=one('committed-before-verdict');ensure(committed.rows.length===1&&committed.rows[0].state==='accepted','CONSUMER_COMMITTED_STATE');same(committed.foreign,[],'CONSUMER_FOREIGN_MUST_BE_EMPTY');
  const unchanged=one('unchanged-wake-before-verdict');ensure(unchanged.before.length===1&&unchanged.after.length===1,'CONSUMER_UNCHANGED_STATE_ROWS');same(unchanged.after[0].producer,unchanged.before[0].producer,'CONSUMER_UNCHANGED_LOGICAL_PRIVATE_STATE');same(unchanged.after[0].config_identity,unchanged.before[0].config_identity,'CONSUMER_UNCHANGED_CONFIG');
  if(control==='jsonb-order'){ensure(Number(unchanged.after[0].revision)>Number(unchanged.before[0].revision),'CONSUMER_JSONB_COMPARATOR_ABLATION_NOT_REACHED');return;}
  same(unchanged.after[0].revision,unchanged.before[0].revision,'CONSUMER_JSONB_MUST_NOT_ADVANCE');
  const per=one('committed-per-cycle');ensure(per.rows.length===2&&new Set(per.rows.map(r=>r.request_id)).size===2&&per.rows.every(r=>r.state==='accepted'),'CONSUMER_NEW_CYCLE_REQUEST');same(per.foreign,[],'CONSUMER_NEW_CYCLE_FOREIGN');
 }
 if(!control||control==='lost-state'){
  const before=one('restart-clear-before-verdict');ensure(before.alarm.state==='accepted'&&!before.alarm.payload.clear&&before.state.length===1,'CONSUMER_RESTART_BASELINE_NOT_REACHED');
  if(control==='lost-state'){same(before.clears,[],'CONSUMER_STATE_LOSS_ABLATION_NOT_REACHED');return;}
  ensure(before.clears.length===1&&before.clears[0].state==='accepted'&&before.clears[0].payload.clear&&before.clears[0].payload.message==="Auto ack'd alarm(s)",'CONSUMER_RESTART_NORMAL_CLEAR');
  const final=one('restart-normal-clear');const clears=final.clears.filter(r=>r.payload.clear);ensure(clears.length===1&&clears[0].request_id===before.clears[0].request_id,'CONSUMER_RESTART_CLEAR_ID_STABLE');
 }
 if(!control){
  const before=one('uncertain-before-death'),after=one('uncertain-restart-before-verdict'),final=one('uncertain-process-restart');ensure(before.original.state==='uncertain'&&before.state.length===1,'CONSUMER_UNCERTAIN_BASELINE');
  ensure(after.death.signal==='SIGKILL'&&after.death.code===null&&Number.isSafeInteger(after.death.pid)&&after.death.pid>0,'CONSUMER_PLANNED_PROCESS_DEATH');
  ensure(after.after.request_id===before.original.request_id&&after.after.state==='accepted'&&after.after.attempt>=2,'CONSUMER_SAME_UUID_RETRY');same(after.after.payload,before.original.payload,'CONSUMER_RETRY_PAYLOAD');same(final.death,after.death,'CONSUMER_DEATH_RAW_IDENTITY');same(final.after,after.after,'CONSUMER_RETRY_FINAL');
 }
 if(!control||control==='cold-no-output'){
  const r=one('control-clear-before-verdict');ensure(r.clinical===null&&r.state.length===1,'CONSUMER_COLD_LAST_NULL_NOT_REACHED');same(r.suppression.map(x=>x.alarm_level).sort(),[1,2],'CONSUMER_COMMITTED_ACK_CASCADE');
  ensure(r.suppression.every(x=>Number(x.acked_at)>1e12&&Number(x.expires_at)-Number(x.acked_at)===60000),'CONSUMER_ACTUAL_ACK_EPOCH');
  if(control==='cold-no-output'){same(r.after,[],'CONSUMER_COLD_ABLATION_NOT_REACHED');return;}
  ensure(r.after.length===1&&r.after[0].notification.clear&&r.after[0].notification.message==="default - Urgent was ack'd",'CONSUMER_COLD_CONTROL_CLEAR');
  const after=one('control-ack-with-failed-clinical');same(after.suppression,r.suppression,'CONSUMER_ACK_NO_EXTENSION');ensure(after.health.consumers.tenants.length===2,'CONSUMER_FOREIGN_HEALTH');
 }
 if(!control){
  const denied=group('ack-privilege-before-verdict');same(denied.map(r=>r.operation),['UPDATE','SELECT','INSERT'],'CONSUMER_ACK_THREE_SQL_OPERATIONS');ensure(denied.every(r=>r.refusal==='42501'&&r.state.length===1),'CONSUMER_ACK_STATE_SELECT_ONLY');
  const unsafe=one('unsafe-state-before-verdict');ensure(unsafe.effectsBefore===unsafe.effectsAfter&&unsafe.state.length===1&&unsafe.health.consumers.tenants.some(t=>t.state==='refused'),'CONSUMER_UNSAFE_RLS_REFUSAL');
  const final=one('ack-state-readonly-and-rls-refusal');ensure(final.effectsBefore===final.effectsAfter,'CONSUMER_UNSAFE_NO_EFFECT');
 }
};
module.exports.ordinaryCounts=ordinaryCounts;
