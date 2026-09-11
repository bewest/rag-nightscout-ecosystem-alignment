# Is there enough evidence for a unified primitive catalogue? A coverage assessment

Date: 2026-09-11. Status: draft for maintainer discussion.

**Short answer: no, we had not done it — five documents referenced a set of
primitives and none defined them. It is now built, and the evidence supports
63% of it with measurement, 37% by declaration only, and names 19 fields
nothing carries at all.**

---

## 1. What was actually missing

Before this change, the artifacts in this series **named** 15 primitives —
every registration says `decomposesTo: [Bolus, CarbIntake, TempBasal, ...]`
— and **defined none of them**. `ControllerSettings` was referenced as a
resource by all three registrations and had no schema. The settings blocks
were bare field-name lists: no types, no units, no ranges, no semantics.

So the composition story had a hole in the middle. Decomposition was
measured (99.86% of treatments route), the sync contract referenced
primitives, the effects model sat beside them — and "what is a `Bolus`" had
no answer in this repository.

Two artifacts close it:

| | |
|---|---|
| `specs/sync/primitives.yaml` | 16 primitives, 134 fields, **each field graded by what backs it** |
| `specs/sync/controller-settings.schema.json` | 19 typed settings, effective-dated, build-versioned. This is roadmap phase 1, which five documents asked for and none wrote |

## 2. How much evidence there actually is

Every field carries a grade, because "we have primitives" and "we have
evidence for primitives" are different claims:

| Grade | Count | Meaning |
|---|---|---|
| `measured` | **84 (63%)** | A wire path in the corpus populates it, or Nocturne's own decomposer maps it from a path the corpus carries |
| `declared` | 50 (37%) | A typed model declares it; this corpus shows no source. Real, unverified |
| `proposed` | 19 more | *We* are asking for it. No shipped model has it |

Per primitive:

| Primitive | Fields | measured | declared |
|---|---|---|---|
| `PumpSnapshot` | 13 | 11 | 2 |
| `ApsSnapshot` | 25 | 14 | 11 |
| `SensorGlucose` | 14 | 8 | 6 |
| `TherapySettings` | 18 | 8 | 10 |
| `Bolus` | 13 | 6 | 7 |
| `TempBasal` | 14 | 6 | 8 |
| `BGCheck` | 5 | 4 | 1 |
| `UploaderSnapshot` | 6 | 4 | 2 |
| `StateSpan` | 8 | 4 | 4 |
| `CarbIntake` | 5 | 2 | 3 |
| `DeviceEvent` | 2 | 2 | — |
| `Note` | 3 | 2 | 1 |
| the four schedules | 8 | 4 | 4 |

### 2.1 The grading was wrong twice before it was right

Worth recording, because the first number was 45/134 and publishing it would
have understated the evidence by a third:

1. **V4 renames on the way in.** `SensorGlucose.Mgdl` is fed by `entries.sgv`;
   `BasalSchedule.Entries` by `profile.store.{}.basal[]`. Name-level matching
   scores a rename as "no evidence" — precisely where the model is doing its
   job.
2. **A generic-name filter suppressed real matches.** `programmed`,
   `duration` and `delivered` are in the corpus on 10 sites and were being
   discarded for being common words.

The fix was to stop guessing and read **Nocturne's own decomposer
assignments** — `Iob = ds.OpenAps.Iob?.Iob`, `Entries =
ConvertTimeValues(profileData.Basal)`. The model states where each value
comes from; combining that statement with the corpus is far stronger evidence
than either alone. That recovered 39 fields, and the remaining generic
matches are flagged `low_confidence` rather than silently counted.

## 3. Where the evidence is strong, and where it is not

**Strong — build on it now**

* **The shape.** All 16 primitives exist as typed classes in a shipped
  implementation, and 99.86% of real treatments route into them by
  `eventType` alone. The decomposition is not speculative.
* **Device and decision state.** `PumpSnapshot` 11/13 and `ApsSnapshot`
  14/25 measured — the two primitives an observability or replay consumer
  reaches for first.
* **Observations.** `SensorGlucose` and `BGCheck` are well grounded.

**Weak — do not claim confidence**

