<!--
  ============================================================================
  GENERATED FILE - MUST NOT BE HAND-EDITED.

  Source of truth:  queue/work-queue.yaml
  Generator:        tools/queue/emit_packets.py   (make packets)
  Staleness check:  python3 tools/queue/emit_packets.py --check

  Review NOTES belong on the pull request, not here. This file is a projection
  of the manifest; anything written into it is destroyed by the next run.
  ============================================================================
-->

# Review packet — P0-C (PR #8754)

**bf/auth - BF-17 plaintext token (BF-30 split out to P0-J)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/auth` |
| base | `origin/dev@a8888f0d` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=P0-C` is the measurement |
| semver | `major` |
| register entries | `BF-17` |

## What this changes

Content: 2 commits at ce82f0cd, 3 files, +310/-18.
lib/authorization/endpoints.js, lib/authorization/storage.js,
tests/authsubjects.test.js. Tip 404e714c is a merge of origin/dev 59430336
into ce82f0cd (2026-09-21). The BF-30 throttle work is on bf/throttle (P0-J),
not here.

## Why that semver

GT4: beyond the two fixes, the branch narrows lib/authorization/storage.js to
write only an allow-list of fields (name, roles, notes, created_at), so any
field a third-party admin tool has stored is dropped on the next edit with NO
error. It also adds `notes` to the GET /api/v1/subjects response. The throttle
change alone would be minor - the sleep moved to the failure path, so no
request that authenticates is delayed by another client's failures behind a
shared proxy.

## What an operator would notice

> Two security fixes, not yet merged or released. Editing a subject (an
> access entry on the admin page) writes that subject's API access token
> into the database in readable form, which turns read access to your
> database into API access; with this fix it no longer does. IMPORTANT:
> tokens already written that way stay in your database - fixing the code
> does not remove them (see P0-C-REMEDIATE for what to do). Brute-force
> slowdown on failed logins is keyed on a value the caller can choose, so it
> never engages; the fix makes it engage. Existing access tokens keep
> working - they are re-derived on every load and are not invalidated by
> this change.

## Who should review this, and why

SECURITY - a human security reviewer first, before any other Phase 0 branch.
This is the one the sequencing document singles out.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/auth origin/bf2/auth-hardening || git`** &nbsp;·&nbsp; kind: `static`

bf/auth ships inside PR #8754 (bf2/auth-hardening, queue BF2-AUTH): its tip is
contained in #8754's head, or in origin/dev once #8754 merges. Needs `git -C
externals/cgm-remote-monitor-official fetch origin` first.

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/auth >/dev/null`** &nbsp;·&nbsp; kind: `static`

trial-merge into origin/dev is conflict-free

**`grep -nE "console\\.log\\('Loading',[[:space:]]*opts\\)" lib/authorization/storage.js && exit 1 || exit 0`** &nbsp;·&nbsp; kind: `static` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-auth`

Regression guard for BF-05's sibling: a per-request debug print of request-
derived values, `console.log('Loading',opts)` in storage.js. The pattern is
whitespace-tolerant on purpose - the code has no space after the comma, and a
pattern requiring one never matches, which makes the gate pass on a false
property. Do not narrow it. Green because commit 56ed29d2 removed the line
from bf/auth (maintainer's choice, 2026-09-16), not because the pattern was
weakened.

**`TEST=authsubjects npm run test-single`** &nbsp;·&nbsp; kind: `integration` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-auth`

BF-17. Not in either local script. 8 passing with MongoDB; 1 passing / 7
failing with the fix ablated.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- `npm run test:unit` is not evidence for this branch: its 44-file brace
  list contains neither of the two test files bf/auth adds, so the suite
  could pass in full with every one of these fixes reverted.
- Nothing here checks that plaintext tokens ALREADY written into existing
  databases get cleaned up, and nothing will: the code fix does not remove
  them, there is no migration, and by decision (2026-09-16) there is no
  detector script. What is measured is next door - P0-C-REMEDIATE's gate
  checks that this branch's PR body and the release notes tell an operator
  the truth about it, including that a rename is not a rotation. Read that
  item before signing this one off.
- One conflict with PR #8605 remains and it is this branch's own -
  lib/authorization/storage.js, which the modernization branch also narrows,
  for different reasons. Measured 2026-09-16: bf/auth against
  origin/chore/nightscout-modernization conflicts in that one file and
  nothing else (the four other conflicts were the BF-30 peer plumbing, which
  is why that half became P0-J). Not gated, because resolving it is a merge
  somebody has to sit down and do, and which side wins depends on whether
  the allow-list lands at all.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-auth.md`](../../reports/phase0-pr-bodies/bf-auth.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Not shipping on its own. bf/auth (content ce82f0cd, tip 404e714c, a merge of
dev 59430336 made 2026-09-21) is contained by ancestry in bf2/auth-hardening,
PR #8754 (BF2-AUTH), which is what ships these fixes in 15.0.9. bf/auth will
not be pushed or merged up on its own; its first gate checks that containment
(in #8754's head b5f61f19, measured 2026-09-24). Review and the remaining work
are on BF2-AUTH. Decisions: - 2026-09-23 (maintainer): the security reviewers
are the maintainer and Andy (a connector maintainer). - 2026-09-16
(maintainer): commit 56ed29d2 removes the leftover
console.log('Loading',opts). The line is on origin/dev at storage.js:84, not
introduced here; it is taken because this branch already rewrites the file and
it is the same defect class as the count-path filter leak fixed on bf/reads. -
2026-09-16 (maintainer): remediation for tokens already stored in plaintext is
text, not tooling (P0-C-REMEDIATE): no detector, no migration, rotation
instructions in the PR body and the 15.0.9 release notes, including that
renaming a subject is not a rotation because the matcher is name-independent.
Sequencing letter C. GT3 found BF-17's created_at residual: the pick() at
endpoints.js:44 is ['_id','name','accessToken','roles','notes']; notes was
added by the fix, created_at was not. FU-RESIDUALS follow-up 4 is carried by
this branch and so by #8754; it is fixed (on a branch), not merged, and FU-
RESIDUALS' gate, which reads origin/dev, correctly still fails. Green gates
here do not mean an operator is safe: tokens written in plaintext before the
upgrade are untouched by it. The 2026-09-21 merge-up was measured rather than
trusted to merge-tree (the register's BF-04 detail records a clean merge-tree
that hid a semantic collision). Only lib/authorization/storage.js is touched
by both sides, in different functions: dev's 06b133a7 (BF-01) replaces the
limit() helper on the read path, while this branch narrows save() to a field
allow-list. TEST=authsubjects 8 passing at ce82f0cd and at 404e714c; full
suite 2319 passing, 3 pending, 0 failing at 404e714c against mongod 7.0.43
started with --ulimit nofile=64000:64000. At Docker's default descriptor limit
mongod dies mid-suite (BF-10) and every later timeout looks like a regression.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-C` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
