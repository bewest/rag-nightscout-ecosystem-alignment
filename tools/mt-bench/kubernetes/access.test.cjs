'use strict';
const assert=require('node:assert/strict'),http=require('node:http'),{EventEmitter}=require('node:events'),{run,scope}=require('./access.cjs');
(async()=>{
 let leakHttp=false,leakFrame=false,connected=true;
 const tenants=[{host:'a.example.test',token:'synthetic-a'},{host:'b.example.test',token:'synthetic-b'}];
 const server=http.createServer((req,res)=>{
   if(req.url.startsWith('/api/v2/authorization/request/')){res.end(JSON.stringify({token:'synthetic-jwt'}));return;}
   res.statusCode=leakHttp?200:403;res.end(leakHttp?'[]':JSON.stringify({error:'AUTHORITY_FORBIDDEN'}));
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const io=()=>{
   const socket=new EventEmitter(),emit=socket.emit.bind(socket);socket.close=()=>{};
   socket.emit=(name,...args)=>{if(name==='authorize'){assert.equal(args[0].token,'synthetic-jwt');if(leakFrame)queueMicrotask(()=>emit('dataUpdate',{sgvs:[]}));return true;}return emit(name,...args);};
   if(connected)queueMicrotask(()=>emit('connect'));return socket;
 };
 const green=async()=>assert.equal((await run(tenants,new URL('http://127.0.0.1:'+server.address().port),io,{observeMs:20})).verdict,'PASS');
 try{
  await green();leakHttp=true;await assert.rejects(green,/K8S_CROSS_TENANT_AUTHORITY/);leakHttp=false;await green();
  leakFrame=true;await assert.rejects(green,/K8S_FOREIGN_SOCKET_FRAME/);leakFrame=false;await green();
  connected=false;
  const lost=await run(tenants,new URL('http://127.0.0.1:'+server.address().port),io,{observeMs:20});
  assert.equal(lost.verdict,'UNMEASURED');assert.equal(lost.unmeasuredCases,2);
  assert.ok(lost.records.some(r=>r.case==='cross-token-socket'&&r.verdict==='UNMEASURED'));
  // The socket-free isolation checks still ran and stayed red-capable.
  assert.ok(lost.records.some(r=>r.case==='cross-token-host'));
  leakHttp=true;await assert.rejects(()=>run(tenants,new URL('http://127.0.0.1:'+server.address().port),io,{observeMs:20}),/K8S_CROSS_TENANT_AUTHORITY/);leakHttp=false;
  // Warm-up: an untyped 403 for the whole warm window is UNMEASURED, never PASS; the run continues.
  const refused=await run(tenants,new URL('http://127.0.0.1:'+server.address().port),()=>{const s=new EventEmitter();s.close=()=>{};queueMicrotask(()=>s.emit('connect_error',{description:403}));return s;},{observeMs:20,warmupMs:1500});
  assert.equal(refused.verdict,'UNMEASURED');assert.equal(refused.warmup.observations[0].verdict,'UNMEASURED');assert.ok(refused.warmup.observations[0].attempts>1);
  connected=true;await green();
  // Scope: loopback forward always; an IPv4 edge ClusterIP only from an in-cluster controller (NS_CAMPAIGN_ATTACH_SCOPE=pod).
  assert.equal(scope(new URL('http://127.0.0.1:1'),{}),true);
  assert.equal(scope(new URL('http://10.245.3.7:8080'),{}),false);
  assert.equal(scope(new URL('http://10.245.3.7:8080'),{NS_CAMPAIGN_ATTACH_SCOPE:'pod'}),true);
  assert.equal(scope(new URL('http://edge.ns.svc:8080'),{NS_CAMPAIGN_ATTACH_SCOPE:'pod'}),false);
  await assert.rejects(()=>run(tenants,new URL('http://10.245.3.7:8080'),io,{observeMs:20}),/K8S_ACCESS_SCOPE/);
  console.log('RED_RESTORED HTTP cross-authority, foreign socket frame; lost or warming socket is UNMEASURED and continues; loopback HTTP and synthetic socket boundary');
 }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
