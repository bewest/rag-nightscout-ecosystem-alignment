# Proposal: the concrete changes that make Nightscout high-fidelity for replay

Date: 2026-09-11. Status: draft for maintainer discussion. Eleventh in the
series, and the first one that is a **change list rather than an analysis.**

> **Two things this document refuses to concede.** That sync has to be
> inefficient, and that fidelity has to be traded against it. §1 shows the
> request count should be **O(1) in the number of resources**, which is a
> small change to code that is already generic. Once it is, every typed
> resource that improves replay costs **zero additional requests**, and the
> rest of this document is just a list of what to record.

---

## TL;DR — five changes, measured

| # | Change | Who | Measured effect |
|---|---|---|---|
| **A** | Collection-agnostic delta read + one batch write | cgm-remote-monitor | AAPS **20 → 2** requests/cycle, and **adding N typed collections costs 0** — the count stops mattering |
| **B** | Eight more keys in `loopSettings`, which Loop already writes on 200 of 202 profile documents | Loop | Loop replay **20% → 65%** recorded; **55% → 100%** recorded-or-derivable |
| **C** | Emit the `determine-basal` input vector alongside its output | Trio / AAPS / oref0 | oref0 replay **50% → 78%** recorded; **72% → 100%** recorded-or-derivable |
| **D** | Exempt cursor-paginated reads from the range cap | cgm-remote-monitor | Backfill and catch-up stop being indistinguishable from abuse |
| **E** | Read `openaps.iob.lastTemp` instead of assuming no temp basal | `oref-digital-twin` | One of the two inputs its own docstring calls unrecoverable **is already published, on 73,891 documents** |

**Change B is the headline and it is smaller than anyone has been assuming.**
Every one of Loop's eight absent dosing inputs is *configuration*, and Loop
already publishes a configuration block — `loopSettings`, on **200 of 202
profile documents across 10 sites**, carrying eight keys today. The ask is
eight more keys in a dictionary it already serialises. Not a new resource,
not a new endpoint, not a new API version.

**And a finding that should embarrass the series a little:** the conformance
profile this work published passes on **27 of 28 obligations at every
in-scope site**, while replay completeness is 20%. A profile that passes
everywhere while the thing it exists to protect is broken is not measuring
the right thing. §7.

---

## 1. Sync cost should be O(1) in the number of resources

### 1.1 Why the current cost is structural, not necessary

v3's delta machinery is per collection: `GET /api/v3/{collection}/history/{from}`.
A client that syncs six collections makes six delta calls, plus
`GET /lastModified`, plus a POST per collection it writes. The measured
result is the one that should have been the clue:

> **AAPS — the only client using v3 as designed — has the worst fan-out**,
> 20 distinct endpoints per cycle, an upper bound of 5,760 requests/day.
> Loop and Trio, which ignore v3 entirely, are cheaper by accident.

Cursor-based sync solved *what changed*. It never addressed *how many round
trips*, and the per-collection shape means every resource added to the model
is a new request in the loop. That is the reason a fidelity proposal reads as
a cost proposal. **It does not have to.**

### 1.2 The change, concretely

Two endpoints, both built from code that is already generic.

```
GET  /api/v3/history/{lastModified}?collections=&limit=
     → { srvDate, cursor, complete, collections: { treatments: [...],
         entries: [...], devicestatus: [...], ... } }

POST /api/v3/batch
     → [ { collection, doc }, ... ]   idempotent per document
```

**Why this is a small change and not a rewrite:**

| Piece needed | Already exists | Where |
|---|---|---|
| Iterate every collection with a per-collection permission check | yes — `collectionsAsync` does exactly this loop with `security.checkPermission(auth, 'api:' + col.colName + ':read')` | `lib/api3/specific/lastModified.js` |
| A delta query generic in the collection | yes — `history(opCtx, fieldsProjector)` reads `opCtx.col` and does `srvModified > from`, sorted ascending, with a limit | `lib/api3/generic/history/operation.js` |
| A registry of live collections | yes — `app.set('collections', cols)` | `lib/api3/generic/setup.js` |
| Per-document create with dedup | yes — the `create` operation each collection already mounts | `lib/api3/generic/create/` |

The new endpoint is `lastModified.js`'s loop with `findMany` in place of
`getLastModified`. It is not a new storage layer, a new index, or a new
identity model.

### 1.3 The one detail that must not be got wrong

**A merged cursor is only safe if it is the minimum over truncated
collections.** With a per-collection page limit, `treatments` may return 500
rows ending at `srvModified = T1` while `entries` drains completely to `T2 >
T1`. Advancing the global cursor to `max()` silently skips every treatment
between `T1` and `T2` — a data-loss bug that would look like flaky sync.

The rule:

