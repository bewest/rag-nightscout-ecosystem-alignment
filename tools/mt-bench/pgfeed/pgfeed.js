// EXP-MT-057 — how does the evaluator learn that a tenant has new data?
//
// The component design says ns-evaluator is "change-driven" and never says by what
// mechanism. There are four candidates and they are not equivalent, because the
// consumer is an ALARM path: an event that is merely delayed is a nuisance, and an
// event that is silently dropped is a missed hypo alert.
//
//   1. write-path publish   the api tells the evaluator on ingest
//   2. LISTEN/NOTIFY        a trigger fires pg_notify; consumers LISTEN
//   3. logical replication  a slot decodes WAL; the slot remembers the position
//   4. polling              ask storage which tenants are due
//
// The question that separates them is not throughput. It is: WHAT HAPPENS WHILE THE
// CONSUMER IS NOT THERE? Every arm below therefore includes a disconnect test —
// write N rows with the consumer down, bring it back, and count what it sees.
//
// Also measured here, because §6.1's RLS PoC used a generic 500x600 corpus rather
// than Nightscout's: does an RLS policy predicate give the planner index bounds on
// the Nightscout query shapes, the way an explicit Mongo discriminator did in
// EXP-MT-011b (10 keys examined for 10 returned)?
//
// Arms:
//   rls     — RLS overhead and index locality on Nightscout query shapes
//   notify  — LISTEN/NOTIFY throughput, latency, and loss across a disconnect
//   slot    — logical replication slot: same, plus WAL retention when abandoned
//   poll    — the aggregate "which tenants are due" query, cost vs tenant count
//
// Usage:
//   node pgfeed.js [arm] [tenants]
//   PG_URL=... node pgfeed.js all 400
//
// LIMITS: one postgres:16-alpine container, loopback, no TLS, laptop. Same caveats
// as §L of the EXP-MT-026 report. What transfers is the SEMANTICS (what is lost,
// what resumes, what the planner does) far more than the timings.

'use strict';

const fs = require('fs');
const path = require('path');
const { Client, Pool } = require('pg');

const PG_URL = process.env.PG_URL || 'postgres://postgres@127.0.0.1:15433/postgres';

// Credentials come from the environment, never from this file. PGPASSWORD is
// what node-postgres reads when the URL carries no password.
if (!process.env.PGPASSWORD && !/:[^@/]*@/.test(PG_URL)) {
  console.error('Set PGPASSWORD before running this (or pass a complete PG_URL).');
  console.error('The throwaway POC container is created with:');
  console.error('  docker run -d --name <name> -e POSTGRES_PASSWORD="$PGPASSWORD" \\');
  console.error('    -p <port>:5432 postgres:16-alpine');
  process.exit(2);
}

// RLS is NOT enforced for superusers — BYPASSRLS is implicit, and FORCE ROW LEVEL
// SECURITY only subjects the table OWNER, not a superuser. Measuring the policy as
// `postgres` measures nothing: the planner never sees the predicate, an unbound
// connection returns every row, and it all looks like RLS is broken. §6.1's
// "app role NOSUPERUSER NOBYPASSRLS" is load-bearing, and this is the arm that
// proves why.
const APP_URL = process.env.APP_URL || 'postgres://ns_app@127.0.0.1:15433/postgres';
const TENANTS = parseInt(process.argv[3], 10) || 400;
const N_ENTRIES = 576;
const SLOT = 'ns_evaluator';

function stats (a) {
  const s = [...a].sort((x, y) => x - y);
  return { p50: +s[Math.floor(s.length * 0.5)].toFixed(3),
    p99: +s[Math.floor(s.length * 0.99)].toFixed(3) };
}
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// ---------------------------------------------------------------- schema
//
// Mirrors rls-poc/setup.sql (which reimplements Nocturne's verified pattern) and
// adds the trigger and slot this experiment needs. FORCE is the load-bearing word:
// without it the table owner bypasses the policy.

const APP_ROLE = `
DROP ROLE IF EXISTS ns_app;
CREATE ROLE ns_app LOGIN PASSWORD 'poc' NOSUPERUSER NOBYPASSRLS;
`;
const GRANTS = `
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO ns_app;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO ns_app;
`;

