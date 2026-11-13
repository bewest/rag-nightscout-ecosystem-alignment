'use strict';
// Functional instrument fixture: real Socket.IO client/server and HTTP, fake
// tenant app. It is not product authorization/clinical/image acceptance.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http'),crypto=require('node:crypto');
const {run}=require('./diagnostic.cjs');
const {spawn,fork}=require('node:child_process');
const core=process.env.M7_DIAGNOSTIC_TEST_CORE;
async function fixture({wrongHost=false,suppressFrame=false,lateStatus=null,suppressInitialFrames=false,lateExchange=false,writeRefusal=false}={}){
  const {Server}=require(path.join(core,'node_modules/socket.io')),{io}=require(path.join(core,'node_modules/socket.io-client'));
  const d=fs.mkdtempSync(path.join(os.tmpdir(),'m7-functional-fixture-'));fs.mkdirSync(path.join(d,'load'));
  const tenants=['a','b'].map(letter=>({id:crypto.randomUUID(),host:letter+'.example.test',token:crypto.randomUUID()}));
  const frames=new Map(tenants.map(row=>[row.host,{sgvs:[]}])) ;let server,socketServer,port;const connections=new Set();let authorized=0;
  const begin=async()=>{
    server=http.createServer((req,res)=>{
      const host=(req.headers.host||'').split(':')[0];if(!frames.has(host)){res.writeHead(421);res.end('{}');return;}
      const respond=body=>{res.setHeader('content-type','application/json');res.end(JSON.stringify(body));};
      if(req.url.startsWith('/api/v2/authorization/request/')){if(lateExchange&&host===tenants[1].host){res.statusCode=503;respond({error:'TENANT_WARMING'});return;}respond({token:crypto.randomUUID()});return;}
      if(req.url.startsWith('/api/v1/status')){if(lateStatus&&host===tenants[1].host&&lateStatus.remaining!==0&&(!lateStatus.sequence||lateStatus.sequence.length)){if(Number.isInteger(lateStatus.remaining))lateStatus.remaining--;const selected=lateStatus.sequence?lateStatus.sequence.shift():lateStatus;const reply=()=>{res.statusCode=selected.status;respond(selected.body)};if(suppressInitialFrames){const until=Date.now()+1000;const wait=()=>authorized>0||Date.now()>=until?reply():setTimeout(wait,5);wait();}else reply();return;}respond({status:'ok'});return;}
      if(req.method==='POST'){
        if(writeRefusal){res.statusCode=503;respond({error:'TENANT_WARMING'});return;}
        const chunks=[];req.on('data',row=>chunks.push(row));req.on('end',()=>{const row=JSON.parse(Buffer.concat(chunks).toString())[0];frames.set(host,{sgvs:[{mills:row.date,mgdl:row.sgv}]});respond([row]);if(!suppressFrame)for(const socket of socketServer.sockets.sockets.values())if(socket.data.host===host)socket.emit('dataUpdate',frames.get(host));});return;
      }
      res.writeHead(404);res.end('{}');
    });
    server.on('connection',socket=>{connections.add(socket);socket.on('close',()=>connections.delete(socket));});
    socketServer=new Server(server,{pingInterval:100,pingTimeout:100,allowRequest:(req,callback)=>callback(null,frames.has((req.headers.host||'').split(':')[0]))});
    socketServer.on('connection',socket=>{socket.data.host=socket.handshake.headers.host.split(':')[0];socket.on('authorize',(body,ack)=>{authorized++;if(!suppressInitialFrames)socket.emit('dataUpdate',frames.get(socket.data.host));ack?.({authorized:true});});});
    await new Promise(resolve=>server.listen(port||0,'127.0.0.1',resolve));port=server.address().port;
  };
  const stop=async()=>{for(const socket of connections)socket.destroy();await new Promise(resolve=>socketServer.close(resolve));await new Promise(resolve=>server.close(resolve));};
  await begin();
  fs.writeFileSync(path.join(d,'owner.json'),JSON.stringify({profile:'fresh-image-diagnostic',tenants:2,replicas:1,port,project:'fixture-only'}));
  fs.writeFileSync(path.join(d,'tenants.private.json'),JSON.stringify(tenants));fs.writeFileSync(path.join(d,'load/runid'),'diagnostic-fixture');fs.writeFileSync(path.join(d,'frozen.compose.json'),JSON.stringify({services:{realtime:{command:['node','entrypoint.js','realtime']}}}));
  return {d,tenants,ioFactory:wrongHost?(url,options)=>io(url.replace(/\/\/[^:]+:/,'//127.0.0.1:'),{...options,extraHeaders:{Host:tenants[0].host}}):io,
    restart:async()=>{await stop();await begin();return {commandMs:1,starts:{realtime:{observed:true}}};},close:async()=>{await stop();fs.rmSync(d,{recursive:true,force:true});}};
}
test('bounded diagnostic uses registered-host stock polling, current frame and unaided recovery', {skip:!core,timeout:10000}, async()=>{
  const f=await fixture();try{const result=await run({directory:f.d,seconds:5,restart:f.restart});assert.ok(Object.values(result.checks).every(Boolean));assert.equal(result.acceptedWrites,2);assert.equal(result.tenants,2);}catch(error){console.log('FIXTURE_OBSERVATION',fs.readFileSync(path.join(f.d,'load/diagnostic-observations.json'),'utf8'));throw error;}finally{await f.close();}
});
test('wrong127URL/extraHeaders client model is rejected instead of measured as product latency', {skip:!core,timeout:5000}, async()=>{
  const f=await fixture({wrongHost:true});try{await assert.rejects(run({directory:f.d,seconds:1,ioFactory:f.ioFactory,restart:f.restart}),error=>['M7_DIAGNOSTIC_DEADLINE','M7_DIAGNOSTIC_STOCK_PRIME_FAILED'].includes(error.code));}finally{await f.close();}
});
test('HTTP ACK without a current frame cannot produce diagnostic PASS', {skip:!core,timeout:5000}, async()=>{
  const f=await fixture({suppressFrame:true});try{await assert.rejects(run({directory:f.d,seconds:1,ioFactory:f.ioFactory,restart:f.restart}),error=>['M7_DIAGNOSTIC_DEADLINE','M7_DIAGNOSTIC_FRAME_MISSING'].includes(error.code));}finally{await f.close();}
});

