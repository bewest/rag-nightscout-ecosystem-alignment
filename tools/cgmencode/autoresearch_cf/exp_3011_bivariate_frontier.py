"""EXP-3011 — Bivariate (timing × magnitude) Pareto frontier.

Joint sweep over SMB-aggression multiplier M and earlier-firing offset T
with EXP-3010's corrected hypo accounting (120-min post-peak look-ahead).
Per controller:
  - compute (cand_overshoot, cand_hypo) on the 6 × 5 grid
  - identify Pareto-optimal points (no other point lower on BOTH axes)
  - recommend the point with maximum overshoot-reduction subject to
    cand_hypo - obs_hypo <= 1.0 pp absolute (relative gate, since the
    EXP-3010 absolute proxy is over-pessimistic but Δ is reliable)

Outputs
-------
externals/experiments/exp-3011_frontier.parquet
externals/experiments/exp-3011_summary.json
docs/60-research/figures/exp-3011_pareto.png
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

EXP_ID = 'EXP-3011'
ASCENT = Path('externals/experiments/exp-3007_ascent_events.parquet')
OUT = Path('externals/experiments')
FIG = Path('docs/60-research/figures') / f'{EXP_ID.lower()}_pareto.png'

OFFSETS_MIN = (0, 5, 10, 15, 20, 30)
MULTIPLIERS = (0.5, 1.0, 1.5, 2.0, 3.0)
WINDOW_MIN = 120
HYPO_FLOOR = 70
HYPO_DELTA_GATE_PP = 1.0   # Δhypo from baseline ≤ 1pp absolute


def evaluate_grid_point(ev: pd.DataFrame, T: float, M: float) -> pd.DataFrame:
    """Evaluate (T, M) per-controller: counterfactual overshoot + trough."""
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

    df = ev[['controller', 'hyper_overshoot']].copy()
    df['cand_overshoot'] = cand_peak >= 180
    df['cand_hypo'] = cand_trough < HYPO_FLOOR
    return df


def pareto_front(points: pd.DataFrame) -> pd.DataFrame:
    """Return Pareto-optimal rows (minimise both cand_overshoot and cand_hypo)."""
    p = points.sort_values(['cand_overshoot', 'cand_hypo']).reset_index(drop=True)
    keep = []
    best_hypo = float('inf')
    for _, r in p.iterrows():
        if r['cand_hypo'] < best_hypo - 1e-12:
            keep.append(r.name)
            best_hypo = r['cand_hypo']
    return p.loc[keep].reset_index(drop=True)


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

    rows = []
    for T in OFFSETS_MIN:
        for M in MULTIPLIERS:
            point = evaluate_grid_point(ev, T, M)
            agg = point.groupby('controller', dropna=False).agg(
                n=('hyper_overshoot', 'size'),
                obs_overshoot=('hyper_overshoot', 'mean'),
                cand_overshoot=('cand_overshoot', 'mean'),
                cand_hypo=('cand_hypo', 'mean'),
            ).reset_index()
            agg['T_min'] = T
            agg['M_mult'] = M
            rows.append(agg)
    df = pd.concat(rows, ignore_index=True)
    df.to_parquet(OUT / f'{EXP_ID.lower()}_frontier.parquet')

    # Per-controller baseline (T=0, M=1.0)
    baseline = df[(df['T_min'] == 0) & (df['M_mult'] == 1.0)].set_index('controller')

    summary = {'window_min': WINDOW_MIN, 'hypo_delta_gate_pp': HYPO_DELTA_GATE_PP,
               'grid': df.to_dict(orient='records'),
               'recommendations': {}, 'pareto_frontiers': {}}

    print(f"[{EXP_ID}] Bivariate (T × M) sweep, W={WINDOW_MIN}min, "
          f"Δhypo gate ≤ {HYPO_DELTA_GATE_PP}pp")
    print(f"  {'controller':<10}  {'T':>3}  {'M':>4}  {'cand_over':>9}  "
          f"{'cand_hypo':>9}  {'Δover_pp':>8}  {'Δhypo_pp':>8}")

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.2))
    for ax, ctrl in zip(axes, ['Loop', 'Trio', 'OpenAPS']):
        sub = df[df['controller'] == ctrl].copy()
        if not len(sub):
            continue
        bl = baseline.loc[ctrl] if ctrl in baseline.index else None
        bl_h = float(bl['cand_hypo']) if bl is not None else 0.0
        bl_o = float(bl['cand_overshoot']) if bl is not None else 0.0

        sub['delta_over_pp'] = (sub['cand_overshoot'] - bl_o) * 100
        sub['delta_hypo_pp'] = (sub['cand_hypo'] - bl_h) * 100
        front = pareto_front(sub[['T_min', 'M_mult', 'cand_overshoot', 'cand_hypo']])
        front['delta_over_pp'] = (front['cand_overshoot'] - bl_o) * 100
        front['delta_hypo_pp'] = (front['cand_hypo'] - bl_h) * 100
        summary['pareto_frontiers'][ctrl] = front.to_dict(orient='records')

        # Recommend: best Δover within Δhypo gate
        elig = sub[sub['delta_hypo_pp'] <= HYPO_DELTA_GATE_PP]
        if len(elig):
            rec = elig.sort_values('delta_over_pp').iloc[0]
            summary['recommendations'][ctrl] = {
                'T_min': int(rec['T_min']), 'M_mult': float(rec['M_mult']),
                'delta_overshoot_pp': float(rec['delta_over_pp']),
                'delta_hypo_pp': float(rec['delta_hypo_pp']),
                'cand_overshoot': float(rec['cand_overshoot']),
                'cand_hypo': float(rec['cand_hypo']),
            }
            print(f"  {ctrl:<10}  RECOMMENDED  T={int(rec['T_min'])}  "
                  f"M={float(rec['M_mult'])}  Δover={rec['delta_over_pp']:+.2f}pp  "
                  f"Δhypo={rec['delta_hypo_pp']:+.3f}pp")

        sc = ax.scatter(sub['delta_hypo_pp'], sub['delta_over_pp'],
                        c=sub['T_min'], s=sub['M_mult'] * 30, cmap='viridis',
                        alpha=0.7, edgecolor='k', linewidth=0.4)
        ax.plot(front['delta_hypo_pp'], front['delta_over_pp'],
                'r-', linewidth=1.5, alpha=0.6, label='Pareto front')
        ax.axvline(HYPO_DELTA_GATE_PP, color='gray', linestyle='--', linewidth=0.8,
                   label=f'{HYPO_DELTA_GATE_PP}pp hypo gate')
        ax.scatter([0], [0], color='black', marker='*', s=120, label='baseline',
                   zorder=5)
        ax.set_xlabel('Δ hypo-rate (pp)'); ax.set_ylabel('Δ overshoot rate (pp)')
        ax.set_title(f'{ctrl}: T×M frontier')
        ax.grid(alpha=0.3); ax.legend(fontsize=7, loc='upper right')
        plt.colorbar(sc, ax=ax, label='T (min)')
    fig.suptitle(f'{EXP_ID}  Bivariate Pareto (color=T, size=M)', y=1.02)
    fig.tight_layout(); fig.savefig(FIG, dpi=120, bbox_inches='tight'); plt.close(fig)

    (OUT / f'{EXP_ID.lower()}_summary.json').write_text(
        json.dumps(summary, indent=2, default=float))
    print(f"\n[{EXP_ID}] {len(df)} grid points; figure → {FIG}")


if __name__ == '__main__':
    main()
