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

# Review packet — BFQ-167 (PR #8845)

**BF-167 - devicestatus remove()'s filter is not pinned by any test**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-record-identity` |
| base | `official/dev@b29f1bf7` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-167` is the measurement |
| semver | `n/a` |
| register entries | `BF-167` |

## What this changes

tests only: one test asserting that devicestatus remove() also deletes soft-
deleted records.

## Why that semver

test only

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Reproduced by tools/lab/seam-propagation/ds-remove-softdeleted.js:
  deletedCount 2 as shipped, 1 with stored_query_for swapped for query_for,
  while the suite stays 3564/0. The fix's proof is that same swap turning
  the new test red.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/60-research/tenancy/seam-propagation-rehearsal-2026-10-07.md`](../../docs/60-research/tenancy/seam-propagation-rehearsal-2026-10-07.md)

## Notes carried on the item

2026-10-25, later: in PR #8845 to dev (branch bf/16.0.0-record-identity; the
remote shows 539856ef; head bf37858e after merging dev 428b20b7, pending
push). 2026-10-25: fixed as 0edb1db9 on bf/16.0.0-record-identity (PR #8845,
head bf37858e after merging dev 428b20b7, pending push; session f4's identity
lane) (test only). Filed 2026-10-07 from the seam propagation rehearsal.
Register §1b, kind (c): behaviour is correct today.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-167` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
