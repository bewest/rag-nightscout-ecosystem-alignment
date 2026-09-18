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

# Review packet — P0-K

**bf/operators - BF-04 extracted, BF-70 found - NOT YET A PR, needs a disclosure
decision first**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/operators` |
| base | `origin/dev@a8888f0d` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=P0-K` is the measurement |
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

It removes reachable behaviour - $expr on /profiles/, $type on any typed
field, and the undocumented pipeline parameter - so it is not a patch by the
project's own reading. It is not major either: no route is removed, no
required input is added, no documented contract breaks, and the census of 14
client projects found zero senders of anything now refused. THE ONE OPEN
QUESTION IS $type. PR #8737 added readTypeOperand() specifically so
find[sgv][$type]=2 keeps working; this allowlist runs first and makes that
reader unreachable over HTTP. Trial-merged and MEASURED - 3 of #8737's tests
fail, all three the allowlist refusing $type, $not or $text. Two one-line
resolutions are set out in the report §2.2 and NEITHER IS TAKEN HERE. That is
the maintainer's call and it changes #8737, not this branch.

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

MAINTAINER, AND THIS ONE DOES NOT GO STRAIGHT TO A PUBLIC PR. BF-70 is an
unauthenticated read oracle over arbitrary collections, live on the shipping
release, and the commit message describing it is precise enough to be a
recipe. The ordinary path for this stack - open a PR, paste the full body -
publishes a working attack against every current deployment before any of them
can take the fix. Someone has to decide sequencing (fix first, publish after)
and whether Nightscout's security contact process is invoked. Until that
decision exists this item is BLOCKED ON A PERSON, not on engineering. BF-04's
two commits carry no such problem and could be split out and opened normally
if the decision takes time. Second thing the reviewer must rule on: the $type
collision with PR #8737 - see semver_reason and the report §2.2.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor a8888f0d bf/operators`** &nbsp;·&nbsp; kind: `static`

bf/operators has not fallen behind the dev tip it was cut from

**`TEST=mongo-query-javascript npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-operators`

BF-04, the JavaScript half. 23 passing, 49 ms, no database. ABLATED 2026-09-18
- commenting out the create() call gives 14 failing, and the ablation was
confirmed applied by grep before the run, because a green ablation that never
landed has happened twice in this programme.

**`TEST=api-v1-operator-allowlist npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-operators`

BF-04, the allowlist. 62 passing + 16 pending without a database; the 16 are
the end-to-end section, which is the only place the ALLOWED operators are
proved to still SELECT rather than merely to pass the guard. ABLATED two ways,
both confirmed applied by grep - removing the create() call gives 14 failing,
making refuse() return instead of throwing gives 36.

**`TEST=api-v1-count-pipeline npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-operators`

BF-70. 8 passing, 30 ms, no database. ABLATED - restoring the two lines the
commit changes gives 3 failing.

**`TEST=api-v1-operator-allowlist npm run test-single`** &nbsp;·&nbsp; kind: `integration` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-operators`

the same file with CUSTOMCONNSTR_mongo set - 78 passing, mongod 7.0 on port
27018, measured 2026-09-18. This is the run that matters: without a database
the end-to-end section skips and the suite proves only that refusals refuse.

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
- `npm test` over the whole suite is 2137 passing / 3 pending / 0 failing on
  this branch with a live mongod, measured 2026-09-18. Not a gate because it
  needs a database on a port other sessions share, and because a whole-suite
  number says nothing about WHICH assertion covers this branch - the three
  TEST= gates above do.
- No PR exists, so there is no pr-body-parity gate and no ls-remote gate.
  Both appear when the disclosure decision in `review` is made and the
  branch is opened. A missing gate that renders blank looks exactly like a
  passing one, which is why this marker is here rather than the rows simply
  being absent.

## Evidence

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
