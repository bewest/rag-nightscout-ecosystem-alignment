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
for (issue #6220); BF-138 - /pebble in the other units computes the Bolus
Wizard Preview against the wrong settings; BF-139 - /pebble scales readings
other requests share**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/pebble-delta-units` |
| base | `origin/dev@e3adc91d` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-128` is the measurement |
| semver | `patch` |
| register entries | `BF-128`, `BF-138`, `BF-139` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

Three commits at b06eb014: aa224c69 (BF-128), df149642 (BF-139), b06eb014
(BF-138). lib/server/pebble.js only: the delta follows the requested units;
the /pebble sandbox works on its own copies of the readings; iob, cob and bwp
are computed in a sandbox in the site's units and bwpo is converted to the
requested units. tests/pebble-units.test.js and tests/pebble-shared-
state.test.js (new). Changes bgdelta, bwp and bwpo only when a request asks
for the units the site does not use.

## Why that semver

the delta and the Bolus Wizard Preview are returned in the units the request
asked for; other responses are unchanged

## What an operator would notice

> If your Nightscout shows glucose in mmol/L and you use a watch face or
> other display that asks Nightscout's /pebble address for mg/dL, the change
> since the last reading (the delta) arrives in mmol/L while the reading is
> in mg/dL. The delta then looks about 18 times smaller than it is, for
> example -0.1 instead of -2. The reading itself is right. Check the delta
> against the Nightscout page or your CGM app before acting on it. Also,
> when such a display asks for the units your site does not use, the bolus
> wizard preview it shows (Nightscout's estimate of insulin needed or in
> excess) is worked out against settings in the other units, so it can be
> wrong in size and even in sign; for example -2.17 instead of -0.96. Do not
> use a watch face's bolus preview to decide a dose; use your looping or
> pump app. Such a request can also leave glucose values in the wrong units
> for other displays until the next reading arrives. Fixes are ready for
> review for 15.0.9 and are not in any release yet. This is not medical
> advice.

## Who should review this, and why

maintainer. Awaiting the maintainer's BF-139 disclosure decision (public PR or
private advisory) before the branch is pushed.

## What was measured

**`git -C externals/cgm-remote-monitor-official grep -qF "delta.mgdl" bf/pebble-delta-units -- lib/server/pebble.`** &nbsp;·&nbsp; kind: `static`

The branch's pebble.js returns delta.mgdl when mg/dL is asked for (origin/dev
has no delta.mgdl and fails this). Replaces a check for the text "mg/dl",
which the branch passes only through a comment: the fix deliberately leaves
the sandbox units alone, because switching them makes bwp wrong (register
BF-128). A presence check only; the probe and tests/pebble-units.test.js
decide. Point it at origin/dev once merged.

**`git -C externals/cgm-remote-monitor-official grep -qF "unscaledCopy" bf/pebble-delta-units -- lib/server/pebbl`** &nbsp;·&nbsp; kind: `static`

BF-139: the branch's prepareSandbox gives the /pebble sandbox its own copies
of the readings (origin/dev has no unscaledCopy and fails this). A presence
check only; tests/pebble-shared-state.test.js decides. Point it at origin/dev
once merged.

**`git -C externals/cgm-remote-monitor-official grep -qF "outcomeInRequestedUnits" bf/pebble-delta-units -- lib/s`** &nbsp;·&nbsp; kind: `static`

BF-138: the branch converts bwpo to the requested units and computes bwp in a
sandbox in the site's units (origin/dev has no outcomeInRequestedUnits and
fails this). A presence check only; tests/pebble-units.test.js decides. Point
it at origin/dev once merged.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by tools/lab/triage-2026-09/pebble-units.js,
  which needs a cgm-remote-monitor tree with node_modules and so is not a
  queue gate. 2026-09-25: exit 1 on v15.0.8 92d08342 and dev 4f705217 (sgv
  "90", bgdelta -0.1); the three controls behave. Exit 0 on a scratch copy
  of dev with the one-line fix. The fix is done when the probe exits 0 on
  the candidate. 2026-09-25: exit 1 on e3adc91d, 0 on the branch aa224c69.
- BF-138 and BF-139 are decided by the branch's tests, which boot against
  MongoDB, so they are not queue gates: suite on b06eb014 3216/0/3 (25 new:
  4 BF-139, 21 BF-138). Of 18 combinations of site units and request, only
  bwp/bwpo change, in the two mismatched ones (plus BF-128's delta).

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
Filed 2026-09-26 as BF-138 and BF-139. 2026-09-26 - Combined run: all six
round-1 branches (bf/activity-date-coercion 20c197bb, bf/entries-unknown-id
f79dc732, bf/maker-level-names 2f50ada9, bf/profile-switch-percentage
5a895b49, bf/pebble-delta-units aa224c69, bf/v1-writes-v3-history 718efddc)
merged on dev e3adc91d as local lab/round1-combined bda225e4 (worktree
externals/work/crm-round1-combined): full suite 3292 passing / 0 failing / 3
pending (= 3170 + 122 new tests), Node 22.23.2, MongoDB 7.0.43. All five
probes gave their expected exit codes: bf106 gate 0, maker-language 0,
profile-switch-percentage 0, pebble-units 0, v1-writes-v3-history 1 on the v1
DELETE arm only (kept by decision, BFQ-122). The run carried 718efddc, not the
later test commit d45987f7. 2026-09-26 - FIXED BF-139 on df149642 (the /pebble
sandbox gets its own copies of the readings without a stored scaled value) and
BF-138 on b06eb014 (iob, cob and bwp computed in a site-units sandbox; bwpo
converted to the requested units; bwp not converted), both on aa224c69, local,
not pushed. Correction to BF-138's figures: on a booted server the usual wrong
output on an mg/dL site asked for mmol is bwp -0.96 (right by coincidence)
with bwpo 23.2, an mg/dL number in an mmol response, because of BF-139;
-2.17/-61.8 appears only in-process on fresh data or between a load and its
evaluation. On an mmol site asked for mg/dL, bwpo stayed in mmol (1.3) next to
an mg/dL sgv. One BF-128 test expectation changed by design (bwpo now moves
with ?units=mgdl). Suite on b06eb014 3216/0/3 (Node 22.23.2, MongoDB 7.0.43,
fresh database). BF-139 reaches the server's own alarm evaluation (reproduced
on a booted server 2026-09-26); severity raised to safety (alarm integrity);
detail withheld pending the maintainer's disclosure decision. Ready to push,
but awaiting the maintainer's BF-139 disclosure decision (public PR or private
advisory) before anything is pushed; the PR body's update for BF-138/BF-139 is
held back from this repository until then. Decisions: - 2026-09-26
(maintainer): file BF-138 and BF-139, both fixed in 15.0.9 on this branch with
BF-128, one PR. The item goes back from ready-to-push to in-progress, because
the branch will gain their commits (fix in progress). BF-139 is described by
mechanism only (live on 15.0.8).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-128` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-25, against cgm-remote-monitor-official `e3adc91d`.*
