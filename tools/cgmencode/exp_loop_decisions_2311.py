#!/usr/bin/env python3
"""
EXP-2311 through EXP-2318: AID Loop Decision Analysis

Examines how the AID loop makes decisions, when it over/under-acts,
and what patterns in loop behavior drive glucose outcomes.

Experiments:
  2311: Loop activity profile (delivery patterns across 24h)
  2312: Prediction accuracy (loop's 30/60-min forecasts vs actual)
  2313: Suspension analysis (when and why the loop suspends delivery)
  2314: Over-delivery episodes (when loop delivers too much insulin)
  2315: Under-delivery episodes (when loop should have delivered more)
  2316: Loop response to meals (enacted vs recommended around meals)
  2317: Loop hypo risk signal evaluation
  2318: Loop effectiveness scorecard

Usage:
  PYTHONPATH=tools python3 tools/cgmencode/exp_loop_decisions_2311.py --figures
  PYTHONPATH=tools python3 tools/cgmencode/exp_loop_decisions_2311.py --figures --tiny
"""

import argparse
import json
import os
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

warnings.filterwarnings('ignore')

STEPS_PER_HOUR = 12
STEP_MINUTES = 5


def load_patients_parquet(parquet_dir='externals/ns-parquet/training'):
    grid = pd.read_parquet(os.path.join(parquet_dir, 'grid.parquet'))
    patients = []
    for pid in sorted(grid['patient_id'].unique()):
        pdf = grid[grid['patient_id'] == pid].copy()
        pdf = pdf.set_index('time').sort_index()
        profile = {
            'isf': float(pdf['scheduled_isf'].median()),
            'cr': float(pdf['scheduled_cr'].median()),
            'basal': float(pdf['scheduled_basal_rate'].median()),
        }
        patients.append({'name': pid, 'df': pdf, 'profile': profile})
        print(f"  {pid}: {len(pdf)} steps")
    return patients


def hour_of_day(df):
    idx = pd.to_datetime(df.index) if not isinstance(df.index, pd.DatetimeIndex) else df.index
    return idx.hour


# ── Experiments ──────────────────────────────────────────────────────────

