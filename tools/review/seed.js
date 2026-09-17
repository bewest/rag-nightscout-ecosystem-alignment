#!/usr/bin/env node
'use strict';
/*
 * seed.js — POST a complete, self-consistent Nightscout instance through the
 * REAL HTTP API, and emit a manifest of exactly what was seeded.
 *
 * WHY THE MANIFEST IS THE POINT. A probe that checks `/count/entries/where`
 * against the same build's list endpoint is comparing a build to itself and
 * catches only half the coercion/reads pair. Probes must assert against a
 * KNOWN SEEDED EXPECTATION. This file is where that expectation is created,
 * so this file is where it is written down.
 *
 * MEASURED CONSTRAINTS THIS OBEYS (plan §4):
 *
 *  - PROFILE FIRST. With entries but no profile the client navigates itself to
 *    /profile and renders no chart, so every branch looks equally broken.
 *  - DISTINCT TIMESTAMPS PER DOCUMENT. The entries upsert key is
 *    (sysTime, type) and nothing else; treatments (created_at, eventType).
 *    A generator that stamps `new Date()` in a tight loop collapses 576 sgv
 *    into 2 documents, with HTTP 200 on every request. Every timestamp here is
 *    computed from an index, never from the clock.
 *  - ONE PATIENT PER INSTANCE. Near-miss timestamps from a second source
 *    survive the upsert and the page still looks alive while /pebble reports
 *    a nonsense delta.
 *  - WHOLE-DAY CLOCK SHIFT. Never anchor the newest reading onto `now`;
 *    that rotates time-of-day and desynchronises the trace from the profile's
 *    own time-of-day schedules.
 *  - DE-IDENTIFIED BY CONSTRUCTION. Every device/enteredBy value is a literal
 *    defined in this file. Nothing is read from externals/ns-data.
 *  - BULK LIMIT. 10,000 entries per POST; 10,001 returns HTTP 400.
 *
 * Usage:
 *   node seed.js --url http://127.0.0.1:14233 --secret <raw> [options]
 *     --hours N        hours of entries       (default 48)
 *     --out FILE       write manifest         (default <root>/run/<db>.manifest.json)
 *     --no-adversarial  skip the §5 fixtures
 */

const http = require('http');
const https = require('https');
const crypto = require('crypto');
const fs = require('fs');

// ---------------------------------------------------------------- literals
// Every identifier-shaped value the harness writes is defined HERE and nowhere
// else, so "did anything from ns-data reach the instance" is answerable by
// reading one screen.
const DEVICE = 'synthetic://review/harness';
const ENTERED_BY = 'nsreview';
const BULK_MAX = 10000;

// ---------------------------------------------------------------- args
const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const flag = k => argv.includes(k);

const URL_BASE = arg('--url');
const SECRET = arg('--secret');
const HOURS = parseInt(arg('--hours', '48'), 10);
// Cadence matters for the cache probes: lib/server/cache.js retains 48h, so
// more HOURS does not grow the cache — only a denser sample does. 30s over 48h
// gives ~5760 entries against 576 at the 5-minute default.
const CADENCE_SEC = parseInt(arg('--cadence-sec', '300'), 10);
const ADVERSARIAL = !flag('--no-adversarial');
const OUT = arg('--out');
const MONGO_DB = arg('--mongo-db');            // authoritative count source
const MONGO_CONTAINER = arg('--mongo-container', 'nsreview-mongo');
if (!URL_BASE || !SECRET) { console.error('need --url and --secret'); process.exit(2); }

const SHA1 = crypto.createHash('sha1').update(SECRET).digest('hex');
const MIN = 60000, HOUR = 60 * MIN, DAY = 24 * HOUR;

// ---------------------------------------------------------------- http
function req(method, path, body) {
  const u = new URL(path, URL_BASE);
  const lib = u.protocol === 'https:' ? https : http;
  const data = body === undefined ? null : Buffer.from(JSON.stringify(body));
  return new Promise((res, rej) => {
    const r = lib.request({
      hostname: u.hostname, port: u.port, path: u.pathname + u.search, method,
      headers: Object.assign({ 'api-secret': SHA1 },
        data ? { 'content-type': 'application/json', 'content-length': data.length } : {}),
    }, x => {
      let b = ''; x.on('data', c => b += c);
      x.on('end', () => res({ code: x.statusCode, body: b }));
    });
    r.on('error', rej);
    if (data) r.write(data);
    r.end();
  });
}
const post = (p, b) => req('POST', p, b);
const get = p => req('GET', p);

