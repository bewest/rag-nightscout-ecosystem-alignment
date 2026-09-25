# `bf3/alarm-no-reading` — an alarm that reaches a page with no reading no longer crashes its handler

**DRAFT — for maintainer review. Not pushed, not opened.** Branch `bf3/alarm-no-reading`, one
commit `92544d8f` on `origin/dev` `74fc6619` (register BF-90, queue BFQ-90). No `CHANGELOG.md`
edit. **Ships in 15.0.9** (decided 2026-09-23). Evidence:
`docs/60-research/remedial/bf90-alarm-no-reading-2026-09-23.md`. The combined run with the other
15.0.9 additions is recorded in `docs/30-design/remedial/rc-15.0.9-integration-record.md`.

> **Read this before the diff.** This is a crash fix only. **It does NOT make a page showing `---`
> sound or show device alarms** (pump, loop, site or sensor age). Before and after this change, a
> Nightscout page with no glucose reading on screen does not present any server alarm. Whether it
> should is a separate decision about alarm behaviour, for later. It is deliberately not part of
> this PR.

---

## What changes for you

*Plain-language summary for people using Nightscout. Nightscout is not a medical device and none
of this is medical advice.*

A few words used below:

- **Device alarm** — an alarm Nightscout can raise about something other than your glucose number,
  if the site owner has switched it on. Examples: a pump reservoir running low, a loop that has
  stopped, a cannula or sensor that is due for a change. Most sites have these off, which is the
  default.
- **`---`** — what the big glucose number on a Nightscout page shows when the page has no recent
  reading to display.

### What was wrong

If a device alarm reached a Nightscout page that showed `---`, the page hit an internal error while
handling it. You could not see the error unless you opened the browser's developer tools. Nothing
on screen changed.

### What changes

The page handles that alarm without the error.

### What does not change, and why it matters

**What you see and hear does not change.** A Nightscout page decides whether to sound a server
alarm by looking at the latest glucose reading. With no reading on screen, it treats every alarm
as "not for me", including device alarms that have nothing to do with glucose. In testing, the same
"URGENT: Pump Reservoir Low" alarm turned the page's title red and played the alarm sound when a
reading was on screen, and showed nothing at all when the page showed `---`. That is true on
15.0.8, on the development branch, and with this fix.

**If you rely on a Nightscout page for device alarms, do not assume a page showing `---` will alert
you.** Keep the alarms on the devices themselves (pump, phone app, CGM receiver) switched on. Talk
to your care team about how you get alerted.

---

## Technical detail

### The defect

`lib/client/index.js`, the `alarm` and `urgent_alarm` handlers (identical on 15.0.8 and `dev`):

```js
var enabled = (isAlarmForHigh() && client.settings.alarmUrgentHigh) || (isAlarmForLow() && client.settings.alarmUrgentLow);
if (enabled) { generateAlarm(urgentAlarmSound, notify); }
else { console.info('urgent alarm was disabled locally', client.latestSGV.mgdl, client.settings); }
chart.update(false);
```

`isAlarmForHigh` and `isAlarmForLow` both begin `client.latestSGV &&`. With no reading both are
false, the `else` branch reads `client.latestSGV.mgdl`, and the handler throws `TypeError: Cannot
read properties of undefined (reading 'mgdl')`. `chart.update(false)` is skipped, and so is any
listener on the same event registered after the page's own. socket.io-client delivers each packet
from a `nextTick`, so the connection and later packets are not affected. No alarm is lost to the
throw, because the branch it sits in does not sound one.

**It is reached without forcing anything.** Any opt-in device alert at a site with no stored CGM
reading gets there, on 15.0.8 and on `dev`. The register's earlier note, "reached only with the
server's delivery gate forced open", is superseded by the browser evidence in the research doc.

**A second throw sits behind the first.** The chart is created by the page's first data update. A
page that has received alarms but never data has no chart. With only the log line guarded, the same
handler throws `reading 'update'`. On `dev` every page that receives alarms also receives data, so
this guard is defence in depth there.

### The fix (`92544d8f`, `lib/client/index.js` only)

- `latestMgdlForLog()` returns the reading, or the string `no reading loaded`. The two log lines
  use it.
- `updateChartAfterAlarm()` calls `chart.update(false)` only when a chart exists. The two handlers
  use it.
