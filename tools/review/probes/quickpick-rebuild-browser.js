#!/usr/bin/env node
'use strict';
/*
 * quickpick-rebuild-browser.js — BF-69, measured the way a user meets it,
 * with BF-35's property (the carbs entered belong to the pick chosen) read
 * back from the page for every pick.
 *
 * The Bolus Wizard's quick-pick chooser was built once, when the calculator
 * was constructed, from the client's initial EMPTY sandbox, and never again.
 * Food arrives later with the first data update, so the chooser offered only
 * "(none)" for the life of the page. probes/quickpick-chooser-browser.js is
 * the two-instance version of the first arm below; this one drives the whole
 * feature on one instance so it can be run against each build in turn:
 *
 *   1. before any click: what the page built at construction (observation)
 *   2. one click on the Bolus Wizard toggle: the chooser offers exactly the
 *      seeded visible quick picks, in `position` order, no plain food, no
 *      hidden pick
 *   3. select each offered pick the way a user does (selectOption): the carbs
 *      field must read the grams in that pick's own label, and each seeded
 *      pick's carbs are distinct, so resolving a neighbour cannot pass
 *   4. a quick pick added through the REST API while the page is open is
 *      offered the next time the drawer is opened, once it is in the page's
 *      data (food is not in the broadcast delta; see step 4 below)
 *   5. hide-after-use (#8735's hidesAfterUse): submit the calculator with a
 *      hide-after-use pick selected; the confirmation must name that pick's
 *      carbs, the stored treatment must carry them (MongoDB), the stored pick
 *      must now be hidden (MongoDB), and the reopened chooser must not offer it
 *   6. no page errors anywhere in the run
 *
 * Also recorded: whether an anonymous viewer (no treatment-create permission)
 * is shown the Bolus Wizard at all, and whether the toggle is shown with
 * SHOW_PLUGINS as the server reports it — i.e. who can reach this.
 *
 * PREREQUISITES: NODE_ENV=development (see probes/provenance.js — run it
 * first), ENABLE containing `boluscalc food`, SHOW_PLUGINS containing
 * `boluscalc`, and an EMPTY database (the probe refuses otherwise). Never
 * waitUntil 'networkidle' (socket.io holds it open). Synthetic data only;
 * every identifier is a literal below.
 *
 * Usage:
 *   node quickpick-rebuild-browser.js --url http://127.0.0.1:14971 --secret <raw> \
 *     --mongo mongodb://127.0.0.1:27193 --db bf3q_dev --label dev [--out f.json] [--shots dir]
 * Exit: 0 every arm holds, 1 not, 2 could not run.
 */

const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { report } = require(path.resolve(__dirname, '..', '..', 'queue', 'gates', '_gate.js'));

const MIN = 60000;
const ENTERED_BY = 'nsreview-bf69';
const DEVICE = 'synthetic://review/bf69';

function resolveDep(name) {
  for (const c of [process.env.NSREVIEW_DEPS && path.join(process.env.NSREVIEW_DEPS, name),
                   process.env.NSREVIEW_ROOT && path.join(process.env.NSREVIEW_ROOT, 'node_modules', name),
                   name].filter(Boolean)) {
    try { require.resolve(c); return require(c); } catch { /* next */ }
  }
  console.error(`${name} not found (set NSREVIEW_DEPS)`); process.exit(2);
}

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const URL_BASE = arg('--url'), SECRET = arg('--secret'), MONGO = arg('--mongo'), DB = arg('--db');
const LABEL = arg('--label', 'instance'), OUT = arg('--out'), SHOTS = arg('--shots');
if (!URL_BASE || !SECRET || !MONGO || !DB) { console.error('need --url --secret --mongo --db'); process.exit(2); }
const SHA1 = crypto.createHash('sha1').update(SECRET).digest('hex');

