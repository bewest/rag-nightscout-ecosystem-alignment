#!/usr/bin/env node
'use strict';
/*
 * brush-extent/probe.js — BF-168 in a real browser: can the context chart's window be dragged
 * back to now?
 *
 * Boots one cgm-remote-monitor tree on a fresh database, seeds a profile and 48 h of synthetic
 * CGM readings, opens the main page in Chromium (Playwright), records the brush's drag limit
 * (d3-brush's stored extent) against the context chart's width, then: taps the middle of the
 * context chart (the page goes back in time), drags the window to the right edge, drags again
 * from near the edge, and taps inside the right edge. After each step it records whether the
 * page is in retro mode, the brush selection, and how far its right end is from now.
 *
 * Usage: node probe.js <crm tree> <label> <port> <mongodb url> <outdir> [mode]
 *   mode: touch (phone landscape, 800x380, touch events) or mouse (1280x800), with suffixes:
 *     -force   the race, forced: every <svg> reports the browser default 300x150 for 6 s after
 *              load, as an <svg> does before the page lays out
 *     -rotate  load in portrait (touch) or 640 wide (mouse), then resize to the mode's viewport
 *     -widen   same as -rotate, the name used for mouse
 * Needs NODE_PATH (or a local node_modules) with playwright; CHROMIUM_PATH overrides the browser.
 * The server runs under `n exec 22.23.2`. Waits 5 s after seeding so the page does not hit
 * BF-159 (the Profile Editor redirect while a profile exists).
 * Synthetic data only. Exit 0 ran (results in <outdir>/<label>-<mode>.json), 2 could not run.
 */
