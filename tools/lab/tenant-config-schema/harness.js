'use strict';
// T30-SCHEMA-CONFIG lab harness. See README.md.
//
//   node harness.js --secrets DIR [--port 5447] [--only GROUP,GROUP] [--out results.json]
//
// Every test runs twice on a fresh database cloned from a migrated template:
//   pass run    -- must not throw;
//   control run -- the same test after a break that removes the protection;
//                  must throw. A control that stays green means the test is
//                  vacuous or the break broke nothing, and the harness says so.
// All tenant-scoped checks run as non-superuser, non-owner application roles.

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { Lab, assertContainerRunning } = require('./lib/db');
const mig = require('./lib/migrator');
const merge = require('./lib/merge');

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf('--' + k); return i >= 0 ? args[i + 1] : d; };
const PORT = Number(opt('port', '5447'));
const SECRETS = opt('secrets', null);
const ONLY = opt('only', null) ? opt('only').split(',') : null;
const OUT = opt('out', path.join(__dirname, 'results.json'));
if (!SECRETS) { console.error('--secrets DIR is required (holds pg-superuser-password; never inside the repo)'); process.exit(2); }
if (path.resolve(SECRETS).startsWith(path.resolve(__dirname, '..', '..', '..'))) {
  console.error('--secrets must be outside the repository'); process.exit(2);
}

const A = 'aaaaaaaa-0000-4000-8000-000000000001';
const B = 'bbbbbbbb-0000-4000-8000-000000000002';
const IA1 = 'a1a1a1a1-0000-4000-8000-0000000000a1';
const IB1 = 'b1b1b1b1-0000-4000-8000-0000000000b1';
const REF = (n) => `sref:v1:builtin:${'r'.repeat(20)}${String(n).padStart(4, '0')}`;
const TEMPLATE = 'cfglab_template';
const J = (x) => JSON.stringify(x);

class Fail extends Error {}
function assert (cond, msg) { if (!cond) throw new Fail(msg); }
async function refused (promise, re, code) {
  try { await promise; } catch (e) {
    if (re && !re.test(e.message)) throw new Fail(`refused for the wrong reason: ${e.message}`);
    if (code && e.code !== code) throw new Fail(`refused with code ${e.code}, expected ${code}: ${e.message}`);
    return e.message;
  }
  throw new Fail(`expected a refusal matching ${re}${code ? ` (${code})` : ''}, but it was accepted`);
}

// ------------------------------------------------------------------ helpers

function apply (t, role, tenant, changes, extra = {}) {
  return t.lab.as(role, t.db, tenant, (c) => c.query(
    'SELECT cfg_apply($1, $2::jsonb, $3, $4, $5, $6, $7, $8::jsonb, $9) AS v',
    [tenant, J(changes), extra.plane || 'owner', extra.subject || `subject-${tenant === A ? 'a' : 'b'}`,
      extra.reason || null, 'change', null, J(extra.confirm || {}),
      extra.provider || ((extra.plane || 'owner') === 'owner' ? 'lab-idp' : null)]).then((r) => r.rows[0].v));
}
function rollback (t, tenant, target, confirm = {}) {
  return t.lab.as('ns_tenant_admin', t.db, tenant, (c) => c.query(
    'SELECT cfg_rollback($1, $2, $3, $4, $5, $6::jsonb, $7) AS v',
    [tenant, target, 'owner', 'subject-a', 'lab rollback', J(confirm), 'lab-idp']).then((r) => r.rows[0].v));
}
function op (t, tenant, sql, params) { return t.lab.as('ns_operator', t.db, tenant, (c) => c.query(sql, params)); }
function owner (t, sql, params) { return t.lab.as('cfg_owner', t.db, null, (c) => c.query(sql, params)); }
function confirmFor (...keys) {
  const o = {}; for (const k of keys) o[k] = { exportOfferedAt: new Date().toISOString() }; return o;
}

async function loadCfg (t, tenant) {
  return t.lab.as('ns_api', t.db, tenant, async (c) => {
    const byKey = (rows, k = 'setting_key') => Object.fromEntries(rows.map((r) => [r[k], r]));
    const catalogue = byKey((await c.query('SELECT * FROM config_setting')).rows, 'key');
    const deployment = byKey((await c.query('SELECT * FROM deployment_policy')).rows);
    const overrides = byKey((await c.query('SELECT * FROM tenant_policy_override')).rows);
    const ownerVals = Object.fromEntries((await c.query('SELECT setting_key, value FROM tenant_setting_value')).rows.map((r) => [r.setting_key, r.value]));
    const th = (await c.query('SELECT * FROM tenant_alarm_thresholds')).rows[0] || null;
    return { catalogue, deployment, overrides, owner: ownerVals, thresholds: th };
  });
}

// ------------------------------------------------------------------ seed

async function seed (t) {
  await op(t, null, "INSERT INTO tenants (id, slug) VALUES ($1, 'alpha'), ($2, 'bravo')", [A, B]);
  const dp = [
    ['SHOW_SECONDS', 'open', null, {}, null],
    ['AUTH_DEFAULT_ROLES', 'bounded', ['denied'], { allowed: ['denied', 'readable'] }, null],
    ['WRITE_VALIDATION', 'bounded', 'log', { min: 'log' }, null],
    ['API3_AUTOPRUNE_ENTRIES', 'bounded', null, { min: 30, max: 3650 }, null],
    ['INTEGRATION_MAX:push-relay', 'pinned', null, {}, 2],
    ['INTEGRATION_MAX:webhook', 'pinned', null, {}, 1],
    ['INTEGRATION_MAX:cgm-connector', 'pinned', null, {}, 1],
    ['INTEGRATION_MAX:app-push', 'pinned', null, {}, 0]
  ];
  await t.lab.as('ns_operator', t.db, null, async (c) => {
    for (const [k, mode, d, cons, pin] of dp) {
      await c.query(`INSERT INTO deployment_policy (setting_key, mode, default_value, constraint_spec, pin_value, updated_by)
                     VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, 'operator-1')`,
      [k, mode, d === null ? null : J(d), J(cons), pin === null ? null : J(pin)]);
    }
    await c.query("INSERT INTO deployment_integration (kind, operator_secret_ref, updated_by) VALUES ('push-relay', $1, 'operator-1')", [REF(900)]);
  });
  await op(t, A, `INSERT INTO tenant_policy_override (tenant_id, setting_key, mode, default_value, updated_by)
                  VALUES ($1, 'DISPLAY_UNITS', 'open', '"mmol"', 'operator-1')`, [A]);
  await op(t, B, `INSERT INTO tenant_policy_override (tenant_id, setting_key, mode, default_value, constraint_spec, updated_by)
                  VALUES ($1, 'AUTH_DEFAULT_ROLES', 'bounded', '["denied"]', '{"allowed": ["denied"]}', 'operator-1')`, [B]);
  await apply(t, 'ns_tenant_admin', A, {
    values: { SHOW_SECONDS: true, AUTH_DEFAULT_ROLES: ['readable'] },
    integrations: { upsert: [{ id: IA1, kind: 'webhook', settings: { url: 'https://hooks.example-receiver.test/ns', events: 'alarm' }, secretRef: REF(1) }] }
  });
  await apply(t, 'ns_tenant_admin', B, {
    values: { SHOW_SECONDS: false },
    integrations: { upsert: [{ id: IB1, kind: 'push-relay', settings: { priority: 'high' }, secretRef: REF(2) }] }
  });
  for (const tn of [A, B]) {
    await t.lab.as('ns_tenant_admin', t.db, tn, (c) => c.query("INSERT INTO tenant_members (id, tenant_id, provider, subject_id) VALUES (gen_random_uuid(), $1, 'lab-idp', 'user_' || md5(random()::text))", [tn]));
  }
  await t.lab.as('ns_api', t.db, A, (c) => c.query('INSERT INTO tenant_integration_status (tenant_id, integration_id, last_success_at) VALUES ($1, $2, now())', [A, IA1]));
  await t.lab.as('ns_api', t.db, B, (c) => c.query("INSERT INTO tenant_integration_status (tenant_id, integration_id, last_error_at, last_error) VALUES ($1, $2, now(), 'timeout')", [B, IB1]));
  if (t.fixture === 'postgate') {
    await apply(t, 'ns_tenant_admin', A, { thresholds: { bgLow: 55, bgTargetBottom: 80, bgTargetTop: 180, bgHigh: 260, enteredUnits: 'mg/dl' } });
    await apply(t, 'ns_tenant_admin', B, { thresholds: { bgLow: 70, bgTargetBottom: 90, bgTargetTop: 160, bgHigh: 240, enteredUnits: 'mmol' } });
  }
}

// The post-gate fixture: what the migration that turns owner alarm settings on
// would grant. Applied only to tests that exercise threshold storage.
const POSTGATE = 'GRANT INSERT, UPDATE, DELETE ON tenant_alarm_thresholds TO ns_tenant_admin';

// A migration's function, re-created with one edit (for controls).
function patchFunction (file, fname, find, replace) {
  const src = fs.readFileSync(path.join(__dirname, 'migrations', file), 'utf8');
  const start = src.indexOf(`CREATE FUNCTION ${fname}(`);
  const end = src.indexOf('END $$;', start) + 'END $$;'.length;
  const body = src.slice(start, end).replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION');
  const out = body.replace(find, replace);
  if (start < 0 || out === body) throw new Error(`could not patch ${fname}`);
  return out;
}

