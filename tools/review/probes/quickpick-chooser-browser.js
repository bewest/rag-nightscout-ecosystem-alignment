#!/usr/bin/env node
'use strict';
/*
 * quickpick-chooser-browser.js — BF-69.
 *
 * The Bolus Wizard's quick-pick chooser is built exactly once, at client
 * construction, from an empty sandbox, and is never rebuilt:
 *
 *   index.js:239  client.sbx = sandbox.clientInit(...)     // EMPTY
 *   index.js:323  client.boluscalc = require('./boluscalc')(client, $)
 *                   -> boluscalc's init calls loadFoodQuickpicks()
 *                      against client.sbx.data.food === []
 *   index.js:596  client.sbx = sandbox.clientInit(...)     // replaced, WITH data
 *   index.js:637  boluscalc.updateVisualisations(sbx)      // does NOT rebuild it
 *
 * `loadFoodQuickpicks` has exactly one call site. So the chooser offers only
 * "(none)" forever, for every operator, while "Add food from database" works
 * because fillForm reads the sandbox at click time.
 *
 * THIS PROBE DRIVES ONLY WHAT A USER DRIVES. It clicks #boluscalcDrawerToggle
 * and reads the chooser. It does NOT call loadFoodQuickpicks() itself — that
 * is what probes/food-boluscalc-browser.js does, deliberately, to reach BF-35's
 * behaviour at all. The difference between the two probes IS the defect.
 *
 * SEQUENCING, measured and not negotiable. The candidate fix (call
 * loadFoodQuickpicks from boluscalc.prepare) was applied to a8888f0d WITHOUT
 * bf/food: the chooser then offered 8 entries — every plain food plus the
 * hidden quick pick — and selecting them produced 5 page errors. BF-35 is
 * latent today ONLY because BF-69 hides it. A build that repairs the chooser
 * without bf/food is strictly worse than today's release, in a bolus
 * calculator. Hence the second arm below: this probe is green only when the
 * chooser is BOTH populated AND correct.
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

const EXPECTED = ['review-qp-visible', 'review-qp-strfalse'];

async function measure(url, secret) {
  const { chromium } = require(PW);
  const sha1 = crypto.createHash('sha1').update(secret).digest('hex');
  const h = { 'api-secret': sha1, 'content-type': 'application/json' };
  await fetch(`${url}/api/v2/authorization/subjects`,
    { method: 'POST', headers: h, body: JSON.stringify({ name: 'reviewer', roles: ['admin'] }) })
    .catch(() => {});
  const subs = await (await fetch(`${url}/api/v2/authorization/subjects`, { headers: h })).json();
  const token = (subs.find(s => s.name === 'reviewer') || {}).accessToken;
  if (!token) throw new Error('could not mint a token');

  const browser = await chromium.launch({ channel: 'chrome', args: ['--no-sandbox'] });
  const page = await (await browser.newContext()).newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e.message)));
  await page.goto(`${url}/?token=${token}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForFunction(
    () => window.Nightscout && Nightscout.client && Nightscout.client.sbx &&
          (Nightscout.client.sbx.data.food || []).length > 0, { timeout: 60000 });
  await page.waitForTimeout(1500);

  // exactly one user action
  await page.evaluate(() => {
    const t = document.querySelector('#boluscalcDrawerToggle'); if (t) t.click();
  });
  await page.waitForTimeout(1500);

  const options = await page.evaluate(() =>
    Array.from(document.querySelectorAll('#bc_quickpick option')).map(o => ({ v: o.value, t: o.text })));

  // select each offered quick pick, as a user would
  for (const o of options.filter(x => Number(x.v) >= 0)) {
    await page.evaluate(v => {
      const s = document.querySelector('#bc_quickpick');
      s.value = v; s.dispatchEvent(new Event('change', { bubbles: true }));
    }, o.v).catch(() => {});
    await page.waitForTimeout(100);
  }

  const foodCount = await page.evaluate(() => (Nightscout.client.sbx.data.food || []).length);
  await browser.close();
  return { options, foodCount, errors: errors.filter(e => !/play\(\) failed/.test(e)) };
}

(async () => {
  const a = process.argv.slice(2);
  const g = k => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : null; };
  const baseUrl = g('--base'), candUrl = g('--candidate'), secret = g('--secret');
  if (!baseUrl || !candUrl || !secret) { console.error('need --base --candidate --secret'); process.exit(2); }

  const base = await measure(baseUrl, secret);
  const cand = await measure(candUrl, secret);
  const sel = r => r.options.filter(o => Number(o.v) >= 0).map(o => o.t);
  const findings = [];

  // ARM 1 — the chooser is populated at all. This is BF-69.
  findings.push({
    ok: sel(cand).length > 0,
    text: `[discriminates] BF-69 chooser is populated after one click: CANDIDATE ${sel(cand).length} ` +
          `option(s) [${sel(cand).join(' | ')}] with ${cand.foodCount} food records loaded`,
  });
  findings.push({
    ok: true,
    text: `[discriminates] CONTROL BASE ${sel(base).length} option(s) [${sel(base).join(' | ')}] with ` +
          `${base.foodCount} food records loaded — ${sel(base).length > 0 ? 'GREEN' : 'RED (feature inert)'}`,
  });
  if (sel(base).length > 0) {
    findings.push({ ok: false, text: '[discriminates] UNINFORMATIVE — BASE populated the chooser too' });
  }

  // ARM 2 — populated is not enough. Repairing BF-69 without bf/food offers 8
  // entries and crashes 5 times; that build is worse than today's release.
  findings.push({
    ok: sel(cand).length === EXPECTED.length &&
        EXPECTED.every(n => sel(cand).some(x => x.startsWith(n))),
    text: `[discriminates] ...and it is CORRECT (exactly the ${EXPECTED.length} visible quick picks, ` +
          `no plain foods, no hidden pick): CANDIDATE [${sel(cand).join(' | ')}]`,
  });
  findings.push({
    ok: cand.errors.length === 0,
    text: `[discriminates] ...and selecting every offered pick throws nothing: CANDIDATE ` +
          `${cand.errors.length} page errors` + (cand.errors.length ? ` -> ${cand.errors[0].slice(0, 54)}` : ''),
  });

  report('quickpick-chooser (BF-69) — browser', findings);
})().catch(e => { console.error('quickpick probe failed:', e.message); process.exit(2); });
