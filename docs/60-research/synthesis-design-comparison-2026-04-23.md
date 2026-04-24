# Synthesis: AID Controller Design Comparison (Apr 2026)

**Date:** 2026-04-23
**Scope statement (binding):** This is **scientific characterisation
of AID controller design choices for open-source AID author
audiences**. It is NOT therapy advice, NOT a per-patient
device-migration recommendation, and NOT a claim of one AID being
"better" for any individual. Patient choice and autonomy depend
on many factors (device access, regulatory, ergonomics, support
ecosystem, feature preferences) outside the scope of any
outcome-numbers analysis.

**Cohort:** 19 patients with lineage-known data — 7 Loop (iOS),
9 oref1 (modern AAPS / Trio), 3 oref0 (legacy openaps/AAPS). All
oref0 cells in derived analyses are n=1–3.

**Source:** `externals/ns-parquet/training/grid.parquet` 5-min cells
(944k rows after lineage filter), `externals/experiments/exp-2891_simpson_dose_response.parquet`
for lineage/cf labels. EXP-2916 through EXP-2927.

---

## 1. Headline outcomes table

| Lineage | n | TIR    | TBR  | TAR    | Fasted-dawn 03:00 hyper | Overnight severe-hypo (low_cf) |
|---------|--:|-------:|-----:|-------:|------------------------:|-------------------------------:|
| Loop    | 7 | 66.1 % | 3.88 | 30.04 %| **12.51 %**             | 0.44 % (n=1)                   |
| oref0   | 3 | 73.7 % | 5.27 | 20.99 %|  5.25 %                 | **4.18 %**                     |
| **oref1** | 9 | **82.6 %** | **3.64** | **13.78 %** | **1.53 %** | 0.61 %                |

oref1 Pareto-dominates Loop on TIR/TBR/TAR pooled (EXP-2925).
The dominance survives Guard #6 cf-conditioning at every tertile
where comparison is possible (EXP-2924, EXP-2925, EXP-2927).

---

## 2. Mechanism stack

| Design feature                    | Loop OFF | Loop ON  | oref0    | oref1    |
|-----------------------------------|---------:|---------:|---------:|---------:|
| Brake-only basal cuts             | yes      | yes      | yes      | yes      |
| Fast basal-cut latency (≤0 min)   | **yes**  | no       | **no (10 min)** | yes |
| SMB as correction                 | no       | partial  | yes      | yes      |
| Pre-emptive autobolus             | no       | **yes**  | no       | partial  |
| Dynamic ISF                       | no       | no       | no       | **yes**  |
| UAM detection                     | no       | no       | partial  | **yes**  |
| **Fasted-dawn hyper %**           | 17.0     | 10.7     | 5.3      | **1.5**  |
| **Pooled TIR %**                  | (split)  | (split)  | 73.7     | **82.6** |

"Loop is two designs" (EXP-2919/2921): autobolus on/off produce
divergent fingerprints (3× latency difference, 2× dawn-hyper
difference). Cross-design tables that aggregate Loop conflate
two distinct policies.

---

## 3. The four design-level findings (with confirmation layers)

### Finding A — Dawn fingerprint (dynamic-ISF lever)

**Loop fasted-dawn 03:00 hyper = 12.51 %; oref1 = 1.53 % (8× gap).**

| Layer | Source       | Evidence |
|-------|--------------|----------|
| 1 — Single-mechanism isolation | EXP-2923  | fasted-only filter rules out meal carry-over |
| 2 — cf-conditioning Guard #6  | EXP-2924  | mid_cf 14.17 pp [12.47, 15.90]; high_cf 4.33 pp [0.04, 8.62] |
| 3 — Decomposition with state  | EXP-2922  | autobolus halves the gap proportionally in BOTH states |

**Causal interpretation:** Brake-only loops cannot address EGP
rises by definition. Dynamic-ISF widens overnight sensitivity
and pre-emptively raises insulin demand against EGP. This is
the cleanest single-mechanism design comparison in this workspace.

