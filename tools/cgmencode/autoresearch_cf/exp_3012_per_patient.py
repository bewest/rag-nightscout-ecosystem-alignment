"""EXP-3012 — Per-patient (T*, M*) recommendation.

Phase 2 (EXP-3011) recommended (T=+30, M=0.5x) per-CONTROLLER. This
experiment evaluates the same bivariate grid PER PATIENT and reports each
patient's optimal point under the relative 1pp delta-hypo gate. Three
quantities of interest:

1. Where does each patient currently sit on the frontier?
2. Which patients have the largest unrealised benefit?
3. Does within-controller heterogeneity exceed between-controller spread?

Outputs
-------
externals/experiments/exp-3012_per_patient.parquet
externals/experiments/exp-3012_summary.json
docs/60-research/figures/exp-3012_per_patient.png
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from tools.cgmencode.autoresearch_cf import replay
from tools.cgmencode.autoresearch_cf.exp_3009_timing_axis import kernel_at

EXP_ID = 'EXP-3012'
ASCENT = Path('externals/experiments/exp-3007_ascent_events.parquet')
OUT = Path('externals/experiments')
FIG = Path('docs/60-research/figures') / f'{EXP_ID.lower()}_per_patient.png'

OFFSETS_MIN = (0, 5, 10, 15, 20, 30)
MULTIPLIERS = (0.5, 1.0, 1.5, 2.0, 3.0)
WINDOW_MIN = 120
HYPO_FLOOR = 70
HYPO_DELTA_GATE_PP = 1.0
MIN_EVENTS = 30   # patient must have ≥ 30 ascent events to recommend


def evaluate_grid_point(ev: pd.DataFrame, T: float, M: float) -> pd.DataFrame:
    half = ev['duration_min'].to_numpy() / 2.0
    eff_off = np.minimum(T, ev['duration_min'].to_numpy())
    t_peak = half + eff_off
    smb_obs = ev['smb_during'].fillna(0).to_numpy()
    smb_cand = smb_obs * M
    isf = ev['isf_used'].to_numpy()

    drop_at_peak = smb_cand * kernel_at(t_peak) * isf
    drop_at_peak_baseline = smb_obs * kernel_at(half) * isf
    cand_peak = ev['bg_peak'].to_numpy() - (drop_at_peak - drop_at_peak_baseline)
    extra_post = (kernel_at(t_peak + WINDOW_MIN) - kernel_at(t_peak)) * smb_cand * isf
    cand_trough = cand_peak - extra_post
    return pd.DataFrame({
        'patient_id': ev['patient_id'].to_numpy(),
        'controller': ev['controller'].to_numpy(),
        'cand_overshoot': cand_peak >= 180,
        'cand_hypo': cand_trough < HYPO_FLOOR,
        'obs_overshoot': ev['hyper_overshoot'].to_numpy(),
    })


def main() -> None:
    ev = pd.read_parquet(ASCENT)
    _, _, profiles = replay.load_inputs()
    isf_map = {}
    for pid in ev['patient_id'].unique():
        prof = profiles[(profiles['patient_id'] == pid) &
                        (profiles['schedule_type'] == 'isf')]
        vals = prof['value'].dropna() if len(prof) else pd.Series(dtype=float)
        vals = vals[(vals >= 30) & (vals <= 200)]
        isf_map[pid] = float(vals.median()) if len(vals) else 50.0
    ev['isf_used'] = ev['patient_id'].map(isf_map)

    # Build full (patient, T, M) table
    rows = []
    for T in OFFSETS_MIN:
        for M in MULTIPLIERS:
            point = evaluate_grid_point(ev, T, M)
            agg = point.groupby(['patient_id', 'controller'], dropna=False).agg(
                n=('cand_overshoot', 'size'),
                obs_overshoot=('obs_overshoot', 'mean'),
                cand_overshoot=('cand_overshoot', 'mean'),
                cand_hypo=('cand_hypo', 'mean'),
            ).reset_index()
            agg['T_min'] = T; agg['M_mult'] = M
            rows.append(agg)
    df = pd.concat(rows, ignore_index=True)

    baseline = df[(df['T_min'] == 0) & (df['M_mult'] == 1.0)].set_index('patient_id')

    # Per-patient recommendation: max overshoot reduction subject to Δhypo ≤ 1pp
    recs = []
    for pid, sub in df.groupby('patient_id'):
        if pid not in baseline.index:
            continue
        bl_o = float(baseline.loc[pid, 'cand_overshoot'])
        bl_h = float(baseline.loc[pid, 'cand_hypo'])
        n = int(baseline.loc[pid, 'n'])
        if n < MIN_EVENTS:
            continue
        sub = sub.copy()
        sub['delta_over_pp'] = (sub['cand_overshoot'] - bl_o) * 100
        sub['delta_hypo_pp'] = (sub['cand_hypo'] - bl_h) * 100
        elig = sub[sub['delta_hypo_pp'] <= HYPO_DELTA_GATE_PP]
        if not len(elig):
            continue
        rec = elig.sort_values('delta_over_pp').iloc[0]
        recs.append({
            'patient_id': pid,
            'controller': rec['controller'],
            'n_events': n,
            'baseline_overshoot': bl_o,
            'baseline_hypo': bl_h,
            'rec_T_min': int(rec['T_min']),
            'rec_M_mult': float(rec['M_mult']),
            'rec_delta_over_pp': float(rec['delta_over_pp']),
            'rec_delta_hypo_pp': float(rec['delta_hypo_pp']),
            'rec_cand_overshoot': float(rec['cand_overshoot']),
            'rec_cand_hypo': float(rec['cand_hypo']),
        })
    rec_df = pd.DataFrame(recs).sort_values('rec_delta_over_pp')
    rec_df.to_parquet(OUT / f'{EXP_ID.lower()}_per_patient.parquet')
    df.to_parquet(OUT / f'{EXP_ID.lower()}_grid.parquet')

    # Headline analysis
    n_pareto = int((rec_df['rec_delta_over_pp'] < 0).sum())
    n_already = int((rec_df['rec_T_min'] == 0).sum() & (rec_df['rec_M_mult'] == 1.0).sum())
    summary = {
        'n_patients_recommended': int(len(rec_df)),
        'n_with_pareto_improvement': n_pareto,
        'n_already_at_optimum': n_already,
        'controller_breakdown': {},
        'recommendation_distribution': {
            f'T={int(t)}_M={float(m):.1f}': int(n)
            for (t, m), n in rec_df.groupby(['rec_T_min', 'rec_M_mult']).size().items()
        },
    }
    for ctrl, sub in rec_df.groupby('controller', dropna=False):
        summary['controller_breakdown'][str(ctrl)] = {
            'n': int(len(sub)),
            'mean_delta_over_pp': float(sub['rec_delta_over_pp'].mean()),
            'median_delta_over_pp': float(sub['rec_delta_over_pp'].median()),
            'std_delta_over_pp': float(sub['rec_delta_over_pp'].std(ddof=0)),
            'mean_rec_T': float(sub['rec_T_min'].mean()),
            'mean_rec_M': float(sub['rec_M_mult'].mean()),
        }
    (OUT / f'{EXP_ID.lower()}_summary.json').write_text(
        json.dumps(summary, indent=2, default=float))

    # Within-vs-between heterogeneity (eta^2 of controller on rec_delta_over_pp)
    if rec_df['controller'].nunique() > 1:
        grand_mean = rec_df['rec_delta_over_pp'].mean()
        ss_total = float(((rec_df['rec_delta_over_pp'] - grand_mean) ** 2).sum())
        ss_between = 0.0
        for _, sub in rec_df.groupby('controller', dropna=False):
            ss_between += len(sub) * (sub['rec_delta_over_pp'].mean() - grand_mean) ** 2
        eta2 = ss_between / ss_total if ss_total > 0 else float('nan')
        summary['eta2_controller_on_benefit'] = float(eta2)
        (OUT / f'{EXP_ID.lower()}_summary.json').write_text(
            json.dumps(summary, indent=2, default=float))

    # Print
    print(f"[{EXP_ID}] {len(rec_df)} patients with recommendations  "
          f"({n_pareto} Pareto improvements; {n_already} already at optimum)")
    print(f"\n  Per-controller benefit distribution:")
    for ctrl, st in summary['controller_breakdown'].items():
        print(f"    {ctrl:<10}  n={st['n']:>2}  mean Δover={st['mean_delta_over_pp']:+6.2f}pp  "
              f"std={st['std_delta_over_pp']:5.2f}  mean T*={st['mean_rec_T']:4.1f}  "
              f"mean M*={st['mean_rec_M']:.2f}")
    if 'eta2_controller_on_benefit' in summary:
        print(f"\n  eta^2(controller→benefit) = {summary['eta2_controller_on_benefit']:.3f}  "
              f"(>0.5 = controller dominates; <0.2 = patient dominates)")
    print(f"\n  Recommendation distribution (T, M) → n patients:")
    for key, n in sorted(summary['recommendation_distribution'].items()):
        print(f"    {key}  →  n={n}")
    print(f"\n  Top-5 patients with largest unrealised benefit:")
    for _, r in rec_df.head(5).iterrows():
        print(f"    {r['patient_id']:<20}  ctrl={r['controller']:<8}  "
              f"T*={r['rec_T_min']:>2}  M*={r['rec_M_mult']:.1f}  "
              f"Δover={r['rec_delta_over_pp']:+6.2f}pp  Δhypo={r['rec_delta_hypo_pp']:+5.2f}pp")

    # Figure
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6))
    if len(rec_df):
        ctrls = sorted(rec_df['controller'].dropna().unique().tolist())
        colors = {c: f'C{i}' for i, c in enumerate(ctrls)}
        for ctrl in ctrls:
            sub = rec_df[rec_df['controller'] == ctrl]
            axes[0].scatter(sub['rec_T_min'] + np.random.uniform(-1.5, 1.5, len(sub)),
                            sub['rec_M_mult'] + np.random.uniform(-0.05, 0.05, len(sub)),
                            s=80, alpha=0.7, edgecolor='k', linewidth=0.5,
                            color=colors[ctrl], label=ctrl)
        axes[0].set_xlabel('Recommended T* (min)')
        axes[0].set_ylabel('Recommended M*')
        axes[0].set_title('Per-patient recommendations (jittered)')
        axes[0].legend(fontsize=8); axes[0].grid(alpha=0.3)
        axes[0].axvline(30, color='gray', linestyle=':', alpha=0.5)
        axes[0].axhline(0.5, color='gray', linestyle=':', alpha=0.5)
        axes[0].annotate('Phase 2\nrec', xy=(30, 0.5), xytext=(22, 0.7),
                         fontsize=8, color='gray',
                         arrowprops=dict(arrowstyle='->', color='gray', alpha=0.5))

        for ctrl in ctrls:
            sub = rec_df[rec_df['controller'] == ctrl]
            axes[1].hist(sub['rec_delta_over_pp'], bins=15, alpha=0.6,
                         label=f'{ctrl} (n={len(sub)})', color=colors[ctrl])
        axes[1].axvline(0, color='black', linestyle='-', linewidth=0.8)
        axes[1].set_xlabel('Δoversht_pp at recommended (T*, M*)')
        axes[1].set_ylabel('# patients')
        axes[1].set_title('Per-patient unrealised benefit')
        axes[1].legend(fontsize=8); axes[1].grid(alpha=0.3)
    fig.suptitle(f'{EXP_ID}  Per-patient (T*, M*) recommendation', y=1.02)
    fig.tight_layout(); fig.savefig(FIG, dpi=120, bbox_inches='tight'); plt.close(fig)
    print(f"\n  → {FIG}")


if __name__ == '__main__':
    main()
