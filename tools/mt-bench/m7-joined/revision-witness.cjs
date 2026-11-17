'use strict';
// Private synthetic witness. Fixed fields only. No wire fields, timers or queries.
const crypto=require('node:crypto'),{AsyncLocalStorage}=require('node:async_hooks');
const digest=value=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
const id=value=>typeof value==='string'&&/^[a-zA-Z0-9_-]{1,64}$/.test(value);
const uuid=value=>typeof value==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value)&&value!=='00000000-0000-0000-0000-000000000000';
const rev=value=>{if(typeof value==='number'&&!Number.isSafeInteger(value))return null;const s=String(value);return /^(0|[1-9][0-9]{0,18})$/.test(s)&&BigInt(s)<=9223372036854775807n?s:null;};
function create({owner,source,targets,persist,maxEvents=64,maxBytes=65536,instance=crypto.randomUUID(),clock=()=>process.hrtime.bigint()}){
 if(!/^[a-f0-9]{32}$/.test(owner)||!/^[a-f0-9]{40}$/.test(source)||!Array.isArray(targets)||!targets.length||targets.length>2||targets.some(t=>!uuid(t.tenant)||!id(t.storedId))||new Set(targets.map(t=>t.tenant)).size!==targets.length||typeof persist!=='function'||!Number.isSafeInteger(maxEvents)||maxEvents<1||maxEvents>64||!Number.isSafeInteger(maxBytes)||maxBytes<1||maxBytes>65536)throw Error('M7_REVISION_BINDING');
 const rows=[],roster=new Map(targets.map(t=>[t.tenant,t]));let bytes=0,dropped=0,failed=false,overheadNs=0n;
 const state=()=>({version:1,owner,source,instance,clockDomain:'process-hrtime',events:rows.slice(),bytes,dropped,failed,overheadNs:String(overheadNs),qualification:dropped||failed?'UNMEASURED':'COMPLETE'});
 function record(stage,tenant,fields={}){
  const target=roster.get(tenant);if(!target)return;
  const start=clock();
  try{
   if(!['complete','selection-send','receipt-commit','acquisition','fanout','emit','engine-arrival','stock-callback'].includes(stage))throw Error('STAGE');
   const row={stage,tenant,storedId:target.storedId,owner,source,instance,clockDomain:'process-hrtime',ordinal:rows.length+1,monoNs:String(start)};
   for(const key of ['outputRevision','deliveryRevision','rawTailHead','inputCheckpoint'])if(fields[key]!==undefined){const value=rev(fields[key]);if(value===null)throw Error('REVISION');row[key]=value;}
   if(fields.inputCoverage!==undefined){const v=fields.inputCoverage;if(!v||typeof v!=='object'||Array.isArray(v)||Object.keys(v).length>6||Object.entries(v).some(([k,x])=>!['clock','settings','policy','activity','lifecycle','bootstrap'].includes(k)||rev(x)===null))throw Error('COVERAGE');row.inputCoverage=Object.fromEntries(Object.entries(v).map(([k,x])=>[k,rev(x)]));}
   for(const key of ['payloadDigest','socket'])if(fields[key]!==undefined){if(!/^[a-f0-9]{64}$/.test(fields[key]))throw Error('DIGEST');row[key]=fields[key];}
   for(const key of ['fifo','incarnation'])if(fields[key]!==undefined){if(!Number.isSafeInteger(fields[key])||fields[key]<1)throw Error('ORDINAL');row[key]=fields[key];}
   if(fields.transport!==undefined){if(!['polling','websocket'].includes(fields.transport))throw Error('TRANSPORT');row.transport=fields.transport;}
   const size=Buffer.byteLength(JSON.stringify(row));if(rows.length>=maxEvents||bytes+size>maxBytes){dropped++;return;}
   rows.push(row);bytes+=size;
  }catch{failed=true;}finally{try{persist(state());}catch{failed=true;}overheadNs+=clock()-start;}
 }
 return {record,state,target:tenant=>roster.get(tenant),matches:(tenant,frame)=>!!roster.get(tenant)&&Array.isArray(frame?.sgvs)&&frame.sgvs.some(s=>String(s._id)===roster.get(tenant).storedId)};
}
function clone(value,changes){const descriptors=Object.getOwnPropertyDescriptors(value);for(const [key,item]of Object.entries(changes))descriptors[key]={...descriptors[key],value:item};return Object.defineProperties({},descriptors);}
function observe(p,done){if(p&&typeof p.then==='function')p.then(value=>{try{done(value);}catch{}},()=>{});return p;}
function install({root,tap,moduleLoader=require('node:module')}){
 const path=require('node:path'),context=new AsyncLocalStorage(),original=moduleLoader._load,wrapped=new Map(),bases=new Map(),undo=[];
 const named={output:path.join(root,'lib/pgstream/realtime-output.js'),runtime:path.join(root,'lib/server/realtime/runtime.js'),typed:path.join(root,'lib/pgstream/typed-checkpoint.js'),receipt:path.join(root,'lib/pgstream/realtime-receipt.js'),scheduler:path.join(root,'lib/pgstream/activity-scheduler.js')};
 function transform(file,value){
  if(file===named.output)return clone(value,{projection:function(options){const result=Reflect.apply(value.projection,this,arguments),tenant=options.current.tenant;return clone(result,{acquire:function(){return observe(Reflect.apply(result.acquire,this,arguments),r=>{if(tap.matches(tenant,r?.frame))tap.record('acquisition',tenant,{outputRevision:r.checkpoint,inputCheckpoint:r.inputCheckpoint});});}});}});
  if(file===named.runtime){const fn=function(options){const fanout=options.fanout;return Reflect.apply(value,this,[{...options,fanout:function(operation){const m={tenant:operation.tenant,outputRevision:operation.next?.checkpoint,inputCheckpoint:operation.next?.inputCheckpoint};return context.run(tap.matches(m.tenant,operation.next?.frame)?m:null,()=>{tap.record('fanout',m.tenant,m);return Reflect.apply(fanout,this,arguments);});}}]);};Object.defineProperties(fn,Object.getOwnPropertyDescriptors(value));return fn;}
  if(file===named.typed)return clone(value,{create:function(){const result=Reflect.apply(value.create,this,arguments);return clone(result,{complete:function(tenant,value){return observe(Reflect.apply(result.complete,this,arguments),r=>{if(tap.matches(tenant,r?.output?.frame))tap.record('complete',tenant,{outputRevision:r.output.outputRevision,inputCheckpoint:r.output.inputCheckpoint,inputCoverage:value?.observed});});}});}});
  if(file===named.receipt)return clone(value,{create:function(){const result=Reflect.apply(value.create,this,arguments);return clone(result,{receive:function(tenant,revision){return observe(Reflect.apply(result.receive,this,arguments),()=>tap.record('receipt-commit',tenant,{deliveryRevision:revision}));}});}});
  if(file===named.scheduler)return clone(value,{start:function(options){const send=options.send;if(typeof send!=='function')return Reflect.apply(value.start,this,arguments);return Reflect.apply(value.start,this,[{...options,send:function(row){tap.record('selection-send',row.tenant,{deliveryRevision:row.revision});return Reflect.apply(send,this,arguments);}}]);}});
  // Observe the real Socket.IO adapter broadcast call after authorization and frame selection.
  if(/node_modules\/socket.io-adapter\/dist\/in-memory-adapter.js$/.test(file)&&value.Adapter?.prototype){const proto=value.Adapter.prototype,base=proto.broadcast;proto.broadcast=function(packet,options){const m=context.getStore();if(m&&packet?.data?.[0]==='dataUpdate'){const rooms=[...(options?.rooms||[])];if(rooms.length&&rooms.length<=4)for(const room of rooms)tap.record('emit',m.tenant,{...m,socket:digest(String(room)),payloadDigest:digest(packet.data),fifo:tap.state().events.filter(e=>e.stage==='emit'&&e.socket===digest(String(room))).length+1});}return Reflect.apply(base,this,arguments);};undo.push(()=>{proto.broadcast=base;});}
  return value;
 }
 moduleLoader._load=function(request,parent,isMain){const file=moduleLoader._resolveFilename(request,parent,isMain);const value=Reflect.apply(original,this,arguments);if(!Object.values(named).includes(file)&&!file.includes('socket.io-adapter/dist/in-memory-adapter.js'))return value;if(!wrapped.has(file)){bases.set(file,value);wrapped.set(file,transform(file,value));}const result=wrapped.get(file),cached=require.cache[file];if(cached&&cached.exports===value&&result!==value)cached.exports=result;return result;};
 return {restore(){moduleLoader._load=original;for(const [file,value] of bases){const cached=require.cache[file];if(cached?.exports===wrapped.get(file))cached.exports=value;}for(const run of undo.reverse())run();},files:named};
}
function client({socket,tenant,tap}){
 let incarnation=0,arrival=0,callback=0;const attached=new WeakSet();
 function engine(){const e=socket.io.engine;if(!e||attached.has(e))return;attached.add(e);e.on('packet',packet=>{if(packet.type!=='message'||typeof packet.data!=='string'||packet.data.length>1048576||!packet.data.startsWith('2['))return;let data;try{data=JSON.parse(packet.data.slice(1));}catch{return;}if(data[0]==='dataUpdate'&&tap.matches(tenant,data[1]))tap.record('engine-arrival',tenant,{socket:digest(socket.id||''),incarnation:Math.max(1,incarnation),fifo:++arrival,payloadDigest:digest(data),transport:e.transport.name});});}
 socket.io.on('open',engine);engine();socket.on('connect',()=>{incarnation++;arrival=callback=0;engine();});
 // Invoke from the existing stock callback; this helper installs no replacement handler.
 return {callback(frame){if(tap.matches(tenant,frame))tap.record('stock-callback',tenant,{socket:digest(socket.id||''),incarnation:Math.max(1,incarnation),fifo:++callback,payloadDigest:digest(['dataUpdate',frame]),transport:socket.io.engine.transport.name});}};
}
function correlate(states){
 const reasons=[],events=[];
 if(!Array.isArray(states)||!states.length)return {verdict:'UNMEASURED',reasons:['M7_REVISION_NO_CAPTURE']};
 const {owner,source}=states[0];
 for(const state of states){if(state.owner!==owner||state.source!==source||state.qualification!=='COMPLETE'||state.clockDomain!=='process-hrtime')reasons.push('M7_REVISION_PROVENANCE');for(const row of state.events||[]){if(row.owner!==owner||row.source!==source||row.instance!==state.instance||row.clockDomain!==state.clockDomain)reasons.push('M7_REVISION_PROVENANCE');events.push(row);}}
 if(events.some(e=>typeof e.monoNs!=='string'||!/^[0-9]{1,24}$/.test(e.monoNs)))return {verdict:'UNMEASURED',reasons:['M7_REVISION_CLOCK_INVALID'],joins:[]};
 const callbacks=events.filter(e=>e.stage==='stock-callback'),joins=[];
 const callbackKeys=callbacks.map(e=>JSON.stringify([e.tenant,e.storedId,e.socket,e.incarnation,e.fifo]));if(new Set(callbackKeys).size!==callbackKeys.length)reasons.push('M7_REVISION_DUPLICATE_CALLBACK');
 for(const callback of callbacks){const same=e=>e.tenant===callback.tenant&&e.storedId===callback.storedId&&e.socket===callback.socket&&e.payloadDigest===callback.payloadDigest&&e.fifo===callback.fifo;
  const emitted=events.filter(e=>e.stage==='emit'&&same(e)),arrival=events.filter(e=>e.stage==='engine-arrival'&&same(e)&&e.instance===callback.instance&&e.incarnation===callback.incarnation);
  if(emitted.length!==1||arrival.length!==1){reasons.push('M7_REVISION_AMBIGUOUS_OR_MISSING');continue;}
  const emit=emitted[0],engine=arrival[0];if(rev(emit.outputRevision)===null||emit.outputRevision==='0'||!Number.isSafeInteger(callback.fifo)||callback.fifo<1){reasons.push('M7_REVISION_IDENTITY');continue;}const acquired=events.filter(e=>e.stage==='acquisition'&&e.instance===emit.instance&&e.tenant===emit.tenant&&e.storedId===emit.storedId&&e.outputRevision===emit.outputRevision&&BigInt(e.monoNs)<=BigInt(emit.monoNs));
  if(!acquired.length||BigInt(engine.monoNs)>BigInt(callback.monoNs)){reasons.push('M7_REVISION_ORDER');continue;}
  const acquire=acquired.reduce((a,b)=>BigInt(a.monoNs)>BigInt(b.monoNs)?a:b);const completions=events.filter(e=>e.stage==='complete'&&e.tenant===emit.tenant&&e.storedId===emit.storedId&&e.outputRevision===emit.outputRevision);const coverages=new Map(completions.filter(e=>e.inputCoverage).map(e=>[JSON.stringify(e.inputCoverage),e.inputCoverage]));joins.push({tenant:callback.tenant,storedId:callback.storedId,outputRevision:emit.outputRevision,inputCheckpoint:acquire.inputCheckpoint,inputCoverage:coverages.size===1?[...coverages.values()][0]:'UNMEASURED',socket:callback.socket,payloadDigest:callback.payloadDigest,fifo:callback.fifo,acquireToEmitNs:String(BigInt(emit.monoNs)-BigInt(acquire.monoNs)),engineToCallbackNs:String(BigInt(callback.monoNs)-BigInt(engine.monoNs)),emitToEngine:'UNMEASURED_CROSS_PROCESS',deliveryRevision:'UNMEASURED',rawTailHead:'UNMEASURED'});
 }
 if(!callbacks.length)reasons.push('M7_REVISION_NO_CALLBACK');
 return {verdict:reasons.length?'UNMEASURED':'PASS',reasons:[...new Set(reasons)],joins,scope:'exact acquired output to emitted payload and stock callback; no cross-process clock subtraction; delivery and raw revisions require separate evidence'};
}
module.exports={create,install,client,correlate,digest};
