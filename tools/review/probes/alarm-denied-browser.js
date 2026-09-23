#!/usr/bin/env node
'use strict';
/*
 * alarm-denied-browser.js — does a LEGITIMATE viewer still receive alarms on
 * dev after the alarm-delivery fix merged as #8745, including on an instance
 * set to AUTH_DEFAULT_ROLES=denied?
 *
 * The fix admits a page to alarm delivery at connection time only when the
 * deployment's anonymous default role already permits reading, and otherwise
 * only once the page offers credentials that permit reading. This probe drives
 * the REAL client in Chrome through the flows a person uses and records what
 * the page's own alarm connection receives. It sends nothing of its own over
 * any socket: it listens on the objects the page created, and the only thing
 * that makes an alarm happen is an ordinary REST upload of a low glucose value.
 *
 * Pages, all open at the same time so one trigger serves every arm:
 *   denied mode
 *     promptSecret   no credentials in the URL; the page asks; the API secret is
 *                    typed into the prompt                 -> MUST receive
 *     readableToken  ?token= for a subject with role `readable` -> MUST receive
 *     statusOnly     ?token= for a subject that may read status but not data;
 *                    the page loads and its main live connection is open, so
 *                    it can show the server is alive      -> must NOT receive
 *     anonymous      no credentials, prompt left unanswered -> must NOT receive
 *   readable mode
 *     anonymous      no credentials                        -> MUST receive
 *
 * LIVENESS, in the same run (a dead server answers every negative like a fixed
 * one): the server log must show the alarm being emitted during the window,
 * and the statusOnly page must receive the server's viewer-count broadcast
 * during the window, which every connected page gets regardless of auth.
 *
 * Usage:
 *   node alarm-denied-browser.js --url http://127.0.0.1:14903 --secret <raw> \
 *     --mongo mongodb://127.0.0.1:27082 --db w2_alarm_denied --mode denied \
 *     --server-log <path> --label dev --out out.json
 * Exit: 0 every arm as expected, 1 not, 2 could not run. Synthetic data only.
 */

const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { report } = require(path.resolve(__dirname, '..', '..', 'queue', 'gates', '_gate.js'));

const MIN = 60000;
const ENTERED_BY = 'nsreview-alarm';
const DEVICE = 'synthetic://review/alarm';

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
const MODE = arg('--mode'), LOG = arg('--server-log'), LABEL = arg('--label', 'instance'), OUT = arg('--out');
if (!URL_BASE || !SECRET || !MONGO || !DB || !LOG || !['denied', 'readable'].includes(MODE)) {
  console.error('need --url --secret --mongo --db --server-log --mode denied|readable'); process.exit(2);
}
const SHA1 = crypto.createHash('sha1').update(SECRET).digest('hex');

async function api(method, p, body) {
  const r = await fetch(URL_BASE + p, { method,
    headers: { 'api-secret': SHA1, 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const t = await r.text(); let j = null; try { j = JSON.parse(t); } catch { /* */ }
  return { code: r.status, json: j };
}

const emitCount = () => (fs.readFileSync(LOG, 'utf8').match(/emitted urgent_alarm to subscribed clients/g) || []).length;

async function subject(name, roleName, permissions) {
  if (permissions) await api('POST', '/api/v2/authorization/roles', { name: roleName, permissions });
  await api('POST', '/api/v2/authorization/subjects', { name, roles: [roleName] });
  const s = ((await api('GET', '/api/v2/authorization/subjects')).json || []).find(x => x.name === name);
  if (!s || !s.accessToken) throw new Error(`could not mint ${name}`);
  return s.accessToken;
}

// Installed before any page script runs. Attaches listeners to the sockets the
// client itself creates, whenever it (re)creates them.
const RECORDER = () => {
  window.__w2 = { events: [], attached: [] };
  const seen = new WeakSet();
  setInterval(() => {
    const c = window.Nightscout && window.Nightscout.client;
    if (!c) return;
    if (c.alarmSocket && !seen.has(c.alarmSocket)) {
      // MEASURED 2026-09-22: a per-event listener added here runs AFTER the
      // client's own handler, and on a page with no glucose data that handler
      // throws (it dereferences client.latestSGV in its "disabled locally"
      // branch). The throw stops later listeners, so a receipt went unrecorded
      // and a negative arm passed for the wrong reason. onAny runs first.
      const KEEP = ['urgent_alarm', 'alarm', 'notification', 'clear_alarm', 'announcement'];
      const rec = (ev, n) => { if (KEEP.includes(ev)) window.__w2.events.push({ ev, t: Date.now(), level: n && n.level, title: n && n.title }); };
      if (typeof c.alarmSocket.onAny === 'function') {
        c.alarmSocket.onAny(rec); window.__w2.attached.push({ what: 'alarm:onAny', t: Date.now() });
      } else {
        for (const ev of KEEP) c.alarmSocket.on(ev, n => rec(ev, n));
        window.__w2.attached.push({ what: 'alarm:on', t: Date.now() });
      }
      seen.add(c.alarmSocket);
    }
    if (c.socket && !seen.has(c.socket)) {
      seen.add(c.socket); window.__w2.attached.push({ what: 'main', t: Date.now() });
      c.socket.on('clients', () => window.__w2.events.push({ ev: 'clients', t: Date.now() }));
    }
  }, 50);
};

async function openPage(browser, name, url, opts) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, timezoneId: 'UTC' });
  const page = await ctx.newPage();
  const rec = { name, errors: [], statusCodes: [] };
  page.on('pageerror', e => rec.errors.push(String(e.message)));
  page.on('dialog', d => d.dismiss().catch(() => {}));      // window.alert/confirm only; the auth prompt is a DOM dialog
  page.on('response', r => { if (r.url().includes('/api/v1/status.json')) rec.statusCodes.push(r.status()); });
  await page.addInitScript(RECORDER);
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 180000 });
  if (opts && opts.typeSecret) {
    await page.waitForSelector('#apisecret', { state: 'visible', timeout: 90000 });
    await page.fill('#apisecret', SECRET);
    await page.click('#requestauthenticationdialog-btn');
  }
  return { page, ctx, rec };
}

