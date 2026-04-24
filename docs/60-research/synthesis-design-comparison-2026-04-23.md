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

**Cohort scope caveat (added 2026-04-23, post-EXP-2980 / EXP-2984):**
All oref1-lineage patients in this cohort are **Trio** (iOS).
There are **no `controller='aaps'` patients** because the ingest
pipeline mis-labels AAPS-Android uploads as `controller='openaps'`
(see EXP-2984 / `docs/40-data-pipelines/aaps-ingestion-scoping-2026-04-23.md`).
Therefore the 3 patients labeled "oref0 (legacy)" may already
include AAPS data silently. **Every "oref1" claim in this
synthesis should be read as "Trio (oref1 lineage)";** the
Trio-vs-AAPS platform-isolation question is structurally blocked
by a labeling bug (data-LABELING gap), not a data-collection gap.

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

> **Capstone**: see
> `docs/60-research/CAPSTONE-iob-age-smb-mechanism-2026-04-23.md`
> for the consolidated 34-evidence-line writeup with mechanism
> decomposition, code-path mappings, and honest reversals. The
> capstone supersedes this section's running tally for external
> readers; this section remains the per-batch development log.

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

### Velocity-coupling robustness sweep — extension (EXP-2965/2969/2970/2966)

Four experiments stress-tested the post-EXP-2964 framework: per-patient
validation of the sustained-high finding, per-patient SMB-channel near-tie
at PP, channel-decomposition at sustained-high, and a BG-band sweep.

- **EXP-2969 — per-patient SMB-channel slope at PP** confirms
  EXP-2964 robustly: median Loop_AB_ON +0.390 vs median oref1
  +0.307; **MWU two-sided p = 0.36** (not significant). Per-patient
  near-tie of the controller-channel slope at PP is now evidence-line
  consistent (12th line).
- **EXP-2965 — per-patient sustained-high** finds both designs
  unanimously positive (Loop_AB_ON 5/5, oref1 9/9 sign-test
  p = 0.004), but MWU between designs at the SMB channel is
  **p = 0.149** — directional Loop > oref1 ordering, not per-patient
  significant. Replicates the EXP-2962 pooled-vs-per-patient lesson.
- **EXP-2970 — sustained-high decomposition** uncovers a **mean-dose
  difference**: Loop_AB_ON delivers ~2.06 U SMB on a 60-min window
  at sustained-high entry vs oref1's ~1.26 U (~63% higher). Pooled
  SMB-slope ratio ~2× (Loop +0.78 vs oref1 +0.39, disjoint 95% CIs)
  but per-patient MWU still p = 0.30. Net call: AID authors should
  treat the delta as **trigger-frequency / IOB-ceiling driven**,
  not per-event-magnitude.
- **EXP-2966 — BG-band sweep** is the strongest new evidence:
  in the **no-carb context with N>100k events per cell**, Loop_AB_ON
  SMB slope exceeds oref1 SMB slope at every BG band by 1.5–1.9×
  with **disjoint 95% CIs** in every band. The maximum coupling for
  both designs is in the **70–100 mg/dL band** (just-above-target,
  recovery climb) — the cleanest "sweet spot" for SMB-on-velocity
  triggering identified in the campaign. Caveat: pooled CIs at high
  N inflate significance; per-patient remains the rigorous test.

### Evidence-line tally (post-this-batch)

| # | Line | Source experiment(s) |
|---|---|---|
| 1 | Within-window IOB-age effect | EXP-2944, 2950, 2954 |
| 2 | Cross-window unification | EXP-2957 |
| 3 | UAM/SMB lever (PP, total slope) | EXP-2960 |
| 4 | Sustained-high replication | EXP-2961 |
| 5 | Per-patient correction (PP) | EXP-2962 |
| 6 | oref0 anomaly = artefact | EXP-2963 |
| 7 | SMB-channel near-tie at PP (pooled) | EXP-2964 |
| 8 | Per-patient sustained-high positivity | EXP-2965 |
| 9 | Per-patient SMB-channel near-tie at PP confirmed | EXP-2969 |
| 10 | Sustained-high mean-dose Loop > oref1 | EXP-2970 |
| 11 | BG-band sweet spot 70-100 (no-carb) | EXP-2966 |
| 12 | Loop > oref1 SMB slope all bands (no-carb, pooled, disjoint CI) | EXP-2966 |

Evidence-line count: **12** (up from 11). The IOB-age framework's
core stays unchanged; the SMB-channel lever is now better resolved as:

- **PP context**: per-event magnitude near-equivalent across SMB-equipped designs.
- **No-carb context**: Loop_AB_ON SMB-on-velocity coupling 1.5–1.9× oref1's at pooled level, every band; per-patient MWU still underpowered.
- **Sweet spot for tuning**: 70–100 mg/dL band (just-above-target recovery climb).

### AID-author lever priority order (post-EXP-2966)

