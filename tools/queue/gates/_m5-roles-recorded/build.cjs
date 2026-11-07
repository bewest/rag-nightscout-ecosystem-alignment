'use strict';
// Reads finished audited synthetic capsules only. No service/install capability.
const fs=require('node:fs'),path=require('node:path'),{execFileSync}=require('node:child_process');
const s=require('./schema.cjs');
const read=f=>fs.readFileSync(f),json=f=>JSON.parse(read(f));
function checkedIndex(directory,pin,count){
 s.ensure(s.sha(read(path.join(directory,'artifact-index.json')))===pin,'ROLE_BUILDER_INDEX');const index=json(path.join(directory,'artifact-index.json')).sha256;
 s.ensure(index&&Object.keys(index).length===count,'ROLE_BUILDER_INDEX_COUNT');
 for(const [file,hash]of Object.entries(index)){s.ensure(!path.isAbsolute(file)&&!file.split('/').includes('..'),'ROLE_INDEX_PATH');const target=path.join(directory,file);s.ensure(fs.lstatSync(target).isFile()&&!fs.lstatSync(target).isSymbolicLink()&&s.sha(read(target))===hash,'ROLE_RAW_HASH '+file);}return index;
}
function build({directory,observer,plan,planBytes,repo,deps}){
 s.ensure(plan.reviewed===true&&plan.pending.length===0&&plan.capsule,'ROLE_RECORD_LOCKED_PENDING_REVIEW');
 const index=checkedIndex(directory,plan.capsule.indexSha256,plan.capsule.indexCount);checkedIndex(observer,plan.capsule.observerIndexSha256,plan.capsule.observerIndexCount);
 const run=json(path.join(directory,'run.json')),source=json(path.join(directory,'source.json')),audit=json(path.join(observer,'observer-audit.json'));
 s.ensure(run.head===plan.head&&source.head===plan.head&&source.tree===plan.tree&&!run.failure,'ROLE_FINISHED_SOURCE');
 s.ensure(source.archiveSha256===plan.capsule.archiveSha256&&s.canonical(source.causal)===s.canonical(plan.causalFiles)&&s.canonical(source.tools)===s.canonical(plan.nativeToolHashes),'ROLE_SOURCE_AND_NATIVE_TOOL_PINS');
 s.ensure(s.sha(read(path.join(directory,'manifest.json')))===plan.capsule.manifestSha256&&s.sha(read(path.join(directory,'verified-artifacts.json')))===plan.capsule.verifiedArtifactsSha256,'ROLE_ORIGINAL_MANIFEST_ARTIFACTS');
 const artifacts=json(path.join(directory,'verified-artifacts.json'));s.ensure(artifacts.bundleSha256===plan.bundleSha256&&artifacts.runtime.sha256===plan.chromiumSha256,'ROLE_ASSET_BINDING');
 s.ensure(audit.campaignAccepted&&audit.cleanupVerified&&audit.commandExit===0&&audit.baselineUnchanged&&audit.independentObservedExact&&audit.observerErrors.length===0&&audit.independentIdentityChecks.every(x=>x.matches),'ROLE_BUILDER_INDEPENDENT_CLEANUP');
 const phases=s.sequence(plan);s.ensure(s.canonical(run.phases.map(p=>({id:p.id,phase:p.phase})))===s.canonical(phases.map(p=>({id:p.id,phase:p.phase}))),'ROLE_BUILDER_PHASE_COVERAGE');
 const doc={version:1,evidenceClass:'RECORDED-EVIDENCE',scope:plan.scope,planSha256:s.sha(planBytes),capsule:{id:plan.capsule.id,head:source.head,tree:source.tree,indexSha256:plan.capsule.indexSha256,observerIndexSha256:plan.capsule.observerIndexSha256,archiveSha256:source.archiveSha256,originalCampaignAccepted:audit.campaignAccepted,cleanup:{commandExit:audit.commandExit,baselineUnchanged:audit.baselineUnchanged,independentObservedExact:audit.independentObservedExact,cleanupVerified:audit.cleanupVerified,observerErrors:audit.observerErrors.length,resourceAbsence:audit.resourceAbsence.every(x=>x.absent===true),processBirthAbsence:audit.processBirthAbsence.every(x=>x.sameBirthPresent===false&&x.uncertain===false),identityMatches:audit.independentIdentityChecks.every(x=>x.matches),containers:audit.ownedCount,volumes:audit.ownedVolumeCount,observedBirths:audit.processBirthAbsence.length}},phases:[]};
 for(const [field,file]of Object.entries({builderSha256:'build.cjs',schemaSha256:'schema.cjs',validatorSha256:'validate.cjs',replaySha256:'replay.cjs'}))doc[field]=s.sha(read(path.join(__dirname,file)));
 for(const selection of phases){
  const stage=run.phases.find(x=>x.id===selection.id),dest=path.join(directory,stage.id),raw=path.join(dest,'private-phase-captures','capture');
  const config=json(path.join(raw,'joined-config.json'));
  const process=json(path.join(dest,'phase-process-before-verdict.json')).result;
  s.ensure(!stage.failure&&stage.cleanup.length===3&&s.canonical(stage.cleanup.map(x=>x.kind).sort())===s.canonical(['mongo','postgres','vault'])&&stage.cleanup.every(x=>x.normalCleanup&&x.verifiedAbsent&&!x.forcedCleanup&&x.image===plan.images[x.kind])&&stage.cleanup.reduce((n,x)=>n+x.mounts.length,0)===5,'ROLE_BUILDER_PHASE_CLEANUP');
  if(selection.phase==='joined-browser-consumer')s.ensure(config.uiFixture.expectedBundleSha256===plan.bundleSha256&&config.browserRuntime.sha256===plan.chromiumSha256,'ROLE_BROWSER_CONFIG_ARTIFACTS');
  const child=json(path.join(dest,'child-cleanup.json')),removed=json(path.join(dest,'private-directory-cleanup.json')),residual=json(path.join(dest,'private-directory-residuals.json'));
  s.ensure(child.allAbsent&&!child.forcedCleanup&&removed.absent&&residual.socketOrSymlinkPaths.length===0,'ROLE_BUILDER_LOCAL_CLEANUP');
  const control=selection.kind==='control'?plan.controls.find(c=>c.id===selection.id):undefined;
  const archiveHashes={};
  for(const [file,hash]of Object.entries(plan.causalFiles)){
   let bytes=require('./replay.cjs').readObject(repo,plan.head,file);s.ensure(s.sha(bytes)===hash,'ROLE_BUILDER_SOURCE');
   for(const patch of control?.patches||[])if(patch.file===file){const text=bytes.toString();s.ensure(text.split(patch.before).length===2,'ROLE_PATCH_UNIQUE');bytes=Buffer.from(text.replace(patch.before,patch.after));}
   const archived=path.join(control?dest:path.join(directory),control?'controlled-source':'source',file);s.ensure(s.sha(read(archived))===s.sha(bytes),'ROLE_EXECUTED_SOURCE '+file);archiveHashes[file]=s.sha(bytes);
  }
  if(control){const applied=json(path.join(dest,'applied-control.json'));s.ensure(applied.id===control.id&&control.patches.every(p=>applied.executedFiles[p.file]===archiveHashes[p.file]),'ROLE_APPLIED_CONTROL');}
  const p={...selection,head:plan.head,tree:plan.tree,process,originalVerdict:stage.result,configuration:s.configuration(config),observations:{},provenance:{},archiveHashes,cleanup:{normal:true,childrenAbsent:true,forced:false,directoryAbsent:true,residuals:0,containers:3,volumes:5}};
  // Validate ORIGINAL URI/path/physical equalities before any projection alias.
  require('./replay.cjs').replay(p,plan,{repo,deps,originalDirectory:raw,configuration:config});
  for(const name of plan.requiredRaw[p.phase]){
   const file=path.join(raw,name),relative=path.relative(directory,file);s.ensure(index[relative]===s.sha(read(file)),'ROLE_INDEXED_RAW');p.observations[name]=s.projectRaw(name,json(file));p.provenance[name]={rawSha256:index[relative],projectedSha256:s.sha(s.canonical(p.observations[name]))};
  }
  if(control){const file=path.join(raw,'native.log'),text=read(file).toString();s.ensure(/^ERR_ASSERTION$/m.test(text),'ROLE_ORIGINAL_ASSERTION_WITNESS');p.assertionWitness='ERR_ASSERTION';p.assertionRawSha256=s.sha(read(file));}
  require('./replay.cjs').replay(p,plan,{repo,deps});doc.phases.push(p);
 }
 doc.projectionSha256=s.documentHash(doc);require('./validate.cjs')(doc,plan,{repo,deps,planBytes});return doc;
}
module.exports={build,checkedIndex};
if(require.main===module){const args=process.argv.slice(2),get=n=>args.includes(n)?args[args.indexOf(n)+1]:null;const file=get('--plan');s.ensure(file&&get('--capsule')&&get('--observer')&&get('--repo')&&get('--deps')&&get('--out'),'Usage: --plan --capsule --observer --repo --deps --out (explicit existing paths)');const bytes=read(file),doc=build({directory:get('--capsule'),observer:get('--observer'),plan:JSON.parse(bytes),planBytes:bytes,repo:get('--repo'),deps:get('--deps')});fs.writeFileSync(get('--out'),JSON.stringify(doc,null,2)+'\n',{flag:'wx',mode:0o644});console.log('RECORDED-EVIDENCE projection created; no native execution');}
