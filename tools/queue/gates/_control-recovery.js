'use strict';

// Narrow properties only. Native fixtures and product modules come from one archive.
const socket = require('./_socket-data-control');
const ownerPreview = require('./_owner-preview-control');
const cases = {
  'owner-preview': ownerPreview.definition,
  'socket-data-forwarding': socket.definition,
  'projection-evaluator': {
    file: 'tests/tenant-projection-evaluator.integration.test.js',
    flag: 'NS_TENANT_PROJECTION_EVALUATOR_TEST', passes: 7,
    controls: {
      identity: ['lib/storage/postgres-durable-replay.js',
        'JSON.stringify([row.domain, row.id_kind, row.doc._id])',
        'JSON.stringify([row.domain, row.doc._id])',
        'preserves typed twins in SQL and the current clinical reading after replay'],
      bootstrap: ['lib/storage/postgres-durable-replay.js',
        'bootstrapped ? -1 : previous', 'previous',
        'bootstraps an advanced empty projection into the same current clinical reading']
    }
  },
  'durable-replay': {
    file: 'tests/tenant-durable-replay.integration.test.js',
    flag: 'NS_TENANT_DURABLE_REPLAY_TEST', passes: 7,
    controls: { identity: ['lib/storage/postgres-durable-replay.js',
      'JSON.stringify([row.domain, row.id_kind, row.doc._id])',
      'JSON.stringify([row.domain, row.doc._id])',
      'bootstraps an advanced empty cache and completes typed tied pages then soft deletes'] }
  }
};
function mutate (source, before, after) {
  if (source.split(before).length !== 2) throw new Error('CONTROL-INVALID: expected exactly one source match');
  return source.replace(before, after);
}
function verify (suite, report, status, control, proofs) {
  if (suite === 'owner-preview') return ownerPreview.verify(report, status, control, proofs);
  if (suite === 'socket-data-forwarding') return socket.verify(report, status, control, proofs);
  const expected = cases[suite];
  if (!control) {
    if (status !== 0 || report.stats.tests !== expected.passes || report.stats.passes !== expected.passes ||
        report.stats.failures !== 0 || report.stats.pending !== 0) throw new Error('Unexpected bounded cohort result');
    return;
  }
  const failure = report.failures[0];
  if (status !== 1 || report.stats.tests !== 1 || report.stats.failures !== 1 ||
      report.stats.passes !== 0 || report.stats.pending !== 0 || failure?.err.code !== 'ERR_ASSERTION') {
    throw new Error('CONTROL-INVALID: setup failure is not a semantic control');
  }
  const err = failure.err;
  if (suite === 'projection-evaluator') {
    if (!Object.hasOwn(expected.controls, control) ||
        !failure.fullTitle?.endsWith(expected.controls[control][3])) {
      throw new Error('CONTROL-INVALID: unexpected clinical assertion case');
    }
    const exact = (actual, value) => actual === value || actual === String(value);
    const valid = control === 'identity'
      ? exact(err.actual, 111) && exact(err.expected, 222) &&
        err.message?.includes('clinical newest reading survives typed replay')
      : (err.actual === undefined || err.actual === 'undefined') && exact(err.expected, 123) &&
        err.message?.includes('advanced empty cache must reconstruct clinical state');
    if (!valid) throw new Error('CONTROL-INVALID: unexpected clinical assertion symptom');
    console.log('CONTROL-SEMANTIC: ' + (control === 'identity'
      ? 'clinical current reading111 instead222 while independent stored typed twins remain'
      : 'clinical current reading missing instead123 after advanced empty bootstrap'));
    return;
  }
  if (Number(err.actual) !== 1 || Number(err.expected) !== 2) {
    throw new Error('CONTROL-INVALID: unexpected assertion symptom');
  }
  console.log('CONTROL-SEMANTIC: typed projection collapsed to one row while two stored identities remain');
}
function validateAudit (suite, captured, control) {
  if (suite === 'owner-preview') return ownerPreview.validateAudit(captured, control);

}
module.exports = { cases, mutate, verify, validateAudit };