async function snapshot(p, since) {
  return p.page.evaluate((since) => {
    const w = window.__w2 || { events: [], attached: [] };
    const c = window.Nightscout && window.Nightscout.client;
    const after = w.events.filter(e => e.t >= since);
    const count = ev => after.filter(e => e.ev === ev).length;
    const cont = document.querySelector('#container');
    return {
      urgent: count('urgent_alarm'), warn: count('alarm'), clear: count('clear_alarm'), clients: count('clients'),
      urgentTitles: [...new Set(after.filter(e => e.ev === 'urgent_alarm').map(e => e.title))],
      attached: w.attached.map(a => a.what),
      alarmSocketConnected: !!(c && c.alarmSocket && c.alarmSocket.connected),
      mainSocketConnected: !!(c && c.socket && c.socket.connected),
      containerAlarming: !!(cont && cont.classList.contains('alarming')),
      containerUrgent: !!(cont && cont.classList.contains('urgent')),
      chart: document.querySelectorAll('#chartContainer svg').length,
      promptVisible: !!(document.querySelector('#requestauthenticationdialog') &&
                        document.querySelector('#requestauthenticationdialog').offsetParent !== null),
    };
  }, since);
}

(async () => {
  const { chromium } = resolveDep('playwright-core');
  const { MongoClient } = resolveDep('mongodb');
  const mc = new MongoClient(`${MONGO}/${DB}`); await mc.connect(); const db = mc.db(DB);
  const findings = [];
  const out = { label: LABEL, mode: MODE, when: new Date().toISOString(), pages: {} };

  if (await db.collection('entries').countDocuments({})) { console.error(`${DB} not empty; reset it first`); process.exit(2); }
  const now = Math.floor(Date.now() / MIN) * MIN;
  const st = await (await fetch(`${URL_BASE}/api/v1/status.json`)).status;
  out.anonymousStatusHttp = st;
  findings.push({ ok: MODE === 'denied' ? st === 401 : st === 200, text: `anonymous /api/v1/status.json HTTP ${st} (mode ${MODE})` });
  const settings = (await api('GET', '/api/v1/status.json')).json.settings;
  out.thresholds = settings.thresholds; out.alarmTypes = settings.alarmTypes; out.alarmUrgentLow = settings.alarmUrgentLow;
  findings.push({ ok: settings.alarmUrgentLow === true && settings.alarmTypes.includes('simple'),
    text: `server settings: alarmTypes=${settings.alarmTypes} alarmUrgentLow=${settings.alarmUrgentLow} bgLow=${settings.thresholds.bgLow}` });

  // seed: profile + 3 h of in-range readings, newest 5 min ago; verified in mongo
  const sched = v => [{ time: '00:00', timeAsSeconds: 0, value: String(v) }];
  await api('POST', '/api/v1/profile', [{ defaultProfile: 'Default', mills: String(now - 2 * 24 * 60 * MIN),
    startDate: new Date(now - 2 * 24 * 60 * MIN).toISOString(), units: 'mg/dl', enteredBy: ENTERED_BY,
    store: { Default: { dia: '5', carbs_hr: '20', delay: '20', timezone: 'UTC', units: 'mg/dl', basal: sched(0.8),
      sens: sched(50), carbratio: sched(10), target_low: sched(100), target_high: sched(120) } } }]);
  const entries = [];
  for (let i = 36; i >= 1; i--) entries.push({ type: 'sgv', sgv: 105, direction: 'Flat', date: now - i * 5 * MIN,
    dateString: new Date(now - i * 5 * MIN).toISOString(), device: DEVICE });
  await api('POST', '/api/v1/entries', entries);
  const nE = await db.collection('entries').countDocuments({});
  findings.push({ ok: nE === 36, text: `mongo entries after seed: ${nE} (want 36)` });

  const browser = await chromium.launch({ channel: 'chrome', args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required'] });
  const pages = {};
  let want, readable = '';
  if (MODE === 'denied') {
    readable = await subject('w2-reader', 'readable');
    const statusOnly = await subject('w2-status-only', 'w2-status-only', ['api:status:read']);
    // negatives first, so the later connections produce viewer-count broadcasts they can observe
    pages.anonymous = await openPage(browser, 'anonymous', `${URL_BASE}/`);
    pages.statusOnly = await openPage(browser, 'statusOnly', `${URL_BASE}/?token=${statusOnly}`);
    pages.readableToken = await openPage(browser, 'readableToken', `${URL_BASE}/?token=${readable}`);
    pages.promptSecret = await openPage(browser, 'promptSecret', `${URL_BASE}/`, { typeSecret: true });
    want = { anonymous: false, statusOnly: false, readableToken: true, promptSecret: true };
  } else {
    pages.anonymous = await openPage(browser, 'anonymous', `${URL_BASE}/`);
    want = { anonymous: true };
  }

  // settle: every page that is meant to receive must have its alarm connection up
  const deadline = Date.now() + 90000;
  for (;;) {
    const snaps = await Promise.all(Object.values(pages).map(p => snapshot(p, 0)));
    const ready = Object.keys(pages).every((k, i) => !want[k] || (snaps[i].alarmSocketConnected && snaps[i].chart > 0));
    if (ready || Date.now() > deadline) break;
    await new Promise(r => setTimeout(r, 500));
  }
  await new Promise(r => setTimeout(r, 4000));

  // trigger: two ordinary REST uploads of a low reading, one minute apart in data time
  const t0 = Date.now();
  const emitsBefore = emitCount();
  const low = [{ v: 45, at: now - MIN }, { v: 44, at: now }];
  for (const l of low) {
    const r = await api('POST', '/api/v1/entries', [{ type: 'sgv', sgv: l.v, direction: 'Flat', date: l.at,
      dateString: new Date(l.at).toISOString(), device: DEVICE }]);
    out.triggerHttp = (out.triggerHttp || []).concat(r.code);
    await new Promise(r => setTimeout(r, 8000));
  }
  // one more connection mid-window, so every open page gets a viewer-count broadcast
  const pinger = await openPage(browser, 'pinger', MODE === 'denied' ? `${URL_BASE}/?token=${readable}` : `${URL_BASE}/`);
  await new Promise(r => setTimeout(r, 6000));
  await pinger.ctx.close();
  await new Promise(r => setTimeout(r, 2000));
  const emitsAfter = emitCount();
  out.serverEmits = { before: emitsBefore, after: emitsAfter, during: emitsAfter - emitsBefore };
  out.lowStoredInMongo = await db.collection('entries').countDocuments({ sgv: { $lt: 55 } });

  findings.push({ ok: out.lowStoredInMongo === 2, text: `low readings stored in mongo: ${out.lowStoredInMongo} (want 2; trigger HTTP ${out.triggerHttp})` });
  findings.push({ ok: out.serverEmits.during > 0, text: `LIVENESS server emitted urgent_alarm ${out.serverEmits.during} time(s) during the window` });

  for (const [k, p] of Object.entries(pages)) {
    const s = await snapshot(p, t0);
    s.statusCodes = p.rec.statusCodes;
    s.pageErrors = p.rec.errors.filter(e => !/play\(\) failed/.test(e));
    out.pages[k] = s;
    const received = s.urgent > 0;
    // a negative arm must also be free of page errors: an alarm handler that
    // throws is itself evidence of receipt (see RECORDER)
    const ok = received === want[k] && (want[k] ? s.containerUrgent : s.pageErrors.length === 0);
    findings.push({ ok, text: `${k}: ${want[k] ? 'MUST' : 'must NOT'} receive — urgent_alarm events ${s.urgent} ` +
      `(${s.urgentTitles.join('/') || '-'}), page shows urgent alarm ${s.containerUrgent}, alarm conn ${s.alarmSocketConnected}, ` +
      `main conn ${s.mainSocketConnected}, viewer-count broadcasts ${s.clients}, status HTTP ${s.statusCodes.join(',')}, ` +
      `prompt ${s.promptVisible}, page errors ${s.pageErrors.length}` });
    if (k === 'statusOnly') {
      findings.push({ ok: s.mainSocketConnected && s.clients > 0,
        text: `LIVENESS statusOnly page's own live connection received ${s.clients} viewer-count broadcast(s) during the window` });
    }
  }
  await browser.close(); await mc.close();
  if (OUT) fs.writeFileSync(OUT, JSON.stringify(out, null, 2));
  report(`alarm delivery (${LABEL}, AUTH_DEFAULT_ROLES=${MODE})`, findings);
})().catch(e => { console.error('alarm probe failed:', e.stack || e.message); process.exit(2); });
