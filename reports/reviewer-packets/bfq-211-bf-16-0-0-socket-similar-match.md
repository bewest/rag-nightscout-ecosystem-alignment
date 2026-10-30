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

# Review packet — BFQ-211 (PR #8877)

**BF-211 - a delete by query in one collection empties all three in-memory
caches**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-socket-similar-match` |
| base | `official/dev@e1f7ac41` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-211` is the measurement |
| semver | `patch` |
| register entries | `BF-211` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/cache.js dataChanged: a remove with no ids flushes only the
collection deleted from, through the existing invalidate(type).

## Why that semver

fewer cache reloads; no reply or stored record changes

## What an operator would notice

> Deleting several records at once made the site re-read days of data from
> its database on the next load. That costs data transfer, which matters for
> sites on MongoDB Atlas's free tier. Nothing shown changes. Not yet in a
> released version.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The fix carries 3 tests that fail on dev (13107d1e on bf/16.0.0-cache-
  flush-scope; npm test 4759 to 4762/0/3), run in the crm worktree. The
  cache-value lab (tools/lab/cache-value) measures the reload: 890 documents
  and 716,202 bytes on dev, 32 documents and 10,289 bytes with the fix.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-29: in the 16.0.0 merge list (maintainer), added to #8877. Fix
13107d1e on bf/16.0.0-cache-flush-scope, cherry-picked onto local
bf/16.0.0-socket-similar-match as ac5d77fb; not pushed (GitHub head of #8877
is ebed6323).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-211` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
