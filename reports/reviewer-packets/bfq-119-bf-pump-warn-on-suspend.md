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

# Review packet — BFQ-119 (PR #8767)

**BF-119 - PUMP_WARN_ON_SUSPEND never raises a suspended-pump warning (issue
#5622)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/pump-warn-on-suspend` |
| base | `origin/dev@4f705217` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-119` is the measurement |
| semver | `patch` |
| register entries | `BF-119` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/plugins/pump.js updateStatus and its caller prepareData (a few lines),
plus tests/pump.test.js. Changes alarm behaviour only for sites that set
PUMP_ENABLE_ALERTS=true and PUMP_WARN_ON_SUSPEND=true.

## Why that semver

a documented setting starts doing what it says; no stored data or API changes

## What an operator would notice

> If you turned on the Nightscout setting that is supposed to warn you when
> your pump is suspended (PUMP_WARN_ON_SUSPEND), it has never worked:
> Nightscout does not raise that warning, even though the pump status on the
> page says "suspended". Do not rely on Nightscout to tell you the pump is
> suspended. Keep the alerts on your pump and your phone switched on. The
> fix is not in any release yet. This is not medical advice; talk to your
> care team about how you are alerted to a suspended pump.

## Who should review this, and why

maintainer

## What was measured

**`sh -c 'git -C externals/cgm-remote-monitor-official cat-file -e bf/pump-warn-on-suspend:lib/plugins/pump.js &&`** &nbsp;·&nbsp; kind: `static`

The branch no longer tests warnOnSuspend on the wrong object. A presence check
only (origin/dev fails it until the fix merges); the probe below is what says
the warning fires without throwing. Point it at origin/dev once merged.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by tools/lab/triage-2026-09/pump-suspend.js,
  which needs a cgm-remote-monitor tree with node_modules and so is not a
  queue gate. 2026-09-25: exit 1 on v15.0.8 92d08342 and dev 4f705217 (no
  Pump notification); both controls behave. Exit 0 on a scratch copy of dev
  with the fix sketch. The fix is done when the probe exits 0 on the
  candidate.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/triage-2026-09/pump-suspend.js`](../../tools/lab/triage-2026-09/pump-suspend.js)

## Notes carried on the item

2026-09-25 - OPEN upstream as #8767, head 3a2e3773 (7b239c01 plus a dev merge
that includes #8766; the pump files are identical to 7b239c01). Goes into
15.0.9 (decided 2026-09-25, maintainer). 2026-09-24/25 - FIXED on bf/pump-
warn-on-suspend 7b239c01 (local, not pushed), on dev 4f705217: updateStatus
takes prefs and builds result.status first; three tests in tests/pump.test.js
(two fail on dev's pump.js). pump 13 passing; probe exit 0 on the branch, 1 on
dev; full suite 2580/3/0 vs dev 2577/3/0, Node 22.23.2, MongoDB 7.0.43. Filed
2026-09-25 from the GitHub issue triage (issue #5622, opened 2020-04-14).
Fixing only the misplaced test would turn the silent miss into a TypeError on
every suspended status, so both mistakes go in one change with a test that
asserts the WARN notification.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-119` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
