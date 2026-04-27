"""EXP-3028 — Per-patient (T*, M*) refit with carb-aware proxy.

Hypothesis
----------
EXP-3012 fitted per-patient (T*, M*) using a NAIVE trough proxy (no carb
absorption). EXP-3014 introduced a carb-aware proxy at the controller level.
EXP-3017 then clamped M* to 1.0 for high-braking phenotypes.

cf-replay-score-v3 evaluates events using the carb-aware proxy. This means
the per-patient table consumed by the scorer is fitted under one proxy and
evaluated under another — a model/scorer mismatch.

EXP-3028 closes that gap: refit per-patient (T*, M*) on TRAINING events
using the same carb-aware proxy used by the scorer, apply the EXP-3017
clamp, then evaluate on the VERIFICATION stripe at the new default
gate=0.10.

Question
--------
Does the carb-aware refit recover any of the +0.0173 composite Δ that was
lost moving the headline gate from 0.15 (Δ=+0.0418) to 0.10 (Δ=+0.0245)?

PASS criteria
-------------
(a) Verification safety_ok = True at gate=0.10 (consistent with EXP-3025-FIX).
(b) Composite Δ ≥ EXP-3017-clamped Δ on verification = +0.0245 (no regression).
(c) Bonus: Δ ≥ +0.0245 + meaningful_lift (we'll quantify ex-post).

If Δ < +0.0245 → FAIL (refit hurts; keep EXP-3017 clamped table).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from tools.cgmencode.autoresearch_cf import replay
from tools.cgmencode.autoresearch_cf.exp_3009_timing_axis import kernel_at

EXP_ID = 'EXP-3028'

# Reuse the same constants as cf_replay_score_v3
WINDOW_MIN = 120
HYPO_FLOOR = 70
DEFAULT_AT_MIN = 180.0  # carb absorption time
ISF_PER_G = 4.0  # mg/dL per g (rough)

OFFSETS_MIN = (0, 5, 10, 15, 20, 30)
MULTIPLIERS = (0.5, 1.0, 1.5, 2.0, 3.0)
HYPO_DELTA_GATE_PP = 1.0
MIN_EVENTS = 30

ROOT = Path(__file__).resolve().parents[2]
EXP_DIR = ROOT / 'externals' / 'experiments'
TRAIN = EXP_DIR / 'exp-3007_ascent_events__training.parquet'
VERIF = EXP_DIR / 'exp-3007_ascent_events__verification.parquet'
PHENO = EXP_DIR / 'exp-2886_phenotype.parquet'
OUT_REC = EXP_DIR / f'{EXP_ID.lower()}_per_patient_carb_aware.parquet'
OUT_SUMMARY = EXP_DIR / f'{EXP_ID.lower()}_summary.json'
CLAMP_GATE = 0.10  # same as EXP-3017


def _isf_map(profiles: pd.DataFrame, pids) -> dict:
    out = {}
    for pid in pids:
        prof = profiles[(profiles['patient_id'] == pid) &
                        (profiles['schedule_type'] == 'isf')]
        vals = prof['value'].dropna() if len(prof) else pd.Series(dtype=float)
        vals = vals[(vals >= 30) & (vals <= 200)]
        out[pid] = float(vals.median()) if len(vals) else 50.0
    return out


def cf_eval_carb_aware(ev: pd.DataFrame, T: float, M: float) -> pd.DataFrame:
    """Same math as cf_replay_score_v3.cf_eval(proxy='carb_aware')."""
    smb_obs = ev['smb_during'].fillna(0).to_numpy()
    smb_cand = smb_obs * M
    isf = ev['isf_used'].to_numpy()
    half = ev['duration_min'].to_numpy() / 2.0
    eff_off = np.minimum(T, ev['duration_min'].to_numpy())
    t_peak = half + eff_off

    drop_at_peak = smb_cand * kernel_at(t_peak) * isf
    drop_at_peak_baseline = smb_obs * kernel_at(half) * isf
    cand_peak = ev['bg_peak'].to_numpy() - (drop_at_peak - drop_at_peak_baseline)

    extra_post = (kernel_at(t_peak + WINDOW_MIN) - kernel_at(t_peak)) * smb_cand * isf
    cand_trough = cand_peak - extra_post

    cob_at_peak = (ev['cob_start'].fillna(0) +
                   ev['carbs_during'].fillna(0)).to_numpy()
    absorbed = cob_at_peak * (WINDOW_MIN / DEFAULT_AT_MIN)
    cand_trough = cand_trough + absorbed * ISF_PER_G

    return pd.DataFrame({
        'patient_id': ev['patient_id'].to_numpy(),
        'controller': ev['controller'].to_numpy(),
        'cand_overshoot': cand_peak >= 180.0,
        'cand_hypo': cand_trough < HYPO_FLOOR,
        'obs_overshoot': ev['hyper_overshoot'].to_numpy(),
    })


def fit_one_patient(ev_p: pd.DataFrame) -> tuple[float, float, float, float, float, float]:
    """Return (T*, M*, baseline_overshoot, baseline_hypo, cand_overshoot, cand_hypo).

    Picks (T, M) that minimises overshoot subject to delta-hypo <= +1.0 pp
    (matches EXP-3012's HYPO_DELTA_GATE_PP rule).
    """
    base = cf_eval_carb_aware(ev_p, T=0.0, M=1.0)
    base_over = float(base['cand_overshoot'].mean())
    base_hypo = float(base['cand_hypo'].mean())

    best = (0.0, 1.0, base_over, base_hypo)
    best_over = base_over
    for T in OFFSETS_MIN:
        for M in MULTIPLIERS:
            r = cf_eval_carb_aware(ev_p, T=float(T), M=float(M))
            cand_over = float(r['cand_overshoot'].mean())
            cand_hypo = float(r['cand_hypo'].mean())
            delta_hypo_pp = (cand_hypo - base_hypo) * 100.0
            if delta_hypo_pp <= HYPO_DELTA_GATE_PP and cand_over < best_over:
                best = (float(T), float(M), cand_over, cand_hypo)
                best_over = cand_over
    return (best[0], best[1], base_over, base_hypo, best[2], best[3])


def main() -> None:
    print(f"[{EXP_ID}] Refitting per-patient (T*, M*) on TRAINING with carb-aware proxy...")

    ev = pd.read_parquet(TRAIN)
    _, _, profiles = replay.load_inputs()
    isf_map = _isf_map(profiles, ev['patient_id'].unique().tolist())
    ev['isf_used'] = ev['patient_id'].map(isf_map)

    rows = []
    for pid, grp in ev.groupby('patient_id'):
        if len(grp) < MIN_EVENTS:
            continue
        T_star, M_star, b_over, b_hypo, c_over, c_hypo = fit_one_patient(grp)
        ctrl = grp['controller'].dropna().mode()
        rows.append({
            'patient_id': pid,
            'controller': str(ctrl.iloc[0]) if len(ctrl) else None,
            'n_events': int(len(grp)),
            'rec_T_min': T_star,
            'rec_M_mult': M_star,
            'baseline_overshoot': b_over,
            'baseline_hypo': b_hypo,
            'rec_cand_overshoot': c_over,
            'rec_cand_hypo': c_hypo,
            'rec_delta_over_pp': (c_over - b_over) * 100.0,
            'rec_delta_hypo_pp': (c_hypo - b_hypo) * 100.0,
        })
    rec = pd.DataFrame(rows)

    # Apply EXP-3017 clamp
    ph = pd.read_parquet(PHENO)[['patient_id', 'braking_ratio']]
    merged = rec.merge(ph, on='patient_id', how='left')
    high = merged['braking_ratio'].fillna(-1) >= CLAMP_GATE
    merged['rec_M_mult_pre_clamp'] = merged['rec_M_mult']
    merged.loc[high, 'rec_M_mult'] = 1.0
    merged['phenotype_clamped'] = high
    n_clamped_changed = int(((merged['rec_M_mult'] != merged['rec_M_mult_pre_clamp'])).sum())

    merged.to_parquet(OUT_REC)
    print(f"[{EXP_ID}] Wrote per-patient table: n={len(merged)}, "
          f"{n_clamped_changed} clamped to M=1.0 → {OUT_REC.name}")

    # Distribution comparison
    rec_3017 = pd.read_parquet(EXP_DIR / 'exp-3017_per_patient_clamped.parquet')[
        ['patient_id', 'rec_T_min', 'rec_M_mult']].rename(
        columns={'rec_T_min': 'T_3017', 'rec_M_mult': 'M_3017'})
    cmp = merged[['patient_id', 'rec_T_min', 'rec_M_mult']].merge(rec_3017, on='patient_id', how='inner')
    diff_T = (cmp['rec_T_min'] - cmp['T_3017']).abs().sum()
    diff_M = (cmp['rec_M_mult'] - cmp['M_3017']).abs().sum()
    print(f"  vs EXP-3017: |ΔT| sum = {diff_T:.1f}, |ΔM| sum = {diff_M:.3f}")

    # ----- Evaluate on verification stripe via cf_replay_score_v3 -----
    print(f"[{EXP_ID}] Evaluating on VERIFICATION stripe at gate=0.10...")
    import sys
    sys.path.insert(0, str(ROOT / 'tools' / 'aid-autoresearch'))
    import cf_replay_score_v3 as scorer  # type: ignore

    # Monkeypatch the per-patient parquet path
    orig_path = scorer.PER_PATIENT_REC_CLAMPED
    scorer.PER_PATIENT_REC_CLAMPED = OUT_REC
    try:
        kw = dict(per_patient=True, proxy='carb_aware', braking_mode='drop',
                  per_patient_source='clamped', safety_mode='stratified',
                  phenotype_source='imputed', braking_gate=0.10)
        cand = scorer.ascent_score_v3(profiles, multiplier=1.0, t_shift=0.0,
                                      events_path=VERIF, **kw)
        # Baseline at gate=0.10 with EXP-3017 clamped (current default)
        scorer.PER_PATIENT_REC_CLAMPED = orig_path
        cand_3017 = scorer.ascent_score_v3(profiles, multiplier=1.0, t_shift=0.0,
                                           events_path=VERIF, **kw)
        # Pure baseline (no per-patient, no gate, raw)
        base_kw = dict(per_patient=False, proxy='carb_aware', braking_mode='recommended',
                       per_patient_source='raw', safety_mode='stratified',
                       phenotype_source='imputed', braking_gate=None)
        base = scorer.ascent_score_v3(profiles, multiplier=1.0, t_shift=0.0,
                                      events_path=VERIF, **base_kw)
    finally:
        scorer.PER_PATIENT_REC_CLAMPED = orig_path

    delta_3028 = cand['ascent_score'] - base['ascent_score']
    delta_3017 = cand_3017['ascent_score'] - base['ascent_score']
    floor = delta_3017  # PASS = no regression vs current default
    passes_safety = bool(cand['safety_ok'])
    passes_floor = bool(delta_3028 >= floor)
    verdict = 'PASS' if (passes_safety and passes_floor) else 'FAIL'

    print(f"\n[{EXP_ID}] Verification scores:")
    print(f"  Baseline (raw):                        score={base['ascent_score']:.4f}")
    print(f"  Cand gate=0.10 + EXP-3017 (current):   score={cand_3017['ascent_score']:.4f}  "
          f"Δ=+{delta_3017:.4f}  safety_ok={cand_3017['safety_ok']}")
    print(f"  Cand gate=0.10 + EXP-3028 (carb-fit):  score={cand['ascent_score']:.4f}  "
          f"Δ=+{delta_3028:.4f}  safety_ok={cand['safety_ok']}")
    print(f"  Lift vs EXP-3017:                      {(delta_3028 - delta_3017):+.4f}")
    print(f"  Verdict: {verdict}")

    summary = {
        'exp_id': EXP_ID,
        'verdict': verdict,
        'n_patients_fit': int(len(merged)),
        'n_clamped': int(high.sum()),
        'fit_drift_vs_3017': {'sum_abs_dT': float(diff_T), 'sum_abs_dM': float(diff_M),
                              'n_compared': int(len(cmp))},
        'verification': {
            'baseline_score': base['ascent_score'],
            'cand_3017_score': cand_3017['ascent_score'],
            'cand_3028_score': cand['ascent_score'],
            'delta_3017': delta_3017,
            'delta_3028': delta_3028,
            'lift': delta_3028 - delta_3017,
            'safety_ok_3028': cand['safety_ok'],
            'safety_ok_3017': cand_3017['safety_ok'],
        },
        'pass_safety': passes_safety,
        'pass_floor': passes_floor,
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, default=float))
    print(f"  → {OUT_SUMMARY}")


if __name__ == '__main__':
    main()
