'use strict';
/*
 * t03-cycle-clone-budget.js — T0.3's stated gate, run live.
 *
 * T0.3 `done` asks for the three cache calls the load cycle makes to come in
 * UNDER 1 ms. THIS GATE IS EXPECTED TO FAIL. It is red because the budget is not
 * met, not because anything is broken, and the number it prints is the point.
 *
 * WHY IT EXISTS. P0-B carried a no-gate marker saying the 3.747 -> 2.657 ms
 * measurement "is not currently RE-RUNNABLE: the workload that produced those two
 * figures is not recorded anywhere in this repository". That was false when it was
 * written. docs/60-research/t02-t03-cache-clone-2026-09-15.md §2 names the
 * harness (tools/mt-bench/apitier.js, arm `cycle`), the fixture (576 entries,
 * 600 treatments of which 361 survive retention, 576 device statuses carrying
 * 72-point prediction arrays, DEVICESTATUS_DAYS=2) and §10 gives the command. The
 * consequence of the wrong marker was not cosmetic: `make queue-status` printed
 * CLAIM UNBACKED on this item, because every runnable gate passed while the state
 * said gate-not-met and the failing property sat behind a marker nobody could run.
 *
 * Re-measured 2026-09-16 on Node v24.15.0: the branch gives 2.656 ms against the
 * recorded 2.657, and origin/dev gives 3.929 against a recorded 3.747 — ordinary
 * run-to-run variance on a timing benchmark, same direction and magnitude.
 *
 * NON-VACUITY IS STRUCTURAL, not asserted. The harness reads the live call sites
 * out of the worktree and prints which shape it found: dev reports
 * entries=insertData, the branch reports entries=insertDataRef. Pointed at a tree
 * it cannot recognise it throws rather than guessing. So it cannot report the
 * branch's number for dev's code.
 *
 * SLOW: it runs a benchmark. kind: integration.
 *
 * Overrides, used by the ablation and by nothing else:
 *   --worktree <path>   --budget <ms>
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { REPO_ROOT, report } = require('./_gate');

function argValue(flag, fallback) {
  const at = process.argv.indexOf(flag);
  return at > -1 && process.argv[at + 1] ? process.argv[at + 1] : fallback;
}

const WORKTREE = path.resolve(argValue('--worktree',
  path.join(REPO_ROOT, 'externals', 'work', 'crm-bf-cache')));
const BUDGET = parseFloat(argValue('--budget', '1'));
const BENCH = path.join(REPO_ROOT, 'tools', 'mt-bench', 'apitier.js');

const findings = [];

if (!fs.existsSync(path.join(WORKTREE, 'node_modules'))) {
  console.log('gate: t03-cycle-clone-budget (P0-B)');
  console.log('  SKIP  ' + WORKTREE + ' has no node_modules; `npm ci` there first.');
  console.log('        An unbuilt worktree is not evidence about the budget.');
  process.exit(0);
}

let out;
try {
  out = execFileSync(process.execPath, ['--expose-gc', BENCH, 'cycle'], {
    cwd: WORKTREE,
    env: Object.assign({}, process.env, { NS_ROOT: WORKTREE }),
    encoding: 'utf8',
    timeout: 600000,
    maxBuffer: 16 * 1024 * 1024
  });
} catch (err) {
  report('t03-cycle-clone-budget (P0-B)',
    [{ ok: false, text: 'the bench did not run: ' + String(err.message).split('\n')[0] }]);
}

/* Which call shape the harness found in THIS tree — the branch's whole content. */
const sites = /live call sites:\s*(.+)/.exec(out);
findings.push({
  ok: !!sites,
  text: sites ? 'harness read the live call sites: ' + sites[1].trim()
              : 'harness did not report call sites — it may not have recognised this tree'
});

const m = /the three calls the cycle makes\s+([0-9.]+) ms/.exec(out);
if (!m) {
  findings.push({ ok: false, text: 'could not parse the cycle figure out of the bench output' });
  report('t03-cycle-clone-budget (P0-B)', findings);
}

const measured = parseFloat(m[1]);
findings.push({
  ok: measured < BUDGET,
  text: 'T0.3 budget: the three cycle calls are ' + measured.toFixed(3) + ' ms, '
      + 'and `done` asks for under ' + BUDGET + ' ms'
      + (measured < BUDGET ? '' :
         ' — NOT MET, and this gate is red on purpose. 98% of what remains is '
       + 'devicestatus, whose caller rewrites fields in place; taking it needs proof '
       + 'no plugin writes to a device-status document, which no test in this tree '
       + 'would catch being wrong.')
});

report('t03-cycle-clone-budget (P0-B)', findings);
