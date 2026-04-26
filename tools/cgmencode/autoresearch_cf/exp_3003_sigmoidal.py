"""EXP-3003 — Sigmoidal nadir-duration (vs linear).

Hypothesis (from EXP-3002 finding): the linear-duration model under-estimates
how long an unmitigated descent would take. A sigmoidal dwell-time captures
the "tail" deceleration as glucose approaches the floor. Combined with PK,
the longer window gives insulin more time to act → some signal returns.

Sweeps duration_model ∈ {linear, sigmoid_correction(k=0.6, k=1.0)} crossed
with kernel ∈ {instantaneous, oref0_peak75}. Reports a 4-cell matrix.
"""
from __future__ import annotations

import json
from functools import partial
from pathlib import Path

import pandas as pd
from scipy import stats

from tools.cgmencode.autoresearch_cf import replay
from tools.cgmencode.autoresearch_cf.figures import figure_three_panel

EXP_ID = 'EXP-3003'
OUT = Path('externals/experiments')
FIG = Path('docs/60-research/figures') / f'{EXP_ID.lower()}_sigmoidal.png'
BASELINE_PP = OUT / 'exp-3001_per_patient.parquet'


def main() -> None:
    events, phenotype, profiles = replay.load_inputs()
    baseline = pd.read_parquet(BASELINE_PP)[['patient_id', 'cf_severe']]
    baseline = baseline.rename(columns={'cf_severe': 'cf_severe_3001'})

    matrix = {}
    canonical = None  # (config_name, result, verdict, notes)
    for kernel_name, kernel in [
        ('instantaneous', replay.kernel_instantaneous),
        ('oref0_peak75', partial(replay.kernel_oref0_exponential,
                                 peak_min=75.0, dia_min=360.0)),
    ]:
        for dur_name, dur in [
            ('linear', replay.duration_linear),
            ('sigmoid_s125', partial(replay.duration_sigmoid_correction,
                                     stretch=1.25)),
            ('sigmoid_s200', partial(replay.duration_sigmoid_correction,
                                     stretch=2.0)),
            ('sigmoid_s400', partial(replay.duration_sigmoid_correction,
                                     stretch=4.0)),
        ]:
            cfg = replay.ReplayConfig(
                name=f'{kernel_name}_{dur_name}_pp_isf',
                isf_source=replay.isf_source_profile,
                insulin_kernel=kernel,
                duration_model=dur,
                isf_source_name='profile_isf',
                kernel_name=kernel_name,
                duration_name=dur_name,
            )
            res = replay.run_replay(events, profiles, phenotype, cfg)
            s = res.summary
            pp = res.per_patient
            cmp = pp.merge(baseline, on='patient_id', how='inner')
            rho_rank, _ = stats.spearmanr(cmp['cf_severe_3001'],
                                          cmp['cf_severe'])
            valid = pp.dropna(subset=['braking_ratio'])
            rho_brake, _ = stats.spearmanr(valid['braking_ratio'],
                                           valid['cf_severe'])
            matrix[f'{kernel_name}__{dur_name}'] = {
                'pop_cf_severe': s['pop_counterfactual_severe'],
                'protection': s['aid_protection_severe_abs'],
                'mean_duration_min': s['mean_duration_min'],
                'mean_extra_drop': s['mean_extra_drop_mgdl'],
                'rank_rho_vs_3001': float(rho_rank),
                'braking_rho': float(rho_brake),
            }
            # Canonical = oref0_peak75 + sigmoid_s400 (most realistic combo)
            if kernel_name == 'oref0_peak75' and dur_name == 'sigmoid_s400':
                canonical = (cfg.name, res, rho_rank, rho_brake)

    print(f"[{EXP_ID}] kernel × duration matrix:")
    print(f"  {'kernel':<14}  {'duration':<12}  {'cf_sev':>7}  "
          f"{'prot':>7}  {'dur_min':>8}  {'drop':>6}  {'rank':>6}  {'brake':>6}")
    for k, v in matrix.items():
        ker, dur = k.split('__')
        print(f"  {ker:<14}  {dur:<12}  {v['pop_cf_severe']:>7.3%}  "
              f"{v['protection']:>7.3%}  {v['mean_duration_min']:>8.1f}  "
              f"{v['mean_extra_drop']:>6.1f}  {v['rank_rho_vs_3001']:>+6.3f}  "
              f"{v['braking_rho']:>+6.3f}")

    cfg_name, res, rho_rank, rho_brake = canonical
    s = res.summary
    if rho_rank >= 0.85 and abs(rho_brake) >= 0.5:
        verdict = 'recovers_signal'
        notes = (f'sigmoidal+PK retains rank rho={rho_rank:.3f}, '
                 f'braking rho={rho_brake:+.3f}')
    elif s['pop_counterfactual_severe'] > 0.6 and abs(rho_brake) >= 0.4:
        verdict = 'partial_recovery'
        notes = (f'longer windows lift cf_severe to '
                 f'{s["pop_counterfactual_severe"]:.3f}; '
                 f'braking rho={rho_brake:+.3f}')
    else:
        verdict = 'pk_dominates'
        notes = ('PK realism + realistic durations still suppress signal; '
                 'EXP-2889 magnitudes only valid under instantaneous assumption')

    OUT.mkdir(parents=True, exist_ok=True)
    res.events.to_parquet(OUT / f'{EXP_ID.lower()}_events.parquet')
    res.per_patient.to_parquet(OUT / f'{EXP_ID.lower()}_per_patient.parquet')
    figure_three_panel(res.per_patient,
                       title=f'{EXP_ID} sigmoid+PK (canonical: {cfg_name})',
                       out_path=FIG)
    (OUT / f'{EXP_ID.lower()}_summary.json').write_text(json.dumps(
        {**s, 'verdict': verdict, 'notes': notes,
         'rank_vs_3001_rho': float(rho_rank),
         'braking_rho': float(rho_brake), 'matrix': matrix},
        indent=2, default=float))
    replay.record_iteration(EXP_ID, res, verdict=verdict, notes=notes)
    print(f"[{EXP_ID}] canonical={cfg_name} verdict={verdict}")


if __name__ == '__main__':
    main()
