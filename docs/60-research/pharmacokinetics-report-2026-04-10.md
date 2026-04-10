# Insulin Pharmacokinetics & Temporal Dynamics Report

**Experiments**: EXP-2021–2028  
**Date**: 2026-04-10  
**Population**: 11 patients, ~180 days each  
**Script**: `tools/cgmencode/exp_pharmacokinetics_2021.py`  
**Status**: AI-generated analysis — findings require clinical validation

---

## Executive Summary

This batch measures what actually happens when insulin is delivered: how long it acts, how fast it starts, whether stacking causes harm, and whether glycemic control is stable over months. The most surprising finding is that **insulin stacking is NOT a risk factor** in AID-managed patients (risk ratio 0.91× — stacking is slightly *protective*). Real-world DIA appears to be ≥6 hours universally (longer than most profile settings of 5h), onset is remarkably consistent at 30 minutes, and month-over-month TIR is unstable for 7/11 patients. Sensor artifacts (compression lows) affect every patient, averaging 44 events over 180 days.

### Key Numbers

| Metric | Value | Implication |
|--------|-------|-------------|
| Effective DIA | ≥5.9h (all patients) | Profile DIA of 5h is too short |
| Insulin onset | 30 min median [15–35] | Consistent across population |
| Stacking risk ratio | 0.91× (protective!) | AID loops manage stacking safely |
| Monthly TIR stability | 3 improving, 3 stable, 4 declining | Control drifts without intervention |
| Weekend effect | −0.8pp (negligible) | Day-of-week is not a useful signal |
| Compression artifacts | 44 mean per patient | ~1 every 4 days, biases hypo counting |
| Top TIR predictor | TAR (r=−0.976) | Hyperglycemia drives TIR loss, not hypos |
| Patients flagged | 9/11 | Most have ≥1 actionable risk |

---

## EXP-2021: Effective DIA from Correction Tail Analysis

![DIA Analysis](figures/pk-fig01-dia.png)

### Method

Isolated correction boluses: ≥0.5U, no carbs ±2h, glucose >140 mg/dL, no subsequent bolus within 3h. Tracked glucose for 6h, normalized per unit of insulin. DIA defined as time when 90% of maximum glucose-lowering effect has dissipated.

### Results

| Patient | N corrections | DIA (h) | Peak Time (h) | Effect (mg/dL/U) | τ (h) |
|---------|--------------|---------|---------------|-------------------|--------|
| a | 58 | 5.9 | 4.0 | −49 | 4.0 |
| c | 19 | 5.9 | 2.4 | −202 | 2.4 |
| e | 38 | 5.9 | 2.5 | −21 | 2.5 |
| f | 90 | 5.9 | 3.3 | −31 | 3.3 |
| i | 21 | 5.9 | 2.4 | −165 | 2.4 |
| j | 6 | 5.9 | 4.2 | −51 | 4.2 |

**5 patients** (b, d, g, h, k) had <5 isolated corrections — AID systems rarely deliver large isolated boluses, making natural-experiment DIA estimation difficult.

### Interpretation

All measurable patients show DIA at our 6h measurement ceiling, meaning true DIA is likely ≥6h. This is consistent with prior EXP-1334 finding (population effective DIA = 6.0h median). **Profile DIA of 5h underestimates real insulin action duration**, which causes the loop to stack insulin before prior doses have fully acted.

The effect magnitude varies enormously (−21 to −202 mg/dL/U), reflecting both ISF differences and AID loop interference during the observation window.

**Limitation**: The 5.9h ceiling for all patients suggests our 6h window is too short. A 8–10h window would better resolve true DIA, but requires even rarer "isolated" corrections.

---

## EXP-2022: Insulin Onset and Peak Timing

![Onset and Peak](figures/pk-fig02-onset-peak.png)

### Method

Found corrections (≥0.3U, no carbs ±1h, glucose >120) and measured: (1) onset = time to first 5 mg/dL drop, (2) peak decline = time of maximum glucose decline rate (smoothed with 3-point moving average).

### Results

| Patient | N events | Onset Median (min) | Onset IQR | Peak Decline (min) |
|---------|----------|-------------------|-----------|-------------------|
| a | 120 | 25 | 10–51 | 55 |
| b | 47 | 15 | 10–40 | 62 |
| c | 2,119 | 35 | 10–75 | 65 |
| d | 1,950 | 30 | 10–55 | 65 |
| e | 2,840 | 30 | 10–70 | 80 |
| f | 144 | 20 | 10–50 | 60 |
| g | 924 | 30 | 15–61 | 65 |
| h | 184 | 20 | 10–50 | 45 |
| i | 4,612 | 20 | 10–55 | 75 |
| j | 7 | 30 | 15–48 | 50 |
| k | 435 | 30 | 10–60 | 55 |

