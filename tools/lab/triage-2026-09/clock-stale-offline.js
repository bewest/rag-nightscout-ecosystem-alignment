'use strict';
/*
 * Issue #7036 probe: does the clock view keep showing an old reading as fresh
 * when its data fetch starts failing?
 *
 * Usage: node tools/lab/triage-2026-09/clock-stale-offline.js <cgm-remote-monitor tree with node_modules>
 *
 * Runs the shipping lib/client/clock-client.js in the tree's own jsdom test
 * fixture (tests/fixtures/benv-loader). client.init() is called for real, with
 * setInterval and Date.now replaced by a manual clock, so the page's own
 * 20-second fetch timer and 1-second time-of-day timer are what fire (Date is
 * replaced too, so `new Date()` follows the manual clock). $.ajax
 * is stubbed. Face "cy13-sg40-ag6": colour background, always show the age
 * text, stale after 13 minutes.
 *
 * At t0 one fetch succeeds with a reading taken at t0. Then 30 minutes pass.
 * Arms:
 *   offline   every later fetch fails (the error callback, as a dropped
 *             network gives). The defect: after 30 minutes the age text still
 *             says "Just now" and the value has no "stale" class.
 * Control:
 *   online    every later fetch succeeds with the SAME t0 reading. After 30
 *             minutes the age text must say "30 minutes ago" and the value
 *             must carry "stale". This shows the harness drives the timers and
 *             that the render computes age when it is called.
 * Liveness: the probe also checks that the fetch timer fired (about 90 calls)
 * and that the time-of-day text moved, in the same run.
 *
 * Exit status: 0 when the offline arm shows the age and stale state updated
 * (fixed), 1 when it still shows the reading as fresh (defect present), 2 when
 * the control or a liveness check misbehaves (the probe measures nothing).
 * No network; nothing is written.
 */
const path = require('path');
const root = path.resolve(process.argv[2] || '.');
const benv = require(path.join(root, 'tests/fixtures/benv-loader'));

const T0 = Date.parse('2026-09-24T12:00:00Z');

function run (mode) {
  return new Promise(function (resolve) {
    benv.setup(function () {
      const $ = require(path.join(root, 'node_modules/jquery'));
      global.$ = $;
      global.localStorage = { getItem: function () { return null; } };
      $('body').html('<div id="inner" data-face="cy13-sg40-ag6-tm10"></div>');
      window.serverSettings = { settings: { units: 'mg/dl', showClockDelta: true, showClockLastTime: true, timeFormat: 24,
        thresholds: { bgHigh: 260, bgLow: 55, bgTargetBottom: 80, bgTargetTop: 180 } } };

      let now = T0;
      const RealDate = Date;
      global.Date = class FakeDate extends RealDate {
        constructor (...a) { if (a.length) { super(...a); } else { super(now); } }
        static now () { return now; }
      };
      const timers = [];
      const realSetInterval = global.setInterval;
      global.setInterval = function (fn, ms) { timers.push({ fn: fn, ms: ms, next: now + ms }); return timers.length; };

      const reading = { bgnow: { sgvs: [{ mgdl: 120, scaled: 120, mills: T0, direction: 'Flat' }] }, delta: { mgdl: 0, display: '+0' } };
      let calls = 0;
      let failing = false;
      $.ajax = function (url, opts) {
        calls++;
        if (failing) { opts.error({ status: 0, statusText: 'error' }); } else { opts.success(reading); }
      };

      const clockPath = path.join(root, 'lib/client/clock-client');
      Object.keys(require.cache).forEach(function (k) { if (k.indexOf(path.join(root, 'lib')) === 0) delete require.cache[k]; });
      const client = require(clockPath);
      const origErr = console.error; console.error = function () {};
      let initErr = null;
      try { client.init(); } catch (e) { initErr = e; }
      const after0 = { tm: $('.tm').text(), ag: $('.ag').text(), stale: $('.sg').hasClass('stale'), sg: $('.sg').text() };

      failing = (mode === 'offline');
      const end = T0 + 30 * 60 * 1000;
      while (true) {
        timers.sort(function (a, b) { return a.next - b.next; });
        const t = timers[0];
        if (!t || t.next > end) break;
        now = t.next; t.next += t.ms;
        try { t.fn(); } catch (e) { initErr = initErr || e; }
      }
      now = end;
      console.error = origErr;
      const out = { mode: mode, initErr: initErr && String(initErr), calls: calls, timers: timers.map(function (t) { return t.ms; }),
        t0: after0, t30: { tm: $('.tm').text(), ag: $('.ag').text(), stale: $('.sg').hasClass('stale'), sg: $('.sg').text(), bg: $('body').css('background-color') } };

      global.setInterval = realSetInterval;
      global.Date = RealDate;
      delete global.$; delete global.localStorage;
      benv.teardown(true);
      resolve(out);
    }, { url: 'http://localhost/clock/clock-color' });
  });
}

(async function main () {
  const online = await run('online');
  const offline = await run('offline');
  for (const r of [online, offline]) console.log(JSON.stringify(r));

  let broken = false;
  for (const r of [online, offline]) {
    if (r.initErr) { console.log(r.mode + ': harness error ' + r.initErr); broken = true; }
    if (r.calls < 80) { console.log(r.mode + ': fetch timer did not fire (' + r.calls + ' calls)'); broken = true; }
    if (!r.t0.tm || r.t0.tm === r.t30.tm) { console.log(r.mode + ': time-of-day text did not move'); broken = true; }
    if (r.t0.ag !== 'Just now' || r.t0.stale || r.t0.sg !== '120') { console.log(r.mode + ': first render wrong'); broken = true; }
  }
  if (!(online.t30.ag === '30 minutes ago' && online.t30.stale)) { console.log('control online: age not updated by a successful fetch'); broken = true; }
  if (broken) { console.log('the probe measures nothing'); process.exit(2); }

  console.log('control online after 30 min: age "' + online.t30.ag + '", stale ' + online.t30.stale);
  console.log('arm offline after 30 min: age "' + offline.t30.ag + '", stale ' + offline.t30.stale + ', value ' + offline.t30.sg);
  if (offline.t30.ag === 'Just now' && !offline.t30.stale) { console.log('DEFECT: 30-minute-old reading still shown as fresh'); process.exit(1); }
  console.log('offline arm shows the reading as old');
  process.exit(0);
})();
