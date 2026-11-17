'use strict';
const assert=require('node:assert/strict'),path=require('node:path'),w=require('./revision-witness.cjs');
const root='/synthetic-root',tenant='11111111-1111-4111-8111-111111111111',frame={sgvs:[{_id:'synthetic-a'}]},calls=[],captured=[];
const tap=w.create({owner:'a'.repeat(32),source:'b'.repeat(40),targets:[{tenant,storedId:'synthetic-a'}],persist:state=>captured.push(state)});
let promise,received,fanoutOptions;
const modules={
 'lib/pgstream/realtime-output.js':{projection(options){calls.push(['projection',options]);return Object.freeze({acquire(...args){calls.push(['acquire',this,args]);return promise;}});}},
 'lib/pgstream/typed-checkpoint.js':{create(options){calls.push(['typed',options]);return Object.freeze({complete(...args){calls.push(['complete',this,args]);return promise;}});}},
 'lib/pgstream/realtime-receipt.js':{create(options){calls.push(['receipt',options]);return Object.freeze({receive(...args){received=args;return promise;}});}},
 'lib/pgstream/activity-scheduler.js':{start(options){calls.push(['scheduler',options]);return options.send({tenant,revision:'99'});}},
 'lib/server/realtime/runtime.js':async function(options){fanoutOptions=options;return options.fanout({tenant,next:{checkpoint:7,inputCheckpoint:12,frame}});}
};
const loader={_resolveFilename(request){return path.join(root,request);},_load(request){return modules[request];}};
const original=loader._load,hook=w.install({root,tap,moduleLoader:loader});
(async()=>{
 const output=loader._load('lib/pgstream/realtime-output.js');assert.equal(output,loader._load('lib/pgstream/realtime-output.js'),'STABLE_REPEATED_EXPORT');assert.equal(Object.keys(require.cache).some(p=>p.startsWith(root)),false,'NO_EAGER_APP_LOAD');
 const component=output.projection({current:{tenant}});const args={unchanged:true};promise=Promise.resolve({checkpoint:7,inputCheckpoint:12,frame});assert.equal(component.acquire(args),promise,'ACQUIRE_PROMISE_IDENTITY');await promise;
 const typed=loader._load('lib/pgstream/typed-checkpoint.js').create({port:'original'});promise=Promise.resolve({output:{outputRevision:7,inputCheckpoint:12,frame}});assert.equal(typed.complete(tenant,args),promise,'COMPLETION_PROMISE_IDENTITY');await promise;
 const receipt=loader._load('lib/pgstream/realtime-receipt.js').create({port:'original'});promise=Promise.resolve('99');assert.equal(receipt.receive(tenant,'99'),promise,'RECEIPT_PROMISE_IDENTITY');await promise;assert.deepEqual(received,[tenant,'99']);
 const sentinel=Promise.resolve('unchanged-send');assert.equal(loader._load('lib/pgstream/activity-scheduler.js').start({send(row){assert.deepEqual(row,{tenant,revision:'99'});return sentinel;}}),sentinel,'SEND_PROMISE_IDENTITY');
 let emitted=0;const runtime=loader._load('lib/server/realtime/runtime.js');await runtime({fanout(operation){emitted++;assert.equal(operation.next.frame,frame);return 'unchanged';}});assert.equal(emitted,1);assert(fanoutOptions);
 assert.deepEqual(tap.state().events.map(e=>e.stage),['acquisition','complete','receipt-commit','selection-send','fanout']);assert.equal(tap.state().events[2].deliveryRevision,'99');assert.equal(tap.state().events[0].outputRevision,'7');
 // Observing a rejected promise leaves rejection object and retry policy intact.
 const refusal=Error('private');promise=Promise.reject(refusal);assert.equal(component.acquire(args),promise);await assert.rejects(promise,e=>e===refusal);await new Promise(r=>setImmediate(r));assert.equal(tap.state().events.length,5);
 // Storage observer failure cannot suppress the underlying call/result.
 const failing=w.create({owner:'a'.repeat(32),source:'b'.repeat(40),targets:[{tenant,storedId:'synthetic-a'}],persist(){throw Error('secret');}});failing.record('acquisition',tenant,{outputRevision:7});assert.equal(failing.state().qualification,'UNMEASURED');
 hook.restore();assert.equal(loader._load,original);console.log(JSON.stringify({status:'PASS',stableExports:true,promiseIdentity:true,forwarding:true,rejectionIdentity:true,restored:true,scope:'lazy wrapper port/argument/result preservation; actual source/native transport in smoke'}));
})().catch(e=>{hook.restore();console.error(e.stack);process.exitCode=1;});
