'use strict';
// External acceptance instrument: no source replacement, no fake SQL driver.
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const { createRequire } = require('node:module');
const { execFileSync } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const { AsyncLocalStorage } = require('node:async_hooks');
const { ANCHORS, PHASES, quote: q, waitFor, exactBackend, TERMINATE, observeClients, boundAdmin } = require('./support.cjs');
function argument (name) { const i = process.argv.indexOf(name); return i < 0 ? undefined : process.argv[i + 1]; }
async function run () {
  if (!process.argv.includes('--run')) {
    console.log(JSON.stringify({ status: 'PREPARED_NOT_RUN', anchors: ANCHORS, phases: PHASES,
      activation: '--run AND NS_SETTINGS_NATIVE_APPROVED=1 AND explicit disposable NS_TEST_POSTGRES_ADMIN_URI',
      scope: 'actual source evaluator boot/owned reader plus native PG; not image/full serve/cohort clinical acceptance' }, null, 2)); return;
  }
  assert.equal(process.env.NS_SETTINGS_NATIVE_APPROVED, '1', 'Native window must be explicitly released');
  const core = path.resolve(argument('--core') || '');
  assert(argument('--core'), 'Explicit frozen core path required');
  assert.equal(execFileSync('git', ['-C', core, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), ANCHORS.core);
  assert.equal(execFileSync('git', ['-C', core, 'status', '--porcelain', '--untracked-files=no'], { encoding: 'utf8' }).trim(), '', 'Frozen core tracked files must be clean');
  const uri = process.env.NS_TEST_POSTGRES_ADMIN_URI; assert(uri, 'Explicit disposable native PostgreSQL URI required');
  assert.match(new URL(uri).pathname, /test/i, 'Native fixture requires a disposable test-named database');
  const output = argument('--output'); assert(output && path.isAbsolute(output), 'Absolute output path required');
  assert(fs.statSync(path.dirname(output)).isDirectory(), 'Output parent must exist');
  assert(!fs.existsSync(output), 'Output must be a fresh measurement path');
  const local = createRequire(path.join(core, 'package.json')), pg = local('pg');
  const req = file => local('./' + file);
  const lab = req('tests/fixtures/evaluator-preview-lab')();
  const scope = req('lib/storage/tenant-scope'), parser = req('lib/server/serve/evaluator-config');
  const previousMode = scope.getTenancyMode();
  const migrations = req('lib/migrations/postgres'), jobs = new AsyncLocalStorage();
  const prefix = 'esn_' + randomBytes(6).toString('hex');
  const settingsNs = prefix + '_settings', policyNs = prefix + '_policy';
  const settingsRole = prefix + '_reader', clinicalRole = prefix + '_clinical';
  const settingsTable = q(settingsNs) + '.tenant_settings', policyTable = q(policyNs) + '.tenant_operator_policy';
  const ledger = q(settingsNs) + '.schema_migrations';
  const roles = [], schemas = [], locks = new Set(), transactions = new WeakSet(), results = [], failures = [];
  let role, shared, loaded, observer, phase = 'preparation';
  const oldReadiness = process.env.NS_TENANT_READINESS;
  const record = (name, details = {}) => { results.push({ phase: name, status: 'reproduced', ...details }); };
  const attempt = async fn => { try { await fn(); } catch (error) { failures.push({ phase: 'cleanup', code: error.code || null, name: error.name }); } };
  async function backends () {
    return (await lab.admin.query(`SELECT pid,backend_start::text AS birth,usename AS role,
      application_name AS app,wait_event_type AS wait,query
      FROM pg_stat_activity WHERE datname=current_database() AND usename=$1`, [settingsRole])).rows;
  }
  async function lock (table) {
    const client = new pg.Client({ connectionString: uri, statement_timeout: 3000 });
    locks.add(client); await client.connect();
    await client.query("SET idle_in_transaction_session_timeout='10s'");
    await client.query('BEGIN'); transactions.add(client); await client.query('LOCK TABLE ' + table + ' IN ACCESS EXCLUSIVE MODE'); return client;
  }
  async function unlock (client) {
    try { if (transactions.has(client)) await client.query('ROLLBACK'); } finally { await client.end(); locks.delete(client); }
  }
  const watch = promise => { promise.catch(() => {}); return promise; };
  const read = (tenant, id) => scope.withTenant(tenant, () => jobs.run({ id, tenant }, () => loaded.readCurrent(tenant, shared)));
  async function restoredMutation (name, change, restore, expected) {
    phase = name;
    try { await change(); await assert.rejects(read(lab.A, name), expected); }
    finally { await restore(); }
    assert.equal((await read(lab.A, name + '-restored')).env.settings.units, 'mmol'); record(name);
  }
  try {
    phase = 'fixture-open'; process.env.NS_TENANT_READINESS = 'all';
    const opening = watch(lab.open());
    assert(lab.admin, 'Reused fixture must synchronously expose its admin before awaiting connect');
    boundAdmin(lab.admin); await opening;
    for (const namespace of [settingsNs, policyNs]) {
      await lab.admin.query('CREATE SCHEMA ' + q(namespace)); schemas.push(namespace);
      await migrations.run('up', { direct: true, connectionString: uri, namespace,
        statementTimeoutMs: 5000, waitMs: 1500, catalogue: req(namespace === settingsNs ? 'lib/tenant-settings/postgres-candidate.json' : 'lib/operator-policy/postgres-candidate.json') });
    }
    const passwords = {};
    for (const name of [settingsRole, clinicalRole]) {
      passwords[name] = randomBytes(24).toString('hex');
      await lab.admin.query(`CREATE ROLE ${q(name)} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${passwords[name]}'`); roles.push(name);
    }
    await lab.admin.query('GRANT ' + q(lab.previewRole) + ' TO ' + q(clinicalRole));
    for (const namespace of schemas) {
      await lab.admin.query('GRANT USAGE ON SCHEMA ' + q(namespace) + ' TO ' + q(settingsRole));
      await lab.admin.query('GRANT SELECT ON ALL TABLES IN SCHEMA ' + q(namespace) + ' TO ' + q(settingsRole));
    }
    for (const tenant of [lab.A, lab.B]) {
      await lab.admin.query(`INSERT INTO ${settingsTable}(tenant_id,version,values) VALUES($1,1,$2)`, [tenant, { SHOW_SECONDS: tenant === lab.A }]);
      await lab.admin.query(`INSERT INTO ${policyTable}(tenant_id,generation,policy,principal,consumer,event_time)
        VALUES($1,1,$2,'synthetic','native',0)`, [tenant, { deployment: {}, overrides: {} }]);
    }
    const uriFor = name => { const url = new URL(uri); url.username = name; url.password = passwords[name]; return url.toString(); };
    await lab.provisionPreview();
    const configured = lab.configure(doc => {
      doc.tenants.forEach(tenant => { tenant.settings = {}; });
      doc.tenantSettings = { connectionEnv: 'NS_SETTINGS_NATIVE_READER', namespaces: { settings: settingsNs, operatorPolicy: policyNs } };
    });
    loaded = parser.load({ MULTITENANT_EVALUATOR_CONFIG: configured.file,
      NS_EVALUATOR_FIXTURE_CONNECTION: uriFor(clinicalRole), NS_SETTINGS_NATIVE_READER: uriFor(settingsRole) });
    observer = observeClients(pg, settingsRole, scope, jobs);
    phase = 'actual-role-boot';
    role = await req('lib/server/serve/evaluator-preview').boot({ ...loaded, readCurrent (tenant, owned) {
      if (shared) assert.equal(owned, shared, 'One boot-owned reader reused'); shared = owned;
      return loaded.readCurrent(tenant, owned);
    } });
    assert(shared && typeof shared.close === 'function');
    await role.acquire(lab.A); record(phase, { capturedBootOwnedReader: true });
    phase = 'fresh-owner-policy-A-B';
    const first = await read(lab.A, 'fresh-a'); assert.equal(first.env.settings.units, 'mg/dl'); assert.equal(first.env.settings.showSeconds, true);
    assert.equal((await read(lab.B, 'fresh-b')).env.settings.showSeconds, false);
    await lab.admin.query(`UPDATE ${settingsTable} SET version=2,values=$2 WHERE tenant_id=$1`, [lab.A, { SHOW_SECONDS: false }]);
    const changed = await read(lab.A, 'owner-updated'); assert.notEqual(changed.identity, first.identity); assert.equal(changed.env.settings.showSeconds, false);
    await lab.admin.query(`UPDATE ${policyTable} SET generation=2,policy=$2 WHERE tenant_id=$1`, [lab.A, { deployment: {}, overrides: { DISPLAY_UNITS: { mode: 'pinned', pin: 'mmol' } } }]);
    assert.equal((await read(lab.A, 'policy-updated')).env.settings.units, 'mmol');
    assert.equal((await read(lab.B, 'foreign-unchanged')).env.settings.units, 'mg/dl');
    await assert.rejects(scope.withTenant(lab.B, () => jobs.run({ id: 'ambient-B-request-A', tenant: lab.B }, () => loaded.readCurrent(lab.A, shared))), { code: 'SETTINGS_POLICY_UNAVAILABLE' });
    assert.equal((await read(lab.A, 'scope-restored-A')).env.settings.units, 'mmol');
    assert.equal((await read(lab.B, 'scope-restored-B')).env.settings.units, 'mg/dl'); record(phase, { ambientTenantMismatchRefused: true });
    await restoredMutation('RLS-refusal-restoration', () => lab.admin.query(`ALTER TABLE ${settingsTable} DISABLE ROW LEVEL SECURITY`),
      () => lab.admin.query(`ALTER TABLE ${settingsTable} ENABLE ROW LEVEL SECURITY`), { code: 'SETTINGS_STORE_UNSAFE' });
    await restoredMutation('SELECT-refusal-restoration', () => lab.admin.query(`REVOKE SELECT ON ${settingsTable} FROM ${q(settingsRole)}`),
      () => lab.admin.query(`GRANT SELECT ON ${settingsTable} TO ${q(settingsRole)}`), { code: 'SETTINGS_STORE_UNSAFE' });
    await restoredMutation('write-grant-refusal-restoration', () => lab.admin.query(`GRANT UPDATE ON ${settingsTable} TO ${q(settingsRole)}`),
      () => lab.admin.query(`REVOKE UPDATE ON ${settingsTable} FROM ${q(settingsRole)}`));
    const original = (await lab.admin.query(`SELECT name,checksum FROM ${ledger} ORDER BY name LIMIT 1`)).rows[0];
    await restoredMutation('catalogue-refusal-restoration', () => lab.admin.query(`UPDATE ${ledger} SET checksum=$2 WHERE name=$1`, [original.name, '0'.repeat(64)]),
      () => lab.admin.query(`UPDATE ${ledger} SET checksum=$2 WHERE name=$1`, [original.name, original.checksum]), { code: 'MIG_DRIFT' });

    phase = 'direct-check-bound-FIFO-context';
    const start = observer.starts.length, held = await lock(ledger), pending = [];
    try {
      for (let n = 0; n < 6; n++) pending.push(watch(read(n % 2 ? lab.B : lab.A, 'queue-' + n)));
      const rows = await waitFor('four-direct-checks-wait', async () => {
        const rows = (await backends()).filter(row => row.wait === 'Lock' && row.app === 'nightscout-operator-migrations'); return rows.length === 4 && rows;
      });
      assert.equal(rows.length, 4);
      await assert.rejects(read(lab.A, 'overflow'), { code: 'SETTINGS_POLICY_UNAVAILABLE' });
      assert.equal(observer.starts.slice(start).filter(id => id === 'queue-4' || id === 'queue-5').length, 0);
      await lab.admin.query(`UPDATE ${settingsTable} SET version=3,values=$2 WHERE tenant_id=$1`, [lab.B, { SHOW_SECONDS: true }]);
      await unlock(held);
      const values = await Promise.all(pending); assert.equal(values[5].env.settings.showSeconds, true);
      const order = observer.starts.slice(start);
      assert(order.indexOf('queue-4') >= 0 && order.indexOf('queue-5') > order.indexOf('queue-4'), 'FIFO pending calls enter in order');
      assert.deepEqual(observer.violations, []); assert(observer.snapshot().peakDirect <= 4); assert(observer.snapshot().peakTotal <= 8);
      record(phase, { observed: observer.snapshot(), blockedDirectClients: rows.length });
    } finally { if (locks.has(held)) await unlock(held); await Promise.allSettled(pending); }

    phase = 'exact-owned-backend-termination-recovery';
    const blocked = await lock(settingsTable); let outcome, victim;
    try {
      const pendingRead = read(lab.A, 'terminated').then(value => ({ value }), error => ({ error }));
      victim = await waitFor('one-owned-tenant-join-wait', async () => (await backends()).find(row => row.wait === 'Lock' && row.query.includes('SELECT s.version,s.values,p.generation,p.policy')));
      const args = exactBackend(victim, settingsRole);
      const killed = (await lab.admin.query(TERMINATE, args)).rows;
      assert.equal(killed.length, 1); assert.equal(killed[0].terminated, true);
      outcome = await pendingRead; assert.equal(outcome.error?.code, 'SETTINGS_POLICY_UNAVAILABLE');
    } finally { await unlock(blocked); }
    assert.equal((await read(lab.A, 'termination-recovered')).env.settings.units, 'mmol');
    record(phase, { pid: victim.pid, backendBirth: victim.birth, terminated: true, readRefused: true, freshRecovery: true });

    phase = 'queued-and-active-shutdown';
    const closingLock = await lock(ledger), calls = []; let refused = 0, stopped = false;
    try {
      for (let n = 0; n < 6; n++) calls.push(watch(assert.rejects(read(n % 2 ? lab.B : lab.A, 'close-' + n), { code: 'SETTINGS_POLICY_UNAVAILABLE' }).then(() => { refused++; })));
      await waitFor('shutdown-four-direct-checks-wait', async () => (await backends()).filter(row => row.wait === 'Lock' && row.app === 'nightscout-operator-migrations').length === 4);
      const closing = watch(role.close().then(() => { stopped = true; }));
      await waitFor('two-queued-cancelled', async () => refused === 2);
      assert.equal(stopped, false, 'Shutdown must drain admitted direct checks');
      await unlock(closingLock); await Promise.all(calls); await closing;
      await assert.rejects(read(lab.A, 'closed-no-reopen'), { code: 'SETTINGS_POLICY_UNAVAILABLE' });
      await waitFor('settings-backends-drained', async () => (await backends()).length === 0);
      assert.equal(observer.live.size, 0); record(phase, { queuedCancelled: 2, admittedDrained: 4 });
    } finally { if (locks.has(closingLock)) await unlock(closingLock); await Promise.allSettled(calls); }
  } catch (error) { failures.push({ phase, code: error.code || null, name: error.name }); }
  finally {
    for (const client of [...locks]) await attempt(() => unlock(client));
    if (role) await attempt(() => role.close());
    if (lab.admin) {
      if (roles.includes(settingsRole)) await attempt(async () => {
        const remaining = await backends(); assert.equal(remaining.length, 0, 'Owned settings backends must drain without forced cleanup');
      });
      for (const schema of [...schemas].reverse()) await attempt(() => lab.admin.query('DROP SCHEMA ' + q(schema) + ' CASCADE'));
      for (const name of [...roles].reverse()) await attempt(async () => { await lab.admin.query('DROP OWNED BY ' + q(name)); await lab.admin.query('DROP ROLE ' + q(name)); });
    }
    await attempt(() => lab.close());
    observer?.restore(); scope.setTenancyMode(previousMode);
    if (oldReadiness === undefined) delete process.env.NS_TENANT_READINESS; else process.env.NS_TENANT_READINESS = oldReadiness;
    if (!failures.length) record('owned-cleanup');
    fs.writeFileSync(output, JSON.stringify({ anchors: ANCHORS, sourceScope: 'actual evaluator role boot with transparent reader capture; native PG, no HTTP/image/full cohort',
      owned: { prefix, fixture: lab.name, settingsRole, clinicalRole, settingsNs, policyNs }, results, failures, status: failures.length ? 'FAILED' : 'REPRODUCED',
      unmeasured: ['running image', 'HTTP', 'full clinical/TIME acceptance', 'capacity/performance', 'real cleanup-end failure (unit mock only)'] }, null, 2) + '\n', { mode: 0o600 });
    if (failures.length) process.exitCode = 1;
  }
}
if (require.main === module) run().catch(error => { console.error(JSON.stringify({ status: 'REFUSED_BEFORE_NATIVE_RUN', name: error.name, code: error.code || null })); process.exitCode = 1; });
module.exports = { run };
