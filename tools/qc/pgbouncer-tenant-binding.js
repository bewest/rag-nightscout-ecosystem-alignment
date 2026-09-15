// Does the D3 tenant binding survive a transaction-pooling connection pooler?
//
// THE QUESTION
// ------------
// The multitenancy execution plan's "what is still unmeasured" table carries one
// row against T2.5:
//
//     pgbouncer + set_config(is_local) | {M} §6.7 says the pooler may be
//     required; its interaction with transaction-scoped binding is untested
//
// tests/postgres-entries-rls.test.js already proves isolation holds with NO
// pooler, including that a connection handed back to node-postgres's own pool
// carries no binding. This harness does not re-test that. It asks only: does the
// property still hold when a REAL pgbouncer sits in between, in each of its
// three pooling modes?
//
// The failure this is looking for is specific and is the classic way RLS
// isolation dies in production. A pooler in `transaction` mode changes the unit
// of connection reuse: the server connection a client's transaction runs on is
// handed to a DIFFERENT client's next transaction. If the tenant binding were
// session-scoped -- `set_config(name, value, false)`, or a bare `SET` -- it
// would outlive the transaction that set it and be visible to whatever ran next
// on that server connection, and pgbouncer does NOT issue `DISCARD ALL` between
// transactions by default (server_reset_query is a *session* mode reset unless
// server_reset_query_always is on). That is one tenant reading another tenant's
// glucose data with no error anywhere.
//
// WHAT IS MEASURED, AND HOW IT CAN GO RED
// ---------------------------------------
// Every positive claim here has a paired break, through the same comparator:
//
//   RED-1  the binding, made session-scoped. The harness writes a COPY of the
//          shipping lib/storage/postgres-storage.js with the single character
//          change `is_local => true` -> `false`, next to the original so its
//          relative requires and __dirname still resolve, and drives the whole
//          battery through the copy. The shipping module is never edited. If
//          the leak probes cannot go red under that copy, they have measured
//          nothing and the green run is vacuous.
//
//   RED-2  BYPASSRLS granted to the very role the run connects as, to show the
//          adapter's boot-time refusal still fires THROUGH the pooler and is
//          not something the pooler hides.
//
// And the run proves, rather than assumes, that the clients shared a backend:
// pg_backend_pid() is read inside every transaction and pgbouncer's own
// SHOW POOLS / SHOW SERVERS is read off the admin console. A green isolation
// result on two clients that never shared a server connection is the exact way
// this test goes vacuous.
//
// SETUP
// -----
//   docker network create pool-net
//   docker run -d --name pool-pg --network pool-net \
//     -e POSTGRES_PASSWORD="$PGPASSWORD" -p 15438:5432 postgres:16-alpine
//
// pgbouncer is started and stopped by this harness, once per pooling mode, from
// a config directory it creates under $TMPDIR and deletes on the way out.
//
//   cd tools/qc && npm install
//   PGPASSWORD=... node pgbouncer-tenant-binding.js [modes...]
//
//   modes: any of  session transaction statement   (default: all three)
//   env:   WORKTREE, PG_URL, POOL_PORT, ROUNDS, LATENCY_ITERS, SKIP_RED
//
// CREDENTIALS. Nothing here is hardcoded and nothing is written into the repo.
// The superuser password is read from PGPASSWORD and never written anywhere.
// The unprivileged role the run connects as is created per run by
// tests/support/postgres.js with a password that exists only in this process's
// memory -- reused rather than reimplemented, because RLS is silently NOT
// enforced for a superuser and a run that connected as one would measure
// nothing. pgbouncer needs that password in a userlist.txt; the file is written
// at 0600 into a mkdtemp directory outside the repository and removed in a
// finally, on SIGINT and on uncaught throw.

'use strict';

const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const { execFileSync } = require('node:child_process');

const { Pool } = require('pg');

const WORKTREE = process.env.WORKTREE
  || '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-pool';

