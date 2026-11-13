'use strict';
// Finite loopback-only HTTP fixture. "Commit" is an in-memory synthetic count.
const fs=require('node:fs'),vm=require('node:vm'),http=require('node:http'),assert=require('node:assert/strict');
const {create}=require('./probe-accounting.cjs');
(async()=>{
 const source=fs.readFileSync(process.argv[2],'utf8'),stored={},snapshots=[];
 const server=http.createServer((req,res)=>{
  const id=req.headers.host;let data='';req.on('data',b=>data+=b);req.on('end',()=>{
   assert(data.length<4096);const code=id==='a'?503:id==='b'?200:id==='c'?200:403;
   if(id!=='d')stored[id]=(stored[id]||0)+1;
   if(id==='b')setTimeout(()=>res.end('{}'),150);else{res.statusCode=code;res.end('{}');}
  });
 });
 await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
 const agent=new http.Agent({keepAlive:false});
 try{
  const accounting=create({ids:['a','b','c','d'],runId:'synthetic-loopback',persist:v=>snapshots.push(v)});
  const requestSource=source.slice(source.indexOf('function request ('),source.indexOf('async function exchange ('));
  const context={http,base:new URL('http://127.0.0.1:'+server.address().port),agent,Buffer,Promise};vm.createContext(context);vm.runInContext(requestSource,context);
  const begin=source.indexOf('    const attempt=accounting?'),end=source.indexOf('    await sleep(PROBE);',begin);assert(begin>=0&&end>begin);
  const body=source.slice(begin,end);let statuses=[];
  for(const id of ['a','b','c','d']){
   const writers=[],writes={ok:0,failed:0},byTenant={},e={};
   // Same actual generated callback. Only the request deadline is fixture-sized.
   const request=(...args)=>context.request(...args,40).then(r=>{statuses.push(r.status);return r;});
   const before=snapshots.length;
   vm.runInNewContext(body,{accounting,t:{id,host:id,token:'SYNTHETIC'},writers,writes,byTenant,e,args:{runid:'synthetic-loopback'},date:Date.now(),request,encodeURIComponent,Date});
   assert(snapshots.length>before);assert.equal(snapshots.at(-1).byTenant[id].pending,1); // BEFORE async HTTP
   await Promise.all(writers);
  }
  accounting.close();const ledger=accounting.snapshot();
  assert.deepEqual(statuses,[503,0,200,403]);assert.equal(ledger.byTenant.a.uncertain,1);assert.equal(ledger.byTenant.b.uncertain,1);assert.equal(ledger.byTenant.c.accepted,1);assert.equal(ledger.byTenant.d.refused,1);
  assert.throws(()=>accounting.begin('a'),/ACCOUNTING_INVALID/);assert.throws(()=>accounting.settle(1,200),/ACCOUNTING_INVALID/);
  assert.equal(ledger.attempts,4);assert(Object.values(ledger.byTenant).every(r=>r.pending===0));
  let partial;const open=create({ids:['a'],runId:'partial',persist:v=>partial=v});const ticket=open.begin('a');open.close();assert.equal(partial.admissionsClosed,true);assert.equal(partial.byTenant.a.pending,1);open.settle(ticket,0);assert.equal(partial.byTenant.a.uncertain,1);
  console.log(JSON.stringify({scope:'actual generated HTTP+callback; recording persistence only, no PG',ledger,stored,statuses,partialPendingPreserved:true,strictCallback:source.includes("if (r.status === 200) { writes.ok++;")}));
 }finally{agent.destroy();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
