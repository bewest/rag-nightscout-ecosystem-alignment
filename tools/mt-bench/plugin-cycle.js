// EXP-MT-035b: the plugin tier, which the first K measurement omitted.
//
// bootevent.js:332-341 runs this after EVERY load, per tenant:
//     var sbx = sandbox().serverInit(env, ctx);
//     ctx.plugins.setProperties(sbx);
//     ctx.notifications.initRequests();
//     ctx.plugins.checkNotifications(sbx);
//     ctx.notifications.process(sbx);
//
// serverInit alone does ctx.ddata.clone() plus a deep clone of profiles and a
// profilefunctions rebuild, so it is not free even before any plugin runs.
//
// Usage: node --expose-gc plugin-cycle.js [iterations] [treatmentCount]

'use strict';

const path = require('path');
const NS_ROOT = process.env.NS_ROOT ||
  path.resolve(__dirname, '../../externals/cgm-remote-monitor-official');

process.env.MONGODB_URI = process.env.MONGODB_URI || 'mongodb://localhost/bench';
process.env.API_SECRET = process.env.API_SECRET || 'x'.repeat(24);
// A realistic Loop/AAPS site's plugin set.
process.env.ENABLE = process.env.ENABLE ||
  'careportal boluscalc food bwp cage sage iage iob cob basal ar2 rawbg bgi delta ' +
  'direction upbat timeago devicestatus openaps loop pump speech';

const ITER = Number(process.argv[2]) || 200;
const NTREAT = Number(process.argv[3]) || 600;

const env = require(path.join(NS_ROOT, 'lib/server/env'))();
const language = require(path.join(NS_ROOT, 'lib/language'))();
language.set('en');
const levels = require(path.join(NS_ROOT, 'lib/levels'));
levels.translate = language.translate;

let idc = 0;
const oid = () => (++idc).toString(16).padStart(24, '0');
const mkSgv = i => { const n = Date.now() - i * 3e5; return { _id: oid(), device: 'xDrip-DexcomG6',
  date: n, dateString: new Date(n).toISOString(), sgv: 70 + (i * 7) % 180, delta: 1.2,
  direction: 'Flat', type: 'sgv', filtered: 180000, unfiltered: 180000, rssi: 100, noise: 1,
  sysTime: new Date(n).toISOString(), utcOffset: 0, mills: n, mgdl: 120 }; };
const mkTr = i => { const n = Date.now() - i * 6e5; return { _id: oid(), eventType: 'Temp Basal',
  duration: 30, absolute: (i % 20) / 10, rate: 0.8, created_at: new Date(n).toISOString(),
  enteredBy: 'loop://iPhone', mills: n, endmills: 0, utcOffset: 0 }; };
const mkDs = i => { const n = Date.now() - i * 3e5, iso = new Date(n).toISOString();
  return { _id: oid(), device: 'loop://iPhone', created_at: iso, mills: n,
    loop: { name: 'Loop', version: '3.4', timestamp: iso, iob: { timestamp: iso, iob: 1.2 },
      cob: { timestamp: iso, cob: 12 },
      predicted: { startDate: iso, values: Array.from({ length: 72 }, (_, k) => 80 + (i + k) % 160) },
      recommendedBolus: 0, enacted: { rate: .75, duration: 30, timestamp: iso, received: true } },
    uploader: { battery: 88 } }; };

const PROFILE = [{ _id: oid(), defaultProfile: 'Default', startDate: new Date(Date.now() - 6e8).toISOString(),
  mills: Date.now() - 6e8, store: { Default: {
    dia: 5, carbratio: [{ time: '00:00', value: 10, timeAsSeconds: 0 }],
    sens: [{ time: '00:00', value: 40, timeAsSeconds: 0 }],
    basal: [{ time: '00:00', value: 0.8, timeAsSeconds: 0 }],
    target_low: [{ time: '00:00', value: 90, timeAsSeconds: 0 }],
    target_high: [{ time: '00:00', value: 120, timeAsSeconds: 0 }],
    timezone: 'UTC', units: 'mg/dl' } } }];

function rawTenant () {
  return { sgvs: Array.from({ length: 576 }, (_, i) => mkSgv(i)),
    treatments: Array.from({ length: NTREAT }, (_, i) => mkTr(i)),
    devicestatus: Array.from({ length: 576 }, (_, i) => mkDs(i)),
    mbgs: [], cals: [], profiles: PROFILE, food: [], activity: [], dbstats: {} };
}

function makeCtx () {
  const ctx = { language, levels, runtimeState: 'loaded', settings: env.settings };
  ctx.ddata = require(path.join(NS_ROOT, 'lib/data/ddata'))();
  ctx.notifications = require(path.join(NS_ROOT, 'lib/notifications'))(env, ctx);
  ctx.plugins = require(path.join(NS_ROOT, 'lib/plugins'))(ctx).registerServerDefaults();
  ctx.bus = { emit () {} };
  Object.assign(ctx.ddata, ctx.ddata.processRawDataForRuntime(rawTenant()));
  ctx.ddata.processTreatments(false);
  return ctx;
}

function stats (s) {
  s = s.slice().sort((a, b) => a - b);
  const q = p => +s[Math.min(s.length - 1, Math.floor(s.length * p))].toFixed(3);
  return { p50: q(.5), p95: q(.95), p99: q(.99) };
}

const ctx = makeCtx();
const sandbox = require(path.join(NS_ROOT, 'lib/sandbox'));
const enabled = ctx.plugins.enabledPlugins ? ctx.plugins.enabledPlugins() : null;

const acc = { serverInit: 0, setProperties: 0, checkNotifications: 0, process: 0 };
const totals = [];

for (let k = 0; k < ITER; k++) {
  // a new reading lands, exactly as a load cycle would leave ddata
  ctx.ddata.sgvs = ctx.ddata.idMergePreferNew(ctx.ddata.sgvs,
    ctx.ddata.processRawDataForRuntime({ sgvs: [mkSgv(-k - 1)] }).sgvs);

  const t0 = process.hrtime.bigint();
  const sbx = sandbox().serverInit(env, ctx);
  const t1 = process.hrtime.bigint();
  ctx.plugins.setProperties(sbx);
  const t2 = process.hrtime.bigint();
  ctx.notifications.initRequests();
  ctx.plugins.checkNotifications(sbx);
  const t3 = process.hrtime.bigint();
  ctx.notifications.process(sbx);
  const t4 = process.hrtime.bigint();

  if (k >= ITER / 5) {
    acc.serverInit += Number(t1 - t0);
    acc.setProperties += Number(t2 - t1);
    acc.checkNotifications += Number(t3 - t2);
    acc.process += Number(t4 - t3);
    totals.push(Number(t4 - t0) / 1e6);
  }
}

const n = totals.length;
const tot = Object.values(acc).reduce((a, b) => a + b, 0);
console.log(JSON.stringify({
  experiment: 'EXP-MT-035b plugin tier',
  treatments: NTREAT,
  enabledPluginCount: Array.isArray(enabled) ? enabled.length : (env.settings.enable || []).length,
  enable: env.settings.enable,
  meanMsByStage: Object.fromEntries(Object.entries(acc)
    .map(([k, v]) => [k, +(v / n / 1e6).toFixed(3)])),
  sharePct: Object.fromEntries(Object.entries(acc)
    .map(([k, v]) => [k, +((v / tot) * 100).toFixed(1)])),
  totalMs: stats(totals)
}, null, 2));
