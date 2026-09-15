// EXP-MT-059 — is LISTEN/NOTIFY built to be used this way, or is this an abuse?
//
// EXP-MT-058 showed NOTIFY does the fan-out hop correctly at 32 listeners. That is
// not the same as showing it SCALES, and the mechanism has three documented
// properties that should make anyone nervous about leaning on it:
//
//   1. NOTIFY serialises. Appending to the notification queue takes an exclusive
//      lock (NotifyQueueLock in src/backend/commands/async.c), so ALL notify
//      traffic in the cluster passes through one lock.
//   2. Delivery is signal-based and O(listeners). At commit, the notifying backend
//      walks every listening backend and signals it (SignalBackends()).
//   3. A listener is a whole Postgres backend. LISTEN is session state, so every
//      listening process consumes a connection out of max_connections, plus a
//      backend's memory.
//
// Each of those is a real ceiling. Whether any of them BINDS depends entirely on
// how many listeners this design actually has — and the answer from EXP-MT-045a
// and the cost model is a handful of ns-realtime processes, not thousands of
// subscribers. The subscribers are websockets; only the PROCESSES listen.
//
// So this measures the curve rather than asserting the conclusion:
//
//   scale     — NOTIFY throughput at the writer as listener count grows
//   ceiling   — raw NOTIFY/s with the writer unconstrained, per-transaction and
//               batched, to find the serialisation limit
//   bouncer   — THE CONFLICT. §6.7 says pgbouncer in transaction mode may be
//               needed for the api tier's pool multiplexing. LISTEN is session
//               state. Do they coexist?
//
// Usage:
//   node notify-scale.js [arm]
//
// LIMITS: one container, loopback, laptop, 16 cores. Absolute throughput will be
// wrong for real hardware. The SHAPE of the curve — flat, linear, or worse in
// listener count — is what transfers, and it is what decides the question.

'use strict';

const fs = require('fs');
const path = require('path');
const { Client, Pool } = require('pg');

const PG_URL = process.env.PG_URL || 'postgres://postgres:poc@127.0.0.1:15433/postgres';
const BOUNCER_URL = process.env.BOUNCER_URL || 'postgres://postgres:poc@127.0.0.1:16432/postgres';
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// The required rate, from the cost model, so every number has something to be
// compared against rather than admired in isolation.
const REQUIRED_CHANGES_PER_S = 33;    // 10,000 tenants, one upload per 5 min
const REQUIRED_LISTENERS = 5;         // a handful of ns-realtime processes

// ---------------------------------------------------------------- arm: scale

async function armScale () {
  console.log('\n--- NOTIFY throughput as listener count grows ---');
  console.log('    (each listener is a full Postgres backend; delivery is O(listeners))\n');
  const pool = new Pool({ connectionString: PG_URL, max: 4 });
  const rows = [];
  const listeners = [];
  let attached = 0;

  for (const target of [1, 8, 32, 128, 256]) {
    while (attached < target) {
      const c = new Client({ connectionString: PG_URL });
      await c.connect();
      c.on('notification', () => {});
      await c.query('LISTEN bus');
      listeners.push(c);
      attached++;
    }
    await sleep(200);

    // One NOTIFY per transaction — the realistic shape, since each change is its
    // own commit.
    const N = 2000;
    const lat = [];
    const t0 = process.hrtime.bigint();
    for (let i = 0; i < N; i++) {
      const s = process.hrtime.bigint();
      await pool.query(`SELECT pg_notify('bus', $1)`, ['{"t":1}']);
      lat.push(Number(process.hrtime.bigint() - s) / 1e6);
    }
    const elapsed = Number(process.hrtime.bigint() - t0) / 1e6;
    lat.sort((a, b) => a - b);
    const row = { listeners: attached, notifyPerS: +(N / (elapsed / 1000)).toFixed(0),
      p50: +lat[N / 2].toFixed(3), p99: +lat[Math.floor(N * 0.99)].toFixed(3) };
    rows.push(row);
    console.log(`  ${String(attached).padStart(4)} listeners   ${String(row.notifyPerS).padStart(6)} NOTIFY/s   ` +
      `writer ${row.p50.toFixed(3)} ms p50 / ${row.p99.toFixed(3)} p99   ` +
      `headroom vs required ${(row.notifyPerS / REQUIRED_CHANGES_PER_S).toFixed(0)}x`);
  }

  for (const c of listeners) await c.end().catch(() => {});
  await pool.end();

  const first = rows[0], last = rows[rows.length - 1];
  const degradation = first.notifyPerS / last.notifyPerS;
  console.log(`\n  throughput ${first.notifyPerS} -> ${last.notifyPerS} NOTIFY/s from ` +
    `${first.listeners} to ${last.listeners} listeners (${degradation.toFixed(2)}x slower)`);
  console.log(`  if delivery were free this would be flat; if strictly O(listeners) it would be ` +
    `${(last.listeners / first.listeners).toFixed(0)}x slower`);
  return { rows, degradationFactor: +degradation.toFixed(2) };
}

// ---------------------------------------------------------------- arm: ceiling

