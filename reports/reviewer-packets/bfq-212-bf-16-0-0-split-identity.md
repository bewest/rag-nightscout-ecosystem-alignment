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

# Review packet — BFQ-212 (PR #8878)

**BF-212 - a chart-drag split leaves two treatments with one client identity; a
re-send can overwrite one's amount, and a re-upload can show the moved insulin
twice**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-split-identity` |
| base | `official/dev@cf3d4b8f` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-212` is the measurement |
| semver | `patch` |
| register entries | `BF-212` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/client/treatmenttime.js splitRecord and its callers in
lib/client/renderer.js (Move insulin, Move carbs). The fix direction is a
manual confirmation before a lossy edit of a record that carries a client
identity (maintainer, 2026-10-29); the shared-identifier overwrite on v1 and
in-process also concerns ID-FIRST-MATCH.

## Why that semver

a confirmation step before a lossy edit; no API or stored-record shape changes

## What an operator would notice

> Moving the insulin or the carbs of a treatment on the Nightscout chart can
> leave two records labelled as the same entry. An app that later sends that
> entry again can overwrite one record's amount with the other's, or the
> moved insulin can be shown twice, which makes the insulin on board (IOB)
> shown on the chart too high. Not fixed in any released version.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Reproduced by a local probe (crm probe/split-ident-2026-10-29 95570d41,
  synthetic data, with a control) and measured by session -4f's matrix
  extension (QC-MATRIX-IDF, pin tools/qc/results/write-contract-
  matrix/dev-e1f7ac41-idfirst.json). A gate once a fix exists: the probe's
  shared-identity checks green and its control red.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/30-design/platform/wc-step-design-note-2026-10-27.md`](../../docs/30-design/platform/wc-step-design-note-2026-10-27.md)

## Notes carried on the item

Filed 2026-10-29 by the records accuracy pass from the chart-drag split probe
on dev e1f7ac41; the overwrite of a shared-identifier record measured the same
day by session -4f (QC-MATRIX-IDF). Not run on v15.0.9; splitRecord there is
the same code (read).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-212` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
