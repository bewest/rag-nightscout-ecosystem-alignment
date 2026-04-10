#!/usr/bin/env python3
"""
EXP-2191–2198: AID Loop Decision Analysis

Analyzes what the AID loop decides, why, and whether those decisions
lead to good or bad glucose outcomes. Maps the decision-to-outcome
pathway to understand why AID patients universally experience hypoglycemia.

Experiments:
  2191 - Loop Decision Taxonomy (suspend/reduce/maintain/increase/bolus)
  2192 - Loop Prediction Accuracy (predicted vs actual glucose)
  2193 - Decision-to-Outcome Mapping (what happens after each decision?)
  2194 - Hypo Risk Calibration (is the loop's risk model accurate?)
  2195 - Pre-Hypo Decision Sequence (what does the loop do before hypos?)
  2196 - Loop Aggressiveness Profile (recommended vs enacted)
  2197 - Circadian Decision Patterns (time-of-day decision variation)
  2198 - Decision Efficiency (glucose change per unit insulin by context)

Usage:
    PYTHONPATH=tools python3 tools/cgmencode/exp_loop_decisions_2191.py --figures
"""

import argparse
import json
import os
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

from cgmencode.exp_metabolic_441 import load_patients

STEPS_PER_HOUR = 12  # 5-min steps
HYPO_THRESHOLD = 70  # mg/dL


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def get_profile_value(schedule, hour):
    """Get profile value for a given hour from schedule."""
    if not schedule:
        return None
    sorted_entries = sorted(schedule, key=lambda x: x.get('timeAsSeconds', 0))
    value = sorted_entries[0].get('value', None)
    for entry in sorted_entries:
        t_sec = entry.get('timeAsSeconds', 0)
        if t_sec / 3600 <= hour:
            value = entry.get('value', value)
    return value


def classify_loop_decision(row, basal_schedule):
    """Classify a single loop decision (legacy, use classify_all_decisions for vectorized)."""
    enacted = row.get('enacted_rate')
    hour = row.name.hour + row.name.minute / 60 if hasattr(row.name, 'hour') else 0
    scheduled = get_profile_value(basal_schedule, hour)

    if pd.isna(enacted) or scheduled is None or scheduled == 0:
        return 'unknown'

    ratio = enacted / scheduled
    if ratio < 0.05:
        return 'suspend'
    elif ratio < 0.5:
        return 'reduce'
    elif ratio <= 1.5:
        return 'maintain'
    elif ratio <= 3.0:
        return 'increase'
    else:
        return 'surge'


def classify_all_decisions(df, basal_schedule):
    """Vectorized classification of all loop decisions."""
    enacted = df['enacted_rate'].values
    hours = df.index.hour + df.index.minute / 60.0

    # Build scheduled basal for each step
    sorted_entries = sorted(basal_schedule, key=lambda x: x.get('timeAsSeconds', 0))
    sched_hours = np.array([e.get('timeAsSeconds', 0) / 3600 for e in sorted_entries])
    sched_vals = np.array([e.get('value', 0) for e in sorted_entries])

    scheduled = np.zeros(len(df))
    for i in range(len(sched_hours)):
        if i < len(sched_hours) - 1:
            mask = (hours >= sched_hours[i]) & (hours < sched_hours[i + 1])
        else:
            mask = hours >= sched_hours[i]
        scheduled[mask] = sched_vals[i]

    # Compute ratio
    with np.errstate(divide='ignore', invalid='ignore'):
        ratio = enacted / scheduled

    # Classify
    decisions = np.full(len(df), 'unknown', dtype=object)
    valid = ~np.isnan(enacted) & (scheduled > 0)
    decisions[valid & (ratio < 0.05)] = 'suspend'
    decisions[valid & (ratio >= 0.05) & (ratio < 0.5)] = 'reduce'
    decisions[valid & (ratio >= 0.5) & (ratio <= 1.5)] = 'maintain'
    decisions[valid & (ratio > 1.5) & (ratio <= 3.0)] = 'increase'
    decisions[valid & (ratio > 3.0)] = 'surge'

    return pd.Series(decisions, index=df.index)


def find_hypo_events(glucose, min_gap=6):
    """Find hypo events (<70 mg/dL) with minimum gap between events."""
    below = glucose < HYPO_THRESHOLD
    events = []
    i = 0
    while i < len(glucose):
        if below.iloc[i]:
            start = i
            while i < len(glucose) and below.iloc[i]:
                i += 1
            events.append(start)
            i += min_gap * STEPS_PER_HOUR
        else:
            i += 1
    return events


def exp_2191_decision_taxonomy(patients, save_dir=None):
    """EXP-2191: Classify all loop decisions into suspend/reduce/maintain/increase/surge."""
    print("\n=== EXP-2191: Loop Decision Taxonomy ===")
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        basal_schedule = df.attrs.get('basal_schedule', [])

        if not basal_schedule:
            print(f"  {name}: no basal schedule, skipping")
            continue

        df_dec = classify_all_decisions(df, basal_schedule)
        counts = df_dec.value_counts()
        total = len(df_dec) - counts.get('unknown', 0)

        # Compute glucose outcome for each decision type
        decision_glucose = {}
        for dec_type in ['suspend', 'reduce', 'maintain', 'increase', 'surge']:
            mask = df_dec == dec_type
            if mask.sum() > 0:
                g = df.loc[mask, 'glucose']
                decision_glucose[dec_type] = {
                    'count': int(mask.sum()),
                    'pct': round(100 * mask.sum() / max(total, 1), 1),
                    'mean_glucose': round(float(g.mean()), 1) if g.notna().sum() > 0 else None,
                    'hypo_pct': round(100 * (g < HYPO_THRESHOLD).sum() / max(g.notna().sum(), 1), 1)
                }

        # Zero delivery percentage
        zero_mask = (df['enacted_rate'].notna()) & (df['enacted_rate'] < 0.05)
        zero_pct = round(100 * zero_mask.sum() / max(df['enacted_rate'].notna().sum(), 1), 1)

        results[name] = {
            'total_decisions': int(total),
            'zero_delivery_pct': zero_pct,
            'decisions': decision_glucose
        }

        top = max(decision_glucose.items(), key=lambda x: x[1]['count'])[0] if decision_glucose else 'unknown'
        print(f"  {name}: {total} decisions, {zero_pct}% zero delivery, top={top} ({decision_glucose.get(top, {}).get('pct', 0)}%)")

    if save_dir:
        _save_json(results, save_dir, 'exp-2191_decision_taxonomy.json')

    return results


