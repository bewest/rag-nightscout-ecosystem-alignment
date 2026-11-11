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

# Review packet — MT-EVAL-COST

**Evaluator per-evaluation cost: no per-cycle copies, dates parsed once, kept
working set, in-process view reads with total order**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/eval-cost-20261111` |
| base | `official/workspace/multitenant-20261102@16a1fc2d45e59602eb6ec3e3bf6f506f35bcc5b1` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=MT-EVAL-COST` is the measurement |
| semver | `n/a` |

## What this changes

Multitenant evaluator only. Steps C/D/E, B and A of decisions.md#evaluation-
cost-candidates; ties break on the insertion ordinal on both paths
(decisions.md#view-reads-total-order).

## Why that semver

unreleased preview

## Who should review this, and why

maintainer; clinical-path review

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured in reports/tenancy/eval-cost-2026-11-11/; frozen-head acceptance
  at the 2026-11-11 batch join.

## Blocked on

`MT-PERF-EVALUATOR`

## Evidence

- [`reports/tenancy/eval-cost-2026-11-11/README.md`](../../reports/tenancy/eval-cost-2026-11-11/README.md)

## Notes carried on the item

2026-11-11: head 745c7f4e. Time-only cycle 19.5 to 4.6 CPU-ms and 44 to 0
statements; acquisition 32.0 to 14.3 CPU-ms. Tie reads: MongoDB matches the
ordinal order on 400 of 402, PostgreSQL's previous order on 0.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-EVAL-COST` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
