'use strict';
// Actual generated probe, harmless HTTP/socket/fs/process recording ports only.
const vm=require('node:vm');const fs=require('node:fs');const assert=require('node:assert/strict');
async function run(source,{purpose='discovery',exchange=503,custody=false,clinical=false,foreign=false}={}){
  let now=1000000;const files=new Map([['/tenants',JSON.stringify([{id:'tenant-a',host:'a.invalid',token:'SYNTHETIC'}])]]);let exit;
  const completion=new Promise(resolve=>{exit=resolve;});
  class DatePort extends Date{constructor(...a){super(...(a.length?a:[now]));}static now(){return now;}}
  const http={Agent:class{},request(options,callback){const handlers={};return {on(name,fn){handlers[name]=fn;},end(){queueMicrotask(()=>callback({statusCode:exchange,resume(){},on(name,fn){if(name==='data')queueMicrotask(()=>fn(JSON.stringify({token:'synthetic-jwt'})));if(name==='end')queueMicrotask(fn);}}));},destroy(){}};},get(options,callback){const req=this.request(options,callback);req.end();return req;}};
  const child={execFile(program,args,opts,cb){if(typeof opts==='function'){cb=opts;opts={};}queueMicrotask(()=>cb(null,program==='python'?JSON.stringify({verdict:clinical||foreign?'FAIL':'UNMEASURED',code:foreign?'M7_EVALUATOR_PROGRESS_FOREIGN':clinical?'M7_EVALUATOR_PROGRESS_ERROR':'M7_EVALUATOR_RECOVERY_NOT_OBSERVED'}):''));return {stdin:{end(){}}};}};
  const io=()=>({on(){},emit(){},connect(){},close(){}});
  const fakeFs={readFileSync(file){assert(files.has(file),'unexpected read '+file);return files.get(file);},writeFileSync(file,body){files.set(file,body);},existsSync(file){return file.endsWith('/.restart')||files.has(file);}};
  const context={require(name){if(name==='node:fs')return fakeFs;if(name==='node:path')return require('node:path');if(name==='node:http')return http;if(name==='node:child_process')return child;if(name==='socket.io-client')return {io};if(name==='./restart.cjs')return {restart:async()=>{if(custody)throw Error('M7_RESTART_NOT_OBSERVED');return {starts:{api:{startedAt:'synthetic'}},commandMs:1};}};throw Error('unexpected require '+name);},process:{argv:['node','probe','--base','http://127.0.0.1:1','--tenants','/tenants','--compose','synthetic|/env|/compose','--signal','/out/.window','--out','/out/probe.json','--per','2','--open','5','--restart',custody||clinical||foreign?'1':'0','--evalTimeout','1'],env:{M7_RUN_PURPOSE:purpose,M7_RESTART_ROLES:'["api"]',M7_EVALUATOR_SERVICES:'["evaluator"]',M7_PROGRESS_PYTHON:'python',M7_PROGRESS_ATTRIBUTION:'{}',STOCK_MS:'1',RECOVERY_MS:'1'},exit(code){exit(code);}},__dirname:'/out',Date:DatePort,URL,Buffer,Map,Set,console:{log(){},error(){}},setTimeout(fn,ms){now+=ms;queueMicrotask(fn);}};
  vm.runInNewContext(source,context,{timeout:1000});const code=await completion;return {code,files,out:JSON.parse(files.get('/out/probe.json')||'null')};
}
(async()=>{
  const source=fs.readFileSync(process.argv[2],'utf8');
  const discovery=await run(source);assert.equal(discovery.code,0);assert(discovery.files.has('/out/.window'));assert.equal(discovery.out.exchangeUnavailable.length,1);assert.equal(discovery.out.prime.primed,0);assert(discovery.out.window);
  const strict=await run(source,{purpose:'acceptance'});assert.equal(strict.code,1);assert(!strict.files.has('/out/.window'));assert.equal(strict.out,null);
  const dark=await run(source,{exchange:200});assert.equal(dark.code,0);assert(dark.files.has('/out/.window'));assert.equal(dark.out.prime.dark,2);
  const custody=await run(source,{exchange:200,custody:true});assert.equal(custody.code,1);assert(custody.out.window);assert.equal(custody.out.hardFailure.code,'M7_RESTART_NOT_OBSERVED');
  const clinical=await run(source,{exchange:200,clinical:true});assert.equal(clinical.code,0);assert(clinical.out.window);assert.equal(clinical.out.restart.runtimeAcquisitionObservation.verdict,'FAIL');assert(!clinical.out.hardFailure);
  const foreign=await run(source,{exchange:200,foreign:true});assert.equal(foreign.code,1);assert.equal(foreign.out.hardFailure.code,'M7_EVALUATOR_PROGRESS_FOREIGN');
  console.log(JSON.stringify({controls:6,discoveryPrimeIncompleteSignals:true,strictPrimeStops:true,darkSocketsObserved:true,custodyRefusesWithPartial:true,workFailurePreservedAsObservation:true,foreignFailRefusesWithPartial:true}));
})().catch(error=>{console.error(error);process.exitCode=1;});