const PG_URL = process.env.PG_URL || 'postgres://postgres@127.0.0.1:15438/postgres';
const POOL_PORT = parseInt(process.env.POOL_PORT || '16438', 10);
const PG_CONTAINER = process.env.PG_CONTAINER || 'pool-pg';
const BOUNCER = process.env.BOUNCER_CONTAINER || 'pool-bouncer';
const DOCKER_NET = process.env.DOCKER_NET || 'pool-net';
const BOUNCER_IMAGE = process.env.BOUNCER_IMAGE || 'edoburu/pgbouncer:latest';
const ROUNDS = parseInt(process.env.ROUNDS || '25', 10);
const LATENCY_ITERS = parseInt(process.env.LATENCY_ITERS || '300', 10);

if (!process.env.PGPASSWORD && !/:[^@/]*@/.test(PG_URL)) {
  console.error('Set PGPASSWORD before running this (or pass a complete PG_URL).');
  console.error('The throwaway containers are created with:');
  console.error('  docker network create pool-net');
  console.error('  docker run -d --name pool-pg --network pool-net \\');
  console.error('    -e POSTGRES_PASSWORD="$PGPASSWORD" -p 15438:5432 postgres:16-alpine');
  console.error('pgbouncer is started by this harness; it needs no password of its own.');
  process.exit(2);
}
process.env.PG_URL = PG_URL;          // tests/support/postgres.js reads it from here

const MODES = (function () {
  const asked = process.argv.slice(2).filter(a => !a.startsWith('-'));
  const all = [ 'session', 'transaction', 'statement' ];
  if (!asked.length) return all;
  for (const m of asked) if (!all.includes(m)) { console.error('unknown mode', m); process.exit(2); }
  return asked;
})();

const req = (p) => require(path.join(WORKTREE, p));
const pgSupport = req('tests/support/postgres.js');
const tenantScope = req('lib/storage/tenant-scope.js');

// Two tenants, fixed, so a failure names the same rows every time. Same pair the
// shipping RLS suite uses, so a cross-tenant row here is recognisable there.
const TENANT_A = '11111111-1111-4111-8111-111111111111';
const TENANT_B = '22222222-2222-4222-8222-222222222222';

// ---------------------------------------------------------------- scratch dir

const SCRATCH = fs.mkdtempSync(path.join(os.tmpdir(), 'poolqc-'));
fs.chmodSync(SCRATCH, 0o700);

// The RED-1 copy of the shipping adapter. Written NEXT TO the original, because
// it reads lib/storage/postgres/generated/ off its own __dirname and requires
// ./tenant-scope; a copy anywhere else would resolve neither. Removed in
// cleanup(). The shipping file is never opened for writing.
const SHIPPING_REL = 'lib/storage/postgres-storage.js';
const RED_REL = 'lib/storage/.qc-red-postgres-storage.js';
const RED_ABS = path.join(WORKTREE, RED_REL);

let cleaned = false;
function cleanup () {
  if (cleaned) return;
  cleaned = true;
  try { execFileSync('docker', [ 'rm', '-f', BOUNCER ], { stdio: 'ignore' }); } catch { /* not running */ }
  try { fs.rmSync(SCRATCH, { recursive: true, force: true }); } catch { /* gone */ }
  try { fs.rmSync(RED_ABS, { force: true }); } catch { /* gone */ }
}
process.on('exit', cleanup);
for (const sig of [ 'SIGINT', 'SIGTERM' ]) process.on(sig, () => { cleanup(); process.exit(130); });

// ------------------------------------------------------------------ plumbing

function docker (args, opts) {
  return execFileSync('docker', args, Object.assign({ encoding: 'utf8' }, opts || { }));
}

function rewriteHostPort (url, host, port) {
  const parsed = new URL(url);
  parsed.hostname = host;
  parsed.port = String(port);
  return parsed.toString();
}

function sleep (ms) { return new Promise(r => setTimeout(r, ms)); }

/**
 * Write pgbouncer's config for one pooling mode and start it.
 *
 * default_pool_size = 1 is the whole point: with one server connection behind
 * the pool, two clients CANNOT avoid sharing a backend, so a green isolation
 * result is a result about a shared backend rather than about two clients that
 * happened never to meet. query_wait_timeout keeps a pool of one from hanging
 * the run forever instead of reporting what it did.
 */
