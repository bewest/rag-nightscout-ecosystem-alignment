# Settings Extraction Report — 2026-04-20

## Summary

Experiments EXP-2803 through EXP-2805 tested three approaches to extracting
actionable AID settings from observational glucose data.

| EXP | Title | Result | Key Insight |
|-----|-------|--------|-------------|
| 2803 | Day-Level Aggregation | 2/5 | Day-to-day TIR persistent but weak; multi-day memory doesn't add predictive power |
| 2804 | Resistance-Corrected ISF | 1/5 | Population resistance signal doesn't translate to individual corrections (too noisy) |
| 2805 | Category-Specific Extraction | 3/5 | Event SELECTION outperforms event CORRECTION; reduces ISF CV by 17% |

## What Works for Settings Extraction

### ISF Extraction — Validated Method

Select correction events meeting ALL criteria:
1. BG ≥ 180 mg/dL (avoids meal contamination)
2. Time-in-high 1–6 hours (optimal correction window from EXP-2801)
3. No carbs within ±3 hours (avoids CR interference)
4. Bolus ≥ 0.5U (meaningful correction)

**Result**: Within-patient CV drops 17% (0.764 → 0.635) vs all events.
Extracted ISF correlates with 1800/TDD rule (r=0.56, p=0.02).

### CR Extraction — Validated Method

Select meal events meeting ALL criteria:
1. Pre-meal BG 100–180 mg/dL (avoids correction confounding)
2. Carbs ≥ 5g AND bolus ≥ 0.5U (confirmed meal bolus)
3. Subtract ISF component from BG change
4. CR = carbs / effective_dose_for_carbs

**Result**: 13/17 patients produce physiologically plausible CR (5–25 g/U).

## What Doesn't Work

### Individual-Event Resistance Correction (EXP-2804)

The non-linear ISF curve (EXP-2801, F=31.6, p<1e-8) is a population-level
statistical pattern. When applied as individual-event correction:
- Resistance coefficient direction is INCONSISTENT (38% negative)
- Between-patient variance INCREASES
- Test prediction WORSENS

**Lesson**: Use optimal event WINDOW to select clean events rather than
correcting noisy events with a model.

### Multi-Day Prediction (EXP-2803)

- Day-to-day TIR correlation is modest (r=0.16)
- 3-day rolling adds NOTHING over 1-day features (Δ≈0)
- Naive "today = yesterday" is terrible (R² = -0.86)
- Causal direction only 58% correct at day level

**Lesson**: Multi-day metabolic memory exists but the AID controller
compensates for it effectively, leaving no exploitable residual.

## 50/50 Rule — Critical Reinterpretation

Traditional: 50% of TDD should be basal, 50% bolus.

**Observed actual delivery**:
| Controller | Actual Basal % | Interpretation |
|-----------|---------------|----------------|
| Loop | 15.5% | Heavy suspension, micro-bolusing |
| Trio | 7.8% | Nearly zero basal, all SMBs |
| OpenAPS | 29.8% | Closest to traditional |

The 50/50 rule applies to **scheduled** basal rates, not **actual delivered**.
AID controllers suspend basal aggressively and deliver insulin through
corrections/SMBs instead. This is BY DESIGN — the controller uses the
scheduled basal as its "anchor" but actually delivers most insulin reactively.

**Implication for ISF×TDD**: The classical formula 1800/TDD assumes
correction-only insulin. In closed-loop, TDD includes preemptive dosing
that prevents highs without causing a measurable BG drop. This is why
ISF×TDD = 4551 rather than 1800.

## Extracted Settings Per Controller

| Metric | Loop | Trio | OpenAPS |
|--------|------|------|---------|
| Median TDD (U/day) | 46 | 52 | 35 |
| Actual Basal % | 15% | 8% | 30% |
| ISF Extracted (mg/dL/U) | 55 | 98 | 82 |
| ISF Profile (mg/dL/U) | 49 | 62 | 50 |
| CR Extracted (g/U) | 10 | 12 | 8 |

## Recommendations

### For AID Users
1. **ISF is likely set too low** — extracted ISF consistently higher than profile
2. **Use the optimal correction window** (1–6h in high) to self-assess ISF
3. **50/50 rule violations are normal** for closed-loop — look at scheduled rates

### For AID Developers
1. **ISF from optimal events** is more reliable than autotune-style bulk regression
2. **Separate ISF and CR extraction** — different event categories, different methods
3. **The 1800/TDD rule overestimates** true correction-ISF in closed-loop
   because TDD includes preemptive insulin that doesn't produce measurable drops
4. **Multi-day memory is weak** — focus on intra-day patterns for optimization

## Source Files
- `tools/cgmencode/exp_day_level_2803.py`
- `tools/cgmencode/exp_resistance_isf_2804.py`
- `tools/cgmencode/exp_category_settings_2805.py`
- `tools/visualizations/category-settings/exp-2805-dashboard.png`
