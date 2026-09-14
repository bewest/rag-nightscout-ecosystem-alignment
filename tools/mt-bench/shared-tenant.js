// EXP-MT-011b — one logical database, tenant discriminator
//
// EXP-MT-026/040b measured database-per-tenant (§6.7's A' rung) and found a hard
// ceiling: 47 WiredTiger files and ~3.7 MB of non-evictable mongod RSS PER TENANT,
// because every tenant gets its own 6 collections and 41 indexes.
//
// That is a property of A', not of multitenancy. The actual multitenant target —
// §6.6's B on Mongo, D on Postgres — is ONE logical database where every document
// carries a tenant discriminator and the index set is tenant-prefixed. Then 6
// collections and 41 indexes are TOTALS, not per-tenant, and the namespace cost is
// O(1) in tenant count instead of O(n).
//
// §6.7 asserts exactly this ("35 total with tenant_id as the leading column, not 35
// per tenant — the curve is flat instead of linear") and never measured it. This
// measures it, against the identical corpus, index set, queries and server config
// as the A' run, so the two are directly comparable.
//
// What this arm is really testing is the OTHER failure mode. A' fails on namespace
// count with flat query latency. Shared-collection cannot fail that way — but its
// indexes now hold every tenant's keys, so the question is whether a tenant-scoped
// query stays flat as the collection grows, or whether B-times-N tenants degrades
// the way §6.1 measured MongoDB's role-keyed views degrading (O(all tenants)).
//
// The discriminator is an explicit field in the query, so the planner gets a
// constant and can build index bounds from it. That is the difference between this
// and §6.1's $expr-over-$$USER_ROLES result, and it is why this is expected to
// work. Expected is not measured.
//
// Usage:
//   node shared-tenant.js [maxTenants] [step]
//
// LIMITS: same laptop, same loopback, no TLS, no auth, reads only. See §L of the
// EXP-MT-026 report — every limit there applies here unchanged.

'use strict';

const path = require('path');
const fs = require('fs');
const { execFileSync } = require('child_process');

const NS_ROOT = process.env.NS_ROOT ||
  path.resolve(__dirname, '../../externals/cgm-remote-monitor-official');
const { MongoClient } = require(path.join(NS_ROOT, 'node_modules/mongodb'));

const MONGO_URL = process.env.MONGO_URL || 'mongodb://127.0.0.1:27099/?directConnection=true';
const CONTAINER = process.env.MONGO_CONTAINER || 'nsbench-mongo';
const DB_NAME = 'nsshared';
const MAX = parseInt(process.argv[2], 10) || 400;
const STEP = parseInt(process.argv[3], 10) || 100;

// Identical per-tenant corpus to dbloop.js, so the comparison is like for like.
const N_ENTRIES = 576, N_TREATMENTS = 600, N_DEVICESTATUS = 576;

// The A' index set, every index prefixed with the tenant discriminator. This is the
// mechanical translation §6.3 describes: each existing index becomes a compound
// index with tenant leading, so the planner can bound the scan to one tenant.
// Count is IDENTICAL (41) — the difference is that here it is 41 total.
const TENANT = 'tenant';
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
function tenantPrefixed (spec) {
  const out = { [TENANT]: 1 };
  if (typeof spec === 'string') { out[spec] = 1; return out; }
  for (const [k, v] of Object.entries(spec)) out[k] = v;
  return out;
}

// ---------------------------------------------------------------- fixtures

let idCounter = 0;
function oid () { return (++idCounter).toString(16).padStart(24, '0'); }
const SPECIAL = ['Sensor Start', 'Sensor Change', 'Sensor Stop', 'Site Change',
  'Insulin Change', 'Pump Battery Change'];

