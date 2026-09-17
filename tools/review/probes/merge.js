#!/usr/bin/env node
'use strict';
/*
 * merge.js — P0-H / bf/merge (#8734), register BF-36.
 *
 * `mergeTreatmentUpdate` in lib/client/receiveddata.js captured the cached
 * array's length ONCE, then spliced that same array inside the loop. The first
 * 'remove' that matched shrank the array and the captured bound went stale, so
 * the next received item matching nothing scanned past the end and threw on
 * `undefined._id`. The throw escapes into `dataUpdate`, which has no
 * try/catch, so the page stops advancing until it is reloaded.
 *
 * WHY THIS IS AN IN-PROCESS PROBE AND NOT A BROWSER ONE. A refuter established
 * that the browser route cannot go red: deleting a treatment OUTSIDE the
 * client's loaded window emits no delta item at all (calcdelta only emits
 * removes for documents present in the server's previous ddata), and every
 * item that IS emitted is by construction present in the client cache — so the
 * inner scan always breaks before reaching the stale bound. The reachable
 * shape is a delta carrying a remove for an id the client does not hold, which
 * the server does not currently produce from an ordinary delete.
 *
 * That makes the defect REAL but, by the routes tested so far, NOT REACHABLE
 * from the server's own delta stream. The probe measures the function
 * contract directly and says so rather than dressing an in-process call up as
 * a user scenario. See plan §7.
 */

const path = require('path');
const { execFileSync } = require('child_process');
const { report } = require(path.resolve(__dirname, '..', '..', 'queue', 'gates', '_gate.js'));

const SENTINEL = '@@NSREVIEW@@';

const LOADER = `
const wt = process.argv[1];
const rd = require(wt + '/lib/client/receiveddata.js');
function run(cached, received) {
  try {
    const out = rd.mergeTreatmentUpdate(true, cached, received);
    return { threw: null, length: (out || cached).length,
             ids: (out || cached).map(function (x) { return x._id; }) };
  } catch (e) { return { threw: e.message, length: null, ids: null }; }
}
const cases = {
  // a remove that matches, then an id the cache does not hold: the captured
  // bound is now one past the end
  staleBound: run(
    [{_id:'a'},{_id:'b'},{_id:'c'}],
    [{_id:'b', action:'remove'},{_id:'zz', action:'remove'}]),
  // two matching removes in a row - the bound goes two stale
  twoRemoves: run(
    [{_id:'a'},{_id:'b'},{_id:'c'},{_id:'d'}],
    [{_id:'b', action:'remove'},{_id:'c', action:'remove'},{_id:'qq', action:'remove'}]),
  // INVARIANT: an ordinary delta that touches only ids the cache holds must
  // behave identically on both builds
  ordinary: run(
    [{_id:'a',v:1},{_id:'b',v:1},{_id:'c',v:1}],
    [{_id:'b', action:'update', v:2},{_id:'c', action:'remove'}]),
};
process.stdout.write('${SENTINEL}' + JSON.stringify(cases) + '${SENTINEL}');
`;

function run(worktree) {
  const out = execFileSync(process.execPath, ['-e', LOADER, worktree],
    { cwd: worktree, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
  const a = out.indexOf(SENTINEL), b = out.lastIndexOf(SENTINEL);
  if (a < 0 || b <= a) throw new Error(`no payload: ${out.slice(0, 300)}`);
  return JSON.parse(out.slice(a + SENTINEL.length, b));
}

function main() {
  const a = process.argv.slice(2);
  const g = k => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : null; };
  const baseWt = g('--base-worktree'), candWt = g('--candidate-worktree');
  if (!baseWt || !candWt) { console.error('need --base-worktree and --candidate-worktree'); process.exit(2); }

  const base = run(baseWt), cand = run(candWt);
  const findings = [];
  const d = r => (r.threw ? `THREW ${r.threw.slice(0, 54)}` : `ok, ${r.length} left [${r.ids.join(',')}]`);

  for (const k of ['staleBound', 'twoRemoves']) {
    findings.push({ ok: !cand[k].threw, text: `[discriminates] ${k}: CANDIDATE ${d(cand[k])}` });
    findings.push({ ok: true, text: `[discriminates] ${k}: CONTROL   BASE ${d(base[k])} — ${base[k].threw ? 'RED' : 'GREEN'}` });
    if (!base[k].threw) {
      findings.push({ ok: false, text: `[discriminates] ${k}: UNINFORMATIVE — BASE did not throw either` });
    }
  }
  // The fix must not change what an ordinary delta produces.
  const same = JSON.stringify(base.ordinary) === JSON.stringify(cand.ordinary);
  findings.push({
    ok: same && !cand.ordinary.threw,
    text: `[invariant] an ordinary delta is unchanged: BASE ${d(base.ordinary)} | CANDIDATE ${d(cand.ordinary)}`,
  });
  report('merge (bf/merge #8734, BF-36)', findings);
}

main();
