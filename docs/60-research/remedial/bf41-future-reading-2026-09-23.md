# BF-41 — a future-dated reading does not silence the stale-data alarm through the real sandbox

> **Snapshot — measured 2026-09-23 against `origin/dev` `74fc6619` and tag `15.0.8` (`92d08342`), Node 20.20.0. Status: the defect as registered does not reproduce. No fix was built, because building the decided fix would only loosen an alarm. Branch `bf3/future-reading-stale` exists locally at `74fc6619` with no commits. Contributor-facing, except §7, which is user-facing. Current facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md).**

## 1. The claim, and why it was not measured before

BF-41 says a reading timestamped ahead of the server clock switches off both stale-data alarm
paths. `lib/plugins/timeago.js` computes staleness as `sbx.time - lastSGVEntry.mills`, which is
negative for a future reading, so the status never leaves `current`.

The arithmetic is right. What it leaves out is where `lastSGVEntry` comes from.
`lib/sandbox.js` `lastEntry`, which `lastSGVEntry` calls, skips every entry later than
`sbx.time`:

```js
return entries.slice().reverse().find(function notInTheFuture (entry) {
  return sbx.entryMills(entry) <= sbx.time;
});
```

This has been in place since `556091bf` ("don't let future data block the current", 2015) and is
in every tag from 0.10.0, including 15.0.8. The timeago plugin never sees a future reading, so the
negative age at `timeago.js:26` and `:97` cannot happen with data that came through the sandbox.

The queue's reproduction gate, `tools/queue/gates/timeago-future-reading.js`, replaces
`sbx.lastSGVEntry` with a stub that returns the future reading. That skips the one step that
prevents the symptom, so the gate reproduces a state the shipping code never reaches.

## 2. Measurement

`tools/remedial/bf3/bf41-real-sandbox.js <tree>` loads `ctx.ddata.sgvs`, builds the sandbox with
`serverInit` (server push path, `enableAlerts` on) and `clientInit` at the wall clock (browser
path), and asks both. It needs no database.

Offsets are minutes relative to the clock. Output was identical on `74fc6619` and `15.0.8`:

| case | readings loaded | reading used | server status | push alarm | browser status |
|---|---|---:|---|---|---|
| C1 control | −2 | −2 | current | none | current |
| C2 control | −20 | −20 | warn | WARN | warn |
| C3 control | −40 | −40 | urgent | URGENT | urgent |
| F1 | +5 only | none | current | none | current |
| F2 | +120 only | none | current | none | current |
| **F3** | −40, +120 | −40 | **urgent** | **URGENT** | **urgent** |
| **F4** | −20, +3 | −20 | **warn** | **WARN** | **warn** |
| F5 | −2, +120 | −2 | current | none | current |
| F7 | uploader 60 min ahead, stopped 15 min ago | 0 | current | none | current |
| F8 | uploader 60 min ahead, stopped 76 min ago | −16 | warn | WARN | warn |

F3 and F4 are the register's claim: a real reading goes stale and a future one arrives. **Both
alarm paths fire**, on dev and on 15.0.8.

**Break-it (the harness is not vacuous).** With `lastEntry`'s filter replaced by `return true` in
the dev worktree (then restored with `git checkout`), F3 and F4 went to `current` / no push /
`current` on both paths, which is exactly the register's symptom. The controls were unchanged. So
the filter is what prevents the symptom, and the harness can see it when it happens.

## 3. What does happen

Two narrower behaviours were measured. Neither is the one registered.

- **Only future readings loaded (F1, F2).** `lastSGVEntry` is empty, and `checkStatus` takes the
  `!lastSGVEntry` branch ("assume current"). The same branch runs when no reading at all has been
  loaded. The server loads two days of entries (`dataloader.js` `TWO_DAYS`), so this needs every
  reading in that window to be in the future, or no reading at all. It is a property of "no usable
  data means no alarm", not of future readings in particular.
- **An uploader clock that runs ahead delays the alarm by the size of the error (F7, F8).** Once
  the wall clock passes a future reading's timestamp, that reading is used as if it were current.
  With an uploader 60 minutes ahead, the warning that a correct clock would raise 15 minutes after
  the feed stops comes about 75 minutes after it stops. **This is the consequential case.** The
  decided fix does not change it, because the fix is about readings that are still ahead of the
  clock. v1 entries record no server-receipt time (`lib/server/entries.js:118-126` derives
  `sysTime` from the reading itself; read, not executed), so an arrival-based check would need new
  data.

