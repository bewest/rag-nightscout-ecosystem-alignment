#!/usr/bin/env node
'use strict';
/*
 * bf94-browser/probe.js — BF-94 in a real browser.
 *
 * lib/profilefunctions.js keeps `prevBasalTreatment` at module scope and returns it from
 * tempBasalTreatment(time) whenever `time` falls inside its [mills, endmills], before
 * searching the current list. The browser keeps one profilefunctions instance across data
 * updates. This probe asks: after a temp basal is replaced or shortened while a page is open,
 * does the page's basal pill or chart line keep showing the old temp?
 *
 * Per scenario: boot the tree's server on a fresh database, seed a 1.0 U/h profile, CGM
 * readings and (with --hist) earlier temps, upload temp A, open a page, wait until it shows
 * A, make the scenario's change over REST as the client does, then sample the open page every
 * 2 s for --watch seconds: the pill text (DOM), the basal line's value at "now" read from the
 * rendered SVG path, and client.profilefunctions.getTempBasal(now). Then a fresh page in a new
 * context (the control: same final data, new instance) and a reload of the first page.
 *
 * Usage: node probe.js --dir <crm tree> --label dev --scenario loop-new [--hist 1]
 *        --mongo mongodb://127.0.0.1:27941 --port 17941 --out results/x.json --shots results/shots
 * Synthetic data only. Exit 0 ran (verdict in JSON), 2 could not run.
 */
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { spawn } = require('child_process');

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const DIR = arg('--dir'), LABEL = arg('--label', 'x'), SC = arg('--scenario');
const HIST = arg('--hist', '0') === '1';
const MONGO = arg('--mongo'), PORT = Number(arg('--port', '17941'));
const OUT = arg('--out'), SHOTS = arg('--shots'), WATCH = Number(arg('--watch', '75'));
const A_LEN = Number(arg('--a-len', '30'));      // temp A programmed minutes
const A_AGO = Number(arg('--a-ago', '10'));      // temp A started this many minutes before the change
const NODE_VER = process.env.NODE_VER || '22.23.2';
if (!DIR || !SC || !MONGO || !OUT) { console.error('need --dir --scenario --mongo --out'); process.exit(2); }

const { chromium } = require('playwright');
const { MongoClient } = require(path.join(DIR, 'node_modules', 'mongodb'));

const MIN = 60000;
const SECRET = crypto.randomBytes(12).toString('hex');
const SHA1 = crypto.createHash('sha1').update(SECRET).digest('hex');
const DB = ('bf94_' + LABEL + '_' + SC + (HIST ? '_h' : '')).replace(/[^a-z0-9_]/gi, '_').slice(0, 60);
const BASE = 'http://127.0.0.1:' + PORT;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const iso = (t) => new Date(t).toISOString();
const uuid = () => crypto.randomUUID();