async function armCeiling () {
  console.log('\n--- raw NOTIFY ceiling (the serialisation limit) ---');
  const pool = new Pool({ connectionString: PG_URL, max: 32 });
  const listener = new Client({ connectionString: PG_URL });
  await listener.connect();
  let got = 0;
  listener.on('notification', () => got++);
  await listener.query('LISTEN bus');

  const out = {};

  // Sequential, one per transaction.
  {
    const N = 3000;
    const t0 = Date.now();
    for (let i = 0; i < N; i++) await pool.query(`SELECT pg_notify('bus','x')`);
    out.sequential = +(N / ((Date.now() - t0) / 1000)).toFixed(0);
    console.log(`  sequential, 1 per txn        ${String(out.sequential).padStart(7)} NOTIFY/s`);
  }

  // Concurrent writers — does the exclusive queue lock cap aggregate throughput?
  for (const conc of [8, 32]) {
    const N = 4000;
    const per = Math.floor(N / conc);
    const t0 = Date.now();
    await Promise.all(Array.from({ length: conc }, async () => {
      for (let i = 0; i < per; i++) await pool.query(`SELECT pg_notify('bus','x')`);
    }));
    const rate = +((per * conc) / ((Date.now() - t0) / 1000)).toFixed(0);
    out[`concurrent${conc}`] = rate;
    console.log(`  ${String(conc).padStart(2)} concurrent writers        ${String(rate).padStart(7)} NOTIFY/s`);
  }

  // Batched inside one transaction — duplicates collapse, distinct payloads do not.
  {
    const N = 20000;
    const t0 = Date.now();
    const c = await pool.connect();
    await c.query('BEGIN');
    for (let i = 0; i < N; i++) await c.query(`SELECT pg_notify('bus', $1)`, [String(i)]);
    await c.query('COMMIT');
    c.release();
    out.batched = +(N / ((Date.now() - t0) / 1000)).toFixed(0);
    console.log(`  batched in one txn           ${String(out.batched).padStart(7)} NOTIFY/s`);
  }

  await sleep(1500);
  await listener.end();
  console.log(`\n  required rate at 10,000 tenants: ${REQUIRED_CHANGES_PER_S} changes/s`);
  console.log(`  headroom on the SLOWEST measured path: ${(out.sequential / REQUIRED_CHANGES_PER_S).toFixed(0)}x`);
  console.log(`  tenants this would support at 1 change/5 min: ` +
    `${(out.sequential * 300).toLocaleString()}`);
  return out;
}

// ---------------------------------------------------------------- arm: bouncer
//
// The conflict §6.7 sets up and never resolves. It recommends pgbouncer in
// transaction mode so one pool serves every tenant with set_config(..., is_local).
// LISTEN is SESSION state: a transaction-pooled connection is handed to another
// client after each COMMIT, so a LISTEN registered on it is both lost and
// dangerous. Whether pgbouncer refuses, silently breaks, or works is worth
// establishing rather than assuming.

async function armBouncer () {
  console.log('\n--- pgbouncer transaction mode + LISTEN: do they coexist? ---');
  const out = {};

  // Sanity: is the bouncer reachable?
  try {
    const probe = new Client({ connectionString: BOUNCER_URL, connectionTimeoutMillis: 4000 });
    await probe.connect();
    out.mode = (await probe.query('show server_version')).rows[0].server_version;
    await probe.end();
    console.log(`  pgbouncer reachable, upstream pg ${out.mode}`);
  } catch (e) {
    console.log(`  pgbouncer not reachable (${e.message.split('\n')[0]}) — arm skipped`);
    return { skipped: true, reason: e.message.split('\n')[0] };
  }

  // Ordinary query through the bouncer: expected to work.
  try {
    const c = new Client({ connectionString: BOUNCER_URL });
    await c.connect();
    await c.query('SELECT 1');
    out.plainQuery = 'ok';
    await c.end();
    console.log('  ordinary query through transaction-mode bouncer: ok');
  } catch (e) { out.plainQuery = e.message.split('\n')[0]; console.log(`  ordinary query FAILED: ${out.plainQuery}`); }

  // LISTEN through the bouncer, then NOTIFY direct to Postgres.
  const lc = new Client({ connectionString: BOUNCER_URL });
  await lc.connect();
  let received = 0;
  lc.on('notification', () => received++);
  try {
    await lc.query('LISTEN bus');
    out.listenAccepted = true;
    console.log('  LISTEN through the bouncer: accepted (no error raised)');
  } catch (e) {
    out.listenAccepted = false;
    out.listenError = e.message.split('\n')[0];
    console.log(`  LISTEN through the bouncer: REJECTED — ${out.listenError}`);
  }

  if (out.listenAccepted) {
    const direct = new Pool({ connectionString: PG_URL, max: 2 });
    for (let i = 0; i < 50; i++) await direct.query(`SELECT pg_notify('bus','x')`);
    await sleep(2000);
    out.deliveredThroughBouncer = received;
    console.log(`  50 NOTIFYs sent direct to Postgres -> ${received} received by the bouncer-side listener`);
    console.log(`  verdict: ${received === 0 ? 'LISTEN is accepted but delivers NOTHING — silent breakage'
      : received < 50 ? 'partial delivery — worse than an error' : 'delivered'}`);
    await direct.end();
  }
  await lc.end().catch(() => {});
  return out;
}

// ---------------------------------------------------------------- main

async function main () {
  const arm = process.argv[2] || 'all';
  const out = { date: new Date().toISOString(),
    requiredChangesPerS: REQUIRED_CHANGES_PER_S, requiredListeners: REQUIRED_LISTENERS };
  if (arm === 'all' || arm === 'scale') out.scale = await armScale();
  if (arm === 'all' || arm === 'ceiling') out.ceiling = await armCeiling();
  if (arm === 'all' || arm === 'bouncer') out.bouncer = await armBouncer();

  const dest = path.join(__dirname, '..', 'results', 'exp-mt-059.json');
  fs.writeFileSync(dest, JSON.stringify(out, null, 2));
  console.log(`\nresults -> ${path.relative(process.cwd(), dest)}`);
}

main().catch(e => { console.error(e); process.exit(1); });
