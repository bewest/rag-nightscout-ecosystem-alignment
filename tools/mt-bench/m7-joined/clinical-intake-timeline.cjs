'use strict';
// Finite fixture tap. No server, timer or query is created here; raw mode observes lifecycle events.
const fs=require('node:fs'),{AsyncLocalStorage}=require('node:async_hooks');
// Raw metadata is opt-in and separate from the selected-body trace.
function safeLsn(value){return typeof value==='string'&&/^[0-9A-F]{1,8}\/[0-9A-F]{1,8}$/.test(value)?value:value==null?'ABSENT':'INVALID';}
function rawLedger({file,maxRows=32768,maxBytes=8388608,maxPending=128}){
 for(const [value,limit] of [[maxRows,32768],[maxBytes,8388608],[maxPending,128]])if(!Number.isSafeInteger(value)||value<1||value>limit)throw Error('M7_CLINICAL_RAW_BOUND');
 const instance=require('node:crypto').randomUUID(),fd=fs.openSync(file,'wx',0o600);let rows=0,bytes=0,pending=0,written=0,dropped=0,failed=null,closed=false;
 const lsn=value=>value==='ABSENT'||value==='INVALID'?value:safeLsn(value);
 const status=()=>({instance,rows,bytes,pending,written,dropped,failed,closed,qualification:pending===0&&!dropped&&!failed?'COMPLETE':'UNMEASURED'});
 function emit(phase,m,extra={}){
  if(closed)return;const record={instance,sequence:rows+1,phase,at:Date.now(),monoNs:String(process.hrtime.bigint()),pid:process.pid,request:m.request,headerLsn:lsn(m.headerLsn),idempotency:lsn(m.idempotency),...extra};
  const text=JSON.stringify(record)+'\n',size=Buffer.byteLength(text);
  if(rows>=maxRows||bytes+size>maxBytes||pending>=maxPending){dropped++;return;}
  rows++;bytes+=size;pending++;
  try{fs.write(fd,text,null,'utf8',(e,n)=>{pending--;if(e||n!==size)failed=e?.code==='ENOSPC'?'ENOSPC':'WRITE_REFUSED';else written++;});}catch{pending--;failed='WRITE_REFUSED';}
 }
 return {instance,emit,status,async seal(){const until=Date.now()+1000;while(pending&&Date.now()<until)await new Promise(r=>setImmediate(r));if(pending)failed='WRITE_DRAIN_INCOMPLETE';closed=true;if(!pending)fs.closeSync(fd);return status();}};
}
function install({file,ids,http,pg,receiver,scheduler,runtime,maxRows=4096,maxBytes=2097152,raw=null}){
 const context=new AsyncLocalStorage(),targets=new Set(ids);let sequence=0,requests=0,bytes=0,pending=0,written=0,dropped=0,failed=null,closed=false;
 const fd=fs.openSync(file,'wx',0o600),rawTap=raw?rawLedger(raw):null,socketIds=new WeakMap();let sockets=0;
 const project=m=>Object.fromEntries(['request','headerLsn','idempotency','tenant','stamp','dataLsn'].filter(k=>m&&Object.hasOwn(m,k)).map(k=>[k,m[k]]));
 function emit(phase,m,fields={}){
  if(closed)return;const record={sequence:sequence+1,phase,at:Date.now(),monoNs:String(process.hrtime.bigint()),pid:process.pid,...(rawTap?{instance:rawTap.instance}:{}),...project(m),...fields};
  const text=JSON.stringify(record)+'\n';if(sequence>=maxRows||bytes+Buffer.byteLength(text)>maxBytes){dropped++;return;}
  sequence++;bytes+=Buffer.byteLength(text);pending++;
  try{fs.write(fd,text,null,'utf8',(e,n)=>{pending--;if(e||n!==Buffer.byteLength(text))failed=e?.code||'PARTIAL_WRITE';else written++;});}catch(e){pending--;failed=e.code||'WRITE_REFUSED';}
 }
 const settle=(p,m,phase,fields={})=>{if(p&&typeof p.then==='function')p.then(()=>emit(phase+'-return',m,fields),e=>emit(phase+'-refusal',m,{...fields,code:/^[A-Z0-9_]{1,64}$/.test(e?.code||'')?e.code:'ERROR'})).catch(()=>{});else emit(phase+'-unsupported',m);};
 const originalServer=http.createServer;
 http.createServer=function(...args){const i=args.findIndex(v=>typeof v==='function');if(i<0)return Reflect.apply(originalServer,this,args);const handler=args[i];args[i]=function(req,res){
  if(req.method!=='POST'||req.url!=='/pgstream')return Reflect.apply(handler,this,[req,res]);
  const m={request:++requests,headerLsn:safeLsn(req.headers['x-pgstream-lsn']),idempotency:safeLsn(req.headers['idempotency-key'])};
  m.arrivedAt=Date.now();m.arrivedMonoNs=String(process.hrtime.bigint());
  if(rawTap){
   const socket=req.socket;if(socket&&typeof socket==='object'&&!socketIds.has(socket))socketIds.set(socket,++sockets);
   rawTap.emit('raw-entry',m,{at:m.arrivedAt,monoNs:m.arrivedMonoNs,connection:socketIds.get(socket)??null,peerPort:Number.isInteger(socket?.remotePort)?socket.remotePort:null,localPort:Number.isInteger(socket?.localPort)?socket.localPort:null});
   req.once('aborted',()=>rawTap.emit('raw-request-aborted',m));
   req.once('close',()=>rawTap.emit('raw-request-close',m,{complete:!!req.complete,aborted:!!req.aborted}));
   res.once('finish',()=>rawTap.emit('raw-response-finish',m,{status:res.statusCode,finished:!!res.writableFinished}));
   res.once('close',()=>rawTap.emit('raw-response-close',m,{status:res.statusCode,finished:!!res.writableFinished}));
  }
  res.once('finish',()=>{if(m.target)emit('http-finish',m,{status:res.statusCode,destroyed:!!res.destroyed,finished:!!res.writableFinished});});res.once('close',()=>{if(m.target)emit('http-close',m,{status:res.statusCode,destroyed:!!res.destroyed,finished:!!res.writableFinished});});
  return context.run(m,()=>Reflect.apply(handler,this,[req,res]));};return Reflect.apply(originalServer,this,args);};
 const receiverSeen=new WeakSet(),pgSeen=new WeakSet(),schedulerSeen=new WeakSet(),runtimeSeen=new WeakMap();
 function attachReceiver(receiver){if(receiverSeen.has(receiver))return receiver;receiverSeen.add(receiver);
 const originalCreate=receiver.create;
 receiver.create=function(options){
 const clockRoutes=new Set(Array.isArray(options.routes)?options.routes.filter(route=>route?.kind==='clock').map(route=>route.schema+'.'+route.table):[]);
  const store=Object.create(options.store);Object.defineProperty(store,'observe',{value:function(...args){const m=context.getStore();const active=m?.target&&targets.has(args[0])&&args[1]==='clock';if(active){m.observing=true;emit('observe-call',m);}let result;
   try{result=Reflect.apply(options.store.observe,options.store,args);}catch(e){if(active)emit('observe-throw',m,{code:/^[A-Z0-9_]{1,64}$/.test(e?.code||'')?e.code:'ERROR'});throw e;}
   if(active){settle(result,m,'observe-commit');result.finally(()=>{m.observing=false;}).catch(()=>{});}return result;}});
  const receive=Reflect.apply(originalCreate,this,[{...options,store,onInput:function(...args){const m=context.getStore();if(m?.target&&targets.has(args[0]))emit('hint-call',m);const result=Reflect.apply(options.onInput,this,args);if(m?.target&&targets.has(args[0]))emit('hint-return',m);return result;}}]);
  return function(event){const m=context.getStore();
   // Inspection never replaces the receiver's own validation or rejection.
   try{const data=event?.Data,columns=data?.columns,identity=data?.identity;
    if(m&&clockRoutes.has(data?.schema+'.'+data?.table)&&Array.isArray(columns)&&(identity==null||Array.isArray(identity))){
     const all=[...(identity||[]),...columns];if(all.every(c=>c&&typeof c.name==='string')){
      const row=Object.fromEntries(all.map(c=>[c.name,c.value]));if(targets.has(row.tenant_id)){
       m.target=true;m.tenant=row.tenant_id;m.stamp=/^[0-9]{1,20}$/.test(String(row.last_stamp))?String(row.last_stamp):'INVALID';m.dataLsn=safeLsn(data.lsn);
       emit('http-arrival',m,{at:m.arrivedAt,monoNs:m.arrivedMonoNs});emit('parsed-clock',m);if(rawTap)rawTap.emit('raw-parsed-target',m);
      }
     }
    }
   }catch{if(rawTap&&m)rawTap.emit('raw-inspector-refusal',m);}
   return Reflect.apply(receive,this,arguments);
  };
 };
 return receiver;}
 function attachPg(pg){if(pgSeen.has(pg))return pg;pgSeen.add(pg);
 const originalConnect=pg.Pool.prototype.connect;
 pg.Pool.prototype.connect=function(...args){const m=context.getStore();if(m?.observing)emit('pool-checkout-call',m);const result=Reflect.apply(originalConnect,this,args);if(m?.observing&&result&&typeof result.then==='function')result.then(client=>emit('pool-checkout-return',m,{backend:client.processID}),e=>emit('pool-checkout-refusal',m,{code:/^[A-Z0-9_]{1,64}$/.test(e?.code||'')?e.code:'ERROR'})).catch(()=>{});return result;};
 const classify=t=>t==='BEGIN'?'begin':t==='COMMIT'?'commit':t==='ROLLBACK'?'rollback':t.includes('FOR UPDATE')&&t.includes('work_observed')?'receipt-lock':t.startsWith('WITH input AS')?'receipt-update':'backend-proof';
 const originalQuery=pg.Client.prototype.query;
 pg.Client.prototype.query=function(...args){const m=context.getStore(),text=typeof args[0]==='string'?args[0]:args[0]?.text;const active=m?.observing&&typeof text==='string';const fields=active?{backend:this.processID,query:classify(text)}:{};if(active)emit('query-call',m,fields);const result=Reflect.apply(originalQuery,this,args);if(active)settle(result,m,'query',fields);return result;};
 return pg;}
 // These taps wrap existing callbacks only: no new query, listener or timer.
 function attachScheduler(scheduler){if(schedulerSeen.has(scheduler))return scheduler;schedulerSeen.add(scheduler);const start=scheduler.start;scheduler.start=function(options){
  const timer=options.setTimer||setTimeout,run=options.run;
  return Reflect.apply(start,this,[{...options,setTimer:function(...args){const value=Reflect.apply(timer,this,args);const m=context.getStore();if(m&&targets.has(m.tenant))emit('scheduler-timer-set',m,{delayMs:args[1],scope:'existing timer created; target hint context, not clinical-version proof'});return value;},run:function(...args){
   const tenant=args[0],m=targets.has(tenant)?{tenant}:null;if(m)emit('scheduler-run-call',m,{kind:args[1],versionScope:'UNMEASURED: run callback carries no version'});
   const result=Reflect.apply(run,this,args);if(m)settle(result,m,'scheduler-run');return result;}}]);
 };return scheduler;}
 function wrapRuntime(original){if(runtimeSeen.has(original))return runtimeSeen.get(original);const wrapped={invoke(options){
  if(!options.durable)return Reflect.apply(original,this,[options]);const durable={...options.durable};
  for(const method of ['begin','complete']){const invoke=options.durable[method];durable[method]=function(...args){
   const tenant=args[0],m=targets.has(tenant)?{tenant,...(method==='complete'?{stamp:String(args[1]?.observed?.clock)}:{})}:null;
   if(m)emit('durable-'+method+'-call',m);const result=Reflect.apply(invoke,options.durable,args);
   if(m&&result&&typeof result.then==='function')result.then(value=>emit('durable-'+method+'-return',method==='begin'?{...m,stamp:String(value?.clock)}:m,{scope:method==='begin'?'actual durable begin vector':'original completion callback resolved after durable transaction'}),e=>emit('durable-'+method+'-refusal',m,{code:/^[A-Z0-9_]{1,64}$/.test(e?.code||'')?e.code:'ERROR'})).catch(()=>{});
   return result;
  };}
  return Reflect.apply(original,this,[{...options,durable}]);
 }}.invoke;Object.setPrototypeOf(wrapped,Object.getPrototypeOf(original));Object.defineProperties(wrapped,Object.getOwnPropertyDescriptors(original));runtimeSeen.set(original,wrapped);runtimeSeen.set(wrapped,wrapped);return wrapped;}
 const attach=(kind,value)=>kind==='receiver'?attachReceiver(value):kind==='pg'?attachPg(value):kind==='scheduler'?attachScheduler(value):kind==='runtime'?wrapRuntime(value):value;
 if(receiver)attachReceiver(receiver);if(pg)attachPg(pg);if(scheduler)attachScheduler(scheduler);if(runtime)runtime.exports=wrapRuntime(runtime.exports);
 return Object.freeze({attach,rawStatus:()=>rawTap?.status()??null,status:()=>({rows:sequence,bytes,pending,written,dropped,failed,closed}),async seal(){if(closed)return;const until=Date.now()+1000;while(pending&&Date.now()<until)await new Promise(r=>setImmediate(r));if(pending)failed='WRITE_DRAIN_INCOMPLETE';closed=true;const seal={phase:'trace-seal',at:Date.now(),pid:process.pid,rows:sequence,bytes,pending,written,dropped,failed};fs.writeSync(fd,JSON.stringify(seal)+'\n');fs.closeSync(fd);if(rawTap)await rawTap.seal();return seal;}});
}
// Observe canonical loads only; resolving paths does not initialize app modules.
function arm({root,targetsFile,traceFile,statusFile,rawFile=null,rawStatusFile=null,moduleLoader=require('node:module')}){
 const path=require('node:path'),ids=JSON.parse(fs.readFileSync(targetsFile,'utf8')).ids;
 if(ids.length!==2||new Set(ids).size!==2||ids.some(id=>!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id)))throw Error('M7_CLINICAL_TIMELINE_BINDING');
 const files={receiver:path.join(root,'lib/pgstream/receiver.js'),scheduler:path.join(root,'lib/pgstream/activity-scheduler.js'),runtime:path.join(root,'lib/server/serve/evaluator-runtime.js'),pg:require.resolve('pg',{paths:[root]})};
 const byFile=new Map(Object.entries(files).map(([kind,file])=>[fs.realpathSync(file),kind]));
 if(!!rawFile!==!!rawStatusFile)throw Error('M7_CLINICAL_RAW_BINDING');
 const tap=install({file:traceFile,ids,http:require('node:http'),raw:rawFile?{file:rawFile}:null});
 const originalLoad=moduleLoader._load;
 function canonicalLoad(request,parent,isMain){
  const value=Reflect.apply(originalLoad,this,arguments);
  const resolved=moduleLoader._resolveFilename(request,parent,isMain),kind=byFile.get(resolved);
  if(!kind)return value;
  const hooked=tap.attach(kind,value);
  if(hooked!==value){const cached=require.cache[resolved];if(!cached||cached.exports!==value)throw Error('M7_CLINICAL_TIMELINE_MODULE_IDENTITY');cached.exports=hooked;}
  return hooked;
 }
 moduleLoader._load=canonicalLoad;
 // CANONICAL_LOAD_BOUNDARY: no app require occurs before the entrypoint.
 process.once('exit',()=>{if(rawStatusFile)fs.writeFileSync(rawStatusFile,JSON.stringify(tap.rawStatus())+'\n',{flag:'wx',mode:0o600});const s=tap.status();fs.writeFileSync(statusFile,JSON.stringify({...s,qualification:s.pending===0&&!s.dropped&&!s.failed?'COMPLETE':'UNMEASURED'})+'\n',{flag:'wx',mode:0o600});});
 return {tap,files,restore(){if(moduleLoader._load!==canonicalLoad)throw Error('M7_CLINICAL_TIMELINE_LOADER_OWNER');moduleLoader._load=originalLoad;}};
}
module.exports={install,arm};
if(process.env.NS_M7_CLINICAL_TIMELINE==='1'){
 if(process.argv.at(-1)!=='evaluator')throw Error('M7_CLINICAL_TIMELINE_BINDING');
 arm({root:process.cwd(),targetsFile:'/run/ns-intake-timeline/targets.json',traceFile:'/run/ns-ipc/clinical-intake-timeline.jsonl',statusFile:'/run/ns-ipc/clinical-intake-timeline-status.json',...(process.env.NS_M7_CLINICAL_RAW_TIMELINE==='1'?{rawFile:'/run/ns-ipc/clinical-intake-raw.jsonl',rawStatusFile:'/run/ns-ipc/clinical-intake-raw-status.json'}:{})});
}
