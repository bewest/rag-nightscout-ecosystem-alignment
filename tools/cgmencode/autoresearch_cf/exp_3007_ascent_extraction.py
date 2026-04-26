"""EXP-3007 — Ascent event extraction from grid.parquet.

Detects sustained positive-ROC episodes (post-prandial / over-correction
overshoots) symmetric to EXP-2881's descent events. Each ascent is a run of
>=4 consecutive 5-min cells with glucose_roc >= ROC_THRESH AND bg crossing
into hyperglycaemic territory.

Output: ``externals/experiments/exp-3007_ascent_events.parquet`` with one row
per ascent event:

  patient_id, controller, time_start, time_peak, duration_min,
  bg_start, bg_peak, peak_delta, ascent_slope (mg/dL/min),
  iob_start, cob_start, basal_during (U), smb_during (U), carbs_during (g),
  smb_count, hyper_overshoot (bool: bg_peak >= 180)

Companion to exp-2881_evening_drivers.parquet; unblocks EXP-3004 (ascent
cf-replay) and EXP-3008 (controller-discriminating cf-replay v2).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

GRID = Path('externals/ns-parquet/training/grid.parquet')
EVENTS_REF = Path('externals/experiments/exp-2881_evening_drivers.parquet')
OUT = Path('externals/experiments') / 'exp-3007_ascent_events.parquet'
SUMMARY = Path('externals/experiments') / 'exp-3007_summary.json'

# Ascent thresholds
ROC_THRESH = 1.5       # mg/dL per 5-min cell
MIN_CELLS = 4          # 20-minute minimum run
MIN_DELTA = 25         # mg/dL minimum peak-minus-start
HYPER_LINE = 180       # overshoot threshold


def detect_ascents_for_patient(g: pd.DataFrame, controller: str | None) -> pd.DataFrame:
    g = g.sort_values('time').reset_index(drop=True)
    roc = g['glucose_roc'].fillna(0).values
    rising = roc >= ROC_THRESH

    # Find contiguous True runs
    events = []
    i = 0
    n = len(rising)
    while i < n:
        if not rising[i]:
            i += 1
            continue
        j = i
        while j < n and rising[j]:
            j += 1
        run_len = j - i
        if run_len >= MIN_CELLS:
            seg = g.iloc[i:j + 1]  # include the cell *after* the run for true peak
            if len(seg) < 2:
                i = j
                continue
            bg_start = float(seg['glucose'].iloc[0])
            bg_peak = float(seg['glucose'].max())
            peak_idx = int(seg['glucose'].idxmax())
            peak_row = g.loc[peak_idx]
            duration_min = (peak_row['time'] - seg['time'].iloc[0]).total_seconds() / 60.0
            peak_delta = bg_peak - bg_start
            if peak_delta < MIN_DELTA or duration_min < 20:
                i = j
                continue
            slope = peak_delta / max(duration_min, 1.0)
            ascent_seg = g.loc[seg.index[0]:peak_idx]
            events.append({
                'patient_id': str(g['patient_id'].iloc[0]),
                'controller': controller,
                'time_start': seg['time'].iloc[0],
                'time_peak': peak_row['time'],
                'duration_min': duration_min,
                'bg_start': bg_start,
                'bg_peak': bg_peak,
                'peak_delta': peak_delta,
                'ascent_slope': slope,
                'iob_start': float(seg['iob'].iloc[0]) if 'iob' in seg else np.nan,
                'cob_start': float(seg['cob'].iloc[0]) if 'cob' in seg else np.nan,
                'basal_during': float(ascent_seg['net_basal'].sum() / 12.0)
                                if 'net_basal' in ascent_seg else np.nan,
                'smb_during': float(ascent_seg['bolus_smb'].sum())
                              if 'bolus_smb' in ascent_seg else np.nan,
                'smb_count': int((ascent_seg.get('bolus_smb',
                                                 pd.Series(dtype=float)) > 0).sum()),
                'carbs_during': float(ascent_seg['carbs'].sum())
                                if 'carbs' in ascent_seg else np.nan,
                'hyper_overshoot': bool(bg_peak >= HYPER_LINE),
            })
        i = j
    return pd.DataFrame(events)


def main() -> None:
    grid = pd.read_parquet(GRID, columns=[
        'patient_id', 'time', 'glucose', 'iob', 'cob',
        'bolus_smb', 'carbs', 'net_basal', 'glucose_roc'])
    ref = pd.read_parquet(EVENTS_REF, columns=['patient_id', 'controller'])
    pid_to_ctrl = (ref.dropna(subset=['controller'])
                      .drop_duplicates('patient_id')
                      .set_index('patient_id')['controller'].to_dict())

    all_events = []
    per_patient_summary = []
    for pid, gp in grid.groupby('patient_id'):
        ctrl = pid_to_ctrl.get(pid)
        ev = detect_ascents_for_patient(gp, ctrl)
        all_events.append(ev)
        per_patient_summary.append({
            'patient_id': pid, 'controller': ctrl,
            'n_cells': len(gp),
            'n_ascents': len(ev),
            'n_hyper_overshoots': int(ev['hyper_overshoot'].sum()) if len(ev) else 0,
            'mean_peak_delta': float(ev['peak_delta'].mean()) if len(ev) else None,
            'mean_smb_during': float(ev['smb_during'].mean()) if len(ev) else None,
        })

    events = pd.concat(all_events, ignore_index=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    events.to_parquet(OUT)

    summary = {
        'roc_thresh_mgdl_per_5min': ROC_THRESH,
        'min_cells': MIN_CELLS,
        'min_delta_mgdl': MIN_DELTA,
        'n_patients': int(events['patient_id'].nunique()),
        'n_events': int(len(events)),
        'n_hyper_overshoots': int(events['hyper_overshoot'].sum()),
        'overshoot_rate': float(events['hyper_overshoot'].mean()),
        'mean_peak_delta': float(events['peak_delta'].mean()),
        'mean_duration_min': float(events['duration_min'].mean()),
        'mean_smb_during': float(events['smb_during'].mean()),
        'pct_with_smb': float((events['smb_count'] > 0).mean()),
        'by_controller': events.groupby('controller', dropna=False).agg(
            n=('bg_peak', 'size'),
            overshoot_rate=('hyper_overshoot', 'mean'),
            mean_peak_delta=('peak_delta', 'mean'),
            mean_smb=('smb_during', 'mean'),
            pct_with_smb=('smb_count', lambda s: float((s > 0).mean())),
        ).reset_index().to_dict(orient='records'),
        'per_patient': per_patient_summary,
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, default=float))

    print(f"[EXP-3007] {summary['n_events']} ascent events / "
          f"{summary['n_patients']} patients")
    print(f"  overshoot_rate={summary['overshoot_rate']:.3%}  "
          f"mean_peak_delta={summary['mean_peak_delta']:.1f} mg/dL  "
          f"mean_dur={summary['mean_duration_min']:.0f} min  "
          f"pct_with_smb={summary['pct_with_smb']:.3%}")
    print(f"  by controller:")
    for r in summary['by_controller']:
        print(f"    {str(r['controller']):>12s}: n={r['n']:>5d}  "
              f"overshoot={r['overshoot_rate']:.3%}  "
              f"peak_delta={r['mean_peak_delta']:.1f}  "
              f"smb={r['mean_smb']:.3f}U  "
              f"with_smb={r['pct_with_smb']:.3%}")
    print(f"  → {OUT}")


if __name__ == '__main__':
    main()
