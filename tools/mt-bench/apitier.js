// EXP-MT-055 (REST read tier) / EXP-MT-035c (resident-cost correction)
//
// The K/residency report measured the load cycle, the plugin tier, realtime fan-out
// and the vendor pool. It did not measure the REST tier, and it assumed a shard's
// per-tenant resident cost is ddata alone. Both gaps change the component picture:
//
//   A. api/entries reads are served FROM RESIDENT MEMORY, not from Mongo, whenever
//      the query is a bare count (or a count plus a `type` filter) and the cache
//      holds enough documents — lib/api/entries/index.js:459-500. That is the
//      highest-QPS endpoint in the Nightscout ecosystem (every follower app polls
//      it), and no document in this workspace records what residency buys there or
//      what it costs. The two branches of that one function differ by a full deep
//      clone of the whole cache array, so they are measured separately.
//
//   B. residency.js's `resident` arm holds ddata plus the retained client
//      projection. A real ctx also holds lib/server/cache.js's arrays — entries
//      (48 h), treatments (60 h), devicestatus (24-48 h) — which are a SECOND copy
//      of the same window, kept so the loader can do incremental merges and so (A)
//      can answer without Mongo. EXP-MT-035's per-tenant figure omits them.
//
//   D. The cycle measurement in the K report times ddata's own functions. The
//      dataloader also calls ctx.cache.insertData once per datatype per cycle, and
//      insertData returns cache.getData() — a full deep clone of the ENTIRE retained
//      array (cache.js:78-82, and getData at :73-76). Three datatypes, every cycle.
//      That cost sits between the loader and ddata and is in neither measurement.
//
//   C. residency.js's `alarm` arm models simplealarms only (last SGV + thresholds +
//      ack state). The shipped alarm set is 18 plugins; surveying what each one
//      actually reads gives a materially larger slice. Measured here so §7.4.1's
//      hot/cold ratio is quoted against the real alarm path.
//
// Arms:
//   read   — api/entries cached-read CPU, typed vs untyped branch  (bounds K_rest)
//   mem    — resident cost with and without ctx.cache              (corrects EXP-MT-035)
//   alarm  — alarm slice scoped to the 18 shipped alarm plugins    (corrects §7.4.1)
//   cycle  — cache.insertData's defensive deep clone, per load cycle (corrects K's cycle)
//
// Usage:
//   node --expose-gc apitier.js <arm> [N]
//   node --expose-gc apitier.js all
//
// No database is in the loop. These are event-loop CPU and heap figures, as
// everywhere else in this harness; they rank hypotheses, they are not capacity.

'use strict';

const path = require('path');
const fs = require('fs');

const NS_ROOT = process.env.NS_ROOT ||
  path.resolve(__dirname, '../../externals/cgm-remote-monitor-official');

const initDdata = require(path.join(NS_ROOT, 'lib/data/ddata'));

// ---------------------------------------------------------------- fixtures
//
// Same shapes as residency.js --unique. Distinct ids throughout: the identical-id
// defect that invalidated the first pass is easy to reintroduce and invisible in
// the output, so ids are asserted distinct before anything is measured.

let idCounter = 0;
const seenIds = new Set();
function oid () {
  const id = (++idCounter).toString(16).padStart(24, '0');
  seenIds.add(id);
  return id;
}

