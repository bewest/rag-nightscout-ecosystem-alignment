# BF-52 — an age reminder whose 20-minute window passed without a check was never sent

> **Snapshot, 2026-09-23, against `origin/dev` `74fc6619`; fix on local branch `bf3/age-push-once` `896629f8` (not pushed). Node 20.20.0 and 22.23.2, MongoDB 7. Current: the fix is prepared and deferred out of 15.0.9 by the maintainer (2026-09-23), to ship later paired with BFQ-92; item state is in queue `BFQ-52`. Contributor-facing, except §6, which is user-facing. Current facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md).**

## 1. The defect, as measured

All four age plugins (`cannulaage`, `sensorage`, `insulinage`, `batteryage`) have the same shape
at all three levels (info, warn, urgent):

- the **level** is graded on `age >= threshold`, so the pill stays red for as long as the item is
  overdue;
- the **notification** is requested only while `age === threshold` (whole hours) **and**
  `minFractions <= 20`, which is the first 20 minutes of the threshold hour.

**Correction to the register.** The window is 21 minutes (minutes 0–20 of the hour), not one
evaluation. The server evaluates on every heartbeat (`settings.heartbeat` 60 s, `lib/bus.js`) and
on every upload (`bootevent.js` `data-loaded`), so inside the window it asks about 20 times. The
notification is lost only when the server does not evaluate at all during those 21 minutes: a
restart or deploy, a host that sleeps, or a stalled data load. Once that happens, nothing later
asks.

## 2. Reproduction (red on dev)

`tests/age-notify-once.test.js` drives each plugin the way `bootevent.js` does: a fresh
`serverInit` sandbox per evaluation, the **same** plugin instance across evaluations,
`setProperties` then `checkNotifications`, with `requestNotify` captured. Six tests per plugin (24
in all). Each change treatment has one fixed instant, and each evaluation sets the sandbox clock.

On dev `74fc6619`, with the new tests plus the one changed `sensorage` test: **15 passing, 17
failing**. Every failure is the original symptom: nothing is requested (`expected 0 to be 1`;
`the missed URGENT notification is asked for on the first evaluation past the threshold`; sage:
`expected undefined to exist`). The in-window control and the below-threshold/alerts-off control
**pass on dev** for all four plugins, so the harness does see requests when they are made.

**On 15.0.8** (the test copied into a detached 15.0.8 worktree, then removed), the same 16
missed-window tests fail for all four plugins. The iage in-window control fails there too, because
BF-28 (the URGENT branch unreachable) is still present in 15.0.8. So `cage`, `sage` and `bage`
ship this defect today. `iage` ships a worse one (no urgent request at all), and dev has fixed
that.

## 3. The fix

`lib/plugins/agenotify.js` (new, shared) remembers, per plugin instance, which levels have been
requested for the current change event. The event is keyed by the change treatment's date, so a
new change starts over. In each plugin's `checkNotifications`:

- if the property carries a notification (the unchanged 20-minute window), request it and record
  the level, **exactly as before**;
- otherwise, if alerts are on and the item is at or past a threshold whose level has not been
  requested since this change, build the same notification and request it once.

The notification text moved into a per-plugin `notificationFor()` so that both routes build the
same notification. The `notification` property that `findLatestTimeChange` returns is unchanged,
so `/api/v2/properties` output and the e05c2a8c window tests are unchanged.

**Nothing that fires today stops firing.** In the window every evaluation still asks. The change
only adds one request where there were none.

Behaviour choices for the maintainer to confirm:

- **All three levels, not only urgent.** The decision named the urgent push. The same one-line
  defect exists at info and warn, and the same mechanism covers them. Restricting it to urgent is a
  one-line change in each plugin.
- **The record lives in memory.** After a restart, an item that is already past a threshold is
  notified **once more**. That errs towards asking twice rather than never. A host that restarts
  every day will re-send one reminder a day for an overdue item. Persisting the record would avoid
  that and is not done here.
- **The first check after upgrading** sends one notification for each item that is already
  overdue.
- **The catch-up request can be swallowed by an active silence.** `notifications.js`
  `emitNotification` drops a request while `(level, group)` is acknowledged. The window path
  retried about 20 times; the catch-up asks once. Not measured.
