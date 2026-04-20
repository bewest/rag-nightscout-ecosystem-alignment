# Per-Patient Settings Report Card — Methodology & Results

## Overview

EXP-2807 produces actionable settings report cards for AID patients using
data-driven extraction validated across EXP-2803–2806.

## Methodology

### ISF Extraction (Optimal Window Method)
Select correction events meeting ALL criteria:
1. BG ≥ 180 mg/dL
2. Time-in-high 1–6 hours (peak correction effectiveness)
3. No carbs within ±3 hours
4. Bolus ≥ 0.5U

Median of resulting ISF values = extracted ISF.
Confidence = high (≥20 events), medium (10–19), low (5–9).

### CR Extraction (Meal Event Method)
Select meal events meeting ALL criteria:
1. Pre-meal BG 100–180 mg/dL
2. Carbs ≥ 5g AND bolus ≥ 0.5U
3. Subtract ISF component from 3h BG change
4. Filter physiologically plausible (2–50 g/U)

### Cross-Checks
- 1800/TDD rule (approximation, known to overestimate in closed-loop)
- 500/TDD rule for CR
- Actual basal delivery vs scheduled

## Key Findings

### ISF Is Almost Universally Set Too Low (Too Aggressive)

| Direction | Count | Meaning |
|-----------|-------|---------|
| INCREASE needed | 16/24 | Profile ISF is too aggressive |
| DECREASE needed | 3/24 | Profile ISF is too conservative |
| OK (±20%) | 5/24 | Settings roughly correct |

**Implication**: Most AID users have settings that cause the controller to
work harder than necessary. The controller compensates by suspending basal
and making many small corrections, leading to oscillations.

### Safety Alerts

- 13/28 patients (46%) have >4% time below 70 mg/dL
- This is strongly correlated with aggressive ISF settings
- Controllers that reduce aggressiveness have fewer lows

### Per-Controller Patterns

| Controller | Typical ISF Issue | Basal Pattern |
|-----------|-------------------|---------------|
| Loop | ISF too low by ~50% | Runs at 15% actual basal |
| Trio | ISF too low by ~60% | Runs at 8% actual basal |
| OpenAPS | More variable | 30% actual basal (closest to traditional) |

## Report Card Structure

Each patient receives:
```
┌─ patient_id (Controller) — N days
│  TIR: X%  |  <70: X%  |  >180: X%  |  Mean: X  |  CV: X%
│  Profile ISF: X  |  Extracted: X  |  1800/TDD: X  |  Confidence
│  TDD: XU  |  Basal: XU (X% sched, X% actual)
│  CR extracted: X g/U  |  500/TDD: X  |  Confidence
│  ⚠️  Recommendations (if any)
└──────────────────────────────────────────────
```

## Architecture Decisions

### Why Not Resistance Correction? (EXP-2804: 1/5)
Individual-event resistance correction fails because:
- 84% of BG drop variance is stochastic (EXP-2683)
- Resistance coefficient direction is inconsistent (38% negative)
- Better to SELECT optimal events than CORRECT noisy events

### Why Not Multi-Day Features? (EXP-2803: 2/5)
- Day-to-day TIR persistence is weak (r=0.16)
- 3-day rolling adds nothing over 1-day
- AID controller compensates for multi-day variation effectively

### Why Separate Timescales? (EXP-2806: 3/5)
- Hourly and 5-min are orthogonal (feedback r=-0.575)
- Hourly: WHY did BG change? → settings extraction
- 5-min: WHAT will BG do next? → forecasting
- Feeding hourly ISF corrections into 5-min models produces zero improvement

## Limitations

1. **ISF vs 1800/TDD disagree on direction** (33% agreement)
   - The 1800 rule uses raw TDD which includes preemptive insulin
   - Extracted ISF uses only measurable correction events
   - They estimate different things

2. **Some patients lack sufficient events**
   - Well-controlled patients rarely hit BG≥180 → few ISF events
   - These get "insufficient confidence" rating

3. **CR extraction requires ISF estimate first**
   - Circular dependency partially mitigated by using profile ISF as fallback
   - Iterative refinement could improve this

## Source Files
- `tools/cgmencode/exp_report_cards_2807.py` — Main report card generator
- `tools/cgmencode/exp_category_settings_2805.py` — Method validation
- `externals/experiments/exp-2807_report_cards.json` — Full results
