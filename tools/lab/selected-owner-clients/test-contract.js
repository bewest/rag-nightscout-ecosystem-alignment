'use strict';
// No Docker, listener or database. Reproduces the policy/oracle contract only.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { CATALOGUE, readiness, measureRefusal, assertRefusal, compareAdmitted } = require('./contract');
const source = process.env.SELECTED_OWNER_SOURCE;
assert.ok(source && path.isAbsolute(source), 'explicit frozen source required');
const { createOwnerReadPolicy, catalogueDigest } = require(path.join(source, 'lib/subject-admin/owner-policy'));
const selected = createOwnerReadPolicy({ catalogue: CATALOGUE }, 'TENANT_AUTHORITY_INVALID');
const row = ceiling => ({ anonymous_roles: ['denied'], owner_catalogue_digest: catalogueDigest(CATALOGUE), owner_ceiling: ceiling });
test('existing denied-anonymous config admits concrete initial subject groups and clamps tightened ceiling', () => {
  assert.deepEqual(selected.clamp([row(CATALOGUE)], [CATALOGUE]), [CATALOGUE]);
  assert.deepEqual(selected.clamp([row([])], [CATALOGUE]), [[]]);
  assert.equal(createOwnerReadPolicy(undefined, 'invalid'), null, 'unselected reference keeps its existing group path');
  assert.throws(() => selected.clamp([{ ...row(CATALOGUE), anonymous_roles: ['readable'] }], [CATALOGUE]), { code: 'TENANT_AUTHORITY_INVALID' });
  assert.throws(() => createOwnerReadPolicy({ catalogue: ['api:*:read'] }, 'invalid'), TypeError);
});
test('readiness only addresses the explicitly provisioned subject and all admitted operations', async () => {
  const calls = [];
  await readiness({ subjectSnapshot: async value => { calls.push(value); return { sub: 'synthetic viewer' }; },
    authorize: async value => { calls.push(value); return true; } }, 'synthetic-tenant', 'synthetic-subject');
  assert.ok(calls.every(c => c.principal.kind === 'subject' && c.principal.subjectId === 'synthetic-subject'));
  assert.deepEqual(calls.slice(1).map(c => c.permission), CATALOGUE);
  await assert.rejects(readiness({ subjectSnapshot: async () => null }, 'tenant', 'subject'), /snapshot required/);
});
test('HTTP and independent stored-state checks each reject their own corruption', () => {
  const before = { entries: [{ date: 100, sgv: 118 }] };
  const changed = { entries: [{ date: 100, sgv: 118 }, { date: 200, sgv: 119 }] };
  assert.deepEqual(measureRefusal({ status: 200 }, before, before), { protectedRefused: false, storedUnchanged: true });
  assert.deepEqual(measureRefusal({ status: 401 }, before, changed), { protectedRefused: true, storedUnchanged: false });
  assert.throws(() => assertRefusal({ status: 200 }, before, before));
  assert.throws(() => assertRefusal({ status: 401 }, before, changed));
  assertRefusal({ status: 401 }, before, before);
});
test('ablated intersection retains permission and both tightening oracle predicates go red; restoration passes', () => {
  const before = { rows: [] };
  const hasGrant = groups => groups.flat().includes('api:entries:create');
  const evaluate = groups => hasGrant(groups) ? { record: { status: 200 }, after: { rows: [{ synthetic: true }] } }
    : { record: { status: 401 }, after: before };
  const ablated = evaluate([CATALOGUE]); // models the exact archived filter ablation, not HTTP execution
  assert.deepEqual(measureRefusal(ablated.record, before, ablated.after), { protectedRefused: false, storedUnchanged: false });
  assert.throws(() => assertRefusal(ablated.record, before, ablated.after));
  const restored = evaluate(selected.clamp([row([])], [CATALOGUE]));
  assertRefusal(restored.record, before, restored.after);
});
test('admitted comparison rejects an unexpected payload difference and accepts restoration', () => {
  const reference = { st: '200', documents: [{ sgv: 118 }] };
  assert.throws(() => compareAdmitted(reference, { ...reference, documents: [{ sgv: 119 }] }));
  compareAdmitted(reference, structuredClone(reference));
});