| Lever | Channel | Effect | Sweet spot | Ranking |
|---|---|---|---|---|
| SMB / auto-bolus on rising velocity | SMB | +0.36–0.79 U per mg/dL/min | **70–100 mg/dL band, no-carb context** | **PRIMARY** |
| SMB trigger frequency / IOB-ceiling at sustained-high | SMB (mean dose) | Loop ~2.06 vs oref1 ~1.26 U/60min | sustained-high entries | **NEW second-order lever** |
| Temp-basal velocity modulation | basal-excess | <0.12 U per mg/dL/min (max +0.45 in 70-100 Loop_AB_OFF) | recovery from low (Loop_AB_OFF only) | Marginal except as SMB substitute |
| User announce-meal pre-bolus | bolus (user) | +0.23–1.00 U per mg/dL/min | PP + sustained-high (user-driven) | NOT a controller lever |

---

### EXP-2971 / 2972 / 2973 / 2974 / 2975 (post-batch update)

This batch tested the EXP-2966 sweet-spot per-patient, decomposed
the lever, stratified by velocity sign, ran the formal U-shape
test, and tied the data findings to source code.

#### Headlines
- **EXP-2971 (MIXED)** — per-patient sign-test in 70-100 no-carb:
  Loop_AB_ON 5/5 positive (sign p=0.063), oref1 9/9 positive
  (sign p=0.004). MWU between designs p=0.30 — within-design
  directional consistency confirmed; between-design effect size
  not separable per-patient at n=5 vs 9.
- **EXP-2972 (POSITIVE / mechanism shift)** — pooled emission
  decomposition: oref1 fires SMB at **2.06× the rate** of
  Loop_AB_ON (em_rate 0.080 vs 0.039, disjoint CIs), with **44%
  smaller per-event size** (0.169 U vs 0.244 U). **Total per-cell
  SMB is higher for oref1** (0.0135 vs 0.0094 U/cell). Per-patient
  MWU on em_rate p=0.060 (marginal); on mean_emission p=0.80 (null).
  Loop_AB_ON is **bimodal across patients** (4/5 fire SMB <0.22%
  of cells; patient `i` fires 12.4%).
- **EXP-2973 (POSITIVE / mechanism decomposition)** — velocity
  stratification reveals **complementary levers**: Loop_AB_ON
  modulates **per-event MAGNITUDE** with velocity (mean_em rises
  0.19→0.36 U from stable→rising, 1.9× scaling, ~flat em_rate).
  oref1 modulates **EMISSION FREQUENCY** with velocity (em_rate
  rises 0.048→0.097 from falling→rising, 2.0× scaling, ~flat
  mean_em). Both designs back off appropriately on falling
  velocity (slopes drop to +0.04 / −0.08).
- **EXP-2974 (CODE MAPPING)** — source-code lookup tying findings
  to specific dosing-path mechanisms:
  - Loop's `partialDose = units × applicationFactor` with
    `applicationFactor` 0.20-0.80 (GBAF) or 0.4 (constant); no
    inter-cycle SMB gate; emission gated implicitly by
    `bolus_increment` rounding.
  - oref1's `microBolus = min(insulinReq/2, basal × 30/60)` with
    explicit `SMBInterval=3min` and an `enable_smb()` gate that
    requires `enableSMB_always` in no-carb context.
  - Full deep-dive: `docs/10-domain/smb-emission-policy-deep-dive-2026-04-23.md`.
- **EXP-2975 (POSITIVE)** — formal U-shape test confirms positive
  curvature for both designs in no-carb context. Loop_AB_ON
  c=+9.4e-6 (z=+9.2, p≈0), vertex BG=214 mg/dL, sharp U with
  meaningful re-engagement at 260-300 mg/dL. oref1 c=+2.8e-6
  (z=+3.15, p=0.002), vertex BG=347 mg/dL (out of range), nearly
  monotonic-decreasing from 85 to 280 mg/dL.

#### Evidence-line tally (post-batch)

| # | Line | Source experiment(s) |
|---|---|---|
| 13 | Per-patient SMB-slope positivity at sweet spot (both designs) | EXP-2971 |
| 14 | Lever decomposition: oref1 = frequency, Loop = magnitude | EXP-2972, 2973 |
| 15 | Code-path mapping (SMB emission policy) | EXP-2974 (deep-dive) |
| 16 | Formal U-shape (positive curvature) of SMB slope vs BG band | EXP-2975 |

Evidence-line count: **16** (up from 12).

#### Updated AID-author lever priority (post-EXP-2972/2973/2974)

The single sentence that summarizes the campaign now:

> The two SMB-equipped controllers (Loop AB-ON and oref1) achieve
> comparable directional SMB-on-velocity behavior at the 70-100
> mg/dL no-carb sweet spot via **complementary mechanisms**:
> oref1 modulates emission FREQUENCY (gated by `SMBInterval` /
> `enable_smb`); Loop modulates emission MAGNITUDE (gated by
> `partialApplicationFactor` × predicted overshoot). Per-patient
> outcome differences remain within natural variation; the
> design-level signal lives at the pooled / cell-count level.

