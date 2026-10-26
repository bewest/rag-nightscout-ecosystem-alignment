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

# Review packet — MOD-WRITE-VALIDATION-READ

**Flag stored records that break a write-validation rule on API v3 reads (read-
side flag, R1/R2)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `official/dev@b29f1bf7` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=MOD-WRITE-VALIDATION-READ` is the measurement |
| semver | `minor` |

## What this changes

API v3 read, search and history: a computed validation member on a record that
breaks a rule (not stored); optionally a report page listing such records. No
migration.

## Why that semver

an added response member on API v3 reads

## What an operator would notice

> Nothing yet. If adopted, apps reading from Nightscout's API v3 could be
> told that a stored record breaks a rule, and a report could list such
> records so you can correct them.

## Who should review this, and why

maintainer, and the API v3 client developers

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- A decision item: whether to flag on read (R1) and report (R2), after the
  write-side log step has soaked. Not started.

## Blocked on

`MOD-WRITE-VALIDATION`

## Evidence

- [`docs/60-research/modernization/write-validation-design-2026-10-25.md`](../../docs/60-research/modernization/write-validation-design-2026-10-25.md)

## Notes carried on the item

2026-10-26: MOD-WRITE-VALIDATION merged (#8841, e09bca3b). Draft #8854 adds a
read-side inspection in a different shape: lib/storage/read-contract.js and a
Nightscout-Data-Warnings header on API v3 responses, not behind
WRITE_VALIDATION (read from its diff, 880b7369). The decision this item waits
on is unchanged. Filed 2026-10-25 by session f4 from the v3-validation lane
(design section 3.3). Hiding or migrating stored records is not recommended:
it would diverge from what uploaders sent and move every rewritten record into
every v3 history cursor.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MOD-WRITE-VALIDATION-READ` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