def exp_2192_prediction_accuracy(patients, save_dir=None):
    """EXP-2192: Compare loop's glucose predictions to actual outcomes."""
    print("\n=== EXP-2192: Loop Prediction Accuracy ===")
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']

        # predicted_30: loop's 30-min prediction
        # predicted_60: loop's 60-min prediction
        # predicted_min: loop's predicted minimum glucose
        pred_cols = ['predicted_30', 'predicted_60', 'predicted_min']
        actual_30 = df['glucose'].shift(-6)  # 30 min ahead
        actual_60 = df['glucose'].shift(-12)  # 60 min ahead

        # 30-min prediction accuracy
        valid_30 = df['predicted_30'].notna() & actual_30.notna()
        if valid_30.sum() > 100:
            err_30 = (df.loc[valid_30, 'predicted_30'] - actual_30[valid_30])
            mae_30 = float(err_30.abs().mean())
            bias_30 = float(err_30.mean())
            rmse_30 = float(np.sqrt((err_30 ** 2).mean()))
            r_30 = float(np.corrcoef(df.loc[valid_30, 'predicted_30'], actual_30[valid_30])[0, 1]) if valid_30.sum() > 2 else 0
        else:
            mae_30 = bias_30 = rmse_30 = r_30 = None

        # 60-min prediction accuracy
        valid_60 = df['predicted_60'].notna() & actual_60.notna()
        if valid_60.sum() > 100:
            err_60 = (df.loc[valid_60, 'predicted_60'] - actual_60[valid_60])
            mae_60 = float(err_60.abs().mean())
            bias_60 = float(err_60.mean())
            rmse_60 = float(np.sqrt((err_60 ** 2).mean()))
            r_60 = float(np.corrcoef(df.loc[valid_60, 'predicted_60'], actual_60[valid_60])[0, 1]) if valid_60.sum() > 2 else 0
        else:
            mae_60 = bias_60 = rmse_60 = r_60 = None

        # predicted_min accuracy: find actual minimum in next 3h window
        step = STEPS_PER_HOUR * 3  # 3-hour window
        # predicted_min: vectorized rolling min over 3h window (sampled hourly)
        glucose_vals = df['glucose'].values
        pred_min_vals = df['predicted_min'].values
        # Compute rolling minimum over 3h forward window
        n = len(glucose_vals)
        rolling_min = np.full(n, np.nan)
        # Use reversed cumulative min approach
        for offset in range(step):
            shifted = np.roll(glucose_vals, -offset)
            shifted[n - offset:] = np.nan
            rolling_min = np.fmin(rolling_min, shifted)

        # Sample at hourly intervals where predicted_min is available
        sample_idx = np.arange(0, n - step, STEPS_PER_HOUR)
        valid_min = ~np.isnan(pred_min_vals[sample_idx]) & ~np.isnan(rolling_min[sample_idx])
        pred_mins = pred_min_vals[sample_idx[valid_min]]
        actual_mins = rolling_min[sample_idx[valid_min]]

        if len(pred_mins) > 10:
            min_err = pred_mins - actual_mins
            mae_min = float(np.abs(min_err).mean())
            bias_min = float(min_err.mean())
            pred_hypo = pred_mins < HYPO_THRESHOLD
            actual_hypo = actual_mins < HYPO_THRESHOLD
            if actual_hypo.sum() > 0:
                sensitivity = float(pred_hypo[actual_hypo].mean())
            else:
                sensitivity = None
            if pred_hypo.sum() > 0:
                ppv = float(actual_hypo[pred_hypo].mean())
            else:
                ppv = None
        else:
            mae_min = bias_min = sensitivity = ppv = None

        results[name] = {
            'n_valid_30': int(valid_30.sum()) if valid_30 is not None else 0,
            'mae_30': round(mae_30, 1) if mae_30 else None,
            'bias_30': round(bias_30, 1) if bias_30 else None,
            'rmse_30': round(rmse_30, 1) if rmse_30 else None,
            'r_30': round(r_30, 3) if r_30 else None,
            'mae_60': round(mae_60, 1) if mae_60 else None,
            'bias_60': round(bias_60, 1) if bias_60 else None,
            'rmse_60': round(rmse_60, 1) if rmse_60 else None,
            'r_60': round(r_60, 3) if r_60 else None,
            'mae_min': round(mae_min, 1) if mae_min else None,
            'bias_min': round(bias_min, 1) if bias_min else None,
            'hypo_sensitivity': round(sensitivity, 3) if sensitivity is not None else None,
            'hypo_ppv': round(ppv, 3) if ppv is not None else None,
        }
        print(f"  {name}: MAE30={mae_30:.1f}, MAE60={mae_60:.1f}, bias30={bias_30:+.1f}, r30={r_30:.3f}" if mae_30 else f"  {name}: insufficient data")

    if save_dir:
        _save_json(results, save_dir, 'exp-2192_prediction_accuracy.json')

    return results


