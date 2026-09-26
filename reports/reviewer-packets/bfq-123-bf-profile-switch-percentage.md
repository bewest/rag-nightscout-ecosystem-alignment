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

# Review packet — BFQ-123

**BF-123 - an AndroidAPS Profile Switch percentage is ignored in the basal, ISF
and carb ratio Nightscout shows (issue #7771)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/profile-switch-percentage` |
| base | `origin/dev@e3adc91d` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-123` is the measurement |
| semver | `patch` |
| register entries | `BF-123` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/profilefunctions.js getValueByTime (which switches are scaled); everything
that reads it: basal pill and chart basal line, Bolus Wizard Preview, IOB/COB
plugins, day-to-day and loopalyzer reports. A new profilefunctions unit test.

## Why that semver

a bug fix in how an existing record is read; nothing stored changes

## What an operator would notice

> If you use AndroidAPS and switch to a profile at a percentage (for example
> 150%), Nightscout shows the new profile name with the percentage, but the
> basal rate, insulin sensitivity and carb ratio it shows are still those of
> the profile at 100%. AndroidAPS itself uses the right values. Nightscout's
> own display and its Bolus Wizard Preview do not. Temporary basal rates are
> shown correctly. Use AndroidAPS, not Nightscout, to check the rates in
> effect during a percentage switch. This is not medical advice. Ask your
> care team about any change to your insulin settings.

## Who should review this, and why

maintainer, plus someone who runs AndroidAPS

## What was measured

**`git -C externals/cgm-remote-monitor-official grep -q aapsSwitchAdjustment bf/profile-switch-percentage -- lib/`** &nbsp;·&nbsp; kind: `static`

The branch's lib/profilefunctions.js recognises the AndroidAPS 3.x switch
shape (aapsSwitchAdjustment; origin/dev has none and fails this, as it fails
the earlier profileJson/percentage check). A presence check only; the probe
and tests/profile-switch-percentage.test.js decide. Point it at origin/dev
once merged.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by tools/lab/triage-2026-09/profile-switch-
  percentage.js, which needs a cgm-remote-monitor tree with node_modules and
  so is not a queue gate. 2026-09-25: exit 1 on v15.0.8 92d08342 and dev
  4f705217 (AAPS-shaped 150% switch: basal 1.0, ISF 50, IC 10); the
  CircadianPercentageProfile control reads 1.5, 33.33, 6.67 on both. Done
  when the probe exits 0 on the candidate. 2026-09-25: exit 1 on e3adc91d, 0
  on the branch 5a895b49.
- Timeshift for the AndroidAPS 3.x shape is measured by the branch's
  tests/profile-switch-percentage.test.js (+/-2 h at several times, midnight
  wrap, whole-hour truncation), which needs node_modules. The
  CircadianPercentageProfile path is unchanged and still does not shift the
  schedule lookup (info arm of the probe). Not checked in a browser (chart
  basal line, reports).

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/triage-2026-09/profile-switch-percentage.js`](../../tools/lab/triage-2026-09/profile-switch-percentage.js)

## Notes carried on the item

Filed 2026-09-25 from the GitHub triage (issue #7771, opened 2022-12-10). AAPS
side read at AndroidAPS 7e1d537d49 (ProfileSwitchExtension.kt
toNSProfileSwitch; TreatmentMapper.kt). Loop and Trio send no Profile Switch;
Loop's Temporary Override insulinNeedsScaleFactor is likewise not applied to
the displayed basal, which is a separate question. Later cut; the maintainer
decides which switches are scaled. 2026-09-25 - FIXED on bf/profile-switch-
percentage 5a895b49 (local, not pushed), one commit on dev e3adc91d: AAPS 3.x
switches (embedded profileJson, numeric percentage, timeshift in ms, no
CircadianPercentageProfile) read as AAPS reads them - basal x pct/100, ISF/IC
x 100/pct, targets unscaled, schedules at t - trunc-hours (timeshift)
(AndroidAPS BlockExtension.kt:14-18, ProfileSealed.kt:77, 324-365 at
7e1d537d49). 35 tests; suite 3205/0/3 (Node 22.23.2, MongoDB 7.0.43). The
CircadianPercentageProfile path is unchanged: its intended timeshift direction
(t + offset, AAPS 2.x) is opposite to AAPS 3.x (reversed in AndroidAPS
37e3c4532a) and it never applies the shift anyway. 2026-09-26 - Combined run:
all six round-1 branches (bf/activity-date-coercion 20c197bb, bf/entries-
unknown-id f79dc732, bf/maker-level-names 2f50ada9, bf/profile-switch-
percentage 5a895b49, bf/pebble-delta-units aa224c69, bf/v1-writes-v3-history
718efddc) merged on dev e3adc91d as local lab/round1-combined bda225e4
(worktree externals/work/crm-round1-combined): full suite 3292 passing / 0
failing / 3 pending (= 3170 + 122 new tests), Node 22.23.2, MongoDB 7.0.43.
All five probes gave their expected exit codes: bf106 gate 0, maker-language
0, profile-switch-percentage 0, pebble-units 0, v1-writes-v3-history 1 on the
v1 DELETE arm only (kept by decision, BFQ-122). The run carried 718efddc, not
the later test commit d45987f7. Decisions: - 2026-09-26 (maintainer): leave
the CircadianPercentageProfile path as it is; not a defect to fix.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-123` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-25, against cgm-remote-monitor-official `e3adc91d`.*
