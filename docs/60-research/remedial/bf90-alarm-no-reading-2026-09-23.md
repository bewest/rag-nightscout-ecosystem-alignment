# BF-90: an alarm at a page with no reading — reproduction, fix and browser evidence

> **Snapshot, 2026-09-22 (US local; run clock 2026-09-23 UTC), against `origin/master` `92d08342` (tag 15.0.8), `origin/dev` `74fc6619` and local branch `bf3/alarm-no-reading` at `92544d8f`. Historical: the fix is merged into `dev` as #8755, not released; 15.0.8 still has BF-90. Current facts about the defect live in the [backfix register](../../30-design/remedial/nightscout-backfix-register.md) (BF-90) and item `BFQ-90` in [`queue/work-queue.yaml`](../../../queue/work-queue.yaml).**

Audience: contributors and the maintainer, except §1, which is written for operators and users.

## 1. What a person sees (plain language)

Nightscout can raise an alarm for things other than glucose, if the site owner has switched it on: for example a pump reservoir running low (`PUMP_ENABLE_ALERTS`), a loop that has stopped, or a cannula or sensor that is overdue for a change. Most sites have these off, which is the default.

**Before the fix**, if one of those alarms reached a Nightscout page that had **no glucose reading to show** (the big number reads `---`), the page hit an internal error while handling it. Nothing on screen changed: no sound, no red banner, no title change. The error itself was invisible unless you opened the browser's developer console.

**After the fix**, the page handles the alarm without the error. **What you see does not change: the page still does not sound or show the alarm.** The fix removes the error. It does not change when alarms sound.

**The part that matters for safety is the part the fix does not change.** A Nightscout page decides whether to sound a server alarm by looking at the latest glucose reading. With no reading, it treats every alarm as "not for me", including a pump or loop alarm that has nothing to do with glucose. In our test, the same "URGENT: Pump Reservoir Low" alarm filled the page's title bar in red and played the alarm sound when a reading was on screen. When no reading was on screen, the page showed nothing at all. This happens on 15.0.8 and on the development branch, with or without this fix.

If you rely on a Nightscout page for device alarms such as pump, loop or site-change alerts, **do not assume a page showing `---` will alert you**. Keep the alarms on the devices themselves (pump, phone app, CGM receiver) switched on. This is not medical advice. Talk to your care team about how you get alerted.

## 2. Mechanism

`lib/client/index.js`, identical on 15.0.8 and dev (lines 1223–1245 on dev):

```js
alarmSocket.on('urgent_alarm', function(notify) {
  var enabled = (isAlarmForHigh() && client.settings.alarmUrgentHigh) || (isAlarmForLow() && client.settings.alarmUrgentLow);
  if (enabled) { generateAlarm(urgentAlarmSound, notify); }
  else { console.info('urgent alarm was disabled locally', client.latestSGV.mgdl, client.settings); }  // throws
  chart.update(false);                                                                                  // skipped
});
```

`isAlarmForHigh` and `isAlarmForLow` both start with `client.latestSGV &&`. With no reading both are false, the branch evaluates `client.latestSGV.mgdl`, and the handler throws `TypeError: Cannot read properties of undefined (reading 'mgdl')`. The `alarm` (warning) handler has the same shape.

**What the throw costs.** socket.io-client 4.8.3 delivers each packet from a `nextTick` (`manager.js` `ondecoded`), so the throw does not break the connection or drop later packets. Two things are lost: the rest of the handler (`chart.update(false)`), and any listener on the same event registered after the page's own. The 2026-09-22 probe hit the second one (see the [RT-D3 / alarm evidence](../modernization/rt-d3-and-alarm-browser-evidence-2026-09-22.md) §4.5). No alarm is lost to the throw, because the branch it sits in does not sound one.

**A second throw behind the first (not in the register).** `chart` is created by the first non-headless `dataUpdate` (`index.js:1399`). A page that has never received data has no chart. With only the log line guarded, the same handler throws `Cannot read properties of undefined (reading 'update')`. This was measured in a browser (§4, break B). The register and queue entry describe one guard in each handler. Two are needed.

## 3. The fix (`bf3/alarm-no-reading`, `92544d8f`)

- `latestMgdlForLog()` returns the reading or the string `no reading loaded`. It is used by the two log lines.
- `updateChartAfterAlarm()` calls `chart.update(false)` only when a chart exists. It is used by the two handlers.
- `isAlarmForHigh`, `isAlarmForLow` and the `enabled` expressions are **unchanged**.

