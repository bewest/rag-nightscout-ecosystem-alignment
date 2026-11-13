'use strict';
// Source-only preparation. This module neither imports a PG client nor launches
// Docker/services. Actual deployment config is evaluated only after source admission.
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process'),crypto=require('node:crypto');
const CORE='074eab44ee75b9175c951b6a8add3df3e9554af7',DEPLOY='3d13c63bc404397d6daee501c152288b12d5931d';
const need=(v,c)=>{if(!v)throw Object.assign(Error(c),{code:c});};
const git=(root,args)=>cp.execFileSync('git',['-C',root,...args],{encoding:'utf8',timeout:10000,maxBuffer:1048576,stdio:['ignore','pipe','pipe']}).trim();
function generate(input){
 need(input&&Object.keys(input).sort().join(',')==='nonce,source,sourceRoot,topology','NATIVE_INPUT_SHAPE');const{sourceRoot,source,nonce,topology}=input;
 need(path.isAbsolute(sourceRoot)&&fs.realpathSync(sourceRoot)===sourceRoot,'NATIVE_SOURCE_PATH');
 need(source&&Object.keys(source).sort().join(',')==='coreCommit,deployCommit'&&source.coreCommit===CORE&&source.deployCommit===DEPLOY,'NATIVE_SOURCE_PIN');
 need(/^[a-f0-9]{32}$/.test(nonce||''),'NATIVE_NONCE');
 need(topology&&Object.keys(topology).sort().join(',')==='api,evaluator,realtime,shards'&&topology.api===2&&topology.realtime===2&&topology.evaluator===2&&topology.shards===4,'NATIVE_TOPOLOGY');
 // Git identity/clean tracked build inputs and exact overlay are checked before
 // loading any source-controlled JavaScript (including build.js itself).
 need(git(sourceRoot,['rev-parse','HEAD'])===CORE,'NATIVE_CORE_CHANGED');
 const markerFile=path.join(sourceRoot,'deploy/multitenant/.overlay.json'),stat=fs.lstatSync(markerFile);need(stat.isFile()&&!stat.isSymbolicLink()&&stat.size<=16384,'NATIVE_OVERLAY');
 const marker=JSON.parse(fs.readFileSync(markerFile));need(marker.deployCommit===source.deployCommit&&path.isAbsolute(marker.deployRepository),'NATIVE_OVERLAY');
 // Only this known host tool is executed before the admitted modules. Diff is
 // read-only; untracked source modules are refused, dependencies are external.
 need(!git(sourceRoot,['status','--porcelain','--untracked-files=all','--','lib','package.json','package-lock.json','server.js']),'NATIVE_SOURCE_DIRTY');
 const names=git(marker.deployRepository,['ls-tree','-r','--name-only',source.deployCommit,'--','bindings/compose/multitenant']).split('\n').filter(Boolean);
 const base=path.join(sourceRoot,'deploy/multitenant');
 for(const name of names){const local=path.join(base,name.slice('bindings/compose/multitenant/'.length));const st=fs.lstatSync(local);need(st.isFile()&&!st.isSymbolicLink(),'NATIVE_OVERLAY');const blob=cp.execFileSync('git',['-C',marker.deployRepository,'show',source.deployCommit+':'+name],{timeout:10000,maxBuffer:1048576});need(fs.readFileSync(local).equals(blob),'NATIVE_OVERLAY_CHANGED');}
 const allowed=new Set(names.map(x=>x.slice('bindings/compose/multitenant/'.length)));
 function visit(dir,prefix=''){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const name=prefix+entry.name;if(['.env','.state','.overlay.json'].includes(name))continue;if(entry.isDirectory())visit(path.join(dir,entry.name),name+'/');else need(allowed.has(name),'NATIVE_OVERLAY_UNTRACKED');}}visit(base);
 const selectedEnvironment={NS_API_REPLICAS:'2',NS_REALTIME_WORKERS:'2',NS_REALTIME_SHARDS:'4',NS_EVALUATOR_WORKERS:'2',NS_DEMO_TENANTS:'16',NS_TENANT_STARTUP_CONCURRENCY:'4',NS_TENANT_READINESS:'serve',NS_OPERATION_LEASE_SESSIONS:'4'};
 const selectedKeys=Object.keys(process.env).filter(x=>/^(NS_POOL_|NS_TENANT_|NS_OPERATION_|NS_API_REPLICAS$|NS_REALTIME_|NS_EVALUATOR_|NS_DEMO_TENANTS$)/.test(x));
 const before={...process.env};try{
  for(const key of selectedKeys)delete process.env[key];Object.assign(process.env,selectedEnvironment);
  const B=require(path.join(base,'connection-budget')),P=require(path.join(base,'connection-budget-profile')),pool=require(path.join(sourceRoot,'lib/server/serve/pool-config'));
  need(B.REVIEWED_CORE_COMMIT===CORE,'NATIVE_COVERAGE_UNKNOWN');
  const descriptors=B.describe(P.sourceDocuments(),pool);
  const slots=descriptors.map(row=>({processInstanceId:row.processInstanceId,capabilities:Object.fromEntries(Object.entries(row.capabilities).map(([key,c])=>[key,c.kind==='pool'?{kind:'pool',poolMax:c.requestedMaximum,maxInstances:c.minimumInstances||1}:{kind:'client',directGroup:key.startsWith('nightscout-feed-')?key:'transient'}])),directGroups:Object.fromEntries([...new Set(Object.entries(row.capabilities).filter(([,c])=>c.kind==='client').map(([key])=>key.startsWith('nightscout-feed-')?key:'transient'))].map(group=>[group,group==='transient'?4:1])),cold:{activeLimit:1,pendingLimit:Math.max(8,row.startupConcurrency*2+1),minDelayMs:25,maxDelayMs:75},maximumOutstandingGenerations:row.processInstanceId==='api'?2:1}));
  need(slots.length===11&&slots.some(x=>x.processInstanceId==='api-2')&&slots.some(x=>x.processInstanceId==='evaluator-2'),'NATIVE_ROSTER');
  const profile={version:1,kind:'explicit-connection-budget-profile',source,resource:{pgResourceId:'native-'+nonce.slice(0,16),systemIdentifier:'OBSERVE_AT_BOOTSTRAP',postmasterStartedAt:'OBSERVE_AT_BOOTSTRAP',serverMaximum:'DERIVE_DECLARED',reserved:{superuser:3,other:0},aliases:['postgres:5432'],allowances:{unmanaged:0,observers:2,controlRecovery:1,bootstrapOverlap:2,oldNewRolloutOverlap:0}},slots,bootstrapSchedule:'EXPLICIT_OVERLAP'};
  const first=P.resolve(profile,{source});const candidate=structuredClone(first.profile);candidate.resource.systemIdentifier='0';candidate.resource.postmasterStartedAt='preparation-only';const initial=B.compile(candidate,P.sourceDocuments(),{source,poolConfig:pool});
  profile.resource.allowances.oldNewRolloutOverlap=initial.slots.find(x=>x.processInstanceId==='api').declaredMaximum;
  const resolved=P.resolve(profile,{source});
  return{generatorSha256:crypto.createHash('sha256').update(fs.readFileSync(__filename)).digest('hex'),kind:'native-admission-source-profile',authorization:'SOURCE_PREP_ONLY_NOT_LAUNCH_AUTHORIZATION',source,nonce,selectedEnvironment,descriptors,profile,derivedMaximum:resolved.requiredMaximum,sourceCost:initial.declaredMaximum,uncertainApiGenerationCredit:profile.resource.allowances.oldNewRolloutOverlap,limits:['Fresh owned PG exclusive unmanaged0 still requires actual metadata/custody checks','Physical resources, ports/IPAM and actual runtime are unmeasured','Cold1 bounded queue and25..75ms jitter are explicit functional experiment, not a production default','Only API slot admits one uncertain overlapping generation; third attempt must refuse']};
 }finally{for(const key of Object.keys(process.env))if(!Object.hasOwn(before,key))delete process.env[key];Object.assign(process.env,before);}
}
module.exports={generate};
if(require.main===module){try{need(process.argv.length===4,'NATIVE_PROFILE_ARGUMENTS');const fd=fs.openSync(process.argv[2],fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);let input;try{const stat=fs.fstatSync(fd);need(stat.isFile()&&!(stat.mode&0o077)&&stat.size<=32768,'NATIVE_INPUT_CUSTODY');const bytes=Buffer.alloc(32769),length=fs.readSync(fd,bytes,0,bytes.length,0);need(length<=32768,'NATIVE_INPUT_CUSTODY');input=JSON.parse(bytes.subarray(0,length));}finally{fs.closeSync(fd);}const output=process.argv[3];need(!fs.existsSync(output),'NATIVE_OUTPUT_EXISTS');const result=generate(input);fs.mkdirSync(output,{mode:0o700});for(const[name,value]of [['profile.json',result.profile],['source-profile.private.json',result]])fs.writeFileSync(path.join(output,name),JSON.stringify(value,null,2)+'\n',{flag:'wx',mode:0o600});process.stdout.write(JSON.stringify({authorization:result.authorization,source:result.source,processes:result.descriptors.length,derivedMaximum:result.derivedMaximum})+'\n');}catch(e){process.stderr.write(JSON.stringify({error:e.code||'NATIVE_PROFILE_REFUSED'})+'\n');process.exitCode=1;}}
