'use strict';
// Shared helpers for the cache-value lab. Synthetic data only.
//
// CRM_DIR names the cgm-remote-monitor tree under test; the MongoDB driver is
// loaded from that tree so the lab uses the same driver version as the server.

const path = require('path');
const crypto = require('crypto');

const CRM_DIR = process.env.CRM_DIR;
if (!CRM_DIR) throw new Error('CRM_DIR is required');
const { MongoClient } = require(path.join(CRM_DIR, 'node_modules/mongodb'));

const MIN = 60 * 1000;
const HOUR = 60 * MIN;

function newSecret () {
  return crypto.randomBytes(24).toString('hex');
}
function secretHash (secret) {
  return crypto.createHash('sha1').update(secret).digest('hex');
}

// A synthetic sensor trace: a slow sine, no real person's data.
function sgvAt (t) {
  return Math.round(120 + 40 * Math.sin(t / (3 * HOUR)));
}

function entry (t) {
  return { type: 'sgv', sgv: sgvAt(t), direction: 'Flat', noise: 1, device: 'cv-lab-synthetic-cgm'
    , date: t, dateString: new Date(t).toISOString() };
}

// Shaped like an OpenAPS/AAPS-style uploader devicestatus (prediction arrays
// make up most of the size of a real one). All values synthetic.
function devicestatus (t) {
  const base = sgvAt(t);
  const pred = (k) => Array.from({ length: 48 }, (_, i) => base + Math.round(k * i));
  return {
    device: 'cv-lab-synthetic-uploader'
    , created_at: new Date(t).toISOString()
    , uploaderBattery: 80
    , openaps: {
      iob: { iob: 1.1, basaliob: 0.4, activity: 0.01, time: new Date(t).toISOString() }
      , suggested: { bg: base, temp: 'absolute', rate: 0.8, duration: 30, reason: 'cv-lab synthetic'
        , predBGs: { IOB: pred(-0.5), ZT: pred(-1), COB: pred(0.3), UAM: pred(0.1) }
        , timestamp: new Date(t).toISOString() }
      , enacted: { rate: 0.8, duration: 30, received: true, timestamp: new Date(t).toISOString() }
    }
    , pump: { clock: new Date(t).toISOString(), reservoir: 100, battery: { percent: 70 }, status: { status: 'normal' } }
  };
}

function treatment (t, i) {
  const kinds = [
    { eventType: 'Correction Bolus', insulin: 0.5 }
    , { eventType: 'Carb Correction', carbs: 15 }
    , { eventType: 'Temp Basal', rate: 0.8, absolute: 0.8, duration: 30 }
  ];
  return Object.assign({ created_at: new Date(t).toISOString(), enteredBy: 'cv-lab' }, kinds[i % kinds.length]);
}

// History a site would hold: entries every 5 min for `entryHours`, devicestatus
// every 5 min for `dsHours`, a treatment every `txEveryMin` minutes for `txHours`.
function history (now, opts) {
  opts = Object.assign({ entryHours: 50, dsHours: 26, txHours: 62, txEveryMin: 120 }, opts);
  const step = 5 * MIN;
  const entries = []; const ds = []; const tx = [];
  for (let t = now - opts.entryHours * HOUR; t < now - MIN; t += step) entries.push(entry(t));
  for (let t = now - opts.dsHours * HOUR; t < now - MIN; t += step) ds.push(devicestatus(t));
  let i = 0;
  for (let t = now - opts.txHours * HOUR; t < now - MIN; t += opts.txEveryMin * MIN) tx.push(treatment(t, i++));
  return { entries, devicestatus: ds, treatments: tx };
}

async function seed (uri, now, opts) {
  const c = await MongoClient.connect(uri, { appName: 'cv-probe' });
  const db = c.db();
  await db.dropDatabase();
  const h = history(now, opts);
  for (const col of ['entries', 'devicestatus', 'treatments']) {
    if (h[col].length) await db.collection(col).insertMany(h[col]);
  }
  await c.close();
  return { entries: h.entries.length, devicestatus: h.devicestatus.length, treatments: h.treatments.length };
}

// serverStatus counters this lab reads per interval.
async function serverCounters (db) {
  const s = await db.admin().command({ serverStatus: 1 });
  return {
    t: Date.now()
    , opcounters: s.opcounters
    , docReturned: s.metrics && s.metrics.document && s.metrics.document.returned
    , bytesOut: s.network && s.network.bytesOut
    , bytesIn: s.network && s.network.bytesIn
    , numRequests: s.network && s.network.numRequests
    , connections: s.connections && s.connections.current
    , version: s.version
  };
}

function pct (arr, p) {
  if (!arr.length) return null;
  const s = arr.slice().sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(p * s.length))];
}

module.exports = { CRM_DIR, MongoClient, MIN, HOUR, newSecret, secretHash, entry, devicestatus, treatment, history, seed, serverCounters, pct };
