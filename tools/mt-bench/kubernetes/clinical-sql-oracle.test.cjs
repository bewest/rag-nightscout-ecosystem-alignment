'use strict';
// Use the actual, unchanged clinical query/assessor with source-bound synthetic
// native receipts. No PostgreSQL or Kubernetes output is manufactured as a pass.
const assert=require('node:assert/strict'),oracle=require('../m7-joined/completed-oracle.cjs'),native=require('../m7-joined/native-observation.cjs');
const original=require('../m7-joined/native-observation-fixture.cjs'),f=structuredClone(original),c=f.config;
c.native.receipt={kind:'native-receipt-contract-v1',evaluatorConfigSha256:c.native.evaluatorConfigSha256,realtimeConfigSha256:c.native.realtimeConfigSha256,contractDigest:f.row.typed.contractDigest,
 selection:{selectionDigest:'d'.repeat(64),binding:{namespace:c.checkpoint,consumer:c.native.inputConsumer,lifecycleNamespace:c.native.lifecycle,generation:c.native.generation,source:structuredClone(f.row.native.actualSource)}}};
f.row.reader=structuredClone(c.binding);oracle.prepare(c);
f.witness.nativeTarget=native.snapshot(f.row,c);
const assess=row=>oracle.assess(row,f.witness,f.clients,2,c),green=()=>assert.equal(assess(f.row).ready,true);
green();
for(const [name,mutate] of [
 ['database',r=>{r.native.actualSource.database='foreign_test';r.native.stream.source_identity.database='foreign_test';}],
 ['system',r=>{r.native.actualSource.system_id='123456';r.native.stream.source_identity.system_id='123456';}],
 ['timeline',r=>{r.native.actualSource.timeline=2;r.native.stream.source_identity.timeline=2;}],
 ['generation',r=>r.native.stream.generation='b'.repeat(32)+':1'],
 ['restore',r=>{r.native.currentRestore='2';r.native.stream.generation=c.native.generation+':2';}],
 ['foreign-tenant',r=>r.tenant='22222222-2222-4222-8222-222222222222'],
 ['stale-completion',r=>{r.state.completed.bootstrap='1';r.typed.completed[5]='1';}],
 ['wrong-clinical-body',r=>r.state.output.result.properties.bgnow.mean=124],
 ['missing-frame',r=>r.state.output.frame.sgvs=[]],
 ['missing-stored-row',r=>r.stored=[]]
]){const bad=structuredClone(f.row);mutate(bad);const result=assess(bad);assert.equal(result.ready,false,name);green();console.log('RED_RESTORED native-clinical '+name+' '+result.code);}
const query=oracle.query(c,[f.row.tenant],'synthetic-clinical');
assert(query.startsWith('SELECT '));assert(query.includes('pg_control_system()')&&query.includes('pg_control_checkpoint()'));
assert(query.includes('l.generation::text')&&query.includes('jsonb_agg(e.doc)')&&query.includes("THEN (c.projection->0->'output')"));
console.log('PASS unchanged full clinical query and strict native/stored/frame/BG-now oracle; synthetic inputs only');
