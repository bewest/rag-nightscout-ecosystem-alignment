'use strict';
// Private bounded observer. Retains no request/error strings or application data.
const crypto=require('node:crypto'),path=require('node:path');
const STAGES=Object.freeze(['admission','exchange']);
// Exact literals from the selected admission/lifecycle/authority boundaries.
// This is an allowlist, never an uppercase-message pattern or string coercion.
const MESSAGE_SYMBOLS=Object.freeze([
 'LIFECYCLE_WINDOW_SCOPE_INVALID','LIFECYCLE_WINDOW_AMBIENT_SCOPE','LIFECYCLE_WINDOW_CLOSED',
 'LIFECYCLE_WINDOW_SESSION_LOST','LIFECYCLE_WINDOW_QUEUE_TIMEOUT','LIFECYCLE_WINDOW_NOT_READY',
 'LIFECYCLE_WINDOW_DATASTORE_CHANGED','LIFECYCLE_WINDOW_DATASTORE_REPLACED','LIFECYCLE_WINDOW_SCHEMA_UNSAFE',
 'LIFECYCLE_WINDOW_ROLE_UNSAFE','LIFECYCLE_WINDOW_TENANT_UNKNOWN','LIFECYCLE_WINDOW_TENANT_AUTHORITY_REFUSED',
 'DATASTORE_RECOVERY_REBIND_REQUIRED','TENANT_DATA_FORBIDDEN','TENANT_SUSPENDED','TENANT_PAUSED',
 'TENANT_ACTIVITY_UNAVAILABLE','ACTIVITY_UNAVAILABLE','ACTIVITY_STORE_UNAVAILABLE',
 'TENANT_AUTHORITY_UNAVAILABLE','TENANT_AUTHORITY_UNSAFE','TENANT_AUTHORITY_UNKNOWN','TENANT_AUTHORITY_INVALID',
 'TENANT_AUTHORITY_PRINCIPAL_INVALID','TENANT_AUTHORITY_PERMISSION_INVALID',
 'SECRETS_LEGACY_AUTHORITY_UNAVAILABLE','SECRETS_LEGACY_AUTHORITY_UNSAFE','SECRETS_LEGACY_AUTHORITY_UNKNOWN',
 'SECRETS_LEGACY_AUTHORITY_INVALID','SECRETS_OPERATION_UNSUPPORTED','SECRETS_KEY_VERSION',
 'TENANT_EXCHANGE_VERIFIER_INVALID','SECRETS_TOKEN_INVALID'
]);
const MESSAGE_CODES=Object.freeze({...Object.fromEntries(MESSAGE_SYMBOLS.map(code=>[code,code])),
 // pg-pool3.14.0 index.js:224; checkout queue timeout, distinct from new-backend timeout.
 'timeout exceeded when trying to connect':'POOL_CHECKOUT_TIMEOUT',
 // serve/api-admission.js current request-context mismatch; no tenant value is retained.
 'API request belongs to another tenant':'API_REQUEST_TENANT_MISMATCH'
});
const CODES=Object.freeze([...new Set(['TENANT_WARMING','TENANT_UNAVAILABLE','TENANT_ACTIVITY_UNAVAILABLE','TENANT_ACTIVITY_REFUSED','TENANT_EXCHANGE_VERIFIER_INVALID','ACCESS_AUTHORITY_UNAVAILABLE','ACCESS_AUTHORITY_INVALID','AUTHORITY_UNAVAILABLE','AUTHORITY_FORBIDDEN','SECRETS_LEGACY_AUTHORITY_UNAVAILABLE','SECRETS_TOKEN_INVALID','DATASTORE_RECOVERY_REBIND_REQUIRED','LIFECYCLE_WINDOW_TENANT_AUTHORITY_REFUSED','LIFECYCLE_LEASE_ACQUISITION_TIMEOUT',...Object.values(MESSAGE_CODES)])]);
const SQLSTATES=Object.freeze(['08000','08001','08003','08004','08006','08007','08P01','25P02','40001','40P01','53300','53400','55P03','57014','57P01','57P02','57P03']);
const UUID=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
function safeCode(error){
 try{
  const descriptor=Object.getOwnPropertyDescriptor(error||{},'code');
  if(descriptor!==undefined){
   // An unknown explicit code is not overridden by a plausible message.
   const code=descriptor.value;
   return CODES.includes(code)?code:SQLSTATES.includes(code)?'SQLSTATE_'+code:'UNCLASSIFIED';
  }
  const descriptorMessage=Object.getOwnPropertyDescriptor(error||{},'message');
  const message=descriptorMessage?.value;
  return typeof message==='string'&&Object.hasOwn(MESSAGE_CODES,message)?MESSAGE_CODES[message]:'UNCLASSIFIED';
 }catch{return 'UNCLASSIFIED';}
}
function create({owner,source,sourceFiles,persist,instance=crypto.randomUUID(),maxEvents=64}){
 if(!/^[a-f0-9]{32}$/.test(owner)||!/^[a-f0-9]{40}$/.test(source)||!UUID.test(instance)||!sourceFiles||Object.values(sourceFiles).some(x=>!/^[a-f0-9]{64}$/.test(x))||typeof persist!=='function'||!Number.isSafeInteger(maxEvents)||maxEvents<1||maxEvents>64)throw Error('M7_API_CAUSE_BINDING');
 const counters=Object.fromEntries(STAGES.map(stage=>[stage,{started:0,fulfilled:0,rejected:0,thrown:0}])),events=[];let dropped=0,failed=false,installed=false;
 const state=()=>({version:1,kind:'m7-api-cause-v1',owner,source,sourceFiles:{...sourceFiles},instance,installed,counters:structuredClone(counters),events:events.map(x=>({...x})),dropped,failed,qualification:failed||dropped?'UNMEASURED':'COMPLETE'});
 function publish(){try{persist(state());}catch{failed=true;}}
 function markInstalled(){installed=true;publish();}
 function record(stage,outcome,error){
  try{
   if(!STAGES.includes(stage)||!['started','fulfilled','rejected','thrown'].includes(outcome))throw Error('INVALID_OBSERVATION');
   counters[stage][outcome]++;
   if(outcome==='rejected'||outcome==='thrown'){
    const code=safeCode(error),prior=events.find(x=>x.stage===stage&&x.code===code);
    if(prior)prior.count++;else if(events.length<maxEvents)events.push({stage,code,count:1});else dropped++;
   }
  }catch{failed=true;}publish();
 }
 publish();return {state,record,markInstalled};
}
function wrap(fn,stage,tap){
 return function(){
  try{tap.record(stage,'started');}catch{}
  let value;try{value=Reflect.apply(fn,this,arguments);}catch(error){try{tap.record(stage,'thrown',error);}catch{}throw error;}
  if(value instanceof Promise){
   // Return the exact original promise. Observers cannot replace its fulfillment/error.
   try{Promise.prototype.then.call(value,()=>{try{tap.record(stage,'fulfilled');}catch{}},error=>{try{tap.record(stage,'rejected',error);}catch{}});}catch{}
  }else{try{tap.record(stage,'fulfilled');}catch{}}
  return value;
 };
}
function install({root,tap,moduleLoader=require('node:module')}){
 if(!path.isAbsolute(root)||typeof tap?.record!=='function'||typeof tap?.markInstalled!=='function')throw Error('M7_API_CAUSE_INSTALL');
 const target=path.join(root,'lib/server/tenant-app/index.js'),original=moduleLoader._load,seen=new WeakMap(),patches=[];let restored=false;
 const hook=function(request,parent,isMain){
  const file=moduleLoader._resolveFilename(request,parent,isMain),value=Reflect.apply(original,this,arguments);
  if(file!==target)return value;
  if(!value||typeof value.createTenantApp!=='function')throw Error('M7_API_CAUSE_EXPORT');
  if(!seen.has(value)){
   const descriptor=Object.getOwnPropertyDescriptor(value,'createTenantApp'),base=value.createTenantApp;
   if(!descriptor||!Object.hasOwn(descriptor,'value')||descriptor.writable!==true)throw Error('M7_API_CAUSE_EXPORT');
   const replacement=function(options){
    if(options===undefined)return Reflect.apply(base,this,arguments);
    if(!options||typeof options!=='object')return Reflect.apply(base,this,arguments);
    const descriptors=Object.getOwnPropertyDescriptors(options),args=Array.from(arguments);
    for(const [key,stage] of [['admitRequest','admission'],['exchange','exchange']]){
     const desc=descriptors[key];if(desc&&Object.hasOwn(desc,'value')&&typeof desc.value==='function')descriptors[key]={...desc,value:wrap(desc.value,stage,tap)};
    }
    args[0]=Object.defineProperties(Object.create(Object.getPrototypeOf(options)),descriptors);
    return Reflect.apply(base,this,args);
   };
   Object.defineProperty(value,'createTenantApp',{...descriptor,value:replacement});seen.set(value,{descriptor,replacement});patches.push(value);try{tap.markInstalled();}catch{}
  }
  return value;
 };
 moduleLoader._load=hook;
 return {target,restore(){if(restored)return;restored=true;if(moduleLoader._load===hook)moduleLoader._load=original;for(const value of patches){const prior=seen.get(value);if(value.createTenantApp===prior.replacement)Object.defineProperty(value,'createTenantApp',prior.descriptor);}},restoreExport(value){const prior=seen.get(value);if(prior&&value.createTenantApp===prior.replacement)Object.defineProperty(value,'createTenantApp',prior.descriptor);}};
}
function assess(states,{owner,source,sourceFiles,requiredStages=STAGES,requiredFailure}={}){
 if(!Array.isArray(states)||!states.length)return {verdict:'UNMEASURED',code:'M7_API_CAUSE_NO_CAPTURE'};
 const instances=new Set();
 for(const s of states){
  if(s?.version!==1||s.kind!=='m7-api-cause-v1'||s.owner!==owner||s.source!==source||JSON.stringify(s.sourceFiles)!==JSON.stringify(sourceFiles)||!UUID.test(s.instance)||instances.has(s.instance))return {verdict:'UNMEASURED',code:'M7_API_CAUSE_PROVENANCE'};
  instances.add(s.instance);
  if(s.qualification!=='COMPLETE'||s.installed!==true||s.failed!==false||s.dropped!==0||!Array.isArray(s.events)||s.events.length>64)return {verdict:'UNMEASURED',code:'M7_API_CAUSE_INCOMPLETE'};
  for(const stage of STAGES){const c=s.counters?.[stage];if(!c||Object.keys(c).sort().join(',')!=='fulfilled,rejected,started,thrown'||Object.values(c).some(x=>!Number.isSafeInteger(x)||x<0)||c.started<c.fulfilled+c.rejected+c.thrown)return {verdict:'UNMEASURED',code:'M7_API_CAUSE_COUNTER'};}
  const keys=new Set();
  for(const e of s.events){const key=e.stage+':'+e.code;if(Object.keys(e).sort().join(',')!=='code,count,stage'||!STAGES.includes(e.stage)||!(CODES.includes(e.code)||e.code==='UNCLASSIFIED'||SQLSTATES.some(x=>'SQLSTATE_'+x===e.code))||!Number.isSafeInteger(e.count)||e.count<1||keys.has(key))return {verdict:'UNMEASURED',code:'M7_API_CAUSE_EVENT'};keys.add(key);}
  for(const stage of STAGES)if(s.events.filter(e=>e.stage===stage).reduce((n,e)=>n+e.count,0)!==s.counters[stage].rejected+s.counters[stage].thrown)return {verdict:'UNMEASURED',code:'M7_API_CAUSE_COUNTER'};
 }
 if(!Array.isArray(requiredStages)||requiredStages.some(x=>!STAGES.includes(x)))throw Error('M7_API_CAUSE_REQUIRED_STAGE');
 if(requiredStages.some(stage=>!states.some(s=>s.counters[stage].started>0)))return {verdict:'UNMEASURED',code:'M7_API_CAUSE_NO_OBSERVATION'};
 if(requiredFailure&&!states.some(s=>s.events.some(e=>e.stage===requiredFailure.stage&&e.code===requiredFailure.code)))return {verdict:'UNMEASURED',code:'M7_API_CAUSE_EXPECTED_FAILURE_MISSING'};
 return {verdict:'MEASURED',code:'M7_API_CAUSE_CAPTURED',instances:states.length,counters:Object.fromEntries(STAGES.map(stage=>[stage,Object.fromEntries(['started','fulfilled','rejected','thrown'].map(k=>[k,states.reduce((n,s)=>n+s.counters[stage][k],0)]))])),events:states.flatMap(s=>s.events.map(e=>({...e,instance:s.instance}))),scope:'bounded API admission/exchange outcomes; no request correlation or root-cause inference for UNCLASSIFIED'};
}
module.exports={STAGES,CODES,SQLSTATES,safeCode,create,wrap,install,assess};
