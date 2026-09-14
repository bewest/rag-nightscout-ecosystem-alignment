// EXP-MT-026 — a real database in the loop
//
// Every other experiment in tools/mt-bench/ runs with no database. That was fine
// while the question was "how much CPU does the resident path burn", and it became
// the largest open risk the moment the recommendation moved to a stateless tier
// that trades resident memory for queries.
//
// THE DISTINCTION THIS SCRIPT EXISTS TO MAKE. A query costs two different things,
// and the cost model in deployment-cost.js only cares about one of them:
//
//   wall time  — how long the caller waits. Dominated by network RTT. Determines
//                request latency and how many connections a pool needs.
//   event-loop CPU — driver serialisation, BSON decode, callback dispatch. This is
//                the term that competes with the load cycle for the single thread,
//                and therefore the ONLY term that sets how many processes an
//                operator runs.
//
// deployment-cost.js guesses dbQueryCpu_ms = 0.15. Arm `cpu` measures it. If CPU
// per query is flat in RTT, then process count is RTT-insensitive and the cost
// model holds against Atlas as well as against loopback; if it is not, the whole
// stateless recommendation needs re-argued. That is the experiment.
//
// Shape under test: database-per-tenant on one cluster — §6.7's A' rung, the
// recommended next step — with the real indexedFields index set from
// lib/server/{entries,treatments,devicestatus,profile}.js. Queries are transcribed
// from lib/data/dataloader.js, not invented.
//
// Arms:
//   load      — create N tenant databases with the real index set and corpus
//   cpu       — event-loop CPU and wall time per query, by query shape
//   cycle     — the ~14 operations of one dataloader cycle (§2.3)
//   read      — the stateless /api/v1/entries read, against EXP-MT-055's cache hit
//   coldwake  — materialise a tenant's whole ddata from storage
//   loopdelay — event-loop responsiveness under concurrent queries
//
// Usage:
//   node dbloop.js load [tenants]
//   node dbloop.js all  [tenants]
//   MONGO_URL=... node dbloop.js all        (default mongodb://127.0.0.1:27099)
//
// LIMITS — read these before quoting any number. See §L in the report.
//   This is a laptop, a loopback socket and one mongod in a container. It is not
//   a hoster's cluster. What it CAN establish is the CPU-vs-wall split, the shape
//   of each query's cost, and whether the planner uses the indexes. What it CANNOT
//   establish is capacity, contention, or anything about a working set larger than
//   the page cache.

'use strict';

const path = require('path');
const fs = require('fs');
const { monitorEventLoopDelay } = require('perf_hooks');

const NS_ROOT = process.env.NS_ROOT ||
  path.resolve(__dirname, '../../externals/cgm-remote-monitor-official');
const { MongoClient } = require(path.join(NS_ROOT, 'node_modules/mongodb'));
const initDdata = require(path.join(NS_ROOT, 'lib/data/ddata'));

const MONGO_URL = process.env.MONGO_URL || 'mongodb://127.0.0.1:27099/?directConnection=true';
const DB_PREFIX = 'nsbench_t';
const TENANTS = parseInt(process.argv[3], 10) || 50;

// Retention windows from lib/server/cache.js:26-31, as document counts at the
// cadences lib/data/dataloader.js actually sees.
const N_ENTRIES = 576;       // 48 h at 5 min
const N_TREATMENTS = 600;    // 60 h, Loop/AAPS temp-basal cadence
const N_DEVICESTATUS = 576;  // 48 h at 5 min, 72-point prediction arrays

// ---------------------------------------------------------------- fixtures

let idCounter = 0;
function oid () { return (++idCounter).toString(16).padStart(24, '0'); }

function mkEntry (i, t) {
  const now = Date.now() - i * 300000;
  return { device: 'xDrip-DexcomG6', date: now, dateString: new Date(now).toISOString(),
    sgv: 70 + ((i * 7 + t * 13) % 180), delta: ((i % 21) - 10) / 5,
    direction: 'Flat', type: 'sgv', filtered: 180000, unfiltered: 180000,
    rssi: 100, noise: 1, sysTime: new Date(now).toISOString(), utcOffset: 0,
    identifier: oid() };
}
// Real sites mix ~28 event types. Six of them are what loadLatestSingle asks for,
// and they are rare, so they are seeded deliberately rather than by chance.
const SPECIAL = ['Sensor Start', 'Sensor Change', 'Sensor Stop', 'Site Change',
  'Insulin Change', 'Pump Battery Change'];
