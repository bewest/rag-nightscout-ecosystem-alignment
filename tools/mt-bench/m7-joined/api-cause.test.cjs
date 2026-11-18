 'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),cause=require('./api-cause.cjs');
const owner='a'.repeat(32),source='b'.repeat(40),sourceFiles={'lib/server/tenant-app/index.js':'c'.repeat(64),'lib/server/serve/api-admission.js':'d'.repeat(64)};
const binding={owner,source,sourceFiles};
function tap(extra={}){return cause.create({...binding,persist(){},...extra});}
test('fixed cause allowlist discards unsafe strings, inherited and accessor code',()=>{
 assert.equal(cause.safeCode({code:'57014'}),'SQLSTATE_57014');assert.equal(cause.safeCode({code:'ACCESS_AUTHORITY_UNAVAILABLE'}),'ACCESS_AUTHORITY_UNAVAILABLE');
 assert.equal(cause.safeCode({code:'SECRET_TOKEN_VALUE'}),'UNCLASSIFIED');assert.equal(cause.safeCode(Object.create({code:'57014'})),'UNCLASSIFIED');
 let called=false;assert.equal(cause.safeCode(Object.defineProperty({},'code',{get(){called=true;throw Error('must not read');}})),'UNCLASSIFIED');assert.equal(called,false);
});
test('wrappers retain exact this/arguments, original promise, values and errors',async()=>{
 const t=tap(),self={},arg={credential:'NEVER_CAPTURE_THIS'},promise=Promise.resolve(arg);let received;
 const wrapped=cause.wrap(function(){received={self:this,args:[...arguments]};return promise;},'exchange',t);
 assert.equal(wrapped.call(self,arg,17),promise);assert.equal(received.self,self);assert.deepEqual(received.args,[arg,17]);assert.equal(await promise,arg);await Promise.resolve();
 assert.equal(cause.wrap(()=>23,'admission',t)(),23);
 const err=Object.assign(new Error('SECRET_MESSAGE'),{code:'57014'}),bad=Promise.reject(err),reject=cause.wrap(()=>bad,'admission',t);
 assert.equal(reject(),bad);await assert.rejects(bad,e=>e===err);await Promise.resolve();
 assert.throws(()=>cause.wrap(()=>{throw err;},'exchange',t)(),e=>e===err);
 assert.equal(t.state().counters.admission.rejected,1);assert.equal(t.state().counters.exchange.thrown,1);
 const raw=JSON.stringify(t.state());assert(!raw.includes('NEVER_CAPTURE_THIS'));assert(!raw.includes('SECRET_MESSAGE'));assert(raw.includes('SQLSTATE_57014'));
});
test('lazy exact target and stable original export object/factory identity restore',async()=>{
 const t=tap(),app={},operator=()=>{},other={unchanged:true},baseLoad=function(request){loads++;return request==='target'?exports:other;},target='/synthetic/lib/server/tenant-app/index.js';let loads=0,passed,calledThis;
 const originalFactory=function(options,extra){calledThis=this;passed={options,extra};return app;},exports={createTenantApp:originalFactory,createOperatorApp:operator};
 const loader={_load:baseLoad,_resolveFilename:name=>name==='target'?target:'/other.js'},hook=cause.install({root:'/synthetic',tap:t,moduleLoader:loader});assert.equal(loads,0);
 assert.equal(loader._load('other'),other);assert.equal(exports.createTenantApp,originalFactory);
 assert.equal(loader._load('target'),exports);const factory=exports.createTenantApp;assert.notEqual(factory,originalFactory);assert.equal(loader._load('target'),exports);assert.equal(exports.createTenantApp,factory);assert.equal(exports.createOperatorApp,operator);
 const self={},value={},opts={exchange:function(a){assert.equal(this,self);assert.equal(a,value);return Promise.resolve(value);},admitRequest:()=>5,kept:value};
 Object.defineProperty(opts,'private',{value:17,enumerable:false});
 assert.equal(factory.call(self,opts,17),app);assert.equal(calledThis,self);assert.equal(passed.extra,17);assert.equal(passed.options.kept,value);assert.equal(Object.getOwnPropertyDescriptor(passed.options,'private').enumerable,false);
 assert.equal(opts.exchange===passed.options.exchange,false);assert.equal(await passed.options.exchange.call(self,value),value);assert.equal(passed.options.admitRequest(),5);
 hook.restore();assert.equal(loader._load,baseLoad);assert.equal(exports.createTenantApp,originalFactory);hook.restore();
});
test('observer faults cannot alter application promise/result/error or factory',async()=>{
 const t={record(){throw Error('observer unavailable');},markInstalled(){throw Error('observer unavailable');}},p=Promise.resolve(7),e=Error('original');
 assert.equal(cause.wrap(()=>p,'exchange',t)(),p);assert.equal(await p,7);assert.throws(()=>cause.wrap(()=>{throw e;},'admission',t)(),v=>v===e);
 const exports={createTenantApp:options=>options.exchange()},loader={_load:()=>exports,_resolveFilename:()=>'/synthetic/lib/server/tenant-app/index.js'};
 const hook=cause.install({root:'/synthetic',tap:t,moduleLoader:loader});assert.equal(loader._load('target').createTenantApp({exchange:()=>5}),5);hook.restore();
 const broken=tap({persist(){throw Error('SINK_SECRET');}});broken.markInstalled();broken.record('admission','started');assert.equal(cause.assess([broken.state()],binding).code,'M7_API_CAUSE_INCOMPLETE');
});
test('missing/suppressed/source-mismatched/bad-code capture stays unmeasured; restored capture measured',async()=>{
 const t=tap();t.markInstalled();cause.wrap(()=>1,'admission',t)();const error=Object.assign(Error('hidden'),{code:'57014'});assert.throws(()=>cause.wrap(()=>{throw error;},'exchange',t)());
 const expected={...binding,requiredFailure:{stage:'exchange',code:'SQLSTATE_57014'}},green=()=>assert.equal(cause.assess([t.state()],expected).verdict,'MEASURED');green();
 assert.equal(cause.assess([],binding).code,'M7_API_CAUSE_NO_CAPTURE');
 const noObservation=tap();noObservation.markInstalled();assert.equal(cause.assess([noObservation.state()],binding).code,'M7_API_CAUSE_NO_OBSERVATION');
 for(const [mutate,code] of [[s=>s.source='e'.repeat(40),'PROVENANCE'],[s=>s.events[0].code='SECRET_TOKEN_VALUE','EVENT'],[s=>s.counters.exchange.thrown=0,'COUNTER'],[s=>s.dropped=1,'INCOMPLETE'],[s=>s.failed=true,'INCOMPLETE']]){const s=t.state();mutate(s);assert.equal(cause.assess([s],expected).code,'M7_API_CAUSE_'+code);green();}
 const max=tap({maxEvents:1});max.markInstalled();max.record('exchange','started');max.record('exchange','thrown',{code:'57014'});max.record('exchange','started');max.record('exchange','thrown',{code:'53300'});assert.equal(max.state().events.length,1);assert.equal(max.state().dropped,1);assert.equal(cause.assess([max.state()],binding).code,'M7_API_CAUSE_INCOMPLETE');green();
});
test('actual rejection observer suppression ablation defeats failure criterion; original restores',async()=>{
 const text=fs.readFileSync(require.resolve('./api-cause.cjs'),'utf8'),anchor="tap.record(stage,'rejected',error)";assert.equal(text.split(anchor).length,2);
 const module={exports:{}};Function('require','module',text.replace(anchor,'void 0'))(require,module);
 async function criterion(api){const t=api.create({...binding,persist(){}});t.markInstalled();api.wrap(()=>1,'admission',t)();const e=Object.assign(Error('hidden'),{code:'57014'});await assert.rejects(api.wrap(()=>Promise.reject(e),'exchange',t)(),v=>v===e);await Promise.resolve();assert.equal(api.assess([t.state()],{...binding,requiredFailure:{stage:'exchange',code:'SQLSTATE_57014'}}).verdict,'MEASURED');}
 await criterion(cause);await assert.rejects(criterion(module.exports),assert.AssertionError);await criterion(cause);
});

