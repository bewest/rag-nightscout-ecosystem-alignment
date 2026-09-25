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

# Review packet — BFQ-134

**BF-134 - every Loop remote command leaves an APNs connection and a heartbeat
timer open**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/loop-apns-shutdown` |
| base | `origin/dev@96a2c948` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-134` is the measurement |
| semver | `patch` |
| register entries | `BF-134` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/loop.js (+6/-2): build the APNs provider just before the send and
shut it down when the send settles; tests/loop-apns-connections.test.js (new);
a no-op shutdown() on the mocked provider in tests/loop-server.test.js (that
file is deleted by #8419, so the branch is re-merged after #8419).

## Why that semver

a resource leak fix; no API or setting changes

## What an operator would notice

> If you use Loop's remote commands through Nightscout (remote overrides,
> carbs or bolus), each command left a connection to Apple's push service
> open until Nightscout restarted, so a site that sends many commands kept
> more and more connections and memory. This release closes each one when
> its push is done. Nothing changes in how commands are sent.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official show bf/loop-apns-shutdown:lib/server/loop.js | grep -q 'provider`** &nbsp;·&nbsp; kind: `static`

The branch's loop.js shuts its APNs provider down (origin/dev has no shutdown
call and fails this). A presence check; the test and the probe decide. Point
it at origin/dev once merged.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured by a probe kept with the fix notes (a local HTTP/2 APNs stand-in
  counting open sessions and heartbeat intervals): 1/5/20 left open after
  1/5/20 commands on v15.0.8 and dev, 0 on the branch. tests/loop-apns-
  connections.test.js is the in-repo check (3 fail on dev's loop.js).

## Blocked on

`RT-PR-8419`

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-09-25 - Re-merged with dev 96a2c948 after #8419 (68937a77: the
tests/loop-server.test.js conflict resolved by deletion; #8419's
loopnotifications mock already has shutdown()), plus c068f935 (the new test
reads certificates from tests/fixtures/, where #8419 moved them). Head
c068f935: 12 passing on Node 20/22/24 for the two loop test files; the 3 new
tests fail with dev's loop.js; probe exit 0; full suite 3170/3/0, Node
22.23.2, MongoDB 7.0.43. Filed 2026-09-25, found from #8419's test hang. Fixed
on bf/loop-apns-shutdown 8046336d, re-merged with dev fbaa4a2a (da2f1763,
local). Full suite 3120/0/3 vs dev 3117/0/3 (Node 22.23.2, MongoDB 7.0.43).
Whether it goes into 15.0.9 is the maintainer's decision.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-134` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
