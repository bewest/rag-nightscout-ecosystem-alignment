 'use strict';
// Setup-only discriminator. No mutations, ordinary workload, retries or cloud actors.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),http=require('node:http');
const {performance}=require('node:perf_hooks');
const wire=require('./serial-exchange-pair.cjs');
const SELECTION=Object.freeze({tenants:1000,stages:Object.freeze([0,4000,8000]),opensPerSecond:50,exchangesPerStage:64,maxElapsedMs:900000,requestTimeoutMs:10000,stockDeadlineMs:60000});
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const fail=code=>Object.assign(new Error(code),{code});
const need=(v,code)=>{if(!v)throw fail(code);};
const same=require('node:util').isDeepStrictEqual;
// Polling-XHR TransportError.description is a status or Error; context.statusText
// can be the Node system Error. Never retain messages, stacks or the XHR itself.
const CONNECT_KINDS=new Map([['xhr poll error','XHR_POLL_ERROR'],['xhr post error','XHR_POST_ERROR'],['timeout','TIMEOUT']]);
const CONNECT_CODES=new Set(['ECONNREFUSED','ECONNRESET','ECONNABORTED','ETIMEDOUT','EPIPE','ENOTFOUND','EAI_AGAIN','EMFILE','ENFILE','ENOBUFS','ENOMEM','EADDRNOTAVAIL','ENETUNREACH','EHOSTUNREACH']);
const CONNECT_GROUP_LIMIT=16;
function safeConnectError(error){
 const code=[error?.code,error?.description?.code,error?.context?.statusText?.code].find(value=>typeof value==='string'&&CONNECT_CODES.has(value))||null;
 const status=[error?.description,error?.context?.status].find(value=>Number.isInteger(value)&&(value===0||value>=100&&value<=599));
 return {transport:'polling',kind:CONNECT_KINDS.get(error?.message)||'OTHER',code,status:status??null};
}
function captureConnectError(summary,error){
 const diagnostic=safeConnectError(error);
 const group=summary.groups.find(g=>g.transport===diagnostic.transport&&g.kind===diagnostic.kind&&g.code===diagnostic.code&&g.status===diagnostic.status);
 const increment=value=>Math.min(Number.MAX_SAFE_INTEGER,value+1);
 summary.total=increment(summary.total);
 if(group)group.count=increment(group.count);
 else if(summary.groups.length<CONNECT_GROUP_LIMIT)summary.groups.push({...diagnostic,count:1});
 else summary.other=increment(summary.other);
}
function load(bindingPath,bindingSha256){
 need(path.isAbsolute(bindingPath)&&/^[a-f0-9]{64}$/.test(bindingSha256),'M7_ADMISSION_BINDING');
 let raw;try{raw=fs.readFileSync(bindingPath);}catch{throw fail('M7_ADMISSION_BINDING');}
 need(raw.length<=8192&&hash(raw)===bindingSha256,'M7_ADMISSION_BINDING');
 let b;try{b=JSON.parse(raw);}catch{throw fail('M7_ADMISSION_BINDING');}
 need(b?.version===1&&b.kind==='m7-admission-stages-v1'&&same(b.selection,SELECTION),'M7_ADMISSION_SELECTION');
 for(const k of ['fixtureDirectory','outputDirectory','nodeExecutable','generatorRoot'])need(typeof b[k]==='string'&&path.isAbsolute(b[k]),'M7_ADMISSION_PATH');
 need(/^[a-f0-9]{32}$/.test(b.owner)&&/^[a-f0-9]{40}$/.test(b.pair?.core)&&/^[a-f0-9]{40}$/.test(b.pair?.deploy)&&/^sha256:[a-f0-9]{64}$/.test(b.imageId)&&/^[a-f0-9]{64}$/.test(b.instrument),'M7_ADMISSION_SOURCE');
 for(const k of ['ownerSha256','tenantsSha256','actorSha256','serialActorSha256','nodeSha256','socketPackageSha256'])need(/^[a-f0-9]{64}$/.test(b[k]),'M7_ADMISSION_HASH');
 let base;try{base=new URL(b.baseUrl);}catch{throw fail('M7_ADMISSION_LOOPBACK');}
 need(base.protocol==='http:'&&base.hostname==='127.0.0.1'&&!base.username&&!base.password&&base.pathname==='/'&&!base.search&&!base.hash&&/^[0-9]+$/.test(base.port)&&Number(base.port)>=1024,'M7_ADMISSION_LOOPBACK');
 const fileHash=file=>{try{return hash(fs.readFileSync(file));}catch{throw fail('M7_ADMISSION_INPUT_UNAVAILABLE');}};
 need(fileHash(__filename)===b.actorSha256&&fileHash(require.resolve('./serial-exchange-pair.cjs'))===b.serialActorSha256&&fs.realpathSync(b.nodeExecutable)===fs.realpathSync(process.execPath)&&fileHash(process.execPath)===b.nodeSha256,'M7_ADMISSION_ACTOR');
 const ownerPath=path.join(b.fixtureDirectory,'owner.json'),tenantsPath=path.join(b.fixtureDirectory,'tenants.private.json');
 need(fileHash(ownerPath)===b.ownerSha256&&fileHash(tenantsPath)===b.tenantsSha256,'M7_ADMISSION_INPUT_CHANGED');
 const m=JSON.parse(fs.readFileSync(ownerPath)),tenants=JSON.parse(fs.readFileSync(tenantsPath));
 need(m.owner===b.owner&&same(m.pair,b.pair)&&m.imageId===b.imageId&&m.instrument?.sha256===b.instrument&&m.tenants===1000&&m.runPurpose==='discovery'&&m.profile==='pgstream-sample','M7_ADMISSION_SOURCE');
 need(Array.isArray(tenants)&&tenants.length===1000&&new Set(tenants.map(t=>t.id)).size===1000&&tenants.every(t=>typeof t.id==='string'&&/^[a-f0-9-]{36}$/.test(t.id)&&typeof t.host==='string'&&/^[a-z0-9.-]{1,253}$/.test(t.host)&&typeof t.token==='string'&&t.token.length>0&&t.token.length<=8192),'M7_ADMISSION_ROSTER');
 need(fileHash(path.join(b.generatorRoot,'node_modules/socket.io-client/package.json'))===b.socketPackageSha256,'M7_ADMISSION_SOCKET_DEPENDENCY');
 need(typeof b.deadlineUtc==='string'&&Number.isFinite(Date.parse(b.deadlineUtc)),'M7_ADMISSION_DEADLINE');
 return {b,base,tenants};
}
function privateRequestOnce(options,timeoutMs,agent){
 return new Promise(resolve=>{
  let done=false,timer,req;const finish=value=>{if(done)return;done=true;clearTimeout(timer);resolve(value);};
  try{
   req=http.request({...options,agent},res=>{
    let body='',bytes=0,oversize=false;
    res.on('data',chunk=>{bytes+=chunk.length;if(bytes<=16384)body+=chunk.toString('utf8');else{oversize=true;body='';}});
    res.on('end',()=>finish({status:res.statusCode,headers:res.headers,body,oversize}));
    res.on('error',()=>finish({status:0,transport:'RESPONSE_TRANSPORT_ERROR'}));
   });
   req.on('error',()=>finish({status:0,transport:'REQUEST_TRANSPORT_ERROR'}));
   timer=setTimeout(()=>{finish({status:0,transport:'REQUEST_TIMEOUT'});req.destroy();},timeoutMs);req.end();
  }catch{finish({status:0,transport:'REQUEST_TRANSPORT_ERROR'});}
 });
}
async function run({bindingPath,bindingSha256,ioFactory,requestOnce=wire.requestOnce,viewerRequest=privateRequestOnce,clock=Date.now,monotonic=()=>performance.now(),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms)),persist,snapshot}){
 const {b,base,tenants}=load(bindingPath,bindingSha256),startedAtMs=clock(),began=monotonic();
 need(Date.parse(b.deadlineUtc)>startedAtMs,'M7_ADMISSION_DEADLINE');
 const budget=Math.min(SELECTION.maxElapsedMs,Date.parse(b.deadlineUtc)-startedAtMs),sockets=[],agents=[],activeRequests=new Set();let stopping=false,timer,stage=null,terminal=null;
 const observation={version:1,kind:b.kind,bindingSha256,owner:b.owner,pair:b.pair,imageId:b.imageId,instrument:b.instrument,selection:SELECTION,clockDomain:'single-driver-performance-now',startedAtMs,stages:[],status:'RUNNING',ordinaryTraffic:'NOT_RUN',sparseWrites:'NOT_RUN',mutations:0,requestRetries:0,connectErrors:{total:0,groups:[],other:0},viewerSetup:{attempts:0,pending:0,responses:0,accepted:0,refused:0,transport:0,retries:0},scope:'stock polling callback availability and setup admission; clinical output/content equivalence UNMEASURED'};
 const outputFile=path.join(b.outputDirectory,'admission-stages.json');
 const publish=persist||((value)=>{fs.mkdirSync(b.outputDirectory,{recursive:true,mode:0o700});const bytes=JSON.stringify(value)+'\n';need(Buffer.byteLength(bytes)<=4194304,'M7_ADMISSION_CAPTURE_BOUND');fs.writeFileSync(outputFile+'.partial',bytes,{mode:0o600});fs.renameSync(outputFile+'.partial',outputFile);});
 const state=()=>({...observation,viewerWitnesses:sockets.map(s=>({viewer:s.viewer,tenantIndex:s.tenantIndex,connects:s.connects,callbacks:s.callbacks,firstCallbackMonoMs:s.firstCallbackMonoMs,firstFrameDigest:s.firstFrameDigest,connected:s.connected,connectError:s.connectError,disconnects:s.disconnects}))});
 const save=()=>publish(state());
 const remaining=()=>budget-(monotonic()-began);
 const ensure=()=>{if(remaining()<=0)throw fail('M7_ADMISSION_DEADLINE');if(terminal)throw fail(terminal);};
 const lookup=(host,options,callback)=>options?.all?callback(null,[{address:'127.0.0.1',family:4}]):callback(null,'127.0.0.1',4);
 const socketAgent=new http.Agent({keepAlive:true,lookup}),requestAgent=new http.Agent({keepAlive:true,maxSockets:1,maxFreeSockets:1});agents.push(socketAgent,requestAgent);
 for(const agent of agents){const add=agent.addRequest.bind(agent);agent.addRequest=(req,opts)=>{if(stopping){queueMicrotask(()=>req.destroy(fail('M7_ADMISSION_STOPPED')));return;}activeRequests.add(req);req.once('close',()=>activeRequests.delete(req));return add(req,opts);};}
 const io=ioFactory||require(path.join(b.generatorRoot,'node_modules/socket.io-client')).io;
 async function exchangePhase(){
  const records=[];
  for(let tenantIndex=0;tenantIndex<SELECTION.exchangesPerStage;tenantIndex++){
   ensure();const t=tenants[tenantIndex],start=monotonic(),timeoutMs=Math.min(SELECTION.requestTimeoutMs,remaining());
   const response=await requestOnce({hostname:base.hostname,port:base.port,method:'GET',path:'/api/v2/authorization/request/'+encodeURIComponent(t.token),headers:{Host:t.host,Accept:'application/json'}},timeoutMs,requestAgent);
   const status=Number.isInteger(response?.status)&&response.status>=0&&response.status<=599?response.status:0;
   const safe=status>0?wire.safeResponse({...response,status}):{errorCode:null,bodyObservation:'NO_HTTP_RESPONSE',retryAfterSeconds:null};
   records.push({tenantIndex,ordinal:tenantIndex+1,status,...safe,elapsedMs:monotonic()-start,timeoutMs,retries:0});stage.exchanges=records;save();
   if(status!==200)throw fail(status===0?'M7_ADMISSION_EXCHANGE_TRANSPORT':'M7_ADMISSION_EXCHANGE_REFUSED');
  }
  return records;
 }
 // The existing safe requestOnce discards successful bodies. Viewer JWT issue
 // uses a separate bounded private-memory request; it has no log/body persistence.
 async function viewerToken(t,tenantIndex){
  ensure();const timeoutMs=Math.min(SELECTION.requestTimeoutMs,remaining()),start=monotonic();
  observation.viewerSetup.attempts++;observation.viewerSetup.pending++;
  const response=await viewerRequest({hostname:base.hostname,port:base.port,method:'GET',path:'/api/v2/authorization/request/'+encodeURIComponent(t.token),headers:{Host:t.host,Accept:'application/json'}},timeoutMs,requestAgent);
  const status=Number.isInteger(response?.status)?response.status:0;observation.viewerSetup.pending--;if(status>0)observation.viewerSetup.responses++;else observation.viewerSetup.transport++;if(status===200)observation.viewerSetup.accepted++;else observation.viewerSetup.refused++;
  if(status!==200){stage.viewerExchangeRefusal={tenantIndex,status,...(status>0?wire.safeResponse(response):{errorCode:null,bodyObservation:'NO_HTTP_RESPONSE',retryAfterSeconds:null}),elapsedMs:monotonic()-start};save();throw fail('M7_ADMISSION_VIEWER_EXCHANGE_REFUSED');}
  let body;try{body=JSON.parse(response.body);}catch{throw fail('M7_ADMISSION_JWT_BODY');}need(typeof body.token==='string'&&body.token.length>0&&body.token.length<=8192,'M7_ADMISSION_JWT_BODY');return body.token;
 }
 async function checkpoints(point){if(snapshot)try{await snapshot({stage:stage.viewers,point,remainingMs:remaining()});}catch{stage.observer='UNMEASURED';save();}}
 save();
 try{
  return await Promise.race([(async()=>{
   const tokens=new Map();let nextOpen=monotonic();
   for(const total of SELECTION.stages){
    ensure();stage={viewers:total,status:'RUNNING',observer:'UNMEASURED',observer:snapshot?'EXTERNAL_SEGMENT_NOT_ASSESSED':'UNMEASURED',startedMonoMs:monotonic(),exchanges:[]};observation.stages.push(stage);save();await checkpoints('before');
    while(sockets.length<total){
     ensure();const viewer=sockets.length,tenantIndex=viewer%tenants.length,t=tenants[tenantIndex];
     if(!tokens.has(tenantIndex))tokens.set(tenantIndex,await viewerToken(t,tenantIndex));
     const wait=nextOpen-monotonic();if(wait>0)await sleep(Math.min(wait,remaining()));ensure();
     const cell={viewer,tenantIndex,connects:0,callbacks:0,firstCallbackMonoMs:null,firstFrameDigest:null,connected:false,connectError:false,disconnects:0};
     cell.socket=io('http://'+t.host+':'+base.port,{transports:['polling'],agent:socketAgent,reconnection:false,timeout:Math.min(10000,remaining())});
     cell.socket.on('connect',()=>{cell.connects++;cell.connected=true;cell.socket.emit('authorize',{client:'web',token:tokens.get(tenantIndex),history:1,status:true},()=>{});});
     cell.socket.on('connect_error',error=>{cell.connectError=true;if(!stopping){captureConnectError(observation.connectErrors,error);terminal='M7_ADMISSION_STOCK_CONNECT_FAILED';}});
     cell.socket.on('disconnect',()=>{cell.connected=false;cell.disconnects++;if(!stopping)terminal='M7_ADMISSION_STOCK_DISCONNECTED';});
     cell.socket.on('dataUpdate',frame=>{
      if(stopping)return;
      const sgvs=frame?.sgvs;
      if(!Array.isArray(sgvs)||sgvs.length<1||sgvs.length>10000||sgvs.some(x=>typeof x?._id!=='string'||x._id.length>64||!Number.isFinite(x.mills)||!Number.isFinite(x.mgdl)))return;
      cell.callbacks++;
      if(cell.firstCallbackMonoMs===null){cell.firstCallbackMonoMs=monotonic();cell.firstFrameDigest=hash(JSON.stringify(sgvs.map(x=>({_id:x._id,mills:x.mills,mgdl:x.mgdl}))));}
     });
     sockets.push(cell);nextOpen=Math.max(nextOpen,monotonic())+1000/SELECTION.opensPerSecond;
     if(sockets.length%50===0)save();
    }
    const primeUntil=Math.min(began+budget,monotonic()+SELECTION.stockDeadlineMs);
    while(sockets.some(s=>!s.connected||s.callbacks===0)){ensure();if(monotonic()>=primeUntil)throw fail('M7_ADMISSION_STOCK_CALLBACK_MISSING');await sleep(Math.min(50,remaining()));}
    stage.stock={requested:total,connected:sockets.filter(s=>s.connected).length,callbackWitnesses:sockets.filter(s=>s.callbacks>0).length};save();
    await checkpoints('primed');await exchangePhase();await checkpoints('after');ensure();stage.status='COMPLETE';stage.finishedMonoMs=monotonic();save();
   }
   observation.status='COMPLETE';observation.finishedAtMs=clock();observation.elapsedMs=monotonic()-began;save();return state();
  })(),new Promise((resolve,reject)=>{timer=setTimeout(()=>{terminal='M7_ADMISSION_DEADLINE';reject(fail(terminal));},budget);})]);
 }catch(error){observation.status='FAILED_PARTIAL';observation.failure={code:/^M7_ADMISSION_[A-Z_]+$/.test(error?.code||'')?error.code:'M7_ADMISSION_FAILED'};if(stage)stage.status='FAILED_PARTIAL';observation.elapsedMs=monotonic()-began;save();throw error;}
 finally{clearTimeout(timer);stopping=true;for(const req of activeRequests)req.destroy();for(const s of sockets)try{s.socket.close();}catch{}for(const agent of agents)agent.destroy();}
}
module.exports={SELECTION,load,run,privateRequestOnce};
if(require.main===module)run({bindingPath:process.argv[2],bindingSha256:process.argv[3]}).then(()=>console.log('M7_ADMISSION_STAGES_COMPLETE')).catch(error=>{console.error(/^M7_ADMISSION_[A-Z_]+$/.test(error?.code||'')?error.code:'M7_ADMISSION_FAILED');process.exitCode=1;});
