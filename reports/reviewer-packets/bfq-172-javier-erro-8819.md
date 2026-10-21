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

# Review packet — BFQ-172 (PR #8819)

**BF-172 - the Bolus Wizard Preview mixes the profile's units with the display
units (#8819 proposed), a known issue of 15.0.9**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `javier-erro:#8819` |
| base | `official/dev@fade2299` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-172` is the measurement |
| semver | `patch` |
| register entries | `BF-172` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/plugins/boluswizardpreview.js calc and its warning check: convert the
profile's sensitivity and both targets to the display units before use (as
basalprofile.js does for sensitivity). Client and server both run the plugin.
No change where the profile and display units match.

## Why that semver

a wrong displayed value corrected; no API shape changes

## What an operator would notice

> On a site whose profile is in different units from the site's display
> units, the BWP pill, its pop-up and the BWP warning show values in the
> right units instead of ones about 18 times off.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured 2026-10-21 in the plugin's unit harness (Node 24.15.0, not in a
  browser): #8819's new test copied onto v15.0.8 92d08342 and dev 4bca2ac2
  fails on both (estimate 80 U, expected 1.29 U); with #8819's
  boluswizardpreview.js on 4bca2ac2 it passes (14 passing). The reverse case
  (mg/dL profile, mmol/L site) read, not run.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Filed 2026-10-21 from the check of PR #8819 (opened 2026-10-20). Decision
2026-10-21 (the maintainers): a known issue of 15.0.9, named in the release
notes; #8819 is based on fade2299 and needs dev merged in before it lands,
after 15.0.9.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-172` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
