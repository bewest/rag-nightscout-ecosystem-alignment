#!/usr/bin/env node
'use strict';
// fake-share.js — a local stand-in for Dexcom Share, for the journey lab's CGM-first sites.
// Contributor-facing; synthetic only; not medical advice.
//
// A cgm-* site runs the real nightscout-connect `dexcomshare` driver (the version the tree pins)
// with CONNECT_SHARE_SERVER=localhost:<port>, and trusts this server's certificate through
// NODE_EXTRA_CA_CERTS. So the connector's own login, session, polling, backfill window and
// Dexcom→Nightscout mapping all run unmodified; only the vendor is fake. The endpoints and
// shapes follow nightscout-connect lib/sources/dexcomshare.js (auth / login / LatestGlucose,
// [{WT, ST, DT, Value, Trend}]).
//
// Each Share account (CONNECT_SHARE_ACCOUNT_NAME, one per site) gets its own deterministic trace
// from household.js. A file "$STATE/share-pause-<account>" makes that account return no new
// readings (signal loss / sensor warm-up) until it is removed. Every request is appended to OUT.
//
// Env: PORT, CERT, KEY, OUT, PIDFILE, LAB_TZ.
const fs = require('fs');
const path = require('path');
const https = require('https');
const crypto = require('crypto');
const H = require('./household');

const STATE = path.dirname(process.env.OUT);
const MIN = 60 * 1000;
const sessions = new Map(); // sessionID -> account
const accountIds = new Map(); // accountId (from the auth step) -> account name
if (process.env.PIDFILE) fs.writeFileSync(process.env.PIDFILE, String(process.pid));
const log = (x) => fs.appendFileSync(process.env.OUT, JSON.stringify(Object.assign({ t: new Date().toISOString() }, x)) + '\n');
const uuidFor = (s) => { const h = crypto.createHash('sha1').update(s).digest('hex'); return `${h.slice(0, 8)}-${h.slice(8, 12)}-4${h.slice(13, 16)}-a${h.slice(17, 20)}-${h.slice(20, 32)}`; };

function readings (account, minutes, maxCount) {
  const now = Date.now();
  const paused = fs.existsSync(path.join(STATE, 'share-pause-' + account)) ? fs.statSync(path.join(STATE, 'share-pause-' + account)).mtimeMs : null;
  const p = H.plan({ start: now - 2 * 24 * 60 * MIN - 5 * MIN, end: now, controller: 'cgm', seed: 'share:' + account, tz: process.env.LAB_TZ || 'UTC' });
  const since = now - minutes * MIN;
  return p.readings.filter(r => r.t >= since && r.t <= now && (paused === null || r.t < paused))
    .reverse().slice(0, maxCount) // Share answers newest first
    .map(r => ({ WT: `/Date(${r.t})/`, ST: `/Date(${r.t})/`, DT: `/Date(${r.t})/`, Value: r.sgv, Trend: r.direction }));
}

const server = https.createServer({ cert: fs.readFileSync(process.env.CERT), key: fs.readFileSync(process.env.KEY) }, (req, res) => {
  let body = '';
  req.on('data', c => { body += c; });
  req.on('end', () => {
    const u = new URL(req.url, 'https://localhost');
    let j = {}; try { j = JSON.parse(body || '{}'); } catch (e) {}
    const send = (code, obj) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(obj)); };
    if (u.pathname.endsWith('/General/AuthenticatePublisherAccount')) {
      log({ path: 'auth', account: j.accountName });
      const id = uuidFor('account:' + j.accountName); accountIds.set(id, j.accountName);
      return send(200, id);
    }
    if (u.pathname.endsWith('/General/LoginPublisherAccountById')) {
      const account = accountIds.get(j.accountId);
      if (!account) { log({ path: 'login', error: 'AccountNotFound' }); return send(500, { Code: 'AccountNotFound' }); }
      const sid = uuidFor('session:' + j.accountId + ':' + Date.now());
      sessions.set(sid, account);
      log({ path: 'login', session: sid.slice(0, 8) });
      return send(200, sid);
    }
    if (u.pathname.endsWith('/Publisher/ReadPublisherLatestGlucoseValues')) {
      const sid = u.searchParams.get('sessionID');
      const account = sessions.get(sid);
      if (!account) { log({ path: 'glucose', error: 'SessionNotValid' }); return send(500, { Code: 'SessionIdNotFound', Message: 'lab: unknown session' }); }
      const minutes = Number(u.searchParams.get('minutes') || 1440); const maxCount = Number(u.searchParams.get('maxCount') || 1);
      const out = readings(account, minutes, maxCount);
      log({ path: 'glucose', account, minutes, maxCount, returned: out.length, newest: out[0] ? out[0].Value : null });
      return send(200, out);
    }
    log({ path: u.pathname, error: 'not found' }); send(404, { Code: 'NotFound' });
  });
});
server.listen(Number(process.env.PORT), '127.0.0.1');
