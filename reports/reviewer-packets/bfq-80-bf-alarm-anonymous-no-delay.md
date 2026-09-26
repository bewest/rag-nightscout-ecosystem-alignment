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

# Review packet — BFQ-80

**BF-80 - an alarm viewer with no credential is held by the failed-login delay
of its address (the cost of BF-75's fix)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/alarm-anonymous-no-delay` |
| base | `origin/dev@e3adc91d` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-80` is the measurement |
| semver | `patch` |
| register entries | `BF-80` |

## What this changes

One commit at 8e295769. lib/authorization/index.js (new resolveAnonymous;
resolve() and every HTTP path unchanged), lib/api3/alarmSocket.js (a subscribe
with no credential uses it), tests/api3.alarm-socket.anonymous-delay.test.js
(new) and an authFailDelay option in tests/fixtures/api3/instance.js (default
0 as before). It narrows a brute-force control for the no-credential case, so
it goes in its own PR with its own review.

## Why that semver

an anonymous /alarm subscribe is answered without the failed-login delay;
every credentialed path is unchanged

## What an operator would notice

> On the next release as it stands (15.0.9), if a device in your home keeps
> failing to sign in to Nightscout (for example an uploader or follower app
> with an old API secret), a Nightscout page open in a browser on the same
> home network can receive an alarm late, by about a minute or more, with
> nothing on the page saying so. 15.0.8 does not have this delay. With this
> fix, a page where nobody is signed in is no longer held back. A page or
> app that is signed in still is, so fix the device that keeps failing to
> sign in. A fix is ready for review for 15.0.9 and is not in any release
> yet. Nightscout is not a medical device and this is not medical advice;
> keep a second way of being alerted and talk to your care team if you rely
> on these alarms.

## Who should review this, and why

maintainer (security; it narrows the failed-login delay)

## What was measured

**`git -C externals/cgm-remote-monitor-official grep -qF "resolveAnonymous" bf/alarm-anonymous-no-delay -- lib/au`** &nbsp;·&nbsp; kind: `static`

The branch answers a no-credential /alarm subscribe through
authorization.resolveAnonymous (origin/dev has no such function and fails
this). A presence check only; tests/api3.alarm-socket.anonymous-delay.test.js
decides. Point it at origin/dev once merged.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The alarm timing needs a booted server and MongoDB, so it is not a queue
  gate. Measured 2026-09-26 on a booted server with the default delay after
  3 failed logins from the viewer's address: anonymous on a readable site,
  ack 9999 ms and no alarm within 20 s on e3adc91d, ack 1 ms and alarm at 13
  ms on 8e295769; anonymous on a denied site answered in 1 ms with read
  false and still no alarm (BF-75 holds); every credentialed subscribe,
  valid or not, unchanged (ack about 10 s, alarm at the next repeat, 37.7 s
  readable, 49.5 s denied). The probe script is held outside version control
  (mechanism, not recipe).
- Not covered by the fix, by the decision: a signed-in viewer on an address
  in the delay, a socket that connects without subscribing, and main-
  namespace chart data still wait. Making connect-time admission skip the
  delay for a no-credential socket too is a one-hunk option awaiting the
  maintainer.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Split out of ADV-ALARM (which keeps BF-75 and BF-76 and names BF-80) so that
the branch has one item, as every fix branch does. BF-80 is only on dev (it is
the cost of BF-75's fix), so it does not reach an operator on 15.0.8.
2026-09-26 - FIXED on bf/alarm-anonymous-no-delay 8e295769 (local, not
pushed), one commit on dev e3adc91d: a /alarm subscribe carrying no credential
(secret, jwtToken, token and accessToken all absent, null or empty) is
answered with AUTH_DEFAULT_ROLES without the failed-login delay; #8754's
anonymous-waits test still passes. Suite 3180/0/3, 10 new tests (4 fail on
e3adc91d) (Node 22.23.2, MongoDB 7.0.43, fresh database). Decisions: -
2026-09-26 (maintainer): option 1 in the register's numbering (the decision
round called it option 2) - a viewer presenting no credential is not held by
the failed-login delay; signed-in viewers keep it. Recorded in ADV-ALARM as
well.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-80` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-25, against cgm-remote-monitor-official `e3adc91d`.*
