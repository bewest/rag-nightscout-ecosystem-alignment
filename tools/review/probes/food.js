#!/usr/bin/env node
'use strict';
/*
 * food.js — P0-G / bf/food (#8735), register BF-16 and BF-35.
 *
 * BF-16, the half this probe can measure over HTTP. `lib/server/food.js`
 * filters quick picks by comparing `hidden` to the STRING 'false'. A quick
 * pick written by any JSON client with a real boolean `false` — the only
 * correct way to say "not hidden" — is therefore silently dropped, while one
 * carrying the string 'false' survives. The user loses a quick pick and is
 * told nothing.
 *
 * Measured 2026-09-17 against the harness seed (3 quick picks: one boolean
 * false, one boolean true, one string 'false'):
 *
 *   BASE a8888f0d : 1 quick pick  — review-qp-strfalse           (the WRONG one)
 *   bf/food       : 2 quick picks — review-qp-visible + strfalse (correct)
 *
 * Note what a count-only assertion would have done here. "Expect 1 visible"
 * is GREEN ON BASE. The arm has to name the expected SET, because BASE
 * returns the right cardinality and the wrong membership.
 *
 * BF-35, the other half, is NOT measurable here and this probe does not
 * pretend otherwise. The bolus calculator's quick-pick chooser builds its
 * <option> list from the whole food collection and resolves the selection
 * against the filtered array, so picking one quick pick loads a different
 * one's carbs. That is `lib/client/boluscalc.js` — it needs a browser, and it
 * is the clinically significant half. See browser card: food-boluscalc.
 */

const { args, fetch, compare } = require('../lib/nsprobe.js');

const VISIBLE_EXPECTED = ['review-qp-visible', 'review-qp-strfalse'];

async function quickpickNames(url, sha1) {
  const r = await fetch(url, '/api/v1/food/quickpicks', sha1);
  if (r.code !== 200) throw new Error(`HTTP ${r.code}`);
  return (r.json || []).map(x => x.name).sort();
}

async function foodCount(url, sha1) {
  const r = await fetch(url, '/api/v1/food', sha1);
  if (r.code !== 200) throw new Error(`HTTP ${r.code}`);
  return (r.json || []).length;
}

(async () => {
  const o = args();
  await compare('food (bf/food #8735, BF-16)', o, [
    {
      kind: 'discriminates',
      what: 'visible quick picks are the two non-hidden ones, by NAME not count',
      measure: quickpickNames,
      ok: v => JSON.stringify(v) === JSON.stringify(VISIBLE_EXPECTED.slice().sort()),
      describe: v => `[${v.join(', ')}] (n=${v.length})`,
    },
    {
      kind: 'discriminates',
      what: 'a boolean-false quick pick is offered at all',
      measure: quickpickNames,
      ok: v => v.includes('review-qp-visible'),
      describe: v => (v.includes('review-qp-visible') ? 'present' : 'ABSENT — a JSON-written quick pick is invisible to the user'),
    },
    {
      // Guard against the fix over-correcting into "show everything".
      // hidden:true must STILL be hidden. Without this arm a branch that
      // simply returned the whole collection would pass the two arms above.
      kind: 'invariant',
      what: 'hidden:true quick pick stays hidden (over-correction guard)',
      measure: quickpickNames,
      ok: v => !v.includes('review-qp-hidden'),
      describe: v => (v.includes('review-qp-hidden') ? 'LEAKED — hidden quick pick is being offered' : 'correctly hidden'),
    },
    {
      kind: 'invariant',
      what: 'the food collection itself is untouched (5 foods + 3 quick picks)',
      measure: foodCount,
      ok: v => v === 8,
      describe: v => `${v} documents`,
    },
  ]);
})().catch(e => { console.error('probe failed:', e.message); process.exit(2); });
