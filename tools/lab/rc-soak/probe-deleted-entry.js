#!/usr/bin/env node
'use strict';
// probe-deleted-entry.js - does a glucose reading deleted through
// DELETE /api/v1/entries/<id> disappear from GET /api/v1/entries.json?
//
//   node probe-deleted-entry.js <base-url> <secret-file>
//
// Writes 30 synthetic readings (5 min apart, the newest 1 min ago), deletes
// the third newest by the _id the server returned, then reads twice:
//   plain     /api/v1/entries.json?count=10   (can be answered from memory)
//   storage   the same with find[sgv][$gte]=0 (must be answered from MongoDB)
// Prints one JSON line; exit 1 when the deleted reading is still returned by
// either read, 2 when the probe could not run (a dead server is never a pass).
// Synthetic data only; the server should be a lab server with an empty database.
const fs = require('fs');
const crypto = require('crypto');

const [BASE, SECRET_FILE] = process.argv.slice(2);
const HASH = crypto.createHash('sha1').update(fs.readFileSync(SECRET_FILE, 'utf8').trim()).digest('hex');
const H = { 'api-secret': HASH, 'content-type': 'application/json' };
const call = async (method, p, body) => {
  const r = await fetch(BASE + p, { method, headers: H, body: body ? JSON.stringify(body) : undefined });
  const t = await r.text(); let j; try { j = JSON.parse(t); } catch (e) { /* */ }
  return { st: r.status, j };
};
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const out = { base: BASE, t: new Date().toISOString() };
  out.live_before = (await call('GET', '/api/v1/status.json')).st;
  const now = Math.floor(Date.now() / 60000) * 60000 - 60000;
  const docs = Array.from({ length: 30 }, (_, i) => { const d = now - i * 300000; return { type: 'sgv', sgv: 100 + i, date: d, dateString: new Date(d).toISOString(), device: 'probe-deleted-entry', direction: 'Flat' }; });
  out.post = (await call('POST', '/api/v1/entries', docs)).st;
  await wait(3000);
  const before = await call('GET', '/api/v1/entries.json?count=10');
  const victim = before.j && before.j[2];
  if (!victim || !victim._id) { out.error = 'no reading to delete'; console.log(JSON.stringify(out)); process.exit(2); }
  out.deleted = { date: victim.dateString, id_form: typeof victim._id };
  out.delete = (await call('DELETE', '/api/v1/entries/' + victim._id)).st;
  await wait(3000);
  const plain = await call('GET', '/api/v1/entries.json?count=10');
  const storage = await call('GET', '/api/v1/entries.json?count=10&find[sgv][$gte]=0');
  const has = (r) => Array.isArray(r.j) && r.j.some((e) => e.date === victim.date && e.device === 'probe-deleted-entry');
  out.plain = { st: plain.st, still_returned: has(plain) };
  out.storage = { st: storage.st, still_returned: has(storage) };
  out.live_after = (await call('GET', '/api/v1/status.json')).st;
  console.log(JSON.stringify(out));
  if (out.live_before !== 200 || out.live_after !== 200 || out.delete !== 200 || plain.st !== 200 || storage.st !== 200) process.exit(2);
  process.exit(out.plain.still_returned || out.storage.still_returned ? 1 : 0);
})().catch((e) => { console.error(e.message); process.exit(2); });
