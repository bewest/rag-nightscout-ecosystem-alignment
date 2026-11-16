'use strict';
// Actual pgstream checkpoint/output contract. SQL is independent of worker
// inspection and counts only the caller's synthetic marker. No connection here.
const {createHash}=require('node:crypto');
const SOURCES=['clock','settings','policy','activity','lifecycle','bootstrap'];
const NAME=/^[a-z][a-z0-9_]{0,62}$/,UUID=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const fail=code=>{throw Error(code);};
const PROTOCOL='pgstream-intake-v1',CODEC='canonical-maintenance-active-plus2-v1',DOMAIN='positive-int8-complete-pair-max-4611686018427387902-v1',POLICY='active-or-suspended-metadata-v1';
const CONTROL_READS={schema_migrations:['name','checksum','applied_at'],tenant_lifecycle_windows:['tenant_id','lock_key','phase','generation','claim_id','artifact_digest'],tenant_lifecycle_operations:['tenant_id','operation_id','generation','finished','owner_pid','owner_birth']};
const canonical=value=>Array.isArray(value)?'['+value.map(canonical).join(',')+']':value&&typeof value==='object'?'{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}':JSON.stringify(value);
const knownSelections=new WeakMap();
const freeze=value=>{if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;};
const hash=value=>createHash('sha256').update(canonical(value)).digest('hex');
const name=value=>typeof value==='string'&&NAME.test(value)&&!value.startsWith('pg_')&&!['public','information_schema'].includes(value);
function plain(value,depth=0,budget={nodes:0}){
 if(++budget.nodes>200000||depth>16)fail('M7_COMPLETION_PROFILE_VALUE_BOUND');
 if(value===null||typeof value==='boolean'||typeof value==='string'&&value.length<=8192||typeof value==='number'&&Number.isFinite(value))return value;
 if(!value||typeof value!=='object'||![Object.prototype,Array.prototype,null].includes(Object.getPrototypeOf(value)))fail('M7_COMPLETION_PROFILE_PLAIN_VALUE');
 const descriptors=Object.getOwnPropertyDescriptors(value),keys=Object.keys(descriptors).filter(k=>!(Array.isArray(value)&&k==='length'));
 if(keys.length>(Array.isArray(value)?10000:256)||keys.some(k=>['__proto__','prototype','constructor'].includes(k)||!descriptors[k].enumerable||!Object.hasOwn(descriptors[k],'value')))fail('M7_COMPLETION_PROFILE_PLAIN_VALUE');
 if(Array.isArray(value)){if(value.length!==keys.length||keys.some((k,i)=>k!==String(i)))fail('M7_COMPLETION_PROFILE_PLAIN_VALUE');return keys.map(k=>plain(descriptors[k].value,depth+1,budget));}
 return Object.fromEntries(keys.map(k=>[k,plain(descriptors[k].value,depth+1,budget)]));
}
function profile(value){
 const p=plain(value),b=p.binding;
 if(!b||Object.keys(p).some(k=>!['binding','digest','contractDigest','ownerKey','assignment'].includes(k))||Object.keys(b).sort().join(',')!=='codec,consumer,controlReads,generationDomain,lifecycleNamespace,members,membershipNamespace,namespace,policy,protocol,revision,role,tenants,workCatalogueRead'||b.protocol!==PROTOCOL||b.codec!==CODEC||b.generationDomain!==DOMAIN||b.policy!==POLICY||canonical(b.controlReads)!==canonical(CONTROL_READS)||canonical(b.workCatalogueRead)!==canonical(['name','checksum']))fail('M7_COMPLETION_SELECTED_PROFILE');
 if(!['namespace','membershipNamespace','lifecycleNamespace','role'].every(k=>name(b[k]))||new Set([b.namespace,b.membershipNamespace,b.lifecycleNamespace]).size!==3||!/^evaluator-[A-Za-z0-9_-]{1,100}$/.test(b.consumer)||![1,2].includes(b.members)||typeof b.revision!=='string'||!/^[1-9][0-9]{0,18}$/.test(b.revision)||BigInt(b.revision)>9223372036854775807n||!Array.isArray(b.tenants)||!b.tenants.length||b.tenants.length>10000||!b.tenants.every(t=>typeof t==='string'&&UUID.test(t))||new Set(b.tenants).size!==b.tenants.length||canonical(b.tenants)!==canonical([...b.tenants].sort()))fail('M7_COMPLETION_SELECTED_PROFILE');
 const digest=hash(b),contractDigest=hash(['evaluator-work-v2',b.namespace,b.consumer,PROTOCOL,digest]),ownerKey=BigInt.asIntN(64,BigInt('0x'+hash(['pgstream-evaluator-owner-v1',b.namespace,b.consumer]).slice(0,16))).toString();
 if(p.digest!==digest||p.contractDigest!==contractDigest||p.ownerKey!==ownerKey)fail('M7_COMPLETION_SELECTED_PROFILE');return {binding:b,digest,contractDigest,ownerKey};
}
function selection(config){
 if(knownSelections.has(config))return knownSelections.get(config);
 const selected=config.selection,tag=config.binding?.selectedProfile;
 if(selected===undefined&&tag===undefined)return null;
 if(!selected||!tag||Object.keys(selected).sort().join(',')!=='profile,provenance')fail('M7_COMPLETION_SELECTED_PROVENANCE');
 const p=profile(selected.profile),v=selected.provenance;
 if(!v||Object.keys(v).sort().join(',')!=='configurationSha256,evaluatorConfigSha256,pair,realtimeConfigSha256'||!['configurationSha256','evaluatorConfigSha256','realtimeConfigSha256'].every(k=>/^[a-f0-9]{64}$/.test(v[k]))||v.configurationSha256!==hash([v.evaluatorConfigSha256,v.realtimeConfigSha256])||canonical(v.pair)!==canonical(config.binding.pair)||tag.protocol!==PROTOCOL||tag.digest!==p.digest||tag.configurationSha256!==v.configurationSha256||config.kind!=='evaluator-work-v2'||p.binding.namespace!==config.checkpoint||p.binding.consumer+'-completed'!==config.consumer||p.binding.members!==2)fail('M7_COMPLETION_SELECTED_PROVENANCE');return p;
}
function binding(value){
 if(!value||Object.keys(value).sort().join(',')!==(value.selectedProfile===undefined?'imageId,instrument,kind,pair':'imageId,instrument,kind,pair,selectedProfile')||!['evaluator-work-v1','evaluator-work-v2'].includes(value.kind)||!value.pair||Object.keys(value.pair).sort().join(',')!=='core,deploy'||!Object.values(value.pair).every(v=>/^[a-f0-9]{40}$/.test(v))||!/^sha256:[a-f0-9]{64}$/.test(value.imageId)||!/^[a-f0-9]{64}$/.test(value.instrument))fail('M7_COMPLETION_BINDING');
 if(value.selectedProfile!==undefined){const p=value.selectedProfile;if(value.kind!=='evaluator-work-v2'||!p||Object.keys(p).sort().join(',')!=='configurationSha256,digest,protocol'||p.protocol!==PROTOCOL||![p.digest,p.configurationSha256].every(v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v)))fail('M7_COMPLETION_SELECTED_PROVENANCE');}
 return value;
}
function prepare(config){const owned=plain(config);binding(owned.binding);const chosen=selection(owned);freeze(owned);if(chosen)knownSelections.set(owned,freeze(chosen));return owned;}
function source(evaluator,realtime,selected){
 if(evaluator&&Object.hasOwn(evaluator,'selectedIntake')||realtime&&Object.hasOwn(realtime,'intakeProfile')){evaluator=plain(evaluator);realtime=plain(realtime);selected=plain(selected);}
 binding(selected);
 const ns=evaluator?.postgres?.namespaces,completed=realtime?.completedOutput;
 if(!evaluator?.pgstream||!ns||!['clock','checkpoint','entries'].every(key=>NAME.test(ns[key]))||!/^evaluator-[A-Za-z0-9_-]{1,100}$/.test(evaluator.consumer)||completed?.namespace!==ns.checkpoint||completed?.consumer!==evaluator.consumer)fail('M7_COMPLETION_SOURCE');
 const config={clock:ns.clock,checkpoint:ns.checkpoint,entries:ns.entries,consumer:evaluator.consumer+'-completed',kind:selected.kind,binding:selected};
 if(Object.hasOwn(evaluator,'selectedIntake')||Object.hasOwn(realtime,'intakeProfile')){
  const e=plain(evaluator),r=plain(realtime),p=profile(e.selectedIntake?.profile),peer=profile(r.intakeProfile);
  if(selected.kind!=='evaluator-work-v2'||p.digest!==peer.digest||p.binding.namespace!==ns.checkpoint||p.binding.consumer!==e.consumer||p.binding.lifecycleNamespace!==e.trustedWorker?.activity||p.binding.lifecycleNamespace!==r.trustedWorker?.activity||p.binding.members!==2)fail('M7_COMPLETION_SELECTED_PROFILE_SOURCE');
  const evaluatorConfigSha256=hash(e),realtimeConfigSha256=hash(r),configurationSha256=hash([evaluatorConfigSha256,realtimeConfigSha256]),tag={protocol:PROTOCOL,digest:p.digest,configurationSha256};
  if(selected.selectedProfile!==undefined&&canonical(selected.selectedProfile)!==canonical(tag))fail('M7_COMPLETION_SELECTED_PROVENANCE');
  config.binding={...plain(selected),selectedProfile:tag};config.selection={profile:p,provenance:{pair:plain(selected.pair),evaluatorConfigSha256,realtimeConfigSha256,configurationSha256}};selection(config);
 }else if(selected.selectedProfile!==undefined)fail('M7_COMPLETION_SELECTED_PROFILE_SOURCE');
 return config.selection?prepare(config):config;
}
function query(config,ids,marker,progress=false){
 if(typeof progress!=='boolean'||progress&&config.kind!=='evaluator-work-v2')fail('M7_COMPLETION_SELECTOR');
 if(!['clock','checkpoint','entries'].every(key=>NAME.test(config[key]))||!/^evaluator-[A-Za-z0-9_-]{1,100}-completed$/.test(config.consumer)||!['evaluator-work-v1','evaluator-work-v2'].includes(config.kind)||!Array.isArray(ids)||!ids.length||ids.length>10000||!ids.every(id=>UUID.test(id))||!/^[a-z0-9-]{1,120}$/.test(marker))fail('M7_COMPLETION_SELECTOR');
 binding(config.binding);const chosen=selection(config);if(chosen&&ids.some(id=>!chosen.binding.tenants.includes(id)))fail('M7_COMPLETION_SELECTOR');if(config.kind!==config.binding.kind)fail('M7_COMPLETION_READER_MISMATCH');
 const selected=ids.map(id=>"'"+id+"'").join(',');
 const vector=column=>`(SELECT coalesce(jsonb_object_agg(k,v),'{}'::jsonb) FROM (VALUES ${SOURCES.map((key,i)=>`('${key}',c.${column}[${i+1}]::text)`).join(',')}) s(k,v) WHERE v IS NOT NULL)`;
 let state='c.projection->0',typed='NULL::jsonb';
 const profileFields=chosen?",'ownerOrdinal',c.work_owner_ordinal,'assignmentRevision',c.work_assignment_revision::text,'installedProfile',jsonb_build_object('consumer',p.consumer,'binding',p.profile,'digest',p.digest,'contractDigest',p.contract_digest)":'';
 if(config.kind==='evaluator-work-v2'){
  const body=progress?"jsonb_build_object('tenant',c.projection->0->'output'->'tenant')":"(c.projection->0->'output')";
  state=`jsonb_build_object('kind',c.projection->0->>'kind','observed',${vector('work_observed')},'completed',${vector('work_completed')},'output',CASE WHEN jsonb_typeof(c.projection->0->'output')='object' THEN ${body} || jsonb_build_object('identity',c.output_identity,'contentDigest',c.output_digest,'outputRevision',c.output_revision,'restoreGeneration',c.output_restore_generation::text) ELSE NULL END)`;
  typed=`jsonb_build_object('version',c.work_version,'contractDigest',c.contract_digest,'observed',c.work_observed::text[],'completed',c.work_completed::text[],'identity',c.output_identity,'digest',c.output_digest,'revision',c.output_revision::text,'generation',c.output_restore_generation::text,'enabled',c.work_enabled,'arrayBounds',array_lower(c.work_observed,1)=1 AND array_lower(c.work_completed,1)=1,'bodyMetadataAbsent',NOT ((c.projection->0->'output') ?| ARRAY['identity','contentDigest','outputRevision','restoreGeneration','runtimeId'])${profileFields})`;
 }
 // One SELECT snapshot: JSON clinical body and typed metadata cannot straddle a completion.
 const stored=progress?"'[]'::jsonb":`coalesce((SELECT jsonb_agg(e.doc) FROM "${config.entries}".entries e WHERE e.tenant_id=w.tenant_id AND e.doc->>'device'='${marker}-probe'),'[]'::jsonb)`;
 return `SELECT json_build_object('tenant',w.tenant_id::text,'stamp',w.last_stamp::text,'reader','${JSON.stringify(config.binding)}'::jsonb,'typed',${typed},'state',${state},'stored',${stored})::text FROM "${config.clock}".tenant_write_clock w LEFT JOIN "${config.checkpoint}".tenant_consumer_checkpoint c ON c.tenant_id=w.tenant_id AND c.consumer='${config.consumer}'${chosen?' LEFT JOIN "'+config.checkpoint+'".pgstream_intake_profile p ON p.consumer=c.consumer':''} WHERE w.tenant_id IN (${selected});`;

}
const version=value=>typeof value==='string'&&/^(0|[1-9][0-9]*)$/.test(value);
const exact=value=>version(value)&&value.length<=19&&BigInt(value)<=9223372036854775807n;
function typedState(row,config,chosen){
 const t=row.typed,s=row.state,o=s?.output;
 const digest=chosen?chosen.contractDigest:createHash('sha256').update(JSON.stringify([config.kind,config.checkpoint,config.consumer.replace(/-completed$/,'')])).digest('hex');
 if(chosen){const installed=t?.installedProfile,ordinal=chosen.binding.tenants.includes(row.tenant)?Number(createHash('sha256').update(row.tenant,'utf8').digest().readBigUInt64BE(0)%BigInt(chosen.binding.members)):-1;if(!installed||installed.consumer!==config.consumer||canonical(installed.binding)!==canonical(chosen.binding)||installed.digest!==chosen.digest||installed.contractDigest!==chosen.contractDigest||t.ownerOrdinal!==ordinal||ordinal<0||t.assignmentRevision!==chosen.binding.revision||!exact(t.generation)||BigInt(t.generation)<1n||BigInt(t.generation)>4611686018427387902n)return false;}
 if(!t||t.version!==2||t.contractDigest!==digest||t.enabled!==true||t.arrayBounds!==true||t.bodyMetadataAbsent!==true||!o||!/^[a-f0-9]{64}$/.test(t.identity)||!/^[a-f0-9]{64}$/.test(t.digest)||!exact(t.revision)||BigInt(t.revision)<1n||BigInt(t.revision)>BigInt(Number.MAX_SAFE_INTEGER)||!(t.generation===null||exact(t.generation)&&BigInt(t.generation)>0n))return false;
 if(o.identity!==t.identity||o.contentDigest!==t.digest||String(o.outputRevision)!==t.revision||o.restoreGeneration!==t.generation)return false;
 for(const [field,name]of [['observed','observed'],['completed','completed']]){
  const values=t[field],map=s?.[name];
  if(!Array.isArray(values)||values.length!==SOURCES.length||!map||Object.keys(map).some(k=>!SOURCES.includes(k)))return false;
  for(let i=0;i<SOURCES.length;i++)if(values[i]===null?Object.hasOwn(map,SOURCES[i]):!exact(values[i])||map[SOURCES[i]]!==values[i])return false;
 }
 for(const key of SOURCES)if(s.completed[key]!==undefined&&(s.observed[key]===undefined||BigInt(s.completed[key])>BigInt(s.observed[key])))return false;
 return true;
}
function assess(row,witness,clients,expected,config){
 const no=code=>({ready:false,code});
 let chosen;try{binding(config?.binding);chosen=selection(config);}catch{return no('M7_COMPLETION_BINDING');}
 if(config.kind!==config.binding.kind||!row?.reader||row.reader.kind!==config.binding.kind||row.reader.imageId!==config.binding.imageId||row.reader.instrument!==config.binding.instrument||row.reader.pair?.core!==config.binding.pair.core||row.reader.pair?.deploy!==config.binding.pair.deploy||row?.state?.kind!==config.kind)return no('M7_COMPLETION_READER_MISMATCH');
 if(config.selection&&canonical(row.reader)!==canonical(config.binding))return no('M7_COMPLETION_READER_MISMATCH');
 if(config.kind==='evaluator-work-v2'&&!typedState(row,config,chosen))return no('M7_COMPLETION_TYPED_STATE');
 if(!row||row.tenant!==witness.tenant||!version(witness.stamp)||!version(row.stamp))return no('M7_COMPLETION_CLOCK');
 const state=row.state,output=state?.output;
 if(state?.kind!==config.kind||!output||output.tenant!==row.tenant||!version(state.observed?.clock)||!version(state.completed?.clock))return no('M7_COMPLETION_STATE');
 if(BigInt(state.observed.clock)<BigInt(witness.stamp)||BigInt(state.completed.clock)<BigInt(witness.stamp)||BigInt(state.completed.clock)>BigInt(state.observed.clock))return no('M7_COMPLETION_PENDING');
 if(typeof output.inputCheckpoint==='number'&&!Number.isSafeInteger(output.inputCheckpoint))return no('M7_COMPLETION_OUTPUT_CLOCK');
 if(!version(String(output.inputCheckpoint))||BigInt(String(output.inputCheckpoint))<BigInt(witness.stamp))return no('M7_COMPLETION_OUTPUT_CLOCK');
 if(!Number.isSafeInteger(output.outputRevision)||output.outputRevision<1||typeof output.contentDigest!=='string'||!/^[a-f0-9]{64}$/.test(output.contentDigest)||!output.result||!output.result.properties)return no('M7_COMPLETION_OUTPUT');
 const stored=row.stored?.filter(doc=>doc.date===witness.date);
 if(stored?.length!==1||typeof stored[0]._id!=='string')return no('M7_COMPLETION_STORED');
 const doc=stored[0],same=sgv=>String(sgv?._id)===doc._id&&sgv.mills===doc.date&&sgv.mgdl===doc.sgv;
 if(!output.rows?.some(value=>value.domain==='entries'&&value.doc?._id===doc._id&&value.doc.sgv===doc.sgv)||!output.frame?.sgvs?.some(same))return no('M7_COMPLETION_FRAME');
 // Source bgnow.analyzeBucket averages valid mg/dl SGVs (>39). Check that
 // completed clinical value against its actual output bucket and frame. This
 // is a selected property witness, not equivalence for every clinical plugin.
 const bg=output.result.properties.bgnow,valid=bg?.sgvs?.filter(sgv=>Number.isFinite(sgv.mgdl)&&sgv.mgdl>39);
 if(!valid?.length||!Number.isFinite(bg.mean)||valid.some(sgv=>!output.frame.sgvs.some(frame=>String(frame._id)===String(sgv._id)&&frame.mills===sgv.mills&&frame.mgdl===sgv.mgdl)))return no('M7_COMPLETION_BG_NOW');
 const mean=valid.reduce((sum,sgv)=>sum+sgv.mgdl,0)/valid.length,last=valid.reduce((a,b)=>a.mills>=b.mills?a:b);
 if(Math.abs(bg.mean-mean)>1e-9||bg.mills!==last.mills||bg.last!==last.mgdl)return no('M7_COMPLETION_BG_NOW');
 if(!Array.isArray(clients)||clients.length!==expected||new Set(clients.map(c=>c.socket)).size!==expected||clients.some(c=>c.connects!==1||!same(c.sgv)))return no('M7_COMPLETION_CLIENT');
 return {ready:true,tenant:row.tenant,storedId:doc._id,completedClock:state.completed.clock,observedClock:state.observed.clock,outputRevision:output.outputRevision,contentDigest:output.contentDigest,clients:clients.length,bgNowMean:bg.mean,clinicalScope:'BG-now selected-bucket mean/last consistency; remaining clinical properties unassessed'};
}
// Read-only work metadata for the NEXT opportunity assessor. Reuse the exact
// typed-state validator; this is neither a clinical nor a client-frame verdict.
function progressSnapshot(rows,config,ids){
 binding(config?.binding);const chosen=selection(config);
 if(config.kind!=='evaluator-work-v2'||config.binding.kind!==config.kind||!Array.isArray(ids)||!ids.length||ids.length>10000||!ids.every(id=>UUID.test(id))||new Set(ids).size!==ids.length||!Array.isArray(rows)||rows.length!==ids.length||new Set(rows.map(r=>r?.tenant)).size!==ids.length)fail('M7_OPPORTUNITY_COVERAGE');
 const byTenant=new Map(rows.map(row=>[row?.tenant,row]));
 const values=ids.map(tenant=>{
  const row=byTenant.get(tenant);
  if(!row||canonical(row.reader)!==canonical(config.binding)||row.state?.kind!==config.kind)fail('M7_COMPLETION_READER_MISMATCH');
  if(!typedState(row,config,chosen))fail('M7_COMPLETION_TYPED_STATE');
  if(row.state.output.tenant!==tenant)fail('M7_COMPLETION_TYPED_STATE');
  if(!exact(row.stamp)||!exact(row.state.observed.clock)||!exact(row.state.completed.clock)||BigInt(row.state.observed.clock)>BigInt(row.stamp))fail('M7_OPPORTUNITY_CLOCK');
  return {tenant,writerClock:row.stamp,observed:{...row.state.observed},completed:{...row.state.completed},outputRevision:row.typed.revision,restoreGeneration:row.typed.generation};
 });
 return {kind:'evaluator-durable-progress-v1',reader:plain(config.binding),rows:values};
}
module.exports={source,prepare,query,assess,assessDurable:(row,witness,config)=>assess(row,witness,[],0,config),progressSnapshot,progressQuery:(config,ids)=>query(config,ids,'progress-opportunity',true)};