const SCHEMA = `
DROP TABLE IF EXISTS entries CASCADE;
DROP TABLE IF EXISTS eval_state CASCADE;

CREATE TABLE entries (
  id          bigserial PRIMARY KEY,
  tenant_id   uuid NOT NULL,
  date        bigint NOT NULL,
  sgv         int,
  direction   text,
  type        text,
  device      text,
  rssi        int,
  doc         jsonb
);
-- The §6.3 shape: tenant_id leading, so the policy predicate is an ordinary
-- equality the planner can build index bounds from.
CREATE INDEX entries_tenant_date ON entries (tenant_id, date DESC);
CREATE INDEX entries_date ON entries (date DESC);

ALTER TABLE entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE entries FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON entries
  USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);

-- Per-tenant evaluation watermark. This is the ack/snooze table's neighbour: the
-- small amount of state the evaluator must keep durably so any worker can pick up
-- any tenant.
CREATE TABLE eval_state (
  tenant_id       uuid PRIMARY KEY,
  last_evaluated  bigint NOT NULL DEFAULT 0
);

-- Arm 2's mechanism. Deliberately minimal: a NOTIFY payload is capped at 8000
-- bytes, so it carries an identifier and never a document.
CREATE OR REPLACE FUNCTION notify_entry() RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify('entries_changed',
    json_build_object('tenant', NEW.tenant_id, 'date', NEW.date)::text);
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER entries_notify AFTER INSERT ON entries
  FOR EACH ROW EXECUTE FUNCTION notify_entry();
`;

function tenantUuid (t) {
  const h = t.toString(16).padStart(12, '0');
  return `00000000-0000-4000-8000-${h}`;
}

async function setup (pool) {
  await pool.query(APP_ROLE).catch(() => {});
  await pool.query(SCHEMA);
  await pool.query(GRANTS);
  console.log('schema created: entries + RLS(FORCE) + tenant_id-leading index + NOTIFY trigger');

  // The trigger makes bulk load expensive and the load is not what is being
  // measured, so it is disabled for the seed and re-enabled afterwards.
  await pool.query('ALTER TABLE entries DISABLE TRIGGER entries_notify');
  const t0 = Date.now();
  for (let t = 0; t < TENANTS; t++) {
    const vals = [];
    const params = [];
    for (let i = 0; i < N_ENTRIES; i++) {
      const base = i * 8;
      vals.push(`($${base + 1},$${base + 2},$${base + 3},$${base + 4},$${base + 5},$${base + 6},$${base + 7},$${base + 8})`);
      params.push(tenantUuid(t), Date.now() - i * 300000, 70 + ((i * 7 + t * 13) % 180),
        'Flat', 'sgv', 'xDrip-DexcomG6', 100, JSON.stringify({ filtered: 180000, noise: 1 }));
    }
    await pool.query(
      `INSERT INTO entries (tenant_id,date,sgv,direction,type,device,rssi,doc) VALUES ${vals.join(',')}`,
      params);
    await pool.query('INSERT INTO eval_state (tenant_id) VALUES ($1) ON CONFLICT DO NOTHING',
      [tenantUuid(t)]);
  }
  await pool.query('ALTER TABLE entries ENABLE TRIGGER entries_notify');
  await pool.query('ANALYZE entries');
  const { rows } = await pool.query(
    `SELECT count(*) n, pg_size_pretty(pg_total_relation_size('entries')) sz FROM entries`);
  console.log(`loaded ${TENANTS} tenants x ${N_ENTRIES} = ${rows[0].n} rows, ${rows[0].sz}, ` +
    `${((Date.now() - t0) / 1000).toFixed(1)}s\n`);
  return { rows: +rows[0].n, size: rows[0].sz };
}

// ---------------------------------------------------------------- arm: rls

