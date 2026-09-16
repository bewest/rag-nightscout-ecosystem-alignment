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

# Review packet — P0-E (PR #8738)

**bf/reads - PR #8738, six read-path fixes, independent of bf/coercion**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/reads` |
| base | `origin/dev@a8888f0d` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=P0-E` is the measurement |
| semver | `major` |
| register entries | `BF-01`, `BF-05`, `BF-13`, `BF-14`, `BF-15`, `BF-33` |

## What this changes

6 commits at 2ecfeb53, all its own, based directly on origin/dev.
lib/server/aggregate.js, entries.js and four siblings,
lib/api3/generic/search/input.js, lib/api3/shared/fieldsProjector.js,
lib/api3/generic/collection.js, lib/server/count.js, lib/api/index.js.

## Why that semver

GT4: six previously-accepted ?count= spellings now return 400, not two, and
the validator is app.use'd on the WHOLE v1 app before every router - so it
covers /treatments, /profile, /devicestatus, /notifications, /activity, /food,
/status, /alexa, /googlehome, and WRITES as well as reads. A POST
/api/v1/treatments?count=0 now returns 400 where it previously succeeded. The
branch CHANGELOG lists read routes only.

## What an operator would notice

> Six fixes to how the API answers read requests. Counting entries that
> matched a filter returned nothing at all; paging through results could
> skip or repeat records; asking for a nested field returned an empty
> answer; and three different ways of asking for "no limit" returned the
> entire collection instead. CHANGE YOU MAY NOTICE: six spellings of ?count=
> that used to be accepted now return an error instead of a surprising
> answer - count=0, count=0x10, count=2.5, count=-3, count=1e2 and
> count=abc. If a script of yours uses one of those, it will now fail loudly
> instead of quietly returning the wrong number of records.

## Who should review this, and why

maintainer. OPENED 2026-09-16 as PR #8738, base dev. NOT after P0-D - the
stack is dissolved and the two branches merge cleanly with each other. Three
things a reviewer cannot get from the diff: it is graded major on one commit
only (06b133a7, the ?count= tightening, which is app.use'd ahead of every v1
router and so covers writes); none of the five test files is in `npm run
test:unit`, so a green run there is evidence for none of the six fixes; and
?count=0 answered TWO different ways on dev depending on whether the runtime
cache could serve the request - see notes. maintainer. NOT after P0-D - the
stack is dissolved and the two branches merge cleanly with each other.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/reads`** &nbsp;·&nbsp; kind: `static`

bf/reads has not fallen behind origin/dev. THIS REPLACES an is-ancestor check
on bf/coercion. The two-deep stack existed only to resolve a CHANGELOG
collision; the CHANGELOG edits were stripped by the maintainer's instruction
and bf/reads was re-cut directly onto dev, so the old gate now measures a fact
that is deliberately false.

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/reads >/dev/null`** &nbsp;·&nbsp; kind: `static`

trial-merge into origin/dev is conflict-free

**`node tools/queue/gates/bf-reads-read-contract.js`** &nbsp;·&nbsp; kind: `static`

THE GATE THAT WAS HERE was `git log --format=%H bf/reads | grep -q .`, which
asserts the branch has at least one commit. The E3 audit ran it against
origin/dev, origin/master and bf/alarms and it passed for all three. This
replaces it with the database-free half of the branch's behaviour, driven
through the four pure modules the six fixes live in:
parseCount/hasCount/applyCount, the dotted-?fields= projector, the _id
tiebreak in the v3 sort chain, and the count path's use of query_for with
nothing printed. 8 assertions. Its own negative control is built in - `--rev
origin/dev` runs the identical assertions against dev materialised from the
object database and gives 4 failing.

**`TEST=api.count-parameter npm run test-single`** &nbsp;·&nbsp; kind: `integration` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-reads`

BF-13/BF-33, 13 passing. CORRECTION TO THE E3 BRIEF, which said this runs "in
2 seconds with no database": it needs MongoDB. Pointed at a dead port it goes
to 0 passing / 1 failing, timing out in the before-all hook. It is fast only
because a mongod happens to be listening on crm-bf-reads' port 27032.

**`TEST=api.count-where npm run test-single`** &nbsp;·&nbsp; kind: `integration` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-reads`

BF-01, 5 passing. Needs MongoDB.

**`TEST=api3.fields npm run test-single`** &nbsp;·&nbsp; kind: `integration` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-reads`

BF-15, 6 passing. Needs MongoDB (5 of 6 survive without it).

**`TEST=api3.limit npm run test-single`** &nbsp;·&nbsp; kind: `integration` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-reads`

BF-33, 8 passing. Needs MongoDB.

**`TEST=api3.paging npm run test-single`** &nbsp;·&nbsp; kind: `integration` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-reads`

BF-14, 3 passing. Needs MongoDB.

