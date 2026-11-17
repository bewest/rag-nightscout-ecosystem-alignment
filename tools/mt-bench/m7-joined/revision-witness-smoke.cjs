'use strict';
// One isolated native helper smoke. Real source projection/runtime/protocol, real polling.
// Storage/authority ports synthetic; no database, clinical or capacity qualification.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http'),Module=require('node:module'),{execFileSync}=require('node:child_process');
const w=require('./revision-witness.cjs');
const [root,out]=process.argv.slice(2);if(!path.isAbsolute(root)||!path.isAbsolute(out)||fs.existsSync(out))throw Error('M7_WITNESS_SMOKE_PATH');fs.mkdirSync(out,{recursive:true,mode:0o700});
const source=execFileSync('git',['-C',root,'rev-parse','HEAD'],{encoding:'utf8'}).trim(),owner=require('node:crypto').randomBytes(16).toString('hex'),tenant='11111111-1111-4111-8111-111111111111',storedId='synthetic-row-a';
const targets=[{tenant,storedId}],taps=[];function tap(name){const t=w.create({owner,source,targets,persist:v=>fs.writeFileSync(path.join(out,name+'.json'),JSON.stringify(v)+'\n',{mode:0o600})});taps.push(t);return t;}
const serverTap=tap('server'),clientTap=tap('client');
// Replace only the store port at its explicit dependency boundary. The actual
// shipping projection checks restore and byte bounds, runtime fences and protocol run.
const originalLoad=Module._load;let revision=1;const body=()=>({tenant,restoreGeneration:1,outputRevision:revision,inputCheckpoint:12,frame:{delta:false,lastUpdated:revision,sgvs:revision===1?[]:[{_id:storedId,mills:1800000000000,mgdl:123,scaled:123}]} });
Module._load=function(request,parent,isMain){const file=Module._resolveFilename(request,parent,isMain);if(file===path.join(root,'lib/pgstream/checkpoint.js'))return {create:()=>({output:async()=>body()})};return Reflect.apply(originalLoad,this,arguments);};
const hook=w.install({root,tap:serverTap});
const scope=require(path.join(root,'lib/storage/tenant-scope'));scope.setTenancyMode('multi');
const projection=require(path.join(root,'lib/pgstream/realtime-output')),start=require(path.join(root,'lib/server/realtime/runtime')),protocolFactory=require(path.join(root,'lib/server/realtime/protocol')),socketServer=require(path.join(root,'lib/server/realtime/socket-server')),client=require(path.join(root,'node_modules/socket.io-client')).io;
const env=require(path.join(root,'lib/server/tenant-app/environment'))({settings:{enable:['bgnow']}}),current={tenant,identity:'synthetic',env},server=http.createServer();let runtime,socket,protocol,sockets,port;
const canBind=port=>new Promise((resolve,reject)=>{const listener=require('node:net').createServer();listener.once('error',error=>error.code==='EADDRINUSE'?resolve(false):reject(error));listener.listen(port,'127.0.0.1',()=>listener.close(()=>resolve(true)));});
const until=async fn=>{const end=Date.now()+5000;while(!fn()){if(Date.now()>end)throw Error('M7_WITNESS_SMOKE_TIMEOUT');await new Promise(r=>setTimeout(r,10));}};
(async()=>{let primed=0;
 try{
 const admission={resolve:async()=>tenant};
 protocol=protocolFactory.create({admission,readCurrent:async()=>current,api:{executeSocketMutation:async()=>({replyArgs:[]}),authorizeSocket:async()=>({permissions:{read:true,write:false,write_treatment:false,ack:false},collections:[]})},runtime:()=>runtime,domains:['entries']});
 sockets=socketServer.attach(server,{protocol,admission,maxMessageBytes:100000});
 runtime=await start({tenants:[tenant],readCurrent:async()=>current,create:current=>projection.projection({config:{completedOutput:{namespace:'test_completed',consumer:'evaluator-test'},maxBytes:100000},connection:{},current,operationWindow:{currentGeneration:()=>1}}),fanout:protocol.fanout,schedule:()=>1,cancel(){}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 port=server.address().port;assert.equal(await canBind(port),false,'M7_OWN_LISTENER_ABSENCE_CONTROL');fs.writeFileSync(path.join(out,'resources.json'),JSON.stringify({owner,source,instrumentFiles:Object.fromEntries(['revision-witness.cjs','revision-witness-smoke.cjs'].map(name=>[name,require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(__dirname,name))).digest('hex')])),pid:process.pid,port,actors:1,sockets:1,sharedHost:true,transport:'polling',storage:'synthetic-port',startedAt:new Date().toISOString()})+'\n');
 socket=client('http://127.0.0.1:'+port,{transports:['polling'],forceNew:true,reconnection:false});const observed=w.client({socket,tenant,tap:clientTap});
 socket.on('connect',()=>socket.emit('authorize',{secret:'synthetic'}));socket.on('dataUpdate',frame=>{observed.callback(frame);primed++;});
 await until(()=>primed>0);revision=7;await runtime.refresh(tenant);await until(()=>clientTap.state().events.some(e=>e.stage==='stock-callback'));
 const result=w.correlate(taps.map(t=>t.state()));fs.writeFileSync(path.join(out,'correlation.json'),JSON.stringify(result,null,2)+'\n');assert.equal(result.verdict,'PASS');assert.equal(result.joins[0].outputRevision,'7');assert.equal(result.joins[0].inputCheckpoint,'12');
 console.log(JSON.stringify({status:'PASS',source,transport:'polling',joins:result.joins.length,limits:'synthetic store/authority ports; clinical completion/receipt/raw-tail and cross-process emit-to-arrival UNMEASURED',overheadNs:taps.map(t=>t.state().overheadNs)}));
 }finally{
 socket?.close();protocol?.close();await runtime?.close();await sockets?.close();if(server.listening)await new Promise(resolve=>server.close(resolve));hook.restore();Module._load=originalLoad;
 // Exact listener negative/restored: a bound listener must fail absence, then close must pass.
 if(port)assert.equal(await canBind(port),true,'M7_OWN_LISTENER_STILL_PRESENT');
 fs.writeFileSync(path.join(out,'cleanup.json'),JSON.stringify({exactPort:port,activeListenerControl:'RED_EXPECTED_EADDRINUSE',restoredBind:'PASS',serverListening:server.listening,clientDisconnected:!socket?.connected,scope:'only owned HTTP/socket actors; exact close plus active bind negative control',closedAt:new Date().toISOString()})+'\n');
 }
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