```
cursor   = min( last srvModified returned, over collections that hit the limit )
           or srvDate, if no collection hit its limit
complete = no collection hit its limit
```

A client loops while `complete` is false. This is the whole of the
correctness argument, and it is worth stating in the endpoint's own
documentation because it is the kind of thing a second implementation gets
wrong.

### 1.4 What it does to the numbers

Same model as `reports/schema-census/sync-cost.json` — a source-derived upper
bound on distinct endpoint calls per 5-minute cycle, not a packet capture.

| | Endpoints/cycle | Requests/day | Cost of adding 10 typed collections |
|---|---|---|---|
| AndroidAPS today (v3, per-collection) | 20 | 5,760 | **+2,880/day** |
| Loop today (v1) | 7 | 2,016 | n/a — no delta at all |
| **With `history/{from}` + `batch`** | **2** | **576** | **0** |

That last column is the point of this section. **Under the current shape,
every typed resource that improves replay makes sync worse. Under this one,
it does not.** The argument that the control-plane RFC's typed collections
are too expensive dissolves — it was an artifact of the sync primitive, not
of the collections.

### 1.5 What this does not claim

* **Payload size is untested.** Request count and byte count are different
  costs and this trades one for the other. A cycle with nothing to report
  should return an empty envelope cheaply; one catching up after an outage
  will be large, which is exactly why `complete` and the page limit exist.
* **v1 is untouched.** Loop and Trio are on v1 and this gives them a reason
  to move that is not "v3 exists", which has not worked for several years.
* **Nothing is retired.** Per-collection `history` keeps working.

---

## 2. What replay actually needs, and who has to change

`specs/nsschema/dosing-input-sources.yaml` maps each algorithm's declared
dosing inputs to where, if anywhere, Nightscout records them. 60 inputs, all
60 verdicts confirmed against the corpus.

| | Declared | Recorded | Derivable | Partial | **Absent** |
|---|---|---|---|---|---|
| Loop | 20 | 4 (20%) | 7 | 1 | **8** |
| oref0 family | 40 | 20 (50%) | 9 | 3 | **8** |

**The structural finding that decides the whole proposal:**

> **All eight of Loop's absent inputs are configuration.**
> **Seven of oref0's eight are runtime state the algorithm holds in hand at
> decision time.**

Two different gaps, two different fixes, neither of which is "design a new
API". §3 and §4.

A note on the third column that must travel with every number here: a
*derivable* input is recomputed from stored history, which yields *a* value
and not necessarily *the* value the controller used — it saw a different
window, with different de-duplication and different noise handling. A replay
built on derived inputs tests the replayer as much as the algorithm. The two
columns should never be collapsed.

---

## 3. Change B — eight more keys in a dictionary Loop already writes

### 3.1 The channel exists and is in use

| | Measured |
|---|---|
| Profile documents carrying `loopSettings` | **200 of 202**, across **10 of 11 sites** |
| Therapy keys it already carries | `dosingEnabled`, `dosingStrategy`, `maximumBasalRatePerHour`, `maximumBolus`, `minimumBGGuard`, `overridePresets[]`, `preMealTargetRange`, `scheduleOverride` — eight of them, plus two identity keys handled in §3.4 |
| Conformance obligation `OBS-PROF-004` — "the dosing safety limits in force" | **met on 10 of 10 sites**, via this block |

Loop is already publishing a settings snapshot. It is simply missing the
eight values that scale the dose.

### 3.2 The eight

| Input | What it changes | Why a default is not good enough |
|---|---|---|
| `automaticBolusApplicationFactor` | The fraction of a recommended bolus actually delivered — **scales every automatic dose** | Defaults to 0.4 and is user-adjustable. A replay that assumes 0.4 is replaying the default, not the user |
| `maxActiveInsulinMultiplier` | Loop's IOB ceiling, as a multiple of `maxBolus` | Defaults to 2. It is the safety limit that determines when dosing stops |
| `carbAbsorptionModel` | Piecewise-linear vs nonlinear carb absorption | Changes the carb effect curve, and so the dose |
| `recommendationInsulinModel` | Which insulin activity curve the recommendation uses | `insulinType` on a treatment names the *product*, which is not the same thing |
| `useIntegralRetrospectiveCorrection` | Integral RC is a materially different correction behaviour | A user-facing toggle; two users with identical profiles dose differently |
| `includePositiveVelocityAndRC` | Whether positive velocity and RC enter the forecast | — |
| `useMidAbsorptionISF` | Whether ISF is re-evaluated mid-absorption | — |
| `gradualTransitionsThreshold` | Dose transition smoothing | — |

Plus one clarification rather than an addition: `recommendationType` is
*partial* today — `dosingStrategy` distinguishes `automaticBolus` from
`tempBasalOnly`, which covers the common case but is not the full set. A
mapping note in the controller description resolves it without a code change.