async function armRls (ownerPool) {
  console.log('--- RLS overhead and index locality on Nightscout query shapes ---');
  console.log('  (as ns_app: NOSUPERUSER NOBYPASSRLS — as a superuser RLS is not enforced at all)');
  const pool = new Pool({ connectionString: APP_URL, max: 20 });
  const tid = tenantUuid(0);

  // Bound per transaction, which is the §6.7 mechanism: one set_config per
  // request on a shared pool, rather than one credential per tenant.
  async function bound (sql, params) {
    const c = await pool.connect();
    try {
      await c.query('BEGIN');
      await c.query(`SELECT set_config('app.current_tenant_id', $1, true)`, [tid]);
      const r = await c.query(sql, params);
      await c.query('COMMIT');
      return r;
    } finally { c.release(); }
  }

  async function timeIt (label, fn, iters) {
    for (let i = 0; i < 20; i++) await fn();
    const w = [];
    for (let i = 0; i < iters; i++) {
      const s = process.hrtime.bigint();
      await fn();
      w.push(Number(process.hrtime.bigint() - s) / 1e6);
    }
    const st = stats(w);
    console.log(`  ${label.padEnd(50)} ${st.p50.toFixed(3)} ms p50 / ${st.p99.toFixed(3)} p99`);
    return st;
  }

  // NOTE: the RLS-bound query carries NO tenant predicate in the SQL at all.
  const rlsRead = await timeIt('RLS-bound, no predicate in SQL (?count=10)',
    () => bound('SELECT * FROM entries ORDER BY date DESC LIMIT 10'), 200);
  const explicit = await timeIt('explicit WHERE tenant_id (RLS also active)',
    () => bound('SELECT * FROM entries WHERE tenant_id=$1 ORDER BY date DESC LIMIT 10', [tid]), 200);
  const window576 = await timeIt('RLS-bound, full 48 h window (576 rows)',
    () => bound('SELECT * FROM entries ORDER BY date DESC LIMIT 576'), 100);

  // Does the policy predicate give the planner index bounds?
  const c = await pool.connect();
  await c.query('BEGIN');
  await c.query(`SELECT set_config('app.current_tenant_id', $1, true)`, [tid]);
  const plan = await c.query(
    'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM entries ORDER BY date DESC LIMIT 10');
  await c.query('COMMIT');
  c.release();
  const p = plan.rows[0]['QUERY PLAN'][0].Plan;
  const node = JSON.stringify(p).match(/"Node Type":"([^"]+)"/g).join(' ');
  const scanned = JSON.stringify(p).match(/"Actual Rows":(\d+)/g);
  console.log(`  plan: ${node}`);
  console.log(`  index used: ${JSON.stringify(p).includes('entries_tenant_date') ? 'entries_tenant_date (tenant_id leading)' : 'NOT the tenant index'}`);
  console.log(`  actual rows at each node: ${scanned ? scanned.join(' ') : 'n/a'}`);

  // Fail-closed: a connection that never binds.
  const unbound = await pool.query('SELECT count(*)::int n FROM entries');
  console.log(`  UNBOUND connection, no predicate: ${unbound.rows[0].n} rows returned ` +
    `(Mongo discriminator equivalent returned all ${TENANTS * N_ENTRIES})`);

  // Same query as the owner, for the contrast that matters.
  const asOwner = await ownerPool.query('SELECT count(*)::int n FROM entries');
  console.log(`  same query as SUPERUSER (RLS not enforced): ${asOwner.rows[0].n} rows`);

  const out = { rlsRead, explicit, window576,
    usesTenantIndex: JSON.stringify(p).includes('entries_tenant_date'),
    unboundRows: unbound.rows[0].n, superuserRows: asOwner.rows[0].n, planNodes: node };
  await pool.end();
  return out;
}

// ---------------------------------------------------------------- arm: notify

