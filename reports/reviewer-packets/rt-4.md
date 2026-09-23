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

# Review packet — RT-4

**Deprecation release - recommended folded into 15.0.9's release notes**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `chore/nightscout-modernization` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=RT-4` is the measurement |
| semver | `minor` |

## What this changes

New code, not just a warning string. lib/server/mmconnect-connect-compat.js
does NOT exist on dev or master - it is born in cut 4, the same branch that
deletes lib/plugins/mmconnect.js.

## Why that semver

adds warnings and a migration shim; removes nothing

## What an operator would notice

> A warning release. If you get your CGM data through the built-in Dexcom
> Share or MiniMed CareLink connection, a future release removes both of
> them, and you will need to move to the nightscout-connect connector first.
> This release tells you whether that applies to you and what to change. If
> you use MiniMed CareLink you will also need to set your country, because
> Nightscout cannot work it out from your existing settings. Nothing stops
> working in this release. Your glucose data continuing to arrive is the
> thing at stake, so please do not skip this one.

## Who should review this, and why

maintainer - this release exists to buy operators time before cut 4

## What was measured

**`node tools/queue/gates/minimed-deprecation-path.js`** &nbsp;·&nbsp; kind: `static`

FAILS while dev carries no named MiniMed escape hatch. GT4 measured the
asymmetry: Dexcom HAS one - bridge-connect-compat.js is on master AND dev with
five DEPRECATION WARNING lines, one naming DEXCOM_BRIDGE_USE_LEGACY. MiniMed's
only warning today is a generic "PLEASE CONSIDER nightscout-connect instead."
naming no setting.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Nobody knows how many operators run MMCONNECT_*, or how many run BRIDGE_*
  and MMCONNECT_* together. Both populations are what decides how long this
  release has to sit before cut 4 follows it, and neither can be measured
  from here.

## Blocked on

`RT-3`

## Evidence

- [`docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`](../../docs/60-research/modernization/gt4-semver-classification-2026-09-15.md)

## Notes carried on the item

DECIDED 2026-09-23 (maintainer) - dropped. The notice goes in 15.0.9's release
notes, as recommended below; no separate deprecation release. 2026-09-23:
local branch bf3/mmconnect-deprecation-warning (5d342ac1, on dev 1f9a9d10, not
pushed) replaces the generic MiniMed warning with one naming every replacement
setting, for 15.0.9. With QUEUE_GATE_REF set to it, the gate's settings check
passes; the shim check stays red by design, because the shim ships with the
removal, which the maintainer lifted onto cut 1. The maintainer confirms
(2026-09-22, operational knowledge) that legacy mmconnect does not work, and
Dexcom BRIDGE_* settings have been served by nightscout-connect by default
since 15.0.8 (a91e8ee4, with a deprecation warning and the
DEXCOM_BRIDGE_USE_LEGACY escape hatch). No working path is left for a separate
release to protect. Recommended: put the notice in 15.0.9's release notes
(MiniMed users: move to CONNECT_SOURCE with your CareLink country; Dexcom
legacy-flag users: the escape hatch goes with cut 4) and drop this release.
The MiniMed shim is still real code and ships with cut 4. BF-44/BF-45 re-
graded low.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-4` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
