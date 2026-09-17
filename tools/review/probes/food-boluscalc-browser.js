#!/usr/bin/env node
'use strict';
/*
 * food-boluscalc-browser.js — BF-35, the clinically significant half of
 * bf/food (#8735). This is the only defect in the cycle that sits next to a
 * dose, and it is not reachable over HTTP: it lives in lib/client/boluscalc.js
 * and only exists once a browser has built the chooser.
 *
 * THE DEFECT. `loadFoodQuickpicks` builds the <option> list by looping over
 * `records` — EVERY food document — while the option VALUE is an index into
 * `quickpicks`, which holds only the quick-pick-typed ones. The two arrays have
 * different lengths and different membership, so:
 *
 *   - plain foods appear in a chooser that is supposed to list quick picks;
 *   - selecting entry i loads quickpicks[i], which is a DIFFERENT quick pick;
 *   - selecting past the end of `quickpicks` resolves to undefined and throws.
 *
 * The user picks one quick pick and the calculator loads another one's carbs.
 *
 * PREREQUISITE, enforced, not assumed: run probes/provenance.js first. In
 * production mode every state serves one shared stale bundle out of the common
 * node_modules cache, so the branch's instance serves dev's client and this
 * probe would compare dev to dev and report a pass. Requires NODE_ENV=development
 * and ENABLE containing `food boluscalc`.
 *
 * Uses playwright-core against system Chrome (no browser download). Never
 * `chrome --headless --dump-dom`, which hangs once socket.io connects.
 */

const path = require('path');
const crypto = require('crypto');
const { report } = require(path.resolve(__dirname, '..', '..', 'queue', 'gates', '_gate.js'));

// playwright-core is installed into the scratch root, not the repo — this is a
// harness dependency, not a project one. Try the places it can legitimately be.
function resolvePlaywright() {
  const root = process.env.NSREVIEW_ROOT || '';
  const candidates = [
    process.env.NSREVIEW_PLAYWRIGHT,
    path.join(root, 'node_modules', 'playwright-core'),
    path.join(root, 'deps', 'node_modules', 'playwright-core'),
    'playwright-core',
  ].filter(Boolean);
  for (const c of candidates) {
    try { require.resolve(c); return c; } catch { /* next */ }
  }
  console.error('playwright-core not found. Install it with:\n' +
    `  npm install --no-save --prefix "$NSREVIEW_ROOT" playwright-core`);
  process.exit(2);
}
const PW = resolvePlaywright();

