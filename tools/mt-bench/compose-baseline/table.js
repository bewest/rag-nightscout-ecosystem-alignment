'use strict';
// Prints the evidence record's tables (markdown) from run summaries, and writes the combined
// summary.json the queue gate reads.  node table.js <runs-dir> <label> [combined-out.json]
const fs = require('node:fs'), path = require('node:path');
const [runs, label, combinedOut] = process.argv.slice(2);
const rows = fs.readdirSync(runs).filter(d => /^n\d+$/.test(d)).map(d => {
  try { return JSON.parse(fs.readFileSync(path.join(runs, d, label, 'summary.json'), 'utf8')); } catch { return null; }
}).filter(Boolean).sort((a, b) => a.tenants - b.tenants);
const f = v => v === null || v === undefined ? '–' : String(v);
const lat = s => s && s.latencyMs ? `${f(s.latencyMs.p50)} / ${f(s.latencyMs.p95)} / ${f(s.latencyMs.p99)}` : '–';
const pct = v => v === null || v === undefined ? '–' : (Math.round(v * 1000) / 10) + '%';
const out = [];
out.push(`#### Latency, ms p50 / p95 / p99 (${label})`, '');
const shapes = ['w_sgv', 'w_devicestatus', 'w_treatments_v3', 'r_sgv', 'r_devicestatus', 'r_treatments', 'r_status'];
out.push('| N | offered req | ' + shapes.join(' | ') + ' | failed | dropped |', '|' + '---|'.repeat(shapes.length + 4));
for (const r of rows) {
  const k = r.k6 || { shapes: {} };
  const failed = shapes.map(s => k.shapes[s]?.failedRate).filter(v => v !== undefined);
  const n = shapes.reduce((a, s) => a + (k.shapes[s]?.latencyMs?.n || 0), 0);
  const failedAll = shapes.reduce((a, s) => a + (k.shapes[s]?.failedRate || 0) * (k.shapes[s]?.latencyMs?.n || 0), 0) / (n || 1);
  out.push(`| ${r.tenants} | ${f(k.requests)} | ` + shapes.map(s => lat(k.shapes[s])).join(' | ') + ` | ${pct(failed.length ? failedAll : null)} | ${f(k.droppedIterations)} |`);
}
out.push('', `#### Sockets, recovery, oracle, disk (${label})`, '');
out.push('| N | sockets | fanout hot p50/p95/p99 ms | fanout cold p50/p95/p99 ms | delivered/expected | realtime restart: stock recovered | retrying client: recovered, all after ms | oracle | bytes per tenant-day |', '|---|---|---|---|---|---|---|---|---|');
for (const r of rows) {
  const fo = r.fanout || {}, rec = fo.recovery || {}, fan = fo.fanout || {};
  const st = s => s && s.n ? `${s.p50} / ${s.p95} / ${s.p99} (n ${s.n})` : '–';
  out.push(`| ${r.tenants} | ${f(fo.initial?.sockets)} (primed ${f(fo.initial?.primed)}) | ${st(fan.hot)} | ${st(fan.cold)} | ${f(fan.delivered)}/${f(fan.expectedDeliveries)} | ${f(rec.stockRecovered)}/${f(rec.sockets)} | ${f(rec.retryRecovered)}/${f(rec.sockets)}, ${f(rec.retryAllRecoveredMs)} | ${(r.oracle || '').replace(/^ORACLE /, '').split(':')[0]} | ${f(r.disk?.bytesPerTenantDay)} |`);
}
out.push('', `#### CPU % mean (max) and RSS MiB max per role, idle → load (${label})`, '');
const roles = ['api', 'realtime', 'evaluator', 'tenant-admin', 'postgres', 'vault', 'nginx', 'ui'];
out.push('| N | ' + roles.join(' | ') + ' |', '|' + '---|'.repeat(roles.length + 1));
for (const r of rows) {
  const c = role => { const x = r.cpuRss?.[role]; if (!x) return '–'; return `${f(x.idle.cpuPctMean)} → ${f(x.load.cpuPctMean)} (${f(x.load.cpuPctMax)}); ${f(x.load.rssMiBMax)}`; };
  out.push(`| ${r.tenants} | ` + roles.map(c).join(' | ') + ' |');
}
out.push('', `#### PostgreSQL per phase (${label}): DB ms/s total; window leases per tenant per second (evaluator, realtime); top waits during load`, '');
out.push('| N | idle DB ms/s | load DB ms/s | idle leases/tenant/s eval, rt | load leases/tenant/s eval, rt | ungranted locks max | top active waits (mean backends) |', '|---|---|---|---|---|---|---|');
for (const r of rows) {
  const p = r.pg?.phases || {};
  const ops = ph => { const o = p[ph]?.windowOps || {}; return `${f(o.lifetime_evaluator?.opsPerTenantPerSec)}, ${f(o.lifetime_realtime?.opsPerTenantPerSec)}`; };
  const waits = Object.entries(r.pg?.activeBackendsByWaitDuringLoad || {}).slice(0, 3).map(([k, v]) => `${k} ${v}`).join('; ');
  out.push(`| ${r.tenants} | ${f(p.idle?.dbMsPerSecTotal)} | ${f(p.load?.dbMsPerSecTotal)} | ${ops('idle')} | ${ops('load')} | ${f(r.pg?.locks?.ungrantedMax)} | ${waits} |`);
}
out.push('', `#### Host during each run (${label})`, '');
out.push('| N | load avg before | load avg after | containers running (other projects) | deploy: bootstrap s, start s |', '|---|---|---|---|---|');
for (const r of rows) out.push(`| ${r.tenants} | ${f(r.host?.before?.loadavg)} | ${f(r.host?.after?.loadavg)} | ${f(r.host?.before?.containers_running)} (${f(r.host?.before?.containers_other)}) | ${f(r.deploy?.bootstrapSeconds)}, ${f(r.deploy?.startSeconds)} |`);
process.stdout.write(out.join('\n') + '\n');
if (combinedOut) {
  let combined = {}; try { combined = JSON.parse(fs.readFileSync(combinedOut, 'utf8')); } catch {}
  combined[label] = rows;
  fs.writeFileSync(combinedOut, JSON.stringify(combined, null, 2) + '\n');
}
