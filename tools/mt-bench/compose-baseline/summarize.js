'use strict';
// Builds summary.json for one run directory from the raw files bench.sh leaves there.
//   node summarize.js <run-dir> <tenants>
const fs = require('node:fs'), path = require('node:path');
const dir = process.argv[2], tenants = Number(process.argv[3]);
const read = f => { try { return fs.readFileSync(path.join(dir, f), 'utf8'); } catch { return null; } };
const kv = text => Object.fromEntries((text || '').split('\n').filter(Boolean).map(l => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)]));
const tsv = text => { const [h, ...rows] = (text || '').split('\n').filter(Boolean); const k = (h || '').split('\t'); return rows.map(r => Object.fromEntries(r.split('\t').map((v, i) => [k[i], v]))); };
const phases = Object.fromEntries(Object.entries(kv(read('phases.txt'))).map(([k, v]) => [k, Number(v)]));
const within = (t, a, b) => t >= phases[a] && t <= phases[b];
const mean = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;
const r1 = v => v === null || v === undefined ? null : Math.round(v * 10) / 10;
const mib = s => { const m = /^([\d.]+)([KMG]i?B)/.exec(s || ''); if (!m) return null; return Number(m[1]) * ({ KiB: 1 / 1024, MiB: 1, GiB: 1024, KB: 1 / 1024, MB: 1, GB: 1024 }[m[2]] || 1); };

// k6
let k6 = null;
const k6raw = read('k6-summary.json');
if (k6raw) {
  const m = JSON.parse(k6raw).metrics;
  const shapes = {};
  for (const [key, v] of Object.entries(m)) {
    const d = /^http_req_duration\{shape:(\w+)\}$/.exec(key);
    if (d) (shapes[d[1]] ||= {}).latencyMs = { p50: r1(v.med), p95: r1(v['p(95)']), p99: r1(v['p(99)']), max: r1(v.max), n: v.count };
    const f = /^http_req_failed\{shape:(\w+)\}$/.exec(key);
    if (f) (shapes[f[1]] ||= {}).failedRate = v.value ?? v.rate ?? null;
  }
  k6 = { shapes, requests: m.http_reqs?.count, rps: r1(m.http_reqs?.rate), droppedIterations: m.dropped_iterations?.count || 0,
    writesOk: m.writes_ok?.count || 0, writesUncertain: m.writes_uncertain?.count || 0, writesRefused: m.writes_refused?.count || 0,
    overall: m.http_req_duration && { p50: r1(m.http_req_duration.med), p95: r1(m.http_req_duration['p(95)']), p99: r1(m.http_req_duration['p(99)']) } };
}

// CPU / RSS per role, idle window and load window
const stats = tsv(read('docker-stats.tsv'));
const roles = {};
for (const row of stats) {
  const role = (row.container || '').replace(/^nsbench-n\d+-/, '').replace(/-1$/, '');
  const t = Number(row.t), cpu = parseFloat(row.cpu_pct), rss = mib((row.mem || '').split(' / ')[0]);
  const w = within(t, 'idle_start', 'idle_end') ? 'idle' : within(t, 'load_start', 'load_end') ? 'load' : null;
  if (!w) continue;
  const r = (roles[role] ||= { idle: { cpu: [], rss: [] }, load: { cpu: [], rss: [] } });
  r[w].cpu.push(cpu); r[w].rss.push(rss);
}
const cpuRss = Object.fromEntries(Object.entries(roles).map(([role, r]) => [role, Object.fromEntries(['idle', 'load'].map(w => [w,
  { cpuPctMean: r1(mean(r[w].cpu)), cpuPctMax: r1(r[w].cpu.length ? Math.max(...r[w].cpu) : null), rssMiBMax: r1(r[w].rss.length ? Math.max(...r[w].rss) : null), samples: r[w].cpu.length }]))]));

// PostgreSQL waits during load
const act = tsv(read('pg-activity.tsv')).filter(r => within(Number(r.t), 'load_start', 'load_end'));
const samples = new Set(act.map(r => r.t)).size || 1;
const waits = {};
for (const r of act) if (r.state === 'active') { const k = (r.wait_event_type || 'CPU') + ':' + (r.wait_event || '-'); waits[k] = (waits[k] || 0) + Number(r.n); }
const pgWaits = Object.fromEntries(Object.entries(waits).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([k, v]) => [k, r1(v / samples)]));
const locks = tsv(read('pg-locks.tsv')).filter(r => within(Number(r.t), 'load_start', 'load_end'));
const pgLocks = { ungrantedMax: locks.length ? Math.max(...locks.map(r => Number(r.ungranted_locks))) : null,
  ungrantedMean: r1(mean(locks.map(r => Number(r.ungranted_locks)))), backendsMax: locks.length ? Math.max(...locks.map(r => Number(r.backends))) : null };
