#!/usr/bin/env node
'use strict';
/*
 * rt-d3-drag-browser.js — RT-D3 (register BF-54): does dragging a treatment on
 * the main chart still write the time the pixel offset says it should, after
 * the D3 5.16 -> 7.9 migration (48075a18)?
 *
 * One instance per run. The caller runs it against 15.0.8 and against dev and
 * compares the two JSON outputs with --compare.
 *
 * WHAT IS MEASURED. A real Chrome, driven by playwright-core, presses the
 * mouse on a treatment's glyph, moves it a known number of CSS pixels, and
 * releases. The page's own confirm() is answered (accept or dismiss). The
 * stored `created_at` is then read from MongoDB DIRECTLY — never through
 * /api/v1/treatments, which applies a default time window.
 *
 * THE EXPECTED VALUE IS COMPUTED FROM THE AXIS, NOT FROM THE HANDLER. The
 * probe reads the focus x-scale's domain and range at release time and does
 * the linear mapping itself:
 *     x0       = (t0 - d0) * (r1 - r0) / (d1 - d0) + r0      (glyph origin)
 *     xRelease = clamp(x0 + dx, 0, chartWidth)
 *     expected = d0 + (xRelease - r0) * (d1 - d0) / (r1 - r0)
 * where the clamp is the one BF-54 names (renderer.js drag handlers). A drag
 * that stays inside the chart therefore expects t0 + dx * msPerPx.
 * Tolerance is 2 px worth of time: the pointer lands on integer device
 * pixels, the glyph origin does not.
 *
 * CONTROLS, all in the same run:
 *   - a drag whose confirm() is DISMISSED must leave created_at unchanged;
 *   - the first accepted drag is re-checked against a deliberately wrong
 *     expectation (+10 min) and that arm MUST come out as a mismatch;
 *   - a provenance check on the served dev bundle, so a 15.0.8 run is not
 *     silently serving dev's client (webpack production output lives in
 *     node_modules; this harness requires NODE_ENV=development).
 *
 * The left clamp is exercised too, and what it reveals is recorded rather than
 * asserted as a Move: x is clamped to 0, which is inside the 50 px "Remove"
 * drop zone, so a far-past drag proposes REMOVING the treatment. That drag is
 * always dismissed here.
 *
 * Usage:
 *   node rt-d3-drag-browser.js --url http://127.0.0.1:14902 --secret <raw> \
 *       --mongo mongodb://127.0.0.1:27082 --db w2_d3_dev --label dev \
 *       --expect-d3 7 --out dev.json [--skip-daytoday] [--only clampRight]
 *   node rt-d3-drag-browser.js --compare a.json b.json
 *
 * Exit: 0 every arm as expected, 1 a mismatch, 2 could not run.
 * Synthetic data only; every identifier below is a literal.
 */

const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { report } = require(path.resolve(__dirname, '..', '..', 'queue', 'gates', '_gate.js'));

const ENTERED_BY = 'nsreview-rt-d3';
const MIN = 60000;

function resolveDep(name) {
  for (const c of [process.env.NSREVIEW_DEPS && path.join(process.env.NSREVIEW_DEPS, name),
                   process.env.NSREVIEW_ROOT && path.join(process.env.NSREVIEW_ROOT, 'node_modules', name),
                   name].filter(Boolean)) {
    try { require.resolve(c); return require(c); } catch { /* next */ }
  }
  console.error(`${name} not found (set NSREVIEW_DEPS to a node_modules holding it)`); process.exit(2);
}

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const flag = k => argv.includes(k);

