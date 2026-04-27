"""EXP-3027 — Leave-one-out validation of EXP-3019 braking-ratio imputation.

Hypothesis
----------
EXP-3019 imputes `braking_ratio` for unknown-controller patients by
controller-median fallback, with prefix heuristic for controller resolution.
The cf_replay_score_v3 stratified safety gate consumes this imputed table.

EXP-3027 asks: how trustworthy is the imputation rule? For each observed
patient, hold them out, recompute the controller medians from the remaining
patients, predict their braking_ratio via the imputation rule, compare to
their observed value.

Pass criteria
-------------
(a) Median absolute error (MAE) on observed braking_ratio ≤ 0.05.
(b) Stratum-agreement rate (low <0.05 / mid 0.05-0.10 / high >=0.10) ≥ 70%.
(c) No catastrophic miss: at most one observed-low patient predicted high
    (these are the safety-relevant flips for cf-replay gating).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

EXP_ID = 'EXP-3027'
ROOT = Path(__file__).resolve().parents[2]
EXP_DIR = ROOT / 'externals' / 'experiments'
PH_SRC = EXP_DIR / 'exp-2886_phenotype.parquet'
OUT_SUMMARY = EXP_DIR / f'{EXP_ID.lower()}_loo_summary.json'
OUT_RESULTS = EXP_DIR / f'{EXP_ID.lower()}_loo_results.csv'

EDGES = (0.05, 0.10)


def stratum(br: float) -> str:
    if pd.isna(br):
        return 'unknown'
    if br < EDGES[0]:
        return 'low'
    if br < EDGES[1]:
        return 'mid'
    return 'high'


def main() -> None:
    ph = pd.read_parquet(PH_SRC)
    obs = ph.dropna(subset=['braking_ratio', 'controller']).copy()
    print(f"[{EXP_ID}] LOO over n={len(obs)} observed-braking patients with known controller")

    rows = []
    for idx, target in obs.iterrows():
        pid = target['patient_id']
        ctrl = target['controller']
        br_obs = float(target['braking_ratio'])

        rest = obs.drop(idx)
        ctrl_median = rest.groupby('controller')['braking_ratio'].median().to_dict()
        cohort_median = float(rest['braking_ratio'].median())
        ctrl_median['OpenAPS'] = ctrl_median.get('AAPS', cohort_median)

        if ctrl in ctrl_median:
            br_pred = float(ctrl_median[ctrl])
            src = f'controller_median:{ctrl}'
        else:
            br_pred = cohort_median
            src = 'cohort_median'

        rows.append({
            'patient_id': pid,
            'controller': ctrl,
            'br_observed': br_obs,
            'br_predicted': br_pred,
            'abs_error': abs(br_pred - br_obs),
            'stratum_observed': stratum(br_obs),
            'stratum_predicted': stratum(br_pred),
            'stratum_match': stratum(br_obs) == stratum(br_pred),
            'imputation_source': src,
        })
    df = pd.DataFrame(rows).sort_values('abs_error', ascending=False)
    df.to_csv(OUT_RESULTS, index=False)
    print(df.to_string(index=False, float_format='%.4f'))

    mae = float(df['abs_error'].median())  # robust median AE
    mean_ae = float(df['abs_error'].mean())
    stratum_agree = float(df['stratum_match'].mean())
    catastrophic_low_to_high = int(((df['stratum_observed'] == 'low') &
                                    (df['stratum_predicted'] == 'high')).sum())
    catastrophic_high_to_low = int(((df['stratum_observed'] == 'high') &
                                    (df['stratum_predicted'] == 'low')).sum())

    pass_mae = mae <= 0.05
    pass_stratum = stratum_agree >= 0.70
    pass_safety = catastrophic_low_to_high <= 1
    verdict = 'PASS' if (pass_mae and pass_stratum and pass_safety) else 'FAIL'

    print(f"\n[{EXP_ID}] Summary:")
    print(f"  Median |error|:           {mae:.4f}  (gate ≤ 0.05) → {'PASS' if pass_mae else 'FAIL'}")
    print(f"  Mean |error|:             {mean_ae:.4f}")
    print(f"  Stratum agreement:        {stratum_agree:.1%}  (gate ≥ 70%) → {'PASS' if pass_stratum else 'FAIL'}")
    print(f"  Catastrophic low→high:    {catastrophic_low_to_high}  (gate ≤ 1) → {'PASS' if pass_safety else 'FAIL'}")
    print(f"  Catastrophic high→low:    {catastrophic_high_to_low}  (informational)")
    print(f"  Verdict: {verdict}")

    summary = {
        'exp_id': EXP_ID,
        'verdict': verdict,
        'n_loo': int(len(df)),
        'median_abs_error': mae,
        'mean_abs_error': mean_ae,
        'stratum_agreement': stratum_agree,
        'catastrophic_low_to_high': catastrophic_low_to_high,
        'catastrophic_high_to_low': catastrophic_high_to_low,
        'gates': {'mae_max': 0.05, 'stratum_agreement_min': 0.70,
                  'catastrophic_low_to_high_max': 1},
        'per_controller_obs_count': df.groupby('controller').size().to_dict(),
        'per_controller_mae': df.groupby('controller')['abs_error'].mean().to_dict(),
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, default=float))
    print(f"  → {OUT_SUMMARY}")


if __name__ == '__main__':
    main()