| Lever | Channel | Mechanism | Code citation | Ranking |
|---|---|---|---|---|
| Cycle-frequency ceiling (`SMBInterval`) | SMB freq | oref1: 3-min minimum; Loop: cycle-only (5 min) | `DetermineBasalSMB.kt:1101`; `LoopDataManager.swift:1818` | **PRIMARY** |
| Enable-gate policy (no-carb regime) | SMB rate | oref1: explicit `enable_smb()`; Loop: implicit `units > rounding` | `DetermineBasalSMB.kt:66`; `DoseMath.swift:101` | **PRIMARY** |
| Per-event multiplier | SMB magnitude | Loop: `partialApplicationFactor` (0.20-0.80); oref1: hard `/2` | `GlucoseBasedApplicationFactorStrategy.swift:14`; `DetermineBasalSMB.kt:1065` | SECONDARY |
| `maxSMBBasalMinutes` cap | SMB ceiling | oref1: `basal × 30/60`; Loop: `maxBolus × factor` | `SMBDefaults.kt`; `LoopDataManager.swift:1840` | TERTIARY |
| Momentum integration into prediction | both | both fold velocity in; differs in where it gates | shared | implicit |

#### Code-path mapping (new sub-section)

For full file:line references, see
`docs/10-domain/smb-emission-policy-deep-dive-2026-04-23.md`.

Key data → code linkages:

| Data finding | Code mechanism |
|---|---|
| oref1 em_rate 2× Loop in 70-100 no-carb (EXP-2972) | `enable_smb()` requires `enableSMB_always` (no-carb path); 8/9 oref1 patients have it on. Loop's implicit gate `units > 0.05U` blocks 4/5 Loop patients. |
| Loop magnitude scaling with velocity (EXP-2973) | `partialDose = units × factor` and `units = (predictedBG − target)/ISF` carries momentum directly. |
| oref1 frequency scaling with velocity (EXP-2973) | `insulinReq` uses `naive_eventualBG`; falling velocity → `naive_eventualBG < target` → cycle skipped. |
| Loop_AB_ON bimodality across patients (EXP-2972) | Sensitivity to `automaticDosingStrategy`, `glucoseBasedApplicationFactorEnabled`, target-range, `maxBolus`. |
| Loop's sharper U-shape (EXP-2975) | `units` scales linearly in BG, so high-BG re-engagement is mechanical; oref1's `min(insulinReq/2, maxBolus)` cap binds at high BG. |

---

## Addendum (Apr-23 eleventh batch): PP context, audit, outcome linkage, platform isolation, Loop factor calibration

### Batch experiments (EXP-2976 through EXP-2980)

- **EXP-2976 (NEGATIVE / NULL)** — PP-context U-shape preserved, did
  not flip. Loop_AB_ON `c=+8.7e-6` (z=+5.0), vertex 236 mg/dL;
  oref1 `c=+3.5e-6` (z=+2.83), vertex 322. Same sign and similar
  magnitude as no-carb (EXP-2975). Conclusion: U-shape is a
  **persistent controller signature**, not a no-carb artifact.
  Lever 3 (meal-state shaping) should preserve U-shape design.
- **EXP-2978 (NEGATIVE)** — per-patient oref1 sustained-high em_rate
  audit: all 9 Trio patients fire SMB at sustained-high BG
  (range 0.11 – 0.34, no outlier ≪ median). The earlier
  EXP-2972 anomaly (em_rate 0.008) was **at the 70-100 sweet spot,
  not at sustained-high** — re-attribute to ISF/profile, not to
  `enableSMB_always` gating.
- **EXP-2979 (MIXED-DIRECTIONAL POSITIVE — outcome linkage)** — at
  rising-stratum 70-100 cells, mechanism difference is mirrored
  in pooled outcomes:

  | Design | smb med | TTT med | overshoot 60min | hypo 60min |
  |--------|---------|---------|-----------------|------------|
  | Loop_AB_ON | 0.40 U | 10 min | **10.7%** | 12.7% |
  | oref1 (Trio) | 0.15 U | 15 min | 3.5% | 18.4% |

  Loop's magnitude lever returns to target ~5 min faster but with
  ~3× higher overshoot. Critical caveat: Loop pooled is
  **single-patient-dominated** (`i` = 361 of 363 events; c/d/e/g
  have 0–1 events each in this stratum). Per-patient MWU not
  feasible (n_loop=1 after threshold). The DIRECTION matches
  mechanism prediction; external validity to other Loop patients
  is unverified.
- **EXP-2980 (MERGED-LABEL / NULL by data availability)** — all 9
  oref1-lineage patients in cohort are controller=Trio. No
  AAPS-on-Android patients available. Re-label all "oref1"
  findings (EXP-2972/2973/2975/2978/2979) as **"Trio (oref1
  lineage)"** for precision. Trio-vs-AAPS platform isolation
  requires future cohort expansion.
