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
 *      out of the released source on `official/master` (15.0.9, c6a0d8ed)
 *      and out of `official/dev`. If a future change makes the name
 *      load-bearing, the prose below becomes wrong in the other direction
 *      and somebody must revisit it. Asserting the prose alone would pin a
 *      claim to nothing. (Until 2026-10-26 the branch side was read from the
 *      bf/auth worktree; that worktree was removed after 15.0.9 shipped the
 *      fix, and the released tree replaces it. On dev the digest line became
 *      `getSubjectHash(readContract.identifier(subject._id))` with #8758's
 *      object-id work; still a function of _id and the enclave key only.)
 *   2. THE PROSE. That every operator-facing document says the two things
 *      that are true (rename is not a rotation; the upgrade does not rewrite
 *      stored rows) and none of them carries the instruction that was wrong.
 *      The 15.0.9 release notes were rewritten as a technical changelog on
 *      2026-10-21 (9ed4a5441, at the maintainers' request) and the rotation
 *      table left with it: the shipped notes say, twice, that copies written
 *      by earlier releases stay in the database until the tokens are rotated,
 *      and name no rotation method. The rename warning and both rotation
 *      options live on in the #8754 PR body, the report and the register,
 *      which this gate still holds to the full text.
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
const { REPO_ROOT, show, report } = require('./_gate');

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
// The released tree and dev spell the derivation differently (dev went through
// #8758's object-id work); both are a function of _id and the enclave key only.
const DERIVE = {
  'official/master (15.0.9)': 'getSubjectHash(subject._id.toString())',
  'official/dev': 'getSubjectHash(readContract.identifier(subject._id))',
};

const master = show('official/master', 'lib/authorization/storage.js');
const dev = show('official/dev', 'lib/authorization/storage.js');

for (const [label, src] of [['official/master (15.0.9)', master], ['official/dev', dev]]) {
  findings.push({
    ok: !!src && src.includes(MATCHER),
    text: `${label}: findSubject matches on the id-derived digest — \`${MATCHER}\``,
  });
  findings.push({
    ok: !!src && src.includes(DERIVE[label]),
    text: `${label}: that digest is derived from _id and the enclave key — \`${DERIVE[label]}\``,
  });
  // The name reaches the token only as the abbrev prefix, which checkToken
  // never reads back. If this line ever stops being how the token is built
  // the whole "a rename is cosmetic" argument has to be re-derived.
  findings.push({
    ok: !!src && /abbrev \+ '-' \+ subject\.digest\.substring\(0, 16\)/.test(src),
    text: `${label}: token is abbrev(name) + "-" + digest16, and only the digest half is matched`,
  });
}

// ---- 2. the prose, per document ------------------------------------------

// The instruction that was wrong, in the shape it actually shipped in.
const RENAME_ROW = /\|\s*\*\*Rename the user\*\*/;

const notes = read(DOCS.notes);
findings.push({
  ok: !!notes && !RENAME_ROW.test(notes),
  text: 'release notes: no "Rename the user" row in the rotation table',
});
// The shipped changelog (9ed4a5441, 2026-10-21) carries the fact in two
// places: the Security entry for #8754 and the Upgrade notes.
findings.push({
  ok: !!notes && /Copies written by earlier releases stay in the database until those tokens are\s+rotated/.test(notes),
  text: 'release notes, Security (#8754): copies written by earlier releases stay until the tokens are rotated',
});
findings.push({
  ok: !!notes && /Access tokens that earlier releases stored in readable form remain in the database until they\s+are rotated/.test(notes),
  text: 'release notes, Upgrade notes: readable-form tokens remain until they are rotated',
});
findings.push({
  ok: !!notes && !/[Rr]enam(e|ing) the (user|subject)[^\n]*(retire|rotat|change)/.test(notes)
             || (!!notes && /not a (rotation|way to retire)/i.test(notes)),
  text: 'release notes: no sentence offers a rename as a way to change or retire a token',
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
  ok: !!rep && /Renaming a subject does not rotate its token/.test(rep),
  text: 'report §2.3: states that a rename is not a rotation, rather than silently dropping the line',
});

const reg = read(DOCS.register);
findings.push({
  ok: !!reg && /A rename is not a rotation/.test(reg),
  text: 'register BF-17: records the corrective fact, since the register is '
      + 'authoritative for defect facts',
});

report('bf17-remediation-note', findings);