def exp_2193_decision_outcome(patients, save_dir=None):
    """EXP-2193: Map loop decisions to glucose outcomes 30/60/120 min later."""
    print("\n=== EXP-2193: Decision-to-Outcome Mapping ===")
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        basal_schedule = df.attrs.get('basal_schedule', [])

        if not basal_schedule:
            continue

        df_dec = classify_all_decisions(df, basal_schedule)

        outcome = {}
        # Pre-compute shifted glucose arrays
        glucose = df['glucose'].values
        g_30 = np.roll(glucose, -6)
        g_60 = np.roll(glucose, -12)
        g_120 = np.roll(glucose, -24)
        # Mark invalid (rolled values)
        g_30[-6:] = np.nan
        g_60[-12:] = np.nan
        g_120[-24:] = np.nan

        for dec_type in ['suspend', 'reduce', 'maintain', 'increase', 'surge']:
            mask = (df_dec == dec_type).values
            g_now = glucose.copy()
            valid = mask & ~np.isnan(g_now)

            if valid.sum() < 20:
                continue

            n = int(mask.sum())
            # Deltas
            d30 = g_30[valid] - g_now[valid]
            d30 = d30[~np.isnan(d30)]
            d60 = g_60[valid] - g_now[valid]
            d60 = d60[~np.isnan(d60)]
            d120 = g_120[valid] - g_now[valid]
            d120 = d120[~np.isnan(d120)]

            # Hypo transitions
            hypo_30_mask = mask.copy()
            hypo_30_mask[-6:] = False
            hypo_30 = int((hypo_30_mask & (g_30 < HYPO_THRESHOLD)).sum())
            hypo_60_mask = mask.copy()
            hypo_60_mask[-12:] = False
            hypo_60 = int((hypo_60_mask & (g_60 < HYPO_THRESHOLD)).sum())

            outcome[dec_type] = {
                'count': n,
                'delta_30_mean': round(float(np.mean(d30)), 1) if len(d30) > 0 else None,
                'delta_60_mean': round(float(np.mean(d60)), 1) if len(d60) > 0 else None,
                'delta_120_mean': round(float(np.mean(d120)), 1) if len(d120) > 0 else None,
                'hypo_30_pct': round(100 * hypo_30 / n, 1),
                'hypo_60_pct': round(100 * hypo_60 / n, 1),
            }

        results[name] = outcome
        sus = outcome.get('suspend', {})
        inc = outcome.get('increase', {})
        print(f"  {name}: suspend→Δ60={sus.get('delta_60_mean', '?')}, increase→Δ60={inc.get('delta_60_mean', '?')}")

    if save_dir:
        _save_json(results, save_dir, 'exp-2193_decision_outcome.json')

    return results


def exp_2194_hypo_risk_calibration(patients, save_dir=None):
    """EXP-2194: Evaluate calibration of the loop's hypo_risk prediction."""
    print("\n=== EXP-2194: Hypo Risk Calibration ===")
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']

        risk = df['hypo_risk']
        valid = risk.notna()
        if valid.sum() < 100:
            continue

        # Actual hypo within next 1h and 2h (vectorized using rolling min)
        glucose = df['glucose'].values
        n = len(glucose)
        # Rolling min forward-looking
        hypo_1h = np.full(n, False)
        hypo_2h = np.full(n, False)
        # Compute from back
        running_min_1h = np.full(n + STEPS_PER_HOUR, np.inf)
        running_min_2h = np.full(n + 2 * STEPS_PER_HOUR, np.inf)
        gpad = np.concatenate([glucose, np.full(2 * STEPS_PER_HOUR, np.nan)])
        for offset in range(STEPS_PER_HOUR):
            shifted = np.roll(gpad, -offset)[:n]
            running_min_1h[:n] = np.fmin(running_min_1h[:n], shifted)
        hypo_1h = running_min_1h[:n] < HYPO_THRESHOLD

        for offset in range(2 * STEPS_PER_HOUR):
            shifted = np.roll(gpad, -offset)[:n]
            running_min_2h[:n] = np.fmin(running_min_2h[:n], shifted)
        hypo_2h = running_min_2h[:n] < HYPO_THRESHOLD

        actual_hypo_1h = pd.Series(hypo_1h, index=df.index)
        actual_hypo_2h = pd.Series(hypo_2h, index=df.index)

        # Bin risk values and compute calibration (vectorized)
        risk_vals = risk[valid].values
        valid_idx = valid.values
        bins = np.linspace(0, 1, 11)
        calibration = []
        # Build full-length risk array aligned with df
        risk_full = risk.values

        for j in range(len(bins) - 1):
            bin_mask = valid_idx & (risk_full >= bins[j]) & (risk_full < bins[j + 1])
            n_bin = bin_mask.sum()
            if n_bin > 10:
                actual_rate_1h = float(actual_hypo_1h[bin_mask].mean())
                actual_rate_2h = float(actual_hypo_2h[bin_mask].mean())
                calibration.append({
                    'bin_low': round(float(bins[j]), 2),
                    'bin_high': round(float(bins[j + 1]), 2),
                    'n': int(n_bin),
                    'actual_1h': round(actual_rate_1h, 3),
                    'actual_2h': round(actual_rate_2h, 3),
                })

        # Overall metrics
        risk_valid = risk[valid]
        high_risk = risk_valid > 0.5
        actual_any = actual_hypo_2h[valid]

        if high_risk.sum() > 0 and actual_any.sum() > 0:
            sensitivity = float(high_risk[actual_any[valid].values].mean()) if actual_any[valid].sum() > 0 else None
            ppv = float(actual_any[valid][high_risk].mean()) if high_risk.sum() > 0 else None
        else:
            sensitivity = ppv = None

        overall_hypo_rate = float(actual_hypo_2h[valid].mean())

        results[name] = {
            'n_valid': int(valid.sum()),
            'risk_mean': round(float(risk_valid.mean()), 3),
            'risk_std': round(float(risk_valid.std()), 3),
            'overall_hypo_2h_rate': round(overall_hypo_rate, 3),
            'high_risk_sensitivity': round(sensitivity, 3) if sensitivity is not None else None,
            'high_risk_ppv': round(ppv, 3) if ppv is not None else None,
            'calibration': calibration,
        }
        print(f"  {name}: risk_mean={risk_valid.mean():.3f}, hypo_2h={overall_hypo_rate:.3f}, sens={sensitivity}, ppv={ppv}")

    if save_dir:
        _save_json(results, save_dir, 'exp-2194_hypo_risk_calibration.json')

    return results


