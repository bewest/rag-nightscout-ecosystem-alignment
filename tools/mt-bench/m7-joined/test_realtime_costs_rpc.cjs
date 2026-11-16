'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(process.env.M7_REALTIME_RPC_SOURCE||path.join(__dirname,'realtime-costs.cjs'),'utf8');
(async()=>{
  const calls=[],lines=[],requestBodies=[];
  const mock={process:{stdout:{write:text=>lines.push(text)},stderr:{write:()=>{}},exit:()=>{throw Error('TIMEOUT');}},Buffer,setTimeout,clearTimeout,require:name=>{
    if(name==='./deploy/multitenant/service-environment')return{read:()=>({XDG_RUNTIME_DIR:'/synthetic'})};
    if(name==='./lib/server/internal-api/listener-config')return{resolve:(roles,env)=>{assert.deepEqual(Array.from(roles),['realtime']);assert.equal(env.XDG_RUNTIME_DIR,'/synthetic');return{peer:(role,options)=>{assert.equal(role,'realtime');assert.equal(options.timeoutMs,5000);return options;}};}};
    if(name==='./lib/server/internal-api/clients')return{realtimeInspection:()=>({inspectRealtime:async(...args)=>{calls.push('inspectRealtime');requestBodies.push(args);if(args.length!==1||JSON.stringify(args[0])!=='{}')throw Object.assign(Error('request object required'),{code:'SOCKET_IPC_REQUEST_REFUSED'});return{kind:'realtime',processIncarnation:'synthetic',phase:'booted',ownerAvailable:true,stats:{version:1,delivery:{received:3,completed:2,retries:1,workQueries:4,metadataUpdates:2,metadataRows:16,maxMetadataBatch:16}},placement:{private:'not copied'}};}})};
    throw Error('UNEXPECTED_SURFACE:'+name);
  }};
  await vm.runInNewContext(source,mock);
  assert.deepEqual(calls,['inspectRealtime']);assert.equal(requestBodies[0].length,1,'RPC must supply one empty request object');assert.equal(JSON.stringify(requestBodies[0][0]),'{}');assert.equal(JSON.parse(lines[0]).placement,undefined);assert.equal(JSON.parse(lines[0]).stats.delivery.metadataRows,16);assert.equal(JSON.parse(lines[0]).stats.delivery.maxMetadataBatch,16);
  process.stdout.write('cached existing RPC only PASS; no tenant scan/query/warm surface reachable\n');
})().catch(error=>{console.error(error);process.exitCode=1;});