function mkTreatment (i, t) {
  const now = Date.now() - i * 600000;
  const special = i % 97 === 0 ? SPECIAL[(i / 97 | 0) % SPECIAL.length] : null;
  return { eventType: special || 'Temp Basal',
    duration: special ? 0 : 30, absolute: (i % 20) / 10, rate: 0.8,
    created_at: new Date(now).toISOString(), enteredBy: `loop://iPhone-${t}`,
    insulin: null, carbs: null, utcOffset: 0, identifier: oid() };
}
function mkDeviceStatus (i, t) {
  const now = Date.now() - i * 300000;
  const iso = new Date(now).toISOString();
  return { device: 'loop://iPhone', created_at: iso,
    loop: { name: 'Loop', version: '3.4', timestamp: iso,
      iob: { timestamp: iso, iob: (i % 50) / 10 },
      cob: { timestamp: iso, cob: 12 },
      predicted: { startDate: iso,
        values: Array.from({ length: 72 }, (_, k) => 80 + ((i + k + t) % 160)) },
      recommendedBolus: 0,
      enacted: { rate: 0.75, duration: 30, timestamp: iso, received: true } },
    uploader: { battery: 88 }, identifier: oid() };
}
function mkProfile () {
  const sched = (v) => Array.from({ length: 8 }, (_, i) => ({
    time: `${String(i * 3).padStart(2, '0')}:00`, timeAsSeconds: i * 10800, value: v + i * 0.1 }));
  return { defaultProfile: 'Default', startDate: new Date().toISOString(),
    created_at: new Date().toISOString(),
    loopSettings: { dia: 6, minimumBGGuard: 80, maximumBasalRatePerHour: 4, maximumBolus: 10 },
    store: { Default: { dia: 6, carbs_hr: 20, delay: 20, timezone: 'US/Pacific',
      carbratio: sched(10), sens: sched(50), basal: sched(0.8),
      target_low: sched(100), target_high: sched(120) } } };
}

// Transcribed from lib/server/{entries,treatments,devicestatus,profile}.js
// indexedFields. 35 secondary indexes per tenant database is the number §6.7 says
// sets the ceiling on A'; this creates them so the planner sees what it would see.
const INDEXES = {
  entries: ['date', 'type', 'sgv', 'mbg', 'sysTime', 'dateString', 'identifier',
    { type: 1, date: -1, dateString: 1 }, { date: -1, identifier: -1, created_at: -1 }],
  treatments: ['created_at', 'eventType', 'insulin', 'carbs', 'glucose', 'enteredBy',
    'boluscalc.foods._id', 'notes', 'NSCLIENT_ID', 'percent', 'absolute', 'duration',
    'identifier', { eventType: 1, duration: 1, created_at: 1 },
    { eventType: 1, created_at: -1, identifier: -1, date: -1 }],
  devicestatus: ['created_at', 'NSCLIENT_ID', { created_at: -1, identifier: -1, date: -1 }],
  profile: ['startDate', 'created_at', 'NSCLIENT_ID', { startDate: -1, _id: -1 }],
  food: ['type', 'position', 'hidden'],
  activity: ['created_at']
};

// ---------------------------------------------------------------- measurement

function stats (samples) {
  const s = [...samples].sort((a, b) => a - b);
  return { p50: +s[Math.floor(s.length * 0.5)].toFixed(4),
    p95: +s[Math.floor(s.length * 0.95)].toFixed(4),
    p99: +s[Math.floor(s.length * 0.99)].toFixed(4),
    mean: +(s.reduce((a, b) => a + b, 0) / s.length).toFixed(4) };
}

