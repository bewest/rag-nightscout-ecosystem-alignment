#!/usr/bin/env node
'use strict';
/*
 * bf103-split-drag-browser.js — BF-103: after a treatment's time is changed
 * from the web UI, do IOB and COB follow the new time?
 *
 * One instance per run (a dev build or a fix build). A real Chrome, driven by
 * playwright-core, changes a treatment's time through the page itself:
 *   - "Move carbs" / "Move insulin": drag a carbs+insulin treatment into the
 *     top / bottom 50 px of the chart (the split);
 *   - "Move": drag a whole treatment, including one already damaged by an
 *     earlier split (stale `mills`, ISO-string `date`, `mgdl`, `scaled`);
 *   - the report editor (Reports > Treatments > edit > Save, which PUTs the
 *     record to /api/v1/treatments);
 *   - a plain API client doing GET, change created_at, PUT /api/v1/treatments.
 *
 * WHAT DECIDES THE VERDICT. The coordinator's control, run per phase:
 *   1. restart the server (no cache can mask the stored document) and read
 *      GET /api/v2/properties/iob,cob             -> "stored"
 *   2. $unset mills, date, mgdl, scaled and endmills on this phase's records,
 *      restart, read again                          -> "oracle"
 * The oracle is the same documents counted at their created_at. FOLLOWS means
 * stored == oracle (within 0.05 U / 0.5 g); STALE means they differ. Every
 * phase's records are cleaned by step 2, so later phases start clean.
 * The stored documents are also read from MongoDB directly and reported.
 *
 * Usage:
 *   node bf103-split-drag-browser.js --url http://127.0.0.1:15611 --secret <raw> \
 *     --mongo mongodb://127.0.0.1:27103 --db bf103_dev --label dev \
 *     --helper tools/review/probes/w2-instance.sh --name split-dev \
 *     --wt <worktree> --port 15611 [--only phaseKey,...] --out dev.json
 * Env for the helper: W2_STATE, W2_MONGO_CONTAINER, W2_MONGO_PORT, W2_NODE.
 * Exit: 0 every phase FOLLOWS, 1 some phase STALE or failed, 2 could not run.
 * Synthetic data only; every identifier below is a literal.
 */

const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { execFileSync } = require('child_process');
const { report } = require(path.resolve(__dirname, '..', '..', 'queue', 'gates', '_gate.js'));

const ENTERED_BY = 'nsreview-bf103';
const MIN = 60000;

function resolveDep(name) {
  for (const c of [process.env.NSREVIEW_DEPS && path.join(process.env.NSREVIEW_DEPS, name), name].filter(Boolean)) {
    try { require.resolve(c); return require(c); } catch { /* next */ }
  }
  console.error(`${name} not found (set NSREVIEW_DEPS)`); process.exit(2);
}

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const URL_BASE = arg('--url'), SECRET = arg('--secret'), MONGO = arg('--mongo'), DB = arg('--db');
const LABEL = arg('--label', 'instance'), OUT = arg('--out'), HELPER = arg('--helper');
const NAME = arg('--name'), WT = arg('--wt'), PORT = arg('--port'), ROLES = arg('--roles', 'denied');
const ONLY = arg('--only') ? arg('--only').split(',') : null;
if (!URL_BASE || !SECRET || !MONGO || !DB || !HELPER || !NAME || !WT || !PORT) {
  console.error('need --url --secret --mongo --db --helper --name --wt --port'); process.exit(2);
}
const SHA1 = crypto.createHash('sha1').update(SECRET).digest('hex');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const iso = ms => new Date(ms).toISOString();

