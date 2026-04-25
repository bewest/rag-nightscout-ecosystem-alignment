"""EXP-3001 — Per-patient profile ISF replaces population ISF=50.

Hypothesis: rank-order of cf_severe per patient is preserved (EXP-2889
explicitly framed pop ISF as adequate for ranking) but population magnitudes
shift because some patients have ISF much higher or lower than 50 mg/dL/U.

Verdict criterion:
- ``rank_preserved`` if Spearman(cf_severe_baseline, cf_severe_per_pt) > 0.85
- ``rank_disturbed`` otherwise (would invalidate EXP-2889 conclusions)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from scipy import stats

from tools.cgmencode.autoresearch_cf import replay
from tools.cgmencode.autoresearch_cf.figures import figure_three_panel

EXP_ID = 'EXP-3001'
OUT = Path('externals/experiments')
FIG = Path('docs/60-research/figures') / f'{EXP_ID.lower()}_per_patient_isf.png'
BASELINE_PP = OUT / 'exp-3000_per_patient.parquet'


def main() -> None:
    events, phenotype, profiles = replay.load_inputs()
    config = replay.ReplayConfig(
        name='per_patient_isf_inst_linear',
        isf_source=replay.isf_source_profile,
        insulin_kernel=replay.kernel_instantaneous,
        duration_model=replay.duration_linear,
        isf_source_name='profile_isf',
        kernel_name='instantaneous',
        duration_name='linear',
    )
    res = replay.run_replay(events, profiles, phenotype, config)
    s = res.summary
    pp = res.per_patient

    # Compare to baseline rank order
    baseline = pd.read_parquet(BASELINE_PP)[['patient_id', 'cf_severe',
                                             'isf_used']]
    baseline = baseline.rename(columns={'cf_severe': 'cf_severe_baseline',
                                        'isf_used': 'isf_baseline'})
    cmp = pp.merge(baseline, on='patient_id', how='inner')
    rho_rank, p_rank = stats.spearmanr(cmp['cf_severe_baseline'],
                                       cmp['cf_severe'])
    rho_braking, p_braking = stats.spearmanr(
        pp.dropna(subset=['braking_ratio'])['braking_ratio'],
        pp.dropna(subset=['braking_ratio'])['cf_severe'])

    isf_distribution = (pp.groupby('patient_id')['isf_used']
                          .first().describe().to_dict())

    # Per-patient ISF used (table for the report)
    per_pt_table = pp[['patient_id', 'isf_used', 'obs_severe',
                       'cf_severe', 'aid_protection_severe']].sort_values(
        'isf_used').to_dict(orient='records')

    if rho_rank >= 0.85:
        verdict = 'rank_preserved'
        notes = (f'rank vs baseline rho={rho_rank:.3f}, '
                 f'braking_ratio rho={rho_braking:+.3f} '
                 f'(baseline -0.711)')
    else:
        verdict = 'rank_disturbed'
        notes = (f'WARNING rank vs baseline rho={rho_rank:.3f} <0.85; '
                 f'EXP-2889 conclusions may be ISF-dependent')

    print(f"[{EXP_ID}] {s['config_name']}: "
          f"pop_obs={s['pop_observed_severe']:.3%} "
          f"pop_cf={s['pop_counterfactual_severe']:.3%} "
          f"protection={s['aid_protection_severe_abs']:.3%} "
          f"mean_isf_used={s['mean_isf_used']:.1f}")
    print(f"  rank-vs-baseline Spearman rho={rho_rank:+.3f} p={p_rank:.3f}")
    print(f"  braking_ratio vs cf_severe   rho={rho_braking:+.3f} "
          f"p={p_braking:.3f} (baseline -0.711)")

    OUT.mkdir(parents=True, exist_ok=True)
    res.events.to_parquet(OUT / f'{EXP_ID.lower()}_events.parquet')
    res.per_patient.to_parquet(OUT / f'{EXP_ID.lower()}_per_patient.parquet')
    summary = {**s, 'verdict': verdict, 'notes': notes,
               'rank_vs_baseline_rho': float(rho_rank),
               'rank_vs_baseline_p': float(p_rank),
               'braking_ratio_rho': float(rho_braking),
               'braking_ratio_p': float(p_braking),
               'isf_distribution': isf_distribution,
               'per_patient_isf_used': per_pt_table}
    (OUT / f'{EXP_ID.lower()}_summary.json').write_text(
        json.dumps(summary, indent=2, default=float))

    figure_three_panel(res.per_patient,
                       title=f'{EXP_ID} per-patient ISF (instantaneous, linear)',
                       out_path=FIG)
    replay.record_iteration(EXP_ID, res, verdict=verdict, notes=notes)
    print(f"[{EXP_ID}] verdict={verdict}  →  {FIG}")


if __name__ == '__main__':
    main()
