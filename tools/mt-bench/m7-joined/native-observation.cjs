"use strict";
// Exact compact-input contract. Native acceptance, the scheduler's local floor,
// public history and output revision stay in separate fields.
const {createHash}=require('node:crypto');
const canonical=x=>Array.isArray(x)?'['+x.map(canonical).join(',')+']':x&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}':JSON.stringify(x);
const hash=x=>createHash('sha256').update(canonical(x)).digest('hex');
const name=x=>typeof x==='string'&&/^[a-z][a-z0-9_]{0,62}$/.test(x)&&!x.startsWith('pg_')&&!['public','information_schema'].includes(x);
const exact=x=>typeof x==='string'&&/^(0|[1-9][0-9]*)$/.test(x)&&x.length<=19&&BigInt(x)<=9223372036854775807n;
const position=x=>{if(typeof x!=='string'||! /^[0-9a-f]{1,8}\/[0-9a-f]{1,8}$/i.test(x))throw Error('M7_COMPLETION_NATIVE_POSITION');const [a,b]=x.split('/');return (BigInt('0x'+a)<<32n)+BigInt('0x'+b);};
function receipt(n,c,value){
 if(!value||Object.keys(value).sort().join(',')!=='contractDigest,evaluatorConfigSha256,kind,realtimeConfigSha256,selection'||value.kind!=='native-receipt-contract-v1'||! /^[a-f0-9]{64}$/.test(value.contractDigest)||value.evaluatorConfigSha256!==n.evaluatorConfigSha256||value.realtimeConfigSha256!==n.realtimeConfigSha256)throw Error('M7_COMPLETION_NATIVE_RECEIPT');
 if(value.selection!==null){const s=value.selection,b=s?.binding;if(!s||Object.keys(s).sort().join(',')!=='binding,selectionDigest'||! /^[a-f0-9]{64}$/.test(s.selectionDigest)||!b||Object.keys(b).sort().join(',')!=='consumer,generation,lifecycleNamespace,namespace,source'||b.namespace!==c.checkpoint||b.consumer!==n.inputConsumer||b.lifecycleNamespace!==n.lifecycle||b.generation!==n.generation||b.source?.slot!==n.slot)throw Error('M7_COMPLETION_NATIVE_RECEIPT');}
 return value;
}
function source(e,r,selected){
 if(!e?.pgstream?.generation&&!e?.pgstream?.recovery)return null;
 if(!/^[a-f0-9]{32}$/.test(e.pgstream.generation)||!e.pgstream.recovery||!name(e.pgstream.slot)||!name(e.trustedWorker?.activity)||!/^evaluator-[A-Za-z0-9_-]{1,100}$/.test(e.consumer)||e.selectedIntake||r.intakeProfile)throw Error('M7_COMPLETION_NATIVE_SOURCE');
 const n={kind:'compact-native-v1',inputConsumer:e.consumer,lifecycle:e.trustedWorker.activity,slot:e.pgstream.slot,generation:e.pgstream.generation,evaluatorConfigSha256:hash(e),realtimeConfigSha256:hash(r)};
 if(selected!==undefined)n.receipt=receipt(n,{checkpoint:e.postgres?.namespaces?.checkpoint},selected);
 return n;
}
function validateConfig(c){
 const n=c.native;
 if(!n||Object.keys(n).sort().join(',')!==(n.receipt===undefined?'evaluatorConfigSha256,generation,inputConsumer,kind,lifecycle,realtimeConfigSha256,slot':'evaluatorConfigSha256,generation,inputConsumer,kind,lifecycle,realtimeConfigSha256,receipt,slot')||n.kind!=='compact-native-v1'||c.kind!=='evaluator-work-v2'||!/^evaluator-[A-Za-z0-9_-]{1,100}$/.test(n.inputConsumer)||n.inputConsumer+'-completed'!==c.consumer||!name(n.lifecycle)||!name(n.slot)||! /^[a-f0-9]{32}$/.test(n.generation)||![n.evaluatorConfigSha256,n.realtimeConfigSha256].every(x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x))||c.binding.nativeConfigurationSha256!==hash(n))throw Error('M7_COMPLETION_NATIVE_BINDING');
 if(n.receipt!==undefined)receipt(n,c,n.receipt);
 return n;
}
function fields(c){
 const n=validateConfig(c);
 return `jsonb_build_object('kind',i.projection->0->>'kind','inputFloor',i.checkpoint::text,'persistedFloor',i.projection->0->>'floor','compact',NOT ((i.projection->0) ? 'rows'),'stream',i.projection->0->'stream','currentRestore',l.generation::text,'phase',l.phase,'actualSource',jsonb_build_object('system_id',(pg_control_system()).system_identifier::text,'timeline',(pg_control_checkpoint()).timeline_id,'database',current_database(),'slot','${n.slot}'),'raw',jsonb_build_object('kind',i.projection->1->>'kind','head',i.projection->1->>'head','base',i.projection->1->>'base'))`;
}
function joins(c){const n=validateConfig(c);return ` LEFT JOIN "${c.checkpoint}".tenant_consumer_checkpoint i ON i.tenant_id=w.tenant_id AND i.consumer='${n.inputConsumer}' LEFT JOIN "${n.lifecycle}".tenant_lifecycle_windows l ON l.tenant_id=w.tenant_id`;}
function snapshot(row,c){
 const n=validateConfig(c),v=row.native,s=v?.stream;
 if(!v||v.kind!=='clinical-stream-v2'||v.compact!==true||!exact(v.inputFloor)||!exact(v.persistedFloor)||BigInt(v.inputFloor)>BigInt(Number.MAX_SAFE_INTEGER)||v.inputFloor!==v.persistedFloor||!exact(v.currentRestore)||BigInt(v.currentRestore)<1n||!['active','suspended'].includes(v.phase))throw Error('M7_COMPLETION_NATIVE_STATE');
 if(s===null||s===undefined)throw Error('M7_COMPLETION_NATIVE_INVALIDATED');
 if(s.generation!==n.generation+':'+v.currentRestore||canonical(s.source_identity)!==canonical(v.actualSource))throw Error('M7_COMPLETION_NATIVE_SOURCE');
 if(n.receipt?.selection&&canonical(n.receipt.selection.binding.source)!==canonical(v.actualSource))throw Error('M7_COMPLETION_NATIVE_SOURCE');
 const a=s.source_identity;
 if(!a||Object.keys(a).sort().join(',')!=='database,slot,system_id,timeline'||!exact(a.system_id)||!Number.isSafeInteger(a.timeline)||a.timeline<1||typeof a.database!=='string'||!a.database||a.slot!==n.slot)throw Error('M7_COMPLETION_NATIVE_SOURCE');
 position(s.snapshot_position);if(s.accepted_position!==null)position(s.accepted_position);
 const raw=v.raw;
 if(!raw||raw.kind!=='storage-events-v1'||!exact(raw.head)||!exact(raw.base)||BigInt(raw.base)>BigInt(raw.head))throw Error('M7_COMPLETION_NATIVE_RAW');
 // Raw continuity is observed; no raw delivery is inferred from this snapshot.
 return {source:{...a},generation:s.generation,inputFloor:v.inputFloor,snapshotPosition:s.snapshot_position,acceptedPosition:s.accepted_position,restoreGeneration:v.currentRestore,raw:{...raw}};
}
function assess(row,witness,c,progress=false){
 let value;try{value=snapshot(row,c);}catch(e){return {ready:false,code:e.message};}
 const target=witness.nativeTarget??value;
 if(canonical(target.source)!==canonical(value.source)||target.generation!==value.generation||target.restoreGeneration!==value.restoreGeneration||!exact(target.inputFloor))return {ready:false,code:'M7_COMPLETION_NATIVE_FENCE'};
 // Explicit lifecycle invalidation can reset the snapshot boundary to 0/0.
 // Accepted commit coverage keeps its own source/generation/position fence.
 try{position(target.snapshotPosition);if(target.acceptedPosition!==null&&(value.acceptedPosition===null||position(value.acceptedPosition)<position(target.acceptedPosition)))return {ready:false,code:'M7_COMPLETION_NATIVE_FENCE'};}catch{return {ready:false,code:'M7_COMPLETION_NATIVE_POSITION'};}
 const completed=row.state?.completed?.bootstrap,observed=row.state?.observed?.bootstrap,output=row.state?.output;
 if(progress)return {ready:true,coverage:value};
 if(!exact(observed)||!exact(completed)||BigInt(completed)>BigInt(observed)||BigInt(completed)<BigInt(target.inputFloor)||BigInt(completed)>BigInt(value.inputFloor))return {ready:false,code:'M7_COMPLETION_PENDING'};
 const covered=row.typed?.inputFloor,floor=String(output?.inputCheckpoint),resultFloor=String(output?.result?.checkpoint);
 if(!exact(covered)||BigInt(covered)<BigInt(target.inputFloor)||BigInt(covered)<BigInt(completed)||BigInt(covered)>BigInt(value.inputFloor)||!exact(floor)||!exact(resultFloor)||floor!==resultFloor||BigInt(floor)>BigInt(covered))return {ready:false,code:'M7_COMPLETION_OUTPUT_CLOCK'};
 if(output.restoreGeneration!==value.restoreGeneration)return {ready:false,code:'M7_COMPLETION_NATIVE_FENCE'};
 return {ready:true,coverage:value,targetInputFloor:target.inputFloor,completedInputFloor:covered,completedBootstrap:completed,outputInputFloor:floor};
}
function progress(row,c){
 const value=snapshot(row,c),completed=row.state?.completed?.bootstrap,observed=row.state?.observed?.bootstrap,floor=row.typed?.inputFloor;
 if(!exact(floor)||BigInt(floor)>BigInt(value.inputFloor)||completed!==undefined&&(!exact(completed)||BigInt(floor)<BigInt(completed))||observed!==undefined&&(!exact(observed)||BigInt(observed)>BigInt(value.inputFloor)))throw Error('M7_COMPLETION_NATIVE_STATE');
 return {...value,completedInputFloor:floor};
}
module.exports={hash,source,validateConfig,fields,joins,snapshot,assess,position,progress};
