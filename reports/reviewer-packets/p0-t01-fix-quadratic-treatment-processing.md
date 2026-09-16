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

# Review packet — P0-T01 (PR #8733)

**T0.1 - PR #8733, the two quadratic treatment scans**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `fix/quadratic-treatment-processing` |
| base | `origin/dev` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=P0-T01` is the measurement |
| semver | `patch` |

## What this changes

dfe2753d. Pushed as bewest/wip/optimize-treatment-processing.

## Why that semver

performance only

## What an operator would notice

> Sites with a lot of treatment records load faster. Nothing you see changes
> value or meaning.

## Who should review this, and why

upstream reviewers on PR #8733 - not ours to land

## What was measured

**`git -C externals/cgm-remote-monitor-official ls-remote --heads origin bewest/wip/optimize-treatment-processing`** &nbsp;·&nbsp; kind: `network`

the one Phase 0 branch that IS legitimately pushed. GT1 verified this live.
Read-only.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- PR merge state is upstream's and cannot be gated from here without a
  GitHub API call. This item is tracked, not driven.

## Evidence

- [`docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`](../../docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md)

## Notes carried on the item

The plan says "everything downstream assumes it". It is the only Phase 0 item
not prepared locally, and the only one already on a remote.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-T01` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
