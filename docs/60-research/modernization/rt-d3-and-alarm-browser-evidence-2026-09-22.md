# RT-D3 treatment drag and alarm delivery under `denied`: browser evidence

> **Snapshot, 2026-09-22 (US local; run clock 2026-09-23 01:10 to 01:22 UTC), against `origin/master` `92d08342` (tag 15.0.8) and `origin/dev` `74fc6619`. Historical: this is the automated evidence for RT-D3, answered 2026-09-24 (the drag check passed by hand and in automation), and for alarm delivery under `AUTH_DEFAULT_ROLES=denied`; both were checked by hand in [manual lab checks on the 15.0.9 rc](../remedial/manual-lab-15.0.9-rc-2026-09-23.md). Nothing measured here is released. Current facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md) (BF-54, BF-57, BF-75) and the `RT-D3` entry in [`queue/work-queue.yaml`](../../../queue/work-queue.yaml).**

Audience: contributors and the maintainer. Contributor-facing and technical. Not medical advice.

## Summary

| question | 15.0.8 `92d08342` | dev `74fc6619` | same on both? |
|---|---|---|---|
| **A.** A treatment dragged by a known number of pixels is stored at the time the chart axis gives for that pixel offset | yes, 2 of 2 accepted in-window drags, within 1 px | yes, 2 of 2, within 1 px | yes |
| **A.** A drag whose confirmation is cancelled leaves `created_at` unchanged | yes, stored string unchanged | yes, stored string unchanged | yes |
| **A.** Right clamp engages | yes, stored time = right edge of the chart window, **+59.2 min after now** | yes, right edge, **+59.7 min after now** | yes |
| **A.** Left clamp engages | yes. The drop turns into a **Remove** prompt, not a Move | yes, Remove prompt | yes |
| **A.** Page errors, main page | 0 | 0 | yes |
| **A.** Day-to-day report renders | 7 day charts, 86 circles, 0 page errors | 7 day charts, 86 circles, 0 page errors | yes |
| **B.** `AUTH_DEFAULT_ROLES=denied`: a person who types the API secret at the prompt receives the urgent-low alarm | not measured (by brief) | yes, 2 of 2 alarms, page shows alarm state | n/a |
| **B.** `denied`: a page opened with a `readable` token receives it | not measured | yes, 2 of 2 | n/a |
| **B.** `denied`: a page that is not authenticated, or authenticated without data-read permission, does not receive it, and the server is alive during that window | not measured | yes, 0 of 2. Server emitted 2; the page's own live connection received 3 viewer-count broadcasts | n/a |
| **B.** `readable` default: an anonymous page still receives it | not measured | yes, 2 of 2 | n/a |

Each property above also has a control that was broken on purpose and went red (§3.4, §4.4).

## 1. Measurement basis

| item | value |
|---|---|
| source clone | `externals/cgm-remote-monitor-official`, fetched 2026-09-22; `origin/dev` = `74fc6619f171`, `origin/master` = `92d0834219aa` = tag `15.0.8` |
| worktrees (created for this run, left in place) | `externals/work/crm-w2-d3-1508` at `92d08342`; `externals/work/crm-w2-d3-dev` at `74fc6619`. Both were clean at the end (`git status --short` empty) |
| dependencies | each worktree has **its own** `npm ci --ignore-scripts`: `d3` 5.16.0 on 15.0.8 and 7.9.0 on dev. `nsctl.sh` was not used because it links every state to one shared `node_modules`, so both states would resolve the same `d3` |
| server runtime | Node 22.22.0 via `n exec` (`engines` `>=20.x`; CI matrix 20/22/24 on both trees) |
| probe runtime | Node 24.15.0; playwright-core 1.63.0 driving system Google Chrome 149.0.7827.102 (no browser download) |
| database | `mongo:7` container `ns-w2-mongo` on 127.0.0.1:27082, one database per state, removed at the end |
| server mode | `NODE_ENV=development`, so each server compiles its own worktree's client and does not serve a production bundle from `node_modules` |
| browser | viewport 1400×900 (Task A) and 1280×800 (Task B), `timezoneId: UTC`, server `TZ=UTC`, `DISPLAY_UNITS=mg/dl`, default 3 h focus |
| data | synthetic only. Every identifier is a literal in the probe source. Nothing was read from `externals/ns-data` |

