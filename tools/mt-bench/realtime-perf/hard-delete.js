#!/usr/bin/env node
'use strict';
// End-to-end hard delete (BF/decision incremental-refresh, evaluator-lane finding): a stock-style
// socket on one tenant, one synthetic sgv posted, then the entry hard-deleted through v1
// (postgres-entries-write remove: no write-clock stamp). Records when the first frame without the
// reading arrives. NODE_PATH=<core>/node_modules. Synthetic data only.
//   hard-delete.js --base URL --tenants FILE --out FILE [--limit 180]
const fs = require('node:fs');
const http = require('node:http');
const { io } = require('socket.io-client');
const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (i % 2 ? a : [...a, [v.replace(/^--/, ''), all[i + 1]]]), []));
const base = new URL(args.base), t = JSON.parse(fs.readFileSync(args.tenants, 'utf8'))[0];
const LIMIT = Number(args.limit || 180) * 1000;
const lookup = (hostname, options, cb) => (options && options.all) ? cb(null, [{ address: base.hostname, family: 4 }]) : cb(null, base.hostname, 4);
const agent = new http.Agent({ keepAlive: true, lookup });
const sleep = ms => new Promise(r => setTimeout(r, ms));
function request (method, path, body) {
  return new Promise((resolve, reject) => {
    const data = body === undefined ? null : JSON.stringify(body);
    const req = http.request({ host: base.hostname, port: base.port, method, path, agent,
      headers: { host: t.host, accept: 'application/json', ...(data ? { 'content-type': 'application/json', 'content-length': Buffer.byteLength(data) } : {}) }, timeout: 30000 }, res => {
      let text = ''; res.on('data', d => { text += d; }); res.on('end', () => resolve({ status: res.statusCode, text }));
    });
    req.on('error', reject); if (data) req.write(data); req.end();
  });
}
(async () => {
  const token = encodeURIComponent(t.token);
  const jwt = JSON.parse((await request('GET', '/api/v2/authorization/request/' + token)).text).token;
  const date = Date.now() - 120000, frames = [];
  const socket = io('http://' + t.host + ':' + base.port, { transports: ['polling'], agent });
  socket.on('connect', () => socket.emit('authorize', { client: 'web', token: jwt, history: 1 }, () => {}));
  socket.on('dataUpdate', frame => frames.push({ at: Date.now(), has: (frame.sgvs || []).some(s => s.mills === date) }));
  while (!frames.length) await sleep(100);
  const posted = await request('POST', '/api/v1/entries?token=' + token, [{ type: 'sgv', sgv: 123, date, dateString: new Date(date).toISOString(), device: 'ns-prt-hard-delete' }]);
  const t0 = Date.now();
  while (!frames.some(f => f.has) && Date.now() - t0 < 30000) await sleep(100);
  const shown = frames.find(f => f.has);
  const found = JSON.parse((await request('GET', '/api/v1/entries.json?token=' + token + '&find[date]=' + date + '&count=1')).text);
  const id = found[0] && found[0]._id;
  const deleted = await request('DELETE', '/api/v1/entries/' + encodeURIComponent(id) + '?token=' + token);
  const d0 = Date.now();
  while (Date.now() - d0 < LIMIT && !frames.some(f => f.at > d0 && !f.has)) await sleep(100);
  const gone = frames.find(f => f.at > d0 && !f.has);
  const after = JSON.parse((await request('GET', '/api/v1/entries.json?token=' + token + '&find[date]=' + date + '&count=1')).text);
  const out = { postStatus: posted.status, shownAfterMs: shown ? shown.at - t0 : null, deleteStatus: deleted.status, storedAfterDelete: after.length,
    removedFromDisplayAfterMs: gone ? gone.at - d0 : null, limitMs: LIMIT, frames: frames.length };
  fs.writeFileSync(args.out, JSON.stringify(out, null, 2) + '\n'); console.log(JSON.stringify(out));
  socket.close(); process.exit(0);
})().catch(e => { console.error('hard-delete failed', e && e.message); process.exit(1); });
