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

# Review packet — BFQ-117 (PR #8758)

**BF-117 - an API v3 DELETE of a record stored twice leaves one copy valid; on
#8758 v3 reads and writes the older copy**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `wip/object-id-crud-fixes-2` |
| base | `official/bf/object-id-crud@ab7b22d6` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-117` is the measurement |
| semver | `patch` |
| register entries | `BF-117` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/api3/generic/delete/operation.js;
lib/api3/storage/mongoCollection/{modify,find,index}.js (updateEveryForm,
deleteEveryForm, findEveryForm; sort {identifier: -1, _id: -1});
lib/api3/storage/mongoCachedCollection/index.js; tests/api3.delete-every-
form.test.js (new); CHANGED EXPECTATION in tests/api3.string-id.test.js (pair
DELETE) and tests/api3.storage.modify.test.js (sort).

## Why that semver

a bug fix in deletes and in which stored copy is read

## What an operator would notice

> If a treatment was stored twice by an older Nightscout and you delete it
> from an app that uses the newer API (for example AndroidAPS), both copies
> are now deleted, so it no longer keeps showing. When only one copy can be
> shown, the one holding the latest edit is shown.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor e9dbb1fb official/bf/object-id-crud`** &nbsp;·&nbsp; kind: `static`

The fixes (e9dbb1fb) are on #8758's pushed branch (f1e8398b, 2026-09-25,
e9dbb1fb merged with 25f5ea21). Containment, not freshness: it stays green
after #8758 merges.

**`git -C externals/cgm-remote-monitor-official grep -q "deleteEveryForm" official/bf/object-id-crud -- lib/api3/`** &nbsp;·&nbsp; kind: `static`

The fix (63dd716c) is on the branch. A presence check only; its control is the
same grep on origin/bf/object-id-crud, which fails until the push.
tests/api3.delete-every-form.test.js is what says the fix works.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is held by tests/api3.delete-every-form.test.js, which needs
  a booted server and a MongoDB, so it is not a queue gate. 2026-09-25 on
  63dd716c, Node 22.23.2, MongoDB 7.0.43 (read from the server): the object-
  id test files pass together (578 passing); each fix hunk reverted fails a
  named test (register detail). The full matrix run is recorded in
  docs/30-design/remedial/rc-15.0.9-integration-record.md.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`reports/consumer-impact-15.0.9/clients-8758.md`](../../reports/consumer-impact-15.0.9/clients-8758.md)

## Notes carried on the item

Open, found 2026-09-25 in the #8758 freeze pass (corpus CANDIDATE-3; the copy-
picking regression found by the review, 40/40 trials). Put on #8758 at the
maintainer's request (2026-09-25, this session). Fix 63dd716c. Not fixed,
follow-up: v3 PUT/PATCH edit one copy and websocket dbUpdate edits both, and
each leaves two records, so #8758's body and release-notes advice 'edit either
one: the two become one record' holds only for v1 PUT/POST; that wording is to
be corrected (reports/phase0-pr-bodies/pr-8758-body.md, releases/cgm- remote-
monitor-15.0.9/release-notes.md); queued as OID-V3-EDIT-MERGE and OID-WS-EDIT-
MERGE. Also seen by the review, not filed: GET /api/v1/entries/<unknown
hex>.json answers 500 'No such id' on both builds, and #8758 lets an upper-
case id reach it. Pushed to #8758 2026-09-25 as f1e8398b (the maintainer
merged e9dbb1fb with 25f5ea21); tree cf590474; CI 13 of 13 jobs green on that
head.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-117` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
