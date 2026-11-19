'use strict';
// Execute the actual generated probe with loopback HTTP and synthetic SQL/socket
// process boundaries. This qualifies adapter wiring, not app/cluster behavior.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),http=require('node:http'),assert=require('node:assert/strict'),{EventEmitter}=require('node:events'),{createHash}=require('node:crypto'),{createRequire}=require('node:module');
(async()=>{
 const target=path.resolve(process.argv[2]),d=path.dirname(target),realRequire=createRequire(target),o=realRequire('./completed-oracle.cjs');
 const unavailable=process.argv[3]==='sql-unavailable';
 const ids=['11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222'];
 const tenants=ids.map((id,i)=>({id,host:(i?'b':'a')+'.example.test',token:'synthetic-'+i}));
 const binding={kind:'evaluator-work-v2',pair:{core:'1'.repeat(40),deploy:'2'.repeat(40)},imageId:'sha256:'+'3'.repeat(64),instrument:'4'.repeat(64)};
 const config=o.source({pgstream:{},consumer:'evaluator-sample',postgres:{namespaces:{clock:'synthetic_clock',checkpoint:'synthetic_checkpoint',entries:'synthetic_entries'}}},{completedOutput:{namespace:'synthetic_checkpoint',consumer:'evaluator-sample'}},binding);
 const stored=new Map(ids.map(t=>[t,[]])),sockets=[];let ordinal=0,queries=0;
 const server=http.createServer((req,res)=>{
   const tenant=tenants.find(t=>t.host===req.headers.host);assert(tenant);
   if(req.url.startsWith('/api/v2/authorization/request/')){res.end(JSON.stringify({token:'synthetic-jwt'}));return;}
   let body='';req.on('data',v=>body+=v);req.on('end',()=>{
     const doc={...JSON.parse(body)[0],_id:'synthetic-stored-'+(++ordinal)};stored.get(tenant.id).push(doc);res.end('{}');
     for(const socket of sockets.filter(s=>s.tenant===tenant.id))socket.deliver('dataUpdate',{sgvs:[{_id:doc._id,mills:doc.date,mgdl:doc.sgv}]});
   });
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 function row(tenant){
   const docs=stored.get(tenant),last=docs.at(-1);if(!last)return null;
   const clock=String(docs.length),sgv={_id:last._id,mills:last.date,mgdl:last.sgv},observed=[clock,null,null,null,null,null];
   return {tenant,stamp:clock,reader:binding,stored:docs,typed:{version:2,contractDigest:createHash('sha256').update(JSON.stringify(['evaluator-work-v2','synthetic_checkpoint','evaluator-sample'])).digest('hex'),observed,completed:observed,identity:'5'.repeat(64),digest:'6'.repeat(64),revision:clock,generation:null,enabled:true,arrayBounds:true,bodyMetadataAbsent:true},
     state:{kind:'evaluator-work-v2',observed:{clock},completed:{clock},output:{tenant,identity:'5'.repeat(64),inputCheckpoint:clock,outputRevision:docs.length,contentDigest:'6'.repeat(64),restoreGeneration:null,result:{properties:{bgnow:{mean:last.sgv,last:last.sgv,mills:last.date,sgvs:[sgv]}}},frame:{sgvs:[sgv]}}}};
 }
 const io=url=>{
   const tenant=tenants.find(t=>t.host===new URL(url).hostname),s=new EventEmitter();s.id='synthetic-transport-'+tenant.id;s.tenant=tenant.id;s.deliver=s.emit.bind(s);s.close=()=>{};
   s.emit=(event,...args)=>{if(event==='authorize'){queueMicrotask(()=>s.deliver('dataUpdate',{sgvs:[]}));return true;}return s.deliver(event,...args);};
   sockets.push(s);queueMicrotask(()=>s.deliver('connect'));return s;
 };
 fs.writeFileSync(path.join(d,'tenants.json'),JSON.stringify(tenants));
 const argv=['node',target,'--base','http://127.0.0.1:'+server.address().port,'--tenants',path.join(d,'tenants.json'),'--runid','synthetic-pipeline','--per','1','--clients','2','--open','0','--probeEvery','1','--maxWrites','2','--restart','0','--out',path.join(d,'probe.json'),'--signal',path.join(d,'.window')];
 const child={execFile(exe,args,opts,callback){assert.equal(exe,'synthetic-python');assert.equal(args[1],'clinical-sql');assert.equal(opts.timeout,60000);queries++;return {stdin:{end(query){assert(query.startsWith('SELECT '));if(unavailable){setImmediate(()=>callback(Object.assign(Error('observer unavailable'),{code:1}),'',''));return;}setImmediate(()=>callback(null,ids.map(row).filter(Boolean).map(r=>JSON.stringify(r)).join('\n')));}}};}};
 let watchdog;
 try{
   await new Promise((resolve,reject)=>{
     watchdog=setTimeout(()=>reject(Error('SYNTHETIC_PROBE_TIMEOUT')),10000);
     const fakeProcess={argv,env:{M7_RUN_PURPOSE:'discovery',M7_COMPLETION_SOURCE:JSON.stringify(config),K8S_PYTHON:'synthetic-python',K8S_ADAPTER:'synthetic-adapter',K8S_RUN_DIRECTORY:d},once(){},exit(code){code?reject(Error('GENERATED_PROBE_EXIT_'+code)):resolve();}};
     const require_=name=>name==='socket.io-client'?{io}:name==='node:child_process'?child:realRequire(name);
     const context={require:require_,process:fakeProcess,console:{log(){},error:reject},__dirname:d,Buffer,URL,performance,setTimeout:(f,ms)=>setTimeout(f,Math.min(ms,10)),clearTimeout,setImmediate};
     vm.runInNewContext(fs.readFileSync(target,'utf8'),context,{filename:target});
   });
   const probe=JSON.parse(fs.readFileSync(path.join(d,'probe.json'))),ledger=JSON.parse(fs.readFileSync(path.join(d,'probe-accounting.json')));
   if(process.argv[4]){
     fs.writeFileSync(process.argv[4],JSON.stringify({config,stored:Object.fromEntries([...stored].map(([id,docs])=>[id,{probe:docs.length}]))}));
   }
   if(unavailable){
     assert.equal(probe.completedOutput.verdict,'UNMEASURED');
     assert.equal(probe.completedOutput.observerFailure.code,'M7_PROBE_SQL_OBSERVATION_UNAVAILABLE');
     assert.equal(ledger.admissionsClosed,true);assert(ledger.attempts>0);
     assert.equal(probe.window.writes.ok,ledger.attempts);assert.equal(probe.window.deliveredFrames,ledger.attempts);
     assert.equal(probe.window.evaluationMissedWithin120s,null);
     console.log(JSON.stringify({clinical:probe.completedOutput.verdict,attempts:ledger.attempts,frames:probe.window.deliveredFrames,queries}));
     return;
   }
   assert.equal(probe.completedOutput.verdict,'PASS');assert.equal(probe.completedOutput.witnesses.length,2);assert.equal(ledger.attempts,2);assert.equal(probe.window.deliveredFrames,2);assert(queries>0);
   process.argv[2]=path.join(__dirname,'../m7-joined/completed-oracle.cjs');const {assess}=require('./claims.cjs');
   assert.equal(assess({completion:config,probe,tenants,clients:2}).verdict,'PASS');
   console.log('PASS actual generated probe -> raw SQL/stored/clinical/client-frame/accounting wiring; synthetic SQL/socket boundaries, loopback HTTP only');
 }finally{clearTimeout(watchdog);server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
