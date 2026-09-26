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

# Review packet — BFQ-128

**BF-128 - /pebble on an mmol site returns the delta in mmol when mg/dL is asked
for (issue #6220)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/pebble-delta-units` |
| base | `origin/dev@e3adc91d` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-128` is the measurement |
| semver | `patch` |
| register entries | `BF-128` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/pebble.js addExtraData (the delta follows the requested units; the
sandbox units are unchanged) and tests/pebble-units.test.js (new). Changes the
bgdelta /pebble returns only for mmol/L sites asked for mg/dL.

## Why that semver

the delta is returned in the units the request asked for; other responses are
unchanged

## What an operator would notice

> If your Nightscout shows glucose in mmol/L and you use a watch face or
> other display that asks Nightscout's /pebble address for mg/dL, the change
> since the last reading (the delta) arrives in mmol/L while the reading is
> in mg/dL. The delta then looks about 18 times smaller than it is, for
> example -0.1 instead of -2. The reading itself is right. Check the delta
> against the Nightscout page or your CGM app before acting on it. The fix
> is not in any release yet. This is not medical advice.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official grep -qF "delta.mgdl" bf/pebble-delta-units -- lib/server/pebble.`** &nbsp;·&nbsp; kind: `static`

The branch's pebble.js returns delta.mgdl when mg/dL is asked for (origin/dev
has no delta.mgdl and fails this). Replaces a check for the text "mg/dl",
which the branch passes only through a comment: the fix deliberately leaves
the sandbox units alone, because switching them makes bwp wrong (register
BF-128). A presence check only; the probe and tests/pebble-units.test.js
decide. Point it at origin/dev once merged.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by tools/lab/triage-2026-09/pebble-units.js,
  which needs a cgm-remote-monitor tree with node_modules and so is not a
  queue gate. 2026-09-25: exit 1 on v15.0.8 92d08342 and dev 4f705217 (sgv
  "90", bgdelta -0.1); the three controls behave. Exit 0 on a scratch copy
  of dev with the one-line fix. The fix is done when the probe exits 0 on
  the candidate. 2026-09-25: exit 1 on e3adc91d, 0 on the branch aa224c69.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/triage-2026-09/pebble-units.js`](../../tools/lab/triage-2026-09/pebble-units.js)

## Notes carried on the item

Filed 2026-09-25 from the GitHub issue triage (issue #6220, opened
2020-10-10). A past maintainer comment suggested deprecating /pebble instead;
that is the maintainer's decision. No client in the externals corpora calls
it. 2026-09-25 - FIXED on bf/pebble-delta-units aa224c69 (local, not pushed),
one commit on dev e3adc91d: addDelta uses delta.mgdl unless mmol is requested;
sandbox units unchanged, because the register's first fix shape
(prepareSandbox to mg/dl) gives bwp "20.32" against the site's "-0.96" on an
mmol site asked for mg/dL (measured). 21 tests; suite 3191/0/3 (Node 22.23.2,
MongoDB 7.0.43). Two further observations await the maintainer and are not
filed: an mg/dL site asked for ?units=mmol computes BWP in an mmol sandbox
against the mg/dL profile (bwp -2.17 against -0.96); and a shared-state
mechanism in which one /pebble request's scaled values persist on shared data.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-128` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-25, against cgm-remote-monitor-official `e3adc91d`.*
