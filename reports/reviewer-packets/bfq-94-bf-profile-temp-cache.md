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

# Review packet — BFQ-94

**BF-94 - a kept profile instance can return a temp basal that has been replaced**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/profile-temp-cache` |
| base | `official/dev@ca6fcfaf` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-94` is the measurement |
| semver | `patch` |
| register entries | `BF-94` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/profilefunctions.js:19 (module-scope prevBasalTreatment), :455-456 (the
early return in tempBasalTreatment), updateTreatments at :292-311 (clears the
cache, not prevBasalTreatment). The same on 15.0.8.

## Why that semver

if it is a defect at all, the fix is a bug fix

## What an operator would notice

> Nightscout keeps a remembered copy of the most recent temporary basal rate
> it looked up. When new treatment data arrives, that copy is not always
> refreshed, so a page that stays open might show a temporary basal rate
> that has since been changed or cancelled. This was shown inside
> Nightscout's code but has not been checked on a real page, so it is not
> yet known whether you would ever see it. The server's own checks are not
> affected. This is not medical advice; your pump or AID app is the record
> of what was delivered.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Reproduced at module level while building tools/remedial/bf3/bf09-dedup-
  zero.js (evidence section 3.2); no standalone instrument exists. A unit
  gate would create one profilefunctions instance, load a temp, replace it
  through updateTreatments and assert the lookup returns the new value. The
  browser, where the instance is kept, was not measured.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/60-research/remedial/bf09-dedup-zero-measurement-2026-09-23.md`](../../docs/60-research/remedial/bf09-dedup-zero-measurement-2026-09-23.md)

## Notes carried on the item

2026-10-02 (session -d4): measured in a browser and fixed. Severity: moderate,
display only (basal pill and line keep a cancelled or shortened temp on an
open page; a reload is right). Branch bf/profile-temp-cache 2a64c500, one
commit on dev ca6fcfaf (lib/profilefunctions.js +6/-1; tests/profile-temp-
cache.test.js, 4 tests, 3 fail on ca6fcfaf; break-it: reset only fails test 3,
per-instance only fails 1-2). Full suite 3538/0/4. Harness
tools/lab/bf94-browser/ (run 2 authoritative). PR body: reports/phase0-pr-
bodies/profile-temp-cache.md. Whether it goes into 15.0.9 is being put to the
maintainer; not in RT-0's blocks_on. Filed 2026-09-23, a side finding of the
BF-09 measurement. Not BF-09.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-94` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