async function api(method, p, body, headers) {
  const h = Object.assign({ 'api-secret': SHA1, 'content-type': 'application/json' }, headers || {});
  Object.keys(h).forEach(k => { if (h[k] === null) delete h[k]; });
  let r;
  for (let attempt = 0; ; attempt++) {
    try {
      r = await fetch(URL_BASE + p, { method, headers: h, body: body === undefined ? undefined : JSON.stringify(body) });
      break;
    } catch (e) {
      // a pooled keep-alive socket to a server this probe just restarted
      if (attempt >= 3 || !(e.cause && e.cause.code === 'UND_ERR_SOCKET')) throw e;
      await new Promise(res => setTimeout(res, 500));
    }
  }
  const t = await r.text();
  let j = null; try { j = JSON.parse(t); } catch { /* not json */ }
  return { code: r.status, body: t, json: j };
}

function restart() {
  execFileSync(HELPER, ['stop', NAME], { stdio: 'pipe' });
  for (let i = 0; i < 40; i++) {
    const busy = execFileSync('bash', ['-c', `ss -ltn "( sport = :${PORT} )" | grep -c LISTEN || true`]).toString().trim();
    if (busy === '0') break;
    execFileSync('sleep', ['0.25']);
  }
  execFileSync(HELPER, ['boot', NAME, WT, PORT, DB, ROLES], { stdio: 'pipe' });
}

async function props() {
  // right after a boot the first read can come back before the plugins have
  // data (iob/cob missing); retry a few times before recording a null
  let r, j;
  for (let i = 0; i < 10; i++) {
    r = await api('GET', '/api/v2/properties/iob,cob');
    j = r.json || {};
    if (j.iob && j.cob && j.iob.iob !== undefined && j.cob.cob !== undefined) break;
    await sleep(1000);
  }
  return { code: r.code, iob: j.iob ? Number(j.iob.iob) : null, cob: j.cob ? Number(j.cob.cob) : null,
           iobSource: j.iob && j.iob.source, cobSource: j.cob && j.cob.source };
}

const DERIVED = { mills: 1, date: 1, mgdl: 1, scaled: 1, endmills: 1 };
function shape(doc) {
  if (!doc) return null;
  const o = { _id: String(doc._id), created_at: doc.created_at };
  for (const k of ['carbs', 'insulin', 'mills', 'date', 'mgdl', 'scaled', 'endmills', 'identifier', 'eventType']) {
    if (doc[k] !== undefined) o[k] = doc[k] instanceof Date ? 'Date(' + doc[k].toISOString() + ')' : doc[k];
  }
  o.dateType = doc.date === undefined ? 'absent' : (doc.date instanceof Date ? 'Date' : typeof doc.date);
  const ca = Date.parse(doc.created_at);
  o.millsVsCreatedMin = typeof doc.mills === 'number' ? +((doc.mills - ca) / MIN).toFixed(2) : null;
  const dm = doc.date === undefined ? NaN : (typeof doc.date === 'number' ? doc.date
    : doc.date instanceof Date ? doc.date.getTime() : (/^\d+$/.test(doc.date) ? Number(doc.date) : Date.parse(doc.date)));
  o.dateVsCreatedMin = Number.isFinite(dm) ? +((dm - ca) / MIN).toFixed(2) : null;
  return o;
}

// ---------------------------------------------------------------- seed
function profileDoc(startMs) {
  const sched = v => [{ time: '00:00', timeAsSeconds: 0, value: String(v) }];
  return [{ defaultProfile: 'Default', mills: String(startMs), startDate: iso(startMs), units: 'mg/dl', enteredBy: ENTERED_BY,
    store: { Default: { dia: '5', carbs_hr: '20', delay: '20', timezone: 'UTC', units: 'mg/dl',
      basal: [{ time: '00:00', timeAsSeconds: 0, value: '0.8' }], sens: sched(50), carbratio: sched(10),
      target_low: sched(100), target_high: sched(120) } } }];
}

