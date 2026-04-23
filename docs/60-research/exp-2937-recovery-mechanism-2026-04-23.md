# EXP-2937 — Sustained-high recovery mechanism decomposition

**Date:** 2026-04-23
**Status:** Closed
**Scope:** Design-feature characterisation for open-source AID author
audience. NOT therapy advice.

## Question

EXP-2934 established that within high_lag (BG >154 mg/dL one hour ago)
oref1 holds 64.26 % TIR vs Loop_AB_ON 46.60 % vs Loop_AB_OFF 34.45 %.
This is the *recovery* mechanism. What does each design *do* during
sustained-high windows that produces the gap?

## Method

Find isolated sustained-high entries: BG crosses >180 mg/dL from below
with the prior 30 min <180 and **no carbs in the prior 60 min**.
This isolates correction-loop behaviour from PP / meal handling.

For the next 60 min characterise:
- SMB count and total
- Mean SMB size
- First-SMB latency
- BG decline rate (mg/dL/min, positive = BG dropped)
- Recovery probability (BG <180 at end of window)

Patients require ≥5 such events to enter per-design averages
(16 patients qualify; 3 242 events total).

## Results

### Per-patient means by design

| design       | n_pat | events_per_pat | smb_count | smb_total_u | smb_mean_u | first_lat_min | decline_mgdl_min | recovered_% |
|--------------|------:|---------------:|----------:|------------:|-----------:|--------------:|-----------------:|------------:|
| Loop_AB_OFF  |     2 |          282.0 |      0.00 |        0.00 |       n/a  |        n/a    |           **−0.38** |    29.64    |
| Loop_AB_ON   |     5 |          287.4 |      4.31 |        1.76 |      0.43  |        3.22   |           −0.17    |    35.67    |
| oref1        |     9 |          137.9 |      2.82 |        1.14 |      0.50  |        5.75   |           **+0.21** |    **56.96** |

### Bootstrap 2000-iter contrasts (oref1 − design)

| metric         | vs Loop_AB_ON               | vs Loop_AB_OFF              |
|----------------|----------------------------:|----------------------------:|
| smb_count      |   **−1.50** [−2.35, −0.54] ★ |   +2.82 [+2.17, +3.50] ★    |
| smb_total_u    |   −0.61 [−1.52, +0.16]      |   +1.14 [+0.86, +1.41] ★    |
| first_lat_min  |   **+2.53** [+0.74, +4.25] ★ |   n/a (no SMBs)             |
| decline        |   +0.38 [+0.18, +0.60] ★    |   +0.59 [+0.39, +0.80] ★    |
| recovered      |   **+0.21** [+0.11, +0.31] ★ |   +0.27 [+0.17, +0.38] ★    |

## Interpretation

Three findings overturn intuitions about the recovery mechanism:

### 1. Loop_AB_OFF: correction loop is structurally absent
Loop_AB_OFF delivers **zero SMBs** during isolated correction windows.
BG continues to rise (decline −0.38 mg/dL/min). Recovery is 29.64 % —
roughly the rate at which spontaneous physiology pulls BG back without
controller help. The sole correction lever is basal cuts, which cannot
*lower* BG, only stop adding insulin. This is the open-loop branch of
Loop. AID-author lever: enable autobolus by default for high-glucose
correction.

### 2. Loop_AB_ON: more SMBs, faster, less effective
Loop_AB_ON delivers **more SMBs** than oref1 (4.31 vs 2.82, sig)
**faster** (first_lat 3.22 vs 5.75 min, sig) at **comparable total
dose** (1.76 vs 1.14 U, not sig). Yet decline rate is −0.17
(BG still rising) vs oref1 +0.21 mg/dL/min (BG dropping), and
recovery probability is **20 pp lower** (35.67 % vs 56.96 %, sig).

The recovery edge is **NOT cadence**. The recovery edge is **NOT first-
fire latency**. Loop AB_ON wins both of these and still loses recovery.

### 3. The lever is correction sizing / dynamic-ISF
oref1 fires fewer, slightly larger (0.50 vs 0.43 U mean) SMBs at higher
latency, and they're more effective per unit. The most parsimonious
explanation: oref1's correction dose is sized to BG and BG velocity
(dynamic-ISF + autosens), so each SMB is calibrated to the metabolic
load actually present. Loop's autobolus dose is sized by IOB shortfall
relative to a model BG forecast; it under-dose-corrects when BG
velocity is positive at high BG.

This is a **separate lever** from the PP dose-shape mechanism
(EXP-2930). EXP-2930 said: "front-load PP dose into 0–60 min." EXP-2937
says: "during sustained-high correction-only windows, dose to BG-and-
velocity, not to IOB-shortfall."

## Mechanism summary across the arc

| Window type           | Loop offence | Loop defence | oref1 offence | oref1 defence |
|-----------------------|:------------:|:------------:|:-------------:|:-------------:|
| PP onset (0-60 min)   |  AB_ON only  |   n/a        |  UAM front-load |  n/a        |
| PP late (60-240 min)  |  basal cut + smaller SMBs   |  n/a   |  continued SMB cadence | n/a |
| Sustained-high (no carbs) |  AB only |  cadence-driven, under-sized | n/a | dynamic-ISF + velocity-sized SMBs |

## AID-author actionable order (refined)

1. Add UAM / glucose-appearance detector + dynamic-ISF (EXP-2930).
2. Implement SMB-as-correction during sustained-high (EXP-2937).
3. Size correction SMBs to BG **and** BG velocity, not just to IOB
   shortfall vs forecast (EXP-2937).
4. Enable autobolus by default for AID-OFF correction loops
   (EXP-2929 + EXP-2937 finding 1).
5. Basal-cut latency (already characterised, EXP-2918).

## What this is NOT

- NOT a per-patient therapy recommendation. Patients vary, and
  configuration choices respond to many constraints.
- NOT a claim Loop's algorithm is "wrong" — Loop is provably designed
  for predictive correction (forecast-aware bolus sizing). The
  observation is that for sustained-high correction-only windows in
  this cohort the forecast-based sizing under-corrects.
- NOT a mechanism attribution to a single algorithm parameter; the
  finding is consistent with several oref1 features acting together
  (dynamic-ISF, autosens, SMB ratio, BG-anchored correction).

## Cross-reference

- EXP-2934: outcome decomposition (avoidance vs recovery)
- EXP-2930: PP dose-shape mechanism (offence)
- EXP-2918: basal-cut latency (defence-side temporal)
- Synthesis: synthesis-design-comparison-2026-04-23.md
- Guard #6 already-applied implicitly (high_lag is a state stratum)
- Guard #8 already-applied (carb-guard 60 min isolates correction
  from event-anchored confound)
