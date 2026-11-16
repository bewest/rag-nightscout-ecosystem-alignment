'use strict';
// Actual receiver + request streams, no sockets, database or service actors.
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict'),Module=require('node:module');
const {PassThrough}=require('node:stream'),{EventEmitter}=require('node:events');
const helper=path.join(__dirname,'clinical-intake-timeline.cjs'),root=path.resolve(process.argv[2]);
const A='11111111-1111-4111-8111-111111111111',B='22222222-2222-4222-8222-222222222222';
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'clinical-raw-control-'));let counter=0;
function load(mode){if(mode==='restored')return require(helper);const source=fs.readFileSync(helper,'utf8'),broken=new Module(helper,module);broken.filename=helper;broken.paths=module.paths;let changed=source;
 if(mode==='late')changed=source.replace("rawTap.emit('raw-entry',m,","if(m.target)rawTap.emit('raw-entry',m,");
 if(mode==='swallow')changed=source.replace("req.once('aborted',()=>rawTap.emit('raw-request-aborted',m));","req.once('aborted',()=>{});");
 if(mode==='forward')changed=source.replace("return context.run(m,()=>Reflect.apply(handler,this,[req,res]));","return context.run(m,()=>{Reflect.apply(handler,this,[req,res]);return undefined;});");
 if(mode==='saturation')changed=source.replace('dropped++;return;','return;');
 assert.notEqual(changed,source);broken._compile(changed,helper);return broken.exports;}
