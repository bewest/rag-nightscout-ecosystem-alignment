'use strict';
const fs=require('node:fs'),path=require('node:path'),{execFileSync}=require('node:child_process');
const {ensure,canonical,sha,documentHash,sequence,projectRaw}=require('./schema.cjs');
const closed=(value,keys)=>ensure(value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).every(k=>keys.split(' ').includes(k)),'ROLE_CLOSED_ENVELOPE');
module.exports=function validate(doc,plan,options){
 ensure(plan.reviewed===true&&plan.pending.length===0&&plan.capsule,'ROLE_RECORD_LOCKED_PENDING_REVIEW');
 ensure(doc.version===1&&doc.evidenceClass==='RECORDED-EVIDENCE'&&doc.projectionSha256===documentHash(doc),'ROLE_DOCUMENT_HASH');
 closed(doc,'version evidenceClass scope planSha256 builderSha256 schemaSha256 validatorSha256 replaySha256 capsule phases projectionSha256');
 ensure(canonical(doc.scope)===canonical(plan.scope)&&doc.scope.freshNativeExecution===false,'ROLE_SCOPE');
 ensure(doc.planSha256===sha(options.planBytes),'ROLE_PLAN_HASH');
 for(const [field,file]of Object.entries({builderSha256:'build.cjs',schemaSha256:'schema.cjs',validatorSha256:'validate.cjs',replaySha256:'replay.cjs'}))ensure(doc[field]===sha(fs.readFileSync(path.join(__dirname,file))),'ROLE_TOOL_HASH '+file);
 const phases=sequence(plan);ensure(canonical(doc.phases.map(p=>({id:p.id,phase:p.phase,kind:p.kind})))===canonical(phases),'ROLE_EXACT_PHASE_COVERAGE');
 ensure(doc.capsule.head===plan.head&&doc.capsule.tree===plan.tree&&doc.capsule.indexSha256===plan.capsule.indexSha256&&doc.capsule.observerIndexSha256===plan.capsule.observerIndexSha256&&doc.capsule.originalCampaignAccepted===true,'ROLE_CAPSULE_ATTRIBUTION');
 closed(doc.capsule,'id head tree indexSha256 observerIndexSha256 archiveSha256 originalCampaignAccepted cleanup');ensure(doc.capsule.id===plan.capsule.id&&doc.capsule.archiveSha256===plan.capsule.archiveSha256,'ROLE_CAPSULE_ARCHIVE');
 const c=doc.capsule.cleanup;ensure(c.commandExit===0&&c.baselineUnchanged===true&&c.independentObservedExact===true&&c.cleanupVerified===true&&c.observerErrors===0&&c.resourceAbsence===true&&c.processBirthAbsence===true&&c.identityMatches===true,'ROLE_INDEPENDENT_CLEANUP');
 closed(c,'commandExit baselineUnchanged independentObservedExact cleanupVerified observerErrors resourceAbsence processBirthAbsence identityMatches containers volumes observedBirths');for(const key of ['containers','volumes','observedBirths'])ensure(c[key]===plan.capsule[key],'ROLE_CLEANUP_COUNT');
 for(const p of doc.phases){
  closed(p,'id phase kind head tree process originalVerdict configuration observations provenance archiveHashes cleanup assertionWitness assertionRawSha256');closed(p.process,'status signal timedOut forcedKill cancelled');closed(p.cleanup,'normal childrenAbsent forced directoryAbsent residuals containers volumes');
  ensure(p.originalVerdict===(p.kind==='control'?'reviewed raw semantic red':'actual ordinary phase matched raw oracle'),'ROLE_ORIGINAL_VERDICT');
  ensure(p.head===plan.head&&p.tree===plan.tree,'ROLE_PHASE_SOURCE');
  ensure(plan.phasePins?.[p.id]&&sha(canonical(p.configuration))===plan.phasePins[p.id].configurationSha256,'ROLE_CONFIGURATION_PIN');
  ensure(sha(canonical(p.process))===plan.phasePins[p.id].processSha256,'ROLE_ORIGINAL_PROCESS_PIN');
  ensure(p.cleanup.normal===true&&p.cleanup.childrenAbsent===true&&p.cleanup.forced===false&&p.cleanup.directoryAbsent===true&&p.cleanup.residuals===0&&p.cleanup.containers===3&&p.cleanup.volumes===5,'ROLE_PHASE_CLEANUP');
  ensure(canonical(Object.keys(p.observations).sort())===canonical([...plan.requiredRaw[p.phase]].sort()),'ROLE_RAW_COVERAGE');
  ensure(canonical(Object.keys(p.archiveHashes).sort())===canonical(Object.keys(plan.causalFiles).sort()),'ROLE_ARCHIVE_COVERAGE');
  const control=p.kind==='control'?plan.controls.find(x=>x.id===p.id):null;
  for(const [file,hash]of Object.entries(plan.causalFiles)){
   let bytes=require('./replay.cjs').readObject(options.repo,plan.head,file);ensure(sha(bytes)===hash,'ROLE_BASE_HASH');
   for(const patch of control?.patches||[])if(patch.file===file){const text=bytes.toString();ensure(text.split(patch.before).length===2,'ROLE_PATCH_UNIQUE');bytes=Buffer.from(text.replace(patch.before,patch.after));}
   ensure(p.archiveHashes[file]===sha(bytes),'ROLE_CONTROL_ARCHIVE_HASH');
  }
  for(const [name,value]of Object.entries(p.observations)){
   ensure(canonical(projectRaw(name,value))===canonical(value),'ROLE_CLOSED_PROJECTION');
   closed(p.provenance[name],'rawSha256 projectedSha256');ensure(p.provenance[name]?.rawSha256===plan.phasePins[p.id].raw[name]&&p.provenance[name].projectedSha256===sha(canonical(value)),'ROLE_RAW_PROVENANCE');
  }
  ensure(canonical(Object.keys(p.provenance).sort())===canonical(Object.keys(p.observations).sort()),'ROLE_PROVENANCE_COVERAGE');
  if(control)ensure(p.assertionWitness==='ERR_ASSERTION'&&p.assertionRawSha256===plan.phasePins[p.id].assertionRawSha256,'ROLE_RAW_ASSERTION_PROVENANCE');
  require('./replay.cjs').replay(p,plan,options);
 }
 return {evidenceClass:'RECORDED-EVIDENCE',phases:doc.phases.length,controls:plan.controls.length,scope:plan.scope};
};
