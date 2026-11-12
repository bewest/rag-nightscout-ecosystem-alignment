'use strict';
// Functional instrument fixture: real Socket.IO client/server and HTTP, fake
// tenant app. It is not product authorization/clinical/image acceptance.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http'),crypto=require('node:crypto');
const {run}=require('./diagnostic.cjs');
const {spawn}=require('node:child_process');
const core=process.env.M7_DIAGNOSTIC_TEST_CORE;
async function fixture({wrongHost=false,suppressFrame=false,lateStatus=null,suppressInitialFrames=false}={}){
  const {Server}=require(path.join(core,'node_modules/socket.io')),{io}=require(path.join(core,'node_modules/socket.io-client'));
  const d=fs.mkdtempSync(path.join(os.tmpdir(),'m7-functional-fixture-'));fs.mkdirSync(path.join(d,'load'));
  const tenants=['a','b'].map(letter=>({id:crypto.randomUUID(),host:letter+'.example.test',token:crypto.randomUUID()}));
  const frames=new Map(tenants.map(row=>[row.host,{sgvs:[]}])) ;let server,socketServer,port;const connections=new Set();let authorized=0;
  const begin=async()=>{
    server=http.createServer((req,res)=>{
      const host=(req.headers.host||'').split(':')[0];if(!frames.has(host)){res.writeHead(421);res.end('{}');return;}
      const respond=body=>{res.setHeader('content-type','application/json');res.end(JSON.stringify(body));};
      if(req.url.startsWith('/api/v2/authorization/request/')){respond({token:crypto.randomUUID()});return;}
      if(req.url.startsWith('/api/v1/status')){if(lateStatus&&host===tenants[1].host){const reply=()=>{res.statusCode=lateStatus.status;respond(lateStatus.body)};if(suppressInitialFrames){const until=Date.now()+1000;const wait=()=>authorized>0||Date.now()>=until?reply():setTimeout(wait,5);wait();}else reply();return;}respond({status:'ok'});return;}
      if(req.method==='POST'){
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

for(const refusal of [{status:503,body:{error:'TENANT_WARMING'},expected:'TENANT_WARMING'},{status:401,body:{error:'AUTHORITY_FORBIDDEN'},expected:'AUTHORITY_FORBIDDEN'},{status:503,body:{error:'UNEXPECTED_UNAVAILABLE'},expected:'UNEXPECTED_UNAVAILABLE'},{status:503,body:{error:'not a typed code',message:'PRIVATE_MESSAGE',token:'PRIVATE_TOKEN'},expected:null}])test('late second-tenant status refusal retains sanitized status and code '+refusal.status+'/'+refusal.expected,{skip:!core,timeout:5000},async()=>{
  const f=await fixture({lateStatus:refusal});let restarted=false;try{
    await assert.rejects(run({directory:f.d,seconds:2,restart:async()=>{restarted=true;throw Error('UNEXPECTED_RESTART')}}),error=>error.code==='M7_DIAGNOSTIC_HTTP_REFUSED');
    const file=path.join(f.d,'load/diagnostic-http.json'),trail=JSON.parse(fs.readFileSync(file,'utf8'));
    assert.equal(trail.requests.length,4,'no retry/exchange fallback/write after refusal');
    assert.deepEqual(trail.requests[3],{request:4,stage:'initial-status',tenantIndex:1,method:'GET',routeClass:'status',status:refusal.status,errorCode:refusal.expected,failureCode:null});
    assert.equal(trail.requests[2].status,200);assert.equal(trail.requests[2].routeClass,'exchange');
    const raw=fs.readFileSync(file,'utf8');for(const secret of [f.tenants[0].token,f.tenants[1].token,f.tenants[0].host,f.tenants[1].host,'PRIVATE_MESSAGE','PRIVATE_TOKEN','/api/','token='])assert.ok(!raw.includes(secret));
    assert.equal(fs.statSync(file).mode&0o777,0o600);assert.ok(Buffer.byteLength(raw)<16384);
    const observation=JSON.parse(fs.readFileSync(path.join(f.d,'load/diagnostic-observations.json'),'utf8'));assert.equal(observation.failureCode,'M7_DIAGNOSTIC_HTTP_REFUSED');assert.equal(observation.dataHttpRequests,4);
    assert.equal(fs.existsSync(path.join(f.d,'load/client-acks.json')),false);assert.equal(restarted,false);
  }finally{await f.close();}
});

for(const status of [503,401])test('spawned CLI exits promptly after fourth HTTP refusal with a connected frameless stock socket '+status,{skip:!core,timeout:5000},async()=>{
  const f=await fixture({lateStatus:{status,body:{error:status===503?'TENANT_WARMING':'AUTHORITY_FORBIDDEN'}},suppressInitialFrames:true});let child,timer;try{
    child=spawn(process.execPath,[path.join(__dirname,'diagnostic.cjs'),f.d,'180'],{env:{PATH:process.env.PATH,NODE_PATH:path.join(core,'node_modules')},stdio:['ignore','pipe','pipe']});
    let stderr='';child.stderr.on('data',bytes=>{stderr+=bytes.toString();assert.ok(stderr.length<4096)});child.stdout.resume();
    const result=await Promise.race([new Promise((resolve,reject)=>{child.once('exit',(code,signal)=>resolve({code,signal}));child.once('error',reject)}),new Promise(resolve=>{timer=setTimeout(()=>resolve({lingered:true}),1500)})]);
    assert.ok(stderr.includes('M7_DIAGNOSTIC_HTTP_REFUSED'),'instrument must retain original refusal taxonomy');
    assert.equal(result.lingered,undefined,'CLI_LINGERED_AFTER_REFUSAL '+stderr);assert.equal(result.code,1);assert.equal(result.signal,null);
    const observation=JSON.parse(fs.readFileSync(path.join(f.d,'load/diagnostic-observations.json'),'utf8'));
    assert.equal(observation.dataHttpRequests,4);assert.equal(observation.sockets[0].connects,1);assert.equal(observation.sockets[0].frames,0);
    const trail=JSON.parse(fs.readFileSync(path.join(f.d,'load/diagnostic-http.json'),'utf8'));assert.equal(trail.requests[3].status,status);
  }finally{clearTimeout(timer);if(child&&child.exitCode===null&&child.signalCode===null){const exited=new Promise(resolve=>child.once('exit',resolve));child.kill('SIGKILL');await exited;}await f.close();}
});
