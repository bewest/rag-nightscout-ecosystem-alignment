'use strict';

// Evaluator cost lane: cross-tree clinical-equivalence trace.
//
// Runs the actual evaluator component (lib/data/tenant-projection-evaluator.js,
// real views, real server plugins, projection reads on actual PostgreSQL) over
// the same recorded synthetic timeline as ../perf-evaluator/equivalence.cjs
// (one hour of lead-in, then HOURS hours: 13 hours by default), and writes ONE
// LINE PER CYCLE:
//
//   <instant ms> <A|T> <sha256 of the full output> <alarm set>
//
// The full output is { emitted, requested, properties, due } of every cycle:
// every notification request and its message text, every emitted
// notification, every plugin property (the pill values and their text), and
// the next due instant. Two trees are clinically equivalent on this timeline
// when their traces are byte-identical (compare.cjs); the alarm set column is
// for reading a difference, not for the verdict.
//
// MODE=base   a cycle every 1000 ms (acquisition when a write landed)
// MODE=due    a cycle at the component's due instant, or SLOW_MS while the
//             output changes continuously (as equivalence.cjs `due`)
//
//   CRM_ROOT=<crm tree> NS_TEST_POSTGRES_ADMIN_URI=<disposable db> PLUGINS=deploy|full MODE=base|due SLOW_MS=1000 OUT=<file> node trace.cjs
//
// Synthetic data only.
const path = require('node:path'), fs = require('node:fs'), crypto = require('node:crypto');
const ROOT = process.env.CRM_ROOT;
if (!ROOT || !process.env.NS_TEST_POSTGRES_ADMIN_URI || !process.env.OUT) { process.stderr.write('CRM_ROOT, NS_TEST_POSTGRES_ADMIN_URI and OUT required\n'); process.exit(2); }
const req = p => require(path.join(ROOT, p));
const { Pool } = req('node_modules/pg');
const scope = req('lib/storage/tenant-scope');
const evaluator = req('lib/data/tenant-projection-evaluator');
const environment = req('lib/server/tenant-app/environment');
const clock = req('tests/lib/views-replay/clock');
console.log = () => {}; console.info = () => {};

const TENANT = '5e5e5e5e-0000-4000-8000-00000000e001';
const HOURS = Number(process.env.HOURS || 12), MODE = process.env.MODE || 'base', SLOW_MS = Number(process.env.SLOW_MS || 1000);
const PLUGINS = process.env.PLUGINS || 'full';
const MIN = 60000, HOUR = 60 * MIN;
const t0 = Date.UTC(2026, 10, 10, 0, 0, 0), tEnd = t0 + HOURS * HOUR;
const iso = ms => new Date(ms).toISOString();
const FULL = ['bgnow', 'delta', 'direction', 'rawbg', 'timeago', 'simplealarms', 'ar2', 'errorcodes', 'treatmentnotify',
  'cage', 'sage', 'iage', 'bage', 'pump', 'loop', 'upbat', 'iob', 'cob', 'bwp', 'basal', 'profile', 'devicestatus'];
const DEPLOY = ['bgnow', 'delta', 'direction', 'simplealarms', 'treatmentnotify'];

