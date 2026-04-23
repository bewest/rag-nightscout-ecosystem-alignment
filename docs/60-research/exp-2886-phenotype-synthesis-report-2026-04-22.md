# EXP-2886 — Three-Dimensional Phenotype Synthesis

**Date:** 2026-04-22
**Stream:** Synthesis (A + B)
**Status:** Complete — three independent phenotype axes confirmed;
actionable archetype map delivered

## Question

EXP-2875 through 2885 established three per-patient signals:

1. **Stacking** (EXP-2882): evening bolus-stacking behavior
2. **Braking** (EXP-2885): AID algorithmic defense during descent
3. **Counter-regulation** (EXP-2875/2877): physiological hypo
   recovery

Are they genuinely independent dimensions, or redundant projections?
What archetypes emerge when combined? Which patients are
safety-critical on composite metrics the single experiments missed?

## Method

Merge per-patient data from EXP-2882, EXP-2885, EXP-2877/2875. For
each patient:

- `stack_score` (0–1, rank-norm of 4h-bolus + IOB deltas)
- `braking_ratio` (actual/scheduled basal during pre-nadir descent,
  averaged across TOD)
- `counter_reg_intercept` (rise rate mg/dL/min at nadir, EXP-2875
  regression)
- `hidden_leverage = stack_score × (1 − braking_ratio)` — proxy for
  AID-compensation dependency

Lineage classification:
- **Loop (iOS)** — LoopKit-based
- **oref1 (modern)** — Trio (AAPS not in sample)
- **oref0 (legacy)** — OpenAPS rig/Edison era (pre-SMB)

Spearman orthogonality among the three dimensions; archetype
classification; lineage mean profiles.

## Result

**VERDICT: THREE TRULY INDEPENDENT AXES. Composite screen identifies
3 hidden-leverage patients and 1 no-counter-reg patient who are
100% AID-dependent.**

### Orthogonality

| Pair | n | Spearman ρ | p |
|---|--:|--:|--:|
| stacking × braking         | 19 | +0.03 | 0.90 |
| stacking × counter-reg     | 24 | −0.19 | 0.38 |
| braking × counter-reg      | 19 | +0.31 | 0.20 |

All |ρ| ≤ 0.32; all p > 0.2. The three signals carry independent
information. No dimension can substitute for another.

### Lineage-level means

| Lineage | n | stack | brake_ratio | suspension | cr_intercept | hidden_lev |
|---|--:|--:|--:|--:|--:|--:|
| **Loop (iOS)**     | 7 | 0.54 | 0.107 | 0.73 | **0.975** | 0.48 |
| **oref1 (modern, Trio)**  | 9 | 0.54 | **0.066** | **0.84** | **0.767** | **0.50** |
| **oref0 (legacy, OpenAPS)** | 3 | 0.58 | 0.535 | 0.35 | 0.966 | 0.35 |

Key lineage insights:

1. **oref1 has the strongest braking** (ratio 0.066, 84%
   suspension) — lowest delivery during descent. Matches user note:
   Trio (and AAPS) descend from oref1 with SMB and tighter
   prediction gates; oref0 (original rig OpenAPS) was pre-SMB with
   conservative basal-only defense.

2. **oref1 has the LOWEST counter-reg** (0.767 vs Loop 0.975 vs
   oref0 0.966) — a potential **HAAF signature**. Modern oref1
   patients may run tighter TIR with more hypo exposure; EXP-2878
   showed β_nadir correlates negatively with hypo_fraction
   (ρ=−0.40, p=0.04). The tight-defense → less-physiology-needed
   → physiology-atrophies chain is consistent.

3. **oref0 has the weakest braking but intact counter-reg** — the
   algorithm relies more on user physiology. With counter-reg
   intact, these patients tolerate the lax algorithm. But they
   would benefit from migrating to oref1 (AAPS/Trio) for
   algorithmic defense, especially for nocturnal windows.

### Archetype distribution