async function armNotify (pool) {
  console.log('\n--- LISTEN/NOTIFY: throughput, latency, and the disconnect test ---');
  const listener = new Client({ connectionString: PG_URL });
  await listener.connect();
  await listener.query('LISTEN entries_changed');

  let received = 0;
  const lat = [];
  listener.on('notification', (msg) => {
    received++;
    try { lat.push(Date.now() - JSON.parse(msg.payload).sentAt); } catch (e) { /* seed rows */ }
  });

  // Throughput and latency with the listener connected.
  const N = 500;
  await pool.query(`CREATE OR REPLACE FUNCTION notify_entry() RETURNS trigger AS $$
    BEGIN PERFORM pg_notify('entries_changed',
      json_build_object('tenant',NEW.tenant_id,'date',NEW.date,
        'sentAt',(extract(epoch from clock_timestamp())*1000)::bigint)::text);
    RETURN NEW; END; $$ LANGUAGE plpgsql;`);

  const t0 = Date.now();
  for (let i = 0; i < N; i++) {
    await pool.query('INSERT INTO entries (tenant_id,date,sgv,type) VALUES ($1,$2,$3,$4)',
      [tenantUuid(i % TENANTS), Date.now(), 120, 'sgv']);
  }
  await sleep(1500);
  const elapsed = Date.now() - t0;
  const connected = received;
  const l = lat.length ? stats(lat) : { p50: null, p99: null };
  console.log(`  connected:    ${connected}/${N} delivered, ${(N / (elapsed / 1000)).toFixed(0)} inserts/s, ` +
    `delivery latency ${l.p50} ms p50 / ${l.p99} p99`);

  // THE TEST THAT MATTERS. Drop the listener, write, reconnect, re-LISTEN.
  await listener.end();
  const M = 200;
  for (let i = 0; i < M; i++) {
    await pool.query('INSERT INTO entries (tenant_id,date,sgv,type) VALUES ($1,$2,$3,$4)',
      [tenantUuid(i % TENANTS), Date.now(), 121, 'sgv']);
  }
  const listener2 = new Client({ connectionString: PG_URL });
  await listener2.connect();
  let afterReconnect = 0;
  listener2.on('notification', () => afterReconnect++);
  await listener2.query('LISTEN entries_changed');
  await sleep(1500);
  console.log(`  DISCONNECT TEST: ${M} rows written while the listener was down`);
  console.log(`                   ${afterReconnect}/${M} delivered after reconnect  <-- ${afterReconnect === 0 ? 'ALL LOST' : 'some arrived'}`);
  await listener2.end();

  return { sent: N, deliveredConnected: connected, insertsPerS: +(N / (elapsed / 1000)).toFixed(0),
    latency: l, writtenWhileDown: M, deliveredAfterReconnect: afterReconnect };
}

// ---------------------------------------------------------------- arm: slot

async function armSlot (pool) {
  console.log('\n--- logical replication slot: the same disconnect test, plus WAL retention ---');
  await pool.query(`SELECT pg_drop_replication_slot($1) FROM pg_replication_slots WHERE slot_name=$1`, [SLOT])
    .catch(() => {});
  await pool.query(`SELECT pg_create_logical_replication_slot($1, 'test_decoding')`, [SLOT]);
  console.log(`  slot '${SLOT}' created (test_decoding)`);

  // There is no consumer at all — the slot is just a position in the WAL.
  const M = 200;
  for (let i = 0; i < M; i++) {
    await pool.query('INSERT INTO entries (tenant_id,date,sgv,type) VALUES ($1,$2,$3,$4)',
      [tenantUuid(i % TENANTS), Date.now(), 122, 'sgv']);
  }
  const lag1 = await pool.query(
    `SELECT pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) retained
     FROM pg_replication_slots WHERE slot_name=$1`, [SLOT]);
  console.log(`  ${M} rows written with NO consumer running; WAL retained: ${lag1.rows[0].retained}`);

  // Now consume. pg_logical_slot_get_changes advances the slot, which is what makes
  // this resumable rather than fire-and-forget.
  const got = await pool.query(
    `SELECT count(*)::int n FROM pg_logical_slot_get_changes($1, NULL, NULL) WHERE data LIKE 'table public.entries: INSERT%'`,
    [SLOT]);
  console.log(`  DISCONNECT TEST: ${got.rows[0].n}/${M} INSERT changes delivered after the consumer arrived` +
    `  <-- ${got.rows[0].n >= M ? 'NOTHING LOST' : 'incomplete'}`);

  // Re-consuming must NOT replay: the slot advanced.
  const again = await pool.query(
    `SELECT count(*)::int n FROM pg_logical_slot_get_changes($1, NULL, NULL)`, [SLOT]);
  console.log(`  re-consume immediately after: ${again.rows[0].n} changes (slot advanced, no replay)`);

  // The cost of the mechanism: an abandoned slot pins WAL forever.
  const K = 400;
  for (let i = 0; i < K; i++) {
    await pool.query('INSERT INTO entries (tenant_id,date,sgv,type) VALUES ($1,$2,$3,$4)',
      [tenantUuid(i % TENANTS), Date.now(), 123, 'sgv']);
  }
  const lag2 = await pool.query(
    `SELECT pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) retained,
            pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint bytes
     FROM pg_replication_slots WHERE slot_name=$1`, [SLOT]);
  const perRow = +lag2.rows[0].bytes / K;
  console.log(`  abandoned slot: ${K} more rows -> ${lag2.rows[0].retained} WAL pinned ` +
    `(~${perRow.toFixed(0)} bytes/row)`);
  console.log(`  at 10,000 tenants x 1 write/5 min = 33 rows/s, an abandoned slot pins ` +
    `~${((perRow * 33 * 3600) / 1073741824).toFixed(2)} GB/hour`);

  await pool.query(`SELECT pg_drop_replication_slot($1)`, [SLOT]).catch(() => {});
  return { writtenWhileDown: M, deliveredAfterConsumerArrived: got.rows[0].n,
    replayOnReconsume: again.rows[0].n, walBytesPerRow: +perRow.toFixed(0),
    abandonedGbPerHourAt33Rps: +((perRow * 33 * 3600) / 1073741824).toFixed(2) };
}

