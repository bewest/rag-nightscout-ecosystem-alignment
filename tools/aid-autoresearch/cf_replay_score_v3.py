#!/usr/bin/env python3
"""CF-Replay Fitness Scorer v3 — per-patient + carb-aware + braking gate (EXP-3015).

Extends ``cf_replay_score_v2.py`` (uniform multiplier) with the three Phase 3
findings:

  * Per-patient (T*, M*) recommendations from EXP-3012 instead of a uniform
    cohort knob (``--per-patient`` mode).
  * Carb-absorption-aware trough proxy from EXP-3014 (default; ``--proxy``
    selects ``carb_aware`` or ``worst_case``).
  * Phenotype gate from EXP-3013: patients with ``braking_ratio >= 0.10`` are
    treated as already-saturated and contribute zero benefit (their cf-replay
    is dropped from the per-controller aggregation).

Backwards-compatible: without ``--per-patient`` the v3 scorer reduces to the
v2 cohort-multiplier behaviour (carb-aware proxy on by default; gate optional).

Composite score (unchanged structure from v2)::

    50 %  descent protection (v1 score)
    35 %  ascent overshoot reduction (per-controller mean)
    15 %  ascent hypo-safety penalty

Hard safety gate: any controller's hypo-rate > 1.0 % → fail.

Usage::

    # cohort uniform (v2 behaviour, carb-aware proxy)
    python3 -m tools.aid_autoresearch.cf_replay_score_v3 --smb-multiplier 0.5

    # per-patient mode (uses exp-3012_per_patient.parquet)
    python3 -m tools.aid_autoresearch.cf_replay_score_v3 --per-patient --braking-gate

    # uniform cohort with explicit T-shift (Phase 2 frontier)
    python3 -m tools.aid_autoresearch.cf_replay_score_v3 \\
        --smb-multiplier 0.5 --t-shift 30
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
from tools.cgmencode.autoresearch_cf.exp_3009_timing_axis import kernel_at  # noqa: E402

_v1_path = REPO_ROOT / 'tools' / 'aid-autoresearch' / 'cf_replay_score.py'
_spec = importlib.util.spec_from_file_location('cf_replay_score_v1', _v1_path)
v1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v1)

ASCENT = REPO_ROOT / 'externals' / 'experiments' / 'exp-3007_ascent_events.parquet'
PER_PATIENT_REC = REPO_ROOT / 'externals' / 'experiments' / 'exp-3012_per_patient.parquet'
PHENOTYPE = REPO_ROOT / 'externals' / 'experiments' / 'exp-2886_phenotype.parquet'

HYPO_GATE = 0.010
HYPO_FLOOR = 70.0
WINDOW_MIN = 120
DEFAULT_AT_MIN = 180.0
ISF_PER_G = 4.0
DEFAULT_BRAKING_GATE = 0.10


def _isf_map(profiles: pd.DataFrame, patient_ids: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for pid in patient_ids:
        prof = profiles[(profiles['patient_id'] == pid) &
                        (profiles['schedule_type'] == 'isf')]
        vals = prof['value'].dropna() if len(prof) else pd.Series(dtype=float)
        vals = vals[(vals >= 30) & (vals <= 200)]
        out[pid] = float(vals.median()) if len(vals) else 50.0
    return out


def cf_eval(ev: pd.DataFrame, T_arr: np.ndarray, M_arr: np.ndarray,
            *, proxy: str) -> pd.DataFrame:
    """Vectorised per-event cf-replay (T, M may vary by row)."""
    df = ev.copy()
    smb_obs = ev['smb_during'].fillna(0).to_numpy()
    smb_cand = smb_obs * M_arr
    isf = ev['isf_used'].to_numpy()
    half = ev['duration_min'].to_numpy() / 2.0
    eff_off = np.minimum(T_arr, ev['duration_min'].to_numpy())
    t_peak = half + eff_off

    drop_at_peak = smb_cand * kernel_at(t_peak) * isf
    drop_at_peak_baseline = smb_obs * kernel_at(half) * isf
    cand_peak = ev['bg_peak'].to_numpy() - (drop_at_peak - drop_at_peak_baseline)

    extra_post = (kernel_at(t_peak + WINDOW_MIN) - kernel_at(t_peak)) * smb_cand * isf
    cand_trough = cand_peak - extra_post

    if proxy == 'carb_aware':
        cob_at_peak = (ev['cob_start'].fillna(0) +
                       ev['carbs_during'].fillna(0)).to_numpy()
        absorbed = cob_at_peak * (WINDOW_MIN / DEFAULT_AT_MIN)
        cand_trough = cand_trough + absorbed * ISF_PER_G

    df['cand_overshoot'] = (cand_peak >= 180.0).astype(float)
    df['cand_hypo'] = (cand_trough < HYPO_FLOOR).astype(float)
    return df


def ascent_score_v3(profiles: pd.DataFrame, *,
                    multiplier: float, t_shift: float,
                    per_patient: bool, proxy: str,
                    braking_gate: float | None) -> dict:
    ev = pd.read_parquet(ASCENT)
    ev['isf_used'] = ev['patient_id'].map(_isf_map(profiles, ev['patient_id'].unique().tolist()))

    n_total = len(ev)
    n_dropped_braking = 0
    if braking_gate is not None and PHENOTYPE.exists():
        ph = pd.read_parquet(PHENOTYPE)[['patient_id', 'braking_ratio']]
        keep = set(ph.loc[ph['braking_ratio'] < braking_gate, 'patient_id'])
        # Patients without a phenotype row pass-through (don't drop unknowns).
        unknown = set(ev['patient_id'].unique()) - set(ph['patient_id'])
        keep = keep | unknown
        before = len(ev)
        ev = ev[ev['patient_id'].isin(keep)].copy()
        n_dropped_braking = before - len(ev)

    if per_patient and PER_PATIENT_REC.exists():
        rec = pd.read_parquet(PER_PATIENT_REC)[
            ['patient_id', 'rec_T_min', 'rec_M_mult']]
        merged = ev.merge(rec, on='patient_id', how='left')
        # Fall back to cohort knobs for unmatched patients.
        T_arr = merged['rec_T_min'].fillna(t_shift).to_numpy()
        M_arr = merged['rec_M_mult'].fillna(multiplier).to_numpy()
        ev = merged
    else:
        T_arr = np.full(len(ev), t_shift)
        M_arr = np.full(len(ev), multiplier)

    out = cf_eval(ev, T_arr, M_arr, proxy=proxy)
    out = out[out['controller'].notna()].copy()

    by = out.groupby('controller', as_index=False).agg(
        cand_overshoot=('cand_overshoot', 'mean'),
        cand_hypo_rate=('cand_hypo', 'mean'),
        n=('cand_overshoot', 'size'))
    obs = (ev[ev['controller'].notna()]
           .groupby('controller', as_index=False)['hyper_overshoot']
           .mean().rename(columns={'hyper_overshoot': 'obs_overshoot'}))
    by = by.merge(obs, on='controller', how='left')
    by['ctrl_score'] = (
        0.70 * (1.0 - by['cand_overshoot']) +
        0.30 * (1.0 - 2 * by['cand_hypo_rate']).clip(lower=0))

    return {
        'ascent_score': float(by['ctrl_score'].mean()),
        'max_hypo_rate': float(by['cand_hypo_rate'].max()),
        'safety_ok': bool(by['cand_hypo_rate'].max() <= HYPO_GATE),
        'per_controller': by.to_dict(orient='records'),
        'meta': {
            'mode': 'per_patient' if per_patient else 'uniform',
            'proxy': proxy,
            'braking_gate': braking_gate,
            'n_events_total': int(n_total),
            'n_dropped_braking': int(n_dropped_braking),
            'n_events_used': int(len(ev)),
        },
    }


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    # v1 descent
    p.add_argument('--isf-source', choices=['profile', 'population'], default='profile')
    p.add_argument('--kernel', choices=['instantaneous', 'pk'], default='pk')
    p.add_argument('--peak-min', type=float, default=75.0)
    p.add_argument('--dia-min', type=float, default=360.0)
    p.add_argument('--duration', choices=['linear', 'sigmoid'], default='sigmoid')
    p.add_argument('--stretch', type=float, default=4.0)
    # v3 ascent
    p.add_argument('--smb-multiplier', type=float, default=1.0)
    p.add_argument('--t-shift', type=float, default=0.0,
                   help='earlier-firing minutes for the cohort-uniform mode')
    p.add_argument('--per-patient', action='store_true',
                   help='use exp-3012 per-patient (T*, M*) instead of uniform knobs')
    p.add_argument('--proxy', choices=['carb_aware', 'worst_case'],
                   default='carb_aware')
    p.add_argument('--braking-gate', nargs='?', const=DEFAULT_BRAKING_GATE,
                   default=None, type=float,
                   help=f'drop patients with braking_ratio >= gate (default {DEFAULT_BRAKING_GATE})')
    p.add_argument('--label', default=None)
    p.add_argument('--json', action='store_true')
    args = p.parse_args()

    try:
        events, phenotype, profiles = replay.load_inputs()
    except Exception as e:
        print(json.dumps({'score': 0.0, 'safety_ok': False,
                          'reason': f'load_inputs failed: {e}',
                          'components': {}}))
        sys.exit(2)

    desc = v1.compute_cf_score(events, profiles, phenotype, args)
    desc.pop('iteration_result', None)
    asc = ascent_score_v3(profiles,
                          multiplier=args.smb_multiplier,
                          t_shift=args.t_shift,
                          per_patient=args.per_patient,
                          proxy=args.proxy,
                          braking_gate=args.braking_gate)

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
            't_shift': args.t_shift,
            'mode': asc['meta']['mode'],
            'proxy': asc['meta']['proxy'],
            'braking_gate': asc['meta']['braking_gate'],
        },
        'per_controller': asc['per_controller'],
        'descent_components': desc.get('components', {}),
        'meta': asc['meta'],
    }

    if args.json:
        print(json.dumps(out, indent=2, default=float))
    else:
        m = asc['meta']
        print(f"score={composite:.4f}  safety={safety_ok}  mode={m['mode']}  "
              f"proxy={m['proxy']}  brake_gate={m['braking_gate']}")
        print(f"  descent_v1    = {desc['score']:.4f}")
        print(f"  ascent_score  = {asc['ascent_score']:.4f}")
        print(f"  max_hypo_rate = {asc['max_hypo_rate']:.4f}  (gate ≤ {HYPO_GATE})")
        print(f"  events used   = {m['n_events_used']}/{m['n_events_total']}  "
              f"(dropped {m['n_dropped_braking']} for braking gate)")
        for r in asc['per_controller']:
            print(f"  [{r['controller']:<8}]  obs_over={r.get('obs_overshoot', float('nan')):.3%}  "
                  f"cand_over={r['cand_overshoot']:.3%}  "
                  f"hypo={r['cand_hypo_rate']:.3%}  score={r['ctrl_score']:.3f}  n={r['n']}")
    sys.exit(0 if safety_ok else 1)


if __name__ == '__main__':
    main()
