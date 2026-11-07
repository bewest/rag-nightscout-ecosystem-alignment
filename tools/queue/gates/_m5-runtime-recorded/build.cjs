'use strict';
// Whitelist projection builder. Reads immutable synthetic capsules and committed
// app objects; never starts services, exports env, or copies arbitrary logs.
const fs=require('node:fs'),path=require('node:path'),{execFileSync}=require('node:child_process');
const {ensure,sha,documentHash,observation,report,safe,text}=require('./schema.cjs');
const args=process.argv.slice(2),option=name=>args.includes(name)?args[args.indexOf(name)+1]:null;
const root=path.resolve(__dirname,'../../../..'),bundle=path.join(root,'reports/tenancy/m5-runtime-2026-11-07/postgres');
const read=file=>fs.readFileSync(file),json=file=>JSON.parse(read(file));
const planFile=path.join(bundle,'plan.json'),plan=json(planFile),repo=option('--repo'),out=option('--out');
ensure(repo&&out&&args.length===12,'Usage: --repo <app-object-repository> --initial <capsule> --continuation <capsule> --restoration <capsule> --invalid-inner-await <capsule> --out <new-file>');
const doc={version:1,evidenceClass:'RECORDED-EVIDENCE',scope:plan.scope,planSha256:sha(read(planFile)),builderSha256:sha(read(__filename)),schemaSha256:sha(read(path.join(__dirname,'schema.cjs'))),capsules:[],phases:[],invalids:[]};
function checkedIndex(dir,pin,count){const file=path.join(dir,'artifact-index.json');ensure(sha(read(file))===pin,'BUILDER_CAPSULE_INDEX');const idx=json(file).sha256;ensure(Object.keys(idx).length===count,'BUILDER_CAPSULE_COUNT');for(const [f,h]of Object.entries(idx)){ensure(!path.isAbsolute(f)&&!f.split('/').includes('..'),'BUILDER_INDEX_PATH');ensure(sha(read(path.join(dir,f)))===h,'BUILDER_CAPSULE_HASH '+f);}return idx;}
function show(head,file){return execFileSync('git',['-C',repo,'show',head+':'+file],{maxBuffer:64*1024*1024});}
for(const spec of plan.capsules){
 const dir=option('--'+spec.id);ensure(dir,'BUILDER_MISSING_CAPSULE');const observer=dir+'-observer';
 const idx=checkedIndex(dir,spec.indexSha256,spec.indexCount);checkedIndex(observer,spec.observerIndexSha256,7);
 const run=json(path.join(dir,'run.json')),source=json(path.join(dir,'source.json')),audit=json(path.join(observer,'observer-audit.json'));
 ensure(run.head===spec.head&&source.head===spec.head&&source.tree===spec.tree,'BUILDER_SOURCE_IDENTITY');
 ensure(audit.cleanupVerified&&audit.baselineUnchanged&&audit.independentObservedExact&&audit.observerErrors.length===0,'BUILDER_CLEANUP');
 const capsule={id:spec.id,head:source.head,tree:source.tree,indexSha256:spec.indexSha256,observerIndexSha256:spec.observerIndexSha256,archiveSha256:source.archiveSha256,originalResult:text(run.result),originalCampaignAccepted:audit.campaignAccepted,
  stop:run.phases.at(-1).failure?{phase:run.phases.at(-1).id,failure:text(run.phases.at(-1).failure)}:null,
  cleanup:{baselineUnchanged:audit.baselineUnchanged,independentObservedExact:audit.independentObservedExact,verified:audit.cleanupVerified,containers:audit.ownedCount,volumes:audit.ownedVolumeCount,nodeBirths:audit.processBirthAbsence.length,
   resourceAbsence:audit.resourceAbsence.every(r=>r.absent===true),processBirthAbsence:audit.processBirthAbsence.every(p=>p.sameBirthPresent===false&&p.uncertain===false),observerErrors:audit.observerErrors.length,commandExit:audit.commandExit}};
 doc.capsules.push(capsule);
 const selected=plan.phases.filter(p=>p.capsule===spec.id);
 const stages=spec.id==='invalid-inner-await'?[{id:'invalid-inner-await',originalPhase:'alarm-precommit',kind:'invalid',capsule:spec.id}]:selected;
 ensure(run.phases.length===stages.length,'BUILDER_EXACT_PHASE_COVERAGE');
 for(const selected of stages){
  const stage=run.phases.find(p=>p.id===selected.originalPhase);ensure(stage,'BUILDER_PHASE_MISSING');
  const phaseDir=path.join(dir,stage.id),raw=read(path.join(phaseDir,'native.log')).toString(),r=json(path.join(phaseDir,'report.json')),process=json(path.join(phaseDir,'process-result.json'));
  const control=selected.kind==='control'?plan.controls.find(c=>c.id===selected.id):null;
  const archiveHashes={};
  for(const [f,h]of Object.entries(plan.causalFiles)){
   let bytes=show(spec.head,f);ensure(sha(bytes)===h,'BUILDER_CAUSAL_BASE '+f);
   const patches=selected.kind==='invalid'?plan.invalidControl.patches:control?.patches||[];
   for(const patch of patches)if(patch.file===f){const source=bytes.toString();ensure(source.split(patch.before).length===2,'BUILDER_PATCH_UNIQUE');bytes=Buffer.from(source.replace(patch.before,patch.after));}
   ensure(sha(read(path.join(phaseDir,'source',f)))===sha(bytes),'BUILDER_ARCHIVED_SOURCE '+selected.id+'/'+f);archiveHashes[f]=sha(bytes);
  }
  const observations={},exits={};for(const [id,c]of Object.entries(plan.components)){
   observations[id]=raw.split(/\r?\n/).filter(l=>l.startsWith(c.markerPrefix+' ')).map(l=>observation(JSON.parse(l.slice(c.markerPrefix.length+1))));
  }
  for(const [id,prefix]of Object.entries({lifecycle:'M5_EVALUATOR_CHILD_EXIT',consumer:'M5_CONSUMER_CHILD_EXIT'}))exits[id]=raw.split(/\r?\n/).filter(l=>l.startsWith(prefix+' ')).map(l=>safe(JSON.parse(l.slice(prefix.length+1))));
  const value={...selected,head:spec.head,tree:spec.tree,originalFailure:stage.failure||null,originalVerdict:stage.verdict||null,report:report(r),process:{status:process.status,signal:process.signal,timedOut:process.timedOut},observations,childExits:exits,
   provenance:{reportSha256:idx[stage.id+'/report.json'],rawSha256:idx[stage.id+'/native.log']},archiveHashes,
   cleanup:{normal:stage.cleanup.every(r=>r.normalCleanup===true&&r.verifiedAbsent===true&&!r.forcedCleanup),count:stage.cleanup.length}};
  if(selected.kind==='invalid')doc.invalids.push(value);else doc.phases.push(value);
 }
}
doc.phases.sort((a,b)=>plan.phases.findIndex(p=>p.id===a.id)-plan.phases.findIndex(p=>p.id===b.id));
doc.projectionSha256=documentHash(doc);fs.writeFileSync(out,JSON.stringify(doc,null,2)+'\n',{flag:'wx',mode:0o644});
console.log('projected '+doc.phases.length+' phases; '+doc.invalids.length+' invalid control retained; sha256 '+doc.projectionSha256);
