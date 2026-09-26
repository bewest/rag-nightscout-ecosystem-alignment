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

# Review packet — BFQ-136

**BF-136 - API v3 refuses an AndroidAPS write that lands on a record written
through v1 (Field app cannot be modified), and AndroidAPS drops it**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/api3-app-field-v1-records` |
| base | `origin/dev@e3adc91d` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-136` is the measurement |
| semver | `patch` |
| register entries | `BF-136` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

One commit at df6c04bc. lib/api3/generic/update/validate.js only
(isSameAsStored, used by the v3 POST dedup, PUT and PATCH) and
tests/api3.v1-record-immutable-fields.test.js (new). Changes which v3 writes
to v1-born records are accepted: a field the stored record lacks is accepted
when it contradicts nothing. With the fix, a v3 POST that deduplicates onto a
same-millisecond v1 record replaces it (pinned by a test).

## Why that semver

a v3 write that was refused with 400 is accepted; nothing that was accepted
changes

## What an operator would notice

> If a treatment such as carbs or insulin was saved in Nightscout by the
> careportal or another app that uses Nightscout's older interface, and
> AndroidAPS then uploads its own entry for exactly the same time and type,
> Nightscout refuses the AndroidAPS entry. AndroidAPS does not try again, so
> that entry never appears on your Nightscout site, in carbs or insulin on
> board (COB and IOB), in reports or for followers. Your AndroidAPS phone
> still has it and doses from its own records. If something you entered in
> AndroidAPS is missing from Nightscout, check whether the same entry was
> also made in the careportal at the same time. Changes made in AndroidAPS
> to an entry that was first saved through the older interface, for example
> a temporary target set in the careportal, are also refused and never reach
> Nightscout; deleting such an entry works. A fix is ready for review for
> 15.0.9 and is not in any release yet. With the fix, if the careportal and
> AndroidAPS save an entry for exactly the same moment, the AndroidAPS entry
> replaces the careportal one, including its notes. This is not medical
> advice.

## Who should review this, and why

maintainer, plus someone who runs AndroidAPS with NSClientV3

## What was measured

**`git -C externals/cgm-remote-monitor-official grep -qF "isSameAsStored" bf/api3-app-field-v1-records -- lib/api`** &nbsp;·&nbsp; kind: `static`

The branch's update validator compares a field the stored record lacks through
isSameAsStored (origin/dev has none and fails this). A presence check only;
the probe and tests/api3.v1-record-immutable-fields.test.js decide. Point it
at origin/dev once merged.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by tools/lab/triage-2026-09/api3-app-field.js,
  which boots a server and needs MongoDB, so it is not a queue gate.
  2026-09-26: exit 1 on v15.0.8 92d08342 and dev e3adc91d (3 of 13 arms
  refused), exit 0 on df6c04bc (13 of 13); 15 controls pass.
- Reproduced 2026-09-25 on v15.0.8 92d08342 and dev e3adc91d: a v1 Meal
  Bolus with 20 g carbs at T, then a v3 Meal Bolus at T from app AAPS with
  no identifier, answered 400 "Field app cannot be modified by the client";
  a v3 PUT to a v1-born record without app answered 400 on both builds. The
  behaviour needs a booted server and MongoDB, so it is not a queue gate.
- The AndroidAPS side is read, not run: NSClientV3Plugin.kt:1019 (AndroidAPS
  7e1d537d49) logs a 400 as FAIL and moves on, so the record is not retried.
  A run of AndroidAPS against a site where the same meal was entered in the
  careportal is the missing confirmation.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/triage-2026-09/api3-app-field.js`](../../tools/lab/triage-2026-09/api3-app-field.js)
- [`reports/phase0-pr-bodies/api3-app-field-v1-records.md`](../../reports/phase0-pr-bodies/api3-app-field-v1-records.md)

## Notes carried on the item

Filed 2026-09-26 from the 2026-09-25 measurement (the v3 PUT refusal was first
noted under OID-V3-EDIT-MERGE). Severity: data loss of AAPS-uploaded
treatments in Nightscout in that collision (dosing-relevant data in
Nightscout; the phone's own dosing is unaffected). 2026-09-26 - FIXED on
bf/api3-app-field-v1-records df6c04bc (local, not pushed), one commit on dev
e3adc91d. Correction to the filed facts: a careportal-shaped v1 record is
refused on date (careportal records have no date), on app only when the v1
record carries a date; a v3 PUT is refused on date whether or not app is sent;
a v3 PATCH with isValid true (what AndroidAPS sends on every update) is
refused with "Field isValid", so every AndroidAPS edit of a v1-born record was
silently dropped (for example a careportal temp target that AAPS changes);
deletes are unaffected. AAPS treats the 400 as final and advances its cursor
(NSClientV3Plugin.kt:1019, DataSyncSelectorV3.kt:256, read). Fix rule
(isSameAsStored in lib/api3/generic/update/validate.js; POST dedup, PUT,
PATCH): a field the stored record lacks is accepted when it contradicts
nothing - app/device first value; isValid true (false stays refused); date
only if equal to the stored created_at instant; identifier, utcOffset,
eventType and server fields stay strict. 16 new tests (9 fail on dev); suite
3186/0/3, and with BF-122 718efddc 3212/0/3 (Node 22.23.2, MongoDB 7.0.43,
fresh database). Trade-off, pinned by a test: v3 fallback dedup (created_at +
eventType, amounts not compared) now replaces a same-millisecond v1 record,
e.g. careportal 20 g becomes AAPS 30 g and the careportal notes/enteredBy are
lost; before, the AAPS entry was lost instead. Rare: careportal times are
whole minutes. With BF-121's fix as well, the takeover raises an open question
for the maintainer (BFQ-121). Decisions: - 2026-09-26 (maintainer): fix in
15.0.9, on bf/api3-app-field-v1-records (worktree
externals/work/crm-r2-fix-136).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-136` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-25, against cgm-remote-monitor-official `e3adc91d`.*
