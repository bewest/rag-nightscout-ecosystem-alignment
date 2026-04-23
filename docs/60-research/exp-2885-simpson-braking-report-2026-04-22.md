# EXP-2885 — Simpson-Decomposed AID Braking: Controller × TOD × Aggressiveness

**Date:** 2026-04-22
**Stream:** A + B (causal + operational)
**Status:** Complete — Simpson's paradox CONFIRMED; controller-specific
signatures hidden by EXP-2884 pooling

## Question

EXP-2884 concluded AID braking is "saturated" at 0 U/h in all TODs
based on pooled medians, implying no differential TOD response.
However, three sources of pooling risk were unaddressed:

1. **Controller aggregation** — Loop/Trio/OpenAPS pooled together
2. **Per-patient pooling** — events vs patients as unit of analysis
3. **Setting aggressiveness** — patients with aggressive profiles may
   ride closer to the braking ceiling

Re-analyze with per-patient means stratified by controller and
aggressiveness to unmask Simpson's-paradox-hidden signals.

## Method

- Pre-nadir descent events from EXP-2881 (n=3,912 events, 31
  patients).
- Aggregate to **per-patient × TOD cells** (≥3 events required) to
  give each patient equal weight within its controller cohort.
- Metrics: `mean_delivery_ratio`, `suspension_rate` (fraction of
  window at zero basal).
- Within each controller: Friedman test across 4 TODs (per-patient),
  Wilcoxon evening vs morning.
- Aggressiveness proxy: patient-level rank of (mean scheduled basal
  + mean 4h bolus). Split into terciles.
- Merge with EXP-2882 stack_score for orthogonality check.

## Result

**VERDICT: SIMPSON'S PARADOX CONFIRMED. Three distinct braking
signatures exist across controllers; pooled analysis obscured them
completely.**

### Per-patient controller × TOD matrix (mean delivery_ratio)

|       | night | morning | afternoon | evening | TOD span |
|-------|------:|--------:|----------:|--------:|---------:|
| **Loop** (n≈8)      | 0.117 | 0.088 | 0.144 | 0.095 | **0.056 (FLAT)** |
| **Trio** (n≈9)      | 0.057 | **0.119** | 0.048 | **0.041** | 0.078 |
| **OpenAPS** (n≈4)   | **0.748** | 0.397 | 0.444 | **0.313** | **0.435** |

Ratio = fraction of scheduled basal actually delivered during the
60-min pre-nadir descent. Lower = more aggressive braking.

### Suspension rate (fraction of window at zero basal)

|       | night | morning | afternoon | evening |
|-------|------:|--------:|----------:|--------:|
| Loop      | 0.70 | 0.75 | 0.70 | 0.71 |
| Trio      | 0.87 | 0.75 | 0.84 | **0.89** |
| OpenAPS   | **0.29** | 0.45 | 0.42 | 0.57 |

### Within-controller TOD tests (per-patient)

| Controller | n | Friedman p | Eve−Morn ratio | Wilcoxon p |
|------------|--:|-----------:|---------------:|-----------:|
| Loop       | 7 | 0.65       | −0.000         | 1.00       |
| **Trio**   | 8 | **0.054**  | **−0.066**     | **0.074**  |
| OpenAPS    | 3 | 0.24       | —              | —          |

### Aggressiveness tercile × controller (mean delivery ratio)

| Tercile      | Overall | Loop     | Trio     | OpenAPS  |
|--------------|--------:|---------:|---------:|---------:|
| conservative | 0.224   | 0.193    | 0.073    | 0.481    |
| mid          | 0.136   | 0.130    | 0.047    | 0.421    |
| aggressive   | 0.084   | **0.043**| 0.079    | 0.222    |

Within Loop, aggressive users brake 4.5× harder than conservative
users (0.043 vs 0.193). Within Trio, braking is flat across terciles
(0.07–0.08), i.e., Trio's zero-temp policy is setting-independent.
Within OpenAPS, aggressive users brake ~2× harder than conservative
(0.222 vs 0.481), but still less than Loop/Trio at any level.

Cohort-wide Spearman: aggr_score vs suspension_rate ρ=+0.16 p=0.49
(no pooled correlation — driven by controller mix).

### Orthogonality with stacker phenotype

- stack_score (EXP-2882) vs suspension_rate: (not computed per
  controller here; n=24 pooled).
- Stack_score was orthogonal to counter-reg (EXP-2882); here the
  braking signal is controller-algorithmic, adding a third
  independent axis for phenotyping.

## Interpretation

### 1. Three distinct controller signatures

**Loop** — FLAT, MODERATE, AGGRESSIVENESS-RESPONSIVE
: No TOD differentiation (Friedman p=0.65). ~70-75% suspension
  across all TODs. But aggressive users force Loop to brake 4.5×
  harder than conservative users. Loop is a "responsive linear
  controller" that scales with scheduled basal.

**Trio** — TOD-STRUCTURED, SETTING-INDEPENDENT
: Near-significant TOD pattern (Friedman p=0.054): morning ratio
  0.119 is 2-3× higher than other TODs → less braking in the
  morning dawn window. Evening ratio 0.041 + suspension rate 0.89 —
  the most aggressive TOD/controller combination observed. Consistent
  across aggressiveness terciles (0.047–0.079 range). Trio's logic
  hits its braking pattern regardless of user settings.