function startBouncer (mode, role, password) {
  const ini = [
    '[databases]'
    , `* = host=${PG_CONTAINER} port=5432`
    , ''
    , '[pgbouncer]'
    , 'listen_addr = 0.0.0.0'
    , 'listen_port = 6432'
    , 'auth_type = scram-sha-256'
    , 'auth_file = /etc/pgbouncer/userlist.txt'
    , `pool_mode = ${mode}`
    , 'default_pool_size = 1'
    , 'min_pool_size = 0'
    , 'reserve_pool_size = 0'
    , 'max_client_conn = 100'
    , 'query_wait_timeout = 15'
    , 'ignore_startup_parameters = extra_float_digits'
    , `admin_users = ${role}`
    , `stats_users = ${role}`
    , 'unix_socket_dir ='
    , 'logfile ='
    , 'pidfile ='
    , ''
  ].join('\n');

  fs.writeFileSync(path.join(SCRATCH, 'pgbouncer.ini'), ini, { mode: 0o644 });
  // The only place this password is ever written. 0600, under mkdtemp, outside
  // the repository, deleted by cleanup().
  fs.writeFileSync(path.join(SCRATCH, 'userlist.txt'), `"${role}" "${password}"\n`, { mode: 0o600 });
  // pgbouncer runs as uid 70 in this image and could not read a 0600 file owned
  // by us, so the container is run AS us instead of loosening the file.
  const uid = typeof process.getuid === 'function' ? process.getuid() : 0;
  const gid = typeof process.getgid === 'function' ? process.getgid() : 0;

  try { docker([ 'rm', '-f', BOUNCER ], { stdio: 'ignore' }); } catch { /* not running */ }
  docker([ 'run', '-d', '--name', BOUNCER, '--network', DOCKER_NET
    , '-p', `${POOL_PORT}:6432`, '--user', `${uid}:${gid}`
    , '-v', `${SCRATCH}:/etc/pgbouncer:ro`
    , '--entrypoint', '/usr/bin/pgbouncer', BOUNCER_IMAGE, '/etc/pgbouncer/pgbouncer.ini' ]);
}

function stopBouncer () {
  try { docker([ 'rm', '-f', BOUNCER ], { stdio: 'ignore' }); } catch { /* not running */ }
}

function bouncerLog () {
  try { return docker([ 'logs', BOUNCER ], { stdio: [ 'ignore', 'pipe', 'pipe' ] }); } catch { return ''; }
}

async function waitForBouncer (uri) {
  for (let i = 0; i < 40; i++) {
    const probe = new Pool({ connectionString: uri, max: 1 });
    try {
      await probe.query('SELECT 1');
      await probe.end();
      return true;
    } catch (err) {
      await probe.end().catch(() => { });
      if (i === 39) throw err;
      await sleep(250);
    }
  }
  return false;
}

// ----------------------------------------------------------- the RED-1 source

/**
 * A copy of the shipping adapter whose ONLY difference is that the tenant
 * binding is session-scoped instead of transaction-scoped.
 *
 * This is the break the whole report rests on. If the leak probes stay green
 * against this copy, then they are not sensitive to the property they claim to
 * measure and every green result above them is vacuous.
 */
function writeRedAdapter () {
  const src = fs.readFileSync(path.join(WORKTREE, SHIPPING_REL), 'utf8');
  const from = "await client.query(\"SELECT set_config('app.current_tenant_id', $1, true)\", [ uuid ]);";
  const to = "await client.query(\"SELECT set_config('app.current_tenant_id', $1, false)\", [ uuid ]);";
  if (!src.includes(from)) {
    throw new Error('the shipping binding statement is not where this harness expects it; '
      + 'refusing to guess. Re-read ' + SHIPPING_REL + ' and fix the RED-1 substitution.');
  }
  if (src.split(from).length !== 2) throw new Error('the binding statement is not unique');
  fs.writeFileSync(RED_ABS, src.replace(from, to));
  return { from, to };
}

// ------------------------------------------------------------- measurements

function pct (values, p) {
  const s = [ ...values ].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(s.length * p))];
}

/**
 * Everything the report needs about one (mode, adapter) pair.
 *
 * `adapterRel` is either the shipping module or the RED-1 copy; both are
 * required from the worktree, so the GREEN arm measures the file that ships and
 * the RED arm measures a file that differs from it by one boolean.
 */
