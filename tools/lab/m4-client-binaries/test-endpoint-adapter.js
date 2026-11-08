'use strict';
// Pure Python helper calls only; no Docker/server/listener/build. Optional actual
// retained endpoint maps remain private and are never copied into this source.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const adapter=require('./endpoint-adapter'),{digest}=require('./custody');
const nid='1'.repeat(64),cid='2'.repeat(64);
const synthetic=()=>({[nid]:{[cid]:{Name:'synthetic-peer',EndpointID:'3'.repeat(64),MacAddress:'02:00:00:00:00:01',IPv4Address:'192.0.2.1/24',IPv6Address:''}}});
const rows=maps=>Object.entries(maps).map(([Id,Containers])=>({Id,Name:'synthetic-network-'+Id,Driver:'bridge',UnknownStatic:{enabled:true},Containers}));
function compareCaller (before,after) {
  const a=adapter.networkSnapshot(rows(before)),b=adapter.networkSnapshot(rows(after));
  assert.equal(digest(a.identities),digest(b.identities),'M4_NETWORK_STATIC_CHANGED');
  return adapter.compareEndpoints(a.endpointMaps,b.endpointMaps);
}
test('actual network caller retains static unknown fields and uses approved typed endpoint profile',()=>{
 const before=synthetic(),after=structuredClone(before);after[nid][cid].EndpointID='4'.repeat(64);after[nid][cid].MacAddress='02:00:00:00:00:02';
 const comparison=compareCaller(before,after);assert.equal(comparison.profile,adapter.PROFILE);assert.equal(comparison.stableEquality,true);assert.equal(comparison.fullEquality,false);assert.equal(comparison.volatileObservationsChanged,true);
 assert.equal(digest(comparison.before),digest(before));assert.equal(digest(comparison.after),digest(after));
 for(const mutate of [v=>{v[nid][cid].Name='synthetic-changed';},v=>{v[nid][cid].IPv4Address='192.0.2.9/24';},v=>{delete v[nid][cid];},v=>{v[nid][cid].UnknownField='refuse';},v=>{v[nid][cid].MacAddress=42;}]){const changed=structuredClone(after);mutate(changed);assert.throws(()=>compareCaller(before,changed),/M4_ENDPOINT_PROFILE_REFUSED/);assert.equal(compareCaller(before,after).fullEquality,false);}
 const a=rows(before),b=rows(after);b[0].UnknownStatic.enabled=1;
 assert.notEqual(digest(adapter.networkSnapshot(a).identities),digest(adapter.networkSnapshot(b).identities));
 const config={Env:['SYNTHETIC_PRIVATE=value'],unknown:true},host={Privileged:false};
 const one=adapter.configurationFingerprint(config,host),two=adapter.configurationFingerprint({...config,unknown:1},host);assert.notEqual(one.sha256,two.sha256);assert(!JSON.stringify(one).includes('SYNTHETIC_PRIVATE'));
});
const beforeFile=process.env.NS_M4_ENDPOINT_BEFORE,afterFile=process.env.NS_M4_ENDPOINT_AFTER;
if(beforeFile || afterFile){
 test('retained actual endpoint maps replay through M4 caller without full endpoint equality',()=>{
  assert(beforeFile && afterFile,'M4_ACTUAL_ENDPOINT_BOTH_INPUTS_REQUIRED');const before=JSON.parse(fs.readFileSync(beforeFile)),after=JSON.parse(fs.readFileSync(afterFile));
  const result=compareCaller(before,after);assert.equal(result.stableEquality,true);assert.equal(result.fullEquality,false);assert(result.volatileDifferences.length>0);
  assert.equal(digest(result.before),digest(before));assert.equal(digest(result.after),digest(after));
  // Network-inspect envelopes above are explicitly synthetic. Only the retained
  // endpoint maps and their approved comparison are actual captured inputs.
 });
}
function baselineTransport (maps, mutate) {
 const networks=rows(maps),containers=new Map();
 for(const [network,members] of Object.entries(maps))for(const [id,endpoint] of Object.entries(members)){
  if(!containers.has(id))containers.set(id,{Id:id,Name:'/'+endpoint.Name,Created:'synthetic-created',Image:'sha256:'+'a'.repeat(64),Config:{Env:['SYNTHETIC_PRIVATE=value']},HostConfig:{OomKillDisable:false,UnknownStatic:true},Mounts:[],State:{Running:true},NetworkSettings:{Ports:{},Networks:{},SandboxID:'',SandboxKey:''}});
  const row=containers.get(id),parse=value=>value?value.split('/'):['','0'],v4=parse(endpoint.IPv4Address),v6=parse(endpoint.IPv6Address);
  row.NetworkSettings.Networks['synthetic-network-'+network]={NetworkID:network,EndpointID:endpoint.EndpointID,MacAddress:endpoint.MacAddress,IPAddress:v4[0],IPPrefixLen:Number(v4[1]),GlobalIPv6Address:v6[0],GlobalIPv6PrefixLen:Number(v6[1]),Gateway:'',Aliases:['synthetic-alias'],UnknownStatic:{preserved:true}};
 }
 if(mutate)mutate({networks,containers});
 return args=>{
  if(args[0]==='ps')return [...containers.keys()].join('\n');
  if(args[0]==='volume' && args[1]==='ls')return '';
  if(args[0]==='network' && args[1]==='ls')return networks.map(r=>r.Id).join('\n');
  if(args[0]==='inspect')return JSON.stringify(args.slice(3).map(id=>containers.get(id)));
  if(args[0]==='network' && args[1]==='inspect')return JSON.stringify(args.slice(2).map(id=>networks.find(r=>r.Id===id)));
  throw new Error('M4_RECORDING_TRANSPORT_COMMAND_REFUSED');
 };
}
test('actual baselineSnapshot/verifyBaseline caller admits only typed observations while all static/unknown/config fields stay exact',()=>{
 const observer=require('./custody-observer'),before=synthetic(),after=structuredClone(before);after[nid][cid].EndpointID='4'.repeat(64);after[nid][cid].MacAddress='02:00:00:00:00:02';
 const captured=observer.baselineSnapshot(baselineTransport(before)),restored=observer.verifyBaseline(baselineTransport(after),captured);assert.equal(restored.endpointComparison.stableEquality,true);assert.equal(restored.endpointComparison.fullEquality,false);
 for(const mutate of [({containers})=>{containers.get(cid).HostConfig.OomKillDisable=null;},({containers})=>{containers.get(cid).Config.Unknown=1;},({containers})=>{containers.get(cid).NetworkSettings.Ports={changed:[]};},({containers})=>{containers.get(cid).NetworkSettings.Networks['synthetic-network-'+nid].Aliases=['changed'];},({containers})=>{containers.get(cid).NetworkSettings.Networks['synthetic-network-'+nid].Gateway='192.0.2.254';},({containers})=>{containers.get(cid).UnknownTopStatic=true;},({containers})=>{containers.get(cid).NetworkSettings.UnknownStatic='new';},({networks})=>{networks[0].UnknownStatic.enabled=1;}])assert.throws(()=>observer.verifyBaseline(baselineTransport(after,mutate),captured),/M4_BASELINE_CHANGED/);
 for(const mutate of [({containers})=>{containers.get(cid).NetworkSettings.Networks['synthetic-network-'+nid].Gateway=1;},({containers})=>{containers.get(cid).NetworkSettings.SandboxKey=1;},({containers})=>{containers.get(cid).NetworkSettings.SandboxID=1;},({containers})=>{containers.get(cid).NetworkSettings.Networks['synthetic-network-'+nid].MacAddress='02:00:00:00:00:ff';},({containers})=>{delete containers.get(cid).NetworkSettings.Networks['synthetic-network-'+nid];}])assert.throws(()=>observer.verifyBaseline(baselineTransport(after,mutate),captured),/M4_ENDPOINT_PROFILE_REFUSED/);
 const lifecycle=observer.verifyBaseline(baselineTransport(after,({containers})=>{containers.get(cid).NetworkSettings.SandboxID='5'.repeat(64);containers.get(cid).NetworkSettings.SandboxKey='/synthetic/lifecycle';}),captured);
 assert.notEqual(digest(lifecycle.endpointComparison.containerObservations.before),digest(lifecycle.endpointComparison.containerObservations.after));assert.equal(lifecycle.endpointComparison.fullEquality,false);
});
if(beforeFile && afterFile)test('retained actual maps pass through actual M4 baseline capture/verification with explicit private fullEqualityfalse',()=>{
 const observer=require('./custody-observer'),before=JSON.parse(fs.readFileSync(beforeFile)),after=JSON.parse(fs.readFileSync(afterFile));
 const captured=observer.baselineSnapshot(baselineTransport(before));assert.notEqual(digest(before),digest(after),'OLD_STRICT_ENDPOINT_MAPS_WOULD_MATCH');
 const current=observer.verifyBaseline(baselineTransport(after),captured);assert.equal(current.endpointComparison.stableEquality,true);assert.equal(current.endpointComparison.fullEquality,false);assert.equal(digest(current.endpointComparison.before),digest(before));assert.equal(digest(current.endpointComparison.after),digest(after));
 const [network,members]=Object.entries(after).find(([,values])=>Object.keys(values).length);const container=Object.keys(members)[0];
 for(const mutate of [value=>{value[network][container].Name='synthetic-changed-peer';},value=>{value[network][container].IPv4Address='192.0.2.99/24';},value=>{delete value[network][container];},value=>{value[network][container].UnknownField=true;},value=>{value[network][container].MacAddress=42;}]){const changed=structuredClone(after);mutate(changed);assert.throws(()=>observer.verifyBaseline(baselineTransport(changed),captured),/M4_BASELINE_CHANGED|M4_ENDPOINT_PROFILE_REFUSED/);assert.equal(observer.verifyBaseline(baselineTransport(after),captured).endpointComparison.fullEquality,false);}

 // Complete inspect rows are synthetic envelopes around ACTUAL retained maps;
 // neither Config/HostConfig nor Sandbox transitions are claimed native here.
});

