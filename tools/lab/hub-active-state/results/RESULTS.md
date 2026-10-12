# hub-active-state — results, 2026-10-12

*Contributor-facing. Snapshot of one run; rerun before quoting.* Both hubs were run over the same
synthetic records (`records/cases.json`, T0 = 2026-01-15T00:00:00Z, all times UTC). The table
records what each hub's own code reports as active at each query time. Lab description and
method: [../README.md](../README.md).

## What was run

| | cgm-remote-monitor | Nocturne |
|---|---|---|
| Commit | `fade229909e6f3a0b5459230bc7273fe85de4f32` (`official/dev`, package version 15.0.9) | `42275c812d9b942251a3309fea8066871940cfc2` |
| Source | GitHub archive of the commit (`fetch-trees.sh`); `node_modules` from a local checkout of the same commit (identical `package-lock.json`, and `lib/` identical to the archive) | GitHub archive of the commit (`fetch-trees.sh`); `src/` identical to `externals/nocturne` at the same commit |
| Runtime | Node.js v24.15.0 | .NET SDK 10.0.112; Microsoft.EntityFrameworkCore.Sqlite 10.0.8, in-memory SQLite |
| Code executed | `lib/data/ddata.js`, `lib/profilefunctions.js`, `lib/plugins/loop.js` (with `lib/client-core/devicestatus/loop.js`), `lib/plugins/override.js` | `TreatmentDecomposer`, `DeviceStatusDecomposer`, `ProfileDecomposer`, `StateSpanService`, `StateSpanRepository`, `DeduplicationService`, `ActiveProfileResolver`, `BasalRateResolver`, the V4 schedule repositories, `PatientRecordRepository` |
| Not executed | the HTTP API and MongoDB storage (the probe applies an upsert by `_id` and the dataloader's sort itself); for overrides from treatments, the client renderer's filter is applied by the probe, not run | the HTTP API, the v1 write path ahead of the decomposers, PostgreSQL (the run uses SQLite, as Nocturne's repository unit tests do) |

Commands (from the repository root):

```sh
tools/lab/hub-active-state/fetch-trees.sh /tmp/hub-trees
tools/lab/hub-active-state/run.sh /tmp/hub-trees/crm-fade2299 /tmp/hub-trees/nocturne-42275c812
```

Two consecutive runs produced byte-identical `compare.md`. The comparator self-test
(`compare.js --selftest`) reported 0 disagreements for identical inputs and 1 for one changed
answer.

## Readings

* **cgm-remote-monitor.** `tt`: the processed temp targets (`ddata.tempTargetTreatments`) whose
  window contains t. `override_tx`: `Temporary Override` treatments whose drawn window contains t
  (the renderer's input; indefinite = open-ended). `override_ds`: `loop.analyzeData` → `lastOverride`
  → `override.isActive`. `profile`: `activeProfileToTime` and `getBasal`.
* **Nocturne.** *GetActiveAt*: `StateSpanRepository.GetActiveAtAsync(category, state: null, t)`
  — the call `SensorContextEnricher` makes for overrides; the latest-starting span containing t,
  in any state. A `Cancelled` temp-target span is read as none. *List read*:
  `GetStateSpansAsync(category, from: t, to: t)` filtered to spans containing t; this path applies
  the deduplication visibility filter. `profile`: `ActiveProfileResolver.GetActiveProfileNameAsync`
  (no span → `BasalRateResolver` uses `Default`) and `BasalRateResolver.GetBasalRateAsync`.

The profile document used by every case: `Default` basal 1.00 at 00:00 rising 0.05 each hour
(02:00 1.10, 03:00 1.15, 05:00 1.25, 07:00 1.35, 08:00 1.40, 10:00 1.50); `Weekend` 0.80 and
`Exercise` 0.50 all day.

## Cases

| case | t | ask | cgm-remote-monitor | Nocturne GetActiveAt | Nocturne list read | agree (GetActiveAt / list) | note |
|---|---|---|---|---|---|---|---|
| c1-tt-cancel | T0+10 | tt | `c1-tt` | `c1-tt` | `c1-tt` | yes / yes |  |
| c1-tt-cancel | T0+30 | tt | `none` | `none` | `c1-cancel+c1-tt` | yes / **no** | GetActiveAt(state "Active") = `c1-tt` |
| c1-tt-cancel | T0+70 | tt | `none` | `none` | `c1-cancel` | yes / **no** |  |
| c2-ov-cancel | T0+10 | override_tx | `c2-ov` | `c2-ov` | `c2-ov` | yes / yes |  |
| c2-ov-cancel | T0+30 | override_tx | `c2-ov` | `c2-ov` | `c2-ov` | yes / yes |  |
| c2-ov-cancel | T0+70 | override_tx | `none` | `none` | `none` | yes / yes |  |
| c3-loop-ds-override | T0+12 | override_ds | `active` | `active` | — | yes |  |
| c3-loop-ds-override | T0+40 | override_ds | `none` | `active` | — | **no** |  |
| c3-loop-ds-override | T0+120 | override_ds | `none` | `active` | — | **no** |  |
| c4-ps-timed-after-permanent | T0+30 | profile | `Weekend basal=0.800` | `Weekend basal=0.800` | — | yes |  |
| c4-ps-timed-after-permanent | T0+90 | profile | `Exercise basal=0.500` | `Exercise basal=0.500` | — | yes |  |
| c4-ps-timed-after-permanent | T0+150 | profile | `Weekend basal=0.800` | `Default basal=1.100` | — | **no** | Nocturne: no profile span at t |
| c5-aaps-timeshift-ms | T0+300 | profile | `Default basal=1.150` | `Default basal=1.250` | — | **no** |  |
| c5-aaps-timeshift-ms | T0+600 | profile | `Default basal=1.400` | `Default basal=1.500` | — | **no** |  |
| c6-tt-same-ms | T0+10 | tt | `c6-tt-a` | `c6-tt-a` | `c6-tt-a` | yes / yes | list read with dedup mocked = `c6-tt-a+c6-tt-b` |
| c6-tt-same-ms | T0+45 | tt | `c6-tt-a` | `c6-tt-a` | `c6-tt-a` | yes / yes |  |
| c7-ov-backfill | T0+30 | override_tx | `c7-ov-earlier` | `c7-ov-earlier` | `c7-ov-earlier` | yes / yes |  |
| c7-ov-backfill | T0+90 | override_tx | `c7-ov-earlier+c7-ov-later` | `c7-ov-later` | `c7-ov-earlier+c7-ov-later` | **no** / yes |  |

What each hub stored or derived (from `results/crm.json` and `results/nocturne.json`):

| case | cgm-remote-monitor | Nocturne |
|---|---|---|
| c1 (60-min TT at +0, cancel at +20 with `duration: 0`) | the cancel truncates the target: one processed target, +0 to +20 | two spans: `c1-tt` Active +0 to +60 (not shortened) and `c1-cancel` **Cancelled**, +20, no end |
| c2 (60-min override, stored `Temporary Override Cancel` at +20) | the cancel has no duration and is not drawn; the override keeps its 60 min | the cancel produces no record (decomposition returned 0 created); one Override span +0 to +60 |
| c3 (Loop devicestatus every 5 min, `override.duration` = seconds remaining, 1800 at +0; `active: false` at +30, +35) | the latest devicestatus override is read; end = `override.timestamp` + `duration` **seconds** → ended at +30; at +40 the latest is `active: false` | one span per devicestatus with an active override, start = devicestatus time, end = start + `duration` **minutes** (+0 → +1800 min, …, +25 → +325 min); timed spans are not superseded; `active: false` creates nothing and closes nothing |
| c4 (permanent Weekend at +0, timed Exercise +60 for 60 min) | Weekend again after +120 | the Exercise span closes the open Weekend span at +60 (superseded); after +120 no span covers t |
| c5 (AAPS 3.x switch, percentage 100, `timeshift: 7200000`) | `aapsSwitchAdjustment` → 2 h; 05:00 reads the 03:00 rate, 10:00 reads 08:00 | `CircadianAdjustment` timeshift **0 ms**: the value is read as hours modulo 24, and 7,200,000 mod 24 = 0 (any whole number of hours in ms is a multiple of 24) |
| c6 (two TTs, same `created_at`, 60 min arrives first, 30 min second) | the second is dropped (`processDurations` keeps the first per mills); the stable sort keeps arrival order | both stored as spans, neither superseded (both timed); `DeduplicationService` puts them in one canonical group with the **second arrival non-primary**, so the list read shows only the first |
| c7 (indefinite overrides; the +60 one arrives before the +0 one) | both drawn open-ended; no truncation for overrides in either arrival order | two open spans: supersession only closes spans that start at or before the new one, so the backfilled +0 span stays open and the +60 span is not closed by it |

## Controls

Each control is a record set where the two hubs were expected to agree. All 20 control rows
agree on every reading.

| case | t | ask | cgm-remote-monitor | Nocturne GetActiveAt | Nocturne list read | agree |
|---|---|---|---|---|---|---|
| c1-ctl (60-min TT, no cancel) | T0+10 / +30 / +70 | tt | `c1-tt` / `c1-tt` / `none` | same | same | yes ×3 |
| c2-ctl (override ended Loop's way: same `_id` re-uploaded with `duration: 20`) | T0+10 / +30 / +70 | override_tx | `c2-ov` / `none` / `none` | same | same | yes ×3 |
| c3-ctl (devicestatus, indefinite override, +0..+25) | T0+12 / +27 / +120 | override_ds | `active` ×3 | `active` ×3 | — | yes ×3 |
| c4-ctl (permanent Weekend only) | T0+30 / +90 / +150 | profile | `Weekend basal=0.800` ×3 | same | — | yes ×3 |
| c5-ctl (AAPS switch, timeshift 0) | T0+300 / +600 | profile | `Default basal=1.250` / `1.500` | same | — | yes ×2 |
| c6-ctl (two TTs at +0 and +90, not overlapping) | T0+10 / +45 / +100 | tt | `c6-tt-a` / `c6-tt-a` / `c6-tt-b` | same | same | yes ×3 |
| c7-ctl (two 30-min overrides at +0 and +60, out of order) | T0+15 / +45 / +75 | override_tx | `c7-ov-earlier` / `none` / `c7-ov-later` | same | same | yes ×3 |

The controls isolate the input each case varies: the cancel record (c1), the cancel encoding
(c2), the duration field (c3), the timed switch's expiry (c4), a non-zero timeshift (c5), the
shared millisecond (c6) and open-endedness (c7). With that input removed the hubs agree, so the
case disagreements come from that input and not from the harness.

## Non-vacuity: one input changed

| perturbation | changed | effect |
|---|---|---|
| c1-perturb | cancel at +40 instead of +20 | both hubs: T0+30 `none` → `c1-tt` |
| c2-perturb | override 25 min instead of 60 | both hubs: T0+30 `c2-ov` → `none` |
| c3-perturb | override 60 min (3600 s remaining at +0), no `active: false` rows | cgm-remote-monitor: T0+40 `none` → `active`; Nocturne unchanged (`active`) |
| c3-perturb-short | one devicestatus, `duration: 60` | Nocturne: T0+120 `active` → `none` (span ends at +60); cgm-remote-monitor `none` at all three times (ends at +1 min) |
| c4-perturb | timed switch 120 min | both hubs: T0+150 → `Exercise basal=0.500` |
| c5-perturb | percentage 200, timeshift 0 | both hubs: basal ×2 (`2.500`, `3.000`) |
| c5-perturb-hours | timeshift `2` (hours, the AAPS 2.x unit) | Nocturne: 05:00 reads the 07:00 rate (`1.350`), 10:00 reads 12:00 (`1.600`), so its timeshift path adds the shift; cgm-remote-monitor unchanged (`1.250`, `1.500`): `Math.trunc(2 / 3600000)` = 0 h |
| c6-perturb | arrival order swapped (30 min first) | cgm-remote-monitor keeps `c6-tt-b`: T0+10 `c6-tt-b`, T0+45 `none`. Nocturne list read the same (`c6-tt-b`, `none`); Nocturne GetActiveAt T0+45 = `c6-tt-a` (the non-primary span; `GetActiveAtAsync` does not apply the deduplication filter) |
| c7-perturb | arrival in time order | Nocturne: T0+90 list read `c7-ov-earlier+c7-ov-later` → `c7-ov-later` (the +0 span is superseded at +60); cgm-remote-monitor unchanged |

With `IDeduplicationService` mocked (`results/nocturne-mockdedup.json`) the only rows that change
are the c6 list reads: both same-millisecond spans become visible.

## Landscape §5: claims checked

| §5 row | Claim (Nocturne side read-derived at `42275c812`) | Lab result |
|---|---|---|
| Temp target + later cancel | cancel becomes a separate open span with state `Cancelled`; a timed target is not shortened | **confirmed** (c1). Agreement depends on the read: the latest-span read (`GetActiveAtAsync`, any state) returns the Cancelled span and so agrees with cgm-remote-monitor; the Active-state read and the list read still return the 60-min target until +60, and the open Cancelled span stays in list reads after +60 |
| `Temporary Override Cancel` | not classified; produces no span | **confirmed** (c2): 0 records created. cgm-remote-monitor also ignores a stored cancel, so the two hubs **agree** (the override runs its full duration in both). Whether careportal stores the cancel was not tested here |
| Loop devicestatus override | cgm-remote-monitor reads `duration` as seconds; Nocturne as minutes, span starting at devicestatus time | **confirmed** (c3, c3-perturb-short). Also measured: each devicestatus adds a timed span, and an `active: false` devicestatus does not end them |
| Timed profile switch after a permanent one | cgm-remote-monitor falls back to the permanent profile; Nocturne has no span after the timed one expires | **confirmed** (c4); Nocturne's `BasalRateResolver` then uses profile `Default` |
| AAPS `timeshift` | cgm-remote-monitor: milliseconds; Nocturne: hours modulo 24 | **confirmed** (c5): a millisecond timeshift becomes 0 in Nocturne. Also measured: Nocturne adds the shift (reads t + shift), cgm-remote-monitor's AAPS 3.x path subtracts it (reads t − shift) |
| Same-millisecond temp targets | cgm-remote-monitor keeps the first; Nocturne upserts both | **partly contradicted** (c6): Nocturne stores both, but `DeduplicationService` marks the second arrival non-primary, so list reads show only the first, as cgm-remote-monitor does. `GetActiveAtAsync` reads both (it does not apply the deduplication filter) |
| §12: out-of-order backfill of two overrides (was not measured) | backfill leaves two open spans | **confirmed** (c7): two open Override spans; `GetActiveAtAsync` returns the later-starting one, the list read returns both. cgm-remote-monitor shows both in either order; Nocturne shows one when the records arrive in time order |

## Not run

* Either hub's HTTP API. Upsert, `_id` handling and same-time deduplication ahead of
  `ddata.js` (cgm-remote-monitor) or ahead of the decomposers (Nocturne) were not exercised.
* Nocturne on PostgreSQL. The tie between two spans with the same start (c6) was broken by
  insertion order on SQLite; PostgreSQL does not guarantee that order.
* cgm-remote-monitor's client renderer; the override-from-treatments answer applies its filter in
  the probe.
* Nocturne's chart and v1 projections of these spans.