// Wall time per call, and CPU actually charged to this process across the batch.
// cpuUsage() covers the whole process, so it is only meaningful over a batch with
// nothing else running — hence sequential, and hence reported as a mean rather
// than a distribution.
async function measure (label, fn, iters) {
  for (let i = 0; i < Math.min(30, iters); i++) await fn();   // warm the planner and the pool
  const wall = [];
  const cpu0 = process.cpuUsage();
  const t0 = process.hrtime.bigint();
  for (let i = 0; i < iters; i++) {
    const s = process.hrtime.bigint();
    await fn();
    wall.push(Number(process.hrtime.bigint() - s) / 1e6);
  }
  const elapsed = Number(process.hrtime.bigint() - t0) / 1e6;
  const cpu = process.cpuUsage(cpu0);
  const cpuMs = (cpu.user + cpu.system) / 1000 / iters;
  const w = stats(wall);
  const row = { label, iters, wall: w, cpuPerOp_ms: +cpuMs.toFixed(4),
    cpuShare: +((cpuMs / w.mean) * 100).toFixed(1), elapsed_ms: +elapsed.toFixed(1) };
  console.log(`  ${label.padEnd(44)} wall ${w.p50.toFixed(3).padStart(7)} p50 /${w.p99.toFixed(3).padStart(8)} p99   cpu ${cpuMs.toFixed(3).padStart(6)} ms  (${row.cpuShare}% of wall)`);
  return row;
}

// ---------------------------------------------------------------- arms

async function armLoad (client, n) {
  console.log(`\nloading ${n} tenant databases, ${N_ENTRIES}+${N_TREATMENTS}+${N_DEVICESTATUS} docs each`);
  const t0 = Date.now();
  for (let t = 0; t < n; t++) {
    const db = client.db(`${DB_PREFIX}${t}`);
    await Promise.all([
      db.collection('entries').deleteMany({}),
      db.collection('treatments').deleteMany({}),
      db.collection('devicestatus').deleteMany({}),
      db.collection('profile').deleteMany({})
    ]);
    await db.collection('entries').insertMany(
      Array.from({ length: N_ENTRIES }, (_, i) => mkEntry(i, t)), { ordered: false });
    await db.collection('treatments').insertMany(
      Array.from({ length: N_TREATMENTS }, (_, i) => mkTreatment(i, t)), { ordered: false });
    await db.collection('devicestatus').insertMany(
      Array.from({ length: N_DEVICESTATUS }, (_, i) => mkDeviceStatus(i, t)), { ordered: false });
    await db.collection('profile').insertOne(mkProfile());
    for (const [col, specs] of Object.entries(INDEXES)) {
      for (const spec of specs) {
        await db.collection(col).createIndex(typeof spec === 'string' ? { [spec]: 1 } : spec);
      }
    }
    if ((t + 1) % 10 === 0) process.stdout.write(`  ${t + 1}/${n}\r`);
  }
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  const st = await client.db(`${DB_PREFIX}0`).stats();
  console.log(`  done in ${secs}s — per-tenant db: ${(st.dataSize / 1048576).toFixed(1)} MB data, ` +
    `${(st.indexSize / 1048576).toFixed(1)} MB indexes, ${st.indexes} indexes across ${st.collections} collections`);
  return { tenants: n, loadSeconds: +secs, perTenantDataMb: +(st.dataSize / 1048576).toFixed(1),
    perTenantIndexMb: +(st.indexSize / 1048576).toFixed(1), indexes: st.indexes };
}

// The query shapes dataloader actually issues, isolated so each one's cost is
// attributable. Names match the loader function that issues them.
async function armCpu (client, n) {
  console.log(`\n--- per-query cost by shape (round-robin over ${n} tenants) ---`);
  let k = 0;
  const db = () => client.db(`${DB_PREFIX}${(k++) % n}`);
  const since = new Date(Date.now() - 15 * 60000).toISOString();
  const rows = [];

  rows.push(await measure('findOne latest entry (date desc, count 1)',
    () => db().collection('entries').find({}).sort({ date: -1 }).limit(1).toArray(), 300));
  rows.push(await measure('entries ?count=10 (the v1 REST read)',
    () => db().collection('entries').find({}).sort({ date: -1 }).limit(10).toArray(), 300));
  rows.push(await measure('entries ?count=576 (full 48 h window)',
    () => db().collection('entries').find({}).sort({ date: -1 }).limit(576).toArray(), 200));
  rows.push(await measure('entries incremental (15 min window)',
    () => db().collection('entries').find({ date: { $gte: Date.now() - 900000 } })
      .sort({ date: -1 }).toArray(), 300));
  rows.push(await measure('treatments 60 h window',
    () => db().collection('treatments').find({ created_at: { $gte: since } })
      .sort({ created_at: -1 }).toArray(), 200));
  rows.push(await measure('loadLatestSingle (eventType, count 1)',
    () => db().collection('treatments')
      .find({ eventType: { $eq: 'Site Change' } }).sort({ created_at: -1 }).limit(1).toArray(), 300));
  rows.push(await measure('devicestatus latest (72-pt prediction)',
    () => db().collection('devicestatus').find({}).sort({ created_at: -1 }).limit(1).toArray(), 300));
  rows.push(await measure('devicestatus 48 h window',
    () => db().collection('devicestatus').find({}).sort({ created_at: -1 }).limit(576).toArray(), 100));
  rows.push(await measure('profile.last()',
    () => db().collection('profile').find({}).sort({ startDate: -1 }).limit(1).toArray(), 300));
  return rows;
}