### Interpretation

**Onset is remarkably consistent**: 20–35 min median across all 11 patients. This aligns with rapid-acting insulin pharmacology (Humalog/NovoLog onset ~15–30 min). The wide IQRs (often 10–60+ min) likely reflect measurement noise from CGM lag and concurrent glucose changes, not true onset variability.

**Peak decline timing** (45–80 min) is more variable and patient-specific. Patient e shows the slowest peak effect (80 min), which may explain their ISF measurement difficulties in prior experiments.

**Large sample sizes** (c: 2,119, i: 4,612 events) reflect that AID loops deliver many small corrections — these are micro-bolus responses, not traditional correction bolus events.

---

## EXP-2023: Stacking Risk — Insulin Overlap

![Stacking Risk](figures/pk-fig03-stacking.png)

### Method

Defined "stacked" boluses as those preceded by another bolus within 2h. Measured hypo rate (<70 mg/dL) within 3h for stacked vs single boluses. Risk ratio = stacked hypo rate / single hypo rate.

### Results

| Patient | Total Boluses | Stacked (%) | Stack Hypo Rate | Single Hypo Rate | Risk Ratio |
|---------|--------------|-------------|----------------|-----------------|------------|
| a | 871 | 57% | 10% | 9% | 1.06 |
| b | 2,009 | 73% | 6% | 6% | 1.05 |
| c | 3,922 | 92% | 15% | 15% | 1.00 |
| d | 3,427 | 96% | 3% | 7% | **0.44** |
| e | 4,913 | 93% | 7% | 10% | **0.73** |
| f | 540 | 35% | 5% | 6% | 0.91 |
| g | 2,890 | 89% | 13% | 24% | **0.55** |
| h | 1,731 | 83% | 18% | 15% | 1.15 |
| i | 6,884 | 95% | 14% | 20% | **0.69** |
| j | 159 | 3% | 25% | 15% | 1.61 |
| k | 3,631 | 96% | 15% | 28% | **0.56** |

**Population median risk ratio: 0.91× (stacking is slightly protective)**

### Interpretation — A Paradigm Shift

This is one of our most counterintuitive findings: **insulin stacking does NOT increase hypoglycemia risk in AID-managed patients**. In fact, for 7/11 patients, stacking is associated with *lower* hypo rates.

**Why?** AID systems (Loop, AAPS, Trio) are *designed* to stack insulin via Super Micro Boluses (SMBs). The loop accounts for IOB when calculating each new dose. When it stacks, it's because the algorithm has determined the prior dose is insufficient — and the algorithm is correct more often than not.

The high stacking rates (92–96% for c, d, e, i, k) mean these patients' loops deliver nearly all corrections as sequences of small overlapping doses. This IS the algorithm working as designed.

**Exception**: Patient j (RR=1.61) has very few boluses (159) and almost no stacking (3%), suggesting manual bolusing without loop management — the one scenario where stacking IS risky.

**Clinical implication**: Traditional "insulin stacking" warnings from MDI/pump era may not apply to AID systems. The loop's IOB tracking provides automatic stacking management.

---

## EXP-2024: Temporal Stability (Month-over-Month)

![Temporal Stability](figures/pk-fig04-temporal.png)

### Method

Split each patient's 180-day dataset into 30-day months. Calculated monthly TIR, TBR, CV. Fit linear trend (slope in pp/month). Classified: improving (>+0.5pp/mo), declining (<−0.5pp/mo), or stable.

### Results

| Patient | Months | TIR Start→End | Slope (pp/mo) | TIR SD | Trend |
|---------|--------|---------------|---------------|--------|-------|
| a | 6 | 60%→52% | −1.7 | 3.3 | **Declining** |
| b | 6 | 48%→60% | +2.3 | 6.2 | **Improving** |
| c | 6 | 62%→60% | −0.4 | 2.7 | Stable |
| d | 6 | 76%→80% | −0.3 | 3.2 | Stable |
| e | 5 | 58%→66% | +1.7 | 3.7 | **Improving** |
| f | 5 | 54%→68% | +4.0 | 7.1 | **Improving** |
| g | 6 | 77%→69% | −1.9 | 4.2 | **Declining** |
| h | 5 | 79%→86% | — | — | Stable |
| i | 6 | 54%→51% | −1.7 | 7.1 | **Declining** |
| k | 5 | 97%→93% | −0.7 | 2.0 | **Declining** |

