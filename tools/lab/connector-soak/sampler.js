#!/usr/bin/env node
'use strict';
/*
 * sampler.js - every INTERVAL_SEC, measure the source and each sink FROM
 * MONGO (never through the endpoint under test), record when each lab record
 * first appears in each sink, and assert liveness of every server with a
 * fresh authenticated read that must succeed.
 *
 * A dead sink answers "no new data" exactly like a sink that is correctly
 * idle, so every sample carries `live` for every server; a sample in which a
 * server is not live is not evidence about that server.
 *
 * Environment:
 *   TARGETS   comma list name=mongoURL|httpURL|secretFile
 *             e.g. s=mongodb://cksoak-mongo-s:27017/cksoak_s|http://cksoak-s:1337|/state/secrets/s
 *   OUT       directory for samples.jsonl and seen-<name>.jsonl
 *   INTERVAL_SEC  default 60
 * Run with NODE_PATH pointing at a node_modules that has `mongodb`.
 */
const fs = require('fs');
const http = require('http');
const crypto = require('crypto');
const { MongoClient } = require('mongodb');

const OUT = process.env.OUT;
const INTERVAL = Number(process.env.INTERVAL_SEC || 60) * 1000;
const COLLS = ['entries', 'treatments', 'devicestatus', 'profile'];
const targets = process.env.TARGETS.split(',').map((spec) => {
  const [name, rest] = spec.split('=');
  const [mongo, url, secretFile] = rest.split('|');
  return { name, mongo, url, secretFile };
});

function get (url, secretFile) {
  const hash = crypto.createHash('sha1').update(fs.readFileSync(secretFile, 'utf8').trim()).digest('hex');
  return new Promise((resolve) => {
    const r = http.get(url, { headers: { 'api-secret': hash }, timeout: 15000 }, (res) => {
      let buf = '';
      res.on('data', (c) => { buf += c; });
      res.on('end', () => {
        let n = null;
        try { const j = JSON.parse(buf); n = Array.isArray(j) ? j.length : null; } catch (e) { /* not json */ }
        resolve({ status: res.statusCode, rows: n });
      });
    });
    r.on('timeout', () => r.destroy(new Error('timeout')));
    r.on('error', (err) => resolve({ status: 0, error: err.code || err.message }));
  });
}

const seen = {};
for (const t of targets) {
  seen[t.name] = new Set();
  const f = `${OUT}/seen-${t.name}.jsonl`;
  if (fs.existsSync(f)) fs.readFileSync(f, 'utf8').split('\n').filter(Boolean).forEach((l) => seen[t.name].add(JSON.parse(l).soakId + '|' + JSON.parse(l).coll));
}

const clients = {};
async function db (t) {
  if (!clients[t.name]) {
    clients[t.name] = new MongoClient(t.mongo, { serverSelectionTimeoutMS: 5000 });
    await clients[t.name].connect();
  }
  return clients[t.name].db();
}

async function sampleOne (t, now) {
  const out = { name: t.name };
  // Liveness: an authenticated status read must return 200. It says the
  // server is up and answering authenticated requests, independent of whether
  // it holds data (a control sink that correctly holds nothing is still live).
  out.live = await get(t.url + '/api/v1/status.json', t.secretFile);
  out.live.ok = out.live.status === 200;
  // Fresh read: the newest entry through the server's own API (200 + 1 row
  // once the server holds data). Counts below come from mongo, not from here.
  out.fresh = await get(t.url + '/api/v1/entries.json?count=1', t.secretFile);
  out.fresh.ok = out.fresh.status === 200 && out.fresh.rows === 1;
  try {
    const d = await db(t);
    out.mongo = true;
    // Connection counts on this server's mongod (BF-10: fd exhaustion). The
    // sampler's own client is one of `current`, constant across the run.
    const conn = (await d.admin().serverStatus()).connections;
    out.conn = { current: conn.current, totalCreated: conn.totalCreated, available: conn.available };
    for (const c of COLLS) {
      const col = d.collection(c);
      out[c] = await col.countDocuments({});
      const docs = await col.find({ soakId: { $exists: true } }, { projection: { soakId: 1 } }).toArray();
      out[c + '_soak'] = docs.length;
      out[c + '_soak_distinct'] = new Set(docs.map((x) => x.soakId)).size;
      const f = `${OUT}/seen-${t.name}.jsonl`;
      for (const x of docs) {
        const k = x.soakId + '|' + c;
        if (!seen[t.name].has(k)) {
          seen[t.name].add(k);
          fs.appendFileSync(f, JSON.stringify({ soakId: x.soakId, coll: c, firstSeen: now.toISOString() }) + '\n');
        }
      }
    }
    const last = await d.collection('entries').find({ type: 'sgv' }).sort({ date: -1 }).limit(1).toArray();
    out.newest_sgv = last.length ? new Date(last[0].date).toISOString() : null;
    out.newest_sgv_age_s = last.length ? Math.round((now.getTime() - last[0].date) / 1000) : null;
  } catch (err) {
    out.mongo = false;
    out.error = err.message;
    if (clients[t.name]) clients[t.name].close().catch(() => {});
    delete clients[t.name];
  }
  return out;
}

async function tick () {
  const now = new Date();
  const rows = await Promise.all(targets.map((t) => sampleOne(t, now)));
  fs.appendFileSync(`${OUT}/samples.jsonl`, JSON.stringify({ t: now.toISOString(), samples: rows }) + '\n');
}

(async function loop () {
  for (;;) {
    const started = Date.now();
    try { await tick(); } catch (err) { console.log(new Date().toISOString() + ' sample failed: ' + err.message); }
    await new Promise((r) => setTimeout(r, Math.max(1000, INTERVAL - (Date.now() - started))));
  }
})();