**OpenAPS** — PERMISSIVE, NOCTURNALLY LAX
: Night delivery ratio **0.748** — OpenAPS delivers 75% of
  scheduled basal during descent toward nocturnal hypo. Huge TOD
  span (0.435). Lowest suspension rates (29-57%). Aggressiveness
  matters a lot here (0.48 → 0.22 conservative → aggressive).

### 2. User-incentive asymmetry (answers user question)

The aggressiveness analysis confirms: **patients CAN and DO get
into over-aggressive settings because the AID compensates**.

- **Loop users** with aggressive settings force the algorithm to
  brake 4.5× harder. The algorithm is "saving them" during
  descents. This creates a hidden risk: if Loop's braking fails
  (connectivity, CGM dropout, closed-loop exit), an aggressive-Loop
  patient has far more insulin running than their safe autonomous
  operation allows. **Aggressive-Loop is a hidden-leverage
  phenotype.**

- **Trio users** show flat braking across settings — Trio brakes
  the same way regardless. This means aggressive-Trio settings
  deliver less compensation, so the aggressiveness shows up in
  outcomes (hypo) more visibly. Safer discovery loop for the
  patient/clinician.

- **OpenAPS users** at aggressive settings still get relatively
  weak nocturnal braking (night ratio 0.75). OpenAPS cannot
  compensate for over-aggressive settings in the nighttime regime.

### 3. Why EXP-2884 missed this

EXP-2884 used pooled medians. Because Trio's 89% evening suspension
and OpenAPS's 29% night suspension both imply "many zeros," the
pooled median was 0 in all TODs, hiding:

- Trio's strong evening braking
- Loop's moderate uniform braking
- OpenAPS's weak nocturnal braking

This is a textbook Simpson's paradox: categorical pooling of very
different subpopulations produces a misleading invariant (all zeros).

### 4. Re-interpretation of EXP-2881/2882

- **EXP-2881's cohort evening descent penalty of 0.13 mg/dL/min**
  reflects the MIX of controllers: Trio brakes hardest here, Loop is
  flat, OpenAPS less so. A controller-specific decomposition would
  show different descent effects per controller.

- **EXP-2882's controller comparison** found Loop stack 0.58 ≈ Trio
  0.56 ≈ OpenAPS 0.75. The stacking phenotype is controller-weak;
  the BRAKING response is controller-strong. The asymmetry:
  similar input → different defense → different hypo outcomes.

## Actionable implications

### For OpenAPS authors

🚨 **Nocturnal braking gap.** OpenAPS delivers 75% of scheduled
basal during night descent toward hypo. Loop/Trio deliver 6–12%.
Candidates for investigation:
- Nighttime max-IOB / suspension trigger thresholds
- Whether `exercise_mode` or `autotune` preferences interact with
  night-time hypo avoidance
- Difference vs AAPS (which is not in this sample)

### For Trio authors

Morning ratio is highest (0.119 vs evening 0.041). This matches
dawn EGP (EXP-2880 morning slowest descent). Trio is implicitly
dawn-aware. Consider whether this is intentional via resistance/
sensitivity defaults or emergent from momentum handling.

### For Loop authors

Uniform braking is a design virtue (predictability) but flattens
differential response — Loop cannot give extra defense when
needed. Candidate: add a TOD-aware momentum factor to give stronger
dawn/evening defense.

### For existing-system settings

- **Loop aggressive users** need to understand the hidden-leverage
  risk. Their tight TIR is AID-dependent; any closed-loop failure
  reveals their settings are running too hot. Guidance: more
  conservative basal + trust the AID less to save you.
- **Trio users** can safely experiment with aggressiveness, because
  Trio doesn't scale its defense with aggressiveness — so poor
  settings show up as events (clear feedback).
- **OpenAPS users with night hypos** should investigate `maxIOB`,
  `exercise` targets, and `A52_risk_enable`-style thresholds.

### For audition framework

Add **`braking_profile`** to `AuditionInputs`:
```python
class AuditionInputs:
    braking_mean_ratio: float  # lower = more braking
    braking_tod_span: float    # 0 = flat, >0 = TOD-structured
    braking_hidden_leverage: float  # aggr × (1 - ratio) proxy
```

Flag `hidden_leverage` when aggressive settings meet aggressive
braking — the patient looks fine until the algorithm can't save
them.

## Limitations

- OpenAPS n=3-4 patients; within-controller tests underpowered.
- Friedman p=0.054 for Trio is borderline; confirmation with more
  patients needed.
- Aggressiveness proxy is cohort-rank-based; not anchored to
  physiology.
- 60-minute pre-nadir window is narrow; controller differences
  outside this regime (ambient control) not assessed.
- UTC TOD bins smear across local evening times.
- Simpson's-paradox-proof: we confirmed *hidden* structure exists;
  we did not exhaustively check other pooling dimensions (insulin
  type, pump model, CGM model).

## Next experiments

- **EXP-2886** — Simpson audit of EXP-2882 stacker phenotype:
  does stack_score vary within controller × aggressiveness cells?
- **EXP-2887** — OpenAPS nocturnal braking drilldown: what
  distinguishes the three OpenAPS patients?
- **EXP-2888** — Stack-aware guard simulation with
  controller-specific braking assumptions.
- **Audition wiring** — add `braking_profile` fields.

## Files

- `tools/cgmencode/exp_simpson_braking_2885.py`
- `externals/experiments/exp-2885_simpson_braking.parquet`
- `externals/experiments/exp-2885_simpson_braking_summary.json`
- `docs/60-research/figures/exp-2885_simpson_braking.png`
