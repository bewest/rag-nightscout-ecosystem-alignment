"""EXP-3017 — Phenotype-clamped per-patient parquet.

Post-processes EXP-3012's per-patient (T*, M*) parquet to enforce the
EXP-3016 finding: high-braking patients (braking_ratio >= 0.10) flip to
M = 1.0 on synthetic frontiers. We clamp M* to 1.0 for those patients while
retaining T*. The resulting parquet, when consumed by cf_replay_score_v3 in
per-patient mode, makes `--braking-mode m_unity` a no-op consistency check
on the high-braking subset.

Outputs
-------
externals/experiments/exp-3017_per_patient_clamped.parquet
externals/experiments/exp-3017_summary.json
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

EXP_ID = 'EXP-3017'
SRC = Path('externals/experiments/exp-3012_per_patient.parquet')
PHENO = Path('externals/experiments/exp-2886_phenotype.parquet')
OUT = Path('externals/experiments')
GATE = 0.10


def main() -> None:
    rec = pd.read_parquet(SRC)
    ph = pd.read_parquet(PHENO)[['patient_id', 'braking_ratio']]
    merged = rec.merge(ph, on='patient_id', how='left')

    pre = merged[['rec_T_min', 'rec_M_mult']].copy()
    high = merged['braking_ratio'].fillna(-1) >= GATE
    n_clamped = int(high.sum())

    merged['rec_M_mult_pre_clamp'] = merged['rec_M_mult']
    merged.loc[high, 'rec_M_mult'] = 1.0
    merged['phenotype_clamped'] = high

    out_path = OUT / f'{EXP_ID.lower()}_per_patient_clamped.parquet'
    merged.to_parquet(out_path)

    summary = {
        'n_total': int(len(merged)),
        'n_high_braking': n_clamped,
        'n_clamped_M_change': int(((pre['rec_M_mult'] != merged['rec_M_mult'])).sum()),
        'M_distribution_before': {
            f'{m:.1f}': int(n) for m, n in pre['rec_M_mult'].value_counts().items()
        },
        'M_distribution_after': {
            f'{m:.1f}': int(n) for m, n in merged['rec_M_mult'].value_counts().items()
        },
        'gate': GATE,
        'output': str(out_path),
    }
    (OUT / f'{EXP_ID.lower()}_summary.json').write_text(
        json.dumps(summary, indent=2, default=float))
    print(f"[{EXP_ID}] {n_clamped}/{len(merged)} patients flagged high-braking; "
          f"{summary['n_clamped_M_change']} had M* changed to 1.0")
    print(f"  M before: {summary['M_distribution_before']}")
    print(f"  M after:  {summary['M_distribution_after']}")
    print(f"  → {out_path}")


if __name__ == '__main__':
    main()
