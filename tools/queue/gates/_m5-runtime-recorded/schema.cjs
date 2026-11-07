'use strict';
const crypto=require('node:crypto');
const ensure=(value,message)=>{if(!value)throw new Error(message);};
const canonical=value=>JSON.stringify(value,(key,item)=>item&&typeof item==='object'&&!Array.isArray(item)?Object.fromEntries(Object.keys(item).sort().map(k=>[k,item[k]])):item);
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const documentHash=value=>sha(canonical(Object.fromEntries(Object.entries(value).filter(([key])=>key!=='projectionSha256'))));
// Reviewed closed vocabulary of synthetic native observations. New fields or
// phases require review; this is not an arbitrary-log redaction/export utility.
const keys=new Set('A B _id a aPhysical accepted accepted_at acked_at acknowledged acks acquired activity adapter after afterFailure afterRestart afterRevoked afterWrites alarm alarm_group alarm_level alarms all allowed attempt attempt_token attempt_until attempts b bAfter bBefore before beforeRestart bgHigh bgLow bgTargetBottom bgTargetBottom bgTargetTop bgnow blocked_until bootError buckets callbacks checkpoint clear cleared_at clears clinical clinicalEligible clinicalIdentity closed code collapsed collection column commits committedReceipts config_identity consumer consumers contexts contract_digest counts created_at current date dateString death debug dedup_key deleted deletedCount delivered denied device devicestatus died direction disabledTenants display doc domain earlyEvents effects effectsAfter effectsBefore eligible emitted enabled entity entries error evaluationRevision event eventName events expectedIdentity expires_at extension failure filtered finished first floor food foreign foreignAfter fromMills group heads health id id_kind identifier identity index inputCheckpoint inserted isEmpty items kind label last lastAckTime lastEmitTime lastHandoffAcceptedAt lastSGV level lock logical mean message mgdl mills name next_at noise normalPolicy notification now observed observedAt observedIntents op operation origin original outcome outcomes output outputRevision outside ownRow payload pending phase physical physicalAfter physicalWhileHeld pid plugin previewConfigError privilege probeType producer profile progress projection properties pushoverSound read ready receipt records refusal refused removed repeated request_id requested requests result retried revision rolbypassrls roles rolsuper route rows rssi runtimeId saved scaled scenario seen selected servers sgv sgvs signal silenceTime source srvCreated srvModified staged stamp startup state status steps suppressed suppression table tables tenant tenant_id tenants thresholds tick title toMills treatments trigger type uncertain unfiltered unsafe value visibleDuringInsert wait_event_type written xid bootRefused'.split(' '));
const phaseFields={
 'preview-startup':['startup','physical'], 'preview-first-result':['first','physical'],
 'preview-cli-restart':['beforeRestart','afterRestart','logs','removed','activity'],
 'preview-backstop':['first','afterWrites','last','physical','removed','activity'],
 'preview-retained-time':['first','written','before','tick','after'], 'preview-time-acquired':['acquired','physical'],
 'preview-config-identity':['first','expectedIdentity','tick','physical'], 'preview-config-disabled':['disabledTenants','current','last','physical'],
 'preview-refusal-row':['written','first','refused','b','health','physical','checkpoint'], 'preview-refusal-byte':['written','first','refused','b','health','physical','checkpoint'],
 'preview-close-fence':['first','physicalWhileHeld','last','health','finished','physicalAfter'],
 'preview-unsafe-grant':['table','column','privilege','allowed','startup','before','after'],
 'native-repeat-restart':['first','repeated','commits','bBefore','bAfter','selected'],
 'native-concurrent-cascade':['outcomes','rows','lock','commits'],
 'native-before-commit':['outside','callbacks'], 'native-rollback-revocation':['failure','staged','afterFailure','denied','afterRevoked','callbacks','commits'],
 'native-isolation':['read','selected','bBefore','bAfter'], 'native-unsafe-writer':['unsafe','aPhysical'],
 'commit-before-dispatch':['seen','saved','heads'], 'child-death-uncertain-retry':['accepted','before','died','retried','after'],
 'transaction-abort-and-uncertain-callback':['visibleDuringInsert','uncertain','attempts'],
 'queued-suppression':['pending','suppressed','attempts','foreign','foreignAfter'], 'restricted-role-rls':['a','b','observed','roles','foreignAfter'],
 'unsafe-readiness-rls-disabled':['scenario','error','effects','physical'], 'unsafe-readiness-broad-table-update':['scenario','error','effects','physical'],
 'unsafe-readiness-schema-create':['scenario','error','effects','physical'], 'unsafe-readiness-foreign-clinical-write':['scenario','error','effects','physical'],
 'durable-receipt-clear':['alarm','clears','after'], 'sink-before-accept':['id','tenant','notification','ownRow'],
 'first-output-before-verdict':['effects','requests','state','health'], 'committed-before-verdict':['rows','state','foreign'],
 'unchanged-wake-before-verdict':['before','after'], 'committed-per-cycle':['rows','state','foreign'],
 'restart-clear-before-verdict':['alarm','clears','state'], 'restart-normal-clear':['alarm','clears','state'],
 'uncertain-before-death':['original','state'], 'uncertain-restart-before-verdict':['original','after','death','all','state'],
 'uncertain-process-restart':['original','after','death','all'], 'control-clear-before-verdict':['suppression','after','state','clinical'],
 'control-ack-with-failed-clinical':['suppression','after','health','state'], 'ack-privilege-before-verdict':['operation','refusal','state'],
 'unsafe-state-before-verdict':['state','effectsBefore','effectsAfter','health'], 'ack-state-readonly-and-rls-refusal':['state','effectsBefore','effectsAfter']
};
function text(value){ensure(typeof value==='string'&&value.length<=32768&&!/[a-z][a-z0-9+.-]*:\/\//i.test(value)&&!/(?:\/home\/|\/Users\/|\/tmp\/|\/var\/run\/)/.test(value),'PROJECTION_PRIVATE_OR_UNBOUNDED_STRING');return value;}
function safe(value,depth=0){
 ensure(depth<32,'PROJECTION_DEPTH');
 if(value===null||typeof value==='boolean')return value;
 if(typeof value==='number'){ensure(Number.isFinite(value),'PROJECTION_UNTYPED_NUMBER');return value;}
 if(typeof value==='string')return text(value);
 if(Array.isArray(value)){ensure(value.length<=1000,'PROJECTION_ARRAY_BOUND');return value.map(x=>safe(x,depth+1));}
 ensure(value&&typeof value==='object','PROJECTION_VALUE');const result={};
 for(const [key,item]of Object.entries(value)){ensure(keys.has(key),'PROJECTION_UNKNOWN_FIELD '+key);result[key]=safe(item,depth+1);}return result;
}
function observation(value){
 const fields=phaseFields[value.phase];ensure(fields,'PROJECTION_UNKNOWN_PHASE');const out={phase:value.phase};
 for(const key of fields){
  if(key==='error'&&!Object.hasOwn(value,key))continue;
  ensure(Object.hasOwn(value,key),'PROJECTION_REQUIRED_FIELD '+value.phase+'.'+key);
  if(key==='logs')out.logs={stdout:/Evaluator preview started/.test(value.logs?.stdout||'')?'Evaluator preview started':''};
  else out[key]=safe(value[key]);
 }
 return out;
}
function report(value){
 const stats=Object.fromEntries(['suites','tests','passes','pending','failures'].map(k=>[k,value.stats[k]]));
 return {stats,tests:value.tests.map(t=>text(t.fullTitle)),failures:value.failures.map(f=>{
  const error={name:text(f.err.name||'Error')};
  if(f.err.code)error.code=text(f.err.code);
  if(/^Timeout of 60000ms exceeded/.test(f.err.message)){error.message='Mocha test timeout';error.timeoutMs=60000;}
  else error.message=text(f.err.message);
  return {title:text(f.fullTitle),error};
 })};
}
module.exports={ensure,canonical,sha,documentHash,safe,text,observation,report};