async function run(mode='restored',rawEnabled=true,rawOptions={}){
 const prefix=path.join(directory,String(++counter)),raw=prefix+'-raw.jsonl',trace=prefix+'-selected.jsonl';
 delete require.cache[require.resolve(path.join(root,'lib/pgstream/receiver.js'))];const receiver=require(path.join(root,'lib/pgstream/receiver.js'));
 const http={createServer:handler=>({handler})};let admissions=0,received=0,release;
 const held=new Promise(resolve=>release=resolve);
 const tap=load(mode).install({file:trace,ids:[A,B],http,receiver,...(rawEnabled?{raw:{file:raw,...rawOptions}}:{})});
 const receive=receiver.create({routes:[{schema:'synthetic',table:'tenant_write_clock',kind:'clock'}],store:{observe(id){admissions++;return id===A?held:Promise.resolve({observed:{clock:'2'},completed:{clock:'1'},pendingAt:1});}},onInput(){received++;},onSchema(){}});
 let calls=0,lastReturn;const binding={original:true};
 const server=http.createServer(function(req,res){assert.equal(this,binding,'HANDLER_THIS');calls++;const result=(async()=>{try{let body='';for await(const chunk of req)body+=chunk;const event=receiver.parse(body);await receive(event);res.statusCode=204;}catch{res.statusCode=503;}res.writableFinished=true;res.emit('finish');res.emit('close');})();lastReturn=result;return result;});
 function request(text,lsn='0/100',abort=false){const req=new PassThrough();Object.assign(req,{method:'POST',url:'/pgstream',headers:{'x-pgstream-lsn':lsn,'idempotency-key':lsn,authorization:'DO_NOT_EMIT_AUTH_SECRET'},complete:false,aborted:false});const res=new EventEmitter();Object.assign(res,{statusCode:200,writableFinished:false});const returned=Reflect.apply(server.handler,binding,[req,res]);assert.equal(returned,lastReturn,'HANDLER_RETURN_IDENTITY');assert.equal(req.listenerCount('data'),0,'NO_EXTRA_BODY_READER');assert.equal(req.listenerCount('error'),1,'ONLY_ASYNC_ITERATOR_ERROR_OBSERVER');if(abort){req.aborted=true;req.emit('aborted');req.destroy(new Error('DO_NOT_EMIT_ERROR_SECRET'));}else{req.complete=true;req.end(text);}return{returned,res,req};}
 const event=id=>JSON.stringify({Data:{action:'U',schema:'synthetic',table:'tenant_write_clock',lsn:'0/100',columns:[{name:'tenant_id',value:id},{name:'last_stamp',value:'2'}]}});
 const malformed=request('{broken','DO_NOT_EMIT_HEADER_SECRET');await malformed.returned;
 const aborted=request('', '0/100',true);await aborted.returned;
 const target=request(event(A));await new Promise(r=>setImmediate(r));assert.equal(target.res.writableFinished,false,'ACK_MUST_WAIT_FOR_ADMISSION');assert.equal(admissions,1,'ONE_ADMISSION_PER_REQUEST');release({observed:{clock:'2'},completed:{clock:'1'},pendingAt:1});await target.returned;
 const duplicate=request(event(A));await duplicate.returned;assert.equal(admissions,2,'DUPLICATE_MUST_REENTER_ADMISSION');
 await tap.seal();const rows=rawEnabled?fs.readFileSync(raw,'utf8').trim().split('\n').filter(Boolean).map(JSON.parse):[];
 return{rows,status:tap.rawStatus(),outcomes:[malformed.res.statusCode,aborted.res.statusCode,target.res.statusCode,duplicate.res.statusCode],calls,admissions,received,raw};
}
async function malformedForwarding(){
 delete require.cache[require.resolve(path.join(root,'lib/pgstream/receiver.js'))];const receiver=require(path.join(root,'lib/pgstream/receiver.js')),http={createServer:handler=>({handler})},prefix=path.join(directory,String(++counter));
 const tap=load('restored').install({file:prefix+'-selected.jsonl',ids:[A,B],http,receiver,raw:{file:prefix+'-raw.jsonl'}});
 const receive=receiver.create({routes:[{schema:'synthetic',table:'tenant_write_clock',kind:'clock'}],store:{observe(){throw Error('MUST_NOT_ADMIT_MALFORMED');}},onInput(){},onSchema(){}});let original;
 const server=http.createServer(function(req,res){original=receive(req.event);return original;});
 for(const columns of [{},[null]]){const req=new EventEmitter(),res=new EventEmitter();Object.assign(req,{method:'POST',url:'/pgstream',headers:{},event:{Data:{action:'U',schema:'synthetic',table:'tenant_write_clock',columns}}});const result=server.handler(req,res);assert.equal(result,original,'MALFORMED_ORIGINAL_PROMISE');await assert.rejects(result,{code:'PGSTREAM_EVENT_COLUMNS'});res.statusCode=503;res.emit('close');}
 const originalError=Error('same exception');const throwing=http.createServer(()=>{throw originalError;});const req=new EventEmitter(),res=new EventEmitter();Object.assign(req,{method:'POST',url:'/pgstream',headers:{}});assert.throws(()=>throwing.handler(req,res),error=>error===originalError,'HANDLER_EXCEPTION_IDENTITY');res.emit('close');await tap.seal();
}
function criterion(result){const rows=result.rows;for(const request of [1,2,3,4])assert(rows.some(r=>r.phase==='raw-entry'&&r.request===request),'UNPARSED_ENTRY_COVERAGE');assert(rows.some(r=>r.phase==='raw-request-aborted'&&r.request===2),'ABORTED_COVERAGE');assert(!rows.some(r=>r.phase==='raw-parsed-target'&&r.request<=2),'UNPARSED_NOT_TARGET');assert(rows.some(r=>r.phase==='raw-parsed-target'&&r.request===3),'LATER_TARGET_JOIN');assert.equal(rows.find(r=>r.request===1).headerLsn,'INVALID');assert.equal(new Set(rows.filter(r=>r.phase==='raw-entry').map(r=>r.request)).size,4,'RETRY_REQUEST_IDENTITY');assert(!JSON.stringify(rows).includes('DO_NOT_EMIT'),'SAFE_FIXED_PROJECTION');assert.equal(result.status.qualification,'COMPLETE');}
(async()=>{
 await malformedForwarding();
 const baseline=await run('restored',false),good=await run();criterion(good);assert.deepEqual(good.outcomes,baseline.outcomes);assert.deepEqual([good.calls,good.admissions,good.received],[baseline.calls,baseline.admissions,baseline.received]);
 for(const mode of ['late','swallow']){const broken=await run(mode);assert.throws(()=>criterion(broken),{code:'ERR_ASSERTION'},mode+'_MUST_BE_RED');criterion(await run());}
 await assert.rejects(run('forward'),{code:'ERR_ASSERTION'},'FORWARDING_CHANGE_MUST_BE_RED');criterion(await run());
 const bounded=await run('restored',true,{maxRows:1});assert(bounded.status.dropped>0);assert.equal(bounded.status.qualification,'UNMEASURED');const noRefusal=await run('saturation',true,{maxRows:1});assert.throws(()=>assert.equal(noRefusal.status.qualification,'UNMEASURED'),{code:'ERR_ASSERTION'},'SATURATION_ABLATION_RED');criterion(await run());
 for(const bound of [{maxBytes:1},{maxPending:1}]){const limited=await run('restored',true,bound);assert(limited.status.dropped>0);assert.equal(limited.status.qualification,'UNMEASURED');}criterion(await run());
 const originalWrite=fs.write;fs.write=function(fd,text,offset,encoding,callback){return originalWrite.call(this,fd,text,offset,encoding,(error,written)=>callback(error,written-1));};let short;try{short=await run();}finally{fs.write=originalWrite;}assert.equal(short.status.qualification,'UNMEASURED');assert.equal(short.status.failed,'WRITE_REFUSED');criterion(await run());
 console.log(JSON.stringify({status:'PASS',scope:'source-only actual receiver and streams; no network/SUT',controls:['unparsed immediate entry','abort before target parse','later request-ID target join','duplicate own admission','ACK after original promise','handler this/args/return forwarding','no extra data/error consumer','safe projection','bounded saturation/short write refuse qualification','late/abort/forwarding/saturation red and restored'],normal:good.status}));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