### 3.3 What it buys

| Loop replay completeness | Now | After |
|---|---|---|
| Recorded | 4/20 — **20%** | 13/20 — **65%** |
| Recorded or derivable | 11/20 — **55%** | 20/20 — **100%** |

### 3.4 Hub-side cost, and one safety condition

cgm-remote-monitor needs **nothing new** to accept these — they are keys in a
profile document it already stores. What it should add is a *published
schema* so the block stops being tacit, which is [Phase 1 of the
roadmap](./nightscout-adoption-roadmap-2026-09-11.md) and needs no new
endpoint.

**The safety condition.** `loopSettings` already carries `deviceToken` and
`bundleIdentifier` — push-notification identity, on 200 documents. Any
settings schema, catalogue entry, or conformance report derived from this
block must carry the type-level sensitivity annotation
(`specs/sync/sensitivity.yaml`) and must **never** propagate those two fields
into a served catalogue, a shared report, or an issue. A settings resource
that leaks a device token is worse than no settings resource.

---

## 4. Change C — oref0: emit the input vector, not just the output

### 4.1 What is missing is not configuration

Seven of the eight absent oref0 inputs are values `determine-basal` computes
or receives *on the way in* and then discards:

| Input | What it is |
|---|---|
| `mealData.mealCOB` | Carbs on board as the meal-assist path saw them |
| `mealData.slopeFromMaxDeviation` | Unannounced-meal detection state |
| `mealData.slopeFromMinDeviation` | ditto |
| `flatBGsDetected` | Whether the glucose series was flat enough to suppress dosing |
| `microBolusAllowed` | Whether SMB was permitted **on this run** |
| `iob.bolusSnooze` | Bolus snooze at decision time |
| `iob.iobWithZeroTemp.bolussnooze` | ditto, zero-temp projection |

Plus one that is configuration and is the most-cited gap in the series:

| `profile.maxIob` | The IOB safety limit. **Recorded by no oref0 derivative anywhere in the corpus.** `oref-digital-twin` lists it in `REQUIRED_SETTINGS` and must assume it |

`microBolusAllowed` is the clearest illustration of why "inferable" is not
"recorded": you can infer it after the fact from whether an SMB was enacted —
but only when one *was*. A cycle where SMB was allowed and not used is
indistinguishable from one where it was forbidden.

### 4.2 Where it goes

Alongside the decision, in the document already being written:
`openaps.suggested.inputs` (or a sibling key — the name matters less than
that it is one object containing the vector the algorithm was called with).
No new collection, no new endpoint, no API version change. oref0 has these
values in scope at the moment it writes `suggested`.

### 4.3 What it buys

| oref0 replay completeness | Now | After |
|---|---|---|
| Recorded | 20/40 — **50%** | 31/40 — **78%** |
| Recorded or derivable | 29/40 — **72%** | 40/40 — **100%** |

### 4.4 The caveat that governs every oref0 number here

**All `openaps.*` frequencies in this document come from one site.** The
corpus has no AAPS closed-loop site at all. Every AAPS-specific statement is
read from source, not observed, and is marked so. Trio and AAPS both
discriminate on `openaps` and are not distinguishable from each other at the
top level — a limit in this work, not only in anyone else's.

---

## 5. Change D — bounded reads must stay possible

`docs/proposals/api-query-normalization.md` caps `devicestatus` at **100
documents and a 7-day range** for anonymous callers, 5× for admin. The
problem it documents is real: `count=999999` and unbounded `devicestatus`
fetches are listed as *common*.

But the cap is expressed in the wrong unit for three legitimate readers:

* a replay tool walking a history,
* a decomposition migration reading everything once,
* a cursor client catching up after an outage — **indistinguishable from an
  abusive caller by request shape alone.**

**The change:** cursor-paginated reads are exempt from the *range* cap and
bounded by *page size* instead. A cursor already guarantees forward progress
and bounded work per request, which is the property the cap exists to
enforce. §1.3's `complete` flag is what makes the client loop rather than ask
for everything.

This is the same argument the sync design makes from the other side: a query
profile fixed in advance is what lets a bounded query be safe without being
small.

---

## 6. Change E — the cheapest fidelity gain, and it needs nobody's permission

`oref-digital-twin/replay/inputs.py` opens with:

> Two inputs cannot be recovered faithfully from devicestatus alone and are
> approximated: `currenttemp` — the temp basal running at decision time
> (assumed none); insulin `activity` — the IOB curve's instantaneous activity
> (assumed 0), which degrades bgi/eventualBG.

**Both halves are now out of date, in different directions.**

