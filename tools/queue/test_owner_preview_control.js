'use strict';
// Source/parser/oracle regression checks ONLY. No service, socket or DB starts.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { execFileSync } = require('node:child_process');
const owner = require('./gates/_owner-preview-control');
const bounded = require('./gates/_control-recovery');
assert.equal(bounded.cases['owner-preview'], owner.definition);
const [repository, ref] = process.argv.slice(2);
assert(repository && ref, 'Pass frozen application repository and commit');
const show = file => execFileSync('git', ['-C', repository, 'show', ref + ':' + file], { encoding: 'utf8' });
const original = show(owner.definition.file), adapted = owner.adapt(original);
assert.equal(original.split('await start(missing, {}, false)').length, 2);
assert.equal(original.split('await start(config(), { OWNER_READER: process.env.NS_TEST_POSTGRES_ADMIN_URI }, false)').length, 2);
new vm.Script(adapted, { filename: 'archived-owner-oracle.js' });
assert.notEqual(adapted, original);
assert.throws(() => owner.adapt(''), /exactly one/);
assert.throws(() => owner.adapt(original + original), /exactly one/);
for (const [file, needle, replacement] of Object.values(owner.definition.controls)) {
  const source = show(file); assert.equal(source.split(needle).length, 2);
  new vm.Script(source.replace(needle, replacement), { filename: file });
}
const clone = value => JSON.parse(JSON.stringify(value));
const A = '11111111-1111-4111-8111-111111111111', B = '22222222-2222-4222-8222-222222222222';
const subjects = '"synthetic_auth".tenant_authorization_subjects';
const links = '"synthetic_auth".tenant_authorization_subject_roles';
const creds = '"synthetic_creds".legacy_credential_subjects';
const audit = '"synthetic_auth".tenant_subject_admin_audit';
function state (name = 'target', count = 0) {
  return { [subjects]: [{ tenant_id: A, subject_id: 'target', display_name: name }, { tenant_id: B, subject_id: 'target', display_name: 'foreign' }],
    [links]: [], [creds]: [], [audit]: Array.from({ length: count }, (_, i) => ({ tenant_id: A, event_id: '00000000-0000-4000-8000-' + String(i + 10).padStart(12, '0'), principal: 'manager', consumer: 'owner-preview', subject_id: 'target', operation: 'update' })) };
}
const first = state('Cache Warmup 0', 1), second = state('Cache Warmup 1', 2);
const warm = [{ kind: 'warmup', index: 0, pid: 101, status: 200, before: state(), current: first, auditDelta: 1 },
  { kind: 'warmup', index: 1, pid: 102, status: 200, before: first, current: second, auditDelta: 1 }];
const revocation = { table: 'credentials', column: 'enabled', disabled: false, observed: [false] };
const stale = { kind: 'protected', phase: 'revocation', pid: 101, status: 200, expectedStatus: 401,
  before: second, current: state('Updated', 3), baselineAfterWarmup: second, revocation, auditDelta: 1 };
const exposure = { kind: 'listener', pid: 103, status: 200, before: state(), current: state('Wrong Plane', 1), auditDelta: 1 };
function report (control) { return { stats: { tests: 1, passes: 0, failures: 1, pending: 0 }, failures: [{
  fullTitle: 'actual owner suite ' + owner.definition.controls[control][3],
  err: { code: 'ERR_ASSERTION', actual: true, expected: false,
    message: control === 'snapshot' ? owner.physicalMessage : owner.listenerMessage }
}] }; }
for (const [control, proofs] of [['snapshot', [...warm, stale]], ['listener', [exposure]]]) {
  owner.verify(report(control), 1, control, proofs);
  bounded.verify('owner-preview', report(control), 1, control, proofs);
  assert.throws(() => owner.verify(report(control), 1, control), /physical observations/);
  assert.throws(() => owner.verify(report(control), 0, control, proofs), /setup\/timeout/);
  for (const code of [undefined, 'ETIMEDOUT', 'ECONNREFUSED']) {
    const r = report(control); r.failures[0].err.code = code;
    assert.throws(() => owner.verify(r, 1, control, proofs), /setup\/timeout/);
  }
  const wrongCase = report(control); wrongCase.failures[0].fullTitle = 'before hook';
  assert.throws(() => owner.verify(wrongCase, 1, control, proofs), /unrelated case/);
  const unrelated = report(control); unrelated.failures[0].err.message = 'different assertion';
  assert.throws(() => owner.verify(unrelated, 1, control, proofs), /assertion symptom/);
  const noEffect = clone(proofs); noEffect.at(-1).current = clone(noEffect.at(-1).before); noEffect.at(-1).auditDelta = 0;
  assert.throws(() => owner.verify(report(control), 1, control, noEffect), /mutation|change/);
  const statusOnly = clone(proofs); statusOnly.at(-1).auditDelta = 0;
  assert.throws(() => owner.verify(report(control), 1, control, statusOnly), /mutation|change/);
  const foreignChanged = clone(proofs); foreignChanged.at(-1).current[subjects][1].display_name = 'changed';
  assert.throws(() => owner.verify(report(control), 1, control, foreignChanged), /mutation|change/);
}
// UUID audit IDs sort independently of event time: a newly committed record
// may be first, so proof must use identity/set delta rather than array suffix.
const reordered = clone([...warm, stale]);
const oldRows = reordered[2].current[audit].slice(0, 2);
const newest = { ...reordered[2].current[audit][2], event_id: '00000000-0000-4000-8000-000000000000' };
reordered[2].current[audit] = [newest, ...oldRows];
owner.verify(report('snapshot'), 1, 'snapshot', reordered);
for (const mutate of [p => { p.shift(); }, p => { p[0].status = 401; }, p => { p[1].pid = p[0].pid; },
  p => { p[2].before = state(); }, p => { p[2].revocation.observed = [true]; }]) {
  const proofs = clone([...warm, stale]); mutate(proofs);
  assert.throws(() => owner.verify(report('snapshot'), 1, 'snapshot', proofs), /warmup|mutation/);
}
const green = { stats: { tests: 9, passes: 9, failures: 0, pending: 0 }, failures: [] };
const schedules = [['credentials', 'enabled', false], ['credentials', 'generation', 2],
  ['sessions', 'active', false], ['sessions', 'generation', 2], ['sessions', 'expires_at', 1],
  ['keys', 'active', false], ['tenants', 'active', false]];