// ---------------------------------------------------------------- arm: poll

async function armPoll (pool) {
  console.log('\n--- the aggregate "which tenants are due" poll ---');
  // This is NOT today's per-tenant poll. It is ONE query returning only the tenants
  // whose newest reading is later than their last evaluation.
  const sql = `
    SELECT e.tenant_id, max(e.date) AS latest
    FROM entries e
    JOIN eval_state s ON s.tenant_id = e.tenant_id
    WHERE e.date > s.last_evaluated
    GROUP BY e.tenant_id`;

  async function timeIt (label, q, params, iters) {
    for (let i = 0; i < 5; i++) await pool.query(q, params);
    const w = [];
    let n = 0;
    for (let i = 0; i < iters; i++) {
      const s = process.hrtime.bigint();
      const r = await pool.query(q, params);
      w.push(Number(process.hrtime.bigint() - s) / 1e6);
      n = r.rowCount;
    }
    const st = stats(w);
    console.log(`  ${label.padEnd(50)} ${st.p50.toFixed(2)} ms p50 / ${st.p99.toFixed(2)} p99, ${n} tenants due`);
    return { ...st, due: n };
  }

  // Everything is due: the pathological case, watermarks all at 0.
  const allDue = await timeIt('all tenants due (watermarks at 0)', sql, [], 20);

  // Realistic: catch the watermarks up, then only recent writers are due.
  await pool.query(`UPDATE eval_state s SET last_evaluated =
    COALESCE((SELECT max(date) FROM entries e WHERE e.tenant_id=s.tenant_id), 0)`);
  const fewDue = await timeIt('steady state (watermarks current)', sql, [], 20);

  // The bounded variant the evaluator would actually run: only look at rows written
  // since the last sweep, which an index on date makes cheap.
  const windowed = `
    SELECT e.tenant_id, max(e.date) AS latest
    FROM entries e JOIN eval_state s ON s.tenant_id = e.tenant_id
    WHERE e.date > $1 AND e.date > s.last_evaluated
    GROUP BY e.tenant_id`;
  const bounded = await timeIt('bounded by date index (last 10 min)', windowed,
    [Date.now() - 600000], 20);

  return { allDue, fewDue, bounded };
}

// ---------------------------------------------------------------- main

async function main () {
  const arm = process.argv[2] || 'all';
  const pool = new Pool({ connectionString: PG_URL, max: 20 });
  const v = await pool.query('show server_version');
  console.log(`postgres ${v.rows[0].server_version} at ${PG_URL.replace(/:[^:@]*@/, ':***@')}\n`);

  const out = { date: new Date().toISOString(), pg: v.rows[0].server_version, tenants: TENANTS };
  if (arm === 'all' || arm === 'setup') out.setup = await setup(pool);
  if (arm === 'all' || arm === 'rls') out.rls = await armRls(pool);
  if (arm === 'all' || arm === 'notify') out.notify = await armNotify(pool);
  if (arm === 'all' || arm === 'slot') out.slot = await armSlot(pool);
  if (arm === 'all' || arm === 'poll') out.poll = await armPoll(pool);

  const dest = path.join(__dirname, '..', 'results', 'exp-mt-057.json');
  fs.writeFileSync(dest, JSON.stringify(out, null, 2));
  console.log(`\nresults -> ${path.relative(process.cwd(), dest)}`);
  await pool.end();
}

main().catch(e => { console.error(e); process.exit(1); });
