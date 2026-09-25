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

# Review packet — BFQ-130

**BF-130 - on #8758, a treatments batch can answer 200 and lose an item that
lands on a string-stored copy**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `wip/object-id-crud-fixes-2` |
| base | `official/bf/object-id-crud@ab7b22d6` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-130` is the measurement |
| semver | `patch` |
| register entries | `BF-130` |

## What this changes

lib/server/treatments.js create, batch path (the trailing deleteMany from
object-id-forms.withStaleStringsRemoved); a test beside tests/api.object-
id.treatments-entries.test.js.

## Why that semver

a defect in an unmerged fix

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor ab7b22d6 wip/object-id-crud-fixes-2`** &nbsp;·&nbsp; kind: `static`

wip/object-id-crud-fixes-2 is a fast-forward of #8758's head ab7b22d6, so the
push is to bf/object-id-crud with no rebase.

**`git -C externals/cgm-remote-monitor-official grep -q "opItem" wip/object-id-crud-fixes-2 -- lib/server/treatme`** &nbsp;·&nbsp; kind: `static`

The fix (6c3ccce6) is on the branch. A presence check only; its control is the
same grep on origin/bf/object-id-crud, which fails until the push.
tests/api.object-id.treatments-entries.test.js is what says the fix works.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is held by tests/api.object-id.treatments- entries.test.js
  (the reproduction is red on cb7d4110 and green on 6c3ccce6; removing the
  index map fails two tests), which needs a booted server and a MongoDB. The
  full six-cell run on 6c3ccce6 is recorded in
  docs/30-design/remedial/rc-15.0.9-integration-record.md.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Open, found 2026-09-25 by the #8758 freeze review, queued at the maintainer's
request. New in #8758 and a silent 200 drop, so it is a candidate to fold into
#8758 before the tag, like BF-115 to BF-117; the reach is narrow. The food and
activity batch paths use the same trailing delete and should be checked for
the same shape. Fixed 2026-09-25 as 6c3ccce6 on wip/object-id-crud-fixes-2 at
the maintainer's request ("fix BF-130 first so I push once").

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-130` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