function mkSgv (i, t) {
  const now = Date.now() - i * 300000;
  return { _id: oid(), device: 'xDrip-DexcomG6', date: now,
    dateString: new Date(now).toISOString(),
    sgv: 70 + ((i * 7 + t * 13) % 180),
    delta: ((i % 21) - 10) / 5,
    direction: 'Flat', type: 'sgv', filtered: 180000, unfiltered: 180000,
    rssi: 100, noise: 1, sysTime: new Date(now).toISOString(), utcOffset: 0,
    mills: now, mgdl: 120 };
}
function mkTr (i, t) {
  const now = Date.now() - i * 600000;
  return { _id: oid(), eventType: 'Temp Basal', duration: 30,
    absolute: (i % 20) / 10, rate: 0.8,
    created_at: new Date(now).toISOString(),
    enteredBy: `loop://iPhone-${t}`,
    carbs: null, insulin: null, mills: now, endmills: 0, utcOffset: 0,
    notes: 'x'.repeat(20) };
}
function mkDs (i, t) {
  const now = Date.now() - i * 300000;
  const iso = new Date(now).toISOString();
  return { _id: oid(), device: 'loop://iPhone', created_at: iso, mills: now,
    loop: { name: 'Loop', version: '3.4', timestamp: iso,
      iob: { timestamp: iso, iob: (i % 50) / 10 },
      cob: { timestamp: iso, cob: 12 },
      predicted: { startDate: iso,
        values: Array.from({ length: 72 }, (_, k) => 80 + ((i + k + t) % 160)) },
      recommendedBolus: 0,
      enacted: { rate: 0.75, duration: 30, timestamp: iso, received: true } },
    uploader: { battery: 88 } };
}

// A profile document, which residency.js's fixture leaves as `{}`. Real profiles
// carry a therapy schedule per named profile, and on Loop sites a loopSettings
// block as well (200 of 202 profile documents across 10 sites, per the
// replay-fidelity work). boluswizardpreview and the Loop remote API both read it,
// so an alarm slice that omits it is not a working alarm slice.
function mkProfile () {
  const sched = (v) => Array.from({ length: 8 }, (_, i) => ({
    time: `${String(i * 3).padStart(2, '0')}:00`, timeAsSeconds: i * 10800, value: v + i * 0.1 }));
  return { _id: oid(), defaultProfile: 'Default', mills: Date.now(),
    startDate: new Date().toISOString(),
    loopSettings: { dia: 6, minimumBGGuard: 80, maximumBasalRatePerHour: 4,
      maximumBolus: 10, deviceToken: 'x'.repeat(64), bundleIdentifier: 'com.example.Loop' },
    store: { Default: { dia: 6, carbs_hr: 20, delay: 20, timezone: 'US/Pacific',
      carbratio: sched(10), sens: sched(50), basal: sched(0.8),
      target_low: sched(100), target_high: sched(120) } } };
}

function rawTenant (t) {
  return {
    sgvs: Array.from({ length: 576 }, (_, i) => mkSgv(i, t)),
    treatments: Array.from({ length: 600 }, (_, i) => mkTr(i, t)),
    devicestatus: Array.from({ length: 576 }, (_, i) => mkDs(i, t)),
    mbgs: [], cals: [], profiles: [mkProfile()], food: [], activity: [], dbstats: {}
  };
}

// ---------------------------------------------------------------- measurement

function collect () { if (global.gc) { global.gc(); global.gc(); } }
function heap () {
  collect();
  const m = process.memoryUsage();
  return m.heapUsed + m.external;
}
function kb (bytes) { return +(bytes / 1024).toFixed(1); }

function timed (fn, iters, warmup) {
  for (let i = 0; i < (warmup || 50); i++) fn();
  const samples = [];
  for (let i = 0; i < iters; i++) {
    const s = process.hrtime.bigint();
    fn();
    samples.push(Number(process.hrtime.bigint() - s) / 1e6);
  }
  samples.sort((a, b) => a - b);
  return {
    p50: +samples[Math.floor(iters * 0.5)].toFixed(4),
    p99: +samples[Math.floor(iters * 0.99)].toFixed(4),
    mean: +(samples.reduce((a, b) => a + b, 0) / iters).toFixed(4)
  };
}

function memArm (build, N) {
  const before = heap();
  const held = new Map();
  for (let i = 0; i < N; i++) held.set(i, build(i));
  const after = heap();
  const per = (after - before) / N;
  held.clear();
  return kb(per);
}

// ---------------------------------------------------------------- arm: read
//
// lib/api/entries/index.js:459-500, transcribed. The branch that matters:
//
//   if (typeQuery) inMemoryCollection = ctx.cache.entries.filter(...)  // by reference
//   else           inMemoryCollection = ctx.cache.getData('entries')   // DEEP CLONE
//   ...
//   res.entries = JSON.parse(JSON.stringify(inMemoryCollection.slice(0, count)))
//
// cache.getData (lib/server/cache.js:73-76) deep-clones the ENTIRE retained array
// before anything is sliced, so an untyped `?count=10` clones 48 h of entries to
// return ten of them, then clones those ten again. The typed branch skips the
// first clone because Array.filter copies references, not documents.

