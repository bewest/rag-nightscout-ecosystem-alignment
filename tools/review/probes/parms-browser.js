#!/usr/bin/env node
'use strict';
/*
 * parms-browser.js — P0-I / bf/parms (#8736), register BF-37 (and BF-39).
 *
 * BF-37. `queryParms()` in lib/client/browser-utils.js reads `[1]` of each
 * `key=value` split without checking one exists, so a valueless parameter —
 * `?debug`, a trailing `&`, `&&`, a lone `?` — throws. It is the FIRST
 * statement of `client.init`, so nothing after it runs: the page stops with
 * the loading message and no chart. Total, silent, and reachable from a URL
 * anyone can paste.
 *
 * MEASURED 2026-09-17, dev mode, identical seed, SAME TOKEN on both:
 *
 *   url                          BASE a8888f0d        bf/parms eb0bc918
 *   ---------------------------  -------------------  ------------------
 *   ?token=..                    chart renders        chart renders
 *   ?token=..&debug              NO CHART + throws    chart renders
 *   ?token=..&a=1&&b=2           NO CHART + throws    chart renders
 *   ?token=..&mute=true&debug    NO CHART + throws    chart renders
 *
 * TWO READOUTS THAT LOOK RIGHT AND ARE NOT, both hit while building this:
 *
 *  - `#loadingMessageText` visibility is TRUE in every cell above, including
 *    the ones that render a chart. It is not a proxy for "the page loaded".
 *    The presence of an SVG in #chartContainer is.
 *  - Without a token the page stops at the loading message on BOTH builds,
 *    for an auth reason that has nothing to do with the defect. An earlier
 *    run compared unauthenticated URLs and every cell was identically broken.
 *    The token is held constant so the parameter is the only variable.
 *
 * Page errors are NOT used as the primary signal here: a plain authenticated
 * load already emits a benign autoplay warning ("play() failed because the
 * user didn't interact"), so an arm counting page errors would be red on BASE
 * for the wrong reason. The chart is the measurement; the throw is corroboration.
 */

const path = require('path');
const crypto = require('crypto');
const { report } = require(path.resolve(__dirname, '..', '..', 'queue', 'gates', '_gate.js'));

function resolvePlaywright() {
  const root = process.env.NSREVIEW_ROOT || '';
  for (const c of [process.env.NSREVIEW_PLAYWRIGHT,
                   path.join(root, 'node_modules', 'playwright-core'),
                   path.join(root, 'deps', 'node_modules', 'playwright-core'),
                   'playwright-core'].filter(Boolean)) {
    try { require.resolve(c); return c; } catch { /* next */ }
  }
  console.error('playwright-core not found'); process.exit(2);
}
const PW = resolvePlaywright();

// '' is the control: a plain authenticated load, which must render on BOTH.
const CASES = ['', '&debug', '&a=1&&b=2', '&mute=true&debug', '&'];

async function mintToken(url, secret) {
  const sha1 = crypto.createHash('sha1').update(secret).digest('hex');
  const h = { 'api-secret': sha1, 'content-type': 'application/json' };
  await fetch(`${url}/api/v2/authorization/subjects`,
    { method: 'POST', headers: h, body: JSON.stringify({ name: 'reviewer', roles: ['admin'] }) })
    .catch(() => {});
  const subs = await (await fetch(`${url}/api/v2/authorization/subjects`, { headers: h })).json();
  const t = (subs.find(s => s.name === 'reviewer') || {}).accessToken;
  if (!t) throw new Error('could not mint a token');
  return t;
}

async function measure(url, secret) {
  const { chromium } = require(PW);
  const token = await mintToken(url, secret);
  const browser = await chromium.launch({ channel: 'chrome', args: ['--no-sandbox'] });
  const out = {};
  for (const q of CASES) {
    const page = await (await browser.newContext()).newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(String(e.message)));
    await page.goto(`${url}/?token=${token}${q}`,
      { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
    // the chart is drawn after the first data tick; give it room
    await page.waitForFunction(
      () => document.querySelectorAll('#chartContainer svg').length > 0,
      { timeout: 15000 }).catch(() => {});
    out[q || '(plain)'] = await page.evaluate(() => ({
      chartSvg: document.querySelectorAll('#chartContainer svg').length,
    })).then(r => ({ ...r, errors: errors.filter(e => !/play\(\) failed/.test(e)) }));
    await page.close();
  }
  await browser.close();
  return out;
}

(async () => {
  const a = process.argv.slice(2);
  const g = k => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : null; };
  const baseUrl = g('--base'), candUrl = g('--candidate'), secret = g('--secret');
  if (!baseUrl || !candUrl || !secret) { console.error('need --base --candidate --secret'); process.exit(2); }

  const base = await measure(baseUrl, secret);
  const cand = await measure(candUrl, secret);
  const findings = [];

  for (const q of CASES) {
    const k = q || '(plain)';
    const b = base[k], c = cand[k];
    const kind = q === '' ? 'invariant' : 'discriminates';
    findings.push({
      ok: c.chartSvg > 0,
      text: `[${kind}] "${k}": CANDIDATE chartSvg=${c.chartSvg}` +
            (c.errors.length ? ` errors=${c.errors.length} (${c.errors[0].slice(0, 46)})` : ''),
    });
    findings.push({
      ok: true,
      text: `[${kind}] "${k}": CONTROL   BASE chartSvg=${b.chartSvg}` +
            (b.errors.length ? ` errors=${b.errors.length} (${b.errors[0].slice(0, 46)})` : '') +
            ` — ${b.chartSvg > 0 ? 'GREEN' : 'RED (page never rendered)'}`,
    });
    if (kind === 'discriminates' && b.chartSvg > 0) {
      findings.push({ ok: false, text: `[${kind}] "${k}": UNINFORMATIVE — BASE rendered too` });
    }
    if (kind === 'invariant' && b.chartSvg === 0) {
      findings.push({ ok: false, text: `[${kind}] "${k}": UNATTRIBUTABLE — BASE cannot render even a plain URL, so nothing here is about this branch` });
    }
  }
  report('parms (bf/parms #8736, BF-37) — browser', findings);
})().catch(e => { console.error('parms probe failed:', e.message); process.exit(2); });