def exp_2311_activity(patients):
    """Loop activity profile — delivery patterns across 24h."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        hours = hour_of_day(df)
        profile = pat['profile']

        enacted = df['loop_enacted_rate'].values if 'loop_enacted_rate' in df.columns else df.get('actual_basal_rate', pd.Series(dtype=float)).values
        scheduled = df['scheduled_basal_rate'].values
        actual = df['actual_basal_rate'].values if 'actual_basal_rate' in df.columns else enacted

        # Hourly delivery profile
        hourly = {}
        for h in range(24):
            mask = hours == h
            enacted_h = enacted[mask]
            sched_h = scheduled[mask]
            actual_h = actual[mask]

            valid_enacted = enacted_h[~np.isnan(enacted_h)]
            valid_actual = actual_h[~np.isnan(actual_h)]

            hourly[str(h)] = {
                'mean_enacted': round(float(np.mean(valid_enacted)), 3) if len(valid_enacted) > 0 else None,
                'mean_scheduled': round(float(np.mean(sched_h[~np.isnan(sched_h)])), 3) if np.sum(~np.isnan(sched_h)) > 0 else None,
                'mean_actual': round(float(np.mean(valid_actual)), 3) if len(valid_actual) > 0 else None,
                'zero_pct': round(float(np.mean(valid_actual == 0) * 100), 1) if len(valid_actual) > 0 else None,
            }

        # Overall metrics
        valid_actual = actual[~np.isnan(actual)]
        valid_sched = scheduled[~np.isnan(scheduled)]

        zero_delivery_pct = float(np.mean(valid_actual == 0) * 100) if len(valid_actual) > 0 else 0
        above_scheduled = float(np.mean(valid_actual > valid_sched[:len(valid_actual)]) * 100) if len(valid_actual) > 0 and len(valid_sched) >= len(valid_actual) else 0

        # Delivery ratio: actual / scheduled
        ratio_mask = (valid_sched > 0) & (~np.isnan(valid_actual[:len(valid_sched)]))
        delivery_ratio = float(np.median(valid_actual[:len(valid_sched)][ratio_mask] / valid_sched[ratio_mask])) if ratio_mask.sum() > 0 else np.nan

        results[name] = {
            'hourly': hourly,
            'zero_delivery_pct': round(zero_delivery_pct, 1),
            'above_scheduled_pct': round(above_scheduled, 1),
            'delivery_ratio': round(delivery_ratio, 2) if not np.isnan(delivery_ratio) else None,
            'mean_actual': round(float(np.mean(valid_actual)), 3) if len(valid_actual) > 0 else None,
            'mean_scheduled': round(float(np.mean(valid_sched)), 3) if len(valid_sched) > 0 else None,
        }
        print(f"  {name}: zero={zero_delivery_pct:.0f}%, above_sched={above_scheduled:.0f}%, ratio={delivery_ratio:.2f}")
    return results


def exp_2312_prediction(patients):
    """Prediction accuracy — loop's 30/60-min forecasts vs actual."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values

        pred_30 = df['loop_predicted_30'].values if 'loop_predicted_30' in df.columns else np.full(len(df), np.nan)
        pred_60 = df['loop_predicted_60'].values if 'loop_predicted_60' in df.columns else np.full(len(df), np.nan)

        # Compare predictions to actual glucose 30/60 min later
        errors_30 = []
        errors_60 = []
        for i in range(len(df) - 12):
            if not np.isnan(pred_30[i]) and not np.isnan(glucose[i + 6]):  # 30 min = 6 steps
                errors_30.append(pred_30[i] - glucose[i + 6])
            if not np.isnan(pred_60[i]) and i + 12 < len(glucose) and not np.isnan(glucose[i + 12]):
                errors_60.append(pred_60[i] - glucose[i + 12])

        e30 = np.array(errors_30)
        e60 = np.array(errors_60)

        results[name] = {
            'n_30min': len(e30),
            'n_60min': len(e60),
            'mae_30': round(float(np.mean(np.abs(e30))), 1) if len(e30) > 0 else None,
            'mae_60': round(float(np.mean(np.abs(e60))), 1) if len(e60) > 0 else None,
            'bias_30': round(float(np.mean(e30)), 1) if len(e30) > 0 else None,
            'bias_60': round(float(np.mean(e60)), 1) if len(e60) > 0 else None,
            'rmse_30': round(float(np.sqrt(np.mean(e30**2))), 1) if len(e30) > 0 else None,
            'rmse_60': round(float(np.sqrt(np.mean(e60**2))), 1) if len(e60) > 0 else None,
        }
        print(f"  {name}: MAE@30min={results[name]['mae_30']}, MAE@60min={results[name]['mae_60']}, bias@30={results[name]['bias_30']}")
    return results