def exp_2195_pre_hypo_decisions(patients, save_dir=None):
    """EXP-2195: Analyze loop decisions in the 2 hours before hypoglycemia."""
    print("\n=== EXP-2195: Pre-Hypo Decision Sequence ===")
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        basal_schedule = df.attrs.get('basal_schedule', [])

        if not basal_schedule:
            continue

        df_dec = classify_all_decisions(df, basal_schedule)

        # Find hypo events
        hypo_starts = find_hypo_events(df['glucose'].fillna(999))
        if len(hypo_starts) < 5:
            print(f"  {name}: only {len(hypo_starts)} hypos, skipping")
            continue

        pre_window = 2 * STEPS_PER_HOUR  # 2 hours before
        pre_decisions = defaultdict(lambda: defaultdict(int))
        pre_iob = []
        pre_glucose_slope = []
        pre_cob = []
        loop_suspended_before = 0

        for start in hypo_starts:
            if start < pre_window:
                continue

            # Decisions in 2h before hypo
            for offset in range(pre_window):
                idx = start - pre_window + offset
                dec = df_dec.iloc[idx]
                time_before = (pre_window - offset) * 5  # minutes before
                bucket = f"{time_before // 30 * 30}-{(time_before // 30 + 1) * 30}min"
                pre_decisions[bucket][dec] += 1

            # IOB at hypo onset
            iob = df['iob'].iloc[start]
            if pd.notna(iob):
                pre_iob.append(float(iob))

            # COB at hypo onset
            cob = df['cob'].iloc[start]
            if pd.notna(cob):
                pre_cob.append(float(cob))

            # Glucose slope in 30min before
            if start >= 6:
                g_prev = df['glucose'].iloc[start - 6]
                g_now = df['glucose'].iloc[start]
                if pd.notna(g_prev) and pd.notna(g_now):
                    pre_glucose_slope.append(float(g_now - g_prev))

            # Was loop suspended in hour before?
            if start >= STEPS_PER_HOUR:
                hour_before = df_dec.iloc[start - STEPS_PER_HOUR:start]
                if (hour_before == 'suspend').any():
                    loop_suspended_before += 1

        # Summarize pre-decision patterns
        decision_summary = {}
        for bucket, decs in sorted(pre_decisions.items()):
            total = sum(decs.values())
            decision_summary[bucket] = {k: round(100 * v / total, 1) for k, v in decs.items()}

        results[name] = {
            'n_hypos': len(hypo_starts),
            'pre_iob_mean': round(float(np.mean(pre_iob)), 2) if pre_iob else None,
            'pre_iob_median': round(float(np.median(pre_iob)), 2) if pre_iob else None,
            'pre_cob_mean': round(float(np.mean(pre_cob)), 1) if pre_cob else None,
            'pre_glucose_slope_mean': round(float(np.mean(pre_glucose_slope)), 1) if pre_glucose_slope else None,
            'loop_suspended_before_pct': round(100 * loop_suspended_before / max(len(hypo_starts), 1), 1),
            'pre_decisions': decision_summary,
        }
        print(f"  {name}: {len(hypo_starts)} hypos, IOB={np.mean(pre_iob):.2f}U, suspended_before={100 * loop_suspended_before / len(hypo_starts):.0f}%")

    if save_dir:
        _save_json(results, save_dir, 'exp-2195_pre_hypo_decisions.json')

    return results


def exp_2196_aggressiveness(patients, save_dir=None):
    """EXP-2196: Compare recommended_bolus to enacted_bolus — loop aggressiveness."""
    print("\n=== EXP-2196: Loop Aggressiveness Profile ===")
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']

        rec = df['recommended_bolus']
        enacted = df['enacted_bolus']
        valid = rec.notna() & enacted.notna()

        if valid.sum() < 100:
            continue

        rec_v = rec[valid]
        en_v = enacted[valid]

        # When recommendation > 0
        rec_positive = rec_v > 0
        if rec_positive.sum() > 10:
            # How often does loop follow recommendation?
            enacted_when_rec = en_v[rec_positive]
            follow_rate = float((enacted_when_rec > 0).mean())
            # Ratio of enacted to recommended
            ratios = enacted_when_rec[enacted_when_rec > 0] / rec_v[rec_positive][enacted_when_rec > 0]
            ratio_mean = float(ratios.mean()) if len(ratios) > 0 else None
        else:
            follow_rate = None
            ratio_mean = None

        # Unsolicited boluses: enacted > 0 but recommended == 0
        unsolicited = (en_v > 0) & (rec_v == 0)
        unsolicited_pct = round(100 * float(unsolicited.mean()), 1)

        # Override: recommended > 0 but enacted == 0
        override = (rec_v > 0) & (en_v == 0)
        override_pct = round(100 * float(override.mean()), 1) if rec_positive.sum() > 0 else 0

        # Enacted bolus size distribution
        enacted_pos = en_v[en_v > 0]
        if len(enacted_pos) > 0:
            bolus_stats = {
                'mean_U': round(float(enacted_pos.mean()), 3),
                'median_U': round(float(enacted_pos.median()), 3),
                'max_U': round(float(enacted_pos.max()), 2),
                'p90_U': round(float(enacted_pos.quantile(0.9)), 3),
            }
        else:
            bolus_stats = {}

        results[name] = {
            'n_valid': int(valid.sum()),
            'rec_positive_count': int(rec_positive.sum()),
            'follow_rate': round(follow_rate, 3) if follow_rate is not None else None,
            'enacted_to_rec_ratio': round(ratio_mean, 3) if ratio_mean is not None else None,
            'unsolicited_pct': unsolicited_pct,
            'override_pct': override_pct,
            'bolus_stats': bolus_stats,
        }
        print(f"  {name}: follow={follow_rate:.1%}, ratio={ratio_mean:.2f}, override={override_pct:.1f}%" if follow_rate else f"  {name}: insufficient recommendations")

    if save_dir:
        _save_json(results, save_dir, 'exp-2196_aggressiveness.json')

    return results