// One dataloader cycle as lib/data/dataloader.js performs it: nine loaders in
// parallel, expanding to ~14 operations (§2.3).
async function armCycle (client, n) {
  console.log(`\n--- one dataloader cycle, ~14 operations in parallel (§2.3) ---`);
  let k = 0;
  const since = new Date(Date.now() - 15 * 60000).toISOString();

  async function cycle () {
    const db = client.db(`${DB_PREFIX}${(k++) % n}`);
    await Promise.all([
      db.collection('entries').find({ date: { $gte: Date.now() - 900000 } }).sort({ date: -1 }).toArray(),
      db.collection('treatments').find({ created_at: { $gte: since } }).sort({ created_at: -1 }).toArray(),
      db.collection('treatments').find({ eventType: { $eq: 'Profile Switch' } }).sort({ created_at: -1 }).limit(1).toArray(),
      ...SPECIAL.map(t => db.collection('treatments')
        .find({ eventType: { $eq: t } }).sort({ created_at: -1 }).limit(1).toArray()),
      db.collection('profile').find({}).sort({ startDate: -1 }).limit(1).toArray(),
      db.collection('food').find({}).toArray(),
      db.collection('devicestatus').find({ created_at: { $gte: since } }).sort({ created_at: -1 }).toArray(),
      db.collection('activity').find({}).toArray(),
      client.db(`${DB_PREFIX}${k % n}`).stats()
    ]);
  }
  return [await measure('incremental cycle, 14 ops in parallel', cycle, 200)];
}

// Materialise a tenant's whole world from storage, then run the real ddata path
// over it — the cold-wake question EXP-MT-026 was originally written to answer.
async function armColdWake (client, n) {
  console.log(`\n--- cold wake: full ddata materialised from storage ---`);
  let k = 0;
  const rows = [];

  async function fetchAll () {
    const db = client.db(`${DB_PREFIX}${(k++) % n}`);
    const [entries, treatments, devicestatus, profiles] = await Promise.all([
      db.collection('entries').find({}).sort({ date: -1 }).limit(N_ENTRIES).toArray(),
      db.collection('treatments').find({}).sort({ created_at: -1 }).limit(N_TREATMENTS).toArray(),
      db.collection('devicestatus').find({}).sort({ created_at: -1 }).limit(N_DEVICESTATUS).toArray(),
      db.collection('profile').find({}).sort({ startDate: -1 }).limit(1).toArray()
    ]);
    return { entries, treatments, devicestatus, profiles };
  }
  rows.push(await measure('fetch whole window (4 queries)', fetchAll, 100));

  async function fullWake () {
    const raw = await fetchAll();
    const dd = initDdata();
    Object.assign(dd, dd.processRawDataForRuntime({
      sgvs: raw.entries.map(e => ({ _id: String(e._id), mgdl: e.sgv, mills: e.date,
        device: e.device, type: 'sgv', direction: e.direction })),
      treatments: raw.treatments, devicestatus: raw.devicestatus, profiles: raw.profiles,
      mbgs: [], cals: [], food: [], activity: [], dbstats: {} }));
    dd.processTreatments(false);
    return dd.dataWithRecentStatuses();
  }
  rows.push(await measure('fetch + build ddata (full cold wake)', fullWake, 100));

  // The alarm slice of EXP-MT-035d, fetched rather than held resident. This is the
  // query ns-evaluator would issue per change.
  async function alarmSlice () {
    const db = client.db(`${DB_PREFIX}${(k++) % n}`);
    const [sgvs, ds, prof, dia, ...special] = await Promise.all([
      db.collection('entries').find({}).sort({ date: -1 }).limit(5).toArray(),
      db.collection('devicestatus').find({}).sort({ created_at: -1 }).limit(1).toArray(),
      db.collection('profile').find({}).sort({ startDate: -1 }).limit(1).toArray(),
      db.collection('treatments').find({ created_at: { $gte: new Date(Date.now() - 6 * 3600000).toISOString() } }).toArray(),
      ...SPECIAL.map(t => db.collection('treatments')
        .find({ eventType: { $eq: t } }).sort({ created_at: -1 }).limit(1).toArray())
    ]);
    return { sgvs, ds, prof, dia, special };
  }
  rows.push(await measure('alarm slice (ns-evaluator per change)', alarmSlice, 200));
  return rows;
}

