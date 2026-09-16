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
//   env:   WORKTREE, PG_URL, POOL_PORT, ROUNDS, LATENCY_ITERS, LATENCY_NOTE_ITERS,
//          BUDGET_MS, SKIP_RED
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
// A wall-clock budget for the two interleave loops. `session` mode with a pool
// of one does not fail, it QUEUES -- every operation waits for another client's
// node-postgres idle timeout to hand the single server connection back -- so a
// loop sized in rounds is a loop of unbounded duration. The budget stops it and
// the report says how many rounds it managed, which is itself the measurement.
const BUDGET_MS = parseInt(process.env.BUDGET_MS || '90000', 10);

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

// --------------------------------------------------- the idle-connection child
//
// Run as `node pgbouncer-tenant-binding.js --idle-child <arm>`, in a CHILD
// process, so that "the process dies" is observed as an exit code rather than
// inferred from a stack trace. See idleConnectionError() below for why.
if (process.argv[2] === '--idle-child') {
  const arm = process.argv[3];
  const { Pool: ChildPool, Client: ChildClient } = require(path.join(WORKTREE, 'node_modules', 'pg'));
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  (async function () {
    let pid;
    if (arm === 'store') {
      const init = require(path.join(WORKTREE, 'lib/storage/postgres-storage.js'));
      const ts = require(path.join(WORKTREE, 'lib/storage/tenant-scope.js'));
      ts.setTenancyMode('single');
      const store = await init({
        storageURI: process.env.QC_STORAGE_URI, storageNamespace: process.env.QC_SCHEMA, storagePoolSize: 1 });
      pid = (await store.query('SELECT pg_backend_pid() AS pid')).rows[0].pid;
      // the client is now back in the store's pool, idle
    } else {
      const pool = new ChildPool({ connectionString: process.env.QC_STORAGE_URI, max: 1 });
      if (arm === 'handled') pool.on('error', (err) => console.log('POOL ERROR HANDLED: ' + err.message));
      pid = (await pool.query('SELECT pg_backend_pid() AS pid')).rows[0].pid;
    }
    await wait(200);
    const admin = new ChildClient({ connectionString: process.env.QC_ADMIN_URI });
    await admin.connect();
    await admin.query('SELECT pg_terminate_backend($1)', [ pid ]);
    await admin.end();
    await wait(1500);
    console.log('SURVIVED');
    process.exit(0);
  })().catch((err) => { console.log('REJECTED: ' + err.message); process.exit(3); });
  return;
}

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

// INSTRUMENTATION, NOT A WORKAROUND. In `statement` pooling mode pgbouncer
// CLOSES the client connection when the adapter sends BEGIN, and node-postgres
// turns that into an 'error' event on a Client that is not inside a query --
// which is an uncaughtException and kills the harness before it can say what
// happened. Recording it here lets the run report the exact error instead of a
// stack trace, and every recorded entry is printed. Nothing is retried, no mode
// is substituted for another, and an arm that dies still reports as dead.
const unhandled = [ ];
process.on('uncaughtException', function (err) {
  unhandled.push({ message: err.message, code: err.code });
});
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

