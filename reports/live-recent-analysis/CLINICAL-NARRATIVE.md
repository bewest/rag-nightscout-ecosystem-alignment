# Live-recent — Clinical narrative

_Hand-authored interpretation layered on top of the auto-generated
`clinical-report.md`. Brings dietary / behavioural context (provided by
the patient out-of-band) into the picture and flags places where the
auto-pipeline’s recommendations should **not** be followed at face
value._

> **Patient context (out-of-band):** Loop, autobolus-OFF.
> Daily routine: ~1 lunch (light, often ~30 g carb), ~1 dinner (pork
> chop or similar fat+protein main, beans / pearled couscous / bread,
> dessert), with whiskey alongside dinner. Carbs almost never logged.

---

## 1. Headline glycemia (60 days)

| Metric | Value | vs target |
|---|---|---|
| Mean glucose | 160 mg/dL | high |
| GMI / eA1c | 7.14 % | just over target |
| TIR 70–180 | **63.8 %** | below 70 % |
| TBR <70 | 2.7 % | borderline |
| TBR <54 | 0.14 % | safe |
| TAR >180 | 33.5 % | high |
| TAR >250 | 8.8 % | acceptable |
| CV | 39.3 % | above 36 % |
| Hypo events / day | **0.67** (~2 every 3 days) | not catastrophic but real |

So the dominant problem is **time-above-range driven by long
post-dinner tails**, not chronic basal deficit. The hypos that exist
are sparse and (per the dietary pattern) almost certainly clustered
overnight when alcohol, leftover dinner IOB, and reduced hepatic
glucose output align.

---

## 2. The dietary signature, in the data

### 2.1 Detected meals match the reported pattern

`pipeline.json::meal_history` finds (per typical day):
- ~11:00–13:00: lunch, ~25–30 g equivalent
- ~20:00: dinner, ~30–35 g equivalent
- often a small late carb pulse (the reported dessert)

That matches “lunch + dinner + dessert”, with **none of them logged**
(`announced=false` everywhere; `meal_logging_qc.flag = under_logger`,
ratio 0.01). This is why §5 of the auto-report says “98 % of detected
meals have no carb entry”.

### 2.2 Insulin action lasts much longer than the pump thinks

`dia_discrepancy`:
- IOB-decay DIA: **3.5 h** (what Loop assumes)
- Glucose-effect DIA: **6.5 h** (what actually happens)
- discrepancy ratio: **1.82×**

`two_component_dia` decomposes this: **63 %** fast component (τ ≈ 0.8 h)
+ **37 %** persistent tail running 12 h. That long persistent tail is
exactly what you’d expect from boluses and basal **stacked on top of
fat-+-fibre-delayed absorption**. The pump model treats the bolus as
done at 3.5 h; the system is still feeling it at 6 h.

### 2.3 Overnight pattern is alcohol-shaped, not basal-deficient

`overnight_assessment` (n_clean_nights = 5 of 56, confidence 0.35):

| Field | Value | Reading |
|---|---|---|
| `mean_overnight_glucose` | **180.6 mg/dL** | high — sitting on dinner tail |
| `drift_mg_dl_per_hour` | **−5.0** | actively dropping ~30 mg/dL overnight |
| `dawn_rise_mg_dl` | **−6.9** | **no dawn phenomenon** |
| `loop_suspension_pct` | **48.3 %** | Loop is already cutting basal half the night |
| `suggested_basal_change_pct` | **−7.4 %** | overnight model wants **less** basal, not more |

`per_patient_egp` ranks this even more strongly:
- Patient `glucose_roc` in deep-fasting / low-IOB windows: **−1.0
  mg/dL per 5 min** (population baseline +1.5)
- Equilibrium basal multiplier: **1.22** — controller sustains 22 %
  *above* scheduled basal during equilibrium

Interpreting these together: when the patient is genuinely fasting and
has little IOB, glucose **drifts down**, not up. That is the classic
fingerprint of **alcohol-suppressed hepatic glucose output** plus the
fat-+-protein dinner still trickling in. The 1.22× equilibrium basal
multiplier is not telling us “the basal schedule is too low”; it is
telling us “the controller has to push extra basal to clear the slow
post-dinner tail, on top of an unusually quiet liver.”

### 2.4 Phenotype fingerprint

`phenotype.evidence`:

> Hypo-prone (high variability): CV=0.39>0.36, TIR=63.8 %, TBR=2.6 %.

`stack_score = 2.0`, `brake_ratio = 0.254` (live-recent §4a). Combined
with the long persistent IOB tail above, this is a **stacking-prone
profile**: late/large dinner correction → tail still running →
overnight controller pulls basal hard → late-night descent. Exactly
the mechanism that produces the sparse but real overnight hypos.

---

## 3. Where the auto-recommendations are right vs misleading

The auto-`clinical-report.md` §5 currently emits five recs. Reading
each through the dietary lens:

