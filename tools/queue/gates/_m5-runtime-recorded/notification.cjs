'use strict';
// Reviewed against actual snapshot native source; synthetic adapter acceptance,
// not provider delivery. Final notifier/consumer owner review remains mandatory.
const ensure=(v,m)=>{if(!v)throw new Error(m);};
const same=(a,b,m)=>ensure(JSON.stringify(a)===JSON.stringify(b),m);
module.exports=function verifyNotification(records,control){
 const by=Object.fromEntries(records.map(r=>[r.phase,r]));
 if(!control||control==='premature-dispatch'){
  const r=by['commit-before-dispatch'];ensure(r&&r.seen.length>0,'NOTIFY_COMMIT_MARKER_MISSING');
  if(control)ensure(r.seen[0].rows.length===0&&r.saved.length===1,'NOTIFY_PRECOMMIT_EFFECT_NOT_REACHED');
  else ensure(r.seen.length===1&&r.seen[0].rows.length===1&&r.seen[0].rows[0].state==='attempting'&&r.saved[0].state==='accepted','NOTIFY_COMMIT_BEFORE_EFFECT');
 }
 if(!control||control==='retry-identity'){
  const r=by['child-death-uncertain-retry'];ensure(r&&r.accepted.phase==='synthetic-acceptance-no-completion'&&r.died.signal==='SIGKILL','NOTIFY_PLANNED_FAULT_INJECTION_NOT_REACHED');
  ensure(r.before.length===1&&r.before[0].state==='attempting'&&r.before[0].request_id===r.accepted.id&&r.retried.length===1,'NOTIFY_UNCERTAIN_COMMITTED_INPUT');
  if(control)ensure(r.retried[0].id!==r.accepted.id&&r.after.length===2,'NOTIFY_RETRY_NEW_ID_ABLATION');
  else ensure(r.retried[0].id===r.accepted.id&&r.after.length===1&&r.after[0].state==='accepted'&&r.after[0].attempt===2,'NOTIFY_SAME_ID_RECOVERY');
 }
 if(!control||control==='failed-accepted'){
  const r=by['transaction-abort-and-uncertain-callback'];ensure(r&&r.visibleDuringInsert.length===0&&r.attempts===1&&r.uncertain.length===1,'NOTIFY_ROLLBACK_OR_CALLBACK_NOT_REACHED');
  ensure(r.uncertain[0].state===(control?'accepted':'uncertain'),'NOTIFY_FAILED_CALLBACK_STATE');
 }
 if(!control||control==='suppression'){
  const r=by['queued-suppression'];ensure(r&&r.pending.length===1,'NOTIFY_PENDING_REQUEST_NOT_REACHED');same(r.foreign,r.foreignAfter,'NOTIFY_FOREIGN_CHANGED');
  if(control)ensure(r.attempts===2&&r.suppressed[0].state==='uncertain','NOTIFY_SUPPRESSION_BYPASS_NOT_REACHED');
  else ensure(r.attempts===1&&r.suppressed[0].state==='cancelled','NOTIFY_CURRENT_SUPPRESSION_NOT_APPLIED');
 }
 if(!control){
  const r=by['restricted-role-rls'];ensure(r&&r.observed.length===1,'NOTIFY_RLS_ROWS');same(r.roles,[{rolsuper:false,rolbypassrls:false}],'NOTIFY_ELEVATED_ROLE');same(r.b,r.foreignAfter,'NOTIFY_RLS_FOREIGN_CHANGED');
 }
 if(!control||control==='readiness'){
  const rs=records.filter(r=>r.phase.startsWith('unsafe-readiness-'));ensure(rs.length===(control?1:4),'NOTIFY_UNSAFE_METADATA_MARKERS');
  for(const r of rs){
   if(control)ensure(r.scenario==='rls-disabled'&&r.effects===1&&r.physical.length===1&&!r.error,'NOTIFY_READINESS_BYPASS_NOT_REACHED');
   else ensure(r.effects===0&&r.physical.length===0&&r.error?.message==='NOTIFICATION_SCHEMA_UNSAFE','NOTIFY_UNSAFE_METADATA_NOT_REFUSED');
  }
 }
 if(!control){
  const r=by['durable-receipt-clear'];ensure(r&&r.clears.length===1&&r.clears[0].request_id===r.alarm.request_id,'NOTIFY_DURABLE_RECEIPT_REFERENCE');
  ensure(r.after.find(x=>x.request_id===r.alarm.request_id).cleared_at!==null&&r.after.some(x=>x.payload.clear&&x.state==='accepted'),'NOTIFY_EXPLICIT_CLEAR_NOT_PERSISTED');
 }
};
