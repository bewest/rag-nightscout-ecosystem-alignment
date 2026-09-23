#!/usr/bin/env node
'use strict';
/*
 * writer.js - seed a source Nightscout with SYNTHETIC history, then keep
 * writing new records at a realistic cadence, and keep a ledger of every
 * record that the source acknowledged.
 *
 * Every value written here is generated in this file. Nothing is read from
 * any real person's data. Each record carries `soakId`, a lab-only field the
 * sink copies verbatim, so the analyser can match source and sink documents
 * without relying on the sink's dedup keys.
 *
 * Environment:
 *   TARGET        source base URL, e.g. http://cksoak-s:1337
 *   SECRET_FILE   file holding the source API_SECRET (raw); never logged
 *   LEDGER        JSONL file, one line per acknowledged record
 *   SEED_HOURS    history to seed on first start (default 60)
 *   TICK_SEC      sgv cadence in seconds (default 300)
 *
 * Cadence (by tick number n, one tick per TICK_SEC):
 *   every tick           sgv
 *   n % 3 == 0           devicestatus
 *   n % 9 == 0           Carb Correction
 *   n % 9 == 4           Correction Bolus
 *   n % 6 == 2           Temp Basal (30 min)
 *   n % 72 == 36         mbg (fingerstick) entry
 * A write the source refuses or cannot receive is queued and retried every
 * 30 s, the way an uploader backfills; the ledger records both the record's
 * own timestamp and the time the source acknowledged it.
 */
const http = require('http');
const crypto = require('crypto');
const fs = require('fs');

const TARGET = process.env.TARGET;
const SECRET = fs.readFileSync(process.env.SECRET_FILE, 'utf8').trim();
const HASH = crypto.createHash('sha1').update(SECRET).digest('hex');
const LEDGER = process.env.LEDGER;
const SEED_HOURS = Number(process.env.SEED_HOURS || 60);
const TICK = Number(process.env.TICK_SEC || 300) * 1000;
const DEVICE = 'synthetic://cksoak/cgm';
const LOOP = 'synthetic://cksoak/loop';
const BY = 'cksoak-writer';

function post (path, body) {
  const u = new URL(path, TARGET);
  const data = Buffer.from(JSON.stringify(body));
  return new Promise((resolve, reject) => {
    const r = http.request({ hostname: u.hostname, port: u.port, path: u.pathname, method: 'POST',
      headers: { 'content-type': 'application/json', 'content-length': data.length, 'api-secret': HASH },
      timeout: 20000 }, (res) => {
      let buf = '';
      res.on('data', (c) => { buf += c; });
      res.on('end', () => res.statusCode === 200 ? resolve(buf) : reject(new Error('HTTP ' + res.statusCode)));
    });
    r.on('timeout', () => r.destroy(new Error('timeout')));
    r.on('error', reject);
    r.end(data);
  });
}

function note (msg) { console.log(new Date().toISOString() + ' ' + msg); }

function ledger (kind, coll, rec, storedAt, extra) {
  const key = coll === 'entries' ? rec.date : rec.created_at;
  fs.appendFileSync(LEDGER, JSON.stringify({ kind, coll, soakId: rec.soakId, at: key,
    type: rec.type || rec.eventType || rec.device, storedAt: storedAt.toISOString(), ...(extra || {}) }) + '\n');
}

// Deterministic synthetic glucose: two slow waves plus bounded noise.
function sgvAt (ms) {
  const h = ms / 3600000;
  const noise = (parseInt(crypto.createHash('md5').update(String(ms)).digest('hex').slice(0, 4), 16) % 11) - 5;
  return Math.round(140 + 55 * Math.sin(2 * Math.PI * h / 7) + 20 * Math.sin(2 * Math.PI * h / 2.3) + noise);
}
function direction (d) {
  if (d > 15) return 'DoubleUp'; if (d > 10) return 'SingleUp'; if (d > 5) return 'FortyFiveUp';
  if (d < -15) return 'DoubleDown'; if (d < -10) return 'SingleDown'; if (d < -5) return 'FortyFiveDown';
  return 'Flat';
}
const id = (p, ms) => 'cksoak-' + p + '-' + ms;

