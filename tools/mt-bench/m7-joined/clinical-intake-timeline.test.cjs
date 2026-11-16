'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict'),{EventEmitter}=require('node:events');
const {install}=require('./clinical-intake-timeline.cjs');
const source=path.resolve(process.argv[2],'lib/pgstream/receiver.js');
const A='11111111-1111-4111-8111-111111111111',B='22222222-2222-4222-8222-222222222222';
async function scenario(file,maxRows){
 delete require.cache[require.resolve(source)];const receiver=require(source);let clientId=40,release;const held=new Promise(resolve=>{release=resolve;});
 class Client{constructor(){this.processID=++clientId;}query(text){const p=text.includes('FOR UPDATE')&&this.held?held:Promise.resolve({command:text});this.last=p;return p;}}
 class Pool{connect(){const p=Promise.resolve(new Client());this.last=p;return p;}}
 let timerReturned,runReturned,beginReturned,completeReturned;
 const scheduler={start:options=>({wake(){const value=options.setTimer(()=>{},0);assert.equal(value,timerReturned,'TIMER_HANDLE_IDENTITY');return value;},run:options.run})};
 const begin=()=>{beginReturned=Promise.resolve({clock:'2'});return beginReturned;},complete=()=>{completeReturned=Promise.resolve({changed:true});return completeReturned;};
 const runtime={exports:options=>{const b=options.durable.begin(B);assert.equal(b,beginReturned,'DURABLE_BEGIN_PROMISE_IDENTITY');const c=options.durable.complete(B,{observed:{clock:'2'}});assert.equal(c,completeReturned,'DURABLE_COMPLETE_PROMISE_IDENTITY');return 'runtime-original-return';}};
 const http={createServer:handler=>({handler})},pg={Pool,Client};const tap=install({file,ids:[A,B],http,pg,receiver,scheduler,runtime,maxRows});
 const scheduled=scheduler.start({setTimer:()=>{timerReturned={existing:true};return timerReturned;},run:()=>{runReturned=Promise.resolve();return runReturned;}});
 assert.equal(runtime.exports({durable:{begin,complete}}),'runtime-original-return','RUNTIME_FACTORY_RETURN_IDENTITY');
 const running=scheduled.run(B,'clock');assert.equal(running,runReturned,'SCHEDULER_RUN_PROMISE_IDENTITY');const pool=new Pool();
 const receives=[];const receive=receiver.create({routes:[{schema:'synthetic',table:'tenant_write_clock',kind:'clock'}],store:{observe:async(id)=>{
  const connected=pool.connect();assert.equal(connected,pool.last,'POOL_PROMISE_IDENTITY');const client=await connected;client.held=id===A;
  for(const sql of ['BEGIN','SELECT work_observed FOR UPDATE','WITH input AS UPDATE','COMMIT']){const p=client.query(sql);assert.equal(p,client.last,'QUERY_PROMISE_IDENTITY');await p;}
  return {observed:{clock:'2'},completed:{clock:'1'},pendingAt:1};}},onInput:id=>{receives.push(id);scheduled.wake();return 'unchanged';},onSchema:()=>{}});
 let originalReturn;const server=http.createServer((req,res)=>{const p=receive(req.event);originalReturn=p;p.then(()=>{res.statusCode=204;res.writableFinished=true;res.emit('finish');res.emit('close');});return p;});
 function request(id,lsn){const req={method:'POST',url:'/pgstream',headers:{'x-pgstream-lsn':lsn,'idempotency-key':lsn},event:{Data:{action:'U',schema:'synthetic',table:'tenant_write_clock',lsn,columns:[{name:'tenant_id',value:id},{name:'last_stamp',value:'2'}],identity:null}}};const res=new EventEmitter();res.statusCode=200;res.destroyed=false;res.writableFinished=false;const result=server.handler(req,res);assert.equal(result,originalReturn,'HTTP_HANDLER_RETURN_IDENTITY');return{result,res};}
 const unrelated=request('33333333-3333-4333-8333-333333333333','0/999');await unrelated.result;const a=request(A,'0/100'),b=request(B,'0/200');await new Promise(r=>setImmediate(r));await new Promise(r=>setImmediate(r));assert.equal(a.res.writableFinished,false);assert.equal(b.res.writableFinished,true,'B_PERSISTS_WHILE_A_HELD');release();await Promise.all([a.result,b.result]);const status=await tap.seal();const rows=fs.readFileSync(file,'utf8').trim().split('\n').map(JSON.parse);return{status,rows};
}
(async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'clinical-intake-hook-'));
 const good=await scenario(path.join(dir,'normal.jsonl'),256);assert.equal(good.status.pending,0);assert.equal(good.status.dropped,0);assert.equal(good.status.failed,null);assert.equal(good.status.written,good.status.rows);
 const b=good.rows.filter(r=>r.tenant===B);const c=b.find(r=>r.phase==='observe-commit-return'),h=b.find(r=>r.phase==='hint-call'),f=b.find(r=>r.phase==='http-finish');assert(c&&h&&f&&c.sequence<h.sequence&&h.sequence<f.sequence,'COMMIT_HINT_ACK_ORDER');assert(b.filter(r=>r.request).every(r=>r.dataLsn==='0/200'&&r.headerLsn==='0/200'&&r.idempotency==='0/200'),'EXACT_LSN_BINDING');assert(!good.rows.some(r=>r.tenant==='33333333-3333-4333-8333-333333333333'),'UNRELATED_TENANT_MUST_NOT_CONSUME_TRACE');for(const phase of ['scheduler-timer-set','scheduler-run-call','durable-begin-return','durable-complete-return'])assert(good.rows.some(r=>r.phase===phase),'REQUIRED_'+phase);
 const limited=await scenario(path.join(dir,'bounded.jsonl'),2);assert(limited.status.dropped>0);assert(limited.status.bytes<=131072);assert.throws(()=>assert.equal(limited.status.dropped,0,'NO_DROPPED_TRACE'),/NO_DROPPED_TRACE/);
 console.log(JSON.stringify({status:'PASS',scope:'fixture event-tap controls; no network/database/container actors',normal:good.status,overflow:limited.status,controls:['original Promise/HTTP handler return identity','independent B survives A hold','commit→hint→ACK ordering','Data/header/idempotency LSN binding','overflow refuses qualification without changing caller completion','two-target-only trace','scheduler/timer/runtime/durable Promise return identities','actual durable begin/completion vector and scheduling phases']}));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
