'use strict';
/*
 * pr-body-parity.js — every in-flight PR's live body matches the file it was
 * posted from.
 *
 * WHY THIS REPLACES pr-body-carries-correction.js. That gate asked one question
 * about one pull request: does #8738's live body carry the ?count=0 two-path
 * correction? It was the right instrument while that correction was owed, and it
 * went green when the edit was pushed on 2026-09-16 — at which point it became a
 * gate that measures a discharged fact forever. The general form is cheaper to
 * keep and catches the next one too.
 *
 * WHAT IT MEASURES. For each pull request named below, the live body fetched with
 * `gh` must equal the local body file, ignoring trailing whitespace and the
 * trailing newline GitHub appends. That direction matters: a body file edited
 * after posting is the normal way these drift, because the file is where
 * corrections get written first.
 *
 * WHAT IT DOES NOT MEASURE. Whether the body is TRUE. Parity with a wrong file is
 * still parity. Every figure in these bodies has been wrong at least once —
 * bf/parms had two, bf/reads had four — and no gate catches that; only measuring
 * the claim does.
 *
 * READS ONLY, over the network. Skips with exit 0 when gh is unavailable or
 * unauthenticated: a missing credential is not evidence that the bodies agree.
 *
 * Overrides, used by the non-vacuity ablation and by nothing else:
 *   --only <pr>        measure one pull request
 *   --body-dir <path>  read body files from somewhere else
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { REPO_ROOT, report } = require('./_gate');

function argValue(flag, fallback) {
  const at = process.argv.indexOf(flag);
  return at > -1 && process.argv[at + 1] ? process.argv[at + 1] : fallback;
}

const REPO = 'nightscout/cgm-remote-monitor';
const BODY_DIR = argValue('--body-dir',
  path.join(REPO_ROOT, 'reports', 'phase0-pr-bodies'));
const ONLY = argValue('--only', null);

/* Each in-flight cgm-remote-monitor PR and the file it was posted from.
 * PR #8733 is not here: it was opened from a branch this programme did not
 * prepare a body file for. */
const PAIRS = [
  ['8734', 'bf-merge.md'],
  ['8735', 'bf-food.md'],
  ['8736', 'bf-parms.md'],
  ['8737', 'bf-coercion.md'],
  ['8738', 'bf-reads.md'],
  ['8739', 'bf-alarms.md']
].filter(([pr]) => !ONLY || pr === ONLY);

const norm = (s) => s.replace(/\r\n/g, '\n')
                     .split('\n').map((l) => l.replace(/\s+$/, ''))
                     .join('\n').replace(/\n+$/, '');

try {
  execFileSync('gh', ['auth', 'status'], { stdio: 'ignore', timeout: 20000 });
} catch (err) {
  console.log('gate: pr-body-parity');
  console.log('  SKIP  gh unavailable or unauthenticated.');
  console.log('        A missing credential is not evidence that the bodies agree.');
  process.exit(0);
}

const findings = [];

for (const [pr, file] of PAIRS) {
  const local = path.join(BODY_DIR, file);
  if (!fs.existsSync(local)) {
    findings.push({ ok: false, text: `#${pr} — body file missing: ${path.relative(REPO_ROOT, local)}` });
    continue;
  }
  let live;
  try {
    live = execFileSync('gh',
      ['pr', 'view', pr, '--repo', REPO, '--json', 'body', '--jq', '.body'],
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000 });
  } catch (err) {
    findings.push({ ok: false, text: `#${pr} — could not be read: ${String(err.message).split('\n')[0]}` });
    continue;
  }
  const a = norm(live), b = norm(fs.readFileSync(local, 'utf8'));
  findings.push({
    ok: a === b,
    text: a === b
      ? `#${pr} matches ${file}`
      : `#${pr} DIFFERS from ${file} — push it with: `
        + `gh pr edit ${pr} --repo ${REPO} --body-file ${path.relative(REPO_ROOT, local)}`
  });
}

report('pr-body-parity', findings);
