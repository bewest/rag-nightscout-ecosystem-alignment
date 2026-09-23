# BF-09 — what socket dedup does with a zero, and whether treating zero as real would bring back the AAPS temp-basal display problem

> **Snapshot — measured 2026-09-23 against `origin/dev` `74fc6619` and tag `15.0.8` (`92d08342`, identical output), Node 20.20.0, MongoDB 7. Status: measurement only, for the maintainer's decision. No fix branch. Contributor-facing. Current facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md).**

## 1. The code

`lib/server/websocket.js` `processSingleDbAdd`, treatments branch:

1. **Exact match.** With `NSCLIENT_ID`: on `NSCLIENT_ID`. Without: on `created_at` + `eventType`.
   A zero plays no part here.
2. **Similar match.** `created_at` within **±2 s** (`maxtimediff`), plus each of `insulin`, `carbs`,
   `percent`, `absolute`, `duration` and `NSCLIENT_ID` **that is truthy**. `eventType` is added
   **only if none of them was**. On a match the incoming record is **dropped**, and the stored one
   has its `created_at` moved to the incoming one's.

So `0`, `''`, `false` and `null` are all left out of the key in the same way. Leaving a field out
does not just lose it as a key: the lookup can end up keyed on a field that a record of another
kind also has (usually `duration`).

**Who reaches this path.** AAPS NSClient v1 sends temp basals over `dbAdd` with **no
`NSCLIENT_ID`**. `externals/AndroidAPS` `plugins/sync/.../nsclient/extensions/TemporaryBasalExtension.kt`
sends `eventType: 'Temp Basal'`, `duration` in whole minutes, `durationInMilliseconds`, and either
`absolute` or `percent: rate - 100`. Also on this path: xDrip's `NSClientChat` and the Nightscout
chart's own drag-to-edit (`lib/client/renderer.js:893`, `:920`). REST and API v3 do not use this
dedup.

## 2. What `bec641ca` changed, and what replaced it