async function seedBase(db, now) {
  const f = [];
  const p = await api('POST', '/api/v1/profile', profileDoc(now - 2 * 24 * 60 * MIN));
  f.push({ ok: p.code < 300, text: `profile POST HTTP ${p.code}` });
  const entries = [];
  for (let i = 0; i < 72; i++) {
    const t = now - (72 - i) * 5 * MIN;
    entries.push({ type: 'sgv', sgv: 110 + (i % 6) * 2, direction: 'Flat', date: t, dateString: iso(t), device: 'synthetic://review/bf103' });
  }
  const e = await api('POST', '/api/v1/entries', entries);
  f.push({ ok: e.code < 300, text: `entries POST HTTP ${e.code}` });
  return f;
}

async function mintToken() {
  const role = 'bf103-treatment-editor';
  await api('POST', '/api/v2/authorization/roles', { name: role, permissions: ['*:*:read', 'api:treatments:*'] });
  await api('POST', '/api/v2/authorization/subjects', { name: 'bf103-editor', roles: [role] });
  const subs = (await api('GET', '/api/v2/authorization/subjects')).json || [];
  const s = subs.find(x => x.name === 'bf103-editor');
  if (!s || !s.accessToken) throw new Error('could not mint an editor token');
  const jwt = (await api('GET', '/api/v2/authorization/request/' + s.accessToken)).json;
  return { token: s.accessToken, jwt: jwt && jwt.token };
}

// ---------------------------------------------------------------- browser helpers
async function openMain(browser, token, out) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 }, timezoneId: 'UTC' });
  const page = await ctx.newPage();
  page.on('pageerror', e => out.pageErrors.push(String(e.message).slice(0, 200)));
  page.on('console', m => { if (m.type() === 'error') out.consoleErrors.push(m.text().slice(0, 200)); });
  await page.goto(`${URL_BASE}/?token=${token}`, { waitUntil: 'domcontentloaded', timeout: 180000 });
  // a token-authenticated load reloads itself once (RT-D3 §3.3 item 5)
  const ready = () => page.waitForFunction(() => window.Nightscout && window.Nightscout.client &&
    window.Nightscout.client.chart && document.querySelectorAll('#chartContainer g.draggable-treatment').length > 0,
    { timeout: 90000 });
  await ready(); await page.waitForTimeout(5000); await ready();
  await page.click('#editbutton');
  await page.waitForTimeout(500);
  return { ctx, page };
}