Snoozes already run on the wall clock. The server compares `ctx.ddata.lastUpdated` (set from
`Date.now()` at each data load, `dataloader.js:68`) with an ack time from `Date.now()`
(`notifications.js:60`, `:173`). The browser uses `Date.now()` (`lib/client/index.js` `notAcked`).
That was read, not tested.

## 4. Why the decided fix was not built

The decision (2026-09-23): the stale-data check ignores a future-dated reading, keeps it as sent,
and has a configurable tolerance with a default of 5 minutes.

Measured against today's code:

- **"Ignore a future-dated reading, keep it as sent."** This is what the shipping code already
  does, with a tolerance of zero. Stored data is not rewritten.
- **"Tolerance, default 5 minutes."** Adding one would make a reading up to 5 minutes ahead count
  as fresh. That is a loosening. **In F4 (a real reading 20 minutes old plus one 3 minutes ahead)
  the warning fires today and would stop firing.** A reading did arrive, so this may be the
  intended product, but it is a case where the fix suppresses an alarm that fires today. The
  brief says to design against exactly that, so it is left for the maintainer.
- It changes nothing in F1, F2, F7 or F8.

The brief's step 2 ("first reproduce on dev with a failing test") cannot be met for the stated
symptom, and the rule is to stop on a mismatch rather than build the nearest thing that works. No
setting was added. A name that fits the existing variables, if one is wanted, would be
`ALARM_TIMEAGO_FUTURE_MINS` read through `lib/settings.js` like `alarmTimeagoWarnMins` (env
`ALARM_TIMEAGO_WARN_MINS`), not through a direct `process.env` read (BF-46).

## 5. Options for the maintainer

1. **Close BF-41 as not reproducing as stated**, correct the register row, and fix the gate so it
   runs through `sbx.lastEntry` instead of a stub. Nothing ships.
2. **Build the decided tolerance** as a setting, with the F4 loosening named in the release notes.
3. **Take on the clock-ahead delay (F7/F8)**, which is the real case. It needs a design decision:
   for example, a reading that arrives already ahead of the clock by more than a tolerance could
   raise its own notice ("readings are dated in the future, check the uploader's clock"). That is
   the other product the register described. The 2026-09-23 decision said "no new warning".
4. **Take on "no usable data means no alarm" (F1/F2)**, separately from future readings.

## 6. What was not measured

- No end-to-end run through a booted server and a real browser. Both paths were driven through the
  shipping sandbox and plugin, not the stub. `bootevent`'s tick and `lib/client/index.js` were
  read, not run.
- The alarm socket, `pushnotify` and Pushover delivery after `requestNotify`.
- The client's hibernation heuristic (a gap of more than 20 s between checks returns `current`).
  The harness uses the server branch to keep it out of the arms.
- Whether any uploader actually produces F7/F8. BF-44 names one mechanism; its magnitude was
  measured there, not here.

## 7. Operator-facing description (user-facing)

*Plain language. This is not medical advice. Talk to your care team about what you rely on
Nightscout for.*

Nightscout can warn you when no new glucose reading has arrived for a while. By default it warns in
the browser at 15 and 30 minutes. An earlier note said that one reading stamped with a time in the
future would switch that warning off. That is **not what happens**: Nightscout skips readings that
are dated in the future when it decides whether your data is stale, and the warning still comes.

One related thing does happen. If the phone or device uploading your readings has its clock set
**ahead** of the real time, Nightscout treats each reading as newer than it is. If your readings
then stop, the warning comes late, by roughly how far ahead that clock is. For example, if the clock
is an hour fast, the 15-minute warning comes after about an hour and a quarter. What you might see
is the "minutes ago" display reading "future" or staying at "1m" while readings are arriving. If you
see that, check the date, time and time zone on the uploading device. If you depend on the stale-data
warning, make sure you have another way to notice that readings have stopped.

## Files

- `tools/remedial/bf3/bf41-real-sandbox.js` — the harness (this repo).
- Worktrees (upstream clone): `externals/work/crm-bf3-future` (branch `bf3/future-reading-stale`,
  no commits), `externals/work/crm-bf3-1508` (detached at `15.0.8`).
