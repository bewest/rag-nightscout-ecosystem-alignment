// EXP-MT-035 / EXP-MT-003 / EXP-MT-004 / EXP-MT-005
//
// Measures the per-tenant cost of the REAL lib/data/ddata.js + calcdelta.js paths,
// not a synthetic Map of plain fixtures, and then solves for K (tenants per process).
//
// Why this exists: §7.4 measured `shared` at 2.2 MB/tenant by holding gen.js payloads
// in a Map. That skips processRawDataForRuntime's deep clone, the eight derived
// treatment arrays, and the retained client projection — i.e. most of what a tenant
// context actually holds. §7.4.1 further argues residency is a policy, so the arms
// below separate what a HOT tenant costs from what a COLD one must still cost.
//
// Arms:
//   raw       — gen.js fixtures in a Map (reproduces §7.4's `shared` measurement)
//   resident  — real ddata, fully processed + client projection retained  (§5B)
//   alarm     — alarm-critical slice only, the cold tier of §7.4.1        (§5C)
//   cycle     — CPU of one incremental load cycle per tenant             (bounds K)
//   rebuild   — CPU of building a tenant's world from raw, per request   (§5D)
//
// Usage:
//   node --expose-gc residency.js <arm> [N] [--unique]
//   node --expose-gc residency.js all
//
// --unique gives every document a distinct _id and varied values. gen.js reuses one
// interned 24-char string for every _id in every tenant, which V8 stores once; real
// Mongo ids do not. Whether that changes the answer is itself a finding.

'use strict';

const path = require('path');

const NS_ROOT = process.env.NS_ROOT ||
  path.resolve(__dirname, '../../externals/cgm-remote-monitor-official');

const initDdata = require(path.join(NS_ROOT, 'lib/data/ddata'));
const calcDelta = require(path.join(NS_ROOT, 'lib/data/calcdelta'));

const UNIQUE = process.argv.includes('--unique');

// ---------------------------------------------------------------- fixtures

let idCounter = 0;
function oid () {
  if (!UNIQUE) return 'a'.repeat(24);
  // A real Mongo ObjectId is 24 distinct hex chars. A monotonic counter in hex,
  // left-padded, is genuinely distinct — an earlier LCG here was degenerate and
  // produced only 16 distinct values, which silently defeats the whole point.
  return (++idCounter).toString(16).padStart(24, '0');
}

// Shapes follow gen.js (which took them from ddata.js and cache.js retention
// windows); --unique varies the values that a real site would vary.
function mkSgv (i, t) {
  const now = Date.now() - i * 300000;
  return { _id: oid(), device: 'xDrip-DexcomG6', date: now,
    dateString: new Date(now).toISOString(),
    sgv: UNIQUE ? 70 + ((i * 7 + t * 13) % 180) : 120,
    delta: UNIQUE ? ((i % 21) - 10) / 5 : 1.2,
    direction: 'Flat', type: 'sgv', filtered: 180000, unfiltered: 180000,
    rssi: 100, noise: 1, sysTime: new Date(now).toISOString(), utcOffset: 0,
    mills: now, mgdl: 120 };
}
function mkTr (i, t) {
  const now = Date.now() - i * 600000;
  return { _id: oid(), eventType: 'Temp Basal', duration: 30,
    absolute: UNIQUE ? ((i % 20) / 10) : 0.8, rate: 0.8,
    created_at: new Date(now).toISOString(),
    enteredBy: UNIQUE ? `loop://iPhone-${t}` : 'loop://iPhone',
    carbs: null, insulin: null, mills: now, endmills: 0, utcOffset: 0,
    notes: 'x'.repeat(20) };
}
function mkDs (i, t) {
  const now = Date.now() - i * 300000;
  const iso = new Date(now).toISOString();
  return { _id: oid(), device: 'loop://iPhone', created_at: iso, mills: now,
    loop: { name: 'Loop', version: '3.4', timestamp: iso,
      iob: { timestamp: iso, iob: UNIQUE ? (i % 50) / 10 : 1.234 },
      cob: { timestamp: iso, cob: 12 },
      predicted: { startDate: iso,
        values: Array.from({ length: 72 }, (_, k) => UNIQUE ? 80 + ((i + k + t) % 160) : 120) },
      recommendedBolus: 0,
      enacted: { rate: 0.75, duration: 30, timestamp: iso, received: true } },
    uploader: { battery: 88 } };
}

function rawTenant (t) {
  return {
    sgvs: Array.from({ length: 576 }, (_, i) => mkSgv(i, t)),
    treatments: Array.from({ length: 600 }, (_, i) => mkTr(i, t)),
    devicestatus: Array.from({ length: 576 }, (_, i) => mkDs(i, t)),
    mbgs: [], cals: [], profiles: [{}], food: [], activity: [], dbstats: {}
  };
}

// ---------------------------------------------------------------- arms

// The real path a tenant's data takes on load (lib/data/dataloader.js calls these).
function residentTenant (t) {
  const raw = rawTenant(t);
  const dd = initDdata();
  const processed = dd.processRawDataForRuntime(raw);
  Object.assign(dd, processed);
  dd.processTreatments(false);
  // Nightscout retains the client-facing projection between updates so the next
  // calcdelta has something to diff against (bootevent.js / websocket.js).
  dd.lastClone = dd.dataWithRecentStatuses();
  return dd;
}

