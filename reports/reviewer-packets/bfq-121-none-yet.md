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

# Review packet — BFQ-121

**BF-121 - two carb entries at the same time are stored as one, and the carbs of
one are lost (issue #8185)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `none yet` |
| base | `origin/dev@e3adc91d` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=BFQ-121` is the measurement |
| semver | `minor` |
| register entries | `BF-121` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/treatments.js upsertQueryFor (v1 POST, PUT and the array
bulkWrite); lib/api3/shared/operationTools.js calculateIdentifier;
lib/server/websocket.js processSingleDbAdd; tests for each. Changes which v1
writes update and which insert, so every uploader that resends records is in
scope.

## Why that semver

changes which v1 treatment writes update and which insert

## What an operator would notice

> If two carb entries of the same kind are recorded for exactly the same
> time, Nightscout keeps only one of them. The other entry's carbs disappear
> from Nightscout's charts, carbs on board, reports and what followers see,
> with no error. This is most likely when you enter two back-dated carb
> entries for the same minute in the Nightscout careportal or bolus wizard,
> and it can happen with Loop remote carbs. The app you entered them in
> still has both. If the totals in Nightscout look lower than what you
> entered, check the app you entered them in, and give each entry a
> different time. The fix is not in 15.0.9. This is not medical advice; talk
> to your care team about how you enter carbs.

## Who should review this, and why

maintainer (API semantics), plus someone who runs Loop

## What was measured

**`sh -c "git -C externals/cgm-remote-monitor-official show origin/dev:lib/server/treatments.js | grep -q 'syncId`** &nbsp;·&nbsp; kind: `static`

FAILS today: origin/dev's v1 upsert fallback key is created_at + eventType
alone, and nothing matches on syncIdentifier. Goes green when either changes
(checked 2026-09-25 against two edited copies: a syncIdentifier branch, and
carbs added to the key). A shape check only; the probe says whether it works.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by tools/lab/triage-2026-09/same-time-carbs.js,
  which boots a server and needs MongoDB, so it is not a queue gate.
  2026-09-25: exit 1 on v15.0.8 92d08342, dev 4f705217 and #8758 ab7b22d6 (7
  same-time arms store 1, 4 controls store 2). Done when it exits 0 on the
  candidate. The ws-similar arm is BF-09's behaviour and needs that entry's
  decision too.
- The design is measured by a lab prototype, lab/6a-fix-121 a8ca1798
  (worktree externals/work/crm-6a-fix-same-time-treatments, one commit on
  dev e3adc91d, local and not for pushing), which switches the fallback key
  three ways. It is a measurement, not a fix branch.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/triage-2026-09/same-time-carbs.js`](../../tools/lab/triage-2026-09/same-time-carbs.js)

## Notes carried on the item

Filed 2026-09-25 from the GitHub triage (issue #8185, opened 2023-11-28). A
maintainer comment on the issue says an identical created_at is expected to
update; the reporter's case is Loop remote carbs at a picked minute.
LoopCaregiver and LoopFollow now add the current seconds to the picked time as
a workaround. 2026-09-25 - Design measured on dev e3adc91d with the lab
prototype lab/6a-fix-121 a8ca1798, switching three keys. Identity-aware
matching fixes the Loop, v3-then-v1 and similar-match arms with no re-send
regression across 19 client shapes. Adding amounts fixes the remaining arms
but makes an AAPS edit after a lost id a duplicate on v3 and the socket.
Awaiting the maintainer's choice among three options.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-121` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-25, against cgm-remote-monitor-official `e3adc91d`.*
