'use strict';
const assert = require('node:assert/strict');
const SUBJECT = '000000000000000000000001';
const CATALOGUE = Object.freeze(['entries', 'treatments', 'devicestatus'].flatMap(d =>
  ['read', 'create'].map(a => 'api:' + d + ':' + a)));
async function readiness (authority, tenant, subjectId) {
  const principal = { kind: 'subject', subjectId };
  const snapshot = await authority.subjectSnapshot({ tenant, principal });
  assert.ok(snapshot && typeof snapshot.sub === 'string', 'explicit lab subject snapshot required');
  for (const permission of CATALOGUE) assert.equal(await authority.authorize({ tenant, principal, permission }), true,
    'initial provisioned subject must be admitted: ' + permission);
}
function measureRefusal (record, before, after) {
  return { protectedRefused: !!record && record.status === 401, storedUnchanged: require('node:util').isDeepStrictEqual(after, before) };
}
function assertRefusal (record, before, after) {
  // Client exit codes are not the protocol oracle: oref0 curl lacks --fail.
  const evidence = measureRefusal(record, before, after);
  assert.deepEqual(evidence, { protectedRefused: true, storedUnchanged: true },
    'tightening requires existing v1 HTTP 401 and independently unchanged stored state');
}
function compareAdmitted (reference, selected) {
  assert.deepEqual(selected, reference, 'admitted subject client reply/stored values must match unselected reference');
}
module.exports = { SUBJECT, CATALOGUE, readiness, measureRefusal, assertRefusal, compareAdmitted };
