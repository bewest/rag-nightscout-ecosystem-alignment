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
 * trailing newline GitHub appends.
 *
 * THE DIRECTION ASSUMPTION WAS WRONG AND IT WAS THE DANGEROUS KIND OF WRONG.
 * Until 2026-09-21 this comment read "a body file edited after posting is the
 * normal way these drift, because the file is where corrections get written
 * first", and on that assumption every failure printed one remedy:
 * `gh pr edit <pr> --body-file <local>`. Measured on 2026-09-21 across the five
 * failing pairs, the drift runs BOTH ways. #8734, #8735, #8736 and #8737 drift as
 * assumed - identical word counts, and the only differences are documentation
 * paths the local files gained when the docs tree was reorganised into programme
 * subdirectories, so the live bodies cite paths that no longer resolve. #8739 does
 * NOT: the live body is 1640 words to the local file's 1537 and carries whole
 * paragraphs the file has never had - the urgent-severity/notification-delivery
 * distinction and the Alexa and Google Home locale note. Somebody improved that
 * body upstream. Running the remedy this gate used to print would have DELETED
 * their work, and the gate would then have gone green on the loss.
 *
 * So it now reports the direction it measured and suggests an overwrite ONLY when
 * the live side is strictly behind. A gate whose printed remedy can destroy the
 * thing it is checking is worse than no gate.
 *
 * The in-gate signal is coarser than the by-hand check above: it counts lines
 * unique to each side, so an edited line scores on both. That is enough to refuse
 * to print a destructive command, and deliberately not enough to pretend it knows
 * what changed.
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
  ['8739', 'bf-alarms.md'],
  ['8740', 'bf-cache.md'],
  ['8743', 'bf-operators.md']
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
  if (a === b) {
    findings.push({ ok: true, text: `#${pr} matches ${file}` });
    continue;
  }

  /* Which side is ahead? Sets of non-empty normalised lines, and the limit of
   * that is stated rather than hidden: a line that was EDITED counts once on each
   * side, so an edit and an addition-plus-deletion are indistinguishable here.
   * The counts are therefore a triage signal, not a diff. What they are for is
   * deciding whether this gate may print an overwrite command at all. */
  const lines = (t) => new Set(t.split('\n').map((l) => l.trim()).filter(Boolean));
  const A = lines(a), B = lines(b);
  const onlyLive = [...A].filter((l) => !B.has(l)).length;
  const onlyLocal = [...B].filter((l) => !A.has(l)).length;
  const where = `live-only ${onlyLive}, file-only ${onlyLocal}`;

  /* Only when the live side is strictly behind is an overwrite offered. Equal
   * counts are the ambiguous case - typically a line-for-line edit, which is what
   * the docs-path reorganisation produced on #8734..#8737 - and ambiguity does not
   * earn a command that cannot be undone from here. */
  findings.push({
    ok: false,
    text: onlyLive < onlyLocal
      ? `#${pr} DIFFERS from ${file} (${where}) — the file is ahead; overwrite with: `
        + `gh pr edit ${pr} --repo ${REPO} --body-file ${path.relative(REPO_ROOT, local)}`
      : onlyLive > onlyLocal
        ? `#${pr} DIFFERS from ${file} (${where}) — THE LIVE BODY IS AHEAD. Do NOT `
          + `overwrite it; reconcile into ${path.relative(REPO_ROOT, local)} first.`
        : `#${pr} DIFFERS from ${file} (${where}) — same line count each way, so this `
          + `is probably an edit rather than an addition. READ THE DIFF before doing `
          + `anything; no overwrite is suggested, because it could be either.`
  });
}

report('pr-body-parity', findings);