// Does a query's RTT block the event loop? If the driver is doing its job, no:
// wall time goes up with concurrency but the loop stays responsive. This is the
// claim the cost model rests on, so it is measured rather than asserted.
async function armLoopDelay (client, n) {
  console.log(`\n--- event-loop delay under concurrent queries ---`);
  const rows = [];
  for (const conc of [1, 16, 64, 256]) {
    const h = monitorEventLoopDelay({ resolution: 1 });
    h.enable();
    const t0 = process.hrtime.bigint();
    const cpu0 = process.cpuUsage();
    const rounds = Math.max(4, Math.ceil(1024 / conc));
    for (let r = 0; r < rounds; r++) {
      await Promise.all(Array.from({ length: conc }, (_, i) =>
        client.db(`${DB_PREFIX}${(r * conc + i) % n}`)
          .collection('entries').find({}).sort({ date: -1 }).limit(10).toArray()));
    }
    const elapsed = Number(process.hrtime.bigint() - t0) / 1e6;
    const cpu = process.cpuUsage(cpu0);
    h.disable();
    const ops = rounds * conc;
    const row = { concurrency: conc, ops,
      throughputPerS: +(ops / (elapsed / 1000)).toFixed(0),
      loopDelayP50_ms: +(h.percentile(50) / 1e6).toFixed(3),
      loopDelayP99_ms: +(h.percentile(99) / 1e6).toFixed(3),
      cpuPerOp_ms: +(((cpu.user + cpu.system) / 1000) / ops).toFixed(4) };
    rows.push(row);
    console.log(`  concurrency ${String(conc).padStart(3)}   ${String(row.throughputPerS).padStart(6)} ops/s   ` +
      `loop delay ${row.loopDelayP50_ms.toFixed(2)} p50 / ${row.loopDelayP99_ms.toFixed(2)} p99 ms   ` +
      `cpu/op ${row.cpuPerOp_ms.toFixed(3)} ms`);
  }
  return rows;
}

// ---------------------------------------------------------------- main

async function main () {
  const arm = process.argv[2] || 'all';
  const client = new MongoClient(MONGO_URL, { maxPoolSize: 100 });
  await client.connect();
  const build = await client.db('admin').command({ buildInfo: 1 });
  console.log(`mongodb ${build.version} at ${MONGO_URL}   node ${process.version}`);

  const out = { date: new Date().toISOString(), mongo: build.version, node: process.version,
    url: MONGO_URL, tenants: TENANTS, rttLabel: process.env.RTT_LABEL || 'loopback' };

  if (arm === 'load' || arm === 'all') out.load = await armLoad(client, TENANTS);
  if (arm === 'cpu' || arm === 'all') out.cpu = await armCpu(client, TENANTS);
  if (arm === 'cycle' || arm === 'all') out.cycle = await armCycle(client, TENANTS);
  if (arm === 'coldwake' || arm === 'all') out.coldwake = await armColdWake(client, TENANTS);
  if (arm === 'loopdelay' || arm === 'all') out.loopdelay = await armLoopDelay(client, TENANTS);

  await client.close();
  const suffix = out.rttLabel === 'loopback' ? '' : `-${out.rttLabel}`;
  const dest = path.join(__dirname, 'results', `exp-mt-026${suffix}.json`);
  fs.writeFileSync(dest, JSON.stringify(out, null, 2));
  console.log(`\nresults -> ${path.relative(process.cwd(), dest)}`);
}

main().catch(e => { console.error(e); process.exit(1); });