async function battery (mode, adapterRel, label, roleInfo) {
  const initPostgres = req(adapterRel);
  const out = { mode, label, adapter: adapterRel, steps: { } };

  // A schema of this arm's own, created and owned by the run's role. Fresh per
  // arm so one arm's rows can never be mistaken for another's.
  const ns = await pgSupport.isolate(`${mode}-${label}`.replace(/[^a-z0-9]+/gi, '-'));
  const pooledURI = rewriteHostPort(ns.storageURI, '127.0.0.1', POOL_PORT);
  const table = `"${ns.storageNamespace}"."entries"`;
  out.schema = ns.storageNamespace;

  // ---- 1. does the adapter boot at all through the pooler
  let storeA = null, storeB = null, bystander = null;
  const openStore = (uri) => initPostgres({
    storageURI: uri
    , storageNamespace: ns.storageNamespace
    , entries_collection: 'entries'
    // One node-side connection per client, so "the client that was just bound"
    // and "the client that queries next" are necessarily the same one and the
    // only multiplexing left is pgbouncer's.
    , storagePoolSize: 1
  });

  try {
    storeA = await openStore(pooledURI);
    out.steps.boot = { ok: true };
  } catch (err) {
    out.steps.boot = { ok: false, error: err.message, code: err.code };
    out.fatal = 'boot';
    out.bouncerLog = bouncerLog().split('\n').filter(l => /WARNING|ERROR|LOG C-|closing/.test(l)).slice(-6);
    return out;
  }

  try {
    // ---- 2. where did ensureSchema's unqualified CREATE TABLE actually land?
    // ensureSchema issues `SET search_path` and then the emitted DDL on the same
    // node-postgres client but OUTSIDE a transaction. Under transaction pooling
    // those are two independent transactions and may reach two different server
    // connections, so this is a real question and not a formality.
    const where = await storeA.query(
      'SELECT n.nspname AS schema FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace '
      + "WHERE c.relname = 'entries' AND n.nspname = $1", [ ns.storageNamespace ]);
    out.steps.tableInExpectedSchema = { ok: where.rowCount === 1, rowCount: where.rowCount };

    // ---- 3. the role, through the pooler. pgbouncer authenticates the client
    // and then opens its OWN server connection; if it did so as anyone else, or
    // as a role that can bypass RLS, nothing below would mean anything.
    const who = await storeA.query(
      'SELECT current_user AS role, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user');
    out.steps.role = who.rows[0];

    storeB = await openStore(pooledURI);

    // A third client that never binds anything: a monitoring query, a health
    // check, a migration, any future code path that reaches the database
    // outside withTenant. This is who inherits a leaked binding.
    bystander = new Pool({ connectionString: pooledURI, max: 1 });

    tenantScope.setTenancyMode('multi');

    // ---- 4. seed, each tenant through its own client
    const collA = storeA.storageCollection({ store: storeA }, { }, 'entries', [ ]);
    const collB = storeB.storageCollection({ store: storeB }, { }, 'entries', [ ]);
    const entry = (date, sgv) => ({ date, sgv, type: 'sgv', dateString: new Date(date).toISOString() });
    await storeA.withTenant(TENANT_A, async () => {
      for (let i = 0; i < 5; i++) await collA.insertOne(entry(1700000000000 + i * 300000, 100 + i), { normalize: false });
    });
    await storeB.withTenant(TENANT_B, async () => {
      for (let i = 0; i < 5; i++) await collB.insertOne(entry(1800000000000 + i * 300000, 200 + i), { normalize: false });
    });
    out.steps.seeded = true;

    // ---- 5. did the two clients actually share a backend?
    const pidOf = (store, tenant) => store.withTenant(tenant, async () =>
      (await store.query('SELECT pg_backend_pid() AS pid')).rows[0].pid);
    const pidsA = [], pidsB = [];
    for (let i = 0; i < 3; i++) { pidsA.push(await pidOf(storeA, TENANT_A)); pidsB.push(await pidOf(storeB, TENANT_B)); }
    const bysPid = (await bystander.query('SELECT pg_backend_pid() AS pid')).rows[0].pid;
    out.steps.backendPids = {
      a: pidsA, b: pidsB, bystander: bysPid
      , shared: new Set([ ...pidsA, ...pidsB, bysPid ]).size === 1
      , distinct: new Set([ ...pidsA, ...pidsB, bysPid ]).size
    };

    // ---- 6. the mechanism, observed rather than read: after a bound
    // transaction commits, what does the next acquisition see?
    await storeA.withTenant(TENANT_A, async () => storeA.query(`SELECT count(*) FROM ${table}`));
    out.steps.pooledTenantBinding = await storeA.pooledTenantBinding();
    const leaked = await bystander.query(
      "SELECT current_setting('app.current_tenant_id', true) AS tenant");
    out.steps.bystanderSeesBinding = leaked.rows[0].tenant || null;

    // ---- 7. THE COUNT. Alternating short transactions through a pool of one,
    // each client reading a table where the other tenant has rows, with an
    // unbound bystander read between every pair.
    const tally = { boundRowsOwn: 0, boundRowsForeign: 0, unboundRows: 0, unboundForeignRows: 0
      , unboundTenantsSeen: new Set(), rounds: 0 };
    const byTenant = async (store, tenant) => store.withTenant(tenant, async () =>
      (await store.query(`SELECT tenant_id::text AS t, count(*)::int AS n FROM ${table} GROUP BY 1`)).rows);

    for (let r = 0; r < ROUNDS; r++) {
      for (const [ store, tenant ] of [ [ storeA, TENANT_A ], [ storeB, TENANT_B ] ]) {
        for (const row of await byTenant(store, tenant)) {
          if (row.t === tenant) tally.boundRowsOwn += row.n; else tally.boundRowsForeign += row.n;
        }
        // The unbound read, on the server connection that transaction just
        // released. Under a transaction-local binding it is unbound and RLS
        // gives it zero rows; under a session-local one it inherits.
        const seen = await bystander.query(
          `SELECT tenant_id::text AS t, count(*)::int AS n FROM ${table} GROUP BY 1`);
        for (const row of seen.rows) {
          tally.unboundRows += row.n;
          tally.unboundForeignRows += row.n;   // every row an unbound reader sees is another tenant's
          tally.unboundTenantsSeen.add(row.t);
        }
      }
      tally.rounds++;
    }
    tally.unboundTenantsSeen = [ ...tally.unboundTenantsSeen ];
    out.steps.interleave = tally;

    // ---- 8. a session-scoped GUC set OUTSIDE any transaction: does the pooler
    // reset it between clients? This is server_reset_query / DISCARD ALL,
    // measured rather than quoted.
    const probeClient = await bystander.connect();
    const probePid = (await probeClient.query('SELECT pg_backend_pid() AS pid')).rows[0].pid;
    await probeClient.query("SELECT set_config('app.qc_session_probe', 'set-by-bystander', false)");
    probeClient.release();
    const after = await bystander.query(
      "SELECT current_setting('app.qc_session_probe', true) AS v, pg_backend_pid() AS pid");
    out.steps.sessionGucAcrossRelease = {
      value: after.rows[0].v || null, samePid: after.rows[0].pid === probePid
      , setPid: probePid, readPid: after.rows[0].pid
    };

    // ---- 9. prepared statements. The adapter uses none -- every query it
    // issues is an unnamed extended-protocol statement -- but transaction
    // pooling is historically where named ones break, so the capability is
    // measured for whoever adds one later.
    try {
      const psClient = await bystander.connect();
      for (let i = 0; i < 3; i++) {
        await psClient.query({ name: 'qc_ps', text: 'SELECT $1::int AS n', values: [ i ] });
        psClient.release();
        // re-acquire, so the named statement's second use may land on a
        // different server connection than its PREPARE did
        Object.assign(psClient, await bystander.connect());
      }
      psClient.release();
      out.steps.namedPreparedStatements = { ok: true };
    } catch (err) {
      out.steps.namedPreparedStatements = { ok: false, error: err.message, code: err.code };
    }

    // ---- 10. latency, indicative only
    const timed = async (fn, n) => {
      const ms = [];
      for (let i = 0; i < n; i++) { const t = process.hrtime.bigint(); await fn(); ms.push(Number(process.hrtime.bigint() - t) / 1e6); }
      return { n, p50: pct(ms, 0.5), p95: pct(ms, 0.95), mean: ms.reduce((a, b) => a + b, 0) / ms.length };
    };
    out.steps.latencyPooled = await timed(
      () => storeA.withTenant(TENANT_A, () => storeA.query(`SELECT count(*) FROM ${table}`)), LATENCY_ITERS);

    const direct = await openStore(ns.storageURI);
    try {
      out.steps.latencyDirect = await timed(
        () => direct.withTenant(TENANT_A, () => direct.query(`SELECT count(*) FROM ${table}`)), LATENCY_ITERS);
    } finally { await direct.end(); }

  } catch (err) {
    out.error = { message: err.message, code: err.code, stack: err.stack.split('\n').slice(0, 4).join('\n') };
  } finally {
    tenantScope.setTenancyMode('single');
    if (bystander) await bystander.end().catch(() => { });
    if (storeB) await storeB.end().catch(() => { });
    if (storeA) await storeA.end().catch(() => { });
  }

  out.bouncerLog = bouncerLog().split('\n').filter(l => /WARNING|ERROR/.test(l)).slice(-6);
  return out;
}

