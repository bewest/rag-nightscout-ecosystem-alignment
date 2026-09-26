#!/usr/bin/env node
'use strict';
/*
 * sampler.js - every INTERVAL_SEC, for each arm: is the process alive, its
 * RSS and open fds from /proc, an authenticated status read, a fresh read of
 * the newest entry through the server (compared with the newest reading the
 * traffic driver saw acknowledged), and document counts and connection counts
 * read FROM MONGO (never through the server under test). Adapted from
 * tools/lab/connector-soak/sampler.js.
 *
 * A dead server answers "nothing new" exactly like an idle one, so every
 * sample carries `live` and `fresh` for every arm; the analyser refuses to
 * call a run a pass unless both hold.
 *
 * Environment:
 *   RUN       run directory (reads state.json, writes samples.jsonl)
 *   ARMS      comma list name=httpBase|mongoURL|secretFile|pidFile
 *   MODULES   node_modules with `mongodb`
 *   INTERVAL_SEC  default 10
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { MongoClient } = require(path.join(process.env.MODULES, 'mongodb'));

const RUN = process.env.RUN;
fs.writeFileSync(path.join(RUN, 'pid-sampler'), String(process.pid));
const INTERVAL = Number(process.env.INTERVAL_SEC || 10) * 1000;
const COLLS = ['entries', 'treatments', 'devicestatus', 'profile', 'food', 'activity'];
const arms = process.env.ARMS.split(',').map((spec) => {
  const [name, rest] = spec.split('=');
  const [base, mongo, secretFile, pidFile] = rest.split('|');
  return { name, base, mongo, pidFile, hash: crypto.createHash('sha1').update(fs.readFileSync(secretFile, 'utf8').trim()).digest('hex') };
});

async function get (arm, p) {
  const t0 = Date.now();
  try {
    const r = await fetch(arm.base + p, { headers: { 'api-secret': arm.hash }, signal: AbortSignal.timeout(15000) });
    const text = await r.text(); let j; try { j = JSON.parse(text); } catch (e) { /* */ }
    return { st: r.status, ms: Date.now() - t0, j };
  } catch (err) { return { st: 0, ms: Date.now() - t0, err: (err.cause && err.cause.code) || err.name }; }
}
function proc (pidFile) {
  try {
    const pid = Number(fs.readFileSync(pidFile, 'utf8').trim());
    const st = fs.readFileSync('/proc/' + pid + '/status', 'utf8');
    const cmd = fs.readFileSync('/proc/' + pid + '/cmdline', 'utf8').replace(/\0/g, ' ');
    return { pid, alive: cmd.includes('lib/server/server.js'), rss_kb: Number((st.match(/VmRSS:\s+(\d+)/) || [])[1]), fds: fs.readdirSync('/proc/' + pid + '/fd').length };
  } catch (err) { return { alive: false }; }
}
const clients = {};
async function mongoSample (arm) {
  try {
    if (!clients[arm.name]) { clients[arm.name] = new MongoClient(arm.mongo, { serverSelectionTimeoutMS: 4000 }); await clients[arm.name].connect(); }
    const db = clients[arm.name].db();
    const o = { ok: true, conn: (await db.admin().serverStatus()).connections.current };
    for (const c of COLLS) o[c] = await db.collection(c).estimatedDocumentCount();
    return o;
  } catch (err) {
    if (clients[arm.name]) clients[arm.name].close().catch(() => {});
    delete clients[arm.name];
    return { ok: false, err: err.message.slice(0, 120) };
  }
}

async function tick () {
  let state = {}; try { state = JSON.parse(fs.readFileSync(path.join(RUN, 'state.json'), 'utf8')); } catch (e) { /* not started */ }
  const rows = await Promise.all(arms.map(async (arm) => {
    const s = { arm: arm.name, proc: proc(arm.pidFile) };
    const st = await get(arm, '/api/v1/status.json');
    s.live = { st: st.st, ms: st.ms, ok: st.st === 200 && Boolean(st.j && st.j.status === 'ok') };
    const e = await get(arm, '/api/v1/entries.json?count=1');
    const newest = e.st === 200 && Array.isArray(e.j) && e.j[0] ? e.j[0].date : null;
    const want = state.lastSgv ? state.lastSgv[arm.name] : null;
    // fresh: the server returns a reading at least as new as the last one the driver saw it acknowledge
    s.fresh = { st: e.st, newest, want, ok: e.st === 200 && (want === null || want === undefined ? true : newest !== null && newest >= want) };
    s.mongo = await mongoSample(arm);
    return s;
  }));
  fs.appendFileSync(path.join(RUN, 'samples.jsonl'), JSON.stringify({ t: new Date().toISOString(), n: state.n, samples: rows }) + '\n');
}

let stop = false; let wake = null;
process.on('SIGTERM', () => { stop = true; if (wake) wake(); }); // do not wait out the interval
(async () => {
  while (!stop) {
    const t0 = Date.now();
    try { await tick(); } catch (err) { console.log(new Date().toISOString() + ' sample failed: ' + err.message); }
    if (!stop) await new Promise((r) => { const t = setTimeout(r, Math.max(500, INTERVAL - (Date.now() - t0))); wake = () => { clearTimeout(t); r(); }; });
  }
  for (const c of Object.values(clients)) await c.close().catch(() => {});
  process.exit(0);
})();
