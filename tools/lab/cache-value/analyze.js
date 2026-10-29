'use strict';
// analyze.js <results/run-dir>: per-arm, per-hour table from replay-*.jsonl and
// metrics-*.jsonl. Writes <run-dir>/summary.json and prints Markdown.
//
// Bytes returned = delta of serverStatus network.bytesOut minus the sampler's
// own two serverStatus replies per sample. Ops = opcounters deltas (CRUD =
// query+getmore+insert+update+delete; "command" includes the sampler's own 2
// serverStatus calls per hour and the drivers' monitoring). Atlas M0 limits
// (read 2026-10-29, https://www.mongodb.com/docs/atlas/reference/free-shared-limitations/):
// 100 operations per second, 500 connections, 10 GB out per rolling 7 days.

const fs = require('fs');
const path = require('path');
const dir = process.argv[2];
const ARMS = ['base-a', 'base-b', 'cache-pool100', 'bypass-pool5', 'bypass-pool100'];
const M0 = { opsPerSec: 100, connections: 500, bytesOutPer7d: 10 * 1e9 };

function pct (arr, p) {
  if (!arr.length) return null;
  const s = arr.slice().sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(p * s.length))];
}
const crud = (o) => o.query + o.getmore + o.insert + o.update + o.delete;

const summary = {};
for (const arm of ARMS) {
  const f = path.join(dir, 'replay-' + arm + '.jsonl');
  if (!fs.existsSync(f)) continue;
  const L = fs.readFileSync(f, 'utf8').trim().split('\n').map(JSON.parse);
  const samples = L.filter(x => x.kind === 'sample');
  const reqs = L.filter(x => x.kind === 'req' && x.cls !== 'check');
  const metrics = fs.readFileSync(path.join(dir, 'metrics-' + arm + '.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
  const rows = [];
  for (let h = 1; h < samples.length; h++) {
    const a = samples[h - 1]; const b = samples[h];
    const inWin = (t) => t >= a.t && t < b.t;
    const r = reqs.filter(x => inWin(x.t));
    const gets = r.filter(x => x.cls === 'get').map(x => x.ms);
    const posts = r.filter(x => x.cls === 'post').map(x => x.ms);
    const m = metrics.filter(x => inWin(x.t));
    const secs = (b.t - a.t) / 1000;
    const crudOps = crud(b.opcounters) - crud(a.opcounters);
    const cmdOps = b.opcounters.command - a.opcounters.command;
    const bytes = (b.bytesOut - a.bytesOut) - a.sampleReplyBytes;
    rows.push({
      hour: h, secs
      , crudOps, queryOps: b.opcounters.query - a.opcounters.query, commandOps: cmdOps
      , opsPerSec: +((crudOps + cmdOps) / secs).toFixed(3)
      , docsReturned: b.docReturned - a.docReturned
      , bytesOut: bytes
      , reloads: b.preload && a.preload ? b.preload.counts['data-loaded'] - a.preload.counts['data-loaded'] : null
      , requests: r.length, errors: r.filter(x => x.err || x.status >= 400).length
      , getP50: pct(gets, 0.5), getP95: pct(gets, 0.95), postP50: pct(posts, 0.5), postP95: pct(posts, 0.95)
      , rssMaxMB: m.length ? +(Math.max(...m.map(x => x.rss)) / 1048576).toFixed(1) : null
      , rssEndMB: b.preload ? +(b.preload.rss / 1048576).toFixed(1) : null
      , connections: b.connections
      , m0OpsPct: +(100 * ((crudOps + cmdOps) / secs) / M0.opsPerSec).toFixed(2)
      , m0BytesOut7dPct: +(100 * (bytes * (7 * 24 * 3600 / secs)) / M0.bytesOutPer7d).toFixed(2)
      , m0ConnPct: +(100 * b.connections / M0.connections).toFixed(1)
    });
  }
  const check = L.find(x => x.kind === 'check');
  summary[arm] = { check: check && check.msg, rows };
}
fs.writeFileSync(path.join(dir, 'summary.json'), JSON.stringify(summary, null, 2) + '\n');

const f2 = (x) => x == null ? '-' : (typeof x === 'number' ? (Number.isInteger(x) ? x.toLocaleString('en-US') : x.toFixed(1)) : x);
console.log('| arm | hour | CRUD ops | command ops | ops/s | docs returned | bytes out | reloads | GET p50/p95 ms | POST p50/p95 ms | RSS max MB | conns | M0: ops/s % of 100 | M0: bytes out/7d % of 10 GB | M0: conns % of 500 |');
console.log('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|');
for (const arm of Object.keys(summary)) {
  for (const r of summary[arm].rows) {
    console.log(`| ${arm} | ${r.hour} | ${f2(r.crudOps)} | ${f2(r.commandOps)} | ${r.opsPerSec.toFixed(2)} | ${f2(r.docsReturned)} | ${f2(r.bytesOut)} | ${f2(r.reloads)} | ${f2(r.getP50)}/${f2(r.getP95)} | ${f2(r.postP50)}/${f2(r.postP95)} | ${f2(r.rssMaxMB)} | ${r.connections} | ${r.m0OpsPct}% | ${r.m0BytesOut7dPct}% | ${r.m0ConnPct}% |`);
  }
}
console.log();
for (const arm of Object.keys(summary)) console.log(`- ${summary[arm].check}; errors: ${summary[arm].rows.reduce((a, r) => a + r.errors, 0)} of ${summary[arm].rows.reduce((a, r) => a + r.requests, 0)} requests`);
