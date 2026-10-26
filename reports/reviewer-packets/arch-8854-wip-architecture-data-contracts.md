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

# Review packet — ARCH-8854 (PR #8854)

**#8854 - shared write boundary, read contract and CI gates; into 16.0.0 after
four alignment conditions (outcome B)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `wip/architecture-data-contracts` |
| base | `official/dev@47723cda` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=ARCH-8854` is the measurement |
| semver | `n/a` |

## What this changes

Draft #8854 at 880b7369 (31 files, +934/-45): lib/storage/write-step.js (every
v1/internal module, the four socket write handlers and API v3 write through
one boundary), lib/storage/read-contract.js and the Nightscout-Data-Warnings
header on API v3 reads, scripts/check-write-boundary.js (AST gate over eight
adapter files), scripts/diagnose-data.js, cache, authorization-subject and
history-cursor guards, --fail-zero on mocha, tests/api.crud-by-
id.matrix.test.js (336 cells equal to dev).

## Why that semver

inside the 16.0.0 major; client-visible parts are conditions 1 and 2

## What an operator would notice

> Nothing changes for apps by default. With WRITE_VALIDATION=reject, the
> socket checks Temporary Targets too; how it answers a refused one is
> condition 1 below.

## Who should review this, and why

maintainer - authored by the co-maintainer; decided 2026-10-26 (outcome B)

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Upstream draft, not merged. The conditions are judged on the PR. After the
  merge, the 67-shape client replay (session -66's run on 47723cda) is re-
  run on the merged tree and compared row by row.

## Evidence

- [`docs/30-design/modernization/pr-8854-alignment-2026-10-26.md`](../../docs/30-design/modernization/pr-8854-alignment-2026-10-26.md)
- [`docs/30-design/platform/next-gen-platform-plan.md`](../../docs/30-design/platform/next-gen-platform-plan.md)

## Notes carried on the item

Decided 2026-10-26 by the maintainer, relayed via session -66: outcome B, in
16.0.0 and aligned first. The four conditions: (1) under reject the socket
answers per item as D2 does for API v1, or socket validation waits for that
decision; (2) Nightscout-Data-Warnings off by default or held back until
settled against #8841's Warning: 299; (3) storage-write-committed marked
internal and unstable; (4) this repository's write(intent) layer gets its own
name. D (split the PR) was considered. WC-STEP-PATCH now builds on this
boundary instead of the September seam chain.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ARCH-8854` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
