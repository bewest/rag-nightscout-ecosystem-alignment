#!/usr/bin/env python3
"""CF-Replay Fitness Scorer for AID Autoresearch.

Companion to ``algorithm_score.py``. Takes an oref0/Loop parameter set and
scores it against the EXP-3000-3003 counterfactual-replay engine: how well
would this controller protect against severe hypoglycaemia on the cohort's
real descent events?

Same JSON contract as ``algorithm_score.py``:

    {"score": 0.0..1.0, "safety_ok": bool, "components": {...}}

Composite (v1) — 4 components:
   45 %  protection rank score   (cohort patients ranked by counterfactual
                                  severe rate; controller's score = mean
                                  rank-percentile across patients)
   25 %  observed-severe penalty (avoid candidates that themselves cause
                                  severe lows in the replay)
   20 %  robustness across kernel/duration sensitivity
                                 (mean of {instant+linear, PK+sigmoid_s400})
   10 %  braking-ratio construct (controller's cf-rank correlates with
                                  measured braking_ratio: rho < -0.5 → full)

Hard safety gate: any patient with cf_severe == 1.0 AND obs_severe > 0.50
fails — controller magnifies hypo without commensurate protection.

Exit code 0 = scored, 1 = safety failure, 2 = engine/data error.

Usage::

    # Score the baseline configuration (population ISF=50)
    python3 tools/aid-autoresearch/cf_replay_score.py --json

    # Score a candidate (per-patient ISF, oref0 PK, sigmoid_s400)
    python3 tools/aid-autoresearch/cf_replay_score.py \
        --isf-source profile --kernel pk --peak-min 75 \
        --duration sigmoid --stretch 4.0 --json

    # Append to ledger with a candidate label
    python3 tools/aid-autoresearch/cf_replay_score.py \
        --label "candidate-A" --append-tsv

Trace: REQ-060, ALG-SCORE-002, EXP-3005.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

import pandas as pd
from scipy import stats

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools.cgmencode.autoresearch_cf import replay  # noqa: E402

LEDGER = REPO_ROOT / 'tools' / 'aid-autoresearch' / 'autoresearch_cf_results.tsv'


def build_config(args) -> replay.ReplayConfig:
    isf = (replay.isf_source_profile if args.isf_source == 'profile'
           else replay.isf_source_population)
    if args.kernel == 'instantaneous':
        kernel = replay.kernel_instantaneous
        kernel_name = 'instantaneous'
    else:
        kernel = partial(replay.kernel_oref0_exponential,
                         peak_min=args.peak_min, dia_min=args.dia_min)
        kernel_name = f'oref0_exp_peak{int(args.peak_min)}'
    if args.duration == 'linear':
        dur = replay.duration_linear
        dur_name = 'linear'
    else:
        dur = partial(replay.duration_sigmoid_correction, stretch=args.stretch)
        dur_name = f'sigmoid_s{int(args.stretch * 100)}'
    return replay.ReplayConfig(
        name=args.label or f'{args.isf_source}_{kernel_name}_{dur_name}',
        isf_source=isf, insulin_kernel=kernel, duration_model=dur,
        isf_source_name=f'{args.isf_source}_isf',
        kernel_name=kernel_name, duration_name=dur_name,
    )


def compute_cf_score(events, profiles, phenotype, args) -> dict:
    """Run two replay configurations (one fast, one realistic) and emit a
    composite score. Returns a dict matching ``algorithm_score.py``'s shape."""
    realistic_config = build_config(args)
    res = replay.run_replay(events, profiles, phenotype, realistic_config)
    pp = res.per_patient
    s = res.summary

    # Hard safety gate
    if (((pp['cf_severe'] >= 0.999) & (pp['obs_severe'] > 0.50)).any()):
        bad = pp[(pp['cf_severe'] >= 0.999) & (pp['obs_severe'] > 0.50)][
            'patient_id'].tolist()
        return {'score': 0.0, 'safety_ok': False,
                'reason': (f'Patients {bad} have cf_severe≈1.0 AND '
                           f'obs_severe>0.5 — controller magnifies hypo '
                           f'without commensurate protection'),
                'components': {}}

    # 1. Protection rank score: cohort rank-percentile
    valid = pp.dropna(subset=['cf_severe', 'aid_protection_severe']).copy()
    valid['cf_severe_pctile'] = valid['cf_severe'].rank(pct=True)
    protection_rank = float(valid['aid_protection_severe'].clip(0, 1).mean())

    # 2. Observed-severe penalty
    obs_severe_pop = float(pp['obs_severe'].mean())
    obs_penalty = max(0.0, 1.0 - 2 * obs_severe_pop)  # 25% obs → 50% credit

    # 3. Robustness — second config (instantaneous fallback)
    fallback_config = replay.ReplayConfig(
        name='robustness_instant',
        isf_source=replay.isf_source_profile,
        insulin_kernel=replay.kernel_instantaneous,
        duration_model=replay.duration_linear,
        isf_source_name='profile_isf',
        kernel_name='instantaneous',
        duration_name='linear',
    )
    res_fb = replay.run_replay(events, profiles, phenotype, fallback_config)
    cmp = pp.merge(res_fb.per_patient[['patient_id', 'cf_severe']]
                       .rename(columns={'cf_severe': 'cf_severe_fb'}),
                   on='patient_id', how='inner')
    if len(cmp) >= 5:
        rho_robust, _ = stats.spearmanr(cmp['cf_severe'], cmp['cf_severe_fb'])
    else:
        rho_robust = 0.0
    robustness = float(max(0.0, rho_robust))

    # 4. Braking-ratio construct validity
    valid_b = pp.dropna(subset=['braking_ratio', 'cf_severe'])
    if len(valid_b) >= 5:
        rho_b, _ = stats.spearmanr(valid_b['braking_ratio'],
                                   valid_b['cf_severe'])
        # Want negative correlation (more braking → less cf hypo)
        construct = float(max(0.0, min(1.0, -rho_b / 0.5)))
    else:
        rho_b = 0.0
        construct = 0.0

    score = (0.45 * protection_rank +
             0.25 * obs_penalty +
             0.20 * robustness +
             0.10 * construct)

    return {
        'score': round(float(score), 6),
        'safety_ok': True,
        'components': {
            'protection_rank': round(protection_rank, 4),
            'obs_penalty': round(obs_penalty, 4),
            'robustness_rho': round(rho_robust, 4),
            'braking_rho': round(rho_b, 4),
            'pop_obs_severe': round(s['pop_observed_severe'], 4),
            'pop_cf_severe': round(s['pop_counterfactual_severe'], 4),
            'aid_protection': round(s['aid_protection_severe_abs'], 4),
            'mean_isf_used': round(s['mean_isf_used'], 2),
            'mean_extra_drop': round(s['mean_extra_drop_mgdl'], 2),
            'n_patients': s['n_patients'],
            'n_events': s['n_events'],
            'config_name': realistic_config.name,
            'isf_source': realistic_config.isf_source_name,
            'kernel': realistic_config.kernel_name,
            'duration_model': realistic_config.duration_name,
        },
        'iteration_result': res,  # passed to ledger writer; stripped from JSON
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--isf-source', choices=['profile', 'population'],
                   default='profile')
    p.add_argument('--kernel', choices=['instantaneous', 'pk'], default='pk')
    p.add_argument('--peak-min', type=float, default=75.0)
    p.add_argument('--dia-min', type=float, default=360.0)
    p.add_argument('--duration', choices=['linear', 'sigmoid'],
                   default='sigmoid')
    p.add_argument('--stretch', type=float, default=4.0)
    p.add_argument('--label', default=None,
                   help='Candidate name, also written to TSV ledger')
    p.add_argument('--append-tsv', action='store_true',
                   help='Append a row to autoresearch_cf_results.tsv')
    p.add_argument('--json', action='store_true', help='JSON output')
    args = p.parse_args()

    try:
        events, phenotype, profiles = replay.load_inputs()
    except Exception as e:
        out = {'score': 0.0, 'safety_ok': False,
               'reason': f'load_inputs failed: {e}', 'components': {}}
        print(json.dumps(out)); sys.exit(2)

    result = compute_cf_score(events, profiles, phenotype, args)
    iter_res = result.pop('iteration_result', None)

    if args.append_tsv and iter_res is not None:
        verdict = ('safety_failed' if not result['safety_ok']
                   else f'autoresearch_score_{result["score"]:.4f}')
        notes = (f'EXP-3005 candidate label={args.label or "(default)"}; '
                 f'components={result["components"]}')
        replay.record_iteration('EXP-3005', iter_res, verdict=verdict,
                                notes=notes)

    if args.json:
        print(json.dumps(result, indent=2, default=float))
    else:
        s = result
        print(f"score={s['score']:.4f}  safety={s['safety_ok']}")
        if s.get('components'):
            for k, v in s['components'].items():
                print(f"  {k:20s}  {v}")
        if not s['safety_ok']:
            print(f"  reason: {s.get('reason')}")
    sys.exit(0 if result['safety_ok'] else 1)


if __name__ == '__main__':
    main()
