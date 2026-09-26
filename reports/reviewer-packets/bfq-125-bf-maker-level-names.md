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

# Review packet — BFQ-125

**BF-125 - IFTTT Maker alarm events use translated level names; a failed call
re-sends every check (issue #8104)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/maker-level-names` |
| base | `origin/dev@e3adc91d` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-125` is the measurement |
| semver | `patch` |
| register entries | `BF-125` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/levels.js (new toKey) and lib/server/pushnotify.js sendMakerEvent (event
level from the untranslated key); the dedup TTL after a failed send is
unchanged; tests/maker-level-names.test.js (new). Changes the IFTTT event
names a non-English site sends.

## Why that semver

restores the documented IFTTT event names; a site that renamed its applets to
the translated names needs a release note

## What an operator would notice

> If your Nightscout language is not English and you use IFTTT, the alarm
> events Nightscout sends are named in your language instead of the
> documented names such as ns-warning and ns-urgent. IFTTT applets set up
> with the documented names never run, so those alerts do not reach you;
> only the general ns-event still works. If Nightscout cannot reach IFTTT,
> it can also send the same alarm again about every minute. Do not rely on
> IFTTT alone for alarms: keep your phone's and devices' own alarms on. The
> fix is not in any release yet. This is not medical advice.

## Who should review this, and why

maintainer, plus someone who uses IFTTT with a non-English language

## What was measured

**`sh -c 'git -C externals/cgm-remote-monitor-official cat-file -e bf/maker-level-names:lib/server/pushnotify.js `** &nbsp;·&nbsp; kind: `static`

The branch names Maker events from levels.toKey, the untranslated level
(origin/dev still uses the translated display level and fails this). A
presence check only; the probe and tests/maker-level-names.test.js decide.
Point it at origin/dev once merged.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by tools/lab/triage-2026-09/maker-language.js,
  which needs a cgm-remote-monitor tree with node_modules and so is not a
  queue gate. 2026-09-25: exit 1 on v15.0.8 92d08342 and dev 4f705217 (ru
  and de give translated names; the en control and the resend controls
  behave). Exit 0 on a scratch copy of dev with an untranslated level key.
  The probe prints the resend half without scoring it. 2026-09-25: exit 1 on
  e3adc91d, 0 on the branch 2f50ada9.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/triage-2026-09/maker-language.js`](../../tools/lab/triage-2026-09/maker-language.js)

## Notes carried on the item

Filed 2026-09-25 from the GitHub issue triage (issue #8104, opened
2023-10-08). The two halves are independent: the translated name happens
whenever the language is not English; the resend happens whenever a Maker call
errors, in any language. What makes a real IFTTT call fail for the reporter
was not reproduced. 2026-09-25 - HALF 1 FIXED on bf/maker-level-names 2f50ada9
(local, not pushed), one commit on dev e3adc91d: Maker event names from the
new levels.toKey (untranslated level). 11 tests; suite 3181/0/3 (Node 22.23.2,
MongoDB 7.0.43). Half 2 (a resend about every 30 s after a failed call) left
unchanged by design: the 2015 commits f805633f and ea745065 say a failed send
is retried, and the branch's tests now pin it. Release note: sites that
renamed their applets to the translated names must rename them back.
2026-09-26 - Combined run: all six round-1 branches (bf/activity-date-coercion
20c197bb, bf/entries-unknown-id f79dc732, bf/maker-level-names 2f50ada9,
bf/profile-switch-percentage 5a895b49, bf/pebble-delta-units aa224c69,
bf/v1-writes-v3-history 718efddc) merged on dev e3adc91d as local
lab/round1-combined bda225e4 (worktree externals/work/crm-round1-combined):
full suite 3292 passing / 0 failing / 3 pending (= 3170 + 122 new tests), Node
22.23.2, MongoDB 7.0.43. All five probes gave their expected exit codes: bf106
gate 0, maker-language 0, profile-switch-percentage 0, pebble-units 0,
v1-writes-v3-history 1 on the v1 DELETE arm only (kept by decision, BFQ-122).
The run carried 718efddc, not the later test commit d45987f7. Decisions: -
2026-09-26 (maintainer): keep half 2 as it is - a failed Maker call keeps
retrying about every 30 s, by design since 2015. BF-125 is recorded fixed. A
related multi-key defect is BF-137 (BFQ-137, after 15.0.9).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-125` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-25, against cgm-remote-monitor-official `e3adc91d`.*
