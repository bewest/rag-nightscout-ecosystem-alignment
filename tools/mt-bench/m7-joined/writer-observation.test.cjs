'use strict';
const assert = require('node:assert/strict');
const {createHash} = require('node:crypto');
const oracle = require('./completed-oracle.cjs');
const fixture = require('./native-observation-fixture.cjs');
const {evaluator, realtime, binding, row, witness, clients} = structuredClone(fixture);
delete evaluator.pgstream;
evaluator.inputTransport = 'writer-driven';
Object.assign(evaluator.postgres.namespaces, {treatments:'synthetic_treatments', devicestatus:'synthetic_devicestatus'});
const config = oracle.source(evaluator, realtime, binding);
assert(!config.native);
assert(oracle.writerBaseline(config).includes('"synthetic_control".tenant_lifecycle_windows'));
const sql = oracle.query(config, [row.tenant], 'synthetic');
assert(!sql.includes('slot') && !sql.includes('storage-events') && sql.includes('c.checkpoint::text'));
delete row.native;
row.writer = {identity:['12345', 1, 'synthetic_test'], generation:'1', phase:'active', evaluated:'102'};
row.stamp = '103';
row.stored[0].srvModified = 101;
witness.stamp = '103';
witness.writerTarget = {identity:row.writer.identity, generation:'1', before:'100', stamp:101, work:'910'};
// Core's native lifecycle contract (native-selection.js), which a writer-driven evaluator selects.
const CODEC = ['canonical-maintenance-active-plus2-v1', 'positive-int8-complete-pair-max-4611686018427387902-v1'];
row.typed.contractDigest = createHash('sha256').update(JSON.stringify([config.kind, config.checkpoint, evaluator.consumer, ...CODEC])).digest('hex');
const threePartDigest = createHash('sha256').update(JSON.stringify([config.kind, config.checkpoint, evaluator.consumer])).digest('hex');
row.state.observed = {clock:'920'};
row.state.completed = {clock:'910'};
row.typed.observed = ['920', null, null, null, null, null];
row.typed.completed = ['910', null, null, null, null, null];
row.state.output.inputCheckpoint = 101;
Object.assign(row.state.output.result, {checkpoint:101, generation:'1', progress:'level-window'});

if (process.argv[2] === 'fixture') {
  console.log(JSON.stringify({config,row,witness,clients}));
} else {
  const proof = value => oracle.assess(value, witness, clients, 2, config);
  assert(proof(row).ready);
  for (const [name, change, code] of [
    ['stale acquisition', r=>{r.writer.evaluated='100';r.state.output.inputCheckpoint=100;r.state.output.result.checkpoint=100;}, 'M7_COMPLETION_PENDING'],
    ['dirty version taken before write', r=>{r.typed.completed[0]='909';r.state.completed.clock='909';}, 'M7_COMPLETION_STATE'],
    ['new restoration', r=>{r.writer.generation='2';}, 'M7_COMPLETION_STATE'],
    ['old retained body', r=>{r.state.output.result.generation='2';}, 'M7_COMPLETION_STATE'],
    ['different database', r=>{r.writer.identity[2]='other';}, 'M7_COMPLETION_STATE'],
    ['wrong transport', r=>{r.state.output.result.progress='current-snapshot';}, 'M7_COMPLETION_STATE'],
    ['stale timing marker', r=>{r.stored[0].srvModified=100;}, 'M7_COMPLETION_STATE'],
    ['contract without the lifecycle codec', r=>{r.typed.contractDigest=threePartDigest;}, 'M7_COMPLETION_TYPED_STATE'],
    ['corrupt clinical value', r=>{r.state.output.result.properties.bgnow.mean++;}, 'M7_COMPLETION_BG_NOW'],
  ]) {
    const changed=structuredClone(row);
    change(changed);
    assert.equal(proof(changed).code, code, name);
    assert(proof(row).ready);
  }
}
