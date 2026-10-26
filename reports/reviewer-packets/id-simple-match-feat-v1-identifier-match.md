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

# Review packet — ID-SIMPLE-MATCH

**API v1 entries and devicestatus match on identifier like treatments (the
simple contract)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `feat/v1-identifier-match` |
| base | `official/dev@47723cda` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=ID-SIMPLE-MATCH` is the measurement |
| semver | `minor` |

## What this changes

Small and standalone, one PR to dev with BF-169 (BFQ-169).
lib/server/entries.js upsertQueryFor (301-319 at fade2299): match identifier
first, as treatments do, then sysTime+type. lib/server/devicestatus.js create
(92-172 at fade2299; insertMany unordered after #8758's withoutStoredIds at
57-90): a status carrying identifier is upserted on it, the rest are inserted
as today. Tests for both. No change to treatments, API v3 or the websocket.

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

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 47723cda feat/v1-identifier-match`** &nbsp;·&nbsp; kind: `static`

The branch contains dev 47723cda (cut 5 merged). Red if the branch is rebased
off dev or deleted.

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
