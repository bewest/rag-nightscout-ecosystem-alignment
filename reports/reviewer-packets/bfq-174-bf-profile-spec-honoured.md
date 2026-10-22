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

# Review packet — BFQ-174 (PR #8826)

**BF-174 - the bolus calculator's profile picker is ignored; every value comes
from the active profile, a known issue of 15.0.9**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/profile-spec-honoured` |
| base | `official/dev@04d435eb` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-174` is the measurement |
| semver | `patch` |
| register entries | `BF-174` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/profilefunctions.js getCurrentProfile (+5/-1): a spec_profile that names a
store entry is used; anything else gives the active profile as before. The
bolus calculator is the only caller that passes a name, so only its values
(and the IOB and COB it adds) change.

## Why that semver

a documented control that had no effect now works; no API shape changes

## What an operator would notice

> Only for sites that show the profile choice in the Careportal Bolus Wizard
> (more than one profile and the profile plugin's multiple setting): the
> profile you choose is now the one whose sensitivity, targets and carb
> ratio are used. Before, the active profile was used whichever you chose.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor official/dev bf/profile-spec-honoured`** &nbsp;·&nbsp; kind: `static`

the branch contains official/dev (04d435eb on 2026-10-21), so it can be pushed
without a further merge; goes red when dev moves ahead

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Reproduced 2026-10-21 in the headless client: with Default (sens 54) and
  Other (sens 27) in the store and Other chosen, v15.0.8 92d08342 and dev
  4bca2ac2 save profile Other with isf 54; with 292f909a, isf 27.
  tests/profile.spec-profile.test.js runs the accessor directly (5 tests,
  the named-profile one fails without the fix).

## Blocked on

`BFQ-173`

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-21 (later): pushed by the maintainer and opened as #8826 against dev
(bf/profile-spec-honoured, head 827df15e; checked with gh). #8826 (BF-174)
must land with or after #8825 (BF-173). 2026-10-21 (after the release):
bf/profile-spec-honoured 827df15e = merge of dev 04d435eb into 292f909a; full
suite 3576/0/4; not pushed; ready to push, but ORDERING HAZARD: it lands with
or after BF-173 (BFQ-173), never alone. On this branch alone, choosing an
mmol/L profile on an mg/dl display gives 81 U where dev gives 2.3 U, because
dev ignores the choice and uses the active profile; with both branches all
four unit combinations give 2.3 U. blocks_on names BFQ-173 for that reason;
one PR carrying both also satisfies it. RT-0 is removed from blocks_on (15.0.9
released). Integration: scratch/dosing-1510 203027c5, 3604/0/4. 2026-10-21:
bf/profile-spec-honoured 292f909a, one commit on dev 4bca2ac2, not pushed. 260
passing across the same suites as BFQ-173; full suite not run. A scratch merge
with bf/boluscalc-profile-units and #8819 passes 266 (#8819's
getUnits(sbx.time) falls back to the active profile). Broken since 14.0.0 by
#5572 and #5729 (2020). Filed after the 15.0.9 readiness decision; named in
15.0.9's release notes as a known issue (9ed4a5441, 2026-10-21).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-174` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
