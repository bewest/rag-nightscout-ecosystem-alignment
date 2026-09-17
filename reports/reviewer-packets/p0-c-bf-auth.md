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

# Review packet — P0-C

**bf/auth - BF-17 plaintext token (BF-30 split out to P0-J)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/auth` |
| base | `origin/dev@a8888f0d` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=P0-C` is the measurement |
| semver | `major` |
| register entries | `BF-17` |

## What this changes

2 commits at ce82f0cd, 3 files, +310/-18. lib/authorization/endpoints.js,
lib/authorization/storage.js, tests/authsubjects.test.js. SPLIT 2026-09-16 -
the BF-30 throttle commit that used to sit underneath this one is now P0-J on
bf/throttle, and the old tip 56ed29d2 no longer exists.

## Why that semver

GT4: beyond the two fixes, the branch narrows lib/authorization/storage.js to
write only an allow-list of fields (name, roles, notes, created_at), so any
field a third-party admin tool has stored is dropped on the next edit with NO
error. It also adds `notes` to the GET /api/v1/subjects response. The throttle
change alone would be minor - the sleep moved to the failure path, so no
request that authenticates is delayed by another client's failures behind a
shared proxy.

## What an operator would notice

> Two security fixes. Editing a subject through the admin page used to write
> that subject's API access token into the database in readable form, which
> turned read access to your database into API access; it no longer does.
> IMPORTANT: tokens already written that way are still in your database -
> fixing the code does not remove them. Brute-force slowdown on failed
> logins was keyed on a value the caller could choose, so it never engaged;
> it now is. Existing access tokens keep working - they are re-derived on
> every load and are not invalidated by this change.

## Who should review this, and why

SECURITY - a human security reviewer first, before any other Phase 0 branch.
This is the one the sequencing document singles out.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/auth`** &nbsp;·&nbsp; kind: `static`

bf/auth has not fallen behind origin/dev

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/auth >/dev/null`** &nbsp;·&nbsp; kind: `static`

trial-merge into origin/dev is conflict-free

**`grep -nE "console\\.log\\('Loading',[[:space:]]*opts\\)" lib/authorization/storage.js && exit 1 || exit 0`** &nbsp;·&nbsp; kind: `static` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-auth`

BF-05's unfixed sibling, a TRACKING gate: it is meant to FAIL while the
residual is present, and the describe it replaces said so in as many words. IT
DID NOT FAIL. The pattern was `console.log('Loading', opts)` with a space
after the comma; the code at storage.js:113 has NO space, so the grep never
matched, the `|| exit 0` arm fired, and P0-C reported 3/3 PASS on a property
that is false. The pattern is now whitespace-tolerant and this gate is red,
which is the honest reading. DO NOT loosen the pattern again. SETTLED
2026-09-16: of the two ways to green this gate offered, the maintainer chose
the first - the one-line removal was taken onto bf/auth as commit 56ed29d2,
and the gate is green because the residual is gone, not because the pattern
was weakened. The gate stays as a regression guard.

**`TEST=authsubjects npm run test-single`** &nbsp;·&nbsp; kind: `integration` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-auth`

BF-17, same story: not in either local script, 8 passing with MongoDB, and 1
passing / 7 failing under the same ablation.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- `npm run test:unit` was here and was recorded as "361 passing / 0 failing
  at GT1's measurement". That number is not evidence for this branch: the
  44-file brace list contains NEITHER of the two test files bf/auth adds, so
  the suite could pass in full with every one of these fixes reverted.
- Nothing here checks that the plaintext tokens ALREADY written into
  existing databases get cleaned up, and nothing will: the code fix does not
  remove them, there is no migration, and as of 2026-09-16 there
  deliberately is no detector script either. What DOES exist is measured
  next door - P0-C-REMEDIATE's gate checks that this branch's PR body and
  the release notes tell an operator the truth about it, including that a
  rename is not a rotation. Read that item before signing this one off; this
  marker is the honest half of the pair.
- ONE CONFLICT WITH PR #8605 REMAINS AND IT IS THIS BRANCH'S OWN -
  lib/authorization/storage.js, which Andy's branch also narrows, for
  different reasons. Measured 2026-09-16 after the split: bf/auth against
  origin/chore/nightscout-modernization conflicts in that one file and
  nothing else. BEFORE THE SPLIT IT WAS FIVE, and the other four were the
  BF-30 peer plumbing alone, which is why that half was re-cut without it -
  see P0-J. Not gated, because resolving it is a merge somebody has to sit
  down and do and which side wins depends on whether the allow-list lands at
  all.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-auth.md`](../../reports/phase0-pr-bodies/bf-auth.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Sequencing letter C. GT3 also found BF-17's created_at residual: the pick() at
endpoints.js:44 is ['_id','name','accessToken','roles','notes'] - notes was
added by the fix, created_at was not. RESOLVED 2026-09-16: commit 56ed29d2
removes the leftover console.log('Loading',opts), the last failing gate, and
all 3 runnable gates now pass. That line was NOT introduced by this branch -
it is on origin/dev at storage.js:84 - and it was taken here rather than left
to FU-RESIDUALS because it sits in a file this branch already rewrites and is
the same defect class as the count-path filter leak fixed on bf/reads: a per-
request debug print of request-derived values. FU-RESIDUALS follow-up 4 is
carried BY THIS BRANCH and should not be fixed there a second time - but it is
NOT yet closed on dev, and FU-RESIDUALS' gate correctly still fails, because
that gate reads origin/dev and the repair only exists on bf/auth until this
merges. Same convention as the register's `fixed`: repaired on a branch, not
merged. THE REAL RISK ON THIS ITEM, RESTATED 2026-09-16: both no-gate markers
still stand and green gates here still do not mean an operator is safe -
tokens written in plaintext before the upgrade are untouched by it. What
changed is that the remediation is no longer unwritten. P0-C-REMEDIATE is
settled as TEXT, not tooling: no detector and no migration, the rotation
instructions carried by this branch's PR body and the 15.0.9 release notes,
and a gate guarding what they say. That review found the instructions were
WRONG - they listed renaming a subject as a rotation, which it is not, because
the matcher is name-independent. Corrected. So the sentence a reviewer needs
when this PR goes up is not "remediation is missing" but "remediation is a
note, the note was wrong once, and here is the gate that says it is right
now".

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-C` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