`bec641ca` ("Increase rendering granularity to support AAPS TBRs", Milos Kozak, 2024-08-07, in
15.0.8 through #8281) is a **rendering** change. It does not touch dedup:

- `lib/client/renderer.js`: the basal line was sampled every **1 minute**; it became every **1 second**.
- `lib/report_plugins/daytoday.js`: sampled every **5 minutes**, then every **1 second**, with the
  per-step insulin fractions to match.

**Why.** AAPS temp basals can start and end between samples, since they are timed to the
millisecond. A fixed step either misses a short temp or draws it at the wrong time.

**It has since been replaced.** `846bb690` ("Optimize basal render sampling", Andy Low,
2026-05-09, also in 15.0.8) went back to a 1-minute step and **added every temp's start and end
as a sample point** (`profilefunctions.getBasalRenderTimes`). So what fixes the AAPS display today
is "sample at every boundary", not "sample every second". It draws every stored temp exactly,
however short it is.

## 3. Measurement

`tools/remedial/bf3/bf09-dedup-zero.js <tree>` (rerun command in §6):

- **Two arms, each a separate process with its own require cache, booting the tree's real server
  and socket.** `shipped` is the tree as it is. `zero-real` is a scratch copy of the tree's `lib/`
  where each numeric key test `if (data.data.X)` becomes `if (data.data.X || data.data.X === 0)`,
  for `insulin`, `carbs`, `percent`, `absolute` and `duration`. That is the smallest change that
  makes 0 a key and leaves `''`, `false`, `null` and absent unchanged. The harness refuses to run
  unless it finds exactly one of each test.
- **Every case is sent over an authorized socket as `dbAdd`, one record at a time**, then the
  treatments collection is read back.
- **Rendering.** The stored records, and separately every record that was **sent** (the
  reference), go through the tree's own `ddata.processTreatments` →
  `profilefunctions.updateTreatments` → `getBasalRenderTimes` / `getTempBasal`, the path
  `renderer.js` takes, on a 1.0 U/h profile over 75 minutes. The table counts the seconds where
  the exact value (`exactΔs`) and the drawn step line (`drawnΔs`) differ from the reference. The
  "U" columns are the area under the drawn basal line over the window. They describe the chart,
  not insulin delivered, and are not a dosing figure.

### 3.1 Results (dev `74fc6619`; 15.0.8 gave the same numbers)

| case | what was sent (≤2 s apart unless stated) | shipped: stored / drawn wrong | zero-real: stored / drawn wrong |
|---|---|---|---|
| Z1 | zero temp, re-sent 1 s later (same content) | 1 of 2 / 1 s | 1 of 2 / 1 s |
| **Z2** | 1.2 U/h temp, then **zero temp**, same duration | **1 of 2 — zero temp dropped / 1801 s** | 2 of 2 / 0 s |
| Z3 | zero temp, then 1.2 U/h temp, same duration | 2 of 2 / 0 s | 2 of 2 / 0 s |
| Z4 | zero temp, then zero temp of another duration | 2 of 2 / 0 s | 2 of 2 / 0 s |
| **Z5** | zero temp, then a **cancel** (`duration: 0`, no rate) | **1 of 2 — cancel dropped / 1801 s** | 2 of 2 / 0 s |
| Z6 | sub-minute zero temp (`duration: 0`, `durationInMilliseconds: 40000`), then 1.2 U/h | 2 of 2 / 0 s | 2 of 2 / 0 s |
| X1 | zero temp, then **Temporary Target**, same duration | **1 of 2 — target dropped** / 2 s | **1 of 2 — target dropped** / 2 s |
| **X2** | Temporary Target, then **zero temp**, same duration | **1 of 2 — zero temp dropped / 1801 s** | 2 of 2 / 0 s |
| P1 | control: percent-mode zero temp (`percent: -100`), then 1.2 U/h | 2 of 2 / 0 s | 2 of 2 / 0 s |
| **P2** | 150 % temp (`percent: 50`), then **100 % temp (`percent: 0`)** | **1 of 2 — dropped / 1801 s** | 2 of 2 / 0 s |
| N1 | control: two zero temps with different `NSCLIENT_ID`s | 2 of 2 / 0 s | 2 of 2 / 0 s |
| W1 | control: 1.2 U/h, then zero temp **3 s** later | 2 of 2 / 0 s | 2 of 2 / 0 s |
| F1–F3 | `absolute: ''` / `false` / `null`, then 1.2 U/h | 2 of 2 / 0 s | 2 of 2 / 0 s |
| B1, C1 | `insulin: 0` then 1 U; `carbs: 0` then 20 g | 2 of 2 | 2 of 2 |
| **B2, C2** | 1 U then **`insulin: 0`**; 20 g then **`carbs: 0`** | **1 of 2 — zero record dropped** | 2 of 2 |

`drawnΔs` equalled `exactΔs` in every row of both arms. The chart draws what is stored, exactly.

Z2, drawn: the reference shows the pump at 0 U/h for 30 minutes. The shipped arm stored only the
1.2 U/h temp, moved to the zero temp's time, so the chart shows 1.2 U/h for those 30 minutes
(area 1.35 U against 0.75 U over the window). Z5 is the reverse: a cancelled zero temp is drawn as
running for its full 30 minutes. X2 and P2 have the same shape as Z2.

**Non-vacuity.** The arms diverge in 6 cases (Z2, Z5, X2, P2, B2, C2) and agree in every control
(Z1, N1, W1, P1). The patch count is checked (5 of 5).

**For context: the sampler bec641ca replaced.** Rendering every **sent** record with a bare
1-minute step (no boundaries) gets 58–117 s of each temp-basal case wrong (Z2 116 s, X2 117 s,
Z1 58 s). That is the class of error bec641ca addressed. The shipped sampler gets 0 s wrong on
the same records.

### 3.2 A second finding, reproduced while building the harness

`lib/profilefunctions.js:19` keeps `prevBasalTreatment` at **module scope**, and
`tempBasalTreatment()` returns it whenever the time falls inside it. Only `profile.clear()`
resets it. That runs when each instance is created (`:34`), but `updateTreatments()` (`:310`)
does not call it. Reproduced on dev and 15.0.8 with a 1.2 U/h temp later cut by a zero temp: **the
same instance returned 1.2 after `updateTreatments` had replaced its treatments** (expected 0). A
new instance created afterwards returned the right value. The first version of this harness gave
inconsistent reference figures for exactly this reason. The server builds a new instance on every
tick, so it is not affected. The browser keeps one `client.profilefunctions` and calls
`updateTreatments` on each data update (`lib/client/index.js:1366`), so a pill or chart lookup
there could return a replaced temp. **The browser was not measured.** This is not BF-09. It is
worth its own register entry.

## 4. Does treating zero as real bring back the AAPS display problem?

**Not on anything measured here.**

- The display fix is in the renderer (bec641ca, then 846bb690's boundary sampling). The dedup
  change does not touch it. In every case, under both arms, the chart drew the stored records with
  0 s of error beyond what dedup had already removed.
- The rapid zero-temp patterns come out the same under both arms. A re-sent zero temp is still
  merged (Z1). Zero temps of different durations were already both kept (Z4). A sub-minute zero
  temp was already kept (Z6).
- The only cases zero-real changes are the ones where shipped dedup **drops** a zero temp, a
  cancel, a 100 % temp, or a zero-valued bolus or carb record. In the temp-basal ones the shipped
  chart then shows the wrong rate for the whole duration (Z2, Z5, X2, P2). **If the display problem
  the maintainer remembers looked like "the chart shows a temp the pump was not running", Z2 is a
  shipped way to produce it, and zero-real removes it.** This measurement cannot tell which of the
  two problems was the one seen.

## 5. Options for the maintainer (not decided here)

1. **Leave as is.** The measured consequences stay: over the socket without `NSCLIENT_ID`, within
   ±2 s, a zero temp or 100 % temp that follows another temp or a target of the same duration is
   dropped and drawn as the earlier rate (Z2, X2, P2). A cancel that follows a zero temp is dropped
   and the temp is drawn as running (Z5). A zero-valued bolus or carb record is dropped (B2, C2).
2. **Zero is a real value for the numeric keys** (`x || x === 0`, the measured variant). This fixes
   Z2, Z5, X2, P2, B2 and C2, changes no control, and leaves `''`, `false` and `null` as absent.
   **It does not fix X1.** A temp target that follows a zero temp of the same duration is still
   dropped, because the target has no numeric key besides the shared `duration`.
3. **Option 2, plus always keying on `eventType`.** This should also fix X1, but it was **not
   measured**. It would change matching for any client that changes a record's `eventType` between
   resends. None was found, but that was not searched for exhaustively.
4. **Presence (`x != null`).** This would also make `''` and `false` keys. **Not measured**, and
   there is no corpus evidence for those values in these fields in either direction.

## 6. Rerun

```sh
docker run -d --name <name> --ulimit nofile=64000:64000 -p <port>:27017 mongo:7
CUSTOMCONNSTR_mongo=mongodb://127.0.0.1:<port>/<name containing "test"> \
  node tools/remedial/bf3/bf09-dedup-zero.js <cgm-remote-monitor tree with node_modules>
```

It deletes every treatment in the named database between cases, and refuses a database whose name
does not contain `test`. The `zero-real` copy goes under `$TMPDIR` and is removed afterwards.

## 7. What was not measured

- **A live AAPS uploader burst.** The cases are hand-built from the v1 upload shape, not replayed
  from a phone. This is still the arm that would settle how often Z2/Z5/X2 happen in practice.
- **Frequency.** The 2026-09-15 corpus census (277,690 treatments) counts stored data only. A
  record dedup dropped cannot appear in it. `tools/queue/gates/bf09-corpus-divergence.js` is noted
  as undercounting and was not fixed or used here.
- The browser itself. Rendering was driven through the shipped `profilefunctions` and
  `getBasalRenderTimes`, not d3 and not a page. `renderer.js` was read.
- The day-to-day report, IOB, and the pump and basal pills.
- Devicestatus and profile dedup, which key on `NSCLIENT_ID`, `created_at` and `startDate` only.

## Files

- `tools/remedial/bf3/bf09-dedup-zero.js` — the harness (this repo).
- Worktrees (upstream clone): `externals/work/crm-bf3-dedup` (detached at `74fc6619`, unmodified),
  `externals/work/crm-bf3-1508` (detached at `15.0.8`).
