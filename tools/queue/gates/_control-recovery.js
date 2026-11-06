'use strict';

// Narrow properties only. Native fixtures and product modules come from one archive.
const cases = {
  'owner-reader': {
    file: 'tests/tenant-authorization-postgres.integration.test.js',
    flag: 'NS_TENANT_AUTHORITY_POSTGRES_DOCKER_TEST', passes: 12,
    controls: { intersection: ['lib/subject-admin/owner-policy.js',
      'project.has(permission) && ceiling.has(permission)', 'true',
      'bounds old subject grants on fresh selected PostgreSQL snapshots across independent pools'] }
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
function verify (suite, report, status, control) {
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
  const owner = suite === 'owner-reader';
  if (owner ? JSON.stringify(err.actual) !== JSON.stringify([true, true, true]) ||
      JSON.stringify(err.expected) !== JSON.stringify([false, false, false]) :
    Number(err.actual) !== 1 || Number(err.expected) !== 2) {
    throw new Error('CONTROL-INVALID: unexpected assertion symptom');
  }
  console.log('CONTROL-SEMANTIC: ' + (owner ? 'fresh tightened ceiling allowed all three protected operations' :
    'typed projection collapsed to one row while two stored identities remain'));
}
function validateAudit (suite, captured) {
  if (suite !== 'owner-reader') return;
  if (!Array.isArray(captured) || captured.length !== 1 ||
      !/^ns-tenant-authority-pg-[0-9a-f]{16}$/.test(captured[0].container) ||
      (captured[0].containerRemoved && !Array.isArray(captured[0].volumeIds))) {
    throw new Error('Owned owner-reader lifecycle audit missing or incomplete');
  }
}
module.exports = { cases, mutate, verify, validateAudit };
