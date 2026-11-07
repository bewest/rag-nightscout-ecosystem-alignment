'use strict';
const ensure=(v,m)=>{if(!v)throw new Error(m);};
const same=(a,b,m)=>ensure(JSON.stringify(a)===JSON.stringify(b),m);
module.exports=function verifyAlarm(records,control){
 const by=Object.fromEntries(records.map(r=>[r.phase,r]));
 if(!control||['repeat','consume'].includes(control)){
  const r=by['native-repeat-restart'];ensure(r&&r.first.length===1&&r.repeated.length===1,'ALARM_PHYSICAL_REPEAT_MISSING');
  ensure(r.commits.length>=2&&r.commits.every(c=>c.status==='committed'),'ALARM_REAL_COMMIT_RECEIPTS');
  same(r.bBefore,r.bAfter,'ALARM_REPEAT_FOREIGN_CHANGED');
  if(control==='repeat')ensure(Number(r.repeated[0].expires_at)>Number(r.first[0].expires_at),'ALARM_REPEAT_ABLATION_NOT_REACHED');
  else same(r.first,r.repeated,'ALARM_ORIGINAL_EXPIRY_CHANGED');
  ensure(r.selected.result.emitted.length===(control==='consume'?3:2),'ALARM_CONSUMPTION_ORACLE');
 }
 if(!control||control==='cascade'){
  const r=by['native-concurrent-cascade'];ensure(r&&r.lock.length>0&&r.lock.every(x=>x.wait_event_type==='Lock'),'ALARM_ACTUAL_LOCK_NOT_OBSERVED');
  ensure(r.outcomes.every(x=>x.delivered)&&r.commits.every(x=>x.status==='committed'),'ALARM_CONCURRENT_COMMITS');
  same(r.rows.map(x=>x.alarm_level),control?[2]:[1,2],'ALARM_CASCADE_PHYSICAL_LEVELS');
  ensure(r.rows.every(x=>Number(x.expires_at)-Number(x.acked_at)===60000),'ALARM_FIRST_WINDOW_DID_NOT_WIN');
 }
 if(!control||['authority','precommit'].includes(control)){
  const before=by['native-before-commit'];ensure(before&&before.outside.length===0,'ALARM_UNCOMMITTED_ROW_VISIBLE');
  ensure(before.callbacks===(control==='precommit'?1:0),'ALARM_CALLBACK_COMMIT_BOUNDARY');
  if(control!=='precommit'){
   const r=by['native-rollback-revocation'];ensure(r&&r.failure.delivered===false&&r.staged.length===0&&r.afterFailure.length===0,'ALARM_ACTUAL_ROLLBACK');
   if(control==='authority'){
    ensure(r.denied.delivered===true&&r.afterRevoked.length===1&&r.callbacks===1&&
      r.commits.length===2&&r.commits[0].status==='aborted'&&r.commits[1].status==='committed','ALARM_REVOKED_AUTHORITY_ABLATION');
    const row=r.afterRevoked[0],at=Number(row.acked_at),expiry=Number(row.expires_at);
    ensure(row.tenant_id==='11111111-1111-4111-8111-111111111111'&&row.alarm_group==='default'&&row.alarm_level===1&&
      Number.isSafeInteger(at)&&at>1e12&&Number.isSafeInteger(expiry)&&expiry-at===60000,'ALARM_REVOKED_AUTHORITY_ROW');
   }
   else ensure(!r.denied.delivered&&r.afterRevoked.length===0&&r.commits.every(c=>c.status==='aborted')&&r.callbacks===1,'ALARM_CURRENT_AUTHORITY_OR_NOACK');
  }
 }
 if(!control){
  const r=by['native-isolation'];ensure(r&&r.read.length===0&&r.selected.result.emitted.length===1,'ALARM_TENANT_ISOLATION');same(r.bBefore,r.bAfter,'ALARM_FOREIGN_MUTATION');
  const u=by['native-unsafe-writer'];ensure(u&&!u.unsafe.delivered&&u.aPhysical.length===0,'ALARM_UNSAFE_WRITER_NOT_REFUSED');
 }
};