// §7.4.1's cold tier: what must stay resident for a tenant nobody is watching,
// so a hypo alarm still fires. Deliberately minimal.
function alarmSlice (t) {
  const raw = rawTenant(t);
  const last = raw.sgvs[0];
  return {
    tenant: `t${t}`,
    lastSgv: { mills: last.mills, sgv: last.sgv, delta: last.delta, direction: last.direction },
    thresholds: { bgHigh: 260, bgTargetTop: 180, bgTargetBottom: 80, bgLow: 55 },
    alarms: {},           // per-service ack/snooze state (lib/notifications.js)
    lastAckTime: 0,
    lastEmitted: 0
  };
}

// ---------------------------------------------------------------- measurement

function gc () { if (global.gc) { global.gc(); global.gc(); } }

function mem () {
  gc();
  const m = process.memoryUsage();
  return { rss: m.rss, heap: m.heapUsed, ext: m.external, ab: m.arrayBuffers,
           total: m.heapUsed + m.external };
}

function mb (bytes) { return +(bytes / 1048576).toFixed(3); }

function memArm (name, build, N, checkpoints) {
  const before = mem();
  const held = new Map();
  const marks = [];
  for (let i = 0; i < N; i++) {
    held.set(`t${i}`, build(i));
    if (checkpoints.includes(i + 1)) {
      const now = mem();
      marks.push({
        n: i + 1,
        totalMB: mb(now.total - before.total),
        rssMB: mb(now.rss - before.rss),
        perTenantKB: +(((now.total - before.total) / (i + 1)) / 1024).toFixed(1),
        perTenantRssKB: +(((now.rss - before.rss) / (i + 1)) / 1024).toFixed(1)
      });
    }
  }
  global.__keep = held;              // defeat escape analysis
  const out = { arm: name, unique: UNIQUE, marks };
  global.__keep = null;
  return out;
}

function stats (samples) {
  const s = samples.slice().sort((a, b) => a - b);
  const q = p => +s[Math.min(s.length - 1, Math.floor(s.length * p))].toFixed(4);
  return { p50: q(0.5), p95: q(0.95), p99: q(0.99), max: +s[s.length - 1].toFixed(4) };
}

// One incremental load cycle, as lib/data/dataloader.js performs it:
// new documents arrive, get processed, merged, re-derived, re-projected, diffed.
function cycleArm (iterations) {
  const dd = residentTenant(0);
  const samples = [];
  for (let k = 0; k < iterations; k++) {
    const fresh = {
      sgvs: [mkSgv(-k - 1, 0)],
      treatments: k % 12 === 0 ? [mkTr(-k - 1, 0)] : [],
      devicestatus: [mkDs(-k - 1, 0)],
      mbgs: [], cals: [], profiles: [], food: [], activity: [], dbstats: {}
    };
    const t0 = process.hrtime.bigint();
    const processed = dd.processRawDataForRuntime(fresh);
    dd.sgvs = dd.idMergePreferNew(dd.sgvs, processed.sgvs);
    if (processed.treatments.length) {
      dd.treatments = dd.idMergePreferNew(dd.treatments, processed.treatments);
    }
    dd.devicestatus = dd.idMergePreferNew(dd.devicestatus, processed.devicestatus);
    dd.processTreatments(false);
    const projection = dd.dataWithRecentStatuses();
    const delta = calcDelta(dd.lastClone, projection);
    dd.lastClone = projection;
    const t1 = process.hrtime.bigint();
    if (k >= iterations / 5) samples.push(Number(t1 - t0) / 1e6);   // drop warm-up
    if (!delta) throw new Error('no delta');
  }
  return { arm: 'cycle', unique: UNIQUE, iterations, ms: stats(samples) };
}

// §5D: hold nothing; rebuild the tenant's world on each request.
function rebuildArm (iterations) {
  const raws = Array.from({ length: 8 }, (_, i) => rawTenant(i));
  const samples = [];
  for (let k = 0; k < iterations; k++) {
    const raw = raws[k % raws.length];
    const t0 = process.hrtime.bigint();
    const dd = initDdata();
    Object.assign(dd, dd.processRawDataForRuntime(raw));
    dd.processTreatments(false);
    const projection = dd.dataWithRecentStatuses();
    const t1 = process.hrtime.bigint();
    if (k >= iterations / 5) samples.push(Number(t1 - t0) / 1e6);
    if (!projection) throw new Error('no projection');
  }
  return { arm: 'rebuild', unique: UNIQUE, iterations, ms: stats(samples) };
}

// ---------------------------------------------------------------- main

const CHECKPOINTS = [1, 10, 25, 50, 100, 200, 300];

function run (arm, N) {
  switch (arm) {
    case 'raw':      return memArm('raw', rawTenant, N, CHECKPOINTS);
    case 'resident': return memArm('resident', residentTenant, N, CHECKPOINTS);
    case 'alarm':    return memArm('alarm', alarmSlice, N, CHECKPOINTS);
    case 'cycle':    return cycleArm(N || 400);
    case 'rebuild':  return rebuildArm(N || 200);
    default: throw new Error(`unknown arm: ${arm}`);
  }
}

const arm = process.argv[2] || 'resident';
const N = Number(process.argv[3]) || undefined;

if (!global.gc) {
  console.error('run with --expose-gc for stable memory numbers');
  process.exit(2);
}

console.log(JSON.stringify(run(arm, N === undefined ? 300 : N), null, 2));
