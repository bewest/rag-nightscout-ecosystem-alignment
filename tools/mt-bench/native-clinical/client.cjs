'use strict';
// Trusted synthetic HTTP/stock-Socket.IO client only. No Docker/PG/Vault module,
// shell, environment loader, worker ticket or admission installer is imported.
const fs=require('node:fs'),path=require('node:path'),net=require('node:net'),crypto=require('node:crypto');
const accounting=require('../m7-joined/probe-accounting.cjs');
const UUID=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const need=(ok,code)=>{if(!ok)throw Object.assign(Error(code),{code});};
const monotonic=()=>process.hrtime.bigint().toString();
function validate(spec){
 need(spec&&spec.version===1&&spec.kind==='native-clinical-http-client','CLIENT_SPEC');
 need(Array.isArray(spec.ids)&&spec.ids.length===16&&new Set(spec.ids).size===16&&spec.ids.every(x=>UUID.test(x)),'CLIENT_ROSTER');
 need(/^m7-native-[a-f0-9]{16,32}$/.test(spec.runId)&&/^[a-f0-9]{32}$/.test(spec.nonce),'CLIENT_NONCE');
 need(Object.keys(spec.endpoints).sort().join(',')==='admin,api,api-2,socket-edge','CLIENT_ENDPOINTS');
 for(const row of Object.values(spec.endpoints)){
  const url=new URL(row.origin);need(url.protocol==='http:'&&net.isIP(url.hostname)===4&&!url.username&&!url.password&&url.pathname==='/'&&!url.search&&!url.hash,'CLIENT_ENDPOINT');
  const a=url.hostname.split('.').map(Number);need(a[0]===10||a[0]===172&&a[1]>=16&&a[1]<=31||a[0]===192&&a[1]===168,'CLIENT_ENDPOINT');
  need(/^[a-f0-9]{64}$/.test(row.cid)&&typeof row.startedAt==='string'&&row.startedAt.length>0,'CLIENT_CUSTODY');
 }
 need(spec.maximumRequests===8192&&spec.maximumSockets===16&&spec.maximumHttpBytes===268435456&&spec.maximumWallMs===1200000,'CLIENT_BOUNDS');
}
function create(spec,{prime,io,persist,now=Date.now,mono=monotonic,delay=ms=>new Promise(r=>setTimeout(r,ms))}){
 validate(spec);const start=now(),ledgers={},receiptPages=new Map(),sockets=new Map();let requests=0,recordedResponses=0,bytes=0,socketBytes=0,socketBudgetRefused=false,closed=false;
 for(const field of ['entries','devicestatus','treatments','probe'])ledgers[field]=accounting.create({ids:spec.ids,runId:spec.runId,persist:value=>persist('ledger-'+field+'.json',value)});
 const check=()=>need(!closed&&now()-start<spec.maximumWallMs&&!socketBudgetRefused,'CLIENT_CLOSED_OR_DEADLINE');
 // Observe stock Engine.IO packets without replacing its parser/protocol.
 // The websocket implementation also receives a fixed one-MiB maxPayload.
 function stockSocket(url,options){
  check();const socket=io(url,options),engine=socket.io?.engine;
  need(engine&&typeof engine.on==='function','CLIENT_STOCK_ENGINE_UNOBSERVED');
  engine.on('packet',packet=>{const data=packet?.data;const size=data===undefined?0:Buffer.isBuffer(data)?data.length:Buffer.byteLength(typeof data==='string'?data:JSON.stringify(data));socketBytes+=size;
   if(size>1048576||socketBytes>268435456){socketBudgetRefused=true;socket.emit('connect_error',Error('CLIENT_SOCKET_BYTE_BUDGET'));socket.close();}
  });return socket;
 }
 const credential=id=>{need(spec.ids.includes(id),'CLIENT_TENANT');const row=spec.credentials.find(x=>x.id===id);need(row&&typeof row.host==='string'&&typeof row.dataToken==='string'&&typeof row.rootHash==='string','CLIENT_CREDENTIAL');return row;};
 async function request(id,service,route,options={}){
  check();need(++requests<=spec.maximumRequests,'CLIENT_REQUEST_BUDGET');const sequence=requests;need(['api','api-2'].includes(service),'CLIENT_API_TARGET');const c=credential(id),begin=mono();let result;
  try{result=await prime.request(spec.endpoints[service].origin,route,{...options,headers:{host:c.host,'api-secret':c.dataToken,...options.headers},timeoutMs:5000});}
  catch{result={status:0,body:null};}
  bytes+=Buffer.byteLength(JSON.stringify(result.body));need(bytes<=spec.maximumHttpBytes,'CLIENT_BYTE_BUDGET');
  const receipt={sequence,accounting:options.instrumentAccounting||null,tenant:id,service,method:options.method||'GET',route,status:result.status,startedMonotonicNs:begin,finishedMonotonicNs:mono(),bodyBytes:Buffer.byteLength(JSON.stringify(result.body)),syntheticRequestSha256:options.body===undefined?null:crypto.createHash('sha256').update(JSON.stringify(options.body)).digest('hex'),documentDate:options.body?.date??null,errorCode:typeof result.body?.error==='string'&&/^[A-Z_]{1,100}$/.test(result.body.error)?result.body.error:null};const page=Math.floor((sequence-1)/64)+1,key='http-receipts-'+String(page).padStart(4,'0')+'.json';const rows=receiptPages.get(page)||[];rows.push(receipt);rows.sort((a,b)=>a.sequence-b.sequence);receiptPages.set(page,rows);recordedResponses++;persist(key,rows);persist('http-receipt-index.json',{requestsBegun:requests,responsesRecorded:recordedResponses,pages:Math.ceil(requests/64),rawStatusesPreserved:true,complete:recordedResponses===requests});return result;
 }
 async function write(id,field,service='api-2',documentDate=now()){
  need(Object.hasOwn(ledgers,field),'CLIENT_COLLECTION');check();const attempt=ledgers[field].begin(id),index=spec.ids.indexOf(id),date=documentDate,identifier=crypto.randomUUID();let status=0;
  const collection=field==='probe'?'entries':field;
  const body=collection==='entries'?{identifier,type:'sgv',sgv:210+index,utcOffset:0,date,dateString:new Date(date).toISOString(),device:spec.runId+(field==='probe'?'-probe':'')}:
   collection==='devicestatus'?{identifier,created_at:new Date(date).toISOString(),device:spec.runId}:
   {identifier,eventType:'Note',created_at:new Date(date).toISOString(),enteredBy:spec.runId,notes:'synthetic admission'};
  try{status=(await request(id,service,'/api/v3/'+collection,{method:'POST',body,instrumentAccounting:{collection:field,attempt}})).status;}
  finally{
   // Preserve the raw status in the receipt. The reused accountant represents
   // accepted with 200; this explicit adapter also accepts API3's 201 creation.
   ledgers[field].settle(attempt,status===201?200:status);
  }
  return {status,identifier,date,sgv:210+index};
 }
 async function history(){const anchor=now();let accepted=0;for(let index=0;index<288;index++){const date=anchor-(288-index)*300000;for(let offset=0;offset<16;offset+=4){const results=await Promise.all(spec.ids.slice(offset,offset+4).map(id=>write(id,'entries','api-2',date)));accepted+=results.filter(x=>x.status===200||x.status===201).length;}}return{kind:'source-bounded-synthetic-history',tenants:16,attempted:4608,accepted,cadenceMs:300000,firstDate:anchor-86400000,lastDate:anchor-300000,marker:spec.runId,scope:'one day of SGVs for source property-loader horizon and bgnow/delta history; no dosing data'};}
 async function clinical(){const observations=[];for(const tenant of spec.ids){const r=await request(tenant,'api-2','/api/v2/properties/bgnow,delta');observations.push({tenant,status:r.status,bgnowMean:r.body?.bgnow?.mean,bgnowMills:r.body?.bgnow?.mills,deltaMgdl:r.body?.delta?.mgdl,deltaRecent:r.body?.delta?.times?.recent,deltaPrevious:r.body?.delta?.times?.previous,observedAt:now(),scope:'actual API clinical properties, not evaluator-specific availability'});}return observations;}
 async function firstTouchStorm(){
  const begin=mono(),results=[],socketResults=[];
  for(let round=0;round<24;round++){
   for(let offset=0;offset<spec.ids.length;offset+=4)results.push(...await Promise.all(spec.ids.slice(offset,offset+4).map(async id=>{const r=await request(id,'api-2','/api/v3/entries');return{tenant:id,status:r.status,warming:r.body?.error==='TENANT_WARMING'};})));
   if(round!==23)await delay(250);
  }
  // Fixed four-at-a-time stock sockets, no hand-written Engine.IO protocol.
  const u=new URL(spec.endpoints['socket-edge'].origin);
  for(let offset=0;offset<spec.ids.length;offset+=4)socketResults.push(...await Promise.all(spec.ids.slice(offset,offset+4).map(async id=>{
   const c=credential(id),agent=new(require('node:http').Agent)({lookup:(host,options,done)=>options?.all?done(null,[{address:u.hostname,family:4}]):done(null,u.hostname,4)}),socket=stockSocket('http://'+c.host+':'+u.port,{agent,forceNew:true,transports:['websocket'],upgrade:false,reconnection:false,maxPayload:1048576,perMessageDeflate:false,timeout:1000});let frames=0,errors=0;
   socket.on('connect',()=>socket.emit('authorize',{secret:c.rootHash}));socket.on('dataUpdate',()=>frames++);socket.on('connect_error',()=>errors++);
   try{const deadline=now()+1500;while(now()<deadline&&!frames&&!errors)await delay(25);return{tenant:id,frames,errors};}finally{socket.close();agent.destroy();}
  })));
  return {kind:'first-touch-http-stock-socket-storm',startedMonotonicNs:begin,finishedMonotonicNs:mono(),results,socketResults,warmingReplies:results.filter(x=>x.warming).length,coldReadinessClaim:'fresh controlled process cohort; source ACK high-water and actual warming observations required'};
 }

 async function connect(id,transport='websocket'){
  check();need(sockets.size<spec.maximumSockets&&!sockets.has(id)&&['websocket','polling'].includes(transport),'CLIENT_SOCKET_BUDGET');const c=credential(id),u=new URL(spec.endpoints['socket-edge'].origin);
  const agent=new(require('node:http').Agent)({keepAlive:true,lookup:(hostname,options,done)=>options?.all?done(null,[{address:u.hostname,family:4}]):done(null,u.hostname,4)});
  const socket=stockSocket('http://'+c.host+':'+u.port,{agent,forceNew:true,transports:[transport],upgrade:false,reconnection:false,maxPayload:1048576,perMessageDeflate:false,timeout:5000});const state={id,transport,agent,socket,connections:0,frames:[],totalFrames:0,foreignFrames:0,errors:0};sockets.set(id,state);
  socket.on('connect',()=>{state.connections++;socket.emit('authorize',{secret:c.rootHash});});
  socket.on('connect_error',()=>state.errors++);
  socket.on('dataUpdate',frame=>{if(!Array.isArray(frame?.sgvs)||frame.sgvs.length>512||++state.totalFrames>8192){state.errors++;socket.close();return;}const points=frame.sgvs.map(x=>({mgdl:x.mgdl,mills:x.mills}));if(points.some(x=>x.mgdl>=210&&x.mgdl<226&&x.mgdl!==210+spec.ids.indexOf(id)))state.foreignFrames++;state.frames.push({sequence:state.totalFrames,receivedMonotonicNs:mono(),sgvs:points,hash:crypto.createHash('sha256').update(JSON.stringify(frame)).digest('hex')});if(state.frames.length>128)state.frames.shift();});
  const deadline=now()+15000;while(now()<deadline&&(!socket.connected||!state.frames.length)&&state.errors===0)await delay(50);
  need(socket.connected&&state.connections===1&&state.frames.length>0,'CLIENT_SOCKET_NOT_OBSERVED');return socketState(id);
 }
 function socketState(id){const s=sockets.get(id);need(s,'CLIENT_SOCKET_MISSING');return {socketId:s.socket.id,connected:s.socket.connected,connections:s.connections,transport:s.transport,frames:s.totalFrames,errors:s.errors};}
 async function healthyB(id){
  const s=sockets.get(id);need(s&&s.socket.connected,'CLIENT_SOCKET_MISSING');const socketId=s.socket.id,from=s.totalFrames,read=await request(id,'api-2','/api/v3/entries'),writeResult=await write(id,'entries');
  const deadline=now()+15000;while(now()<deadline&&!s.frames.filter(f=>f.sequence>from).some(f=>f.sgvs.some(x=>x.mgdl===writeResult.sgv&&x.mills===writeResult.date)))await delay(50);
  const ownFrameAfterWrite=s.frames.filter(f=>f.sequence>from).some(f=>f.sgvs.some(x=>x.mgdl===writeResult.sgv&&x.mills===writeResult.date));
  need(s.socket.id===socketId&&s.connections===1&&s.errors===0,'CLIENT_HEALTHY_B_RECONNECT');
  return {...socketState(id),readStatus:read.status,writeStatus:writeResult.status,ownFrameAfterWrite,foreignFrames:s.foreignFrames,requestToFrameClock:'producer-local-monotonic; exact DATA date matched in subsequent stock frame'};
 }
 async function isolation(a,b){
  need(a!==b,'CLIENT_ISOLATION_SELECTION');const ca=credential(a),cb=credential(b),positive=sockets.get(b);
  need(positive&&positive.socket.connected&&positive.totalFrames>0,'CLIENT_ISOLATION_POSITIVE_MISSING');
  const cross=await request(a,'api-2','/api/v3/entries',{headers:{host:cb.host,'api-secret':ca.dataToken}});
  const u=new URL(spec.endpoints['socket-edge'].origin),agent=new(require('node:http').Agent)({lookup:(host,options,done)=>options?.all?done(null,[{address:u.hostname,family:4}]):done(null,u.hostname,4)});
  const socket=stockSocket('http://'+cb.host+':'+u.port,{agent,forceNew:true,transports:['websocket'],upgrade:false,reconnection:false,maxPayload:1048576,perMessageDeflate:false,timeout:5000});
  let connected=false,explicitDisconnect=false,foreignFrames=0;
  socket.on('connect',()=>{connected=true;socket.emit('authorize',{secret:ca.rootHash});});
  socket.on('dataUpdate',()=>foreignFrames++);socket.on('disconnect',reason=>{explicitDisconnect=reason==='io server disconnect';});
  try{const deadline=now()+10000;while(now()<deadline&&!explicitDisconnect&&!foreignFrames)await delay(50);}
  finally{socket.close();agent.destroy();}
  // An observed explicit refusal plus a fresh authorized positive frame is the
  // discriminator. Silence or a timeout alone never proves socket isolation.
  const own=await healthyB(b);
  return {tenantA:a,tenantB:b,crossStatus:cross.status,crossAuthorizationRefused:[401,403,421].includes(cross.status),socketConnectedBeforeRefusal:connected,socketExplicitRefusal:explicitDisconnect,foreignFrames,positiveOwnFrame:own.ownFrameAfterWrite,scope:'bounded actual cross-credential DATA and stock root-socket refusal with authorized positive progression'};
 }

 function close(){need(!closed,'CLIENT_ALREADY_CLOSED');closed=true;let failure;for(const ledger of Object.values(ledgers))try{ledger.close();}catch(error){failure=failure||error;}for(const s of sockets.values()){s.socket.close();s.agent.destroy();}if(failure)throw failure;return{admissionsClosed:true,requests,responseBytes:bytes,socketBytes,socketBudgetRefused,httpEvidence:{requestsBegun:requests,responsesRecorded:recordedResponses,pages:Math.ceil(requests/64),complete:recordedResponses===requests},ledgers:Object.fromEntries(Object.entries(ledgers).map(([k,v])=>[k,v.snapshot()]))};}
 function rebind(endpoints){check();validate({...spec,endpoints});spec.endpoints=endpoints;return{endpointsBound:true};}
 return {request,write,history,clinical,firstTouchStorm,connect,socketState,healthyB,isolation,close,rebind};
}
module.exports={create,validate};