- **EXP-2977 (INCONCLUSIVE / methodological)** — implicit
  `partialApplicationFactor` per Loop patient: all 5 patients
  show negative `est_factor`-vs-BG slope (opposite of GBAF's
  expected positive slide). Most likely explanation:
  `proxy_insulinReq` over-estimates at high BG because it
  doesn't account for IOB / RC, biasing the estimator. Cannot
  separate Constant vs GBAF strategy from observational data
  without per-patient ISF (oref1-only column). IQR of est_factor
  (0.11 – 0.29) is wider than constant-factor would predict, so
  some sliding/context-dependence is operating, but the source
  cannot be pinned without a profile-JSON audit.

### Evidence-line tally (post-batch)

| # | Line | Source |
|---|---|---|
| 17 | U-shape persistent across meal context (no-carb + PP both U) | EXP-2976 |
| 18 | oref1 sustained-high SMB universally enabled (no patient with gate-off pattern) | EXP-2978 |
| 19 | Mechanism-to-outcome linkage: magnitude → faster+overshoot, frequency → slower+tighter (directional, single-patient Loop arm) | EXP-2979 |
| 20 | Platform-isolation gap formally documented (no AAPS in cohort) | EXP-2980 |

Evidence-line count: **20** (up from 16). Lines 17 and 19 are
the new high-value additions; 18 is a clean negative; 20 is a
documented limitation. EXP-2977 does NOT add an evidence line
(inconclusive).

### Updated AID-author lever priority (post-EXP-2979)

EXP-2979 introduces a **per-mechanism guard-rail** consideration
without rewriting the lever order:

| Lever | Channel | Mechanism | Guard-rail (NEW) | Ranking |
|---|---|---|---|---|
| Cycle-frequency ceiling | SMB freq | oref1 3-min `SMBInterval` | **IOB-stacking governor** at sustained correction (oref1 patients show 0–50% hypo scatter) | PRIMARY |
| Enable-gate policy | SMB rate | oref1 `enable_smb()`; Loop implicit | (unchanged) | PRIMARY |
| Per-event multiplier | SMB magnitude | Loop `partialApplicationFactor` × overshoot | **Overshoot governor** (post-SMB cool-down OR predict-aware sizing cap when projected post-SMB BG > 180) | SECONDARY → upgraded |
| `maxSMBBasalMinutes` cap | SMB ceiling | oref1 30/60 cap | (unchanged) | TERTIARY |
| Per-mechanism guard-rails | NEW: mechanism-specific safety, not identical for both designs | EXP-2979 directional outcome difference | (this row) | NEW SECONDARY |

### Counter-recommendation (NEW)

Generic "add safety guard-rails" advice is INCORRECT for both
designs. Magnitude-lever and frequency-lever AIDs need **different**
safety guard-rails — the failure modes differ (overshoot for
magnitude, IOB-stacking hypo for frequency). EXP-2979 is
directional-only at single Loop patient n, but the asymmetry
matches mechanism prediction; future work should validate at
multi-patient Loop_AB_ON n.

### Re-labeling note

All prior "oref1" claims in this synthesis are now formally
"Trio (oref1 lineage)". The algorithmic claims likely transfer
to AAPS but **iOS / Android scheduler differences** (BLE timing,
Doze, BackgroundTasks vs AlarmManager) are an unmeasured gap.

## Addendum (Apr-23 twelfth batch): patient-i representativeness, overshoot governor, IOB-stacking governor, AAPS scoping, cross-band overshoot

### Batch experiments (EXP-2981 through EXP-2985)

