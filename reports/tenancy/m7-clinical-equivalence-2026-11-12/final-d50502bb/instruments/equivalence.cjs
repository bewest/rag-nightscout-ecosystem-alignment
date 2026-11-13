'use strict';

// Lane EV equivalence lab (cost-proportional-to-activity): does evaluating on
// due times give the same clinical output as the one-second time tick?
//
// The actual evaluator component (lib/data/tenant-projection-evaluator.js:
// real views, real server plugins, projection reads on actual PostgreSQL) over
// one recorded synthetic 12-hour timeline, run twice:
//   base  a time-only cycle every 1000 ms (the removed per-tenant poll);
//   due   a time-only cycle only at the component's due instant, or on the
//         slow timer (SLOW_MS) while the output changes continuously.
// In both, a write is acquired at the first whole second at or after it (the
// write-to-evaluation latency is measured separately, on the runtime).
//
// Compared, from the evaluator's own output (result.requested):
//   alarm set   [plugin, level, group, title] of every notify request;
//   content     the full requested rows (messages included).
// Equivalent: the same sequence of sets, and each transition in `due` at or
// before the base's and less than 1000 ms earlier (the base tick quantum).
//
//   CRM_ROOT=<crm worktree> NS_TEST_POSTGRES_ADMIN_URI=<disposable db> SLOW_MS=1000 node equivalence.cjs
//   HOURS=12 (timeline length)  OUT=<json path> (per-cycle cost records)
// Synthetic data only.
const path = require('node:path'), fs = require('node:fs');
const ROOT = process.env.CRM_ROOT;
if (!ROOT || !process.env.NS_TEST_POSTGRES_ADMIN_URI) { process.stderr.write('CRM_ROOT and NS_TEST_POSTGRES_ADMIN_URI required\n'); process.exit(2); }
const req = p => require(path.join(ROOT, p));
const { Pool } = req('node_modules/pg');
const scope = req('lib/storage/tenant-scope');
const evaluator = req('lib/data/tenant-projection-evaluator');
const environment = req('lib/server/tenant-app/environment');
// Plugins that read the wall clock (treatmentnotify isCurrent, loop/openaps
// message formatAgo, xdripjs) see the evaluation instant, as in deployment
// where the instant is the current time (the views-replay lab's pinned clock).
const clock = req('tests/lib/views-replay/clock');

const TENANT = '5e5e5e5e-0000-4000-8000-00000000e001';
const SLOWS = (process.env.SLOWS || '1000').split(',').map(Number), HOURS = Number(process.env.HOURS || 12);
const DROP = new Set((process.env.DROP_PLUGINS || '').split(',').filter(Boolean));
const RealNow = () => (clock ? clock.RealDate.now() : Date.now());
const say = (...args) => process.stdout.write(args.join(' ') + '\n');
// The legacy notification processing logs every emission; keep the lab output readable.
console.log = () => {}; console.info = () => {};
const MIN = 60000, HOUR = 60 * MIN;
const t0 = Date.UTC(2026, 10, 10, 0, 0, 0), tEnd = t0 + HOURS * HOUR;
const iso = ms => new Date(ms).toISOString();

// ---- the recorded synthetic timeline: [writeAt, domain, document] ----
function timeline () {
  const rows = [];
  const write = (at, domain, doc) => rows.push([at, domain, doc]);
  write(t0 - 2 * HOUR, 'profile', { _id: 'synthetic-profile', defaultProfile: 'Default', startDate: iso(t0 - 2 * 86400000), created_at: iso(t0 - 2 * HOUR),
    mills: t0 - 2 * HOUR, units: 'mg/dl', store: { Default: { dia: 3, carbratio: [{ time: '00:00', value: 10 }], sens: [{ time: '00:00', value: 50 }],
      basal: [{ time: '00:00', value: 1 }], target_low: [{ time: '00:00', value: 100 }], target_high: [{ time: '00:00', value: 120 }], timezone: 'UTC', units: 'mg/dl' } } });
  const sgv = at => {
    const m = (at - t0) / MIN;
    if (m >= 60 && m < 80) return 50; // urgent low
    if (m >= 120 && m < 140) return 262; // urgent high
    return Math.round(140 + 30 * Math.sin(m / 40));
  };
  // CGM every 5 min and loop/pump/uploader device status, then gaps.
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
    enable: ['bgnow', 'delta', 'direction', 'rawbg', 'timeago', 'simplealarms', 'ar2', 'errorcodes', 'treatmentnotify',
      'cage', 'sage', 'iage', 'bage', 'pump', 'loop', 'upbat', 'iob', 'cob', 'bwp', 'basal', 'profile', 'devicestatus'].filter(name => !DROP.has(name)) },
  extendedSettings: { timeago: { enableAlerts: true }, cage: age(2, 3, 4), sage: age(5, 6, 7), iage: age(6, 7, 8), bage: age(9, 10, 11),
    loop: { enableAlerts: true, warn: 30, urgent: 60 }, pump: { enableAlerts: true, warnClock: 30, urgentClock: 60 } } });
}

