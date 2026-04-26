"""EXP-3000 — Baseline re-run of EXP-2889 via the new replay engine.

Validates that the refactored ``autoresearch_cf.replay`` engine reproduces
EXP-2889's headline numbers (pop observed=36.2%, pop counterfactual=94.7%,
braking_ratio rho=-0.711). If verdict='match', subsequent iterations have a
verified baseline to diff against.

Usage::

    python3 -m tools.cgmencode.autoresearch_cf.exp_3000_baseline
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from scipy import stats

from tools.cgmencode.autoresearch_cf import replay
from tools.cgmencode.autoresearch_cf.figures import figure_three_panel

EXP_ID = 'EXP-3000'
OUT = Path('externals/experiments')
FIG = Path('docs/60-research/figures') / f'{EXP_ID.lower()}_baseline.png'


def main() -> None:
    events, phenotype, profiles = replay.load_inputs()
    config = replay.ReplayConfig(
        name='baseline_pop_inst_linear',
        isf_source=replay.isf_source_population,
        insulin_kernel=replay.kernel_instantaneous,
        duration_model=replay.duration_linear,
        isf_source_name='population_isf50',
        kernel_name='instantaneous',
        duration_name='linear',
    )
    res = replay.run_replay(events, profiles, phenotype, config)

    # Reproduce the EXP-2889 correlation block
    pp = res.per_patient
    valid = pp.dropna(subset=['braking_ratio', 'cf_severe',
                              'hidden_leverage', 'stack_score'])
    correlations = {}
    for var in ['braking_ratio', 'hidden_leverage', 'stack_score',
                'counter_reg_intercept']:
        if var not in valid.columns:
            continue
        for outcome in ['cf_severe', 'cf_hypo', 'aid_protection_severe']:
            if outcome not in valid.columns:
                continue
            v = valid.dropna(subset=[var, outcome])
            if len(v) < 5:
                continue
            r, p = stats.spearmanr(v[var], v[outcome])
            correlations[f'{var}__{outcome}'] = {
                'rho': float(r), 'p': float(p), 'n': int(len(v))}

    s = res.summary
    print(f"[{EXP_ID}] {s['config_name']}: "
          f"pop_obs_severe={s['pop_observed_severe']:.3%} "
          f"pop_cf_severe={s['pop_counterfactual_severe']:.3%} "
          f"protection={s['aid_protection_severe_abs']:.3%}")
    for k, v in correlations.items():
        marker = '*' if v['p'] < 0.05 else ' '
        print(f"  {marker} {k:46s} rho={v['rho']:+.3f} p={v['p']:.3f} n={v['n']}")

    # Compare to EXP-2889 published figures
    expected_obs = 0.362
    expected_cf = 0.947
    drift = abs(s['pop_observed_severe'] - expected_obs)
    cf_drift = abs(s['pop_counterfactual_severe'] - expected_cf)
    if drift < 0.02 and cf_drift < 0.02:
        verdict = 'baseline_match'
        notes = (f'matches EXP-2889 within 2pp (obs drift {drift:.3f}, '
                 f'cf drift {cf_drift:.3f})')
    else:
        verdict = 'baseline_drift'
        notes = (f'differs from EXP-2889 (obs drift {drift:.3f}, '
                 f'cf drift {cf_drift:.3f})')

    OUT.mkdir(parents=True, exist_ok=True)
    res.events.to_parquet(OUT / f'{EXP_ID.lower()}_events.parquet')
    res.per_patient.to_parquet(OUT / f'{EXP_ID.lower()}_per_patient.parquet')
    summary_full = {**s, 'verdict': verdict, 'notes': notes,
                    'correlations': correlations}
    (OUT / f'{EXP_ID.lower()}_summary.json').write_text(
        json.dumps(summary_full, indent=2))

    figure_three_panel(res.per_patient,
                       title=f'{EXP_ID} baseline (pop ISF, instantaneous, linear)',
                       out_path=FIG)
    replay.record_iteration(EXP_ID, res, verdict=verdict, notes=notes)
    print(f"[{EXP_ID}] verdict={verdict}  →  {FIG}")


if __name__ == '__main__':
    main()
