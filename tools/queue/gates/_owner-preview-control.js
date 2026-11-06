'use strict';

// Defensive archived regression checks only. Product and synthetic test copies
// share one frozen source; no deployed service or production selection is used.
const definition = {
  file: 'tests/owner-preview.integration.test.js', flag: 'NS_OWNER_PREVIEW_TEST', passes: 9,
  controls: {
    snapshot: ['lib/server/serve/owner-preview-authentication.js',
      '  const authenticate = createAuthentication({ verifyToken: createVerifier(verification), snapshot });',
      `  let cachedSnapshot;
  const authenticate = createAuthentication({ verifyToken: createVerifier(verification),
    snapshot: async claims => {
      if (cachedSnapshot === undefined) cachedSnapshot = await snapshot(claims);
      return cachedSnapshot;
    } });`,
      'observes current credential/session/key/tenant revocation on the next operation across two independent workers'],
    listener: ['lib/server/serve/index.js', 'const { app } = preview ? ctx : role.createApp(env, ctx);',
      "const { app } = preview ? (spec.role === 'api' ? contexts['tenant-admin'] : ctx) : role.createApp(env, ctx);",
      'uses separate actual API and owner listeners in one CLI process with real PostgreSQL and Vault']
  }
};
const physicalMessage = 'owner protected request changed physical subject/link/credential/audit state before status assertion';
const listenerMessage = 'owner DATA listener changed physical owner state before refusal assertion';
const adaptations = [
  ["const assert = require('node:assert/strict');", `const assert = require('node:assert/strict');
const gateProofs = [];
let gatePhase = 'ordinary', gateBaseline, gateRevocation;
function gateRecord (proof) {
  gateProofs.push(proof);
  require('node:fs').writeFileSync(process.env.NS_OWNER_GATE_PROOF, JSON.stringify(gateProofs));
}`],
  ['      worker.child = child; children.add(worker);', `      worker.child = child; children.add(worker);
      gateRecord({ kind: 'worker-start', pid: child.pid, roles: 'tenant-admin' });`],
  ['      await worker.closed; children.delete(worker);', `      await worker.closed; children.delete(worker);
      gateRecord({ kind: 'worker-stop', pid: worker.child.pid, roles: 'tenant-admin',
        code: worker.child.exitCode, signal: worker.child.signalCode });`],
  [`      const before = await snapshot(); const response = await http(worker, credential, body, host);
      assert.equal(response.status, status, JSON.stringify(response.body)); assert.deepEqual(await snapshot(), before);`,
  `      const before = await snapshot(); const response = await http(worker, credential, body, host);
      const current = await snapshot();
      const effectsChanged = JSON.stringify(current) !== JSON.stringify(before);
      gateRecord({ kind: 'protected', phase: gatePhase, pid: worker.child.pid, status: response.status,
        expectedStatus: status, before, current, baselineAfterWarmup: gateBaseline, revocation: gateRevocation,
        auditDelta: current[t('tenant_subject_admin_audit')].length - before[t('tenant_subject_admin_audit')].length });
      assert.equal(effectsChanged, false, '${physicalMessage}');
      assert.deepEqual(current, before);
      assert.equal(response.status, status, JSON.stringify(response.body));`],
  [`    it('${definition.controls.snapshot[3]}', async function () {
      const credential = token();`,
  `    it('${definition.controls.snapshot[3]}', async function () {
      const credential = token();
      for (const [index, worker] of workers.entries()) {
        const before = await snapshot();
        const response = await http(worker, credential, { _id: TARGET, name: 'Cache Warmup ' + index, roles: ['reader'] });
        const current = await snapshot();
        const auditDelta = current[t('tenant_subject_admin_audit')].length - before[t('tenant_subject_admin_audit')].length;
        gateRecord({ kind: 'warmup', index, pid: worker.child.pid, status: response.status, before, current, auditDelta });
        assert.equal(response.status, 200, 'both real workers must authenticate while current authority is active');
        assert.equal(auditDelta, 1, 'each real worker warmup commits one independent audit event');
        assert.equal(current[t('tenant_authorization_subjects')].find(row => row.tenant_id === A && row.subject_id === TARGET).display_name,
          'Cache Warmup ' + index, 'independent target confirms valid authenticated warmup');
      }
      gateBaseline = await snapshot(); gatePhase = 'revocation';`],
  [`      }
    });
    it('retains transactional operator ceiling and current actor delegation fences',`,
  `      }
      gatePhase = 'ordinary'; gateBaseline = undefined; gateRevocation = undefined;
    });
    it('retains transactional operator ceiling and current actor delegation fences',`],
  ["        }, { roles: 'tenant-admin,api' });", `        }, { roles: 'tenant-admin,api' });
        gateRecord({ kind: 'worker-start', pid: combined.child.pid, roles: 'tenant-admin,api' });`],
  [`        assert([401, 403, 404, 405].includes(response.status), 'data listener must not expose management route: ' + response.status);
        assert.deepEqual(await snapshot(), before, 'data listener refusal must not mutate owner rows or audit');`,
  `        const current = await snapshot();
        const effectsChanged = JSON.stringify(current) !== JSON.stringify(before);
        gateRecord({ kind: 'listener', pid: combined.child.pid, status: response.status, before, current,
          auditDelta: current[t('tenant_subject_admin_audit')].length - before[t('tenant_subject_admin_audit')].length });
        assert.equal(effectsChanged, false, '${listenerMessage}');
        assert.deepEqual(current, before, 'data listener refusal must not mutate owner rows or audit');
        assert([401, 403, 404, 405].includes(response.status), 'data listener must not expose management route: ' + response.status);`],
  ['      } finally { await data.cleanup(); }', `      } finally {
        await data.cleanup();
        if (combined) gateRecord({ kind: 'worker-stop', pid: combined.child.pid, roles: 'tenant-admin,api',
          code: combined.exit?.code, signal: combined.exit?.signal });
      }`],
  ["        await admin.query(`UPDATE ${a(table)} SET \"${column}\"=$2 WHERE tenant_id=$1`, [A, disabled]);", "        await admin.query(`UPDATE ${a(table)} SET \"${column}\"=$2 WHERE tenant_id=$1`, [A, disabled]);\n        const observed = (await admin.query(`SELECT \"${column}\" AS value FROM ${a(table)} WHERE tenant_id=$1`, [A])).rows.map(row => row.value);\n        assert(observed.length > 0 && observed.every(value => value === disabled || value === String(disabled)),\n          'independent operator read must confirm committed current-state revocation');\n        gateRevocation = { table, column, disabled, observed };"]
];
function adapt (source) {
  for (const [before, after] of adaptations) {
    if (source.split(before).length !== 2) throw new Error('CONTROL-INVALID: expected exactly one owner oracle boundary');
    source = source.replace(before, after);
  }
  return source;
}
const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
function table (state, name) {
  const keys = state && Object.keys(state).filter(key => key.endsWith('.' + name));
  if (!keys || keys.length !== 1 || !Array.isArray(state[keys[0]])) throw new Error('CONTROL-INVALID: owner physical table missing/ambiguous');
  return state[keys[0]];
}
function complete (state) {
  if (!state || Object.keys(state).length !== 4) throw new Error('CONTROL-INVALID: owner physical state is incomplete');
  for (const name of ['tenant_authorization_subjects', 'tenant_authorization_subject_roles', 'legacy_credential_subjects', 'tenant_subject_admin_audit']) table(state, name);
  return true;
}
function effect (proof, name) {
  if (!proof || !proof.before || !proof.current || !Number.isSafeInteger(proof.auditDelta)) return false;
  complete(proof.before); complete(proof.current);
  const subjects = state => table(state, 'tenant_authorization_subjects');
  const audit = state => table(state, 'tenant_subject_admin_audit');
  const target = state => subjects(state).filter(row => row.tenant_id === '11111111-1111-4111-8111-111111111111' && row.subject_id === 'target');
  const prior = target(proof.before), current = target(proof.current);
  const oldAudit = audit(proof.before), newAudit = audit(proof.current);
  const oldIds = new Set(oldAudit.map(row => row.event_id));
  const added = newAudit.filter(row => !oldIds.has(row.event_id));
  const foreign = state => Object.fromEntries(Object.entries(state).map(([key, rows]) =>
    [key, rows.filter(row => row.tenant_id === '22222222-2222-4222-8222-222222222222')]));
  return prior.length === 1 && current.length === 1 && prior[0].display_name !== name && current[0].display_name === name &&
    proof.auditDelta === 1 && newAudit.length === oldAudit.length + 1 && oldIds.size === oldAudit.length &&
    new Set(newAudit.map(row => row.event_id)).size === newAudit.length && added.length === 1 &&
    equal(newAudit.filter(row => oldIds.has(row.event_id)), oldAudit) &&
    added[0].principal === 'manager' && added[0].consumer === 'owner-preview' &&
    added[0].subject_id === 'target' && added[0].operation === 'update' &&
    equal(foreign(proof.before), foreign(proof.current));
}
function warmups (proofs) {
  const warm = proofs.filter(p => p.kind === 'warmup');
  if (warm.length !== 2 || new Set(warm.map(p => p.pid)).size !== 2 ||
      warm.some((p, i) => p.index !== i || p.status !== 200 || !effect(p, 'Cache Warmup ' + i)) ||
      !equal(warm[0].current, warm[1].before)) throw new Error('CONTROL-INVALID: both real workers require valid physical warmup');
  return warm;
}
function verify (report, status, control, proofs) {
  if (!Array.isArray(proofs)) throw new Error('CONTROL-INVALID: owner physical observations missing');
  if (!control) {
    if (status !== 0 || report.stats.tests !== 9 || report.stats.passes !== 9 || report.stats.failures !== 0 || report.stats.pending !== 0)
      throw new Error('Unexpected bounded owner cohort result');
    const warm = warmups(proofs), revoked = proofs.filter(p => p.kind === 'protected' && p.phase === 'revocation');
    const listener = proofs.filter(p => p.kind === 'listener');
    const schedules = [['credentials', 'enabled', false], ['credentials', 'generation', 2],
      ['sessions', 'active', false], ['sessions', 'generation', 2], ['sessions', 'expires_at', 1],
      ['keys', 'active', false], ['tenants', 'active', false]];
    if (revoked.length !== 14 || !equal(revoked[0].baselineAfterWarmup, warm[1].current) ||
        revoked.some((p, i) => !p.revocation || p.pid !== warm[i % 2].pid ||
          p.revocation.table !== schedules[Math.floor(i / 2)][0] || p.revocation.column !== schedules[Math.floor(i / 2)][1] ||
          p.revocation.disabled !== schedules[Math.floor(i / 2)][2] || !p.revocation || !Array.isArray(p.revocation.observed) || !p.revocation.observed.length ||
          p.revocation.observed.some(value => value !== p.revocation.disabled && value !== String(p.revocation.disabled)) || p.status !== 401 || p.expectedStatus !== 401 || p.auditDelta !== 0 || !equal(p.before, p.current) ||
          !equal(p.before, warm[1].current)) || listener.length !== 1 || ![401, 403, 404, 405].includes(listener[0].status) ||
        !complete(listener[0].before) || !complete(listener[0].current) || listener[0].auditDelta !== 0 || !equal(listener[0].before, listener[0].current))
      throw new Error('Missing restored owner physical no-effects observations');
    return;
  }
  const failure = report.failures?.[0], err = failure?.err;
  if (!Object.hasOwn(definition.controls, control) || status !== 1 || report.stats.tests !== 1 || report.stats.failures !== 1 ||
      report.stats.passes !== 0 || report.stats.pending !== 0 || err?.code !== 'ERR_ASSERTION' ||
      !failure.fullTitle?.endsWith(definition.controls[control][3])) throw new Error('CONTROL-INVALID: owner setup/timeout/unrelated case is not evidence');
  const exact = (value, wanted) => value === wanted || value === String(wanted);
  if (!exact(err.actual, true) || !exact(err.expected, false) ||
      !err.message?.includes(control === 'snapshot' ? physicalMessage : listenerMessage))
    throw new Error('CONTROL-INVALID: unexpected owner physical assertion symptom');
  if (control === 'snapshot') {
    const warm = warmups(proofs), denied = proofs.filter(p => p.kind === 'protected');
    if (denied.length !== 1 || denied[0].phase !== 'revocation' || denied[0].status !== 200 || denied[0].expectedStatus !== 401 ||
        denied[0].revocation?.table !== 'credentials' || denied[0].revocation?.column !== 'enabled' ||
        denied[0].revocation?.disabled !== false || !equal(denied[0].revocation?.observed, [false]) || denied[0].pid !== warm[0].pid || !equal(denied[0].baselineAfterWarmup, warm[1].current) ||
        !equal(denied[0].before, warm[1].current) || !effect(denied[0], 'Updated'))
      throw new Error('CONTROL-INVALID: stale snapshot did not show actual post-warmup unauthorized target and audit mutation');
  } else {
    const listener = proofs.filter(p => p.kind === 'listener');
    if (listener.length !== 1 || listener[0].status !== 200 || !effect(listener[0], 'Wrong Plane'))
      throw new Error('CONTROL-INVALID: listener mutation did not show DATA request and physical owner target/audit change');
  }
  console.log('CONTROL-SEMANTIC: ' + (control === 'snapshot'
    ? 'validly warmed actual worker reused stale authority after committed revocation; target and audit changed'
    : 'real DATA listener accepted management request; owner target and audit changed'));
}
function auditChildren (proofs, control, present = pid => {
  try { process.kill(pid, 0); return true; } catch (error) { if (error.code === 'ESRCH') return false; throw error; }
}) {
  const starts = proofs.filter(p => p.kind === 'worker-start'), stops = proofs.filter(p => p.kind === 'worker-stop');
  const count = control === 'snapshot' ? 2 : control === 'listener' ? 3 : 6;
  if (starts.length !== count || stops.length !== count || new Set(starts.map(p => p.pid)).size !== count)
    throw new Error('Owned owner CLI lifecycle audit missing/ambiguous');
  return starts.map(start => {
    const matches = stops.filter(stop => stop.pid === start.pid && stop.roles === start.roles);
    const stop = matches[0];
    const valid = matches.length === 1 && Number.isSafeInteger(start.pid) && start.pid > 0 &&
      (stop.code === 0 && stop.signal === null || !control && stop.roles === 'tenant-admin' && stop.code === 78 && stop.signal === null ||
        control === 'listener' && stop.roles === 'tenant-admin,api' && stop.code === null && stop.signal === 'SIGKILL');
    if (!valid || present(start.pid)) throw new Error('Owned owner CLI lifecycle/absence audit failed');
    return { ...start, exit: stop, independentlyAbsent: true };
  });
}
function validateAudit (captured, control) {
  const count = control === 'snapshot' ? 0 : 2;
  if (!Array.isArray(captured) || captured.length !== count || new Set(captured.map(record => record.container)).size !== count ||
      count === 2 && (!captured.some(record => record.container.startsWith('ns-preview-replicas-pg-')) ||
        !captured.some(record => record.container.startsWith('ns-preview-replicas-vault-'))) || captured.some(record =>
    !/^ns-preview-replicas-(pg|vault)-[0-9a-f]{16}$/.test(record.container) || record.containerRemoved !== true ||
    !Array.isArray(record.volumeIds) || new Set(record.volumeIds).size !== record.volumeIds.length ||
    record.volumeIds.some(id => typeof id !== 'string' || !id) || record.volumeIds.length !== (record.container.includes('-vault-') ? 2 : 1)))
    throw new Error('Owned owner native PG/Vault lifecycle audit missing/incomplete');
}
module.exports = { definition, adaptations, adapt, verify, auditChildren, validateAudit, physicalMessage, listenerMessage };
