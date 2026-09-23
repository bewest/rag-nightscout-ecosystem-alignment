#!/usr/bin/env node
'use strict';
/*
 * alarm-no-reading-browser.js — BF-90. What does a Nightscout page do, and
 * show, when an alarm reaches it while it holds no glucose reading?
 *
 * The page's `alarm` / `urgent_alarm` handlers decide whether to sound from
 * the latest reading (isAlarmForHigh / isAlarmForLow). With no reading both
 * are false, so the handler takes its "disabled locally" branch, and on
 * 15.0.8 and dev that branch logs `client.latestSGV.mgdl` unguarded: a
 * TypeError, and the chart refresh after it is skipped.
 *
 * NOTHING HERE FORCES A SERVER DECISION. Two ordinary ways in:
 *   --mode readable  (the shipped default) an anonymous page, and an opt-in
 *                    device alert (PUMP_ENABLE_ALERTS=true, pump in ENABLE)
 *                    raised by ordinary REST uploads of pump status while no
 *                    CGM reading is stored. Reachable on dev and on 15.0.8.
 *   --mode denied    a page whose token may read status but not data, next
 *                    to a `readable`-token page. On a release that delivers
 *                    alarms to the whole namespace (BF-75, 15.0.8) the
 *                    status-only page receives them with no data and no
 *                    chart; on dev it should not receive them at all.
 *
 * --reading present seeds 12 in-range readings first. It is the control: the
 * same pump alarm, with a reading, must sound, which is what makes "does not
 * sound with no reading" attributable to the missing reading and nothing else.
 *
 * Trigger: a pump status with a low reservoir (8 U -> WARN -> `alarm`), then a
 * lower one (3 U -> URGENT -> `urgent_alarm`), both verified in MongoDB.
 * Recording: a catch-all listener on the page's own alarm connection runs
 * before the page's handlers (a per-event listener registered after a
 * throwing handler never runs — measured 2026-09-22), plus page errors,
 * the page's own console lines from these handlers, and its alarm state.
 * Liveness in the same window: the server log's emission counts must rise.
 *
 * Usage:
 *   node alarm-no-reading-browser.js --url http://127.0.0.1:14961 --secret <raw> \
 *     --mongo mongodb://127.0.0.1:27193 --db bf3_x --mode readable --reading none \
 *     --server-log <path> --label dev [--out out.json] [--shots dir]
 * Exit: 0 every arm holds, 1 not, 2 could not run. Synthetic data only.
 */

const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { report } = require(path.resolve(__dirname, '..', '..', 'queue', 'gates', '_gate.js'));

const MIN = 60000;
const ENTERED_BY = 'nsreview-bf90';
const DEVICE = 'synthetic://review/bf90';

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
const MODE = arg('--mode'), READING = arg('--reading'), LOG = arg('--server-log');
const LABEL = arg('--label', 'instance'), OUT = arg('--out'), SHOTS = arg('--shots');
if (!URL_BASE || !SECRET || !MONGO || !DB || !LOG || !['denied', 'readable'].includes(MODE) ||
    !['none', 'present'].includes(READING)) {
  console.error('need --url --secret --mongo --db --server-log --mode denied|readable --reading none|present');
  process.exit(2);
}
const SHA1 = crypto.createHash('sha1').update(SECRET).digest('hex');

async function api(method, p, body) {
  const r = await fetch(URL_BASE + p, { method,
    headers: { 'api-secret': SHA1, 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const t = await r.text(); let j = null; try { j = JSON.parse(t); } catch { /* */ }
  return { code: r.status, json: j };
}

// 15.0.8 logs "... to all clients", dev "... to subscribed clients"
const emits = () => {
  const s = fs.readFileSync(LOG, 'utf8');
  return { warn: (s.match(/emitted alarm to /g) || []).length, urgent: (s.match(/emitted urgent_alarm to /g) || []).length };
};

async function subject(name, roleName, permissions) {
  if (permissions) await api('POST', '/api/v2/authorization/roles', { name: roleName, permissions });
  await api('POST', '/api/v2/authorization/subjects', { name, roles: [roleName] });
  const s = ((await api('GET', '/api/v2/authorization/subjects')).json || []).find(x => x.name === name);
  if (!s || !s.accessToken) throw new Error(`could not mint ${name}`);
  return s.accessToken;
}

const RECORDER = () => {
  window.__bf90 = { events: [] };
  const seen = new WeakSet();
  setInterval(() => {
    const c = window.Nightscout && window.Nightscout.client;
    if (!c || !c.alarmSocket || seen.has(c.alarmSocket)) return;
    const KEEP = ['urgent_alarm', 'alarm', 'clear_alarm'];
    c.alarmSocket.onAny((ev, n) => {
      if (KEEP.includes(ev)) window.__bf90.events.push({ ev, t: Date.now(), level: n && n.level, title: n && n.title });
    });
    seen.add(c.alarmSocket);
  }, 50);
};

const HANDLER_LINE = /alarm was disabled locally|Alarm raised!|Urgent alarm raised!/;

async function openPage(browser, name, url) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, timezoneId: 'UTC' });
  const page = await ctx.newPage();
  const rec = { name, errors: [], handlerLines: [] };
  page.on('pageerror', e => rec.errors.push({ t: Date.now(), msg: String(e.message) }));
  page.on('console', m => { const t = m.text(); if (HANDLER_LINE.test(t)) rec.handlerLines.push({ t: Date.now(), text: t.slice(0, 120) }); });
  page.on('dialog', d => d.dismiss().catch(() => {}));
  await page.addInitScript(RECORDER);
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 180000 });
  return { page, ctx, rec };
}