**Provenance.** This is the pre-gate built into the drag probe. Each server's `/devbundle/js/bundle.app.js` was fetched and checked for two tokens that exist only in dev's source for the D3-touched files: `d3.pointer(event.touches` (`lib/client/chart.js`) and `profileRedirectRequested` (`lib/client/renderer.js`).

| state | bundle bytes | md5 (12) | `d3.pointer(event.touches` | `profileRedirectRequested` |
|---|---|---|---|---|
| 15.0.8 | 10,246,799 | `ea45bb20dec8` | 0 | 0 |
| dev | 10,933,669 | `1ac471657512` | 1 | 3 |
| dev with clamps deleted (§3.4) | 10,933,319 | `e86e19681c0e` | 1 | 3 |

## 2. What the drag does (read from source, then measured)

`48075a18` rewrites the drag handlers from `d3.event.x` to the D3 6+ `event.x` argument. It leaves the clamps in place. On dev they are at `lib/client/renderer.js:766` (drag start) and `:772-773` (drag). On 15.0.8 they are at `:764` and `:770-771`. BF-54 cites `:764` / `:770-771` "on `origin/dev`". Those are the 15.0.8 line numbers; dev is two lines later because the same commit added `profileRedirectRequested` above them.

- `x` is clamped to `0 … chart width`. On both builds the chart width is also the focus x-scale's range, so a clamped `x` maps to a time within the chart's visible window.
- On release, a **Move** asks `Change treatment time to <time> ?`. If confirmed, the page writes `created_at` = the new time as an ISO string, with milliseconds, over its authenticated live connection.
- Drop zones are tested **after** clamping: **Remove** is `x` 0–50 px across the full focus height. For a treatment carrying both carbs and insulin, **Move carbs** is the top 50 px and **Move insulin** the bottom 50 px. So `x` clamped to 0 always lands in Remove.
- Drag is enabled only in edit mode. The edit button shows only when `EDIT_MODE` is on (the default) and the viewer may update treatments.

## 3. Task A: dragging a treatment (RT-D3)

### 3.1 Method

The probe is `tools/review/probes/rt-d3-drag-browser.js`, one instance per run.

1. It seeds a profile, 72 five-minute glucose readings (110–120 mg/dL) and five treatments through the real REST API, then reads them back **from MongoDB**.
2. It creates role `w2-treatment-editor` (`*:*:read`, `api:treatments:*`) and a subject with that role. The page is opened with that subject's token on an `AUTH_DEFAULT_ROLES=denied` instance, and edit mode is switched on with the page's own button.
3. For each scenario it finds the treatment's glyph by its x-scale position. It then presses the mouse at the glyph's screen origin, confirms that `elementFromPoint` is on that glyph, moves in 12 steps, and releases. It answers the page's `confirm()` and polls MongoDB for the stored `created_at`.
4. **Expected value.** The probe computes this itself from the focus x-scale's domain and range, read immediately before release. It does not use the handler's result: `x0 = xScale(t0)`, `x = clamp(x0 + Δpx, 0, width)`, `expected = invert(x)`, done as explicit linear arithmetic. Tolerance is 2 px of time (about 20.6 s at the measured 10.29 s/px), because the pointer lands on whole pixels and the glyph origin does not.

Axis at release, both builds: chart width 1396 px, focus domain 4 h (from about 3 h before now to about 1 h after), 10,267 to 10,310 ms per px.

### 3.2 Results

All times are UTC on 2026-09-22/23. "Shift" is (stored − seeded) in pixels.