Test: `tests/client.alarm-no-reading.test.js`, 4 tests. They run against the production bundle through `tests/fixtures/headless.js`, like `careportal.test.js`. They deliver `alarm` and `urgent_alarm` through a recording `io` mock:

| test | kind | dev `74fc6619` | branch |
|---|---|---|---|
| page with no data at all takes urgent + warning alarm without throwing | discriminates | **red**, `reading 'mgdl'` | green |
| page whose data holds no reading takes both kinds without throwing | discriminates | **red**, `reading 'mgdl'` | green |
| still does not sound with no reading (unchanged) | invariant | green | green |
| control: same urgent alarm with a reading does sound | invariant | green | green |

**Harness defect found on the way (pre-existing, not fixed on the branch).** `headless.js` passes the shim an un-normalised path (`tests/fixtures/../../node_modules/...`), so `benv-shim.js`'s `delete require.cache[filename]` misses the key Node stored the bundle under. A second headless suite in the same mocha process gets the cached bundle, and `$` is undefined. `careportal` was the only live headless suite, so nothing had shown this before. The new test busts the resolved key itself, with a comment. The one-line shim fix (`path.resolve`) is left for a separate change.

## 4. Browser evidence

Probe: [`tools/review/probes/alarm-no-reading-browser.js`](../../../tools/review/probes/alarm-no-reading-browser.js). One instance per build. Each instance has its own `node_modules` via [`w2-instance.sh`](../../../tools/review/probes/w2-instance.sh) (which gained a `W2_MONGO_PORT` override), and runs with `NODE_ENV=development`, `ENABLE="careportal basal iob cob bwp boluscalc pump"` and `PUMP_ENABLE_ALERTS=true`. Chrome 149.0.7827.102 was driven by playwright-core 1.63.0 (no browser download). Each run started from a fresh database (`reset` stops the server before dropping). The data is synthetic.

**No server decision is forced.** The trigger is two ordinary REST uploads of pump status: reservoir 8 U (WARN, `alarm`), then 3 U (URGENT, `urgent_alarm`), both counted in MongoDB. The recorder is an `onAny` listener on the page's own alarm connection, which runs before the page's handlers. Liveness is checked in the same window: the server log's emission counts must rise.

**Provenance gate** (`probes/provenance.js --unit bf3/alarm-no-reading`, tokens `latestMgdlForLog` and `updateChartAfterAlarm`, tried verbatim and eval-escaped): BASE dev 0/0, candidate 3/3, bundles differ (10933669 B vs 10935629 B). BASE 15.0.8 (10246799 B) 0/0 against the same candidate. **Pass.**

| scenario | build | page | alarms received (warn / urgent) | page errors | "disabled locally" lines | page presents alarm |
|---|---|---|---|---|---|---|
| `readable`, no reading | 15.0.8 | anonymous | 1 / 1 | **2**, `reading 'mgdl'` | 0 | no |
| | dev | anonymous | 1 / 1 | **2**, `reading 'mgdl'` | 0 | no |
| | branch | anonymous | 1 / 1 | **0** | 2 (`… no reading loaded …`) | no |
| `readable`, 12 in-range readings (control) | 15.0.8 / dev / branch | anonymous | 1 / 1 each | 0 each | 0 | **yes**: title `URGENT: Pump Reservoir Low`, `#container.alarming.urgent`, 1 audio playing |
| `denied`, no reading | 15.0.8 | status-only token | 1 / 1 (**BF-75**: delivered to a page that may not read data) | **2**, `reading 'mgdl'` | 0 | no |
| | 15.0.8 | `readable` token | 1 / 1 | **2**, `reading 'mgdl'` | 0 | no |
| | dev | status-only token | 0 / 0 (BF-75 fixed) | 0 | 0 | no |
| | dev | `readable` token | 1 / 1 | **2**, `reading 'mgdl'` | 0 | no |
| | branch | `readable` token | 1 / 1 | **0** | 2 | no |
| | 15.0.8 + branch diff (scratch, restored) | status-only token (no data, **no chart**) | 1 / 1 | **0** | 2 | no |
| | 15.0.8 + branch diff | `readable` token | 1 / 1 | 0 | 2 | no |

Every run showed the server emitting 1 `alarm` and 1 `urgent_alarm` during the window. MongoDB held 2 pump statuses and the expected entry count (0 or 12).