/**
 * RED-2: the adapter refuses to boot under BYPASSRLS. Run THROUGH the pooler,
 * because the interesting question is not whether the check works (the shipping
 * suite shows that) but whether a pooler in between hides the answer -- it is
 * pgbouncer that opens the server connection, and pgbouncer that could have
 * been talking to a different role than the client authenticated as.
 */
async function bypassRlsProbe (mode, roleInfo, pooledURI, namespace) {
  const initPostgres = req(SHIPPING_REL);
  const out = { };
  const admin = await pgSupport.connectAdmin();
  try {
    await admin.query(`ALTER ROLE "${roleInfo.role}" BYPASSRLS`);
  } finally { await admin.end(); }
  try {
    const store = await initPostgres({ storageURI: pooledURI, storageNamespace: namespace, storagePoolSize: 1 });
    await store.end();
    out.refused = false;
  } catch (err) {
    out.refused = /BYPASSRLS|SUPERUSER/.test(err.message);
    out.error = err.message;
  } finally {
    const admin2 = await pgSupport.connectAdmin();
    try { await admin2.query(`ALTER ROLE "${roleInfo.role}" NOBYPASSRLS`); } finally { await admin2.end(); }
  }
  return out;
}

// ------------------------------------------------------------------- reporting

function line (s) { console.log(s); }
function head (s) { line(''); line('='.repeat(78)); line(s); line('='.repeat(78)); }