for(const refusal of [{status:401,body:{error:'AUTHORITY_FORBIDDEN'},expected:'AUTHORITY_FORBIDDEN'},{status:503,body:{error:'UNEXPECTED_UNAVAILABLE'},expected:'UNEXPECTED_UNAVAILABLE'},{status:503,body:{error:'not a typed code',message:'PRIVATE_MESSAGE',token:'PRIVATE_TOKEN'},expected:null}])test('late second-tenant status refusal retains sanitized status and code '+refusal.status+'/'+refusal.expected,{skip:!core,timeout:5000},async()=>{
  const f=await fixture({lateStatus:refusal});let restarted=false;try{
    await assert.rejects(run({directory:f.d,seconds:2,restart:async()=>{restarted=true;throw Error('UNEXPECTED_RESTART')}}),error=>error.code==='M7_DIAGNOSTIC_HTTP_REFUSED');
    const file=path.join(f.d,'load/diagnostic-http.json'),trail=JSON.parse(fs.readFileSync(file,'utf8'));
    assert.equal(trail.requests.length,4,'no retry/exchange fallback/write after refusal');
    assert.deepEqual(trail.requests[3],{request:4,classification:'refused',stage:'initial-status',tenantIndex:1,method:'GET',routeClass:'status',status:refusal.status,errorCode:refusal.expected,failureCode:null});
    assert.equal(trail.requests[2].status,200);assert.equal(trail.requests[2].routeClass,'exchange');
    const raw=fs.readFileSync(file,'utf8');for(const secret of [f.tenants[0].token,f.tenants[1].token,f.tenants[0].host,f.tenants[1].host,'PRIVATE_MESSAGE','PRIVATE_TOKEN','/api/','token='])assert.ok(!raw.includes(secret));
    assert.equal(fs.statSync(file).mode&0o777,0o600);assert.ok(Buffer.byteLength(raw)<16384);
    const observation=JSON.parse(fs.readFileSync(path.join(f.d,'load/diagnostic-observations.json'),'utf8'));assert.equal(observation.failureCode,'M7_DIAGNOSTIC_HTTP_REFUSED');assert.equal(observation.physicalHttpRequests,4);assert.equal(observation.criterionHttpRequests,3);
    assert.equal(fs.existsSync(path.join(f.d,'load/client-acks.json')),false);assert.equal(restarted,false);
  }finally{await f.close();}
});

