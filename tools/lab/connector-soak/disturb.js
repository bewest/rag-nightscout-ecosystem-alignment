#!/usr/bin/env node
'use strict';
/*
 * disturb.js - source-side changes a real site sees, made through the
 * source's own API, each recorded so the analyser reports it separately:
 *
 *   update-treatment  PUT a changed carbs value on an already-synced treatment
 *   update-entry      re-POST an already-synced sgv with a different value
 *                     (same date+type: the source's upsert replaces it)
 *   delete            DELETE one already-synced treatment, entry, devicestatus
 *   backdate          POST a NEW treatment and a NEW sgv whose timestamps are
 *                     older than records the sinks already hold (a carb entry
 *                     logged "20 minutes ago"; an sgv backfilled after a gap)
 *
 * Environment: TARGET, SECRET_FILE, MONGO (source db URL), OUT (dir with
 * exclude.txt and disturb.jsonl), NODE_PATH with `mongodb`.
 *   node disturb.js <action>
 * Records chosen are 60-120 minutes old, so every sink has held them.
 */
const http = require('http');
const crypto = require('crypto');
const fs = require('fs');
const { MongoClient } = require('mongodb');

const TARGET = process.env.TARGET;
const HASH = crypto.createHash('sha1').update(fs.readFileSync(process.env.SECRET_FILE, 'utf8').trim()).digest('hex');
const OUT = process.env.OUT;
const action = process.argv[2];

function call (method, path, body) {
  const u = new URL(path, TARGET);
  const data = body ? Buffer.from(JSON.stringify(body)) : null;
  return new Promise((resolve, reject) => {
    const r = http.request({ hostname: u.hostname, port: u.port, path: u.pathname, method,
      headers: { 'api-secret': HASH, 'content-type': 'application/json', ...(data ? { 'content-length': data.length } : {}) } }, (res) => {
      let buf = ''; res.on('data', (c) => { buf += c; });
      res.on('end', () => res.statusCode === 200 ? resolve(buf) : reject(new Error(method + ' ' + u.pathname + ' HTTP ' + res.statusCode)));
    });
    r.on('error', reject); r.end(data || undefined);
  });
}
function record (what, soakId, detail) {
  fs.appendFileSync(`${OUT}/exclude.txt`, soakId + '\n');
  const line = { t: new Date().toISOString(), action: what, soakId, ...detail };
  fs.appendFileSync(`${OUT}/disturb.jsonl`, JSON.stringify(line) + '\n');
  console.log(JSON.stringify(line));
}

(async () => {
  const cli = new MongoClient(process.env.MONGO); await cli.connect();
  const db = cli.db();
  const now = Date.now(), lo = now - 120 * 60000, hi = now - 60 * 60000;
  const iso = (ms) => new Date(ms).toISOString();
  if (action === 'update-treatment') {
    const t = await db.collection('treatments').findOne({ eventType: 'Carb Correction', created_at: { $gt: iso(lo), $lt: iso(hi) } });
    const changed = { ...t, _id: String(t._id), carbs: t.carbs + 7 };
    await call('PUT', '/api/v1/treatments', changed);
    record('update-treatment', t.soakId, { field: 'carbs', from: t.carbs, to: changed.carbs });
  } else if (action === 'update-entry') {
    const e = await db.collection('entries').findOne({ type: 'sgv', date: { $gt: lo, $lt: hi } });
    const re = { type: 'sgv', sgv: e.sgv + 11, direction: e.direction, device: e.device, date: e.date, dateString: iso(e.date), noise: e.noise, soakId: e.soakId };
    await call('POST', '/api/v1/entries', [re]);
    record('update-entry', e.soakId, { field: 'sgv', from: e.sgv, to: re.sgv });
  } else if (action === 'delete') {
    const t = await db.collection('treatments').findOne({ eventType: 'Correction Bolus', created_at: { $gt: iso(lo), $lt: iso(hi) } });
    await call('DELETE', '/api/v1/treatments/' + t._id);
    record('delete', t.soakId, { coll: 'treatments' });
    const e = await db.collection('entries').find({ type: 'sgv', date: { $gt: lo, $lt: hi } }).sort({ date: -1 }).limit(1).next();
    await call('DELETE', '/api/v1/entries/' + e._id);
    record('delete', e.soakId, { coll: 'entries' });
    const d = await db.collection('devicestatus').findOne({ created_at: { $gt: iso(lo), $lt: iso(hi) } });
    await call('DELETE', '/api/v1/devicestatus/' + d._id);
    record('delete', d.soakId, { coll: 'devicestatus' });
    for (const [c, id] of [['treatments', t._id], ['entries', e._id], ['devicestatus', d._id]]) {
      const left = await db.collection(c).countDocuments({ _id: id });
      console.log(JSON.stringify({ check: 'source still holds deleted ' + c, count: left }));
    }
  } else if (action === 'backdate') {
    const tms = now - 20 * 60000 + 13000;
    const t = { soakId: 'cksoak-carb-backdated-' + tms, eventType: 'Carb Correction', carbs: 25, enteredBy: 'cksoak-writer', created_at: iso(tms) };
    await call('POST', '/api/v1/treatments', [t]);
    record('backdate', t.soakId, { coll: 'treatments', at: t.created_at, age_min: 20 });
    const ems = now - 12 * 60000 + 150000; // between two grid readings, 12 min old
    const e = { soakId: 'cksoak-sgv-backdated-' + ems, type: 'sgv', sgv: 123, direction: 'Flat', device: 'synthetic://cksoak/cgm', date: ems, dateString: iso(ems), noise: 1 };
    await call('POST', '/api/v1/entries', [e]);
    record('backdate', e.soakId, { coll: 'entries', at: e.dateString, age_min: 9.5 });
  } else {
    throw new Error('action: update-treatment | update-entry | delete | backdate');
  }
  await cli.close();
})().catch((err) => { console.error(err.message); process.exit(1); });