| # | Auto-rec | Verdict |
|---|---|---|
| 1 | **ISF: 40 → 18** (more aggressive corrections) | ⚠️ **Do not act on as-stated.** Driven from only **2 correction events**; the +26 pp TIR delta is statistically meaningless at that n. The underlying signal (`dia_discrepancy 1.82×`, `iob_persistent_effect 37 %`) actually argues the opposite: corrections already act longer than the pump thinks, so smaller / less-frequent corrections, not bigger, are safer. |
| 2 | **Overnight basal: 1.70 → 2.04 U/h (+20 %)** | ❌ **Probably harmful.** Directly contradicts `overnight_assessment.suggested_basal_change_pct = −7.4 %` and `loop_suspension_pct = 48.3 %`. Loop is already cutting basal half the night because the alcohol-suppressed liver + slow dinner tail pushes glucose **down** overnight. Raising basal here is the textbook recipe for an alcohol-induced 03:00 hypo. |
| 3 | **Correction threshold: 180 → 166 mg/dL** | ⚠️ Moves in the wrong direction for this phenotype. With a 6.5 h glucose-effect DIA and stacking tendency, lowering the correction trigger means more overlapping corrections on a still-falling tail. |
| 4 | **Log meals (98 % unannounced)** | ✅ **Most important rec in the report.** Every other lever is blunted while every meal arrives unannounced. Even rough carb estimates would unlock pre-bolus timing and let Loop’s autobolus / SMB logic see the meal coming. |
| 5 | **TAR 33 % — review CR / carb counting** | ✅ Correct *direction* but the right intervention is meal-shape (pre-bolus + extended) and meal-logging, not just CR. |

**Internal-consistency bug:** the recommender (Rec 2: +20 % basal)
disagrees with `overnight_assessment` (−7.4 %) and with
`aid_compensation` (which mirrors Rec 2). The pipeline is currently
emitting the more aggressive of two contradictory advisor outputs
without a conflict-resolution layer that weighs the
overnight-specific, alcohol-aware signal more heavily. Filed as a gap;
see plan.md.

**Detection bug:** `warnings[1]` says “Controller detected: AAPS
(balanced).” Patient is actually Loop, autobolus-OFF. Controller
detection is misclassifying — likely because absent autobolus, the
SMB/temp-basal pattern looks AAPS-like to the heuristic. This affects
which advisor codepaths fire. Filed as a gap.

---

## 4. What we would actually recommend (clinician-facing)

In rough priority order:

1. **Pre-bolus + extended/dual-wave for dinner.** Front-load 50–60 %
   of the dinner bolus 15–20 min before the first bite; spread the
   remainder over 2–3 h to match the pork-chop + bean / couscous +
   dessert absorption curve. This collapses the late-night tail that
   currently drives the 33 % TAR.
2. **Log meals — even rough estimates.** Carb logging unlocks
   essentially every other Loop lever (predictions, autobolus if ever
   re-enabled, retrospective correction). 98 % unannounced is the
   single biggest leverage point in the dataset.
3. **Alcohol-aware overnight rule.** On evenings with whiskey, set a
   higher overnight target (e.g. +20 mg/dL) or run a Loop override
   that softens basal. **Do not** raise scheduled basal: the
   alcohol-suppressed liver means raised basal will produce an
   overnight low on the very nights the rationale assumed it
   wouldn’t.
4. **Leave ISF alone for now.** Re-evaluate after 4 weeks of meal
   logging — the existing ISF estimate is built on too few correction
   events to be trustworthy, and the 1.82× DIA discrepancy means the
   measured ISF is being attributed to too short a window anyway.
5. **Consider Loop autobolus ON, _after_ the above.** The current
   autobolus-OFF posture means correction insulin only arrives when
   the user notices the climb — given the slow, late dinners that is
   almost always too late. Autobolus would shorten the lag, but only
   safely once meal logging and the alcohol-overnight rule are in
   place; otherwise it would amplify the stacking signature already
   visible in `phenotype.stack_score`.
6. **Trio / oref1 is not the lever here.** From the experiments
   in this repo (EXP-2929/2930/2934/2937), the oref1 advantage shows
   up most cleanly on patients who are *over-bolused* at meals and
   need front-loaded UAM. This patient is *under-bolused* at meals
   (because nothing is logged) and is on the wrong end of an
   alcohol-shaped overnight; switching algorithms wouldn’t address
   either.

---

## 5. Counter-intuitive headline (sanity check)

> _“We are below TIR target with TAR 33 %. Are we really saying that
> lowering insulin delivery on every channel would improve TIR?”_

Not on every channel — only **overnight** and **on corrections**.
The right move is:

- **More** insulin **at meals** (pre-bolus, extended, eventually
  autobolus once meals are logged) → eats into the 33 % TAR.
- **Less** insulin **overnight on alcohol nights** → keeps the sparse
  but real hypos from getting worse.
- **Logging** is what unlocks both directions.

The auto-pipeline’s suggestion to raise overnight basal and tighten
corrections is treating the *symptom* (high mean, some hypos) without
the *cause* (slow late dinner + alcohol-suppressed liver +
unannounced meals).

---

## 6. Provenance

- Auto-generated facts: `clinical-report.md`, `facts.json`,
  `pipeline.json`, `meal_audit.csv` (this directory).
- Pipeline: `tools/cgmencode/production` at HEAD.
- Wrapper: `tools/cgmencode/run_private_report.py`.
- Source parquet: `externals/ns-parquet/live-recent/grid.parquet`
  (gitignored).
- Profile timezone: `Etc/GMT+8`.
