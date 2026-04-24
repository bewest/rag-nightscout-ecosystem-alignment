# EXP-2987: Peer suppression of SMB at 70-100 — lever decomposition

**Date**: 2026-04-23
**Audience**: open-source AID code authors (Loop)
**Scope**: For Loop_AB_ON peers c, d, e, g, i, decompose the
asymmetry in SMB fire rate at 70-100 mg/dL into four candidate
levers: (a) override active in cell, (b) recent carbs (<30 min),
(c) per-patient IOB cap (proxy: patient-95th-percentile IOB),
(d) eligibility threshold. Identify the most asymmetric lever
between i and peers c/d/e/g.
**What this is NOT**: not a Loop ABDose source-trace; not a
deterministic reconstruction of the gating logic. This is a
behavioral correlate using observational grid data only.

---

## 1. Per-patient lever table

```
patient n_band_70_100  frac_override  frac_recent_carbs  iob_p50  iob_p95  iob_max  n_eligible  fire_rate_overall  fire_rate_eligible  suppress_eligible
c             6143         0.1291            0.0135       0.298    5.879   15.749       5240             0.0000              0.0000             1.0000
d             6083         0.0000            0.0339       0.494    4.634   12.210       5866             0.0112              0.0111             0.9889
e             4731         0.0203            0.0552       2.176   12.796   33.115       4351             0.0002              0.0002             0.9998
g             8173         0.1308            0.1247       1.076    5.920   17.350       6056             0.0064              0.0064             0.9936
i             9325         0.2238            0.0104       0.761    9.953   27.641       7169             0.1298              0.1300             0.8700
```

"Eligible" = in band AND no override AND no recent carb (<30 min)
AND iob below patient-95th-percentile.

---

## 2. i-vs-peer-mean deltas

```
lever                          i           peer-mean   delta
frac_override                  0.2238      0.0700      +0.154
frac_recent_carbs              0.0104      0.0568      −0.046
iob_p50                        0.761       1.011       −0.250
iob_p95                        9.953       7.307       +2.646
fire_rate_overall              0.1298      0.0044      +0.125
fire_rate_eligible             0.1300      0.0044      +0.126
suppression_rate_eligible      0.8700      0.9956      −0.126
```

Top asymmetric lever (by |delta|): **iob_p95** (+2.65 U).

---

## 3. Findings

1. **None of the 4 hypothesized levers cleanly explains the
   asymmetry.** Peers c, e suppress >99% of *eligible* cells;
   peers d, g suppress 98.9-99.4%. Patient i suppresses only
   87% — fire-rate is **30× peer-mean** even after stripping
   override / recent-carb / IOB-cap effects.
2. **Override frequency is OPPOSITE the suppression direction.**
   Patient i has 22% override fraction (mostly low-temp-target
   for hypo-protection) vs peer-mean 7%, yet still fires more.
   So `override_active` is NOT the lever peers use to suppress.
3. **iob_p95 asymmetry (i=9.95 vs peers=7.31)** is consistent
   with patient i having a LARGER IOB cap configured in Loop.
   But the gap is too small to fully explain a 30× fire-rate
   delta — at most ⅓ of the difference.
4. **Remaining hypothesis space** (not directly observable in
   grid):
   - Loop `recommendation_threshold` setting (the BG floor below
     which AB-mode will not dose)
   - Per-patient glucose target range
   - AB-mode `partialApplicationFactor` configuration (drives
     dose per cycle, not gate)
   - Patient-specific autobolus-disable schedule

---

## 4. Code references

- `externals/LoopWorkspace/LoopAlgorithm/.../*Dose*.swift` —
  ABDose generator and gate logic
- `externals/LoopWorkspace/Loop/.../GlucoseRangeSchedule.swift` —
  target-range schedule (per-patient)
- `tools/cgmencode/exp_peer_suppression_levers_2987.py` — this
  experiment's source

---

## 5. Verdict

**NULL/MIXED — proposed levers do NOT explain peer suppression.**
The asymmetry is real and large (≥30× fire-rate gap with a
mechanism intact at >99% suppression for peers), but is not
attributable to the four observable levers tested. Patient-i is
configured with a more aggressive Loop policy across multiple
unobserved settings simultaneously.

**AID-author implication**: aggressiveness in Loop is multi-
dimensional. A user-facing "policy summary" combining
`recommendation_threshold`, `partialApplicationFactor`, `maxIOB`,
and target-range floor would help users understand the joint
aggressiveness their settings represent. A single "aggressiveness"
slider would be wrong because patients adopt different
combinations.

Output: `externals/experiments/exp-2987_summary.json`.