async function api (method, p, body, headers) {
  const r = await fetch(BASE + p, { method, headers: { 'content-type': 'application/json', 'api-secret': SHA1, ...(headers || {}) },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const t = await r.text(); let j = null; try { j = JSON.parse(t); } catch { /* */ }
  if (r.status >= 300) throw new Error(method + ' ' + p + ' -> ' + r.status + ' ' + t.slice(0, 200));
  return j;
}

let jwt = null;
async function v3headers () {
  if (jwt) return { authorization: 'Bearer ' + jwt };
  await api('POST', '/api/v2/authorization/subjects', { name: 'bf94-aaps', roles: ['admin'] });
  let tok = null;
  for (let i = 0; i < 20 && !tok; i++) {
    const l = await api('GET', '/api/v2/authorization/subjects');
    const s = (l || []).find((x) => x.name === 'bf94-aaps'); tok = s && s.accessToken; if (!tok) await sleep(500);
  }
  for (let i = 0; i < 20 && !jwt; i++) {
    const r = await fetch(BASE + '/api/v2/authorization/request/' + tok); const j = await r.json().catch(() => null);
    jwt = j && j.token; if (!jwt) await sleep(500);
  }
  if (!jwt) throw new Error('no JWT for v3');
  return { authorization: 'Bearer ' + jwt };
}

// ---- client shapes (read from the client sources; see README)
const loopTemp = (t, rate, dur, sid) => ({ eventType: 'Temp Basal', created_at: iso(t), timestamp: iso(t), rate, absolute: rate,
  duration: dur, temp: 'absolute', automatic: true, enteredBy: 'loop://iPhone', syncIdentifier: sid });
const trioTemp = (t, rate, dur, id) => ({ id, eventType: 'Temp Basal', created_at: iso(t), duration: dur, absolute: rate, rate, enteredBy: 'Trio' });
const aapsTemp = (t, rate, dur, identifier, pumpId) => ({ identifier, date: t, utcOffset: 0, app: 'AndroidAPS', device: 'AndroidAPS-DanaRS',
  eventType: 'Temp Basal', isValid: true, rate, absolute: rate, isAbsolute: true, duration: dur, durationInMilliseconds: dur * MIN,
  type: 'NORMAL', pumpId, pumpType: 'DANA_RS', pumpSerial: 'SYNTH0001' });
const orefCancel = (t) => ({ eventType: 'Temp Basal', created_at: iso(t), duration: 0, rate: 0, absolute: 0, temp: 'absolute', enteredBy: 'openaps://medtronic/522' });

// each scenario: setup(T) uploads A; change(T) makes the change; expectNow = U/h a fresh view must show
const SCEN = {
  // Loop: a new temp with a later start; A is not edited
  'loop-new': {
    setup: async (c) => { await api('POST', '/api/v1/treatments', [loopTemp(c.aAt, 2.0, A_LEN, c.sidA)]); },
    change: async (c) => { await api('POST', '/api/v1/treatments', [loopTemp(c.bAt, 0, 30, c.sidB)]); },
    expect: 0
  },
  // Trio: when a temp is finalized shorter it re-uploads it (PumpHistoryStorage isUploadedToNS=false), then the new temp
  'trio-reupload-new': {
    setup: async (c) => { await api('POST', '/api/v1/treatments', [trioTemp(c.aAt, 2.0, A_LEN, c.sidA)]); },
    change: async (c) => { await api('POST', '/api/v1/treatments', [trioTemp(c.aAt, 2.0, A_AGO - 1, c.sidA), trioTemp(c.bAt, 0, 30, c.sidB)]); },
    expect: 0
  },
  // AAPS v3: PATCH A with the shortened duration (nsUpdate), then create B
  'aaps-v3': {
    setup: async (c) => { await api('POST', '/api/v3/treatments', aapsTemp(c.aAt, 2.0, A_LEN, c.sidA, 1001), await v3headers()); },
    change: async (c) => {
      await api('PATCH', '/api/v3/treatments/' + c.sidA, aapsTemp(c.aAt, 2.0, A_AGO - 1, c.sidA, 1001), await v3headers());
      await api('POST', '/api/v3/treatments', aapsTemp(c.bAt, 0, 30, c.sidB, 1002), await v3headers());
    },
    expect: 0
  },
  // Cancel, Trio shape: the finalized (shortened) temp re-uploaded; nothing follows
  'cancel-trio': {
    setup: async (c) => { await api('POST', '/api/v1/treatments', [trioTemp(c.aAt, 2.0, A_LEN, c.sidA)]); },
    change: async (c) => { await api('POST', '/api/v1/treatments', [trioTemp(c.aAt, 2.0, A_AGO - 1, c.sidA)]); },
    expect: 1.0
  },
  // Cancel, AAPS v3 shape: PATCH A shortened; nothing follows
  'cancel-aaps-v3': {
    setup: async (c) => { await api('POST', '/api/v3/treatments', aapsTemp(c.aAt, 2.0, A_LEN, c.sidA, 1001), await v3headers()); },
    change: async (c) => { await api('PATCH', '/api/v3/treatments/' + c.sidA, aapsTemp(c.aAt, 2.0, A_AGO - 1, c.sidA, 1001), await v3headers()); },
    expect: 1.0
  },
  // Cancel, OpenAPS/oref0 shape: a new zero-duration Temp Basal end event
  'cancel-oref': {
    setup: async (c) => { await api('POST', '/api/v1/treatments', [{ ...loopTemp(c.aAt, 2.0, A_LEN), enteredBy: 'openaps://medtronic/522', syncIdentifier: undefined }]); },
    change: async (c) => { await api('POST', '/api/v1/treatments', [orefCancel(c.bAt)]); },
    expect: 1.0
  }
};

function sampleInPage () {
  const c = window.Nightscout && window.Nightscout.client;
  const now = Date.now();
  const em = document.querySelector('span.pill.basal em');
  const pill = em ? em.textContent : null;
  let line = null;
  try {
    const d = document.querySelector('path.basalline').getAttribute('d');
    const nums = (d.match(/-?\d+(\.\d+)?(e-?\d+)?/g) || []).map(Number);
    const X = c.chart.xScaleBasals(new Date(now));
    let y = null;
    for (let i = 0; i + 1 < nums.length; i += 2) { if (nums[i] <= X + 1e-6) y = nums[i + 1]; }
    if (y !== null) line = Math.round(c.chart.yScaleBasals.invert(y) * 1000) / 1000;
  } catch (e) { line = 'err:' + e.message; }
  let fn = null;
  try {
    const tb = c.profilefunctions.getTempBasal(now);
    fn = { total: tb.totalbasal, t: tb.treatment ? { mills: tb.treatment.mills, endmills: tb.treatment.endmills, duration: tb.treatment.duration, absolute: tb.treatment.absolute } : null };
  } catch (e) { fn = 'err:' + e.message; }
  const list = (c.ddata.tempbasalTreatments || []).filter((t) => t.mills > now - 40 * 60000)
    .map((t) => ({ mills: t.mills, duration: t.duration, endmills: t.endmills, absolute: t.absolute }));
  return { now, pill, line, fn, list, lastUpdated: c.dataLastUpdated || 0, updates: (window.__bf94 || []).length };
}
const num = (s) => { const m = s && String(s).match(/(\d+(\.\d+)?)U/); return m ? Number(m[1]) : null; };

async function main () {
  const sc = SCEN[SC]; if (!sc) { console.error('unknown scenario ' + SC); process.exit(2); }
  const mc = new MongoClient(MONGO); await mc.connect(); await mc.db(DB).dropDatabase();  // before the server starts
  const env = { PATH: process.env.PATH, HOME: process.env.HOME, N_PREFIX: process.env.N_PREFIX || '',
    MONGODB_URI: MONGO + '/' + DB, API_SECRET: SECRET, PORT: String(PORT), HOSTNAME: '127.0.0.1', INSECURE_USE_HTTP: 'true',
    ENABLE: 'careportal basal iob cob pump devicestatus profile', SHOW_PLUGINS: 'basal', BASAL_RENDER: 'default',
    DISPLAY_UNITS: 'mg/dl', AUTH_DEFAULT_ROLES: 'readable', TZ: 'UTC' };
  const logf = OUT.replace(/\.json$/, '.server.log');
  const srv = spawn('n', ['exec', NODE_VER, 'node', 'lib/server/server.js'], { cwd: DIR, env, detached: true,
    stdio: ['ignore', fs.openSync(logf, 'w'), fs.openSync(logf, 'a')] });
  const stop = () => { try { process.kill(-srv.pid, 'SIGTERM'); } catch { /* */ } };
  process.on('exit', stop);
  let up = false;
  for (let i = 0; i < 120 && !up; i++) { try { up = (await fetch(BASE + '/api/v1/status.json')).ok; } catch { /* */ } if (!up) await sleep(500); }
  if (!up) { console.error('server did not start; see ' + logf); process.exit(2); }

  const t0 = Date.now();
  const c = { aAt: t0 - A_AGO * MIN + 30000, sidA: uuid(), sidB: uuid() };
  // profile, readings, optional history
  await api('POST', '/api/v1/profile', { defaultProfile: 'Default', startDate: '2026-01-01T00:00:00.000Z', mills: 0, units: 'mg/dl',
    store: { Default: { dia: 4, carbratio: [{ time: '00:00', value: 10, timeAsSeconds: 0 }], sens: [{ time: '00:00', value: 50, timeAsSeconds: 0 }],
      basal: [{ time: '00:00', value: 1.0, timeAsSeconds: 0 }], target_low: [{ time: '00:00', value: 100, timeAsSeconds: 0 }],
      target_high: [{ time: '00:00', value: 120, timeAsSeconds: 0 }], units: 'mg/dl', timezone: 'UTC', carbs_hr: 20, delay: 20 } } });
  const sgvs = []; for (let k = 36; k >= 0; k--) { const t = t0 - k * 5 * MIN; sgvs.push({ type: 'sgv', sgv: 120, direction: 'Flat', date: t, dateString: iso(t), device: 'synthetic://bf94' }); }
  await api('POST', '/api/v1/entries', sgvs);
  if (HIST) {
    const h = []; for (let t = t0 - 180 * MIN; t < c.aAt - 10 * MIN; t += 10 * MIN) h.push(loopTemp(t, (h.length % 2) ? 1.5 : 0.5, 10, uuid()));
    await api('POST', '/api/v1/treatments', h);
  }
  await sc.setup(c);

  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, timezoneId: 'UTC' });
  const page = await ctx.newPage();
  const pageErrors = []; page.on('pageerror', (e) => pageErrors.push(String(e)));
  await page.goto(BASE + '/');
  try {
    await page.waitForFunction(() => { const e = document.querySelector('span.pill.basal em'); return e && /T: 2\.000U/.test(e.textContent); }, null, { timeout: 90000 });
  } catch (e) {
    const s0 = await page.evaluate(sampleInPage).catch((x) => String(x));
    if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${LABEL}-${SC}${HIST ? '-h' : ''}-setup-timeout.png`) }).catch(() => {});
    console.error('setup: page never showed temp A: ' + JSON.stringify(s0).slice(0, 1500)); process.exit(2);
  }
  await page.evaluate(() => { window.__bf94 = []; window.Nightscout.client.socket.on('dataUpdate', (d) => window.__bf94.push({ t: Date.now(), delta: d.delta, tr: (d.treatments || []).map((x) => ({ a: x.action || 'new', dur: x.duration, mills: x.mills })) })); });
  const before = await page.evaluate(sampleInPage);
  const lu0 = before.lastUpdated;
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${LABEL}-${SC}${HIST ? '-h' : ''}-0-before.png`) });

  c.bAt = Date.now() - 1 * MIN;
  const tChange = Date.now();
  await sc.change(c);
  // stored truth from MongoDB
  const stored = (await mc.db(DB).collection('treatments').find({ eventType: 'Temp Basal', created_at: { $gte: iso(c.aAt - 1000) } }).toArray())
    .map((t) => ({ created_at: t.created_at, duration: t.duration, absolute: t.absolute }));

  const samples = [];
  let shotAt = null;
  const end = tChange + WATCH * 1000;
  while (Date.now() < end) {
    const s = await page.evaluate(sampleInPage); s.dt = Math.round((s.now - tChange) / 1000); s.arrived = s.lastUpdated > lu0 && s.lastUpdated >= tChange; samples.push(s);
    if (SHOTS && shotAt === null && s.arrived && s.dt >= 8) { shotAt = s.dt; await page.screenshot({ path: path.join(SHOTS, `${LABEL}-${SC}${HIST ? '-h' : ''}-1-live.png`) }); }
    await sleep(2000);
  }
  const updates = await page.evaluate(() => window.__bf94);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${LABEL}-${SC}${HIST ? '-h' : ''}-2-live-end.png`) });

  // control: a fresh page, new context, same final data
  const ctx2 = await browser.newContext({ viewport: { width: 1280, height: 800 }, timezoneId: 'UTC' });
  const p2 = await ctx2.newPage(); await p2.goto(BASE + '/');
  await p2.waitForFunction(() => { const e = document.querySelector('span.pill.basal em'); return e && /U/.test(e.textContent); }, null, { timeout: 60000 });
  await sleep(3000);
  const fresh = await p2.evaluate(sampleInPage);
  if (SHOTS) await p2.screenshot({ path: path.join(SHOTS, `${LABEL}-${SC}${HIST ? '-h' : ''}-3-fresh.png`) });
  // the open page after a reload
  await page.reload();
  await page.waitForFunction(() => { const e = document.querySelector('span.pill.basal em'); return e && /U/.test(e.textContent); }, null, { timeout: 60000 });
  await sleep(3000);
  const reloaded = await page.evaluate(sampleInPage);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${LABEL}-${SC}${HIST ? '-h' : ''}-4-reloaded.png`) });
  await browser.close();

  const first = samples.find((s) => s.arrived);
  const live = samples.filter((s) => first && s.now >= first.now);   // every sample from the one that first saw the update
  const stalePill = live.filter((s) => Math.abs(num(s.pill) - sc.expect) > 0.001);
  const staleLine = live.filter((s) => typeof s.line === 'number' && Math.abs(s.line - sc.expect) > 0.001);
  const staleFn = live.filter((s) => s.fn && Math.abs(s.fn.total - sc.expect) > 0.001);
  const res = {
    label: LABEL, scenario: SC, hist: HIST, db: DB, a: { at: iso(c.aAt), len: A_LEN }, change_at: iso(tChange), b_at: c.bAt && iso(c.bAt), expect: sc.expect, stored,
    before: { pill: before.pill, line: before.line, fn: before.fn && before.fn.total },
    update_arrived_s: first ? first.dt : null, updates,
    live_samples: live.length,
    live_pill_values: [...new Set(live.map((s) => s.pill))], live_line_values: [...new Set(live.map((s) => s.line))],
    live_fn_values: [...new Set(live.map((s) => s.fn && s.fn.total))],
    stale_pill_samples: stalePill.length, stale_line_samples: staleLine.length, stale_fn_samples: staleFn.length,
    stale_pill_last_dt: stalePill.length ? stalePill[stalePill.length - 1].dt : null,
    live_last: live.length ? live[live.length - 1] : null,
    fresh: { pill: fresh.pill, line: fresh.line, fn: fresh.fn && fresh.fn.total },
    reloaded: { pill: reloaded.pill, line: reloaded.line, fn: reloaded.fn && reloaded.fn.total },
    pageErrors, samples
  };
  res.verdict = !first ? 'NO-UPDATE' : (stalePill.length || staleLine.length || staleFn.length) ? 'STALE' : 'CORRECT';
  fs.writeFileSync(OUT, JSON.stringify(res, null, 1));
  console.log(JSON.stringify({ label: LABEL, sc: SC, hist: HIST, verdict: res.verdict, before: res.before, arrived: res.update_arrived_s,
    pill: res.live_pill_values, line: res.live_line_values, fn: res.live_fn_values, stalePill: stalePill.length + '/' + live.length,
    staleLastDt: res.stale_pill_last_dt, fresh: res.fresh, reloaded: res.reloaded, stored, errs: pageErrors.length }));
  await mc.close(); stop(); process.exit(0);
}
main().catch((e) => { console.error(e); process.exit(2); });