// Per phase: statements/s and DB ms per second by role; lifecycle operations (window leases) per second
// per tenant for the evaluator and realtime lifetime identities (each tenant cycle takes one lease).
const lines = f => (read(f) || '').split('\n').filter(Boolean).map(l => l.split('\t'));
const phaseSeconds = { idle: phases.idle_end - phases.idle_start, load: phases.load_end - phases.idle_end };
const pgPhases = {};
for (const [phase, sec] of Object.entries(phaseSeconds)) {
  if (!sec) continue;
  const roles = Object.fromEntries(lines(`pg-by-role-${phase}.tsv`).map(([role, calls, ms]) => [role.replace(/^nsdemo_/, ''),
    { statementsPerSec: r1(Number(calls) / sec), dbMsPerSec: r1(Number(ms) / sec) }]));
  const ops = Object.fromEntries(lines(`pg-ops-${phase}.tsv`).map(([role, calls]) => [role.replace(/^nsdemo_/, ''),
    { opsPerSec: r1(Number(calls) / sec), opsPerTenantPerSec: Math.round(Number(calls) / sec / tenants * 100) / 100 }]));
  const total = Object.values(roles).reduce((a, r) => a + r.dbMsPerSec, 0);
  pgPhases[phase] = { seconds: r1(sec), dbMsPerSecTotal: r1(total), roles, windowOps: ops };
}

// Disk
const disk = text => {
  const out = { tables: {} };
  for (const l of (text || '').split('\n').filter(Boolean)) {
    const p = l.split('\t');
    if (p[0] === 'database_bytes') out.database = Number(p[1]);
    if (p[0] === 'table_bytes') out.tables[p[1]] = Number(p[2]);
    if (p[0] === 'run_rows') (out.run ||= {})[p[1]] = { rows: Number(p[2]), docBytes: Number(p[3] || 0) };
  }
  return out;
};
const d0 = disk(read('disk-before.txt')), d1 = disk(read('disk.txt'));
let diskOut = null;
if (d1.run) {
  const map = { entries: 'nsdemo_entries.entries', devicestatus: 'nsdemo_devicestatus.devicestatus', treatments: 'nsdemo_treatments.treatments' };
  const per = {};
  // The probe's sgv rows land in the same entries table; count them with the run's rows.
  const probeRows = (read('oracle-stored.tsv') || '').split('\n').filter(l => l.split('\t')[1] === 'probe').reduce((x, l) => x + Number(l.split('\t')[2]), 0);
  for (const [k, table] of Object.entries(map)) {
    const rows = (d1.run[k]?.rows || 0) + (k === 'entries' ? probeRows : 0), grown = (d1.tables[table] || 0) - (d0.tables[table] || 0);
    per[k] = { rows, tableGrowthBytes: grown, bytesPerRow: rows ? Math.round(grown / rows) : null, docBytesPerRow: d1.run[k]?.rows ? Math.round(d1.run[k].docBytes / d1.run[k].rows) : null };
  }
  // A tenant-day at the pinned shapes: 288 of each write (one per 5-minute cycle).
  const day = ['entries', 'devicestatus', 'treatments'].reduce((a, k) => a + (per[k].bytesPerRow || 0) * 288, 0);
  diskOut = { perDomain: per, bytesPerTenantDay: day, databaseGrowthBytes: (d1.database || 0) - (d0.database || 0), databaseBytes: d1.database };
}

const oracleText = read('oracle.txt') || '';
const verdict = /ORACLE (GREEN|RED)[^\n]*/.exec(oracleText);
const summary = {
  tenants, runid: (read('runid') || '').trim(), workload: (() => { try { return JSON.parse(read('bench.json')); } catch { return null; } })(), host: { before: kv(read('host-before.txt')), after: kv(read('host-after.txt')) },
  deploy: (() => { try { return JSON.parse(fs.readFileSync(path.join(dir, '..', 'deploy.json'), 'utf8')); } catch { return null; } })(),
  phases, k6, fanout: (() => { try { return JSON.parse(read('fanout.json')); } catch { return null; } })(),
  cpuRss, pg: { activeBackendsByWaitDuringLoad: pgWaits, locks: pgLocks, phases: pgPhases },
  disk: diskOut, oracle: verdict ? verdict[0] : 'UNMEASURED',
};
process.stdout.write(JSON.stringify(summary, null, 2) + '\n');