def exp_2313_suspension(patients):
    """Suspension analysis — when and why the loop suspends delivery."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        hours = hour_of_day(df)
        glucose = df['glucose'].values
        actual = df['actual_basal_rate'].values if 'actual_basal_rate' in df.columns else np.full(len(df), np.nan)

        # Identify suspensions (actual_basal_rate == 0)
        valid_mask = ~np.isnan(actual)
        suspended = (actual == 0) & valid_mask

        # Glucose during suspensions
        susp_bg = glucose[suspended & ~np.isnan(glucose)]
        non_susp_bg = glucose[~suspended & ~np.isnan(glucose)]

        # Hourly suspension rate
        hourly_susp = {}
        for h in range(24):
            mask = (hours == h) & valid_mask
            if mask.sum() > 0:
                hourly_susp[str(h)] = round(float(np.mean(actual[mask] == 0) * 100), 1)

        # Suspension duration analysis
        susp_runs = []
        in_suspension = False
        run_length = 0
        for i in range(len(df)):
            if suspended[i]:
                if not in_suspension:
                    in_suspension = True
                    run_length = 1
                else:
                    run_length += 1
            else:
                if in_suspension:
                    susp_runs.append(run_length * STEP_MINUTES)
                    in_suspension = False
                    run_length = 0
        if in_suspension:
            susp_runs.append(run_length * STEP_MINUTES)

        results[name] = {
            'suspension_pct': round(float(suspended.sum() / valid_mask.sum() * 100), 1) if valid_mask.sum() > 0 else 0,
            'mean_bg_during': round(float(np.mean(susp_bg)), 1) if len(susp_bg) > 0 else None,
            'mean_bg_outside': round(float(np.mean(non_susp_bg)), 1) if len(non_susp_bg) > 0 else None,
            'hourly_suspension': hourly_susp,
            'n_suspension_episodes': len(susp_runs),
            'mean_duration_min': round(float(np.mean(susp_runs)), 1) if susp_runs else 0,
            'median_duration_min': round(float(np.median(susp_runs)), 1) if susp_runs else 0,
            'max_duration_min': round(float(np.max(susp_runs)), 1) if susp_runs else 0,
        }
        print(f"  {name}: {results[name]['suspension_pct']:.0f}% suspended, {len(susp_runs)} episodes, median {results[name]['median_duration_min']:.0f}min")
    return results


def exp_2314_over_delivery(patients):
    """Over-delivery episodes — when loop delivers too much insulin."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        actual = df['actual_basal_rate'].values if 'actual_basal_rate' in df.columns else np.full(len(df), np.nan)
        scheduled = df['scheduled_basal_rate'].values

        # Over-delivery: actual > 2× scheduled AND glucose drops below 80 within 2 hours
        over_episodes = 0
        over_to_hypo = 0
        over_ratios = []

        for i in range(len(df) - 24):
            if np.isnan(actual[i]) or np.isnan(scheduled[i]) or scheduled[i] == 0:
                continue
            ratio = actual[i] / scheduled[i]
            if ratio > 2.0:
                over_episodes += 1
                over_ratios.append(ratio)
                # Check if glucose goes below 80 in next 2h
                future_bg = glucose[i:i + 24]
                if np.any(future_bg[~np.isnan(future_bg)] < 80):
                    over_to_hypo += 1

        n_days = len(df) / (STEPS_PER_HOUR * 24)
        results[name] = {
            'over_delivery_episodes': over_episodes,
            'over_per_day': round(over_episodes / n_days, 1),
            'over_leading_to_hypo': over_to_hypo,
            'hypo_rate_from_over': round(over_to_hypo / over_episodes * 100, 1) if over_episodes > 0 else 0,
            'mean_over_ratio': round(float(np.mean(over_ratios)), 2) if over_ratios else 0,
            'max_over_ratio': round(float(np.max(over_ratios)), 2) if over_ratios else 0,
        }
        print(f"  {name}: {over_episodes} over-delivery ({over_episodes/n_days:.0f}/day), {over_to_hypo} led to hypo ({results[name]['hypo_rate_from_over']:.0f}%)")
    return results