**`git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/reads | grep -q 2ecfeb53ff1e6121ef5f7`** &nbsp;·&nbsp; kind: `network`

the branch behind PR #8738 is on the remote at the exact tip this item was
measured against. Read-only. Verified 2026-09-16.

**`node tools/queue/gates/pr-body-parity.js --only 8738`** &nbsp;·&nbsp; kind: `network`

the live body of PR #8738 still matches the file it was posted from. Bodies
drift in one direction - a correction gets written into the file first - and
the only previous record that one was owed was a sentence in a notes: field,
which is what let #8738 stay wrong in public for a day. It does NOT measure
whether the body is TRUE: parity with a wrong file is still parity, and every
figure in these bodies has been wrong at least once. NON-VACUITY, reproduced
2026-09-16: one altered file gives 1 failing, an empty body dir gives 6
failing. SKIPS with exit 0 when gh is unauthenticated.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- THE `npm run test:unit` GATE WAS REMOVED, not downgraded. It was recorded
  as "361 passing / 0 failing at GT1's measurement", but not one of the five
  test files this branch adds is in the 44-file brace list - all five are
  api*/api3* and match test:integration's glob - so the suite could have
  passed in full with every fix reverted.
- The ordering constraint inside the branch (BF-05's commit must follow
  BF-01's) is not machine-checked. After the CHANGELOG strip and the re-cut
  onto dev the two commits are 3b588098 and 4772b983, so any gate quoting an
  earlier SHA is stale by construction. A real gate would assert the
  relative order of the two by subject line, and nobody has written it.
- The CHANGELOG on this branch lists read routes only, while the ?count=
  validator covers writes too. Nothing checks a release note against the
  code it describes.
- Review and merge state of PR #8738 is upstream's, and cannot be gated from
  here without a GitHub API call. Tracked, not driven.
- THE TWO-PATH BEHAVIOUR OF ?count=0 IS MEASURED BUT NOT ASSERTED.
  tools/probes/count0-two-paths.js reproduces it - 0 rows from the cache and
  all 24 from the database on dev, 400 on both after this branch, with two
  controls that stay sane on each tree - but it PRINTS rather than exits
  non-zero, so it is a probe and not a gate. Making it one means deciding
  what the contract IS, and that is the reviewer's call on #8738, not this
  queue's. It also needs two worktrees and a mongod.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-reads.md`](../../reports/phase0-pr-bodies/bf-reads.md)
- [`docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`](../../docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md)
- [`docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`](../../docs/60-research/modernization/gt4-semver-classification-2026-09-15.md)
- [`docs/60-research/remedial/e3-gate-vacuity-audit-2026-09-15.md`](../../docs/60-research/remedial/e3-gate-vacuity-audit-2026-09-15.md)

## Notes carried on the item

THE CORRECTION IS PUSHED. #8738's body carried the wrong account of ?count=0
for a day - it said the whole collection, which is true only past the runtime
cache; the plain spelling returns 0 rows and is correct. Edited 2026-09-16 and
the parity gate above is green. The state question this raised is settled and
worth keeping: while the gate was red this item reported FAIL and the state
stayed in-flight-upstream, because the manifest's gate-not-met rule was
written for a red gate meaning a DEFECT IN THE CODE, and here the branch was
fine and the PROSE was stale. Those are different questions and the state
model does not separate them. --- MEASURED 2026-09-16, AFTER THE PR WAS
POSTED, and the PR body is wrong about it: `?count=0` answered TWO different
ways on dev depending on the path. With no `find`, the runtime cache served it
and returned 0 rows - which is what the client asked for and is CORRECT. With
a `find` that forces the read past the cache to the database, `.limit(0)`
means unbounded and it returned all 24 of 24. Both measured against dev
a8888f0d with 24 stored entries, controls sane (count=5 -> 5 rows, no count ->
10, the default). The read-defects report has the 24-row half and says it
forced past the cache; nobody wrote down the other half, so the PR body states
the unbounded answer as if it were the only one. A reviewer who tests plain
`?count=0` on their own instance sees `[]` and concludes the premise is wrong.
Correction prepared in the body file, NOT yet pushed to #8738. --- Sequencing
letter E. THE SHA HISTORY, because three documents quote different ones: GT1
measured 824380a0 (7 commits, on dev); this queue first recorded 0d19bb31 (8
commits, on bf/coercion, after a rebase); the CHANGELOG-only commit was then
dropped and the branch re-cut directly onto origin/dev, and it is now
2ecfeb53, 6 commits. `git range-diff` showed all six content-identical to
their pre-strip selves. THE STACK IS DISSOLVED, so blocks_on is empty. The §3b
concern survives and is NOT a merge hazard: bf/coercion gives query.js a new
`collection:` option and bf/reads fixes aggregate.js, which calls query.js
through api.query_for and passes no options - so the count path still gets the
legacy default walker after both land. Deliberately in neither PR.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-E` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