async function snapshot(p, since) {
  return p.page.evaluate((since) => {
    const w = window.__bf90 || { events: [] };
    const c = window.Nightscout && window.Nightscout.client;
    const after = w.events.filter(e => e.t >= since);
    const cont = document.querySelector('#container');
    return {
      warn: after.filter(e => e.ev === 'alarm').length,
      urgent: after.filter(e => e.ev === 'urgent_alarm').length,
      titles: [...new Set(after.map(e => e.title))],
      alarmSocketConnected: !!(c && c.alarmSocket && c.alarmSocket.connected),
      hasReading: !!(c && c.latestSGV),
      hasChart: !!(c && c.chart),
      chartSvgs: document.querySelectorAll('#chartContainer svg').length,
      containerAlarming: !!(cont && cont.classList.contains('alarming')),
      containerUrgent: !!(cont && cont.classList.contains('urgent')),
      containerWarning: !!(cont && cont.classList.contains('warning')),
      audioPlaying: document.querySelectorAll('.audio.alarms audio.playing').length,
      title: document.title,
      bgNow: (document.querySelector('.bgStatus .currentBG') || {}).textContent || '',
    };
  }, since);
}

(async () => {
  const { chromium } = resolveDep('playwright-core');
  const { MongoClient } = resolveDep('mongodb');
  const mc = new MongoClient(`${MONGO}/${DB}`); await mc.connect(); const db = mc.db(DB);
  const findings = [];
  const out = { label: LABEL, mode: MODE, reading: READING, when: new Date().toISOString(), pages: {} };

  for (const coll of ['entries', 'devicestatus']) {
    if (await db.collection(coll).countDocuments({})) { console.error(`${DB}.${coll} not empty; reset it first`); process.exit(2); }
  }
  const now = Math.floor(Date.now() / MIN) * MIN;
  const status = (await api('GET', '/api/v1/status.json')).json;
  const settings = status.settings;
  out.enable = settings.enable; out.pumpAlerts = status.extendedSettings && status.extendedSettings.pump;
  findings.push({ ok: settings.enable.includes('pump') && !!(out.pumpAlerts && String(out.pumpAlerts.enableAlerts) === 'true'),
    text: `server settings: pump enabled ${settings.enable.includes('pump')}, pump alerts ${JSON.stringify(out.pumpAlerts)}` });

  const sched = v => [{ time: '00:00', timeAsSeconds: 0, value: String(v) }];
  await api('POST', '/api/v1/profile', [{ defaultProfile: 'Default', mills: String(now - 2 * 24 * 60 * MIN),
    startDate: new Date(now - 2 * 24 * 60 * MIN).toISOString(), units: 'mg/dl', enteredBy: ENTERED_BY,
    store: { Default: { dia: '5', carbs_hr: '20', delay: '20', timezone: 'UTC', units: 'mg/dl', basal: sched(0.8),
      sens: sched(50), carbratio: sched(10), target_low: sched(100), target_high: sched(120) } } }]);
  const wantEntries = READING === 'present' ? 12 : 0;
  if (wantEntries) {
    const entries = [];
    for (let i = wantEntries; i >= 1; i--) entries.push({ type: 'sgv', sgv: 105, direction: 'Flat', date: now - i * 5 * MIN,
      dateString: new Date(now - i * 5 * MIN).toISOString(), device: DEVICE });
    await api('POST', '/api/v1/entries', entries);
  }
  const nE = await db.collection('entries').countDocuments({});
  findings.push({ ok: nE === wantEntries, text: `mongo entries after seed: ${nE} (want ${wantEntries})` });

  const browser = await chromium.launch({ channel: 'chrome', args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required'] });
  const pages = {}; let want;
  if (MODE === 'denied') {
    const statusOnly = await subject('bf90-status-only', 'bf90-status-only', ['api:status:read']);
    const readable = await subject('bf90-reader', 'readable');
    pages.statusOnly = await openPage(browser, 'statusOnly', `${URL_BASE}/?token=${statusOnly}`);
    pages.readableToken = await openPage(browser, 'readableToken', `${URL_BASE}/?token=${readable}`);
    want = { statusOnly: 'either', readableToken: 'receive' };
  } else {
    pages.anonymous = await openPage(browser, 'anonymous', `${URL_BASE}/`);
    want = { anonymous: 'receive' };
  }

  const deadline = Date.now() + 90000;
  for (;;) {
    const snaps = await Promise.all(Object.values(pages).map(p => snapshot(p, 0)));
    const ready = Object.keys(pages).every((k, i) => want[k] !== 'receive' || (snaps[i].alarmSocketConnected && snaps[i].hasChart));
    if (ready || Date.now() > deadline) break;
    await new Promise(r => setTimeout(r, 500));
  }
  await new Promise(r => setTimeout(r, 5000));   // the token page reloads itself once

  const t0 = Date.now();
  const before = emits();
  out.triggerHttp = [];
  for (const reservoir of [8, 3]) {
    const at = Date.now();
    const r = await api('POST', '/api/v1/devicestatus', [{ device: DEVICE, created_at: new Date(at).toISOString(),
      pump: { clock: new Date(at).toISOString(), reservoir, status: { status: 'normal', bolusing: false, suspended: false } } }]);
    out.triggerHttp.push(r.code);
    await new Promise(r => setTimeout(r, 9000));
  }
  const after = emits();
  out.serverEmits = { warn: after.warn - before.warn, urgent: after.urgent - before.urgent };
  out.devicestatusInMongo = await db.collection('devicestatus').countDocuments({});
  out.entriesInMongo = await db.collection('entries').countDocuments({});

  findings.push({ ok: out.devicestatusInMongo === 2, text: `trigger: pump statuses stored in mongo ${out.devicestatusInMongo} (want 2; HTTP ${out.triggerHttp})` });
  findings.push({ ok: out.entriesInMongo === wantEntries, text: `no reading arrived during the window: mongo entries ${out.entriesInMongo} (want ${wantEntries})` });
  findings.push({ ok: out.serverEmits.warn > 0 && out.serverEmits.urgent > 0,
    text: `LIVENESS server emitted alarm ${out.serverEmits.warn}x and urgent_alarm ${out.serverEmits.urgent}x during the window` });

  for (const [k, p] of Object.entries(pages)) {
    const s = await snapshot(p, t0);
    s.pageErrors = p.rec.errors.filter(e => e.t >= t0 && !/play\(\) failed/.test(e.msg)).map(e => e.msg);
    s.handlerLines = p.rec.handlerLines.filter(e => e.t >= t0).map(e => e.text);
    s.disabledLocallyLines = s.handlerLines.filter(l => /disabled locally/.test(l)).length;
    s.raisedLines = s.handlerLines.filter(l => /raised!/.test(l)).length;
    out.pages[k] = s;
    if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await p.page.screenshot({ path: path.join(SHOTS, `${LABEL}-${MODE}-${READING}-${k}.png`) }); }
    const received = s.warn + s.urgent;
    const summary = `${k}: received alarm ${s.warn}x urgent_alarm ${s.urgent}x (${s.titles.join(' / ') || '-'}); ` +
      `reading ${s.hasReading}, chart ${s.hasChart}; page errors ${s.pageErrors.length}` +
      (s.pageErrors.length ? ` [${[...new Set(s.pageErrors)].join(' | ').slice(0, 90)}]` : '') +
      `; handler lines: disabled-locally ${s.disabledLocallyLines}, raised ${s.raisedLines}; ` +
      `page alarm state ${s.containerAlarming ? (s.containerUrgent ? 'URGENT' : 'WARNING') : 'none'}, audio playing ${s.audioPlaying}`;
    if (want[k] === 'receive') {
      findings.push({ ok: s.warn > 0 && s.urgent > 0, text: `LIVENESS ${k} page received both alarm kinds — ${summary}` });
    } else {
      findings.push({ ok: true, text: `[observation] ${summary}` });
    }
    if (received === 0) continue;
    // DISCRIMINATES: the throw. Red on 15.0.8 and dev wherever a no-reading page receives.
    findings.push({ ok: s.pageErrors.length === 0, text: `[discriminates] ${k}: no page error while handling ${received} alarm(s)` });
    // DISCRIMINATES (no-reading pages): the handler reaches the end of its branch
    // and says why it did not sound. On the unfixed build the throw happens while
    // evaluating that log line's arguments, so the line never prints.
    if (!s.hasReading) {
      findings.push({ ok: s.disabledLocallyLines === received,
        text: `[discriminates] ${k}: every received alarm reached "disabled locally" (${s.disabledLocallyLines} of ${received})` });
    }
    // INVARIANT: whether the alarm is presented is unchanged by the fix.
    if (s.hasReading) {
      findings.push({ ok: s.containerAlarming && s.containerUrgent && s.raisedLines > 0,
        text: `[invariant] ${k}: WITH a reading the pump alarm is presented (urgent state ${s.containerUrgent}, raised lines ${s.raisedLines})` });
    } else {
      findings.push({ ok: !s.containerAlarming && s.raisedLines === 0,
        text: `[invariant] ${k}: with NO reading the page does not present the alarm (state ${s.containerAlarming}, raised lines ${s.raisedLines}) — the handler's decision, unchanged` });
    }
  }
  await browser.close(); await mc.close();
  if (OUT) fs.writeFileSync(OUT, JSON.stringify(out, null, 2));
  report(`alarm at a page with no reading — BF-90 (${LABEL}, ${MODE}, reading ${READING})`, findings);
})().catch(e => { console.error('bf90 probe failed:', e.stack || e.message); process.exit(2); });
