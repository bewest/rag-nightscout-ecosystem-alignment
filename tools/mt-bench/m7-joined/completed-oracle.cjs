'use strict';
// Actual pgstream checkpoint/output contract. SQL is independent of worker
// inspection and counts only the caller's synthetic marker. No connection here.
const {createHash}=require('node:crypto'),native=require('./native-observation.cjs');
const SOURCES=['clock','settings','policy','activity','lifecycle','bootstrap'];
const NAME=/^[a-z][a-z0-9_]{0,62}$/,UUID=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const fail=code=>{throw Error(code);};
const canonical=value=>Array.isArray(value)?'['+value.map(canonical).join(',')+']':value&&typeof value==='object'?'{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}':JSON.stringify(value);
const freeze=value=>{if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;};
function plain(value,depth=0,budget={nodes:0}){
 if(++budget.nodes>200000||depth>16)fail('M7_COMPLETION_PROFILE_VALUE_BOUND');
 if(value===null||typeof value==='boolean'||typeof value==='string'&&value.length<=8192||typeof value==='number'&&Number.isFinite(value))return value;
 if(!value||typeof value!=='object'||![Object.prototype,Array.prototype,null].includes(Object.getPrototypeOf(value)))fail('M7_COMPLETION_PROFILE_PLAIN_VALUE');
 const descriptors=Object.getOwnPropertyDescriptors(value),keys=Object.keys(descriptors).filter(k=>!(Array.isArray(value)&&k==='length'));
 if(keys.length>(Array.isArray(value)?10000:256)||keys.some(k=>['__proto__','prototype','constructor'].includes(k)||!descriptors[k].enumerable||!Object.hasOwn(descriptors[k],'value')))fail('M7_COMPLETION_PROFILE_PLAIN_VALUE');
 if(Array.isArray(value)){if(value.length!==keys.length||keys.some((k,i)=>k!==String(i)))fail('M7_COMPLETION_PROFILE_PLAIN_VALUE');return keys.map(k=>plain(descriptors[k].value,depth+1,budget));}
 return Object.fromEntries(keys.map(k=>[k,plain(descriptors[k].value,depth+1,budget)]));
}
function selection(config){if(config.selection!==undefined||config.binding?.selectedProfile!==undefined)fail('M7_COMPLETION_SELECTED_PROFILE_RETIRED');}
function binding(value){
 if(!value||Object.keys(value).sort().join(',')!==(value.nativeConfigurationSha256!==undefined?'imageId,instrument,kind,nativeConfigurationSha256,pair':'imageId,instrument,kind,pair')||!['evaluator-work-v1','evaluator-work-v2'].includes(value.kind)||!value.pair||Object.keys(value.pair).sort().join(',')!=='core,deploy'||!Object.values(value.pair).every(v=>/^[a-f0-9]{40}$/.test(v))||!/^sha256:[a-f0-9]{64}$/.test(value.imageId)||!/^[a-f0-9]{64}$/.test(value.instrument))fail('M7_COMPLETION_BINDING');
 if(value.nativeConfigurationSha256!==undefined&&(value.kind!=='evaluator-work-v2'||typeof value.nativeConfigurationSha256!=='string'||! /^[a-f0-9]{64}$/.test(value.nativeConfigurationSha256)))fail('M7_COMPLETION_NATIVE_BINDING');

 return value;
}
function prepare(config){const owned=plain(config);binding(owned.binding);if(!!owned.native!==!!owned.binding.nativeConfigurationSha256)fail('M7_COMPLETION_NATIVE_BINDING');if(owned.native)native.validateConfig(owned);selection(owned);freeze(owned);return owned;}
function source(evaluator,realtime,selected){
 if(evaluator?.selectedIntake!==undefined||realtime?.intakeProfile!==undefined)fail('M7_COMPLETION_SELECTED_PROFILE_RETIRED');
 binding(selected);
 const ns=evaluator?.postgres?.namespaces,completed=realtime?.completedOutput;
 if(!evaluator?.pgstream||!ns||!['clock','checkpoint','entries'].every(key=>NAME.test(ns[key]))||!/^evaluator-[A-Za-z0-9_-]{1,100}$/.test(evaluator.consumer)||completed?.namespace!==ns.checkpoint||completed?.consumer!==evaluator.consumer)fail('M7_COMPLETION_SOURCE');
 const config={clock:ns.clock,checkpoint:ns.checkpoint,entries:ns.entries,consumer:evaluator.consumer+'-completed',kind:selected.kind,binding:selected};

 const n=native.source(evaluator,realtime);if(n){config.native=n;config.binding={...config.binding,nativeConfigurationSha256:native.hash(n)};return prepare(config);}
 return config;
}
function query(config,ids,marker,progress=false){
 if(typeof progress!=='boolean'||progress&&config.kind!=='evaluator-work-v2')fail('M7_COMPLETION_SELECTOR');
 if(!['clock','checkpoint','entries'].every(key=>NAME.test(config[key]))||!/^evaluator-[A-Za-z0-9_-]{1,100}-completed$/.test(config.consumer)||!['evaluator-work-v1','evaluator-work-v2'].includes(config.kind)||!Array.isArray(ids)||!ids.length||!ids.every(id=>UUID.test(id))||!/^[a-z0-9-]{1,120}$/.test(marker))fail('M7_COMPLETION_SELECTOR');
 binding(config.binding);selection(config);if(config.kind!==config.binding.kind)fail('M7_COMPLETION_READER_MISMATCH');
 const selected=ids.map(id=>"'"+id+"'").join(',');
 const vector=column=>`(SELECT coalesce(jsonb_object_agg(k,v),'{}'::jsonb) FROM (VALUES ${SOURCES.map((key,i)=>`('${key}',c.${column}[${i+1}]::text)`).join(',')}) s(k,v) WHERE v IS NOT NULL)`;
 let state='c.projection->0',typed='NULL::jsonb';

 if(config.kind==='evaluator-work-v2'){
  const body=progress?"jsonb_build_object('tenant',c.projection->0->'output'->'tenant')":"(c.projection->0->'output')";
  state=`jsonb_build_object('kind',c.projection->0->>'kind','observed',${vector('work_observed')},'completed',${vector('work_completed')},'output',CASE WHEN jsonb_typeof(c.projection->0->'output')='object' THEN ${body} || jsonb_build_object('identity',c.output_identity,'contentDigest',c.output_digest,'outputRevision',c.output_revision,'restoreGeneration',c.output_restore_generation::text) ELSE NULL END)`;
  typed=`jsonb_build_object('version',c.work_version,'contractDigest',c.contract_digest,'observed',c.work_observed::text[],'completed',c.work_completed::text[],'identity',c.output_identity,'digest',c.output_digest,'revision',c.output_revision::text,'generation',c.output_restore_generation::text,'enabled',c.work_enabled,'arrayBounds',array_lower(c.work_observed,1)=1 AND array_lower(c.work_completed,1)=1,'dueAt',c.work_due_at::text,'completedAt',c.work_completed_at::text,'pendingAt',c.work_pending_at::text${config.native?",'inputFloor',c.checkpoint::text":''},'bodyMetadataAbsent',(jsonb_typeof(c.projection->0->'output') IN ('object','null') AND NOT ((c.projection->0->'output') ?| ARRAY['identity','contentDigest','outputRevision','restoreGeneration','runtimeId'])))`;
 }
 // One SELECT snapshot: JSON clinical body and typed metadata cannot straddle a completion.
 const stored=progress?"'[]'::jsonb":`coalesce((SELECT jsonb_agg(e.doc) FROM "${config.entries}".entries e WHERE e.tenant_id=w.tenant_id AND e.doc->>'device'='${marker}-probe'),'[]'::jsonb)`;
 return `SELECT json_build_object('tenant',w.tenant_id::text,'stamp',w.last_stamp::text,'reader','${JSON.stringify(config.binding)}'::jsonb,'typed',${typed},'state',${state},'stored',${stored}${config.native?",'native',"+native.fields(config):''})::text FROM "${config.clock}".tenant_write_clock w LEFT JOIN "${config.checkpoint}".tenant_consumer_checkpoint c ON c.tenant_id=w.tenant_id AND c.consumer='${config.consumer}' ${config.native?native.joins(config):''} WHERE w.tenant_id IN (${selected});`;

}
const version=value=>typeof value==='string'&&/^(0|[1-9][0-9]*)$/.test(value);
const exact=value=>version(value)&&value.length<=19&&BigInt(value)<=9223372036854775807n;
// The native receipt cutover rewrites contract_digest to the native selection's
// contract (core lib/pgstream/native-receipt-cutover.js). The row is already
// selected by table and consumer, so a native row needs only a well-formed
// digest; the non-native contract keeps its exact recomputation.
function contractMatches(t,config){
 if(config.native)return typeof t?.contractDigest==='string'&&/^[a-f0-9]{64}$/.test(t.contractDigest);
 return t?.contractDigest===createHash('sha256').update(JSON.stringify([config.kind,config.checkpoint,config.consumer.replace(/-completed$/,'')])).digest('hex');
}
function typedState(row,config,progress=false){
 const t=row.typed,s=row.state,o=s?.output;

 if(!t||t.version!==2||!contractMatches(t,config)||t.enabled!==true||t.arrayBounds!==true||t.bodyMetadataAbsent!==true)return false;
 for(const [field,name]of [['observed','observed'],['completed','completed']]){
  const values=t[field],map=s?.[name];
  if(!Array.isArray(values)||values.length!==SOURCES.length||!map||typeof map!=='object'||Array.isArray(map)||Object.keys(map).some(k=>!SOURCES.includes(k)))return false;
  for(let i=0;i<SOURCES.length;i++)if(values[i]===null?Object.hasOwn(map,SOURCES[i]):!exact(values[i])||map[SOURCES[i]]!==values[i])return false;
 }
 for(const key of SOURCES)if(s.completed[key]!==undefined&&(s.observed[key]===undefined||BigInt(s.completed[key])>BigInt(s.observed[key])))return false;
 // Admission has no completed output yet. Only the metadata accessor may
 // carry this exact empty completion, never the clinical completion assessor.
 if(progress&&o===null&&t.identity===null&&t.digest===null&&t.revision==='0'&&t.generation===null&&t.completed.every(v=>v===null))return true;
 if(!o||!/^[a-f0-9]{64}$/.test(t.identity)||!/^[a-f0-9]{64}$/.test(t.digest)||!exact(t.revision)||BigInt(t.revision)<1n||BigInt(t.revision)>BigInt(Number.MAX_SAFE_INTEGER)||!(t.generation===null||exact(t.generation)&&BigInt(t.generation)>0n))return false;
 if(o.identity!==t.identity||o.contentDigest!==t.digest||String(o.outputRevision)!==t.revision||o.restoreGeneration!==t.generation)return false;
 return true;
}
function assess(row,witness,clients,expected,config){
 const no=code=>({ready:false,code});
 try{binding(config?.binding);if(!!config.native!==!!config.binding.nativeConfigurationSha256)fail('M7_COMPLETION_NATIVE_BINDING');if(config.native)native.validateConfig(config);selection(config);}catch{return no('M7_COMPLETION_BINDING');}
 if(config.kind!==config.binding.kind||!row?.reader||row.reader.kind!==config.binding.kind||row.reader.imageId!==config.binding.imageId||row.reader.instrument!==config.binding.instrument||row.reader.pair?.core!==config.binding.pair.core||row.reader.pair?.deploy!==config.binding.pair.deploy||row?.state?.kind!==config.kind)return no('M7_COMPLETION_READER_MISMATCH');
 if(config.native&&canonical(row.reader)!==canonical(config.binding))return no('M7_COMPLETION_READER_MISMATCH');
 if(config.kind==='evaluator-work-v2'&&!typedState(row,config))return no('M7_COMPLETION_TYPED_STATE');
 if(!row||row.tenant!==witness.tenant||!version(witness.stamp)||!version(row.stamp))return no('M7_COMPLETION_CLOCK');
 const state=row.state,output=state?.output;
 let coverage;
 if(config.native){const proof=native.assess(row,witness,config);if(!proof.ready)return proof;coverage=proof;
 }else{
 if(state?.kind!==config.kind||!output||output.tenant!==row.tenant||!version(state.observed?.clock)||!version(state.completed?.clock))return no('M7_COMPLETION_STATE');
 if(BigInt(state.observed.clock)<BigInt(witness.stamp)||BigInt(state.completed.clock)<BigInt(witness.stamp)||BigInt(state.completed.clock)>BigInt(state.observed.clock))return no('M7_COMPLETION_PENDING');
 if(typeof output.inputCheckpoint==='number'&&!Number.isSafeInteger(output.inputCheckpoint))return no('M7_COMPLETION_OUTPUT_CLOCK');
 if(!version(String(output.inputCheckpoint))||BigInt(String(output.inputCheckpoint))<BigInt(witness.stamp))return no('M7_COMPLETION_OUTPUT_CLOCK');
 }
 if(!Number.isSafeInteger(output.outputRevision)||output.outputRevision<1||typeof output.contentDigest!=='string'||!/^[a-f0-9]{64}$/.test(output.contentDigest)||!output.result||!output.result.properties)return no('M7_COMPLETION_OUTPUT');
 const stored=row.stored?.filter(doc=>doc.date===witness.date);
 if(stored?.length!==1||typeof stored[0]._id!=='string')return no('M7_COMPLETION_STORED');
 const doc=stored[0],same=sgv=>String(sgv?._id)===doc._id&&sgv.mills===doc.date&&sgv.mgdl===doc.sgv;
 // The bounded materializer publishes completed frames, without duplicating raw rows.
 if(!output.frame?.sgvs?.some(same))return no('M7_COMPLETION_FRAME');
 // Source bgnow.analyzeBucket averages valid mg/dl SGVs (>39). Check that
 // completed clinical value against its actual output bucket and frame. This
 // is a selected property witness, not equivalence for every clinical plugin.
 const bg=output.result.properties.bgnow,valid=bg?.sgvs?.filter(sgv=>Number.isFinite(sgv.mgdl)&&sgv.mgdl>39);
 if(!valid?.length||!Number.isFinite(bg.mean)||valid.some(sgv=>!output.frame.sgvs.some(frame=>String(frame._id)===String(sgv._id)&&frame.mills===sgv.mills&&frame.mgdl===sgv.mgdl)))return no('M7_COMPLETION_BG_NOW');
 const mean=valid.reduce((sum,sgv)=>sum+sgv.mgdl,0)/valid.length,last=valid.reduce((a,b)=>a.mills>=b.mills?a:b);
 if(Math.abs(bg.mean-mean)>1e-9||bg.mills!==last.mills||bg.last!==last.mgdl)return no('M7_COMPLETION_BG_NOW');
 const client=require('./client-delivery.cjs').assess(clients,expected,doc,expected===0?{}:witness);
 if(!client.ready)return {...no('M7_COMPLETION_CLIENT'),clientFailure:client.code};
 return {ready:true,...(coverage?{nativeCoverage:coverage.coverage,completedInputFloor:coverage.completedInputFloor,outputInputFloor:coverage.outputInputFloor}:{}),tenant:row.tenant,storedId:doc._id,completedClock:state.completed.clock,observedClock:state.observed.clock,outputRevision:output.outputRevision,contentDigest:output.contentDigest,clients:clients.length,bgNowMean:bg.mean,clinicalScope:'BG-now selected-bucket mean/last consistency; remaining clinical properties unassessed'};
}
// Read-only work metadata for the NEXT opportunity assessor. Reuse the exact
// typed vector/output fences, with an exact admission-only empty output case.
// This is neither a clinical nor a client-frame verdict.
function progressSnapshot(rows,config,ids){
 binding(config?.binding);selection(config);
 if(config.kind!=='evaluator-work-v2'||config.binding.kind!==config.kind||!Array.isArray(ids)||!ids.length||!ids.every(id=>UUID.test(id))||new Set(ids).size!==ids.length||!Array.isArray(rows)||rows.length!==ids.length||new Set(rows.map(r=>r?.tenant)).size!==ids.length)fail('M7_OPPORTUNITY_COVERAGE');
 const byTenant=new Map(rows.map(row=>[row?.tenant,row]));
 const values=ids.map(tenant=>{
  const row=byTenant.get(tenant);
  if(!row||canonical(row.reader)!==canonical(config.binding)||row.state?.kind!==config.kind)fail('M7_COMPLETION_READER_MISMATCH');
  if(!typedState(row,config,true)||row.state.output!==null&&row.state.output?.tenant!==tenant){
   const t=row.typed,error=Error('M7_COMPLETION_TYPED_STATE');
   // Fixed-size predicates only: never retain a clinical body, identifiers,
   // arbitrary row keys or error text through this private failure receipt.
   error.completionDiagnostic={rowIndex:ids.indexOf(tenant),predicates:{
    outputNull:row.state.output===null,outputObject:!!row.state.output&&typeof row.state.output==='object',
    outputTenantMatches:row.state.output?.tenant===tenant,
    revisionZero:t?.revision==='0',identityNull:t?.identity===null,digestNull:t?.digest===null,
    completedEmpty:Array.isArray(t?.completed)&&t.completed.length===6&&t.completed.every(v=>v===null),
    versionTwo:t?.version===2,enabled:t?.enabled===true,arrayBounds:t?.arrayBounds===true,bodyMetadataAbsent:t?.bodyMetadataAbsent===true,
    contractDigestMatches:contractMatches(t,config),
    observedSixSlots:Array.isArray(t?.observed)&&t.observed.length===6,
    completedSixSlots:Array.isArray(t?.completed)&&t.completed.length===6}};
   throw error;
  }
  if(config.native)native.snapshot(row,config);
  if(!exact(row.stamp)||(row.state.observed.clock!==undefined&&(!exact(row.state.observed.clock)||BigInt(row.state.observed.clock)>BigInt(row.stamp))))fail('M7_OPPORTUNITY_CLOCK');
  const timing={};
  for(const key of ['dueAt','completedAt','pendingAt'])if(Object.hasOwn(row.typed,key)){const value=row.typed[key];if(value!==null&&(!exact(value)||!Number.isSafeInteger(Number(value))))fail('M7_OPPORTUNITY_TIME');timing[key]=value===null?null:Number(value);}
  return {...timing,...(config.native?{native:native.progress(row,config)}:{}),tenant,writerClock:row.stamp,observed:{...row.state.observed},completed:{...row.state.completed},outputRevision:row.typed.revision,restoreGeneration:row.typed.generation};
 });
 return {kind:'evaluator-durable-progress-v1',reader:plain(config.binding),rows:values};
}
module.exports={source,prepare,query,assess,assessDurable:(row,witness,config)=>assess(row,witness,[],0,config),progressSnapshot,progressQuery:(config,ids)=>query(config,ids,'progress-opportunity',true)};