// The timeline of ../perf-evaluator/equivalence.cjs, unchanged.
function timeline () {
  const rows = [];
  const write = (at, domain, doc) => rows.push([at, domain, doc]);
  write(t0 - 2 * HOUR, 'profile', { _id: 'synthetic-profile', defaultProfile: 'Default', startDate: iso(t0 - 2 * 86400000), created_at: iso(t0 - 2 * HOUR),
    mills: t0 - 2 * HOUR, units: 'mg/dl', store: { Default: { dia: 3, carbratio: [{ time: '00:00', value: 10 }], sens: [{ time: '00:00', value: 50 }],
      basal: [{ time: '00:00', value: 1 }], target_low: [{ time: '00:00', value: 100 }], target_high: [{ time: '00:00', value: 120 }], timezone: 'UTC', units: 'mg/dl' } } });
  const sgv = at => {
    const m = (at - t0) / MIN;
    if (m >= 60 && m < 80) return 50;
    if (m >= 120 && m < 140) return 262;
    return Math.round(140 + 30 * Math.sin(m / 40));
  };
  const live = at => (at < t0 + 3 * HOUR) || (at >= t0 + 4 * HOUR && at < t0 + 8 * HOUR);
  for (let at = t0 - HOUR; at < tEnd; at += 5 * MIN) {
    if (!live(at)) continue;
    write(at + 20000, 'entries', { _id: 'sgv-' + at, type: 'sgv', sgv: sgv(at), date: at, dateString: iso(at), direction: 'Flat', device: 'synthetic-cgm' });
    write(at + 40000, 'devicestatus', { _id: 'ds-' + at, created_at: iso(at + 30000), device: 'synthetic-loop',
      uploader: { battery: 60 - Math.floor((at - t0) / HOUR) },
      pump: { clock: iso(at + 30000), reservoir: 100 - (at - t0) / HOUR, battery: { percent: 80 } },
      loop: { timestamp: iso(at + 30000), iob: { timestamp: iso(at + 30000), iob: 0.5 }, cob: { cob: 0 },
        predicted: { startDate: iso(at), values: [sgv(at), sgv(at), sgv(at)] },
        enacted: { timestamp: iso(at + 30000), rate: 1, duration: 30, received: true } } });
  }
  const treatment = (at, doc) => write(at + 10000, 'treatments', { _id: 'tr-' + doc.eventType.replace(/\W/g, '') + '-' + at, created_at: iso(at), ...doc });
  treatment(t0 - 1 * HOUR, { eventType: 'Site Change' });
  treatment(t0 - 2 * HOUR, { eventType: 'Sensor Change' });
  treatment(t0 - 30 * MIN, { eventType: 'Insulin Change' });
  treatment(t0, { eventType: 'Pump Battery Change' });
  treatment(t0 + 90 * MIN, { eventType: 'Correction Bolus', insulin: 2 });
  treatment(t0 + 250 * MIN, { eventType: 'Meal Bolus', insulin: 4, carbs: 40 });
  write(t0 + 5 * HOUR + 20000, 'entries', { _id: 'mbg-1', type: 'mbg', mbg: 150, date: t0 + 5 * HOUR, dateString: iso(t0 + 5 * HOUR), device: 'synthetic-meter' });
  return rows.sort((a, b) => a[0] - b[0]);
}

function env () {
  const age = (info, warn, urgent) => ({ enableAlerts: true, info, warn, urgent });
  return environment({ settings: {
    units: 'mg/dl', thresholds: { bgHigh: 250, bgTargetTop: 180, bgTargetBottom: 80, bgLow: 55 },
    alarmUrgentHigh: true, alarmHigh: true, alarmLow: true, alarmUrgentLow: true,
    alarmTimeagoWarn: true, alarmTimeagoWarnMins: 15, alarmTimeagoUrgent: true, alarmTimeagoUrgentMins: 30,
    enable: PLUGINS === 'deploy' ? DEPLOY : FULL },
  extendedSettings: { timeago: { enableAlerts: true }, cage: age(2, 3, 4), sage: age(5, 6, 7), iage: age(6, 7, 8), bage: age(9, 10, 11),
    loop: { enableAlerts: true, warn: 30, urgent: 60 }, pump: { enableAlerts: true, warnClock: 30, urgentClock: 60 } } });
}

const alarmSet = result => (result.requested || []).filter(r => r.kind === 'notify')
  .map(r => [r.plugin?.name || r.eventName || null, r.level, r.group || null, r.title].join('|')).sort().join(';') || '-';
// Functions (plugin objects carry them) drop out of JSON; everything a client or a notification sees stays.
const full = result => JSON.stringify({ emitted: result.emitted, requested: result.requested, properties: result.properties, due: result.due });

