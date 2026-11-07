'use strict';
const fs=require('node:fs'),path=require('node:path'),{execFileSync}=require('node:child_process');
const {ensure,canonical,sha,documentHash,text}=require('./schema.cjs');
const same=(a,b,message)=>ensure(canonical(a)===canonical(b),message);
module.exports=function validate(document,plan,{repo,toolDir}){
 (function scan(value){if(typeof value==='string')text(value);else if(value&&typeof value==='object')for(const x of Object.values(value))scan(x);})(document);
 ensure(document.version===1&&document.evidenceClass==='RECORDED-EVIDENCE'&&document.projectionSha256===documentHash(document),'RECORDED_PROJECTION_HASH');
 same(document.scope,plan.scope,'RECORDED_SCOPE_CHANGED');ensure(document.scope.freshNativeExecution===false&&document.scope.roles==='UNMEASURED','RECORDED_SCOPE_OVERCLAIM');
 ensure(document.builderSha256===sha(fs.readFileSync(path.join(toolDir,'build.cjs')))&&document.schemaSha256===sha(fs.readFileSync(path.join(toolDir,'schema.cjs'))),'RECORDED_PROJECTOR_IDENTITY');
 for(const [file,h]of Object.entries(plan.adapterHashes))ensure(sha(fs.readFileSync(path.join(toolDir,file)))===h,'RECORDED_ADAPTER_HASH');
 const sources=new Map();
 for(const capsule of plan.capsules){
  ensure(/^[0-9a-f]{40}$/.test(capsule.head),'RECORDED_SOURCE_FORMAT');
  if(sources.has(capsule.head))continue;
  const tree=execFileSync('git',['-C',repo,'rev-parse','--verify',capsule.head+'^{tree}'],{encoding:'utf8',stdio:['ignore','pipe','pipe']}).trim();ensure(tree===capsule.tree,'RECORDED_SOURCE_TREE');
  const files={};for(const [file,h]of Object.entries(plan.causalFiles)){
   ensure(!path.isAbsolute(file)&&!file.split('/').includes('..'),'RECORDED_SOURCE_PATH');
   files[file]=execFileSync('git',['-C',repo,'show',capsule.head+':'+file],{maxBuffer:64*1024*1024,stdio:['ignore','pipe','pipe']});ensure(sha(files[file])===h,'RECORDED_CAUSAL_HASH '+file);
  }sources.set(capsule.head,files);
 }
 ensure(Object.keys(plan.causalFiles).length===38&&plan.causalDeclaration.originalPriorFiles===37&&plan.causalDeclaration.additionalControlSources===1&&plan.causalDeclaration.equivalentAtAllDeclaredHeads===true,'RECORDED_CAUSAL_COVERAGE');
 same(document.capsules.map(x=>x.id).sort(),plan.capsules.map(x=>x.id).sort(),'RECORDED_CAPSULE_COVERAGE');
 for(const spec of plan.capsules){const c=document.capsules.find(c=>c.id===spec.id);ensure(c.head===spec.head&&c.tree===spec.tree&&c.indexSha256===spec.indexSha256&&c.observerIndexSha256===spec.observerIndexSha256,'RECORDED_CAPSULE_ATTRIBUTION');
  const cleanup=c.cleanup;ensure(cleanup.verified===true&&cleanup.baselineUnchanged===true&&cleanup.independentObservedExact===true&&cleanup.resourceAbsence===true&&cleanup.processBirthAbsence===true&&cleanup.observerErrors===0&&cleanup.containers===spec.containers&&cleanup.volumes===spec.volumes&&cleanup.nodeBirths===spec.nodeBirths,'RECORDED_CLEANUP');
  ensure(c.originalCampaignAccepted===(spec.id==='restoration')&&cleanup.commandExit===(spec.id==='restoration'?0:1),'RECORDED_ORIGINAL_VERDICT');
  if(spec.id!=='restoration')ensure(c.originalResult==='mismatch retained; no retry','RECORDED_STOP_RETAINED');else ensure(c.stop===null,'RECORDED_RESTORATION_STOP');
 }
 same(document.phases.map(p=>p.id),plan.phases.map(p=>p.id),'RECORDED_EXACT_PHASE_COVERAGE');
 for(const expected of plan.phases){
  const p=document.phases.find(p=>p.id===expected.id),capsule=plan.capsules.find(c=>c.id===expected.capsule),control=expected.kind==='control'?plan.controls.find(c=>c.id===p.id):null;
  for(const field of ['capsule','originalPhase','kind','regrade'])same(p[field],expected[field],'RECORDED_PHASE_ATTRIBUTION');
  ensure(p.head===capsule.head&&p.tree===capsule.tree,'RECORDED_PHASE_SOURCE');ensure(p.cleanup.normal===true&&p.cleanup.count===1,'RECORDED_PHASE_CLEANUP');
  ensure(!p.process.signal&&!p.process.timedOut,'RECORDED_PHASE_INTERRUPTED');
  const ids=control?[control.component]:Object.keys(plan.components),titles=control?control.selection:ids.flatMap(id=>plan.components[id].fullTitles);
  same([...p.report.tests].sort(),[...titles].sort(),'RECORDED_TEST_SELECTION');ensure(p.report.stats.tests===titles.length&&p.report.stats.pending===0,'RECORDED_BODY_COUNT');
  if(control){const error=p.report.failures[0]?.error;ensure(p.process.status!==0&&p.report.stats.passes===0&&p.report.stats.failures===1&&p.report.failures.length===1&&
   (error?.code==='ERR_ASSERTION'||/^AssertionError/.test(error?.name||''))&&error.message.includes(control.failure),'RECORDED_SEMANTIC_RED');
   if(p.regrade){ensure(p.originalVerdict===null&&p.originalFailure===document.capsules.find(c=>c.id===p.capsule).stop.failure&&document.capsules.find(c=>c.id===p.capsule).stop.phase===p.originalPhase,'RECORDED_REGRADE_ORIGINAL_STOP');}
   else ensure(p.originalFailure===null&&p.originalVerdict==='matched reviewed physical/native phase','RECORDED_ORIGINAL_PHASE_VERDICT');
  }else ensure(p.process.status===0&&p.report.stats.passes===23&&p.report.stats.failures===0&&p.report.failures.length===0&&p.originalFailure===null&&p.originalVerdict==='matched reviewed physical/native phase','RECORDED_ORDINARY');
  for(const id of Object.keys(plan.components)){
   const component=plan.components[id],records=p.observations[id];ensure(Array.isArray(records),'RECORDED_OBSERVATIONS');
   if(!ids.includes(id)){ensure(records.length===0,'RECORDED_UNSELECTED_COMPONENT');continue;}
   if(id!=='consumer')ensure(records.length===(control?control.expectedMarkers:component.expectedMarkers),'RECORDED_RAW_MARKER_COUNT '+id);
   require(path.join(toolDir,component.adapter))(records,control?.control);
  }
  if(ids.includes('lifecycle')){const exits=p.childExits.lifecycle;ensure(exits.length===(control?1:12)&&exits.every(e=>!e.signal&&(e.code===0||e.kind==='worker'&&e.bootRefused&&e.code===1)),'RECORDED_LIFECYCLE_EXITS');}
  if(ids.includes('consumer')){const exits=p.childExits.consumer;
   if(control)ensure(exits.length===control.expectedConsumerExits&&exits.every(e=>e.code===0&&!e.signal),'RECORDED_CONTROL_CONSUMER_EXITS');
   else {const death=p.observations.consumer.find(r=>r.phase==='uncertain-process-restart')?.death;ensure(exits.length===plan.components.consumer.expectedChildExits&&death&&exits.filter(e=>e.signal==='SIGKILL'&&e.pid===death.pid&&e.code===null).length===1&&exits.filter(e=>e.signal).length===1&&exits.filter(e=>e.pid!==death.pid).every(e=>e.code===0&&!e.signal),'RECORDED_PLANNED_DEATH');}
  }
  for(const [file,bytes]of Object.entries(sources.get(p.head))){let source=bytes.toString();for(const patch of control?.patches||[])if(patch.file===file){ensure(source.split(patch.before).length===2,'RECORDED_PATCH_UNIQUE');source=source.replace(patch.before,patch.after);}ensure(p.archiveHashes[file]===sha(source),'RECORDED_ARCHIVE_HASH '+file);}
 }
 const controls=document.phases.filter(p=>p.kind==='control');ensure(controls.length===19&&new Set(controls.map(c=>c.id)).size===19,'RECORDED_CONTROL_COVERAGE');
 ensure(document.phases.filter(p=>p.kind==='ordinary').length===2&&document.phases.at(-1).id==='restored','RECORDED_FRESH_RESTORATION_REQUIRED');
 ensure(document.invalids.length===1,'RECORDED_INVALID_CONTROL_RETAINED');const invalid=document.invalids[0];
 ensure(invalid.id==='invalid-inner-await'&&invalid.capsule==='invalid-inner-await'&&invalid.originalPhase==='alarm-precommit'&&invalid.kind==='invalid'&&invalid.report.stats.tests===1&&invalid.report.stats.passes===0&&invalid.report.stats.failures===1&&invalid.report.failures[0]?.error.timeoutMs===60000&&invalid.originalFailure==='RAW_MARKER_COUNT alarm'&&invalid.originalVerdict===null,'RECORDED_INVALID_TIMEOUT');
 const invalidSource=plan.capsules.find(c=>c.id==='invalid-inner-await');ensure(invalid.head===invalidSource.head&&invalid.tree===invalidSource.tree&&!invalid.process.signal&&!invalid.process.timedOut&&invalid.process.status===1,'RECORDED_INVALID_ATTRIBUTION');
 for(const [file,bytes]of Object.entries(sources.get(invalid.head))){let value=bytes.toString();for(const patch of plan.invalidControl.patches)if(patch.file===file){ensure(value.split(patch.before).length===2,'RECORDED_INVALID_PATCH_UNIQUE');value=value.replace(patch.before,patch.after);}ensure(invalid.archiveHashes[file]===sha(value),'RECORDED_INVALID_ARCHIVE_HASH');}
 ensure(Object.values(invalid.observations).every(v=>v.length===0)&&invalid.cleanup.normal===true,'RECORDED_INVALID_BOUNDARY_NOT_REACHED');
 return {evidenceClass:'RECORDED-EVIDENCE',phaseRecords:document.phases.length,invalidControlsRetained:document.invalids.length,committedSourceFilesPerHead:Object.keys(plan.causalFiles).length,ordinary:23,distinctControls:19,restored:23,sourceHeads:[...sources.keys()],roles:'UNMEASURED',claim:'archived record validation only; no fresh DB execution'};
};
