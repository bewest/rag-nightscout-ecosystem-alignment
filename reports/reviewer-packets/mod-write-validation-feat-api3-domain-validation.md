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

# Review packet — MOD-WRITE-VALIDATION

**WRITE_VALIDATION=off|log|reject: opt-in domain validation of Temporary Target
writes on API v1 and v3 (draft)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `feat/api3-domain-validation` |
| base | `official/dev@b29f1bf7` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=MOD-WRITE-VALIDATION` is the measurement |
| semver | `minor` |

## What this changes

New lib/server/write-validation.js (pure rules); hooks in
lib/server/treatments.js create (v1 batch: store valid items, refused slots in
place), lib/api3/shared/operationTools.js validateDomain (v3 create, PUT,
PATCH on the merged record), lib/api/treatments/index.js (400 mapping),
lib/server/env.js (the setting). Default off: no behaviour change. Socket
dbAdd/dbUpdate not covered.

## Why that semver

a new opt-in setting; default behaviour unchanged

## What an operator would notice

> A new optional setting, WRITE_VALIDATION. Nothing changes unless you set
> it. With log, Nightscout stores temporary targets as today and writes a
> log line when one breaks a rule that holds for every app (for example a
> low target above the high target, or mg/dL numbers labelled mmol/L). With
> reject, it refuses such a temporary target; most apps that upload to
> Nightscout do not show you that refusal and lose the record, so reject is
> for operators who accept that. This is not medical advice; talk to your
> care team about how you set temporary targets.

## Who should review this, and why

maintainer, and the AndroidAPS, Loop and Trio developers on the refusal shape

## What was measured

**`git -C externals/cgm-remote-monitor-official cat-file -e a2e5fe49^{commit}`** &nbsp;·&nbsp; kind: `static`

the branch head exists in the shared clone; red if the local branch is lost
before it is pushed (a rebase changes the id, and this gate must then name the
new one)

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree official/dev feat/api3-domain-validation `** &nbsp;·&nbsp; kind: `static`

Merges into official/dev with no conflict.

**`git -C externals/cgm-remote-monitor-official grep -q "readENV('WRITE_VALIDATION', 'off')" feat/api3-domain-val`** &nbsp;·&nbsp; kind: `static`

The default is off on the branch (D1); red if a later commit changes the
default, which the decided ladder keeps for a major.

**`cd externals/work/crm-v3validate-1600 && npx mocha --timeout 10000 --exit tests/write-validation.test.js`** &nbsp;·&nbsp; kind: `unit`

The rule edges and that no refusal message contains the two 400 texts
AndroidAPS string-matches; 10 passing on 2026-10-25. Control (lane): a message
containing "cannot be modified by the client" fails it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The integration test tests/api.treatments-write-validation.test.js (22
  passing on the branch, MongoDB 8.0.34) needs MongoDB. Its red controls,
  reported by the lane: on dev's lib/ 12 of the first 20 fail (expected 400,
  got 201/200); all-or-nothing batches fail the mixed-batch case; leaving
  refusal objects out fails on the reply length Loop needs; the default set
  to reject fails the 5 default-off cases.

## Evidence

- [`docs/60-research/modernization/write-validation-design-2026-10-25.md`](../../docs/60-research/modernization/write-validation-design-2026-10-25.md)
- [`docs/60-research/remedial/upload-refusal-client-behaviour-2026-10-25.md`](../../docs/60-research/remedial/upload-refusal-client-behaviour-2026-10-25.md)

## Notes carried on the item

Filed 2026-10-25 by session f4 from the v3-validation lane. Draft: local
branch feat/api3-domain-validation a2e5fe49 (e8125d89, 6e842c07, a2e5fe49)
over dev b29f1bf7, not pushed. Decided 2026-10-25 (maintainer): D1 the setting
shape; D2 a v1 batch under reject stores its valid items, keeps one object per
item in order with refused slots without _id plus a refused member and a
Warning 299 header, and answers 400 when every item is refused; D4 a double-
labelled record is refused with a message naming the field and the units to
send. Open: D5 (N1 or N2 and the conversion constant, MOD-UNITS-CANONICAL), D6
(thresholds 30 mmol/L and 20 mg/dL). Making reject the default is blocked on a
refusal the person can see (clients that read refused, or a Nightscout-side
notice), not on a date. ready-to-push means the gates pass and the next step
is a human push of a draft PR.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MOD-WRITE-VALIDATION` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
