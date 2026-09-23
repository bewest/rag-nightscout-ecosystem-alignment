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

# Review packet — BFQ-52

**BF-52 - an age reminder whose 20-minute window passed without a check was
never sent**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf3/age-push-once` |
| base | `origin/dev@74fc6619` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-52` is the measurement |
| semver | `patch` |
| register entries | `BF-52` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

One commit, 896629f8, 8 files, +338/-66. lib/plugins/agenotify.js (new,
shared), lib/plugins/{cannulaage,sensorage,insulinage,batteryage}.js,
tests/age-notify-once.test.js (new, 24 tests), tests/sensorage.test.js (one
expectation changed: it asserted the defect), README.md (the *_ENABLE_ALERTS
entries and IAGE_URGENT).

## Why that semver

A bug fix to an opt-in notification, matching the maintainer's 2026-09-23
decision. Nothing that fires today stops firing; a missed request is made
once. No setting, API or on-screen level changes.

## What an operator would notice

> Not released. Nightscout can remind you when a cannula (infusion site),
> sensor, insulin reservoir or pump battery is getting old. The coloured
> indicator on screen already stays red for as long as the item is overdue,
> and that does not change. The optional push reminder (a notification sent
> to your phone or other device, which is off unless you switched it on with
> a setting such as SAGE_ENABLE_ALERTS) could only be sent during the first
> 20 minutes of the hour when the item reached its reminder time. If
> Nightscout was restarting, asleep or otherwise not checking during those
> 20 minutes, the reminder was never sent. With this change, a reminder that
> was missed that way is sent once, the next time Nightscout checks, and it
> is not repeated after that. Two things you may notice - after Nightscout
> restarts, an item that is already overdue may send its reminder one more
> time, and right after upgrading you may get one reminder for each item
> that is already overdue. This is not medical advice; talk to your care
> team about how you manage site, sensor, reservoir and battery changes.

## Who should review this, and why

maintainer, who should confirm the behaviour choices named in the evidence -
all three levels rather than urgent only; the record lives in memory, so a
restart re-sends one reminder for an item already overdue; the first check
after upgrading sends one reminder per overdue item; a catch-up request can be
swallowed by an active silence (not measured).

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf3/age-push-once >/dev/null`** &nbsp;·&nbsp; kind: `static`

Merges into origin/dev with no conflict.

**`cd externals/work/crm-bf3-agepush && n exec 20.20.0 npx mocha --timeout 10000 --exit tests/age-notify-once.tes`** &nbsp;·&nbsp; kind: `unit`

The sequence tests (24, each plugin driven the way bootevent.js does, missed
windows included) and the changed sensorage test, no database; 32 passing.
Control, run 2026-09-23 with tools/queue/gates/ablate.sh (the four plugins put
back to origin/dev, agenotify.js removed) - the new test file exits 16, the
missed-window tests failing with the original symptom. The evidence's full-
tree break-it gives 17 red.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The full suite (2410/0/3 on Node 20.20.0 and 22.23.2, against 2386/0/3 on
  dev, +24 exactly by title) needs MongoDB and is recorded in the evidence,
  not gated here. Delivery after requestNotify (pushnotify, Pushover, the
  alarm socket) and a real restart were not measured.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/60-research/remedial/bf52-age-push-once-2026-09-23.md`](../../docs/60-research/remedial/bf52-age-push-once-2026-09-23.md)

## Notes carried on the item

PREPARED 2026-09-23 - bf3/age-push-once 896629f8, one commit on 74fc6619, not
pushed. Reproduced red on dev and on 15.0.8 first. The window is minutes 0-20
of the threshold hour, not a single evaluation, and the shape is the same at
all three levels in all four plugins. Destination release not decided (plan
section 1a, "backfix 3"). DECIDED 2026-09-23 (maintainer) - send once, even if
the exact check is missed: fire the push the first time the age is at or past
the threshold and remember that it was sent, so a restart or a data gap cannot
swallow it and it does not repeat every check. That makes today's exact-match
behaviour a defect; the fix is on bf3/age-push-once (above). BF-28 masked this
on insulinage for years - the level line was broken, so nobody reached the
notification line. The three sibling plugins have shipped with the same shape
unmasked. Any release note for BF-28 (merged to dev via #8739, arriving in
15.0.9) must get two things right - the push alarm is opt-in and off by
default, and what does reach everyone is the on-screen pill, because the level
is assigned outside the alerts guard.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-52` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
