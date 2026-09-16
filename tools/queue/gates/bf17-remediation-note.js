'use strict';
/*
 * bf17-remediation-note.js  —  BF-17 / P0-C-REMEDIATE
 *
 * BF-17 has no code remediation and will not get one. The maintainer decided
 * on 2026-09-16 that no detector script and no migration would be written:
 * rows already carrying a plaintext token are remediated by ROTATION, which
 * is an operator decision no script can take, and the deliverable is therefore
 * OPERATOR-FACING TEXT. This gate is what stops "the deliverable is text" from
 * meaning "the deliverable is unmeasured".
 *
 * WHY IT EXISTS, CONCRETELY. The text was wrong. The 15.0.9 release notes
 * listed "rename the user" as one of three ways to change an exposed token,
 * and the report §2.3 it was written from listed it too. It is not a rotation:
 *
 *   checkToken splits the presented token on '-', keeps the LAST segment as
 *   `prefix`, and matches
 *     subject.accessTokenDigest.indexOf(accessToken) === 0
 *     || subject.digest.indexOf(prefix) === 0
 *   and `subject.digest` is enclave.getSubjectHash(subject._id) — a function
 *   of _id and the enclave key ONLY. The name contributes the `abbrev` at the
 *   front of the token, which checkToken never reads.
 *
 * So a rename changes what a token looks like and leaves the old one
 * authenticating. An operator who followed that instruction and stopped would
 * believe a leaked credential was retired when it was still live. That is a
 * worse failure than silence, and it survived review in two documents.
 *
 * THIS GATE MEASURES TWO THINGS, and needs both:
 *
 *   1. THE CODE PROPERTY. That the matcher really is name-independent, read
 *      out of the shipping source on `origin/dev` and out of the bf/auth
 *      worktree. If a future change makes the name load-bearing, the prose
 *      below becomes wrong in the other direction and somebody must revisit
 *      it. Asserting the prose alone would pin a claim to nothing.
 *   2. THE PROSE. That every operator-facing document says the two things
 *      that are true (rename is not a rotation; the upgrade does not rewrite
 *      stored rows) and none of them carries the instruction that was wrong.
 *
 * NON-VACUITY. Run `tools/queue/vacuity.py` — with QUEUE_GATE_ROOT pointing at
 * an empty tree every document read returns null and every finding fails.
 * Reintroducing the defect is the direct control: restore the
 * `| **Rename the user**` row to the release notes and the negative check goes
 * BAD on its own, which was reproduced 2026-09-16 before this gate was
 * committed.
 *
 * READS ONLY. `git show` into memory and fs.readFileSync. No checkout, no
 * database, no network. Rule 0 and rule 5.
 */

const fs = require('fs');
const path = require('path');
const { REPO_ROOT, CRM, show, report } = require('./_gate');

function read (rel) {
  try {
    return fs.readFileSync(path.join(REPO_ROOT, rel), 'utf8');
  } catch (e) {
    return null;
  }
}

const DOCS = {
  notes: 'releases/cgm-remote-monitor-15.0.9/release-notes.md',
  prbody: 'reports/phase0-pr-bodies/bf-auth.md',
  report: 'docs/60-research/remedial/bf17-bf30-auth-defects-2026-09-15.md',
  register: 'docs/30-design/remedial/nightscout-backfix-register.md',
};

const findings = [];

// ---- 1. the code property the prose is pinned to -------------------------

const MATCHER = 'subject.digest.indexOf(prefix) === 0';
const DERIVE = 'getSubjectHash(subject._id.toString())';

const dev = show('origin/dev', 'lib/authorization/storage.js');
const branchPath = path.join(REPO_ROOT, 'externals', 'work', 'crm-bf-auth',
                             'lib', 'authorization', 'storage.js');
let branch = null;
try { branch = fs.readFileSync(branchPath, 'utf8'); } catch (e) { branch = null; }

for (const [label, src] of [['origin/dev', dev], ['bf/auth worktree', branch]]) {
  findings.push({
    ok: !!src && src.includes(MATCHER),
    text: `${label}: findSubject matches on the id-derived digest — \`${MATCHER}\``,
  });
  findings.push({
    ok: !!src && src.includes(DERIVE),
    text: `${label}: that digest is derived from _id and the enclave key — \`${DERIVE}\``,
  });
}

// The name reaches the token only as the abbrev prefix, which checkToken
// never reads back. If this line ever stops being how the token is built the
// whole "a rename is cosmetic" argument has to be re-derived.
findings.push({
  ok: !!branch && /abbrev \+ '-' \+ subject\.digest\.substring\(0, 16\)/.test(branch),
  text: 'bf/auth worktree: token is abbrev(name) + "-" + digest16, and only the '
      + 'digest half is matched',
});

// ---- 2. the prose, per document ------------------------------------------

// The instruction that was wrong, in the shape it actually shipped in.
const RENAME_ROW = /\|\s*\*\*Rename the user\*\*/;

const notes = read(DOCS.notes);
findings.push({
  ok: !!notes && !RENAME_ROW.test(notes),
  text: 'release notes: no "Rename the user" row in the rotation table',
});
findings.push({
  ok: !!notes && /Renaming the user is \*\*not\*\* a third way/.test(notes),
  text: 'release notes: says plainly that renaming is not a way to retire a token',
});
findings.push({
  ok: !!notes && /Upgrading does not delete it/.test(notes),
  text: 'release notes: says the upgrade does not remove the stored plain-text copy',
});
findings.push({
  ok: !!notes && /Delete the user and create a new one/.test(notes)
             && /Change your site's `API_SECRET`/.test(notes),
  text: 'release notes: both real rotation options are present',
});
findings.push({
  ok: !!notes && /renaming the user does not retire its/i.test(notes),
  text: 'release notes: the must-do list repeats the rename warning where people skim',
});

const prbody = read(DOCS.prbody);
findings.push({
  ok: !!prbody && /\*\*Renaming is not a rotation\.\*\*/.test(prbody),
  text: 'bf/auth PR body: says plainly that renaming is not a rotation',
});
findings.push({
  ok: !!prbody && /The stored row itself is not rewritten by the upgrade/.test(prbody),
  text: 'bf/auth PR body: does not overclaim that the upgrade clears stored rows',
});
findings.push({
  ok: !!prbody && !/discarded when Nightscout next loads it/.test(prbody),
  text: 'bf/auth PR body: the retracted "discarded when Nightscout next loads it" '
      + 'sentence is gone',
});
findings.push({
  ok: !!prbody && /auth_subjects/.test(prbody),
  text: 'bf/auth PR body: the manual auth_subjects check is present — it is what '
      + 'stands in for the detector script that was decided against',
});

const rep = read(DOCS.report);
findings.push({
  ok: !!rep && !/change the subject's name \(which changes the/.test(rep),
  text: 'report §2.3: the rename-as-rotation option is withdrawn',
});
findings.push({
  ok: !!rep && /CORRECTED 2026-09-16/.test(rep),
  text: 'report §2.3: carries the correction rather than silently dropping the line',
});

const reg = read(DOCS.register);
findings.push({
  ok: !!reg && /A rename is not a rotation/.test(reg),
  text: 'register BF-17: records the corrective fact, since the register is '
      + 'authoritative for defect facts',
});

report('bf17-remediation-note', findings);
