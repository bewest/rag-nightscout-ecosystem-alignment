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

# Review packet — M4-CLIENT-LAB

**M4 client-binary lab: real pinned clients against the multitenant preview and
single-site Mongo**

| | |
|---|---|
| repository | `rag-nightscout-ecosystem-alignment` |
| branch | `codex/m4-client-lab-20261106` |
| base | `main@88902eba2532c42bf83a91a8104f9ea64da2ca18` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=M4-CLIENT-LAB` is the measurement |
| semver | `n/a` |

## What this changes

Lab code under tools/lab/m4-client-binaries, one queue gate and its control, a
run record. No cgm-remote-monitor or client file changes. Measures the M4
criterion "actual client execution distinguished from source-pattern replay"
for the three headless Linux clients; promotes nothing.

## Why that semver

Measurement only; no shipped surface moves.

## Who should review this, and why

maintainer; compatibility and tenancy review of the classified cells

## What was measured

**`node tools/queue/gates/m4-client-binaries.js --ref c0e8ad3c562f5d6df3652bf2ba8d161fc1f69cf6`** &nbsp;·&nbsp; kind: `integration`

Archives the cumulative head, boots the preview and single-site Mongo from it,
runs the pinned cgmsim-lib and oref0 binaries in host-network containers
against both, reads stored rows from PostgreSQL and MongoDB oracles, and
classifies every differing cell with the compat vocabulary; red on any failed
positive or negative check or any unexplained cell.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Connector scenarios are opt-in and separate from the default gate. Fixed-
  data Share upload/restart and preview-to-single-site entries-only source
  execution are measured in the dated report. Connector-specific refusal
  controls, incremental new-reading polling, baseline-as-source
  differential, mobile/v3 binaries, socket forwarding and TLS remain
  UNMEASURED. D23 entry condition 2 has no forwarding-realtime
  implementation on the selected head.

## Evidence

- [`docs/30-design/tenancy/m4-client-binary-lab-packet-2026-11-06.md`](../../docs/30-design/tenancy/m4-client-binary-lab-packet-2026-11-06.md)
- [`reports/m4-client-binaries/2026-11-06/README.md`](../../reports/m4-client-binaries/2026-11-06/README.md)
- [`reports/m4-client-binaries/2026-11-06-batch-a/README.md`](../../reports/m4-client-binaries/2026-11-06-batch-a/README.md)
- [`reports/m4-client-binaries/2026-11-06-revised-freeze/README.md`](../../reports/m4-client-binaries/2026-11-06-revised-freeze/README.md)

## Notes carried on the item

Locally accepted bounded lab; proposed ready-to-push claim on this isolated
branch, pending coordinator integration before canonical
promotion/publication. Exact registered default gate passed on c0e8 with zero
differences after focused semantic controls and restoration. Prior failed
captures and the combined 863 connector scope remain immutable. Current
reports hold counts, client provenance, limitations and source ancestry. No
general M4 promotion. Shared main/index draft is archived; only root retires
the exact unchanged old draft after integrating the committed replacement. No
application push.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=M4-CLIENT-LAB` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