| | Docstring says | Actually |
|---|---|---|
| insulin `activity` | assumed 0 | **Already fixed in its own code** — `_iob_data_from_cycle` reads `openaps.iob.activity` when present and flags `activity_known` |
| `currenttemp` | assumed none | **Published, and not read.** `openaps.iob.lastTemp` carries `rate`, `duration`, `started_at` and `date` on **73,891 documents**. Our own dosing map classifies `currentTemp.rate` and `currentTemp.duration` as **recorded**, and `OBS-OREF-006` already checks for the path |

So the replay tool still substitutes `{"duration": 0, "rate": 0}` for a value
that is sitting in the document it is already parsing. That is a few lines in
one consumer, and it improves fidelity for every oref0 site immediately.

**And a correction this forces on our own series.** The hub-sync document and
the controller-descriptions proposal both cite this tool as evidence that two
inputs are unrecoverable. One never was unrecoverable and the other has
already been recovered. The *category* of finding stands — a serious replay
tool works around gaps Nightscout leaves — but this particular pair is the
wrong illustration of it. `max_iob`, which genuinely is recorded nowhere, is
the right one.

---

## 7. The conformance profile passes while replay is at 20%

`specs/conformance/observability-profile.yaml` defines 28 obligations across
seven roles. Measured across all 11 sites:

| | |
|---|---|
| Obligations met at **every** in-scope site | **27 of 28** |
| The only exception | `OBS-CGM-005`, signal quality — **MAY** level, met at 1 of 11 sites |
| Loop-specific obligations `OBS-LOOP-001…006` | **all met, 10 of 10 sites** |
| oref0-specific `OBS-OREF-001…007` | **all met, 1 of 1 site** |

A profile that passes everywhere, while the thing it exists to protect sits
at 20% completeness, is measuring presence rather than sufficiency. It asks
"is IOB written down" and not "is enough written down to reproduce the dose".

**The change:** derive the profile's obligations from the dosing-input map
rather than from hand-picked paths. Concretely, add one obligation per
declared input with `status: recorded`, at `SHOULD`, per algorithm family —
which makes the profile fail today, on purpose, at exactly the eight-plus-eight
places §3 and §4 name. A conformance report is only useful if passing it
means something.

This is a change to *our* artifact, not anyone else's, and it should land
before the profile is quoted at a maintainer.

---

## 8. Cost, per project

| Project | What is asked | Size |
|---|---|---|
| **Loop** | Eight more keys in the `loopSettings` block it already writes on 200 of 202 profile documents | Serialisation only. No new call, no new endpoint, no schema negotiation |
| **Trio / AAPS** | One object alongside `openaps.suggested` carrying the input vector; publish `maxIob` | Serialisation of values already in scope at the call site |
| **cgm-remote-monitor** | One collection-agnostic history endpoint and one batch write (§1); a published settings schema (§3.4); a cursor exemption in query limits (§5) | The two endpoints reuse `lastModified.js`'s loop and `history/operation.js`'s query. No storage or identity change |
| **`oref-digital-twin`** | Read `openaps.iob.lastTemp`; refresh a stale docstring | A few lines |
| **This repository** | Rebuild the conformance profile from the dosing-input map so it can fail (§7) | Generator change |

**Nothing in this list requires a new API version, and nothing requires any
two projects to move together.** Each change is useful alone, which is the
only sequencing property that matters when no maintainer has agreed to
anything.

---

## 9. Evidence

| Claim | Command | Output |
|---|---|---|
| 60 dosing inputs, per-algorithm status | `make schema-dosing` | `reports/schema-census/dosing-inputs.json` |
| `loopSettings` on 200 of 202 profile documents | `make schema-profile` | `reports/schema-census/profile.census.json` |
| `openaps.iob.lastTemp` on 73,891 documents | `make schema-devicestatus` | `reports/schema-census/devicestatus.census.json` |
| 27 of 28 obligations met everywhere | `make schema-observability` | `reports/schema-census/observability.json` |
| Endpoint counts and the batched comparison | `make schema-sync-cost` | `reports/schema-census/sync-cost.json` |

## 10. What is not measured

* **Payload size under a merged envelope.** §1.5.
* **Whether a decomposed set round-trips** into a document a legacy client
  accepts.
* **Anything about AAPS from data.** No AAPS closed-loop site in the corpus;
  all `openaps.*` figures are single-site.
* **Whether the eight Loop settings are accessible at the point Loop
  serialises `loopSettings`.** They are all `LoopSettings`/therapy-settings
  values, so this is likely, but it is read from source and has not been
  confirmed by anyone who maintains Loop.
* **Cursor behaviour under concurrent writers.** Two controllers plus a
  care-portal user writing to one site is the normal case, and `srvModified`
  ordering under that load is unexamined — here and upstream.
* **Nobody has been asked.** Every row in §8 is a proposal to a project, not
  a plan for it.
