# EXP-2977 — Per-patient implicit `partialApplicationFactor` calibration (Loop)

**Date**: 2026-04-23
**Audience**: Open-source AID code authors
**Scope**: Estimate the implicit Loop `partialApplicationFactor`
per Loop_AB_ON patient from observed SMB / proxy-correction
ratio, looking for bimodal distribution that would distinguish
Constant (0.4) vs `GlucoseBasedApplicationFactorStrategy` (0.2-0.8
sliding) usage.
**What this is NOT**: a recommendation about which strategy to
enable; the estimator carries an ISF-proxy bias documented below.

## Method

For each Loop_AB_ON SMB event with no carbs in prior 120 min and
non-decreasing velocity:

```
proxy_insulinReq(i) = max(bg[i] - 110, 0) / ISF_PROXY
                     + (vel_pre * 30) / ISF_PROXY
est_factor(i) = bolus_smb[i] / proxy_insulinReq(i)
```

ISF_PROXY = 50 mg/dL/U (population mid-point). Per-patient ISF
would shift absolute factor level; the **shape vs BG** is the
diagnostic of interest.

## Result — INCONCLUSIVE about Constant vs GBAF strategy

| patient | n events | factor median | IQR | factor-vs-BG slope (p)        | classification |
|---------|---------:|--------------:|----:|-------------------------------|----------------|
| c       |     6813 |  0.113        | 0.121 | -0.00043 (p=2e-95)         | Mixed |
| d       |     5261 |  0.153        | 0.181 | -0.00229 (p=1e-235)        | Mixed |
| e       |     6931 |  0.144        | 0.189 | -0.00182 (p=4e-248)        | Mixed |
| g       |     4508 |  0.103        | 0.112 | -0.00063 (p=7e-115)        | Mixed |
| i       |     6792 |  0.206        | 0.290 | -0.00128 (p=6e-142)        | Mixed |

All 5 patients show **negative** factor-vs-BG slopes — the
opposite sign from a GBAF-active strategy (which slides
0.2 → 0.8 from BG 90 → 200). Possible interpretations:

1. **Constant strategy with proxy bias**: if `partialApplicationFactor`
   is constant ~0.4 but our proxy `insulinReq(i)` over-estimates
   at high BG (because Loop's RC and IOB also enter), `est_factor`
   would APPEAR to fall with BG. This is the most likely
   interpretation given the consistent negative slope across all
   5 patients.
2. **Velocity-dominated dosing**: if Loop sizes more by velocity
   than by BG-level at high BG, the BG-level term in our proxy
   would dominate `req` while `smb` stays modest, again producing
   negative slope.
3. **Suspend-threshold backoff**: at high BG, Loop reduces sizing
   if it predicts going into hypo from the projected curve — this
   would also produce negative apparent factor.

The **inability to distinguish Constant from GBAF from this
estimator** is itself the finding: the proxy needs per-patient
ISF/CR (oref1-only columns we cannot use for Loop patients) to
yield a clean factor estimate.

## Interpretation for AID authors

- We **cannot confirm** GBAF on/off from observational data alone
  in this cohort.
- If you want to detect GBAF empirically, you need either (a) the
  user's profile JSON (settings audit), or (b) a controlled bolus
  log per cycle (which Loop already writes to the device-status
  payload but is not in our cohort).
- The IQR spread (0.11 – 0.29) is **wider than a constant-factor
  controller would produce** (you'd expect IQR < 0.05 if factor
  were truly fixed at 0.4). So at least **some sliding /
  context-dependence is operating** — but whether it is GBAF or
  another internal modulator (suspend-threshold, IOB cap, max
  cycle dose) cannot be separated here.

## Code refs

- `externals/LoopWorkspace/LoopKit/LoopKit/LoopAlgorithm/DoseMath.swift:120`
  — `asPartialBolus = units * partialApplicationFactor`
- `externals/LoopWorkspace/Loop/Loop/Models/GlucoseBasedApplicationFactorStrategy.swift:14-42`
  — sliding scale 0.2 → 0.8 over BG 90 → 200 mg/dL
- `externals/LoopWorkspace/Loop/Loop/Managers/LoopDataManager.swift:1818-1855`
  — strategy selection (`Constant` vs GBAF)

## Source / data

- Script: `tools/cgmencode/exp_loop_paf_calibration_2977.py`
- Output: `externals/experiments/exp-2977_summary.json`
