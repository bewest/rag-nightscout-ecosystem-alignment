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

# Review packet — BFQ-118

**BF-118 - on an mmol site, targets set without BG_HIGH are never converted, so
low alarms cannot fire (issue #7729)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/mmol-partial-thresholds` |
| base | `origin/dev@4f705217` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-118` is the measurement |
| semver | `patch` |
| register entries | `BF-118` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/settings.js processRawSettings threshold conversion (and verifyThresholds
if designed together with BF-67/BF-86); tests/settings.test.js.

## Why that semver

a bug fix in how documented settings are read; a site that set all four values
sees no change

## What an operator would notice

> If your Nightscout site shows glucose in mmol/L and you set the target
> range (BG_TARGET_TOP and BG_TARGET_BOTTOM) in mmol/L without also setting
> BG_HIGH and BG_LOW in mmol/L, Nightscout reads your target numbers as
> mg/dL. Then Nightscout cannot raise a low or urgent-low alarm at all, and
> it raises a high warning for every reading, including low ones. To check,
> look at where the target lines are drawn on your chart. If they are near
> zero, this affects you. Setting all four values (BG_HIGH, BG_TARGET_TOP,
> BG_TARGET_BOTTOM and BG_LOW) in mmol/L avoids it. Keep the alarms on your
> phone, CGM app or receiver switched on. This is not medical advice; ask
> your care team which alarm levels are right for you.

## Who should review this, and why

maintainer, plus someone who runs an mmol/L site

## What was measured

**`sh -c 's=$(git -C externals/cgm-remote-monitor-official show bf/mmol-partial-thresholds:lib/settings.js) && ! `** &nbsp;·&nbsp; kind: `static`

The branch no longer decides the unit of all four thresholds from BG_HIGH
alone (origin/dev fails this until the fix merges; point it at origin/dev
then). A presence check only, red if the file cannot be read; the probe below
says whether a partial mmol set converts.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by tools/lab/triage-2026-09/mmol-partial-
  thresholds.js, which needs a cgm-remote-monitor tree with node_modules and
  so is not a queue gate. 2026-09-25: exit 1 on v15.0.8 92d08342 and dev
  4f705217 (stored 260/8.5/3.9/2.9 mg/dL; 45 mg/dL raises Warning HIGH, no
  low alarm); both controls raise Urgent LOW at 45 on both. Done when the
  probe exits 0 on the candidate.
- tools/queue/gates/threshold-silent-rewrite.js (BF-67) does not cover this
  input: its mmol control sets all four thresholds. A partial-mmol arm
  belongs in tests/settings.test.js with the fix.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/triage-2026-09/mmol-partial-thresholds.js`](../../tools/lab/triage-2026-09/mmol-partial-thresholds.js)

## Notes carried on the item

2026-09-25 - FIXED on bf/mmol-partial-thresholds 93359650 (local, not pushed),
on dev 4f705217: on an mmol site each threshold is read on its own (below 30 =
mmol/L, converted; 30 or more = mg/dL, kept), one log line per conversion,
README bullet. 8 new tests (6 fail on dev's settings.js with the symptom);
probe exit 0 on the branch, 1 on dev; full suite 2585/3/0 vs dev 2577/3/0,
Node 22.23.2, MongoDB 7.0.43. For the maintainer's review: the cut-off of 30,
and one stored-value change (BG_HIGH=14 with BG_TARGET_TOP=180 now gives
252/180/80/55, not 3244/3243/1441/991). Filed 2026-09-25 from the GitHub
triage (issue #7729, opened 2022-11-30). Same design decision as BF-67 and
BF-86 (how threshold numbers are validated and interpreted), and should be
decided with them; the trigger (conversion keyed on BG_HIGH alone, on a
correctly configured mmol site) and the false high warning are this entry's
own. Open PR #8522 does not touch it.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-118` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
