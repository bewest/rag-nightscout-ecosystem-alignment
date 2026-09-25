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

# Review packet — BFQ-120

**BF-120 - the clock view shows an old reading as current when its data fetch
fails (issue #7036)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/clock-stale-offline` |
| base | `origin/dev@ecb63223` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-120` is the measurement |
| semver | `patch` |
| register entries | `BF-120` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/client/clock-client.js (client.query error path, client.render,
client.init timers) and tests/clock-client.test.js. The main page is not
touched.

## Why that semver

a bug fix in how the clock page draws data it already has

## What an operator would notice

> If you or a family member watch glucose on a Nightscout clock page (the
> Clock, Color or Simple view, or a custom clock face), and that page loses
> its connection to your Nightscout site, it keeps showing the last glucose
> value as if it were current. It does not turn grey and does not say how
> old the value is, however long the connection is down. Only the time of
> day keeps changing. Do not rely on a clock page alone. Check the time of
> the reading in the main Nightscout page or your app, and keep the alarms
> on your phone, CGM app or receiver switched on. This is not medical
> advice.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official grep -q 'setInterval(refresh' bf/clock-stale-offline -- lib/clien`** &nbsp;·&nbsp; kind: `static`

The branch's clock timer calls refresh(), which redraws from the last data
before fetching (origin/dev still calls client.query directly and fails this).
A presence check only; the probe below decides. Point it at origin/dev once
merged.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by tools/lab/triage-2026-09/clock-stale-
  offline.js, which needs a cgm-remote-monitor tree with node_modules and so
  is not a queue gate. 2026-09-25: exit 1 on v15.0.8 92d08342 and dev
  4f705217 (30 minutes after the last successful fetch the face says "Just
  now", not stale, in-range colour); the online control shows "30 minutes
  ago" and stale on both. Done when the probe exits 0 on the candidate.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/triage-2026-09/clock-stale-offline.js`](../../tools/lab/triage-2026-09/clock-stale-offline.js)

## Notes carried on the item

2026-09-25 - FIXED on bf/clock-stale-offline 48ba1856 (local, not pushed), on
dev ecb63223: the 20 s timer redraws from the last data before fetching, so
age and stale state keep moving while fetches fail. 5 new tests (3 fail on
dev's clock-client.js); probe exit 0 on the branch, 1 on dev; full suite
2593/3/0 vs dev 2588/3/0, Node 22.23.2, MongoDB 7.0.43. For review: the Simple
face (bn0-sg40) never goes stale; bn13-sg40 proposed. Filed 2026-09-25 from
the GitHub triage (issue #7036, opened 2021-05-31). Issue #8186 (clock reading
age out of sync) may share the mechanism and needs browser console output to
tell. Issue #7377 (clock blank with a URL token) is what a failing first fetch
looks like: with no successful fetch nothing is ever drawn. Candidate for the
remaining 15.0.9 cleanup; the maintainer decides.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-120` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
