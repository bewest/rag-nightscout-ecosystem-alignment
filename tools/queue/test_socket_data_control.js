'use strict';

// Instrument checks only, no application runtime or fixtures started.
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const socket = require('./gates/_socket-data-control');
const [repository, ref] = process.argv.slice(2);
assert(repository && ref, 'Pass frozen application repository and commit');
const show = file => execFileSync('git', ['-C', repository, 'show', ref + ':' + file], { encoding: 'utf8' });
const original = show(socket.definition.file), adapted = socket.adapt(original);
assert.notEqual(adapted, original);
assert.throws(() => socket.adapt(''), /exactly one/);
assert.throws(() => socket.adapt(original + original), /exactly one/);
for (const [, needle] of Object.values(socket.definition.controls)) {
  assert.equal(show('lib/server/tenant-socket-forwarding.js').split(needle).length, 2);
}
const clone = data => JSON.parse(JSON.stringify(data));
const proofs = {
  earlyack: { kind: 'earlyack', postWrite: true, acknowledged: true, current: [], eventCount: 0, events: 0 },
  role: { kind: 'role', observation: 'callback', acknowledged: true, before: [], current: [{ _id: 'synthetic', srvModified: 123 }],
    expectedForeign: [], foreign: [], eventCount: 0, events: 1 }
};
function red (control) {
  return { stats: { tests: 1, passes: 0, failures: 1, pending: 0 }, failures: [{
    fullTitle: 'native socket suite ' + socket.definition.controls[control][3],
    err: { code: 'ERR_ASSERTION', actual: control === 'earlyack' ? true : 1, expected: control === 'earlyack' ? false : 0,
      message: control === 'earlyack' ? 'socket success callback observed before API COMMIT with uncommitted stored row' :
        'socket role substitution changed committed tenant A row count' }
  }] };
}
for (const control of Object.keys(proofs)) {
  socket.verify(red(control), 1, control, [proofs[control]]);
  assert.throws(() => socket.verify(red(control), 1, control), /physical observation missing/);
  for (const code of [undefined, 'ETIMEDOUT', 'ECONNREFUSED']) {
    const report = red(control); report.failures[0].err.code = code;
    assert.throws(() => socket.verify(report, 1, control, [proofs[control]]), /setup\/timeout/);
  }
  const unrelated = red(control); unrelated.failures[0].err.message = 'unrelated assertion';
  assert.throws(() => socket.verify(unrelated, 1, control, [proofs[control]]), /unexpected socket assertion/);
  const invalidCase = red(control); invalidCase.failures[0].fullTitle = 'before hook';
  assert.throws(() => socket.verify(invalidCase, 1, control, [proofs[control]]), /unrelated case/);
  for (const actual of [null, 'extra', 99, control === 'earlyack' ? false : 0]) {
    const report = red(control); report.failures[0].err.actual = actual;
    assert.throws(() => socket.verify(report, 1, control, [proofs[control]]), /unexpected socket assertion/);
  }
  const wrong = clone(proofs[control]); wrong.events += 1;
  assert.throws(() => socket.verify(red(control), 1, control, [wrong]), /physical symptom/);
}
const notReached = clone(proofs.earlyack); notReached.postWrite = false;
assert.throws(() => socket.verify(red('earlyack'), 1, 'earlyack', [notReached]), /physical symptom/);
const notCommitted = clone(proofs.role); notCommitted.current = [];
assert.throws(() => socket.verify(red('role'), 1, 'role', [notCommitted]), /physical symptom/);
const restored = { stats: { tests: 4, passes: 4, failures: 0, pending: 0 }, failures: [] };
const restoredProof = [{ ...proofs.earlyack, acknowledged: false },
  { ...proofs.role, observation: 'refused', acknowledged: false, current: [], events: 0 }];
socket.verify(restored, 0, undefined, restoredProof);
assert.throws(() => socket.verify(restored, 0, undefined, []), /Missing restored/);
const output = 'Single reference child started: {"pid":123,"mode":"single"}\n' +
  'Single reference child cleanup: {"pid":123,"code":0,"signal":null,"absent":true}\n';
assert.equal(socket.auditChild(output, () => false).independentlyAbsent, true);
assert.throws(() => socket.auditChild(output, () => true), /audit failed/);
assert.throws(() => socket.auditChild(output + output, () => false), /missing\/ambiguous/);
assert.throws(() => socket.auditChild('', () => false), /missing\/ambiguous/);
console.log('PASS socket instrument strict source/oracle/classifier/child-audit checks; native UNMEASURED');
