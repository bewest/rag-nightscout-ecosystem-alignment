'use strict';
const assert=require('node:assert/strict'),crypto=require('node:crypto');
const canonical=value=>JSON.stringify(value,(key,item)=>item&&typeof item==='object'&&!Array.isArray(item)?Object.fromEntries(Object.keys(item).sort().map(k=>[k,item[k]])):item);
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const documentHash=value=>sha(canonical(Object.fromEntries(Object.entries(value).filter(([key])=>key!=='projectionSha256'))));
const ensure=(value,message)=>assert(value,message);
const PHASES=Object.freeze(['joined-role-recovery','joined-data-parity','joined-consumer-handoff','joined-consumer-plugin-ack','joined-socket-epoch','joined-browser-consumer']);
const RAW={
 'joined-recovery-observations.json':'transport admitted delta sgvs quietRemoval clockUnchanged fullAbsence tightened noProtectedDelivery cleanupErrors',
 'realtime-reader-denials.json':'logical refusal',
 'actual-storage-proof.json':'classification socketsClosed subscriptions baseline STORAGE_CONNECTED_TYPED_CREATE STORAGE_CONNECTED_TYPED_UPDATE STORAGE_CONNECTED_TYPED_DELETE typedWireAmbiguity STORAGE_CURRENT_COLLECTION_REVOKED revocationGrants revocationCurrent revocationPipelineBarrier lastCheckpoint semanticFailure',
 'socket-data-physical-parity.json':'logical attempt producer before expected actual clocks windows pgRaw mongoRaw pgDocuments physicalTypes cleanupErrors',
 'actual-consumer-handoff.json':'events attempts accepted suppressed retryPhysical coldPackets coldPhysicalRows coldAckPhysical coldBeforeAck coldAfterAck coldClear warmEvaluatorPid beforeAckRequestIds beforeAckClearEvents sameIdRetry suppressionStopsDelivery semanticFailure cleanupErrors',
 'actual-plugin-ack.json':'packet reply physical windowBefore beforeOwner ackStartedAt ackReply immediately producerAfter afterOwner pluginAckIgnored originalAbsoluteExpiryPreserved semanticFailure cleanupErrors',
 'actual-socket-epoch.json':'kind namespace read deniedRead protectedEvents handoff errors operatorRestored',
 'actual-browser-consumer.json':'classification origin resolverHosts browserRuntime redirectRefusals initial result',
 'actual-browser-diagnostics.json':'version classification browserRuntime activeStage status stages diagnostics droppedDiagnostics'
};
const OMIT={
 'actual-storage-proof.json':['clients','foreignClients'],
 'actual-consumer-handoff.json':['beforeAckProducer','coldAckProducerObservations','coldAfterAckRequests','relayPhysicalRows','requests'],
 'actual-plugin-ack.json':['producerBefore'],
 'actual-socket-epoch.json':['at','sequence']
};
const FORBIDDEN=/^(?:env|environment|headers|cookies|authorization|password|token|accessToken|jwtToken|transportToken|ciphertext|secret|connectionString|stack|stdout|stderr|url)$/i;
// Nested vocabulary is deliberately finite. An unknown synthetic fixture field
// stops export for review; source changes never silently enlarge the vocabulary.
const NESTED=new Set(('A B _id id identifier id_kind tenant tenant_id transport admitted delta sgvs mgdl mills date dateString sgv direction device srvCreated srvModified created_at updated_at type eventType carbs insulin notes duration enteredBy units clock consumer checkpointNamespace foreignRows twins doc event value colName clients foreignClients clockBefore clockAfter foreignBefore foreignAfter stage marker rows checkpoint projection floor current permissions collections read write write_treatment write_treatments denied grants logical domain stamp last_stamp contract_digest source state count name code message title level group plugin pluginType isAnnouncement clear eventName pushoverSound sound timestamp request_id config_identity dedup_key origin payload attempt attempt_token attempt_until next_at accepted_at receipt cleared_at expires_at acked_at alarm_group alarm_level producer revision alarms effects acks outputRevision inputCheckpoint runtimeId identity evaluatedRevision eligible clinicalIdentity clinicalEligible requested lastAckTime silenceTime lastEmitTime accepted result notification durable first retry responseLost requestId acceptedAt retryAt packet data outcome args before pgRaw pgDocuments mongoRaw expected actual clocks windows postgres mongo kind upper observed after before startedAt finishedAt types descriptors path objectid objectId date string initial normalized wire beforeRevision ackKeys beforeAckRequestIds suppressed cold health tenants last classification sourceHead phaseId pid observedAt beforeAckClearEvents sameIdRetry suppressionStopsDelivery coldClear warmEvaluatorPid coldPackets coldPhysicalRows coldAckPhysical coldBeforeAck coldAfterAck retryPhysical accepted pending suppressed cancelled attempting uncertain cleared request_id queued maxRows pageSize consumerId normalPolicy errors semanticFailure error refusal cleanupErrors originalAbsoluteExpiryPreserved pluginAckIgnored windowBefore beforeOwner ackStartedAt ackReply immediately producerAfter afterOwner main alarm urgentUi events sgvs event initial count resolverHosts origin socketOrSymlinkPaths baseline subscriptions socketsClosed physicalKinds normalizedIdentifierShared deleteDoesNotIdentifyKind typedWireAmbiguity identifier revocationGrants revocationCurrent revocationPipelineBarrier lastCheckpoint version browserRuntime activeStage status stages diagnostics droppedDiagnostics stage edge snapshot snapshotError snapshotUnavailable documentReadyState nightscoutType clientType present connected engineTransport engineReadyState sgvCount hasExpectedSynthetic123 eventNames knownHost route eio transport networkCode messageHash browser executablePath sha256 dev ino mode group current connected collections success read write treatment delta dataUpdate created deleted create update delete errorType name notification result observedIntents graph data nested basal rate time value startDate defaultProfile store timezone dia carbratio sens target_low target_high carbs_hr created_at srvCreated srvModified before pgDocuments mongoRaw pgRaw clientId read_treatment write_profile read_profile index rssi noise scaled max attempt title message bgHigh bgLow bgTargetTop bgTargetBottom thresholds enabled').split(' '));
for(const words of Object.values(RAW))for(const key of words.split(' '))NESTED.add(key);
for(const key of 'foreignTenant foreignHost Synthetic trigger category portion unit timeAsSeconds NSCLIENT_ID lastSGV notifyhash dataSize ctid debug output profiles ack collection recipient clearedRequestIds devicestatus treatments food activity profile entries cals mbgs dbstats lastUpdated errorcodes physicalTypes beforeMongo beforePostgres host port scheme coldAcquisition entryCount dataParityOracle reviewed file initialStateExport replayExport storageProofExpectation browserHost browserResolverHosts'.split(' '))NESTED.add(key);
function string(value){
 ensure(typeof value==='string'&&value.length<=65536,'ROLE_STRING_BOUND');
 ensure(!/[a-z][a-z0-9+.-]*:\/\//i.test(value)&&!/(?:\/home\/|\/Users\/|\/tmp\/|\/var\/run\/)/.test(value),'ROLE_PRIVATE_OR_URI');
 ensure(!/\bBearer\s|eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/.test(value),'ROLE_CREDENTIAL_VALUE');return value;
}
function safe(value,depth=0){
 ensure(depth<40,'ROLE_DEPTH');if(value===null||typeof value==='boolean')return value;
 if(typeof value==='number'){ensure(Number.isFinite(value),'ROLE_NUMBER');return value;}
 if(typeof value==='string')return string(value);
 if(Array.isArray(value)){ensure(value.length<=4096,'ROLE_ARRAY_BOUND');return value.map(x=>safe(x,depth+1));}
 ensure(value&&typeof value==='object'&&Object.getPrototypeOf(value)===Object.prototype,'ROLE_OBJECT');const out={};
 for(const [key,item]of Object.entries(value)){ensure(!FORBIDDEN.test(key)&&NESTED.has(key),'ROLE_UNKNOWN_OR_CREDENTIAL_FIELD '+key);out[key]=safe(item,depth+1);}return out;
}
function pick(value,keys){ensure(value&&typeof value==='object'&&!Array.isArray(value),'ROLE_RECORD');return Object.fromEntries(keys.split(' ').filter(k=>Object.hasOwn(value,k)).map(k=>[k,value[k]]));}
function origin(value){if(value&&typeof value==='object'){ensure(Object.keys(value).sort().join(',')==='host,port,scheme'&&value.scheme==='http'&&['one.example.test','two.example.test'].includes(value.host)&&Number.isSafeInteger(value.port)&&value.port>0&&value.port<65536,'ROLE_SYNTHETIC_ORIGIN');return value;}const u=new URL(value);ensure(u.protocol==='http:'&&['one.example.test','two.example.test'].includes(u.hostname)&&!u.username&&!u.password&&u.pathname==='/'&&!u.search&&!u.hash,'ROLE_SYNTHETIC_ORIGIN');return {scheme:'http',host:u.hostname,port:Number(u.port||80)};}
function runtime(value){ensure(value?.browser==='chromium'&&/^[a-f0-9]{64}$/.test(value.sha256),'ROLE_BROWSER_ARTIFACT');return {browser:'chromium',executablePath:'reviewedChromium',sha256:value.sha256,...(value.version?{version:string(value.version)}:{})};}
function projectRaw(filename,value){
 ensure(Object.hasOwn(RAW,filename),'ROLE_RAW_FILENAME');
 const closed=row=>{ensure(Object.keys(row).every(key=>RAW[filename].split(' ').includes(key)||(OMIT[filename]||[]).includes(key)),'ROLE_UNREVIEWED_RAW_FIELD '+filename);return pick(row,RAW[filename]);};
 const selected=Array.isArray(value)?value.map(closed):closed(value);
 if(filename==='actual-consumer-handoff.json'){
  const cold=row=>{const out=pick(row,'classification sourceHead phaseId pid observedAt last');out.health={tenants:row.health.tenants.map(t=>pick(t,'tenant code'))};return out;};
  for(const field of ['coldBeforeAck','coldAfterAck'])if(selected[field])selected[field]=cold(selected[field]);
  if(selected.coldAckPhysical)selected.coldAckPhysical={...selected.coldAckPhysical,cold:cold(selected.coldAckPhysical.cold)};
 }
 if(filename==='actual-browser-consumer.json'){
  // Original strict verifier runs BEFORE this transform. Structured origins
  // preserve host/port equality rather than replacing all URLs with one value.
  selected.origin=origin(selected.origin);selected.initial={...selected.initial,main:origin(selected.initial.main),alarm:origin(selected.initial.alarm)};selected.browserRuntime=runtime(selected.browserRuntime);
 }
 if(filename==='actual-browser-diagnostics.json')selected.browserRuntime=runtime(selected.browserRuntime);
 // Origin objects belong only at the reviewed browser locations.
 const validate=(value,depth=0)=>{
  ensure(depth<40,'ROLE_DEPTH');
  if(value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join(',')==='host,port,scheme'){
   ensure(value.scheme==='http'&&['one.example.test','two.example.test'].includes(value.host)&&Number.isSafeInteger(value.port)&&value.port>0&&value.port<65536,'ROLE_ORIGIN');return value;
  }
  if(Array.isArray(value)){ensure(value.length<=4096,'ROLE_ARRAY_BOUND');return value.map(x=>validate(x,depth+1));}
  if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>{ensure(!FORBIDDEN.test(k)&&NESTED.has(k),'ROLE_UNKNOWN_OR_CREDENTIAL_FIELD '+k);return [k,validate(v,depth+1)];}));
  return safe(value);
 };return validate(selected);
}
function sequence(plan){ensure(canonical(plan.phases)===canonical(PHASES),'ROLE_EXACT_SIX_PHASES');ensure(plan.controls.length===6&&new Set(plan.controls.map(c=>c.id)).size===6,'ROLE_EXACT_SIX_CONTROLS');return [...PHASES.map(phase=>({id:'ordinary-'+phase,phase,kind:'ordinary'})),...plan.controls.map(c=>({id:c.id,phase:c.phase,kind:'control'})),...PHASES.map(phase=>({id:'restored-'+phase,phase,kind:'restored'}))];}
function configuration(value){const out=pick(value,'sourceHead tenant foreignTenant host foreignHost browserHost browserResolverHosts storageProofExpectation dataParityOracle');if(value.coldAcquisition)out.coldAcquisition={entryCount:value.coldAcquisition.entryCount};if(value.browserRuntime)out.browserRuntime=runtime(value.browserRuntime);return safe(out);}
module.exports={ensure,canonical,sha,documentHash,PHASES,RAW,string,safe,pick,origin,runtime,projectRaw,configuration,sequence};