function reportArm (r) {
  line('');
  line(`--- ${r.mode} / ${r.label} (schema ${r.schema || 'n/a'})`);
  if (r.steps.boot && !r.steps.boot.ok) {
    line(`  BOOT FAILED: [${r.steps.boot.code || '-'}] ${r.steps.boot.error}`);
    if (r.bouncerLog && r.bouncerLog.length) line('  pgbouncer: ' + r.bouncerLog.join(' | '));
    return;
  }
  line(`  boot                         : ok`);
  const s = r.steps;
  if (s.tableInExpectedSchema) line(`  entries table in run schema  : ${s.tableInExpectedSchema.ok ? 'yes' : 'NO (' + s.tableInExpectedSchema.rowCount + ')'}`);
  if (s.role) line(`  role through pooler          : ${s.role.role} rolsuper=${s.role.rolsuper} rolbypassrls=${s.role.rolbypassrls}`);
  if (s.backendPids) {
    line(`  backend pids A/B/bystander   : ${s.backendPids.a.join(',')} / ${s.backendPids.b.join(',')} / ${s.backendPids.bystander}`);
    line(`  SHARED BACKEND               : ${s.backendPids.shared ? 'YES (1 distinct pid)' : 'no (' + s.backendPids.distinct + ' distinct pids)'}`);
  }
  if ('pooledTenantBinding' in s) line(`  binding after COMMIT (adapter): ${s.pooledTenantBinding === null ? 'none' : s.pooledTenantBinding}`);
  if ('bystanderSeesBinding' in s) line(`  binding seen by bystander    : ${s.bystanderSeesBinding === null ? 'none' : s.bystanderSeesBinding}`);
  if (s.interleave) {
    const t = s.interleave;
    line(`  interleave rounds            : ${t.rounds} (${t.rounds * 2} bound txns, ${t.rounds * 2} unbound reads)`);
    line(`  rows a BOUND client saw that belong to the other tenant : ${t.boundRowsForeign}`);
    line(`  rows an UNBOUND reader saw (all of them foreign)        : ${t.unboundForeignRows}  tenants=${JSON.stringify(t.unboundTenantsSeen)}`);
  }
  if (s.sessionGucAcrossRelease) {
    const g = s.sessionGucAcrossRelease;
    line(`  session GUC across release   : ${g.value === null ? 'cleared' : 'SURVIVED (' + g.value + ')'} (pids ${g.setPid} -> ${g.readPid})`);
  }
  if (s.namedPreparedStatements) {
    line(`  named prepared statements    : ${s.namedPreparedStatements.ok ? 'ok' : 'FAILED [' + (s.namedPreparedStatements.code || '-') + '] ' + s.namedPreparedStatements.error}`);
  }
  if (s.latencyPooled && s.latencyDirect) {
    const f = (x) => x.toFixed(3);
    line(`  latency n=${s.latencyPooled.n} pooled p50/p95/mean ms : ${f(s.latencyPooled.p50)} / ${f(s.latencyPooled.p95)} / ${f(s.latencyPooled.mean)}`);
    line(`  latency n=${s.latencyDirect.n} direct p50/p95/mean ms : ${f(s.latencyDirect.p50)} / ${f(s.latencyDirect.p95)} / ${f(s.latencyDirect.mean)}`);
  }
  if (r.error) line(`  ERROR: [${r.error.code || '-'}] ${r.error.message}`);
  if (r.bouncerLog && r.bouncerLog.length) line('  pgbouncer: ' + r.bouncerLog.join(' | '));
}