const alarmSet = result => (result.requested || []).filter(r => r.kind === 'notify')
  .map(r => [r.plugin?.name || r.eventName || null, r.level, r.group || null, r.title].join('|')).sort();
const content = result => JSON.stringify((result.requested || []).map(r => [r.kind, r.plugin?.name || null, r.level, r.group || null, r.title, r.message, r.lengthMills ?? null]));

async function run (mode, pool, rows, SLOW_MS) {
  const ENV = env();
  const language = req('lib/language')(); language.set('en');
  let checkpoint = 0;
  const written = new Map(); let pending = 0;
  const replay = { async reconcile () {
    return { checkpoint, progress: 'current-snapshot', rows: [...written.values()], signature: { stamp: checkpoint, rows: written.size, digest: String(checkpoint) } };
  } };
  const connection = { query: (text, values) => pool.query(text, values) };
  const component = evaluator({ tenant: TENANT, replay, connection, env: ENV, language, maxRows: 10000, maxBytes: 16 * 1024 * 1024,
    dbstats: async () => ({ dataSize: 10000, indexSize: 1000 }) });
  const writeTicks = [];
  for (const [at] of rows) { const tick = Math.ceil(at / 1000) * 1000; if (writeTicks.at(-1) !== tick) writeTicks.push(tick); }
  let wi = 0, ri = 0;
  const cycles = []; let last = null;
  const transitions = [], contents = [];
  async function cycle (at, acquire) {
    while (ri < rows.length && rows[ri][0] <= at) { const [w, domain, document] = rows[ri++]; written.set(domain + '/' + document._id, { domain, document }); checkpoint = w; pending++; }
    clock.pin(at);
    const cpu = process.cpuUsage(), wall = process.hrtime.bigint();
    const result = await scope.withTenant(TENANT, () => acquire ? component.evaluate({ at }) : component.evaluateTime({ at }));
    const used = process.cpuUsage(cpu), ms = Number(process.hrtime.bigint() - wall) / 1e6;
    cycles.push({ at, acquire, cpuMs: (used.user + used.system) / 1000, wallMs: ms, rows: written.size });
    const set = alarmSet(result), text = content(result);
    if (!last || JSON.stringify(set) !== JSON.stringify(last.set)) transitions.push({ at, set });
    if (!last || text !== last.text) contents.push({ at, text });
    last = { set, text };
    return result;
  }
  const start = t0 - HOUR;
  let at = start, result = await cycle(at, true);
  while (wi < writeTicks.length && writeTicks[wi] <= at) wi++;
  if (mode === 'base') {
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
  component.close();
  return { mode, cycles, transitions, contents };
}

function compare (base, due, key) {
  const a = base[key], b = due[key], field = key === 'transitions' ? 'set' : 'text';
  const problems = [];
  if (a.length !== b.length) problems.push(key + ' count base ' + a.length + ' due ' + b.length);
  let maxEarlyMs = 0;
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    if (JSON.stringify(a[i][field]) !== JSON.stringify(b[i][field])) { problems.push(key + '[' + i + '] differs at base ' + iso(a[i].at) + ' due ' + iso(b[i].at) + ': ' + JSON.stringify(a[i][field]).slice(0, 160) + ' vs ' + JSON.stringify(b[i][field]).slice(0, 160)); break; }
    const early = a[i].at - b[i].at;
    if (early < 0 || early >= 1000) {
      const before = i ? JSON.stringify(a[i - 1][field]) : null, after = JSON.stringify(a[i][field]);
      let from = 0; while (before && from < after.length && before[from] === after[from]) from++;
      problems.push(key + '[' + i + '] at base ' + iso(a[i].at) + ' due ' + iso(b[i].at) + ' (' + (b[i].at - a[i].at) + ' ms late); changed text: ' + after.slice(Math.max(0, from - 80), from + 160));
    }
    maxEarlyMs = Math.max(maxEarlyMs, early);
  }
  return { problems, maxEarlyMs };
}