* **`TherapySettings` at 8/18.** The settings primitive is the one the
  physician complaint is about, and it is the *least* grounded of the large
  ones, because the corpus was collected through `/api/v1/` and settings
  mostly are not there.
* **The four schedules at 4/8.** Their `ProfileName` and `Entries` shape is
  right; the `ScheduleEntry` interior is unexamined.
* **Anything AAPS.** No AAPS closed-loop site in the corpus. Every AAPS
  statement in this series is read from source.

**Absent — 19 fields nothing carries**

Including `automaticBolusApplicationFactor` (scales every automatic Loop
dose), `carbAbsorptionModel`, `maxIob`, `microBolusAllowed` and
`flatBGsDetected`. These are not modelling gaps; they are **publication**
gaps, and they are the content of the settings schema.

## 4. The settings schema — phase 1, written

`specs/sync/controller-settings.schema.json`: 19 settings, generated from the
dosing-input map so it cannot claim more than was measured.

| Status today | Count | Fields |
|---|---|---|
| recorded | 4 | `dia`, `maxBasalRate`, `maxBolus`, `units` |
| partial | 4 | `dosingStrategy`, `maxBasal`, `recommendationType`, `suspendThreshold` |
| derivable | 1 | `maxDailyBasal` |
| **absent** | **10** | `automaticBolusApplicationFactor`, `carbAbsorptionModel`, `gradualTransitionsThreshold`, `includePositiveVelocityAndRC`, `maxActiveInsulinMultiplier`, `maxIob`, `microBolusAllowed`, `recommendationInsulinModel`, `useIntegralRetrospectiveCorrection`, `useMidAbsorptionISF` |

Three design decisions worth arguing with:

* **Every setting is optional, and absent is not a default.** A controller
  publishes what it has; "not published" is information a replay needs, and
  collapsing it into a default value is how a replay silently becomes
  fiction.
* **`controller.version` is required.** Algorithm behaviour changes between
  releases, so a setting without a build cannot be replayed against the right
  code.
* **Eleven inputs were deliberately excluded** as per-cycle state rather than
  configuration — `flatBGsDetected`, the meal-detection slopes, the IOB
  components, and the *effective* sensitivity and carb ratio, whose scheduled
  forms belong to the schedule primitives. The boundary is stated in the
  generator rather than implied, because it is exactly the kind of line that
  drifts.

## 5. So: enough evidence, with high confidence?

Honestly graded:

| Question | Answer |
|---|---|
| Enough to name the primitives? | **Yes.** All 16 exist in a shipped implementation and the routing is measured |
| Enough to define their fields with confidence? | **For 63%.** The rest is declared-but-unobserved, and labelled as such |
| Enough for high-fidelity replay? | **No, and the catalogue now says exactly why**: 10 settings no controller publishes, plus 8 oref0 run-state inputs |
| Enough for observability? | **Mostly yes** — the device and decision primitives are the best-grounded, and the obligations profile states the floor |
| Enough to unify the proposals? | **Yes, structurally.** The catalogue is the missing referent; every other document in this series pointed at it |

The useful way to read 63% is not as a shortfall but as a map: it says which
parts of a decomposition could be built today against real data, and which
would be building against a model nobody has verified. Those are different
risks and they were previously indistinguishable.

## 6. What would raise confidence most, in order

1. **Collect a corpus through `/api/v3/`.** A large share of `declared` is an
   artefact of v1 collection — the metadata envelope and anything v3-only is
   structurally invisible. This is a fetcher change, not a negotiation.
2. **One AAPS closed-loop site.** It would convert every AAPS claim in this
   series from source-derived to corroborated.
3. **Any controller publishing a settings document.** Ten absent settings
   become measurable the moment one does.
4. **Examine `ScheduleEntry`.** The schedules' interior is the largest
   unexamined structure.
5. **Ask Nocturne whether the decomposer assignments are the intended
   mapping**, rather than inferring them from source.

## 7. Reproduce

```bash
make schema-primitives   # -> specs/sync/primitives.yaml
make schema-settings     # -> specs/sync/controller-settings.schema.json
make schema-dosing       # the input map both are generated from
```

Tests pin the parts that would rot silently: that every primitive a
registration names is defined, that every field is graded with a reason, that
the decomposer assignments still parse, that the settings schema still
requires a build version, and that per-cycle state stays out of it.