async function inspect(url, secret) {
  const { chromium } = require(PW);
  const browser = await chromium.launch({ channel: 'chrome', args: ['--no-sandbox'] });
  const page = await (await browser.newContext()).newPage();
  const pageErrors = [];
  page.on('pageerror', e => pageErrors.push(String(e.message)));

  // A token, not the api-secret: the drawer toggle is hidden unless the
  // subject may create treatments.
  const sha1 = crypto.createHash('sha1').update(secret).digest('hex');
  const mk = await fetch(`${url}/api/v2/authorization/subjects`, {
    method: 'POST', headers: { 'api-secret': sha1, 'content-type': 'application/json' },
    body: JSON.stringify({ name: 'reviewer', roles: ['admin'] }),
  }).catch(() => null);
  if (mk) { /* already exists is fine */ }
  const subs = await (await fetch(`${url}/api/v2/authorization/subjects`,
    { headers: { 'api-secret': sha1 } })).json();
  const tok = (subs.find(s => s.name === 'reviewer') || {}).accessToken;
  if (!tok) throw new Error('could not mint a reviewer token');

  // NEVER waitUntil:'networkidle' — socket.io holds the connection open and it
  // never fires (measured: 60 s timeout every time).
  await page.goto(`${url}/?token=${tok}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForFunction(
    () => window.Nightscout && Nightscout.client && Nightscout.client.sbx &&
          Nightscout.client.sbx.data && (Nightscout.client.sbx.data.food || []).length > 0,
    { timeout: 60000 });

  const result = await page.evaluate(() => {
    const c = Nightscout.client;
    // loadFoodQuickpicks is called ONCE, at client init, before the socket has
    // delivered any food — so the shipping chooser is empty and a user never
    // sees either behaviour until something rebuilds it. Driving it directly
    // here is what makes the defect observable at all; it is the exact
    // function the PR changes, running against real client state.
    c.boluscalc.loadFoodQuickpicks();
    const sel = document.querySelector('#bc_quickpick');
    const options = Array.from(sel.options).map(o => ({ value: o.value, text: o.text }));

    // Drive each selection the way a user does and read back what the
    // calculator loaded into the carbs field.
    const picks = [];
    for (const o of options.filter(x => Number(x.value) >= 0)) {
      let loaded = null, threw = null;
      try {
        sel.value = o.value;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
        const carbs = document.querySelector('#bc_carbs');
        loaded = carbs ? carbs.value : null;
      } catch (e) { threw = e.message; }
      const m = /\((\d+)\s*g\)/.exec(o.text);
      picks.push({ value: o.value, label: o.text, labelled: m ? m[1] : null, loaded, threw });
    }
    return { options, picks, foodCount: (c.sbx.data.food || []).length };
  });

  await browser.close();
  return { ...result, pageErrors };
}

(async () => {
  const a = process.argv.slice(2);
  const g = k => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : null; };
  const baseUrl = g('--base'), candUrl = g('--candidate'), secret = g('--secret');
  if (!baseUrl || !candUrl || !secret) { console.error('need --base --candidate --secret'); process.exit(2); }

  const base = await inspect(baseUrl, secret);
  const cand = await inspect(candUrl, secret);
  const findings = [];
  const selectable = r => r.options.filter(o => Number(o.value) >= 0);
  const names = r => selectable(r).map(o => o.text).join(' | ');

  // ARM 1 — chooser MEMBERSHIP. Not a count: BASE offers every plain food and
  // the quick pick the user deliberately hid.
  findings.push({
    kind: 'discriminates', ok: selectable(cand).length === 2 &&
      !names(cand).includes('review-oats') && !names(cand).includes('review-qp-hidden'),
    text: `[discriminates] chooser offers only the visible quick picks: CANDIDATE ${selectable(cand).length} — ${names(cand)}`,
  });
  findings.push({ ok: true,
    text: `[discriminates] CONTROL BASE offers ${selectable(base).length} — ${names(base)} — ` +
          (selectable(base).length === 2 ? 'GREEN' : 'RED (plain foods and a hidden quick pick are offered)') });
  if (selectable(base).length === 2) {
    findings.push({ ok: false, text: '[discriminates] UNINFORMATIVE — BASE offered the same chooser' });
  }

  // ARM 2 — the CRASH. The option value indexes `quickpicks`, which holds only
  // the quick-pick-typed records, so every option past its end resolves to
  // undefined and `qp.foods` throws (boluscalc.js:579-580). With 3 quick picks
  // behind 8 options that is 5 throws, and the throw escapes into the jQuery
  // change handler rather than reaching this evaluate — so it is counted from
  // page errors, not from a try/catch.
  findings.push({
    kind: 'discriminates', ok: cand.pageErrors.length === 0,
    text: `[discriminates] selecting every offered quick pick throws nothing: CANDIDATE ${cand.pageErrors.length} page errors`,
  });
  findings.push({ ok: true,
    text: `[discriminates] CONTROL BASE ${base.pageErrors.length} page errors` +
          (base.pageErrors.length ? ` -> ${base.pageErrors[0]}` : '') + ' — ' +
          (base.pageErrors.length ? 'RED (a selection crashes the calculator)' : 'GREEN') });
  if (base.pageErrors.length === 0) {
    findings.push({ ok: false, text: '[discriminates] UNINFORMATIVE — BASE threw nothing either' });
  }

  // ARM 3 — invariant: the real quick picks are still all offered. Guards the
  // fix against over-correcting into "show nothing".
  findings.push({
    kind: 'invariant', ok: names(cand).includes('review-qp-visible') && names(cand).includes('review-qp-strfalse'),
    text: `[invariant] both genuinely-visible quick picks are still offered on CANDIDATE`,
  });

  /*
   * NOT MEASURED HERE, deliberately. "Picking one quick pick loads a DIFFERENT
   * one's carbs" is the half of BF-35 with dose consequences, and it is
   * inferred from the index arithmetic above rather than read from the DOM:
   * `foods` is module-private, `#bc_carbs` is only written on the "(none)"
   * branch, and `#bc_food` renders empty in this synthetic state. An earlier
   * revision of this probe asserted on #bc_carbs and read 0 on BOTH builds —
   * a criterion that would have passed anything. What IS measured is that on
   * BASE options 0-2 resolve silently to the three quick picks while carrying
   * a plain food's label, and options 3-7 throw. See plan §7.
   */
  report('food-boluscalc (BF-35, #8735) — browser', findings);
})().catch(e => { console.error('browser probe failed:', e.message); process.exit(2); });
