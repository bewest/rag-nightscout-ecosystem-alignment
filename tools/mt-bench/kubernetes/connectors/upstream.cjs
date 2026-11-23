'use strict';
// Synthetic upstream Nightscout for the vcpool connector workload. One process serves many
// synthetic single-tenant "sites" under /s/<site>/, each with its own source token, and answers
// only what the nightscout-connect Nightscout source reads (lib/sources/nightscout.js in the
// core image's nightscout-connect):
//   GET /s/<site>/api/v2/authorization/request/<token>   -> { token, iat, exp } (the bearer)
//   GET /s/<site>/api/v1/entries.json?find[dateString][$gt]=ISO&count=N
//   GET /s/<site>/api/v1/treatments.json?find[created_at][$gt]=ISO&count=N
//   GET /s/<site>/api/v1/devicestatus.json?find[created_at][$gt]=ISO&count=N
//   GET /s/<site>/api/v1/profiles.json, /api/v1/profile.json -> []
// Data is synthetic looping data, a pure function of (site, time): a CGM entry and a loop
// devicestatus every 5 minutes, a correction bolus every 30 minutes, each visible once the clock
// passes its timestamp, from historyStartMs on. The scorer uses the same generator, so the
// expected set is known without asking the server (a stopped server still has expectations).
//
//   node upstream.cjs serve      env UPSTREAM_SITES_FILE (JSON {"<site>": "<token>"}), UPSTREAM_HISTORY_START_MS, PORT
// Synthetic data only; no clinical meaning.
const crypto = require('node:crypto');
const http = require('node:http');
const fs = require('node:fs');

const STEP = 5 * 60 * 1000;
const KINDS = Object.freeze({
  entries: { field: 'dateString', offsetMs: 0, every: 1 },
  devicestatus: { field: 'created_at', offsetMs: 20000, every: 1 },
  treatments: { field: 'created_at', offsetMs: 40000, every: 6 },
});
const hex = text => crypto.createHash('sha1').update(text).digest('hex').slice(0, 24);
// Per-site phase so sites do not all land on the same instant (0..290 s in 10 s steps).
const phase = site => (Number.parseInt(hex('phase:' + site).slice(0, 6), 16) % 30) * 10000;

function at (site, kind, k) { return k * STEP + phase(site) + KINDS[kind].offsetMs; }
function record (site, kind, k) {
  const t = at(site, kind, k), iso = new Date(t).toISOString(), id = hex(site + ':' + kind + ':' + k);
  const sgv = 110 + Math.round(45 * Math.sin(k / 9 + Number.parseInt(hex(site).slice(0, 4), 16)));
  if (kind === 'entries') return { _id: id, type: 'sgv', sgv, direction: 'Flat', device: 'synthetic-upstream', date: t, dateString: iso };
  if (kind === 'devicestatus') {
    return { _id: id, created_at: iso, device: 'synthetic-loop',
      loop: { timestamp: iso, iob: { iob: 1.2, timestamp: iso }, cob: { cob: 0, timestamp: iso },
        predicted: { startDate: iso, values: [sgv, sgv - 2, sgv - 4, sgv - 5, sgv - 6, sgv - 6] } } };
  }
  return { _id: id, created_at: iso, eventType: 'Correction Bolus', insulin: 0.5, enteredBy: 'synthetic-upstream' };
}
// Records of `kind` with historyStart <= time <= until, newest first. `since` is exclusive.
function records (site, kind, { historyStartMs, sinceMs = -Infinity, untilMs, limit = Infinity }) {
  const spec = KINDS[kind], out = [];
  for (let k = Math.floor((untilMs - phase(site)) / STEP) + 1; out.length < limit; k--) {
    const t = at(site, kind, k);
    if (t > untilMs) continue;
    if (t < historyStartMs || t <= sinceMs) break;
    if (k % spec.every === 0) out.push(record(site, kind, k));
  }
  return out;
}
// The identity a stored copy keeps: the record time in ms (entries `date`, others `created_at`).
const keyOf = (kind, doc) => kind === 'entries' ? Number(doc.date) : Date.parse(doc.created_at);

function bearerFor (secret, site, token) { return 'synthetic.' + crypto.createHmac('sha256', secret).update(site + ':' + token).digest('hex'); }

function createServer ({ sites, historyStartMs, now = Date.now, secret = crypto.randomBytes(16) }) {
  const counters = { requests: 0, refused: 0, served: 0 };
  const server = http.createServer((req, res) => {
    counters.requests += 1;
    const reply = (status, body) => { res.writeHead(status, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)); };
    const url = new URL(req.url, 'http://upstream.invalid');
    if (url.pathname === '/healthz') return reply(200, { ok: true, ...counters });
    const m = /^\/s\/([a-z0-9-]{1,32})(\/api\/.*)$/.exec(url.pathname);
    if (req.method !== 'GET' || !m || !Object.hasOwn(sites, m[1])) { counters.refused += 1; return reply(404, { status: 404 }); }
    const [, site, route] = m;
    const auth = /^\/api\/v2\/authorization\/request\/([^/]+)$/.exec(route);
    if (auth) {
      if (auth[1] !== sites[site]) { counters.refused += 1; return reply(401, { status: 401 }); }
      const iat = Math.floor(now() / 1000);
      return reply(200, { token: bearerFor(secret, site, sites[site]), iat, exp: iat + 8 * 3600 });
    }
    if (req.headers.authorization !== 'Bearer ' + bearerFor(secret, site, sites[site])) { counters.refused += 1; return reply(401, { status: 401 }); }
    if (route === '/api/v1/profiles.json' || route === '/api/v1/profile.json') return reply(200, []);
    const coll = /^\/api\/v1\/(entries|treatments|devicestatus)\.json$/.exec(route);
    if (!coll) { counters.refused += 1; return reply(404, { status: 404 }); }
    const kind = coll[1], field = KINDS[kind].field;
    const since = url.searchParams.get('find[' + field + '][$gt]');
    const sinceMs = since ? Date.parse(since) : -Infinity;
    const count = Math.min(Number(url.searchParams.get('count') || 10), 10000);
    if (Number.isNaN(sinceMs) || !Number.isSafeInteger(count) || count < 1) { counters.refused += 1; return reply(400, { status: 400 }); }
    const out = records(site, kind, { historyStartMs, sinceMs, untilMs: now(), limit: count });
    counters.served += out.length;
    return reply(200, out);
  });
  server.counters = counters;
  return server;
}

if (require.main === module && process.argv[2] === 'serve') {
  const sites = JSON.parse(fs.readFileSync(process.env.UPSTREAM_SITES_FILE, 'utf8'));
  const historyStartMs = Number(process.env.UPSTREAM_HISTORY_START_MS);
  if (!Number.isSafeInteger(historyStartMs)) throw new Error('UPSTREAM_HISTORY_START_MS required');
  const server = createServer({ sites, historyStartMs });
  server.listen(Number(process.env.PORT || 1337), '0.0.0.0', () => console.log(JSON.stringify({ state: 'upstream-listening', sites: Object.keys(sites).length, historyStartMs })));
  process.on('SIGTERM', () => server.close(() => process.exit(0)));
}
module.exports = { STEP, KINDS, phase, at, record, records, keyOf, createServer };
