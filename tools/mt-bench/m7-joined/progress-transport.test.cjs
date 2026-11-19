'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const transport=require('./progress-transport.cjs'),oracle=require('./completed-oracle.cjs');
const {config,row}=require('./native-observation-fixture.cjs');
// Authored independent wire fixture: duplicates deliberately remain distinct
// so a wrong state/typed pair cannot be repaired by transport reconstruction.
function wire(r){return [r.tenant,r.stamp,
 [r.typed.version,r.typed.contractDigest,r.typed.observed,r.typed.completed,r.typed.identity,r.typed.digest,r.typed.revision,r.typed.generation,r.typed.enabled,r.typed.arrayBounds,r.typed.dueAt,r.typed.completedAt,r.typed.pendingAt,r.typed.bodyMetadataAbsent,r.typed.inputFloor],
 [r.state.kind,r.state.observed,r.state.completed,r.state.output===null?null:[r.state.output.tenant,r.state.output.identity,r.state.output.contentDigest,r.state.output.outputRevision,r.state.output.restoreGeneration]],r.native];}
const ids=[row.tenant],snapshot=r=>transport.snapshot([wire(r)],config,ids);
test('progress wire preserves every strict native snapshot field',()=>{
 assert.deepEqual(snapshot(row),oracle.progressSnapshot([row],config,ids));
 const sql=transport.query(config,ids);
 assert(sql.startsWith('SELECT '));assert(sql.includes('pg_control_system()'));
 assert(!sql.includes('jsonb_agg(e.doc)'));assert(!sql.includes("THEN (c.projection->0->'output')"));
 // The original clinical query is called independently with its complete body.
 assert(oracle.query(config,ids,'synthetic-native').includes('jsonb_agg(e.doc)'));
});
test('wire retains metadata, source, generation, restore and positional failures',()=>{
 for(const mutate of [r=>r.typed.contractDigest='0'.repeat(64),r=>r.typed.observed=[null,null,null,null,null,'1'],
   r=>r.state.output.identity='0'.repeat(64),r=>r.state.output.tenant='22222222-2222-4222-8222-222222222222',
   r=>r.typed.arrayBounds=false,r=>r.typed.bodyMetadataAbsent=false,
   r=>r.native.stream.source_identity={...r.native.actualSource,system_id:'2'},r=>r.native.currentRestore='2',
   r=>r.native.stream.generation='b'.repeat(32)+':1',r=>r.native.stream=null]){
  const bad=structuredClone(row);mutate(bad);assert.throws(()=>snapshot(bad));
  assert.deepEqual(snapshot(row),oracle.progressSnapshot([row],config,ids));
 }
 for(const mutate of [v=>v.pop(),v=>v[2].pop(),v=>v[3].pop(),v=>v[3][3].pop()]){
  const bad=wire(structuredClone(row));mutate(bad);assert.throws(()=>transport.snapshot([bad],config,ids),/TRANSPORT/);
 }
 assert.throws(()=>transport.snapshot([],config,ids),/COVERAGE/);
});
test('admission-only empty completion remains exact',()=>{
 const empty=structuredClone(row);empty.state.output=null;empty.state.completed={};
 Object.assign(empty.typed,{completed:[null,null,null,null,null,null],identity:null,digest:null,revision:'0',generation:null,inputFloor:'0'});
 assert.deepEqual(snapshot(empty),oracle.progressSnapshot([empty],config,ids));
});
test('inspection helper obeys the selected remaining round across RPC pages',async()=>{
 const fs=require('node:fs'),vm=require('node:vm'),source=fs.readFileSync(require.resolve('./evaluator-progress.cjs'),'utf8');
 async function run(code,selected){
  let now=0,rpcs=0,exit=null,lines=0;
  const ids=Array.from({length:513},(_,i)=>(i+1).toString(16).padStart(8,'0')+'-1111-4111-8111-111111111111');
  const prefix='const M7_PROGRESS_IDS='+JSON.stringify(ids)+',M7_PROGRESS_QUERY_BUDGET=5,M7_PROGRESS_BYTE_BUDGET=1048576;'+(selected===undefined?'':'const M7_PROGRESS_DEADLINE_MS='+selected+';');
  await vm.runInNewContext(prefix+code,{Date:{now:()=>now},Buffer,Promise,Object,Number,Math,
   setTimeout:()=>1,clearTimeout(){},process:{stdout:{write(){lines++;return true;}},stderr:{write(){}},set exitCode(v){exit=v;}},
   require(name){
    if(name==='./deploy/multitenant/service-environment')return{read:()=>({NS_SERVE_INTERNAL_SOCKET:'/synthetic/private.sock'})};
    if(name==='./lib/pool-membership/config')return{fromEnvironment:()=>({partitioned:false})};
    if(name==='./lib/server/internal-api/listener-config')return{resolve:()=>({peer:()=>({})})};
    if(name==='./lib/server/internal-api/clients')return{evaluatorInspection:()=>({async inspectEvaluator(){rpcs++;now+=4000;return{};}})};
    throw Error('FORBIDDEN_ADMISSION_OR_SQL:'+name);
   }});
  return{rpcs,exit,lines};
 }
 assert.deepEqual(await run(source),{rpcs:4,exit:1,lines:4});
 const green=async code=>assert.deepEqual(await run(code,30000),{rpcs:5,exit:null,lines:5});
 await green(source);
 const mutant=source.replace("const selected=typeof M7_PROGRESS_DEADLINE_MS==='undefined'?15000:M7_PROGRESS_DEADLINE_MS;",'const selected=15000;');
 assert.notEqual(mutant,source);await assert.rejects(()=>green(mutant),assert.AssertionError);await green(source);
 assert.deepEqual(await run(source,0),{rpcs:0,exit:1,lines:0});
});

test('both SQL selectors accept a roster above 10,000 and progress requires every row',()=>{
 const ids=Array.from({length:10001},(_,i)=>i.toString(16).padStart(8,'0')+'-1111-4111-8111-111111111111');
 const rows=ids.map(tenant=>wire({...row,tenant,state:{...row.state,output:{...row.state.output,tenant}}}));
 assert(oracle.query(config,ids,'synthetic-native').includes(ids.at(-1)));
 assert(transport.query(config,ids).includes(ids.at(-1)));
 assert.throws(()=>transport.snapshot(rows.slice(1),config,ids),/M7_OPPORTUNITY_COVERAGE/);
 assert.equal(transport.snapshot(rows,config,ids).rows.length,ids.length);
});