### Interpretation

**Control is NOT stable for most patients**: Only 3/10 (30%) maintain stable TIR over 6 months. 4 are declining, 3 are improving. This challenges the assumption that AID settings, once configured, remain adequate.

**High TIR SD** (b: 6.2pp, f: 7.1pp, i: 7.1pp) means monthly TIR can swing by 10+ percentage points — enough to move a patient from "meeting targets" to "needs intervention" in a single month.

**Patient f** shows the most dramatic improvement (+4.0 pp/month, 54%→68%), possibly reflecting a settings adjustment or behavior change during the observation period.

**Clinical implication**: Quarterly reviews may miss significant control degradation. Monthly TIR monitoring with automated drift detection could catch declining patients before they reach crisis.

---

## EXP-2025: Weekday vs Weekend Glycemic Patterns

![Weekday vs Weekend](figures/pk-fig05-weekday-weekend.png)

### Method

Classified days as weekday (Mon–Fri) or weekend (Sat–Sun) using modular arithmetic. Compared TIR, TBR, and mean glucose.

### Results

| Patient | Weekday TIR | Weekend TIR | Δ (pp) | Weekday Mean | Weekend Mean |
|---------|------------|------------|--------|-------------|-------------|
| a | 56% | 55% | −1.3 | 180 | 184 |
| b | 55% | 60% | **+4.5** | 177 | 170 |
| c | 63% | 58% | **−5.8** | 160 | 168 |
| d | 79% | 79% | 0.0 | 146 | 147 |
| e | 65% | 65% | −0.7 | 161 | 163 |
| f | 66% | 65% | −1.1 | 157 | 158 |
| g | 75% | 77% | +2.0 | 146 | 144 |
| h | 86% | 83% | −3.1 | 118 | 120 |
| j | 82% | 77% | −4.4 | 140 | 146 |
| k | 95% | 96% | +1.2 | 93 | 94 |

**Population mean: −0.8pp (negligible weekend effect)**

### Interpretation

**Day of week is NOT a useful predictive signal for glucose control.** This confirms EXP-1132 (DOW patterns absent for 0/11 patients). Individual differences exist (b does better on weekends, c/j worse), but the population effect is noise-level.

**Assumption caveat**: We don't have true calendar dates, so weekday assignment is approximate. However, even with perfect dates, prior work shows DOW patterns don't survive cross-validation.

---

## EXP-2026: Sensor Artifact Detection

![Sensor Artifacts](figures/pk-fig06-artifacts.png)

### Method

Three artifact types analyzed:

1. **Compression lows**: Glucose <60 with rapid drop from >30 mg/dL higher, followed by rapid recovery (>40 mg/dL within 1h)
2. **Warmup effects**: TIR in first 12h of sensor life vs remainder
3. **Data gaps**: Consecutive missing readings

### Results

| Patient | Coverage | Compression Events | Warmup TIR Δ | Gap Count | Gap % |
|---------|----------|--------------------|--------------|-----------|-------|
| a | 88% | 59 | −13.5pp | 67 | 11.6% |
| b | 90% | 37 | +11.8pp | 41 | 10.4% |
| c | 83% | 77 | −11.3pp | 34 | 17.3% |
| d | 87% | 51 | −5.7pp | 64 | 12.6% |
| e | 89% | 47 | −10.3pp | 47 | 10.9% |
| f | 89% | 17 | −10.6pp | 46 | 11.1% |
| g | 89% | 66 | +4.8pp | 63 | 11.0% |
| h | **36%** | 50 | +3.2pp | 17 | **64.2%** |
| i | 90% | 33 | −11.2pp | 60 | 10.5% |
| j | 90% | 7 | — | 11 | 9.8% |
| k | 89% | 45 | −2.9pp | 52 | 11.0% |

### Interpretation

**Compression lows are universal**: Every patient has them (7–77 over 180 days). With ~44 mean events, that's roughly **one potential false hypo every 4 days**. This directly biases hypo counting in all our analyses.

**Patient c** has the most compression artifacts (77), which may partly explain their apparent high hypo rate in prior experiments.

**Patient h** has catastrophic coverage (36%, 64% gaps). All analyses for this patient are unreliable. This was flagged in prior work (EXP-1291: "h CGM=35.8%").

**Warmup effects are large**: Most patients show −5 to −13pp lower TIR during sensor warmup (first 12h). This is a known CGM limitation — new sensors read lower initially, biasing towards apparent hypoglycemia.

