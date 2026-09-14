// EXP-MT-028 (extended): what sets K — architecture, or two quadratics?
//
// Measures one incremental load cycle three ways against the real ddata/calcdelta:
//   current   — stock lib/data/ddata.js + lib/data/calcdelta.js
//   +delta    — calcDelta's nsArrayTreatments replaced with a Map-indexed diff
//   +both     — also processDurations replaced with a sorted forward-scan
//
// processDurations (ddata.js:198-247) is quadratic twice: an O(n^2) dedup via
// filter+findIndex, and an explicit treatments x treatments overlap cut. Neither
// is listed among §2.1's three cost centres, and it dominates the cycle.
//
// The replacement is semantics-preserving by construction: cutIfInInterval only
// fires when base.mills < end.mills, so only later events matter; durations shrink
// monotonically under cutting, so a forward scan that re-reads the bound each step
// visits exactly the pairs that can act.
//
// Usage: node cycle-fix.js [iterations] [treatmentCount]

'use strict';

const path = require('path');
const NS_ROOT = process.env.NS_ROOT ||
  path.resolve(__dirname, '../../externals/cgm-remote-monitor-official');
const initDdata = require(path.join(NS_ROOT, 'lib/data/ddata'));
const calcDelta = require(path.join(NS_ROOT, 'lib/data/calcdelta'));
const times = require(path.join(NS_ROOT, 'lib/times'));

const ITER = Number(process.argv[2]) || 300;
const NTREAT = Number(process.argv[3]) || 600;

let idc = 0;
const oid = () => (++idc).toString(16).padStart(24, '0');

const mkSgv = i => { const n = Date.now() - i * 3e5; return { _id: oid(), device: 'xDrip-DexcomG6',
  date: n, dateString: new Date(n).toISOString(), sgv: 70 + (i * 7) % 180, delta: 1.2,
  direction: 'Flat', type: 'sgv', filtered: 180000, unfiltered: 180000, rssi: 100, noise: 1,
  sysTime: new Date(n).toISOString(), utcOffset: 0, mills: n, mgdl: 120 }; };
const mkTr = i => { const n = Date.now() - i * 6e5; return { _id: oid(), eventType: 'Temp Basal',
  duration: 30, absolute: (i % 20) / 10, rate: 0.8, created_at: new Date(n).toISOString(),
  enteredBy: 'loop://iPhone', carbs: null, insulin: null, mills: n, endmills: 0, utcOffset: 0,
  notes: 'x'.repeat(20) }; };
const mkDs = i => { const n = Date.now() - i * 3e5, iso = new Date(n).toISOString();
  return { _id: oid(), device: 'loop://iPhone', created_at: iso, mills: n,
    loop: { name: 'Loop', version: '3.4', timestamp: iso, iob: { timestamp: iso, iob: 1.2 },
      cob: { timestamp: iso, cob: 12 },
      predicted: { startDate: iso, values: Array.from({ length: 72 }, (_, k) => 80 + (i + k) % 160) },
      recommendedBolus: 0, enacted: { rate: .75, duration: 30, timestamp: iso, received: true } },
    uploader: { battery: 88 } }; };

function rawTenant () {
  return { sgvs: Array.from({ length: 576 }, (_, i) => mkSgv(i)),
    treatments: Array.from({ length: NTREAT }, (_, i) => mkTr(i)),
    devicestatus: Array.from({ length: 576 }, (_, i) => mkDs(i)),
    mbgs: [], cals: [], profiles: [{}], food: [], activity: [], dbstats: {} };
}

// ---- candidate replacements -------------------------------------------------

function fastProcessDurations (treatments, keepzeroduration) {
  const seen = new Set();
  const uniq = [];
  for (const t of treatments) {                       // O(n) dedup by mills
    if (!seen.has(t.mills)) { seen.add(t.mills); uniq.push(t); }
  }
  const sorted = uniq.slice().sort((a, b) => a.mills - b.mills);
  const cut = (base, end) => {
    if (base.mills < end.mills && base.mills + times.mins(base.duration).msecs > end.mills) {
      base.duration = times.msecs(end.mills - base.mills).mins;
      if (end.profile) { base.cuttedby = end.profile; end.cutting = base.profile; }
    }
  };
  // end events (no duration) can cut anything; carried in the same forward scan
  for (let i = 0; i < sorted.length; i++) {
    const base = sorted[i];
    if (!base.duration) continue;
    for (let j = i + 1; j < sorted.length; j++) {
      const end = sorted[j];
      if (end.mills >= base.mills + times.mins(base.duration).msecs) break;
      cut(base, end);
    }
  }
  return keepzeroduration ? uniq : uniq.filter(t => t.duration);
}

