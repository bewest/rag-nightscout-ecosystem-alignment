 'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto'),{EventEmitter}=require('node:events'),{spawnSync}=require('node:child_process');
const actor=require('./admission-stages.cjs'),hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
function fixture(){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'m7-admission-control-')),d=path.join(root,'fixture'),generatorRoot=path.join(root,'generator');fs.mkdirSync(d);fs.mkdirSync(path.join(generatorRoot,'node_modules/socket.io-client'),{recursive:true});fs.writeFileSync(path.join(generatorRoot,'node_modules/socket.io-client/package.json'),'{}');
 const owner={tenants:1000,owner:'a'.repeat(32),pair:{core:'b'.repeat(40),deploy:'c'.repeat(40)},imageId:'sha256:'+'d'.repeat(64),instrument:{sha256:'e'.repeat(64)},profile:'pgstream-sample',runPurpose:'discovery'};
 const tenants=Array.from({length:1000},(_,i)=>({id:'30000000-3333-4333-8333-'+i.toString(16).padStart(12,'0'),host:'tenant'+i+'.synthetic',token:'PRIVATE_CREDENTIAL_'+i}));
 fs.writeFileSync(path.join(d,'owner.json'),JSON.stringify(owner));fs.writeFileSync(path.join(d,'tenants.private.json'),JSON.stringify(tenants));
 const b={version:1,kind:'m7-admission-stages-v1',selection:actor.SELECTION,fixtureDirectory:d,outputDirectory:path.join(root,'out'),generatorRoot,nodeExecutable:process.execPath,owner:owner.owner,pair:owner.pair,imageId:owner.imageId,instrument:owner.instrument.sha256,baseUrl:'http://127.0.0.1:54173/',deadlineUtc:new Date(1000000+actor.SELECTION.maxElapsedMs).toISOString(),ownerSha256:hash(fs.readFileSync(path.join(d,'owner.json'))),tenantsSha256:hash(fs.readFileSync(path.join(d,'tenants.private.json'))),actorSha256:hash(fs.readFileSync(require.resolve('./admission-stages.cjs'))),serialActorSha256:hash(fs.readFileSync(require.resolve('./serial-exchange-pair.cjs'))),nodeSha256:hash(fs.readFileSync(process.execPath)),socketPackageSha256:hash(Buffer.from('{}'))};
 const file=path.join(root,'binding.json');const save=()=>{fs.writeFileSync(file,JSON.stringify(b));return hash(fs.readFileSync(file));};
 return {root,d,b,file,save,remove:()=>fs.rmSync(root,{recursive:true,force:true})};
}
async function simulated(f,{refuseAt,connectErrorAt,connectErrors=[Error('PRIVATE_ERROR')],missingCallbackAt,disconnectAt,deadlineMs,timeoutAt,observerFails=false}={}){
 let now=0,requests=0,viewerRequests=0,opened=0,closed=0,last=null,clockStart=1000000;const opens=[],stages=[],snapshots=[];
 if(deadlineMs!==undefined)f.b.deadlineUtc=new Date(clockStart+deadlineMs).toISOString();const bindingSha256=f.save();
 function io(url,options){
  assert.match(url,/^http:\/\/tenant\d+\.synthetic:54173$/);assert.deepEqual(options.transports,['polling']);assert.equal(options.reconnection,false);
  const ordinal=opened++,socket=new EventEmitter();opens.push(now);socket.close=()=>{closed++;socket.emit('disconnect','io client disconnect');};
  const emit=socket.emit.bind(socket);socket.emit=(name,...args)=>{if(name==='authorize'){assert.equal(args[0].client,'web');assert.equal(args[0].history,1);assert.equal(args[0].token,'PRIVATE_JWT');if(ordinal!==missingCallbackAt)queueMicrotask(()=>emit('dataUpdate',{sgvs:[{_id:'synthetic-stored',mills:1,mgdl:123}]}));return true;}return emit(name,...args);};
  queueMicrotask(()=>{if(ordinal===connectErrorAt){for(const error of connectErrors)emit('connect_error',error);}else{emit('connect');if(ordinal===disconnectAt)queueMicrotask(()=>emit('disconnect','transport close'));}});return socket;
 }
 const settings={bindingPath:f.file,bindingSha256,ioFactory:io,clock:()=>clockStart+now,monotonic:()=>now,sleep:async ms=>{now+=ms;await Promise.resolve();},requestOnce:async(options,timeout)=>{requests++;now+=1;assert.equal(options.method,'GET');assert.equal(options.hostname,'127.0.0.1');assert(timeout>0&&timeout<=10000);if(requests===refuseAt)return {status:503,headers:{'content-type':'application/json'},body:'{"error":"AUTHORITY_UNAVAILABLE","secret":"DO_NOT_SAVE"}'};if(requests===timeoutAt)return {status:0,transport:'REQUEST_TIMEOUT'};return {status:200,headers:{},body:''};},viewerRequest:async()=>{viewerRequests++;now+=1;return {status:200,headers:{},body:'{"token":"PRIVATE_JWT"}'};},persist:value=>{last=value;if(value.stages.length>stages.length)stages.push(value.stages.at(-1).viewers);},snapshot:async value=>{snapshots.push(value);if(observerFails)throw Error('observer unavailable');}};
 let value,error;try{value=await actor.run(settings);}catch(e){error=e;}
 return {value,error,last,opened,closed,requests,viewerRequests,opens,stages,snapshots,now};
}
test('exact source/config/hash preflight refuses mismatches before any driver work',()=>{
 const f=fixture();try{
  let digest=f.save();assert.equal(actor.load(f.file,digest).tenants.length,1000);
  for(const mutate of [()=>f.b.pair.core='f'.repeat(40),()=>f.b.selection={...actor.SELECTION,opensPerSecond:51},()=>f.b.actorSha256='0'.repeat(64),()=>f.b.baseUrl='http://example.com:54173/']){
   const original=structuredClone(f.b);mutate();digest=f.save();assert.throws(()=>actor.load(f.file,digest),/M7_ADMISSION_/);Object.assign(f.b,original);
  }
  digest=f.save();fs.appendFileSync(path.join(f.d,'owner.json'),' ');assert.throws(()=>actor.load(f.file,digest),/INPUT_CHANGED|SOURCE/);
 }finally{f.remove();}
});
test('fixed stages use actual stock callback hook, bounded50/s opens,192 no-retry probes and owned close',async()=>{
 const f=fixture();try{const r=await simulated(f);assert.ifError(r.error);assert.equal(r.value.status,'COMPLETE');assert.equal(r.requests,192);assert.equal(r.viewerRequests,1000);assert.equal(r.opened,8000);assert.equal(r.closed,8000);assert.deepEqual(r.stages,[0,4000,8000]);
  assert(r.opens.slice(1).every((t,i)=>t-r.opens[i]>=20),'new socket pacing caught up in an unbounded burst');assert.deepEqual(r.value.stages.map(s=>s.exchanges.length),[64,64,64]);assert.deepEqual(r.value.stages.map(s=>s.stock.callbackWitnesses),[0,4000,8000]);assert(r.value.viewerWitnesses.every(s=>s.callbacks===1&&s.connects===1&&/^[a-f0-9]{64}$/.test(s.firstFrameDigest)));assert.deepEqual(r.value.connectErrors,{total:0,groups:[],other:0});assert.equal(r.value.mutations,0);assert.deepEqual(r.value.viewerSetup,{attempts:1000,pending:0,responses:1000,accepted:1000,refused:0,transport:0,retries:0});assert.equal(r.value.ordinaryTraffic,'NOT_RUN');assert.equal(r.value.sparseWrites,'NOT_RUN');const raw=JSON.stringify(r.value);assert(!raw.includes('PRIVATE_JWT'));assert(!raw.includes('PRIVATE_CREDENTIAL'));assert(!raw.includes('synthetic-stored'));assert.equal(r.snapshots.length,9);
 }finally{f.remove();}
});
test('first unexpected exchange refusal retains successful segment, no retry, close all actors',async()=>{
 const f=fixture();try{const r=await simulated(f,{refuseAt:65});assert.equal(r.error.code,'M7_ADMISSION_EXCHANGE_REFUSED');assert.equal(r.requests,65);assert.equal(r.opened,4000);assert.equal(r.closed,4000);assert.equal(r.last.stages[0].status,'COMPLETE');assert.equal(r.last.stages[1].status,'FAILED_PARTIAL');assert.equal(r.last.stages[1].exchanges[0].errorCode,'AUTHORITY_UNAVAILABLE');assert(!JSON.stringify(r.last).includes('DO_NOT_SAVE'));}finally{f.remove();}
});
test('missing callback, first connect failure and disconnected viewer each fail actual availability',async()=>{
 for(const opts of [{missingCallbackAt:7},{connectErrorAt:7},{disconnectAt:7}]){
  const f=fixture();try{const r=await simulated(f,opts);assert(r.error);assert.match(r.error.code,/M7_ADMISSION_STOCK_/);assert.equal(r.last.stages[0].status,'COMPLETE');assert.equal(r.closed,r.opened);assert.equal(r.requests,64);assert.equal(r.last.status,'FAILED_PARTIAL');assert(!JSON.stringify(r.last).includes('PRIVATE_ERROR'));}finally{f.remove();}
 }
});
test('global elapsed cutoff and no-response stop without retries or erasing earlier stage',async()=>{
 let f=fixture();try{const r=await simulated(f,{deadlineMs:100});assert.equal(r.error.code,'M7_ADMISSION_DEADLINE');assert(r.now<=100);assert.equal(r.last.stages[0].status,'COMPLETE');assert.equal(r.closed,r.opened);}finally{f.remove();}
 f=fixture();try{const r=await simulated(f,{timeoutAt:65});assert.equal(r.error.code,'M7_ADMISSION_EXCHANGE_TRANSPORT');assert.equal(r.requests,65);assert.equal(r.last.stages[1].exchanges[0].status,0);assert.equal(r.last.stages[0].status,'COMPLETE');assert.equal(r.closed,r.opened);}finally{f.remove();}
});
test('optional stage observer failure remains explicitly unmeasured beside independent setup proof',async()=>{
 const f=fixture();try{const r=await simulated(f,{observerFails:true});assert.ifError(r.error);assert(r.value.stages.every(s=>s.observer==='UNMEASURED'));assert.equal(r.value.scope.includes('UNMEASURED'),true);}finally{f.remove();}
});
test('CLI refusal prints typed code without source paths or unsafe binding contents',()=>{
 const f=fixture();try{fs.writeFileSync(f.file,'PRIVATE_BINDING_SECRET');const p=spawnSync(process.execPath,[require.resolve('./admission-stages.cjs'),f.file,'0'.repeat(64)],{encoding:'utf8'});assert.notEqual(p.status,0);assert.match(p.stderr,/M7_ADMISSION_BINDING/);assert(!p.stderr.includes('PRIVATE_BINDING_SECRET'));assert(!p.stderr.includes(f.file));}finally{f.remove();}
});