// The cfg_apply body with its advisory lock removed (control for V-8).
function cfgApplyWithoutLock () {
  const src = fs.readFileSync(path.join(__dirname, 'migrations', '0007_owner_values_and_versions.up.sql'), 'utf8');
  const start = src.indexOf('CREATE FUNCTION cfg_apply(');
  const end = src.indexOf('END $$;', start) + 'END $$;'.length;
  const body = src.slice(start, end).replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION');
  const out = body.replace(/\n\s*PERFORM pg_advisory_xact_lock\([^;]*;/, '');
  if (out === body) throw new Error('could not find the advisory lock to remove');
  return out;
}

// A rollback that restores values only (control for V-4 / V-7).
const ROLLBACK_VALUES_ONLY = `
CREATE OR REPLACE FUNCTION cfg_rollback(p_tenant uuid, p_target integer, p_actor_plane text, p_actor_subject text,
                             p_reason text DEFAULT NULL, p_confirmations jsonb DEFAULT '{}'::jsonb,
                             p_actor_provider text DEFAULT NULL)
RETURNS integer LANGUAGE plpgsql AS $f$
DECLARE target jsonb; cur jsonb; vals jsonb;
BEGIN
  SELECT state INTO target FROM tenant_config_version WHERE tenant_id = p_tenant AND version = p_target;
  cur := cfg_current_state(p_tenant);
  SELECT COALESCE(jsonb_object_agg(k, COALESCE(target -> 'values' -> k, 'null'::jsonb)), '{}'::jsonb) INTO vals
    FROM (SELECT jsonb_object_keys(target -> 'values') AS k UNION SELECT jsonb_object_keys(cur -> 'values')) keys
   WHERE (target -> 'values' -> k) IS DISTINCT FROM (cur -> 'values' -> k);
  RETURN cfg_apply(p_tenant, jsonb_build_object('values', vals), p_actor_plane, p_actor_subject, p_reason, 'rollback', p_target, p_confirmations, p_actor_provider);
END $f$;`;

// ------------------------------------------------------------------ tests

const tests = [];
const T = (x) => tests.push(x);

// ---- isolation, one per tenant-scoped table ------------------------------
const ISO = [
  { table: 'tenant_members', writer: 'ns_tenant_admin', insert: "INSERT INTO tenant_members (id, tenant_id, provider, subject_id) VALUES (gen_random_uuid(), $1, 'lab-idp', 'user_x')" },
  { table: 'tenant_policy_override', writer: 'ns_operator', insert: "INSERT INTO tenant_policy_override (tenant_id, setting_key, mode, updated_by) VALUES ($1, 'SHOW_SECONDS', 'open', 'op')" },
  { table: 'tenant_setting_value', writer: 'ns_tenant_admin', insert: `INSERT INTO tenant_setting_value (tenant_id, setting_key, value) VALUES ($1, 'DISPLAY_UNITS', '"mmol"')` },
  { table: 'tenant_alarm_thresholds', fixture: 'postgate', writer: 'ns_tenant_admin', insert: "INSERT INTO tenant_alarm_thresholds (tenant_id, bg_low_mgdl, bg_target_bottom_mgdl, bg_target_top_mgdl, bg_high_mgdl, entered_units) VALUES ($1, 60, 80, 180, 250, 'mg/dl')" },
  { table: 'tenant_config_version', writer: 'ns_tenant_admin', noUpdate: true, insert: "INSERT INTO tenant_config_version (tenant_id, version, actor_plane, actor_subject, kind, state) VALUES ($1, 99, 'owner', 'x', 'change', '{}')" },
  { table: 'tenant_integration', writer: 'ns_tenant_admin', insert: `INSERT INTO tenant_integration (tenant_id, id, kind, settings, owner_secret_ref) VALUES ($1, gen_random_uuid(), 'push-relay', '{"priority": "normal"}', '${REF(77)}')` },
  { table: 'tenant_integration_status', writer: 'ns_api', insert: `INSERT INTO tenant_integration_status (tenant_id, integration_id) VALUES ($1, '${IB1}')` }
];
for (const iso of ISO) {
  T({
    id: `ISO-${iso.table}`, group: 'isolation', fixture: iso.fixture,
    title: `${iso.table}: a role bound to tenant A reads, updates and inserts only A's rows; unbound it reads none`,
    async run (t) {
      const reader = t.reader || 'ns_api';
      const seen = await t.lab.as(reader, t.db, A, (c) => c.query(`SELECT tenant_id::text AS t FROM ${iso.table}`));
      assert(seen.rows.length > 0, `bound to A, ${reader} saw no rows at all (seed missing: the test would be vacuous)`);
      assert(seen.rows.every((r) => r.t === A), `bound to A, ${reader} saw tenant B's rows in ${iso.table}`);
      const unbound = await t.lab.as(reader, t.db, null, (c) => c.query(`SELECT count(*)::int AS n FROM ${iso.table}`));
      assert(unbound.rows[0].n === 0, `unbound, ${reader} saw ${unbound.rows[0].n} rows`);
      if (!iso.noUpdate) {
        const upd = await t.lab.as(iso.writer, t.db, A, (c) => c.query(`UPDATE ${iso.table} SET tenant_id = tenant_id WHERE tenant_id = $1`, [B]));
        assert(upd.rowCount === 0, `bound to A, ${iso.writer} updated ${upd.rowCount} of B's rows`);
      }
      await refused(t.lab.as(iso.writer, t.db, A, (c) => c.query(iso.insert, [B])), /row-level security/, '42501');
    },
    controls: [
      { title: 'RLS disabled on the table', ownerSql: `ALTER TABLE ${iso.table} DISABLE ROW LEVEL SECURITY` },
      { title: 'same reads as the container superuser (RLS bypassed)', reader: 'superuser' }
    ]
  });
}

T({
  id: 'ISO-roles', group: 'isolation',
  title: 'the roles the tests use are NOSUPERUSER NOBYPASSRLS, own no table, and RLS is active for each on every tenant table (row_security_active)',
  async run (t) {
    const roles = t.roles || ['ns_api', 'ns_tenant_admin', 'ns_operator', 'cfg_owner'];
    const tables = ISO.map((x) => x.table);
    for (const r of roles) {
      const who = await t.lab.as(r, t.db, null, (c) => c.query('SELECT current_user AS u, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user'));
      assert(!who.rows[0].rolsuper && !who.rows[0].rolbypassrls, `${who.rows[0].u} is superuser or bypassrls`);
      for (const tb of tables) {
        const act = await t.lab.as(r, t.db, null, (c) => c.query('SELECT row_security_active($1) AS on', [tb]));
        assert(act.rows[0].on === true, `RLS is not active for ${who.rows[0].u} on ${tb}`);
      }
    }
    const owned = await owner(t, "SELECT c.relname, pg_get_userbyid(c.relowner) AS o FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r' AND pg_get_userbyid(c.relowner) <> 'cfg_owner'");
    assert(owned.rows.length === 0, `tables owned by other roles: ${J(owned.rows)}`);
  },
  controls: [
    { title: 'include the container superuser among the roles', roles: ['ns_api', 'superuser'] },
    { title: 'NO FORCE on one table: the owning migration role escapes RLS', ownerSql: 'ALTER TABLE tenant_setting_value NO FORCE ROW LEVEL SECURITY' }
  ]
});

T({
  id: 'ISO-complete', group: 'isolation',
  title: 'every table with a tenant_id column has RLS enabled and forced and a policy on app.current_tenant_id (discovered, not listed); only `tenants` is exempt',
  async run (t) {
    const r = await owner(t, `
      SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
             EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid
                      AND pg_get_expr(p.polqual, p.polrelid) LIKE '%app.current_tenant_id%'
                      AND pg_get_expr(p.polwithcheck, p.polrelid) LIKE '%app.current_tenant_id%') AS has_policy
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped
       WHERE n.nspname = 'public' AND c.relkind = 'r'`);
    assert(r.rows.length >= 7, `only ${r.rows.length} tenant tables discovered`);
    const bad = r.rows.filter((x) => !(x.relrowsecurity && x.relforcerowsecurity && x.has_policy));
    assert(bad.length === 0, `unprotected tenant tables: ${bad.map((x) => x.relname).join(', ')}`);
  },
  controls: [{ title: 'a new tenant table without RLS', ownerSql: 'CREATE TABLE tenant_notes (tenant_id uuid NOT NULL, note text)' }]
});

// ---- tenant_members: provider + subject (decided 2026-10-27) ---------------
T({
  id: 'MEMBER-identity', group: 'isolation', raw: true,
  title: 'tenant_members names a person by (provider, subject) as text: any provider\'s subject fits, the pair is unique within a tenant, the same person may join two tenants, and no foreign key names an identity table',
  async run (t) {
    await t.lab.createDb(t.db);
    const c = await t.lab.connect('cfg_owner', t.db);
    try { await mig.migrateUp({ client: c, to: t.upTo || undefined }); } finally { await c.end(); }
    if (t.ownerSqlAfter) await owner(t, t.ownerSqlAfter);
    if (t.upTo) {
      await t.lab.super(t.db, (q) => q.query('GRANT SELECT, INSERT ON tenants TO ns_operator; GRANT SELECT, INSERT ON tenant_members TO ns_tenant_admin'));
    }
    await op(t, null, "INSERT INTO tenants (id, slug) VALUES ($1, 'alpha'), ($2, 'bravo')", [A, B]);
    const add = (tn, provider, subject) => t.lab.as('ns_tenant_admin', t.db, tn, (q) => q.query(
      'INSERT INTO tenant_members (id, tenant_id, provider, subject_id) VALUES (gen_random_uuid(), $1, $2, $3)', [tn, provider, subject]));
    await add(A, 'kratos', '6f1c2d3e-0000-4000-8000-00000000abcd');
    await add(A, 'clerk', 'user_2abcXYZ');
    await add(A, 'oidc-example', 'opaque|subject:42');
    await add(A, 'clerk', '6f1c2d3e-0000-4000-8000-00000000abcd');
    await refused(add(A, 'clerk', 'user_2abcXYZ'), /tenant_members_identity/);
    await add(B, 'clerk', 'user_2abcXYZ');
    await refused(add(A, 'Clerk Inc', 'x'), /tenant_members_provider_format/);
    const fks = await t.lab.super(t.db, (q) => q.query("SELECT conname, confrelid::regclass::text AS ref FROM pg_constraint WHERE conrelid = 'tenant_members'::regclass AND contype = 'f'"));
    assert(fks.rows.length === 1 && fks.rows[0].ref === 'tenants', `foreign keys: ${J(fks.rows)}`);
  },
  controls: [
    { title: "the pair's unique constraint dropped", ownerSqlAfter: 'ALTER TABLE tenant_members DROP CONSTRAINT tenant_members_identity' },
    { title: "the seam's shape (0001 only: subject_id uuid, no provider)", upTo: '0001_platform_base' }
  ]
});

T({
  id: 'MEMBER-migration-refuses-rows', group: 'migrate', raw: true,
  title: "0002 refuses to run while tenant_members holds rows whose provider nobody recorded, and its row count is not blinded by FORCE RLS",
  async run (t) {
    await t.lab.createDb(t.db);
    const dir = copyMigrations(t, t.edit);
    const c = await t.lab.connect('cfg_owner', t.db);
    try {
      await mig.migrateUp({ client: c, dir, to: '0001_platform_base' });
      await t.lab.as('cfg_owner', t.db, A, (q) => q.query("INSERT INTO tenants (id, slug) VALUES ($1, 'alpha'); INSERT INTO tenant_members (id, tenant_id, subject_id) VALUES (gen_random_uuid(), $1, gen_random_uuid())".replace(/\$1/g, `'${A}'`)));
      await refused(mig.migrateUp({ client: c, dir }), /tenant_members has 1 rows/);
    } finally { await c.end(); }
  },
  controls: [{ title: "0002 without the NO FORCE around its count", edit: (dir) => {
    const f = path.join(dir, '0002_member_identity.up.sql');
    fs.writeFileSync(f, fs.readFileSync(f, 'utf8').replace('ALTER TABLE tenant_members NO FORCE ROW LEVEL SECURITY;', '').replace('ALTER TABLE tenant_members FORCE ROW LEVEL SECURITY;\n\nALTER', 'ALTER'));
  } }]
});

// ---- merge precedence ---------------------------------------------------
T({
  id: 'MERGE-layers', group: 'merge',
  title: 'code default, operator default, per-tenant override default, owner value and operator pin each win where D22 says',
  async run (t) {
    const eff = merge.effective(await loadCfg(t, A), t.brk);
    const v = (k) => eff.values[k];
    assert(v('BG_HIGH').value === 260 && v('BG_HIGH').source === 'code', `BG_HIGH ${J(v('BG_HIGH'))}`);
    assert(v('WRITE_VALIDATION').value === 'log' && v('WRITE_VALIDATION').source === 'operator-default', `WRITE_VALIDATION ${J(v('WRITE_VALIDATION'))}`);
    assert(v('DISPLAY_UNITS').value === 'mmol' && v('DISPLAY_UNITS').source === 'operator-default', `DISPLAY_UNITS (A's override) ${J(v('DISPLAY_UNITS'))}`);
    assert(v('SHOW_SECONDS').value === true && v('SHOW_SECONDS').source === 'owner', `SHOW_SECONDS ${J(v('SHOW_SECONDS'))}`);
    assert(J(v('AUTH_DEFAULT_ROLES').value) === '["readable"]' && v('AUTH_DEFAULT_ROLES').source === 'owner', `AUTH_DEFAULT_ROLES ${J(v('AUTH_DEFAULT_ROLES'))}`);
    assert(v('INTEGRATION_MAX:webhook').value === 1 && v('INTEGRATION_MAX:webhook').source === 'operator-pin', `INTEGRATION_MAX:webhook ${J(v('INTEGRATION_MAX:webhook'))}`);
    assert(eff.floorViolations.length === 0, `floor violations ${J(eff.floorViolations)}`);
    const effB = merge.effective(await loadCfg(t, B), t.brk);
    assert(effB.values.DISPLAY_UNITS.value === 'mg/dl', `B got A's override: ${J(effB.values.DISPLAY_UNITS)}`);
  },
  controls: [{ title: 'merge ignores per-tenant overrides', brk: { ignoreOverrides: true } }]
});

T({
  id: 'MERGE-override-narrows', group: 'merge',
  title: "an override that narrows tenant B's policy after B's owner set a value: B falls back to the override default and the stale value is reported; A is unaffected",
  async run (t) {
    await op(t, B, "DELETE FROM tenant_policy_override WHERE tenant_id = $1 AND setting_key = 'AUTH_DEFAULT_ROLES'", [B]);
    await apply(t, 'ns_tenant_admin', B, { values: { AUTH_DEFAULT_ROLES: ['readable'] } });
    await op(t, B, `INSERT INTO tenant_policy_override (tenant_id, setting_key, mode, default_value, constraint_spec, updated_by)
                    VALUES ($1, 'AUTH_DEFAULT_ROLES', 'bounded', '["denied"]', '{"allowed": ["denied"]}', 'operator-1')`, [B]);
    const effB = merge.effective(await loadCfg(t, B), t.brk);
    assert(J(effB.values.AUTH_DEFAULT_ROLES.value) === '["denied"]', `B AUTH_DEFAULT_ROLES ${J(effB.values.AUTH_DEFAULT_ROLES)}`);
    assert(effB.ignoredOwnerValues.some((x) => x.key === 'AUTH_DEFAULT_ROLES' && x.why === 'outside constraint'), `stale value not reported: ${J(effB.ignoredOwnerValues)}`);
    const effA = merge.effective(await loadCfg(t, A), t.brk);
    assert(J(effA.values.AUTH_DEFAULT_ROLES.value) === '["readable"]', `A AUTH_DEFAULT_ROLES ${J(effA.values.AUTH_DEFAULT_ROLES)}`);
  },
  controls: [{ title: 'merge ignores per-tenant overrides', brk: { ignoreOverrides: true } }]
});

T({
  id: 'MERGE-pin-beats-owner', group: 'merge',
  title: "a per-tenant pin on A overrides A's stored owner value; B keeps its own",
  async run (t) {
    await op(t, A, `INSERT INTO tenant_policy_override (tenant_id, setting_key, mode, pin_value, updated_by)
                    VALUES ($1, 'SHOW_SECONDS', 'pinned', 'false', 'operator-1')`, [A]);
    const effA = merge.effective(await loadCfg(t, A), t.brk);
    assert(effA.values.SHOW_SECONDS.value === false && effA.values.SHOW_SECONDS.source === 'operator-pin', `A ${J(effA.values.SHOW_SECONDS)}`);
    assert(effA.ignoredOwnerValues.some((x) => x.key === 'SHOW_SECONDS'), 'shadowed owner value not reported');
    const effB = merge.effective(await loadCfg(t, B), t.brk);
    assert(effB.values.SHOW_SECONDS.source === 'owner', `B ${J(effB.values.SHOW_SECONDS)}`);
  },
  controls: [{ title: 'merge applies the pin before the owner value', brk: { pinBeforeOwner: true } }]
});

T({
  id: 'MERGE-floor-on-effective', group: 'merge',
  title: "with no operator row for WRITE_VALIDATION the code default 'off' breaks the floor: the merge reports it so the process refuses",
  async run (t) {
    await op(t, null, "DELETE FROM deployment_policy WHERE setting_key = 'WRITE_VALIDATION'");
    const eff = merge.effective(await loadCfg(t, A), t.brk);
    assert(eff.values.WRITE_VALIDATION.value === 'off', 'precondition');
    assert(eff.floorViolations.some((x) => x.key === 'WRITE_VALIDATION'), `no violation: ${J(eff.floorViolations)}`);
  },
  controls: [{ title: 'floors skipped in the merge', brk: { skipFloors: true } }]
});

T({
  id: 'MERGE-thresholds-refused-not-rewritten', group: 'merge',
  title: 'operator threshold defaults that are out of order are reported as a violation and left as written (no silent nudge, contrast BF-67)',
  async run (t) {
    await op(t, null, `INSERT INTO deployment_policy (setting_key, mode, pin_value, updated_by) VALUES ('BG_LOW', 'pinned', '190', 'operator-1')`);
    const eff = merge.effective(await loadCfg(t, A), t.brk);
    assert(eff.thresholds.bgLow === 190, `bgLow rewritten to ${eff.thresholds.bgLow}`);
    assert(eff.floorViolations.some((x) => x.key === 'thresholds'), 'misordered thresholds not reported');
  },
  controls: [{ title: 'threshold order check skipped', brk: { skipThresholdOrder: true } }]
});

T({
  id: 'MERGE-differential', group: 'merge',
  title: "the merge's acceptance rule (JS) and the database's (cfg_value_ok + cfg_satisfies) agree on every case",
  async run (t) {
    const cfg = await loadCfg(t, A);
    const cases = [
      ['AUTH_DEFAULT_ROLES', 'floor', ['readable']], ['AUTH_DEFAULT_ROLES', 'floor', ['careportal']],
      ['AUTH_DEFAULT_ROLES', 'floor', ['denied', 'readable']], ['AUTH_DEFAULT_ROLES', 'floor', []],
      ['AUTH_DEFAULT_ROLES', 'floor', ['readable', 'readable']], ['AUTH_DEFAULT_ROLES', 'floor', 'readable'],
      ['AUTH_DEFAULT_ROLES', 'floor', [1]], ['AUTH_DEFAULT_ROLES', 'floor', ['admin']],
      ['WRITE_VALIDATION', 'floor', 'off'], ['WRITE_VALIDATION', 'floor', 'log'], ['WRITE_VALIDATION', 'floor', 'reject'],
      ['WRITE_VALIDATION', 'floor', 'LOG'], ['WRITE_VALIDATION', 'floor', 1],
      ['WRITE_VALIDATION', { max: 'log' }, 'reject'], ['WRITE_VALIDATION', { max: 'log' }, 'log'],
      ['API3_AUTOPRUNE_ENTRIES', { min: 30, max: 3650 }, 7], ['API3_AUTOPRUNE_ENTRIES', { min: 30, max: 3650 }, 30],
      ['API3_AUTOPRUNE_ENTRIES', { min: 30, max: 3650 }, 3650], ['API3_AUTOPRUNE_ENTRIES', { min: 30, max: 3650 }, 3651],
      ['API3_AUTOPRUNE_ENTRIES', { min: 30, max: 3650 }, 30.5], ['API3_AUTOPRUNE_ENTRIES', { min: 30, max: 3650 }, '30'],
      ['SHOW_SECONDS', {}, true], ['SHOW_SECONDS', {}, 'true'], ['SHOW_SECONDS', {}, 1],
      ['DISPLAY_UNITS', { allowed: ['mg/dl'] }, 'mmol'], ['DISPLAY_UNITS', { allowed: ['mg/dl'] }, 'mg/dl'],
      ['INTEGRATION_HOSTS:webhook', { allowed: ['a.example.test'] }, ['a.example.test']],
      ['INTEGRATION_HOSTS:webhook', { allowed: ['a.example.test'] }, ['b.example.test']],
      ['INTEGRATION_HOSTS:webhook', {}, ['not a host']], ['INTEGRATION_HOSTS:webhook', {}, []]
    ];
    const disagree = [];
    await t.lab.as('ns_api', t.db, null, async (c) => {
      for (const [key, cons, v] of cases) {
        const s = cfg.catalogue[key];
        const cc = cons === 'floor' ? s.floor : cons;
        const js = merge.accepts(s, cc, v, t.brk);
        const r = await c.query(`SELECT CASE WHEN cfg_value_ok(value_type, enum_values, $2::jsonb)
                                      THEN cfg_satisfies(value_type, enum_values, $3::jsonb, $2::jsonb) ELSE false END AS ok
                                   FROM config_setting WHERE key = $1`, [key, J(v), J(cc)]);
        if (r.rows[0].ok !== js) disagree.push({ key, cons: cc, v, sql: r.rows[0].ok, js });
      }
    });
    t.observe(`${cases.length} cases compared`);
    assert(disagree.length === 0, `JS and SQL disagree: ${J(disagree)}`);
  },
  controls: [{ title: 'an off-by-one in the JS ordinal minimum', brk: { ordinalOffByOne: true } }]
});

// ---- floors in the database ---------------------------------------------
T({
  id: 'FLOOR-anon-roles-owner', group: 'floors-db',
  title: 'no anonymous writes: with the operator policy OPEN, an owner still cannot pick careportal or admin as a default role',
  async run (t) {
    await op(t, null, "UPDATE deployment_policy SET mode = 'open', constraint_spec = '{}', default_value = NULL WHERE setting_key = 'AUTH_DEFAULT_ROLES'");
    for (const roles of [['careportal'], ['readable', 'devicestatus-upload'], ['admin']]) {
      await refused(apply(t, 'ns_tenant_admin', A, { values: { AUTH_DEFAULT_ROLES: roles } }), /^floor:/);
    }
    await apply(t, 'ns_tenant_admin', A, { values: { AUTH_DEFAULT_ROLES: ['status-only'] } });
  },
  controls: [{ title: 'project floor removed from the catalogue row', ownerSql: "UPDATE config_setting SET floor = '{}', default_constraint = '{}' WHERE key = 'AUTH_DEFAULT_ROLES'" }]
});

T({
  id: 'FLOOR-anon-roles-policy', group: 'floors-db',
  title: 'no anonymous writes: the operator cannot offer, default to or pin a write role, at deployment or per tenant',
  async run (t) {
    await refused(op(t, A, `INSERT INTO tenant_policy_override (tenant_id, setting_key, mode, constraint_spec, updated_by)
                           VALUES ($1, 'AUTH_DEFAULT_ROLES', 'bounded', '{"allowed": ["denied", "careportal"]}', 'op')`, [A]), /^floor:/);
    await refused(op(t, null, `UPDATE deployment_policy SET mode = 'open', constraint_spec = '{}', default_value = '["careportal"]' WHERE setting_key = 'AUTH_DEFAULT_ROLES'`), /^floor:/);
    await refused(op(t, null, `UPDATE deployment_policy SET mode = 'pinned', constraint_spec = '{}', default_value = NULL, pin_value = '["admin"]' WHERE setting_key = 'AUTH_DEFAULT_ROLES'`), /^floor:/);
  },
  controls: [{ title: 'project floor removed from the catalogue row', ownerSql: "UPDATE config_setting SET floor = '{}', default_constraint = '{}' WHERE key = 'AUTH_DEFAULT_ROLES'" }]
});

T({
  id: 'FLOOR-write-validation', group: 'floors-db',
  title: "data safety: WRITE_VALIDATION below 'log' is refused as an owner value (policy open), an operator default and an operator pin",
  async run (t) {
    await op(t, null, "UPDATE deployment_policy SET mode = 'open', constraint_spec = '{}' WHERE setting_key = 'WRITE_VALIDATION'");
    await refused(apply(t, 'ns_tenant_admin', A, { values: { WRITE_VALIDATION: 'off' } }), /^floor:/);
    await refused(op(t, null, `UPDATE deployment_policy SET default_value = '"off"' WHERE setting_key = 'WRITE_VALIDATION'`), /^floor:/);
    await refused(op(t, B, `INSERT INTO tenant_policy_override (tenant_id, setting_key, mode, pin_value, updated_by) VALUES ($1, 'WRITE_VALIDATION', 'pinned', '"off"', 'op')`, [B]), /^floor:/);
    await apply(t, 'ns_tenant_admin', A, { values: { WRITE_VALIDATION: 'reject' } });
  },
  controls: [{ title: 'project floor removed', ownerSql: "UPDATE config_setting SET floor = '{}', default_constraint = '{}' WHERE key = 'WRITE_VALIDATION'" }]
});

const NOT_OFFERED = ['API_SECRET', 'API_SECRET_FILE', 'TREATMENTS_AUTH', 'IMPORT_CONFIG', 'TRUST_PROXY', 'BASE_URL',
  'DEBUG_LOGGING', 'API3_SECURITY_ENABLE', 'API3_SETTINGS_STRICT_READ_ENABLED', 'DBSIZE_MAX', 'CONNECT_SOURCE_ENDPOINT', 'WEBHOOK_HOST'];
T({
  id: 'FLOOR-not-offered', group: 'floors-db',
  title: `names the floors withdraw under multi cannot appear in any policy or owner row: ${NOT_OFFERED.join(', ')}`,
  async run (t) {
    for (const k of NOT_OFFERED) {
      await refused(op(t, null, `INSERT INTO deployment_policy (setting_key, mode, pin_value, updated_by) VALUES ($1, 'pinned', '"on"', 'op')`, [k]), /not a hosted setting|foreign key/);
      await refused(apply(t, 'ns_tenant_admin', A, { values: { [k]: 'x' } }), /foreign key|not a hosted/);
    }
  },
  controls: [{ title: 'TREATMENTS_AUTH added to the catalogue', ownerSql: "INSERT INTO config_setting (key, value_type, enum_values, owner_settable, default_mode) VALUES ('TREATMENTS_AUTH', 'enum', ARRAY['on','off','x'], true, 'open')" }]
});

T({
  id: 'FLOOR-catalogue-no-secret-names', group: 'floors-db',
  title: 'no deployment secrets, no secrets as settings: even the migration role cannot put a credential-like name in the catalogue',
  async run (t) {
    for (const k of ['API_SECRET', 'PUSHOVER_API_TOKEN', 'LOOP_APNS_KEY', 'CONNECT_SHARE_PASSWORD', 'MAKER_KEY']) {
      await refused(owner(t, "INSERT INTO config_setting (key, value_type, owner_settable) VALUES ($1, 'boolean', false)", [k]), /config_setting_no_secret_names/);
    }
  },
  controls: [{ title: 'name CHECK dropped', ownerSql: 'ALTER TABLE config_setting DROP CONSTRAINT config_setting_no_secret_names' }]
});

T({
  id: 'FLOOR-catalogue-readonly', group: 'floors-db',
  title: 'no application role can edit the catalogue (and so cannot loosen a floor)',
  async run (t) {
    for (const r of ['ns_operator', 'ns_tenant_admin', 'ns_api']) {
      await refused(t.lab.as(r, t.db, null, (c) => c.query("UPDATE config_setting SET floor = '{}' WHERE key = 'WRITE_VALIDATION'")), /permission denied/, '42501');
      await refused(t.lab.as(r, t.db, null, (c) => c.query("UPDATE integration_kind SET driver_hosts = '{evil.test}'")), /permission denied/, '42501');
    }
  },
  controls: [{ title: 'UPDATE granted to the operator', ownerSql: 'GRANT UPDATE ON config_setting, integration_kind TO ns_operator' }]
});

T({
  id: 'FLOOR-autoprune-confirmation', group: 'floors-db',
  title: 'data safety: turning on permanent deletion needs a recorded confirmation and export offer',
  async run (t) {
    await refused(apply(t, 'ns_tenant_admin', A, { values: { API3_AUTOPRUNE_ENTRIES: 90 } }), /^floor:.*confirmation/);
    await refused(t.lab.as('ns_tenant_admin', t.db, A, (c) => c.query(
      "SELECT cfg_apply($1, '{\"values\": {\"API3_AUTOPRUNE_ENTRIES\": 90}}', 'owner', 's', NULL, 'change', NULL, '{\"API3_AUTOPRUNE_ENTRIES\": {}}', 'lab-idp')", [A])), /^floor:/);
    await apply(t, 'ns_tenant_admin', A, { values: { API3_AUTOPRUNE_ENTRIES: 90 } }, { confirm: confirmFor('API3_AUTOPRUNE_ENTRIES') });
  },
  controls: [{ title: 'needs_confirmation cleared', ownerSql: "UPDATE config_setting SET needs_confirmation = false WHERE key LIKE 'API3_AUTOPRUNE_%'" }]
});

T({
  id: 'FLOOR-alarms-hidden', group: 'floors-db',
  title: 'alarm settings hidden until the 7a gate: the owner listener cannot write thresholds or alarm keys, and no alarm key can be made owner-settable',
  async run (t) {
    await refused(apply(t, 'ns_tenant_admin', A, { thresholds: { bgLow: 55, bgTargetBottom: 80, bgTargetTop: 180, bgHigh: 260 } }), /permission denied/, '42501');
    await refused(apply(t, 'ns_tenant_admin', A, { values: { BG_HIGH: 250 } }), /not set by the owner/);
    await refused(apply(t, 'ns_tenant_admin', A, { values: { ALARM_URGENT_LOW: false } }), /not set by the owner/);
    await refused(owner(t, "UPDATE config_setting SET owner_settable = true WHERE key = 'ALARM_URGENT_LOW'"), /config_setting_alarms_hidden/);
  },
  controls: [
    { title: 'post-gate GRANT applied', ownerSql: POSTGATE },
    { title: 'alarms-hidden CHECK dropped', ownerSql: 'ALTER TABLE config_setting DROP CONSTRAINT config_setting_alarms_hidden' }
  ]
});

T({
  id: 'FLOOR-webhook-public', group: 'floors-db',
  title: 'network safety: a webhook url must be https, carry no credentials, and not name a private, loopback, link-local or local-only host',
  async run (t) {
    const bad = ['https://10.0.0.5/x', 'https://127.0.0.1/', 'https://localhost/', 'https://192.168.1.10/', 'https://169.254.169.254/latest',
      'https://172.20.0.1/', 'https://100.64.0.1/', 'http://hooks.example-receiver.test/', 'https://user:pw@hooks.example-receiver.test/',
      'https://printer.local/', 'https://intranet/', 'https://svc.internal/'];
    for (const url of bad) {
      await refused(apply(t, 'ns_tenant_admin', A, { integrations: { upsert: [{ id: IA1, kind: 'webhook', settings: { url, events: 'alarm' }, secretRef: REF(1) }] } }), /integration:/);
    }
    await apply(t, 'ns_tenant_admin', A, { integrations: { upsert: [{ id: IA1, kind: 'webhook', settings: { url: 'https://203.0.113.9/hook', events: 'all' }, secretRef: REF(1) }] } });
  },
  controls: [{ title: 'public-host check replaced by `true`', ownerSql: 'CREATE OR REPLACE FUNCTION cfg_public_host_ok(h text) RETURNS boolean LANGUAGE sql IMMUTABLE AS $$ SELECT true $$' }]
});

T({
  id: 'FLOOR-connector-driver-hosts', group: 'floors-db',
  title: 'network safety: a connector endpoint may only name a host its driver defines',
  async run (t) {
    const add = (endpoint) => apply(t, 'ns_tenant_admin', B, { integrations: { upsert: [{ id: 'c0c0c0c0-0000-4000-8000-0000000000c0', kind: 'cgm-connector', settings: { region: 'us', endpoint }, secretRef: REF(3) }] } });
    await refused(add('https://attacker.example.test/'), /^integration: floor:/);
    await refused(add('https://10.1.1.1/'), /^integration: floor:/);
    await add('https://share1.cgm-driver.test/');
  },
  controls: [{ title: "kind's endpoint rule changed from driver to public", ownerSql: `UPDATE integration_kind SET settings_schema = jsonb_set(settings_schema, '{fields,endpoint,hosts}', '"public"') WHERE kind = 'cgm-connector'` }]
});

const CLASS_D = ['API_V3_DATA_WARNINGS', 'API_V1_COUNT_LEADING_NUMBER', 'API_V1_COUNT_ZERO_WINDOW', 'TRUST_PROXY', 'DEBUG_LOGGING', 'PORT', 'STORAGE_URI'];
T({
  id: 'CLASSD-environment', group: 'floors-db',
  title: "class D values live in each role's environment (decided 2026-10-27): the database refuses them as deployment or per-tenant policy, and each role reads its own environment",
  async run (t) {
    for (const k of CLASS_D) {
      await refused(op(t, null, `INSERT INTO deployment_policy (setting_key, mode, pin_value, updated_by) VALUES ($1, 'pinned', 'true', 'op')`, [k]), /not a hosted setting|foreign key/);
      await refused(op(t, A, `INSERT INTO tenant_policy_override (tenant_id, setting_key, mode, pin_value, updated_by) VALUES ($1, $2, 'pinned', 'true', 'op')`, [A, k]), /not a hosted setting|foreign key/);
    }
    const api = merge.deploymentValues({ TRUST_PROXY: '1', API_V3_DATA_WARNINGS: 'true' }, t.brk);
    const evaluator = merge.deploymentValues({ TRUST_PROXY: '2' }, t.brk);
    assert(api.TRUST_PROXY === '1' && api.API_V3_DATA_WARNINGS === true, `api role ${J(api)}`);
    assert(evaluator.TRUST_PROXY === '2' && evaluator.API_V3_DATA_WARNINGS === false && evaluator.API_V1_COUNT_ZERO_WINDOW === true, `evaluator role ${J(evaluator)}`);
  },
  controls: [
    { title: 'API_V3_DATA_WARNINGS added to the catalogue', ownerSql: "INSERT INTO config_setting (key, value_type, owner_settable, default_mode) VALUES ('API_V3_DATA_WARNINGS', 'boolean', false, 'pinned')" },
    { title: 'roles ignore their environment (code defaults only)', brk: { classDFromCodeDefaults: true } }
  ]
});

// ---- floors in the application ------------------------------------------
T({
  id: 'FLOOR-app-process', group: 'floors-app',
  title: 'process start under multi refuses API_SECRET(_FILE), API3_SECURITY_ENABLE=false, an empty or non-numeric TRUST_PROXY and DEBUG_LOGGING; IMPORT_CONFIG is ignored with a warning',
  async run (t) {
    const good = { TRUST_PROXY: '1' };
    assert(merge.processFloors(good, t.brk).refuse.length === 0, 'good env refused');
    const cases = [
      [{ ...good, API_SECRET: 'x'.repeat(12) }, /API_SECRET/], [{ ...good, API_SECRET_FILE: '/run/s' }, /API_SECRET_FILE/],
      [{ ...good, API3_SECURITY_ENABLE: 'false' }, /API3_SECURITY_ENABLE/],
      [{}, /TRUST_PROXY/], [{ TRUST_PROXY: '' }, /TRUST_PROXY/], [{ TRUST_PROXY: 'true' }, /TRUST_PROXY/],
      [{ ...good, DEBUG_LOGGING: 'true' }, /DEBUG_LOGGING/]
    ];
    for (const [env, re] of cases) {
      const r = merge.processFloors(env, t.brk);
      assert(r.refuse.some((m) => re.test(m)), `not refused: ${J(Object.keys(env))}`);
    }
    assert(merge.processFloors({ TRUST_PROXY: '10.0.0.0/8,fd00::/8' }, t.brk).refuse.length === 0, 'CIDR list refused');
    assert(merge.processFloors({ ...good, IMPORT_CONFIG: 'https://x.test/c.json' }, t.brk).warn.length === 1, 'IMPORT_CONFIG not warned');
  },
  controls: [
    { title: 'secret check off', brk: { noSecretCheck: true } },
    { title: 'API3 security check off', brk: { noApi3SecurityCheck: true } },
    { title: 'TRUST_PROXY check off', brk: { noTrustProxyCheck: true } },
    { title: 'DEBUG_LOGGING check off', brk: { noDebugLoggingCheck: true } }
  ]
});

T({
  id: 'FLOOR-app-settings-private', group: 'floors-app',
  title: 'app settings stay private: under multi, reading a settings record by identifier needs api:settings:admin even when API3_SETTINGS_STRICT_READ_ENABLED=false',
  async run (t) {
    assert(merge.settingsReadByIdPermission({ API3_SETTINGS_STRICT_READ_ENABLED: 'false' }, 'multi', t.brk) === 'api:settings:admin', 'multi honoured the env');
    assert(merge.settingsReadByIdPermission({}, 'single', t.brk) === 'api:settings:read', 'single changed (D15: single unchanged)');
  },
  controls: [{ title: 'multi honours the env value', brk: { honourStrictReadEnv: true } }]
});

// ---- owner values refused outside policy -----------------------------------
const DROP_OWNER_CHECK = 'DROP TRIGGER tenant_setting_value_check ON tenant_setting_value';
T({
  id: 'POLICY-pinned', group: 'policy', title: 'an owner value for a setting the operator has pinned is refused',
  async run (t) {
    await op(t, null, "UPDATE deployment_policy SET mode = 'pinned', pin_value = 'false' WHERE setting_key = 'SHOW_SECONDS'");
    await refused(apply(t, 'ns_tenant_admin', B, { values: { SHOW_SECONDS: true } }), /pinned/);
    await refused(apply(t, 'ns_tenant_admin', B, { values: { API3_AUTOPRUNE_FOOD: 90 } }, { confirm: confirmFor('API3_AUTOPRUNE_FOOD') }), /pinned by the operator \(catalogue rule/);
  },
  controls: [{ title: 'owner-value trigger dropped', ownerSql: DROP_OWNER_CHECK }]
});
T({
  id: 'POLICY-bounded', group: 'policy', title: "values outside a bounded list or range are refused; inside are accepted",
  async run (t) {
    await refused(apply(t, 'ns_tenant_admin', A, { values: { AUTH_DEFAULT_ROLES: ['status-only'] } }), /outside the operator/);
    await apply(t, 'ns_tenant_admin', A, { values: { AUTH_DEFAULT_ROLES: ['denied'] } });
    for (const d of [7, 4000]) {
      await refused(apply(t, 'ns_tenant_admin', A, { values: { API3_AUTOPRUNE_ENTRIES: d } }, { confirm: confirmFor('API3_AUTOPRUNE_ENTRIES') }), /outside the operator/);
    }
    await apply(t, 'ns_tenant_admin', A, { values: { API3_AUTOPRUNE_ENTRIES: 90 } }, { confirm: confirmFor('API3_AUTOPRUNE_ENTRIES') });
  },
  controls: [{ title: 'owner-value trigger dropped', ownerSql: DROP_OWNER_CHECK }]
});
T({
  id: 'POLICY-per-tenant-override', group: 'policy', title: "B's override narrows AUTH_DEFAULT_ROLES to denied: readable is refused for B and accepted for A",
  async run (t) {
    await refused(apply(t, 'ns_tenant_admin', B, { values: { AUTH_DEFAULT_ROLES: ['readable'] } }), /\(override rule: bounded/);
    await apply(t, 'ns_tenant_admin', A, { values: { AUTH_DEFAULT_ROLES: ['readable'] } });
  },
  controls: [{ title: 'owner-value trigger dropped', ownerSql: DROP_OWNER_CHECK }]
});
T({
  id: 'POLICY-type-and-ownership', group: 'policy', title: 'wrongly typed values and operator-only keys are refused',
  async run (t) {
    await refused(apply(t, 'ns_tenant_admin', A, { values: { SHOW_SECONDS: 'yes' } }), /must be a boolean/);
    await refused(apply(t, 'ns_tenant_admin', A, { values: { DISPLAY_UNITS: 'mmol/L' } }), /must be a enum/);
    await refused(apply(t, 'ns_tenant_admin', A, { values: { 'INTEGRATION_MAX:webhook': 5 } }), /not set by the owner/);
  },
  controls: [{ title: 'owner-value trigger dropped', ownerSql: DROP_OWNER_CHECK }]
});
T({
  id: 'POLICY-planes', group: 'policy', title: 'the owner listener cannot write policy; the operator plane cannot write owner values',
  async run (t) {
    await refused(t.lab.as('ns_tenant_admin', t.db, null, (c) => c.query("INSERT INTO deployment_policy (setting_key, mode, updated_by) VALUES ('DISPLAY_UNITS', 'open', 'x')")), /permission denied/, '42501');
    await refused(t.lab.as('ns_tenant_admin', t.db, A, (c) => c.query("INSERT INTO tenant_policy_override (tenant_id, setting_key, mode, updated_by) VALUES ($1, 'DISPLAY_UNITS', 'open', 'x')", [A])), /permission denied/, '42501');
    await refused(apply(t, 'ns_operator', A, { values: { DISPLAY_UNITS: 'mmol' } }, { plane: 'operator' }), /permission denied/, '42501');
  },
  controls: [{ title: 'owner listener granted policy writes', ownerSql: 'GRANT INSERT ON deployment_policy, tenant_policy_override TO ns_tenant_admin' }]
});
T({
  id: 'POLICY-webhook-allowlist', group: 'policy', title: "the operator's optional webhook host allow-list (census row 4) refuses other public hosts",
  async run (t) {
    await op(t, null, `INSERT INTO deployment_policy (setting_key, mode, pin_value, updated_by) VALUES ('INTEGRATION_HOSTS:webhook', 'pinned', '["hooks.example-receiver.test"]', 'op')`);
    await refused(apply(t, 'ns_tenant_admin', A, { integrations: { upsert: [{ id: IA1, kind: 'webhook', settings: { url: 'https://other.example.test/', events: 'all' }, secretRef: REF(1) }] } }), /allow-list/);
    await apply(t, 'ns_tenant_admin', A, { integrations: { upsert: [{ id: IA1, kind: 'webhook', settings: { url: 'https://hooks.example-receiver.test/v2', events: 'all' }, secretRef: REF(1) }] } });
  },
  controls: [{ title: 'policy lookup made blind to INTEGRATION_HOSTS keys', ownerSql: patchFunction('0005_policy.up.sql', 'cfg_policy_for', 'BEGIN\n', "BEGIN\n  IF p_key LIKE 'INTEGRATION_HOSTS:%' THEN RETURN; END IF;\n") }]
});

// ---- versions and rollback -------------------------------------------------
T({
  id: 'VERSION-numbered', group: 'versions', title: 'each change is a numbered version with plane, subject, time, kind and the full state after it',
  async run (t) {
    await apply(t, 'ns_tenant_admin', A, { values: { SHOW_SECONDS: false } }, { subject: 'subject-a2', reason: 'second' });
    await apply(t, 'ns_tenant_admin', A, { values: { DISPLAY_UNITS: 'mg/dl' } });
    const v = await t.lab.as('ns_tenant_admin', t.db, A, (c) => c.query('SELECT version, actor_plane, actor_subject, kind, reason, created_at, state FROM tenant_config_version ORDER BY version'));
    assert(J(v.rows.map((r) => r.version)) === '[1,2,3]', `versions ${J(v.rows.map((r) => r.version))}`);
    assert(v.rows[1].actor_subject === 'subject-a2' && v.rows[1].actor_plane === 'owner' && v.rows[1].reason === 'second' && v.rows[1].created_at, 'who/when/why missing');
    assert(v.rows[1].state.values.SHOW_SECONDS === false && v.rows[0].state.values.SHOW_SECONDS === true, 'states do not record what changed');
    assert(v.rows[2].state.values.DISPLAY_UNITS === 'mg/dl', 'v3 state');
  },
  controls: [{ title: 'state snapshot broken: cfg_current_state returns an empty state', ownerSql: "CREATE OR REPLACE FUNCTION cfg_current_state(p_tenant uuid) RETURNS jsonb LANGUAGE sql STABLE AS $$ SELECT cfg_empty_state() $$" }]
});
T({
  id: 'VERSION-unversioned-write-refused', group: 'versions', title: 'a write that skips cfg_apply cannot commit (update, insert or delete; values and integrations)',
  async run (t) {
    await refused(t.lab.as('ns_tenant_admin', t.db, A, (c) => c.query(`UPDATE tenant_setting_value SET value = 'false' WHERE setting_key = 'SHOW_SECONDS'`)), /without a version/);
    await refused(t.lab.as('ns_tenant_admin', t.db, A, (c) => c.query(`INSERT INTO tenant_setting_value (tenant_id, setting_key, value) VALUES ($1, 'DISPLAY_UNITS', '"mg/dl"')`, [A])), /without a version/);
    await refused(t.lab.as('ns_tenant_admin', t.db, A, (c) => c.query('DELETE FROM tenant_integration')), /without a version/);
  },
  controls: [{ title: 'commit-time version guards dropped', ownerSql: 'DROP TRIGGER tenant_setting_value_versioned ON tenant_setting_value; DROP TRIGGER tenant_integration_versioned ON tenant_integration' }]
});
T({
  id: 'VERSION-append-only', group: 'versions', title: 'versions cannot be edited or deleted, even by the owning migration role',
  async run (t) {
    await refused(t.lab.as('ns_tenant_admin', t.db, A, (c) => c.query("UPDATE tenant_config_version SET reason = 'x'")), /permission denied/, '42501');
    await refused(t.lab.as('cfg_owner', t.db, A, (c) => c.query("UPDATE tenant_config_version SET reason = 'x'")), /append-only/);
    await refused(t.lab.as('cfg_owner', t.db, A, (c) => c.query('DELETE FROM tenant_config_version')), /append-only/);
  },
  controls: [{ title: 'append-only trigger dropped', ownerSql: 'DROP TRIGGER tenant_config_version_immutable ON tenant_config_version' }]
});
T({
  id: 'VERSION-rollback-restores', group: 'versions', fixture: 'postgate',
  title: 'rollback to v1 writes a new version (kind rollback, rollback_of 1) whose state, and the live state, equal v1: values, thresholds and integrations',
  async run (t) {
    const s = (await t.lab.as('ns_tenant_admin', t.db, A, (c) => c.query('SELECT version, state FROM tenant_config_version ORDER BY version'))).rows;
    const base = s[s.length - 1];
    await apply(t, 'ns_tenant_admin', A, { values: { SHOW_SECONDS: false, DISPLAY_UNITS: 'mg/dl' }, thresholds: { bgLow: 60, bgTargetBottom: 90, bgTargetTop: 170, bgHigh: 250, enteredUnits: 'mg/dl' } });
    await apply(t, 'ns_tenant_admin', A, { integrations: { delete: [IA1] } });
    const v = await rollback(t, A, base.version);
    const after = await t.lab.as('ns_tenant_admin', t.db, A, (c) => c.query('SELECT kind, rollback_of, state, cfg_current_state($1) AS live FROM tenant_config_version WHERE version = $2', [A, v]));
    const r = after.rows[0];
    assert(r.kind === 'rollback' && r.rollback_of === base.version, `kind ${r.kind} of ${r.rollback_of}`);
    assert(deepEq(r.live, base.state), `live state differs from v${base.version}: ${J(r.live)} vs ${J(base.state)}`);
    assert(deepEq(r.state, base.state), 'rollback version state differs');
  },
  controls: [{ title: 'rollback restores values only', ownerSql: ROLLBACK_VALUES_ONLY }]
});
T({
  id: 'VERSION-rollback-vs-new-policy', group: 'versions',
  title: 'Q3 (decided): rollback to a version whose settings the operator has since pinned or narrowed is refused whole, naming EACH blocked setting and the operator rule behind it; nothing changes and no version is written',
  async run (t) {
    await apply(t, 'ns_tenant_admin', A, { values: { SHOW_SECONDS: null, AUTH_DEFAULT_ROLES: ['denied'] } });
    await op(t, null, "UPDATE deployment_policy SET mode = 'pinned', pin_value = 'false' WHERE setting_key = 'SHOW_SECONDS'");
    await op(t, A, `INSERT INTO tenant_policy_override (tenant_id, setting_key, mode, default_value, constraint_spec, updated_by)
                    VALUES ($1, 'AUTH_DEFAULT_ROLES', 'bounded', '["denied"]', '{"allowed": ["denied"]}', 'operator-1')`, [A]);
    const before = await t.lab.as('ns_tenant_admin', t.db, A, (c) => c.query('SELECT max(version) AS v, cfg_current_state($1) AS s FROM tenant_config_version', [A]));
    const msg = await refused(rollback(t, A, 1), /refused; 2 setting\(s\) blocked/);
    t.observe(msg);
    assert(/SHOW_SECONDS is pinned by the operator \(deployment rule: pinned to false\)/.test(msg), `SHOW_SECONDS or its rule not named: ${msg}`);
    assert(/AUTH_DEFAULT_ROLES = \["readable"\] is outside the operator's constraint \(override rule: bounded \{"allowed": \["denied"\]\}\)/.test(msg), `AUTH_DEFAULT_ROLES or its rule not named: ${msg}`);
    const after = await t.lab.as('ns_tenant_admin', t.db, A, (c) => c.query('SELECT max(version) AS v, cfg_current_state($1) AS s FROM tenant_config_version', [A]));
    assert(after.rows[0].v === before.rows[0].v && deepEq(after.rows[0].s, before.rows[0].s), 'partial rollback or version written');
  },
  controls: [
    { title: 'checks removed: owner-value trigger dropped and the pre-check made permissive', ownerSql: DROP_OWNER_CHECK + "; CREATE OR REPLACE FUNCTION cfg_owner_value_error(p_tenant uuid, p_key text, p_value jsonb, p_confirmed boolean) RETURNS text LANGUAGE sql STABLE AS $$ SELECT NULL::text $$" },
    { title: 'rollback reports only the first blocked setting', ownerSql: patchFunction('0007_owner_values_and_versions.up.sql', 'cfg_rollback', 'SELECT array_agg(e ORDER BY e) INTO blocked', 'SELECT (array_agg(e ORDER BY e))[1:1] INTO blocked') }
  ]
});
T({
  id: 'VERSION-rollback-needs-fresh-confirmation', group: 'versions',
  title: 'rolling back to a version that had permanent deletion on needs a fresh confirmation; the old one is not carried forward',
  async run (t) {
    const v2 = await apply(t, 'ns_tenant_admin', A, { values: { API3_AUTOPRUNE_ENTRIES: 90 } }, { confirm: confirmFor('API3_AUTOPRUNE_ENTRIES') });
    await apply(t, 'ns_tenant_admin', A, { values: { API3_AUTOPRUNE_ENTRIES: null } });
    await refused(rollback(t, A, v2), /blocked: floor: API3_AUTOPRUNE_ENTRIES deletes data permanently.*confirmation/);
    await rollback(t, A, v2, confirmFor('API3_AUTOPRUNE_ENTRIES'));
  },
  controls: [{ title: 'needs_confirmation cleared', ownerSql: "UPDATE config_setting SET needs_confirmation = false WHERE key LIKE 'API3_AUTOPRUNE_%'" }]
});
T({
  id: 'VERSION-concurrent-writers', group: 'versions',
  title: 'two owner sessions saving at once get consecutive versions; neither fails',
  async run (t) {
    const c1 = await t.lab.connect('ns_tenant_admin', t.db);
    const c2 = await t.lab.connect('ns_tenant_admin', t.db);
    try {
      for (const c of [c1, c2]) { await c.query('BEGIN'); await c.query("SELECT set_config('app.current_tenant_id', $1, true)", [A]); }
      const q = "SELECT cfg_apply($1, $2::jsonb, 'owner', 's', p_actor_provider => 'lab-idp') AS v";
      const v1 = (await c1.query(q, [A, J({ values: { SHOW_SECONDS: false } })])).rows[0].v;
      const p2 = c2.query(q, [A, J({ values: { DISPLAY_UNITS: 'mg/dl' } })]).then((r) => c2.query('COMMIT').then(() => r.rows[0].v));
      p2.catch(() => {});
      await new Promise((r) => setTimeout(r, 400));
      await c1.query('COMMIT');
      const v2 = await p2;
      assert(v2 === v1 + 1, `versions ${v1} then ${v2}`);
    } finally { await c1.end().catch(() => {}); await c2.end().catch(() => {}); }
  },
  controls: [{ title: 'advisory lock removed from cfg_apply', ownerSql: cfgApplyWithoutLock() }]
});

// ---- no plaintext secrets --------------------------------------------------
const SECRET_COL = '(password|passwd|secret|token|credential|private|apikey|api_key|signing|material|cipher|plaintext)';
T({
  id: 'SECRETS-schema-scan', group: 'secrets',
  title: 'information_schema: no column named like a credential (except *_ref / *_parts), no bytea column, and every *_ref column is CHECKed by cfg_is_secret_ref',
  async run (t) {
    const named = await owner(t, `SELECT table_name, column_name FROM information_schema.columns
                                    WHERE table_schema = 'public' AND column_name ~* $1 AND column_name !~ '(_ref|_parts)$'`, [SECRET_COL]);
    assert(named.rows.length === 0, `credential-like columns: ${J(named.rows)}`);
    const bytea = await owner(t, "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public' AND data_type = 'bytea'");
    assert(bytea.rows.length === 0, `bytea columns: ${J(bytea.rows)}`);
    const refs = await owner(t, "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name LIKE '%\\_ref' AND table_name <> 'schema_migrations'");
    assert(refs.rows.length >= 2, `found ${refs.rows.length} _ref columns (expected the two integration references)`);
    for (const r of refs.rows) {
      const chk = await owner(t, `SELECT 1 FROM pg_constraint WHERE conrelid = $1::regclass AND contype = 'c'
                                    AND pg_get_constraintdef(oid) LIKE '%cfg_is_secret_ref(' || $2 || ')%'`, [r.table_name, r.column_name]);
      assert(chk.rows.length === 1, `${r.table_name}.${r.column_name} has no reference-format CHECK`);
    }
    t.observe(`reference columns: ${refs.rows.map((r) => r.table_name + '.' + r.column_name).join(', ')}`);
  },
  controls: [
    { title: 'a plaintext password column added', ownerSql: 'ALTER TABLE tenant_integration ADD COLUMN password text' },
    { title: 'a bytea material column added', ownerSql: 'ALTER TABLE tenant_integration ADD COLUMN material_blob bytea' },
    { title: 'an unconstrained *_ref column added', ownerSql: 'ALTER TABLE tenant_integration ADD COLUMN backup_ref text' }
  ]
});
T({
  id: 'SECRETS-not-in-settings', group: 'secrets',
  title: "integration settings cannot carry a credential: unknown fields are refused and no kind's schema may declare a credential-like field",
  async run (t) {
    await refused(apply(t, 'ns_tenant_admin', A, { integrations: { upsert: [{ id: IA1, kind: 'webhook', settings: { url: 'https://hooks.example-receiver.test/ns', events: 'alarm', password: 'hunter2' }, secretRef: REF(1) }] } }), /unknown field password/);
    await refused(apply(t, 'ns_tenant_admin', B, { integrations: { upsert: [{ id: IB1, kind: 'push-relay', settings: { priority: 'high', userKey: 'u123' }, secretRef: REF(2) }] } }), /unknown field userKey/);
    await refused(owner(t, `UPDATE integration_kind SET settings_schema = jsonb_set(settings_schema, '{fields,password}', '{"type": "string"}') WHERE kind = 'webhook'`), /integration_kind_no_secret_fields/);
  },
  controls: [{ title: 'kind CHECK dropped and a password field added to the webhook schema', ownerSql: `ALTER TABLE integration_kind DROP CONSTRAINT integration_kind_no_secret_fields; UPDATE integration_kind SET settings_schema = jsonb_set(settings_schema, '{fields,password}', '{"type": "string"}') WHERE kind = 'webhook'` }]
});
T({
  id: 'SECRETS-reference-format', group: 'secrets',
  title: 'a reference column refuses a value that is not a reference (a pasted plaintext credential)',
  async run (t) {
    await refused(apply(t, 'ns_tenant_admin', A, { integrations: { upsert: [{ id: IA1, kind: 'webhook', settings: { url: 'https://hooks.example-receiver.test/ns', events: 'alarm' }, secretRef: 'hunter2' }] } }), /tenant_integration_ref_format/);
    await refused(op(t, null, "UPDATE deployment_integration SET operator_secret_ref = 'a-plain-app-token' WHERE kind = 'push-relay'"), /deployment_integration_ref_format/);
  },
  controls: [{ title: 'reference CHECKs dropped', ownerSql: 'ALTER TABLE tenant_integration DROP CONSTRAINT tenant_integration_ref_format; ALTER TABLE deployment_integration DROP CONSTRAINT deployment_integration_ref_format' }]
});
T({
  id: 'SECRETS-owner-cannot-see-operator-part', group: 'secrets',
  title: "the owner listener can see that the operator's part exists, not its reference",
  async run (t) {
    const ok = await t.lab.as('ns_tenant_admin', t.db, null, (c) => c.query('SELECT kind, operator_configured FROM deployment_integration'));
    assert(ok.rows.length === 1 && ok.rows[0].operator_configured === true, 'operator_configured not visible');
    await refused(t.lab.as('ns_tenant_admin', t.db, null, (c) => c.query('SELECT operator_secret_ref FROM deployment_integration')), /permission denied/, '42501');
  },
  controls: [{ title: 'whole-table SELECT granted to the owner listener', ownerSql: 'GRANT SELECT ON deployment_integration TO ns_tenant_admin' }]
});

// ---- mmol thresholds (A.3) -------------------------------------------------
async function writeThresholdsNew (t, th) {
  return apply(t, 'ns_tenant_admin', A, { thresholds: th });
}
async function writeThresholdsOld (t, th) {
  return t.lab.as('ns_tenant_admin', t.db, A, (c) => c.query(
    `INSERT INTO tenant_settings (tenant_id, settings) VALUES ($1, $2::jsonb)
     ON CONFLICT (tenant_id) DO UPDATE SET settings = EXCLUDED.settings`, [A, J({ thresholds: th })]));
}
T({
  id: 'MMOL-stored-safely', group: 'mmol', fixture: 'postgate',
  title: "A.3: a partial mmol override, a full mmol set, an integer mmol-looking set and a misordered set are all refused; a valid mg/dL set is stored exactly",
  async run (t) {
    const w = t.shape === 'old' ? writeThresholdsOld : writeThresholdsNew;
    const obs = [];
    const expectRefused = async (label, th) => {
      try { await w(t, th); } catch (e) { obs.push(`${label}: refused (${e.code} ${e.message.split('\n')[0]})`); return; }
      obs.push(`${label}: ACCEPTED`);
      throw new Fail(`${label} was accepted: ${J(th)}`);
    };
    try {
      await expectRefused('partial {bgHigh:14}', { bgHigh: 14 });
      await expectRefused('full mmol {3.1,4.5,10,14}', { bgLow: 3.1, bgTargetBottom: 4.5, bgTargetTop: 10, bgHigh: 14 });
      await expectRefused('integer mmol-looking {3,5,10,14}', { bgLow: 3, bgTargetBottom: 5, bgTargetTop: 10, bgHigh: 14 });
      await expectRefused('misordered {80,55,180,260}', { bgLow: 80, bgTargetBottom: 55, bgTargetTop: 180, bgHigh: 260 });
      await expectRefused('string threshold {"x",...}', { bgLow: 'x', bgTargetBottom: 80, bgTargetTop: 180, bgHigh: 260 });
      await w(t, { bgLow: 56, bgTargetBottom: 81, bgTargetTop: 180, bgHigh: 252 });
      obs.push('valid mg/dL {56,81,180,252}: accepted');
    } finally { obs.forEach((o) => t.observe(o)); }
  },
  controls: [
    { title: 'the OLD shape: tenant_settings as drafted in config-surface §A.2', shape: 'old' },
    { title: 'new shape with the range CHECK dropped and the columns made nullable', ownerSql: 'ALTER TABLE tenant_alarm_thresholds DROP CONSTRAINT tenant_alarm_thresholds_plausible_mgdl; ALTER TABLE tenant_alarm_thresholds ALTER bg_low_mgdl DROP NOT NULL, ALTER bg_target_bottom_mgdl DROP NOT NULL, ALTER bg_target_top_mgdl DROP NOT NULL; DROP FUNCTION cfg_threshold_input_check(jsonb); CREATE FUNCTION cfg_threshold_input_check(th jsonb) RETURNS void LANGUAGE plpgsql AS $$ BEGIN END $$' }
  ]
});
T({
  id: 'MMOL-old-shape-profile', group: 'mmol', fixture: 'postgate', defaults: { shape: 'old' },
  title: "the §A.2 draft, measured: its CHECK is live (a complete mmol set is refused) yet a partial mmol override passes on SQL NULL; each input's outcome is recorded",
  async run (t) {
    const w = t.shape === 'old' ? writeThresholdsOld : writeThresholdsNew;
    const out = {};
    const inputs = {
      partial: { bgHigh: 14 },
      fullMmol: { bgLow: 3.1, bgTargetBottom: 4.5, bgTargetTop: 10, bgHigh: 14 },
      integerMmol: { bgLow: 3, bgTargetBottom: 5, bgTargetTop: 10, bgHigh: 14 },
      misordered: { bgLow: 80, bgTargetBottom: 55, bgTargetTop: 180, bgHigh: 260 },
      string: { bgLow: 'x', bgTargetBottom: 80, bgTargetTop: 180, bgHigh: 260 },
      valid: { bgLow: 56, bgTargetBottom: 81, bgTargetTop: 180, bgHigh: 252 }
    };
    for (const [k, th] of Object.entries(inputs)) {
      try { await w(t, th); out[k] = 'accepted'; } catch (e) { out[k] = `refused ${e.code}: ${e.message.split('\n')[0]}`; }
      t.observe(`${k} ${J(th)}: ${out[k]}`);
    }
    assert(out.fullMmol.startsWith('refused'), 'the constraint is not live at all (a complete mmol set passed): the measurement would be vacuous');
    assert(out.partial === 'accepted', 'the partial mmol override was refused: hazard not reproduced on this shape');
  },
  controls: [{ title: 'the same inputs against the new shape', shape: 'new' }]
});

T({
  id: 'MMOL-converted-and-echoed', group: 'mmol', fixture: 'postgate',
  title: 'the write boundary converts mmol/L to mg/dL and the stored numbers come back for the owner to see (A.3 defence 2): 3.1/4.5/10/14 -> 56/81/180/252',
  async run (t) {
    const stored = merge.thresholdsForStorage({ bgLow: 3.1, bgTargetBottom: 4.5, bgTargetTop: 10, bgHigh: 14 }, 'mmol', t.brk);
    await writeThresholdsNew(t, stored);
    const r = await t.lab.as('ns_tenant_admin', t.db, A, (c) => c.query('SELECT bg_low_mgdl, bg_target_bottom_mgdl, bg_target_top_mgdl, bg_high_mgdl, entered_units FROM tenant_alarm_thresholds'));
    const row = r.rows[0];
    assert(J([row.bg_low_mgdl, row.bg_target_bottom_mgdl, row.bg_target_top_mgdl, row.bg_high_mgdl]) === '[56,81,180,252]', `stored ${J(row)}`);
    assert(row.entered_units === 'mmol', 'entered units not kept');
  },
  controls: [{ title: 'conversion skipped at the write boundary', brk: { skipConversion: true } }]
});

// ---- integrations validated per kind ---------------------------------------
const DROP_INTEGRATION_CHECK = 'DROP TRIGGER tenant_integration_check ON tenant_integration';
T({
  id: 'INTEGRATION-kind-limits', group: 'integrations', title: 'kinds the operator disabled are refused, and the per-tenant count is held',
  async run (t) {
    const pr = (id) => ({ id, kind: 'push-relay', settings: { priority: 'normal' }, secretRef: REF(10) });
    await apply(t, 'ns_tenant_admin', B, { integrations: { upsert: [pr('b2b2b2b2-0000-4000-8000-0000000000b2')] } });
    await refused(apply(t, 'ns_tenant_admin', B, { integrations: { upsert: [pr('b3b3b3b3-0000-4000-8000-0000000000b3')] } }), /allows 2 per tenant/);
    await refused(apply(t, 'ns_tenant_admin', A, { integrations: { upsert: [{ id: 'a2a2a2a2-0000-4000-8000-0000000000a2', kind: 'app-push', settings: { bundleId: 'org.example.app', environment: 'production' }, secretRef: REF(11) }] } }), /allows 0 per tenant/);
    await refused(apply(t, 'ns_tenant_admin', A, { integrations: { upsert: [{ id: 'a3a3a3a3-0000-4000-8000-0000000000a3', kind: 'webhook', settings: { url: 'https://hooks.example-receiver.test/2', events: 'all' }, secretRef: REF(12) }] } }), /allows 1 per tenant/);
  },
  controls: [{ title: 'integration trigger dropped', ownerSql: DROP_INTEGRATION_CHECK }]
});
T({
  id: 'INTEGRATION-settings-schema', group: 'integrations', title: "settings are validated against the kind's schema: required, unknown, enum, type, length",
  async run (t) {
    const up = (settings) => apply(t, 'ns_tenant_admin', B, { integrations: { upsert: [{ id: IB1, kind: 'push-relay', settings, secretRef: REF(2) }] } });
    await refused(up({}), /missing field priority/);
    await refused(up({ priority: 'high', colour: 'red' }), /unknown field colour/);
    await refused(up({ priority: 'loud' }), /must be one of/);
    await refused(up({ priority: 1 }), /must be one of/);
    await refused(up({ priority: 'high', sound: 'x'.repeat(41) }), /too long/);
    await up({ priority: 'emergency', sound: 'siren' });
  },
  controls: [{ title: 'integration trigger dropped', ownerSql: DROP_INTEGRATION_CHECK }]
});
T({
  id: 'INTEGRATION-credential-parts', group: 'integrations', title: "an owner part needs a reference; a kind with an operator part needs the operator's part configured first; a record's kind is fixed",
  async run (t) {
    await refused(apply(t, 'ns_tenant_admin', B, { integrations: { upsert: [{ id: IB1, kind: 'push-relay', settings: { priority: 'high' } }] } }), /needs a reference/);
    await refused(apply(t, 'ns_tenant_admin', A, { integrations: { upsert: [{ id: IA1, kind: 'cgm-connector', settings: { region: 'us' }, secretRef: REF(1) }] } }), /cannot change/);
    await op(t, null, "UPDATE deployment_integration SET operator_secret_ref = NULL WHERE kind = 'push-relay'");
    await refused(apply(t, 'ns_tenant_admin', B, { integrations: { upsert: [{ id: 'b4b4b4b4-0000-4000-8000-0000000000b4', kind: 'push-relay', settings: { priority: 'high' }, secretRef: REF(13) }] } }), /operator has not configured/);
  },
  controls: [{ title: 'integration trigger dropped', ownerSql: DROP_INTEGRATION_CHECK }]
});

// ---- migration tooling (umzug) -------------------------------------------
function child (pg, argv) {
  const p = spawn(process.execPath, [path.join(__dirname, 'lib', 'run-migrate.js'), ...argv], { env: { ...process.env, CFGLAB_PG: J(pg) } });
  let out = '';
  p.stdout.on('data', (d) => { out += d; });
  p.stderr.on('data', (d) => { out += d; });
  const done = new Promise((resolve) => p.on('exit', (code, signal) => resolve({ code, signal, out: out.trim(), pid: p.pid })));
  done.proc = p;
  return done;
}
function pgFor (t, db) { return { host: t.lab.host, port: t.lab.port, user: 'cfg_owner', password: t.lab.passwords.cfg_owner, database: db }; }
function copyMigrations (t, edit) {
  const dir = fs.mkdtempSync(path.join(t.scratch, 'mig-'));
  for (const f of fs.readdirSync(mig.MIGRATIONS_DIR)) fs.copyFileSync(path.join(mig.MIGRATIONS_DIR, f), path.join(dir, f));
  if (edit) edit(dir);
  return dir;
}
async function publicObjects (t, db) {
  return t.lab.super(db, async (c) => (await c.query(`
    SELECT count(*)::int AS n FROM (
      SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND relname <> 'schema_migrations' AND relkind IN ('r','v','S','i') AND relname NOT LIKE 'schema_migrations%'
      UNION ALL SELECT proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'public') x`)).rows[0].n);
}

T({
  id: 'MIGRATE-up-down-up', group: 'migrate', raw: true,
  title: 'umzug applies 0001-0008, rolls all of them back to an empty schema, and applies them again',
  async run (t) {
    await t.lab.createDb(t.db);
    const dir = copyMigrations(t, t.edit);
    const c = await t.lab.connect('cfg_owner', t.db);
    try {
      const up1 = await mig.migrateUp({ client: c, dir });
      assert(up1.length === 8, `up applied ${up1.length}`);
      const objs = await publicObjects(t, t.db);
      const down = await mig.migrateDown({ client: c, dir });
      assert(down.length === 8, `down reverted ${down.length}`);
      const left = await publicObjects(t, t.db);
      assert(left === 0, `${left} objects left after down to 0 (of ${objs})`);
      const up2 = await mig.migrateUp({ client: c, dir });
      assert(up2.length === 8, `re-up applied ${up2.length}`);
      t.observe(`${objs} schema objects created; 0 left after down; re-applied`);
    } finally { await c.end(); }
  },
  controls: [{ title: "0006's down migration forgets one function", edit: (dir) => {
    const f = path.join(dir, '0006_integrations.down.sql');
    fs.writeFileSync(f, fs.readFileSync(f, 'utf8').replace('DROP FUNCTION cfg_https_host(text);', ''));
  } }]
});

async function ledgerAndSchema (t) {
  return t.lab.super(t.db, async (c) => ({
    ledger: (await c.query("SELECT name FROM schema_migrations ORDER BY name")).rows.map((x) => x.name),
    policyTable: (await c.query("SELECT to_regclass('public.deployment_policy') IS NOT NULL AS p")).rows[0].p,
    integrationTable: (await c.query("SELECT to_regclass('public.tenant_integration') IS NOT NULL AS p")).rows[0].p
  }));
}
const atomicArg = (t) => (t.atomic === false ? ['--atomic', '0'] : []);

T({
  id: 'MIGRATE-crash-mid', group: 'migrate', raw: true,
  title: 'a migrate process killed while a migration runs: once the server finishes with the orphaned session, the migration is either applied and recorded or neither; a re-run completes',
  async run (t) {
    await t.lab.createDb(t.db);
    const dir = copyMigrations(t, (d) => {
      const f = path.join(d, '0005_policy.up.sql');
      fs.writeFileSync(f, fs.readFileSync(f, 'utf8') + '\nSELECT pg_sleep(5);\n');
    });
    const pg = pgFor(t, t.db);
    const run = child(pg, ['up', '--dir', dir, ...atomicArg(t)]);
    const sleeping = async () => (await t.lab.super(t.db, (c) => c.query("SELECT 1 FROM pg_stat_activity WHERE wait_event = 'PgSleep' AND datname = $1", [t.db]))).rowCount > 0;
    let deadline = Date.now() + 15000;
    while (Date.now() < deadline && !(await sleeping())) await new Promise((r) => setTimeout(r, 100));
    assert(await sleeping(), 'migration 0005 never started');
    const killedAt = Date.now();
    run.proc.kill('SIGKILL');
    const r1 = await run;
    assert(r1.signal === 'SIGKILL', `child ended ${r1.code}/${r1.signal}`);
    deadline = Date.now() + 15000;
    while (Date.now() < deadline && (await sleeping())) await new Promise((r) => setTimeout(r, 100));
    await new Promise((r) => setTimeout(r, 300));
    const orphanMs = Date.now() - killedAt;
    const st = await ledgerAndSchema(t);
    t.observe(`orphaned server session ran on for about ${orphanMs} ms after the kill; then ledger ${J(st.ledger)}, deployment_policy present: ${st.policyTable}`);
    assert(st.ledger.includes('0005_policy') === st.policyTable, `0005 applied but not recorded (or the reverse): ${J(st)}`);
    const r3 = await child(pg, ['up', '--dir', copyMigrations(t), ...atomicArg(t)]);
    assert(r3.code === 0, `re-run failed: ${r3.out}`);
  },
  controls: [{ title: "umzug's default split: migration and ledger row in separate steps", atomic: false }]
});

T({
  id: 'MIGRATE-crash-after', group: 'migrate', raw: true,
  title: 'a migrate process killed just after a migration returns (before the next starts) leaves the ledger matching the schema; a re-run completes',
  async run (t) {
    await t.lab.createDb(t.db);
    const pg = pgFor(t, t.db);
    const dir = copyMigrations(t);
    const r2 = await child(pg, ['up', '--dir', dir, '--crash-after', '0006_integrations', ...atomicArg(t)]);
    assert(r2.signal === 'SIGKILL', `crash-after child ended ${r2.code}/${r2.signal}: ${r2.out}`);
    const st = await ledgerAndSchema(t);
    t.observe(`after the kill: ledger ${J(st.ledger)}, tenant_integration present: ${st.integrationTable}`);
    assert(st.ledger.includes('0006_integrations') === st.integrationTable, `0006 applied but not recorded: ${J(st)}`);
    const r3 = await child(pg, ['up', '--dir', dir, ...atomicArg(t)]);
    assert(r3.code === 0, `re-run failed: ${r3.out}`);
    const n = await t.lab.super(t.db, (c) => c.query('SELECT count(*)::int AS n FROM schema_migrations'));
    assert(n.rows[0].n === 8, `ledger has ${n.rows[0].n}`);
  },
  controls: [{ title: "umzug's default split: migration and ledger row in separate steps", atomic: false }]
});

T({
  id: 'MIGRATE-concurrent', group: 'migrate', raw: true,
  title: 'four migrate processes started at once on an empty database: all succeed and each migration is applied once',
  async run (t) {
    await t.lab.createDb(t.db);
    const dir = copyMigrations(t, (d) => {
      const f = path.join(d, '0001_platform_base.up.sql');
      fs.writeFileSync(f, 'SELECT pg_sleep(0.7);\n' + fs.readFileSync(f, 'utf8'));
    });
    const pg = pgFor(t, t.db);
    const rs = await Promise.all([1, 2, 3, 4].map(() => child(pg, ['up', '--dir', dir, ...(t.lock === false ? ['--lock', '0'] : [])])));
    const failed = rs.filter((r) => r.code !== 0);
    assert(failed.length === 0, `${failed.length} of 4 failed: ${failed.map((r) => r.out).join(' | ').slice(0, 400)}`);
    const n = await t.lab.super(t.db, (c) => c.query('SELECT count(*)::int AS n FROM schema_migrations'));
    assert(n.rows[0].n === 8, `ledger has ${n.rows[0].n}`);
    const applied = rs.map((r) => JSON.parse(r.out.split('\n').pop()).done.length);
    assert(applied.reduce((a, b) => a + b, 0) === 8, `applied counts ${J(applied)}`);
    t.observe(`applied per process: ${J(applied)}`);
  },
  controls: [{ title: 'advisory lock off', lock: false }]
});

T({
  id: 'MIGRATE-drift', group: 'migrate', raw: true,
  title: 'a migration file edited after it was applied stops the next run',
  async run (t) {
    await t.lab.createDb(t.db);
    const dir = copyMigrations(t);
    const c = await t.lab.connect('cfg_owner', t.db);
    try {
      await mig.migrateUp({ client: c, dir });
      const f = path.join(dir, '0004_catalogue_seed.up.sql');
      fs.writeFileSync(f, fs.readFileSync(f, 'utf8') + '\n-- edited after release\n');
      await refused(mig.migrateUp({ client: c, dir, checkDrift: t.checkDrift }), /drift: 0004_catalogue_seed/);
    } finally { await c.end(); }
  },
  controls: [{ title: 'drift check off', checkDrift: false }]
});

T({
  id: 'MIGRATE-serve-refuses-stale-schema', group: 'migrate', raw: true,
  title: 'a hosted role at start refuses a schema with pending migrations instead of migrating it',
  async run (t) {
    await t.lab.createDb(t.db);
    const c = await t.lab.connect('cfg_owner', t.db);
    try {
      await mig.migrateUp({ client: c, to: t.upTo || '0006_integrations' });
      await refused(mig.assertCurrent(c), /pending \[0007_owner_values_and_versions, 0008_grants\]/);
    } finally { await c.end(); }
  },
  controls: [{ title: 'schema fully migrated (the check must not be constant)', upTo: '0008_grants' }]
});

// ------------------------------------------------------------------ runner

function deepEq (a, b) { return J(sortKeys(a)) === J(sortKeys(b)); }
function sortKeys (x) {
  if (Array.isArray(x)) return x.map(sortKeys);
  if (x && typeof x === 'object') return Object.fromEntries(Object.keys(x).sort().map((k) => [k, sortKeys(x[k])]));
  return x;
}

async function runOne (lab, test, ctl, n) {
  const db = `cfgt_${n}`;
  const obs = [];
  const t = { lab, db, brk: (ctl && ctl.brk) || {}, fixture: test.fixture, scratch: lab.scratch, observe: (o) => obs.push(o) };
  for (const k of ['reader', 'roles', 'shape', 'atomic', 'lock', 'checkDrift', 'upTo', 'edit', 'ownerSqlAfter']) {
    if (test.defaults && k in test.defaults) t[k] = test.defaults[k];
    if (ctl && k in ctl) t[k] = ctl[k];
  }
  let stage = 'setup';
  try {
    if (!test.raw) {
      if (t.shape === 'old') {
        await lab.createDb(db);
        const c = await lab.connect('cfg_owner', db);
        try {
          await mig.migrateUp({ client: c, to: '0001_platform_base' });
          await c.query(fs.readFileSync(path.join(__dirname, 'old-shape', 'a2-tenant-settings.sql'), 'utf8'));
        } finally { await c.end(); }
        await lab.super(db, (c) => c.query('GRANT USAGE ON SCHEMA public TO ns_tenant_admin; GRANT SELECT, INSERT ON tenants TO ns_tenant_admin'));
        await lab.as('ns_tenant_admin', db, null, (c) => c.query("INSERT INTO tenants (id, slug) VALUES ($1, 'alpha')", [A]));
      } else {
        await lab.createDb(db, TEMPLATE);
        if (test.fixture === 'postgate') await owner(t, POSTGATE);
        if (ctl && ctl.ownerSql) await owner(t, ctl.ownerSql);
        await seed(t);
      }
    }
    stage = 'run';
    await test.run(t);
    return { ok: true, obs };
  } catch (e) {
    // A control whose SETUP fails proves nothing: it is reported, never counted red.
    return { ok: false, setupError: stage === 'setup', error: (stage === 'setup' ? 'SETUP: ' : '') + (e instanceof Fail ? '' : `${e.code || ''} `) + e.message.split('\n')[0], obs };
  } finally {
    await lab.dropDb(db).catch(() => {});
  }
}

(async () => {
  assertContainerRunning(PORT);
  const lab = new Lab({ port: PORT, secretsDir: SECRETS });
  lab.scratch = fs.mkdtempSync(path.join(SECRETS, 'run-'));
  await lab.init();
  const version = await lab.super('postgres', (c) => c.query('SHOW server_version'));
  await lab.createDb(TEMPLATE);
  const c = await lab.connect('cfg_owner', TEMPLATE);
  await mig.migrateUp({ client: c });
  await c.end();

  const selected = tests.filter((x) => !ONLY || ONLY.includes(x.group) || ONLY.includes(x.id));
  const results = [];
  let n = 0;
  for (const test of selected) {
    const pass = await runOne(lab, test, null, n++);
    const controls = [];
    for (const ctl of test.controls || []) {
      const r = await runOne(lab, test, ctl, n++);
      controls.push({ title: ctl.title, red: !r.ok && !r.setupError, setupError: !!r.setupError, error: r.error || null, obs: r.obs });
    }
    const verdict = pass.ok && controls.length > 0 && controls.every((x) => x.red) ? 'PASS' : (!pass.ok ? 'FAIL' : 'VACUOUS?');
    results.push({ id: test.id, group: test.group, title: test.title, verdict, pass, controls });
    console.log(`${verdict.padEnd(8)} ${test.id}${pass.ok ? '' : '  -- ' + pass.error}`);
    for (const ctl of controls) console.log(`         control ${ctl.red ? 'red  ' : (ctl.setupError ? 'SETUP' : 'GREEN')} ${ctl.title}${ctl.error ? '  -- ' + ctl.error : ''}`);
  }
  await lab.dropDb(TEMPLATE);
  fs.rmSync(lab.scratch, { recursive: true, force: true });
  const summary = {
    when: new Date().toISOString(),
    server: `PostgreSQL ${version.rows[0].server_version} (container cfgschema-pg, postgres:16)`,
    node: process.version,
    tests: results.length,
    pass: results.filter((r) => r.verdict === 'PASS').length,
    controls: results.reduce((a, r) => a + r.controls.length, 0),
    controlsRed: results.reduce((a, r) => a + r.controls.filter((x) => x.red).length, 0)
  };
  if (!ONLY) fs.writeFileSync(OUT, JSON.stringify({ summary, results }, null, 2) + '\n');
  console.log(J(summary));
  process.exit(summary.pass === summary.tests && summary.controls === summary.controlsRed ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
