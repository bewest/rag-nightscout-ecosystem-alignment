'use strict';
// Actual pinned receiver factory; finite synthetic ports, no actors.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm'),{EventEmitter}=require('node:events');
const root=path.resolve(process.argv[2]),A='11111111-1111-4111-8111-111111111111',B='30000397-3333-4333-8333-000000000397';
const helper=path.join(__dirname,'clinical-intake-timeline.cjs'),text=fs.readFileSync(helper,'utf8');
function version(broken){if(!broken)return require(helper);const m={exports:{}};const source=text.replace('if(clinical){','if(false&&clinical){');assert.notEqual(source,text);vm.runInNewContext(source,{require,module:m,exports:m.exports,process,Buffer,setImmediate},{filename:helper});return m.exports;}
async function scenario(broken){
 const receiverFile=path.join(root,'lib/pgstream/receiver.js');delete require.cache[require.resolve(receiverFile)];const receiver=require(receiverFile);const file=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'materializer-tap-')),'events.jsonl');
 let latest,thrown;class Client{constructor(){this.processID=40;}query(){return Promise.resolve({});}}class Pool{connect(){return Promise.resolve(new Client());}}
 const pool=new Pool(),store=Object.freeze({consumer:'fixture',digest:'synthetic'});let called=0;
 class Port{#brand=1;constructor(){this.accept=function(tenant,data,domain,gotStore){assert.equal(this,clinical,'ORIGINAL_THIS');assert.equal(this.brand,1);assert.equal(gotStore,store,'ORIGINAL_STORE');assert.equal(domain,undefined);called++;if(thrown)throw thrown;latest=(async()=>{const c=await pool.connect();await c.query('BEGIN');await c.query('SELECT work_observed FOR UPDATE');await c.query('COMMIT');return {observed:{clock:'2'},completed:{clock:'1'},pendingAt:1};})();return latest;};}get brand(){return this.#brand;}}
 const clinical=Object.freeze(new Port()),http={createServer:handler=>({handler})};const tap=version(broken).install({file,ids:[A,B],receiver,http,pg:{Pool,Client}});
 // Capture the forwarded port once to exercise exact Promise identity directly.
 let captured;const factory={create:options=>{captured=options;return ()=>{};}},directFile=file+'.direct';const direct=version(broken).install({file:directFile,ids:[A,B],receiver:factory,http:{createServer:h=>h}});factory.create({store,clinical,onInput:()=>{}});const forwarded=captured.clinical;const event={};const promise=forwarded.accept(B,event,undefined,store);assert.equal(promise,latest,'ORIGINAL_ACCEPT_PROMISE');assert.equal(Object.getPrototypeOf(forwarded),Object.getPrototypeOf(clinical));assert.equal(Object.isFrozen(forwarded),true);await promise;await direct.seal();called=0;
 const receive=receiver.create({routes:[{schema:'synthetic',table:'tenant_write_clock',kind:'clock'}],store,clinical,onInput:()=>{},onSchema:()=>{}});
 async function request(tenant){const req={method:'POST',url:'/pgstream',headers:{},event:{Data:{action:'U',schema:'synthetic',table:'tenant_write_clock',lsn:'0/100',xid:1,columns:[{name:'tenant_id',value:tenant},{name:'last_stamp',value:'2'}]}}};const res=new EventEmitter();const server=http.createServer((req,res)=>receive(req.event).then(v=>{res.statusCode=204;res.writableFinished=true;res.emit('finish');return v;}));return server.handler(req,res);}
 await request(B);assert.equal(called,1);assert(Object.isFrozen(clinical));assert.equal(clinical.brand,1);
 thrown=Object.assign(Error('sentinel'),{code:'SENTINEL'});await assert.rejects(request(B),e=>e===thrown,'ORIGINAL_THROW_IDENTITY');thrown=null;await request(A);await new Promise(r=>setImmediate(r));await tap.seal();const rows=fs.readFileSync(file,'utf8').trim().split('\n').map(JSON.parse);return rows;
}
function criterion(rows){const b=rows.filter(r=>r.tenant===B);const phases=b.map(r=>r.phase);for(const p of ['http-arrival','parsed-clock','observe-call','pool-checkout-call','pool-checkout-return','query-call','query-return','observe-commit-return','hint-call','http-finish'])assert(phases.includes(p),'MATERIALIZER_RECEIPT_STAGE_'+p);assert(b.find(r=>r.phase==='observe-commit-return').sequence<b.find(r=>r.phase==='hint-call').sequence);}
async function sourceControl(){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'timeline-source-')),target=path.join(dir,'targets.json');
 const files=['lib/pgstream/receiver.js','lib/pgstream/activity-scheduler.js','lib/server/serve/evaluator-runtime.js','lib/storage/clinical-stream-sql.js','lib/server/serve/evaluator-preview.js'];
 const sourceFiles=Object.fromEntries(files.map(f=>[f,require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(root,f))).digest('hex')]));
 const args={root,targetsFile:target,traceFile:path.join(dir,'trace'),statusFile:path.join(dir,'status')};
 targetWrite({...sourceFiles,[files[0]]:'0'.repeat(64)});assert.throws(()=>require(helper).arm(args),/M7_CLINICAL_TIMELINE_SOURCE/);
 targetWrite(sourceFiles);const state=require(helper).arm(args);state.restore();await state.tap.seal();
 function targetWrite(hashes){fs.writeFileSync(target,JSON.stringify({ids:[A],sourceFiles:hashes}));}
}
(async()=>{await sourceControl();criterion(await scenario(false));assert.throws(()=>criterion([]),/MATERIALIZER_RECEIPT_STAGE/);let rejected=false;try{criterion(await scenario(true));}catch(e){assert.match(e.message,/MATERIALIZER_RECEIPT_STAGE/);rejected=true;}assert(rejected,'OLD_TAP_MUST_MISS_MATERIALIZER_RECEIPT');criterion(await scenario(false));console.log(JSON.stringify({status:'PASS',actors:0,controls:['actual c117 receiver materializer branch','old store.observe-only tap misses receipt stages','restored materializer receipt→hint→ACK','frozen private-brand original this/store/error identity','actual c117 source hash wrong/restored preload','one-target preload']}));})().catch(e=>{console.error(e);process.exitCode=1;});