**Reachability, corrected.** The register says this was "reached only with the server's `/alarm` delivery gate forced open". That is no longer the whole picture. It is reached **without forcing anything**, on both 15.0.8 and dev, by any opt-in device alert at a site with no stored CGM reading. On 15.0.8 it is also reached by any page that may not read data (BF-75).

## 5. Break-its (each run, then restored; `git status` clean afterwards)

| break | where | result | reproduces the original symptom |
|---|---|---|---|
| A: both log lines back to `client.latestSGV.mgdl` | unit | 2 of 4 red, `reading 'mgdl'` | yes |
| A | browser, branch instance, `readable`/none (provenance re-run first) | 2 of 9 arms red, 2 page errors `reading 'mgdl'`, 0 "disabled locally" lines | yes |
| B: both `updateChartAfterAlarm()` back to `chart.update(false)` | unit | 2 of 4 red, `reading 'update'` | yes (the second throw) |
| B | browser, 15.0.8 + branch diff, `denied` status-only page | 1 arm red, 2 page errors `reading 'update'`; the `readable`-token page (which has a chart) stays green | yes |
| B | browser, dev-based branch, `readable`/none | not run as a control: every page that receives alarms on dev has a chart, so this break changes nothing a browser on dev can reach | n/a |
| C: `if (enabled)` → `if (false && enabled)` | unit | control red (1 of 4) | shows the control can fail |
| D: `isAlarmForLow` returns true with no reading | unit | "does not sound with no reading" red (1 of 4) | shows the invariant can fail |

## 6. Suite (`npm test`, own MongoDB 7.0.43 container, production bundle rebuilt first)

| tree | Node | passing | failing | pending |
|---|---|---|---|---|
| dev `74fc6619` | 20.20.0 | 2386 | 0 | 3 |
| dev `74fc6619` | 22.23.2 | 2386 | 0 | 3 |
| `bf3/alarm-no-reading` `92544d8f` | 20.20.0 | 2390 | 0 | 3 |
| `bf3/alarm-no-reading` `92544d8f` | 22.23.2 | 2390 | 0 | 3 |

That is exactly +4, the four new tests. No existing test expectation was changed. **Setup trap:** a worktree prepared with `npm ci --ignore-scripts` has no production bundle, so `careportal` fails in its `before all` hook (2359 / 1 / 4) until `npm run bundle` is run.

## 7. For the reviewer to decide or verify

1. **The local alarm decision (not changed here).** A page with no reading never presents a server alarm, including device alarms unrelated to glucose (§1, §4 control). Whether that is intended is a clinical-behaviour question for the maintainer. It should not ride along on a crash fix. Proposed as a new register entry (see the report that accompanies this record).
2. Whether the log text `no reading loaded` is acceptable, or `undefined` should be kept as before.
3. The second guard (`chart`) is reached only on pages that receive alarms without ever receiving data: 15.0.8 today (BF-75), or any future delivery path with that property. On dev it is defence in depth.

## 8. Reproduce

```bash
export W2_STATE=<scratch>/w2 W2_MONGO_CONTAINER=bf3cli-mongo W2_MONGO_PORT=27193 W2_NODE=20.20.0
export NSREVIEW_DEPS=<dir>/node_modules          # playwright-core@1, mongodb@6
H=tools/review/probes/w2-instance.sh; SEC="$(cat "$W2_STATE/secret")"
docker run -d --name bf3cli-mongo --ulimit nofile=64000:64000 -p 127.0.0.1:27193:27017 mongo:7
$H prep externals/work/crm-bf3-alarmnoread     # and the dev / 15.0.8 worktrees
export ENABLE="careportal basal iob cob bwp boluscalc pump"
$H reset a-fix "$PWD/externals/work/crm-bf3-alarmnoread" 14963 bf3a_fix readable PUMP_ENABLE_ALERTS=true
node tools/review/probes/provenance.js --base http://127.0.0.1:14961 --candidate http://127.0.0.1:14963 --unit bf3/alarm-no-reading
node tools/review/probes/alarm-no-reading-browser.js --url http://127.0.0.1:14963 --secret "$SEC" \
  --mongo mongodb://127.0.0.1:27193 --db bf3a_fix --mode readable --reading none \
  --server-log "$W2_STATE/a-fix.log" --label fix
# --reading present for the control; --mode denied (and `reset … denied`) for the token pages
```
