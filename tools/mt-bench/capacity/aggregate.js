#!/usr/bin/env node
'use strict';
// Tables for the capacity record from every <label>-n<N>/summary.json under a work directory.
//   aggregate.js <work-dir> > tables.md
const fs = require('node:fs'), path = require('node:path');
const work = process.argv[2];
const runs = fs.readdirSync(work).filter(d => /^[a-z0-9]+-n\d+$/.test(d) && fs.existsSync(path.join(work, d, 'summary.json')) && !d.startsWith('smoke-'))
  .map(d => ({ id: d, label: d.split('-n')[0], N: Number(d.split('-n')[1]), s: JSON.parse(fs.readFileSync(path.join(work, d, 'summary.json'), 'utf8')) }))
  .sort((a, b) => a.N - b.N || a.label.localeCompare(b.label));
const f = (x, d = 1) => x == null ? '–' : typeof x === 'number' ? (Math.round(x * 10 ** d) / 10 ** d).toLocaleString('en-US') : String(x);
const s1 = ms => ms == null ? '–' : f(ms / 1000);
const load = h => h?.loadavg ? h.loadavg.split(' ')[0] : (h?.uptime || '').replace(/.*load average: /, '').split(',')[0] || '–';
const row = cells => '| ' + cells.join(' | ') + ' |';
const out = [];
const head = (cols) => { out.push(row(cols)); out.push(row(cols.map(() => '---'))); };

out.push('### Startup (cold deploy; s from `compose up`)\n');
head(['run', 'N', 'load at deploy', 'api listener / healthy / drained', 'realtime listener / healthy / drained', 'evaluator healthy / drained', 'first served (3 tenants)']);
for (const r of runs) { const st = r.s.startup; if (!st) continue; const R = st.roles;
  out.push(row([r.label, f(r.N, 0), load(r.s.host.deploy), [R.api.listenerOpenMs, R.api.healthyMs, R.api.warmDrainedMs].map(s1).join(' / '),
    [R.realtime.listenerOpenMs, R.realtime.healthyMs, R.realtime.warmDrainedMs].map(s1).join(' / '), [R.evaluator.healthyMs, R.evaluator.warmDrainedMs].map(s1).join(' / '),
    st.firstServedMs.map(s1).join(', ')])); }

for (const ph of ['idle', 'load']) {
  out.push(`\n### ${ph === 'idle' ? 'Idle (no clients)' : 'Real cadence (k6 + 2 sockets per tenant + probe writes)'}: CPU-ms per tenant-minute, memory (anon MiB), DB\n`);
  head(['run', 'N', 'load (mean of 2 s samples)', 'api', 'realtime', 'evaluator', 'tenant-admin', 'postgres', 'nginx', 'DB-ms / tenant-min', 'backends (max)']);
  for (const r of runs) { const p = r.s[ph]; if (!p) continue; const c = k => p.roles[k] ? f(p.roles[k].cpuMsPerTenantMin, 2) + ' (' + f(p.roles[k].anonMiB, 0) + ')' : '–';
    out.push(row([r.label, f(r.N, 0), f((ph === 'idle' ? r.s.host.loadavgIdle : r.s.host.loadavgLoad)?.mean), c('api'), c('realtime'), c('evaluator'), c('tenant-admin'), c('postgres'), c('nginx'),
      f(p.dbMsPerTenantMin, 2), f(ph === 'idle' ? r.s.idleMaxBackends : r.s.loadMaxBackends, 0)])); }
}

out.push('\n### HTTP p50 / p95 / p99 ms (k6, real cadence, through nginx)\n');
head(['run', 'N', 'POST v1 entries', 'GET v1 sgv', 'GET v1 status', 'failed rate (max over shapes)', 'dropped iterations']);
for (const r of runs) { const h = r.s.http; if (!h) continue; const t = k => h[k] ? [h[k].p50, h[k].p95, h[k].p99].map(x => f(x, 0)).join(' / ') : '–';
  const fr = Math.max(...Object.values(h).filter(v => v && typeof v === 'object').map(v => v.failedRate || 0));
  out.push(row([r.label, f(r.N, 0), t('POST v1 entries'), t('GET v1 sgv'), t('GET v1 status'), f(fr, 4), f(h.droppedIterations, 0)])); }

