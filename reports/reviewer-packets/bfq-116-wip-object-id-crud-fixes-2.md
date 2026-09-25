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

# Review packet — BFQ-116 (PR #8758)

**BF-116 - on #8758, a devicestatus re-send answers 500 and loses the rest of
the batch**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `wip/object-id-crud-fixes-2` |
| base | `official/bf/object-id-crud@ab7b22d6` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-116` is the measurement |
| semver | `patch` |
| register entries | `BF-116` |

## What this changes

lib/server/devicestatus.js create (withoutStoredIds replaces
storeIdsAsObjectIds; insertMany unordered with duplicate-key acceptance for
statuses sent with their own _id); tests/api.devicestatus.resend-guard.test.js
and the devicestatus row of tests/api.crud-by-id.matrix.test.js change from
500 to 200 (CHANGED EXPECTATION).

## Why that semver

a defect in an unmerged fix

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor e9dbb1fb official/bf/object-id-crud`** &nbsp;·&nbsp; kind: `static`

The fixes (e9dbb1fb) are on #8758's pushed branch (f1e8398b, 2026-09-25,
e9dbb1fb merged with 25f5ea21). Containment, not freshness: it stays green
after #8758 merges.

**`git -C externals/cgm-remote-monitor-official grep -q "withoutStoredIds" official/bf/object-id-crud -- lib/serv`** &nbsp;·&nbsp; kind: `static`

The fix (c3a34bac) is on the branch. A presence check only; its control is the
same grep on origin/bf/object-id-crud, which fails until the push.
tests/api.devicestatus.resend-guard.test.js is what says the fix works.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is held by tests/api.devicestatus.resend-guard.test.js,
  which needs a booted server and a MongoDB, so it is not a queue gate.
  2026-09-25 on 63dd716c, Node 22.23.2, MongoDB 7.0.43 (read from the
  server): the object-id test files pass together (578 passing); each fix
  hunk reverted fails a named test (register detail). The full matrix run is
  recorded in docs/30-design/remedial/rc-15.0.9-integration-record.md.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`reports/consumer-impact-15.0.9/clients-8758.md`](../../reports/consumer-impact-15.0.9/clients-8758.md)

## Notes carried on the item

Open, found 2026-09-25 in the #8758 freeze pass (corpus CANDIDATE-2,
reproduced by the review). This reverses #8758's own design, which refused a
re-send with 500 as profile create does (BF-99); the maintainer asked for it
on #8758 (2026-09-25, this session). Profile create still refuses a re-send
with 500; making it match is not done. No AID uploader in the corpus sends a
devicestatus _id. Fix c3a34bac. Pushed to #8758 2026-09-25 as f1e8398b (the
maintainer merged e9dbb1fb with 25f5ea21); tree cf590474; CI 13 of 13 jobs
green on that head.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-116` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