def exp_2197_circadian_decisions(patients, save_dir=None):
    """EXP-2197: How do loop decisions vary by time of day?"""
    print("\n=== EXP-2197: Circadian Decision Patterns ===")
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        basal_schedule = df.attrs.get('basal_schedule', [])

        if not basal_schedule:
            continue

        df_dec = classify_all_decisions(df, basal_schedule)

        # Group by hour
        hours = df.index.hour
        hourly = {}
        for h in range(24):
            mask = hours == h
            dec_h = df_dec[mask]
            g_h = df['glucose'][mask]
            iob_h = df['iob'][mask]

            total = (dec_h != 'unknown').sum()
            if total < 10:
                continue

            hourly[int(h)] = {
                'suspend_pct': round(100 * (dec_h == 'suspend').sum() / total, 1),
                'reduce_pct': round(100 * (dec_h == 'reduce').sum() / total, 1),
                'maintain_pct': round(100 * (dec_h == 'maintain').sum() / total, 1),
                'increase_pct': round(100 * (dec_h == 'increase').sum() / total, 1),
                'surge_pct': round(100 * (dec_h == 'surge').sum() / total, 1),
                'mean_glucose': round(float(g_h.mean()), 1) if g_h.notna().sum() > 0 else None,
                'mean_iob': round(float(iob_h.mean()), 2) if iob_h.notna().sum() > 0 else None,
                'hypo_pct': round(100 * (g_h < HYPO_THRESHOLD).sum() / max(g_h.notna().sum(), 1), 1),
            }

        # Compute night vs day summary
        night_hours = [h for h in hourly if h in range(0, 6)]
        day_hours = [h for h in hourly if h in range(8, 20)]
        if night_hours and day_hours:
            night_suspend = np.mean([hourly[h]['suspend_pct'] for h in night_hours])
            day_suspend = np.mean([hourly[h]['suspend_pct'] for h in day_hours])
            night_increase = np.mean([hourly[h]['increase_pct'] for h in night_hours])
            day_increase = np.mean([hourly[h]['increase_pct'] for h in day_hours])
        else:
            night_suspend = day_suspend = night_increase = day_increase = None

        results[name] = {
            'hourly': hourly,
            'night_suspend_pct': round(float(night_suspend), 1) if night_suspend is not None else None,
            'day_suspend_pct': round(float(day_suspend), 1) if day_suspend is not None else None,
            'night_increase_pct': round(float(night_increase), 1) if night_increase is not None else None,
            'day_increase_pct': round(float(day_increase), 1) if day_increase is not None else None,
        }
        if night_suspend is not None:
            print(f"  {name}: night_suspend={night_suspend:.1f}%, day_suspend={day_suspend:.1f}%, night_inc={night_increase:.1f}%, day_inc={day_increase:.1f}%")
        else:
            print(f"  {name}: insufficient hourly data")

    if save_dir:
        _save_json(results, save_dir, 'exp-2197_circadian_decisions.json')

    return results


def exp_2198_decision_efficiency(patients, save_dir=None):
    """EXP-2198: Glucose change per unit insulin by decision context."""
    print("\n=== EXP-2198: Decision Efficiency ===")
    results = {}

    for p in patients:
        name = p['name']
        df = p['df']

        # Compute insulin delivered per step
        enacted = df['enacted_rate'].fillna(0) / STEPS_PER_HOUR  # U per 5-min step
        bolus = df['bolus'].fillna(0)
        total_insulin = enacted + bolus

        # Glucose change over next hour
        glucose = df['glucose']
        delta_1h = glucose.shift(-STEPS_PER_HOUR) - glucose

        # Efficiency by glucose zone
        zones = {
            'hypo': glucose < 70,
            'low_normal': (glucose >= 70) & (glucose < 100),
            'normal': (glucose >= 100) & (glucose < 140),
            'high_normal': (glucose >= 140) & (glucose < 180),
            'high': (glucose >= 180) & (glucose < 250),
            'very_high': glucose >= 250,
        }

        zone_results = {}
        for zone_name, zone_mask in zones.items():
            valid = zone_mask & delta_1h.notna() & (total_insulin > 0)
            if valid.sum() < 20:
                continue

            ins = total_insulin[valid]
            delta = delta_1h[valid]
            efficiency = delta / ins  # mg/dL per U

            zone_results[zone_name] = {
                'count': int(valid.sum()),
                'mean_insulin_U': round(float(ins.mean()), 3),
                'mean_delta_1h': round(float(delta.mean()), 1),
                'efficiency_per_U': round(float(efficiency.median()), 1),
                'hypo_transition_pct': round(100 * float((glucose.shift(-STEPS_PER_HOUR)[valid] < HYPO_THRESHOLD).mean()), 1),
            }

        # Time-of-day efficiency
        tod_results = {}
        for period, hours in [('night', range(0, 6)), ('morning', range(6, 12)),
                               ('afternoon', range(12, 18)), ('evening', range(18, 24))]:
            mask = df.index.hour.isin(hours) & delta_1h.notna() & (total_insulin > 0)
            if mask.sum() < 20:
                continue
            ins = total_insulin[mask]
            delta = delta_1h[mask]
            efficiency = delta / ins
            tod_results[period] = {
                'count': int(mask.sum()),
                'mean_insulin_U': round(float(ins.mean()), 3),
                'efficiency_per_U': round(float(efficiency.median()), 1),
            }

        results[name] = {
            'by_zone': zone_results,
            'by_time_of_day': tod_results,
        }

        # Print summary
        if 'normal' in zone_results and 'high' in zone_results:
            print(f"  {name}: normal_eff={zone_results['normal']['efficiency_per_U']}, high_eff={zone_results['high']['efficiency_per_U']}")
        else:
            print(f"  {name}: zones computed: {list(zone_results.keys())}")

    if save_dir:
        _save_json(results, save_dir, 'exp-2198_decision_efficiency.json')

    return results