### Finding B — Post-prandial gap (UAM/SMB lever; dose-shape mechanism)

**Loop PP TIR = 48.64 %; oref1 PP TIR = 75.81 % (27 pp gap).**

| Layer | Source     | Evidence |
|-------|------------|----------|
| 1 — Pooled state TIR | EXP-2927 | 48.64 vs 75.81 % at PP |
| 2 — cf-conditioning  | EXP-2927 | mid_cf +27.80 pp [+7.93, +46.32]; high_cf +18.48 pp [+0.06, +37.55] |
| 3 — Comparator cell  | EXP-2927 | oref0 PP TIR 70.47 % — UAM+SMB stack alone is competitive |
| 4 — Autobolus split  | EXP-2929 | Loop_AB_OFF PP TIR = 32.14 %; ON = 55.23 %. Autobolus closes 53 % (23.10 of 43.67 pp) of the gap; residual 20.57 pp [+7.02, +36.28] |
| 5 — Dose-shape mechanism | EXP-2930 | First-SMB latency identical (oref1 10 min vs Loop_AB_ON 12 min). oref1 front-loads dose: **2.2× in 0-30 min, 6.6× in 30-60 min**. Loop catches up corrective at 120-240 min into already-elevated BG |

**Causal interpretation:** Half of Loop post-prandial cells are
out of range. The mechanism is **dose shape, not cadence or
first-fire timing** — both designs fire 4-7 SMBs per meal at
the same first-fire latency. oref1's UAM detector + dynamic-ISF
loads insulin during the early absorption phase; Loop autobolus
fires when prediction crosses target (typically 30-90 min post-meal)
and back-loads correction into already-elevated BG. **This is the
larger absolute lever** — bigger than the dawn fingerprint.

**Decomposed causal chain (closed by EXP-2930):**
- ~53 % of the brake-only PP gap is closable by enabling autobolus
  (Loop_AB_OFF → Loop_AB_ON, no UAM needed).
- Remaining ~47 % requires a **glucose-appearance / UAM-style
  detector** that does not depend on prediction crossing target,
  plus **dynamic-ISF widening during early absorption** to
  amplify the auto-correction dose.

### Finding C — Overnight basal-cut latency (oref0 weakness)

**oref0 midnight severe-hypo = 4.18 %; oref1 = 0.61 % (~7×, non-overlapping CIs).**

| Layer | Source      | Evidence |
|-------|-------------|----------|
| 1 — Latency by design | EXP-2918  | oref0 median latency 10 min vs Loop/oref1 0 min |
| 2 — Outcome by design | EXP-2920  | midnight peak hypo 4.66 % oref0 vs 1.27 % oref1 |
| 3 — cf-conditioned    | EXP-2925  | low_cf cell oref0 4.18 % CI[1.94, 6.58] vs oref1 0.61 % CI[0.42, 0.80] |

**Causal interpretation:** oref0's slower basal-cut decision
policy translates to ~7× higher overnight severe-hypo incidence
under matched cf load. **Lowest-hanging design fix for legacy
code.** Note: oref0 is otherwise competitive (PP TIR 70.47 %,
fasted-dawn 5.25 %) — its design weakness is temporally specific.

### Finding D — Loop autobolus is two designs

**Autobolus halves dawn-hyper but doesn't change morning hypo
or basal-cut latency.**

| Layer | Source     | Evidence |
|-------|------------|----------|
| 1 — Latency split | EXP-2919 | OFF mean 9.3 min, ON mean 31.0 min |
| 2 — TOD hyper     | EXP-2921 | OFF 30.65 % at 04:00, ON 14.30 % at 03:00 |
| 3 — State decomp  | EXP-2922 | autobolus reduces hyper ~40 % in BOTH fasted and PP |

**Implication:** Cross-design tables that aggregate Loop conflate
two policies. Future comparisons should split (or note Loop
results carry hidden subgroup variance ~2×).

---

## 4. AID-author priority order