test('private viewer request bounds successful body in RAM and retains no oversized body',async()=>{
 const http=require('node:http'),original=http.request;
 try{
  for(const bytes of ['{"token":"PRIVATE_JWT"}','x'.repeat(17000)]){
   http.request=(options,callback)=>{const req=new EventEmitter();req.end=()=>queueMicrotask(()=>{const res=new EventEmitter();res.statusCode=200;res.headers={'content-type':'application/json'};callback(res);res.emit('data',Buffer.from(bytes));res.emit('end');});req.destroy=()=>{};return req;};
   const value=await actor.privateRequestOnce({hostname:'127.0.0.1',port:54173},1000,{});assert.equal(value.status,200);assert.equal(value.oversize,bytes.length>16384);assert.equal(value.body,bytes.length>16384?'':bytes);
  }
 }finally{http.request=original;}
});

// Synthetic hostile fields exercise only the new projection, never a real credential.
test('connect failure retains polling category/system code/status without private error context',async()=>{
 const secret='PRIVATE_ERROR_CREDENTIAL_IDENTIFIER',url='https://private.invalid/?token='+secret;
 const error=Object.assign(Error('xhr poll error'),{type:'TransportError',description:0,context:{status:0,statusText:Object.assign(Error(secret),{code:'ECONNREFUSED',address:secret,port:1234}),responseText:secret,responseURL:url,getAllResponseHeaders:()=>secret},stack:secret,data:{token:secret},request:{url,headers:{Authorization:secret}},auth:secret});
 const f=fixture();try{
  const r=await simulated(f,{connectErrorAt:7,connectErrors:[error]});
  assert.equal(r.error.code,'M7_ADMISSION_STOCK_CONNECT_FAILED');assert.equal(r.requests,64);assert.equal(r.viewerRequests,9); // Existing async token request can start before queued connect_error is observed.
  assert.equal(r.opened,8);assert.equal(r.closed,8);
  assert.equal(r.last.stages[0].status,'COMPLETE');assert.equal(r.last.stages[1].status,'FAILED_PARTIAL');assert.equal(r.last.viewerWitnesses[7].connectError,true);
  assert.deepEqual(r.last.connectErrors,{total:1,groups:[{transport:'polling',kind:'XHR_POLL_ERROR',code:'ECONNREFUSED',status:0,count:1}],other:0});
  const raw=JSON.stringify(r.last);for(const value of [secret,url,'Authorization','responseText','statusText','PRIVATE_JWT','PRIVATE_CREDENTIAL','tenant7.synthetic'])assert(!raw.includes(value),value);
 }finally{f.remove();}
});
test('connect failure projection accepts only fixed codes/categories and valid primitive statuses',async()=>{
 const errors=[
  Object.assign(Error('PRIVATE_ERROR'),{code:'PRIVATE_CODE',description:{code:'PRIVATE_DESCRIPTION'},context:{status:'503',statusText:{code:'PRIVATE_CONTEXT'}}}),
  Object.assign(Error('xhr post error'),{description:503,context:{status:401}}),
  Object.assign(Error('timeout'),{code:'ETIMEDOUT',description:-24,context:{status:600}}),
  Object.assign(Error('PRIVATE_ERROR'),{description:Object.assign(Error('PRIVATE_ERROR'),{code:'EMFILE'}),context:{status:502}}),
  null,'PRIVATE_ERROR',Object.assign(Error('PRIVATE_ERROR'),{code:123,description:200.5,context:{status:NaN}})
 ];
 const f=fixture();try{
  const r=await simulated(f,{connectErrorAt:7,connectErrors:errors});
  assert.deepEqual(r.last.connectErrors,{total:7,groups:[
   {transport:'polling',kind:'OTHER',code:null,status:null,count:4},
   {transport:'polling',kind:'XHR_POST_ERROR',code:null,status:503,count:1},
   {transport:'polling',kind:'TIMEOUT',code:'ETIMEDOUT',status:null,count:1},
   {transport:'polling',kind:'OTHER',code:'EMFILE',status:502,count:1}
  ],other:0});
  assert(!JSON.stringify(r.last).includes('PRIVATE_'));
 }finally{f.remove();}
});
test('repeated connect errors keep fixed group capacity and count overflow without changing stop behavior',async()=>{
 const errors=Array.from({length:1000},(_,i)=>Object.assign(Error('xhr poll error'),{description:400+i%20}));
 const f=fixture();try{
  const r=await simulated(f,{connectErrorAt:7,connectErrors:errors});
  assert.equal(r.error.code,'M7_ADMISSION_STOCK_CONNECT_FAILED');assert.equal(r.opened,8);assert.equal(r.requests,64);assert.equal(r.closed,8);
  assert.equal(r.last.connectErrors.total,1000);assert.equal(r.last.connectErrors.groups.length,16);assert(r.last.connectErrors.groups.every(g=>g.count===50));assert.equal(r.last.connectErrors.other,200);
  assert(Buffer.byteLength(JSON.stringify(r.last.connectErrors))<2048);
 }finally{f.remove();}
});

