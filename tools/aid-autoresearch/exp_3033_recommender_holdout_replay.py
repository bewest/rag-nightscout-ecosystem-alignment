"""EXP-3033 — Held-out cf-replay validation of EXP-3022b recommendations.

Closes the recommender loop. The EXP-3022b pipeline issues per-patient
ISF/CR/basal/correction-threshold recommendations on training data,
each tagged with a `predicted_tir_delta` (e.g., +7.6 pp for patient g
ISF-increase, +5.8 pp for patient a ISF-decrease). Question: do those
recommendations transport to a *truly held-out* stripe (verification-2,
post-2026-04-19 fresh refetch from EXP-3031) under cf-replay scoring?

Method:
1. Restrict to EXP-3022b patients that exist in verification-2: g, i, a.
   (Trio ns-* and AAPS odc-* patients have no refresh path.)
2. For each patient, extract the ISF recommendation multiplier from
   `reports/exp-3022b/{pid}/pipeline.json`.
3. Map ISF → SMB scaling: a recommended ISF *increase* by r_isf means
   the patient is more insulin-sensitive than the profile assumed, so
   the same correction would produce a larger BG drop — equivalent to
   needing less insulin per unit BG, i.e., M_equiv = 1 / r_isf.
4. Apply M_equiv per-patient to verification-2 ascent events via
   cf_eval (the v3 scorer's per-event kernel). Compare overshoot rate
   and hypo rate vs baseline (M=1.0).
5. Verdict: recommendation transports if cf_score sign matches
   predicted_tir_delta sign for each patient.

Caveats / scope:
- ISF→M mapping is exact for the cf-replay model (linear in dose).
- CR recommendations are NOT included: CR drives meal-bolus sizing,
  which doesn't enter the ascent-event cf-replay kernel cleanly.
- basal_rate / correction_threshold also fall outside the kernel.
- ISF-decrease recs (M_equiv > 1) raise overshoot and hypo risk;
  cf-replay-v3 safety gate can flag these.

Outputs:
  externals/experiments/exp-3033_holdout_replay.json
  externals/experiments/exp-3033_holdout_replay.parquet
  docs/60-research/figures/exp-3033_predicted_vs_observed.png
  docs/60-research/exp-3033-recommender-holdout-replay-2026-04-27.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Make the v3 scorer importable as a module.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools' / 'aid-autoresearch'))
from cf_replay_score_v3 import cf_eval, _isf_map  # noqa: E402

ASCENT = ROOT / 'externals' / 'experiments' / 'exp-3007_ascent_events__verification2.parquet'
PROFILES = ROOT / 'externals' / 'ns-parquet' / 'training' / 'profiles.parquet'
EXP3022B_DIR = ROOT / 'reports' / 'exp-3022b'
OUT_JSON = ROOT / 'externals' / 'experiments' / 'exp-3033_holdout_replay.json'
OUT_PARQ = ROOT / 'externals' / 'experiments' / 'exp-3033_holdout_replay.parquet'
FIG_PATH = ROOT / 'docs' / '60-research' / 'figures' / 'exp-3033_predicted_vs_observed.png'

EXP_ID = 'EXP-3033'


def extract_isf_mult(pid: str) -> tuple[float | None, float | None]:
    """Return (isf_multiplier, predicted_tir_delta_pp) for the ISF rec.

    Returns (None, None) if no ISF rec was issued for this patient.
    """
    pipe = json.loads((EXP3022B_DIR / pid / 'pipeline.json').read_text())
    for r in pipe.get('settings_recs', []):
        rat = (r.get('rationale', '') or '').lower()
        ev = (r.get('evidence', '') or '').lower()
        if 'isf' not in rat and 'isf' not in ev:
            continue
        cur = r.get('current_value')
        sug = r.get('suggested_value')
        if not cur or not sug:
            continue
        return float(sug) / float(cur), float(r.get('predicted_tir_delta', 0.0))
    return None, None


def main() -> None:
    print(f'[{EXP_ID}] Loading verification-2 ascent events from {ASCENT}')
    if not ASCENT.exists():
        sys.exit(f'ERROR: missing {ASCENT}; run EXP-3007 with --source verification2 first.')
    ev = pd.read_parquet(ASCENT)
    profiles = pd.read_parquet(PROFILES)
    ev['isf_used'] = ev['patient_id'].map(_isf_map(profiles, ev['patient_id'].unique().tolist()))
    print(f'  → {len(ev)} ascent events across {ev["patient_id"].nunique()} patients')

    # Per-patient ISF→M mapping (only for EXP-3022b patients that are in verif2).
    rec_pids = sorted([p.name for p in EXP3022B_DIR.iterdir()
                       if p.is_dir() and (p / 'pipeline.json').exists()])
    in_v2 = set(ev['patient_id'].unique())
    intersect = sorted(set(rec_pids) & in_v2)
    print(f'  → recommender patients in verif-2: {intersect}')

    rec_table_rows = []
    for pid in intersect:
        isf_mult, pred_tir = extract_isf_mult(pid)
        if isf_mult is None:
            continue
        m_equiv = 1.0 / isf_mult
        rec_table_rows.append({
            'patient_id': pid,
            'isf_mult': isf_mult,
            'M_equiv': m_equiv,
            'pred_tir_delta_pp': pred_tir,
        })
    rec_df = pd.DataFrame(rec_table_rows)
    if rec_df.empty:
        sys.exit(f'ERROR: no ISF recommendations found for verif-2 patients.')
    print(f'\n[{EXP_ID}] Recommendation map (ISF rec → SMB-equivalent M):')
    for _, r in rec_df.iterrows():
        print(f'  {r["patient_id"]:6s} ISF×{r["isf_mult"]:.3f}  →  M={r["M_equiv"]:.3f}  '
              f'(predicted ΔTIR={r["pred_tir_delta_pp"]:+.1f} pp)')

    # Build per-event M array: candidate = 1/isf_mult for recommended pts;
    # all other patients get M=1.0 (no recommendation = no perturbation).
    pid_to_m = dict(zip(rec_df['patient_id'], rec_df['M_equiv']))
    M_cand = ev['patient_id'].map(pid_to_m).fillna(1.0).to_numpy()
    T_zero = np.zeros(len(ev))
    M_base = np.ones(len(ev))

    print(f'\n[{EXP_ID}] Running cf_eval (baseline M=1 vs candidate M=1/r_isf) ...')
    base = cf_eval(ev.copy(), T_zero, M_base, proxy='carb_aware')
    cand = cf_eval(ev.copy(), T_zero, M_cand, proxy='carb_aware')

    # Continuous peak/trough deltas (more sensitive than the binary
    # 180 mg/dL crossing). Re-derive using the same kernel as cf_eval.
    from cf_replay_score_v3 import kernel_at, WINDOW_MIN  # noqa: E402
    smb_obs = ev['smb_during'].fillna(0).to_numpy()
    isf_arr = ev['isf_used'].to_numpy()
    half_arr = ev['duration_min'].to_numpy() / 2.0

    def _peak_trough(M_arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        smb_cand_v = smb_obs * M_arr
        eff_off = np.minimum(np.zeros(len(ev)), ev['duration_min'].to_numpy())
        t_peak = half_arr + eff_off
        drop_peak = smb_cand_v * kernel_at(t_peak) * isf_arr
        drop_peak_base = smb_obs * kernel_at(half_arr) * isf_arr
        peak = ev['bg_peak'].to_numpy() - (drop_peak - drop_peak_base)
        extra_post = (kernel_at(t_peak + WINDOW_MIN) - kernel_at(t_peak)) * smb_cand_v * isf_arr
        trough = peak - extra_post
        return peak, trough

    base_peak, base_trough = _peak_trough(M_base)
    cand_peak, cand_trough = _peak_trough(M_cand)

    cont = pd.DataFrame({
        'patient_id': ev['patient_id'].to_numpy(),
        'base_peak': base_peak, 'cand_peak': cand_peak,
        'base_trough': base_trough, 'cand_trough': cand_trough,
    })
    cont_per_pt = cont.groupby('patient_id').agg(
        cand_peak_mean=('cand_peak', 'mean'),
        base_peak_mean=('base_peak', 'mean'),
        cand_trough_mean=('cand_trough', 'mean'),
        base_trough_mean=('base_trough', 'mean'),
    ).reset_index()
    # peak_lift_mgdl > 0 means candidate REDUCED the peak (good for hyper).
    cont_per_pt['peak_lift_mgdl'] = cont_per_pt['base_peak_mean'] - cont_per_pt['cand_peak_mean']
    # trough_lift_mgdl > 0 means candidate RAISED the trough (good for hypo).
    cont_per_pt['trough_lift_mgdl'] = cont_per_pt['cand_trough_mean'] - cont_per_pt['base_trough_mean']

    # Per-patient observed deltas (binary) for safety check.
    base_per_pt = base.groupby('patient_id').agg(
        n=('cand_overshoot', 'size'),
        base_overshoot=('cand_overshoot', 'mean'),
        base_hypo=('cand_hypo', 'mean')).reset_index()
    cand_per_pt = cand.groupby('patient_id').agg(
        cand_overshoot=('cand_overshoot', 'mean'),
        cand_hypo=('cand_hypo', 'mean')).reset_index()
    per_pt = base_per_pt.merge(cand_per_pt, on='patient_id', how='left')
    per_pt = per_pt.merge(cont_per_pt, on='patient_id', how='left')
    per_pt = per_pt.merge(rec_df, on='patient_id', how='left')

    # Composite TIR-proxy lift on the held-out stripe (pp):
    #   = -(overshoot_delta) - (hypo_delta)   in pp
    # Positive when candidate reduces hyper and/or hypo on the held-out
    # ascent events (matches the EXP-3022b predicted_tir_delta sign
    # convention).
    per_pt['observed_overshoot_delta_pp'] = (per_pt['cand_overshoot'] - per_pt['base_overshoot']) * 100.0
    per_pt['observed_hypo_delta_pp'] = (per_pt['cand_hypo'] - per_pt['base_hypo']) * 100.0
    per_pt['observed_tir_proxy_pp'] = (
        -per_pt['observed_overshoot_delta_pp'] - per_pt['observed_hypo_delta_pp']
    )

    # Restrict verdict to recommender patients only.
    rec_only = per_pt[per_pt['pred_tir_delta_pp'].notna()].copy()
    print(f'\n[{EXP_ID}] Per-patient verdict on verification-2 (recommender subset):')
    cols = ['patient_id', 'n', 'pred_tir_delta_pp', 'M_equiv',
            'peak_lift_mgdl', 'trough_lift_mgdl',
            'observed_overshoot_delta_pp', 'observed_hypo_delta_pp',
            'observed_tir_proxy_pp']
    print(rec_only[cols].to_string(index=False))

    # Sign agreement: predicted +TIR should yield observed +TIR-proxy.
    rec_only['sign_agrees'] = (
        (rec_only['pred_tir_delta_pp'] > 0) == (rec_only['observed_tir_proxy_pp'] > 0)
    )
    n_agree = int(rec_only['sign_agrees'].sum())
    n_total = len(rec_only)
    print(f'\n[{EXP_ID}] Sign agreement (TIR-proxy): {n_agree}/{n_total}')

    # Cohort-level summary on the recommended subset only.
    rec_pid_mask = ev['patient_id'].isin(rec_df['patient_id'])
    n_rec_events = int(rec_pid_mask.sum())
    base_sub = base[rec_pid_mask].copy()
    cand_sub = cand[rec_pid_mask].copy()
    cohort = {
        'n_events_recommended_subset': n_rec_events,
        'baseline_overshoot': float(base_sub['cand_overshoot'].mean()),
        'candidate_overshoot': float(cand_sub['cand_overshoot'].mean()),
        'baseline_hypo': float(base_sub['cand_hypo'].mean()),
        'candidate_hypo': float(cand_sub['cand_hypo'].mean()),
    }
    cohort['overshoot_delta_pp'] = (cohort['candidate_overshoot'] - cohort['baseline_overshoot']) * 100.0
    cohort['hypo_delta_pp'] = (cohort['candidate_hypo'] - cohort['baseline_hypo']) * 100.0
    cohort['ascent_lift_pp'] = -cohort['overshoot_delta_pp']
    cohort['tir_proxy_pp'] = -cohort['overshoot_delta_pp'] - cohort['hypo_delta_pp']
    print(f'\n[{EXP_ID}] Cohort (recommended subset, n={n_rec_events}):')
    for k, v in cohort.items():
        print(f'  {k:32s} = {v:.4f}' if isinstance(v, float) else f'  {k:32s} = {v}')

    # ---- Plot ----
    try:
        import matplotlib.pyplot as plt
        FIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(7, 5))
        x = rec_only['pred_tir_delta_pp'].astype(float)
        y = rec_only['observed_tir_proxy_pp'].astype(float)
        ax.scatter(x, y, s=120, c=['#2ecc71' if a else '#e74c3c' for a in rec_only['sign_agrees']],
                   edgecolor='black', zorder=3)
        for _, r in rec_only.iterrows():
            ax.annotate(f"  {r['patient_id']} (n={int(r['n'])})",
                        (r['pred_tir_delta_pp'], r['observed_tir_proxy_pp']),
                        fontsize=10)
        # Quadrant guides
        lim = float(max(abs(x).max(), abs(y).max())) * 1.3 + 1
        ax.axhline(0, color='gray', lw=0.6); ax.axvline(0, color='gray', lw=0.6)
        ax.plot([-lim, lim], [-lim, lim], '--', color='gray', lw=0.5,
                label='y=x (perfect transport)')
        ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim)
        ax.set_xlabel('Predicted ΔTIR (pp, from EXP-3022b ISF rec)')
        ax.set_ylabel('Observed TIR-proxy lift on verification-2 (pp)\n[= −Δovershoot − Δhypo]')
        ax.set_title(f'{EXP_ID}: Recommendation transport on held-out stripe\n'
                     f'(green = sign agrees, red = sign flips)')
        ax.legend(loc='lower right', fontsize=8)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(FIG_PATH, dpi=110)
        plt.close(fig)
        print(f'[{EXP_ID}] figure: {FIG_PATH}')
    except Exception as e:
        print(f'[{EXP_ID}] WARNING: plot failed ({e!r})', file=sys.stderr)

    # ---- Persist ----
    OUT_PARQ.parent.mkdir(parents=True, exist_ok=True)
    per_pt.to_parquet(OUT_PARQ, index=False)
    OUT_JSON.write_text(json.dumps({
        'exp_id': EXP_ID,
        'source': 'verification2',
        'recommended_patients': intersect,
        'per_patient': per_pt.to_dict(orient='records'),
        'cohort': cohort,
        'sign_agreement': {'n_agree': n_agree, 'n_total': n_total},
    }, indent=2, default=float))
    print(f'[{EXP_ID}] artifacts: {OUT_JSON}, {OUT_PARQ}')


if __name__ == '__main__':
    main()