// ---------------------------------------------------------------- compare mode
if (flag('--compare')) {
  const i = argv.indexOf('--compare');
  const a = JSON.parse(fs.readFileSync(argv[i + 1], 'utf8'));
  const b = JSON.parse(fs.readFileSync(argv[i + 2], 'utf8'));
  const findings = [];
  for (const s of Object.keys(a.scenarios)) {
    const x = a.scenarios[s], y = b.scenarios[s];
    if (!y) { findings.push({ ok: false, text: `${s}: missing from ${b.label}` }); continue; }
    const same = x.operation === y.operation && x.accepted === y.accepted &&
                 x.verdict === y.verdict && x.changed === y.changed;
    findings.push({ ok: same, text: `${s}: ${a.label} ${x.verdict} (op ${x.operation}, Δstored ${x.storedShiftPx} px) | ` +
                                     `${b.label} ${y.verdict} (op ${y.operation}, Δstored ${y.storedShiftPx} px)` });
  }
  findings.push({ ok: a.pageErrors.length === b.pageErrors.length,
                  text: `page errors: ${a.label} ${a.pageErrors.length}, ${b.label} ${b.pageErrors.length}` });
  report(`rt-d3 drag: ${a.label} vs ${b.label}`, findings);
  return;
}

const URL_BASE = arg('--url');
const SECRET = arg('--secret');
const MONGO = arg('--mongo');
const DB = arg('--db');
const LABEL = arg('--label', 'instance');
const EXPECT_D3 = arg('--expect-d3');
const OUT = arg('--out');
const ONLY = arg('--only');
if (!URL_BASE || !SECRET || !MONGO || !DB || !EXPECT_D3) {
  console.error('need --url --secret --mongo --db --expect-d3'); process.exit(2);
}
const SHA1 = crypto.createHash('sha1').update(SECRET).digest('hex');

