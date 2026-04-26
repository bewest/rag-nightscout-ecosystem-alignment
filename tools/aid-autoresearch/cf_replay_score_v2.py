#!/usr/bin/env python3
"""CF-Replay Fitness Scorer v2 — descent + ascent (EXP-3008).

Extends ``cf_replay_score.py`` (v1, descent-only) with the ascent
dose-response axis from EXP-3008. A candidate controller is parameterised
by ``--smb-multiplier`` (scale on observed SMB-during-ascent); v2 reports a
composite fitness combining:

    50 %  descent protection (v1 score, severe-hypo safety on descents)
    35 %  ascent overshoot reduction (per-controller slope from EXP-3008)
    15 %  ascent hypo-safety penalty (60-min look-ahead proxy < 70 mg/dL)

Hard safety gate (v2-specific):
  ascent hypo-rate at the candidate multiplier > 1.0 % on ANY controller →
  fail (candidate is too aggressive in the post-peak window).

Same JSON contract as v1::

    {"score": 0.0..1.0, "safety_ok": bool, "components": {...},
     "per_controller": {Loop: {...}, Trio: {...}, OpenAPS: {...}}}

Usage::

    python3 -m tools.aid_autoresearch.cf_replay_score_v2 \\
        --smb-multiplier 1.5 --append-tsv --label cand-trio-up
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools.cgmencode.autoresearch_cf import replay  # noqa: E402
from tools.cgmencode.autoresearch_cf.exp_3004_ascent_replay import (  # noqa: E402
    kernel_fraction)
from tools.cgmencode.autoresearch_cf.exp_3008_dose_response import (  # noqa: E402
    candidate_score)

# v1 scorer lives in a hyphenated dir; load by file path
_v1_path = REPO_ROOT / 'tools' / 'aid-autoresearch' / 'cf_replay_score.py'
_spec = importlib.util.spec_from_file_location('cf_replay_score_v1', _v1_path)
v1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v1)

ASCENT = Path('externals/experiments/exp-3007_ascent_events.parquet')
HYPO_GATE = 0.010   # 1.0 % per-controller hypo-rate hard fail


def ascent_score(multiplier: float, profiles: pd.DataFrame) -> dict:
    ev = pd.read_parquet(ASCENT)
    isf_map = {}
    for pid in ev['patient_id'].unique():
        prof = profiles[(profiles['patient_id'] == pid) &
                        (profiles['schedule_type'] == 'isf')]
        vals = prof['value'].dropna() if len(prof) else pd.Series(dtype=float)
        vals = vals[(vals >= 30) & (vals <= 200)]
        isf_map[pid] = float(vals.median()) if len(vals) else 50.0
    ev['isf_used'] = ev['patient_id'].map(isf_map)
    ev['kernel_factor'] = kernel_fraction(ev['duration_min'])

    by = candidate_score(ev, multiplier)
    by = by[by['controller'].notna()].copy()

    # Per-controller composite: 70% lower-overshoot + 30% lower-hypo
    by['ctrl_score'] = (
        0.70 * (1.0 - by['cand_overshoot']) +
        0.30 * (1.0 - 2 * by['cand_hypo_rate']).clip(lower=0))

    # Aggregate ascent score = mean of per-controller scores
    ascent_overshoot_score = float(by['ctrl_score'].mean())
    max_hypo = float(by['cand_hypo_rate'].max())
    safety_ok = max_hypo <= HYPO_GATE

    return {
        'ascent_score': ascent_overshoot_score,
        'max_hypo_rate': max_hypo,
        'safety_ok': safety_ok,
        'per_controller': by[['controller', 'multiplier', 'obs_overshoot',
                              'cand_overshoot', 'cand_hypo_rate',
                              'ctrl_score']].to_dict(orient='records'),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    # v1 descent knobs (passed through)
    p.add_argument('--isf-source', choices=['profile', 'population'], default='profile')
    p.add_argument('--kernel', choices=['instantaneous', 'pk'], default='pk')
    p.add_argument('--peak-min', type=float, default=75.0)
    p.add_argument('--dia-min', type=float, default=360.0)
    p.add_argument('--duration', choices=['linear', 'sigmoid'], default='sigmoid')
    p.add_argument('--stretch', type=float, default=4.0)
    # v2 ascent knob
    p.add_argument('--smb-multiplier', type=float, default=1.0,
                   help='SMB aggression multiplier on ascent events (1.0 = baseline)')
    # bookkeeping
    p.add_argument('--label', default=None)
    p.add_argument('--append-tsv', action='store_true')
    p.add_argument('--json', action='store_true')
    args = p.parse_args()

    try:
        events, phenotype, profiles = replay.load_inputs()
    except Exception as e:
        print(json.dumps({'score': 0.0, 'safety_ok': False,
                          'reason': f'load_inputs failed: {e}',
                          'components': {}})); sys.exit(2)

    desc = v1.compute_cf_score(events, profiles, phenotype, args)
    desc.pop('iteration_result', None)
    asc = ascent_score(args.smb_multiplier, profiles)

    composite = (0.50 * desc['score'] +
                 0.35 * asc['ascent_score'] +
                 0.15 * (1.0 - 2 * asc['max_hypo_rate']))
    composite = max(0.0, min(1.0, composite))
    safety_ok = bool(desc['safety_ok'] and asc['safety_ok'])

    out = {
        'score': composite,
        'safety_ok': safety_ok,
        'components': {
            'descent_v1_score': desc['score'],
            'ascent_score': asc['ascent_score'],
            'ascent_max_hypo_rate': asc['max_hypo_rate'],
            'smb_multiplier': args.smb_multiplier,
        },
        'per_controller': asc['per_controller'],
        'descent_components': desc.get('components', {}),
    }

    if args.append_tsv:
        verdict = ('safety_failed' if not safety_ok
                   else f'autoresearch_v2_score_{composite:.4f}')
        notes = (f'EXP-3008 candidate label={args.label or "(default)"} '
                 f'mult={args.smb_multiplier} '
                 f'desc={desc["score"]:.3f} asc={asc["ascent_score"]:.3f} '
                 f'max_hypo={asc["max_hypo_rate"]:.4f}')
        # Lightweight ledger-shim (no full ReplayResult; we hand-write a row)
        tsv = Path('tools/aid-autoresearch/autoresearch_cf_results.tsv')
        from datetime import datetime, timezone
        row = {
            'timestamp_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'iteration_id': 'EXP-3008',
            'isf_source': args.isf_source,
            'kernel': args.kernel,
            'peak_min': args.peak_min,
            'dia_min': args.dia_min,
            'duration_model': args.duration,
            'n_patients': '', 'mean_obs_severe': '',
            'mean_cf_severe': '', 'mean_protection_abs': '',
            'mean_protection_rel': '',
            'verdict': verdict, 'notes': notes,
        }
        header_needed = not tsv.exists() or tsv.stat().st_size == 0
        with tsv.open('a') as f:
            if header_needed:
                f.write('\t'.join(row.keys()) + '\n')
            f.write('\t'.join(str(v) for v in row.values()) + '\n')

    if args.json:
        print(json.dumps(out, indent=2, default=float))
    else:
        print(f"score={composite:.4f}  safety={safety_ok}  "
              f"mult={args.smb_multiplier}")
        print(f"  descent_v1     = {desc['score']:.4f}")
        print(f"  ascent_score   = {asc['ascent_score']:.4f}")
        print(f"  max_hypo_rate  = {asc['max_hypo_rate']:.4f}  "
              f"(gate ≤ {HYPO_GATE})")
        for r in asc['per_controller']:
            print(f"  [{r['controller']:<8}]  obs_over={r['obs_overshoot']:.3%}  "
                  f"cand_over={r['cand_overshoot']:.3%}  "
                  f"hypo={r['cand_hypo_rate']:.3%}  ctrl_score={r['ctrl_score']:.3f}")
    sys.exit(0 if safety_ok else 1)


if __name__ == '__main__':
    main()