def _save_json(data, save_dir, filename):
    path = os.path.join(save_dir, filename)
    os.makedirs(save_dir, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, cls=NumpyEncoder)
    print(f"  Saved {path}")


def generate_figures(all_results, fig_dir):
    """Generate 8 figures for loop decision analysis."""
    os.makedirs(fig_dir, exist_ok=True)

    # Fig 1: Decision Taxonomy Stacked Bar
    r2191 = all_results.get('exp_2191', {})
    if r2191:
        fig, ax = plt.subplots(figsize=(14, 7))
        names = sorted(r2191.keys())
        dec_types = ['suspend', 'reduce', 'maintain', 'increase', 'surge']
        colors = ['#d62728', '#ff7f0e', '#2ca02c', '#1f77b4', '#9467bd']
        bottoms = np.zeros(len(names))

        for dt, color in zip(dec_types, colors):
            vals = []
            for n in names:
                decs = r2191[n].get('decisions', {})
                vals.append(decs.get(dt, {}).get('pct', 0))
            ax.bar(names, vals, bottom=bottoms, label=dt, color=color, alpha=0.85)
            bottoms += np.array(vals)

        ax.set_ylabel('% of Loop Decisions')
        ax.set_title('EXP-2191: AID Loop Decision Taxonomy by Patient')
        ax.legend(loc='upper right')
        ax.set_ylim(0, 105)
        for i, n in enumerate(names):
            zd = r2191[n].get('zero_delivery_pct', 0)
            ax.text(i, 102, f'{zd:.0f}%\nzero', ha='center', va='bottom', fontsize=7, color='red')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'loop-fig01-decision-taxonomy.png'), dpi=150)
        plt.close()
        print("  Fig 1: Decision taxonomy")

    # Fig 2: Prediction Accuracy Scatter
    r2192 = all_results.get('exp_2192', {})
    if r2192:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        names = sorted(r2192.keys())

        # MAE comparison
        mae30 = [r2192[n].get('mae_30', 0) or 0 for n in names]
        mae60 = [r2192[n].get('mae_60', 0) or 0 for n in names]
        x = np.arange(len(names))
        axes[0].bar(x - 0.2, mae30, 0.35, label='30-min MAE', color='#1f77b4')
        axes[0].bar(x + 0.2, mae60, 0.35, label='60-min MAE', color='#ff7f0e')
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('MAE (mg/dL)')
        axes[0].set_title('Loop Prediction Error')
        axes[0].legend()

        # Bias
        bias30 = [r2192[n].get('bias_30', 0) or 0 for n in names]
        bias60 = [r2192[n].get('bias_60', 0) or 0 for n in names]
        axes[1].bar(x - 0.2, bias30, 0.35, label='30-min Bias', color='#1f77b4')
        axes[1].bar(x + 0.2, bias60, 0.35, label='60-min Bias', color='#ff7f0e')
        axes[1].axhline(0, color='k', linewidth=0.5)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('Bias (mg/dL)')
        axes[1].set_title('Loop Prediction Bias (+ = overestimate)')
        axes[1].legend()

        plt.suptitle('EXP-2192: Loop Glucose Prediction Accuracy', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'loop-fig02-prediction-accuracy.png'), dpi=150)
        plt.close()
        print("  Fig 2: Prediction accuracy")

    # Fig 3: Decision-to-Outcome Heatmap
    r2193 = all_results.get('exp_2193', {})
    if r2193:
        fig, ax = plt.subplots(figsize=(12, 8))
        dec_types = ['suspend', 'reduce', 'maintain', 'increase', 'surge']
        names = sorted(r2193.keys())

        data_matrix = []
        ylabels = []
        for n in names:
            row = []
            for dt in dec_types:
                val = r2193[n].get(dt, {}).get('delta_60_mean', None)
                row.append(val if val is not None else np.nan)
            data_matrix.append(row)
            ylabels.append(n)

        data_matrix = np.array(data_matrix)
        im = ax.imshow(data_matrix, cmap='RdYlGn_r', aspect='auto',
                       vmin=-30, vmax=30)
        ax.set_xticks(range(len(dec_types)))
        ax.set_xticklabels(dec_types)
        ax.set_yticks(range(len(ylabels)))
        ax.set_yticklabels(ylabels)

        for i in range(len(ylabels)):
            for j in range(len(dec_types)):
                val = data_matrix[i, j]
                if not np.isnan(val):
                    ax.text(j, i, f'{val:+.0f}', ha='center', va='center',
                            fontsize=9, fontweight='bold',
                            color='white' if abs(val) > 15 else 'black')

        plt.colorbar(im, label='Δ Glucose 60min (mg/dL)')
        ax.set_title('EXP-2193: Glucose Change 60min After Loop Decision')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'loop-fig03-decision-outcome.png'), dpi=150)
        plt.close()
        print("  Fig 3: Decision-outcome heatmap")

    # Fig 4: Hypo Risk Calibration
    r2194 = all_results.get('exp_2194', {})
    if r2194:
        fig, axes = plt.subplots(2, 3, figsize=(16, 10))
        axes = axes.flatten()
        names = sorted(r2194.keys())[:6]  # Top 6 for readability

        for idx, n in enumerate(names):
            ax = axes[idx]
            cal = r2194[n].get('calibration', [])
            if not cal:
                ax.text(0.5, 0.5, 'No data', ha='center', transform=ax.transAxes)
                ax.set_title(n)
                continue

            predicted = [(c['bin_low'] + c['bin_high']) / 2 for c in cal]
            actual_1h = [c['actual_1h'] for c in cal]
            actual_2h = [c['actual_2h'] for c in cal]
            sizes = [max(c['n'] / 100, 5) for c in cal]

            ax.scatter(predicted, actual_2h, s=sizes, alpha=0.7, color='#d62728', label='Actual 2h')
            ax.scatter(predicted, actual_1h, s=sizes, alpha=0.7, color='#1f77b4', label='Actual 1h')
            ax.plot([0, 1], [0, 1], 'k--', alpha=0.3, label='Perfect')
            ax.set_xlim(-0.05, 1.05)
            ax.set_ylim(-0.05, max(0.5, max(actual_2h) * 1.1) if actual_2h else 0.5)
            ax.set_title(f'Patient {n}')
            ax.set_xlabel('Predicted Risk')
            ax.set_ylabel('Actual Hypo Rate')
            if idx == 0:
                ax.legend(fontsize=7)

        plt.suptitle('EXP-2194: Hypo Risk Calibration', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'loop-fig04-hypo-calibration.png'), dpi=150)
        plt.close()
        print("  Fig 4: Hypo risk calibration")

    # Fig 5: Pre-Hypo Decision Sequence
    r2195 = all_results.get('exp_2195', {})
    if r2195:
        fig, axes = plt.subplots(2, 3, figsize=(16, 10))
        axes = axes.flatten()
        names = sorted(r2195.keys())[:6]

        for idx, n in enumerate(names):
            ax = axes[idx]
            pre_dec = r2195[n].get('pre_decisions', {})
            if not pre_dec:
                ax.text(0.5, 0.5, 'No data', ha='center', transform=ax.transAxes)
                ax.set_title(n)
                continue

            buckets = sorted(pre_dec.keys(), key=lambda x: int(x.split('-')[0]))
            dec_types = ['suspend', 'reduce', 'maintain', 'increase', 'surge']
            colors = ['#d62728', '#ff7f0e', '#2ca02c', '#1f77b4', '#9467bd']
            bottoms = np.zeros(len(buckets))

            for dt, color in zip(dec_types, colors):
                vals = [pre_dec[b].get(dt, 0) for b in buckets]
                ax.bar(range(len(buckets)), vals, bottom=bottoms, color=color, alpha=0.8, label=dt)
                bottoms += np.array(vals)

            ax.set_xticks(range(len(buckets)))
            ax.set_xticklabels([b.split('-')[0] for b in buckets], rotation=45, fontsize=7)
            ax.set_xlabel('Minutes before hypo')
            ax.set_ylabel('% of decisions')
            ax.set_title(f'{n} (n={r2195[n]["n_hypos"]})')
            if idx == 0:
                ax.legend(fontsize=6)

        plt.suptitle('EXP-2195: Loop Decisions Before Hypoglycemia', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'loop-fig05-pre-hypo-decisions.png'), dpi=150)
        plt.close()
        print("  Fig 5: Pre-hypo decisions")

    # Fig 6: Aggressiveness Profile
    r2196 = all_results.get('exp_2196', {})
    if r2196:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))
        names = sorted(r2196.keys())

        # Follow rate
        follow = [r2196[n].get('follow_rate', 0) or 0 for n in names]
        axes[0].barh(names, [f * 100 for f in follow], color='#2ca02c')
        axes[0].set_xlabel('Follow Rate (%)')
        axes[0].set_title('Recommendation Follow Rate')
        axes[0].set_xlim(0, 105)

        # Override %
        override = [r2196[n].get('override_pct', 0) for n in names]
        axes[1].barh(names, override, color='#d62728')
        axes[1].set_xlabel('Override Rate (%)')
        axes[1].set_title('Recommendation Override Rate')

        # Enacted/Recommended ratio
        ratio = [r2196[n].get('enacted_to_rec_ratio', 1) or 1 for n in names]
        colors = ['#d62728' if r > 1.2 else '#2ca02c' if r < 0.8 else '#1f77b4' for r in ratio]
        axes[2].barh(names, ratio, color=colors)
        axes[2].axvline(1.0, color='k', linestyle='--', alpha=0.5)
        axes[2].set_xlabel('Enacted / Recommended')
        axes[2].set_title('Dosing Ratio')

        plt.suptitle('EXP-2196: Loop Aggressiveness', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'loop-fig06-aggressiveness.png'), dpi=150)
        plt.close()
        print("  Fig 6: Aggressiveness")

    # Fig 7: Circadian Decision Patterns (selected patients)
    r2197 = all_results.get('exp_2197', {})
    if r2197:
        fig, axes = plt.subplots(3, 2, figsize=(16, 14))
        axes = axes.flatten()
        names = sorted(r2197.keys())[:6]

        for idx, n in enumerate(names):
            ax = axes[idx]
            hourly = r2197[n].get('hourly', {})
            if not hourly:
                ax.set_title(n)
                continue

            hours = sorted([int(h) for h in hourly.keys()])
            dec_types = ['suspend', 'reduce', 'maintain', 'increase', 'surge']
            colors = ['#d62728', '#ff7f0e', '#2ca02c', '#1f77b4', '#9467bd']

            bottoms = np.zeros(len(hours))
            for dt, color in zip(dec_types, colors):
                vals = [hourly.get(str(h), hourly.get(h, {})).get(f'{dt}_pct', 0) for h in hours]
                ax.bar(hours, vals, bottom=bottoms, color=color, alpha=0.8, label=dt)
                bottoms += np.array(vals)

            # Overlay glucose
            ax2 = ax.twinx()
            glucose_vals = [hourly.get(str(h), hourly.get(h, {})).get('mean_glucose', None) for h in hours]
            glucose_vals = [g for g in glucose_vals if g is not None]
            if glucose_vals:
                ax2.plot(hours[:len(glucose_vals)], glucose_vals, 'k-o', markersize=3, linewidth=1.5, label='Glucose')
                ax2.set_ylabel('Mean Glucose (mg/dL)', fontsize=8)

            ax.set_xlabel('Hour')
            ax.set_ylabel('% Decisions')
            ax.set_title(f'Patient {n}')
            ax.set_xlim(-0.5, 23.5)
            if idx == 0:
                ax.legend(fontsize=6, loc='upper left')

        plt.suptitle('EXP-2197: Circadian Loop Decision Patterns', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'loop-fig07-circadian-decisions.png'), dpi=150)
        plt.close()
        print("  Fig 7: Circadian decisions")

    # Fig 8: Decision Efficiency by Zone
    r2198 = all_results.get('exp_2198', {})
    if r2198:
        fig, axes = plt.subplots(1, 2, figsize=(16, 7))
        names = sorted(r2198.keys())

        # By glucose zone
        zones = ['hypo', 'low_normal', 'normal', 'high_normal', 'high', 'very_high']
        zone_colors = ['#d62728', '#ff7f0e', '#2ca02c', '#1f77b4', '#9467bd', '#8c564b']

        for zi, zone in enumerate(zones):
            effs = []
            labels = []
            for n in names:
                val = r2198[n].get('by_zone', {}).get(zone, {}).get('efficiency_per_U', None)
                if val is not None:
                    effs.append(val)
                    labels.append(n)
            if effs:
                axes[0].scatter([zi] * len(effs), effs, color=zone_colors[zi], alpha=0.7, s=60,
                              label=zone if zi < 6 else None)
                for j, (lbl, eff) in enumerate(zip(labels, effs)):
                    axes[0].annotate(lbl, (zi, eff), fontsize=6, alpha=0.5)

        axes[0].set_xticks(range(len(zones)))
        axes[0].set_xticklabels(zones, rotation=30)
        axes[0].set_ylabel('Efficiency (mg/dL per U)')
        axes[0].set_title('Insulin Efficiency by Glucose Zone')
        axes[0].axhline(0, color='k', linewidth=0.5)

        # By time of day
        periods = ['night', 'morning', 'afternoon', 'evening']
        period_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
        for pi, period in enumerate(periods):
            effs = []
            labels = []
            for n in names:
                val = r2198[n].get('by_time_of_day', {}).get(period, {}).get('efficiency_per_U', None)
                if val is not None:
                    effs.append(val)
                    labels.append(n)
            if effs:
                axes[1].scatter([pi] * len(effs), effs, color=period_colors[pi], alpha=0.7, s=60)
                for j, (lbl, eff) in enumerate(zip(labels, effs)):
                    axes[1].annotate(lbl, (pi, eff), fontsize=6, alpha=0.5)

        axes[1].set_xticks(range(len(periods)))
        axes[1].set_xticklabels(periods)
        axes[1].set_ylabel('Efficiency (mg/dL per U)')
        axes[1].set_title('Insulin Efficiency by Time of Day')
        axes[1].axhline(0, color='k', linewidth=0.5)

        plt.suptitle('EXP-2198: Loop Decision Efficiency', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'loop-fig08-efficiency.png'), dpi=150)
        plt.close()
        print("  Fig 8: Decision efficiency")


