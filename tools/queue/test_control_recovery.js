'use strict';

// Instrument/parser checks only; these are not application runtime evidence.
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { cases, mutate, verify, validateAudit } = require('./gates/_control-recovery');
const repository = process.argv[2];
const ref = process.argv[3];
assert.ok(repository && ref, 'Pass the frozen application repository and commit');
assert.throws(() => validateAudit('owner-reader', []), /missing or incomplete/);
const owned = { container: 'ns-tenant-authority-pg-0123456789abcdef', containerRemoved: true, volumeIds: null };
assert.throws(() => validateAudit('owner-reader', [owned]), /missing or incomplete/);
validateAudit('owner-reader', [{ ...owned, volumeIds: ['synthetic-volume'] }]);
for (const [suite, item] of Object.entries(cases)) {
  for (const [file, before, after] of Object.values(item.controls)) {
    const source = execFileSync('git', ['-C', repository, 'show', ref + ':' + file], { encoding: 'utf8' });
    assert.notEqual(mutate(source, before, after), source);
    assert.throws(() => mutate('', before, after), /exactly one/);
    assert.throws(() => mutate(before + before, before, after), /exactly one/);
  }
  const green = { stats: { tests: item.passes, passes: item.passes, failures: 0, pending: 0 }, failures: [] };
  verify(suite, green, 0);
  assert.throws(() => verify(suite, green, 1), /cohort/);
  assert.throws(() => verify(suite, green, 0, true), /setup failure/);
  if (suite === 'projection-evaluator') {
    for (const control of ['identity', 'bootstrap']) {
      const failure = { stats: { tests: 1, passes: 0, failures: 1, pending: 0 }, failures: [{
        fullTitle: 'native clinical suite ' + item.controls[control][3],
        err: { code: 'ERR_ASSERTION', actual: control === 'identity' ? '111' : 'undefined',
          expected: control === 'identity' ? '222' : '123', message: control === 'identity'
            ? 'clinical newest reading survives typed replay' : 'advanced empty cache must reconstruct clinical state' }
      }] };
      verify(suite, failure, 1, control);
      const original = { ...failure.failures[0].err };
      for (const invalid of [null, false, '111extra', 'NaN', control === 'identity' ? '112' : '0']) {
        failure.failures[0].err.actual = invalid;
        assert.throws(() => verify(suite, failure, 1, control), /unexpected clinical assertion/);
      }
      failure.failures[0].err = { ...original, code: undefined, name: 'TypeError' };
      assert.throws(() => verify(suite, failure, 1, control), /setup failure/);
      failure.failures[0].err = { ...original, message: 'unrelated failure' };
      assert.throws(() => verify(suite, failure, 1, control), /unexpected clinical assertion/);
      failure.failures[0].err = original;
      failure.failures[0].fullTitle = 'before hook setup';
      assert.throws(() => verify(suite, failure, 1, control), /unexpected clinical assertion/);
    }
    continue;
  }
  const failure = { stats: { tests: 1, passes: 0, failures: 1, pending: 0 },
    failures: [{ err: { code: 'ERR_ASSERTION', actual: suite === 'owner-reader' ? [true, true, true] : 1,
      expected: suite === 'owner-reader' ? [false, false, false] : 2 } }] };
  verify(suite, failure, 1, true);
  if (suite === 'owner-reader') {
    failure.failures[0].err.actual = '[\n  true\n  true\n  true\n]';
    failure.failures[0].err.expected = '[\n  false\n  false\n  false\n]';
    verify(suite, failure, 1, true);
    for (const invalid of ['[true true]', '[true false true]', '[true true true] extra', [true, true], [true, false, true]]) {
      failure.failures[0].err.actual = invalid;
      assert.throws(() => verify(suite, failure, 1, true), /unexpected assertion/);
    }
  }
  failure.failures[0].err.code = 'ECONNREFUSED';
  assert.throws(() => verify(suite, failure, 1, true), /setup failure/);
  failure.failures[0].err.code = 'ERR_ASSERTION';
  failure.failures[0].err.actual = 'unrelated assertion';
  assert.throws(() => verify(suite, failure, 1, true), /unexpected assertion/);
}
console.log('PASS instrument-only strict mutations and result classification; runtime UNMEASURED');
