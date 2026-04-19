# Wave-5: Robustness Check — What Survives Independence?

**Date**: 2026-04-19  
**Experiments**: EXP-2714, EXP-2715, EXP-2716  
**Scope**: Validation of waves 1-4 findings against statistical independence and horizon sensitivity  

---

## Executive Summary

Wave-5 subjected our 12-experiment findings to three critical robustness checks.
The results are **scientifically more important than the discoveries themselves**
because they separate what's real from what was artifact.

| Finding | Survives? | Implication |
|---------|-----------|-------------|
| Multi-factor R² structure | ✅ YES (0.173 vs 0.224) | Real but ~23% weaker |
| Dose as top predictor | ✅ YES (ΔR²=0.102) | Insulin dose genuinely explains ISF variance |
| Patient physiology matters | ✅ YES (ΔR²=0.061) | Individual variation is real |
| SC ceiling β=0.595 | ❌ NO (→ -0.041) | Artifact of overlapping windows |
| SC ceiling power-law | ❌ NO (β→0 at 6h) | Transient PK effect, not stable dose-response |
| Circadian ISF peak shift | ⚠️ PARTIAL | Needs explicit BG₀ residualization |
| Shrinkage stability gain | ✅ YES (+159% r) | Dramatically more reproducible patterns |

**Bottom line**: The "subtract what you know" framework works — multi-factor
deconfounding extracts real signal. But the SC ceiling power-law was the most
fragile finding, collapsing under both independence and horizon tests.

---

## Part 1: The Independence Problem (EXP-2714)

### What we found

Our 65,425 "events" are actually **~6,000 independent observations** (9.2%
retention at 2h gap). The massive autocorrelation (lag-1 = 0.638) from
EXP-2713 was caused by overlapping measurement windows — events 5 minutes
apart measure the same glucose trajectory.

After subsampling to independent events:

```
Autocorrelation: 0.638 → -0.051  (eliminated ✓)
Multi-factor R²: 0.224 → 0.173   (real, 23% smaller)
SC ceiling β:    0.595 → -0.041  (collapsed ✗)
BG prediction:   24.8  → 50.4    (degraded ✗)
```

### What survives independence

**Stepwise R² waterfall (independent events, N=5,998)**:
```
+patient_id     R²=0.061  (+0.061)  ← Still #2
+BG₀            R²=0.064  (+0.003)
+circadian      R²=0.065  (+0.002)
+dose           R²=0.167  (+0.102)  ← Still #1, largest contributor
+IOB            R²=0.170  (+0.003)
+channels       R²=0.173  (+0.003)
+glycogen       R²=0.173  (+0.000)
```

The factor ordering is preserved (dose and patient_id dominate), and the
bootstrap 95% CI is [0.147, 0.286] — comfortably above zero.

### What doesn't survive

SC ceiling β collapses to -0.041 (effectively zero). This means the
apparent diminishing returns at high IOB were an artifact of measuring
overlapping windows within the same correction episode. Independent events
show NO systematic dose-response non-linearity.

### Implications

1. **All p-values from prior experiments are overconfident** — effective N is ~10× smaller
2. **Effect sizes are real but more modest** — R² of 0.17 not 0.22
3. **The oref0-style "subtract and reason about residual" approach IS validated**
4. **SC ceiling needs complete re-evaluation** (see EXP-2716)

---

## Part 2: β Vanishes at Longer Horizons (EXP-2716)

### The surprising finding

β DECREASES with measurement horizon — completely opposite to our hypothesis
that longer horizons would show more diminishing returns:

| Horizon | β | R² | Interpretation |
|---------|------|------|----------------|
| 1h | 0.277 | 0.629 | Moderate PK effect |
| 2h | 0.314 | 0.489 | Peak apparent effect |
| 3h | 0.201 | 0.198 | Controller compensating |
| 4h | 0.092 | 0.031 | Mostly compensated |
| 5h | 0.062 | 0.014 | Nearly flat |
| 6h | 0.006 | 0.000 | No SC ceiling at all |

Kendall τ = -0.867 (p=0.017) — statistically significant DECREASE.

### What this means

The SC ceiling is a **transient pharmacokinetic absorption bottleneck**:
- At 1-2h: insulin is still being absorbed; high IOB → absorption queue
- At 3-4h: AID controller has reduced basal/suspended delivery to compensate
- At 6h: full dose has acted; controller has fully compensated

This completely reconciles **GAP-ALG-073** (β=0.595 vs simulator β=0.9):
- Neither value is "correct" — both are measurement artifacts at different horizons
- The "true" SC ceiling is a transient PK phenomenon, not a stable ISF dampening factor
- Forward simulator's β=0.9 was set for full DIA (6h) where observational β→0

### Recommendation for AID controllers

**Do NOT implement ISF dampening as a static power-law.** Instead:
- The absorption bottleneck is real but transient
- AID controllers already compensate via dynamic basal adjustment
- If implementing SC ceiling, it should be time-varying: strong at 0-2h, zero at 6h
- Consider it a pharmacokinetic model parameter, not a dose-response curve

---

## Part 3: Shrinkage Works for Stability, Not Accuracy (EXP-2715)

### The nuanced result

Shrinkage circadian ISF tables achieved dramatically better temporal stability
(split-half r: 0.235 → 0.609, +159% improvement) but did NOT improve prediction
accuracy over flat ISF.

| Method | Median MAE | Split-half r |
|--------|-----------|-------------|
| Flat demand ISF | 40.3 | N/A |
| Raw circadian | 43.6 | 0.235 |
| Shrinkage circadian | 45.3 | 0.609 |

