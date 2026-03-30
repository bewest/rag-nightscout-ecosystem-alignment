#!/usr/bin/env node
/**
 * Smoke test for in-silico simulation engines.
 *
 * Runs one scenario per engine configuration, asserts BG range thresholds.
 * Designed for CI: exits 0 on success, 1 on any assertion failure.
 *
 * Usage:
 *   node smoke-test-engines.js          # run all checks
 *   node smoke-test-engines.js --quiet  # only print failures
 *
 * Trace: GAP-ALG-025 regression guard
 */

const { execSync } = require('child_process');
const path = require('path');

const BRIDGE = path.join(__dirname, 'in-silico-bridge.js');
const quiet = process.argv.includes('--quiet');
let failures = 0;

function run(label, engineArgs, assertions) {
  const cmd = `node ${BRIDGE} --scenario meal-rise --mode open-loop ${engineArgs} 2>&1`;
  let output;
  try {
    output = execSync(cmd, { encoding: 'utf8', timeout: 120000 });
  } catch (e) {
    console.error(`FAIL [${label}]: execution error — ${e.message}`);
    failures++;
    return;
  }

  // Parse the summary table for min/max
  const match = output.match(/║\s*Meal with adequate bolus\s*│\s*open-loop\s*│\s*(\d+)\s*│\s*(\d+)\s*│\s*(\d+)/);
  if (!match) {
    console.error(`FAIL [${label}]: could not parse summary table`);
    failures++;
    return;
  }

  const avg = parseInt(match[1]);
  const min = parseInt(match[2]);
  const max = parseInt(match[3]);

  for (const a of assertions) {
    const val = { avg, min, max }[a.field];
    const pass = a.op === '>=' ? val >= a.threshold : val <= a.threshold;
    if (!pass) {
      console.error(`FAIL [${label}]: ${a.field}=${val} expected ${a.op} ${a.threshold}`);
      failures++;
    } else if (!quiet) {
      console.log(`  OK [${label}]: ${a.field}=${val} ${a.op} ${a.threshold}`);
    }
  }
}

console.log('In-silico engine smoke tests\n');

run('CGMSIM baseline', '', [
  { field: 'min', op: '>=', threshold: 39 },
  { field: 'max', op: '<=', threshold: 200 },
]);

run('UVA/Padova', '--engine uva-padova', [
  { field: 'min', op: '>=', threshold: 39 },
  { field: 'max', op: '>=', threshold: 130 },  // must show meaningful excursion
  { field: 'max', op: '<=', threshold: 350 },
]);

run('UVA/Padova + Facchinetti noise', '--engine uva-padova --sensor facchinetti', [
  { field: 'min', op: '>=', threshold: 39 },
  { field: 'max', op: '>=', threshold: 130 },
  { field: 'max', op: '<=', threshold: 400 },
]);

console.log(`\n${failures === 0 ? '✅ All checks passed' : `❌ ${failures} check(s) failed`}`);
process.exit(failures === 0 ? 0 : 1);