function fastCalcDelta (oldData, newData) {
  if (!oldData.sgvs) return newData;
  const ix = new Map();
  for (const o of oldData.treatments || []) ix.set(String(o._id), o);
  const saveOld = oldData.treatments;
  // Let stock calcDelta do everything except the quadratic treatment scan, which
  // we pre-resolve: if nothing changed, hand it two identical empty arrays.
  let changed = false;
  for (const n of newData.treatments || []) {
    const o = ix.get(String(n._id));
    if (!o || JSON.stringify(o) !== JSON.stringify(n)) { changed = true; break; }
  }
  if (!changed) {
    oldData = Object.assign({}, oldData, { treatments: [] });
    newData = Object.assign({}, newData, { treatments: [] });
  }
  const d = calcDelta(oldData, newData);
  oldData.treatments = saveOld;
  return d;
}

// ---- harness ----------------------------------------------------------------

function stats (s) {
  s = s.slice().sort((a, b) => a - b);
  const q = p => +s[Math.min(s.length - 1, Math.floor(s.length * p))].toFixed(3);
  return { p50: q(.5), p95: q(.95), p99: q(.99) };
}

function runArm (name, useFastDurations, useFastDelta) {
  const dd = initDdata();
  const stockDurations = dd.processDurations;
  if (useFastDurations) dd.processDurations = fastProcessDurations;
  Object.assign(dd, dd.processRawDataForRuntime(rawTenant()));
  dd.processTreatments(false);
  let lastClone = dd.dataWithRecentStatuses();
  const delta = useFastDelta ? fastCalcDelta : calcDelta;

  const samples = [];
  for (let k = 0; k < ITER; k++) {
    const fresh = { sgvs: [mkSgv(-k - 1)], treatments: k % 12 === 0 ? [mkTr(-k - 1)] : [],
      devicestatus: [mkDs(-k - 1)], mbgs: [], cals: [], profiles: [], food: [], activity: [], dbstats: {} };
    const t0 = process.hrtime.bigint();
    const p = dd.processRawDataForRuntime(fresh);
    dd.sgvs = dd.idMergePreferNew(dd.sgvs, p.sgvs);
    if (p.treatments.length) dd.treatments = dd.idMergePreferNew(dd.treatments, p.treatments);
    dd.devicestatus = dd.idMergePreferNew(dd.devicestatus, p.devicestatus);
    dd.processTreatments(false);
    const proj = dd.dataWithRecentStatuses();
    delta(lastClone, proj);
    lastClone = proj;
    const t1 = process.hrtime.bigint();
    if (k >= ITER / 5) samples.push(Number(t1 - t0) / 1e6);
  }
  dd.processDurations = stockDurations;
  return { arm: name, treatments: NTREAT, ms: stats(samples) };
}

// Correctness: the replacement must produce the same durations as the stock one.
function checkDurations () {
  const dd = initDdata();
  const src = Array.from({ length: 200 }, (_, i) => mkTr(i));
  const extra = src.slice(0, 20).map(t => ({ ...t, _id: oid(), duration: 0 }));
  const input = src.concat(extra);
  const a = dd.processDurations(input.map(o => ({ ...o })), false)
    .map(t => [t.mills, t.duration]).sort((x, y) => x[0] - y[0]);
  const b = fastProcessDurations(input.map(o => ({ ...o })), false)
    .map(t => [t.mills, t.duration]).sort((x, y) => x[0] - y[0]);
  return JSON.stringify(a) === JSON.stringify(b) ? 'MATCH' : `MISMATCH (${a.length} vs ${b.length})`;
}

console.log(JSON.stringify({
  durationsEquivalence: checkDurations(),
  arms: [
    runArm('current', false, false),
    runArm('+delta indexed', false, true),
    runArm('+both', true, true)
  ]
}, null, 2));
