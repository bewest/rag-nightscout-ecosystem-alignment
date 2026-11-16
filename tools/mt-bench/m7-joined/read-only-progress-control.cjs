'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require.resolve('./evaluator-progress.cjs'),'utf8');
async function run(code){
 let reads=0,rpcs=0,exit=null;const lines=[],values={SECRET:'never copied',NS_SERVE_INTERNAL_SOCKET:'/synthetic/private.sock'};
 const result=vm.runInNewContext('const M7_PROGRESS_IDS=["11111111-1111-4111-8111-111111111111"],M7_PROGRESS_QUERY_BUDGET=1,M7_PROGRESS_BYTE_BUDGET=1048576;\n'+code,{
 Date,Buffer,Promise,Object,setTimeout,clearTimeout,process:{env:{},stdout:{write(line){lines.push(line);return true;}},stderr:{write(){}},set exitCode(value){exit=value;}},
 require(name){
  if(name==='./deploy/multitenant/service-environment')return{read(){reads++;return values;}};
  if(name==='./lib/server/serve/evaluator-config')return{partitionFor(v){assert.equal(v,values);return{partitioned:false};}};
  if(name==='./lib/server/internal-api/listener-config')return{resolve(roles,v){assert.deepEqual(Object.keys(v),['NS_SERVE_INTERNAL_SOCKET']);return{peer(){return{};}};}};
  if(name==='./lib/server/internal-api/clients')return{evaluatorInspection(){return{async inspectEvaluator(){rpcs++;return{kind:'evaluator'};}};}};
  throw Error('FORBIDDEN_ADMISSION_OR_SQL:'+name);
 }});
 await result;return{reads,rpcs,exit,lines:lines.length};
}
(async()=>{
 assert.deepEqual(await run(source),{reads:1,rpcs:1,exit:null,lines:1});
 const mutant=source.replace("const values=require('./deploy/multitenant/service-environment').read();","require('./deploy/multitenant/load-env');const values={};");assert.notEqual(mutant,source);
 assert.deepEqual(await run(mutant),{reads:0,rpcs:0,exit:1,lines:0});
 assert.deepEqual(await run(source),{reads:1,rpcs:1,exit:null,lines:1});
 console.log('GREEN read-only progress; EXPECTED_RED admission loader; RESTORED_GREEN; recording RPC only');
})().catch(e=>{console.error(e);process.exitCode=1;});
