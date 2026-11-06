'use strict';
// M4-only synthetic Share fixture. Generate the trace once at a fixed base;
// later requests select from that immutable trace instead of re-integrating it.
const MIN = 60000;
function fixtureSeries (base, count = 240) {
  if (!Number.isFinite(base)) throw new Error('M4_BASE must be a finite timestamp');
  const newest = Math.floor(base / (5 * MIN)) * 5 * MIN - 5 * MIN;
  return Array.from({ length: count }, (_, i) => {
    const date = newest - (count - 1 - i) * 5 * MIN;
    return { sgv: 100 + (i % 41), date, dateString: new Date(date).toISOString(),
      trend: 4, direction: 'Flat', device: 'nightscout-connect', type: 'sgv' };
  });
}
function selectReadings (series, now, minutes, maxCount) {
  if (!Number.isFinite(minutes) || !Number.isFinite(maxCount) || minutes < 0 || maxCount < 0) return [];
  return series.filter(r => r.date >= now - minutes * MIN && r.date <= now)
    .slice().reverse().slice(0, Math.floor(maxCount))
    .map(r => ({ WT: `/Date(${r.date})/`, ST: `/Date(${r.date})/`, DT: `/Date(${r.date})/`, Value: r.sgv, Trend: r.trend }));
}
function serve () {
  const fs = require('node:fs');
  const https = require('node:https');
  const crypto = require('node:crypto');
  const series = fixtureSeries(Number(process.env.M4_BASE));
  const accountId = '11111111-1111-4111-8111-111111111111';
  const sessions = new Set();
  const log = value => fs.appendFileSync(process.env.OUT, JSON.stringify(value) + '\n');
  const server = https.createServer({ cert: fs.readFileSync(process.env.CERT), key: fs.readFileSync(process.env.KEY) }, (req, res) => {
    let bytes = '';
    req.on('data', b => { bytes += b; });
    req.on('end', () => {
      const url = new URL(req.url, 'https://localhost');
      let body = {}; try { body = JSON.parse(bytes || '{}'); } catch {}
      const send = (status, value) => { res.writeHead(status, { 'content-type': 'application/json' }); res.end(JSON.stringify(value)); };
      if (url.pathname.endsWith('/General/AuthenticatePublisherAccount')) {
        log({ path: 'auth' }); return send(200, accountId);
      }
      if (url.pathname.endsWith('/General/LoginPublisherAccountById')) {
        if (body.accountId !== accountId) return send(500, { Code: 'AccountNotFound' });
        const id = crypto.randomUUID(); sessions.add(id); log({ path: 'login' }); return send(200, id);
      }
      if (url.pathname.endsWith('/Publisher/ReadPublisherLatestGlucoseValues')) {
        if (!sessions.has(url.searchParams.get('sessionID'))) return send(500, { Code: 'SessionIdNotFound' });
        const minutes = Number(url.searchParams.get('minutes') ?? 1440);
        const maxCount = Number(url.searchParams.get('maxCount') ?? 1);
        const out = selectReadings(series, Date.now(), minutes, maxCount);
        log({ path: 'glucose', minutes, maxCount, returned: out.length });
        return send(200, out);
      }
      return send(404, { Code: 'NotFound' });
    });
  });
  server.listen(Number(process.env.PORT), '127.0.0.1');
}
module.exports = { fixtureSeries, selectReadings };
if (require.main === module) serve();
