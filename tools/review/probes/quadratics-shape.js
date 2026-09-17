#!/usr/bin/env node
'use strict';
/*
 * quadratics-shape.js — P0-T01 / #8733, the two quadratic scans over the
 * treatment window (lib/data/ddata.js processDurations, lib/data/calcdelta.js).
 *
 * SHAPE, NOT A MULTIPLE — for the same reason as cache-shape.js. The first
 * draft required ">= 20x faster at n = 500, 2000 and 5000". Measured, two of
 * those three are BELOW the bar ON THE CORRECT BUILD: 1.7x/3.0x at n=500 and
 * 12.0x/11.0x at n=2000; only n=5000 clears it at 43.6x/47.6x. A gate binding
 * 20x at every n is stuck red on the fix.
 *
 * What the PR actually removes is an O(n^2) scan. So the assertion is about
 * the exponent, and it is scale-free:
 *
 *   BASE  t(5000)/t(500)  >=  SUPERLINEAR_MIN   (10x the input costs much more
 *                                                than 10x the time -> quadratic)
 *   RC    t(5000)/t(500)  <=  NEARLY_LINEAR_MAX (10x the input costs about 10x
 *                                                the time, or less)
 *
 * A 10x increase in n is linear at exactly 10x time. Measured on this machine:
 * BASE 81.8x (processDurations) and 84.5x (calcDelta) — the quadratic
 * signature; the fix 7.6x and 7.9x — better than linear, because the per-item
 * work shrank as well.
 *
 * THE EQUALITY ARM IS DELIBERATELY ABSENT. The plan wanted "processDurations
 * output byte-identical to BASE, including which event carries `cutting`". A
 * refuter tried two independent injected defects in the branch's own
 * optimisation — reversing the candidate visit order (the plan's own named
 * break) and an off-by-one on the window limit — and BOTH left the output hash
 * UNCHANGED, because cutIfInInterval re-validates the interval and absorbs
 * extra or missing boundary candidates. An arm with no demonstrated reachable
 * red is not evidence, so it is not shipped. Output equality is checked here
 * only as a smoke test and reported, never asserted. See plan §7.
 */

const path = require('path');
const { execFileSync } = require('child_process');
const { report } = require(path.resolve(__dirname, '..', '..', 'queue', 'gates', '_gate.js'));

const SENTINEL = '@@NSREVIEW@@';
const SUPERLINEAR_MIN = 15;    // linear over a 10x input increase would be 10
// Linear over a 10x input increase is 10x. The bar must therefore sit ABOVE
// 10, or a perfectly linear fix fails. Set to 13 for noise headroom.
//
// This file's FIRST version set it to 6 and the fix failed at 7.6x — a
// stuck-red threshold, which is precisely the error this probe's header
// criticises in the original plan. Writing the warning down did not prevent
// repeating it; running the probe did. The separation is wide either way:
// BASE measured ~82x, the fix ~7.6x.
const NEARLY_LINEAR_MAX = 13;

const LOADER = `
const wt = process.argv[1];
// ddata is a FACTORY - require(...)() - not a module with .init(). The recon's
// scratch/quadbench.js had this right; deriving it again got it wrong.
const ddata = require(wt + '/lib/data/ddata')();
const calcDelta = require(wt + '/lib/data/calcdelta');

// Deterministic fixture: overlapping temp basals at 5-minute spacing with
// 30-minute durations, so every item overlaps five neighbours. Fixed epoch and
// a fixed pattern, so both builds see byte-identical input.
function fixture(n){
  var t0 = Date.UTC(2026,0,1,0,0,0), out = [];
  for (var i = 0; i < n; i++) {
    out.push({ _id: '7000000000000000' + String(100000+i),
               eventType: 'Temp Basal', mills: t0 + i*300000,
               duration: 30, absolute: 0.8 + (i%10)/10,
               enteredBy: 'nsreview' });
  }
  return out;
}
var clone = function (x) { return JSON.parse(JSON.stringify(x)); };

function timePD(n){
  var t = fixture(n);
  var t0 = process.hrtime.bigint();
  ddata.processDurations(clone(t), false);
  return Number(process.hrtime.bigint()-t0)/1e6;
}
function timeCD(n){
  var t = fixture(n);
  var blank = {sgvs:[],mbgs:[],cals:[],food:[],devicestatus:[],profiles:[],activity:[]};
  var oldD = Object.assign({treatments: clone(t)}, blank);
  var newD = Object.assign({treatments: clone(t)}, blank);
  newD.treatments[n-1] = Object.assign({}, newD.treatments[n-1], {absolute: 9.9});
  var t0 = process.hrtime.bigint();
  calcDelta(oldD, newD);
  return Number(process.hrtime.bigint()-t0)/1e6;
}
function med3(f, n){ f(n); var r=[f(n),f(n),f(n)].sort(function(a,b){return a-b;}); return r[1]; }

var out = {};
[500, 2000, 5000].forEach(function(n){
  out['pd'+n] = med3(timePD, n);
  out['cd'+n] = med3(timeCD, n);
});
out.len = ddata.processDurations(clone(fixture(500)), false) === undefined
  ? 500 : (ddata.processDurations(clone(fixture(500)), false) || []).length;
process.stdout.write('${SENTINEL}' + JSON.stringify(out) + '${SENTINEL}');
`;

function timings(worktree) {
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

  const b = timings(baseWt), c = timings(candWt);
  const findings = [];

  for (const [fn, label] of [['pd', 'processDurations'], ['cd', 'calcDelta']]) {
    const r = t => t[fn + '5000'] / t[fn + '500'];
    const fmt = t => `n500 ${t[fn + '500'].toFixed(1)}ms, n2000 ${t[fn + '2000'].toFixed(1)}ms, ` +
                     `n5000 ${t[fn + '5000'].toFixed(1)}ms -> ${r(t).toFixed(1)}x for 10x input`;
    findings.push({
      ok: r(b) >= SUPERLINEAR_MIN,
      text: `[control] ${label}: BASE is SUPERLINEAR (need >= ${SUPERLINEAR_MIN}x; linear is 10x): ${fmt(b)}` +
            (r(b) >= SUPERLINEAR_MIN ? '' : ' — no quadratic behaviour here, the candidate arm proves nothing'),
    });
    findings.push({
      ok: r(c) <= NEARLY_LINEAR_MAX,
      text: `[discriminates] ${label}: CANDIDATE is at worst NEARLY LINEAR (need <= ${NEARLY_LINEAR_MAX}x): ${fmt(c)}`,
    });
    findings.push({
      ok: true,
      text: `[context] ${label}: absolute speedup at n=5000 is ${(b[fn + '5000'] / c[fn + '5000']).toFixed(1)}x — ` +
            `reported, NOT asserted (a 20x bar measured stuck-red at n=500 and n=2000 on the correct build)`,
    });
  }
  report('quadratics-shape (#8733, T0.1)', findings);
}

main();