// pgbouncer's admin console is a database called `pgbouncer` on the pooler
// itself. Reached with the same credentials; the role is in admin_users.
function adminConsoleURI (url) {
  const parsed = new URL(rewriteHostPort(url, '127.0.0.1', POOL_PORT));
  parsed.pathname = '/pgbouncer';
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
function startBouncer (mode, role, password, poolSize) {
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
    , `default_pool_size = ${poolSize || 1}`
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
 * Can an explicit transaction be opened at all in this pooling mode?
 *
 * Asked before the adapter is booted, with a client whose errors this harness
 * owns, so that a mode which refuses `BEGIN` is reported as a refusal with
 * pgbouncer's own words rather than as a crash somewhere inside the store.
 * Every operation the adapter performs is inside a transaction it opens itself,
 * so this is a precondition for the backend existing at all -- not a detail.
 */
async function beginProbe (pooledURI) {
  const p = new Pool({ connectionString: pooledURI, max: 1 });
  p.on('error', () => { });
  let c = null;
  try {
    c = await p.connect();
    c.on('error', () => { });
    await c.query('BEGIN');
    await c.query('SELECT 1');
    await c.query('COMMIT');
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message, code: err.code };
  } finally {
    if (c) { try { c.release(true); } catch { /* already gone */ } }
    await p.end().catch(() => { });
  }
}

/**
 * Everything the report needs about one (mode, adapter) pair.
 *
 * `adapterRel` is either the shipping module or the RED-1 copy; both are
 * required from the worktree, so the GREEN arm measures the file that ships and
 * the RED arm measures a file that differs from it by one boolean.
 *
 * TWO SHAPES, because one shape cannot answer for all three pooling modes.
 *
 *   SERIAL HANDOFF — one live client connection at a time. A client connects,
 *     binds a tenant, commits, disconnects; the next client connects and reads
 *     without binding anything. With default_pool_size = 1 this forces the same
 *     server connection to be handed from one client to the next in EVERY
 *     pooling mode, session included, which is the literal shape of the failure
 *     being looked for.
 *
 *   CONCURRENT INTERLEAVE — three live client connections alternating short
 *     transactions through a pool of one. This is what a hoster actually runs
 *     and is the shape transaction pooling exists for. In `session` mode a pool
 *     of one cannot serve three live clients at all, and saying so is a result;
 *     the harness records the wait timeout rather than quietly raising the pool
 *     size to get a green run.
 */
function step (out, name, fn) {
  return Promise.resolve().then(fn).then(
    (v) => { out.steps[name] = v; return v; },
    (err) => { out.steps[name] = { failed: true, error: err.message, code: err.code }; return null; });
}

async function battery (mode, adapterRel, label, roleInfo) {
  const initPostgres = req(adapterRel);
  const out = { mode, label, adapter: adapterRel, steps: { } };

  // A schema of this arm's own, created and owned by the run's role. Fresh per
  // arm so one arm's rows can never be mistaken for another's.
  const ns = await pgSupport.isolate(`${mode}-${label}`.replace(/[^a-z0-9]+/gi, '-').slice(0, 20));
  const pooledURI = rewriteHostPort(ns.storageURI, '127.0.0.1', POOL_PORT);
  const table = `"${ns.storageNamespace}"."entries"`;
  out.schema = ns.storageNamespace;

  const openStore = (uri) => initPostgres({
    storageURI: uri
    , storageNamespace: ns.storageNamespace
    , entries_collection: 'entries'
    // One node-side connection per client, so "the client that was just bound"
    // and "the client that queries next" are necessarily the same one and the
    // only multiplexing left is pgbouncer's.
    , storagePoolSize: 1
  });
  const entry = (date, sgv) => ({ date, sgv, type: 'sgv', dateString: new Date(date).toISOString() });

  // ---- 1. does the adapter boot at all through the pooler?
  let storeA = null;
  try {
    storeA = await openStore(pooledURI);
    out.steps.boot = { ok: true };
  } catch (err) {
    out.steps.boot = { ok: false, error: err.message, code: err.code };
    out.fatal = 'boot';
    out.bouncerLog = bouncerLog().split('\n').filter(l => /WARNING|ERROR/.test(l)).slice(-6);
    return out;
  }

  let storeB = null, bystander = null;

  try {
    // ---- 2. where did ensureSchema's unqualified CREATE TABLE land?
    // Asked in single-tenant mode, before the multitenant assertion is armed:
    // these two are catalogue questions, not tenant reads, and an unscoped
    // operation is legitimate in the mode every deployment runs today.
    // ensureSchema issues `SET search_path` and then the emitted DDL on the same
    // node-postgres client but OUTSIDE a transaction. Under transaction or
    // statement pooling those are separate transactions and may reach different
    // server connections, so this is a real question and not a formality.
    await step(out, 'tableInExpectedSchema', async () => {
      const where = await storeA.query(
        'SELECT n.nspname AS schema FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace '
        + "WHERE c.relname = 'entries' AND n.nspname = $1", [ ns.storageNamespace ]);
      const anywhere = await storeA.query(
        'SELECT n.nspname AS schema FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace '
        + "WHERE c.relname = 'entries' AND n.nspname NOT IN ('pg_catalog','information_schema')");
      return { ok: where.rowCount === 1, foundIn: anywhere.rows.map(r => r.schema) };
    });

    // ---- 3. the role, through the pooler. pgbouncer authenticates the client
    // and then opens its OWN server connection; if it did so as anyone else, or
    // as a role that can bypass RLS, nothing below would mean anything.
    await step(out, 'role', async () => (await storeA.query(
      'SELECT current_user AS role, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user')).rows[0]);

    tenantScope.setTenancyMode('multi');

    // ---- 4. seed both tenants. Done from one client while it is the only one
    // live, so this works in session mode too.
    await step(out, 'seed', async () => {
      const coll = storeA.storageCollection({ store: storeA }, { }, 'entries', [ ]);
      for (const [ tenant, base, sgv ] of [ [ TENANT_A, 1700000000000, 100 ], [ TENANT_B, 1800000000000, 200 ] ]) {
        await storeA.withTenant(tenant, async () => {
          for (let i = 0; i < 5; i++) await coll.insertOne(entry(base + i * 300000, sgv + i), { normalize: false });
        });
      }
      return { rowsPerTenant: 5 };
    });

    // ---- 5. SERIAL HANDOFF. One live client at a time, so the single server
    // connection behind the pooler is necessarily passed from each client to
    // the next. This is the probe that answers for all three modes.
    await step(out, 'serialHandoff', async () => {
      await storeA.end(); storeA = null;
      const tally = { rounds: 0, bindingsInherited: 0, inheritedValues: new Set()
        , unboundRowsSeen: 0, unboundTenantsSeen: new Set(), serverPids: new Set(), errors: [ ] };
      const SERIAL_ROUNDS = Math.max(4, Math.min(10, ROUNDS));

      const started = Date.now();
      for (let r = 0; r < SERIAL_ROUNDS && Date.now() - started < BUDGET_MS; r++) {
        const tenant = r % 2 === 0 ? TENANT_A : TENANT_B;

        // (a) a bound client: connect, bind, commit, disconnect.
        const s = await openStore(pooledURI);
        try {
          await s.withTenant(tenant, async () => {
            const pid = await s.query('SELECT pg_backend_pid() AS pid');
            tally.serverPids.add(pid.rows[0].pid);
            await s.query(`SELECT count(*) FROM ${table}`);
          });
        } finally { await s.end().catch(() => { }); }

        // (b) an UNBOUND client on the connection (a) just released: a health
        // check, a monitoring query, a migration, any future code path that
        // reaches the database outside withTenant. This is who inherits a
        // leaked binding, and the rows it can see are rows of a tenant it never
        // named.
        const bys = new Pool({ connectionString: pooledURI, max: 1 });
        try {
          const b = await bys.query("SELECT current_setting('app.current_tenant_id', true) AS tenant, pg_backend_pid() AS pid");
          tally.serverPids.add(b.rows[0].pid);
          if (b.rows[0].tenant) { tally.bindingsInherited++; tally.inheritedValues.add(b.rows[0].tenant); }
          const rows = await bys.query(`SELECT tenant_id::text AS t, count(*)::int AS n FROM ${table} GROUP BY 1`);
          for (const row of rows.rows) { tally.unboundRowsSeen += row.n; tally.unboundTenantsSeen.add(row.t); }
        } catch (err) {
          tally.errors.push(err.message);
        } finally { await bys.end().catch(() => { }); }

        tally.rounds++;
      }
      const elapsedMs = Date.now() - started;
      storeA = await openStore(pooledURI);
      return {
        rounds: tally.rounds, requestedRounds: SERIAL_ROUNDS, elapsedMs
        , msPerRound: tally.rounds ? Math.round(elapsedMs / tally.rounds) : null
        , bindingsInherited: tally.bindingsInherited
        , inheritedValues: [ ...tally.inheritedValues ]
        , unboundRowsSeen: tally.unboundRowsSeen
        , unboundTenantsSeen: [ ...tally.unboundTenantsSeen ]
        , distinctServerPids: tally.serverPids.size
        , serverPids: [ ...tally.serverPids ]
        , errors: tally.errors.slice(0, 3)
      };
    });

    // ---- 6. the mechanism, observed rather than read from the source: after a
    // bound transaction commits, what does the next acquisition see?
    await step(out, 'bindingAfterCommit', async () => {
      await storeA.withTenant(TENANT_A, () => storeA.query(`SELECT count(*) FROM ${table}`));
      return { viaAdapter: await storeA.pooledTenantBinding() };
    });

    // ---- 7. CONCURRENT INTERLEAVE. Three live clients, one server connection.
    await step(out, 'interleave', async () => {
      storeB = await openStore(pooledURI);
      bystander = new Pool({ connectionString: pooledURI, max: 1 });

      const pidOf = (store, tenant) => store.withTenant(tenant, async () =>
        (await store.query('SELECT pg_backend_pid() AS pid')).rows[0].pid);
      const pids = new Set();
      for (let i = 0; i < 3; i++) { pids.add(await pidOf(storeA, TENANT_A)); pids.add(await pidOf(storeB, TENANT_B)); }
      pids.add((await bystander.query('SELECT pg_backend_pid() AS pid')).rows[0].pid);

      const tally = { rounds: 0, boundRowsOwn: 0, boundRowsForeign: 0
        , unboundForeignRows: 0, unboundTenantsSeen: new Set() };
      const byTenant = async (store, tenant) => store.withTenant(tenant, async () =>
        (await store.query(`SELECT tenant_id::text AS t, count(*)::int AS n FROM ${table} GROUP BY 1`)).rows);

      const started = Date.now();
      for (let r = 0; r < ROUNDS && Date.now() - started < BUDGET_MS; r++) {
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
            tally.unboundForeignRows += row.n;    // every row an unbound reader sees is someone else's
            tally.unboundTenantsSeen.add(row.t);
          }
        }
        tally.rounds++;
      }
      const elapsedMs = Date.now() - started;
      return {
        rounds: tally.rounds, requestedRounds: ROUNDS, elapsedMs
        , msPerRound: tally.rounds ? Math.round(elapsedMs / tally.rounds) : null
        , boundRowsOwn: tally.boundRowsOwn, boundRowsForeign: tally.boundRowsForeign
        , unboundForeignRows: tally.unboundForeignRows, unboundTenantsSeen: [ ...tally.unboundTenantsSeen ]
        , distinctServerPids: pids.size, serverPids: [ ...pids ], sharedBackend: pids.size === 1
      };
    });

    // ---- 8. a session-scoped GUC set OUTSIDE any transaction: does the pooler
    // reset it between clients? server_reset_query / DISCARD ALL, measured
    // rather than quoted.
    await step(out, 'sessionGucAcrossRelease', async () => {
      const one = new Pool({ connectionString: pooledURI, max: 1 });
      const setPid = (await one.query("SELECT set_config('app.qc_session_probe','set-by-a',false), pg_backend_pid() AS pid")).rows[0].pid;
      await one.end();
      const two = new Pool({ connectionString: pooledURI, max: 1 });
      const r = await two.query("SELECT current_setting('app.qc_session_probe', true) AS v, pg_backend_pid() AS pid");
      await two.end();
      return { value: r.rows[0].v || null, setPid, readPid: r.rows[0].pid, samePid: setPid === r.rows[0].pid };
    });

    // ---- 9. named prepared statements. The adapter uses NONE -- every query it
    // issues is an unnamed extended-protocol statement -- but transaction
    // pooling is historically where named ones break, so the capability is
    // measured for whoever adds one later.
    await step(out, 'namedPreparedStatements', async () => {
      const psPool = new Pool({ connectionString: pooledURI, max: 1 });
      try {
        const uses = [ ];
        for (let i = 0; i < 4; i++) {
          const c = await psPool.connect();
          try {
            const r = await c.query({ name: 'qc_ps', text: 'SELECT $1::int AS n, pg_backend_pid() AS pid', values: [ i ] });
            uses.push(r.rows[0].pid);
          } finally { c.release(); }
        }
        return { ok: true, backendPids: [ ...new Set(uses) ] };
      } catch (err) {
        return { ok: false, error: err.message, code: err.code };
      } finally { await psPool.end().catch(() => { }); }
    });

    // ---- 10. latency, indicative only: one machine, one run, loopback.
    await step(out, 'latency', async () => {
      const timed = async (fn, n) => {
        const ms = [ ];
        for (let i = 0; i < n; i++) {
          const t = process.hrtime.bigint(); await fn(); ms.push(Number(process.hrtime.bigint() - t) / 1e6);
        }
        return { n, p50: pct(ms, 0.5), p95: pct(ms, 0.95), mean: ms.reduce((a, b) => a + b, 0) / ms.length };
      };
      const pooled = await timed(
        () => storeA.withTenant(TENANT_A, () => storeA.query(`SELECT count(*) FROM ${table}`)), LATENCY_ITERS);
      const direct = await openStore(ns.storageURI);
      let d;
      try {
        d = await timed(
          () => direct.withTenant(TENANT_A, () => direct.query(`SELECT count(*) FROM ${table}`)), LATENCY_ITERS);
      } finally { await direct.end(); }
      return { pooled, direct: d };
    });

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
 * The second question transaction pooling raises, which is not about the tenant
 * binding at all.
 *
 * `postgres-storage.js` issues `SET search_path` in two places, both of them
 * OUTSIDE any transaction:
 *
 *   pool.on('connect', client => client.query(`SET search_path TO "${schema}"`))
 *   ensureSchema()  ->  SET search_path, then the emitted DDL unqualified
 *
 * Under a transaction pooler a statement outside a transaction is its own
 * transaction, and the server connection it lands on is not the server
 * connection the NEXT statement from the same client lands on. `SET` is session
 * state on the server, so the guarantee the `on('connect')` handler is written
 * to provide -- "every connection in the pool, including ones created later" --
 * does not exist through pgbouncer. Whether that matters depends on whether
 * anything relies on search_path; tableFor() qualifies every table name, so
 * ordinary reads do not, but ensureSchema's DDL does.
 *
 * This is demonstrated rather than argued. default_pool_size = 2 gives the
 * pooler a second server connection to fall back on; pinning the first inside
 * an open transaction from another client makes the fallback certain rather
 * than probable, so the probe is deterministic instead of a race the harness
 * hopes to lose.
 */
async function searchPathHazard (roleInfo, seed) {
  const initPostgres = req(SHIPPING_REL);
  const out = { };
  const ns = await pgSupport.isolate('searchpath');
  const pooledURI = rewriteHostPort(ns.storageURI, '127.0.0.1', POOL_PORT);
  out.schema = ns.storageNamespace;

  const store = await initPostgres({
    storageURI: pooledURI, storageNamespace: ns.storageNamespace
    , entries_collection: 'entries', storagePoolSize: 1
  });

  // pin: an open transaction on another client occupies one server connection
  // for as long as it is held.
  const pinPool = new Pool({ connectionString: pooledURI, max: 1 });
  let pinned = null;
  try {
    const ask = async () => {
      const r = await store.query('SELECT current_setting(\'search_path\') AS sp, pg_backend_pid() AS pid');
      return { searchPath: r.rows[0].sp, pid: r.rows[0].pid };
    };
    const unqualified = async () => {
      try {
        await store.query('SELECT count(*) FROM entries');
        return 'resolved';
      } catch (err) { return `[${err.code}] ${err.message}`; }
    };

    out.before = await ask();
    out.beforeUnqualified = await unqualified();

    pinned = await pinPool.connect();
    await pinned.query('BEGIN');
    out.pinPid = (await pinned.query('SELECT pg_backend_pid() AS pid')).rows[0].pid;

    out.after = await ask();
    out.afterUnqualified = await unqualified();

    out.searchPathSurvived = out.before.searchPath === out.after.searchPath;
    out.landedOnAnotherBackend = out.before.pid !== out.after.pid;
  } finally {
    if (pinned) { try { await pinned.query('COMMIT'); } catch { /* going away anyway */ } pinned.release(); }
    await pinPool.end().catch(() => { });
    await store.end().catch(() => { });
  }
  return out;
}

/**
 * An indicative cost note, measured somewhere the number can mean something.
 *
 * The latency figures inside each mode's battery are NOT usable as a cost note:
 * they are taken with three live clients contending for a pool of ONE, which is
 * a configuration chosen to force connection reuse, not to go fast. Two runs of
 * the same harness put the transaction-mode pooled p50 at 0.74 ms and 2.85 ms.
 *
 * This runs the same bound read with a single client and default_pool_size = 20,
 * where the pooler is doing its ordinary job, and reports pooled against direct
 * back to back. One machine, one run, loopback TCP, a 10-row table entirely in
 * cache: it is an order-of-magnitude note about the cost of one extra hop, not
 * a benchmark, and it says nothing about the pooler under load, which is the
 * situation a pooler is added for.
 */
async function latencyNote (roleInfo, seed) {
  const initPostgres = req(SHIPPING_REL);
  const ns = await pgSupport.isolate('latency');
  const pooledURI = rewriteHostPort(ns.storageURI, '127.0.0.1', POOL_PORT);
  const table = `"${ns.storageNamespace}"."entries"`;
  const N = parseInt(process.env.LATENCY_NOTE_ITERS || '2000', 10);

  const open = (uri) => initPostgres({
    storageURI: uri, storageNamespace: ns.storageNamespace, entries_collection: 'entries', storagePoolSize: 1 });

  const timed = async (store) => {
    const ms = [ ];
    for (let i = 0; i < N; i++) {
      const t = process.hrtime.bigint();
      await store.withTenant(TENANT_A, () => store.query(`SELECT count(*) FROM ${table}`));
      ms.push(Number(process.hrtime.bigint() - t) / 1e6);
    }
    return { n: N, p50: pct(ms, 0.5), p90: pct(ms, 0.9), p99: pct(ms, 0.99)
      , mean: ms.reduce((a, b) => a + b, 0) / ms.length };
  };

  tenantScope.setTenancyMode('multi');
  const out = { };
  try {
    // warm both paths first, so neither pays for its own first connection
    const pooled = await open(pooledURI);
    try { out.pooled = await timed(pooled); } finally { await pooled.end(); }
    const direct = await open(ns.storageURI);
    try { out.direct = await timed(direct); } finally { await direct.end(); }
  } finally { tenantScope.setTenancyMode('single'); }
  out.overheadP50 = out.pooled.p50 - out.direct.p50;
  return out;
}

/**
 * Does an error on an IDLE pooled connection reach anybody?
 *
 * `pg-pool` re-emits an idle client's error on the Pool
 * (node_modules/pg-pool/index.js:62, `pool.emit('error', err, client)`), and
 * Node's EventEmitter THROWS on an 'error' event that has no listener. So a
 * Pool created without `pool.on('error')` converts any server-side disconnect
 * of an idle connection into an uncaught exception, which ends the process.
 *
 * postgres-storage.js registers `pool.on('connect')` and no 'error' listener.
 * This is not a pgbouncer defect and it reproduces against a direct connection
 * -- it is in this report because the pooler is what made it visible: the
 * `statement` mode arms above produced nine of these, and the only reason this
 * harness survived to report anything is its own uncaughtException instrument.
 *
 * Three arms, so the answer is a differential rather than an anecdote:
 *   store    the shipping adapter's own pool
 *   bare     a pg.Pool with no error listener       -- the mechanism alone
 *   handled  the same pool WITH pool.on('error')    -- the fix, demonstrated
 *
 * The disconnect is a plain `pg_terminate_backend()`, which is what a failover,
 * a restart, an idle-connection reaper or an operator does.
 */
async function idleConnectionError () {
  const ns = await pgSupport.isolate('idleerr');
  const adminURI = pgSupport.withCredentials(PG_URL, new URL(PG_URL).username || 'postgres', process.env.PGPASSWORD);
  const results = { };
  for (const arm of [ 'store', 'bare', 'handled' ]) {
    try {
      const stdout = execFileSync(process.execPath, [ __filename, '--idle-child', arm ], {
        encoding: 'utf8', stdio: [ 'ignore', 'pipe', 'pipe' ]
        , env: Object.assign({ }, process.env, {
          WORKTREE, QC_STORAGE_URI: ns.storageURI, QC_SCHEMA: ns.storageNamespace, QC_ADMIN_URI: adminURI })
      });
      results[arm] = { exit: 0, out: stdout.trim().split('\n').slice(-2).join(' / ') };
    } catch (err) {
      results[arm] = {
        exit: err.status
        , out: String(err.stdout || '').trim()
        , err: String(err.stderr || '').split('\n').filter(l => l.trim()).slice(0, 4).join(' | ')
      };
    }
  }
  return results;
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
  const s = r.steps || { };
  const f = (x) => x.toFixed(3);
  const bad = (v) => v && v.failed ? `FAILED [${v.code || '-'}] ${v.error}` : null;
  line('');
  line(`--- ${r.mode} / ${r.label} (schema ${r.schema || 'n/a'})`);
  if (s.boot && !s.boot.ok) {
    line(`  boot                    : FAILED [${s.boot.code || '-'}] ${s.boot.error}`);
    if (r.bouncerLog && r.bouncerLog.length) line('  pgbouncer: ' + r.bouncerLog.join(' | '));
    return;
  }
  line('  boot                    : ok');

  if (s.tableInExpectedSchema) line(`  entries table in schema : ${bad(s.tableInExpectedSchema)
    || (s.tableInExpectedSchema.ok ? 'yes' : 'NO — found in ' + JSON.stringify(s.tableInExpectedSchema.foundIn))}`);
  if (s.role) line(`  role through pooler     : ${bad(s.role)
    || `${s.role.role} rolsuper=${s.role.rolsuper} rolbypassrls=${s.role.rolbypassrls}`}`);
  if (s.seed) line(`  seed                    : ${bad(s.seed) || s.seed.rowsPerTenant + ' rows per tenant'}`);

  if (s.serialHandoff) {
    const h = s.serialHandoff;
    if (bad(h)) line(`  SERIAL HANDOFF          : ${bad(h)}`);
    else {
      line(`  SERIAL HANDOFF          : ${h.rounds}/${h.requestedRounds} rounds in ${h.elapsedMs} ms (${h.msPerRound} ms/round), ${h.distinctServerPids} distinct backend pid(s) ${JSON.stringify(h.serverPids)}`);
      line(`    bindings inherited by an unbound client : ${h.bindingsInherited}/${h.rounds} ${JSON.stringify(h.inheritedValues)}`);
      line(`    ROWS an UNBOUND client saw (all foreign): ${h.unboundRowsSeen}  tenants=${JSON.stringify(h.unboundTenantsSeen)}`);
      if (h.errors.length) line(`    errors: ${h.errors.join(' | ')}`);
    }
  }

  if (s.bindingAfterCommit) line(`  binding after COMMIT    : ${bad(s.bindingAfterCommit)
    || (s.bindingAfterCommit.viaAdapter === null ? 'none' : 'PRESENT ' + s.bindingAfterCommit.viaAdapter)}`);

  if (s.interleave) {
    const t = s.interleave;
    if (bad(t)) line(`  CONCURRENT INTERLEAVE   : ${bad(t)}`);
    else {
      line(`  CONCURRENT INTERLEAVE   : ${t.rounds}/${t.requestedRounds} rounds in ${t.elapsedMs} ms (${t.msPerRound} ms/round), ${t.rounds * 2} bound txns + ${t.rounds * 2} unbound reads`);
      line(`    SHARED BACKEND        : ${t.sharedBackend ? 'YES (1 distinct pid)' : 'no (' + t.distinctServerPids + ' pids)'} ${JSON.stringify(t.serverPids)}`);
      line(`    rows a BOUND client saw belonging to the other tenant : ${t.boundRowsForeign}`);
      line(`    rows an UNBOUND reader saw (all foreign)              : ${t.unboundForeignRows} tenants=${JSON.stringify(t.unboundTenantsSeen)}`);
    }
  }

  if (s.sessionGucAcrossRelease) {
    const g = s.sessionGucAcrossRelease;
    line(`  session GUC across a client disconnect : ${bad(g)
      || (g.value === null ? 'cleared' : 'SURVIVED (' + g.value + ')') + ` (pid ${g.setPid} -> ${g.readPid}${g.samePid ? ', same backend' : ', different backend'})`}`);
  }
  if (s.namedPreparedStatements) {
    const p = s.namedPreparedStatements;
    line(`  named prepared statements : ${bad(p) || (p.ok ? 'ok, backend pids ' + JSON.stringify(p.backendPids)
      : 'FAILED [' + (p.code || '-') + '] ' + p.error)}`);
  }
  if (s.latency) {
    if (bad(s.latency)) line(`  latency                 : ${bad(s.latency)}`);
    else {
      line(`  latency n=${s.latency.pooled.n} pooled p50/p95/mean ms : ${f(s.latency.pooled.p50)} / ${f(s.latency.pooled.p95)} / ${f(s.latency.pooled.mean)}`);
      line(`  latency n=${s.latency.direct.n} direct p50/p95/mean ms : ${f(s.latency.direct.p50)} / ${f(s.latency.direct.p95)} / ${f(s.latency.direct.mean)}`);
    }
  }
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
  const summaryExtras = { };

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

    const bp = await beginProbe(rewriteHostPort(seed.storageURI, '127.0.0.1', POOL_PORT));
    line(`explicit BEGIN/COMMIT in this mode : ${bp.ok ? 'accepted' : 'REFUSED [' + (bp.code || '-') + '] ' + bp.error}`);
    if (!bp.ok) {
      line('  Every operation the adapter performs runs inside a transaction it opens itself,');
      line('  so this mode cannot carry the PostgreSQL backend at all. The battery below runs');
      line('  anyway, to record how the failure reaches a caller.');
      const bl = bouncerLog().split('\n').filter(l => /ERROR|WARNING|closing because/.test(l)).slice(-4);
      if (bl.length) line('  pgbouncer said: ' + bl.join(' | '));
    }
    summaryExtras.beginProbe = summaryExtras.beginProbe || { };
    summaryExtras.beginProbe[mode] = bp;

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
        connectionString: adminConsoleURI(seed.storageURI), max: 1
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

  if (MODES.includes('transaction')) {
    head('Indicative cost: one bound read through the pooler vs direct (default_pool_size = 20, one client)');
    startBouncer('transaction', roleInfo.role, roleInfo.password, 20);
    try {
      await waitForBouncer(rewriteHostPort(seed.storageURI, '127.0.0.1', POOL_PORT));
      const c = await latencyNote(roleInfo, seed);
      const f = (x) => x.toFixed(3);
      line(`  n=${c.pooled.n} per arm, transaction pooling, a 10-row table in cache, loopback TCP`);
      line(`  pooled  p50/p90/p99/mean ms : ${f(c.pooled.p50)} / ${f(c.pooled.p90)} / ${f(c.pooled.p99)} / ${f(c.pooled.mean)}`);
      line(`  direct  p50/p90/p99/mean ms : ${f(c.direct.p50)} / ${f(c.direct.p90)} / ${f(c.direct.p99)} / ${f(c.direct.mean)}`);
      line(`  p50 overhead of the extra hop : ${f(c.overheadP50)} ms`);
      line('  INDICATIVE ONLY: one machine, one run, no load, no TLS. Not a benchmark.');
      summaryExtras.latencyNote = c;
    } catch (err) { line(`  probe failed: ${err.message}`); }
    stopBouncer();
  }

  head('An error on an IDLE pooled connection: does it reach anybody?');
  try {
    const idle = await idleConnectionError();
    for (const arm of [ 'store', 'bare', 'handled' ]) {
      const r = idle[arm];
      line(`  ${arm.padEnd(8)} : exit ${r.exit} ${r.out ? ':: ' + r.out : ''}${r.err ? ' :: ' + r.err : ''}`);
    }
    summaryExtras.idleConnectionError = idle;
  } catch (err) { line(`  probe failed: ${err.message}`); }

  // The SET search_path hazard, at default_pool_size = 2 so the pooler HAS a
  // second server connection to hand the next statement to.
  if (MODES.includes('transaction')) {
    head('The SET search_path hazard under transaction pooling (default_pool_size = 2)');
    startBouncer('transaction', roleInfo.role, roleInfo.password, 2);
    try {
      await waitForBouncer(rewriteHostPort(seed.storageURI, '127.0.0.1', POOL_PORT));
      const h = await searchPathHazard(roleInfo, seed);
      line(`  schema under test                     : ${h.schema}`);
      line(`  before pinning : search_path=${h.before.searchPath} backend=${h.before.pid}`);
      line(`                   unqualified SELECT   : ${h.beforeUnqualified}`);
      line(`  pinned backend : ${h.pinPid} (held inside an open transaction by another client)`);
      line(`  after pinning  : search_path=${h.after.searchPath} backend=${h.after.pid}`);
      line(`                   unqualified SELECT   : ${h.afterUnqualified}`);
      line(`  landed on another backend             : ${h.landedOnAnotherBackend ? 'YES' : 'no'}`);
      line(`  search_path survived                  : ${h.searchPathSurvived ? 'yes' : 'NO — the on(connect) SET does not apply here'}`);
      summaryExtras.searchPath = h;
    } catch (err) {
      line(`  probe failed: ${err.message}`);
    }
    stopBouncer();
  }

  // ------------------------------------------------------------ the summary
  head('SUMMARY');
  line('mode        | arm                         | boot | serial: pids/inherited/rows | concurrent: shared/bound-x/unbound-x');
  line('------------|-----------------------------|------|-----------------------------|------------------------------------');
  for (const r of results) {
    const st = r.steps || { };
    const boot = st.boot && !st.boot.ok ? 'FAIL' : 'ok';
    const h = st.serialHandoff;
    const serial = !h ? '-' : h.failed ? 'err'
      : `${h.distinctServerPids}pid / ${h.bindingsInherited}/${h.rounds} / ${h.unboundRowsSeen}`;
    const t = st.interleave;
    const conc = !t ? '-' : t.failed ? 'err: ' + String(t.error).slice(0, 28)
      : `${t.sharedBackend ? 'shared' : t.distinctServerPids + 'pids'} / ${t.boundRowsForeign} / ${t.unboundForeignRows}`;
    line(`${r.mode.padEnd(11)} | ${String(r.label).padEnd(27)} | ${boot.padEnd(4)} | ${serial.padEnd(27)} | ${conc}`);
  }
  line('');
  line('serial:     distinct backend pids / rounds where an unbound client inherited a binding / rows it could then read');
  line('concurrent: backend sharing / rows a bound client saw of the other tenant / rows an unbound reader saw');
  line('');
  line('A GREEN row of 0 is evidence ONLY if the RED-1 row beneath it is non-zero. If both are 0 the');
  line('probe is insensitive to the property it claims to measure and the green result means nothing.');

  if (unhandled.length) {
    head('Errors that reached no caller (uncaught), recorded rather than swallowed');
    for (const u of unhandled.slice(0, 12)) line(`  [${u.code || '-'}] ${u.message}`);
    if (unhandled.length > 12) line(`  ... and ${unhandled.length - 12} more`);
    summaryExtras.unhandled = unhandled;
  }

  console.log('\n----- machine readable -----');
  console.log(JSON.stringify({ results, extras: summaryExtras }, null, 1));
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