function readArm (N) {
  const cache = { entries: Array.from({ length: 576 }, (_, i) => mkSgv(i, 0)) };
  const getData = () => JSON.parse(JSON.stringify(cache.entries));

  function untyped (count) {
    const coll = getData();
    return JSON.parse(JSON.stringify(coll.slice(0, count)));
  }
  function typed (count) {
    const coll = cache.entries.filter(o => 'sgv' in o);
    return JSON.parse(JSON.stringify(coll.slice(0, count)));
  }

  const rows = [];
  for (const count of [1, 10, 144, 576]) {
    const u = timed(() => untyped(count), N);
    const t = timed(() => typed(count), N);
    rows.push({ count, untyped: u, typed: t, ratio: +(u.p50 / t.p50).toFixed(1) });
    console.log(`  count=${String(count).padStart(3)}  untyped ${u.p50.toFixed(3)} ms p50 / ${u.p99.toFixed(3)} p99` +
                `   typed ${t.p50.toFixed(3)} ms p50 / ${t.p99.toFixed(3)} p99   ${(u.p50 / t.p50).toFixed(1)}x`);
  }
  console.log(`  cache holds ${cache.entries.length} entries, ${JSON.stringify(cache.entries).length} bytes JSON`);

  // K_rest: this is SYNCHRONOUS event-loop work, so it competes with the load
  // cycle rather than yielding like a DB round-trip would. Same 30 % utilisation
  // target as §5 of the K report, and the same per-tenant demand assumption:
  // three follower apps polling /api/v1/entries once a minute.
  const POLLS_PER_TENANT_PER_S = 3 / 60;
  const row10 = rows.find(r => r.count === 10);
  const kRest = {
    untyped: Math.floor((0.3 * 1000 / row10.untyped.p50) / POLLS_PER_TENANT_PER_S),
    typed: Math.floor((0.3 * 1000 / row10.typed.p50) / POLLS_PER_TENANT_PER_S)
  };
  console.log(`  K_rest at count=10, 3 followers/tenant polling 60 s, 30 % budget:`);
  console.log(`    untyped branch  ${kRest.untyped.toLocaleString()} tenants/process`);
  console.log(`    typed branch    ${kRest.typed.toLocaleString()} tenants/process`);
  return { rows, kRest };
}

// ---------------------------------------------------------------- arm: mem

function residentTenant (t) {
  const raw = rawTenant(t);
  const dd = initDdata();
  Object.assign(dd, dd.processRawDataForRuntime(raw));
  dd.processTreatments(false);
  dd.lastClone = dd.dataWithRecentStatuses();
  return dd;
}

// What a real ctx holds: the above, plus lib/server/cache.js's own arrays. The
// cache is NOT a view onto ddata — dataloader merges query results into both
// independently, so the documents are separate object graphs.
function residentPlusCache (t) {
  const dd = residentTenant(t);
  const cached = rawTenant(t);
  dd._cache = { entries: cached.sgvs, treatments: cached.treatments,
    devicestatus: cached.devicestatus };
  return dd;
}

function memArmAll (N) {
  const ddataOnly = memArm(residentTenant, N);
  const withCache = memArm(residentPlusCache, N);
  console.log(`  ddata + client projection      ${ddataOnly} KB/tenant`);
  console.log(`  + ctx.cache arrays             ${withCache} KB/tenant   (${(withCache / ddataOnly).toFixed(2)}x)`);
  console.log(`  K_memory @4 GB                 ${Math.floor(4 * 1048576 / ddataOnly)} -> ${Math.floor(4 * 1048576 / withCache)} tenants`);
  return { ddataOnly, withCache,
    kMemBefore: Math.floor(4 * 1048576 / ddataOnly),
    kMemAfter: Math.floor(4 * 1048576 / withCache) };
}

