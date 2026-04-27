# EXP-3028 — Per-patient (T*, M*) refit with carb-aware proxy

**Date:** 2026-04-26
**Predecessors:** EXP-3017 (clamped per-patient table), EXP-3025-FIX/LOPO (gate=0.10 ship-candidate)
**Verdict:** ✅ **PASS** — verification Δ +0.0327 (lift +0.0082 vs current default), safety_ok=True

## Hypothesis

EXP-3012 fitted per-patient (T*, M*) using a **naive** trough proxy (no carb absorption). EXP-3014 introduced a carb-aware proxy at the controller level. EXP-3017 then clamped M* to 1.0 for high-braking phenotypes. The current production scorer (`cf_replay_score_v3`) evaluates events using the **carb-aware** proxy.

→ **Model/scorer mismatch**: the per-patient table was fitted under one proxy, evaluated under another.

EXP-3028 closes that mismatch by refitting per-patient (T*, M*) on the training stripe using the *same* carb-aware proxy used by the scorer, then applying the EXP-3017 clamp (M=1.0 for high-braking patients), and evaluating on the verification stripe at the new default gate=0.10.

## Method

| Step | Detail |
|---|---|
| Fit set | `exp-3007_ascent_events__training.parquet` (3 593 events / 28 patients) |
| Eval set | `exp-3007_ascent_events__verification.parquet` (2 822 events / 23 patients) |
| Grid | T ∈ {0, 5, 10, 15, 20, 30} min; M ∈ {0.5, 1.0, 1.5, 2.0, 3.0} |
| Selection rule | Min cand_overshoot s.t. Δhypo_pp ≤ +1.0 (matches EXP-3012) |
| Proxy | `carb_aware` (matches scorer; Δ vs EXP-3012 is the proxy) |
| Clamp | EXP-3017: force M=1.0 if `braking_ratio ≥ 0.10` |
| Min events | 30 per patient |

## Result

```
Baseline (raw, no per-patient, no gate):  score=0.6333
Cand gate=0.10 + EXP-3017 (current):      score=0.6577  Δ=+0.0245  safety_ok=True
Cand gate=0.10 + EXP-3028 (carb-fit):     score=0.6660  Δ=+0.0327  safety_ok=True
                                                       lift=+0.0082
```

**PASS criteria:**
- (a) verification safety_ok=True ✅
- (b) Δ_3028 ≥ Δ_3017 (no regression) ✅ (+0.0082 lift)

## Drift from EXP-3017

| Quantity | Value |
|---|---|
| Patients fit (n_3028) | 29 |
| Patients clamped (M→1.0) | 1 |
| `Σ|ΔT|` vs EXP-3017 | 80 min (avg 2.8 min/patient) |
| `Σ|ΔM|` vs EXP-3017 | 2.000 (avg 0.069/patient) |

Under the carb-aware proxy, predicted troughs sit higher (carb absorption adds positive offset) → optimizer has more room to push M closer to 1.0 (less aggressive de-escalation) on patients where the naive proxy was too pessimistic. This is consistent with the modest |ΔM| spread.

## Recovery analysis vs gate=0.15

| Configuration | Verification Δ |
|---|---:|
| gate=0.15 + EXP-3017 (pre-EXP-3025) | +0.0418 |
| gate=0.10 + EXP-3017 (EXP-3025-FIX/LOPO ship) | +0.0245 |
| gate=0.10 + EXP-3028 (this experiment) | **+0.0327** |
| Recovery | **47 % of the +0.0173 lost** |

EXP-3028 cannot fully reclaim the lost composite (the high-stratum hypo regression that motivated lowering the gate is real, not a fitting artifact), but reclaims roughly half. The remaining 53 % gap is the structural cost of the safety constraint itself.

## Operational recommendation

**Do not flip yet.** Two reasons:

1. The verification stripe is now retired (touched 4 times against this policy line); a fresh holdout should validate the table swap before flipping `PER_PATIENT_REC_CLAMPED` in production.
2. Lift is +0.0082 — meaningful but modest. Worth a clean LOPO confirmation similar to EXP-3025-LOPO before production.

Concrete follow-ups in priority order:

- **EXP-3028-LOPO** (cheap): leave-one-patient-out within verification stripe, confirm lift is not carried by 1–2 patients. PASS criterion: ≥ 80 % of LOPO splits keep Δ_3028 ≥ Δ_3017 + 0.005.
- **Fresh future-dated holdout** (preferred): cut a new ≥10-day calendar stripe past 2026-04-19 and re-evaluate.

## Files

- `tools/aid-autoresearch/exp_3028_eventwise_carb_refit.py` (this experiment; fit + eval one-shot)
- `externals/experiments/exp-3028_per_patient_carb_aware.parquet` (gitignored; 29 rows)
- `externals/experiments/exp-3028_summary.json` (gitignored; verdict + verification scores)
