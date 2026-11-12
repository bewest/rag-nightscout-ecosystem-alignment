'use strict';
// Focused oracle: real pinned status router + tenant environment, synthetic
// authorization, real local HTTP. This is not full serving/DB acceptance.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const core=process.argv[2],out=process.argv[3];
const express=require(path.join(core,'node_modules/express'));
const env=require(path.join(core,'lib/server/tenant-app/environment'))();
const app=express();app.set('name','synthetic fixture');app.set('version','fixture');app.enable('api');app.extendedClientSettings=env.extendedSettings;
const wares={sendJSONStatus:(_req,_res,next)=>next(),extensions:()=> (_req,_res,next)=>next()};
const ctx={authorization:{isPermitted:()=> (_req,_res,next)=>next()},runtimeState:{}};
app.use(require(path.join(core,'lib/api/status'))(app,wares,env,ctx,{authorizeStatus:async()=>false}));
app.use((_error,_req,res,_next)=>res.status(500).json({error:'fixture-failed'}));
const server=app.listen(0,'127.0.0.1',()=>{
  http.get({host:'127.0.0.1',port:server.address().port,path:'/status',headers:{Accept:'application/json'}},res=>{
    const chunks=[];res.on('data',data=>chunks.push(data));res.on('end',()=>{
      if(res.statusCode!==200){process.exitCode=1;server.close();return;}
      fs.writeFileSync(out,Buffer.concat(chunks),{mode:0o600});server.close();
    });
  }).on('error',()=>{process.exitCode=1;server.close();});
});