- **EXP-2981 (STRONG OUTLIER finding, downgrade pressure on EXP-2979)**
  — Patient `i` is a Tukey-IQR outlier on **8 of 17** baseline /
  event-count metrics: frac_in_70_100 (19.4% vs 13.1% peers),
  frac_below_70 (10.7% vs 2.5%), n_smb_in_70_100 (1115 vs ~1.5),
  smb_dose_mean (0.45U vs 0.25U). Critically, peers c/d/e/g
  **descend into 70-100 frequently** (n_5min in 70-100 ranges
  4.5k–7.8k) but **almost never fire SMB there** (0–18 SMBs
  vs `i`'s 1115). This is a **policy difference, not a
  use-pattern difference** — likely a temp-target / GBAF /
  override gating that suppresses SMB at low BG for c/d/e/g
  but not for `i`.
- **EXP-2982 (NEGATIVE)** — Linear counterfactual cap sweep
  (PAF ∈ {1.0, 0.8, 0.6, 0.4, 0.2}) for patient `i`'s 361
  events: projected overshoot rate **does not decrease** as cap
  shrinks (10.5% → 12.5%). The rise in 70-100 is **endogenous**
  (carb residual / dawn / counter-reg); the SMB at this band is
  small relative to the rise and ends up above 180 regardless.
  PAF reduction is **not the lever** to fix this overshoot;
  earlier dosing or pre-emptive temp basal would be more
  promising candidates.
- **EXP-2983 (NULL on stacking-ceiling)** — Across 8 Trio patients
  with ≥20 no-carb SMB events, Spearman ρ(mean_IOB, hypo_rate)
  = **−0.333** (p=0.38) and ρ(p75_IOB, hypo_rate) = −0.469
  (p=0.20). Within-patient IOB-tertile analysis: hypo rate is
  flat or **decreasing** with IOB. Pooled across-Trio bands:
  hypo 4.0% at IOB <0.5 → 1.3% at IOB 3-5. **No empirical IOB
  ceiling** above which hypo discontinuously jumps. Existing
  Trio caps (`maxIOB`, `enableSMB_always: false`) appear to
  prevent the dangerous regime; the hypo-prevention lever is
  **not** "lower maxIOB" but suppression at low BG.
- **EXP-2984 (POSITIVE / ACTIONABLE — pipeline diagnosis)** — The
  AAPS-Android gap surfaced in EXP-2980 is a **data-LABELING
  bug, not a data-collection failure**. AAPS uploads ARE
  ingested (via `tools/ns2parquet/odc_loader.py`), but every
  synthesized record stamps `device='openaps://AndroidAPS'`,
  which `_detect_controller()` matches first as openaps. A
  2-line fix (reorder branches; rename device prefix) plus a
  one-time relabel pass would restore the AAPS arm. The 3
  patients currently labeled "oref0 (legacy)" likely contain
  mis-labeled AAPS data. Detail: `docs/40-data-pipelines/aaps-ingestion-scoping-2026-04-23.md`.
- **EXP-2985 (POSITIVE — `i` is band-representative)** — Per-band
  overshoot rate for Loop_AB_ON: at 100-140, 140-180, 180-220,
  220+ patient `i` is **inside the cohort range** (in fact `c`
  shows higher overshoot at 100-140 (32.5%) and 140-180
  (53.6%)). At 70-100 only `i` fires meaningfully (1097 events
  vs 0–12 for peers); his 7.3% overshoot there is plausible.
  EXP-2979's directional claim STANDS but its scope is
  appropriately narrowed: "the only Loop_AB_ON configuration
  that fires SMB at low BG shows 10.7% overshoot vs 3.5% Trio
  pooled."

### Evidence-line tally (post-batch)

| # | Line | Source |
|---|---|---|
| 21 | Loop_AB_ON SMB-at-low-BG behavior is policy-bimodal: 4 of 5 patients suppress, 1 fires aggressively | EXP-2981 |
| 22 | In rising-70-100 endogenous-rise stratum, PAF reduction does not reduce overshoot — wrong lever | EXP-2982 |
| 23 | No IOB-ceiling for Trio hypo within observed range; existing Trio caps already gate the danger zone | EXP-2983 |
| 24 | Trio-vs-AAPS gap is labeling not collection — fixable in pipeline | EXP-2984 |
| 25 | EXP-2979's directional Loop-overshoot claim is scope-narrowed but stands; `i` is overshoot-representative at all bands where peers fire | EXP-2985 |

Evidence-line count: **25** (up from 20). Lines 21, 22, 24 are
high-value structural findings; 23 is a clean negative; 25
re-confirms / scope-narrows the prior directional claim.

### Updated re-labeling and counter-recommendations

- **EXP-2979 re-labeled**: "Loop magnitude lever overshoot 10.7%"
  → "**single Loop_AB_ON configuration that does not gate SMB
  at low BG** shows 10.7% projected overshoot at rising 70-100;
  4 of 5 cohort Loop patients gate this band off and so the
  population claim cannot be tested in this dataset." Direction
  still matches mechanism prediction.
- **PAF / `partialApplicationFactor` lever**: EXP-2982 contradicts
  the intuitive expectation that smaller dose → less overshoot
  in this stratum. Listed lever order in the eleventh-batch
  addendum should be read with this caveat: PAF reduction is a
  **post-prediction** safety control; it does not address
  endogenous-rise overshoot, only insulin-stacking overshoot.
- **`maxIOB` lever**: EXP-2983 finds no stacking-ceiling effect
  in observed Trio data; "raise/lower maxIOB" is therefore not
  a high-value lever for hypo prevention in this cohort.

### Cohort scope caveat (re-iterated)

The synthesis "Cohort scope caveat" near the top of this
document was added in this batch (post-EXP-2980 / EXP-2984).
All "oref1" findings should be read as "Trio (oref1 lineage)"
until the AAPS labeling fix is applied and EXP-2980 can be
re-run with a separated AAPS arm.

---

## Addendum (Apr-23 thirteenth batch): AAPS labeling fix applied, peer-suppression mechanism, earlier-dosing test

### Batch experiments (EXP-2986 through EXP-2988)

#### Headlines

- **EXP-2986 — STRUCTURAL FIX APPLIED (POSITIVE)**: AAPS-labeling
  bug closed. Two code fixes + one data-relabel script. Cohort
  controller distribution corrected from `OpenAPS=3 / Trio=9 /
  Loop=7` (mis-labeled) to `AAPS=3 / Trio=9 / Loop=7` (platform-
  correct). **Lineage NOT changed**: post-fix inspection of the 3
  ODC patients shows `eventual_bg` populated but `algorithm_isf`,
  `algorithm_cr`, `algorithm_tdd`, `insulin_activity`, `bolus_iob`
  ALL zero non-null AND zero `bolus_smb` cells across the entire
  grid. These patients run **AAPS-platform with oref0-algorithm**
  (SMB/UAM/dynamic-ISF disabled or pre-oref1 AAPS version), so the
  algorithm-correct lineage label is `oref0 (legacy)`.
  Critically: this means the cohort has **zero AAPS-oref1**
  patients, so EXP-2989 platform-isolation experiments (Trio-vs-
  AAPS within oref1) **cannot yet be performed**. Future ODC /
  AAPS-NS additions are required.
- **EXP-2987 — NULL/MIXED**: None of the four hypothesized levers
  (override, recent-carbs, IOB-cap, IOB-threshold) cleanly
  explains the patient-i-vs-peer asymmetry at 70-100. Peers c/d/g
  suppress >99% of *eligible* cells (no override, no recent carbs,
  IOB below patient-95th-pct), patient e suppresses 99.98%, but
  patient i still fires in 13% of *eligible* cells. Patient i has
  HIGHER override fraction (22% vs peer-mean 7%) yet still fires
  more often, meaning override is not the suppressing lever for
  peers. The asymmetric-lever ranking puts `iob_p95` first
  (i=9.95 vs peer-mean 7.31 U) — consistent with patient i
  tolerating a larger IOB cap setting in Loop, but the magnitude
  is not enough to fully explain the 130× fire-rate gap. The
  remaining lever space is patient-specific Loop settings
  (`recommendation_threshold`, glucose-target range, AB-mode
  dose-fraction) not directly observable in the grid.
- **EXP-2988 — NEGATIVE**: The earlier-dosing hypothesis is
  REJECTED. Patient i fires MORE in the 100-140 ascent leading
  into 70-100 entries (56.0%) than peers c/d/e/g (mean 32.1%),
  AND fires more at 70-100 itself. Peers do NOT pre-empt the
  rise; they simply fire less at every band. Combined with
  EXP-2987, this confirms patient-i is a uniformly more-aggressive
  policy across all glucose bands, not a "fires-late vs fires-
  early" temporal-strategy difference.

#### Source-of-truth fixes (commit-traceable)

| File | Change | EXP |
|---|---|---|
| `tools/ns2parquet/normalize.py:87-102` | Reorder `_detect_controller()` branches: test `'aaps'`/`'androidaps'` BEFORE `'openaps'` so AAPS device strings (`openaps://AndroidAPS`) classify as `aaps` not `openaps` | EXP-2986 |
| `tools/cgmencode/exp_state_clustering_2810.py:73-83` | Map `pid.startswith('odc-')` → `'AAPS'` (was `'OpenAPS'`); separates platform from algorithm | EXP-2986 |
| `tools/cgmencode/exp_phenotype_synthesis_2886.py:41-55` | Add separate AAPS branch in `lineage()`; defaults to `'oref0 (legacy)'` for current cohort but documents per-patient override condition for oref1-mode AAPS | EXP-2986 |
| `tools/ns2parquet/exp_2986_relabel_aaps.py` | Idempotent relabel of derived parquets (controller column only) to avoid full pipeline re-run | EXP-2986 |

### Evidence-line tally (post-batch)

| # | Line | Source |
|---|---|---|
| 26 | The "OpenAPS / oref0 (legacy)" arm in this cohort is actually AAPS-platform running oref0-algorithm; platform and algorithm must be tracked separately. There are zero AAPS-oref1 patients in the current cohort | EXP-2986 |
| 27 | Patient-i SMB asymmetry at 70-100 is not explained by override/recent-carbs/IOB-cap/IOB-threshold — patient-specific Loop settings (recommendation_threshold, AB-mode dose fraction) are the remaining hypothesis space | EXP-2987 |
| 28 | Patient-i is uniformly more aggressive across all glucose bands (≥100-140 ascent AND 70-100 band); peers do NOT pre-empt by dosing the rise | EXP-2988 |

Evidence-line count: **28** (up from 25). Line 26 is the highest-
value structural correction of the batch — it forces a re-read of
ALL prior "oref0 vs oref1" claims in this synthesis: those
comparisons are AAPS-oref0 (n=3) vs Trio-oref1 (n=9), NOT
upstream-oref0 vs downstream-oref1.

### Updated re-labeling

- **All prior "oref0 (legacy)" findings**: re-label as "AAPS-
  platform / oref0-algorithm (n=3 ODC patients)". The platform
  is AAPS, not historical OpenAPS-on-Edison. Behavioral
  conclusions (no SMB, simpler IOB profile) remain valid because
  algorithm = oref0; but cross-platform comparisons (e.g., basal
  scheduler granularity, profile-sync cadence) cannot be
  attributed to "OpenAPS reference design" — they are AAPS-
  Android implementation properties.
- **All prior "oref1 (modern)" findings**: re-label as "Trio-
  iOS / oref1-algorithm (n=9)". No AAPS-oref1 patients exist in
  this cohort, so the Trio-vs-AAPS platform isolation EXP-2980
  proposed remains pending future data.

### Updated AID-author lever priority (post-EXP-2987/2988)

For the patient-i overshoot phenotype (EXP-2979/2985), the lever
priority must be revised — the previously-guessed PAF lever is
ruled out (EXP-2982), and now the recent-carbs/IOB-cap/override
levers are also ruled out (EXP-2987). Remaining patient-specific
levers (highest priority first):

1. **Loop `recommendation_threshold` / target-range floor** — the
   gate that keeps peers from dosing in 70-100 must be configured
   higher in peers than in patient i. AID authors should expose
   this gate clearly in UI and warn when a low recommendation
   threshold is set in combination with AB-ON.
2. **AB-mode dose fraction (`partialApplicationFactor`)** — even
   if PAF doesn't change overshoot in the rising-70-100 endogenous
   stratum (EXP-2982), it directly scales fire-rate in 100-140
   ascent. Patient i's higher pre-entry fire-rate (56% vs 32%)
   is consistent with a higher PAF setting.
3. **Per-patient maxIOB** — patient i's iob_p95 = 9.95 U vs peer-
   mean 7.31 U. AID authors should present a "policy
   conservatism" summary at setup combining maxIOB + PAF +
   recommendation_threshold so the user understands the joint
   aggressiveness.

### Counter-recommendation (NEW)

Do NOT build a single "Loop AB-ON aggressiveness" knob. The
patient-i-vs-peers split shows that aggressiveness is multi-
dimensional (cap, gate, fraction) and patients adopt different
combinations. A single knob would force a particular combination
on all users.


## Addendum (Apr-23 fourteenth batch): Loop SMB-gating code mapping, policy-conservatism dial, algorithm_mode column, intra-design heterogeneity

### EXP-2990 — Loop SMB-gating deep dive (POSITIVE; HIGH AID-author signal)

The >99% peer-suppression of SMB at 70-100 mg/dL among Loop_AB_ON
patients c, d, e, g (ruled out of behavioural levers in EXP-2987)
maps to a single dominant code gate:

* **Gate G4** — `externals/LoopAlgorithm/Sources/LoopAlgorithm/LoopAlgorithm.swift:419-423`:
  if `correction == .aboveRange` AND predicted minimum < target lower
  bound, then `deliveryMax = 0` ⇒ SMB suppressed.

A secondary gate **G1** — `externals/LoopAlgorithm/.../DoseMath.swift:207-210`:
short-circuits to `.suspend` if any predicted value < `suspendThreshold`.

Five-gate enumeration plus IOB-headroom amplifier in
`docs/10-domain/loop-smb-gating-deep-dive-2026-04-23.md`. Patient i's
break-out from peer-suppression is now narrowed to the
**(suspendThreshold, correctionRange.lowerBound, maxBolus)**
configuration triple — none individually observable in the grid.

This **promotes** the `recommendation_threshold / target-range floor`
lever from "remaining hypothesis" (synthesis §13) to **rank-1 priority**
in AID-author user-facing documentation.

### EXP-2991 — Policy-conservatism score (MIXED)

A four-proxy conservatism score (`iob_p95`, `bolus_smb_p95`,
`suppress_70_100_eligible`, `basal_frac_of_tdd`) cleanly orders the
five Loop_AB_ON peers (d > c > g > e > i) but does **not** correlate
with overshoot rate (Pearson r = +0.013). The score is internally
consistent; the dial-as-overshoot-predictor framing is rejected.

### EXP-2992 — `algorithm_mode` column added (POSITIVE; SCHEMA)

Three per-patient summary parquets now carry an `algorithm_mode`
column derived from `(controller, lineage, ∃ bolus_smb > 0)`:

```
Trio-oref1 : 9   Loop-AB-ON : 5   AAPS-oref0 : 3
Loop-AB-OFF: 2   unknown    : 5
```

**AAPS-oref1 confirmed as zero-patient gap** in this cohort. Future
experiments SHOULD use `algorithm_mode` as the primary stratification
key. See `docs/40-data-pipelines/cohort-algorithm-mode-2026-04-23.md`.

### EXP-2993 — Intra-design heterogeneity within Loop_AB_ON (POSITIVE; HIGH AID-author signal)

Stratifying the five Loop_AB_ON peers by conservatism tertile rejects
the trade-off hypothesis decisively:

| Tertile | overshoot | TTT_median (min) | TAR_frac |
|---------|-----------|------------------|----------|
| aggressive   (i, e) | 0.255 | 67.5 | 0.278 |
| mid          (g)    | 0.210 | 50.0 | 0.191 |
| conservative (c, d) | 0.275 | 53.8 | 0.227 |

Spearman ρ(conservatism, TTT_median) = **−0.82** —
**aggressive Loop_AB_ON has *longer* recovery times, not shorter.**
Conservative Loop_AB_ON dominates aggressive on every outcome axis;
the "sweet spot" is patient g (mid tertile).

**AID-author finding (NEW):** Do NOT market the aggressive end of
the Loop_AB_ON dial as a "faster recovery" mode — in this cohort it
delivers *slower* recovery AND comparable-or-worse overshoot. Surface
the four-proxy conservatism score in user-facing diagnostics.

### Updated lever-priority order (replaces synthesis §13's earlier list)

1. **Loop `correctionRange.lowerBound` (and `suspendThreshold`)** —
   identified as Gate G4 (and G1) in EXP-2990; configurable knobs
   that drive the >99% peer-suppression pattern. **Highest priority
   for user-facing documentation and Insights surfacing.**
2. **`maxBolus` (which sets the IOB-headroom cap as `maxBolus * 2`)**
   — secondary gate that amplifies G4 suppression at high IOB.
3. **AB-mode dose fraction (`partialApplicationFactor` / GBAF)** —
   attenuates per-cycle dose; combined with pump rounding can
   convert near-zero corrections to literal zeros.

### Counter-recommendation reinforced

The within-Loop_AB_ON results (EXP-2993) confirm the synthesis §13
counter-recommendation: a single "aggressiveness" knob would force
patients toward the strictly-worse end of the dial. Multi-axis
visibility (the EXP-2991 score's four components) is the responsible
UX choice.


## Addendum (Apr-23 fifteenth batch / capstone): patient-g sweet-spot reproducibility, phenotype × algorithm_mode confounding test

### EXP-2994 — Patient `g` sweet-spot vignette (POSITIVE)

EXP-2993 flagged patient `g` (mid-conservatism Loop_AB_ON) as the
within-design sweet spot. EXP-2994 confirms reproducibility and
identifies the tunable settings signature.

- **Reproducibility**: 27-week partition, TIR mean 0.667 (std 0.092,
  CV 0.138); overshoot mean 0.213 (std 0.060). Stable, not a lucky
  window.
- **Distinguishing settings axes vs Loop_AB_ON peer mean**:
  `bolus_smb_p95 = 0.55 U` (peer 0.95, −1.0 SD) and
  `basal_frac_of_tdd = 0.060` (peer 0.258, −1.9 SD). Both are
  configurable pump axes, not patient-physiology proxies.
- **Verdict**: tunable target rather than idiosyncratic. AID-author
  preset candidate: small SMB cap + low scheduled-basal share,
  paired with a deployment-risk warning about Loop dependency.

### EXP-2995 — Phenotype × algorithm_mode re-stratification (MIXED)

Re-stratify EXP-2886's three orthogonal phenotype axes by EXP-2992's
`algorithm_mode` column.

- Cramér's V (archetype × mode) = **0.564** (moderate); V (lineage ×
  mode) = 0.975 (sanity).
- η² per continuous axis vs `algorithm_mode`:
  - `stack_score` η² = **0.044** → CROSS-CUTS (genuine patient
    heterogeneity).
  - `braking_ratio` η² = **0.650** → ALIGNS (algorithm property).
  - `counter_reg_intercept` η² = 0.225 → modest alignment.
  - `hidden_leverage` η² = 0.091 → CROSS-CUTS.
- Within-mode std / overall std for `braking_ratio` is 0.10–0.32
  (very low) confirming braking ratio is essentially an algorithm
  feature.
- 6/6 `algorithm_dependent` archetype patients are on Loop-AB-ON or
  Trio-oref1 (SMB-emitting designs); 0/3 on AAPS-oref0 (no SMB →
  no algorithm to depend on).

**Implication**: EXP-2886 archetype labels mix algorithm-driven and
patient-driven features. Per-patient audition logic should preserve
`stack_score` / `hidden_leverage` (genuine patient signals) but
re-read `braking_ratio` as an algorithm fingerprint.

### Evidence-line tally (post-capstone)

| # | Line | Source |
|---|---|---|
| 33 | Patient `g` sweet-spot is reproducible across 27 weeks (TIR CV 0.14); distinguishing settings signature is observable on tunable pump axes | EXP-2994 |
| 34 | EXP-2886 phenotype clusters partially align with `algorithm_mode` (V 0.56). `braking_ratio` mostly algorithm-driven (η² 0.65); `stack_score` and `hidden_leverage` cross-cut mode (η² 0.04, 0.09); `counter_reg_intercept` weakly aligns (η² 0.22) | EXP-2995 |

Evidence-line count: **34** (up from 32 prior to capstone batch).
The framework's central claims are unchanged; the capstone
consolidates them with code-path mappings and honest reversals
in `docs/60-research/CAPSTONE-iob-age-smb-mechanism-2026-04-23.md`.
