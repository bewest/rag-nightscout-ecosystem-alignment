# EXP-3020 — cf-replay-v3 harness sweep: gate × mode × proxy × source

**Date:** 2026-04-26
**Trace:** EXP-3015..3019 productionised → harness (this experiment).
**Tool:** `tools/aid-autoresearch/cf_replay_v3_harness.py`.
**Cohort:** 31 patients, 17 919 ascent events, stratified safety gate.

## Goal

Wire the productionised v3 scorer into a continuous autoresearch loop and
sweep its remaining cohort-level free knobs (gate × mode × proxy × source)
to verify that the Phase-5 default invocation is still optimal — or find a
better one.

## Method

The harness runs cf_replay_score_v3 over a 5×2×2×2 = 40-cell grid plus 2
references (baseline M=1/T=0; uniform frontier M=0.5/T=+30) and records
score, per-stratum + cohort safety, and event accounting to TSV. Every
cell uses `--per-patient --safety-mode stratified --phenotype-source
imputed` (the Phase 5 defaults).

| Axis | Values |
|---|---|
| `--braking-gate` | 0.05, 0.075, 0.10, 0.125, 0.15 |
| `--braking-mode` | drop, m_unity |
| `--proxy` | carb_aware, worst_case |
| `--per-patient-source` | raw (EXP-3012), clamped (EXP-3017) |

## Results

**Safe cells: 17 / 42.** Top-12 safe by score:

| rank | gate  | mode    | proxy      | src     | score  | n_used | n_drop | n_mu  |
|-----:|------:|---------|------------|---------|-------:|-------:|-------:|------:|
| 1    | 0.05  | drop    | carb_aware | raw     | 0.7160 |  4 838 | 13 081 |     0 |
| 1    | 0.05  | drop    | carb_aware | clamped | 0.7160 |  4 838 | 13 081 |     0 |
| 3    | 0.15  | drop    | carb_aware | raw     | 0.7150 | 12 969 |  4 950 |     0 |
| 4    | 0.125 | drop    | carb_aware | raw     | 0.7114 | 12 233 |  5 686 |     0 |
| ref  | —     | uniform | carb_aware | n/a     | 0.7088 | 17 919 |      0 |     0 |
| 5    | 0.075 | drop    | carb_aware | raw     | 0.7083 |  9 497 |  8 422 |     0 |
| 5    | 0.075 | drop    | carb_aware | clamped | 0.7083 |  9 497 |  8 422 |     0 |
| 7    | 0.15  | m_unity | carb_aware | raw     | 0.7082 | 17 919 |      0 | 4 950 |
| 8    | 0.125 | m_unity | carb_aware | raw     | 0.7075 | 17 919 |      0 | 5 686 |
| 8    | 0.10  | drop    | carb_aware | raw     | 0.7075 | 11 551 |  6 368 |     0 |
| 8    | 0.10  | drop    | carb_aware | clamped | 0.7075 | 11 551 |  6 368 |     0 |
| 11   | 0.10  | m_unity | carb_aware | raw     | 0.7050 | 17 919 |      0 | 6 368 |

Phase-5 default (clamped + m_unity + gate=0.10) sits at 0.7050 (rank ≈ 12).

## Findings

1. **`worst_case` proxy is unsafe** under stratified gate at every cell.
   Confirms EXP-3014: worst_case over-counts hypo events that carb-rescue
   would have prevented, tripping the per-stratum ceiling.
2. **`raw` beats `clamped`** for `m_unity` mode at gate ≥ 0.125. The clamp
   pre-forces M = 1.0 for ≈ 7 high-braking patients; with `m_unity` the
   gate would have done the same job, so `clamped` is double-clamping —
   discarding M\* < 1 information for low-braking patients in the same
   bins. **Recommendation: drop `clamped` from default; use `raw` + a gate.**
3. **Gate = 0.15 dominates gate = 0.10** for `m_unity` (0.7082 vs 0.7050,
   same retention). The clamp at gate = 0.10 was over-conservative; raising
   the gate to 0.15 lets two patients who actually respond well to M\* < 1
   keep their per-patient recommendation.
4. **Drop mode at gate = 0.15 + raw** gives the highest score with full
   safety (0.7150) at the cost of losing 4 950 events (28 % of cohort).
   That cohort is the high-braking population where `m_unity` would force
   them to baseline anyway — the drop is a fair representation of "we can't
   currently improve these patients."
5. **Top-1 cell (gate = 0.05, drop) is selection-biased**. Only 4 838
   events survive (27 % of cohort); the score reflects an easy subset.
   Not a deployable.

## Updated deployable shortlist

| Variant | Invocation | Score | Events | Comment |
|---|---|--:|--:|---|
| Phase-5 closeout default | `--per-patient --braking-gate --braking-mode m_unity --safety-mode stratified` (clamped+imputed defaults) | 0.7050 | 17 919 | Conservative; clamp + m_unity double-clamps. |
| **EXP-3020 recommended (full-retention)** | `--per-patient --per-patient-source raw --braking-gate 0.15 --braking-mode m_unity --safety-mode stratified` | **0.7082** | 17 919 | +0.32 pp over closeout default; strict superset. |
| EXP-3020 alternative (high-confidence-only) | `--per-patient --per-patient-source raw --braking-gate 0.15 --braking-mode drop --safety-mode stratified` | 0.7150 | 12 969 | +1.00 pp over closeout default; declines to recommend on 4 950 events of high-braking patients. |

## Follow-ups

- **Update Phase 5 closeout default**: switch the headline invocation to
  the EXP-3020 recommendation. Keep the closeout default available as a
  conservative fallback.
- Drop `--per-patient-source clamped` as the default once clamp is
  redundant with the gate. (The clamped parquet is preserved for
  reproducibility but no longer the recommended source.)
- Re-run the harness whenever EXP-3012 (per-patient lookup) is re-fit
  or new patients enter the cohort.

## Reproducibility

```bash
python3 tools/aid-autoresearch/cf_replay_v3_harness.py \
    --safety-mode stratified --refine --random-iterations 10 --json \
  > externals/experiments/cf_replay_v3_harness_$(date -u +%Y%m%dT%H%M%SZ).json
```

TSV from the original grid run: `externals/experiments/cf_replay_v3_harness_20260426T192303Z.tsv`.
TSV from the extended grid + refine + random run: `externals/experiments/cf_replay_v3_harness_20260426T192900Z.tsv`.

## Addendum (extended harness, refine + random)

A second run added a 1D refine sweep around the unconstrained winner
plus 10 random samples in `braking_gate ∈ [0.04, 0.30]`. Two findings:

1. **m_unity score plateau above gate ≈ 0.15.** The candidates
   `(gate = 0.1568, 0.2262, 0.2889) × m_unity × raw × carb_aware` all
   produce score = 0.7082 — bit-identical to gate = 0.15. The gate is at
   a knee: every patient with `braking_ratio ≥ 0.15` that the gate
   catches keeps catching them as the threshold rises further.
2. **drop-mode global maximum at gate = 0.15.** Drop-mode score peaks at
   0.7150 (gate = 0.15 / 12 969 events); both lower and higher gates score
   strictly worse with the same retention bias. Confirms the choice of
   0.15 as the deployable gate.

Selection bias confirmed:  the unconstrained `--refine` seed cell at
gate = 0.05 / 4 838 events scores 0.7160, but only on ≈ 27 % of the cohort.
The harness now has `--min-retention 0.80` (default) which selects the
deployable winner from cells using ≥ 80 % of the cohort and reports the
unconstrained winner separately as `raw_winner` for diagnostic purposes.
