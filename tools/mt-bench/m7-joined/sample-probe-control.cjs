'use strict';
// Exercise the generated probe's real HTTP callback/poller/frame join through
// recording ports. No real HTTP listener, socket, SQL, process or Docker call.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict'),oracle=require('./completed-oracle.cjs'),lag=require('./durable-lag.cjs');
const binding={kind:'evaluator-work-v1',pair:{core:'1'.repeat(40),deploy:'2'.repeat(40)},imageId:'sha256:'+'3'.repeat(64),instrument:'4'.repeat(64)};
const tenant='11111111-1111-4111-8111-111111111111';
async function run(source,{dropClient=false,dropCompletion=false}={}){
 let now=1000000,stamp=0,stored=[],sql=0;const peers=[],files=new Map([['/tenants',JSON.stringify([{id:tenant,host:'a.invalid',token:'synthetic'}])]]);let resolve;
 const done=new Promise(r=>{resolve=r;});
 class Clock extends Date{constructor(...v){super(...(v.length?v:[now]));}static now(){return now;}}
 const http={Agent:class{},request(options,callback){return{on(){return this;},destroy(){},end(body){let frame;
  if(options.method==='POST'){
   const doc={...JSON.parse(body)[0],_id:'synthetic-'+(++stamp)};stored.push(doc);frame={sgvs:[{_id:doc._id,mills:doc.date,mgdl:doc.sgv}]};
  }
  queueMicrotask(()=>{const response={statusCode:200,on(event,fn){if(event==='data')queueMicrotask(()=>fn(JSON.stringify({token:'synthetic'})));if(event==='end')queueMicrotask(fn);}};callback(response);
   if(frame&&!dropClient)queueMicrotask(()=>{for(const peer of peers)peer.handlers.dataUpdate(frame);});
  });
 }};}};
 const io=()=>{const peer={id:'synthetic-transport-'+peers.length,handlers:{},on(event,fn){this.handlers[event]=fn;return this;},emit(){},close(){}};peers.push(peer);queueMicrotask(()=>{peer.handlers.connect();peer.handlers.dataUpdate({sgvs:[]});});return peer;};
 const child={execFile(program,args,options,callback){sql++;const row={tenant,reader:binding,stamp:String(stamp),stored,state:{kind:'evaluator-work-v1',observed:{clock:String(stamp)},completed:{clock:dropCompletion?'0':String(stamp)},output:{tenant,inputCheckpoint:String(stamp),outputRevision:Math.max(1,stamp),contentDigest:'a'.repeat(64),result:{properties:{bgnow:{mean:stored.length?stored.reduce((sum,doc)=>sum+doc.sgv,0)/stored.length:0,last:stored.at(-1)?.sgv,mills:stored.at(-1)?.date,sgvs:stored.map(doc=>({_id:doc._id,mills:doc.date,mgdl:doc.sgv}))}}},rows:stored.map(doc=>({domain:'entries',doc})),frame:{sgvs:stored.map(doc=>({_id:doc._id,mills:doc.date,mgdl:doc.sgv}))}}}};queueMicrotask(()=>callback(null,JSON.stringify(row)+'\n'));}};
 const fakeFs={readFileSync(file){assert(files.has(file));return files.get(file);},writeFileSync(file,value){files.set(file,value);},existsSync(file){return file.endsWith('/.restart')?now>=1010000:files.has(file);}};
 const context={performance:{now:()=>now},Date:Clock,Buffer,URL,Map,Set,Object,Promise,console:{log(){},error(){}},setTimeout(fn,ms){now+=ms;queueMicrotask(fn);},process:{argv:['node','probe','--base','http://127.0.0.1:1','--tenants','/tenants','--compose','synthetic|/env|/compose','--runid','synthetic-run','--per','2','--open','0','--probeEvery','300000','--restart','0','--out','/out/probe.json','--signal','/out/.window'],env:{M7_COMPLETION_SOURCE:JSON.stringify({clock:'synthetic_clock',checkpoint:'synthetic_checkpoint',entries:'synthetic_entries',consumer:'evaluator-synthetic-completed',kind:'evaluator-work-v1',binding})},exit(code){resolve(code);}},require(name){if(name==='node:fs')return fakeFs;if(name==='node:path')return require('node:path');if(name==='node:http')return http;if(name==='node:child_process')return child;if(name==='socket.io-client')return{io};if(name==='./completed-oracle.cjs')return oracle;if(name==='./durable-lag.cjs')return lag;throw Error('Unexpected require '+name);}};
 vm.runInNewContext(source,context,{timeout:1000});const exit=await done;assert.equal(exit,0);assert(sql>0);return JSON.parse(files.get('/out/probe.json'));
}
(async()=>{
 const source=fs.readFileSync(process.argv[2],'utf8');
 const observed=value=>{assert.equal(value.completedOutput.verdict,'PASS');assert(value.durableOutputObservation.durableUpperMs.n>0,'durable observation missing');assert.equal(value.durableOutputObservation.missing,0);};
 observed(await run(source));
 const noClient=await run(source,{dropClient:true});assert.equal(noClient.completedOutput.verdict,'FAIL');assert(noClient.durableOutputObservation.durableUpperMs.n>0);
 const noCompletion=await run(source,{dropCompletion:true});assert.equal(noCompletion.completedOutput.verdict,'FAIL');assert.equal(noCompletion.durableOutputObservation.durableUpperMs.n,0);
 const anchor='lag.observe(e,durable,queryStart,queryEnd);';assert.equal(source.split(anchor).length,2);
 const noObservation=await run(source.replace(anchor,''));assert.throws(()=>observed(noObservation),/durable observation missing/);
 observed(await run(source));
 console.log('GREEN actual generated probe join; EXPECTED_RED client/completion/durable observer suppression; RESTORED_GREEN; recording ports only');
})().catch(e=>{console.error(e);process.exitCode=1;});
