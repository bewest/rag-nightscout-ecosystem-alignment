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

# Review packet — BFQ-195 (PR #8859)

**BF-195 - a stale profile is pushed over the socket after a profile re-send**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-null-removes` |
| base | `official/dev@47723cda` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-195` is the measurement |
| semver | `patch` |
| register entries | `BF-195` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/profile.js: the ctx.bus.emit('data-received') at :171 on dev
47723cda (:90 on v15.0.9), which runs before the merge write of a re-sent
profile finishes. The socket's dataUpdate and the data reload it drives. Lands
with the Q1b change on the same branch.

## Why that semver

a race fixed; what is stored and replied does not change

## What an operator would notice

> After an app sends a profile again, a Nightscout page or follower app that
> is connected at that moment can briefly show the profile as it was before,
> until the next data update. The saved profile is correct.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 47723cda bf/16.0.0-null-removes`** &nbsp;·&nbsp; kind: `static`

The PR #8859 branch contains dev 47723cda. Red if the branch is rebased off
dev or deleted.

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 1bdce62c bf/16.0.0-null-removes`** &nbsp;·&nbsp; kind: `static`

The fix commit 1bdce62c is on the PR #8859 branch. Red if the branch is
rewritten without it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Reproduced 2026-10-26 by the Q1b study, 2 of 2 runs on dev 47723cda and on
  lab/q1b-null-removes 63c33a0e: a socket client receives the earlier
  profile in dataUpdate after a profile re-send. A queue gate would re-send
  a profile in-process with a socket listener and assert the pushed profile
  is the merged one; control: dev 47723cda fails it. The fix's test is in
  draft PR #8859 (bf/16.0.0-null-removes, head fc170a4c); behaviour is
  measured outside the queue (the suite needs MongoDB): on fc170a4c,
  measured by session -66, npm test 4375 passing, 0 failing, 3 pending and
  test:all 4703 passing, 0 failing, 3 pending (re-run 2026-10-26; the first
  run had 1 environmental failure, development-watch ENOSPC on the file-
  watcher limit).

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-26, after #8854 merged (dev 7ad3a67f): session -66 merged dev 7ad3a67f
into bf/16.0.0-null-removes locally as 5c6ceabb, not pushed (the PR head is
still fc170a4c; the push is the maintainer's). The resolution: both requires
kept in lib/api3/generic/patch/operation.js; #8854's cross-path entries resend
cells in tests/api.crud-by-id.matrix.test.js updated (the v1 resend expects
200, the _id-collision branch removed; only v3 to socket still duplicates). On
5c6ceabb: npm test 4521 passing, 0 failing, 3 pending; test:all 4849 passing,
0 failing, 3 pending. Red control: dev's matrix file on the merged tree gives
413 passing, 9 failing (the 4 cross-path cells and 5 v3 devicestatus resend
rows); with the updated file 422 passing, 0 failing. #8854's boundary
validates the effective result of $set and $unset (lib/storage/write-
step.js:35, lib/server/write-validation.js:143), so a null that removes a
field goes through reject-mode validation. 2026-10-26, later: in draft PR
#8859 to dev (bf/16.0.0-null-removes, head fc170a4c), opened by the
maintainer, as 1bdce62c ("Announce a profile write after it finishes, not when
it starts"), with Q1b 913d0895, ID-SIMPLE-MATCH (merge cf2a2a67) and the
devicestatus rule fc170a4c. Measured by session -66: npm test 4375 passing, 0
failing, 3 pending and test:all 4703 / 0 / 3 (re-run 2026-10-26; the first run
had 1 environmental ENOSPC failure). Merges cleanly with #8856; with #8854 one
import-line conflict and a 3-line matrix expectation change (ID-SIMPLE-MATCH).
2026-10-26, later: lands in the one 16.0.0 re-send and merge PR on
bf/16.0.0-null-removes (Q1b head 1bdce62c; bundle in progress; at cf2a2a67 the
branch carries 913d0895 for Q1b, 1bdce62c for BF-195 and a merge of 8d0f9a22,
read from git log, not measured here) with Q1b, ID-SIMPLE-MATCH and the
devicestatus identifier re-send rule (maintainer, 2026-10-26). 2026-10-26: id
allocated by session -66 and filed from the Q1b study. Fix direction,
unverified: emit data-received once the write has completed. To land with Q1b
(a null in an update removes the field, decided by the maintainer 2026-10-26,
for 16.0.0) on bf/16.0.0-null-removes, in progress (the branch is at dev
47723cda).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-195` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
