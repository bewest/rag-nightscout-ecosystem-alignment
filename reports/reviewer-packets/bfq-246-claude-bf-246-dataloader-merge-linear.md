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

# Review packet — BFQ-246

**BF-246 - linear mergeProcessSort in the shared dataloader (16.0.0)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `claude/bf-246-dataloader-merge-linear` |
| base | `official/dev@79144cbd0` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-246` is the measurement |
| semver | `patch` |
| register entries | `BF-246` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

1 commit (f97df2c1c), 2 files: lib/data/dataloader.js (+33/-1: stringIds
helper, the set-based branch of mergeProcessSort, mergeProcessSort exported
for the test) and tests/dataloader.test.js (3 tests). No setting, route,
response or stored record changes.

## Why that semver

Performance only; the same records in the same order. No surface moves.

## What an operator would notice

> Nothing changes in what Nightscout shows. Sites with many treatments or
> device statuses spend less processor time each time new data is loaded, so
> the server answers sooner during loads.

## Who should review this, and why

maintainer, plus one reviewer who has not merged their own work here

## What was measured

**`node tools/queue/gates/dataloader-merge-linear.js --ref claude/bf-246-dataloader-merge-linear`** &nbsp;·&nbsp; kind: `unit`

The branch's mergeProcessSort keeps the loop's records, order and errors over
2,000 seeded cases and reads an old _id at most 3 times per record (dev's
loop: about n^2/2).

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Approved by the maintainer for 16.0.0 on 2026-11-22 (file, queue, fix). Found
in the #8898 evaluator round (INC-E2, multitenant fix 76e2ec0df on
claude/inc-e2-hotspots-20261122); this branch is the single-tenant port from
official/dev. 2026-11-22 on f97df2c1c (Node 22.23.4, MongoDB 8.0.34
container): test:affected 3133/3/0, npm test 6369/3/0, prcheck OK. When it
merges, switch the gate's --ref to official/dev and the control's to v15.0.9
(exits 1 there, measured 2026-11-22).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-246` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
