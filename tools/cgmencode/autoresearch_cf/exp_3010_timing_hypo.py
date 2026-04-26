"""EXP-3010 — Timing-axis hypo-redistribution check.

EXP-3009 assumed earlier-firing has zero hypo penalty because total insulin
units are unchanged. This experiment tests that assumption honestly: shifting
SMB earlier also shifts where the kernel CURVE peaks, potentially deepening
the post-peak trough.

For each ascent event with shift T, integrate the kernel from delivery time
through DIA. Quantify post-peak insulin effect over [peak, peak+60] and
[peak, peak+120] and check trough proxy against the hypo floor.

Trough proxy
------------
cf_trough = cf_peak - [kernel(t_peak + W) - kernel(t_peak)] * smb * isf

where t_peak = duration_min/2 + T (time-from-delivery-to-peak under shift)
and W is the post-peak look-ahead window in minutes.

Outputs
-------
externals/experiments/exp-3010_timing_hypo.parquet
externals/experiments/exp-3010_summary.json
docs/60-research/figures/exp-3010_timing_hypo.png
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
from tools.cgmencode.autoresearch_cf.exp_3009_timing_axis import (
    kernel_at, candidate_timing, OFFSETS_MIN as _OFF)

EXP_ID = 'EXP-3010'
ASCENT = Path('externals/experiments/exp-3007_ascent_events.parquet')
OUT = Path('externals/experiments')
FIG = Path('docs/60-research/figures') / f'{EXP_ID.lower()}_timing_hypo.png'

OFFSETS_MIN = (0, 5, 10, 15, 20, 30)
WINDOWS_MIN = (60, 120)
HYPO_FLOOR = 70


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
    for off in OFFSETS_MIN:
        sub = candidate_timing(ev, off)
        smb = sub['smb_during'].fillna(0).to_numpy()
        isf = sub['isf_used'].to_numpy()
        half = sub['duration_min'].to_numpy() / 2.0
        eff_off = np.minimum(off, sub['duration_min'].to_numpy())
        t_peak = half + eff_off
        for W in WINDOWS_MIN:
            extra_post = (kernel_at(t_peak + W) - kernel_at(t_peak)) * smb * isf
            cf_trough = sub['cand_peak'].to_numpy() - extra_post
            sub2 = sub.assign(
                window_min=W,
                cf_trough=cf_trough,
                cand_hypo=cf_trough < HYPO_FLOOR,
                extra_post_drop=extra_post,
            )
            agg = sub2.groupby('controller', dropna=False).agg(
                n=('bg_peak', 'size'),
                obs_overshoot=('hyper_overshoot', 'mean'),
                cand_overshoot=('cand_overshoot', 'mean'),
                cand_hypo_rate=('cand_hypo', 'mean'),
                mean_extra_post=('extra_post_drop', 'mean'),
                p1_trough=('cf_trough', lambda s: float(np.percentile(s.dropna(), 1))),
            ).reset_index()
            agg['offset_min'] = off
            agg['window_min'] = W
            rows.append(agg)
    df = pd.concat(rows, ignore_index=True)
    df.to_parquet(OUT / f'{EXP_ID.lower()}_timing_hypo.parquet')

    # Print and figure focus on W=120 (worst-case window)
    summary_rows = df[df['window_min'] == 120].copy()
    summary = {
        'offsets_min': list(OFFSETS_MIN),
        'windows_min': list(WINDOWS_MIN),
        'hypo_floor_mgdl': HYPO_FLOOR,
        'curve': df.to_dict(orient='records'),
        'verdict_per_controller': {},
    }

    print(f"[{EXP_ID}] timing-axis with hypo redistribution (W=120 min)")
    print(f"  {'controller':<10}  {'offset':>6}  {'cand_over':>9}  "
          f"{'cand_hypo':>9}  {'1%-trough':>10}")
    for _, r in summary_rows.sort_values(['controller', 'offset_min']).iterrows():
        print(f"  {str(r['controller']):<10}  {r['offset_min']:>6}  "
              f"{r['cand_overshoot']:>9.3%}  {r['cand_hypo_rate']:>9.3%}  "
              f"{r['p1_trough']:>10.1f}")

    # Per-controller verdict: does hypo rate increase as offset increases?
    print(f"\n[{EXP_ID}] hypo-redistribution verdict per controller:")
    for ctrl in summary_rows['controller'].dropna().unique():
        sub = summary_rows[summary_rows['controller'] == ctrl].sort_values('offset_min')
        h0 = float(sub.iloc[0]['cand_hypo_rate'])
        h_end = float(sub.iloc[-1]['cand_hypo_rate'])
        d_over = float(sub.iloc[-1]['cand_overshoot'] - sub.iloc[0]['cand_overshoot']) * 100
        d_hypo_pp = (h_end - h0) * 100
        verdict = ('safe' if h_end <= 0.01 else
                   'borderline' if h_end <= 0.03 else 'unsafe')
        summary['verdict_per_controller'][str(ctrl)] = {
            'hypo_at_0min': h0, 'hypo_at_30min': h_end,
            'd_overshoot_pp': d_over, 'd_hypo_pp': d_hypo_pp,
            'verdict': verdict,
        }
        print(f"  {str(ctrl):<10}  hypo 0min={h0:.3%}  hypo 30min={h_end:.3%}  "
              f"Δover={d_over:+.2f}pp  Δhypo={d_hypo_pp:+.3f}pp  → {verdict}")

    (OUT / f'{EXP_ID.lower()}_summary.json').write_text(
        json.dumps(summary, indent=2, default=float))

    # Figure: dual-axis per controller (overshoot down vs hypo up)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ctrl in summary_rows['controller'].dropna().unique():
        sub = summary_rows[summary_rows['controller'] == ctrl].sort_values('offset_min')
        axes[0].plot(sub['offset_min'], sub['cand_overshoot'] * 100, marker='o', label=str(ctrl))
        axes[1].plot(sub['offset_min'], sub['cand_hypo_rate'] * 100, marker='o', label=str(ctrl))
    axes[0].set_xlabel('Earlier-firing offset (min)'); axes[0].set_ylabel('Overshoot rate (%)')
    axes[0].set_title('Overshoot ↓ as SMB fires earlier'); axes[0].legend(fontsize=8); axes[0].grid(alpha=0.3)
    axes[1].set_xlabel('Earlier-firing offset (min)'); axes[1].set_ylabel('Hypo-rate (%) — peak+120 min')
    axes[1].set_title('Hypo-redistribution: trough by 120-min look-ahead')
    axes[1].axhline(1.0, color='red', linestyle='--', linewidth=0.8, label='1% safety gate')
    axes[1].legend(fontsize=8); axes[1].grid(alpha=0.3)
    fig.suptitle(f'{EXP_ID}  Timing-axis safety/efficacy (W=120 min)', y=1.02)
    fig.tight_layout(); fig.savefig(FIG, dpi=120, bbox_inches='tight'); plt.close(fig)
    print(f"  → {FIG}")


if __name__ == '__main__':
    main()
