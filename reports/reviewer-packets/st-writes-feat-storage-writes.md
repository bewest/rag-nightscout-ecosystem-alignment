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

# Review packet — ST-WRITES (PR #8863)

**Storage interface, second PR: API v1, authorization storage and socket writes
through the interface, each labelled by source; #8854's boundary check fails a
write that skips the interface**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `feat/storage-writes` |
| base | `feat/storage-filter@48e7e101` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=ST-WRITES` is the measurement |
| semver | `patch` |

## What this changes

lib/server/{entries, treatments, devicestatus, profile, food, activity,
websocket}.js, lib/authorization/storage.js, the new lib/server/storage-
writes.js, lib/api3/storage/mongoCollection (write context {source,
validated}, write options), the cache wrapper, delete-status.js,
scripts/check-write-boundary.js (a new rule: every write goes through the
interface). aggregate.js is unchanged (BF-70).

## Why that semver

No client-visible change; the write-contract matrix, #8854's CRUD matrix and
an 88-step write differential are the pins.

## What an operator would notice

> Nothing should look different: every API v1 write and socket event gets
> the same reply and stores the same documents as before.

## Who should review this, and why

maintainer, plus a second human - every v1 and socket write path moves

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured by the lab, not re-runnable from this repository alone. On
  feat/storage-writes 38b910d7 against 48e7e101 (Node 22.23.4, MongoDB
  8.0.34): npm test 4588/0/3 (base 4577), test:all 4916/0/3 (base 4905),
  check-write-boundary 9 entry points (red: a raw deleteMany), #8854 matrix
  422 (red: socket label dropped, 78 failing), write-contract matrix 0 of
  336 cells off and reject (red: deleted alias, 3 cells; reject mode is not
  exercised by the matrix, see QC-MATRIX-TT), v1 GET differential 700/700,
  write differential 88/88 with 3254 documents (red: alias 11 replies,
  $unset 11 stored states).

## Blocked on

`ST-FILTER-READS`

## Evidence

- [`docs/30-design/platform/next-gen-platform-plan.md`](../../docs/30-design/platform/next-gen-platform-plan.md)
- [`tools/qc/write-contract-matrix.js`](../../tools/qc/write-contract-matrix.js)
- [`tools/seam/DIFFERENTIALS.md`](../../tools/seam/DIFFERENTIALS.md)

## Notes carried on the item

2026-10-26: draft #8863, stacked on #8861 (base feat/storage-filter); it
retargets to dev when #8861 merges. Labels: v1 modules 'v1/internal', socket
'socket', authorization storage 'internal', default 'v3'; an unknown source is
refused; origin has room but is not passed. Open in the PR: commit events for
authorization writes, splitting 'v1/internal', insertOne normalize:false
setting _id as interface contract, moving the write differential into
tools/seam.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ST-WRITES` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
