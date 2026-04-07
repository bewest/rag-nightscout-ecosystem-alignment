# Capability Report: Pattern & Drift Recognition

**Date**: 2026-04-07 | **Overnight batch**: EXP-686, EXP-696, EXP-765, EXP-781 | **Patients**: 11

---

## Capability Definition

Detect physiological shifts over time — circadian patterns, insulin sensitivity drift, settings adequacy changes, and weekly trend evolution — enabling proactive therapy adjustment before control deteriorates.

---

## Current State of the Art

| Task | Best Result | Method | Status |
|------|-------------|--------|--------|
| Circadian pattern extraction | **71.3 ± 18.7 mg/dL** amplitude | Per-patient extraction | ✅ Validated |
| Circadian correction | **+0.474 R²** at 60 min | sin/cos(2πh/24) residual correction | ✅ Largest single gain |
| ISF time-of-day variation | **29.7% mean** (9/11 patients) | Per-hour ISF estimation | ✅ Quantified |
| Settings change detection | **5.3 changepoints/patient** mean | Rolling RMSD analysis | ✅ Production |
| Weekly trend classification | 4 improving, 5 declining, 2 stable | Half-vs-half TIR comparison | ✅ Production |
| ISF drift tracking | r = −0.156 (corrected from +0.70) | Sliding median (4-day lookback) | ⚠️ Weak signal |
| Weekly routine hotspots | 2 phenotypes identified | Per-block TIR analysis | ✅ Analytics only |

---

## Circadian Patterns (EXP-126, EXP-781)

The circadian signal is the **largest single improvement lever** in the entire research program at ≥30-minute horizons.

**Correction model**: 3 parameters trained on prediction residuals: `a·sin(2πh/24) + b·cos(2πh/24) + c`

| Horizon | Base R² | + Circadian R² | Δ |
|---------|---------|----------------|---|
| 5 min | 0.973 | 0.976 | +0.003 |
| 15 min | 0.845 | 0.873 | +0.029 |
| 30 min | 0.510 | 0.627 | **+0.117** |
| 60 min | −0.625 | −0.152 | **+0.474** |

At 60 minutes, circadian correction is the difference between a model that's worse than persistence (−0.625) and one that's approaching usefulness (−0.152). The 3-parameter correction captures the dawn phenomenon's systematic bias.

**Universal finding**: 10/10 patients with sufficient overnight data show measurable circadian patterns. The 71.3 mg/dL amplitude means the time-of-day signal alone swings glucose across the entire in-range band (70–180).

---

## ISF Time-of-Day Variation (EXP-765)

Insulin sensitivity varies significantly across the day for most patients:

| Metric | Value |
|--------|-------|
| Patients with significant variation | 9 of 11 (82%) |
| Mean variation | 29.7% |
| Maximum variation (patient c) | **82.2%** |
| Minimum variation | ~5% |

Patient c's insulin sensitivity nearly doubles from morning to evening. A flat ISF profile for this patient is fundamentally wrong for ~16 hours of the day.

---

## Settings Change Detection (EXP-696)

Detects when a patient's underlying metabolic response shifts enough to indicate settings need adjustment:

| Patient | Weeks | Changepoints | Pattern |
|---------|-------|-------------|---------|
| i (most volatile) | 25 | **23** | Near-continuous shift |
| c | 25 | 11 | Frequent adjustment needed |
| e | 22 | 10 | Regular shifts |
| f, g, j, k | 25, 25, 8, 25 | **0 each** | Stable — no changes needed |
| d | 25 | 2 | Rare, manageable |

The distribution is bimodal: patients are either **stable** (0 changepoints) or **frequently shifting** (10+ changepoints). There is no middle ground. This maps to clinical experience — some patients need settings adjusted monthly, others run the same settings for years.

---

## Weekly Trend Reporting (EXP-686)

Tracks glycemic control evolution to identify improving vs declining trajectories:

| Trend | Count | Example |
|-------|-------|---------|
| Improving | 4 | Patient b: TIR 52.4% → 60.0% |
| Declining | 5 | Patient a: TIR 58.5% → 52.4% |
| Stable | 2 | Patient k: TIR 95.8% → 94.1% |

Mean significant changes per patient: 12.0 over 25 weeks (roughly one notable shift every 2 weeks).

---

## Weekly Routine Phenotypes (EXP-416)

Two distinct patient phenotypes emerge from per-block TIR analysis (no ML required):

| Phenotype | Patients | Worst 6h Block | Block TIR |
|-----------|----------|---------------|-----------|
| Morning-high | a, b, c, d, f | 06:00–12:00 | 31–53% |
| Night-hypo | g, h, i, k | 00:00–06:00 | Varies |

The morning-high phenotype patients show dramatically worse TIR in the 06:00–12:00 block — the dawn phenomenon window. This is actionable: these patients would benefit from higher overnight basal or an early-morning override.

---

## Validation Vignette

**Patient c — ISF variation across the day**: Profile ISF = 72 mg/dL/U, but effective ISF ranges from ~40 (morning) to ~130 (evening) — an 82.2% variation. The settings change detector flags 11 changepoints over 25 weeks. The circadian correction captures this: adding sin/cos features improves cohort-wide mean 30-minute R² by 0.117 (patient c benefits particularly given their high ISF variability). The recommendation engine identifies the ISF mismatch and recommends time-of-day ISF profiling.

**Patient f — Stable phenotype**: Zero changepoints detected over 25 weeks. Weekly trends show improving trajectory (TIR 62.0% → 68.8%). The system correctly recommends maintaining current settings and outputs Grade B. No intervention needed.

---

## Key Insight

Time-of-day is not a feature — it is a **symmetry break**. At episode scales (≤12 hours), glucose dynamics are time-translation invariant: a meal spike at 8 AM is identical to one at 8 PM. But at ≥24-hour scales, the circadian signal breaks this symmetry with a 71.3 mg/dL amplitude swing. The 3-parameter circadian correction (the cheapest possible model) captures more variance than any neural architecture change — because it encodes the right physics.
