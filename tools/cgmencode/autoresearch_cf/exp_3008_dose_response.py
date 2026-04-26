"""EXP-3008 — Controller-discriminating cf-replay (dose-response).

Sweeps an SMB aggression multiplier ∈ {0.0, 0.5, 1.0, 1.5, 2.0, 3.0} applied
to the observed `smb_during` per ascent event (from EXP-3007), re-replays
through the EXP-3004 engine, and reports the resulting overshoot rate AND
the candidate's predicted hypo risk via a 60-min look-ahead penalty.

This discriminates candidate controllers along a single axis ("how
aggressively should the controller dose during ascents?") and exposes the
classic safety/efficacy trade-off:

  multiplier ↑  →  overshoot ↓  AND  hypo-risk ↑

The candidate score combines:
  60 % overshoot-prevention + 40 % hypo-safety penalty
A multiplier scoring above the observed (1.0) baseline is considered a
*plausible improvement candidate*. Multiple controllers (Loop, Trio,
AAPS) get scored separately so we can see the lever each has remaining.

Outputs:
  externals/experiments/exp-3008_dose_response.parquet
  externals/experiments/exp-3008_summary.json
  docs/60-research/figures/exp-3008_dose_response.png
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
from tools.cgmencode.autoresearch_cf.exp_3004_ascent_replay import (
    kernel_fraction, PEAK_MIN)

EXP_ID = 'EXP-3008'
ASCENT = Path('externals/experiments/exp-3007_ascent_events.parquet')
OUT = Path('externals/experiments')
FIG = Path('docs/60-research/figures') / f'{EXP_ID.lower()}_dose_response.png'

MULTIPLIERS = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0)
HYPO_FLOOR = 70   # mg/dL
# 60-min look-ahead post-peak: extra SMB above baseline contributes to hypo
# risk via its FULL kernel by post-peak+60min (peak is at descent_start)
LOOKAHEAD_MIN = 60


def candidate_score(events: pd.DataFrame, mult: float) -> dict:
    """Score the candidate at a given SMB-aggression multiplier."""
    ev = events.copy()
    # Counterfactual SMB delivered = observed × multiplier
    ev['smb_candidate'] = ev['smb_during'].fillna(0) * mult
    extra_smb = ev['smb_candidate'] - ev['smb_during'].fillna(0)

    # Effect on PEAK: kernel fraction at midpoint of ascent window
    peak_drop = (ev['smb_candidate'] * ev['kernel_factor'] * ev['isf_used'])
    ev['cand_peak'] = ev['bg_peak'] - (
        peak_drop - ev['smb_during'].fillna(0) * ev['kernel_factor'] * ev['isf_used'])
    ev['cand_overshoot'] = ev['cand_peak'] >= 180

    # Effect on POST-PEAK 60min: full kernel contribution from extra SMB acts
    # over a longer (peak→peak+60) window, fraction at midpoint=30min
    tail_t = LOOKAHEAD_MIN / 2.0
    tail_frac = 1.0 - (1.0 + tail_t / PEAK_MIN) * np.exp(-tail_t / PEAK_MIN)
    extra_post_drop = extra_smb * tail_frac * ev['isf_used']
    # Use bg at peak-60min as proxy for "trajectory floor under candidate"
    # (we don't have time-series here; assume worst case = bg_peak - peak_drop
    # - extra_post_drop). Hypo if below HYPO_FLOOR.
    ev['cand_floor_proxy'] = (ev['cand_peak'] - extra_post_drop).clip(lower=0)
    ev['cand_hypo'] = ev['cand_floor_proxy'] < HYPO_FLOOR

    by_ctrl = ev.groupby('controller', dropna=False).agg(
        n=('bg_peak', 'size'),
        obs_overshoot=('hyper_overshoot', 'mean'),
        cand_overshoot=('cand_overshoot', 'mean'),
        cand_hypo_rate=('cand_hypo', 'mean'),
        mean_extra_smb=('smb_candidate', lambda s: float(s.mean())),
    ).reset_index()
    by_ctrl['multiplier'] = mult
    by_ctrl['delta_overshoot'] = by_ctrl['cand_overshoot'] - by_ctrl['obs_overshoot']
    # Score: 60% prevention (lower overshoot is better), 40% safety
    by_ctrl['cand_score'] = (
        0.60 * (1.0 - by_ctrl['cand_overshoot']) +
        0.40 * (1.0 - 2 * by_ctrl['cand_hypo_rate']).clip(lower=0))
    return by_ctrl


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
    ev['kernel_factor'] = kernel_fraction(ev['duration_min'])

    rows = []
    for m in MULTIPLIERS:
        rows.append(candidate_score(ev, m))
    df = pd.concat(rows, ignore_index=True)
    df.to_parquet(OUT / f'{EXP_ID.lower()}_dose_response.parquet')

    # Find best multiplier per controller
    best = (df.sort_values('cand_score', ascending=False)
              .groupby('controller', dropna=False).first().reset_index())

    summary = {
        'multipliers': list(MULTIPLIERS),
        'lookahead_min': LOOKAHEAD_MIN,
        'hypo_floor_mgdl': HYPO_FLOOR,
        'curve': df.to_dict(orient='records'),
        'best_per_controller': best[['controller', 'multiplier',
                                     'obs_overshoot', 'cand_overshoot',
                                     'cand_hypo_rate', 'cand_score']].to_dict(orient='records'),
    }
    (OUT / f'{EXP_ID.lower()}_summary.json').write_text(
        json.dumps(summary, indent=2, default=float))

    # Plot dose-response curves per controller
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ctrl in df['controller'].dropna().unique():
        sub = df[df['controller'] == ctrl].sort_values('multiplier')
        axes[0].plot(sub['multiplier'], sub['cand_overshoot'], marker='o', label=str(ctrl))
        axes[1].plot(sub['multiplier'], sub['cand_hypo_rate'], marker='o', label=str(ctrl))
    axes[0].set_xlabel('SMB aggression multiplier'); axes[0].set_ylabel('Overshoot rate')
    axes[0].set_title('Overshoot ↓ as SMB aggression ↑'); axes[0].legend(fontsize=8); axes[0].grid(alpha=0.3)
    axes[1].set_xlabel('SMB aggression multiplier'); axes[1].set_ylabel('Hypo-risk rate (proxy)')
    axes[1].set_title('Hypo-risk ↑ as SMB aggression ↑'); axes[1].legend(fontsize=8); axes[1].grid(alpha=0.3)
    fig.suptitle(f'{EXP_ID}  Controller-discriminating dose-response', y=1.02)
    fig.tight_layout(); fig.savefig(FIG, dpi=120, bbox_inches='tight'); plt.close(fig)

    print(f"[{EXP_ID}] dose-response sweep over multipliers {MULTIPLIERS}")
    print(f"  {'controller':<10}  {'mult':>5}  {'obs_over':>8}  "
          f"{'cand_over':>9}  {'cand_hypo':>9}  {'score':>6}")
    for _, r in df.sort_values(['controller', 'multiplier']).iterrows():
        print(f"  {str(r['controller']):<10}  {r['multiplier']:>5.1f}  "
              f"{r['obs_overshoot']:>8.3%}  {r['cand_overshoot']:>9.3%}  "
              f"{r['cand_hypo_rate']:>9.3%}  {r['cand_score']:>6.3f}")
    print(f"\n[{EXP_ID}] Best multiplier per controller:")
    for _, r in best.iterrows():
        print(f"  {str(r['controller']):<10}  best_mult={r['multiplier']}  "
              f"score={r['cand_score']:.3f}  cand_overshoot={r['cand_overshoot']:.3%}  "
              f"cand_hypo={r['cand_hypo_rate']:.3%}")
    print(f"  → {FIG}")


if __name__ == '__main__':
    main()