(async () => {
  const pool = new Pool({ connectionString: process.env.NS_TEST_POSTGRES_ADMIN_URI, max: 2 });
  scope.setTenancyMode('multi'); clock.install();
  const rows = timeline();
  const language = req('lib/language')(); language.set('en');
  let checkpoint = 0;
  const written = new Map();
  // Each row's per-tenant insertion ordinal: its first write's sequence (an
  // update keeps the row, as PostgreSQL's upsert does). A tree that predates
  // decision view-reads-total-order ignores it.
  let ordinals = 0;
  const replay = { async reconcile () {
    return { checkpoint, progress: 'current-snapshot', rows: [...written.values()], signature: { stamp: checkpoint, rows: written.size, digest: String(checkpoint) } };
  } };
  const component = evaluator({ tenant: TENANT, replay, connection: { query: (text, values) => pool.query(text, values) }, env: env(), language,
    maxRows: 10000, maxBytes: 16 * 1024 * 1024, dbstats: async () => ({ dataSize: 10000, indexSize: 1000 }) });
  const writeTicks = [];
  for (const [at] of rows) { const tick = Math.ceil(at / 1000) * 1000; if (writeTicks.at(-1) !== tick) writeTicks.push(tick); }
  const out = fs.openSync(process.env.OUT, 'w');
  let wi = 0, ri = 0, n = 0, cpuMs = 0;
  const started = clock.RealDate.now();
  async function cycle (at, acquire) {
    while (ri < rows.length && rows[ri][0] <= at) { const [w, domain, document] = rows[ri++]; const key = domain + "/" + document._id; written.set(key, { domain, document, ordinal: written.has(key) ? written.get(key).ordinal : ++ordinals }); checkpoint = w; }
    clock.pin(at);
    const cpu = process.cpuUsage();
    const result = await scope.withTenant(TENANT, () => acquire ? component.evaluate({ at }) : component.evaluateTime({ at }));
    const used = process.cpuUsage(cpu); cpuMs += (used.user + used.system) / 1000; n++;
    fs.writeSync(out, at + ' ' + (acquire ? 'A' : 'T') + ' ' + crypto.createHash('sha256').update(full(result)).digest('hex').slice(0, 32) + ' ' + alarmSet(result) + '\n');
    return result;
  }
  const start = t0 - HOUR;
  let at = start, result = await cycle(at, true);
  while (wi < writeTicks.length && writeTicks[wi] <= at) wi++;
  if (MODE === 'base') {
    for (at = start + 1000; at <= tEnd; at += 1000) {
      const acquire = wi < writeTicks.length && writeTicks[wi] === at;
      if (acquire) wi++;
      result = await cycle(at, acquire);
    }
  } else {
    for (;;) {
      const due = result.due;
      let next = due && Number.isFinite(due.dueAt) ? due.dueAt : Infinity;
      if (due && due.slow.length) next = Math.min(next, at + SLOW_MS);
      const nextWrite = wi < writeTicks.length ? writeTicks[wi] : Infinity;
      const t = Math.min(next, nextWrite);
      if (!(t <= tEnd)) break;
      const acquire = t === nextWrite;
      if (acquire) wi++;
      at = t; result = await cycle(at, acquire);
    }
  }
  component.close(); fs.closeSync(out); await pool.end();
  process.stdout.write('TRACE plugins=' + PLUGINS + ' mode=' + MODE + (MODE === 'due' ? ' slow=' + SLOW_MS : '') + ' cycles=' + n +
    ' cpuMsMean=' + (cpuMs / n).toFixed(2) + ' elapsed_s=' + ((clock.RealDate.now() - started) / 1000).toFixed(1) +
    ' load=' + require('node:os').loadavg().map(x => x.toFixed(2)).join(' ') + '\n');
})().catch(error => { process.stderr.write(String(error.stack || error) + '\n'); process.exit(1); });