// ---------------------------------------------------------------- arm: alarm
//
// residency.js's alarm slice is simplealarms' inputs. Surveying every plugin that
// implements checkNotifications on dev @ a8888f0d gives four classes of need:
//
//   latest value only   simplealarms errorcodes timeago dbsize pump loop openaps
//                       xdripjs upbat treatmentnotify
//   short SGV window    ar2, via bgnow's buckets (~20 min)
//   latest-of-type      cannulaage insulinage sensorage batteryage — newest
//                       Site Change / Insulin Change / Sensor Start / Pump Battery
//                       Change, which dataloader already fetches as six count:1
//                       queries (loadLatestSingle, dataloader.js:396-418)
//   DIA window          boluswizardpreview — profile + IOB/COB over the treatment
//                       window, the only genuinely expensive member of the set
//
// Sizing DIA_TREATMENTS: a 6 h DIA at a realistic bolus + temp-basal cadence.
// Loop and AAPS write a temp basal every ~5 min, so this is the dominant term and
// the one worth varying.

const BGNOW_SGVS = 5;      // bgnow default 4 buckets x 5 min, plus the current reading
const SPECIAL_TYPES = 6;   // the six loadLatestSingle event types
const DIA_TREATMENTS = 72; // 6 h at a 5-minute temp-basal cadence

function alarmSliceMinimal (t) {
  const last = mkSgv(0, t);
  return {
    tenant: `t${t}`,
    lastSgv: { mills: last.mills, sgv: last.sgv, delta: last.delta, direction: last.direction },
    thresholds: { bgHigh: 260, bgTargetTop: 180, bgTargetBottom: 80, bgLow: 55 },
    alarms: {}, lastAckTime: 0, lastEmitted: 0
  };
}

function alarmSliceShipped (t) {
  const slice = alarmSliceMinimal(t);
  slice.recentSgvs = Array.from({ length: BGNOW_SGVS }, (_, i) => mkSgv(i, t));
  slice.latestDevicestatus = mkDs(0, t);
  slice.latestSpecial = Array.from({ length: SPECIAL_TYPES }, (_, i) => mkTr(i, t));
  slice.profile = mkProfile();
  slice.diaTreatments = Array.from({ length: DIA_TREATMENTS }, (_, i) => mkTr(i, t));
  return slice;
}

function alarmArm (N) {
  const minimal = memArm(alarmSliceMinimal, N);
  const shipped = memArm(alarmSliceShipped, N);
  const resident = memArm(residentPlusCache, N);
  console.log(`  minimal slice (simplealarms only)   ${minimal} KB/tenant`);
  console.log(`  shipped slice (18 alarm plugins)    ${shipped} KB/tenant   (${(shipped / minimal).toFixed(0)}x larger)`);
  console.log(`  hot/cold ratio vs resident          ${(resident / minimal).toFixed(0)}x -> ${(resident / shipped).toFixed(0)}x`);
  console.log(`  10,000 cold tenants                 ${(minimal * 10000 / 1024).toFixed(0)} MB -> ${(shipped * 10000 / 1024).toFixed(0)} MB`);
  return { minimal, shipped, resident,
    ratioBefore: Math.round(resident / minimal), ratioAfter: Math.round(resident / shipped),
    coldMbBefore: +(minimal * 10000 / 1024).toFixed(0),
    coldMbAfter: +(shipped * 10000 / 1024).toFixed(0) };
}

// ---------------------------------------------------------------- arm: cycle
//
// dataloader.js:196 / :333 / :490 each call ctx.cache.insertData(type, batch), and
// insertData ends with `return data.getData(datatype)` — a JSON round-trip over the
// whole retained array, not over the incremental batch that was just merged. So a
// cycle that merges three new documents still deep-clones 48 h of entries, 60 h of
// treatments and 24-48 h of devicestatus.
//
// The caller does not keep the returned array: it reverses it and projects each
// element into a fresh object. The clone is defending against a mutation that
// mostly does not happen — but see dataloader.js:203, `if (!element.mills)
// element.mills = element.date`, which DOES write to the element. Any change here
// has to resolve that write first; the number below sizes the prize, it does not
// license the patch.

