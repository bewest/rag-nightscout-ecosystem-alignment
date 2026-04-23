# EXP-2890 — Robustness Audit of the Braking Signal

**Date:** 2026-04-22
**Stream:** Validation guard before production wiring
**Status:** All robustness checks PASS — ready to wire

## Summary

Before promoting `braking_ratio` to `production/audition_matrix.py`
as a validated fragility signal, audit the EXP-2889 finding
(ρ=−0.711, p=0.001) against:

| Check | Result | Verdict |
| ----- | ------ | ------- |
| ISF sweep 30 → 100 mg/dL/U | ρ ∈ [−0.51, −0.84], all p < 0.03 | PASS |
| Bootstrap 5 000 resamples (ISF=50) | mean ρ = −0.69, 95% CI [−0.95, −0.27], does not cross 0 | PASS |
| Per-patient profile ISF (7/19 known) | ρ = −0.711, p = 0.0006 | PASS (identical) |
| Event-weighted pooling | ρ = −0.258, p ≪ 0.001 (n=2 748) | PASS with caveat (Simpson-safe) |
| Drop 99th-pct extra-insulin outliers | ρ = −0.711, p = 0.0006 | PASS (identical) |

### ISF sensitivity detail

| ISF | ρ | p | cf_severe % |
| --- | - | - | ----------- |
| 30 | −0.505 | 0.027 | 90.6 |
| 40 | −0.615 | 0.005 | 92.9 |
| **50** (baseline) | **−0.711** | **0.0006** | **94.7** |
| 60 | −0.805 | < 0.001 | 95.4 |
| 70 | −0.838 | < 0.001 | 95.8 |
| 100 | −0.801 | < 0.001 | 96.3 |

Saturates at ISF ≈ 70 mg/dL/U because cf_severe approaches 1.0.
Lower ISF makes the counterfactual less severe but rank-order
preserved.  Signal is not an artefact of the chosen ISF.

### Simpson safety

Patient-weighted ρ = −0.71; event-weighted ρ = −0.26.  Same sign,
same significance class, expected magnitude difference (prolific
events dilute patient effect).  This is consistent with EXP-2885's
finding that per-patient aggregation is the correct scale.

### Bootstrap CI

```
mean    = -0.693
median  = -0.706
95% CI  = [-0.947, -0.272]
P(ρ > 0) = 0.000
```

CI floor −0.27 is still a moderately strong negative correlation.
Worst-case sampling realization still supports the construct.

## Decision

**Promote `braking_ratio` to audition_matrix.** Also promote
`counterfactual_severe` and `aid_protection_severe` — they are
computed from the same validated methodology.

Do **not** promote `hidden_leverage` as a composite score;
EXP-2888 showed composite loses information.  Instead keep the
three orthogonal components as separate columns.

## Artifacts

- `tools/cgmencode/exp_robustness_audit_2890.py`
- `externals/experiments/exp-2890_robustness_audit_summary.json`
- `docs/60-research/figures/exp-2890_robustness_audit.png`
