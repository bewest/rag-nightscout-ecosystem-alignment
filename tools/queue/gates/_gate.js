'use strict';
/*
 * _gate.js — the tiny contract every queue gate obeys.
 *
 * A gate is a MEASUREMENT with an exit code. It exits 0 when the property it
 * names holds and 1 when it does not, and it prints enough for a human to see
 * what was measured either way. It never prints "OK" without having looked.
 *
 * Gates live here as Node rather than Python (which is what `emit.py` and
 * `status.py` are) for one reason: several of them have to `require()` or
 * execute a shipping module by path to measure it, which is the convention
 * already established by the `tools/qc/*-arm.js` harnesses.
 *
 * NOTHING IN HERE MAY WRITE TO A SHIPPING CHECKOUT OR A WORKTREE. Gates read.
 * `git show` into memory, never `git checkout`. Rule 0 and rule 5.
 */

const { execFileSync } = require('child_process');
const path = require('path');

// QUEUE_GATE_ROOT lets a NEGATIVE CONTROL point a gate at a different tree —
// an empty directory, or a copy of the repository with the property this gate
// asserts deliberately broken. Without it there is no way to ask a
// file-reading gate "would you still pass if your inputs were not there?", and
// a gate nobody can ask that question of is a gate nobody can trust.
// See tools/queue/vacuity.py and tools/queue/gates/empty-root-control.sh.
const REPO_ROOT = process.env.QUEUE_GATE_ROOT
  ? path.resolve(process.env.QUEUE_GATE_ROOT)
  : path.resolve(__dirname, '..', '..', '..');
const CRM = path.join(REPO_ROOT, 'externals', 'cgm-remote-monitor-official');

function show(ref, file, repo) {
  // Read a file out of a git object database without touching any working
  // tree. Returns null when the path does not exist at that ref, which is
  // itself frequently the measurement.
  try {
    return execFileSync('git', ['-C', repo || CRM, 'show', `${ref}:${file}`],
                        { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024,
                          stdio: ['ignore', 'pipe', 'ignore'] });
  } catch (e) {
    return null;
  }
}

function git(args, repo) {
  return execFileSync('git', ['-C', repo || CRM].concat(args),
                      { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 }).trim();
}

/*
 * report(name, findings)
 *
 * `findings` is a list of { ok, text }. The gate fails if ANY finding is not
 * ok. Every finding is printed regardless, because a gate that prints only
 * its failures cannot be checked for vacuity — you could not tell a gate that
 * examined forty things and liked them all from a gate that examined nothing.
 */
function report(name, findings) {
  console.log(`gate: ${name}`);
  let bad = 0;
  for (const f of findings) {
    if (!f.ok) bad += 1;
    console.log(`  ${f.ok ? 'ok  ' : 'BAD '} ${f.text}`);
  }
  console.log(`  ${findings.length} checked, ${bad} failing`);
  if (findings.length === 0) {
    // A gate with nothing to say has not measured anything, and must not be
    // read as a pass. This is the vacuity trap in its purest form.
    console.log('  VACUOUS: this gate examined nothing. Treating as failure.');
    process.exit(1);
  }
  process.exit(bad ? 1 : 0);
}

module.exports = { REPO_ROOT, CRM, show, git, report };