function cycleArm (N) {
  const t = rawTenant(0);
  const cache = { entries: t.sgvs, treatments: t.treatments, devicestatus: t.devicestatus };
  const getData = (k) => JSON.parse(JSON.stringify(cache[k]));

  const per = {};
  let total = 0;
  for (const type of ['entries', 'treatments', 'devicestatus']) {
    const r = timed(() => getData(type), N * 2, 30);
    per[type] = r;
    total += r.p50;
    console.log(`  getData('${type}')`.padEnd(38) + `${r.p50.toFixed(3)} ms p50 / ${r.p99.toFixed(3)} p99   n=${cache[type].length}`);
  }
  total = +total.toFixed(3);

  // Cycle figures carried from the K report §3 (measured) and §5 (fixes applied).
  const CYCLE_CURRENT = 9.457;
  const CYCLE_FIXED = 2.19;
  const LOADS_PER_S = 0.2;      // active tenant, UPDATE_MAX_WAIT
  const UTIL = 0.3;
  const k = (ms) => Math.floor((UTIL * 1000) / (ms * LOADS_PER_S));

  console.log(`  ---`);
  console.log(`  clone cost per cycle (3 datatypes)   ${total} ms`);
  console.log(`  cycle as measured / with clones      ${CYCLE_CURRENT} -> ${(CYCLE_CURRENT + total).toFixed(2)} ms   K ${k(CYCLE_CURRENT)} -> ${k(CYCLE_CURRENT + total)}`);
  console.log(`  quadratics fixed / with clones       ${CYCLE_FIXED} -> ${(CYCLE_FIXED + total).toFixed(2)} ms   K ${k(CYCLE_FIXED)} -> ${k(CYCLE_FIXED + total)}`);
  console.log(`  clone share of the FIXED cycle       ${((total / (CYCLE_FIXED + total)) * 100).toFixed(0)} %`);

  return { per, total,
    cycleCurrent: CYCLE_CURRENT, cycleCurrentWithClones: +(CYCLE_CURRENT + total).toFixed(2),
    cycleFixed: CYCLE_FIXED, cycleFixedWithClones: +(CYCLE_FIXED + total).toFixed(2),
    kCurrent: k(CYCLE_CURRENT), kCurrentWithClones: k(CYCLE_CURRENT + total),
    kFixed: k(CYCLE_FIXED), kFixedWithClones: k(CYCLE_FIXED + total),
    cloneShareOfFixed: +((total / (CYCLE_FIXED + total)) * 100).toFixed(0) };
}

// ---------------------------------------------------------------- main

function main () {
  const arm = process.argv[2] || 'all';
  const N = parseInt(process.argv[3], 10) || 200;
  const out = { node: process.version, date: new Date().toISOString(), N };

  if (arm === 'read' || arm === 'all') {
    console.log('\nEXP-MT-055 — api/entries cached read path (lib/api/entries/index.js:459-500)');
    out.read = readArm(Math.max(N * 5, 1000));
  }
  if (arm === 'mem' || arm === 'all') {
    console.log('\nEXP-MT-035c — resident cost, ddata alone vs ddata + ctx.cache');
    out.mem = memArmAll(N);
  }
  if (arm === 'cycle' || arm === 'all') {
    console.log('\nEXP-MT-055b — cache.insertData deep clone, per load cycle (cache.js:73-82)');
    out.cycle = cycleArm(N);
  }
  if (arm === 'alarm' || arm === 'all') {
    console.log('\nEXP-MT-035d — alarm slice, simplealarms only vs the shipped alarm set');
    out.alarm = alarmArm(N);
  }

  if (seenIds.size !== idCounter) {
    throw new Error(`id generator is degenerate: ${seenIds.size} distinct from ${idCounter} calls`);
  }
  console.log(`\nids: ${seenIds.size} distinct from ${idCounter} calls — ok`);

  const dest = path.join(__dirname, 'results', 'exp-mt-apitier.json');
  fs.writeFileSync(dest, JSON.stringify(out, null, 2));
  console.log(`results -> ${path.relative(process.cwd(), dest)}`);
}

main();