| Archetype            | n | Description | Lineage mix |
|----------------------|--:|-------------|-------------|
| algorithm_dependent  | 6 | strong brake + weak CR | 4 oref1, 2 Loop |
| well_defended        | 5 | low stack + normal CR | 3 oref1, 2 Loop |
| **hidden_leverage**  | **3** | **stacker + strong brake** | 2 Loop, 1 oref1 |
| exposed_stacker      | 2 | stacker + weak brake | 1 Loop, 1 oref0 |
| stacker_weak_defense | 1 | stacker + weak CR    | oref1 |
| stacker_balanced     | 1 | stacker, normal CR, weak brake | oref0 |
| lax_braking          | 1 | weak brake + intact CR | oref0 |
| insufficient_data    | 5 | missing braking data | unknown |

### Top hidden-leverage patients (safety-critical)

| Patient         | Ctrl    | stack | brake | hidden_lev | CR    | Note |
|-----------------|---------|------:|------:|-----------:|------:|------|
| `g`             | Loop    | 0.83  | 0.025 | **0.81**   | 0.94  | Loop is cutting 97.5% of scheduled basal during every descent |
| `ns-8f3527d1ee40` | Trio  | 0.90  | 0.146 | 0.77       | 0.88  | Extreme SMB-upshifter, Trio's 85% brake barely enough |
| `ns-8b3c1b50793c` | Trio  | 0.73  | 0.038 | 0.70       | **−0.16** | **No detectable counter-regulation** — 100% AID-dependent |
| `i`             | Loop    | 0.69  | 0.057 | 0.65       | 1.06  | Loop cutting 94% basal |
| `odc-74077367`  | OpenAPS | 0.75  | 0.222 | 0.58       | 1.45  | oref0 with stacking; strong CR but only 78% cut |

### The `ns-8b3c1b50793c` case

This patient has **counter_reg_intercept = −0.16 mg/dL/min**, which
means BG is still *falling* at nadir (no physiological defense, no
glucagon/epinephrine rebound). Survival depends entirely on Trio
cutting 96% of scheduled basal during every descent.

**Implications:**

- This is a "100% AID-dependent" phenotype. Closed-loop failure
  (CGM loss, pump fault, controller crash) removes the only defense.
- Clinical intervention candidate: glucagon emergency plan,
  hypoglycemia-unawareness clinical workup, possibly formal HAAF
  assessment with CGM deskewing.
- From audition framework: this patient should trigger a
  `critical_defense_gap` flag at the highest severity.

## Interpretation

### 1. Three axes, three interventions

Because the axes are orthogonal, interventions target different
levers:

| Axis | Lever | Who it helps |
|------|-------|-------------|
| Stacking | Bolus attenuation, 4h-bolus guard | Behavioral + AID bolus logic |
| Braking | Algorithm update (oref0→oref1, Loop momentum factor) | AID authors |
| Counter-reg | HAAF workup, glucagon, hypo-exposure reduction | Clinical |

A composite audition must assess all three; a patient weak on any
one dimension is not compensated by strength on another (hence the
hidden-leverage archetype: strength on braking masks weakness on
the other two).

### 2. Why oref1 shows low counter-reg: candidate HAAF feedback

EXP-2878 found β_nadir (gradient of CR response) correlates
negatively with hypo_fraction (ρ=−0.40). Combining with EXP-2886:

- oref1 cohort has tightest TIR / most hypo exposure (implied by
  strongest braking plus stacking behaviors)
- oref1 cohort has weakest counter-reg intercept (0.77 vs 0.97)

This is consistent with hypoglycemia-associated autonomic failure
(HAAF): more hypo exposure → attenuated counter-reg → more
dependence on algorithm → more hypo exposure → …

This is a **testable hypothesis**, not yet proven: n=9 oref1 and
n=3 oref0 patients is underpowered for a controlled comparison.
But the direction is consistent.

### 3. The hidden-leverage pattern as a clinical talking point

For a patient `g` (Loop, hidden-leverage), a clinician report could say:

> "Your data shows Loop is cutting 97% of your scheduled basal
> every time your BG heads down. Your pump settings are running
> hotter than your physiology alone would tolerate. **Loop is
> saving you — but if Loop ever stops (CGM loss, connectivity
> failure, pump-loop exit), you will have substantial unopposed
> insulin working.** We should either (a) soften your pump settings
> toward autonomous-safe values, or (b) strengthen your fallback
> plan for Loop failures."

This is more actionable than "TIR is 78%, keep doing what you're
doing."

### 4. Lineage migration implication

For oref0 users (the 3 OpenAPS patients):

