'use strict';
/*
 * d3-drag-clamp-covered.js  — RT-D3
 *
 * THE D3 GAP, expressed as an ablation instead of an opinion.
 *
 * Release-readiness §2 said every claim about chart interaction "rests on jsdom
 * and on whatever manual checking was done". GT2 measured that as too
 * pessimistic: dev DOES carry tests/dependency-d3.test.js, a 218-line suite
 * driving the real renderer and chart against the D3 7 browser bundle, 24
 * passing, and it catches the migration's core hazard (D3 6's event-as-first-
 * argument change).
 *
 * But it found a sharper gap underneath. Deleting BOTH treatment-drag clamps
 * from lib/client/renderer.js leaves the suite fully green, because the drag
 * handler is exercised 25 times with only x in {20,400} and y in {20,150,380},
 * all strictly inside 0..900 and 0..399. The clamp executes on every call and
 * its boundary is never reached, so the suite cannot tell a clamped handler
 * from an unclamped one.
 *
 * WHY THESE PARTICULAR LINES MATTER. The clamped x feeds
 * `newTime = new Date(chart().xScale.invert(x))`, and the drag-end handler
 * emits `dbUpdate` on treatments with `{ created_at: newTime.toISOString() }`.
 * A treatment's timestamp is what IOB and COB key off. So the least-covered
 * lines the D3 6 migration rewrote are the ones that bound a user-initiated
 * rewrite of when a dose happened — and IOB/COB are what a person reads when
 * deciding about food or a correction. This is not a rendering nicety.
 *
 * HOW IT MEASURES, and why it is an ablation rather than a coverage number.
 * Line coverage would call these lines covered: they execute on every drag.
 * Only removing them and seeing whether anything notices distinguishes "run"
 * from "tested". That is the non-vacuity rule applied to somebody else's suite.
 *
 *   control   unmodified tree -> the suite must PASS. If it does not, the
 *             harness is broken and the ablation below means nothing.
 *   ablation  clamps removed -> the suite must FAIL. If it still passes, the
 *             clamps are untested and THIS GATE FAILS.
 *
 * Reads only. `git archive` into a scratch directory; no worktree is written to
 * and node_modules is borrowed by symlink, never modified.
 */

const { execFileSync, spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { REPO_ROOT, CRM, report } = require('./_gate');

const REF = 'origin/dev';
const SUITE = 'tests/dependency-d3.test.js';
const TARGET = 'lib/client/renderer.js';

// The two clamp expressions, as literals. A regex is the wrong tool here: the
// second argument contains its own parentheses, and a naive `[^)]*\)` truncates
// the expression and produces a SYNTAX ERROR, which the suite then reports as a
// failure -- an ablation that "works" for entirely the wrong reason. That
// happened while this gate was being written.
const CLAMPS = [
  ["Math.min(Math.max(0, event.x), chart().charts.attr('width'))", 'event.x'],
  ['Math.min(Math.max(0, event.y), chart().focusHeight)', 'event.y'],
];

const findings = [];

function donorModules() {
  const work = path.join(REPO_ROOT, 'externals', 'work');
  if (!fs.existsSync(work)) return null;
  for (const name of fs.readdirSync(work)) {
    const modules = path.join(work, name, 'node_modules');
    if (fs.existsSync(path.join(modules, 'd3'))
        && fs.existsSync(path.join(modules, '.bin', 'mocha'))) {
      return modules;
    }
  }
  return null;
}

const modules = donorModules();
if (!modules) {
  findings.push({
    ok: false,
    text: 'no worktree under externals/work/ has both d3 and mocha installed, so the '
        + 'suite cannot be run. NOTHING WAS MEASURED -- this is a broken gate, not a '
        + 'clean result.',
  });
  report('d3-drag-clamp-covered (RT-D3)', findings);
}

const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'queue-d3-'));
function runSuite() {
  const result = spawnSync(path.join(modules, '.bin', 'mocha'),
                           ['--timeout', '15000', SUITE],
                           { cwd: scratch, encoding: 'utf8' });
  const out = (result.stdout || '') + (result.stderr || '');
  const passing = Number((out.match(/(\d+) passing/) || [])[1] || 0);
  const failing = Number((out.match(/(\d+) failing/) || [])[1] || 0);
  return { passing, failing, code: result.status };
}

try {
  execFileSync('bash', ['-c',
    `git -C ${JSON.stringify(CRM)} archive ${REF} | tar -x -C ${JSON.stringify(scratch)}`]);
  fs.symlinkSync(modules, path.join(scratch, 'node_modules'));

  if (!fs.existsSync(path.join(scratch, SUITE))) {
    findings.push({ ok: false, text: `${REF} has no ${SUITE}; nothing measured` });
    report('d3-drag-clamp-covered (RT-D3)', findings);
  }

  // --- control ------------------------------------------------------------
  const control = runSuite();
  findings.push({
    ok: control.failing === 0 && control.passing > 0,
    text: `CONTROL: unmodified ${REF} -> ${control.passing} passing, `
        + `${control.failing} failing (the harness works)`,
  });
  if (control.failing !== 0 || control.passing === 0) {
    report('d3-drag-clamp-covered (RT-D3)', findings);
  }

  // --- ablation -----------------------------------------------------------
  const file = path.join(scratch, TARGET);
  let source = fs.readFileSync(file, 'utf8');
  let removed = 0;
  for (const [needle, replacement] of CLAMPS) {
    removed += source.split(needle).length - 1;
    source = source.split(needle).join(replacement);
  }
  fs.writeFileSync(file, source);

  findings.push({
    ok: removed > 0,
    text: `ablation removed ${removed} treatment-drag clamp expression(s) from ${TARGET}`,
  });

  // The ablated file must still PARSE, or the suite fails on a syntax error and
  // the gate would report "covered" when it measured nothing of the kind.
  const parses = spawnSync(process.execPath, ['--check', file], { encoding: 'utf8' });
  findings.push({
    ok: parses.status === 0,
    text: 'the ablated renderer still parses, so any suite failure is a failure to '
        + 'accept unclamped behaviour and not a syntax error',
  });
  if (parses.status !== 0 || removed === 0) {
    report('d3-drag-clamp-covered (RT-D3)', findings);
  }

  const ablated = runSuite();
  findings.push({
    ok: ablated.failing > 0,
    text: ablated.failing > 0
      ? `ablated tree -> ${ablated.passing} passing, ${ablated.failing} failing: the `
        + 'suite notices when the drag clamps are gone'
      : `ablated tree -> ${ablated.passing} passing, ${ablated.failing} failing. The `
        + 'clamps can be DELETED ENTIRELY and nothing goes red. They bound a '
        + "user-initiated rewrite of a treatment's created_at, which is what IOB and "
        + 'COB key off, and they are the lines the D3 6 migration rewrote.',
  });
} finally {
  try { fs.rmSync(scratch, { recursive: true, force: true }); } catch (e) { /* scratch only */ }
}

report('d3-drag-clamp-covered (RT-D3)', findings);
