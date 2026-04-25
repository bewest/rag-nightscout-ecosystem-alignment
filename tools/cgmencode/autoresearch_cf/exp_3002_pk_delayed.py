"""EXP-3002 — Replace instantaneous insulin effect with oref0 exponential PK.

Hypothesis: an event lasting ~30 min only realises a fraction of its insulin's
peak effect by the nadir; cf_severe should *decrease* relative to EXP-3001
(less protection magnitude attributed to AID, narrower upper bound).

Verdict criterion:
- ``conservative_lower_bound`` if cf_severe(EXP-3002) < cf_severe(EXP-3001)
  AND rank-vs-baseline rho > 0.85 (still ranks the same patients).
- ``destabilised`` if rank rho < 0.85 (different patients now flagged).

Sweeps two PK params (peak_min ∈ {55, 75, 95}) to bracket sensitivity.
"""
from __future__ import annotations

import json
from functools import partial
from pathlib import Path

import pandas as pd
from scipy import stats

from tools.cgmencode.autoresearch_cf import replay
from tools.cgmencode.autoresearch_cf.figures import figure_three_panel

EXP_ID = 'EXP-3002'
OUT = Path('externals/experiments')
FIG = Path('docs/60-research/figures') / f'{EXP_ID.lower()}_pk_delayed.png'
BASELINE_PP = OUT / 'exp-3001_per_patient.parquet'


def main() -> None:
    events, phenotype, profiles = replay.load_inputs()
    rows_for_table = []
    sweep_results = {}
    for peak_min in (55.0, 75.0, 95.0):
        kernel = partial(replay.kernel_oref0_exponential,
                         peak_min=peak_min, dia_min=360.0)
        config = replay.ReplayConfig(
            name=f'pk_peak{int(peak_min)}_pp_isf_linear',
            isf_source=replay.isf_source_profile,
            insulin_kernel=kernel,
            duration_model=replay.duration_linear,
            isf_source_name='profile_isf',
            kernel_name=f'oref0_exp_peak{int(peak_min)}',
            duration_name='linear',
        )
        res = replay.run_replay(events, profiles, phenotype, config)
        s = res.summary
        pp = res.per_patient

        baseline = pd.read_parquet(BASELINE_PP)[['patient_id', 'cf_severe']]
        baseline = baseline.rename(columns={'cf_severe': 'cf_severe_3001'})
        cmp = pp.merge(baseline, on='patient_id', how='inner')
        rho_rank, p_rank = stats.spearmanr(cmp['cf_severe_3001'],
                                           cmp['cf_severe'])
        valid = pp.dropna(subset=['braking_ratio'])
        rho_brake, p_brake = stats.spearmanr(valid['braking_ratio'],
                                             valid['cf_severe'])
        sweep_results[f'peak_{int(peak_min)}'] = {
            'pop_cf_severe': s['pop_counterfactual_severe'],
            'aid_protection_severe': s['aid_protection_severe_abs'],
            'rank_rho_vs_3001': float(rho_rank),
            'braking_rho': float(rho_brake),
            'braking_p': float(rho_brake),
            'mean_extra_drop': s['mean_extra_drop_mgdl'],
        }
        rows_for_table.append((peak_min, s, rho_rank, rho_brake))

        # Persist + record only the canonical peak=75 case as the iteration
        if int(peak_min) == 75:
            res.events.to_parquet(OUT / f'{EXP_ID.lower()}_events.parquet')
            res.per_patient.to_parquet(
                OUT / f'{EXP_ID.lower()}_per_patient.parquet')
            figure_three_panel(
                res.per_patient,
                title=f'{EXP_ID} oref0-PK peak=75min (per-patient ISF)',
                out_path=FIG)
            baseline_protection = pd.read_parquet(BASELINE_PP)[
                'aid_protection_severe'].mean() if BASELINE_PP.exists() else None
            decreased = (s['pop_counterfactual_severe'] < 0.959)  # vs 3001
            if rho_rank >= 0.85 and decreased:
                verdict = 'conservative_lower_bound'
                notes = (f'PK-realised cf_severe={s["pop_counterfactual_severe"]:.3f}'
                         f' (3001 baseline 0.959); rank rho={rho_rank:.3f}; '
                         f'braking rho={rho_brake:+.3f} (3001 -0.878)')
            elif rho_rank < 0.85:
                verdict = 'destabilised'
                notes = (f'rank rho={rho_rank:.3f} <0.85 — PK kernel changes '
                         f'which patients are flagged')
            else:
                verdict = 'unexpected_increase'
                notes = (f'cf_severe DID NOT decrease '
                         f'({s["pop_counterfactual_severe"]:.3f}); investigate '
                         f'kernel form')
            replay.record_iteration(EXP_ID, res, verdict=verdict, notes=notes)
            canonical_summary = {**s, 'verdict': verdict, 'notes': notes,
                                 'rank_vs_3001_rho': float(rho_rank),
                                 'braking_rho': float(rho_brake),
                                 'baseline_3001_protection': (
                                     float(baseline_protection)
                                     if baseline_protection is not None else None),
                                 'sweep': sweep_results}

    print(f"[{EXP_ID}] sweep over PK peak (min):")
    print(f"  {'peak':>6}  {'cf_severe':>10}  {'protection':>11}  "
          f"{'rank_rho':>9}  {'brake_rho':>10}  {'mean_drop':>10}")
    for peak, s, rho_rank, rho_brake in rows_for_table:
        print(f"  {int(peak):>6d}  {s['pop_counterfactual_severe']:>10.3%}  "
              f"{s['aid_protection_severe_abs']:>11.3%}  "
              f"{rho_rank:>+9.3f}  {rho_brake:>+10.3f}  "
              f"{s['mean_extra_drop_mgdl']:>10.2f}")

    (OUT / f'{EXP_ID.lower()}_summary.json').write_text(
        json.dumps(canonical_summary, indent=2, default=float))
    print(f"[{EXP_ID}] canonical (peak=75) verdict={canonical_summary['verdict']}"
          f"  →  {FIG}")


if __name__ == '__main__':
    main()