const engineBefore=process.env.NS_M4_FIRST_START_BEFORE,engineAfter=process.env.NS_M4_FIRST_START_AFTER;
if(engineBefore || engineAfter)test('retained actual engine Config/HostConfig passes the actual owned first-start observation caller',()=>{
 assert(engineBefore && engineAfter,'M4_ACTUAL_ENGINE_BOTH_INPUTS_REQUIRED');const custody=require('./custody'),before=JSON.parse(fs.readFileSync(engineBefore)),after=JSON.parse(fs.readFileSync(engineAfter));
 const row=value=>({Id:'6'.repeat(64),Name:'/synthetic-owned-envelope',Image:'sha256:'+'7'.repeat(64),Created:'synthetic-created',...value,Mounts:[],NetworkSettings:{},State:{StartedAt:'2026-synthetic-start'}});
 const record={identity:custody.identity(row(before)),firstStart:{oomKillDisable:false}};const observed=custody.firstStartObservation(record,row(after));assert.equal(observed.transition,'oom-kill-disable-false-to-null');assert(custody.firstStartMatches(observed));
 assert.equal(adapter.configurationFingerprint(before.Config,before.HostConfig).sha256,'1796fa9a8459abb04114566411b984f925b2fd4aedc485a69bc991216cf03f2f');
 assert.equal(adapter.configurationFingerprint(after.Config,after.HostConfig).sha256,'998e46e9a8aff5b93385061fb987b0b3f7268642ab7e1c8a40b65a78aff02097');
 const changed=structuredClone(after);changed.HostConfig.UnknownOtherField=true;assert.throws(()=>custody.firstStartObservation(record,row(changed)),/FIRST_START_OTHER_DRIFT/);
 // Only Config/HostConfig are ACTUAL retained engine data. Other identity fields
 // are synthetic: this replays the caller, not a native M4 fixture or image.
});
function explicitTransport (containers,networks) {
 return args=>{
  if(args[0]==='ps')return containers.map(row=>row.Id).join('\n');
  if(args[0]==='volume' && args[1]==='ls')return '';
  if(args[0]==='network' && args[1]==='ls')return networks.map(row=>row.Id).join('\n');
  if(args[0]==='inspect')return JSON.stringify(args.slice(3).map(id=>containers.find(row=>row.Id===id)));
  if(args[0]==='network' && args[1]==='inspect')return JSON.stringify(args.slice(2).map(id=>networks.find(row=>row.Id===id)));
  throw new Error('M4_EXPLICIT_RECORDING_COMMAND_REFUSED');
 };
}
function stoppedRows () {
 const networkName='synthetic-network-'+nid;
 const endpoint={NetworkID:nid,EndpointID:'',MacAddress:'',IPAddress:'',IPPrefixLen:0,GlobalIPv6Address:'',GlobalIPv6PrefixLen:0,Gateway:'',IPv6Gateway:'',Aliases:null,UnknownStatic:{preserved:true}};
 return {containers:[{Id:cid,Name:'/synthetic-stopped',Created:'synthetic-created',Image:'sha256:'+'a'.repeat(64),Config:{Env:['SYNTHETIC_PRIVATE=value']},HostConfig:{OomKillDisable:false},Mounts:[],State:{Status:'exited',Running:false,Restarting:false,Paused:false,Dead:false},NetworkSettings:{Ports:{},Networks:{[networkName]:endpoint},SandboxID:'',SandboxKey:''}}],networks:[{Id:nid,Name:networkName,Containers:{},UnknownStatic:true}]};
}
test('actual adapter distinguishes typed inactive configured membership without weakening active correlation or exact configuration',()=>{
 const observer=require('./custody-observer'),given=stoppedRows(),capture=()=>observer.baselineSnapshot(explicitTransport(given.containers,given.networks)),before=capture();
 assert.equal(observer.verifyBaseline(explicitTransport(given.containers,given.networks),before).endpointComparison.fullEquality,true);
 for(const mutate of [r=>{r.State.Running=true;},r=>{r.State.Status='running';},r=>{r.State.Paused=true;},r=>{r.State.Running=0;},r=>{r.NetworkSettings.Networks['synthetic-network-'+nid].EndpointID='4'.repeat(64);},r=>{r.NetworkSettings.Networks['synthetic-network-'+nid].MacAddress=0;},r=>{r.NetworkSettings.Networks['synthetic-network-'+nid].IPPrefixLen=false;},r=>{r.NetworkSettings.Networks['synthetic-network-'+nid].NetworkID='not-a-full-id';}]){const changed=structuredClone(given);mutate(changed.containers[0]);assert.throws(()=>observer.baselineSnapshot(explicitTransport(changed.containers,changed.networks)),/M4_ENDPOINT_PROFILE_REFUSED/);assert.equal(capture().endpointProfile,adapter.PROFILE);}
 for(const mutate of [r=>{r.NetworkSettings.Networks['synthetic-network-'+nid].NetworkID='5'.repeat(64);},r=>{r.NetworkSettings.Networks['synthetic-network-'+nid].Aliases=['changed'];},r=>{r.NetworkSettings.Networks['synthetic-network-'+nid].UnknownStatic.preserved=1;},r=>{r.HostConfig.OomKillDisable=null;},r=>{r.Config.Unknown='changed';}]){const changed=structuredClone(given);mutate(changed.containers[0]);assert.throws(()=>observer.verifyBaseline(explicitTransport(changed.containers,changed.networks),before),/M4_BASELINE_CHANGED/);}
 const created=structuredClone(given);created.containers[0].State.Status='created';assert.equal(observer.baselineSnapshot(explicitTransport(created.containers,created.networks)).endpointProfile,adapter.PROFILE);
});
const shapesFile=process.env.NS_M4_BASELINE_SHAPES;
if(shapesFile)test('retained actual stopped/live State and NetworkSettings representatives pass actual adapter in synthetic complete envelopes',()=>{
 const observer=require('./custody-observer'),sample=JSON.parse(fs.readFileSync(shapesFile));
 const envelope=row=>({Created:'synthetic-created',Image:'sha256:'+'a'.repeat(64),Config:{Env:['SYNTHETIC_PRIVATE=value']},HostConfig:{OomKillDisable:false},Mounts:[],Id:row.Id,Name:row.Name,State:row.State,NetworkSettings:row.NetworkSettings});
 const containers=sample.containers.map(envelope),networks=sample.networks.map(row=>({Id:row.Id,Name:row.Name,Containers:row.Containers,UnknownStatic:'synthetic-envelope'}));
 const captured=observer.baselineSnapshot(explicitTransport(containers,networks));assert.equal(observer.verifyBaseline(explicitTransport(containers,networks),captured).endpointComparison.fullEquality,true);
 const stopped=sample.containers.find(row=>row.classification==='stopped-configured-not-live');assert(stopped);const index=containers.findIndex(row=>row.Id===stopped.Id);
 for(const mutate of [r=>{r.State.Running=true;},r=>{Object.values(r.NetworkSettings.Networks)[0].EndpointID='4'.repeat(64);},r=>{Object.values(r.NetworkSettings.Networks)[0].MacAddress=1;}]){const changed=structuredClone(containers);mutate(changed[index]);assert.throws(()=>observer.baselineSnapshot(explicitTransport(changed,networks)),/M4_ENDPOINT_PROFILE_REFUSED/);}
 const staticChange=structuredClone(containers);Object.values(staticChange[index].NetworkSettings.Networks)[0].UnknownStatic='drift';assert.throws(()=>observer.verifyBaseline(explicitTransport(staticChange,networks),captured),/M4_BASELINE_CHANGED/);
 // Retained State/NetworkSettings + selected live map only are ACTUAL; all
 // Config/HostConfig/creation/image/mount envelopes are explicitly synthetic.
});
test('inactive orphan configuration remains exact without inventing a global network or mutation handle',()=>{
 const observer=require('./custody-observer'),given=stoppedRows();given.networks=[];const commands=[],invoke=explicitTransport(given.containers,given.networks),capture=()=>observer.baselineSnapshot(args=>{commands.push(args);return invoke(args);}),before=capture();
 assert.equal(before.ids.networks.length,0);assert.equal(Object.keys(before.identities.networks).length,0);assert.equal(Object.keys(before.endpointMaps).length,0);assert(!commands.some(args=>args.includes(nid)),'M4_ORPHAN_REFERENCE_MUST_NOT_BECOME_DOCKER_HANDLE');
 const path=require('node:path'),os=require('node:os'),custody=require('./custody'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'m4-orphan-authority-'));let mutations=0;
 try{const dockerConfig=path.join(temporary,'docker');fs.mkdirSync(dockerConfig);const plan={version:1,status:'PARENT_BOUND',profile:custody.PROFILE,ownerUUID:'44444444-4444-4444-8444-444444444444',dockerExecutable:'/usr/bin/docker',dockerConfig,endpointProfile:adapter.PROFILE,baseline:before.ids,images:Object.fromEntries(['client','mongo','postgres','vault'].map(kind=>[kind,'sha256:'+'a'.repeat(64)]))};const controller=custody.create({plan,directory:path.join(temporary,'custody'),invoke:()=>{mutations++;throw new Error('unexpected mutation');}});assert.throws(()=>controller.remove(nid),/CUSTODY_UNKNOWN_OR_UNJOURNALED_ID/);assert.throws(()=>controller.read(['network','rm',nid]),/CUSTODY_READ_COMMAND/);assert.equal(mutations,0);}finally{fs.rmSync(temporary,{recursive:true,force:true});}

 assert.equal(observer.verifyBaseline(invoke,before).endpointComparison.fullEquality,true);
 for(const mutate of [r=>{r.State.Running=true;},r=>{r.State.Status='running';},r=>{r.State.Dead=true;},r=>{r.NetworkSettings.Networks['synthetic-network-'+nid].EndpointID='4'.repeat(64);},r=>{r.NetworkSettings.Networks['synthetic-network-'+nid].MacAddress=false;},r=>{r.NetworkSettings.Networks['synthetic-network-'+nid].NetworkID='not-a-full-id';}]){const changed=structuredClone(given);mutate(changed.containers[0]);assert.throws(()=>observer.baselineSnapshot(explicitTransport(changed.containers,changed.networks)),/M4_ENDPOINT_PROFILE_REFUSED/);}
 const changed=structuredClone(given);changed.containers[0].NetworkSettings.Networks['synthetic-network-'+nid].Aliases=['drift'];assert.throws(()=>observer.verifyBaseline(explicitTransport(changed.containers,changed.networks),before),/M4_BASELINE_CHANGED/);
 assert.throws(()=>observer.verifyBaseline(explicitTransport(given.containers,[{Id:nid,Name:'synthetic-network-'+nid,Containers:{}}]),before),/M4_BASELINE_CHANGED/);
});
const orphanFile=process.env.NS_M4_ORPHAN_SHAPE;
if(orphanFile)test('retained actual orphan State/NetworkSettings replay through adapter without a partial-baseline acceptance claim',()=>{
 const observer=require('./custody-observer'),sample=JSON.parse(fs.readFileSync(orphanFile));assert.equal(Object.keys(sample.globalEndpoints).length,0);const row={Id:sample.Id,Name:sample.Name,State:sample.State,NetworkSettings:sample.NetworkSettings,Created:'synthetic-created',Image:'sha256:'+'a'.repeat(64),Config:{Env:['SYNTHETIC_PRIVATE=value']},HostConfig:{OomKillDisable:false},Mounts:[]};
 const captured=observer.baselineSnapshot(explicitTransport([row],[]));assert.equal(captured.ids.networks.length,0);assert.equal(observer.verifyBaseline(explicitTransport([row],[]),captured).endpointComparison.fullEquality,true);
 for(const mutate of [r=>{r.State.Running=true;},r=>{Object.values(r.NetworkSettings.Networks)[0].EndpointID='4'.repeat(64);},r=>{Object.values(r.NetworkSettings.Networks)[0].IPPrefixLen=false;}]){const changed=structuredClone(row);mutate(changed);assert.throws(()=>observer.baselineSnapshot(explicitTransport([changed],[])),/M4_ENDPOINT_PROFILE_REFUSED/);}
 const changed=structuredClone(row);Object.values(changed.NetworkSettings.Networks)[0].UnknownStatic='drift';assert.throws(()=>observer.verifyBaseline(explicitTransport([changed],[]),captured),/M4_BASELINE_CHANGED/);
 // ACTUAL sanitized State/NetworkSettings and missing referenced global network;
 // other fields/universe are synthetic, NOT a replacement for the full baseline.
});