const path = require('path'), fs = require('fs'), { spawn } = require('child_process');
const [DIR, LABEL, PORT, MONGO, OUT, MODE0 = 'touch'] = process.argv.slice(2);
const FORCE = /-force/.test(MODE0), ROTATE = /-(rotate|widen)/.test(MODE0), MODE = MODE0.replace(/-(rotate|widen|force)/g,'');
const { chromium } = require('playwright');
const { MongoClient } = require(path.join(DIR, 'node_modules', 'mongodb'));
const SECRET = 'brushlab-secret-0001', DB = 'brush_' + LABEL.replace(/\W/g, '');
const BASE = `http://127.0.0.1:${PORT}`, MIN = 60000, sleep = (ms) => new Promise(r => setTimeout(r, ms));
const sha1 = require('crypto').createHash('sha1').update(SECRET).digest('hex');
const api = (m, p, b) => fetch(BASE + p, { method: m, headers: { 'api-secret': sha1, 'content-type': 'application/json' }, body: JSON.stringify(b) });
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const mc = new MongoClient(MONGO); await mc.connect(); await mc.db(DB).dropDatabase(); await mc.close();
  const env = { PATH: process.env.PATH, HOME: process.env.HOME, N_PREFIX: process.env.N_PREFIX || '', MONGODB_URI: MONGO + '/' + DB, API_SECRET: SECRET, PORT, HOSTNAME: '127.0.0.1',
    INSECURE_USE_HTTP: 'true', ENABLE: 'careportal basal iob cob', DISPLAY_UNITS: 'mg/dl', AUTH_DEFAULT_ROLES: 'readable', TZ: 'UTC' };
  const logf = path.join(OUT, LABEL + '-' + MODE0 + '.server.log');
  const srv = spawn('n', ['exec', '22.23.2', 'node', 'lib/server/server.js'], { cwd: DIR, env, detached: true, stdio: ['ignore', fs.openSync(logf, 'w'), fs.openSync(logf, 'a')] });
  process.on('exit', () => { try { process.kill(-srv.pid, 'SIGTERM'); } catch {} });
  let up = false; for (let i = 0; i < 120 && !up; i++) { try { up = (await fetch(BASE + '/api/v1/status.json')).ok; } catch {} if (!up) await sleep(500); }
  if (!up) { console.error('no server'); process.exit(2); }
  const t0 = Date.now(), sgvs = [];
  for (let k = 48 * 12; k >= 0; k--) { const t = t0 - k * 5 * MIN; sgvs.push({ type: 'sgv', sgv: Math.round(120 + 40 * Math.sin(k / 20)), direction: 'Flat', date: t, dateString: new Date(t).toISOString(), device: 'synthetic://brushlab' }); }
  await api('POST', '/api/v1/profile', { defaultProfile: 'Default', startDate: '2026-01-01T00:00:00.000Z', mills: 0, units: 'mg/dl',
    store: { Default: { dia: 4, carbratio: [{ time: '00:00', value: 10, timeAsSeconds: 0 }], sens: [{ time: '00:00', value: 50, timeAsSeconds: 0 }],
      basal: [{ time: '00:00', value: 1.0, timeAsSeconds: 0 }], target_low: [{ time: '00:00', value: 100, timeAsSeconds: 0 }],
      target_high: [{ time: '00:00', value: 120, timeAsSeconds: 0 }], units: 'mg/dl', timezone: 'UTC', carbs_hr: 20, delay: 20 } } });
  await api('POST', '/api/v1/entries', sgvs);
  await sleep(5000);
  const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
  const touch = MODE === 'touch';
  const ctx = await browser.newContext({ viewport: touch ? (ROTATE ? { width: 380, height: 800 } : { width: 800, height: 380 }) : (ROTATE ? { width: 640, height: 800 } : { width: 1280, height: 800 }), hasTouch: touch, isMobile: touch, deviceScaleFactor: touch ? 2.6 : 1, timezoneId: 'UTC' });
  if (FORCE) await ctx.addInitScript(() => {
    // the race, forced: the <svg> reports the browser default 300x150 until 6 s after load
    const until = Date.now() + 6000, d = Object.getOwnPropertyDescriptor(SVGSVGElement.prototype, 'width'), h = Object.getOwnPropertyDescriptor(SVGSVGElement.prototype, 'height');
    Object.defineProperty(SVGSVGElement.prototype, 'width', { configurable: true, get () { return Date.now() < until ? { baseVal: { value: 300 } } : d.get.call(this); } });
    Object.defineProperty(SVGSVGElement.prototype, 'height', { configurable: true, get () { return Date.now() < until ? { baseVal: { value: 150 } } : h.get.call(this); } });
  });
  const page = await ctx.newPage(); const errs = []; page.on('pageerror', e => errs.push(String(e)));
  await page.goto(BASE + '/');
  try { await page.waitForFunction(() => document.querySelector('.x.brush .overlay') && window.Nightscout.client.entries && window.Nightscout.client.entries.length > 200, null, { timeout: 60000 }); } catch (e) { console.log(await page.evaluate(() => ({ ov: !!document.querySelector('.x.brush .overlay'), n: window.Nightscout && window.Nightscout.client && (window.Nightscout.client.entries||[]).length, title: document.title }))); console.log(errs); process.exit(2); }
  await sleep(FORCE ? 7000 : 3000);
  const atLoad = await page.evaluate(() => ({ extent: window.Nightscout.client.chart.theBrush.node().__brush.extent, svgW: document.querySelector('#chartContainer svg').getBoundingClientRect().width, range: window.Nightscout.client.chart.xScale2.range() }));
  if (ROTATE) { await page.setViewportSize(touch ? { width: 800, height: 380 } : { width: 1280, height: 800 }); await sleep(3000); }
  const state = () => page.evaluate(() => {
    const c = window.Nightscout.client, ch = c.chart;
    const br = ch.theBrush.node(); const s = br.__brush && br.__brush.selection;
    const xs = ch.xScale.domain().map(d => +d), r2 = ch.xScale2.range(), d2 = ch.xScale2.domain().map(d => +d);
    return { retro: ch.inRetroMode(), brushSel: s ? [s[0][0], s[1][0]] : null, x2range: r2, x2domainEndMinAgo: (Date.now() - d2[1]) / 60000,
      focusEndMinFromNow: (xs[1] - Date.now()) / 60000, brushEndTime: s ? (Date.now() - +ch.xScale2.invert(s[1][0])) / 60000 : null,
      bodyRetro: document.body.classList.contains('retro') || !!document.querySelector('.container.retro, #container.retro') };
  });
  const box = await page.evaluate(() => { const r = document.querySelector('.x.brush .overlay').getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
  const res = { label: LABEL, mode: MODE0, atLoad, extent: await page.evaluate(() => window.Nightscout.client.chart.theBrush.node().__brush.extent), svgW: await page.evaluate(() => document.querySelector('#chartContainer svg').getBoundingClientRect().width), box, steps: [] };
  res.steps.push({ step: 'initial', ...(await state()) });
  await page.screenshot({ path: path.join(OUT, `${LABEL}-${MODE0}-0-initial.png`) });
  const y = box.y + box.h / 2, xMid = box.x + box.w * 0.5;
  const cdp = await ctx.newCDPSession(page);
  const tap = async (x) => { if (touch) { await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] }); await sleep(60); await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] }); } else { await page.mouse.click(x, y); } await sleep(800); };
  const drag = async (x0, x1, n = 25) => {
    if (touch) { await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: x0, y }] });
      for (let i = 1; i <= n; i++) { await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x0 + (x1 - x0) * i / n, y }] }); await sleep(30); }
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    } else { await page.mouse.move(x0, y); await page.mouse.down(); for (let i = 1; i <= n; i++) { await page.mouse.move(x0 + (x1 - x0) * i / n, y); await sleep(30); } await page.mouse.up(); }
    await sleep(800);
  };
  await tap(xMid); res.steps.push({ step: 'tap middle', ...(await state()) });
  await page.screenshot({ path: path.join(OUT, `${LABEL}-${MODE0}-1-tapmid.png`) });
  // drag from the middle to the right edge of the context chart, then again from near the edge
  await drag(xMid, box.x + box.w - 2); res.steps.push({ step: 'drag middle -> right edge', ...(await state()) });
  await page.screenshot({ path: path.join(OUT, `${LABEL}-${MODE0}-2-dragright.png`) });
  await drag(box.x + box.w - 30, box.x + box.w - 1); res.steps.push({ step: 'drag near edge -> right edge', ...(await state()) });
  await page.screenshot({ path: path.join(OUT, `${LABEL}-${MODE0}-3-drag2.png`) });
  await tap(box.x + box.w - 3); res.steps.push({ step: 'tap inside right edge', ...(await state()) });
  await page.screenshot({ path: path.join(OUT, `${LABEL}-${MODE0}-4-tapright.png`) });
  res.errors = errs;
  fs.writeFileSync(path.join(OUT, `${LABEL}-${MODE0}.json`), JSON.stringify(res, null, 1));
  console.log(JSON.stringify(res, null, 1));
  await browser.close(); process.exit(0);
})().catch(e => { console.error(e); process.exit(2); });