| scenario | build | pointer Δ | seeded | stored | expected | stored − expected | shift | clamp | prompt | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| carbs + insulin, move left, accept | 15.0.8 | −80 px | 23:50:00.000 | 23:36:11.607 | 23:36:16.598 | −5.0 s | −80.5 px | no | Move | **MATCH** |
| | dev | −80 px | 23:51:00.000 | 23:37:06.254 | 23:37:15.201 | −8.9 s | −80.9 px | no | Move | **MATCH** |
| carbs only, move right, accept | 15.0.8 | +45 px | 00:35:00.000 | 00:42:36.700 | 00:42:42.997 | −6.3 s | +44.4 px | no | Move | **MATCH** |
| | dev | +45 px | 00:36:00.000 | 00:43:38.104 | 00:43:43.782 | −5.7 s | +44.4 px | no | Move | **MATCH** |
| carbs + insulin, move left, **cancel** | 15.0.8 | −60 px | 23:20:00.000 | 23:20:00.000 | (unchanged) | n/a | 0 | no | Move | **UNCHANGED** |
| | dev | −60 px | 23:21:00.000 | 23:21:00.000 | (unchanged) | n/a | 0 | no | Move | **UNCHANGED** |
| carbs only, drag 120 px past right edge, accept | 15.0.8 | +529 px | 01:00:00.000 | 02:10:04.000 | 02:10:04.000 | 0.0 s | +408.7 px | **yes** | Move | **MATCH** |
| | dev | +528 px | 01:01:00.000 | 02:11:04.000 | 02:11:04.000 | 0.0 s | +408.0 px | **yes** | Move | **MATCH** |
| insulin only, drag 120 px past left edge, **cancel** | 15.0.8 | −845 px | 00:15:00.000 | 00:15:00.000 | (unchanged) | n/a | 0 | **yes** | **Remove** | **UNCHANGED** |
| | dev | −846 px | 00:16:00.000 | 00:16:00.000 | (unchanged) | n/a | 0 | **yes** | **Remove** | **UNCHANGED** |

All five scenarios agree between the builds on verdict, prompt and changed flag. `--compare` reports 6 checked and 0 failing, the sixth check being equal page-error counts. A first complete pass on each build, run before the prompt assertion was added, gave the same verdicts on every row.

The stored value's type is `string` on both builds (ISO 8601 with milliseconds). The time in the confirmation prompt matched the stored time to the second.

### 3.3 Findings

1. **15.0.8 and dev behave the same** on every drag measured. The D3 7 `event.x` produces the same local coordinate D3 5's `d3.event.x` did. Accepted in-window drags store the axis-predicted time to within 1 px on both builds.
2. **The right clamp bounds a Move to the chart window's right edge, and that edge is in the future.** On both builds the clamped drag stored a `created_at` **59.2 min (15.0.8) and 59.7 min (dev) after the time of the drag**. The clamp stops a time from being written outside the visible window. It does not stop a future time. This is behaviour shared by both builds, not something the D3 change introduced. It is recorded here because BF-54's framing ("clamps bound a user-initiated rewrite") is accurate but does not say where the bound is.
3. **The left clamp never produces a far-past Move.** A drag past the left edge is clamped to `x = 0`, which falls in the Remove zone, so the page asks `Remove treatment ?`. Dismissing it left the treatment unchanged. In practice the earliest time a Move can target is about 50 px, roughly 8.6 min, after the window's left edge.
4. **No page errors** on the main page on either build, including through five drags, two dismissed prompts and the redraw after each update.
5. **Harness observation.** A token-authenticated main page navigates its main frame twice (the client reloads itself once) on both builds. A probe that starts on the first chart it sees can find it torn down mid-run. The probe waits out the reload.

### 3.4 Controls

