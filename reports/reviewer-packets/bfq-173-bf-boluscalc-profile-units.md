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

# Review packet — BFQ-173 (PR #8825)

**BF-173 - the Careportal Bolus Wizard mixes the profile's units with the
display units, a known issue of 15.0.9**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/boluscalc-profile-units` |
| base | `official/dev@04d435eb` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-173` is the measurement |
| semver | `patch` |
| register entries | `BF-173` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/client/boluscalc.js gatherBoluscalcData (+11): where the profile's units
differ from the display units, its targets and sensitivity are converted to
the display units and rounded as shown, as basalprofile.js does. Browser only.
No change where the units match.

## Why that semver

a wrong suggested value corrected; no API shape changes

## What an operator would notice

> Where your profile is in different units (mg/dL or mmol/L) from the units
> your browser shows, the Careportal Bolus Wizard's suggested insulin is
> worked out in one unit instead of being far too large or negative. The
> saved Bolus Wizard entry then records the values it used, in the units
> shown.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor official/dev bf/boluscalc-profile-units`** &nbsp;·&nbsp; kind: `static`

the branch contains official/dev (04d435eb on 2026-10-21), so it can be pushed
without a further merge; goes red when dev moves ahead

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Reproduced 2026-10-21 in the headless client (each tree's own webpack
  bundle, jsdom, Node 24.15.0, not a browser): an mmol/L profile on an mg/dl
  site gives 81 U and an mg/dl profile on an mmol/L site -1.41 U on v15.0.8
  92d08342 and dev 4bca2ac2, where 2.3 U is right; the same-unit controls
  give 2.30 U on both. With ee0cc4f7 all four give 2.30 U.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/30-design/platform/glucose-units-at-the-profile-boundary-2026-10-21.md`](../../docs/30-design/platform/glucose-units-at-the-profile-boundary-2026-10-21.md)

## Notes carried on the item

2026-10-21 (later): pushed by the maintainer and opened as #8825 against dev
(bf/boluscalc-profile-units, head 34c73bd7; checked with gh). #8826 (BF-174)
must land with or after #8825 (BF-173). 2026-10-21 (after the release):
bf/boluscalc-profile-units 34c73bd7 = merge of dev 04d435eb into ee0cc4f7;
full suite 3573/0/4; break-it ok; not pushed. 15.0.9 is released and RT-0 is
removed from blocks_on. It lands before or with BF-174 (BFQ-174), which must
not land alone. Integration: scratch/dosing-1510 203027c5 (this branch,
BF-174's, BF-09's and #8819 on dev 04d435eb), 3604/0/4. 2026-10-21:
bf/boluscalc-profile-units ee0cc4f7, one commit on dev 4bca2ac2, not pushed; 4
tests added to tests/careportal.test.js (a separate headless file breaks the
next headless suite in the same mocha process). Break-it: the 2 mismatch tests
fail on the unfixed bundle, the 2 controls pass. 257 passing across the
profile, boluscalc, careportal, BWP, basal profile, IOB, COB, plugins, profile
editor, units, sandbox, Loop and OpenAPS suites; full suite not run. Filed
after the 15.0.9 readiness decision; named in 15.0.9's release notes as a
known issue (9ed4a5441, 2026-10-21), which settles UD1 in the design note.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-173` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
