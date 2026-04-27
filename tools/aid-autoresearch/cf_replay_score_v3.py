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

EXP_DIR = REPO_ROOT / 'externals' / 'experiments'
ASCENT = EXP_DIR / 'exp-3007_ascent_events.parquet'  # legacy default (training)
ASCENT_BY_SOURCE = {
    'training': EXP_DIR / 'exp-3007_ascent_events__training.parquet',
    'verification': EXP_DIR / 'exp-3007_ascent_events__verification.parquet',
}
PER_PATIENT_REC = EXP_DIR / 'exp-3012_per_patient.parquet'
PER_PATIENT_REC_CLAMPED = EXP_DIR / 'exp-3028_per_patient_carb_aware.parquet'  # EXP-3030: replaces exp-3017_per_patient_clamped.parquet after PASS-validated +0.0022 verif lift, 23/23 LOPO safe.
PER_PATIENT_REC_CLAMPED_LEGACY = EXP_DIR / 'exp-3017_per_patient_clamped.parquet'  # kept for diagnostic comparisons
PHENOTYPE = EXP_DIR / 'exp-2886_phenotype.parquet'
PHENOTYPE_IMPUTED = EXP_DIR / 'exp-3019_phenotype_imputed.parquet'

import hashlib  # noqa: E402


def _resolve_events_path(source: str | None, events_path: str | None) -> Path:
    if events_path:
        return Path(events_path)
    if source is None:
        return ASCENT  # legacy default for back-compat
    p = ASCENT_BY_SOURCE.get(source)
    if p is None:
        raise ValueError(f'unknown source: {source!r}')
    return p


def _events_sha256(path: Path) -> str:
    if not path.exists():
        return ''
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

HYPO_GATE = 0.010
HYPO_FLOOR = 70.0
WINDOW_MIN = 120
DEFAULT_AT_MIN = 180.0
ISF_PER_G = 4.0
DEFAULT_BRAKING_GATE = 0.10  # EXP-3025-FIX + EXP-3025-LOPO: lowered from 0.15 to coincide with STRAT_BRAKING_EDGES upper boundary; verification-stripe high-stratum safety pass + 23/23 LOPO robustness (delta mean +0.0245, std 0.0037).
STRAT_DELTA_PP = 1.0  # per-stratum Δhypo gate (pp) above stratum baseline
STRAT_BRAKING_EDGES = (0.05, 0.10)  # low / mid / high boundaries


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


def _phenotype_path(source: str = 'imputed') -> Path:
    """Pick imputed parquet by default; fall back to observed if missing."""
    if source == 'imputed' and PHENOTYPE_IMPUTED.exists():
        return PHENOTYPE_IMPUTED
    return PHENOTYPE


def _stratify_braking(pid_series: pd.Series, *, source: str = 'imputed') -> pd.Series:
    """Map patient_id → braking stratum {'low','mid','high','unknown'}."""
    path = _phenotype_path(source)
    if not path.exists():
        return pd.Series(['unknown'] * len(pid_series), index=pid_series.index)
    ph = pd.read_parquet(path)[['patient_id', 'braking_ratio']]
    pmap = dict(zip(ph['patient_id'], ph['braking_ratio']))
    lo, hi = STRAT_BRAKING_EDGES
    def _bin(pid: str) -> str:
        v = pmap.get(pid)
        if v is None or pd.isna(v):
            return 'unknown'
        if v < lo:   return 'low'
        if v < hi:   return 'mid'
        return 'high'
    return pid_series.map(_bin)


def _stratified_safety(out: pd.DataFrame, ev_baseline: pd.DataFrame,
                       *, source: str = 'imputed') -> dict:
    """Compare per-stratum candidate hypo vs baseline (M=1,T=0) hypo."""
    out = out.copy()
    out['stratum'] = _stratify_braking(out['patient_id'], source=source).values
    ev_baseline = ev_baseline.copy()
    ev_baseline['stratum'] = _stratify_braking(ev_baseline['patient_id'],
                                                source=source).values

    rows = []
    all_pass = True
    for stratum, sub in out.groupby('stratum'):
        bsub = ev_baseline[ev_baseline['stratum'] == stratum]
        if not len(bsub):
            continue
        cand_h = float(sub['cand_hypo'].mean())
        base_h = float(bsub['baseline_cand_hypo'].mean())
        delta_pp = (cand_h - base_h) * 100
        ceiling = HYPO_GATE * 2.0
        passes = (delta_pp <= STRAT_DELTA_PP) and (cand_h <= ceiling)
        all_pass = all_pass and passes
        rows.append({
            'stratum': stratum,
            'n': int(len(sub)),
            'baseline_hypo': base_h,
            'cand_hypo': cand_h,
            'delta_pp': delta_pp,
            'passes': passes,
        })
    return {'safety_ok': all_pass, 'per_stratum': rows}


