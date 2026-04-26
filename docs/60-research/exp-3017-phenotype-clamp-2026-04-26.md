# EXP-3017 — Phenotype-clamped per-patient parquet (closes EXP-3015b loop)

**Date:** 2026-04-26
**Hypothesis:** Pre-applying the EXP-3016 phenotype clamp (force M*=1.0 when
braking_ratio ≥ 0.10) directly to the EXP-3012 per-patient parquet should
make the runtime `--braking-mode m_unity` gate a no-op consistency check —
i.e. `m_unity` and `none` should produce identical scores when consuming the
clamped parquet.
**Verdict:** Confirmed. Clamped+m_unity == Clamped+none == 0.7051 exactly.

## Method

`tools/cgmencode/autoresearch_cf/exp_3017_phenotype_clamp.py` reads
`exp-3012_per_patient.parquet`, joins phenotype's `braking_ratio`, and
overwrites `rec_M_mult` to 1.0 wherever `braking_ratio ≥ 0.10`. Original
value is retained as `rec_M_mult_pre_clamp`. Output:
`externals/experiments/exp-3017_per_patient_clamped.parquet`.

`cf_replay_score_v3.py` gains `--per-patient-source {raw,clamped}` (default
`clamped`).

## Clamp footprint

| Quantity                              | Value |
|---------------------------------------|------:|
| Patients in EXP-3012 parquet          |    29 |
| Patients with braking_ratio ≥ 0.10    |     7 |
| Patients whose M* changed (0.5 → 1.0) |     7 |
| M=0.5 distribution before clamp       |    22 |
| M=0.5 distribution after clamp        |    15 |

All 7 high-braking patients had previously been recommended M=0.5 by the
EXP-3012 individual gate. The remaining 22 high-braking-or-low-braking
patients keep their EXP-3012 (T*, M*).

## Consistency check (Phase 4 cohort, carb-aware proxy)

| Source × Mode               | events used | M=1.0 forced | score  | safety |
|-----------------------------|------------:|-------------:|-------:|--------|
| raw + m_unity               |      17 919 |        6 131 | 0.7051 | FAIL   |
| **clamped + m_unity**       |      17 919 |        6 131 | **0.7051** | FAIL   |
| **clamped + none (no gate)**|      17 919 |            0 | **0.7051** | FAIL   |
| clamped + drop              |      11 788 |            — | 0.7031 | pass   |

`clamped + m_unity` and `clamped + none` produce **bit-identical** composite
scores. This is the desired invariant: the clamp moves the gate decision
into the parquet, so the runtime `m_unity` flag is now a redundant safety
net rather than a behaviour-modifying flag. The runtime gate remains useful
for `drop` mode (dropping events from the cohort score is not pre-bakeable).

`raw + m_unity` and `clamped + m_unity` also match (0.7051) — confirming
the clamp simply pre-bakes the runtime override.

## What this means for downstream consumers

- **Default v3 invocation** now uses the clamped parquet automatically.
- Existing call sites that passed `--per-patient` get the EXP-3016 phenotype
  refinement for free; no flag changes required.
- For comparison/regression work, `--per-patient-source raw` reproduces the
  pre-clamp behaviour.
- The 4-mode smoke test `test_cf_replay_score_v3.py` continues to pass
  (it doesn't pin `--per-patient-source` and so picks up the clamped default).

## Open follow-up

The cohort safety gate remains FAIL under `m_unity`/`none` because forcing
M=1.0 for high-braking patients re-exposes baseline tail risk on those
patients. This is **not** a bug in the clamp — it accurately reports that
the high-braking subset has no safe magnitude reduction available. A
*subset-stratified* safety gate (one threshold per phenotype stratum) would
distinguish this from the deployable `drop` mode. Tracked as a Phase 5
candidate.

## Files

- New: `tools/cgmencode/autoresearch_cf/exp_3017_phenotype_clamp.py`
- New: `externals/experiments/exp-3017_per_patient_clamped.parquet` (gitignored)
- Modified: `tools/aid-autoresearch/cf_replay_score_v3.py` (`--per-patient-source` flag, default `clamped`)
- Source: this report.
