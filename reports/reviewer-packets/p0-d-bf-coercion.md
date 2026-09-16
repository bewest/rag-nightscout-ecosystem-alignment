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

# Review packet — P0-D (PR #8737)

**bf/coercion - PR #8737, query filter typing (T0.5) and the $exists inversion**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/coercion` |
| base | `origin/dev@a8888f0d` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=P0-D` is the measurement |
| semver | `minor` |
| register entries | `BF-02`, `BF-03`, `BF-11`, `BF-32`, `BF-40`, `BF-68` |

## What this changes

2 commits at b7234753, the largest change in the set. lib/server/query.js plus
a generated coercion table over 5 collections; 158 coercions replace 13 hand-
written entries.

## Why that semver

GT4 measured the change in answers: find[duration][$gte]=30 goes from
{"$gte":"30"} (matched nothing) to {"$gte":30}; find[insulin][$gte]=1.5 from
{"$gte":1} to {"$gte":1.5}; find[sgv][$exists]=true from {"$exists":NaN}
(which returned the documents that LACK the field) to {"$exists":"true"}. No
request that worked stops working.

## What an operator would notice

> Searches through the API that filter on a number used to compare that
> number against text, so many of them quietly matched nothing and still
> answered "OK". They now compare correctly. If you have a saved search, a
> script or a third-party app that was returning nothing, it may start
> returning results - that is the fix working, not a new problem.
> SEPARATELY, and this is the one most likely to have been acted on: asking
> the API for records that do NOT have a field - $exists=false - returned
> exactly the records that DO have it, with a success code and nothing to
> say the answer was inverted. Any report, dashboard or script filtering on
> $exists=false was answering the opposite question, and a count from one
> was counting the wrong group. Re-run anything built on one; the set it
> returns now is the complement of what it returned before. $exists=true was
> correct before and is correct after.

## Who should review this, and why

maintainer. OPENED 2026-09-16 as PR #8737, base dev. The old text here said
"lands first of the stack so the query path settles"; there is no stack, and
the branch merges clean against dev and against all eight others. Three things
a reviewer cannot get from the diff: the classification is minor and rests on
no request that worked ceasing to work; `tests/query.operands.test.js` matches
neither local brace list, so a green `npm run test:unit` is evidence for the
typing fix and none for BF-40; and the composition with bf/reads is a property
of the PAIR, not of either diff, and is deliberately in neither PR.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/coercion`** &nbsp;·&nbsp; kind: `static`

bf/coercion has not fallen behind origin/dev

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/coercion >/dev/null`** &nbsp;·&nbsp; kind: `static`

trial-merge into origin/dev is conflict-free

**`TEST=query.operands npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-coercion`

BF-40's own test, 12 cases, on the second commit. In NEITHER local brace list
(GT1), so a green `npm run test:unit` is not evidence for it. Ablated three
ways with each break confirmed to land: removing the call fails 6, mapping ""
to false fails exactly the test pinning that decision, adding $regex to the
reader map fails exactly the $regex test.

**`TEST=query npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-coercion`

29 passing, database-free (measured against a dead mongo port). E3 RE-ABLATED
it properly: GT1's control was "the file cannot even LOAD against pristine
dev", which is a module-resolution failure, not a behavioural one. Reverting
ONLY lib/server/query.js and keeping the new table gives 24 passing / 4
failing on assertions ("expected '1.5' to be 1.5"), which is the control that
means something.

**`T=$(mktemp -d) && trap 'rm -rf "$T"' EXIT && python3 -m tools.nsschema.emit.coercion_emit --bundle "$T/emitted`** &nbsp;·&nbsp; kind: `static`

House style is "emit, then check the emission", and THE GATE THAT WAS HERE DID
NOT CHECK IT. `coercion_emit --drift` ends in `return 0` unconditionally: E3
ran it and it exited 0 while printing "DRIFT vs the shipping walkers: 157
disagreements". It also compares against a HARDCODED transcription of
origin/dev's walkers, so it says nothing about bf/coercion at all and would
have exited 0 with the branch deleted. What is gateable is the emission
itself: the table vendored into the branch must be byte-identical to what the
emitter produces today, or the branch is shipping a stale generated file.

**`git -C externals/cgm-remote-monitor-official ls-remote --heads origin bf/coercion | grep -q b72347538ba29f965c`** &nbsp;·&nbsp; kind: `network`

the branch behind PR #8737 is on the remote at the exact tip this item was
measured against. Read-only. Verified 2026-09-16.

**`node tools/queue/gates/pr-body-parity.js --only 8737`** &nbsp;·&nbsp; kind: `network`

the live body of PR #8737 still matches the file it was posted from. Bodies
drift in one direction - a correction gets written into the file first - and
the only previous record that one was owed was a sentence in a notes: field,
which is what let #8738 stay wrong in public for a day. It does NOT measure
whether the body is TRUE: parity with a wrong file is still parity, and every
figure in these bodies has been wrong at least once. NON-VACUITY, reproduced
2026-09-16: one altered file gives 1 failing, an empty body dir gives 6
failing. SKIPS with exit 0 when gh is unauthenticated.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Review and merge state of PR #8737 is upstream's, and cannot be gated from
  here without a GitHub API call. Tracked, not driven.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-coercion.md`](../../reports/phase0-pr-bodies/bf-coercion.md)
- [`tools/nsschema/emit/coercion_emit.py`](../../tools/nsschema/emit/coercion_emit.py)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Sequencing letter D. BF-03 is closed for devicestatus and profile only -
`food` reaches query.js at no point and `activity`'s model has no numeric
field, so those two halves were misfiled rather than fixed.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-D` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