async function postChunked(path, docs, label) {
  let ok = 0;
  for (let i = 0; i < docs.length; i += BULK_MAX) {
    const chunk = docs.slice(i, i + BULK_MAX);
    const r = await post(path, chunk);
    if (r.code >= 300) throw new Error(`${label}: HTTP ${r.code} ${r.body.slice(0, 200)}`);
    ok += chunk.length;
  }
  return ok;
}

// ---------------------------------------------------------------- clock
// Whole-DAY shift keeps time-of-day aligned with the profile's schedules.
// The series ends one cadence-step before now so the newest reading is fresh
// but not in the future (a future-dated reading silences the stale alarm —
// BF-41, which is NOT in this cycle and must not be simulated by accident).
const NOW = Date.now();
const CADENCE = CADENCE_SEC * 1000;
const SERIES_END = Math.floor(NOW / CADENCE) * CADENCE - CADENCE;
const SERIES_START = SERIES_END - HOURS * HOUR;

// deterministic PRNG so two runs seed byte-identical values
function mulberry(seed) {
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0;
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

// A day-shaped trace: overnight flat-ish, three meal excursions, dawn rise.
function glucoseAt(ms, rnd) {
  const d = new Date(ms);
  const h = d.getUTCHours() + d.getUTCMinutes() / 60;
  let bg = 110;
  bg += 18 * Math.sin((h - 3) / 24 * 2 * Math.PI);          // circadian
  for (const [mh, amp] of [[7.5, 55], [12.5, 70], [19, 65]]) { // meals
    const dt = h - mh;
    if (dt > 0 && dt < 3) bg += amp * Math.exp(-Math.pow(dt - 0.75, 2) / 0.45);
  }
  if (h > 4 && h < 8) bg += 12 * (h - 4) / 4;                // dawn
  bg += (rnd() - 0.5) * 9;
  return Math.max(48, Math.min(330, Math.round(bg)));
}

function directionFor(prev, cur) {
  if (prev == null) return 'Flat';
  const d = cur - prev;
  if (d >= 15) return 'DoubleUp';
  if (d >= 8) return 'SingleUp';
  if (d >= 3) return 'FortyFiveUp';
  if (d <= -15) return 'DoubleDown';
  if (d <= -8) return 'SingleDown';
  if (d <= -3) return 'FortyFiveDown';
  return 'Flat';
}

// ---------------------------------------------------------------- profile
function buildProfile() {
  const sched = v => [{ time: '00:00', timeAsSeconds: 0, value: String(v) }];
  const basal = [
    { time: '00:00', timeAsSeconds: 0, value: '0.75' },
    { time: '04:00', timeAsSeconds: 14400, value: '0.95' },
    { time: '10:00', timeAsSeconds: 36000, value: '0.80' },
    { time: '18:00', timeAsSeconds: 64800, value: '0.85' },
  ];
  return [{
    defaultProfile: 'Default',
    mills: String(SERIES_START - DAY),
    startDate: new Date(SERIES_START - DAY).toISOString(),
    units: 'mg/dl',
    enteredBy: ENTERED_BY,
    store: {
      Default: {
        dia: '5', carbs_hr: '20', delay: '20', timezone: 'UTC',
        units: 'mg/dl',
        basal,
        sens: sched(50),          // ISF
        carbratio: sched(10),     // CR
        target_low: sched(100),
        target_high: sched(120),
      },
    },
  }];
}

// ---------------------------------------------------------------- main
(async () => {
  const manifest = { seededAt: new Date(NOW).toISOString(), url: URL_BASE, hours: HOURS,
                     device: DEVICE, enteredBy: ENTERED_BY, expect: {}, counts: {} };

  // ---- 1. PROFILE FIRST
  {
    const r = await post('/api/v1/profile', buildProfile());
    if (r.code >= 300) throw new Error(`profile: HTTP ${r.code} ${r.body.slice(0, 300)}`);
    manifest.counts.profile = 1;
  }

  // ---- 2. ENTRIES — distinct timestamp per document, varying sgv
  const rnd = mulberry(20260917);
  const entries = [];
  let prev = null;
  for (let t = SERIES_START; t <= SERIES_END; t += CADENCE) {
    const sgv = glucoseAt(t, rnd);
    entries.push({
      type: 'sgv', sgv, date: t, dateString: new Date(t).toISOString(),
      direction: directionFor(prev, sgv), device: DEVICE,
    });
    prev = sgv;
  }
  manifest.cadenceSec = CADENCE_SEC;
  manifest.counts.entries = await postChunked('/api/v1/entries', entries, 'entries');

  // ---- 3. TREATMENTS — 60h, each on its own created_at
  const treatments = [];
  const tStart = SERIES_END - 60 * HOUR;
  for (let t = tStart; t <= SERIES_END; t += HOUR) {
    const d = new Date(t); const h = d.getUTCHours();
    if (h === 7 || h === 12 || h === 19) {
      treatments.push({ eventType: 'Meal Bolus', created_at: new Date(t).toISOString(),
        carbs: h === 7 ? 45 : h === 12 ? 60 : 55, insulin: h === 7 ? 4.5 : h === 12 ? 6 : 5.5,
        enteredBy: ENTERED_BY });
    } else if (h % 3 === 0) {
      treatments.push({ eventType: 'Temp Basal', created_at: new Date(t).toISOString(),
        absolute: 0.6, duration: 30, enteredBy: ENTERED_BY });
    }
  }
  // exactly one of each age-pill event, positioned to be OVERDUE — one document
  // each, not a history (the 62-day window needs a single document).
  treatments.push({ eventType: 'Site Change', created_at: new Date(SERIES_END - 5 * DAY).toISOString(), enteredBy: ENTERED_BY });
  treatments.push({ eventType: 'Sensor Start', created_at: new Date(SERIES_END - 12 * DAY).toISOString(), enteredBy: ENTERED_BY });
  // BF-28: insulinage's URGENT branch. One insulin change aged well past it.
  treatments.push({ eventType: 'Insulin Change', created_at: new Date(SERIES_END - 9 * DAY).toISOString(), enteredBy: ENTERED_BY });
  manifest.counts.treatments = await postChunked('/api/v1/treatments', treatments, 'treatments');
  manifest.expect.insulinChangeAgeDays = 9;
  manifest.expect.siteChangeAgeDays = 5;

  // ---- 4. DEVICESTATUS — nested, numeric, 24h
  const ds = [];
  for (let t = SERIES_END - 24 * HOUR; t <= SERIES_END; t += CADENCE * 2) {
    ds.push({
      created_at: new Date(t).toISOString(), device: DEVICE,
      openaps: {
        iob: { iob: Math.round(rnd() * 300) / 100, timestamp: new Date(t).toISOString() },
        suggested: { COB: Math.round(rnd() * 40), timestamp: new Date(t).toISOString(), bg: glucoseAt(t, rnd) },
      },
      pump: { battery: { percent: 70 + Math.floor(rnd() * 30) }, reservoir: Math.round(rnd() * 200) / 2,
              clock: new Date(t).toISOString() },
      uploader: { battery: 50 + Math.floor(rnd() * 50) },
    });
  }
  manifest.counts.devicestatus = await postChunked('/api/v1/devicestatus', ds, 'devicestatus');

  // ---- 5. ADVERSARIAL FIXTURES (plan §5)
  if (ADVERSARIAL) {
    // --- coercion+reads: a KNOWN present/absent split on one field.
    // `mbg` is present on exactly N docs and absent on every sgv doc, so
    // $exists true/false must PARTITION the collection. The probe asserts
    // against these numbers, never against the same build's list endpoint.
    const mbgCount = 5;
    const mbg = [];
    for (let i = 0; i < mbgCount; i++) {
      const t = SERIES_START - (i + 1) * CADENCE;   // outside the sgv series
      mbg.push({ type: 'mbg', mbg: 100 + i, date: t, dateString: new Date(t).toISOString(), device: DEVICE });
    }
    await postChunked('/api/v1/entries', mbg, 'entries-mbg');
    manifest.counts.entriesMbg = mbgCount;
    manifest.expect.entriesTotal = manifest.counts.entries + mbgCount;
    manifest.expect.mbgExistsTrue = mbgCount;
    manifest.expect.mbgExistsFalse = manifest.counts.entries;   // every sgv doc
    // BF-40 note: `find[mbg][$exists]=false` is INVERTED on dev AND on
    // bf/coercion (the operand stays the truthy string 'false'). The probe
    // records it; it is not fixed in this cycle.

    // --- bf/food: the five-way `hidden` typing. Written as JSON, which is the
    // only way to produce a real boolean — the food editor cannot.
    const foods = [
      { type: 'food', name: 'review-oats',    carbs: 27, portion: 1, unit: 'g', category: 'review', subcategory: 'grain', hidden: true },
      { type: 'food', name: 'review-apple',   carbs: 21, portion: 1, unit: 'g', category: 'review', subcategory: 'fruit', hidden: false },
      { type: 'food', name: 'review-bread',   carbs: 15, portion: 1, unit: 'g', category: 'review', subcategory: 'grain' },
      { type: 'food', name: 'review-rice',    carbs: 45, portion: 1, unit: 'g', category: 'review', subcategory: 'grain', hidden: 'false' },
      { type: 'food', name: 'review-pasta',   carbs: 43, portion: 1, unit: 'g', category: 'review', subcategory: 'grain', hidden: 'true' },
    ];
    const qp = [
      { type: 'quickpick', name: 'review-qp-visible', carbs: 30, hidden: false, hideafteruse: false, position: 0, foods: [foods[1]] },
      { type: 'quickpick', name: 'review-qp-hidden',  carbs: 20, hidden: true,  hideafteruse: false, position: 1, foods: [foods[0]] },
      { type: 'quickpick', name: 'review-qp-strfalse', carbs: 40, hidden: 'false', hideafteruse: false, position: 2, foods: [foods[3]] },
    ];
    let foodOk = 0;
    for (const f of foods.concat(qp)) {
      const r = await post('/api/v1/food', f);
      if (r.code < 300) foodOk++;
    }
    manifest.counts.food = foodOk;
    // Only ONE quickpick has a real boolean false. A correct build offers 1.
    manifest.expect.quickpicksVisible = 1;
    manifest.expect.quickpicksTotal = qp.length;
    manifest.expect.foodTotal = foods.length;
  }

  // ---- 6. verify what was stored.
  //
  // AUTHORITATIVE COUNTS COME FROM THE DATABASE, NOT THE API. Measured
  // 2026-09-17: 29 treatments were posted and all 29 are in mongo, but
  // GET /api/v1/treatments.json?count=99999 returns 26 — the endpoint applies
  // a default time window, so the three deliberately-aged age-pill events are
  // invisible to it. Verifying the seed through that endpoint would have
  // reported a phantom 3-document data loss.
  //
  // It matters beyond neatness: /api/v1/treatments and /api/v1/entries are
  // precisely the read paths bf/reads and bf/coercion rewrite. A seed check
  // that runs through them cannot distinguish "the seed is wrong" from "the
  // branch changed the read", which is the one distinction the whole cycle
  // rests on.
  const st = await get('/api/v1/status.json');
  manifest.serverVersion = JSON.parse(st.body).version;

  if (MONGO_DB) {
    const { execFileSync } = require('child_process');
    const js = `["entries","treatments","devicestatus","food","profile"]`
      + `.forEach(c=>print(c+" "+db.getCollection(c).countDocuments()))`;
    try {
      const out = execFileSync('docker',
        ['exec', MONGO_CONTAINER, 'mongosh', '--quiet', MONGO_DB, '--eval', js],
        { encoding: 'utf8' });
      manifest.stored = {};
      for (const line of out.trim().split('\n')) {
        const [c, n] = line.trim().split(/\s+/);
        if (c) manifest.stored[c] = parseInt(n, 10);
      }
    } catch (e) { manifest.stored = { error: String(e.message).slice(0, 200) }; }
  }

  // Kept as a SEPARATE diagnostic, never as truth. The gap between these and
  // `stored` is the read window, and that gap is itself worth seeing.
  manifest.asReadByApi = {};
  for (const [k, path] of [['entries', '/api/v1/entries.json?count=99999'],
                           ['treatments', '/api/v1/treatments.json?count=99999'],
                           ['food', '/api/v1/food.json']]) {
    const r = await get(path);
    try { manifest.asReadByApi[k] = JSON.parse(r.body).length; }
    catch { manifest.asReadByApi[k] = `HTTP ${r.code}`; }
  }

  const out = OUT || `/tmp/nsreview-seed-${Date.now()}.json`;
  fs.writeFileSync(out, JSON.stringify(manifest, null, 2));
  console.log(JSON.stringify(manifest, null, 2));
  console.error(`\nmanifest -> ${out}`);

  // The collapse check — against the DATABASE. If stored << posted, the
  // (sysTime,type) upsert key ate documents and every later probe is invalid.
  if (manifest.stored && typeof manifest.stored.entries === 'number') {
    const posted = manifest.expect.entriesTotal || manifest.counts.entries;
    if (manifest.stored.entries < posted) {
      console.error(`\n*** SEED COLLAPSE: posted ${posted} entries, stored ${manifest.stored.entries}`);
      process.exit(1);
    }
    if (manifest.stored.treatments < manifest.counts.treatments) {
      console.error(`\n*** SEED COLLAPSE: posted ${manifest.counts.treatments} treatments, stored ${manifest.stored.treatments}`);
      process.exit(1);
    }
  } else {
    console.error('\n*** WARNING: no --mongo-db given; collapse check DID NOT RUN.');
  }
})().catch(e => { console.error('SEED FAILED:', e.message); process.exit(1); });
