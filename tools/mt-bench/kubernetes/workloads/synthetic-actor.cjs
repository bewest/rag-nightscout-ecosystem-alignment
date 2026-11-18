"use strict";
// Instrument fixture only: synthetic HTTP/socket/SQL boundaries, no product.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),crypto=require('node:crypto');
const [directory,dependencies]=process.argv.slice(2),input=JSON.parse(fs.readFileSync(path.join(directory,'actor-input.json')));
const {Server}=require(path.join(dependencies,'node_modules/socket.io'));
const {tenants,completion,status}=input,docs=new Map(tenants.map(t=>[t.id,[]]));let ordinal=0,round=0;const calls=[];
const frame=id=>({sgvs:docs.get(id).filter(d=>d.type==='sgv').map(d=>({_id:d._id,mills:d.date,mgdl:d.sgv}))});
const counts=marker=>Object.fromEntries(tenants.map(t=>[t.id,Object.fromEntries(['entries','devicestatus','treatments','probe'].map(kind=>[kind,docs.get(t.id).filter(d=>d._kind===kind&&(d.device===marker||d.enteredBy===marker||kind==='probe'&&d.device===marker+'-probe')).length]))]));
function row(t){
 const all=docs.get(t.id),stored=all.filter(d=>d._kind==='probe');if(!stored.length)return null;
 const clock=String(all.length),f=frame(t.id),valid=f.sgvs.filter(s=>s.mgdl>39),last=valid.reduce((a,b)=>a.mills>=b.mills?a:b),observed=[clock,null,null,null,null,null];
 return {tenant:t.id,stamp:clock,reader:completion.binding,stored,typed:{version:2,contractDigest:crypto.createHash('sha256').update(JSON.stringify(['evaluator-work-v2',completion.checkpoint,'evaluator-sample'])).digest('hex'),observed,completed:observed,identity:'5'.repeat(64),digest:'6'.repeat(64),revision:clock,generation:null,enabled:true,arrayBounds:true,bodyMetadataAbsent:true},state:{kind:'evaluator-work-v2',observed:{clock},completed:{clock},output:{tenant:t.id,identity:'5'.repeat(64),inputCheckpoint:clock,outputRevision:all.length,contentDigest:'6'.repeat(64),restoreGeneration:null,result:{properties:{bgnow:{mean:valid.reduce((n,s)=>n+s.mgdl,0)/valid.length,last:last.mgdl,mills:last.mills,sgvs:valid}}},frame:f}}};
}
const server=http.createServer(async(req,res)=>{
 let raw='';for await(const chunk of req)raw+=chunk;
 const respond=v=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(v));};
 if(req.url==='/synthetic/sql'){
  if(raw.includes('UNION ALL')){const marker=/doc->>'device'='([a-z0-9-]+)'/.exec(raw)[1];res.end(Object.entries(counts(marker)).flatMap(([id,v])=>Object.entries(v).filter(([,n])=>n).map(([kind,n])=>[id,kind,n].join('\t'))).join('\n'));}
  else res.end(tenants.filter(t=>raw.includes(t.id)).map(row).filter(Boolean).map(r=>JSON.stringify(r)).join('\n'));
  return;
 }
 if(req.url==='/synthetic/progress'){
  const ids=JSON.parse(raw);round++;respond({selected:ids,selfOrdinal:0,selfMode:'partitioned',view:{kind:'evaluator',runtimeId:'33333333-3333-4333-8333-333333333333',configured:{ordinal:0,mode:'partitioned'},gate:{eligible:true,reason:null},tenants:ids.map((tenant,i)=>({tenant,admitted:true,ready:true,cycles:round,dueAt:null,dueReason:null,code:null,evaluation:{alert:null},progress:{generation:i+1,completedAcquisitions:round,completedTimeCycles:0,failedCompletions:0,lastCompletedAgeMs:0}}))}});return;
 }
 if(req.url==='/synthetic/calls'){respond(calls);return;}
 const tenant=tenants.find(t=>t.host===req.headers.host?.split(':')[0]);if(!tenant){res.statusCode=403;respond({});return;}
 calls.push({tenant:tenant.id,method:req.method,path:req.url.split('?')[0]});
 if(req.url.includes('/authorization/request/')){respond({token:tenant.id});return;}
 if(req.method==='POST'){
  const body=JSON.parse(raw),values=Array.isArray(body)?body:[body];
  for(const value of values){const doc={...value,_id:'synthetic-'+(++ordinal),_kind:value.device?.endsWith('-probe')?'probe':req.url.includes('devicestatus')?'devicestatus':req.url.includes('treatments')?'treatments':'entries'};docs.get(tenant.id).push(doc);}
  respond([]);io.to(tenant.id).emit('dataUpdate',frame(tenant.id));return;
 }
 respond(req.url.includes('/status.json')?status:[]);
});
const io=new Server(server,{transports:['polling']});
io.on('connection',socket=>socket.on('authorize',(auth,ack)=>{const t=tenants.find(t=>t.id===auth.token);if(!t)return socket.disconnect(true);socket.join(t.id);ack?.({});socket.emit('dataUpdate',frame(t.id));}));
server.listen(0,'127.0.0.1',()=>fs.writeFileSync(path.join(directory,'actor-ready.json'),JSON.stringify({port:server.address().port})));
process.on('SIGTERM',()=>io.close(()=>server.close(()=>process.exit(0))));