Suggested by absolute TIR delta in this cohort:

1. **UAM detection + SMB-as-correction during absorption.**
   Largest TIR delta (~27 pp PP). Addresses the dominant
   out-of-range burden.
2. **Dynamic-ISF for dawn EGP.** Cleanest causal isolation;
   smaller absolute effect (~17 pp fasted) but distinct
   physiologic lever.
3. **Improve basal-cut latency.** Smallest absolute TIR effect
   but the lowest-effort fix in legacy oref0/openaps codebases
   and the highest-impact safety improvement (overnight severe
   hypo).
4. **For Loop-style brake-only loops: enable autobolus.**
   Halves dawn 03:00 hyper and closes ~53 % of the PP TIR gap
   (EXP-2929). Does not address the residual UAM/dynamic-ISF lever
   (~47 % of PP gap remains; ~16 pp fasted gap unchanged).
5. **Dose shape, not cadence.** Both autobolus and oref1-UAM fire
   ~5 SMBs per meal at the same first-fire latency (EXP-2930).
   The lever is **front-loaded delivery during early absorption**
   (oref1 delivers 2.2× the dose in 0-30 min and 6.6× in 30-60 min
   post-meal), which requires UAM-style appearance detection and
   dynamic-ISF widening — not "fire SMBs more often."

---

## 5. Methodological invariants codified by this arc

1. **Cross-AID comparisons are scientific characterisation, not
   therapy advice** (binding scope statement). Audition flags
   must NOT recommend changing AID systems.
   See `exp-2916-design-gap-2026-04-23.md`.
2. **Default Guard #6 (cf-conditioning):** any cross-design claim
   must be tested after matching/stratifying on patient cf load.
   Toolkit §4.6.
3. **Default Guard #7 (load-mediation, EXP-2912/2913):** when
   correlating cf with physiology outcomes, also report against
   `cf × (1 − protection)` to detect coverage-distribution artefacts.
   Toolkit §4.7.
4. **Small-n bootstrap caveat (EXP-2917):** paired CIs against
   n=1 cells are degenerate (zero-width) and inherit only the
   multi-patient side's variance. Always flag with † and corroborate
   with mechanism stack. Toolkit §2.8 (extended).
5. **3D mechanism stack template** (EXP-2892 + 2916 + 2918): when
   cell n is small, three independent dimensions of the same
   design decision-policy gap (utilisation × magnitude × latency)
   substitute for inferential CI.
6. **Loop is two effective designs.** Always consider splitting
   Loop by autobolus on/off in cross-design analyses.

---

## 6. Cohort and statistical caveats

- 19 patients total, 7/9/3 split by lineage. All oref0 cells in
  finer breakdowns are n=1–3.
- Hour-of-day not TZ-normalised. Patient-local clock as recorded.
- `time_since_carb_min` capped at 360 — long fasts all bin into
  ≥300 min.
- `cf_severe` tertiles defined on overall cf, not state-windowed.
- All statistics are observational, not interventional. No patient
  was randomised to a design.

The single largest data-quality improvement available is **AAPS
data ingestion (EXP-2908)** — only path to widening the oref-family
patient base and resolving all n=1 oref0 cells with honest CIs.

---

## 7. Experiment index for this arc

| EXP    | Title | Result |
|--------|-------|--------|
| 2916   | Design gap (cell-level) | oref0/oref1/Loop protection deltas |
| 2917   | Bootstrap CIs | mid_cf and high_cf gaps significant |
| 2917b  | Forest plot | n=1 cells flagged; visual companion |
| 2918   | Basal-cut latency | oref0 only design with non-zero median |
| 2919   | Loop autobolus split | OFF 9.3 min vs ON 31.0 min |
| 2920   | TOD profiles | Loop dawn-hyper 18.93 % at 03:00 |
| 2921   | Loop autobolus × TOD | autobolus halves dawn-hyper |
| 2922   | Fasted vs PP (Loop) | dawn signature is real, not meal carry-over |
| 2923   | Fasted vs PP (cross-design) | 8× fasted-dawn gap Loop vs oref1 |
| 2924   | Guard #6 confirmation | 8× gap survives cf-matching |
| 2925   | Hypo symmetry | oref1 Pareto-dominates; no hypo trade |
| 2927   | TIR decomposition | PP gap > fasted gap (1.4–1.7×) |
| 2929   | Loop autobolus × PP TIR | autobolus closes 53 % of PP gap; FASTED unchanged |
| 2930   | SMB temporal alignment | identical first-fire latency; oref1 front-loads dose 2.2-6.6× |
| Toolkit | Guard #7 (load-mediation), §2.8 small-n caveat | new methodological additions |