| control | what it shows | 15.0.8 | dev |
|---|---|---|---|
| cancelled drag must leave `created_at` unchanged | the probe can tell an un-written drag from a written one | UNCHANGED (would have been 617 s away if written) | UNCHANGED (618 s) |
| stored value vs a deliberately wrong expectation (+10 min) | the comparison can report a mismatch | **MISMATCH** | **MISMATCH** |
| provenance tokens | each server serves its own worktree's client | 0 / 0 | 1 / 3 |
| **clamp ablation** (BF-54's deletion, done in the browser on dev): the three clamp expressions replaced with raw `event.x` / `event.y`, grep count 3 → 0, server restarted, same probe | the clamp arms can fail, and fail with the symptom BF-54 describes | n/a | **2 of 19 arms red** (below); worktree restored, `git status` clean |

With the clamps deleted on dev:

| scenario | stored | expected (clamped) | result |
|---|---|---|---|
| drag past right edge, accept | 02:31:37.641, **79.6 min after now**, 20.6 min past the window edge | 02:11:04.000 | **MISMATCH** (+1233.6 s) |
| drag past left edge | prompt became `Change treatment time to 9:51:28 PM ?`, a **Move** to about 20 min before the window's left edge, instead of Remove | Remove | **operation wrong** (dismissed, so nothing stored) |
| the other three scenarios | unchanged from §3.2 | | MATCH / UNCHANGED |

So the browser probe detects both clamps being deleted. BF-54 measured that `tests/dependency-d3.test.js` does not (24/24 with the clamps deleted).

### 3.5 Day-to-day report

The report page was opened with the same token. The probe selected the day-to-day tab, pressed Show, and hovered the first glucose circle.

| build | day charts | svg | circles | page errors |
|---|---|---|---|---|
| 15.0.8 | 7 | 7 | 86 | 0 |
| dev | 7 | 7 | 86 | 0 |

The `daytoday.js` lines `48075a18` changed are inside a `mouseover` handler whose tooltip renders only when the OpenAPS option is on and the point carries OpenAPS data. The seed has none. The handler ran on hover without error, but **the tooltip branch itself was not exercised**.

### 3.6 Not covered

- Touch input. `chart.js`'s brush now reads `event.touches`, and nothing here drives touch.
- The split operations (Move carbs, Move insulin, Remove carbs, Remove insulin) and an accepted Remove.
- Browsers other than Chrome, other viewport sizes, focus ranges other than 3 h, mmol/L display.
- BF-57 (`lib/plugins/cob.js`, `34e9b2da`). It is not part of `48075a18`, and nothing here measures COB.

## 4. Task B: alarm delivery on dev with `AUTH_DEFAULT_ROLES=denied`

### 4.1 What is being checked

PR #8745 (register BF-75) changed which pages receive alarm messages. In the decided shape, a page is admitted to alarm delivery when it connects **only if** the deployment's anonymous default role already permits reading. Otherwise it is admitted when it offers credentials that permit reading. The question is whether a legitimate person on a `denied` instance still gets alarms through the normal page flow. Per the brief this was measured on dev only. Nothing here describes how to reach the alarm channel other than through the unmodified page.

### 4.2 Method

The probe is `tools/review/probes/alarm-denied-browser.js`.

- **Server.** `ALARM_TYPES=simple`, `BG_LOW=55`, urgent-low on (the default). It confirms from `/api/v1/status.json` (read with the API secret) that `alarmTypes=simple`, `alarmUrgentLow=true`, `bgLow=55`.
- **Seed.** A profile and 36 in-range readings (105 mg/dL), verified in MongoDB.
- **Pages.** In `denied` mode, four pages are open **at the same time**, so one trigger serves every arm:

| page | how it authenticates | expected |
|---|---|---|
| `promptSecret` | none in the URL; the API secret is typed into the page's own prompt | receive |
| `readableToken` | `?token=` for a subject with the built-in `readable` role | receive |
| `statusOnly` | `?token=` for a subject whose only permission is `api:status:read`. The page loads and its live connections open, but it may not read data | not receive |
| `anonymous` | none; the prompt is left unanswered | not receive |

In `readable` mode a single anonymous page is expected to receive.

- **Trigger.** Two ordinary REST uploads of a low reading (45, then 44 mg/dL). Both are verified in MongoDB.
- **Recording.** The probe sends nothing over any socket. A catch-all listener on the page's own alarm connection object runs before the page's handlers. The probe also records whether the page enters alarm state (`#container` gains `alarming urgent`).
- **Liveness, same window.** (a) the server log's count of urgent-alarm emissions must increase; (b) the `statusOnly` page's own live connection must receive the viewer-count broadcast, which every connected page gets whatever its permissions.

### 4.3 Results (dev `74fc6619`)

| mode | page | alarms received (of 2 emitted) | page in alarm state | alarm conn. | main conn. | viewer-count broadcasts | status HTTP seen by page | page errors | verdict |
|---|---|---|---|---|---|---|---|---|---|
| `denied` | promptSecret | **2** | yes | up | up | 3 | 401, 401, 200 | 0 | receives |
| `denied` | readableToken | **2** | yes | up | up | 3 | 200, 200 | 0 | receives |
| `denied` | statusOnly | **0** | no | up | up | **3** | 200, 200 | 0 | does not receive, while live |
| `denied` | anonymous | **0** | no | never opened | never opened | 0 | 401, 401 | 0 | does not receive |
| `readable` | anonymous | **2** | yes | up | up | 3 | 200, 200 | 0 | receives |

In both modes the server log showed 2 urgent-alarm emissions during the window. The alarm title seen by receiving pages was `Urgent LOW`.

### 4.4 Controls: the same probe against two deliberate breaks

In a copy of dev (the worktree, restored afterwards, `git status` clean), the fix's single read-entitlement decision in `lib/api3/alarmSocket.js` (`applyReadEntitlement`, line 45) was forced to a constant. The server was restarted and the probe re-run.

| break | page | expected by the probe | measured | probe verdict |
|---|---|---|---|---|
| **forced to refuse** (`denied`) | promptSecret | receive | 0 | **red** |
| | readableToken | receive | 0 | **red** |
| | statusOnly / anonymous | not receive | 0 / 0 | green |
| **forced to refuse** (`readable`) | anonymous | receive | 0 | **red** |
| **forced to admit** (`denied`) | statusOnly | not receive | **2** | **red** |
| | anonymous | not receive | 0 | green (see below) |
| | promptSecret / readableToken | receive | 2 / 2 | green |

What this shows:

- Every "receives" arm can fail, and fails when delivery is refused.
- The `statusOnly` arm is the one that tests the server's decision: it goes red when the decision is forced open.
- **The `anonymous` arm on `denied` does not test the server's decision.** It stays green even when the decision is forced open. Under `denied` the page's first status request is refused (401), so the client never gets as far as opening either live connection, and nothing can reach it. It is a correct statement about the unmodified page. It is not evidence about the gate.

### 4.5 Findings

1. **On dev with `AUTH_DEFAULT_ROLES=denied`, a legitimate person receives alarms through the normal page flow**, whether they type the API secret at the prompt or open the page with a `readable` token. The page re-requests delivery after in-page authentication (`hashauth.updateSocketAuth` → `subscribeForAlarms`). The prompt flow's status requests went 401, 401, then 200 after the secret was entered.
2. **On dev with `denied`, a page that may not read data does not receive alarms**, while the server is shown alive in the same window.
3. **On dev with the shipped `readable` default, an anonymous page still receives alarms.**
4. **Unexpected: a latent page error in the client's alarm handlers, identical on 15.0.8 and dev.** When a page receives a warning or urgent alarm while it holds no glucose data, the handlers' "disabled locally" branch dereferences `client.latestSGV`. The page then throws `Cannot read properties of undefined (reading 'mgdl')` (`lib/client/index.js:1230` and `:1242` on both trees). It was seen only with the decision forced open, where a page without data-read permission received alarms (2 alarms, 2 page errors). On the unmodified build no measured page reached that state. It also cost the probe a result: in the first version of the probe, the throw stopped a per-event listener registered after the page's handler, so a receipt went unrecorded and a negative arm passed for the wrong reason. The recorder now uses a catch-all listener that runs first, and negative arms also require zero page errors.

### 4.6 Not covered

- 15.0.8 (excluded by the brief; the shipped release is still affected by BF-75).
- `AUTHENTICATION_PROMPT_ON_LOAD=true`, token entry at the prompt (as opposed to `?token=`), a remembered secret across reloads, and acknowledging or silencing an alarm (BF-76).
- Warning-level alarms, announcements and clear messages. Only urgent-low was triggered, although the recorder logs all five kinds.

## 5. Reproduce

These are the commands used, from the alignment repository root. The helper keeps logs and the generated API secret under `$W2_STATE`. The secret is never printed.

```bash
export W2_STATE=/path/to/scratch/w2-state            # logs + generated secret (mode 600)
export NSREVIEW_DEPS=/path/to/dir/node_modules       # holds playwright-core@1 and mongodb@6
H=tools/review/probes/w2-instance.sh
SEC="$(cat "$W2_STATE/secret")"                       # created by the helper's first run

git -C externals/cgm-remote-monitor-official fetch origin
git -C externals/cgm-remote-monitor-official worktree add ../work/crm-w2-d3-dev  74fc6619 --detach
git -C externals/cgm-remote-monitor-official worktree add ../work/crm-w2-d3-1508 92d08342 --detach
$H prep "$PWD/externals/work/crm-w2-d3-dev"; $H prep "$PWD/externals/work/crm-w2-d3-1508"
docker run -d --name ns-w2-mongo --ulimit nofile=64000:64000 -p 27082:27017 mongo:7

# Task A, each state on a fresh database
$H reset d3-1508 "$PWD/externals/work/crm-w2-d3-1508" 14901 w2_d3_1508 denied
n exec 24.15.0 node tools/review/probes/rt-d3-drag-browser.js --url http://127.0.0.1:14901 \
  --secret "$SEC" --mongo mongodb://127.0.0.1:27082 --db w2_d3_1508 --label 15.0.8 --expect-d3 5 --out a.json
$H reset d3-dev "$PWD/externals/work/crm-w2-d3-dev" 14902 w2_d3_dev denied
n exec 24.15.0 node tools/review/probes/rt-d3-drag-browser.js --url http://127.0.0.1:14902 \
  --secret "$SEC" --mongo mongodb://127.0.0.1:27082 --db w2_d3_dev --label dev --expect-d3 7 --out b.json
n exec 24.15.0 node tools/review/probes/rt-d3-drag-browser.js --compare a.json b.json

# Task B, dev only
$H reset alarm-denied "$PWD/externals/work/crm-w2-d3-dev" 14903 w2_alarm_denied denied ALARM_TYPES=simple BG_LOW=55
n exec 24.15.0 node tools/review/probes/alarm-denied-browser.js --url http://127.0.0.1:14903 --secret "$SEC" \
  --mongo mongodb://127.0.0.1:27082 --db w2_alarm_denied --mode denied --server-log "$W2_STATE/alarm-denied.log"
$H reset alarm-readable "$PWD/externals/work/crm-w2-d3-dev" 14904 w2_alarm_readable readable ALARM_TYPES=simple BG_LOW=55
n exec 24.15.0 node tools/review/probes/alarm-denied-browser.js --url http://127.0.0.1:14904 --secret "$SEC" \
  --mongo mongodb://127.0.0.1:27082 --db w2_alarm_readable --mode readable --server-log "$W2_STATE/alarm-readable.log"

# teardown
for n in d3-1508 d3-dev alarm-denied alarm-readable; do $H stop $n; done
docker rm -f ns-w2-mongo
```

The two break controls (§3.4, §4.4) are single-expression edits in the dev worktree, followed by `reset` and a re-run of the same probe, then `git checkout --` of the edited file. The drag probe refuses to run against a database that already holds treatments, and the alarm probe refuses one that already holds entries. `reset` stops the server before dropping, because a database dropped under a live server leaves its cache populated.

## 6. For the reviewers

| sign-off | the evidence above supports | the reviewer should still decide or verify |
|---|---|---|
| RT-D3 | drag-to-move behaves the same on 15.0.8 and dev in Chrome with a mouse; the clamps engage and are now covered by a browser check that fails when they are deleted | whether a Move up to about 1 h into the future (the window's right edge) is acceptable behaviour, and whether touch and the split operations need their own check before release |
| alarm delivery (#8745) | a legitimate viewer on `denied` receives alarms via prompt or readable token; a non-entitled viewer does not while the server is alive; the `readable` default is unchanged for anonymous viewers | whether the latent client page error in §4.5 item 4 needs a register entry |
