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

# Review packet — P0-K (PR #8743)

**bf/operators - PR #8743, BF-04 extracted, BF-70 found**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/operators` |
| base | `origin/dev@fdd08706` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=P0-K` is the measurement |
| semver | `minor` |
| register entries | `BF-04`, `BF-70` |

## What this changes

3 commits at 52b7b640. New: lib/storage/assert-no-query-javascript.js,
lib/server/query-operator-allowlist.js, lib/api/shared/query-error.js and
three test files. Modified: lib/server/query.js, lib/server/aggregate.js, the
five v1 API modules, both swagger files. OVERLAPS bf/reads on
lib/server/aggregate.js - the only Phase 0 branch it conflicts with;
resolution written out in the report §4.2 and measured.

## Why that semver

It removes reachable behaviour - $expr on /profiles/ and the undocumented
pipeline parameter - so it is not a patch by the project's own reading. It is
not major either: no route is removed, no required input is added, no
documented contract breaks, and the census of 14 client projects found zero
senders of anything now refused. $type RESOLVED 2026-09-18, and the resolution
reversed this item's earlier position. The allowlist refused $type, and this
field recorded the collision with PR #8737 as the maintainer's call, taken by
nobody. #8737 then MERGED, which settled it: readTypeOperand() is on dev
because find[sgv][$type]=2 must arrive as the number 2 or the request becomes
an HTTP 500, measured against mongod 3.6.8 and 7.0.43. Refusing $type would
regress a fix that landed a week earlier to gain nothing - it executes nothing
and reads nothing outside the document. $type is now ALLOWED and is the one
departure from the storage seam's set; the cost is priced, not discovered:
when the seam lands its AST needs a $type node or v1 narrows by one operator
then. $not and $text stay refused - both were FIXTURES in #8737's tests rather
than subjects, and their assertions are rewritten, not deleted.

## What an operator would notice

> Nightscout's older API let a web address ask the database to run
> JavaScript, and let one particular address ask questions about parts of
> the database it had no business reading - including, on a default setup,
> without any password or token. Both are closed. What you may notice: a
> filter using an unusual option now answers with a clear error instead of
> appearing to work, and the "count" address no longer accepts a `pipeline`
> setting, which was never documented and which no known app uses. Ordinary
> filters - date ranges, event types, glucose thresholds - are unchanged.
> Your stored data is not touched. Nightscout is not a medical device and
> this is not medical advice; if a report or app you rely on starts showing
> an error after this lands, it is telling you the request was malformed,
> not that your data is gone.

## Who should review this, and why

MAINTAINER. OPENED 2026-09-18 as PR #8743, base dev, and MERGED UP to dev
fdd08706 the same day. Three things the reviewer should be told rather than
left to find: (1) THIS DOES NOT CLOSE THE REPORTED NoSQL-INJECTION ADVISORY.
Of its three PoCs only $where is refused; the date-window bypass
find[dateString][$ne]=x - the full-history PHI dump, the advisory's own
primary evidence - and the $regex extraction both still work, MEASURED on the
merged tip. An allowlist structurally cannot close the first: $ne is an
ordinary comparison every client sends, and the defect is in where
enforceDateFilter() applies its bound. Against the advisory's five remediation
items this does 1 and 2, not 3, 4 or 5. The PR body says so above the
mechanism, not in a footnote. (2) BF-70 has NO advisory of its own. It is a
second unauthenticated read path with the same reachability, and the advisory
covers find[...] only. (3) The $type question this item used to hold open is
CLOSED - see semver_reason.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor a8888f0d bf/operators`** &nbsp;·&nbsp; kind: `static`

bf/operators has not fallen behind the dev tip it was cut from

**`TEST=mongo-query-javascript npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-operators`

BF-04, the JavaScript half. 23 passing, 49 ms, no database. ABLATED on the dev
merge - commenting out the create() call gives 7 failing, confirmed applied by
grep before the run. IT WAS 14 BEFORE THE MERGE AND THE DROP IS A FINDING: the
allowlist also refuses $where, as an unlisted operator with the generic
message, so the 7 are the cases asserting the SPECIFIC JavaScript wording.
This guard is now mostly about the message, not the refusal.

