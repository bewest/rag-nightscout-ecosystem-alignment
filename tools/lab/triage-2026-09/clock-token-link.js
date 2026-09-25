'use strict';
/*
 * Issue #7377 probe: is a clock view blank when it is opened from the main
 * page's Clock menu on a site the viewer reached with ?token=... ?
 *
 * Usage:
 *   node tools/lab/triage-2026-09/clock-token-link.js <cgm-remote-monitor tree with node_modules>
 *        [--base http://127.0.0.1:PORT --token-file <file holding a readable token>]
 *
 * Client arms (always run, in the tree's own jsdom fixture, tests/fixtures/benv-loader):
 *   The page URL is taken from the tree's views/index.html Clock menu link
 *   (id clockcolorlink), which is where a viewer on /?token=... is sent.
 *   $.ajax is stubbed as a site with AUTH_DEFAULT_ROLES=denied: a data fetch
 *   succeeds only when its URL carries the token, and otherwise gets the error
 *   callback with status 401. client.init() runs for real. localStorage holds
 *   no API secret (a token viewer has none).
 *   menu      page at the menu link. The defect: no value is ever drawn.
 * Control:
 *   direct    page at the same link with ?token=<token> appended by hand. A
 *             value must be drawn, so the harness can render at all.
 *
 * Server arm (only with --base): against a booted server started with
 * AUTH_DEFAULT_ROLES=denied, checks that GET /clock/clock-color is 200 (the page
 * shell is served), that /api/v1/status.js and /api/v2/properties answer 401
 * without a token (what the menu-opened page asks for), and 200 with it
 * (liveness and control in the same run). The token is read from the file and
 * never printed.
 *
 * Exit status: 0 when the menu-opened page draws a value (fixed), 1 when it is
 * blank (defect present), 2 when the control, the link lookup or the server
 * arm misbehaves (the probe measures nothing).
 */
const fs = require('fs');
const path = require('path');
const http = require('http');
const argv = process.argv.slice(2);
const root = path.resolve(argv[0] || '.');
function opt (name) { const i = argv.indexOf(name); return i > 0 ? argv[i + 1] : null; }
const benv = require(path.join(root, 'tests/fixtures/benv-loader'));

const TOKEN = 'probe-token-0123456789abcdef';
const index = fs.readFileSync(path.join(root, 'views/index.html'), 'utf8');
const m = index.match(/id="clockcolorlink"\s+href="([^"]+)"/);
if (!m) { console.log('Clock menu link not found in views/index.html'); process.exit(2); }
const menuHref = m[1];

function run (label, pageUrl) {
  return new Promise(function (resolve) {
    benv.setup(function () {
      const $ = require(path.join(root, 'node_modules/jquery'));
      global.$ = $;
      global.localStorage = { getItem: function () { return null; } };
      $('body').html('<div id="inner" data-face="cy13-sg40-ag6"></div>');
      window.serverSettings = { settings: { units: 'mg/dl', showClockDelta: true, showClockLastTime: true,
        thresholds: { bgHigh: 260, bgLow: 55, bgTargetBottom: 80, bgTargetTop: 180 } } };
      const realSetInterval = global.setInterval;
      global.setInterval = function () { return 0; };
      const asked = [];
      $.ajax = function (url, opts) {
        asked.push(url.indexOf('token=' + TOKEN) >= 0 ? 'with-token' : 'no-token');
        if (url.indexOf('token=' + TOKEN) >= 0) {
          opts.success({ bgnow: { sgvs: [{ mgdl: 120, scaled: 120, mills: Date.now(), direction: 'Flat' }] }, delta: { mgdl: 0, display: '+0' } });
        } else {
          opts.error({ status: 401, statusText: 'Unauthorized' });
        }
      };
      Object.keys(require.cache).forEach(function (k) { if (k.indexOf(path.join(root, 'lib')) === 0) delete require.cache[k]; });
      const client = require(path.join(root, 'lib/client/clock-client'));
      const origErr = console.error; console.error = function () {};
      let err = null;
      try { client.init(); } catch (e) { err = String(e); }
      console.error = origErr;
      const out = { arm: label, url: pageUrl.replace(TOKEN, '<token>'), asked: asked, err: err, sg: $('.sg').text(), children: $('#inner').children().length };
      global.setInterval = realSetInterval;
      delete global.$; delete global.localStorage;
      benv.teardown(true);
      resolve(out);
    }, { url: 'http://localhost' + pageUrl });
  });
}

function get (base, p) {
  return new Promise(function (resolve) {
    http.get(base + p, function (res) { res.resume(); resolve(res.statusCode); }).on('error', function (e) { resolve('ERR ' + e.code); });
  });
}

(async function main () {
  const menu = await run('menu', menuHref);
  const direct = await run('direct', menuHref + (menuHref.indexOf('?') >= 0 ? '&' : '?') + 'token=' + TOKEN);
  console.log(JSON.stringify(menu)); console.log(JSON.stringify(direct));
  let broken = false;
  if (direct.err || direct.sg !== '120') { console.log('control direct: no value drawn; the harness cannot render'); broken = true; }
  if (menu.err) { console.log('menu arm: harness error ' + menu.err); broken = true; }

  const base = opt('--base');
  if (base) {
    const tokenFile = opt('--token-file');
    const tok = tokenFile ? fs.readFileSync(tokenFile, 'utf8').trim() : '';
    if (!tok) { console.log('--base needs --token-file'); process.exit(2); }
    const r = {
      page: await get(base, menuHref),
      statusNoToken: await get(base, '/api/v1/status.js'),
      propsNoToken: await get(base, '/api/v2/properties'),
      statusToken: await get(base, '/api/v1/status.js?token=' + encodeURIComponent(tok)),
      propsToken: await get(base, '/api/v2/properties?token=' + encodeURIComponent(tok)),
    };
    console.log('server ' + JSON.stringify(r));
    if (r.page !== 200 || r.statusToken !== 200 || r.propsToken !== 200) { console.log('server arm: not live, or the token does not read'); broken = true; }
    if (r.statusNoToken !== 401 || r.propsNoToken !== 401) { console.log('server arm: site is not denying anonymous reads; the precondition is absent'); broken = true; }
  }
  if (broken) { console.log('the probe measures nothing'); process.exit(2); }
  if (menu.sg === '') { console.log('DEFECT: the clock opened from the menu (' + menuHref + ') draws nothing; its fetches carried no token'); process.exit(1); }
  console.log('menu-opened clock draws a value');
  process.exit(0);
})();