---

## 8. Outstanding questions (next R&D batch)

- **EXP-2931 candidate:** Apply Guard #7 retroactively to
  EXP-2912 stacker phenotype claim.
- **EXP-2932 candidate:** post-meal TBR by design — does oref1's
  front-loaded dose carry hypo cost? ("no free lunch" check at
  meal-window granularity).
- **AAPS ingestion (EXP-2908):** the only structural fix for
  small-n oref0 cells.
- **Per-patient TZ normalisation:** removes the local-clock
  caveat from all TOD findings.

---

## Addendum (Apr-23 ninth+tenth batches): Recovery channel decomposition

### Finding D — Sustained-high recovery: two-tier mechanism stack

**Claim:** During carb-isolated sustained-high windows (BG crosses
180 from quiet baseline, 60-min carb-guard before/after), recovery
follows a **two-tier algorithmic structure**:

| Tier | Lever | Evidence | Effect |
|------|-------|----------|--------|
| 1. Channel availability | SMB-as-correction present | EXP-2942 cross-cohort match (oref0 zero-SMB ≈ Loop_AB_OFF zero-SMB at 30%) | +6 pp Loop_AB_ON over no-SMB floor |
| 2. Dose-sizing logic | velocity/absorption-aware sizing | EXP-2937 (sizing not cadence) + EXP-2940 (time-to-peak 22.9 vs 29.7 min) | +21 pp oref1 over Loop_AB_ON |

**Per-design recovery (4 060 events, 19 patients):**

| Design       | Recovery | SMB count | Decline |
|--------------|---------:|----------:|--------:|
| Loop_AB_OFF  |   29.6%  |   0.00    |  −0.38  |
| Loop_AB_ON   |   35.7%  |   4.31    |  −0.18  |
| oref0        |   30.0%  |   0.00    |  −0.12  |
| oref1        |   57.0%  |   2.82    |  +0.21  |

### Mechanism-elimination cascade (EXP-2937–2941, then 2942–2943)

To attribute the +21 pp Loop_AB_ON → oref1 gap to a specific channel,
8 candidates were sequentially refuted in carb-isolated windows:
SMB cadence, first-fire latency, total dose, dose-to-velocity,
dose-per-mgdl above target, dynamic-ISF amplification slope,
within-window dose schedule shape, and pre-window SMB IOB proxy.

EXP-2941 flagged selection-bias as the leading hypothesis. EXP-2942
and EXP-2943 then **rebutted selection-bias** with two independent
tests:

- **EXP-2942 cross-cohort match.** oref0 (n=3, no SMB, OpenAPS
  algorithm family) recovers at 30.0%, statistically
  indistinguishable from Loop_AB_OFF (29.6%, CI [−0.095, +0.087]).
  Two no-SMB designs from entirely independent patient cohorts
  converge — selection bias would not predict this.
- **EXP-2943 variance decomposition.** η² = 0.640 (design explains
  64% of recovery variance vs 36% from within-design patient
  heterogeneity).

**Combined verdict:** algorithm-channel hypothesis rehabilitated.
The single in-grid lever that distinguishes oref1 from Loop_AB_ON
is dose-sizing logic (the EXP-2940 6.8-min time-to-BG-peak signal).
Patient-self-selection cannot be fully eliminated without
within-patient AID-switch data, but is no longer parsimonious.

