'use strict';
const assert=require('node:assert/strict'),http=require('node:http'),{EventEmitter}=require('node:events'),{run}=require('./access.cjs');
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
  connected=false;await assert.rejects(green,/K8S_SOCKET_REFUSAL_UNMEASURED/);connected=true;await green();
  console.log('RED_RESTORED HTTP cross-authority, foreign socket frame, lost socket observation; loopback HTTP and synthetic socket boundary');
 }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