out.push('\n### Latency to frame and to evaluation (probe writes), oracle\n');
head(['run', 'N', 'sockets primed', 'write→frame p50/p95/p99 ms', 'frames delivered', 'write→evaluation p50/p95/p99 ms', 'not evaluated in 120 s', 'oracle']);
for (const r of runs) { const w = r.s.probe?.window; if (!w) continue;
  out.push(row([r.label, f(r.N, 0), `${r.s.probe.prime.primed}/${r.s.probe.prime.sockets} in ${s1(r.s.probe.prime.ms)} s`,
    [w.writeToFrameMs.p50, w.writeToFrameMs.p95, w.writeToFrameMs.p99].map(x => f(x, 0)).join(' / '), `${w.deliveredFrames}/${w.expectedFrames}`,
    [w.writeToEvaluationMs.p50, w.writeToEvaluationMs.p95, w.writeToEvaluationMs.p99].map(x => f(x, 0)).join(' / '), f(w.evaluationMissedWithin120s, 0),
    (r.s.oracle || '–').replace(/^ORACLE /, '').split(':')[0] + (r.s.oracle ? ' (' + (/stored (\d+), accepted (\d+)/.exec(r.s.oracle) || []).slice(1).join(' = ') + ')' : '')])); }

out.push('\n### Full restart (4 roles; edge sampled, then nginx restarted: labelled variant)\n');
head(['run', 'N', 'restart cmd s', 'edge after role restart', 'nginx restart at / cmd s', 'healthy api / realtime / evaluator s (probe saw)', 'evaluator healthcheck first pass s', 'first served s (3)', 'eval gap p50 / p90 / max s', 'evaluated ≤60 s / ≤300 s / all', 'stock sockets', 'stock all-recovered s', 'retry flood']);
for (const r of runs) { const x = r.s.restart; if (!x) continue; const g = x.evalGap || {};
  out.push(row([r.label, f(r.N, 0), s1(x.restartCommandMs), (x.edgeAfterRoleRestart || []).join(','), x.edgeRestarted ? s1(x.edgeRestarted.atMs) + ' / ' + s1(x.edgeRestarted.commandMs) : '–',
    ['api', 'realtime', 'evaluator'].map(k => s1(x.healthyMs?.[k])).join(' / '), x.healthCheckPassMs ? s1(x.healthCheckPassMs.evaluator) : 'not recorded', Object.values(x.firstServedMs || {}).map(v => s1(v.ms)).join(', '),
    [g.sinceRestartMs?.p50, g.sinceRestartMs?.p90, g.sinceRestartMs?.max].map(s1).join(' / '), `${g.within?.['60s']} / ${g.within?.['300s']} / ${g.evaluatedAfterReady}`,
    `${x.stockRecovered}/${x.sockets}`, s1(x.stockAllRecoveredMs), `${x.retryRecovered}/${x.sockets}` + (x.retryAllRecoveredMs != null ? ' in ' + s1(x.retryAllRecoveredMs) + ' s' : '')])); }

out.push('\n### Realtime after the full restart (instrument DIAG, 1 s; times from the restart command)\n');
head(['run', 'N', 'TENANT_WARM_FAILED alerts', 'failed peak', 'warm drained line', 'all startup-ready s', 'all runtime-healthy s', 'failed (first / last seen) s', 'socket refreshes / failures at +60 s', 'primed at +60 s']);
for (const r of runs) { const d = r.s.realtimeDiag; if (!d) continue; const p = d.at60s?.p || {};
  out.push(row([r.label, f(r.N, 0), f(d.tenantWarmFailedAlerts, 0), f(d.startupFailedMax, 0), (d.drainedLines || []).join('; ').replace('Tenant warm drained: ', ''),
    s1(d.startupAllReadyMs), s1(d.runtimeAllHealthyMs), s1(d.failedFirstSeenMs) + ' / ' + s1(d.failedLastSeenMs),
    f(p.primeRefreshes, 0) + ' / ' + f(p.primeRefreshFailures, 0), f(p.primed, 0)])); }

