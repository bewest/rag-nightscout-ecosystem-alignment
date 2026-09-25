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

# Review packet — BFQ-131 (PR #8758)

**BF-131 - on #8758, a record deleted by _id stays in the in-memory cache, so
pages and unfiltered reads keep showing it**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `wip/object-id-crud-fixes-2` |
| base | `official/bf/object-id-crud@ab7b22d6` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-131` is the measurement |
| semver | `patch` |
| register entries | `BF-131` |

## What this changes

lib/server/object-id-forms.js cacheRemoval (new); remove() in
lib/server/entries.js, treatments.js and devicestatus.js; websocket dbRemove
in lib/server/websocket.js; tests/cache.remove-by-id.test.js (new) and one
case in tests/websocket.object-id.test.js.

## Why that semver

a defect in an unmerged fix

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor e9dbb1fb official/bf/object-id-crud`** &nbsp;·&nbsp; kind: `static`

The fixes (e9dbb1fb) are on #8758's pushed branch (f1e8398b, 2026-09-25,
e9dbb1fb merged with 25f5ea21). Containment, not freshness: it stays green
after #8758 merges.

**`git -C externals/cgm-remote-monitor-official grep -q "cacheRemoval" official/bf/object-id-crud -- lib/server/e`** &nbsp;·&nbsp; kind: `static`

The fix (e9dbb1fb) is on the branch. A presence check only; its control is the
same grep on origin/bf/object-id-crud, which fails until the push.
tests/cache.remove-by-id.test.js and tools/lab/rc-soak/probe-deleted-entry.js
say whether it works.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour needs a booted server and a MongoDB: tests/cache.remove- by-
  id.test.js (red on 6c3ccce6, green on e9dbb1fb, 2026-09-25, Node 22.23.2,
  MongoDB 7.0.43) and the soak probe (exit 1 on ab7b22d6, 0 on 92d08342 and
  4f705217). The full six-cell run on e9dbb1fb is recorded in
  docs/30-design/remedial/rc-15.0.9-integration-record.md.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/rc-soak/probe-deleted-entry.js`](../../tools/lab/rc-soak/probe-deleted-entry.js)

## Notes carried on the item

Found 2026-09-25 by the 15.0.9 A/B soak (tools/lab/rc-soak, RT-SOAK), after
runs 011 to 014 of the full suite were green: the suite never read the cache
after a delete. Fixed the same day as e9dbb1fb before the push, at the
maintainer's request to push once. Safety-visible: a deleted bolus or carbs
entry kept being shown on newly opened pages and could count in insulin and
carbs on board there. Pushed to #8758 2026-09-25 as f1e8398b (the maintainer
merged e9dbb1fb with 25f5ea21); tree cf590474; CI 13 of 13 jobs green on that
head.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-131` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
