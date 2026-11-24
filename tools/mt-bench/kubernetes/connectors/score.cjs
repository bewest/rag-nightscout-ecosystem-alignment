'use strict';
// Connector score for the vcpool workload: upstream record -> stored in the tenant -> visible to
// a tenant reader.
//
//   node score.cjs poll        (in the cluster) env SCORE_INPUT_FILE; writes JSON lines to stdout
//   node score.cjs summarize <input.json> <poll.log> [--from ms] [--until ms] [--miss-after-seconds s]
//
// poll: every SCORE_EVERY_MS (default 10 s) reads each connector tenant's entries, treatments and
// devicestatus since the upstream history start through the tenant's own API (the tenant chosen by
// Host, the roster's DATA subject token as API-SECRET sha1), and prints one `seen` line per new
// stored document (its record time, the server's srvCreated and the reader's first sight), a
// `pass` line for read errors or duplicates, and a heartbeat after every complete sweep.
//
// summarize: the expected set is the synthetic generator's (upstream.cjs), so a stopped upstream
// still has expectations. A record is scored when its availability (its timestamp) falls in
// [from, until - missAfter]. Measured: stored latency = srvCreated - availability; visible latency
// = first sight - availability (resolution: the poll period). A miss is a scored record not stored
// within missAfter seconds of availability. A duplicate is a record time stored more than once.
// Backfill (records older than the connector's entry) is scored apart: its latency starts at entry.
const crypto = require('node:crypto');
const http = require('node:http');
const fs = require('node:fs');
const upstream = require('./upstream.cjs');

const KIND_NAMES = Object.keys(upstream.KINDS);
const sha1 = text => crypto.createHash('sha1').update(text).digest('hex');

function get (origin, host, route, secret) {
  return new Promise((resolve, reject) => {
    // A data JWT goes as a bearer; a legacy subject token as API-SECRET sha1(token), as an uploader sends it.
    const auth = /^[\w-]+\.[\w-]+\.[\w-]+$/.test(secret) ? { Authorization: 'Bearer ' + secret } : { 'API-SECRET': sha1(secret) };
    const req = http.request(new URL(route, origin), { headers: { Host: host, ...auth, accept: 'application/json' }, timeout: 20000 }, res => {
      const chunks = []; res.on('data', c => chunks.push(c));
      res.on('end', () => { try { resolve({ status: res.statusCode, body: JSON.parse(Buffer.concat(chunks).toString('utf8')) }); } catch { resolve({ status: res.statusCode, body: null }); } });
    });
    req.on('timeout', () => req.destroy(new Error('timeout'))); req.on('error', reject); req.end();
  });
}
function query (kind, sinceMs) {
  const p = new URLSearchParams();
  if (kind === 'entries') p.set('find[date][$gte]', String(sinceMs)); else p.set('find[created_at][$gte]', new Date(sinceMs).toISOString());
  p.set('count', '5000');
  return '/api/v1/' + kind + '.json?' + p.toString();
}

async function poll (env = process.env, out = line => process.stdout.write(JSON.stringify(line) + '\n')) {
  const input = JSON.parse(fs.readFileSync(env.SCORE_INPUT_FILE, 'utf8'));
  const every = Number(env.SCORE_EVERY_MS || 10000), seen = new Set();
  out({ t: 'start', at: Date.now(), tenants: input.tenants.length, every });
  for (;;) {
    for (const tenant of input.tenants) {
      for (const kind of KIND_NAMES) {
        const at = Date.now();
        let r;
        try { r = await get(input.apiOrigin, tenant.host, query(kind, input.historyStartMs), tenant.token); }
        catch (error) { out({ t: 'pass', site: tenant.site, kind, at, error: String(error.code || error.message).slice(0, 40) }); continue; }
        if (r.status !== 200 || !Array.isArray(r.body)) { out({ t: 'pass', site: tenant.site, kind, at, status: r.status }); continue; }
        const copies = {};
        for (const doc of r.body) {
          if (doc.device !== 'synthetic-upstream' && doc.device !== 'synthetic-loop' && doc.enteredBy !== 'synthetic-upstream') continue;
          const key = upstream.keyOf(kind, doc);
          copies[key] = (copies[key] || 0) + 1;
          const id = tenant.site + ':' + kind + ':' + key + ':' + (doc._id || '');
          if (!seen.has(id)) { seen.add(id); out({ t: 'seen', site: tenant.site, kind, key, srvCreated: doc.srvCreated ?? null, seenAt: at, id: doc._id ?? null }); }
        }
        const dup = Object.entries(copies).filter(([, n]) => n > 1).map(([key, n]) => [Number(key), n]);
        if (dup.length) out({ t: 'pass', site: tenant.site, kind, at, status: 200, stored: r.body.length, duplicates: dup });
      }
    }
    // Successful reads without duplicates need only one heartbeat for the full sweep. At 100
    // sites, a separate line for each one rotates away first sightings before a one-hour run ends.
    out({ t: 'sweep', at: Date.now(), reads: input.tenants.length * KIND_NAMES.length });
    await new Promise(resolve => setTimeout(resolve, every));
  }
}