test('exact own message literals map lifecycle/admission/authority and source-confirmed checkout timeout',()=>{
 for(const code of ['LIFECYCLE_WINDOW_SCOPE_INVALID','LIFECYCLE_WINDOW_QUEUE_TIMEOUT','TENANT_DATA_FORBIDDEN','TENANT_AUTHORITY_UNAVAILABLE','SECRETS_LEGACY_AUTHORITY_UNKNOWN']){
  assert.equal(cause.safeCode(new Error(code)),code);
  assert.equal(cause.safeCode({code}),code);
 }
 assert.equal(cause.safeCode(new Error('timeout exceeded when trying to connect')),'POOL_CHECKOUT_TIMEOUT');
 assert.equal(cause.safeCode(new Error('API request belongs to another tenant')),'API_REQUEST_TENANT_MISMATCH');
 for(const message of ['LIFECYCLE_WINDOW_SCOPE_INVALID: tenant-secret','LIFECYCLE_WINDOW_NOT_A_REAL_SYMBOL','timeout exceeded when trying to connect ','Connection terminated due to connection timeout','PRIVATE_TOKEN_MESSAGE','57014'])assert.equal(cause.safeCode(new Error(message)),'UNCLASSIFIED');
 assert.equal(cause.safeCode({code:'WRONG_CODE',message:'LIFECYCLE_WINDOW_SCOPE_INVALID'}),'UNCLASSIFIED');
 assert.equal(cause.safeCode(Object.create({message:'LIFECYCLE_WINDOW_SCOPE_INVALID'})),'UNCLASSIFIED');
});
test('message/code/stack/getter/toString/toJSON traps are never evaluated or retained',()=>{
 let reads=0;
 const trap=()=>{reads++;throw Error('PRIVATE_GETTER_TOKEN');};
 const getterError={};for(const key of ['message','code','stack'])Object.defineProperty(getterError,key,{get:trap});
 getterError.toString=trap;getterError.toJSON=trap;assert.equal(cause.safeCode(getterError),'UNCLASSIFIED');
 const messageTrap=Object.defineProperties({},{message:{get:trap},stack:{get:trap}});assert.equal(cause.safeCode(messageTrap),'UNCLASSIFIED');
 const dataMessage=Object.defineProperties({message:'LIFECYCLE_WINDOW_SCOPE_INVALID'},{stack:{get:trap},toJSON:{get:trap}});
 assert.equal(cause.safeCode(dataMessage),'LIFECYCLE_WINDOW_SCOPE_INVALID');
 assert.equal(cause.safeCode({message:{toString:trap}}),'UNCLASSIFIED');
 const t=tap();t.markInstalled();t.record('admission','started');t.record('admission','thrown',getterError);t.record('exchange','started');t.record('exchange','thrown',dataMessage);
 const text=JSON.stringify(t.state());assert(!text.includes('PRIVATE_GETTER_TOKEN'));assert(!text.includes('message'));assert(!text.includes('stack'));assert.equal(reads,0);
 assert.equal(cause.assess([t.state()],{...binding,requiredFailure:{stage:'exchange',code:'LIFECYCLE_WINDOW_SCOPE_INVALID'}}).verdict,'MEASURED');
 const secretError={message:'PRIVATE_TOKEN_MESSAGE',stack:'PRIVATE_STACK_TOKEN'};t.record('exchange','started');t.record('exchange','thrown',secretError);
 assert(!JSON.stringify(t.state()).includes('PRIVATE_TOKEN'));assert(!JSON.stringify(t.state()).includes('PRIVATE_STACK'));
});