def exp_2315_under_delivery(patients):
    """Under-delivery episodes — when loop should have delivered more."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        actual = df['actual_basal_rate'].values if 'actual_basal_rate' in df.columns else np.full(len(df), np.nan)
        scheduled = df['scheduled_basal_rate'].values

        # Under-delivery: actual < 0.5× scheduled AND glucose rises above 200 within 2 hours
        under_episodes = 0
        under_to_hyper = 0
        under_ratios = []

        for i in range(len(df) - 24):
            if np.isnan(actual[i]) or np.isnan(scheduled[i]) or scheduled[i] == 0:
                continue
            ratio = actual[i] / scheduled[i]
            if ratio < 0.5:
                under_episodes += 1
                under_ratios.append(ratio)
                future_bg = glucose[i:i + 24]
                if np.any(future_bg[~np.isnan(future_bg)] > 200):
                    under_to_hyper += 1

        n_days = len(df) / (STEPS_PER_HOUR * 24)
        results[name] = {
            'under_delivery_episodes': under_episodes,
            'under_per_day': round(under_episodes / n_days, 1),
            'under_leading_to_hyper': under_to_hyper,
            'hyper_rate_from_under': round(under_to_hyper / under_episodes * 100, 1) if under_episodes > 0 else 0,
            'mean_under_ratio': round(float(np.mean(under_ratios)), 2) if under_ratios else 0,
        }
        print(f"  {name}: {under_episodes} under-delivery ({under_episodes/n_days:.0f}/day), {under_to_hyper} led to hyper ({results[name]['hyper_rate_from_under']:.0f}%)")
    return results


def exp_2316_meal_response(patients):
    """Loop response to meals — enacted vs recommended around meals."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        carbs = df['carbs'].values
        actual = df['actual_basal_rate'].values if 'actual_basal_rate' in df.columns else np.full(len(df), np.nan)
        scheduled = df['scheduled_basal_rate'].values
        glucose = df['glucose'].values

        # Find meals
        meal_steps = []
        last = -24
        for i in range(len(df)):
            if carbs[i] >= 5 and (i - last) >= 24:
                meal_steps.append(i)
                last = i

        if len(meal_steps) < 5:
            results[name] = {'skipped': True}
            continue

        # Analyze loop behavior around meals
        pre_rates = []    # 1h before meal
        post_rates = []   # 2h after meal
        pre_bg = []
        post_bg = []

        for step in meal_steps:
            if step < 12 or step + 24 >= len(df):
                continue
            # Pre-meal (1h before)
            pre = actual[step - 12:step]
            pre_valid = pre[~np.isnan(pre)]
            if len(pre_valid) > 0:
                pre_rates.append(float(np.mean(pre_valid)))

            # Post-meal (2h after)
            post = actual[step:step + 24]
            post_valid = post[~np.isnan(post)]
            if len(post_valid) > 0:
                post_rates.append(float(np.mean(post_valid)))

            # BG
            if not np.isnan(glucose[step]):
                pre_bg.append(float(glucose[step]))
            future = glucose[step:step + 24]
            valid_future = future[~np.isnan(future)]
            if len(valid_future) > 0:
                post_bg.append(float(np.max(valid_future)))

        sched_mean = float(np.mean(scheduled[~np.isnan(scheduled)])) if np.sum(~np.isnan(scheduled)) > 0 else 0

        results[name] = {
            'n_meals': len(meal_steps),
            'mean_pre_rate': round(float(np.mean(pre_rates)), 3) if pre_rates else None,
            'mean_post_rate': round(float(np.mean(post_rates)), 3) if post_rates else None,
            'mean_scheduled': round(sched_mean, 3),
            'post_vs_pre_ratio': round(float(np.mean(post_rates)) / float(np.mean(pre_rates)), 2) if pre_rates and post_rates and np.mean(pre_rates) > 0 else None,
            'mean_pre_bg': round(float(np.mean(pre_bg)), 1) if pre_bg else None,
            'mean_post_peak_bg': round(float(np.mean(post_bg)), 1) if post_bg else None,
        }
        print(f"  {name}: pre={results[name]['mean_pre_rate']}, post={results[name]['mean_post_rate']}, ratio={results[name]['post_vs_pre_ratio']}")
    return results


