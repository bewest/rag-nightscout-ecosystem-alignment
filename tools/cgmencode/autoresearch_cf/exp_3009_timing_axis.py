"""EXP-3009 — SMB-timing-axis cf-replay (fire earlier in ascent).

EXP-3008 found Loop's overshoot rate is essentially PK-bounded for the
*magnitude* axis: even tripling SMB only removes ~3 pp of overshoot. The
remaining lever is **timing**: fire the same SMB units earlier in the
ascent so the oref0 PK kernel has more time to act on the peak.

Method
------
For each ascent event, model "what if the observed `smb_during` units were
delivered T minutes earlier than their actual midpoint?" Earlier delivery
shifts the kernel evaluation point from duration/2 to (duration/2 + T),
which (because t_eval is the time-from-delivery to peak) increases the
realised kernel fraction. Sweep T in {0, 5, 10, 15, 20, 30} minutes.

Per-controller dose-response on TIMING:
  d_overshoot / d_T = how many pp of overshoot disappear per minute earlier?

Outputs
-------
externals/experiments/exp-3009_timing_response.parquet
externals/experiments/exp-3009_summary.json
docs/60-research/figures/exp-3009_timing_response.png
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
from tools.cgmencode.autoresearch_cf.exp_3004_ascent_replay import PEAK_MIN

EXP_ID = 'EXP-3009'
ASCENT = Path('externals/experiments/exp-3007_ascent_events.parquet')
OUT = Path('externals/experiments')
FIG = Path('docs/60-research/figures') / f'{EXP_ID.lower()}_timing_response.png'

OFFSETS_MIN = (0, 5, 10, 15, 20, 30)


def kernel_at(t_min: np.ndarray | float) -> np.ndarray | float:
    """oref0 exponential kernel realised fraction at t minutes from delivery."""
    t = np.asarray(t_min, dtype=float)
    return 1.0 - (1.0 + t / PEAK_MIN) * np.exp(-t / PEAK_MIN)


def candidate_timing(events: pd.DataFrame, offset_min: float) -> pd.DataFrame:
    """For each event, evaluate kernel as if SMB were fired offset_min earlier.

    The baseline kernel point is (duration_min / 2) (midpoint of ascent).
    Shifting earlier increases the time-to-peak budget by offset_min, but
    we cap the shift at duration_min (cannot fire before ascent_start).
    """
    ev = events.copy()
    half = ev['duration_min'].to_numpy() / 2.0
    eff_offset = np.minimum(offset_min, ev['duration_min'].to_numpy())
    t_eval = half + eff_offset    # minutes from (shifted) delivery to peak
    kf = kernel_at(t_eval)
    base_kf = kernel_at(half)
    extra = (kf - base_kf) * ev['smb_during'].fillna(0).to_numpy() * ev['isf_used'].to_numpy()
    ev['cand_peak'] = ev['bg_peak'].to_numpy() - extra
    ev['cand_overshoot'] = ev['cand_peak'] >= 180
    ev['kernel_factor_shifted'] = kf
    ev['extra_drop_at_peak'] = extra
    ev['offset_min'] = offset_min
    return ev


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
        agg = sub.groupby('controller', dropna=False).agg(
            n=('bg_peak', 'size'),
            obs_overshoot=('hyper_overshoot', 'mean'),
            cand_overshoot=('cand_overshoot', 'mean'),
            mean_extra_drop=('extra_drop_at_peak', 'mean'),
        ).reset_index()
        agg['offset_min'] = off
        agg['delta_overshoot_pp'] = (agg['cand_overshoot'] - agg['obs_overshoot']) * 100
        rows.append(agg)
    df = pd.concat(rows, ignore_index=True)
    df.to_parquet(OUT / f'{EXP_ID.lower()}_timing_response.parquet')

    # Per-controller slope d(overshoot_pp)/d(offset_min) via OLS
    slopes = {}
    for ctrl, sub in df[df['controller'].notna()].groupby('controller'):
        x = sub['offset_min'].to_numpy(dtype=float)
        y = sub['delta_overshoot_pp'].to_numpy(dtype=float)
        slope = float(np.polyfit(x, y, 1)[0]) if len(x) >= 2 else float('nan')
        slopes[str(ctrl)] = slope

    summary = {
        'offsets_min': list(OFFSETS_MIN),
        'peak_min': PEAK_MIN,
        'slope_pp_per_min': slopes,
        'curve': df.to_dict(orient='records'),
    }
    (OUT / f'{EXP_ID.lower()}_summary.json').write_text(
        json.dumps(summary, indent=2, default=float))

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for ctrl in df['controller'].dropna().unique():
        sub = df[df['controller'] == ctrl].sort_values('offset_min')
        ax.plot(sub['offset_min'], sub['cand_overshoot'] * 100,
                marker='o', label=f"{ctrl} (slope={slopes[str(ctrl)]:+.2f} pp/min)")
    ax.set_xlabel('Earlier-firing offset (minutes before observed midpoint)')
    ax.set_ylabel('Counterfactual overshoot rate (%)')
    ax.set_title(f'{EXP_ID}  Per-controller timing-axis dose-response')
    ax.legend(fontsize=9); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(FIG, dpi=120, bbox_inches='tight'); plt.close(fig)

    print(f"[{EXP_ID}] timing-axis sweep over offsets {OFFSETS_MIN} min")
    print(f"  {'controller':<10}  {'offset':>6}  {'obs_over':>8}  "
          f"{'cand_over':>9}  {'delta_pp':>8}  {'extra_drop':>10}")
    for _, r in df.sort_values(['controller', 'offset_min']).iterrows():
        print(f"  {str(r['controller']):<10}  {r['offset_min']:>6}  "
              f"{r['obs_overshoot']:>8.3%}  {r['cand_overshoot']:>9.3%}  "
              f"{r['delta_overshoot_pp']:>+7.2f}  {r['mean_extra_drop']:>10.3f}")
    print(f"\n[{EXP_ID}] Per-controller slopes (pp overshoot per minute earlier):")
    for ctrl, s in sorted(slopes.items(), key=lambda kv: kv[1]):
        print(f"  {ctrl:<10}  {s:+.3f} pp/min")
    print(f"  → {FIG}")


if __name__ == '__main__':
    main()