- `isAlarmForHigh`, `isAlarmForLow` and both `enabled` expressions are **unchanged**. Whether an
  alarm sounds is exactly as before.

### Tests

`tests/client.alarm-no-reading.test.js`, 4 tests, run against the production bundle through
`tests/fixtures/headless.js`, as `careportal.test.js` is. They deliver `alarm` and `urgent_alarm`
through a recording `io` mock.

| test | kind | on `dev` `74fc6619` | on this branch |
|---|---|---|---|
| a page that has received no data at all takes an urgent alarm without throwing | discriminates | fails, `reading 'mgdl'` | passes |
| a page whose data holds no reading takes both alarm kinds without throwing | discriminates | fails, `reading 'mgdl'` | passes |
| still does not sound an alarm when it has no reading to judge it by (unchanged) | invariant | passes | passes |
| control: the same urgent alarm with a reading loaded does sound | invariant | passes | passes |

The two invariants are there so that a later change to *when* alarms sound cannot land by accident
under this PR. Each was checked by breaking the fix:

| break | result |
|---|---|
| both log lines back to `client.latestSGV.mgdl` | 2 of 4 fail, `reading 'mgdl'` |
| both `updateChartAfterAlarm()` back to `chart.update(false)` | 2 of 4 fail, `reading 'update'` (the second throw) |
| `if (enabled)` → `if (false && enabled)` | the control fails |
| `isAlarmForLow` returns true with no reading | "does not sound with no reading" fails |

**Build the bundle before running these.** A checkout installed with `npm ci --ignore-scripts` has
no production bundle, and `careportal` then fails in its `before all` hook. `npm ci` (which runs
`postinstall`) or `npm run bundle` fixes it.

**A harness defect found on the way, not fixed here.** `tests/fixtures/headless.js` passes the shim
an un-normalised path, so `benv-shim.js`'s `delete require.cache[filename]` misses the key Node
stored the bundle under. A second headless suite in the same mocha process gets the cached bundle
and `$` is undefined. `careportal` was the only headless suite until now. The new test clears the
resolved key itself, with a comment. The one-line shim fix (`path.resolve`) belongs in a separate
change.

### Full suite, Node 20.20.0 and 22.23.2, MongoDB 7.0.43

| build | passing | failing | pending |
|---|---|---|---|
| `dev` `74fc6619` | 2386 | 0 | 3 |
| this branch `92544d8f` | 2390 | 0 | 3 |

Exactly +4, the four new tests. No existing test expectation was changed.

### Browser evidence

Measured in Chrome against a real server for 15.0.8, `dev` and this branch, with the alarm
triggered by two ordinary pump-status uploads (reservoir 8 U, then 3 U), not by forcing a server
decision. With no reading on the page, 15.0.8 and `dev` each logged 2 page errors
(`reading 'mgdl'`) and this branch logged none. With 12 in-range readings (the control), all three
builds showed `URGENT: Pump Reservoir Low` in the title, set the page's urgent alarm state and
played the alarm sound. With no reading, none of the three builds presented the alarm. The data
was synthetic. Full table and probe: the research doc, §4.

## For the reviewer to decide or verify

1. **The alarm decision is not changed here, on purpose.** A page with no reading never presents a
   server alarm, including device alarms unrelated to glucose. Whether that is intended is a
   clinical-behaviour question for the maintainer. It is tracked separately and should not ride
   along on a crash fix.
2. Whether the log text `no reading loaded` is acceptable, or `undefined` should be kept as before.
3. The `chart` guard is reached only by a page that receives alarms without ever receiving data. On
   `dev` it is defence in depth.

## Tested together with the other 15.0.9 changes

On a local integration branch (`rc/15.0.9-additions-d`) cut from the eight-unit 15.0.9 branch
(`b9c9828b`, 2508/0/3), this branch was merged ninth of ten, before `bf3/quickpick-rebuild`. The
merge had no conflicts. The full suite went from 2508 to 2512 passing, with 0 failing and 3
pending, on Node 20.20.0 and MongoDB 7.0.43. The difference is the 4 tests above, and no other test
changed state. After both merges, the full suite passes on Node 20, 22 and 24 against both MongoDB
4.4.24 and 7.0.43 (2520/0/3 each).

On the integrated tree, reverting this commit's `lib/client/index.js` hunk made the two
discriminating tests fail with `reading 'mgdl'`, and the two invariants still passed.