async function api(method, p, body) {
  const r = await fetch(URL_BASE + p, { method,
    headers: { 'api-secret': SHA1, 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const t = await r.text(); let j = null; try { j = JSON.parse(t); } catch { /* */ }
  return { code: r.status, json: j };
}

// Each pick's `carbs` equals the sum of its foods' carbs x portions, which is
// what the calculator enters, and no two picks share a total.
const item = (name, carbs, portions) => ({ name, carbs, portion: 1, portions, unit: 'g' });
const PLAIN = [
  { type: 'food', name: 'bf69-apple', carbs: 12, portion: 1, unit: 'g', category: 'bf69', subcategory: 'fruit' },
  { type: 'food', name: 'bf69-bread', carbs: 15, portion: 1, unit: 'g', category: 'bf69', subcategory: 'grain' },
];
const PICKS = [   // inserted in this order; offered in position order
  { type: 'quickpick', name: 'bf69-lunch', carbs: 70, position: 2, hidden: false, hideafteruse: false, foods: [item('bf69-rice', 35, 2)] },
  { type: 'quickpick', name: 'bf69-hidden', carbs: 99, position: 0, hidden: true, hideafteruse: false, foods: [item('bf69-cake', 99, 1)] },
  { type: 'quickpick', name: 'bf69-breakfast', carbs: 45, position: 1, hidden: false, hideafteruse: false, foods: [item('bf69-oats', 45, 1)] },
  { type: 'quickpick', name: 'bf69-snack', carbs: 20, position: 3, hidden: false, hideafteruse: true, foods: [item('bf69-bar', 10, 2)] },
];
const LATE = { type: 'quickpick', name: 'bf69-late', carbs: 33, position: 4, hidden: false, hideafteruse: false, foods: [item('bf69-soup', 33, 1)] };
const EXPECT_OFFERED = ['bf69-breakfast (45 g)', 'bf69-lunch (70 g)', 'bf69-snack (20 g)'];

async function mintToken(name, role) {
  await api('POST', '/api/v2/authorization/subjects', { name, roles: [role] });
  const s = ((await api('GET', '/api/v2/authorization/subjects')).json || []).find(x => x.name === name);
  if (!s || !s.accessToken) throw new Error(`could not mint ${name}`);
  return s.accessToken;
}

const chooser = page => page.evaluate(() =>
  Array.from(document.querySelectorAll('#bc_quickpick option')).map(o => ({ v: o.value, t: o.text })));
const offered = opts => opts.filter(o => Number(o.v) >= 0).map(o => o.t);
const drawerOpen = page => page.evaluate(() => {
  const d = document.querySelector('#boluscalcDrawer'); return !!d && d.offsetParent !== null && getComputedStyle(d).display !== 'none';
});
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function clickToggle(page) {
  await page.click('#boluscalcDrawerToggle');
  await sleep(1200);
}

async function openDrawer(page) {
  if (await drawerOpen(page)) { await clickToggle(page); }   // close first
  await clickToggle(page);
}

(async () => {
  const { chromium } = resolveDep('playwright-core');
  const { MongoClient } = resolveDep('mongodb');
  const mc = new MongoClient(`${MONGO}/${DB}`); await mc.connect(); const db = mc.db(DB);
  const findings = [];
  const out = { label: LABEL, when: new Date().toISOString() };

  for (const coll of ['entries', 'food', 'treatments']) {
    if (await db.collection(coll).countDocuments({})) { console.error(`${DB}.${coll} not empty; reset it first`); process.exit(2); }
  }
  const status = (await api('GET', '/api/v1/status.json')).json;
  out.enable = status.settings.enable; out.showPlugins = status.settings.showPlugins;
  findings.push({ ok: out.enable.includes('boluscalc') && out.enable.includes('food') && /\bboluscalc\b/.test(out.showPlugins),
    text: `server settings: enable has boluscalc+food ${out.enable.includes('boluscalc') && out.enable.includes('food')}, showPlugins "${out.showPlugins}"` });

  // seed: profile, a short in-range trace (so the page is an ordinary one), foods
  const now = Math.floor(Date.now() / MIN) * MIN;
  const sched = v => [{ time: '00:00', timeAsSeconds: 0, value: String(v) }];
  await api('POST', '/api/v1/profile', [{ defaultProfile: 'Default', mills: String(now - 2 * 24 * 60 * MIN),
    startDate: new Date(now - 2 * 24 * 60 * MIN).toISOString(), units: 'mg/dl', enteredBy: ENTERED_BY,
    store: { Default: { dia: '5', carbs_hr: '20', delay: '20', timezone: 'UTC', units: 'mg/dl', basal: sched(0.8),
      sens: sched(50), carbratio: sched(10), target_low: sched(100), target_high: sched(120) } } }]);
  const entries = [];
  for (let i = 12; i >= 1; i--) entries.push({ type: 'sgv', sgv: 110, direction: 'Flat', date: now - i * 5 * MIN,
    dateString: new Date(now - i * 5 * MIN).toISOString(), device: DEVICE });
  await api('POST', '/api/v1/entries', entries);
  // interleave plain foods between quick picks, so an index into the wrong array lands on a different record
  for (const f of [PLAIN[0], PICKS[0], PICKS[1], PLAIN[1], PICKS[2], PICKS[3]]) await api('POST', '/api/v1/food', f);
  out.seeded = { food: await db.collection('food').countDocuments({}), quickpick: await db.collection('food').countDocuments({ type: 'quickpick' }),
    entries: await db.collection('entries').countDocuments({}) };
  findings.push({ ok: out.seeded.food === 6 && out.seeded.quickpick === 4 && out.seeded.entries === 12,
    text: `mongo after seed: food ${out.seeded.food} (want 6, of which quickpick ${out.seeded.quickpick}/4), entries ${out.seeded.entries}/12` });

  const browser = await chromium.launch({ channel: 'chrome', args: ['--no-sandbox'] });
  const errors = [];
  const dialogs = [];

  // who can reach it: an anonymous viewer on the default `readable` role
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, timezoneId: 'UTC' });
    const p = await ctx.newPage();
    p.on('pageerror', e => errors.push(`anonymous: ${e.message}`));
    await p.goto(`${URL_BASE}/`, { waitUntil: 'domcontentloaded', timeout: 180000 });
    await p.waitForFunction(() => window.Nightscout && Nightscout.client && Nightscout.client.sbx &&
      (Nightscout.client.sbx.data.food || []).length > 0, null, { timeout: 90000 }).catch(() => {});
    await sleep(2000);
    out.anonymousToggleVisible = await p.evaluate(() => { const t = document.querySelector('#boluscalcDrawerToggle'); return !!t && t.offsetParent !== null; });
    await ctx.close();
  }

  const token = await mintToken('bf69-admin', 'admin');
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, timezoneId: 'UTC' });
  const page = await ctx.newPage();
  page.on('pageerror', e => errors.push(String(e.message)));
  page.on('dialog', d => { dialogs.push({ type: d.type(), message: d.message() }); d.accept().catch(() => {}); });
  await page.goto(`${URL_BASE}/?token=${token}`, { waitUntil: 'domcontentloaded', timeout: 180000 });
  await sleep(4000);   // a token page reloads itself once; do not start on the first one
  await page.waitForFunction(() => window.Nightscout && Nightscout.client && Nightscout.client.sbx &&
    (Nightscout.client.sbx.data.food || []).length > 0, null, { timeout: 90000 });
  await page.waitForSelector('#boluscalcDrawerToggle', { state: 'visible', timeout: 30000 });
  await sleep(1500);
  out.foodInPage = await page.evaluate(() => Nightscout.client.sbx.data.food.length);

  // 1. what construction built
  out.beforeClick = offered(await chooser(page));
  findings.push({ ok: true, text: `[observation] before any click the chooser offers [${out.beforeClick.join(' | ')}] with ${out.foodInPage} food records in the page` });

  // 2. one user click
  await clickToggle(page);
  out.drawerOpenAfterClick = await drawerOpen(page);
  out.afterClick = offered(await chooser(page));
  if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, `${LABEL}-bf69-open.png`) }); }
  findings.push({ ok: JSON.stringify(out.afterClick) === JSON.stringify(EXPECT_OFFERED),
    text: `[discriminates] after one click on the Bolus Wizard (drawer open ${out.drawerOpenAfterClick}) the chooser offers ` +
          `[${out.afterClick.join(' | ')}] — want [${EXPECT_OFFERED.join(' | ')}]` });
  findings.push({ ok: !out.afterClick.some(t => /bf69-(apple|bread|hidden)/.test(t)),
    text: `[invariant] no plain food and no hidden quick pick is offered: [${out.afterClick.filter(t => /bf69-(apple|bread|hidden)/.test(t)).join(' | ') || 'none'}]` });

  // 3. select each pick as a user does; read back the carbs entered
  out.picks = [];
  for (const o of (await chooser(page)).filter(x => Number(x.v) >= 0)) {
    await page.selectOption('#bc_quickpick', o.v);
    await sleep(300);
    const carbs = await page.evaluate(() => document.querySelector('#bc_carbs').value);
    const m = /\((\d+) g\)$/.exec(o.t);
    out.picks.push({ label: o.t, labelled: m ? m[1] : null, entered: carbs });
  }
  await page.selectOption('#bc_quickpick', '-1'); await sleep(300);
  out.carbsAfterNone = await page.evaluate(() => document.querySelector('#bc_carbs').value);
  const matched = out.picks.filter(p => p.labelled !== null && p.entered === p.labelled);
  findings.push({ ok: out.picks.length === EXPECT_OFFERED.length && matched.length === out.picks.length,
    text: `[discriminates] every offered pick enters its own label's carbs: ${matched.length} of ${out.picks.length} ` +
          `(want ${EXPECT_OFFERED.length}) — ${out.picks.map(p => `${p.label} -> ${p.entered} g`).join('; ') || 'nothing to select'}; "(none)" -> ${out.carbsAfterNone}` });

  // 4. a quick pick added while the page is open. MEASURED 2026-09-23 on
  // 15.0.8, dev and the fix alike: a food written through the API does NOT
  // reach an open page by itself — lib/data/calcdelta.js leaves `food` out of
  // the delta it broadcasts, so only a full load carries food. A full load is
  // what a page gets on every (re)connection, so the probe waits for the delta
  // first, records that it did not come, then drops the page's transport the
  // way a network blip or a sleeping laptop does and lets socket.io reconnect.
  // The arm is about the chooser once the data IS in the page; the delivery
  // gap is recorded separately and is not BF-69.
  await clickToggle(page);   // close
  const lateHttp = (await api('POST', '/api/v1/food', LATE)).code;
  const lateIn = ms => page.waitForFunction(() => (Nightscout.client.sbx.data.food || []).some(f => f.name === 'bf69-late'), null, { timeout: ms })
    .then(() => true, () => false);
  out.lateByDelta = await lateIn(20000);
  out.lateByReconnect = null;
  if (!out.lateByDelta) {
    await page.evaluate(() => Nightscout.client.socket.io.engine.close());
    out.lateByReconnect = await lateIn(60000);
  }
  await sleep(1500);
  await openDrawer(page);
  out.afterLate = offered(await chooser(page));
  findings.push({ ok: true, text: `[observation] a food added through the API (HTTP ${lateHttp}) reached the open page by broadcast: ${out.lateByDelta}` +
    (out.lateByDelta ? '' : `; after a reconnect: ${out.lateByReconnect}`) });
  findings.push({ ok: (out.lateByDelta || out.lateByReconnect) === true && out.afterLate.includes('bf69-late (33 g)'),
    text: `[discriminates] once a new quick pick is in the page's data, the next open offers it: [${out.afterLate.join(' | ')}]` });

  // 5. hide after use, through the calculator's own submit
  const snack = (await chooser(page)).find(o => o.t === 'bf69-snack (20 g)');
  out.hideAfterUse = { selectable: !!snack };
  if (snack) {
    await page.selectOption('#bc_quickpick', snack.v); await sleep(300);
    out.hideAfterUse.entered = await page.evaluate(() => document.querySelector('#bc_carbs').value);
    await page.fill('#bc_enteredBy', ENTERED_BY).catch(() => {});
    const nDialogs = dialogs.length;
    await page.click('#boluscalcDrawer button');
    await sleep(4000);
    const confirm = dialogs.slice(nDialogs).find(d => d.type === 'confirm');
    out.hideAfterUse.confirmCarbs = confirm ? ((/Carbs Given: (\d+)/.exec(confirm.message) || [])[1] || null) : null;
    const t = await db.collection('treatments').find({ enteredBy: ENTERED_BY }).toArray();
    out.hideAfterUse.treatments = t.map(x => ({ eventType: x.eventType, carbs: x.carbs }));
    const stored = await db.collection('food').findOne({ name: 'bf69-snack' });
    out.hideAfterUse.storedHidden = stored ? stored.hidden : null;
    await openDrawer(page);
    out.hideAfterUse.offeredAfter = offered(await chooser(page));
  }
  const h = out.hideAfterUse;
  findings.push({ ok: !!h.selectable && h.entered === '20' && h.confirmCarbs === '20' &&
                      (h.treatments || []).length === 1 && Number(h.treatments[0].carbs) === 20 &&
                      String(h.storedHidden) === 'true' && !(h.offeredAfter || []).some(t => /bf69-snack/.test(t)),
    text: `[discriminates] hide-after-use: pick offered ${!!h.selectable}, entered ${h.entered} g, confirmation says ${h.confirmCarbs} g, ` +
          `stored treatment ${JSON.stringify(h.treatments || [])}, stored pick hidden ${h.storedHidden}, ` +
          `offered on reopen [${(h.offeredAfter || []).join(' | ')}]` });

  findings.push({ ok: errors.length === 0, text: `[discriminates] no page errors in the run: ${errors.length}` + (errors.length ? ` [${[...new Set(errors)].join(' | ').slice(0, 100)}]` : '') });
  findings.push({ ok: true, text: `[observation] reach: an anonymous viewer is shown the Bolus Wizard toggle: ${out.anonymousToggleVisible}; ` +
    `the admin-token viewer is, with showPlugins "${out.showPlugins}"` });

  out.errors = errors;
  await browser.close(); await mc.close();
  if (OUT) fs.writeFileSync(OUT, JSON.stringify(out, null, 2));
  report(`quick-pick chooser rebuild — BF-69 (${LABEL})`, findings);
})().catch(e => { console.error('bf69 probe failed:', e.stack || e.message); process.exit(2); });
