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

# Review packet — ID-SIMPLE-MATCH (PR #8859)

**API v1 entries and devicestatus match on identifier like treatments (the
simple contract)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-null-removes` |
| base | `official/dev@47723cda` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=ID-SIMPLE-MATCH` is the measurement |
| semver | `minor` |

## What this changes

Built as feat/v1-identifier-match 8d0f9a22; ships inside draft PR #8859
(bf/16.0.0-null-removes), the 16.0.0 re-send and merge PR. First scoped as one
PR to dev with BF-169 (BFQ-169). lib/server/entries.js upsertQueryFor (301-319
at fade2299): match identifier first, as treatments do, then sysTime+type.
lib/server/devicestatus.js create (92-172 at fade2299; insertMany unordered
after #8758's withoutStoredIds at 57-90): a status whose identifier is already
stored writes nothing and is answered with the stored _id (decided 2026-10-26;
8d0f9a22 replaces the stored status's fields, so the bundle changes it), the
rest are inserted as today. Tests for both. No change to treatments, API v3 or
the websocket.

## Why that semver

Versioning policy section 2, question 10: the same write stores a different
set of records (a re-send that today adds a second entry or devicestatus
becomes a match on the stored one). By rule R3 one minor row makes the release
a minor, and 15.0.9 is decided as a patch (RT-VERSION, RT-COUNT-COMPAT), so it
cannot go into 15.0.9.

## What an operator would notice

> An app that labels each glucose reading or loop status with its own id can
> send it again without a second copy being stored.

## Who should review this, and why

maintainer - re-send behaviour clients see changes

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 47723cda bf/16.0.0-null-removes`** &nbsp;·&nbsp; kind: `static`

The PR #8859 branch contains dev 47723cda (cut 5 merged). Red if the branch is
rebased off dev or deleted.

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 8d0f9a22 bf/16.0.0-null-removes`** &nbsp;·&nbsp; kind: `static`

This item's commit 8d0f9a22 (built as feat/v1-identifier-match) is on the PR
#8859 branch. Red if the branch is rewritten without it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Behaviour is measured outside the queue. tools/lab/v3-identifier-
  immutable's "v1 entries: same identifier, date +60 s" cell, run
  2026-10-26: stored n=2 on dev 47723cda, n=1 on 8d0f9a22 with the later
  date kept; every API v3 cell the same on both builds. The PR's mocha cases
  (11 entries, 7 devicestatus) each have a red control. Against dev's two
  files, 6 of 11 and 3 of 7 fail with the original symptom (expected 2 to be
  1). Seven code mutations turn the cases that pass on dev red. 74 related
  test files, 1428 passing; tests/tiers.json check ok; trial merge with
  #8854 880b7369 clean, its boundary gate passes.

## Evidence

- [`docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md`](../../docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md)
- [`tools/lab/v3-identifier-immutable/results/v3-identifier-immutable-2026-10-17.md`](../../tools/lab/v3-identifier-immutable/results/v3-identifier-immutable-2026-10-17.md)
- [`docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md`](../../docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md)

## Notes carried on the item

2026-10-26, later: ships inside draft PR #8859 to dev (bf/16.0.0-null-removes,
head fc170a4c), opened by the maintainer, with Q1b (913d0895), BF-195
(1bdce62c), a merge of 8d0f9a22 (cf2a2a67: entries find their stored match
first, then merge) and the devicestatus rule (b) as fc170a4c (a re-send with a
stored identifier writes nothing and the reply carries the stored _id, v1 and
v3; lib/api3/generic/create/acknowledge.js). dev is still 47723cda. Measured
by session -66: npm test 4375 passing, 0 failing, 3 pending and test:all 4703
passing, 0 failing, 3 pending (re-run on fc170a4c 2026-10-26, Node 22.23.4,
MongoDB 5.0; the first run, before push, had 1 environmental failure,
development-watch ENOSPC on the host's file-watcher limit). With the code
reverted 6 of 10 new v1 tests and 5 of 8 new v3 tests fail, controls pass; the
devicestatus re-send probe leaves 1 record where dev stored 2, 3, then 4. Two
existing expectations changed deliberately (api.crud-by-id matrix v3
devicestatus re-send row; api3.empty-identifier-edit). Trial merge with #8854:
one textual conflict (an import line in lib/api3/generic/patch/operation.js,
keep both requires) and 4 of #8854's cross-path matrix cells need a 3-line
expectation change, applied by whichever PR merges second; with it all 405
matrix tests pass. Merges cleanly with #8856. Points for review in the PR
body: v3's created_at+device devicestatus fallback still replaces; a deleted
status re-sent with its identifier stays deleted; two simultaneous first sends
with the same new identifier can both be stored (no unique index). 2026-10-26,
later (maintainer, via session -66): (a) D-ID-FALLBACK decided: for 16.0.0 a
v1 entries re-send whose identifier matches nothing still matches on
sysTime+type, as today (TEST-ENTRY-UUID-003); treatments never fall back; to
be revisited once identifiers are common. (b) A devicestatus re-send whose
identifier is already stored writes nothing (no merge, no new record, no
srvModified change) and the reply carries the stored _id, on API v1 and v3;
v3, which today replaces and moves srvModified, is aligned in the same PR. (c)
This item ships in one 16.0.0 re-send and merge PR with Q1b, BF-195 and (b),
on bf/16.0.0-null-removes (Q1b head 1bdce62c; bundle in progress). Evidence
for (b): the devicestatus study of 2026-10-26, reproduced on dev 47723cda and
8d0f9a22; client survey read-derived: no client sends an identifier on any
devicestatus path (Loop's remote overrides travel as treatments and push
notifications). 2026-10-26: carries the API v1 half of ID-CLIENT-OID-DECISION
(the Loop reply's simple contract: whether a client may create its own
ObjectId as _id over v1); the API v3 half is decided (BF-170, identity I2).
2026-10-26: built as feat/v1-identifier-match 8d0f9a22 (one commit over dev
47723cda; lib/server/entries.js +84/-8, lib/server/devicestatus.js +97, two
test files), not pushed. A re-sent identifier updates the stored record; an
identifier miss still falls back to sysTime+type for entries (status quo,
TEST-ENTRY-UUID-003 pins it), unlike v1 treatments, which never fall back;
that choice is the maintainer's (next-gen plan decision D-ID-FALLBACK).
identifier decides over a conflicting _id. upsertQueryFor is at entries.js:308
on 47723cda. Draft PR body and push commands are in the lane report.
2026-10-25: RT-1 merged (#8828, dev eb72a1d3), so this item is no longer
blocked and can go to dev. Neither lib/server/entries.js nor
lib/server/devicestatus.js changed between fade2299 and eb72a1d3 (git diff
--name-only fade2299 official/dev -- both files prints nothing), so the line
numbers above still hold. Cut 2 changes entries.js, so landing before cut 2's
catch-up adds to that merge (RT-2). 2026-10-21, later: cut 1's catch-up merge
is done (RT-REBASE's cut 1 part; 806ff2f0 contains dev 04d435eb), so blocks_on
moves from RT-REBASE to RT-1: this lands on dev after #8828 merges, which is
the maintainer's 2026-10-17 order. Cut 1 still touches neither
lib/server/entries.js nor lib/server/devicestatus.js (`git diff --name-only
official/dev official/chore/retire-jsdom` on 806ff2f0 lists neither).
2026-10-21: 15.0.9 is released and RT-0 is removed from blocks_on. Still waits
on cut 1's catch-up merge (RT-REBASE, in progress). Decided by the maintainer
2026-10-17: not in 15.0.9; lands on dev after cut 1's rebase, with BFQ-169.
15.0.9 is dev as it stands at fade2299 (releases/cgm-remote-
monitor-15.0.9/contents.md), and any merge to dev moves the head off the
candidate whose re-approval RT-0 owes. blocks_on names RT-REBASE because no
separate item marks cut 1's catch-up merge done; only cut 1's part is needed
(RT-1 blocks on the same two). Why after the rebase: RT-REBASE records that
each further merge to dev raises the cuts' catch-up cost. Cuts 2-5 already
change both files this item touches: `git diff --name-only $(git merge-base
fade2299 <cut>) <cut> -- lib/server/entries.js lib/server/devicestatus.js`
lists entries.js on cut 2 and both files on cuts 3, 4 and 5 (measured
2026-10-17); cut 1 touches neither. Landing after the catch-up merge keeps
this change out of that merge's conflicts. The tenancy item ID-FIRST-MATCH
absorbs this rule into the write step once WC-STEP-PATCH exists (it blocks on
this item). Background: the simple contract in the Loop reply (LOOP-ID-REPLY)
- _id an ObjectId or absent; identifier when _id is absent; the time key when
neither.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ID-SIMPLE-MATCH` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