def exp_2317_hypo_risk(patients):
    """Loop hypo risk signal evaluation."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values
        hypo_risk = df['loop_hypo_risk'].values if 'loop_hypo_risk' in df.columns else np.full(len(df), np.nan)
        pred_min = df['loop_predicted_min'].values if 'loop_predicted_min' in df.columns else np.full(len(df), np.nan)

        # Evaluate: when hypo_risk > 0, does glucose actually go below 70 within 1h?
        true_positives = 0
        false_positives = 0
        true_negatives = 0
        false_negatives = 0

        for i in range(len(df) - 12):
            if np.isnan(hypo_risk[i]):
                continue
            predicted_risk = hypo_risk[i] > 0

            # Check actual
            future_bg = glucose[i:i + 12]
            actual_hypo = np.any(future_bg[~np.isnan(future_bg)] < 70) if np.sum(~np.isnan(future_bg)) > 0 else False

            if predicted_risk and actual_hypo:
                true_positives += 1
            elif predicted_risk and not actual_hypo:
                false_positives += 1
            elif not predicted_risk and actual_hypo:
                false_negatives += 1
            else:
                true_negatives += 1

        total = true_positives + false_positives + true_negatives + false_negatives
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        # Also check predicted_min accuracy
        min_errors = []
        for i in range(len(df) - 12):
            if np.isnan(pred_min[i]):
                continue
            future_bg = glucose[i:i + 12]
            valid = future_bg[~np.isnan(future_bg)]
            if len(valid) > 0:
                actual_min = float(np.min(valid))
                min_errors.append(pred_min[i] - actual_min)

        min_err = np.array(min_errors)

        results[name] = {
            'true_positives': true_positives,
            'false_positives': false_positives,
            'false_negatives': false_negatives,
            'true_negatives': true_negatives,
            'precision': round(precision, 3),
            'recall': round(recall, 3),
            'f1': round(f1, 3),
            'predicted_min_mae': round(float(np.mean(np.abs(min_err))), 1) if len(min_err) > 0 else None,
            'predicted_min_bias': round(float(np.mean(min_err)), 1) if len(min_err) > 0 else None,
        }
        print(f"  {name}: P={precision:.2f}, R={recall:.2f}, F1={f1:.2f}, min_MAE={results[name]['predicted_min_mae']}")
    return results


def exp_2318_scorecard(patients, all_results):
    """Loop effectiveness scorecard."""
    results = {}
    for pat in patients:
        name = pat['name']

        r2311 = all_results.get('exp_2311', {}).get(name, {})
        r2312 = all_results.get('exp_2312', {}).get(name, {})
        r2313 = all_results.get('exp_2313', {}).get(name, {})
        r2314 = all_results.get('exp_2314', {}).get(name, {})
        r2317 = all_results.get('exp_2317', {}).get(name, {})

        scores = {}

        # 1. Prediction accuracy: MAE@30 < 15 = 100, > 40 = 0
        mae30 = r2312.get('mae_30', 30) or 30
        scores['prediction'] = max(0, min(100, 100 - (mae30 - 15) * 100 / 25))

        # 2. Low suspension: < 20% = 100, > 60% = 0
        susp = r2313.get('suspension_pct', 30)
        scores['low_suspension'] = max(0, min(100, 100 - (susp - 20) * 100 / 40))

        # 3. Safe delivery: low % over-delivery episodes leading to hypo
        hypo_from_over = r2314.get('hypo_rate_from_over', 20)
        scores['safe_delivery'] = max(0, min(100, 100 - hypo_from_over * 2))

        # 4. Risk detection F1 > 0.5 = 100, < 0.1 = 0
        f1 = r2317.get('f1', 0.2)
        scores['risk_detection'] = max(0, min(100, f1 * 100 / 0.5))

        # 5. Delivery ratio close to 1.0
        ratio = r2311.get('delivery_ratio', 1.0) or 1.0
        deviation = abs(ratio - 1.0)
        scores['delivery_balance'] = max(0, min(100, 100 - deviation * 200))

        overall = round(float(np.mean(list(scores.values()))), 1)
        grade = 'A' if overall >= 80 else 'B' if overall >= 60 else 'C' if overall >= 40 else 'D'

        results[name] = {
            'scores': {k: round(v, 1) for k, v in scores.items()},
            'overall': overall,
            'grade': grade,
        }
        print(f"  {name}: {grade} ({overall:.0f}/100)")
    return results


# ── Figures ──────────────────────────────────────────────────────────────

def generate_figures(results, patients, fig_dir):
    os.makedirs(fig_dir, exist_ok=True)
    names = sorted([p['name'] for p in patients])

    # Fig 1: Activity profile
    fig, axes = plt.subplots(3, 4, figsize=(16, 10))
    axes_flat = axes.flatten()
    r2311 = results['exp_2311']
    for idx, name in enumerate(names):
        if idx >= 11: break
        ax = axes_flat[idx]
        data = r2311[name]
        hrs = list(range(24))
        actual_vals = [data['hourly'][str(h)].get('mean_actual') or 0 for h in hrs]
        sched_vals = [data['hourly'][str(h)].get('mean_scheduled') or 0 for h in hrs]
        ax.fill_between(hrs, actual_vals, alpha=0.3, color='steelblue', label='Actual')
        ax.plot(hrs, actual_vals, 'b-', lw=1.5)
        ax.plot(hrs, sched_vals, 'r--', lw=1, label='Scheduled')
        ax.set_title(f"{name}: {data['zero_delivery_pct']:.0f}% zero")
        ax.set_xlim(-0.5, 23.5)
    axes_flat[-1].axis('off')
    fig.suptitle('EXP-2311: Loop Delivery Profile (Actual vs Scheduled)', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/loop-fig01-activity.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 1: activity")

    # Fig 2: Prediction accuracy
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2312 = results['exp_2312']
    x = np.arange(len(names))
    mae30 = [r2312[n].get('mae_30') or 0 for n in names]
    mae60 = [r2312[n].get('mae_60') or 0 for n in names]
    w = 0.35
    axes[0].bar(x - w/2, mae30, w, label='30-min MAE', color='steelblue', alpha=0.7)
    axes[0].bar(x + w/2, mae60, w, label='60-min MAE', color='coral', alpha=0.7)
    axes[0].set_xticks(x); axes[0].set_xticklabels(names)
    axes[0].set_ylabel('MAE (mg/dL)'); axes[0].legend()
    axes[0].set_title('Prediction Error')

    bias30 = [r2312[n].get('bias_30') or 0 for n in names]
    bias60 = [r2312[n].get('bias_60') or 0 for n in names]
    axes[1].bar(x - w/2, bias30, w, label='30-min Bias', color='steelblue', alpha=0.7)
    axes[1].bar(x + w/2, bias60, w, label='60-min Bias', color='coral', alpha=0.7)
    axes[1].axhline(0, color='black', lw=0.5)
    axes[1].set_xticks(x); axes[1].set_xticklabels(names)
    axes[1].set_ylabel('Bias (mg/dL)'); axes[1].legend()
    axes[1].set_title('Prediction Bias (positive = overestimates)')
    fig.suptitle('EXP-2312: Loop Prediction Accuracy', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/loop-fig02-prediction.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 2: prediction")

    # Fig 3: Suspension analysis
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2313 = results['exp_2313']
    susp_pct = [r2313[n]['suspension_pct'] for n in names]
    axes[0].bar(np.arange(len(names)), susp_pct, color='red', alpha=0.5)
    axes[0].set_xticks(np.arange(len(names))); axes[0].set_xticklabels(names)
    axes[0].set_ylabel('% Time Suspended'); axes[0].set_title('Suspension Rate')

    med_dur = [r2313[n]['median_duration_min'] for n in names]
    axes[1].bar(np.arange(len(names)), med_dur, color='orange', alpha=0.7)
    axes[1].set_xticks(np.arange(len(names))); axes[1].set_xticklabels(names)
    axes[1].set_ylabel('Minutes'); axes[1].set_title('Median Suspension Duration')
    fig.suptitle('EXP-2313: Suspension Analysis', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/loop-fig03-suspension.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 3: suspension")

    # Fig 4: Over-delivery
    fig, ax = plt.subplots(figsize=(12, 5))
    r2314 = results['exp_2314']
    x = np.arange(len(names))
    total = [r2314[n]['over_per_day'] for n in names]
    hypo = [r2314[n]['over_leading_to_hypo'] / (len(patients[0]['df']) / 288) for n in names]  # approx
    ax.bar(x, total, color='mediumpurple', alpha=0.7, label='Over-delivery/day')
    ax.set_xticks(x); ax.set_xticklabels(names)
    ax.set_ylabel('Episodes/Day'); ax.legend()
    ax.set_title('EXP-2314: Over-Delivery Episodes (>2× scheduled)')
    for i, n in enumerate(names):
        rate = r2314[n]['hypo_rate_from_over']
        ax.text(i, total[i], f'{rate:.0f}%\nhypo', ha='center', va='bottom', fontsize=8)
    plt.tight_layout(); plt.savefig(f'{fig_dir}/loop-fig04-over-delivery.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 4: over-delivery")

    # Fig 5: Under-delivery
    fig, ax = plt.subplots(figsize=(12, 5))
    r2315 = results['exp_2315']
    x = np.arange(len(names))
    total = [r2315[n]['under_per_day'] for n in names]
    ax.bar(x, total, color='skyblue', alpha=0.7, label='Under-delivery/day')
    ax.set_xticks(x); ax.set_xticklabels(names)
    ax.set_ylabel('Episodes/Day'); ax.legend()
    ax.set_title('EXP-2315: Under-Delivery Episodes (<0.5× scheduled)')
    for i, n in enumerate(names):
        rate = r2315[n]['hyper_rate_from_under']
        ax.text(i, total[i], f'{rate:.0f}%\nhyper', ha='center', va='bottom', fontsize=8)
    plt.tight_layout(); plt.savefig(f'{fig_dir}/loop-fig05-under-delivery.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 5: under-delivery")

    # Fig 6: Meal response
    fig, ax = plt.subplots(figsize=(12, 5))
    r2316 = results['exp_2316']
    valid = [n for n in names if not r2316.get(n, {}).get('skipped')]
    x = np.arange(len(valid))
    pre = [r2316[n]['mean_pre_rate'] or 0 for n in valid]
    post = [r2316[n]['mean_post_rate'] or 0 for n in valid]
    w = 0.35
    ax.bar(x - w/2, pre, w, label='Pre-meal rate', color='steelblue', alpha=0.7)
    ax.bar(x + w/2, post, w, label='Post-meal rate', color='coral', alpha=0.7)
    ax.set_xticks(x); ax.set_xticklabels(valid)
    ax.set_ylabel('Basal Rate (U/hr)'); ax.legend()
    ax.set_title('EXP-2316: Loop Delivery Rate Around Meals')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/loop-fig06-meal-response.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 6: meal response")

    # Fig 7: Hypo risk evaluation
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    r2317 = results['exp_2317']
    x = np.arange(len(names))
    prec = [r2317[n]['precision'] for n in names]
    rec = [r2317[n]['recall'] for n in names]
    f1_vals = [r2317[n]['f1'] for n in names]
    w = 0.25
    axes[0].bar(x - w, prec, w, label='Precision', color='steelblue', alpha=0.7)
    axes[0].bar(x, rec, w, label='Recall', color='coral', alpha=0.7)
    axes[0].bar(x + w, f1_vals, w, label='F1', color='green', alpha=0.7)
    axes[0].set_xticks(x); axes[0].set_xticklabels(names)
    axes[0].set_ylabel('Score'); axes[0].legend()
    axes[0].set_title('Hypo Risk Detection')

    min_mae = [r2317[n].get('predicted_min_mae') or 0 for n in names]
    axes[1].bar(x, min_mae, color='purple', alpha=0.7)
    axes[1].set_xticks(x); axes[1].set_xticklabels(names)
    axes[1].set_ylabel('MAE (mg/dL)'); axes[1].set_title('Predicted Minimum BG Error')
    fig.suptitle('EXP-2317: Loop Hypo Risk Signal Evaluation', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/loop-fig07-hypo-risk.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 7: hypo risk")

    # Fig 8: Scorecard
    fig, ax = plt.subplots(figsize=(14, 6))
    r2318 = results['exp_2318']
    valid = [n for n in names if not r2318.get(n, {}).get('skipped')]
    categories = ['prediction', 'low_suspension', 'safe_delivery', 'risk_detection', 'delivery_balance']
    cat_labels = ['Prediction\nAccuracy', 'Low\nSuspension', 'Safe\nDelivery', 'Risk\nDetection', 'Delivery\nBalance']
    data_matrix = np.array([[r2318[n]['scores'][c] for c in categories] for n in valid])
    im = ax.imshow(data_matrix.T, aspect='auto', cmap='RdYlGn', vmin=0, vmax=100)
    ax.set_xticks(range(len(valid))); ax.set_xticklabels(valid)
    ax.set_yticks(range(len(cat_labels))); ax.set_yticklabels(cat_labels)
    for i in range(len(valid)):
        for j in range(len(categories)):
            val = data_matrix[i, j]
            ax.text(i, j, f'{val:.0f}', ha='center', va='center', fontsize=9,
                    color='white' if val < 40 else 'black')
        grade = r2318[valid[i]]['grade']
        overall = r2318[valid[i]]['overall']
        ax.text(i, -0.6, f'{grade} ({overall:.0f})', ha='center', va='center', fontsize=10, fontweight='bold')
    plt.colorbar(im, label='Score (0-100)')
    ax.set_title('EXP-2318: Loop Effectiveness Scorecard', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/loop-fig08-scorecard.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 8: scorecard")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    parser.add_argument('--tiny', action='store_true')
    args = parser.parse_args()

    parquet_dir = 'externals/ns-parquet-tiny/training' if args.tiny else 'externals/ns-parquet/training'
    print(f"Loading patients from {parquet_dir}...")
    patients = load_patients_parquet(parquet_dir)
    print(f"Loaded {len(patients)} patients\n")

    results = {}

    for exp_id, exp_name, exp_fn in [
        ('exp_2311', 'Activity Profile', lambda: exp_2311_activity(patients)),
        ('exp_2312', 'Prediction Accuracy', lambda: exp_2312_prediction(patients)),
        ('exp_2313', 'Suspension Analysis', lambda: exp_2313_suspension(patients)),
        ('exp_2314', 'Over-Delivery', lambda: exp_2314_over_delivery(patients)),
        ('exp_2315', 'Under-Delivery', lambda: exp_2315_under_delivery(patients)),
        ('exp_2316', 'Meal Response', lambda: exp_2316_meal_response(patients)),
        ('exp_2317', 'Hypo Risk Signal', lambda: exp_2317_hypo_risk(patients)),
    ]:
        print(f"Running {exp_id}: {exp_name}...")
        results[exp_id] = exp_fn()
        print(f"  ✓ completed\n")

    print("Running exp_2318: Scorecard...")
    results['exp_2318'] = exp_2318_scorecard(patients, results)
    print("  ✓ completed\n")

    out_path = 'externals/experiments/exp-2311-2318_loop_decisions.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    def convert(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, (np.bool_,)): return bool(obj)
        raise TypeError(f"Not serializable: {type(obj)}")
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"Results saved to {out_path}")

    if args.figures:
        print("\nGenerating figures...")
        generate_figures(results, patients, 'docs/60-research/figures')
        print("All figures generated.")


if __name__ == '__main__':
    main()