// ------------------------------------------------------------------- the run

async function main () {
  head('pgbouncer + set_config(is_local) — does the D3 tenant binding survive a pooler?');
  line(`worktree : ${WORKTREE}`);
  line(`commit   : ${execFileSync('git', [ '-C', WORKTREE, 'rev-parse', 'HEAD' ], { encoding: 'utf8' }).trim()}`);
  line(`postgres : ${PG_URL.replace(/:\/\/[^@]*@/, '://***@')}`);
  line(`pooler   : 127.0.0.1:${POOL_PORT}, default_pool_size=1, modes ${MODES.join(', ')}`);
  line(`scratch  : ${SCRATCH} (userlist.txt 0600, removed on exit)`);

  // The role and its password. Created by the shipping test harness so this run
  // cannot accidentally connect as a superuser and measure nothing.
  const seed = await pgSupport.isolate('bootstrap');
  const roleInfo = { role: seed.role, password: new URL(seed.storageURI).password };
  line(`role     : ${roleInfo.role} (NOSUPERUSER NOBYPASSRLS, generated per run)`);

  const sub = writeRedAdapter();
  line(`RED-1    : ${RED_REL} = shipping module with`);
  line(`             ${sub.from}`);
  line(`           replaced by`);
  line(`             ${sub.to}`);

  const results = [ ];

  for (const mode of MODES) {
    head(`pool_mode = ${mode}`);
    startBouncer(mode, roleInfo.role, roleInfo.password);
    const probeURI = rewriteHostPort(seed.storageURI, '127.0.0.1', POOL_PORT);
    try {
      await waitForBouncer(probeURI);
      line('pgbouncer up and accepting connections');
    } catch (err) {
      line(`pgbouncer did NOT accept a connection: ${err.message}`);
      line(bouncerLog().split('\n').slice(-8).join('\n'));
      results.push({ mode, label: 'GREEN(shipping)', steps: { boot: { ok: false, error: 'pooler unreachable: ' + err.message } } });
      stopBouncer();
      continue;
    }

    const green = await battery(mode, SHIPPING_REL, 'GREEN(shipping)', roleInfo);
    reportArm(green);
    results.push(green);

    if (!process.env.SKIP_RED) {
      const red = await battery(mode, RED_REL, 'RED-1(session-scoped binding)', roleInfo);
      reportArm(red);
      results.push(red);
    }

    // pgbouncer's own account of what happened, so "shared backend" is not only
    // our inference from pg_backend_pid().
    try {
      const adminConsole = new Pool({
        connectionString: rewriteHostPort(seed.storageURI, '127.0.0.1', POOL_PORT).replace(/\/[^/?]*(\?|$)/, '/pgbouncer$1')
        , max: 1
      });
      for (const q of [ 'SHOW POOLS', 'SHOW SERVERS', 'SHOW CONFIG' ]) {
        const r = await adminConsole.query(q);
        if (q === 'SHOW CONFIG') {
          const keep = r.rows.filter(row => /pool_mode|server_reset_query|max_prepared|default_pool_size|server_lifetime/.test(row.key));
          line(`  ${q}: ` + keep.map(row => `${row.key}=${JSON.stringify(row.value)}`).join(' '));
        } else if (q === 'SHOW POOLS') {
          line(`  ${q}: ` + r.rows.filter(row => row.database !== 'pgbouncer')
            .map(row => `db=${row.database} user=${row.user} cl_active=${row.cl_active} sv_active=${row.sv_active} sv_idle=${row.sv_idle} sv_used=${row.sv_used} pool_mode=${row.pool_mode}`).join(' | '));
        } else {
          line(`  ${q}: ` + (r.rows.length ? r.rows.map(row => `pid=${row.remote_pid} state=${row.state}`).join(' | ') : '(none live)'));
        }
      }
      await adminConsole.end();
    } catch (err) {
      line(`  admin console unavailable: ${err.message}`);
    }

    stopBouncer();
  }

  // RED-2, once, in the mode that matters most.
  if (MODES.includes('transaction') && !process.env.SKIP_RED) {
    head('RED-2: does the BYPASSRLS refusal still fire through the pooler?');
    startBouncer('transaction', roleInfo.role, roleInfo.password);
    const ns = await pgSupport.isolate('bypass');
    const pooledURI = rewriteHostPort(ns.storageURI, '127.0.0.1', POOL_PORT);
    try {
      await waitForBouncer(pooledURI);
      const r = await bypassRlsProbe('transaction', roleInfo, pooledURI, ns.storageNamespace);
      line(`  store refused to boot under BYPASSRLS : ${r.refused ? 'YES' : 'NO — THE POOLER HID IT'}`);
      line(`  error                                 : ${r.error || '(none — it booted)'}`);
    } catch (err) {
      line(`  probe failed: ${err.message}`);
    }
    stopBouncer();
  }

  // ------------------------------------------------------------ the summary
  head('SUMMARY');
  line('mode         | arm                           | boot | shared backend | bound cross-tenant rows | unbound reader rows');
  line('-------------|-------------------------------|------|----------------|-------------------------|--------------------');
  for (const r of results) {
    const s = r.steps || { };
    const boot = s.boot && !s.boot.ok ? 'FAIL' : 'ok';
    const shared = s.backendPids ? (s.backendPids.shared ? 'YES' : 'no(' + s.backendPids.distinct + ')') : '-';
    const bound = s.interleave ? String(s.interleave.boundRowsForeign) : '-';
    const unbound = s.interleave ? String(s.interleave.unboundForeignRows) : '-';
    line(`${r.mode.padEnd(12)} | ${String(r.label).padEnd(29)} | ${boot.padEnd(4)} | ${shared.padEnd(14)} | ${bound.padEnd(23)} | ${unbound}`);
  }
  line('');
  line('A GREEN row with 0 / 0 is evidence only if the RED-1 row beneath it is non-zero.');
  line('If both are 0, the probe is insensitive and the green result means nothing.');

  console.log('\n----- machine readable -----');
  console.log(JSON.stringify(results, null, 1));
}

main().then(async () => {
  await pgSupport.cleanup();
  cleanup();
  process.exit(0);
}, async (err) => {
  console.error('\nHARNESS FAILED:', err && err.stack || err);
  try { await pgSupport.cleanup(); } catch { /* best effort */ }
  cleanup();
  process.exit(1);
});
