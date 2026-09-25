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

# Review packet — BFQ-115

**BF-115 - an entry or treatment with an unusable _id is stored with it, and one
such value stops the server at every load**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `wip/object-id-crud-fixes-2` |
| base | `official/bf/object-id-crud@ab7b22d6` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-115` is the measurement |
| semver | `patch` |
| register entries | `BF-115` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/object-id-forms.js dropEmptyId (new); normalizeEntryId in
lib/server/entries.js and normalizeTreatmentId in lib/server/treatments.js
call it; null-_id guards in lib/data/ddata.js, lib/data/dataloader.js,
lib/data/calcdelta.js and API v3 normalizeDoc
(lib/api3/storage/mongoCollection/utils.js).

## Why that semver

a crash fix; a request that stored an unusable id now stores a server id

## What an operator would notice

> A treatment or glucose entry sent without a usable record id now gets one
> from the server. One kind of badly formed record could stop a Nightscout
> site from running, and keep stopping it after every restart; that can no
> longer happen, and a site that already holds such a record keeps running.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor ab7b22d6 wip/object-id-crud-fixes-2`** &nbsp;·&nbsp; kind: `static`

wip/object-id-crud-fixes-2 is a fast-forward of #8758's head ab7b22d6, so the
push is to bf/object-id-crud with no rebase.

**`git -C externals/cgm-remote-monitor-official grep -q "dropEmptyId" wip/object-id-crud-fixes-2 -- lib/server/ob`** &nbsp;·&nbsp; kind: `static`

The fix (17add44b) is on the branch. A presence check only; its control is the
same grep on origin/bf/object-id-crud, which fails until the push.
tests/api.empty-id.test.js is what says the fix works.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is held by tests/api.empty-id.test.js, which needs a booted
  server and a MongoDB, so it is not a queue gate. 2026-09-25 on 63dd716c,
  Node 22.23.2, MongoDB 7.0.43 (read from the server): the object-id test
  files pass together (578 passing); each fix hunk reverted fails a named
  test (register detail). The full matrix run is recorded in
  docs/30-design/remedial/rc-15.0.9-integration-record.md.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`reports/consumer-impact-15.0.9/clients-8758.md`](../../reports/consumer-impact-15.0.9/clients-8758.md)

## Notes carried on the item

Open, found 2026-09-25 in the #8758 freeze pass (corpus CANDIDATE-1,
reproduced by the review). Live on 15.0.8; needs a credential that can create
treatments or entries; no corpus client sends such a value. Put on #8758 at
the maintainer's request (2026-09-25, this session). Fix 17add44b. Not fixed,
follow-up: websocket dbAdd stores '' and 0, and API v3 POST stores '', 0,
false and {} as _id, without a crash but unaddressable by any id route.
Public-disclosure note: the fix commit and its test show the value once
pushed; the register names the mechanism only.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-115` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