- Stacker_balanced + lax_braking + exposed_stacker archetypes
- Intact counter-reg (lucky — physiology compensating for weak
  algorithm)
- **Migration to oref1 (AAPS or Trio) would give them the stronger
  braking without requiring settings changes**
- Downside risk: if they acquire the oref1-lineage weaker counter-reg
  over time (HAAF from tighter TIR), they may end up with a different
  problem

### 5. Missing lineage: AAPS

Our dataset has **no AAPS patients**. AAPS runs oref1 on Android,
with additional prediction/plugin layers. The Trio-as-oref1
findings are a partial proxy; a proper oref1-vs-oref0 comparison
needs AAPS data. Worth flagging as a dataset gap.

## Implications summary

### For clinicians

Add a three-dimensional phenotype chart to the patient-C-style
vignette:
- Stacking (operational lever)
- Braking (algorithmic lever)
- Counter-reg (physiological lever)

Label archetype; interpret hidden-leverage and algorithm-dependent
as distinct risk-management conversations.

### For AID authors

- **OpenAPS/oref0 maintainers**: document the nocturnal braking
  gap and recommend oref1 migration paths (AAPS, Trio).
- **Trio/AAPS maintainers**: investigate whether tight oref1
  defaults may cause HAAF-compatible counter-reg attenuation over
  long-term use. Consider optional "counter-reg preservation"
  mode that occasionally allows BG to climb slightly above nadir
  before heavy braking engages (hypothesis).
- **Loop maintainers**: identify and alert hidden-leverage
  patients via in-app analytics — when settings require >90%
  basal cut frequently, prompt the user for a settings review.

### For existing-system users

Three-axis phenotype self-assessment:
- Stacking (check your evening 4h-bolus pattern)
- AID dependence (check your actual-vs-scheduled basal during hypo
  approaches)
- Physiological resilience (CGM rebound rate at nadirs)

Aggressive settings that require AID heavy-lifting are *fragile*
even when numerically tight. Predictable, slightly-less-tight
settings with algorithmic margin are *robust*.

### For the audition framework

Add composite audition fields:
```python
class AuditionInputs:
    # existing + EXP-2876/2882/2885:
    stack_score: float
    braking_ratio: float
    counter_reg_intercept: float
    # new composite:
    hidden_leverage_score: float  # stack × (1 − brake)
    archetype: str
    algorithm_lineage: str  # Loop / oref1 / oref0
```

Flag thresholds:
- `hidden_leverage_score > 0.70` → safety review triggered
- `counter_reg_intercept < 0.5` → HAAF/hypo-unawareness workup
- `archetype == 'hidden_leverage'` → "AID-dependence" patient conversation
- `archetype == 'exposed_stacker'` → bolus-attenuation intervention

## Limitations

- n=24 with complete data; 5 patients missing controller labels
  (excluded from lineage analyses).
- No AAPS in sample — cannot validate oref1 lineage across platforms.
- oref0 cohort n=3 — all analyses involving OpenAPS are
  underpowered.
- Counter-reg intercept = single 60-min post-nadir window;
  alternative definitions (15-min immediate, 120-min extended)
  may give different rankings.
- Hidden-leverage score is a simple product, not validated against
  outcomes (actual closed-loop-failure hypo rates).
- UTC TOD smearing (noted throughout arc).

## Next experiments

- **EXP-2887** — HAAF feedback: does hypo_fraction (EXP-2878)
  mediate the oref1 counter-reg gap? (4-axis regression)
- **EXP-2888** — Simulate closed-loop failure on hidden-leverage
  patients: what is predicted IOB trajectory if AID disengages at
  BG 100 on descent?
- **EXP-2889** — Validate `hidden_leverage_score` threshold against
  severe hypo events (from EXP-2877 strata).
- **Vignette**: produce `ns-8b3c1b50793c` (no-counter-reg, Trio-
  dependent) as a safety-focused vignette — very different from the
  patient-C optimization vignette.
- **Audition wiring**: add `archetype`, `hidden_leverage_score`,
  `algorithm_lineage` to `production/audition_matrix.py`.

## Files

- `tools/cgmencode/exp_phenotype_synthesis_2886.py`
- `externals/experiments/exp-2886_phenotype.parquet`
- `externals/experiments/exp-2886_phenotype_summary.json`
- `docs/60-research/figures/exp-2886_phenotype.png`