out.push('\n### Alert codes after the full restart, per role (log lines; startup health() causes where instrumented)\n');
head(['run', 'N', 'api log codes', 'api warm drained', 'api failed peak (causes)', 'realtime log codes', 'realtime warm drained', 'realtime failed peak (causes)', 'realtime all ready s', 'evaluator log codes', 'realtime /health after']);
const codes = c => Object.entries(c || {}).map(([k, v]) => k.replace(/^Tenant readiness alert /, '').replace(/^Evaluator alert /, 'eval ') + ' ×' + v).join('; ') || 'none';
for (const r of runs) { const a = r.s.alertsAfterRestart; if (!a) continue; const sh = x => x?.startupHealth ? f(x.startupHealth.worstFailed, 0) + (Object.keys(x.startupHealth.worstCauses || {}).length ? ' (' + codes(x.startupHealth.worstCauses) + ')' : '') : 'not instrumented';
  const h = a.realtimeHealthEndpoint;
  out.push(row([r.label, f(r.N, 0), codes(a.api?.logAlertCodes), (a.api?.drained || []).join('; ').replace(/Tenant warm drained: /g, ''), sh(a.api),
    codes(a.realtime?.logAlertCodes), (a.realtime?.drained || []).join('; ').replace(/Tenant warm drained: /g, ''), sh(a.realtime), s1(a.realtime?.startupHealth?.allReadyMs),
    codes(a.evaluator?.logAlertCodes), h ? (h.status + ' healthy ' + h.healthy + '/' + h.configured + ' failed ' + h.failed) : 'not captured'])); }

out.push('\n### Realtime whole-file config reads (instrument; per second of window)\n');
head(['run', 'N', 'phase', 'readCurrent calls/s', 'ms per call', 'readAll calls/s', 'ms per call', 'read ms/s', 'realtime CPU ms/s', 'share of realtime CPU']);
for (const r of runs) { const c = r.s.realtimeConfigReads; if (!c) continue;
  for (const ph of ['idle', 'load']) { const x = c[ph]; if (!x) continue;
    out.push(row([r.label, f(r.N, 0), ph, f(x.readCurrent.callsPerSec), f(x.readCurrent.msPerCall, 2), f(x.readAll.callsPerSec), f(x.readAll.msPerCall, 2),
      f(x.readCurrent.msPerSec + x.readAll.msPerSec), f(x.realtimeCpuMsPerSec), f(x.readShareOfRealtimeCpu, 3)])); } }

out.push('\n### Sockets after the full restart: stock clients, server disconnects, realtime authorize pressure\n');
head(['run', 'N', 'stock recovered (no client retry)', 'server disconnects after restart (client-seen)', 'disconnects by 5 s from restart', 'realtime sockets min after +30 s', 'authorize in flight (max)', 'recheckFailures (end)', 'retry flood']);
for (const r of runs) { const x = r.s.restart, d = r.s.realtimeDiag; if (!x) continue;
  const sd = x.serverDisconnectsBy5s; const sdTotal = sd ? Object.values(sd).reduce((a, b) => a + b, 0) : (x.reasons === undefined ? null : null);
  const minSock = d?.socketTimeline ? Math.min(...d.socketTimeline.filter(v => v[0] >= 30 && v[1] != null).map(v => v[1])) : null;
  out.push(row([r.label, f(r.N, 0), `${x.stockRecovered}/${x.sockets}` + (x.stockAllRecoveredMs != null ? ' by ' + s1(x.stockAllRecoveredMs) + ' s' : ''),
    sd ? f(sdTotal, 0) : 'not recorded', sd ? Object.entries(sd).map(([k, v]) => k + 's:' + v).join(' ') : '–', f(minSock, 0),
    f(d?.authorizeInFlightMax, 0), f(d?.recheckFailuresEnd, 0), `${x.retryRecovered}/${x.sockets}` + (x.retryAllRecoveredMs != null ? ' in ' + s1(x.retryAllRecoveredMs) + ' s' : '')])); }
process.stdout.write(out.join('\n') + '\n');
// Machine-readable means per N (non-control runs) for the marginal-cost derivation.
const byN = {};
for (const r of runs.filter(r => r.label !== 'ctl')) (byN[r.N] ||= []).push(r.s);
const mean = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;
const means = Object.fromEntries(Object.entries(byN).map(([N, ss]) => [N, Object.fromEntries(['idle', 'load'].map(ph => [ph, {
  roles: Object.fromEntries(['api', 'realtime', 'evaluator', 'tenant-admin', 'postgres', 'nginx'].map(k => [k, {
    cpuMsPerMin: mean(ss.map(s => s[ph]?.roles[k]?.cpuMsPerMin).filter(x => x != null)), anonMiB: mean(ss.map(s => s[ph]?.roles[k]?.anonMiB).filter(x => x != null)) }])),
  dbMsPerMin: mean(ss.map(s => s[ph] && s[ph].dbMsPerTenantMin * Number(N)).filter(x => x != null)), runs: ss.length }]))]));
fs.writeFileSync(path.join(work, 'means.json'), JSON.stringify(means, null, 2) + '\n');