- **The in-app alarm raised by a catch-up is cleared on the next tick.** The next evaluation does
  not request it, so `autoAckAlarms` sends `clear_alarm` about a minute later. Inside the window it
  stayed up for up to 20 minutes, as before. Read, not run.
- **An expectation changed.** `tests/sensorage.test.js` "not trigger an alarm when sensor is 6 days
  and 23 hours old" asserted the defect: 167 h is past the default urgent threshold of 166 h. It
  now asserts one URGENT request, and none on the next evaluation. The reason is written in the
  file.
- **README.** The `IAGE_URGENT` entry (added on dev in e05c2a8c) said the upgrade "does not issue a
  catch-up notification". That documented the old behaviour and is replaced. Each
  `*_ENABLE_ALERTS` entry now says when the notification is requested.

## 4. Counts

Full suite, `./tests/*.test.js`, JSON reporter, each run on its own test database:

| run | tree | tests | passing | failing | pending |
|---|---|---:|---:|---:|---:|
| dev, Node 20.20.0 | `74fc6619` | 2389 | 2386 | 0 | 3 |
| dev, Node 22.23.2 | `74fc6619` | 2389 | 2386 | 0 | 3 |
| fix, Node 20.20.0 | `896629f8` | 2413 | 2410 | 0 | 3 |
| fix, Node 22.23.2 | `896629f8` | 2413 | 2410 | 0 | 3 |
| **break-it**, Node 20.20.0 | `896629f8` with the four plugins restored to `74fc6619` and `agenotify.js` removed | 2413 | 2393 | **17** | 3 |

**Delta, by test title, on both Node versions:** 25 titles added and 1 gone. The 24 added in
`age-notify-once.test.js`, plus the renamed sage test, make the 25; the gone title is the sage
test's old name. The 3 pending titles are the same. Nothing else changed.

**Break-it:** the 17 failures are exactly the 16 missed-window tests plus the changed sage test,
with the original symptom (`expected 0 to be 1` / `expected undefined to exist`). The worktree was
restored with `git checkout HEAD -- lib/plugins` and verified clean afterwards.

Dev's baseline matches the brief (2386 / 0 / 3). An earlier baseline attempt was void. Two of my
runners were live at once, and the first test database names did not contain `test`, which trips
the suite's own safety check. Both problems were in my setup, not in dev. All the counts above come
from single sequential runs under a lock.

## 5. What was not measured

- A booted server across a real restart. The restart is modelled as a new plugin instance.
- Delivery after `requestNotify`: `pushnotify` (which suppresses repeats of the same key for
  15 minutes, so the window path could already send a second push around minute 15), Pushover,
  IFTTT and the alarm socket.
- The silence and in-app-clear interplay in §3.
- Non-default thresholds, or `display: days`.

## 6. Operator-facing description (user-facing)

*Plain language. This is not medical advice. Talk to your care team about how you manage site,
sensor, reservoir and battery changes.*

Nightscout can remind you when a cannula (infusion site), sensor, insulin reservoir or pump battery
is getting old. The coloured indicator on screen already stays red for as long as the item is
overdue, and that does not change.

The **optional push reminder** (a notification sent to your phone or other device, which is off
unless you switched it on with a setting such as `SAGE_ENABLE_ALERTS`) could only be sent during
the first 20 minutes of the hour when the item reached its reminder time. If Nightscout was
restarting, asleep or otherwise not checking during those 20 minutes, the reminder was never sent.

With this change, a reminder that was missed that way is sent **once**, the next time Nightscout
checks, and it is not repeated after that. Two things you may notice: after Nightscout restarts, an
item that is already overdue may send its reminder one more time, and right after upgrading you may
get one reminder for each item that is already overdue. The on-screen indicator is the same as
before.

## Files

- Upstream clone, branch `bf3/age-push-once` `896629f8` in `externals/work/crm-bf3-agepush`:
  `lib/plugins/agenotify.js` (new), the four plugins, `tests/age-notify-once.test.js` (new),
  `tests/sensorage.test.js`, `README.md`.
