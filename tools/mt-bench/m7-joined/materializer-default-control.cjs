'use strict';
// Source-only discriminator. This exercises maintained default route/wire
// exports, not a copied route list or an opt-in diagnostic route override.
// It proves wiring only; row application/recovery require actual runtime tests.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createRequire}=require('node:module');
const domains=['entries','treatments','devicestatus','profile','food','activity'];
function loadDeployment(file,core){
 const module={exports:{}},local=createRequire(file),app=createRequire(path.join(core,'package.json'));
 const bound=name=>name.startsWith('../../lib/')?app('./lib/'+name.slice('../../lib/'.length)):local(name);
 vm.runInThisContext('(function(require,module,exports,__dirname,__filename){'+fs.readFileSync(file,'utf8')+'\n})',{filename:file})(bound,module,module.exports,path.dirname(file),file);
 return module.exports;
}
function fixture(){return {namespaces:Object.fromEntries([...domains,'clock','checkpoint'].map(k=>[k,'synthetic_'+k])),trustedWorker:{settings:'synthetic_settings',operatorPolicy:'synthetic_policy',activity:'synthetic_control'},pgstream:{slot:'synthetic_slot',receiver:{url:'http://evaluator:19913/',trust:'network',bindHost:'0.0.0.0',maxBytes:16777216,timeoutMs:5000}}};}
function assertWiring(routes,wire,config){
 const keys=routes.map(r=>r.schema+'.'+r.table);
 for(const domain of domains)assert(keys.includes(config.namespaces[domain]+'.'+domain),'DEFAULT_CLINICAL_ROUTE_MISSING:'+domain);
 const plugin=wire.source.postgres.replication.plugin;
 assert.equal(plugin.include_xids,true,'DEFAULT_XID_NOT_ENABLED');
 const admitted=plugin.add_tables.split(',');
 for(const domain of domains)assert(admitted.includes(config.namespaces[domain]+'.'+domain),'DECODER_CLINICAL_ROUTE_MISSING:'+domain);
 assert(!admitted.includes(config.namespaces.checkpoint+'.tenant_consumer_checkpoint'),'OUTPUT_FEEDBACK_ROUTE');
 assert.equal(wire.target.webhooks.notifier.worker_count,1,'COHORT_DELIVERY_ORDER');
 assert.equal(wire.target.webhooks.notifier.strict_mode,true,'FAILED_RECEIPT_MUST_BLOCK_TRANSPORT');
}
function run(core,deploy){
 const config=fixture(),evaluator=require(path.join(core,'lib/pgstream/evaluator.js'));
 const deployment=loadDeployment(path.join(deploy,'bindings/compose/multitenant/pgstream.js'),core);
 const routes=evaluator.routes(config),wire=deployment.wire(config,'postgresql://synthetic:synthetic@postgres/materializer_test');
 assertWiring(routes,wire,config);
 // Mechanism controls remove actual clinical routes or XID decoding from the
 // observed export values. Each must fail for the named symptom; then restore.
 const controls=[['five-route-clock-feed',()=>assertWiring(routes.filter(r=>!domains.includes(r.table)),wire,config),/DEFAULT_CLINICAL_ROUTE_MISSING/],['missing-xids',()=>{const broken=structuredClone(wire);delete broken.source.postgres.replication.plugin.include_xids;assertWiring(routes,broken,config);},/DEFAULT_XID_NOT_ENABLED/],['decoder-filter-loses-rows',()=>{const broken=structuredClone(wire);broken.source.postgres.replication.plugin.add_tables=broken.source.postgres.replication.plugin.add_tables.split(',').filter(t=>t!==config.namespaces.entries+'.entries').join(',');assertWiring(routes,broken,config);},/DECODER_CLINICAL_ROUTE_MISSING/]];
 for(const[name,control,symptom]of controls){assert.throws(control,symptom,name+':ABLATION_MUST_FAIL');assertWiring(routes,wire,config);}
 return {verdict:'PASS',scope:'source-only maintained default route/wire; no runtime/clinical/recovery/capacity claim',controls:controls.map(c=>c[0])};
}
module.exports={run,assertWiring,fixture};
if(require.main===module){try{if(process.argv.length!==4)throw Error('Usage: node materializer-default-control.cjs APP_WORKTREE DEPLOY_WORKTREE');console.log(JSON.stringify(run(path.resolve(process.argv[2]),path.resolve(process.argv[3]))));}catch(error){console.error(error.message);process.exitCode=1;}}