const pct = (values, p) => {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.ceil(p / 100 * s.length) - 1)];
};
const stats = v => ({ n: v.length, p50: pct(v, 50), p95: pct(v, 95), max: v.length ? Math.max(...v) : null });

// input: { tenants: [{ site, enteredAt }], historyStartMs, timing }; lines: parsed poll lines. timing is the
// upstream's (upstream.cjs TIMINGS); absent means the default.
function summarize (input, lines, { from, until, missAfterMs = 360000 }) {
  const firstSeen = new Map(), stored = new Map(), dupMax = new Map(), errors = {};
  for (const l of lines) {
    if (l.t === 'seen') {
      const k = l.site + ':' + l.kind + ':' + l.key;
      if (!firstSeen.has(k) || l.seenAt < firstSeen.get(k)) firstSeen.set(k, l.seenAt);
      if (Number.isFinite(l.srvCreated) && (!stored.has(k) || l.srvCreated < stored.get(k))) stored.set(k, l.srvCreated);
    } else if (l.t === 'pass') {
      // A duplicate seen in this point still counts even if the underlying record is older.
      if (l.at < from || l.at > until) continue;
      if (l.status !== 200) errors[l.error || ('http-' + l.status)] = (errors[l.error || ('http-' + l.status)] || 0) + 1;
      for (const [key, n] of l.duplicates || []) {
        const k = l.site + ':' + l.kind + ':' + key;
        dupMax.set(k, Math.max(dupMax.get(k) || 0, n));
      }
    }
  }
  const live = { stored: [], visible: [] }, backfill = { stored: [], visible: [] }, misses = [], late = [];
  let scored = 0, backfillScored = 0;
  for (const tenant of input.tenants) {
    for (const kind of KIND_NAMES) {
      for (const rec of upstream.records(tenant.site, kind, { historyStartMs: input.historyStartMs, untilMs: until - missAfterMs, timing: input.timing })) {
        const t = upstream.keyOf(kind, rec), k = tenant.site + ':' + kind + ':' + t;
        const isBackfill = t < tenant.enteredAt;
        const available = isBackfill ? tenant.enteredAt : t;
        if (available < from) continue;
        const target = isBackfill ? backfill : live;
        if (isBackfill) backfillScored += 1; else scored += 1;
        const s = stored.get(k), v = firstSeen.get(k);
        if (s === undefined && v === undefined) { misses.push({ site: tenant.site, kind, key: t, backfill: isBackfill }); continue; }
        const storedAt = s ?? v;
        if (storedAt - available > missAfterMs) late.push({ site: tenant.site, kind, key: t, backfill: isBackfill, ms: storedAt - available });
        if (s !== undefined) target.stored.push(s - available);
        if (v !== undefined) target.visible.push(v - available);
      }
    }
  }
  const duplicates = [...dupMax].filter(([, n]) => n > 1).map(([k, n]) => ({ record: k, copies: n }));
  const missed = misses.length + late.length;
  return {
    version: 1, kind: 'vcpool-connector-score', window: { from, until, missAfterMs }, timing: input.timing || upstream.DEFAULT_TIMING,
    basis: 'measured: srvCreated from the tenant API (server stamp), first sight from the poll loop (resolution = poll period); expected set from the synthetic generator',
    live: { scored, stored: stats(live.stored), visible: stats(live.visible) },
    backfill: { scored: backfillScored, stored: stats(backfill.stored), visible: stats(backfill.visible) },
    misses: misses.length, late: late.length, missesSample: misses.slice(0, 10), lateSample: late.slice(0, 10),
    duplicates: duplicates.length, duplicatesSample: duplicates.slice(0, 10), readErrors: errors,
    verdict: missed === 0 && duplicates.length === 0 ? 'PASS' : 'FAIL',
  };
}

if (require.main === module) {
  const [mode, ...rest] = process.argv.slice(2);
  if (mode === 'poll') poll().catch(error => { console.error(JSON.stringify({ error: String(error.message).slice(0, 200) })); process.exit(1); });
  else if (mode === 'summarize') {
    const [inputFile, logFile, ...flags] = rest, opt = {};
    for (let i = 0; i < flags.length; i += 2) opt[flags[i].replace(/^--/, '')] = Number(flags[i + 1]);
    const input = JSON.parse(fs.readFileSync(inputFile, 'utf8'));
    const lines = fs.readFileSync(logFile, 'utf8').split('\n').filter(l => l.startsWith('{')).map(l => JSON.parse(l));
    const result = summarize(input, lines, { from: opt.from, until: opt.until, missAfterMs: (opt['miss-after-seconds'] ?? 360) * 1000 });
    console.log(JSON.stringify(result, null, 2));
    process.exitCode = result.verdict === 'PASS' ? 0 : 1;
  } else { console.error('usage: score.cjs poll | summarize <input> <log> [--from ms] [--until ms] [--miss-after-seconds s]'); process.exitCode = 64; }
}
module.exports = { summarize, query, stats, pct };
