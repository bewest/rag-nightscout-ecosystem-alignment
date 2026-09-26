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
| branch | `bf/same-time-treatments` |
| base | `origin/dev@e3adc91d` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-121` is the measurement |
| semver | `minor` |
| register entries | `BF-121` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

One commit at fc821024. lib/server/treatment-fallback-key.js (new), used by
lib/server/treatments.js upsertQueryFor (v1 POST, PUT and the array bulkWrite)
and lib/server/websocket.js processSingleDbAdd and its similar match;
tests/api.same-time-treatments.test.js (new), with changed expectations in
tests/storage.selector-hardening.test.js and tests/websocket.input-
validation.test.js. API v3 is unchanged. Changes which v1 and socket writes
update and which insert, so every uploader that resends records is in scope.
Conflicts textually with bf/v1-writes-v3-history (BFQ-122), which merges
first.

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
> different time. A fix is ready for review for 15.0.9 and is not in any
> release yet. Even with the fix, two entries for the same minute with the
> same amount are still kept as one, because nothing tells them apart from
> the same entry sent twice; and in AndroidAPS, a bolus and carbs saved at
> the same instant as one "meal bolus" can still be kept as one. This is not
> medical advice; talk to your care team about how you enter carbs.

## Who should review this, and why

maintainer (API semantics), plus someone who runs Loop

## What was measured

**`sh -c 'git -C externals/cgm-remote-monitor-official cat-file -e bf/same-time-treatments:lib/server/treatment-f`** &nbsp;·&nbsp; kind: `static`

The branch's v1 upsert and socket dbAdd take their key from
lib/server/treatment-fallback-key.js (origin/dev has no such file and fails
this). A presence check only; the probe and tests/api.same-time-
treatments.test.js decide. Point it at origin/dev once merged. (The origin/dev
shape check this replaces was dropped on 2026-09-26, when the item became
ready-to-push: it could only go green by merging.)

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by tools/lab/triage-2026-09/same-time-carbs.js,
  which boots a server and needs MongoDB, so it is not a queue gate.
  2026-09-25: exit 1 on v15.0.8 92d08342, dev 4f705217 and #8758 ab7b22d6 (7
  same-time arms store 1, 4 controls store 2). Since 2026-09-26 it prints a
  verdict per arm; the arms the decided fix leaves (v3-noid, ws-dbAdd) are
  reported as known issues and do not decide the exit status unless --strict
  is given. 2026-09-26: exit 1 on e3adc91d, exit 0 on fc821024.
- Re-send regressions are measured by tools/lab/triage-2026-09/same-time-
  resend-shapes.js (new 2026-09-26), which boots each tree against MongoDB,
  so it is not a queue gate: all 22 measured re-send shapes store the same
  on fc821024 as on e3adc91d.
- The design is measured by a lab prototype, lab/6a-fix-121 a8ca1798
  (worktree externals/work/crm-6a-fix-same-time-treatments, one commit on
  dev e3adc91d, local and not for pushing), which switches the fallback key
  three ways. It is a measurement, not a fix branch. The fix (option 3,
  decided 2026-09-26) is bf/same-time-treatments fc821024.

## Blocked on

`BFQ-122`

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/triage-2026-09/same-time-carbs.js`](../../tools/lab/triage-2026-09/same-time-carbs.js)
- [`tools/lab/triage-2026-09/same-time-resend-shapes.js`](../../tools/lab/triage-2026-09/same-time-resend-shapes.js)
- [`reports/phase0-pr-bodies/same-time-treatments.md`](../../reports/phase0-pr-bodies/same-time-treatments.md)

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
2026-09-26 - FIXED on bf/same-time-treatments fc821024 (local, not pushed),
one commit on dev e3adc91d, option 3: client identity (syncIdentifier, id,
uuid, NSCLIENT_ID) must match, and a write without one matches only a record
without one (v1 and socket dbAdd); carbs and insulin join the key for v1
writes without identity; the socket similar match always keys on eventType.
Fixes v1-single, v1-array, v1-careportal, v3-then-v1, ws-similar and the
tconnectsync bolus+extended, careportal-then-Loop and careportal 20 g/15 g
cases; all 22 measured re-send shapes unchanged. Left by design: v3 without
identifier, socket dbAdd without identity (an edit after a lost ack stays
stale), AAPS v3 bolus+carbs in the same ms; careportal same-minute same-amount
entries cannot be distinguished. 18 new tests (10 fail on e3adc91d); suite
3189/0/3 (Node 22.23.2, MongoDB 7.0.43, fresh database). Conflicts textually
with bf/v1-writes-v3-history (the websocket.js requires, one input-validation
expectation); resolved in a trial merge, 3215/0/3. Ready to push once BFQ-122
has merged and this branch is merged up onto it (blocks_on). Interacts with
BF-09 (BFQ-09): X1/X2 fixed by this change; Z2, Z5, P2, B2, C2 remain; a BF-09
branch will conflict on the similar-match lines. Open question for the
maintainer: with BF-136's fix and this one both present, an AAPS v3 POST at
the same created_at and eventType as a v1 record takes that record over (it
gains an identifier); a later identical v1 re-send of the original then no
longer matches, so it is stored as a duplicate when the amounts are equal
(with different amounts both are kept). It needs all three conditions; no
corpus client was found that does all three. PR body draft: reports/phase0-pr-
bodies/same-time-treatments.md. Decisions: - 2026-09-26 (maintainer): option 3
- identity-aware matching for v1 and the websocket, plus the carbs and insulin
amounts in the key only for v1 REST writes with no client identity; AAPS v3
and socket dbAdd unchanged. The maintainer asked whether it occurs: yes, issue
#8185 is a real report (a caregiver sent Loop remote carbs 16 g then 4 g, both
back-dated to 7:40; the 16 g disappeared from Nightscout's chart, reports and
daily total, while Loop's own COB kept 20 g). Known issues that remain after
the fix: an AAPS v3 bolus and carbs in the same millisecond, both Meal Bolus,
still merge; careportal same-minute same-amount double entries still merge (no
design separates them). Fix in progress for 15.0.9 on bf/same-time-treatments
(worktree externals/work/crm-r2-fix-121), no commit recorded yet.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-121` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-25, against cgm-remote-monitor-official `e3adc91d`.*
