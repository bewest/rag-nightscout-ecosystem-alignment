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

# Review packet — MT-ENVELOPE

**M7: declare the operating envelope, then measure it**

| | |
|---|---|
| repository | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@9029fb6dd` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=MT-ENVELOPE` is the measurement |
| semver | `n/a` |

## What this changes

Human input first: active/idle tenant counts, rows/bytes, ingestion and
reconnect bursts, retention, freshness and recovery targets. Then one
benchmark window with an independent stored-count oracle.

## Why that semver

measurement

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- UNMEASURED by design until the envelope is declared; no number is invented
  from functional passes.

## Evidence

- [`docs/30-design/tenancy/m5-m6-decision-list.md`](../../docs/30-design/tenancy/m5-m6-decision-list.md)

## Notes carried on the item

Was part of M6; moved to M7 on 2026-11-09. Required before a production
cohort, not before the dormant alpha.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-ENVELOPE` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