### Methodological invariant added

- **Cross-cohort matching + η² > 0.5 = selection-bias rejected.**
  When two algorithmically-matched designs from independent patient
  cohorts converge to within-CI on the outcome AND design assignment
  explains majority of variance, the design — not the cohort — is
  the dominant signal. Use as canonical rebuttal template when
  in-grid mechanism search exhausts.

### AID-author priority order (re-affirmed, post EXP-2942/2943)

1. UAM/glucose-appearance + dynamic-ISF (PP offence)
2. SMB-as-correction during sustained-high (channel-availability tier)
3. **Size correction SMBs to BG and BG velocity, not to
   IOB-shortfall vs forecast** (dose-sizing tier — re-affirmed)
4. Enable autobolus by default for AID-OFF correction loops
5. Basal-cut latency (defence-side temporal — EXP-2918)

### Experiment additions to index

| EXP    | Title | Result |
|--------|-------|--------|
| 2933   | Pre-meal context | Guard #8 founded; explains EXP-2931 early-TBR gap |
| 2934   | Day-level TIR Guard #8 | TIR edge = avoidance + recovery (compounding) |
| 2937   | Sustained-high recovery | sizing lever, not cadence/latency |
| 2938   | Velocity-binned recovery | gap constant across velocity tertiles |
| 2939   | Dynamic-ISF amplification proxy | both designs scale similarly; refuted |
| 2940   | Within-window dose schedule | identical schedules; time-to-peak 6.8 min apart |
| 2941   | Pre-window IOB proxy | identical; selection-bias hypothesis flagged |
| 2942   | oref0 cross-cohort | 30.0% ≈ 29.6% Loop_AB_OFF — selection-bias rejected |
| 2943   | Variance decomposition | η²=0.640 design-dominated |
| 2944   | True-IOB during sustained-high | iob_delta +0.629U gap — Loop loading vs oref1 peaking |
| 2946   | PP IOB timing | Loop iob_peak 9.0 vs oref1 4.5 U; iob-vs-bg-peak lead -35 vs -55 min |
| 2947   | Hypo IOB-age | Loop more cuts/decay yet 2× severe-hypo; mechanism is IOB AGE |

---

## 9. Finding E — UNIFIED IOB-AGE FRAMEWORK

After EXP-2944/2946/2947, all three window-class outcomes
(sustained-high recovery, PP TIR, hypo descent TBR) collapse to a
single design principle.

### One mechanism, three windows

| Window         | Outcome  | Loop_AB_ON pattern                | oref1 pattern                          |
|----------------|----------|-----------------------------------|----------------------------------------|
| Sustained-high | Recovery | IOB +0.59 U during window (climbing) | IOB −0.04 U (peaking, acting now)   |
| PP             | TIR      | IOB peak 35 min before BG peak    | IOB peak 55 min before BG peak         |
| Hypo descent   | TBR      | Less iob_at_entry, MORE prior decay, MORE basal cuts; 2× severe-hypo | More iob_at_entry, less decay, fewer cuts; less hypo |

### The unifying variable: IOB AGE

EXP-2947 reveals what underlies the three observations:

- **Fresh IOB** (recently delivered, pre-peak action) drives BG
  down regardless of basal-cut posture. Loop_AB_ON shedding IOB
  faster doesn't help because the IOB it has is still at its
  most active phase.
- **Stale IOB** (post-peak, gracefully decaying) is a buffer
  rather than a driver. oref1's higher iob_at_entry at hypo
  descents is benign because the dose was placed earlier and
  the active phase is past.

The same IOB value can be a **hazard** (fresh) or a **buffer**
(stale) depending on age relative to the response window.

### Single AID-author design principle

**Predict-and-fire on rising velocity early, so that IOB ages
before the BG response window.**

This produces:
- During BG rise: IOB is near peak action when needed (PP TIR,
  sustained-high recovery)
