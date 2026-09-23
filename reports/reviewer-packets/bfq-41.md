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

# Review packet — BFQ-41

**BF-41 - a future-dated reading does not silence the stale-data alarm as
registered; a clock running ahead delays it**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `origin/dev@74fc6619` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=BFQ-41` is the measurement |
| semver | `minor` |
| register entries | `BF-41` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

Nothing built. The behaviour lives in lib/sandbox.js lastEntry (the
notInTheFuture filter, since 556091bf, 2015) and lib/plugins/timeago.js
checkStatus and checkNotifications. Local branch bf3/future-reading-stale
exists at 74fc6619 with no commits.

## Why that semver

Closing the entry as not reproducing ships nothing. Any of the other options
changes when an alarm that is on by default fires - the tolerance loosens it,
a clock-ahead notice adds one - which is a behaviour change on a safety-
adjacent surface and cannot arrive as a silent patch.

## What an operator would notice

> Nightscout can warn you when no new glucose reading has arrived for a
> while. By default it warns in the browser at 15 and 30 minutes. An earlier
> note said that one reading stamped with a time in the future would switch
> that warning off. That is not what happens: Nightscout skips readings
> dated in the future when it decides whether your data is stale, and the
> warning still comes. One related thing does happen. If the phone or device
> uploading your readings has its clock set AHEAD of the real time,
> Nightscout treats each reading as newer than it is, so if your readings
> then stop, the warning comes late, by roughly how far ahead that clock is.
> For example, if the clock is an hour fast, the 15-minute warning comes
> after about an hour and a quarter. You might see the "minutes ago" display
> reading "future" or staying at "1m" while readings are arriving; if you
> do, check the date, time and time zone on the uploading device. Also, when
> Nightscout has no usable reading at all, it gives no stale-data warning.
> If you depend on the stale-data warning, make sure you have another way to
> notice that readings have stopped, and talk to your care team about what
> you rely on Nightscout for. This is not medical advice.

## Who should review this, and why

maintainer, and it needs a decision before it needs code. The registered
symptom does not reproduce through the real sandbox, and the decided 5-minute
tolerance would loosen an alarm that fires today. The four options are in the
evidence: close as not reproducing; build the tolerance and name the
loosening; take on the clock-ahead delay; take on "no usable reading means no
alarm".

## What was measured

**`node tools/queue/gates/timeago-future-reading.js`** &nbsp;·&nbsp; kind: `static`

Loads readings into the data the sandbox is built from and lets the shipping
lib/sandbox.js lastEntry choose the reading, on the server path (serverInit,
checkStatus, checkNotifications with alerts on, the push request recorded) and
the browser path (clientInit, checkStatus). PASSES when the registered defect
does not reproduce - a real reading 40 or 20 minutes old still gives urgent or
warn on both paths, and the push alarm, when a reading 3 to 120 minutes ahead
is also loaded - and FAILS if a future-dated reading ever silences either
path. Three controls (2, 20, 40 minutes, no future reading) must come out
current, warn and urgent. Measured 2026-09-23 - green, 8 checked / 0 failing,
on the official checkout; with the notInTheFuture filter replaced by `return
true` in a scratch copy of the dev tree (--tree), the four future arms go
current with no push, 4 failing, exit 1, and the controls stay green. The
earlier version of this gate stubbed sbx.lastSGVEntry past that filter and was
vacuous.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Nothing gates the residual that does reproduce - an uploader clock running
  ahead delays the stale-data alarm by the size of the skew (F7/F8 in the
  evidence, measured with tools/remedial/bf3/bf41-real-sandbox.js, which is
  a characterisation that always exits 0). A gate for it waits on the
  maintainer's choice of option, because which way it should go red depends
  on the product decided.
- "No usable reading means no alarm" (every loaded reading in the future, or
  none loaded) is the checkStatus no-reading branch assuming current. It is
  not specific to future readings, and nothing gates it.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/60-research/remedial/bf41-future-reading-2026-09-23.md`](../../docs/60-research/remedial/bf41-future-reading-2026-09-23.md)
- [`tools/remedial/bf3/bf41-real-sandbox.js`](../../tools/remedial/bf3/bf41-real-sandbox.js)

## Notes carried on the item

MEASURED 2026-09-23 - does NOT reproduce as registered (reproduced-negative
through the real sandbox on 74fc6619 and 15.0.8, with a break-it that removes
the 556091bf filter and brings the symptom back). The decided tolerance was
not built: in the case "a real reading 20 minutes old plus one 3 minutes
ahead" the warning fires today and would stop firing. It changes nothing in
the clock-ahead case, which is the consequential one. DECIDED 2026-09-23
(maintainer) - a reading dated ahead of the clock is kept as sent, and the
stale-data check uses the newest reading that is not in the future; no new
warning. "In the future" means more than a tolerance ahead of the server
clock, configurable, default 5 minutes. Snooze runs on the wall clock. The
hosted evaluator may apply the same rule, but never to live alarms. BF-44 is a
concrete, shipping way to produce a future-dated reading, which is why BFQ-
MINIMED carries the same severity argument from the other end.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-41` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