The circadian peak appeared at 12-16h (midday) — the CONFOUNDED position.
This means the BG₀ residualization from EXP-2708 was NOT applied in EXP-2715's
event extraction. The raw circadian pattern is still BG₀-dominated.

### What this means

1. **Shrinkage is the right technique** — it massively reduces noise
2. **But it must be applied to BG-adjusted ISF**, not raw demand ISF
3. **Per-block circadian ISF adds noise** when there aren't enough events per block
4. **Flat ISF is a strong baseline** — hard to beat without BG adjustment

### For settings optimization

Use shrinkage when building per-patient ISF schedules:
- Start with population circadian shape (BG-adjusted)
- Shrink patient-specific blocks toward population based on event count
- This gives reproducible, stable settings even for patients with few events

---

## Part 4: Updated Recommendations

### For Data Understanding (Research)

| Claim | Status | Confidence |
|-------|--------|-----------|
| Multi-factor R² = ~0.17 | ✅ Validated | Bootstrap CI [0.15, 0.29] |
| Dose explains most variance | ✅ Validated | ΔR²=0.10 on independent events |
| Patient physiology #2 factor | ✅ Validated | ΔR²=0.06 on independent events |
| SC ceiling power-law | ❌ Retracted | β collapses with independence |
| Circadian ISF real | ⚠️ Needs BG adjustment | Raw peak is confounded |
| Glycogen state weak | ✅ Confirmed weak | ΔR²≈0 even with independence |

### For Settings Optimization (Users)

1. **Flat demand ISF per patient** remains the most robust single estimate
2. **Circadian adjustments** require BG₀ residualization to be meaningful
3. **SC ceiling-based ISF dampening** should NOT be used — β is not robust
4. **Shrinkage** should be used for any per-block or per-condition ISF tables

### For AID Controllers (Developers)

1. **SC ceiling is transient PK, not stable dose-response** — do not implement as static dampening
2. **If modeling absorption bottleneck**, use time-varying: strong early, zero by 6h
3. **AID controllers already compensate** for SC ceiling via dynamic basal — it's working
4. **Population β=0.595 at 2h** was inflated by overlapping windows (true independent β≈0)
5. **Forward simulator β=0.9** should be removed or replaced with PK-based transient model

### Updated GAP Status

| GAP | Original | Updated |
|-----|----------|---------|
| GAP-ALG-071 | Circadian peak wrong | Confirmed: raw=midday, adjusted=evening |
| GAP-ALG-072 | SC ceiling needs BG strat | **RETRACTED**: SC ceiling is transient PK artifact |
| GAP-ALG-073 | β=0.595 ≠ 0.9 | **RESOLVED**: Both are horizon-dependent artifacts; true β→0 |

---

## Part 5: Experiment Scorecard (All 15 Experiments)

| Wave | EXP | Title | H1 | H2 | H3 | H4 | Score |
|------|-----|-------|----|----|----|----|-------|
| Tier-1 | 2702 | Circadian demand-ISF | ✓ | ✓ | ✓ | ✗ | 3/4 |
| Tier-1 | 2703 | SC ceiling per-patient | ✓ | ✗ | ✗ | ✓ | 2/4 |
| Tier-1 | 2704 | Glycogen state | ✓ | ✗ | ✗ | ✗ | 1/4 |
| Confound | 2705 | Midday ISF peak | ✓ | ✓ | ✓ | ✗ | 3/4 |
| Confound | 2706 | SC slope raw | ✗ | ✓ | ✗ | ✗ | 1/4 |
| Confound | 2707 | Glycogen confound | ✗ | ✓ | ✗ | ✗ | 1/4 |
| Wave-3 | 2708 | BG-adjusted circadian | ✓ | ✓ | ✗ | ✓ | 3/4 |
| Wave-3 | 2709 | SC ceiling BG-controlled | ✗ | ✓ | ✓ | ✗ | 2/4 |
| Wave-3 | 2710 | Multi-factor deconfound | ✓ | ✓ | ✓ | ✓ | 4/4 |
| Wave-4 | 2711 | Circadian settings | ✓ | ✗ | ✓ | ✗ | 2/4 |
| Wave-4 | 2712 | SC ceiling settings | ✓ | ✓ | ✓ | ✓ | 4/4 |
| Wave-4 | 2713 | Residual structure | ✓ | ✗ | ✓ | ✓ | 3/4 |
| **Wave-5** | **2714** | **Independence corrected** | **✓** | **✗** | **✓** | **✗** | **2/4** |
| **Wave-5** | **2715** | **Shrinkage circadian** | **✗** | **✗** | **✗** | **✓** | **1/4** |
| **Wave-5** | **2716** | **β horizon sensitivity** | **✓** | **✗** | **✗** | **✗** | **1/4** |
| | | **Total** | | | | | **33/60** |

### Wave-5 Outcome: Low Pass Rate, High Information Value

Wave-5 has the lowest pass rate (4/12) but highest scientific value. Failed
hypotheses that DISPROVE earlier findings are more important than confirming them.
The independence check (EXP-2714) and horizon sensitivity (EXP-2716) together
establish that SC ceiling power-law was the least robust of our discoveries,
while multi-factor R² structure is the most robust.

---

## Part 6: What's Next

### Validated Foundation
- Multi-factor deconfounding (R²~0.17) on independent events
- Dose and patient physiology as dominant factors
- Shrinkage for stable per-patient estimates

### Open Questions
1. **BG-adjusted shrinkage circadian**: Combine EXP-2708's residualization with EXP-2715's shrinkage
2. **Independent-event settings extraction**: Re-run settings optimization on N=6K
3. **Transient PK model**: Model β as time-varying function for controller integration
4. **Cross-validation on held-out patients**: Test generalization beyond 21 patients