function sgv (ms) {
  const v = sgvAt(ms);
  return { soakId: id('sgv', ms), type: 'sgv', sgv: v, direction: direction(v - sgvAt(ms - TICK)),
    device: DEVICE, date: ms, dateString: new Date(ms).toISOString(), noise: 1 };
}
function mbg (ms) { return { soakId: id('mbg', ms), type: 'mbg', mbg: sgvAt(ms) + 4, device: DEVICE, date: ms, dateString: new Date(ms).toISOString() }; }
function status (ms, n) {
  return { soakId: id('ds', ms), device: LOOP, created_at: new Date(ms).toISOString(),
    uploader: { battery: 100 - (n % 60) },
    pump: { reservoir: 150 - (n % 100) * 1.2, battery: { percent: 80 }, status: { status: 'normal', bolusing: false, suspended: false } },
    openaps: { iob: { iob: Number(((n % 17) / 5).toFixed(2)), timestamp: new Date(ms).toISOString() },
      suggested: { bg: sgvAt(ms), eventualBG: sgvAt(ms) - 10, reason: 'synthetic', timestamp: new Date(ms).toISOString() } } };
}
function treatmentsAt (ms, n) {
  const at = new Date(ms + 1000).toISOString(); // +1 s keeps treatments off the sgv second
  const out = [];
  if (n % 9 === 0) out.push({ soakId: id('carb', ms), eventType: 'Carb Correction', carbs: 10 + (n % 5) * 5, enteredBy: BY, created_at: at });
  if (n % 9 === 4) out.push({ soakId: id('bolus', ms), eventType: 'Correction Bolus', insulin: Number((0.5 + (n % 4) * 0.25).toFixed(2)), enteredBy: BY, created_at: at });
  if (n % 6 === 2) out.push({ soakId: id('temp', ms), eventType: 'Temp Basal', rate: Number((0.4 + (n % 7) * 0.1).toFixed(2)), absolute: Number((0.4 + (n % 7) * 0.1).toFixed(2)), duration: 30, enteredBy: BY, created_at: new Date(ms + 2000).toISOString() });
  return out;
}
function profile (ms) {
  const sched = (v) => [{ time: '00:00', value: v, timeAsSeconds: 0 }];
  return { soakId: 'cksoak-profile-1', defaultProfile: 'Synthetic', startDate: new Date(ms).toISOString(), mills: ms, units: 'mg/dl',
    store: { Synthetic: { dia: 5, carbratio: sched(10), sens: sched(45), basal: [{ time: '00:00', value: 0.8, timeAsSeconds: 0 }, { time: '06:00', value: 1.0, timeAsSeconds: 21600 }],
      target_low: sched(100), target_high: sched(120), units: 'mg/dl', timezone: 'UTC', delay: 20, startDate: '1970-01-01T00:00:00.000Z' } } };
}

const queue = [];
async function send (kind, coll, path, rows) {
  if (!rows.length) return;
  try {
    await post(path, rows);
    const t = new Date();
    rows.forEach((r) => ledger(kind, coll, r, t));
  } catch (err) {
    note('write failed ' + coll + ' x' + rows.length + ' (' + err.message + '), queued');
    queue.push({ kind, coll, path, rows });
  }
}
let draining = false;
async function drain () {
  if (draining) return;
  draining = true;
  try { await drainOnce(); } finally { draining = false; }
}
async function drainOnce () {
  while (queue.length) {
    const job = queue[0];
    try { await post(job.path, job.rows); } catch (err) { return; }
    queue.shift();
    const t = new Date();
    job.rows.forEach((r) => ledger(job.kind, job.coll, r, t, { late: true }));
    note('queued write delivered ' + job.coll + ' x' + job.rows.length);
  }
}

const tickOf = (ms) => Math.floor(ms / TICK);

async function seed () {
  if (fs.existsSync(LEDGER) && fs.readFileSync(LEDGER, 'utf8').includes('"kind":"seed"')) { note('ledger already seeded'); return; }
  const now = Date.now();
  const first = tickOf(now - SEED_HOURS * 3600000), last = tickOf(now) - 1;
  const e = [], t = [], d = [];
  for (let n = first; n <= last; n++) {
    const ms = n * TICK + 7000; // readings land 7 s after the tick boundary
    e.push(sgv(ms));
    if (n % 72 === 36) e.push(mbg(ms + 3000));
    if (n % 3 === 0) d.push(status(ms + 30000, n));
    t.push(...treatmentsAt(ms, n));
  }
  await send('seed', 'profile', '/api/v1/profile', [profile(now - SEED_HOURS * 3600000)]);
  for (let i = 0; i < e.length; i += 500) await send('seed', 'entries', '/api/v1/entries', e.slice(i, i + 500));
  for (let i = 0; i < t.length; i += 200) await send('seed', 'treatments', '/api/v1/treatments', t.slice(i, i + 200));
  for (let i = 0; i < d.length; i += 200) await send('seed', 'devicestatus', '/api/v1/devicestatus', d.slice(i, i + 200));
  if (queue.length) { note('seed incomplete; refusing to continue'); process.exit(3); }
  note('seeded ' + e.length + ' entries, ' + t.length + ' treatments, ' + d.length + ' devicestatus, 1 profile');
}

async function live () {
  let n = tickOf(Date.now());
  for (;;) {
    n += 1;
    const ms = n * TICK + 7000;
    const wait = ms - Date.now();
    if (wait > 0) await new Promise((r) => setTimeout(r, wait));
    await drain();
    const e = [sgv(ms)];
    if (n % 72 === 36) e.push(mbg(ms + 3000));
    await send('live', 'entries', '/api/v1/entries', e);
    await send('live', 'treatments', '/api/v1/treatments', treatmentsAt(ms, n));
    if (n % 3 === 0) {
      await new Promise((r) => setTimeout(r, 30000));
      await send('live', 'devicestatus', '/api/v1/devicestatus', [status(ms + 30000, n)]);
    }
  }
}

setInterval(() => { drain().catch(() => {}); }, 30000).unref();
seed().then(live).catch((err) => { note('writer stopped: ' + err.message); process.exit(1); });