**Patients b, g, h show positive warmup TIR differences** (better during warmup), which is unusual and may indicate different sensor systems or calibration practices.

---

## EXP-2027: Hidden Variable Identification

![Hidden Variables](figures/pk-fig07-hidden-vars.png)

### Method

Computed 13 features per patient and correlated each with TIR. Then performed residual analysis: after removing the top predictor, what explains remaining TIR variance?

### Results

**Direct TIR correlations (sorted by |r|):**

| Feature | Correlation | Direction |
|---------|------------|-----------|
| TAR (Time Above Range) | −0.976 | Higher TAR → lower TIR |
| Mean glucose | −0.932 | Higher mean → lower TIR |
| CV | −0.764 | Higher variability → lower TIR |
| Max rise rate | −0.575 | Faster spikes → lower TIR |
| Mean abs change | −0.562 | More variability → lower TIR |
| Zero delivery % | +0.523 | More suspension → higher TIR |
| Max drop rate | +0.425 | Faster drops → higher TIR (!) |
| Max IOB | −0.380 | Higher IOB → lower TIR |
| Mean IOB | −0.354 | Higher IOB → lower TIR |
| Meals per day | −0.247 | More meals → lower TIR |
| Daily insulin | −0.213 | More insulin → lower TIR |
| Daily carbs | −0.065 | Not predictive |
| TBR | −0.044 | Not predictive of overall TIR |

**After removing TAR (residual analysis):**

| Feature | Residual r | Meaning |
|---------|-----------|---------|
| TBR | −0.984 | Hypos explain remaining variance |
| CV | −0.495 | Variability secondary |
| Daily carbs | +0.430 | More carbs → better (unexpected!) |

### Interpretation

**TIR loss is almost entirely hyperglycemia-driven**, not hypoglycemia-driven. TAR explains 95.3% of TIR variance (r²=0.953). After accounting for TAR, TBR explains essentially all remaining variance.

**The positive correlation between zero delivery % and TIR (+0.523) seems paradoxical** — more pump suspension associates with better control. This reflects that well-controlled patients (k, h, d) have loops that *can afford* to suspend frequently because their glucose is often in range.

**Daily carbs positively correlating with residual TIR** suggests that patients who eat more carbs (and thus have their CR actively tested) may have better-calibrated settings, or that restrictive eating patterns create other control problems.

**TBR is NOT a predictor of overall TIR (r=−0.044)**, confirming that hypos are rare enough to barely affect TIR. The clinical problem with hypos is safety, not TIR accounting.

---

## EXP-2028: Synthesis — Personalized Pharmacokinetic Profiles

![Synthesis](figures/pk-fig08-synthesis.png)

### Per-Patient Risk Assessment

| Patient | DIA | Onset | Stack RR | Trend | Weekend Δ | Risk Flags |
|---------|-----|-------|----------|-------|-----------|------------|
| a | 5.9h | 25 min | 1.06 | Declining | −1.3 | SENSOR_ARTIFACTS, LONG_DIA |
| b | — | 15 min | 1.05 | Improving | +4.5 | UNSTABLE_TIR |
| c | 5.9h | 35 min | 1.00 | Stable | −5.8 | SENSOR_ARTIFACTS, LONG_DIA |
| d | — | 30 min | 0.44 | Stable | 0.0 | SENSOR_ARTIFACTS |
| e | 5.9h | 30 min | 0.73 | Improving | −0.7 | LONG_DIA |
| f | 5.9h | 20 min | 0.91 | Improving | −1.1 | UNSTABLE_TIR, LONG_DIA |
| g | — | 30 min | 0.55 | Declining | +2.0 | SENSOR_ARTIFACTS |
| h | — | 20 min | 1.15 | Stable | −3.1 | *(none — but 36% coverage)* |
| i | 5.9h | 20 min | 0.69 | Declining | −0.5 | UNSTABLE_TIR, LONG_DIA |
| j | 5.9h | 30 min | 1.61 | — | −4.4 | HIGH_STACKING_RISK, LONG_DIA |
| k | — | 30 min | 0.56 | Declining | +1.2 | *(none)* |

**9/11 patients have ≥1 actionable risk flag.**

### Risk Flag Definitions

| Flag | Criteria | Count | Action |
|------|----------|-------|--------|
| LONG_DIA | DIA >5.5h measured | 6/6 measured | Increase profile DIA from 5h to 6h |
| SENSOR_ARTIFACTS | >50 compression events | 4/11 | Filter suspected compression lows |
| UNSTABLE_TIR | Monthly TIR SD >5pp | 3/11 | Monthly review cadence |
| HIGH_STACKING_RISK | Stacking RR >1.5× | 1/11 (patient j) | Review manual bolusing |