async function api(method, p, body) {
  const r = await fetch(URL_BASE + p, {
    method, headers: { 'api-secret': SHA1, 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const t = await r.text();
  let j = null; try { j = JSON.parse(t); } catch { /* not json */ }
  return { code: r.status, body: t, json: j };
}

// ---------------------------------------------------------------- provenance
// Tokens that exist only in dev's client source for the three D3 files.
// Each must be ABSENT when --expect-d3 5 and PRESENT when --expect-d3 7.
const DEV_ONLY_TOKENS = ['d3.pointer(event.touches', 'profileRedirectRequested'];
async function provenance() {
  const b = await (await fetch(URL_BASE + '/devbundle/js/bundle.app.js')).text();
  const out = { bytes: b.length, md5: crypto.createHash('md5').update(b).digest('hex').slice(0, 12), tokens: {} };
  for (const t of DEV_ONLY_TOKENS) out.tokens[t] = b.split(t).length - 1;
  const want = EXPECT_D3 === '7';
  out.ok = b.length > 100000 && DEV_ONLY_TOKENS.every(t => (out.tokens[t] > 0) === want);
  return out;
}

// ---------------------------------------------------------------- seed
function profile(startMs) {
  const sched = v => [{ time: '00:00', timeAsSeconds: 0, value: String(v) }];
  return [{
    defaultProfile: 'Default', mills: String(startMs), startDate: new Date(startMs).toISOString(),
    units: 'mg/dl', enteredBy: ENTERED_BY,
    store: { Default: { dia: '5', carbs_hr: '20', delay: '20', timezone: 'UTC', units: 'mg/dl',
      basal: sched(0.8), sens: sched(50), carbratio: sched(10), target_low: sched(100), target_high: sched(120) } },
  }];
}

// Scenario table. offsetMin places the treatment; dx is the pointer move in CSS
// px, or 'right'/'left' for a drag deliberately past the chart edge.
const SCENARIOS = [
  { key: 'comboMoveLeft',  offsetMin: -80, carbs: 30, insulin: 2, eventType: 'Meal Bolus',       dx: -80, accept: true, expectOp: 'Move' },
  { key: 'carbMoveRight',  offsetMin: -35, carbs: 15,             eventType: 'Carb Correction',  dx: 45,  accept: true, expectOp: 'Move' },
  { key: 'cancelled',      offsetMin: -110, carbs: 20, insulin: 1, eventType: 'Meal Bolus',      dx: -60, accept: false, expectOp: 'Move' },
  { key: 'clampRight',     offsetMin: -10, carbs: 12,             eventType: 'Carb Correction',  dx: 'right', accept: true, expectOp: 'Move' },
  { key: 'clampLeft',      offsetMin: -55, insulin: 1.5,          eventType: 'Correction Bolus', dx: 'left', accept: false, expectOp: 'Remove' },
];

async function seed(db, now) {
  const findings = [];
  const prof = await api('POST', '/api/v1/profile', profile(now - 2 * 24 * 60 * MIN));
  findings.push({ ok: prof.code < 300, text: `profile POST HTTP ${prof.code}` });
  const entries = [];
  for (let i = 0; i < 72; i++) {           // 6 h of 5-minute readings, oldest first
    const t = now - (72 - i) * 5 * MIN;
    entries.push({ type: 'sgv', sgv: 110 + (i % 6) * 2, direction: 'Flat', date: t,
                   dateString: new Date(t).toISOString(), device: 'synthetic://review/rt-d3' });
  }
  const e = await api('POST', '/api/v1/entries', entries);
  findings.push({ ok: e.code < 300, text: `entries POST HTTP ${e.code} (${entries.length})` });
  const tx = SCENARIOS.map(s => Object.assign({
    eventType: s.eventType, created_at: new Date(now + s.offsetMin * MIN).toISOString(),
    enteredBy: ENTERED_BY, notes: 'rt-d3 ' + s.key,
  }, s.carbs ? { carbs: s.carbs } : {}, s.insulin ? { insulin: s.insulin } : {}));
  const t = await api('POST', '/api/v1/treatments', tx);
  findings.push({ ok: t.code < 300, text: `treatments POST HTTP ${t.code} (${tx.length})` });
  // authoritative: mongo, not the endpoint under test
  const ids = {};
  for (const s of SCENARIOS) {
    const doc = await db.collection('treatments').findOne({ notes: 'rt-d3 ' + s.key });
    ids[s.key] = doc ? { _id: doc._id, t0: Date.parse(doc.created_at), stored0: doc.created_at } : null;
    findings.push({ ok: !!doc, text: `mongo has ${s.key}: ${doc ? doc.created_at : 'MISSING'}` });
  }
  const nE = await db.collection('entries').countDocuments({});
  findings.push({ ok: nE === entries.length, text: `mongo entries ${nE} (want ${entries.length})` });
  return { findings, ids };
}

async function mintToken() {
  const role = 'w2-treatment-editor';
  await api('POST', '/api/v2/authorization/roles', { name: role, permissions: ['*:*:read', 'api:treatments:*'] });
  await api('POST', '/api/v2/authorization/subjects', { name: 'w2-editor', roles: [role] });
  const subs = (await api('GET', '/api/v2/authorization/subjects')).json || [];
  const s = subs.find(x => x.name === 'w2-editor');
  if (!s || !s.accessToken) throw new Error('could not mint an editor token');
  return { token: s.accessToken, role, permissions: ['*:*:read', 'api:treatments:*'] };
}

// ---------------------------------------------------------------- browser
async function glyph(page, t0) {
  return page.evaluate((t0) => {
    const c = window.Nightscout && window.Nightscout.client;
    const ch = c && c.chart;
    if (!ch || !ch.xScale) return { error: 'no chart' };
    const d = ch.xScale.domain().map(Number), r = ch.xScale.range();
    const width = Number(ch.charts.attr('width'));
    const x0 = (t0 - d[0]) * (r[1] - r[0]) / (d[1] - d[0]) + r[0];
    const gs = [...document.querySelectorAll('#chartContainer g.draggable-treatment')];
    const mine = gs.filter(g => {
      const m = /translate\(\s*([-\d.e]+)[ ,]+([-\d.e]+)/.exec(g.getAttribute('transform') || '');
      return m && Math.abs(Number(m[1]) - x0) < 0.75;
    });
    if (!mine.length) return { error: `no glyph at x0=${x0.toFixed(2)} (have ${gs.length})`, d, r, width };
    const ctm = mine[0].getScreenCTM();
    const svg = document.querySelector('#chartContainer svg').getBoundingClientRect();
    const under = document.elementFromPoint(ctm.e, ctm.f);
    return {
      d, r, width, x0, focusHeight: ch.focusHeight, cx: ctm.e, cy: ctm.f, scale: ctm.a,
      svgLeft: svg.left, svgRight: svg.right, cursor: getComputedStyle(mine[0]).cursor,
      hit: !!(under && mine.some(g => g.contains(under))),
      yLocal: Number(/translate\(\s*[-\d.e]+[ ,]+([-\d.e]+)/.exec(mine[0].getAttribute('transform'))[1]),
    };
  }, t0);
}

async function drag(page, db, sc, ids) {
  const id = ids[sc.key];
  const g = await glyph(page, id.t0);
  if (g.error) return { error: g.error };
  let target;
  if (sc.dx === 'right') target = g.svgRight + 120;
  else if (sc.dx === 'left') target = g.svgLeft - 120;
  else target = g.cx + sc.dx;
  const dxPx = target - g.cx;

  let dialog = null;
  const onDialog = async dl => { dialog = dl.message(); if (sc.accept) await dl.accept(); else await dl.dismiss(); };
  page.once('dialog', onDialog);

  await page.mouse.move(g.cx, g.cy);
  await page.mouse.down();
  const steps = 12;
  for (let i = 1; i <= steps; i++) await page.mouse.move(g.cx + dxPx * i / steps, g.cy, { steps: 1 });
  // the axis as it stands at release: what the handler's xScale.invert uses
  const atRelease = await page.evaluate(() => {
    const ch = window.Nightscout.client.chart;
    return { d: ch.xScale.domain().map(Number), r: ch.xScale.range(), width: Number(ch.charts.attr('width')),
             tooltip: (document.querySelector('#tooltip, .tooltip') || {}).innerText || '' };
  });
  await page.mouse.up();
  for (let i = 0; i < 50 && dialog === null; i++) await page.waitForTimeout(100);
  page.off('dialog', onDialog);

  // read back from mongo; poll for a change when accepted, fixed wait when not
  let doc = null;
  for (let i = 0; i < (sc.accept ? 60 : 30); i++) {
    await new Promise(r => setTimeout(r, 100));
    doc = await db.collection('treatments').findOne({ _id: id._id });
    if (sc.accept && doc && doc.created_at !== id.stored0) break;
  }

  const { d, r, width } = atRelease;
  const msPerPx = (d[1] - d[0]) / (r[1] - r[0]);
  const x0 = (id.t0 - d[0]) / msPerPx + r[0];
  const xLocalUnclamped = x0 + dxPx / g.scale;
  const xRelease = Math.min(Math.max(0, xLocalUnclamped), width);
  const clamped = xRelease !== xLocalUnclamped;
  const expected = d[0] + (xRelease - r[0]) * msPerPx;
  const storedMs = doc ? Date.parse(doc.created_at) : NaN;
  const changed = !!doc && doc.created_at !== id.stored0;
  const tol = 2 * msPerPx;

  const opMatch = /^([A-Za-z ]+?) \?|^Change treatment time/.exec(dialog || '');
  const operation = !dialog ? 'no dialog'
    : /^Change treatment time/.test(dialog) ? 'Move'
    : /^Remove treatment/.test(dialog) ? 'Remove'
    : /^Change (carbs|insulin) time/.test(dialog) ? 'Move ' + /^Change (\w+)/.exec(dialog)[1]
    : /^Remove (carbs|insulin)/.test(dialog) ? 'Remove ' + /^Remove (\w+)/.exec(dialog)[1]
    : (opMatch ? opMatch[1] : dialog);

  let verdict;
  if (sc.accept) verdict = changed && Math.abs(storedMs - expected) <= tol ? 'MATCH' : 'MISMATCH';
  else verdict = !changed && doc ? 'UNCHANGED' : 'CHANGED';

  return {
    t0: id.stored0, stored: doc ? doc.created_at : null, docType: doc ? typeof doc.created_at : null,
    expected: new Date(Math.round(expected)).toISOString(), deltaMs: Math.round(storedMs - expected),
    tolMs: Math.round(tol), msPerPx: Math.round(msPerPx), pointerDxPx: Math.round(dxPx), ctmScale: g.scale,
    x0: +x0.toFixed(2), xRelease: +xRelease.toFixed(2), xUnclamped: +xLocalUnclamped.toFixed(2), clamped,
    chartWidth: width, domain: d.map(v => new Date(v).toISOString()), yLocal: +g.yLocal.toFixed(1),
    focusHeight: +g.focusHeight.toFixed(1), hitOnGlyph: g.hit, cursor: g.cursor,
    dialog, operation, accepted: sc.accept, changed,
    storedShiftPx: doc ? +((storedMs - id.t0) / msPerPx).toFixed(1) : null,
    storedVsNowMin: doc ? +((storedMs - Date.now()) / MIN).toFixed(1) : null,
    verdict,
  };
}

async function daytoday(browser, token) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 }, timezoneId: 'UTC' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e.message)));
  await page.goto(`${URL_BASE}/report?token=${token}`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.waitForSelector('#rp_show', { state: 'visible', timeout: 60000 });
  await page.click('#daytoday');
  await page.click('#rp_show');
  await page.waitForFunction(() => document.querySelectorAll('[id^="daytodaychart-"] svg').length > 0,
    { timeout: 60000 }).catch(() => {});
  const r = await page.evaluate(() => ({
    charts: document.querySelectorAll('[id^="daytodaychart-"]').length,
    svgs: document.querySelectorAll('[id^="daytodaychart-"] svg').length,
    circles: document.querySelectorAll('[id^="daytodaychart-"] svg circle').length,
  }));
  // exercise the migrated mouseover path (it only renders a tooltip for OpenAPS
  // data, but the handler runs for every glucose circle)
  const c = await page.$('[id^="daytodaychart-"] svg circle');
  if (c) { await c.hover().catch(() => {}); await page.waitForTimeout(300); }
  await ctx.close();
  return Object.assign(r, { errors: errors.filter(e => !/play\(\) failed/.test(e)) });
}

(async () => {
  const { chromium } = resolveDep('playwright-core');
  const { MongoClient } = resolveDep('mongodb');
  const mc = new MongoClient(`${MONGO}/${DB}`);
  await mc.connect();
  const db = mc.db(DB);
  const findings = [];
  const out = { label: LABEL, url: URL_BASE, when: new Date().toISOString(), scenarios: {}, pageErrors: [] };

  const prov = await provenance();
  out.provenance = prov;
  findings.push({ ok: prov.ok, text: `provenance (expect D3 ${EXPECT_D3}): bundle ${prov.bytes}B md5 ${prov.md5} tokens ${JSON.stringify(prov.tokens)}` });
  if (!prov.ok) { report(`rt-d3 drag (${LABEL})`, findings); process.exit(1); }

  const existing = await db.collection('treatments').countDocuments({});
  if (existing) { console.error(`database ${DB} already holds ${existing} treatments; reset it first`); process.exit(2); }
  const now = Math.floor(Date.now() / MIN) * MIN;
  const s = await seed(db, now);
  findings.push(...s.findings);
  const tok = await mintToken();
  out.role = { name: tok.role, permissions: tok.permissions };

  const browser = await chromium.launch({ channel: 'chrome', args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 }, timezoneId: 'UTC' });
  const page = await ctx.newPage();
  page.on('pageerror', e => out.pageErrors.push(String(e.message)));
  page.on('console', m => { if (m.type() === 'error') (out.consoleErrors = out.consoleErrors || []).push(m.text().slice(0, 200)); });
  out.navigations = 0;
  page.on('framenavigated', f => { if (f === page.mainFrame()) out.navigations += 1; });
  await page.goto(`${URL_BASE}/?token=${tok.token}`, { waitUntil: 'domcontentloaded', timeout: 180000 });
  // MEASURED: a token-authenticated load navigates the main frame TWICE (the
  // client reloads itself once), so the first chart seen can be torn down
  // mid-probe. Wait for the chart, let the reload happen, then wait again.
  const chartReady = () => page.waitForFunction(() => window.Nightscout && window.Nightscout.client &&
    window.Nightscout.client.chart && document.querySelectorAll('#chartContainer g.draggable-treatment').length > 0,
    { timeout: 90000 });
  await chartReady();
  await page.waitForTimeout(5000);
  await chartReady();
  const editVisible = await page.isVisible('#editbutton');
  findings.push({ ok: editVisible, text: `edit button visible for role ${tok.role}: ${editVisible}` });
  await page.click('#editbutton');
  await page.waitForTimeout(500);

  for (const sc of SCENARIOS) {
    if (ONLY && sc.key !== ONLY) continue;
    const r = await drag(page, db, sc, s.ids);
    out.scenarios[sc.key] = r;
    if (r.error) { findings.push({ ok: false, text: `${sc.key}: COULD NOT DRAG — ${r.error}` }); continue; }
    const want = sc.accept ? 'MATCH' : 'UNCHANGED';
    // the operation is asserted too: under clamp ablation a far-left drag stops
    // proposing Remove and proposes a Move into the far past instead
    findings.push({ ok: r.verdict === want && r.hitOnGlyph && r.operation === sc.expectOp,
      text: `${sc.key}: op=${r.operation} (want ${sc.expectOp}) ${sc.accept ? 'accepted' : 'dismissed'} pointer ${r.pointerDxPx}px ` +
            `stored ${r.t0} -> ${r.stored} expected ${r.expected} Δ${r.deltaMs}ms (tol ${r.tolMs}) ` +
            `clamped=${r.clamped} -> ${r.verdict}` });
    await page.waitForTimeout(1500);   // let the data-update redraw land before the next glyph lookup
  }

  // CONTROL: the comparison must be able to say MISMATCH.
  const first = out.scenarios.comboMoveLeft || out.scenarios[ONLY];
  if (first && first.stored && first.accepted) {
    const wrong = Date.parse(first.expected) + 10 * MIN;
    const says = Math.abs(Date.parse(first.stored) - wrong) <= first.tolMs ? 'MATCH' : 'MISMATCH';
    out.wrongExpectedControl = { wrongExpected: new Date(wrong).toISOString(), says };
    findings.push({ ok: says === 'MISMATCH', text: `control: same stored value vs deliberately wrong expectation (+10 min) -> ${says} (must be MISMATCH)` });
  }

  const drawn = await page.evaluate(() => document.querySelectorAll('#chartContainer svg').length);
  findings.push({ ok: drawn > 0, text: `main chart svg present after drags: ${drawn}` });
  const pe = out.pageErrors.filter(e => !/play\(\) failed/.test(e));
  findings.push({ ok: pe.length === 0, text: `main page errors: ${pe.length}${pe.length ? ' (' + pe[0].slice(0, 80) + ')' : ''}` });
  await ctx.close();

  if (!flag('--skip-daytoday')) {
    const dt = await daytoday(browser, tok.token);
    out.daytoday = dt;
    findings.push({ ok: dt.svgs > 0 && dt.errors.length === 0,
      text: `daytoday report: ${dt.charts} day charts, ${dt.svgs} svg, ${dt.circles} circles, ${dt.errors.length} page errors` +
            (dt.errors.length ? ' (' + dt.errors[0].slice(0, 80) + ')' : '') });
  }
  await browser.close();
  await mc.close();
  if (OUT) fs.writeFileSync(OUT, JSON.stringify(out, null, 2));
  report(`rt-d3 drag (${LABEL})`, findings);
})().catch(e => { console.error('rt-d3 drag probe failed:', e.stack || e.message); process.exit(2); });