function summary (r) {
  const by = kind => r.cycles.filter(c => (kind === 'acquisition') === c.acquire);
  const stats = list => {
    if (!list.length) return null;
    const cpu = list.map(c => c.cpuMs).sort((x, y) => x - y), wall = list.map(c => c.wallMs).sort((x, y) => x - y);
    const q = (v, p) => +v[Math.min(v.length - 1, Math.floor(p * v.length))].toFixed(2);
    return { n: list.length, cpuMsMean: +(cpu.reduce((s, x) => s + x, 0) / cpu.length).toFixed(2), cpuMsP50: q(cpu, 0.5), cpuMsP95: q(cpu, 0.95), wallMsP50: q(wall, 0.5), wallMsP95: q(wall, 0.95) };
  };
  return { cycles: r.cycles.length, acquisitions: stats(by('acquisition')), timeOnly: stats(by('time')), alarmTransitions: r.transitions.length, contentTransitions: r.contents.length };
}

(async () => {
  const pool = new Pool({ connectionString: process.env.NS_TEST_POSTGRES_ADMIN_URI, max: 2 });
  scope.setTenancyMode('multi'); clock.install();
  const rows = timeline();
  say('LAB hours=' + HOURS + ' drop=' + ([...DROP].join(',') || '-') + ' records=' + rows.length + ' load=' + require('node:os').loadavg().map(x => x.toFixed(2)).join(' '));
  const results = {};
  let started = RealNow();
  results.base = await run('base', pool, rows, 1000);
  say('RUN base', JSON.stringify(summary(results.base)), 'elapsed_s=' + ((RealNow() - started) / 1000).toFixed(1));
  say('TRANSITIONS base\n  ' + results.base.transitions.map(t => iso(t.at).slice(11, 19) + ' ' + (t.set.join(';') || '(none)')).join('\n  '));
  for (const slow of SLOWS) {
    started = RealNow();
    const due = results['due-' + slow] = await run('due', pool, rows, slow);
    say('RUN due slow=' + slow, JSON.stringify(summary(due)), 'elapsed_s=' + ((RealNow() - started) / 1000).toFixed(1));
    const alarms = compare(results.base, due, 'transitions');
    say((alarms.problems.length ? 'FAIL' : 'PASS') + ' ALARM_SET_EQUIVALENT slow=' + slow + ' :: ' + results.base.transitions.length + ' transitions, due at most ' + alarms.maxEarlyMs + ' ms before base' + (alarms.problems.length ? '\n  ' + alarms.problems.slice(0, 8).join('\n  ') : ''));
    const text = compare(results.base, due, 'contents');
    say((text.problems.length ? 'DIFF' : 'PASS') + ' CONTENT_EQUIVALENT slow=' + slow + ' :: ' + results.base.contents.length + ' base content transitions, ' + due.contents.length + ' due' + (text.problems.length ? '\n  ' + text.problems.slice(0, 3).join('\n  ') : ''));
    say('CYCLES slow=' + slow + ' base ' + results.base.cycles.length + ' due ' + due.cycles.length + ' (' + (results.base.cycles.length / due.cycles.length).toFixed(1) + 'x fewer)');
  }
  await pool.end();
  if (process.env.OUT) fs.writeFileSync(process.env.OUT, JSON.stringify(Object.fromEntries(Object.entries(results).map(([k, v]) => [k, { summary: summary(v), transitions: v.transitions.map(t => ({ at: iso(t.at), set: t.set })) }])), null, 1));
})().catch(error => { console.error(error); process.exit(1); });