- During BG fall: IOB is past peak action (hypo defence; stale
  buffer rather than fresh driver)

oref1's UAM/dynamic-ISF/autosens stack is one implementation.
Other implementations are possible — the principle, not the
specific algorithm, is the recommendation.

### Why reactive cutting cannot substitute

Loop_AB_ON cuts basal in 96.1% of pre-hypo cells (vs oref1's
91.1%) and sheds IOB at −1.45 U/h pre-event (vs oref1 −0.54).
**It is winning every reactive metric and losing the BG outcome**
(2× severe hypo). The fresh IOB it is reacting to was placed
too late.

This rules out the "more aggressive cuts will fix it" tuning
recommendation. The fix is upstream — earlier predictive delivery,
not deeper cuts.

### Selection-bias hypothesis CLOSED

Combined evidence (eight independent lines):
1. EXP-2942 cross-cohort match (oref0 ≈ Loop_AB_OFF at no-SMB floor)
2. EXP-2943 variance decomposition (η²=0.64 design-dominated)
3. EXP-2944 true-IOB mechanism in sustained-high (iob_delta gap +1.18 U)
4. EXP-2946 IOB-timing in PP (cross-window validation; oref0
   channel-positions shift by window class)
5. EXP-2947 IOB-age framework unifies all three windows
6. EXP-2950 uniform biexponential action-curve (peak 75/DIA 300)
   re-derives the iob_delta gap independent of grid `iob`
   bookkeeping (p=9.5e-21; bg_delta gap 21.8 mg/dL p=1.7e-34)
7. EXP-2953 same uniform curve at hypo descent: `synth_act_entry`
   higher in Loop (p=4e-3); bg_min 4.1 mg/dL deeper (p=7e-25)
8. EXP-2954 GOLD STANDARD within-patient regression: 19/19
   patients negative slope on bg_min ~ synth_act_entry
   (sign test p=1.9e-06); 15/19 individually p<0.05.
   Mechanism is biology, not design-cohort artifact.
9. EXP-2957 action-curve sensitivity sweep: 9/9 combos
   peak{60,75,90}×DIA{240,300,360} confirm oref1 sheds
   faster than Loop_AB_ON during sustained-high (median gap
   −1.10 U; all p<1e-10). Framework is robust to action-curve
   parameter choice — closes natural reviewer objection.
10. EXP-2960 velocity-vs-insulin coupling at PP (forward channel):
    oref1 slope +1.36 U per mg/dL/min vs Loop_AB_ON +0.62 U per
    mg/dL/min (95% CIs non-overlapping). oref1 commits insulin to
    early rising velocity ~2.2× more strongly than Loop AB ON —
    direct forward-response observation of lever (3) at PP. Closes
    "designs differ only in defence" alternative explanation.

The selection-bias hypothesis would need to coincidentally produce
all ten patterns from patient-cohort differences. EXP-2954 in
particular operates entirely WITHIN patients, eliminating cohort
composition as a possible explanation. EXP-2957 closes the parameter-
choice objection. Algorithm mechanism is the parsimonious explanation.

### Window-class scoping refinement (EXP-2955)

Within-patient PP cross-validation (EXP-2955) found single-predictor
18/18 patients negative (p=3.8e-06) BUT multi-factor (controlling for
carbs and bg_entry) only 11/18 (p=0.24). The PP within-patient signal
is dominated by meal context (carbs, starting BG), NOT by pre-meal
IOB age per se.

This refines lever (3) below:
- IOB-AGE-AS-CAUSE is strongest at **hypo** (within-patient validated).
- At **sustained-high**, between-design with strong mechanism support.
- At **PP**, the cleanest framing is WITHIN-window SMB activity (the
  SMB-during-rising-window mechanism), not pre-window IOB age.

### AID-author lever priority order (FINAL)

