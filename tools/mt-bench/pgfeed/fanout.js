// EXP-MT-058 — how a change reaches the subscribers of one tenant
//
// EXP-MT-057 settled how ns-evaluator LEARNS about a change. It did not touch the
// hop after that: a change for tenant X has to reach the sockets subscribed to
// tenant X, which are held by one of N ns-realtime processes, and the process that
// learns about the change is not necessarily the one holding the socket.
//
// The design question underneath: is a Postgres primitive enough, or does this hop
// need its own stateful routing (tenant->process affinity, a Redis adapter, a
// per-tenant cursor)?
//
// The asymmetry that makes this tractable, and which this script is built around:
//
//   ns-evaluator  losing a change = a missed hypo alarm.    Needs the slot.
//   ns-realtime   losing a dataUpdate = a browser is stale
//                 until the next reading, and re-syncs on
//                 reconnect anyway.                          Can tolerate loss.
//
// So the two hops can use different mechanisms, and the cheap lossy one is
// admissible exactly where correctness does not depend on it.
//
// Arms:
//   fanout   — M concurrent LISTEN connections: does every listener get every
//              event, and what does latency do as M grows?
//   payload  — does a realistic dataUpdate delta fit NOTIFY's 8000-byte cap?
//   channels — LISTEN on a channel per tenant: does Postgres do the filtering, and
//              how many channels can one connection hold?
//   queue    — THE HAZARD. A stuck listener cannot be disconnected by the server.
//              Its un-consumed notifications pin the 8 GB SLRU queue. Measure
//              whether a stuck ns-realtime can degrade or block INGEST.
//
// Usage:
//   node fanout.js [arm] [listeners]
//
// LIMITS: one container, loopback, laptop. As everywhere in this harness, the
// SEMANTICS transfer (what is delivered, what blocks, what filters) far better
// than the timings.

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

const LISTENERS = parseInt(process.argv[3], 10) || 32;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const stats = (a) => {
  const s = [...a].sort((x, y) => x - y);
  return { p50: +s[Math.floor(s.length * 0.5)].toFixed(2),
    p99: +s[Math.floor(s.length * 0.99)].toFixed(2),
    max: +s[s.length - 1].toFixed(2) };
};

// A realistic dataUpdate delta as lib/server/websocket.js:150 emits: one new SGV
// plus one devicestatus carrying Loop's 72-point prediction array. This is the
// payload the realtime hop would have to carry if NOTIFY carried data rather than
// an identifier.
function realisticDelta () {
  const now = Date.now();
  const iso = new Date(now).toISOString();
  return {
    delta: true, lastUpdated: now,
    sgvs: [{ _id: 'a'.repeat(24), mgdl: 124, mills: now, device: 'xDrip-DexcomG6',
      direction: 'Flat', type: 'sgv', filtered: 180000, unfiltered: 180000, rssi: 100, noise: 1 }],
    devicestatus: [{ _id: 'b'.repeat(24), device: 'loop://iPhone', created_at: iso, mills: now,
      loop: { name: 'Loop', version: '3.4', timestamp: iso,
        iob: { timestamp: iso, iob: 1.23 }, cob: { timestamp: iso, cob: 12 },
        predicted: { startDate: iso, values: Array.from({ length: 72 }, (_, k) => 90 + (k % 60)) },
        recommendedBolus: 0,
        enacted: { rate: 0.75, duration: 30, timestamp: iso, received: true } },
      uploader: { battery: 88 } }]
  };
}

async function setup (pool) {
  await pool.query(`
    DROP TABLE IF EXISTS fanout_events CASCADE;
    CREATE TABLE fanout_events (
      id bigserial PRIMARY KEY, tenant_id int NOT NULL,
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(), payload jsonb);
    CREATE INDEX fanout_tenant ON fanout_events (tenant_id, id DESC);`);
}

// ---------------------------------------------------------------- arm: fanout
//
// The multi-process question. N ns-realtime processes each LISTEN on one shared
// channel; a change is NOTIFYed once. Does every process see it? If so, no
// tenant->process affinity is needed: each process emits to whichever of its own
// local socket rooms match, and ignores the rest.