for(const status of [503,401])test('spawned CLI exits promptly after fourth HTTP refusal with a connected frameless stock socket '+status,{skip:!core,timeout:5000},async()=>{
  const f=await fixture({lateStatus:{status,body:{error:status===503?'UNEXPECTED_UNAVAILABLE':'AUTHORITY_FORBIDDEN'}},suppressInitialFrames:true});let child,timer;try{
    child=spawn(process.execPath,[path.join(__dirname,'diagnostic.cjs'),f.d,'180'],{env:{PATH:process.env.PATH,NODE_PATH:path.join(core,'node_modules')},stdio:['ignore','pipe','pipe']});
    let stderr='';child.stderr.on('data',bytes=>{stderr+=bytes.toString();assert.ok(stderr.length<4096)});child.stdout.resume();
    const result=await Promise.race([new Promise((resolve,reject)=>{child.once('exit',(code,signal)=>resolve({code,signal}));child.once('error',reject)}),new Promise(resolve=>{timer=setTimeout(()=>resolve({lingered:true}),1500)})]);
    assert.ok(stderr.includes('M7_DIAGNOSTIC_HTTP_REFUSED'),'instrument must retain original refusal taxonomy');
    assert.equal(result.lingered,undefined,'CLI_LINGERED_AFTER_REFUSAL '+stderr);assert.equal(result.code,1);assert.equal(result.signal,null);
    const observation=JSON.parse(fs.readFileSync(path.join(f.d,'load/diagnostic-observations.json'),'utf8'));
    assert.equal(observation.physicalHttpRequests,4);assert.equal(observation.criterionHttpRequests,3);assert.equal(observation.sockets[0].connects,1);assert.equal(observation.sockets[0].frames,0);
    const trail=JSON.parse(fs.readFileSync(path.join(f.d,'load/diagnostic-http.json'),'utf8'));assert.equal(trail.requests[3].status,status);
  }finally{clearTimeout(timer);if(child&&child.exitCode===null&&child.signalCode===null){const exited=new Promise(resolve=>child.once('exit',resolve));child.kill('SIGKILL');await exited;}await f.close();}
});

test('typed status warming becomes200 while retaining first refusal and separate accounting',{skip:!core,timeout:10000},async()=>{
  const f=await fixture({lateStatus:{status:503,body:{error:'TENANT_WARMING'},remaining:2}});try{
    const value=await run({directory:f.d,seconds:5,restart:f.restart});assert.ok(Object.values(value.checks).every(Boolean));
    assert.equal(value.criterionHttpRequests,8);assert.equal(value.dataHttpRequests,8);assert.equal(value.physicalHttpRequests,10);assert.equal(value.warmProbeHttpRequests,2);assert.equal(value.trailRecords,10);
    const trail=JSON.parse(fs.readFileSync(path.join(f.d,'load/diagnostic-http.json'),'utf8'));assert.equal(trail.requests[3].status,503);assert.equal(trail.requests[3].errorCode,'TENANT_WARMING');assert.equal(trail.requests[3].classification,'warming-probe');assert.equal(trail.requests[5].status,200);assert.ok(value.trailBytes<=262144);
  }finally{await f.close();}
});
test('global warming probe limit refuses before a further request or mutation',{skip:!core,timeout:5000},async()=>{
  const f=await fixture({lateStatus:{status:503,body:{error:'TENANT_WARMING'}}});let restarted=false;try{
    await assert.rejects(run({directory:f.d,seconds:5,maxWarmProbes:2,restart:async()=>{restarted=true}}),error=>error.code==='M7_DIAGNOSTIC_WARM_PROBE_LIMIT');
    const value=JSON.parse(fs.readFileSync(path.join(f.d,'load/diagnostic-observations.json'),'utf8'));assert.equal(value.physicalHttpRequests,5);assert.equal(value.warmProbeHttpRequests,2);assert.equal(value.criterionHttpRequests,3);assert.equal(restarted,false);assert.equal(fs.existsSync(path.join(f.d,'load/client-acks.json')),false);
  }finally{await f.close();}
});
test('spawned CLI exhausts unchanged deadline while warming and exits cleanly',{skip:!core,timeout:5000},async()=>{
  const f=await fixture({lateStatus:{status:503,body:{error:'TENANT_WARMING'}},suppressInitialFrames:true});let child,timer;try{
    child=spawn(process.execPath,[path.join(__dirname,'diagnostic.cjs'),f.d,'1'],{env:{PATH:process.env.PATH,NODE_PATH:path.join(core,'node_modules')},stdio:['ignore','pipe','pipe']});let stderr='';child.stderr.on('data',bytes=>stderr+=bytes);child.stdout.resume();
    const result=await Promise.race([new Promise((resolve,reject)=>{child.once('exit',code=>resolve(code));child.once('error',reject)}),new Promise(resolve=>{timer=setTimeout(()=>resolve('LINGERED'),2500)})]);assert.equal(result,1);assert.ok(stderr.includes('M7_DIAGNOSTIC_DEADLINE'));
    const value=JSON.parse(fs.readFileSync(path.join(f.d,'load/diagnostic-observations.json'),'utf8'));assert.ok(value.warmProbeHttpRequests>0&&value.warmProbeHttpRequests<=512);assert.equal(value.criterionHttpRequests,3);assert.equal(fs.existsSync(path.join(f.d,'load/client-acks.json')),false);
  }finally{clearTimeout(timer);if(child&&child.exitCode===null&&child.signalCode===null){const exited=new Promise(resolve=>child.once('exit',resolve));child.kill('SIGKILL');await exited;}await f.close();}
});

