'use strict';
const crypto=require('node:crypto');
const ensure=(ok,message)=>{if(!ok)throw new Error(message);};
function canonical(value){if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';return JSON.stringify(value);}
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const payloadHash=value=>sha(canonical(Object.fromEntries(Object.entries(value).filter(([key])=>!['projectionSha256','planSha256'].includes(key)))));
const documentHash=value=>sha(canonical(Object.fromEntries(Object.entries(value).filter(([key])=>key!=='projectionSha256'))));
const text=value=>{ensure(typeof value==='string'&&value.length<=32768&&!/[a-z][a-z0-9+.-]*:\/\//i.test(value)&&!/(?:\/home\/|\/Users\/|\/tmp\/|\/var\/lib\/docker\/|\/var\/run\/)/.test(value),'M6_PRIVATE_OR_UNBOUNDED_STRING');return value;};
const opaqueFields={
 'secrets.secret_records':['ciphertext','id'], 'secrets.secret_audit':['secret_id'],
 'legacy.legacy_credential_config':['root_reference_id'], 'legacy.legacy_credential_subjects':['token_prefix'],
 'access.access_credentials':['credential_id'], 'access.access_sessions':['credential_id','session_id'], 'access.access_keys':['kid']
};
const valueKeys=["DISPLAY_UNITS","SHOW_SECONDS","_id","accepted_at","acked_at","acks","actions","active","after","alarm_group","alarm_level","alarms","anonymous_roles","artifact_digest","attempt","attempt_token","attempt_until","attgenerated","attidentity","attname","attnotnull","backupAccepted","before","blocked_until","boundary","can_configure","can_update","cancelled","cancelledAt","cancelled_at","cancelled_by","cancelled_consumer","catalogue_digest","ceiling","check","checkpoint","checksum","childAfter","childBefore","child_name","child_namespace","ciphertext","claimFirst","claimId","claim_id","clear","cleared_at","clinicalIdentity","code","codes","column","columns","command","config_identity","confirmed_at","confirmed_by","confirmed_consumer","conname","constraints","consumer","contract_digest","count","created_at","credential_id","current","date","dateString","dedup_key","definition","delegable","descendant_only","device","display_name","doc","duration","effects","enabled","eraseCodes","eventType","event_id","event_time","execute","executed_at","executed_by","executed_consumer","expires_at","exportAccepted","extension","extraOmitted","family","files","flag","format","generation","grants","group","hiddenRows","id","id_kind","identifier","identity","increment_by","inheritance","inserted","insertion_ordinal","isValid","isolation","kid","kind","label","lastAckTime","lastEmitTime","last_stamp","last_value","ledger","level","max","mbg","message","name","next","next_at","notes","nullable","ok","operation","ordered","origin","outcomes","output","owner_fence","parent_name","parent_namespace","payload","permissions","phase","plane","plugin","polcmd","policies","policy","polpermissive","polroles","populated","principal","priorCounter","producer","projection","purpose","quiesced","receipt","reference","refusal","relations","relforcerowsecurity","relispartition","relkind","relname","relrowsecurity","renamed","requestId","request_id","requested_at","requested_by","requested_consumer","restored_from","resumed","retainedArtifact","revision","roleClass","role_name","root_reference_id","rowCount","schemaname","scope","secret_id","sequencename","sequences","session_id","sgv","silenceTime","srvCreated","srvModified","start_value","startedAt","started_at","started_by","started_consumer","state","subject_id","synthetic","sysTime","table","target_version","tenant","tenantRestoreComplete","tenant_id","title","token_prefix","type","using","value","values","version","wholeCFixtureActors","zero"];
const physicalFields=['ledger','columns','rows','constraints','policies','isolation','sequences','relations','inheritance'];
const artifactPhases=['C1-independent-artifact-before-verdict','C3-independent-OLD-artifact-before-NEW','C3-interrupted-OLD-artifact-before-NEW'];
const physicalPhases=[
 'C1-source-before-verdict','C1-restored-before-verdict','C1-after-denials-before-verdict',
 'C2-empty-before','C2-tamper-physical-before-verdict','C2-damaged-target-before-verdict','C2-interrupted-before-verdict','C2-source','C2-rerun-before-verdict',
 'C3-OLD-before-verdict','C3-NEW-before-verdict','C3-interruption-OLD-before','C3-interruption-lifecycle-before','C3-interrupted-lifecycle-before-verdict',
 'C4-NEW-forensic-before-rollback','C4-fresh-OLD-before-verdict','C4-NEW-retained-before-verdict',
 ...['profile','heads','requests'].flatMap(k=>[false,true].flatMap(v=>['C4-guard-before-'+k+'-'+v,'C4-guard-after-before-verdict-'+k+'-'+v])),
 'C5-inheritance-before','C5-inheritance-after-before-verdict','C5-known-ledger-drift-before','C5-known-ledger-drift-after-before-verdict','C5-unknown-ledger-before','C5-unknown-ledger-after-before-verdict',
 'C5-combined-ledger-physical-before','C5-combined-ledger-physical-after-before-verdict','C5-combined-ledger-physical-preserved',
 'C5-unconfirmed-before-verdict','C5-foreign-request-before-verdict','C5-race-before-verdict','C5-execute-cancel-after-before-verdict','C5-destructive-rollback-before-verdict','C5-deleted-before-verdict',
 'C5-identity-import-refusal-before-verdict','C5-identity-refusal-foreign-before-verdict','C5-canonical-writer-foreign-before-verdict','C5-late-write-before-refusal','C5-late-write-after-before-verdict','C5-revoked-authority-before','C5-revoked-authority-after-before-verdict'
];
const specialFields={
 'actual-role-statement':['roleClass','kind','table','operation','column?','code','count'],
 'actual-writer-next-identity':['kind','max','next'], 'expected-refusal':['label','codes','name'],
 'C2-tamper-actual-statements-before-verdict':null,'C2-tamper-completed-SQL-before-verdict':null,'C2-tamper-statement-categories':null,
 'C2-durability-physical-before-verdict':['boundary','renamed','files'],'C2-durability-physical':['boundary','renamed','files'],
 'C3-interruption-failure':['codes','retainedArtifact'],'C4-actual-OLD-record-refusal':['refusal'],'C4-guard-result':['family','populated','codes'],
 'C5-inheritance-effects-before-verdict':['exportAccepted','extraOmitted','childBefore','childAfter','eraseCodes'],
 'C5-known-ledger-drift-effects-before-verdict':['hiddenRows','backupAccepted','eraseCodes'],
 'C5-unknown-ledger-effects-before-verdict':['relations','eraseCodes'],
 'C5-execute-cancel-outcomes-before-verdict':['executeFirst','barriers','graphs','outcomes'],
 'C5-race-outcomes':['claimFirst','outcomes'], 'C5-live-writer-physical-before-verdict':['proof','clock'],
 'C5-live-writer-observation':null,'C5-identity-refusal-sequences-before-verdict':['before','after','tenantRestoreComplete'],
 'C5-next-canonical-writer-before-verdict':['inserted','priorCounter','scope']
};
const allowedPhases=new Set([...physicalPhases,...artifactPhases,...Object.keys(specialFields)]);
function fields(value,names){const out={};for(const raw of names){const optional=raw.endsWith('?'),name=raw.replace(/\?$/,'');if(optional&&!Object.hasOwn(value,name))continue;ensure(Object.hasOwn(value,name),'M6_REQUIRED_FIELD '+name);out[name]=value[name];}return out;}
function expand(value,dict){if(value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===1&&value.frame){const frame=dict.frames[value.frame];ensure(frame&&sha(canonical(frame))===value.frame,'M6_FRAME_HASH');return Object.fromEntries(Object.entries(frame).map(([key,refs])=>{const metadata=dict.metadata[refs.metadata],rows=dict.rowSets[refs.rows];ensure(metadata&&rows&&sha(canonical(metadata))===refs.metadata&&sha(canonical(rows))===refs.rows,'M6_DICTIONARY_HASH');return [key,{...metadata,rows}];}));}if(Array.isArray(value))return value.map(v=>expand(v,dict));if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,expand(v,dict)]));return value;}
module.exports={payloadHash,valueKeys,ensure,canonical,sha,documentHash,text,opaqueFields,physicalFields,physicalPhases,artifactPhases,specialFields,allowedPhases,fields,expand};
