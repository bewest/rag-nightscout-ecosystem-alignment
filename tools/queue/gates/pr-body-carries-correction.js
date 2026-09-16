'use strict';
/*
 * pr-body-carries-correction.js — A TRACKING GATE.
 *
 * It is meant to FAIL while a correction that exists locally has not reached the
 * live pull request body, and to go green when somebody pushes the edit. It is
 * not a defect in any branch.
 *
 * WHY IT EXISTS. #8738's body was posted, and afterwards the plainest question
 * anyone could ask about its headline defect - "does ?count=0 now return zero
 * documents?" - turned up a fact nobody had written down: on dev, ?count=0
 * answers TWO ways. The runtime cache returns 0 rows, which is correct; forced
 * past the cache to the database it returns the whole collection. The posted body
 * states the unbounded answer as though it were the only one, so a reviewer who
 * tries the plain spelling on their own instance sees [] and concludes the
 * premise is wrong.
 *
 * The local body file carries the correction. The live PR does not. The previous
 * record of that was one sentence in a notes: field, which is exactly the shape
 * of thing this programme keeps finding stale. So it is measured instead.
 *
 * READS ONLY, over the network, via `gh`. Skips (exit 0 with a message) when gh
 * is unavailable or unauthenticated, because a missing credential is not evidence
 * that the text is right.
 *
 * Overrides, used by the non-vacuity ablation and by nothing else:
 *   --pr <n>  --needle <string>  --body-file <path>
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { REPO_ROOT, report } = require('./_gate');

function argValue(flag, fallback) {
  const at = process.argv.indexOf(flag);
  return at > -1 && process.argv[at + 1] ? process.argv[at + 1] : fallback;
}

const PR    = argValue('--pr', '8738');
const REPO  = 'nightscout/cgm-remote-monitor';
const BODY  = argValue('--body-file',
  path.join(REPO_ROOT, 'reports', 'phase0-pr-bodies', 'bf-reads.md'));

/* The sentence the correction turns on. Short enough to survive reflowing, long
 * enough that it cannot appear by accident. */
const NEEDLE = argValue('--needle', 'served from the runtime cache');

const checks = [];

let live = null;
try {
  live = execFileSync('gh',
    ['pr', 'view', PR, '--repo', REPO, '--json', 'body', '--jq', '.body'],
    { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000 });
} catch (err) {
  console.log('gate: pr-body-carries-correction (#' + PR + ')');
  console.log('  SKIP  gh unavailable or unauthenticated: ' + String(err.message).split('\n')[0]);
  console.log('        A missing credential is not evidence that the body is correct.');
  process.exit(0);
}

const localText = fs.readFileSync(BODY, 'utf8');

checks.push({
  ok: localText.includes(NEEDLE),
  text: 'the local body file ' + path.relative(REPO_ROOT, BODY) + ' carries the correction'
       + ' (if this fails, the gate is pointed at the wrong file, not at a stale PR)'
});

checks.push({
  ok: live.includes(NEEDLE),
  text: 'the LIVE body of PR #' + PR + ' carries it too'
       + ' — push it with: gh pr edit ' + PR + ' --repo ' + REPO
       + ' --body-file ' + path.relative(REPO_ROOT, BODY)
});

report('pr-body-carries-correction (#' + PR + ')', checks);
