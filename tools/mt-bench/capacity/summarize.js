#!/usr/bin/env node
'use strict';
// Folds one capacity run directory (<label>-n<N>) into summary.json. Reads only files the run wrote.
//   summarize.js <run-dir> <N>
const fs = require('node:fs'), path = require('node:path');
const [dir, Nraw] = process.argv.slice(2); const N = Number(Nraw);
const read = f => { try { return fs.readFileSync(path.join(dir, f), 'utf8'); } catch { return null; } };
const json = f => { const t = read(f); try { return t ? JSON.parse(t) : null; } catch { return null; } };
const kv = f => Object.fromEntries((read(f) || '').split('\n').filter(l => l.includes('=')).map(l => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)]));
const r1 = x => x == null ? null : Math.round(x * 10) / 10;
const ROLES = ['api', 'realtime', 'evaluator', 'tenant-admin', 'postgres', 'nginx'];

function phase (prefix, before, after) {
  const a = json(before), b = json(after); if (!a || !b) return null;
  const minutes = (b.at - a.at) / 60000;
  const roles = {};
  for (const r of ROLES) {
    if (!a[r] || !b[r]) continue;
    const cpuMs = (b[r].cpuUsec - a[r].cpuUsec) / 1000;
    roles[r] = { cpuMsPerMin: r1(cpuMs / minutes), cpuMsPerTenantMin: Math.round(cpuMs / minutes / N * 1000) / 1000, cpuCores: Math.round(cpuMs / minutes / 60000 * 1000) / 1000,
      memMiB: r1(b[r].memoryCurrent / 1048576), anonMiB: r1(b[r].anon / 1048576), anonMiBPerTenant: Math.round(b[r].anon / 1048576 / N * 1000) / 1000 };
  }
  const db = {}; let dbMs = 0;
  for (const line of (read(prefix + '-pg-by-role.tsv') || '').split('\n').filter(Boolean)) {
    const [role, calls, ms] = line.split('\t'); db[role.replace(/^nsdemo_/, '')] = { calls: Number(calls), ms: Number(ms) }; dbMs += Number(ms);
  }
  const conns = {}; let connTotal = 0;
  for (const line of (read(prefix + '-pg-conns.tsv') || '').split('\n').filter(Boolean)) {
    const [user, , n] = line.split('\t'); conns[user || '(none)'] = (conns[user || '(none)'] || 0) + Number(n); connTotal += Number(n);
  }
  return { minutes: r1(minutes), roles, dbMsPerTenantMin: Math.round(dbMs / minutes / N * 1000) / 1000, dbMsTotal: r1(dbMs), dbByRole: db, connections: connTotal, connectionsByIdentity: conns };
}
function maxConnections (f) {
  const by = new Map();
  for (const line of (read(f) || '').split('\n').slice(1).filter(Boolean)) { const [t, , backends] = line.split('\t'); by.set(t, Number(backends)); }
  return by.size ? Math.max(...by.values()) : null;
}
function loadRange (f) {
  const v = (read(f) || '').split('\n').slice(1).filter(Boolean).map(l => Number(l.split('\t')[1]));
  return v.length ? { min: Math.min(...v), max: Math.max(...v), mean: r1(v.reduce((a, b) => a + b, 0) / v.length) } : null;
}
function k6 () {
  const s = json('load/k6-summary.json'); if (!s) return null;
  const m = s.metrics; const out = {};
  const names = { 'POST v1 entries': 'w_sgv', 'POST v1 devicestatus': 'w_devicestatus', 'GET v1 sgv': 'r_sgv', 'GET v1 devicestatus': 'r_devicestatus', 'GET v1 treatments': 'r_treatments', 'GET v1 status': 'r_status' };
  for (const [label, shape] of Object.entries(names)) {
    const d = m[`http_req_duration{shape:${shape}}`]; const f = m[`http_req_failed{shape:${shape}}`];
    if (!d) continue;
    out[label] = { n: d.count, p50: r1(d.med), p95: r1(d['p(95)']), p99: r1(d['p(99)']), max: r1(d.max), failedRate: f ? f.value ?? f.rate : null };
  }
  out.iterations = m.iterations?.count; out.droppedIterations = m.dropped_iterations?.count || 0;
  out.writesOk = m.writes_ok?.count || 0; out.writesUncertain = m.writes_uncertain?.count || 0; out.writesRefused = m.writes_refused?.count || 0;
  return out;
}
function diag () {
  const text = read('load/realtime.log'); const restartAt = Number(read('load/.restart-at') || 0); if (!text || !restartAt) return null;
  const lines = text.split('\n').filter(l => l.includes('DIAG {')).map(l => { try { return JSON.parse(l.slice(l.indexOf('DIAG ') + 5)); } catch { return null; } }).filter(Boolean);
  // Only the new realtime process: DIAG lines from its listener open onward (restart-startup.json).
  const listen = json('load/restart-startup.json')?.roles?.realtime?.listenerOpenMs;
  const from = restartAt + (listen || 0);
  const after = lines.filter(d => d.t >= from); if (!after.length) return null;
  const at = s => after.filter(d => d.t <= restartAt + s * 1000).at(-1) || null;
  const firstWhere = f => { const d = after.find(f); return d ? d.t - restartAt : null; };
  const failedSeen = after.filter(d => d.s && d.s.failed > 0);
  // health().ready is a boolean (the count is overridden): all ready = nothing warming, cold, deferred or failed.
  const startupAllReadyMs = firstWhere(d => d.s && d.s.warming + d.s.cold + d.s.deferred + d.s.failed === 0);
  const failedFirstMs = failedSeen.length ? failedSeen[0].t - restartAt : null;
  const tlines = text.split("\n").filter(l => { const m = /(\d{4}-\d\d-\d\dT[0-9:.]+Z)/.exec(l); return m && Date.parse(m[1]) >= restartAt; });
  return {
    // Realtime after the full restart, from the instrument's 1 s DIAG line:
    // s = tenant-startup state (the warm), h = runtime cells (refresh), p = protocol counters.
    startupAllReadyMs, runtimeAllHealthyMs: firstWhere(d => d.h && d.h.healthy === N),
    startupFailedMax: failedSeen.length ? Math.max(...failedSeen.map(d => d.s.failed)) : 0,
    failedFirstSeenMs: failedFirstMs, failedLastSeenMs: failedSeen.length ? failedSeen.at(-1).t - restartAt : null,
    failedRecoveredBeforeRetry: failedFirstMs === null ? null : (startupAllReadyMs !== null && startupAllReadyMs - failedFirstMs < 30000),
    failedTimeline: after.filter((d, i) => i % 10 === 0).map(d => [Math.round((d.t - restartAt) / 1000), d.s ? d.s.failed : null, d.s ? d.s.warming + d.s.cold : null, d.h ? d.h.healthy : null, d.p ? d.p.primed : null]),
    // Every 10 s from the restart command: [s, sockets held by realtime, authorize calls in flight, recheckFailures (cumulative), cold+warming tenants, primed sockets].
    socketTimelineColumns: ['s', 'sockets', 'authorizeInFlight', 'recheckFailures', 'coldOrWarming', 'primed'],
    socketTimeline: after.filter((d, i) => i % 10 === 0).map(d => [Math.round((d.t - restartAt) / 1000), d.p?.sockets ?? null, d.p?.authorizeInFlight ?? null, d.p?.recheckFailures ?? null, d.s ? d.s.warming + d.s.cold : null, d.p?.primed ?? null]),
    authorizeInFlightMax: Math.max(0, ...after.map(d => d.p?.authorizeInFlight || 0)), recheckFailuresEnd: after.at(-1)?.p?.recheckFailures ?? null,
    tenantWarmFailedAlerts: tlines.filter(l => l.includes("TENANT_WARM_FAILED")).length,
    drainedLines: tlines.filter(l => l.includes('Tenant warm drained')).map(l => l.slice(l.indexOf('Tenant warm drained')).slice(0, 120)),
    at30s: at(30), at60s: at(60), at120s: at(120), last: after.at(-1) };
}
// Realtime config re-read cost (instrument realtime-config-stats.js, 5517cb6c runs): whole-file reads by caller
// per second and their wall time, against the realtime process's own CPU, over the idle and load windows.
function cfgReads () {
  const text = read('load/realtime.log'); if (!text) return null;
  const lines = text.split('\n').filter(l => l.includes('DIAG {')).map(l => { try { return JSON.parse(l.slice(l.indexOf('DIAG ') + 5)); } catch { return null; } }).filter(d => d && d.cfg && d.cpu);
  if (!lines.length) return null;
  const restartAt = Number(read('load/.restart-at') || 0) || Infinity;
  const win = (a, b) => {
    const A = json(a), B = json(b); if (!A || !B) return null;
    const pre = lines.filter(d => d.t < restartAt);
    const s = pre.filter(d => d.t >= A.at)[0], e = pre.filter(d => d.t <= B.at).at(-1); if (!s || !e || e.t <= s.t) return null;
    const sec = (e.t - s.t) / 1000, out = { seconds: r1(sec) };
    let ns = 0;
    for (const k of ['readCurrent', 'readAll']) { const calls = e.cfg[k].calls - s.cfg[k].calls, kn = e.cfg[k].ns - s.cfg[k].ns; ns += kn;
      out[k] = { callsPerSec: r1(calls / sec), msPerCall: calls ? Math.round(kn / calls / 1e4) / 100 : null, msPerSec: r1(kn / 1e6 / sec) }; }
    const cpuMs = ((e.cpu.user + e.cpu.system) - (s.cpu.user + s.cpu.system)) / 1000;
    out.realtimeCpuMsPerSec = r1(cpuMs / sec); out.readShareOfRealtimeCpu = cpuMs ? Math.round(ns / 1e6 / cpuMs * 1000) / 1000 : null;
    return out;
  };
  return { idle: win('idle/cgroups-before.json', 'idle/cgroups-after.json'), load: win('load/cgroups-before.json', 'load/cgroups-after.json') };
}
// Alert codes after the restart phase, per role: log lines (every role) and, where instrumented, the
// tenant-startup health() alert causes (realtime DIAG `a`, api DIAGAPI `a`) at their worst and at the end.
function alertsAfterRestart () {
  const restartAt = Number(read('load/.restart-at') || 0); if (!restartAt) return null;
  const out = {};
  for (const role of ['api', 'realtime', 'evaluator', 'tenant-admin']) {
    const text = read('load/' + role + '.log'); if (!text) continue;
    const after = text.split('\n').filter(l => { const m = /(\d{4}-\d\d-\d\dT[0-9:.]+Z)/.exec(l); return m && Date.parse(m[1]) >= restartAt; });
    const codes = {};
    for (const l of after) { const m = /(Tenant readiness alert|Evaluator alert|Evaluator stopped for tenant \S+:) ([A-Z][A-Z0-9_]+)/.exec(l); if (m) { const k = m[1].replace(/ for tenant \S+:/, '') + ' ' + m[2]; codes[k] = (codes[k] || 0) + 1; } }
    const r = { logAlertCodes: codes, drained: after.filter(l => l.includes('Tenant warm drained')).map(l => l.slice(l.indexOf('Tenant warm drained')).slice(0, 120)) };
    const tag = role === 'api' ? 'DIAGAPI {' : role === 'realtime' ? 'DIAG {' : null;
    if (tag) {
      // Only the new process: from its listener open (restart-startup.json), as diag() does.
      const listen = json('load/restart-startup.json')?.roles?.[role]?.listenerOpenMs;
      const from = restartAt + (listen || 0);
      const d = after.filter(l => l.includes(tag)).map(l => { try { return JSON.parse(l.slice(l.indexOf(tag) + tag.length - 1)); } catch { return null; } }).filter(x => x && x.s && x.t >= from);
      if (d.length) {
        const worst = d.reduce((a, b) => (b.s.failed > a.s.failed ? b : a), d[0]);
        r.startupHealth = { worstFailed: worst.s.failed, worstAtMs: worst.t - restartAt, worstCauses: worst.a || {}, end: d.at(-1).s, endCauses: d.at(-1).a || {},
          fromMs: from - restartAt, allReadyMs: (() => { const x = d.find(x => x.s.warming + x.s.cold + x.s.deferred + x.s.failed === 0); return x ? x.t - restartAt : null; })() };
      }
    }
    out[role] = r;
  }
  out.realtimeHealthEndpoint = json('load/realtime-health-after.json');
  return out;
}
// Main-thread saturation (instruments, 5c60aec6 runs with DIAGAPI elu/threads and realtime DIAG elu): per window,
// event-loop utilization mean/max, event-loop delay p99 (max of 2 s intervals), and process CPU split by thread
// (main JavaScript thread vs the rest: GC, libuv pool, compiler), in cores.
function mainThread () {
  const restartAt = Number(read('load/.restart-at') || 0) || Infinity;
  const parse = (file, tag) => (read(file) || '').split('\n').filter(l => l.includes(tag)).map(l => { try { return JSON.parse(l.slice(l.indexOf(tag) + tag.length - 1)); } catch { return null; } }).filter(d => d && d.elu !== undefined && d.t < restartAt);
  const api = parse('load/api.log', 'DIAGAPI {'), rt = parse('load/realtime.log', 'DIAG {');
  const win = (rows, a, b) => {
    const A = json(a), B = json(b); if (!A || !B || !rows.length) return null;
    const w = rows.filter(d => d.t >= A.at && d.t <= B.at); if (w.length < 2) return null;
    const sec = (w.at(-1).t - w[0].t) / 1000, out = { samples: w.length,
      eluMean: Math.round(w.reduce((s, d) => s + d.elu, 0) / w.length * 1000) / 1000, eluMax: Math.max(...w.map(d => d.elu)),
      lagP99MaxMs: Math.max(...w.map(d => d.lagMs?.p99 || 0)), lagMaxMs: Math.max(...w.map(d => d.lagMs?.max || 0)),
      processCores: Math.round(((w.at(-1).cpu.user + w.at(-1).cpu.system) - (w[0].cpu.user + w[0].cpu.system)) / 1e6 / sec * 100) / 100 };
    if (w[0].threads && w.at(-1).threads) { const th = {}; for (const k of Object.keys(w.at(-1).threads)) th[k] = Math.round(((w.at(-1).threads[k] || 0) - (w[0].threads[k] || 0)) / 100 / sec * 100) / 100;
      out.threadCores = Object.fromEntries(Object.entries(th).filter(([, v]) => v > 0.005).sort((x, y) => y[1] - x[1])); }
    return out;
  };
  const both = rows => ({ idle: win(rows, 'idle/cgroups-before.json', 'idle/cgroups-after.json'), load: win(rows, 'load/cgroups-before.json', 'load/cgroups-after.json') });
  return { api: both(api), realtime: both(rt) };
}
// PostgreSQL active backends (2 s sampler) per window: mean and max of the per-sample active count.
function pgActive (sub) {
  const rows = (read(sub + '/pg-activity.tsv') || '').split('\n').slice(1).filter(Boolean).map(l => l.split('\t'));
  const by = new Map(); for (const r of rows) { if (!by.has(r[0])) by.set(r[0], 0); if (r[2] === 'active') by.set(r[0], by.get(r[0]) + Number(r[5])); }
  const v = [...by.values()]; return v.length ? { samples: v.length, mean: r1(v.reduce((a, b) => a + b, 0) / v.length), max: Math.max(...v) } : null;
}
// Peak PostgreSQL connections per role (any state), from the 2 s sampler, per window; and their sum.
function pgPeakByRole (sub) {
  const rows = (read(sub + '/pg-activity.tsv') || '').split('\n').slice(1).filter(Boolean).map(l => l.split('\t'));
  const by = new Map(); for (const r of rows) { const k = r[0] + '|' + r[1]; by.set(k, (by.get(k) || 0) + Number(r[5])); }
  const mx = {}; for (const [k, v] of by) { const u = k.split('|')[1] || '(none)'; mx[u] = Math.max(mx[u] || 0, v); }
  const perSample = new Map(); for (const r of rows) perSample.set(r[0], (perSample.get(r[0]) || 0) + Number(r[5]));
  return Object.keys(mx).length ? { byRole: mx, sumOfRolePeaks: Object.values(mx).reduce((a, b) => a + b, 0), concurrentMax: Math.max(...perSample.values()) } : null;
}
// Realtime -> api authorize throughput (realtime DIAG p.authorizeCalls), per 60 s from the probe's socket opens
// to the restart, and its peak minute.
function authorizeRate () {
  const restartAt = Number(read('load/.restart-at') || 0) || Infinity;
  const d = (read('load/realtime.log') || '').split('\n').filter(l => l.includes('DIAG {')).map(l => { try { return JSON.parse(l.slice(l.indexOf('DIAG ') + 5)); } catch { return null; } }).filter(x => x && x.p && x.t < restartAt);
  const first = d.findIndex(x => x.p.authorizeCalls > 0); if (first < 0) return null;
  const per = []; for (let i = first; i + 60 < d.length; i += 60) per.push(Math.round((d[i + 60].p.authorizeCalls - d[i].p.authorizeCalls) / ((d[i + 60].t - d[i].t) / 1000)));
  return { perSecondByMinute: per, peak: per.length ? Math.max(...per) : null, total: d.at(-1).p.authorizeCalls };
}
function loadgen () {
  const rows = (read('load/loadgen.tsv') || '').split('\n').slice(1).filter(Boolean).map(l => l.split('\t'));
  if (!rows.length) return null;
  const k6 = rows.map(r => parseFloat(r[1])).filter(x => !isNaN(x)), pr = rows.map(r => parseFloat(r[3])).filter(x => !isNaN(x));
  const m = a => a.length ? Math.round(a.reduce((s, x) => s + x, 0) / a.length) : null;
  return { samples: rows.length, k6CpuPctMean: m(k6), k6CpuPctMax: k6.length ? Math.max(...k6) : null, probeCpuPctMean: m(pr), probeCpuPctMax: pr.length ? Math.max(...pr) : null };
}
const startup = json('startup.json'); const probe = json('load/probe.json');
const summary = {
  tenants: N, deploy: json('deploy.json'),
  host: { deploy: kv('host-deploy.txt'), idleBefore: kv('idle/host-before.txt'), loadBefore: kv('load/host-before.txt'), loadAfter: kv('load/host-after.txt'),
    loadavgIdle: loadRange('idle/host-load.tsv'), loadavgLoad: loadRange('load/host-load.tsv') },
  startup: startup && { firstServedMs: Object.values(startup.firstServed).map(v => v.firstServedMs), roles: startup.roles },
  idle: phase('idle/idle', 'idle/cgroups-before.json', 'idle/cgroups-after.json'),
  idleMaxBackends: maxConnections('idle/pg-locks.tsv'),
  load: phase('load/load', 'load/cgroups-before.json', 'load/cgroups-after.json'),
  loadMaxBackends: maxConnections('load/pg-locks.tsv'),
  http: k6(), probe: probe && { exchangeMs: probe.exchangeMs, prime: probe.prime, window: probe.window },
  restart: probe && probe.restart && { ...probe.restart, reasons: undefined, logs: json('load/restart-startup.json') },
  realtimeDiag: diag(),
  realtimeConfigReads: cfgReads(), alertsAfterRestart: alertsAfterRestart(), mainThread: mainThread(), loadGenerators: loadgen(), pgActive: { idle: pgActive('idle'), load: pgActive('load') }, pgPeakByRole: { idle: pgPeakByRole('idle'), load: pgPeakByRole('load') }, authorizeRate: authorizeRate(),
  oracle: (read('load/oracle.txt') || '').trim().split('\n').at(-1) || null,
  oracleControl: (read('load/oracle-control.txt') || '').trim().split('\n').at(-1) || null,
};
fs.writeFileSync(path.join(dir, 'summary.json'), JSON.stringify(summary, null, 2) + '\n');
console.log(JSON.stringify({ tenants: N, oracle: summary.oracle, restart: summary.restart && { cmd: summary.restart.restartCommandMs, stock: summary.restart.stockRecovered + '/' + summary.restart.sockets, gap: summary.restart.evalGap?.sinceRestartMs } }));