**`TEST=api-v1-operator-allowlist npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-operators`

BF-04, the allowlist. 63 passing + 16 pending without a database; the 16 are
the end-to-end section, which is the only place the ALLOWED operators are
proved to still SELECT rather than merely to pass the guard. ABLATED two ways,
both confirmed applied by grep - removing the create() call gives 14 failing,
making refuse() return instead of throwing gives 35.

**`TEST=api-v1-count-pipeline npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-operators`

BF-70. 8 passing, 30 ms, no database. ABLATED - restoring the two lines the
commit changes gives 3 failing.

**`TEST=api-v1-operator-allowlist npm run test-single`** &nbsp;·&nbsp; kind: `integration` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-operators`

the same file with CUSTOMCONNSTR_mongo set - 79 passing, mongod 7.0 on port
27018, re-measured on the dev merge 9745cae2. This is the run that matters:
without a database the end-to-end section skips and the suite proves only that
refusals refuse.

**`git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/operators | grep -q .`** &nbsp;·&nbsp; kind: `network` &nbsp;·&nbsp; cwd: `.`

the branch behind PR #8743 is on the remote. Read-only. The tip is
deliberately NOT pinned to a sha here: this branch merges dev forward while it
is open, so a pinned tip would go red on every merge-up and say nothing about
correctness.

**`node tools/queue/gates/pr-body-parity.js --only 8743`** &nbsp;·&nbsp; kind: `network` &nbsp;·&nbsp; cwd: `.`

the live body of PR #8743 still matches the file it was posted from. Bodies
drift in one direction - a correction gets written into the file first. It
does NOT measure whether the body is TRUE. This body has already been
corrected once, when #8737 merging reversed the $type decision. SKIPS with
exit 0 when gh is unauthenticated.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- THE STRONGEST CONTROL THIS BRANCH HAS IS NOT RUNNABLE FROM HERE, and
  saying so is the point. The BF-70 reproduction extracts a seeded value
  over unauthenticated HTTP on a8888f0d and extracts nothing on 52b7b640 -
  same machine, same database, same session, same unmodified probe. It is
  deliberately NOT committed: this repository is public and the defect is
  live on the shipping release. A gate that ran it would have to carry it.
  Held outside version control; see the register's BF-70 detail before
  reconstructing it.
- `npm test` over the whole suite is 2223 passing / 3 pending / 0 failing on
  the dev merge 9745cae2 with a live mongod. Not a gate because it needs a
  database on a port other sessions share, and because a whole-suite number
  says nothing about WHICH assertion covers this branch - the three TEST=
  gates above do.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-operators.md`](../../reports/phase0-pr-bodies/bf-operators.md)
- [`docs/60-research/remedial/bf04-bf70-operator-allowlist-2026-09-18.md`](../../docs/60-research/remedial/bf04-bf70-operator-allowlist-2026-09-18.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/60-research/tenancy/v1-operator-census-2026-09-14.md`](../../docs/60-research/tenancy/v1-operator-census-2026-09-14.md)

## Notes carried on the item

Sequencing letter K. This item exists because a reader asked whether PR #8737
disallows $where and other dangerous operators. It does not and was never
meant to - $where is in that branch's NON_VALUE_OPERATORS table as an
exemption from type conversion, not a refusal - and answering the question
required measuring what API v1 actually carries, which is BF-04. Worth
keeping: BF-04 sat at `fixed-in-seam` from 2026-09-14, high severity, live for
every operator, in no open-work list, and it took an unrelated question about
a different branch to get it scheduled. The register flagged that failure mode
on 2026-09-15 and the flag did not cause the work; the question did. The
allowlist and the JavaScript guard are extracted from the seam branch
(seam/t2-4-allowlist 987e9657) rather than written fresh, with the framing
inverted: on the seam that module is a better error message in front of a
structural guard, and on dev there is no AST behind it, so there it IS the
guard. lib/storage/assert-no-query-javascript.js is carried across byte-
identical at the same path so the seam merge is free.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-K` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