for(const refusal of [{status:401,error:'AUTHORITY_FORBIDDEN'},{status:503,error:'UNEXPECTED_UNAVAILABLE'}])test('warming followed by '+refusal.status+' does not broaden retry policy',{skip:!core,timeout:5000},async()=>{
  const f=await fixture({lateStatus:{sequence:[{status:503,body:{error:'TENANT_WARMING'}},{status:refusal.status,body:{error:refusal.error}}]}});try{
    await assert.rejects(run({directory:f.d,seconds:3,restart:async()=>{throw Error('UNEXPECTED_RESTART')}}),error=>error.code==='M7_DIAGNOSTIC_HTTP_REFUSED');
    const trail=JSON.parse(fs.readFileSync(path.join(f.d,'load/diagnostic-http.json'),'utf8'));assert.equal(trail.requests.length,5);assert.equal(trail.requests[3].classification,'warming-probe');assert.equal(trail.requests[4].classification,'refused');assert.equal(trail.requests[4].errorCode,refusal.error);assert.equal(fs.existsSync(path.join(f.d,'load/client-acks.json')),false);
  }finally{await f.close();}
});
test('real SDK child CLI completes warming-to200 and stock frame/recovery criteria',{skip:!core,timeout:10000},async()=>{
  const f=await fixture({lateStatus:{status:503,body:{error:'TENANT_WARMING'},remaining:2}});let child,timer;try{
    child=fork(path.join(__dirname,'diagnostic-fixture-cli.cjs'),[f.d,'5'],{env:{PATH:process.env.PATH,NODE_PATH:path.join(core,'node_modules')},stdio:['ignore','pipe','pipe','ipc']});let stdout='',stderr='';child.stdout.on('data',bytes=>stdout+=bytes);child.stderr.on('data',bytes=>stderr+=bytes);
    child.on('message',async value=>{if(value?.kind==='fixture-restart'){const result=await f.restart();child.send({kind:'fixture-restarted',result});}});
    const result=await Promise.race([new Promise((resolve,reject)=>{child.once('exit',code=>resolve(code));child.once('error',reject)}),new Promise(resolve=>{timer=setTimeout(()=>resolve('LINGERED'),6500)})]);assert.equal(result,0,stderr);assert.ok(stdout.includes('M7_DIAGNOSTIC_CLIENT_CRITERIA_PASS'));
    const value=JSON.parse(fs.readFileSync(path.join(f.d,'load/diagnostic-observations.json'),'utf8'));assert.ok(Object.values(value.checks).every(Boolean));assert.equal(value.criterionHttpRequests,8);assert.equal(value.physicalHttpRequests,10);assert.equal(value.warmProbeHttpRequests,2);const trail=JSON.parse(fs.readFileSync(path.join(f.d,'load/diagnostic-http.json'),'utf8'));assert.equal(trail.requests[3].status,503);assert.equal(trail.requests[3].classification,'warming-probe');
  }finally{clearTimeout(timer);if(child&&child.exitCode===null&&child.signalCode===null){const exited=new Promise(resolve=>child.once('exit',resolve));child.kill('SIGKILL');await exited;}await f.close();}
});

test('exchange warming refusal is not a status probe or credential fallback',{skip:!core,timeout:5000},async()=>{
  const f=await fixture({lateExchange:true});try{await assert.rejects(run({directory:f.d,seconds:3}),error=>error.code==='M7_DIAGNOSTIC_DATA_EXCHANGE_REFUSED');const value=JSON.parse(fs.readFileSync(path.join(f.d,'load/diagnostic-observations.json'),'utf8'));assert.equal(value.physicalHttpRequests,3);assert.equal(value.warmProbeHttpRequests,0);assert.equal(fs.existsSync(path.join(f.d,'load/client-acks.json')),false);}finally{await f.close();}
});
test('mutation warming refusal is never retried',{skip:!core,timeout:5000},async()=>{
  const f=await fixture({writeRefusal:true});try{await assert.rejects(run({directory:f.d,seconds:3}),error=>error.code==='M7_DIAGNOSTIC_WRITE_REFUSED');const value=JSON.parse(fs.readFileSync(path.join(f.d,'load/diagnostic-observations.json'),'utf8'));assert.equal(value.physicalHttpRequests,5);assert.equal(value.warmProbeHttpRequests,0);const trail=JSON.parse(fs.readFileSync(path.join(f.d,'load/diagnostic-http.json'),'utf8'));assert.equal(trail.requests.filter(row=>row.method==='POST').length,1);assert.equal(fs.existsSync(path.join(f.d,'load/client-acks.json')),false);}finally{await f.close();}
});
test('probe count cannot be configured beyond the production bound',async()=>{await assert.rejects(run({directory:'/unused',seconds:1,maxWarmProbes:513}),error=>error.code==='M7_DIAGNOSTIC_WARM_PROBE_LIMIT_INVALID');});
