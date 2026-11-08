'use strict';
// Recording Docker protocol only. No process, Docker, listener or image is started.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const custody=require('./custody'),observer=require('./custody-observer');
const owner='44444444-4444-4444-8444-444444444444';
function fixture ({mutate,append}={}){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'m4-custody-source-'));const config=path.join(root,'docker');fs.mkdirSync(config);
 const kinds=['postgres','mongo','vault','client'],images=Object.fromEntries(kinds.map((k,i)=>[k,'sha256:'+String(i+1).repeat(64)]));
 const plan={version:1,profile:custody.PROFILE,status:'PARENT_BOUND',ownerUUID:owner,dockerExecutable:'/usr/bin/docker',dockerConfig:config,
  endpointProfile:'stable-network-settings-v1',baseline:{containers:[],volumes:[],networks:[]},images};
 const records=[],calls=[],containers=new Map(),volumes=new Map();let serial=0;
 const image=kind=>({Id:images[kind],Config:{Env:['PATH=/bin'],Labels:{},Cmd:[kind==='postgres'?'postgres':kind==='mongo'?'mongod':kind==='vault'?'server':'node'],Entrypoint:['entry'],Volumes:kind==='postgres'?{'/data':{}}:{},User:'',WorkingDir:''}});
 const transport=(args)=>{
  calls.push(args);const ok=value=>({status:0,stdout:typeof value==='string'?value:JSON.stringify(value),stderr:''});
  if(args[0]==='image')return ok([image(kinds.find(k=>images[k]===args.at(-1)))]);
  if(args[0]==='create'){
   const at=args.findIndex(v=>v.startsWith('sha256:')),kind=kinds.find(k=>images[k]===args[at]),source=image(kind);
   const id=(++serial).toString(16).padStart(64,'0'),row={Id:id,Name:'/'+args[args.indexOf('--name')+1],Image:images[kind],Created:'synthetic-created',
    Config:{...source.Config,Image:images[kind],Labels:{},Env:['PATH=/bin'],Cmd:args.slice(at+1).length?args.slice(at+1):source.Config.Cmd},
    HostConfig:{NetworkMode:kind==='client'?'host':'bridge',AutoRemove:false,Privileged:false,PublishAllPorts:false,CapAdd:null,Devices:[],SecurityOpt:null,ExtraHosts:[],PortBindings:{}},
    Mounts:[],NetworkSettings:{Ports:{},Networks:{},SandboxID:''},State:{Status:'created',Running:false,StartedAt:'0001-',FinishedAt:'0001-',ExitCode:0,Error:''}};
   const env=new Map([['PATH','/bin']]);for(let i=1;i<at;i++){
    if(args[i]==='--label'){const [k,v]=args[++i].split('=');row.Config.Labels[k]=v;}
    if(args[i]==='-e'){const k=args[++i];env.set(k,'synthetic-secret');}
    if(args[i]==='-p'){const port=args[++i].split(':').at(-1)+'/tcp';row.HostConfig.PortBindings[port]=[{HostIp:'127.0.0.1',HostPort:''}];}
    if(args[i]==='--user')row.Config.User=args[++i];if(args[i]==='--workdir')row.Config.WorkingDir=args[++i];
    if(args[i]==='--add-host')row.HostConfig.ExtraHosts.push(args[++i]);
    if(args[i]==='--mount'){const parts=args[++i].split(','),kv=Object.fromEntries(parts.map(p=>p.split('=')));row.Mounts.push({Type:'bind',Source:kv.src,Destination:kv.dst,RW:!parts.includes('readonly')});}
   }
   row.Config.Env=[...env].map(([k,v])=>k+'='+v);row.Path='entry';row.Args=[...row.Config.Cmd];
   if(kind==='postgres'){const name='anonymous_'+id;volumes.set(name,{Name:name,Driver:'local',CreatedAt:'synthetic-created',Labels:null,Options:null,Scope:'local'});row.Mounts.push({Type:'volume',Name:name,Source:'/private-volume',Destination:'/data',RW:true});}
   containers.set(id,row);if(mutate)mutate(row,args);return ok(id);
  }
  if(args[0]==='inspect'){
   const ids=args[1]==='--type'?[args[3]]:args.slice(1);if(ids.some(id=>!containers.has(id)))return {status:1,stdout:'',stderr:'No such container'};
   return ok(ids.map(id=>containers.get(id)));
  }
  if(args[0]==='ps')return ok(args.includes('--format')?[...containers].map(([id,row])=>id+' '+row.Name.slice(1)).join('\n'):[...containers.keys()].join('\n'));
  if(args[0]==='start'){const row=containers.get(args[1]);row.State.Running=true;row.State.StartedAt='2026-start';return ok(args[1]);}
  if(args[0]==='rm'){assert.equal(args[1],'--force');containers.delete(args[2]);return ok(args[2]);}
  if(args[0]==='volume' && args[1]==='inspect')return volumes.has(args[2])?ok([volumes.get(args[2])]):{status:1,stdout:'',stderr:'No such volume'};
  if(args[0]==='volume' && args[1]==='rm'){volumes.delete(args[2]);return ok(args[2]);}
  throw new Error('Unexpected recording Docker command');
 };
 const api=custody.create({plan,directory:path.join(root,'custody'),invoke:transport,append:entry=>{if(append)append(entry);records.push(structuredClone(entry));
    if(entry.type==='created-identified'){const ack=observer.admitCreated(entry,containers.get(entry.value.id),plan.baseline);fs.writeFileSync(path.join(root,'custody','receipts',entry.value.id+'.json'),JSON.stringify(ack),{mode:0o600});}}});api.initialize();
 return {api,plan,records,calls,containers,volumes,root,invoke:transport,close:()=>fs.rmSync(root,{recursive:true,force:true})};
}
const serviceSpec={ports:['5432/tcp'],env:{POSTGRES_PASSWORD:'synthetic-secret'}};
test('staged create records exact identities and anonymous volumes before start; cleanup uses IDs and fresh empty references',()=>{
 const f=fixture();try{
  const id=f.api.stage('postgres',serviceSpec);assert(f.records.some(r=>r.type==='created-identified'));assert(!f.calls.some(a=>a[0]==='start'));
  f.api.start(id);assert.equal(f.api.close()[0].id,id);assert.equal(f.volumes.size,0);
  assert(f.calls.filter(a=>a[0]==='rm').every(a=>a[2]===id));assert(!JSON.stringify(f.records).includes('synthetic-secret'));
 }finally{f.close();}
});
test('wrong ID/name/config/argv/mount and missing journal never permit start or cleanup by name',()=>{
 for(const mutate of [r=>{r.Id='e'.repeat(64);},r=>{r.Mounts.push({Type:'bind',Source:'/foreign',Destination:'/foreign',RW:true});},r=>{r.Name='/foreign';},r=>{r.Image='sha256:'+'f'.repeat(64);},r=>{r.Config.Cmd=['foreign'];},r=>{r.HostConfig.Privileged=true;},r=>{r.Config.Env=['PASSWORD=foreign'];}]){
  const f=fixture({mutate});try{assert.throws(()=>f.api.stage('postgres',serviceSpec));assert(!f.calls.some(a=>a[0]==='start'||a[0]==='rm'));assert.throws(()=>f.api.close(),/UNCLOSED/);}finally{f.close();}
 }
 const f=fixture({append:r=>{if(r.type==='created-identified')throw new Error('disk fault');}});try{assert.throws(()=>f.api.stage('postgres',serviceSpec),/JOURNAL/);assert.throws(()=>f.api.start('1'.padStart(64,'0')),/UNJOURNALED/);assert(!f.calls.some(a=>a[0]==='start'));}finally{f.close();}
});
test('changed complete Config or HostConfig fingerprint refuses cleanup; client exit comes from actual container state',()=>{
 const f=fixture();try{const id=f.api.stage('postgres',serviceSpec);f.containers.get(id).Config.Unexpected='changed';assert.throws(()=>f.api.remove(id),/IDENTITY_DRIFT/);delete f.containers.get(id).Config.Unexpected;f.api.remove(id);
  const client=f.api.stage('client',{command:['node','synthetic-program']});const argv=f.api.start(client,true);assert.deepEqual(argv.slice(-3),['start','--attach',client]);
  Object.assign(f.containers.get(client).State,{Running:false,StartedAt:'2026-start',FinishedAt:'2026-finish',ExitCode:5});assert.equal(f.api.finishClient(client,{status:0,signal:null}),5);f.api.remove(client);f.api.close();
 }finally{f.close();}
});
test('four live containers and one serial client are hard bounds; held anonymous reference refuses volume deletion',()=>{
 const f=fixture();try{
  const pg=f.api.stage('postgres',serviceSpec);f.api.stage('mongo',{});f.api.stage('vault',{});f.api.stage('client',{});assert.throws(()=>f.api.stage('client',{}),/LIVE_BOUND/);
  const other=f.containers.values().next().value;other.Mounts.push({Type:'volume',Name:'foreign',Source:'/foreign',Destination:'/extra',RW:true});assert.throws(()=>f.api.remove(pg),/IDENTITY_DRIFT/);
 }finally{f.close();}
});
test('M4 observer consumes complete journal and refuses omitted start/cleanup or unknown host child',()=>{
 const f=fixture();try{
  const ids=['postgres','mongo','vault'].map(kind=>f.api.stage(kind,kind==='postgres'?serviceSpec:{}));for(const id of ids)f.api.start(id);const client=f.api.stage('client',{});f.api.start(client,true);Object.assign(f.containers.get(client).State,{StartedAt:'2026-start',FinishedAt:'2026-end',ExitCode:0});f.api.finishClient(client,{status:0,signal:null});f.api.remove(client);f.api.close();
  const supervisor={phase:'m4-clients',hostProcessesClosed:true,directChildrenReaped:true,processAudit:{unknownAdopted:[],freshReadbackWithinBudget:true,terminalReceiptFailures:[],lastReadback:{readbackComplete:true,knownPresent:[],unknownAdopted:[]}}};
  const input={owner,baseline:f.plan.baseline,supervisor,run:{clients:['cgmsim','oref0']}};assert.equal(observer.normalize(f.records,input).length,4);
  assert.throws(()=>observer.normalize(f.records.slice(0,-1),input),/CLEANUP/);
  const noIntent=f.records.filter(r=>r.type!=='start-intent').map((r,i)=>({...r,sequence:i+1}));assert.throws(()=>observer.normalize(noIntent,input),/START_INTENT_REQUIRED|CLIENT_EXIT_MISSING/);
  const omitted=f.records.filter(r=>r.type!=='started').map((r,i)=>({...r,sequence:i+1}));assert.throws(()=>observer.normalize(omitted,input),/START_OR_EXIT/);
  assert.throws(()=>observer.normalize(f.records,{...input,supervisor:{...supervisor,processAudit:{...supervisor.processAudit,unknownAdopted:[{pid:123}]}}}),/HOST_CUSTODY/);
 }finally{f.close();}
});
test('independent observer consumes actual journal, persists before ACK, and a missing durable write leaves start unadmitted',()=>{
 const f=fixture();try{
  const id=f.api.stage('postgres',serviceSpec),directory=path.join(f.root,'independent');fs.mkdirSync(directory);fs.mkdirSync(path.join(directory,'receipts'));
  fs.writeFileSync(path.join(directory,'custody.jsonl'),f.records.map(r=>JSON.stringify(r)).join('\n')+'\n');
  const read=args=>{assert.equal(args[0],args[1]==='inspect'?'volume':'inspect');return JSON.stringify(args[0]==='volume'?[f.volumes.get(args[2])]:[f.containers.get(args.at(-1))]);};
  const broken=observer.observe({plan:f.plan,directory,invoke:read,append:()=>{throw new Error('durable disk failure');}});
  assert.throws(()=>broken.scan(),/durable disk failure/);assert(!fs.existsSync(path.join(directory,'receipts',id+'.json')));
  const actual=observer.observe({plan:f.plan,directory,invoke:read});actual.scan();actual.scan();assert.deepEqual(actual.identified(),[id]);
  const receipt=JSON.parse(fs.readFileSync(path.join(directory,'receipts',id+'.json')));assert.equal(receipt.identity,custody.digest(custody.identity(f.containers.get(id))));
  assert.equal(fs.readFileSync(path.join(directory,'observer.jsonl'),'utf8').trim().split('\n').length,1);
  // Actual start rejects a forged receipt, then consumes restored independently checked ACK.
  const file=path.join(f.root,'custody','receipts',id+'.json');fs.writeFileSync(file,JSON.stringify({...receipt,identity:'wrong'}));assert.throws(()=>f.api.start(id),/OBSERVER_RECEIPT/);
  fs.writeFileSync(file,JSON.stringify(receipt));f.api.start(id);f.api.close();
 }finally{f.close();}
});
test('baseline full fingerprints use strict 32-ID exact batches; missing late rows and Config drift refuse',()=>{
 const rows=Array.from({length:65},(_,i)=>({Id:(i+1).toString(16).padStart(64,'0'),Name:'/synthetic-'+i,Image:'sha256:'+'a'.repeat(64),Created:'synthetic',Config:{Env:['SECRET=synthetic-private']},HostConfig:{Privileged:false},Mounts:[],NetworkSettings:{Ports:{},Networks:{},SandboxID:''}}));
 const calls=[];let missing=false,drift=false;
 const invoke=args=>{calls.push(args);if(args[0]==='ps')return rows.map(r=>r.Id).join('\n');if(args[1]==='ls')return '';
  assert.deepEqual(args.slice(0,3),['inspect','--type','container']);assert(args.length<=35);let selected=args.slice(3).map(id=>structuredClone(rows.find(r=>r.Id===id)));if(missing && args.length===4)selected=[];if(drift)selected[0].Config.Env.push('CHANGED=yes');return JSON.stringify(selected);};
 const baseline=observer.baselineSnapshot(invoke);assert.equal(Object.keys(baseline.identities.containers).length,65);assert(!JSON.stringify(baseline).includes('synthetic-private'));
 assert.equal(calls.filter(a=>a[0]==='inspect').length,3);missing=true;assert.throws(()=>observer.verifyBaseline(invoke,baseline),/EXACT_BATCH/);
 missing=false;drift=true;assert.throws(()=>observer.verifyBaseline(invoke,baseline),/BASELINE_CHANGED/);drift=false;observer.verifyBaseline(invoke,baseline);
});
test('actual Lab.runClient preserves output and inspected exit while binding exact attach argv and cleanup',async()=>{
 const vm=require('node:vm'),{EventEmitter}=require('node:events'),{createRequire}=require('node:module');
 const filename=path.join(__dirname,'lab.js'),local=createRequire(filename),calls=[];
 const cp={...require('node:child_process'),spawn(executable,args){calls.push([executable,...args]);const child=new EventEmitter();child.stdout=new EventEmitter();child.stderr=new EventEmitter();child.kill=()=>{throw new Error('unexpected timeout');};setImmediate(()=>{child.stdout.emit('data',Buffer.from('synthetic output'));child.stderr.emit('data',Buffer.from('synthetic stderr'));child.emit('close',0,null);});return child;}};
 const sandbox={module:{exports:{}},__dirname,__filename:filename,URL,console,process,Buffer,setTimeout,clearTimeout,require:name=>name==='node:child_process'?cp:local(name)};
 vm.runInNewContext(fs.readFileSync(filename,'utf8'),sandbox,{filename});const root=fs.mkdtempSync(path.join(os.tmpdir(),'m4-client-output-'));
 const id='f'.repeat(64),events=[],subject={opt:{out:root},clientSpec:()=>({}),custody:{stage:()=>id,start:value=>{assert.equal(value,id);return ['/usr/bin/docker','start','--attach',id];},finishClient:(value,r)=>{assert.equal(value,id);assert.equal(r.status,0);events.push('inspected');return 5;},remove:value=>{assert.equal(value,id);events.push('removed');}},redactSecrets:value=>value};
 try{const result=await sandbox.module.exports.Lab.prototype.runClient.call(subject,'/unused',{},['synthetic'],'recording');assert.equal(result.status,5);assert.equal(result.stdout,'synthetic output');assert.equal(result.stderr,'synthetic stderr');assert.deepEqual(events,['inspected','removed']);assert.deepEqual(calls,[['/usr/bin/docker','start','--attach',id]]);}finally{fs.rmSync(root,{recursive:true,force:true});}
});
test('fixed wrapper consumes parent source/budget binding and original gate argv without starting a process',async()=>{
 const {EventEmitter}=require('node:events'),wrapper=require('./custody-run'),f=fixture();
 try{const planFile=path.join(f.root,'parent.json'),head='a'.repeat(40),plan={...f.plan,applicationHead:head,activeSeconds:600,cleanupSeconds:120};fs.writeFileSync(planFile,JSON.stringify(plan));let called=0;
 const spawn=(executable,args,options)=>{called++;assert.equal(executable,process.execPath);assert.deepEqual(args.slice(-4),['--ref',head,'--clients','cgmsim,oref0']);assert.equal(options.env.NS_M4_CUSTODY_PLAN,planFile);const child=new EventEmitter();child.kill=()=>{throw new Error('unexpected kill');};setImmediate(()=>child.emit('close',7,null));return child;};
 const options={planFile,out:path.join(f.root,'uncreated-output'),ref:head,repository:'/synthetic/repository',dependencies:'/synthetic/dependencies',spawn,invoke:()=>{throw new Error('no resource was created');}};
 assert.equal(await wrapper.run(options),7);assert.equal(called,1);plan.applicationHead='b'.repeat(40);fs.writeFileSync(planFile,JSON.stringify(plan));assert.throws(()=>wrapper.run(options),/PARENT_BINDING/);assert.equal(called,1);
 }finally{f.close();}
});
test('anonymous volume deletion requires a fresh empty reference set, and recovery only verifies prior exact IDs',()=>{
 const f=fixture();try{const pg=f.api.stage('postgres',serviceSpec),mongo=f.api.stage('mongo',{}),volume=[...f.volumes.keys()][0];
 f.containers.get(mongo).Mounts.push({Type:'volume',Name:volume,Source:'/private-volume',Destination:'/held',RW:true});
 assert.throws(()=>f.api.remove(pg),/VOLUME_REFERENCED/);assert.throws(()=>f.api.stage('client',{}),/UNRESOLVED_RESOURCE/);assert(f.volumes.has(volume));assert(!f.calls.some(a=>a[0]==='volume' && a[1]==='rm'));
 f.containers.get(mongo).Mounts.pop();f.api.close();
 const directory=path.join(f.root,'recovery');fs.mkdirSync(directory);fs.writeFileSync(path.join(directory,'custody.jsonl'),f.records.map(r=>JSON.stringify(r)).join('\n')+'\n');
 const before=f.calls.length;const result=custody.recover({plan:f.plan,directory,invoke:f.invoke});assert.equal(result.length,2);assert(f.calls.slice(before).every(a=>a[0]==='inspect'||(a[0]==='volume' && a[1]==='inspect')));
 fs.appendFileSync(path.join(directory,'custody.jsonl'),JSON.stringify({sequence:f.records.length+1,owner,type:'create-intent',value:{name:'foreign'}})+'\n');assert.throws(()=>custody.recover({plan:f.plan,directory,invoke:f.invoke}),/RECOVERY_SEQUENCE/);
 }finally{f.close();}
});
test('physical closed prefixes remain distinct from scientific completeness',()=>{
 const supervisor={phase:'m4-clients',hostProcessesClosed:true,directChildrenReaped:true,processAudit:{unknownAdopted:[],freshReadbackWithinBudget:true,terminalReceiptFailures:[],lastReadback:{readbackComplete:true,knownPresent:[],unknownAdopted:[]}}};
 for(const count of [0,1,2]){const f=fixture();try{for(const kind of ['mongo','vault'].slice(0,count))f.api.stage(kind,{});f.api.close();const input={owner,baseline:f.plan.baseline,supervisor};assert.equal(observer.normalize(f.records,input).length,count);assert.throws(()=>observer.normalize(f.records,{...input,run:{clients:['cgmsim','oref0']}}),/RUN_START_OR_EXIT/);}finally{f.close();}}
});
test('malformed observer IDs never reach transport',()=>{
 const f=fixture();try{const directory=path.join(f.root,'malformed');fs.mkdirSync(directory);fs.mkdirSync(path.join(directory,'receipts'));let calls=0;
 const entry={sequence:1,owner,type:'created-identified',value:{id:'--invalid-id',volumes:[]}};fs.writeFileSync(path.join(directory,'custody.jsonl'),JSON.stringify(entry)+'\n');const observed=observer.observe({plan:f.plan,directory,invoke:()=>{calls++;throw new Error('transport forbidden');}});assert.throws(()=>observed.scan(),/CREATED_FULL_ID/);assert.equal(calls,0);
 }finally{f.close();}
});
test('initial validation rejects running or previously run containers before independent ACK admission',()=>{
 for(const mutate of [r=>{r.State.Running=true;},r=>{r.State.StartedAt='2026-already-ran';}]){const f=fixture({mutate});try{assert.throws(()=>f.api.stage('postgres',serviceSpec),/CUSTODY_INITIAL_STOPPED/);assert(!f.records.some(r=>r.type==='created-identified'));assert(!f.calls.some(a=>a[0]==='start'));}finally{f.close();}}
});
test('an unresolved initial create forbids any subsequent creation',()=>{
 let first=true;const f=fixture({mutate:r=>{if(first){first=false;r.Name='/foreign';}}});try{assert.throws(()=>f.api.stage('postgres',serviceSpec),/CUSTODY_NAME_IMAGE/);const before=f.calls.filter(a=>a[0]==='create').length;assert.throws(()=>f.api.stage('client',{}),/CUSTODY_UNRESOLVED_RESOURCE/);assert.equal(f.calls.filter(a=>a[0]==='create').length,before);}finally{f.close();}
});