def ascent_score_v3(profiles: pd.DataFrame, *,
                    multiplier: float, t_shift: float,
                    per_patient: bool, proxy: str,
                    braking_gate: float | None,
                    braking_mode: str = 'm_unity',
                    per_patient_source: str = 'clamped',
                    safety_mode: str = 'cohort',
                    phenotype_source: str = 'imputed',
                    events_path: Path | None = None) -> dict:
    ev_path = events_path if events_path is not None else ASCENT
    ev = pd.read_parquet(ev_path)
    ev['isf_used'] = ev['patient_id'].map(_isf_map(profiles, ev['patient_id'].unique().tolist()))

    n_total = len(ev)
    n_dropped_braking = 0
    high_braking_pids: set[str] = set()
    if braking_gate is not None and braking_mode != 'none':
        ph_path = _phenotype_path(phenotype_source)
        if ph_path.exists():
            ph = pd.read_parquet(ph_path)[['patient_id', 'braking_ratio']]
            high_braking_pids = set(ph.loc[ph['braking_ratio'] >= braking_gate,
                                           'patient_id'])
            if braking_mode == 'drop':
                before = len(ev)
                ev = ev[~ev['patient_id'].isin(high_braking_pids)].copy()
                n_dropped_braking = before - len(ev)

    rec_path = (PER_PATIENT_REC_CLAMPED if per_patient_source == 'clamped'
                and PER_PATIENT_REC_CLAMPED.exists()
                else PER_PATIENT_REC)
    if per_patient and rec_path.exists():
        rec = pd.read_parquet(rec_path)[
            ['patient_id', 'rec_T_min', 'rec_M_mult']]
        merged = ev.merge(rec, on='patient_id', how='left')
        T_arr = merged['rec_T_min'].fillna(t_shift).to_numpy()
        M_arr = merged['rec_M_mult'].fillna(multiplier).to_numpy()
        ev = merged
    else:
        T_arr = np.full(len(ev), t_shift)
        M_arr = np.full(len(ev), multiplier)

    n_m_unity = 0
    if braking_mode == 'm_unity' and high_braking_pids:
        mask = ev['patient_id'].isin(high_braking_pids).to_numpy()
        # Force M=1.0 for high-braking events; keep T as configured.
        # (per EXP-3016: timing benefit retained, magnitude reduction unwanted)
        M_arr = np.where(mask, 1.0, M_arr)
        n_m_unity = int(mask.sum())

    out = cf_eval(ev, T_arr, M_arr, proxy=proxy)
    out = out[out['controller'].notna()].copy()

    # Per-stratum safety needs a baseline (M=1,T=0) cf-replay for the SAME
    # event set, so we compute it here even if cohort mode is selected (cheap).
    n_ev = len(ev)
    base_eval = cf_eval(ev, np.zeros(n_ev), np.ones(n_ev), proxy=proxy)
    base_eval = base_eval[base_eval['controller'].notna()].copy()
    base_eval = base_eval.rename(columns={'cand_hypo': 'baseline_cand_hypo'})

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

    cohort_safety_ok = bool(by['cand_hypo_rate'].max() <= HYPO_GATE)
    strat = _stratified_safety(out, base_eval, source=phenotype_source)
    safety_ok = strat['safety_ok'] if safety_mode == 'stratified' else cohort_safety_ok

    return {
        'ascent_score': float(by['ctrl_score'].mean()),
        'max_hypo_rate': float(by['cand_hypo_rate'].max()),
        'safety_ok': safety_ok,
        'cohort_safety_ok': cohort_safety_ok,
        'stratified_safety_ok': strat['safety_ok'],
        'per_stratum': strat['per_stratum'],
        'per_controller': by.to_dict(orient='records'),
        'meta': {
            'mode': 'per_patient' if per_patient else 'uniform',
            'proxy': proxy,
            'safety_mode': safety_mode,
            'braking_gate': braking_gate,
            'braking_mode': braking_mode if braking_gate is not None else None,
            'n_events_total': int(n_total),
            'n_dropped_braking': int(n_dropped_braking),
            'n_m_unity': int(n_m_unity),
            'n_events_used': int(len(ev)),
            'events_path': str(ev_path),
            'events_sha256': _events_sha256(ev_path),
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
    p.add_argument('--per-patient-source', choices=['raw', 'clamped'],
                   default='raw',
                   help='which per-patient parquet to use: raw=EXP-3012 (default '
                        'per EXP-3020; clamped+m_unity was double-clamping), '
                        'clamped=EXP-3017 phenotype-clamped (legacy fallback)')
    p.add_argument('--proxy', choices=['carb_aware', 'worst_case'],
                   default='carb_aware')
    p.add_argument('--braking-gate', nargs='?', const=DEFAULT_BRAKING_GATE,
                   default=None, type=float,
                   help=f'apply phenotype gate at braking_ratio >= VALUE (default {DEFAULT_BRAKING_GATE})')
    p.add_argument('--braking-mode', choices=['drop', 'm_unity', 'none'],
                   default='m_unity',
                   help='action for gated patients: drop=remove from cohort, '
                        'm_unity=force M=1.0 retaining T (EXP-3016 default), '
                        'none=no gate effect even if --braking-gate set')
    p.add_argument('--phenotype-source', choices=['observed', 'imputed'],
                   default='imputed',
                   help='observed=EXP-2886 only; imputed=EXP-3019 with prefix '
                        'heuristic for unknown patients (default)')
    p.add_argument('--safety-mode', choices=['cohort', 'stratified'],
                   default='cohort',
                   help='cohort: max(per-controller hypo) <= 1pp; '
                        'stratified: per-braking-stratum Δhypo vs baseline (EXP-3018)')
    p.add_argument('--source', choices=['training', 'verification'], default=None,
                   help='which ascent-events partition to score against. '
                        'When omitted, uses the legacy un-suffixed parquet '
                        '(historically training). Use --source verification for '
                        'held-out within-cohort validation (EXP-3025).')
    p.add_argument('--events-path', default=None,
                   help='explicit path to an ascent-events parquet, '
                        'overrides --source.')
    p.add_argument('--label', default=None)
    p.add_argument('--json', action='store_true')
    args = p.parse_args()

    events_path = _resolve_events_path(args.source, args.events_path)
    if not events_path.exists():
        msg = (f'events parquet missing: {events_path}. Run '
               f'`python3 -m tools.cgmencode.autoresearch_cf.exp_3007_ascent_extraction '
               f'--source {args.source or "training"}` first.')
        print(json.dumps({'score': 0.0, 'safety_ok': False, 'reason': msg,
                          'components': {}}))
        sys.exit(2)

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
                          braking_gate=args.braking_gate,
                          braking_mode=args.braking_mode,
                          per_patient_source=args.per_patient_source,
                          safety_mode=args.safety_mode,
                          phenotype_source=args.phenotype_source,
                          events_path=events_path)

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
        'per_stratum': asc.get('per_stratum', []),
        'cohort_safety_ok': asc.get('cohort_safety_ok'),
        'stratified_safety_ok': asc.get('stratified_safety_ok'),
        'descent_components': desc.get('components', {}),
        'meta': asc['meta'],
        'provenance': {
            'eval_source': args.source or 'legacy_default',
            'events_path': str(events_path),
            'events_sha256': asc['meta'].get('events_sha256', ''),
            'fit_source': 'training',  # per-patient + phenotype always trained on training
            'per_patient_parquet': str(
                PER_PATIENT_REC_CLAMPED if args.per_patient_source == 'clamped'
                and PER_PATIENT_REC_CLAMPED.exists() else PER_PATIENT_REC),
            'phenotype_parquet': str(_phenotype_path(args.phenotype_source)),
            'n_events_used': asc['meta']['n_events_used'],
        },
    }

    if args.json:
        print(json.dumps(out, indent=2, default=float))
    else:
        m = asc['meta']
        print(f"score={composite:.4f}  safety={safety_ok}  mode={m['mode']}  "
              f"proxy={m['proxy']}  safety_mode={m['safety_mode']}  "
              f"brake_gate={m['braking_gate']}  brake_mode={m['braking_mode']}")
        print(f"  descent_v1    = {desc['score']:.4f}")
        print(f"  ascent_score  = {asc['ascent_score']:.4f}")
        print(f"  max_hypo_rate = {asc['max_hypo_rate']:.4f}  (cohort gate ≤ {HYPO_GATE})")
        print(f"  cohort_safety = {asc.get('cohort_safety_ok')}  "
              f"stratified_safety = {asc.get('stratified_safety_ok')}")
        print(f"  events used   = {m['n_events_used']}/{m['n_events_total']}  "
              f"(dropped {m['n_dropped_braking']}, m_unity-forced {m['n_m_unity']})")
        for r in asc.get('per_stratum', []):
            mark = '✓' if r['passes'] else '✗'
            print(f"  [strat {r['stratum']:<7}] n={r['n']:>5}  "
                  f"base_h={r['baseline_hypo']:.3%}  cand_h={r['cand_hypo']:.3%}  "
                  f"Δ={r['delta_pp']:+5.2f}pp  {mark}")
        for r in asc['per_controller']:
            print(f"  [{r['controller']:<8}]  obs_over={r.get('obs_overshoot', float('nan')):.3%}  "
                  f"cand_over={r['cand_overshoot']:.3%}  "
                  f"hypo={r['cand_hypo_rate']:.3%}  score={r['ctrl_score']:.3f}  n={r['n']}")
    sys.exit(0 if safety_ok else 1)


if __name__ == '__main__':
    main()