def main():
    parser = argparse.ArgumentParser(description='EXP-2191–2198: AID Loop Decision Analysis')
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    parser.add_argument('--data-dir', default='externals/ns-data/patients/', help='Patient data directory')
    parser.add_argument('--save-dir', default='externals/experiments/', help='Results save directory')
    parser.add_argument('--fig-dir', default='docs/60-research/figures/', help='Figure output directory')
    args = parser.parse_args()

    print("Loading patient data...")
    patients = load_patients(args.data_dir)
    print(f"Loaded {len(patients)} patients\n")

    all_results = {}

    # Run all experiments
    all_results['exp_2191'] = exp_2191_decision_taxonomy(patients, args.save_dir)
    all_results['exp_2192'] = exp_2192_prediction_accuracy(patients, args.save_dir)
    all_results['exp_2193'] = exp_2193_decision_outcome(patients, args.save_dir)
    all_results['exp_2194'] = exp_2194_hypo_risk_calibration(patients, args.save_dir)
    all_results['exp_2195'] = exp_2195_pre_hypo_decisions(patients, args.save_dir)
    all_results['exp_2196'] = exp_2196_aggressiveness(patients, args.save_dir)
    all_results['exp_2197'] = exp_2197_circadian_decisions(patients, args.save_dir)
    all_results['exp_2198'] = exp_2198_decision_efficiency(patients, args.save_dir)

    if args.figures:
        print("\n=== Generating Figures ===")
        generate_figures(all_results, args.fig_dir)

    print("\n=== All 8 experiments complete ===")

    # Summary
    print("\nKey Findings Summary:")
    for name, r in all_results.get('exp_2191', {}).items():
        zd = r.get('zero_delivery_pct', 0)
        sus = r.get('decisions', {}).get('suspend', {}).get('pct', 0)
        print(f"  {name}: {zd:.0f}% zero delivery, {sus:.0f}% suspend")


if __name__ == '__main__':
    main()