1. **UAM/glucose-appearance + dynamic-ISF** (PP offence channel)
2. **SMB-as-correction** (sustained-high channel)
3. **Predict-and-fire on rising velocity early** so insulin activity
   exists during the response window — UNIFIED across PP TIR (via
   WITHIN-window SMB activity, EXP-2946), sustained-high recovery
   (via pre-window IOB-age, EXP-2944/2950/2957), and hypo defence
   (via pre-window IOB-age, within-patient validated EXP-2954).
   See Window-class scoping refinement above.
4. Enable autobolus by default for AID-OFF correction loops
5. Basal-cut latency (defence-side; SECONDARY to IOB age)

### Mechanism decomposition (EXP-2958/2959/2960)

Three follow-on experiments dissect *what part* of lever (3)'s
"predict-and-fire" mechanism is observable from data:

- **EXP-2958 — Within-patient SMB-vs-recovery at sustained-high
  (NEGATIVE / reverse-caused).** 12/13 patients show POSITIVE
  within-patient slope of `delta_60 ~ smb_30` — the controller
  delivers more SMB precisely BECAUSE the rise is steeper. Within-
  patient causal inference on controller-emitted variables is
  unidentifiable from observational data; lever (3) at sustained-
  high stands as a *between-design* claim only.
- **EXP-2959 — Per-patient empirical action-curve peak (NULL).**
  Mann-Whitney across designs on best-fit peak ∈ {45,60,75,90,105
  min} all p ≥ 0.62 (oref median 60, Loop median 75 — directionally
  consistent but not significant). RSS objective is essentially flat
  (<1.5% improvement vs canonical 75/300 for nearly all patients).
  The iob_delta gap is **not** explained by per-design insulin-
  pharmacokinetic differences — it is event-emission timing that
  matters. **Strengthens the framework's central claim.**
- **EXP-2960 — Velocity-vs-insulin coupling at PP (CLEAN POSITIVE).**
  Per-design slope of insulin-in-[0,60min] on bg-velocity-in-[0,30min]:
  Loop_AB_OFF +1.01, Loop_AB_ON +0.62, oref0 −0.27, **oref1 +1.36**.
  oref1 vs Loop_AB_ON 95% CIs do not overlap (0.84 vs 1.21). oref1's
  autonomous controller couples insulin to early rising velocity ~2.2×
  more strongly than Loop AB ON. This is the FORWARD-response analogue
  of the IOB-age framework: oref1 ages insulin earlier *because* it
  commits insulin earlier in response to rising velocity.

**Net effect on the framework:** EXP-2959 closes the
"insulin-pharmacokinetics" alternative explanation for the iob_delta
gap. EXP-2960 adds a **tenth independent evidence line** (forward
velocity-coupling). EXP-2958 honestly confines lever (3)'s within-
patient causal claim to the hypo channel only.

### Velocity-coupling robustness sweep (EXP-2961/2962/2963/2964)

A four-experiment batch interrogates the EXP-2960 velocity-coupling
finding for context-generality, single-patient leverage, and
controller-vs-user channel decomposition.

- **EXP-2961 — Velocity-coupling at sustained-high (no meal),
  POSITIVE w/ surprise.** At sustained-high (BG > 200, no carbs prior
  120 min), Loop_AB_ON pooled slope is +2.05 (95% CI [+1.88, +2.23]),
  oref1 +0.98 (+0.81, +1.15), oref0 +0.06 (CI crosses 0), Loop_AB_OFF
  +1.18. **Velocity-coupling persists OUTSIDE meals — confirming it
  is a controller property, not a meal-detection artefact** (eleventh
  independent evidence line). But the ordering FLIPS: Loop_AB_ON >
  oref1 at sustained-high (opposite of PP). oref0's near-zero slope
  here is consistent with its controller channel having no SMB.
