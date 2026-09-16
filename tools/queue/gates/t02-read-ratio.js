'use strict';
/*
 * t02-read-ratio.js — T0.2's stated gate, run live. This one is MET.
 *
 * T0.2 `done` asks that an untyped /api/v1/entries read come within 2x of a typed
 * one at count=10. On origin/dev it is 40x, because the untyped branch deep-clones
 * the whole retained window before slicing ten documents out of it. The branch
 * slices first and clones the slice.
 *
 * It is carried beside t03-cycle-clone-budget.js deliberately. That one is RED and
 * says so; this one is GREEN. P0-B has one target met and one not, and an item that
 * showed only the failure would misrepresent the branch as much as one that showed
 * only the win.
 *
 * NON-VACUITY IS STRUCTURAL, same as its sibling: the harness reads
 * lib/api/entries/index.js out of the worktree and names the shape it found —
 * `clone-then-slice` on dev, `slice-then-clone` on the branch — and throws on a
 * tree it cannot recognise. Measured 2026-09-16: dev FAILs this gate at 40.3x,
 * the branch PASSes at 0.7x, so it distinguishes them.
 *
 * SLOW: it runs a benchmark. kind: integration.
 *
 * Overrides, used by the ablation and by nothing else:
 *   --worktree <path>
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
const BENCH = path.join(REPO_ROOT, 'tools', 'mt-bench', 'apitier.js');

if (!fs.existsSync(path.join(WORKTREE, 'node_modules'))) {
  console.log('gate: t02-read-ratio (P0-B)');
  console.log('  SKIP  ' + WORKTREE + ' has no node_modules; `npm ci` there first.');
  process.exit(0);
}

let out;
try {
  out = execFileSync(process.execPath, ['--expose-gc', BENCH, 'read'], {
    cwd: WORKTREE,
    env: Object.assign({}, process.env, { NS_ROOT: WORKTREE }),
    encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024
  });
} catch (err) {
  report('t02-read-ratio (P0-B)',
    [{ ok: false, text: 'the bench did not run: ' + String(err.message).split('\n')[0] }]);
}

const findings = [];

const shape = /live source shape:\s*(\S+)/.exec(out);
findings.push({
  ok: !!shape,
  text: shape ? 'harness read the live source shape: ' + shape[1]
              : 'harness did not name a source shape — it may not have recognised this tree'
});

const g = /T0\.2 gate:.*->\s*(PASS|FAIL)\s*\(([^)]+)\)/.exec(out);
findings.push({
  ok: !!g && g[1] === 'PASS',
  text: g ? 'T0.2 budget: untyped within 2x of typed at count=10 — ' + g[1] + ' (' + g[2] + ')'
          : 'could not parse the T0.2 gate line out of the bench output'
});

report('t02-read-ratio (P0-B)', findings);
