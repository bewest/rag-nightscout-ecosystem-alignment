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

# Review packet — BFQ-222 (PR #8883)

**BF-222 - API v3 autoPrune can leave pruned records in the server's cache**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-batch-replies` |
| base | `official/dev@368e6c23` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-222` is the measurement |
| semver | `patch` |
| register entries | `BF-222` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/api3/storage/mongoCachedCollection/index.js deleteManyOr: the pre- read of
ids to announce uses the same OR as the delete (logicalOperator 'or');
tests/api3.autoprune.test.js gains a red/green test (9d8dbc76, cherry-picked
as 789d5d9d).

## Why that semver

the cache matches the database after a prune; nothing stored changes

## What an operator would notice

> Only on sites that set API3_AUTOPRUNE_<collection> to fewer days than the
> server keeps in memory. A record pruned by its date could keep showing
> until the server dropped it from memory by age. With the fix the server
> forgets every record the prune deletes. Not yet in a released version.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official fetch -q official pull/8883/head && git -C externals/cgm-remote-m`** &nbsp;·&nbsp; kind: `network`

#8883's head on GitHub contains BF-222's fix 789d5d9d; red if the PR drops it.
Once #8883 merges, replace with the official/dev ancestor gate and set merged-
upstream

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/30-design/remedial/rc-16.0.0-integration-record.md`](../../docs/30-design/remedial/rc-16.0.0-integration-record.md)

## Notes carried on the item

2026-10-31: in #8883 (bf/16.0.0-batch-replies, head 789d5d9d, base dev
368e6c23, 0 behind; CI 13 passed and 2 pending at 05:30Z); not merged. Merges
before #8879's next dev merge (they conflict in four files). Filed by session
-7d to close the register-queue coverage gap.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-222` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