function mkEntry (i, t) {
  const now = Date.now() - i * 300000;
  return { tenant: `t${t}`, device: 'xDrip-DexcomG6', date: now,
    dateString: new Date(now).toISOString(), sgv: 70 + ((i * 7 + t * 13) % 180),
    delta: ((i % 21) - 10) / 5, direction: 'Flat', type: 'sgv', filtered: 180000,
    unfiltered: 180000, rssi: 100, noise: 1, sysTime: new Date(now).toISOString(),
    utcOffset: 0, identifier: oid() };
}
function mkTreatment (i, t) {
  const now = Date.now() - i * 600000;
  const special = i % 97 === 0 ? SPECIAL[(i / 97 | 0) % SPECIAL.length] : null;
  return { tenant: `t${t}`, eventType: special || 'Temp Basal', duration: special ? 0 : 30,
    absolute: (i % 20) / 10, rate: 0.8, created_at: new Date(now).toISOString(),
    enteredBy: `loop://iPhone-${t}`, insulin: null, carbs: null, utcOffset: 0,
    identifier: oid() };
}
function mkDeviceStatus (i, t) {
  const now = Date.now() - i * 300000;
  const iso = new Date(now).toISOString();
  return { tenant: `t${t}`, device: 'loop://iPhone', created_at: iso,
    loop: { name: 'Loop', version: '3.4', timestamp: iso,
      iob: { timestamp: iso, iob: (i % 50) / 10 }, cob: { timestamp: iso, cob: 12 },
      predicted: { startDate: iso,
        values: Array.from({ length: 72 }, (_, k) => 80 + ((i + k + t) % 160)) },
      recommendedBolus: 0,
      enacted: { rate: 0.75, duration: 30, timestamp: iso, received: true } },
    uploader: { battery: 88 }, identifier: oid() };
}
function mkProfile (t) {
  const sched = (v) => Array.from({ length: 8 }, (_, i) => ({
    time: `${String(i * 3).padStart(2, '0')}:00`, timeAsSeconds: i * 10800, value: v + i * 0.1 }));
  return { tenant: `t${t}`, defaultProfile: 'Default', startDate: new Date().toISOString(),
    created_at: new Date().toISOString(),
    loopSettings: { dia: 6, minimumBGGuard: 80, maximumBasalRatePerHour: 4, maximumBolus: 10 },
    store: { Default: { dia: 6, carbs_hr: 20, delay: 20, timezone: 'US/Pacific',
      carbratio: sched(10), sens: sched(50), basal: sched(0.8),
      target_low: sched(100), target_high: sched(120) } } };
}

// ---------------------------------------------------------------- measurement

function inContainer (cmd) {
  try { return execFileSync('docker', ['exec', CONTAINER, 'sh', '-c', cmd],
    { encoding: 'utf8', timeout: 30000 }).trim(); } catch (e) { return null; }
}
const wtFiles = () => { const v = inContainer('ls /data/db/*.wt 2>/dev/null | wc -l'); return v ? +v : null; };
const rssMb = () => { const v = inContainer("grep VmRSS /proc/1/status | awk '{print $2}'"); return v ? +(v / 1024).toFixed(1) : null; };
const fds = () => { const v = inContainer('ls /proc/1/fd 2>/dev/null | wc -l'); return v ? +v : null; };

async function timeIt (fn, iters) {
  for (let i = 0; i < 30; i++) await fn();
  const wall = [];
  const cpu0 = process.cpuUsage();
  for (let i = 0; i < iters; i++) {
    const s = process.hrtime.bigint();
    await fn();
    wall.push(Number(process.hrtime.bigint() - s) / 1e6);
  }
  const cpu = process.cpuUsage(cpu0);
  wall.sort((a, b) => a - b);
  return { p50: +wall[Math.floor(iters * 0.5)].toFixed(3),
    p99: +wall[Math.floor(iters * 0.99)].toFixed(3),
    cpu: +(((cpu.user + cpu.system) / 1000) / iters).toFixed(4) };
}

// ---------------------------------------------------------------- main