test('installed polling client refused-loopback shape survives the driver projection',{skip:!process.env.M7_ADMISSION_CLIENT_ROOT},async()=>{
 const net=require('node:net'),{io}=require(path.join(process.env.M7_ADMISSION_CLIENT_ROOT,'node_modules/socket.io-client'));
 const server=net.createServer();let socket;
 try{
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});const port=server.address().port;
  await new Promise((resolve,reject)=>server.close(error=>error?reject(error):resolve()));
  const error=await new Promise((resolve,reject)=>{
   socket=io('http://127.0.0.1:'+port,{transports:['polling'],reconnection:false,forceNew:true,timeout:1000});
   socket.once('connect_error',resolve);socket.once('connect',()=>reject(Error('REFUSAL_CONTROL_UNEXPECTED_CONNECT')));
  });
  assert.equal(error.type,'TransportError');assert.equal(error.message,'xhr poll error');assert.equal(error.description,0);assert.equal(error.context.statusText.code,'ECONNREFUSED');
  const f=fixture();try{
   const r=await simulated(f,{connectErrorAt:7,connectErrors:[error]});
   assert.equal(r.error.code,'M7_ADMISSION_STOCK_CONNECT_FAILED');
   assert.deepEqual(r.last.connectErrors,{total:1,groups:[{transport:'polling',kind:'XHR_POLL_ERROR',code:'ECONNREFUSED',status:0,count:1}],other:0});
  }finally{f.remove();}
 }finally{socket?.close();if(server.listening)await new Promise(resolve=>server.close(resolve));}
});