async function armFanout (pool, M) {
  console.log(`\n--- fan-out: ${M} concurrent LISTEN connections on one channel ---`);
  const listeners = [];
  const counts = new Array(M).fill(0);
  const lat = [];

  for (let i = 0; i < M; i++) {
    const c = new Client({ connectionString: PG_URL });
    await c.connect();
    c.on('notification', (msg) => {
      counts[i]++;
      try { lat.push(Date.now() - JSON.parse(msg.payload).t); } catch (e) {}
    });
    await c.query('LISTEN tenant_changes');
    listeners.push(c);
  }

  const N = 200;
  const t0 = Date.now();
  for (let i = 0; i < N; i++) {
    await pool.query(`SELECT pg_notify('tenant_changes', $1)`,
      [JSON.stringify({ tenant: i % 400, t: Date.now() })]);
  }
  const emitMs = Date.now() - t0;
  await sleep(2000);

  const delivered = counts.reduce((a, b) => a + b, 0);
  const complete = counts.filter(c => c >= N).length;
  const l = lat.length ? stats(lat) : { p50: null, p99: null, max: null };
  console.log(`  ${N} NOTIFYs -> ${delivered} deliveries across ${M} listeners ` +
    `(expected ${N * M}, ${complete}/${M} listeners complete)`);
  console.log(`  notify cost ${(emitMs / N).toFixed(3)} ms/event at the writer; ` +
    `delivery latency ${l.p50} ms p50 / ${l.p99} p99 / ${l.max} max`);

  for (const c of listeners) await c.end();
  return { listeners: M, sent: N, delivered, listenersComplete: complete,
    writerMsPerEvent: +(emitMs / N).toFixed(3), latency: l };
}

// ---------------------------------------------------------------- arm: payload

async function armPayload (pool) {
  console.log('\n--- payload: does a real dataUpdate delta fit NOTIFY? ---');
  const delta = realisticDelta();
  const json = JSON.stringify(delta);
  console.log(`  realistic dataUpdate delta (1 SGV + 1 Loop devicestatus): ${json.length} bytes`);
  console.log(`  NOTIFY payload limit: 8000 bytes  -> ${json.length < 8000 ? 'FITS' : 'DOES NOT FIT'}`);

  let maxOk = 0, firstFail = null;
  for (const size of [1000, 4000, 7900, 8000, 8100, 16000]) {
    try {
      await pool.query(`SELECT pg_notify('sizetest', $1)`, ['x'.repeat(size)]);
      maxOk = size;
    } catch (e) {
      if (!firstFail) firstFail = { size, message: e.message.split('\n')[0] };
    }
  }
  console.log(`  largest payload accepted: ${maxOk} bytes`);
  if (firstFail) console.log(`  first rejection at ${firstFail.size}: ${firstFail.message}`);

  // The identifier-only alternative: NOTIFY carries a row id, the listener reads
  // the row. Costs one indexed query per event on the realtime hop.
  await pool.query(`INSERT INTO fanout_events (tenant_id, payload) VALUES (1, $1)`, [json]);
  const t0 = process.hrtime.bigint();
  const iters = 200;
  for (let i = 0; i < iters; i++) {
    await pool.query('SELECT payload FROM fanout_events WHERE tenant_id=$1 ORDER BY id DESC LIMIT 1', [1]);
  }
  const perRead = Number(process.hrtime.bigint() - t0) / 1e6 / iters;
  console.log(`  identifier-only alternative: ${perRead.toFixed(3)} ms per lookup to fetch the row`);

  return { deltaBytes: json.length, fits: json.length < 8000, maxAccepted: maxOk,
    firstFail, rowLookupMs: +perRead.toFixed(3) };
}

// ---------------------------------------------------------------- arm: channels
//
// Could Postgres do the per-tenant filtering itself? LISTEN takes a channel name,
// so a channel per tenant would mean the server only delivers what a given process
// cares about. Whether that is usable depends on how many channels one connection
// can hold and what that costs.

async function armChannels (pool) {
  console.log('\n--- channel-per-tenant: can Postgres do the routing? ---');
  const c = new Client({ connectionString: PG_URL });
  await c.connect();
  let got = 0;
  c.on('notification', () => got++);

  const results = [];
  let subscribed = 0;
  for (const target of [100, 1000, 5000, 10000]) {
    const t0 = Date.now();
    try {
      for (; subscribed < target; subscribed++) {
        await c.query(`LISTEN "tenant_${subscribed}"`);
      }
    } catch (e) {
      console.log(`  failed at ${subscribed} channels: ${e.message.split('\n')[0]}`);
      break;
    }
    const ms = Date.now() - t0;

    // Does a notify on one of those channels arrive, and only that one?
    got = 0;
    await pool.query(`SELECT pg_notify('tenant_${target - 1}', 'x')`);
    await pool.query(`SELECT pg_notify('tenant_999999', 'x')`);  // not subscribed
    await sleep(400);
    const mem = await pool.query(
      `SELECT pg_size_pretty(sum(pg_column_size(l.*))::bigint) sz FROM pg_listening_channels() l`)
      .catch(() => ({ rows: [{ sz: 'n/a' }] }));
    results.push({ channels: subscribed, subscribeMsTotal: ms, delivered: got });
    console.log(`  ${String(subscribed).padStart(6)} channels subscribed  ` +
      `(${(ms / (target - results.reduce((a, r) => a + 0, 0))).toFixed(2)} ms/channel batch)  ` +
      `targeted notify delivered: ${got} (1 expected, unsubscribed channel filtered out)`);
  }
  await c.end();
  return results;
}