// Find the glyph of a treatment: by its x position (t0), or, for a record whose
// stored date is a string (drawn with an invalid transform at the focus origin),
// by the invalid transform.
async function findGlyph(page, t0) {
  return page.evaluate((t0) => {
    const ch = window.Nightscout.client.chart;
    const d = ch.xScale.domain().map(Number), r = ch.xScale.range();
    const gs = [...document.querySelectorAll('#chartContainer g.draggable-treatment')];
    let mine, invalid = false;
    if (t0 === 'invalid') {
      mine = gs.filter(g => /undefined|NaN/.test(g.getAttribute('transform') || ''));
      invalid = true;
    } else {
      const x0 = (t0 - d[0]) * (r[1] - r[0]) / (d[1] - d[0]) + r[0];
      mine = gs.filter(g => {
        const m = /translate\(\s*([-\d.e]+)[ ,]+([-\d.e]+)/.exec(g.getAttribute('transform') || '');
        return m && Math.abs(Number(m[1]) - x0) < 0.75;
      });
    }
    // one <g> per pie arc of the same treatment, all at one transform
    if (new Set(mine.map(g => g.getAttribute('transform'))).size !== 1) return { error: `found ${mine.length} glyphs for ${t0} (have ${gs.length}); transforms ` +
      gs.map(g => g.getAttribute('transform')).join(' | ').slice(0, 300) };
    const ctm = mine[0].getScreenCTM();
    const under = document.elementFromPoint(ctm.e, ctm.f);
    return { cx: ctm.e, cy: ctm.f, invalid, transform: mine[0].getAttribute('transform'),
             arcs: mine.length, hit: !!(under && mine.some(g => g.contains(under))) };
  }, t0);
}

// Screen point for a local (focus) coordinate, plus what the axis says.
async function localToScreen(page, targetMs, zone) {
  return page.evaluate(({ targetMs, zone }) => {
    const ch = window.Nightscout.client.chart;
    const g = document.querySelector('#chartContainer g.draggable-treatment');
    const parent = g.parentNode;
    const m = parent.getScreenCTM();
    const bottom = ch.yScale(ch.yScale.domain()[0]);
    const xL = ch.xScale(new Date(targetMs));
    const yL = zone === 'top' ? 20 : zone === 'bottom' ? bottom - 20 : bottom / 2;
    return { sx: m.a * xL + m.c * yL + m.e, sy: m.b * xL + m.d * yL + m.f, xL, yL, bottom };
  }, { targetMs, zone });
}

async function screenToTime(page, sx, sy) {
  return page.evaluate(({ sx, sy }) => {
    const ch = window.Nightscout.client.chart;
    const parent = document.querySelector('#chartContainer g.draggable-treatment').parentNode;
    const inv = parent.getScreenCTM().inverse();
    const xL = inv.a * sx + inv.c * sy + inv.e;
    const x = Math.min(Math.max(0, xL), Number(ch.charts.attr('width')));
    const d = ch.xScale.domain().map(Number), r = ch.xScale.range();
    return { expected: d[0] + (x - r[0]) * (d[1] - d[0]) / (r[1] - r[0]), msPerPx: (d[1] - d[0]) / (r[1] - r[0]) };
  }, { sx, sy });
}

async function dragTo(page, t0, targetMs, zone) {
  const g = await findGlyph(page, t0);
  if (g.error) return { error: g.error };
  const tgt = await localToScreen(page, targetMs, zone);
  let dialog = null;
  const onDialog = async dl => { dialog = dl.message(); await dl.accept(); };
  page.once('dialog', onDialog);
  await page.mouse.move(g.cx, g.cy);
  await page.mouse.down();
  for (let i = 1; i <= 12; i++) await page.mouse.move(g.cx + (tgt.sx - g.cx) * i / 12, g.cy + (tgt.sy - g.cy) * i / 12);
  const exp = await screenToTime(page, tgt.sx, tgt.sy);
  await page.mouse.up();
  for (let i = 0; i < 50 && dialog === null; i++) await page.waitForTimeout(100);
  page.off('dialog', onDialog);
  return { glyph: g, dialog, expected: exp.expected, tolMs: 2 * exp.msPerPx };
}

async function glyphTransformAfter(page, key) {
  // after the page's own data update: is any draggable glyph drawn with an invalid transform?
  await page.waitForTimeout(3000);
  return page.evaluate(() => [...document.querySelectorAll('#chartContainer g.draggable-treatment')]
    .filter(g => /undefined|NaN/.test(g.getAttribute('transform') || '')).length);
}

// ---------------------------------------------------------------- phases
// Each phase: seed -> restart -> change the time through the UI/API -> read
// mongo -> live props -> control (stored vs oracle).
function phases(now) {
  const T = off => now + off * MIN;
  return [
    { key: 'splitCarbs', via: 'drag Move carbs', what: 'cob',
      seed: { rest: { eventType: 'Meal Bolus', created_at: iso(T(-150)), carbs: 25, insulin: 2.5 } },
      t0: T(-150), target: T(-5), zone: 'top' },
    { key: 'splitInsulin', via: 'drag Move insulin', what: 'iob',
      seed: { rest: { eventType: 'Meal Bolus', created_at: iso(T(-150)), carbs: 20, insulin: 2.5 } },
      t0: T(-150), target: T(-5), zone: 'bottom' },
    { key: 'moveDamagedRc', via: 'drag Move (damaged, 15.0.9-rc shape)', what: 'cob',
      seed: { mongo: { eventType: 'Carb Correction', created_at: iso(T(-40)), carbs: 25,
        mills: T(-150), date: iso(T(-150)), mgdl: 110, scaled: 110 } },
      t0: 'invalid', target: T(-5), zone: 'middle' },
    { key: 'moveDamaged1508', via: 'drag Move (damaged, 15.0.8 shape)', what: 'iob',
      seed: { mongo: { eventType: 'Correction Bolus', created_at: iso(T(-40)), insulin: 2.5,
        mills: T(-150), date: iso(T(-150)), mgdl: 110 } },
      t0: 'invalid', target: T(-5), zone: 'middle' },
    { key: 'splitDamaged', via: 'drag Move carbs (damaged record carrying carbs and insulin)', what: 'iob',
      seed: { mongo: { eventType: 'Meal Bolus', created_at: iso(T(-20)), carbs: 20, insulin: 2.5,
        mills: T(-150), date: iso(T(-150)), mgdl: 110, scaled: 110 } },
      t0: 'invalid', target: T(-5), zone: 'top', checkLeftBehind: true },
    { key: 'moveV3', via: 'drag Move (API v3 record, numeric date)', what: 'cob',
      seed: { v3: { eventType: 'Carb Correction', date: T(-60), carbs: 15, app: 'bf103-probe', device: 'synthetic://review/bf103' } },
      t0: T(-60), target: T(-5), zone: 'middle' },
    { key: 'splitV3', via: 'drag Move carbs (API v3 record)', what: 'cob',
      seed: { v3: { eventType: 'Meal Bolus', date: T(-152), carbs: 25, insulin: 2.5, app: 'bf103-probe', device: 'synthetic://review/bf103' } },
      t0: T(-152), target: T(-5), zone: 'top' },
    { key: 'reportEditDamaged', via: 'report editor Save (PUT /api/v1/treatments)', what: 'cob',
      seed: { mongo: { eventType: 'Carb Correction', created_at: iso(T(-40)), carbs: 25,
        mills: T(-150), date: iso(T(-150)), mgdl: 110, scaled: 110 } },
      report: true, target: T(-5) },
    { key: 'v1PutDamaged', via: 'API client GET, change created_at, PUT /api/v1/treatments', what: 'cob',
      seed: { mongo: { eventType: 'Carb Correction', created_at: iso(T(-40)), carbs: 25,
        mills: T(-150), date: iso(T(-150)), mgdl: 110, scaled: 110 } },
      put: true, target: T(-5) },
  ];
}

async function seedPhase(db, ph, tok) {
  const doc = Object.assign({ enteredBy: ENTERED_BY, notes: 'bf103 ' + ph.key }, ph.seed.rest || ph.seed.mongo || ph.seed.v3);
  if (ph.seed.rest) {
    const r = await api('POST', '/api/v1/treatments', [doc]);
    if (r.code >= 300) throw new Error(`${ph.key}: POST HTTP ${r.code}`);
  } else if (ph.seed.mongo) {
    await db.collection('treatments').insertOne(doc);
  } else {
    const r = await api('POST', '/api/v3/treatments', doc, { authorization: 'Bearer ' + tok.jwt, 'api-secret': null });
    if (r.code >= 300) throw new Error(`${ph.key}: v3 POST HTTP ${r.code} ${r.body.slice(0, 200)}`);
  }
  const stored = await db.collection('treatments').findOne({ notes: 'bf103 ' + ph.key });
  return stored;
}

async function reportEdit(browser, tok, ph, out) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 }, timezoneId: 'UTC' });
  const page = await ctx.newPage();
  page.on('pageerror', e => out.pageErrors.push('report: ' + String(e.message).slice(0, 200)));
  await page.goto(`${URL_BASE}/report?token=${tok.token}`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.waitForSelector('#rp_show', { state: 'visible', timeout: 60000 });
  await page.waitForTimeout(3000);
  await page.click('#treatments');
  await page.click('#rp_show');
  const sel = `img.editTreatment`;
  await page.waitForSelector(sel, { timeout: 60000 });
  const idx = await page.evaluate((note) => [...document.querySelectorAll('img.editTreatment')]
    .findIndex(i => { try { return JSON.parse(i.getAttribute('data')).notes === note; } catch { return false; } }), 'bf103 ' + ph.key);
  if (idx < 0) { await ctx.close(); return { error: 'row not found in report' }; }
  await page.locator(sel).nth(idx).click();
  await page.waitForSelector('#rped_eventTimeValue', { state: 'visible', timeout: 10000 });
  const d = new Date(ph.target);
  await page.fill('#rped_eventDateValue', d.toISOString().slice(0, 10));
  await page.fill('#rped_eventTimeValue', d.toISOString().slice(11, 16));
  let put = null;
  page.on('request', rq => { if (rq.method() === 'PUT' && /\/api\/v1\/treatments/.test(rq.url())) put = rq.postData(); });
  await page.click('.ui-dialog-buttonset button:has-text("Save")');
  for (let i = 0; i < 50 && put === null; i++) await page.waitForTimeout(100);
  await page.waitForTimeout(1500);
  await ctx.close();
  return { putBodyHasDate: put ? /(^|&)date=/.test(put) : null, putBodyHasMills: put ? /(^|&)mills=/.test(put) : null,
           expected: Math.floor(ph.target / MIN) * MIN, tolMs: 1000 };
}