const restored = [...clone(warm), ...Array.from({ length: 14 }, (_, i) => ({ kind: 'protected', phase: 'revocation',
  pid: 101 + i % 2, status: 401, expectedStatus: 401, before: second, current: second,
  baselineAfterWarmup: second, revocation: { table: schedules[Math.floor(i / 2)][0], column: schedules[Math.floor(i / 2)][1],
    disabled: schedules[Math.floor(i / 2)][2], observed: [schedules[Math.floor(i / 2)][2]] }, auditDelta: 0 })),
{ kind: 'listener', status: 405, before: second, current: second, auditDelta: 0 }];
owner.verify(green, 0, undefined, restored);
bounded.verify('owner-preview', green, 0, undefined, restored);
assert.throws(() => owner.verify(green, 0, undefined, []), /warmup/);
const missing = clone(restored); missing.pop(); assert.throws(() => owner.verify(green, 0, undefined, missing), /restored/);
const wrongGreen = clone(green); wrongGreen.stats.pending = 1;
assert.throws(() => owner.verify(wrongGreen, 0, undefined, restored), /cohort/);
const children = (count, listener = false) => Array.from({ length: count }, (_, i) => {
  const roles = listener && i === count - 1 ? 'tenant-admin,api' : 'tenant-admin';
  const noBind = count === 6 && [2, 3].includes(i);
  return [{ kind: 'worker-start', pid: i + 1, roles, expectedReady: !noBind }, { kind: 'worker-stop', pid: i + 1, roles,
    code: noBind ? 1 : listener && i === count - 1 ? null : 0, signal: listener && i === count - 1 ? 'SIGKILL' : null,
    listeningMarker: !noBind, portPresent: !noBind }];
}).flat();
assert.equal(owner.auditChildren(children(2), 'snapshot', () => false).length, 2);
assert.equal(owner.auditChildren(children(3, true), 'listener', () => false).length, 3);
assert.equal(owner.auditChildren(children(6), undefined, () => false).length, 6);
assert.throws(() => owner.auditChildren(children(2), 'snapshot', () => true), /absence audit/);
assert.throws(() => owner.auditChildren([], 'snapshot', () => false), /missing\/ambiguous/);
for (const mutate of [p => { p[1].code = 1; }, p => { delete p[5].listeningMarker; },
  p => { p[5].listeningMarker = true; }, p => { p[4].expectedReady = true; p[0].expectedReady = false; },
  p => { p[5].portPresent = true; }, p => { delete p[4].expectedReady; }]) {
  const proof = children(6); mutate(proof);
  assert.throws(() => owner.auditChildren(proof, undefined, () => false), /classification|lifecycle/);
}

owner.validateAudit([], 'snapshot');
const containers = ['pg', 'vault'].map(kind => ({ container: 'ns-preview-replicas-' + kind + '-0123456789abcdef',
  volumeIds: Array.from({ length: kind === 'pg' ? 1 : 2 }, (_, i) => kind + '-synthetic-volume-' + i), containerRemoved: true }));
owner.validateAudit(containers);
bounded.validateAudit('owner-preview', containers);
assert.throws(() => owner.validateAudit([]), /missing\/incomplete/);
assert.throws(() => owner.validateAudit([containers[0], containers[0]]), /missing\/incomplete/);
console.log('PASS owner archived source, strict physical oracle, warmup, child and owned-container parser checks; native UNMEASURED');
