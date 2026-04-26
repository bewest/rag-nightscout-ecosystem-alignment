# EXP-3015b — Braking-mode flag (drop / m_unity / none) on cf_replay_score_v3

**Date:** 2026-04-26
**Hypothesis:** Per EXP-3016, the high-braking phenotype stratum benefits from
the timing shift (T = +30 min) but *not* from the magnitude reduction
(M = 0.5×). The binary "drop high-braking patients" gate from EXP-3013 is too
coarse: it sacrifices the timing signal for those patients. A per-axis gate
that retains T but forces M = 1.0 should preserve the timing benefit while
withdrawing the unwanted magnitude pressure.
**Verdict:** Implemented; behaves as predicted; safety semantics need
clarification (see below).

## What changed

`cf_replay_score_v3.py` previously had `--braking-gate` as a single binary
"drop the high-braking subset" flag. Added `--braking-mode` with three values:

| Mode      | Behaviour for patients with `braking_ratio ≥ gate`                |
|-----------|--------------------------------------------------------------------|
| `drop`    | Remove from the cohort entirely (legacy EXP-3013 gate behaviour). |
| `m_unity` | Keep in cohort; force `M = 1.0` while leaving `T` at config or `T*`. |
| `none`    | Gate has no effect (sanity / debugging).                           |

Default is now `m_unity` per EXP-3016's per-axis recommendation.

## 4-mode smoke results (Phase 4 cohort)

| Mode                 | events used | M=1.0 forced | score  | safety  |
|----------------------|------------:|-------------:|-------:|---------|
| baseline (1.0, 0)    | 17 919      | —            | 0.6888 | FAIL    |
| frontier (0.5, +30)  | 17 919      | —            | 0.7088 | pass    |
| per-patient + drop   | 11 788      | —            | 0.7031 | pass    |
| per-patient + m_unity| 17 919      | 6 131        | 0.7051 | FAIL    |

`m_unity` retains all events (does not drop any), forces 6 131 events for
high-braking patients to baseline magnitude, and produces a slightly higher
composite score than `drop` (0.7051 > 0.7031) because it also retains the
remaining 6 131 events at a non-degenerate T = +30 timing shift.

## Why does m_unity fail the safety gate?

This is intentional and consistent.

The cohort safety gate reads `max(per-controller hypo rate)`. Forcing
`M = 1.0` for high-braking patients reverts their cf-replay forecast toward
the *baseline* dosing pattern — the same pattern that fails the gate at
4.29 % Trio hypo. So m_unity faithfully reports: "if you do nothing magnitude
reducing for high-brakers, you inherit the baseline tail risk for them."

The drop mode passes the gate because it removes those patients entirely
from the per-controller hypo aggregation — the gate becomes silent on them.

**Clinical reading.** Neither of these is the right population gate. The
*correct* clinical test is: "for the responsive (non-high-braking) subset,
does the policy improve outcomes without introducing population-level harm?"
That maps onto `drop` mode for cohort scoring + `m_unity` for individualised
deployment (i.e. report the recommendation but do not advertise a hypo
reduction for the high-braking subset; their recommendation is "T = +30 only,
M unchanged").

## Open issue: regenerate per-patient parquet

The current `externals/experiments/exp-3012_per_patient.parquet` was computed
under the EXP-3012 individual-gate assumption that any `(T*, M*)` passing the
1 pp Δhypo gate against that patient's own baseline is acceptable. EXP-3016
shows this is over-promising for high-braking patients (synthetic frontier
flips to M = 1.0 in that stratum). A future iteration should either:

1. Regenerate the parquet with `M*` clamped to 1.0 when `braking_ratio ≥ 0.10`,
   so `m_unity` mode becomes a no-op consistency check, or
2. Add an EXP-3012b column `rec_M_mult_after_phenotype` that already encodes
   the clamp, and have v3 prefer that column when present.

Tracked as a follow-up but not gating Phase 4.

## Files

- Code: `tools/aid-autoresearch/cf_replay_score_v3.py` (added `--braking-mode`)
- Test: `tools/aid-autoresearch/test_cf_replay_score_v3.py` (4-mode smoke)
- Source: this report.