// ---------------------------------------------------------------- arm: queue
//
// THE HAZARD. A LISTENing session that stops consuming cannot be cleaned up by the
// server: its notifications are retained in a shared 8 GB SLRU queue until it
// reads them or disconnects. The question for the component design is whether one
// stuck ns-realtime process can degrade or stop INGEST — which would make the
// cheap lossy fan-out hop a liability on the write path.

async function armQueue (pool) {
  console.log('\n--- the hazard: can a stuck listener affect ingest? ---');

  // A listener that connects, LISTENs, and then never processes. Blocking the
  // event loop of a separate connection is the closest honest simulation of a
  // wedged process that still holds its socket open.
  const stuck = new Client({ connectionString: PG_URL });
  await stuck.connect();
  await stuck.query('LISTEN tenant_changes');
  // Detach the connection's stream so incoming notifications are never read from
  // the socket: the server-side queue cannot advance for this session.
  stuck.connection.stream.pause();
  console.log('  one listener is now LISTENing and not reading its socket');

  const before = await pool.query('SELECT pg_notification_queue_usage() u');
  const PAYLOAD = 'x'.repeat(4000);
  const BATCH = 20000;
  const t0 = Date.now();
  let sent = 0, failed = null;
  const writeLat = [];
  try {
    for (; sent < BATCH; sent++) {
      const s = process.hrtime.bigint();
      await pool.query(`SELECT pg_notify('tenant_changes', $1)`, [PAYLOAD]);
      writeLat.push(Number(process.hrtime.bigint() - s) / 1e6);
      if (sent % 5000 === 0 && sent > 0) {
        const u = await pool.query('SELECT pg_notification_queue_usage() u');
        console.log(`    ${sent} notifies, queue ${(u.rows[0].u * 100).toFixed(4)}% full, ` +
          `write p50 ${stats(writeLat).p50} ms`);
      }
    }
  } catch (e) { failed = e.message.split('\n')[0]; }
  const elapsed = Date.now() - t0;
  const after = await pool.query('SELECT pg_notification_queue_usage() u');

  console.log(`  ${sent} notifies in ${(elapsed / 1000).toFixed(1)}s with a stuck listener`);
  console.log(`  queue usage ${(before.rows[0].u * 100).toFixed(4)}% -> ${(after.rows[0].u * 100).toFixed(4)}%`);
  console.log(`  write latency ${JSON.stringify(stats(writeLat))}`);
  if (failed) console.log(`  WRITES FAILED: ${failed}`);

  // Does an ordinary INSERT (the ingest path) still work?
  const ins = process.hrtime.bigint();
  await pool.query('INSERT INTO fanout_events (tenant_id, payload) VALUES (99, $1)', ['{}']);
  const insMs = Number(process.hrtime.bigint() - ins) / 1e6;
  console.log(`  ordinary INSERT with the queue in this state: ${insMs.toFixed(3)} ms — ingest ${insMs < 50 ? 'UNAFFECTED' : 'DEGRADED'}`);

  // Extrapolate: how long could a stuck listener be tolerated?
  const perNotify = (after.rows[0].u - before.rows[0].u) / Math.max(sent, 1);
  const toFull = perNotify > 0 ? Math.floor(1 / perNotify) : null;
  if (toFull) {
    console.log(`  ~${(perNotify * 100).toExponential(2)}% of the queue per notify ` +
      `-> ~${toFull.toLocaleString()} notifies to fill it`);
    console.log(`  at 33 changes/s (10,000 tenants), a stuck listener has ` +
      `~${(toFull / 33 / 3600).toFixed(1)} hours before the queue is full`);
  }

  await stuck.connection.stream.resume();
  await stuck.end().catch(() => {});
  return { sent, failed, queueBefore: before.rows[0].u, queueAfter: after.rows[0].u,
    writeLatency: stats(writeLat), insertMs: +insMs.toFixed(3),
    notifiesToFill: toFull, hoursAt33Rps: toFull ? +(toFull / 33 / 3600).toFixed(1) : null };
}

// ---------------------------------------------------------------- main

async function main () {
  const arm = process.argv[2] || 'all';
  const pool = new Pool({ connectionString: PG_URL, max: 10 });
  console.log(`postgres ${(await pool.query('show server_version')).rows[0].server_version}`);
  await setup(pool);

  const out = { date: new Date().toISOString(), listeners: LISTENERS };
  if (arm === 'all' || arm === 'fanout') out.fanout = await armFanout(pool, LISTENERS);
  if (arm === 'all' || arm === 'payload') out.payload = await armPayload(pool);
  if (arm === 'all' || arm === 'channels') out.channels = await armChannels(pool);
  if (arm === 'all' || arm === 'queue') out.queue = await armQueue(pool);

  const dest = path.join(__dirname, '..', 'results', 'exp-mt-058.json');
  fs.writeFileSync(dest, JSON.stringify(out, null, 2));
  console.log(`\nresults -> ${path.relative(process.cwd(), dest)}`);
  await pool.end();
}

main().catch(e => { console.error(e); process.exit(1); });