async function v1Put(ph) {
  const g = await api('GET', `/api/v1/treatments.json?find[notes]=${encodeURIComponent('bf103 ' + ph.key)}`);
  const doc = (g.json || [])[0];
  if (!doc) return { error: `GET found nothing (HTTP ${g.code})` };
  doc.created_at = iso(ph.target);
  const r = await api('PUT', '/api/v1/treatments', doc);
  return { putCode: r.code, getHadMills: 'mills' in doc, getHadDate: 'date' in doc, expected: ph.target, tolMs: 1000 };
}

(async () => {
  const { chromium } = resolveDep('playwright-core');
  const { MongoClient } = resolveDep('mongodb');
  const mc = new MongoClient(`${MONGO}/${DB}`); await mc.connect();
  const db = mc.db(DB);
  const findings = [];
  const out = { label: LABEL, url: URL_BASE, when: new Date().toISOString(), phases: {}, pageErrors: [], consoleErrors: [] };
  if (await db.collection('treatments').countDocuments({})) { console.error(`${DB} already holds treatments; reset it`); process.exit(2); }
  const now = Math.floor(Date.now() / MIN) * MIN;
  findings.push(...await seedBase(db, now));
  const tok = await mintToken();
  const browser = await chromium.launch({ channel: 'chrome', args: ['--no-sandbox'] });

  for (const ph of phases(now)) {
    if (ONLY && !ONLY.includes(ph.key)) continue;
    const r = { via: ph.via, what: ph.what };
    out.phases[ph.key] = r;
    try {
      const seeded = await seedPhase(db, ph, tok);
      r.seeded = shape(seeded);
      restart();
      let act;
      if (ph.report) act = await reportEdit(browser, tok, ph, out);
      else if (ph.put) act = await v1Put(ph);
      else {
        const { ctx, page } = await openMain(browser, tok.token, out);
        act = await dragTo(page, ph.t0 === 'invalid' ? 'invalid' : ph.t0, ph.target, ph.zone);
        if (!act.error) {
          // wait for the write(s) to land
          for (let i = 0; i < 60; i++) {
            await sleep(100);
            const docs = await db.collection('treatments').find({ notes: 'bf103 ' + ph.key }).toArray();
            if (ph.zone === 'middle' ? docs[0] && docs[0].created_at !== seeded.created_at : docs.length >= 2) break;
          }
          await sleep(1500);
          r.invalidGlyphsAfter = await glyphTransformAfter(page);
        }
        await ctx.close();
      }
      if (act.error) throw new Error(act.error);
      r.action = Object.assign({}, act, { glyph: act.glyph ? { invalid: act.glyph.invalid, hit: act.glyph.hit, transform: act.glyph.transform } : undefined,
        expected: act.expected ? iso(Math.round(act.expected)) : undefined });
      const docs = await db.collection('treatments').find({ notes: 'bf103 ' + ph.key }).toArray();
      r.docs = docs.map(shape);
      const moved = ph.zone === 'top' ? docs.find(d => d.carbs && !d.insulin && String(d._id) !== String(seeded._id))
        : ph.zone === 'bottom' ? docs.find(d => d.insulin && !d.carbs && String(d._id) !== String(seeded._id))
        : docs.find(d => String(d._id) === String(seeded._id));
      r.movedCreatedAtOk = !!moved && Math.abs(Date.parse(moved.created_at) - act.expected) <= act.tolMs;
      r.movedStaleFields = moved ? Object.keys(DERIVED).filter(k => {
        if (moved[k] === undefined) return false;
        if (k === 'date') return shape(moved).dateVsCreatedMin !== 0;
        if (k === 'mills') return moved.mills !== Date.parse(moved.created_at);
        return true;
      }) : null;
      if (ph.checkLeftBehind) {
        const left = docs.find(d => String(d._id) === String(seeded._id));
        r.leftBehindStaleFields = left ? Object.keys(DERIVED).filter(k => left[k] !== undefined &&
          (k === 'date' ? shape(left).dateVsCreatedMin !== 0 : k === 'mills' ? left.mills !== Date.parse(left.created_at) : true)) : ['missing'];
      }
      r.live = await props();
      if (ph.report || ph.put) { await sleep(70000); r.live70s = await props(); }
      restart();
      r.stored = await props();
      await db.collection('treatments').updateMany({ notes: 'bf103 ' + ph.key }, { $unset: DERIVED });
      restart();
      r.oracle = await props();
      const v = ph.what;
      const tol = v === 'iob' ? 0.05 : 0.5;
      r.delta = +(r.stored[v] - r.oracle[v]).toFixed(3);
      r.verdict = Math.abs(r.delta) <= tol ? 'FOLLOWS' : 'STALE';
      r.clean = (r.movedStaleFields || ['?']).length === 0 && (r.leftBehindStaleFields || []).length === 0 &&
        !(r.invalidGlyphsAfter > 0);
      findings.push({ ok: r.verdict === 'FOLLOWS' && r.movedCreatedAtOk && r.clean,
        text: `${ph.key} [${ph.via}]: ${v.toUpperCase()} stored ${r.stored[v]} vs oracle ${r.oracle[v]} (live ${r.live[v]}) -> ${r.verdict}; ` +
              `created_at at target ${r.movedCreatedAtOk}; stale fields on moved record [${(r.movedStaleFields || []).join(',')}]` +
              (r.leftBehindStaleFields ? `; stale fields left behind [${r.leftBehindStaleFields.join(',')}]` : '') +
              (r.invalidGlyphsAfter !== undefined ? `; invalid glyphs after ${r.invalidGlyphsAfter}` : '') +
              (r.live70s ? `; live after 70 s ${r.live70s[v]}` : '') });
    } catch (e) {
      r.error = e.message + (e.cause ? ' (' + (e.cause.code || e.cause.message) + ')' : '');
      findings.push({ ok: false, text: `${ph.key}: COULD NOT RUN — ${r.error}` });
    }
  }
  await browser.close();
  await mc.close();
  if (OUT) fs.writeFileSync(OUT, JSON.stringify(out, null, 2));
  findings.push({ ok: true, text: `page errors ${out.pageErrors.length}, console errors ${out.consoleErrors.length}` });
  report(`bf103 split drag (${LABEL})`, findings);
})().catch(e => { console.error('bf103 probe failed:', e.stack || e.message); process.exit(2); });