- **EXP-2962 — Per-patient velocity-coupling at PP (CLEAN POSITIVE
  but DOWNGRADES EXP-2960).** All 9 oref1 patients individually have
  positive slopes (sign-test p=0.0039), median +0.95. LOO pooled
  slopes range +1.21 to +1.48 — robust. **However**, Mann-Whitney on
  per-patient slopes oref1 vs Loop_AB_ON is p=0.22 (not significant);
  Loop_AB_ON per-patient slopes (median +0.79) sit inside the oref1
  distribution. The pooled-event "2.2×" headline conflates patient-
  count and event-count weighting; per-patient framing reduces this
  to a non-significant trend. **Reframe EXP-2960 as a within-design
  positive-coupling finding, not a between-design contrast.**
- **EXP-2963 — oref0 −0.27 anomaly (RESOLVED: artefact).** Of the 3
  oref0 patients, slopes are {+0.50, +0.04, −0.48}. Removing patient
  `odc-96254963` collapses the pooled slope from −0.27 to −0.027.
  In ALL 3 patients the slope lives in the BOLUS channel
  (max |basal-x slope| = 0.015). **The negative pooled slope was
  one-patient user-bolus reverse-causation, not a controller
  property.** oref0's controller-channel coupling at PP is
  essentially zero — consistent with EXP-2961 sustained-high.
- **EXP-2964 — SMB-vs-basal channel decomposition (MAJOR FRAMEWORK
  UPDATE).** At PP, the SMB-channel velocity-coupling slope is
  **near-identical between Loop_AB_ON (+0.380) and oref1 (+0.361)**
  (95% CIs overlap). The +0.62 vs +1.36 total-slope difference is
  driven primarily by the BOLUS channel (+0.23 vs +1.00) — i.e. USER
  manual-bolus practice, not controller. Basal-excess velocity-
  coupling is small in all designs (max 0.06).

**Net framework update:** Lever (3)'s controller-side action at PP is
quantified by the SMB-channel slope (~+0.37 U per mg/dL/min for both
SMB-equipped designs). Loop_AB_ON and oref1 are quantitatively
similar at this lever; they differ in event-emission timing
(triggering thresholds, frequency caps, IOB-budget heuristics). The
EXP-2960 between-design "2.2×" headline is corrected to: **EXP-2960
mixed controller-channel and user-channel velocity-coupling. The
controller-channel comparison is a near-tie at PP (+0.36 vs +0.38).**

The IOB-age framework as a whole is unaffected by this correction —
it rests on EXP-2944/2950/2954/2957 within-window mechanics and on
EXP-2961's controller-property confirmation outside meals. The
correction sharpens which channel (SMB) carries the controller's
velocity-coupling signal.

### AID-author lever priority order — REVISED (post-EXP-2964)

| Lever | Channel | Controller-attributable effect at PP | Ranking |
|---|---|---|---|
| Auto-bolus / SMB on rising velocity (UAM, AB) | SMB | +0.36–0.38 U per mg/dL/min | **PRIMARY controller lever** |
| Temp-basal velocity modulation | basal-excess | < 0.07 U per mg/dL/min | Marginal at 30-min horizon |
| User announce-meal pre-bolus practice | bolus (user) | +0.23–1.00 U per mg/dL/min | NOT a controller lever — cohort-dependent |

For controller authors: enabling SMB / auto-bolus on a rising-velocity
heuristic is the single dominant code-level lever for forward
velocity-response at PP. Tuning the basal channel alone cannot match
the SMB-channel response in the 30-minute horizon. The Loop AB vs
oref1 UAM heuristic differences do not translate to a measurable
SMB-channel slope difference in this cohort — both deliver ~0.37 U
per mg/dL/min of additional automated insulin.

### Counter-recommendations (what NOT to tune)

- Don't increase basal-cut aggressiveness beyond ~91% as a hypo-
  defence lever. Loop_AB_ON already cuts in 96.1% of cells and
  loses the BG outcome.
- Don't increase total dose magnitude within a design. Within-
  design dose tertile is flat for both PP TIR (EXP-2946) and
  sustained-high recovery (EXP-2944, Loop tertile flat).
- Don't make oref1 dose more like Loop or vice versa. Different
  dose policies are part of integrated bolus-calc + absorption
  + ISF tuning, not isolated knobs.
