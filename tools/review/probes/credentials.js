#!/usr/bin/env node
'use strict';
/*
 * credentials.js — #8741 wip/dtschida/env-credential-coercion.
 *
 * `findExtendedSettings` in lib/server/env.js converts any plugin setting that
 * "looks numeric" with `if (!isNaN(value)) { value = Number(value); }`. For a
 * credential that is not a normalisation, it is a CHANGE OF VALUE: the string
 * the operator typed is not the string that reaches the service.
 *
 * MEASURED 2026-09-17, in-process, no network and no real credentials:
 *
 *   setting               BASE a8888f0d          pr8741 97bb005c
 *   --------------------  ---------------------  ----------------------
 *   BRIDGE_USER_NAME      15551234567  (number)  "15551234567" (string)
 *   BRIDGE_PASSWORD       7700         (number)  "007700"      (string)
 *
 * The password arm is the one to look at. `007700` becomes `7700`: two leading
 * characters are silently deleted from a credential. The login then fails, the
 * operator is told only that their password is wrong, and nothing anywhere
 * reports that Nightscout changed it.
 *
 * WHY THIS PROBE IS IN-PROCESS. The refuters established that the HTTP route
 * to this defect is not usable as a gate: with the connector's source at
 * AUTH_DEFAULT_ROLES=denied the FIXED build is stuck red for an unrelated
 * reason, and with the source readable the pull succeeds anonymously so the
 * credential is never exercised at all. The env.js surface is deterministic,
 * needs no second instance, and measures exactly the thing the PR changes.
 *
 * NOT COVERED: whether a real Dexcom Share login then succeeds. That needs
 * live credentials and is out of scope for this harness. See plan §7.
 */

const path = require('path');
const { execFileSync } = require('child_process');
const { report } = require(path.resolve(__dirname, '..', '..', 'queue', 'gates', '_gate.js'));

const CASES = [
  { env: 'BRIDGE_USER_NAME', plugin: 'bridge', key: 'userName', value: '15551234567',
    why: 'a Dexcom account name that is a phone number' },
  { env: 'BRIDGE_PASSWORD', plugin: 'bridge', key: 'password', value: '007700',
    why: 'a password with leading zeros — the destructive case' },
];

// A genuinely numeric, NON-credential setting. It must still become a Number
// on both builds, or the fix has over-reached and broken every numeric plugin
// option. Set explicitly: an unset key yields undefined on both sides and the
// guard would compare undefined to undefined, which measures nothing.
const NUMERIC_GUARD = { env: 'BRIDGE_MAX_FAILURES', plugin: 'bridge', key: 'maxFailures', value: '3' };

// Runs env.js inside a worktree and reports the type and value it produced.
//
// Two things this gets right that cost a debugging cycle each:
//  - With `node -e SCRIPT a b c`, process.argv is [execPath, 'a', 'b', 'c'].
//    There is NO script path at argv[1], so the worktree is argv[1] and the
//    key=value pairs start at argv[2], not argv[2]/argv[3].
//  - env.js writes "API_SECRET has N bits of entropy" to STDOUT, which lands
//    in the middle of the JSON. The payload is fenced with a sentinel and the
//    fence is extracted rather than the whole stream parsed.
const SENTINEL = '@@NSREVIEW@@';
const LOADER = `
process.env.MONGODB_URI='mongodb://127.0.0.1:1/probe';
process.env.API_SECRET='aaaaaaaaaaaaaaaa';
process.env.ENABLE='bridge connect';
for (const kv of process.argv.slice(2)) {
  const i = kv.indexOf('='); process.env[kv.slice(0, i)] = kv.slice(i + 1);
}
const env = require(process.argv[1] + '/lib/server/env.js')();
process.stdout.write('${SENTINEL}' + JSON.stringify(env.extendedSettings || {}) + '${SENTINEL}');
`;

function settingsFor(worktree) {
  const out = execFileSync(process.execPath,
    ['-e', LOADER, worktree].concat(
      CASES.concat([NUMERIC_GUARD]).map(c => `${c.env}=${c.value}`)),
    { cwd: worktree, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
  const a = out.indexOf(SENTINEL), b = out.lastIndexOf(SENTINEL);
  if (a < 0 || b <= a) throw new Error(`no payload from ${worktree}: ${out.slice(0, 200)}`);
  return JSON.parse(out.slice(a + SENTINEL.length, b));
}

function main() {
  const a = process.argv.slice(2);
  const get = k => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : null; };
  const baseWt = get('--base-worktree');
  const candWt = get('--candidate-worktree');
  if (!baseWt || !candWt) {
    console.error('need --base-worktree and --candidate-worktree');
    process.exit(2);
  }

  const base = settingsFor(baseWt);
  const cand = settingsFor(candWt);
  const findings = [];

  for (const c of CASES) {
    const bv = ((base[c.plugin] || {})[c.key]);
    const cv = ((cand[c.plugin] || {})[c.key]);
    const label = `${c.env} (${c.why})`;

    // CANDIDATE: the value must survive as the exact string the operator typed.
    findings.push({
      ok: cv === c.value,
      text: `[discriminates] ${label}: CANDIDATE ${JSON.stringify(cv)} (${typeof cv}) — typed ${JSON.stringify(c.value)}`,
    });
    // CONTROL: BASE must mangle it, or this arm proves nothing.
    const baseMangled = bv !== c.value;
    findings.push({
      ok: true,
      text: `[discriminates] ${label}: CONTROL   BASE ${JSON.stringify(bv)} (${typeof bv}) — ${baseMangled ? 'RED (value changed)' : 'GREEN'}`,
    });
    if (!baseMangled) {
      findings.push({
        ok: false,
        text: `[discriminates] ${label}: UNINFORMATIVE — BASE preserved this value too, so the arm measured nothing`,
      });
    }
  }

  // Over-correction guard: genuinely numeric, non-credential settings must
  // still become numbers, or the fix has broken every numeric plugin option.
  const bInt = (base[NUMERIC_GUARD.plugin] || {})[NUMERIC_GUARD.key];
  const cInt = (cand[NUMERIC_GUARD.plugin] || {})[NUMERIC_GUARD.key];
  findings.push({
    ok: cInt === 3 && bInt === 3,
    text: `[invariant] ${NUMERIC_GUARD.env}=3 still coerces to a number on both: BASE ${JSON.stringify(bInt)} (${typeof bInt}), CANDIDATE ${JSON.stringify(cInt)} (${typeof cInt})`,
  });

  report('credentials (#8741, env.js credential coercion)', findings);
}

main();
