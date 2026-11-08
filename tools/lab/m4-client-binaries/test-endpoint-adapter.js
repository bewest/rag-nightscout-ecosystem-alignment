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