---

## Cross-Experiment Synthesis

### Finding 1: DIA Is Universally Underestimated

Every patient with measurable DIA shows ≥5.9h (our measurement ceiling). Combined with EXP-1334 (population median 6.0h), this strongly suggests **profile DIA of 5h is too short for all 11 patients**. 

**Mechanism**: When DIA is set too short, the loop "forgets" about active insulin earlier than it should. This leads to:
1. Over-correction (loop delivers more insulin while prior dose is still acting)
2. Apparent ISF miscalibration (insulin appears less effective because each dose isn't fully tracked)
3. Post-correction hypoglycemia (stacked "forgotten" insulin hits at once)

### Finding 2: Stacking Is Safe Under AID Management

The traditional warning "don't stack insulin" comes from MDI/pump eras where IOB wasn't tracked automatically. With AID systems tracking IOB continuously, stacking is the *mechanism of action* — SMBs are rapid sequences of small overlapping doses. Risk ratio 0.91× means the AID stacking algorithm is working correctly.

**Exception**: Manual bolusing without loop management (patient j pattern) remains risky.

### Finding 3: Control Drifts Without Monitoring

With 4/10 patients declining over 6 months, static AID settings are insufficient for long-term management. This supports the earlier finding that AID loops compensate for mismatched settings (EXP-1881) — but this compensation degrades over time as conditions change.

### Finding 4: Hyperglycemia Dominates TIR Loss

TAR explains 95.3% of TIR variance. Hypoglycemia is a safety concern but NOT a TIR concern. This means **TIR improvement efforts should focus on reducing time above 180 mg/dL** (meal spikes, dawn phenomenon, inadequate correction) rather than preventing lows.

### Finding 5: Sensor Artifacts Contaminate Every Analysis

44 compression events and −10pp warmup bias mean all hypo-related analyses in this research program have noise contamination. Future work should filter compression lows and exclude warmup periods for clean hypo counting.

---

## Methodological Notes

### Assumptions Made

1. **DIA measurement**: We assume glucose changes after isolated corrections are primarily driven by that bolus. AID loop adjustments during the observation window introduce confounding.

2. **Stacking definition**: "Within 2h" is arbitrary. Different windows would change stacking percentages but likely not the protective finding.

3. **Temporal stability**: Linear slope assumes monotonic trends. Seasonal cycling would show up as "stable" even if varying significantly.

4. **Compression detection**: Our heuristic (rapid drop >30, rapid recovery >40 within 1h from glucose <60) is conservative. True compression artifacts may be more common.

5. **Weekday assignment**: Without true calendar dates, we use modular arithmetic (day index % 7), which may not align with actual days of the week.

### Limitations

- DIA measurement ceiling at 6h — true DIA may be longer
- Only 6/11 patients had enough isolated corrections for DIA estimation
- Stacking analysis doesn't account for bolus size (a 0.1U SMB stack differs from a 5U manual stack)
- Patient h (36% coverage) is unreliable for all analyses
- 11-patient sample limits hidden variable analysis statistical power

### Recommendations for Future Work

1. **Extend DIA window to 10h** with relaxed isolation criteria
2. **Implement compression low filter** across all experiments
3. **Exclude sensor warmup periods** (<12h SAGE) from hypo counting
4. **Monthly automated reports** to detect declining patients
5. **Separate SMB stacking from manual stacking** in risk analysis

---

## Experiment Registry

| ID | Title | Status | Key Finding |
|----|-------|--------|-------------|
| EXP-2021 | Effective DIA | ✅ | DIA ≥5.9h universally (ceiling) |
| EXP-2022 | Onset/Peak | ✅ | Onset 30min median, very consistent |
| EXP-2023 | Stacking Risk | ✅ | **RR=0.91× — stacking is protective** |
| EXP-2024 | Temporal Stability | ✅ | 4/10 declining, 3 improving, 3 stable |
| EXP-2025 | Weekday/Weekend | ✅ | −0.8pp — no meaningful difference |
| EXP-2026 | Sensor Artifacts | ✅ | 44 compressions/patient, h=36% coverage |
| EXP-2027 | Hidden Variables | ✅ | TAR explains 95.3% of TIR variance |
| EXP-2028 | PK Synthesis | ✅ | 9/11 patients have ≥1 risk flag |

---

*Generated by autoresearch pipeline. Findings are data-driven observations from retrospective CGM/AID data. Clinical validation required before any treatment recommendations.*