async function main () {
  const client = new MongoClient(MONGO_URL, { maxPoolSize: 100 });
  await client.connect();
  const db = client.db(DB_NAME);
  await db.dropDatabase();

  const base = { files: wtFiles(), rss: rssMb(), fds: fds() };
  console.log(`baseline: ${base.files} wt files, mongod RSS ${base.rss} MB, ${base.fds} fds`);

  // The whole point: create the collections and the index set ONCE.
  let indexCount = 0;
  for (const [col, specs] of Object.entries(INDEXES)) {
    await db.createCollection(col).catch(() => {});
    for (const spec of specs) { await db.collection(col).createIndex(tenantPrefixed(spec)); indexCount++; }
    await db.collection(col).createIndex({ [TENANT]: 1 }); indexCount++;
  }
  const afterIdx = { files: wtFiles(), rss: rssMb() };
  console.log(`index set created ONCE: ${indexCount} indexes, ${afterIdx.files - base.files} wt files total ` +
    `(A' needed 47 PER TENANT)\n`);

  const rows = [];
  let loaded = 0;
  for (let target = STEP; target <= MAX; target += STEP) {
    const t0 = Date.now();
    for (; loaded < target; loaded++) {
      await db.collection('entries').insertMany(
        Array.from({ length: N_ENTRIES }, (_, i) => mkEntry(i, loaded)), { ordered: false });
      await db.collection('treatments').insertMany(
        Array.from({ length: N_TREATMENTS }, (_, i) => mkTreatment(i, loaded)), { ordered: false });
      await db.collection('devicestatus').insertMany(
        Array.from({ length: N_DEVICESTATUS }, (_, i) => mkDeviceStatus(i, loaded)), { ordered: false });
      await db.collection('profile').insertOne(mkProfile(loaded));
    }
    const loadMs = Date.now() - t0;

    // Tenant-scoped reads, round-robin across every loaded tenant so no single
    // tenant's working set stays hot.
    let k = 0;
    const T = () => `t${(k++) % loaded}`;
    const read10 = await timeIt(() => db.collection('entries')
      .find({ tenant: T() }).sort({ date: -1 }).limit(10).toArray(), 300);
    const readWindow = await timeIt(() => db.collection('entries')
      .find({ tenant: T() }).sort({ date: -1 }).limit(576).toArray(), 100);
    const latestSingle = await timeIt(() => db.collection('treatments')
      .find({ tenant: T(), eventType: { $eq: 'Site Change' } })
      .sort({ created_at: -1 }).limit(1).toArray(), 300);
    const dsLatest = await timeIt(() => db.collection('devicestatus')
      .find({ tenant: T() }).sort({ created_at: -1 }).limit(1).toArray(), 300);

    // Did the planner actually use the tenant-prefixed index, and how many keys
    // did it have to look at? This is the §6.1 question: O(one tenant) or O(all)?
    const exp = await db.collection('entries')
      .find({ tenant: 't0' }).sort({ date: -1 }).limit(10).explain('executionStats');
    const st = exp.executionStats;
    const stats = await db.stats();

    const row = { tenants: loaded,
      docs: loaded * (N_ENTRIES + N_TREATMENTS + N_DEVICESTATUS + 1),
      wtFiles: wtFiles(), mongodRssMb: rssMb(), openFds: fds(),
      dataMb: +(stats.dataSize / 1048576).toFixed(1),
      indexMb: +(stats.indexSize / 1048576).toFixed(1),
      loadMsPerTenant: +(loadMs / STEP).toFixed(0),
      read10, readWindow, latestSingle, dsLatest,
      plan: st.executionStages.stage, keysExamined: st.totalKeysExamined,
      docsExamined: st.totalDocsExamined, returned: st.nReturned };
    rows.push(row);
    console.log(`  ${String(loaded).padStart(4)} tenants  ${String(row.docs).padStart(8)} docs  ` +
      `${String(row.wtFiles).padStart(3)} files  RSS ${String(row.mongodRssMb).padStart(6)} MB  ` +
      `${String(row.dataMb).padStart(6)} MB data / ${String(row.indexMb).padStart(5)} MB idx`);
    console.log(`        read10 ${row.read10.p50.toFixed(3)} p50 / ${row.read10.p99.toFixed(3)} p99, cpu ${row.read10.cpu.toFixed(3)}   ` +
      `window ${row.readWindow.p50.toFixed(2)}   latestSingle ${row.latestSingle.p50.toFixed(3)}   dsLatest ${row.dsLatest.p50.toFixed(3)}`);
    console.log(`        plan ${row.plan}, keys examined ${row.keysExamined} for ${row.returned} returned`);
  }

  const first = rows[0], last = rows[rows.length - 1];
  console.log(`\n  namespace cost: ${last.wtFiles} files TOTAL at ${last.tenants} tenants ` +
    `(${(last.wtFiles / last.tenants).toFixed(2)}/tenant) — A' measured 47.0/tenant`);
  console.log(`  mongod RSS: ${base.rss} -> ${last.mongodRssMb} MB over ${last.tenants} tenants ` +
    `= ${((last.mongodRssMb - base.rss) * 1024 / last.tenants).toFixed(0)} KB/tenant — A' measured 3,793 KB/tenant`);
  console.log(`  read10 p50: ${first.read10.p50} ms at ${first.tenants} tenants -> ` +
    `${last.read10.p50} ms at ${last.tenants} (${(last.read10.p50 / first.read10.p50).toFixed(2)}x)`);
  console.log(`  keys examined stayed ${first.keysExamined} -> ${last.keysExamined} for 10 returned`);

  const out = { date: new Date().toISOString(), baseline: base, indexCount,
    indexFilesTotal: afterIdx.files - base.files, rows,
    filesPerTenant: +(last.wtFiles / last.tenants).toFixed(2),
    rssKbPerTenant: +((last.mongodRssMb - base.rss) * 1024 / last.tenants).toFixed(0) };
  fs.writeFileSync(path.join(__dirname, 'results', 'exp-mt-011b.json'), JSON.stringify(out, null, 2));
  console.log(`\nresults -> results/exp-mt-011b.json`);
  await client.close();
}

main().catch(e => { console.error(e); process.exit(1); });
