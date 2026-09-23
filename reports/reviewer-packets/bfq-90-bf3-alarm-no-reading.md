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

# Review packet — BFQ-90

**BF-90 - an alarm at a page with no reading throws in the client**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf3/alarm-no-reading` |
| base | `origin/dev@74fc6619` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-90` is the measurement |
| semver | `patch` |
| register entries | `BF-90` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

One commit, 92544d8f, 2 files, +165/-4. lib/client/index.js - two helpers,
latestMgdlForLog() for the two log lines and updateChartAfterAlarm() for the
two chart.update calls, so two guards per handler; the alarm decision
(isAlarmForHigh, isAlarmForLow, enabled) is unchanged. tests/client.alarm-no-
reading.test.js (new, 4 tests). Client-side, so it needs a rebundle, not a
restart.

## Why that semver

a client-side bug fix; what is shown and sounded is unchanged with or without
data

## What an operator would notice

> Not released. If a Nightscout page that has no glucose reading to show
> (the big number reads ---) receives an alarm - for example an optional
> pump, loop or site-change alert that the site owner has switched on - the
> page hits an internal error while handling it. You would not see the
> error; it appears only in the browser's developer console. This fix
> removes the error. It does not change when alarms sound. The error costs
> no alarm only because a page with no reading already shows and sounds no
> server alarm at all, including device alarms (see BFQ-92). That silence is
> the part that matters for safety, and this fix does not change it. If you
> rely on a Nightscout page for device alarms such as pump, loop or site-
> change alerts, do not assume a page showing --- will alert you; keep the
> alarms on the devices themselves switched on. This is not medical advice;
> talk to your care team about how you get alerted.

## Who should review this, and why

maintainer. Decide whether the log text "no reading loaded" is acceptable. The
alarm decision itself is deliberately not changed here - that is BFQ-92, a
clinical-behaviour decision that should not ride along on a crash fix.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf3/alarm-no-reading >/dev/nul`** &nbsp;·&nbsp; kind: `static`

Merges into origin/dev with no conflict.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The branch's own test, tests/client.alarm-no-reading.test.js (4 passing),
  runs against the PRODUCTION BUNDLE in node_modules/.cache, not against
  lib/client/index.js. Measured 2026-09-23 - tools/queue/gates/ablate.sh
  with the fix reverted stays green (exit 0), because the ablated worktree
  borrows the donor's already-built bundle. So as a queue gate it would be
  vacuous. A gate needs the bundle rebuilt inside the ablated tree (npm run
  bundle). The evidence records the break-its run by hand with the bundle
  rebuilt - A (log lines back) 2 of 4 red, B (chart guard back) 2 of 4 red,
  C and D showing the invariants can fail - and a browser run on 15.0.8, dev
  and the branch.
- The full suite (2390/0/3 on Node 20.20.0 and 22.23.2, +4 exactly) needs
  MongoDB and a rebuilt bundle, and is recorded in the evidence.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf3-alarm-no-reading.md`](../../reports/phase0-pr-bodies/bf3-alarm-no-reading.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/60-research/remedial/bf90-alarm-no-reading-2026-09-23.md`](../../docs/60-research/remedial/bf90-alarm-no-reading-2026-09-23.md)
- [`docs/60-research/modernization/rt-d3-and-alarm-browser-evidence-2026-09-22.md`](../../docs/60-research/modernization/rt-d3-and-alarm-browser-evidence-2026-09-22.md)
- [`docs/30-design/remedial/rc-15.0.9-additions-d-2026-09-23.md`](../../docs/30-design/remedial/rc-15.0.9-additions-d-2026-09-23.md)

## Notes carried on the item

PREPARED 2026-09-23 - bf3/alarm-no-reading 92544d8f, one commit on 74fc6619,
not pushed. Reachability corrected: it is reached with no forcing, on 15.0.8
and dev, by any opt-in device alert at a site with no stored CGM reading (and
on 15.0.8 also by a page that may not read data, BF-75). It was first seen
with the /alarm gate forced open. Register grade re-stated 2026-09-23 as low -
reachable, not latent - because the throw's own cost is a skipped chart
redraw; "no alarm is lost" holds only because the page drops every server
alarm when it has no reading (BF-92, BFQ-92). A second throw behind the first
(no chart on a page that never received data) is why each handler needs two
guards. SHIPS IN 15.0.9 (maintainer, 2026-09-23). Integrated on
rc/15.0.9-additions-d 5764156e, 2520/0/3 on every Node and MongoDB pair
(docs/30-design/remedial/rc-15.0.9-additions-d-2026-09-23.md); PR body drafted
in reports/phase0-pr-bodies/bf3-alarm-no-reading.md.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-90` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
