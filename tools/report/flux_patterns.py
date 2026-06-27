from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import ceil
from typing import Any

import numpy as np


def _nan_summary(values: list[float]) -> dict[str, list[float]]:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return {'median': [], 'p25': [], 'p75': []}
    return {
        'median': [round(float(v), 3) if np.isfinite(v) else None for v in np.nanmedian(arr, axis=0)],
        'p25': [round(float(v), 3) if np.isfinite(v) else None for v in np.nanpercentile(arr, 25, axis=0)],
        'p75': [round(float(v), 3) if np.isfinite(v) else None for v in np.nanpercentile(arr, 75, axis=0)],
    }


def build_flux_pattern_summary(
    net_flux: np.ndarray | list[float] | None,
    timestamps_ms: np.ndarray | list[float],
) -> dict[str, Any]:
    if net_flux is None:
        return {
            'available': False,
            'reason': 'no-net-flux',
        }

    flux = np.asarray(net_flux, dtype=float)
    ts = np.asarray(timestamps_ms, dtype=float)
    if flux.size == 0 or ts.size == 0 or flux.size != ts.size:
        return {
            'available': False,
            'reason': 'invalid-shape',
        }

    day_hour_values: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for value, ts_ms in zip(flux, ts):
        if not np.isfinite(value):
            continue
        dt = datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc)
        day_key = dt.strftime('%Y-%m-%d')
        day_hour_values[day_key][dt.hour].append(float(value))

    day_profiles: list[dict[str, Any]] = []
    for day, hour_map in sorted(day_hour_values.items()):
        hourly_profile = [np.nan] * 24
        raw_values: list[float] = []
        for hour in range(24):
            vals = hour_map.get(hour, [])
            if vals:
                hourly_profile[hour] = float(np.mean(vals))
                raw_values.extend(vals)
        finite_hours = sum(np.isfinite(hourly_profile))
        if finite_hours < 18 or not raw_values:
            continue
        hourly_arr = np.asarray(hourly_profile, dtype=float)
        raw_arr = np.asarray(raw_values, dtype=float)
        overnight = hourly_arr[0:6]
        daytime = hourly_arr[6:24]
        day_profiles.append({
            'date': day,
            'hourly_profile': hourly_arr,
            'finite_hours': finite_hours,
            'mean_abs_flux': round(float(np.mean(np.abs(raw_arr))), 3),
            'max_abs_flux': round(float(np.max(np.abs(raw_arr))), 3),
            'mean_net_flux': round(float(np.mean(raw_arr)), 3),
            'overnight_mean': round(float(np.nanmean(overnight)), 3),
            'daytime_mean': round(float(np.nanmean(daytime)), 3),
        })

    if len(day_profiles) < 3:
        return {
            'available': False,
            'reason': 'insufficient-days',
            'n_days': len(day_profiles),
        }

    profile_matrix = np.vstack([row['hourly_profile'] for row in day_profiles])
    median_profile = np.nanmedian(profile_matrix, axis=0)
    for row in day_profiles:
        row['deviation_score'] = round(
            float(np.nanmean(np.abs(row['hourly_profile'] - median_profile))),
            3,
        )

    ordered = sorted(day_profiles, key=lambda row: row['deviation_score'])
    unusual_count = max(1, ceil(len(ordered) * 0.2))
    typical_count = max(1, ceil(len(ordered) * 0.5))
    typical = ordered[:typical_count]
    unusual = ordered[-unusual_count:]
    typical_dates = {row['date'] for row in typical}
    unusual_dates = {row['date'] for row in unusual}

    daily_rows = []
    for row in day_profiles:
        if row['date'] in unusual_dates:
            label = 'unusual'
        elif row['date'] in typical_dates:
            label = 'typical'
        else:
            label = 'middle'
        daily_rows.append({
            'date': row['date'],
            'mean_abs_flux': row['mean_abs_flux'],
            'max_abs_flux': row['max_abs_flux'],
            'mean_net_flux': row['mean_net_flux'],
            'overnight_mean': row['overnight_mean'],
            'daytime_mean': row['daytime_mean'],
            'deviation_score': row['deviation_score'],
            'label': label,
        })

    return {
        'available': True,
        'n_days': len(day_profiles),
        'classification_rule': 'typical = closest 50% of days to median hourly profile; unusual = farthest 20%',
        'typical_day_summary': {
            'n_days': len(typical),
            **_nan_summary([row['hourly_profile'] for row in typical]),
        },
        'unusual_day_summary': {
            'n_days': len(unusual),
            **_nan_summary([row['hourly_profile'] for row in unusual]),
        },
        'top_unusual_dates': [row['date'] for row in sorted(unusual, key=lambda row: row['deviation_score'], reverse=True)[:5]],
        'daily_rows': daily_rows,
    }
