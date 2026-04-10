#!/usr/bin/env python3
"""
EXP-2041–2048: AID Loop Decision Analysis

Analyzing how the AID loop actually makes decisions: when it acts, how
it distributes insulin, what triggers corrections, and where it fails.
Maps findings to actionable algorithm improvements.

EXP-2041: Insulin distribution analysis (basal vs bolus vs correction)
EXP-2042: Loop decision patterns (when does the loop suspend/increase/correct)
EXP-2043: Prediction accuracy by context (pre-meal, post-meal, overnight, correction)
EXP-2044: Overcorrection detection (when does the loop cause hypos)
EXP-2045: Overnight control analysis (dawn phenomenon, compression lows, basal adequacy)
EXP-2046: Recovery time analysis (how long to return to range from hyper/hypo)
EXP-2047: Glycemic variability decomposition (what fraction from meals, basal, corrections)
EXP-2048: Synthesis — AID optimization opportunities

Depends on: exp_metabolic_441.py
"""

import json
import sys
import os
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from exp_metabolic_441 import load_patients, compute_supply_demand

PATIENT_DIR = 'externals/ns-data/patients/'
FIG_DIR = 'docs/60-research/figures'
EXP_DIR = 'externals/experiments'
MAKE_FIGS = '--figures' in sys.argv

if MAKE_FIGS:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    os.makedirs(FIG_DIR, exist_ok=True)

os.makedirs(EXP_DIR, exist_ok=True)

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
HYPO_THRESH = 70
TARGET_LOW = 70
TARGET_HIGH = 180


patients = load_patients(PATIENT_DIR)
results = {}


# ══════════════════════════════════════════════════════════════
# EXP-2041: Insulin Distribution Analysis
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2041")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2041: Insulin Distribution Analysis")
print("=" * 70)

exp2041 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))
    net_basal = df['net_basal'].values.astype(float) if 'net_basal' in df.columns else np.zeros(len(glucose))
    temp_rate = df['temp_rate'].values.astype(float) if 'temp_rate' in df.columns else np.zeros(len(glucose))

    n_days = len(glucose) / STEPS_PER_DAY

    # Total insulin per day
    total_bolus = np.nansum(bolus) / n_days
    # Basal: only positive net_basal contributions (temp above zero)
    basal_valid = net_basal[np.isfinite(net_basal)]
    total_basal_per_step = np.nanmean(np.maximum(basal_valid, 0)) if len(basal_valid) > 0 else 0
    total_basal = total_basal_per_step * STEPS_PER_DAY  # per day

    total_daily = total_bolus + total_basal

    # Classify boluses: meal bolus (within 15min of carbs) vs correction
    meal_bolus_total = 0
    correction_bolus_total = 0
    for i in range(len(bolus)):
        if bolus[i] < 0.05:
            continue
        # Check if near carbs
        carb_window = carbs[max(0, i-3):min(len(carbs), i+3)]
        if np.nansum(carb_window) >= 5:
            meal_bolus_total += bolus[i]
        else:
            correction_bolus_total += bolus[i]

    meal_bolus_daily = meal_bolus_total / n_days
    correction_bolus_daily = correction_bolus_total / n_days

    # Micro-bolus detection (SMB): bolus < 0.5U
    smb_count = np.sum(bolus[(bolus > 0.01) & (bolus < 0.5)])
    large_bolus_count = np.sum(bolus[bolus >= 0.5])
    smb_pct = smb_count / (smb_count + large_bolus_count) * 100 if (smb_count + large_bolus_count) > 0 else 0

    # Zero delivery periods
    zero_delivery = np.sum((np.abs(net_basal) < 0.01) & np.isfinite(net_basal))
    zero_pct = zero_delivery / len(net_basal) * 100

    exp2041[name] = {
        'total_daily_insulin': round(total_daily, 1),
        'bolus_daily': round(total_bolus, 1),
        'basal_daily': round(total_basal, 1),
        'bolus_pct': round(total_bolus / total_daily * 100, 1) if total_daily > 0 else 0,
        'meal_bolus_daily': round(meal_bolus_daily, 1),
        'correction_bolus_daily': round(correction_bolus_daily, 1),
        'smb_insulin_pct': round(smb_pct, 1),
        'zero_delivery_pct': round(zero_pct, 1),
    }

    print(f"  {name}: TDI={total_daily:.1f}U/day bolus={total_bolus:.1f}({total_bolus/total_daily*100:.0f}%) "
          f"basal={total_basal:.1f} meal={meal_bolus_daily:.1f} corr={correction_bolus_daily:.1f} "
          f"SMB={smb_pct:.0f}% zero={zero_pct:.0f}%")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    ax = axes[0, 0]
    names_list = list(exp2041.keys())
    basal = [exp2041[n]['basal_daily'] for n in names_list]
    meal = [exp2041[n]['meal_bolus_daily'] for n in names_list]
    corr = [exp2041[n]['correction_bolus_daily'] for n in names_list]
    x = np.arange(len(names_list))
    ax.bar(x, basal, label='Basal', color='steelblue', alpha=0.7)
    ax.bar(x, meal, bottom=basal, label='Meal Bolus', color='green', alpha=0.7)
    bottom2 = [b + m for b, m in zip(basal, meal)]
    ax.bar(x, corr, bottom=bottom2, label='Correction Bolus', color='red', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Insulin (U/day)')
    ax.set_title('Daily Insulin Breakdown')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    ax = axes[0, 1]
    bolus_pct = [exp2041[n]['bolus_pct'] for n in names_list]
    ax.barh(range(len(names_list)), bolus_pct, color='steelblue', alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Bolus % of TDI')
    ax.set_title('Bolus vs Basal Split')
    ax.axvline(50, color='black', ls='--', alpha=0.5, label='50/50')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1, 0]
    smb = [exp2041[n]['smb_insulin_pct'] for n in names_list]
    ax.barh(range(len(names_list)), smb, color='orange', alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('SMB Insulin % (<0.5U boluses)')
    ax.set_title('Micro-Bolus (SMB) Insulin Fraction')
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1, 1]
    zero = [exp2041[n]['zero_delivery_pct'] for n in names_list]
    colors = ['red' if z > 50 else 'orange' if z > 30 else 'green' for z in zero]
    ax.barh(range(len(names_list)), zero, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Zero Delivery (%)')
    ax.set_title('Time at Zero Insulin Delivery')
    ax.grid(True, alpha=0.3, axis='x')

    plt.suptitle('EXP-2041: Insulin Distribution', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/loop-fig01-insulin-dist.png', dpi=150)
    plt.close()
    print(f"  → Saved loop-fig01-insulin-dist.png")

mean_bolus_pct = np.mean([exp2041[n]['bolus_pct'] for n in exp2041])
verdict_2041 = f"BOLUS_{mean_bolus_pct:.0f}%_MEAN"
results['EXP-2041'] = verdict_2041
print(f"\n  ✓ EXP-2041 verdict: {verdict_2041}")


# ══════════════════════════════════════════════════════════════
# EXP-2042: Loop Decision Patterns
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2042")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2042: Loop Decision Patterns")
print("=" * 70)

exp2042 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    net_basal = df['net_basal'].values.astype(float) if 'net_basal' in df.columns else np.zeros(len(glucose))
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))

    # Classify each step by loop decision
    n = len(glucose)
    decisions = {'suspend': 0, 'reduce': 0, 'normal': 0, 'increase': 0, 'bolus': 0}

    for i in range(n):
        if bolus[i] > 0.05:
            decisions['bolus'] += 1
        elif not np.isfinite(net_basal[i]):
            continue
        elif net_basal[i] < 0.01:
            decisions['suspend'] += 1
        elif net_basal[i] < 0.5:  # below typical basal
            decisions['reduce'] += 1
        elif net_basal[i] > 1.5:  # above typical basal
            decisions['increase'] += 1
        else:
            decisions['normal'] += 1

    total = sum(decisions.values())
    pcts = {k: round(v / total * 100, 1) if total > 0 else 0 for k, v in decisions.items()}

    # Glucose context at each decision
    suspend_glucose = []
    increase_glucose = []
    for i in range(n):
        if not np.isfinite(glucose[i]) or not np.isfinite(net_basal[i]):
            continue
        if net_basal[i] < 0.01 and bolus[i] < 0.05:
            suspend_glucose.append(glucose[i])
        elif net_basal[i] > 1.5:
            increase_glucose.append(glucose[i])

    exp2042[name] = {
        'decision_pcts': pcts,
        'suspend_mean_glucose': round(float(np.mean(suspend_glucose)), 0) if suspend_glucose else np.nan,
        'increase_mean_glucose': round(float(np.mean(increase_glucose)), 0) if increase_glucose else np.nan,
    }

    print(f"  {name}: suspend={pcts['suspend']:.0f}% reduce={pcts['reduce']:.0f}% "
          f"normal={pcts['normal']:.0f}% increase={pcts['increase']:.0f}% bolus={pcts['bolus']:.0f}% "
          f"suspend@{exp2042[name]['suspend_mean_glucose']:.0f} increase@{exp2042[name]['increase_mean_glucose']:.0f}")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    names_list = list(exp2042.keys())
    categories = ['suspend', 'reduce', 'normal', 'increase', 'bolus']
    cat_colors = ['red', 'orange', 'gray', 'green', 'blue']
    bottom = np.zeros(len(names_list))
    for cat, color in zip(categories, cat_colors):
        vals = [exp2042[n]['decision_pcts'].get(cat, 0) for n in names_list]
        ax.barh(range(len(names_list)), vals, left=bottom, label=cat, color=color, alpha=0.7)
        bottom += vals
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Percentage')
    ax.set_title('Loop Decision Distribution')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1]
    susp_g = [exp2042[n]['suspend_mean_glucose'] for n in names_list]
    inc_g = [exp2042[n]['increase_mean_glucose'] for n in names_list]
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, susp_g, width, label='Suspend @', color='red', alpha=0.7)
    ax.bar(x + width/2, inc_g, width, label='Increase @', color='green', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Mean Glucose (mg/dL)')
    ax.set_title('Glucose at Loop Decision Points')
    ax.axhline(TARGET_LOW, color='red', ls='--', alpha=0.3)
    ax.axhline(TARGET_HIGH, color='orange', ls='--', alpha=0.3)
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    plt.suptitle('EXP-2042: Loop Decision Patterns', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/loop-fig02-decisions.png', dpi=150)
    plt.close()
    print(f"  → Saved loop-fig02-decisions.png")

mean_suspend = np.mean([exp2042[n]['decision_pcts']['suspend'] for n in exp2042])
verdict_2042 = f"SUSPEND_{mean_suspend:.0f}%_MEAN"
results['EXP-2042'] = verdict_2042
print(f"\n  ✓ EXP-2042 verdict: {verdict_2042}")


# ══════════════════════════════════════════════════════════════
# EXP-2043: Prediction Accuracy by Context
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2043")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2043: Prediction Accuracy by Context")
print("=" * 70)

exp2043 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    predicted_30 = df['predicted_30'].values.astype(float) if 'predicted_30' in df.columns else np.full(len(glucose), np.nan)
    predicted_60 = df['predicted_60'].values.astype(float) if 'predicted_60' in df.columns else np.full(len(glucose), np.nan)
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))

    contexts = {
        'overnight': {'errors_30': [], 'errors_60': []},
        'post_meal': {'errors_30': [], 'errors_60': []},
        'correction': {'errors_30': [], 'errors_60': []},
        'steady': {'errors_30': [], 'errors_60': []},
    }

    for i in range(len(glucose) - 12):
        if not np.isfinite(glucose[i]) or not np.isfinite(predicted_30[i]):
            continue
        actual_30 = glucose[min(i + 6, len(glucose) - 1)]
        if not np.isfinite(actual_30):
            continue
        error_30 = predicted_30[i] - actual_30

        actual_60 = glucose[min(i + 12, len(glucose) - 1)] if i + 12 < len(glucose) else np.nan
        error_60 = (predicted_60[i] - actual_60) if np.isfinite(predicted_60[i]) and np.isfinite(actual_60) else np.nan

        hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
        recent_carbs = np.nansum(carbs[max(0, i-12):i])
        recent_bolus = np.nansum(bolus[max(0, i-6):i])

        if 0 <= hour < 6:
            ctx = 'overnight'
        elif recent_carbs > 5:
            ctx = 'post_meal'
        elif recent_bolus > 0.3 and recent_carbs < 5:
            ctx = 'correction'
        else:
            ctx = 'steady'

        contexts[ctx]['errors_30'].append(error_30)
        if np.isfinite(error_60):
            contexts[ctx]['errors_60'].append(error_60)

    result = {}
    for ctx, data in contexts.items():
        e30 = np.array(data['errors_30'])
        e60 = np.array(data['errors_60'])
        result[ctx] = {
            'n': len(e30),
            'bias_30': round(float(np.mean(e30)), 1) if len(e30) > 0 else np.nan,
            'mae_30': round(float(np.mean(np.abs(e30))), 1) if len(e30) > 0 else np.nan,
            'bias_60': round(float(np.mean(e60)), 1) if len(e60) > 0 else np.nan,
            'mae_60': round(float(np.mean(np.abs(e60))), 1) if len(e60) > 0 else np.nan,
        }

    exp2043[name] = result
    worst_ctx = max(result.items(), key=lambda x: x[1].get('mae_30', 0) if np.isfinite(x[1].get('mae_30', 0)) else 0)
    print(f"  {name}: worst={worst_ctx[0]}(MAE30={worst_ctx[1].get('mae_30', '?')}) "
          f"overnight_bias={result['overnight'].get('bias_30', '?')} "
          f"post_meal_bias={result['post_meal'].get('bias_30', '?')}")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    ctxs = ['overnight', 'post_meal', 'correction', 'steady']
    ctx_colors = ['navy', 'green', 'red', 'gray']
    names_list = list(exp2043.keys())
    x = np.arange(len(names_list))
    width = 0.2
    for ci, (ctx, color) in enumerate(zip(ctxs, ctx_colors)):
        vals = [exp2043[n].get(ctx, {}).get('mae_30', 0) for n in names_list]
        ax.bar(x + (ci - 1.5) * width, vals, width, label=ctx, color=color, alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('MAE 30min (mg/dL)')
    ax.set_title('Prediction Error by Context')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis='y')

    ax = axes[1]
    for ci, (ctx, color) in enumerate(zip(ctxs, ctx_colors)):
        vals = [exp2043[n].get(ctx, {}).get('bias_30', 0) for n in names_list]
        ax.bar(x + (ci - 1.5) * width, vals, width, label=ctx, color=color, alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Bias 30min (mg/dL)')
    ax.set_title('Prediction Bias by Context')
    ax.axhline(0, color='black', ls='--', alpha=0.5)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis='y')

    plt.suptitle('EXP-2043: Prediction Accuracy by Context', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/loop-fig03-prediction.png', dpi=150)
    plt.close()
    print(f"  → Saved loop-fig03-prediction.png")

# Worst context across population
ctx_maes = {}
for ctx in ['overnight', 'post_meal', 'correction', 'steady']:
    maes = [exp2043[n].get(ctx, {}).get('mae_30', 0) for n in exp2043]
    ctx_maes[ctx] = np.mean(maes)
worst = max(ctx_maes.items(), key=lambda x: x[1])
verdict_2043 = f"WORST_CTX={worst[0]}_MAE={worst[1]:.0f}"
results['EXP-2043'] = verdict_2043
print(f"\n  ✓ EXP-2043 verdict: {verdict_2043}")


# ══════════════════════════════════════════════════════════════
# EXP-2044: Overcorrection Detection
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2044")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2044: Overcorrection Detection")
print("=" * 70)

exp2044 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))

    # Find corrections (bolus without carbs, glucose > 150)
    overcorrections = 0
    corrections_total = 0
    overcorr_doses = []

    for i in range(len(glucose) - 36):
        if bolus[i] < 0.3:
            continue
        carb_window = carbs[max(0, i-3):min(len(carbs), i+3)]
        if np.nansum(carb_window) > 3:
            continue
        if not np.isfinite(glucose[i]) or glucose[i] < 150:
            continue

        corrections_total += 1

        # Check if glucose goes below 70 within 4h
        future_g = glucose[i:min(i + 48, len(glucose))]
        valid_future = future_g[np.isfinite(future_g)]
        if len(valid_future) > 0 and np.min(valid_future) < HYPO_THRESH:
            overcorrections += 1
            overcorr_doses.append(bolus[i])

    overcorr_rate = overcorrections / corrections_total * 100 if corrections_total > 0 else 0

    exp2044[name] = {
        'corrections_total': corrections_total,
        'overcorrections': overcorrections,
        'overcorrection_rate': round(overcorr_rate, 1),
        'mean_overcorr_dose': round(float(np.mean(overcorr_doses)), 2) if overcorr_doses else 0,
    }

    print(f"  {name}: corrections={corrections_total} overcorr={overcorrections}({overcorr_rate:.0f}%) "
          f"mean_dose={np.mean(overcorr_doses):.2f}U" if overcorr_doses else
          f"  {name}: corrections={corrections_total} overcorr={overcorrections}({overcorr_rate:.0f}%)")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    names_list = list(exp2044.keys())
    rates = [exp2044[n]['overcorrection_rate'] for n in names_list]
    colors = ['red' if r > 15 else 'orange' if r > 10 else 'green' for r in rates]
    ax.barh(range(len(names_list)), rates, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Overcorrection Rate (%)')
    ax.set_title('Corrections Leading to Hypoglycemia')
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1]
    totals = [exp2044[n]['corrections_total'] for n in names_list]
    overcorrs = [exp2044[n]['overcorrections'] for n in names_list]
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, totals, width, label='Total Corrections', color='steelblue', alpha=0.7)
    ax.bar(x + width/2, overcorrs, width, label='Overcorrections', color='red', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Count')
    ax.set_title('Correction Count vs Overcorrections')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    plt.suptitle('EXP-2044: Overcorrection Detection', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/loop-fig04-overcorrection.png', dpi=150)
    plt.close()
    print(f"  → Saved loop-fig04-overcorrection.png")

mean_rate = np.mean([exp2044[n]['overcorrection_rate'] for n in exp2044])
verdict_2044 = f"OVERCORR_{mean_rate:.0f}%_MEAN"
results['EXP-2044'] = verdict_2044
print(f"\n  ✓ EXP-2044 verdict: {verdict_2044}")


# ══════════════════════════════════════════════════════════════
# EXP-2045: Overnight Control Analysis
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2045")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2045: Overnight Control Analysis")
print("=" * 70)

exp2045 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    n_days = len(glucose) // STEPS_PER_DAY

    overnight_tirs = []
    dawn_rises = []
    overnight_hypos = 0
    overnight_hypers = 0
    total_nights = 0

    for d in range(n_days):
        # Overnight: midnight (0) to 6am (72 steps)
        start = d * STEPS_PER_DAY
        overnight = glucose[start:start + 72]
        valid = overnight[np.isfinite(overnight)]
        if len(valid) < 40:
            continue
        total_nights += 1

        tir = float(np.mean((valid >= TARGET_LOW) & (valid <= TARGET_HIGH)) * 100)
        overnight_tirs.append(tir)

        if np.any(valid < HYPO_THRESH):
            overnight_hypos += 1
        if np.any(valid > TARGET_HIGH):
            overnight_hypers += 1

        # Dawn rise: 4am-7am glucose change
        dawn_start = start + 48  # 4am
        dawn_end = start + 84    # 7am
        if dawn_end < len(glucose):
            dawn_g = glucose[dawn_start:dawn_end]
            valid_dawn = dawn_g[np.isfinite(dawn_g)]
            if len(valid_dawn) >= 12:
                dawn_rise = float(valid_dawn[-1] - valid_dawn[0])
                dawn_rises.append(dawn_rise)

    if total_nights < 10:
        exp2045[name] = {'status': 'insufficient', 'nights': total_nights}
        print(f"  {name}: only {total_nights} valid nights")
        continue

    exp2045[name] = {
        'total_nights': total_nights,
        'overnight_tir': round(float(np.mean(overnight_tirs)), 1),
        'overnight_hypo_pct': round(overnight_hypos / total_nights * 100, 1),
        'overnight_hyper_pct': round(overnight_hypers / total_nights * 100, 1),
        'dawn_rise_mean': round(float(np.mean(dawn_rises)), 1) if dawn_rises else np.nan,
        'dawn_rise_sd': round(float(np.std(dawn_rises)), 1) if dawn_rises else np.nan,
    }

    print(f"  {name}: nights={total_nights} overnight_TIR={np.mean(overnight_tirs):.0f}% "
          f"hypo_nights={overnight_hypos}({overnight_hypos/total_nights*100:.0f}%) "
          f"dawn_rise={np.mean(dawn_rises):.0f}±{np.std(dawn_rises):.0f}mg/dL")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    ax = axes[0, 0]
    names_list = [n for n in exp2045 if 'overnight_tir' in exp2045[n]]
    tirs = [exp2045[n]['overnight_tir'] for n in names_list]
    ax.barh(range(len(names_list)), tirs, color='steelblue', alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Overnight TIR (%)')
    ax.set_title('Overnight Time in Range')
    ax.axvline(70, color='green', ls='--', alpha=0.5, label='70% target')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[0, 1]
    dawn = [exp2045[n].get('dawn_rise_mean', 0) for n in names_list]
    colors = ['red' if d > 20 else 'orange' if d > 10 else 'green' for d in dawn]
    ax.barh(range(len(names_list)), dawn, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Mean Dawn Rise (mg/dL)')
    ax.set_title('Dawn Phenomenon (4–7am)')
    ax.axvline(0, color='black', ls='--', alpha=0.5)
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1, 0]
    hypo_pct = [exp2045[n].get('overnight_hypo_pct', 0) for n in names_list]
    hyper_pct = [exp2045[n].get('overnight_hyper_pct', 0) for n in names_list]
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, hypo_pct, width, label='Hypo Nights', color='red', alpha=0.7)
    ax.bar(x + width/2, hyper_pct, width, label='Hyper Nights', color='orange', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('% of Nights')
    ax.set_title('Nights with Hypo/Hyper Events')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    ax = axes[1, 1]
    dawn_sd = [exp2045[n].get('dawn_rise_sd', 0) for n in names_list]
    ax.scatter(dawn, dawn_sd, s=60, zorder=3)
    for n, dr, ds in zip(names_list, dawn, dawn_sd):
        ax.annotate(n, (dr, ds), fontsize=9)
    ax.set_xlabel('Mean Dawn Rise (mg/dL)')
    ax.set_ylabel('Dawn Rise SD (mg/dL)')
    ax.set_title('Dawn Consistency (low SD = predictable)')
    ax.grid(True, alpha=0.3)

    plt.suptitle('EXP-2045: Overnight Control', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/loop-fig05-overnight.png', dpi=150)
    plt.close()
    print(f"  → Saved loop-fig05-overnight.png")

mean_overnight_tir = np.mean([exp2045[n]['overnight_tir'] for n in exp2045 if 'overnight_tir' in exp2045[n]])
verdict_2045 = f"OVERNIGHT_TIR={mean_overnight_tir:.0f}%"
results['EXP-2045'] = verdict_2045
print(f"\n  ✓ EXP-2045 verdict: {verdict_2045}")


# ══════════════════════════════════════════════════════════════
# EXP-2046: Recovery Time Analysis
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2046")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2046: Recovery Time Analysis")
print("=" * 70)

exp2046 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)

    hypo_recovery_times = []
    hyper_recovery_times = []

    # Hypo recovery: time from glucose < 70 to glucose > 80
    in_hypo = False
    hypo_start = 0
    for i in range(len(glucose)):
        if not np.isfinite(glucose[i]):
            continue
        if not in_hypo and glucose[i] < HYPO_THRESH:
            in_hypo = True
            hypo_start = i
        elif in_hypo and glucose[i] > 80:
            recovery_min = (i - hypo_start) * 5
            if recovery_min < 360:  # cap at 6h
                hypo_recovery_times.append(recovery_min)
            in_hypo = False

    # Hyper recovery: time from glucose > 250 to glucose < 180
    in_hyper = False
    hyper_start = 0
    for i in range(len(glucose)):
        if not np.isfinite(glucose[i]):
            continue
        if not in_hyper and glucose[i] > 250:
            in_hyper = True
            hyper_start = i
        elif in_hyper and glucose[i] < TARGET_HIGH:
            recovery_min = (i - hyper_start) * 5
            if recovery_min < 720:  # cap at 12h
                hyper_recovery_times.append(recovery_min)
            in_hyper = False

    exp2046[name] = {
        'hypo_events': len(hypo_recovery_times),
        'hypo_recovery_median_min': int(np.median(hypo_recovery_times)) if hypo_recovery_times else np.nan,
        'hypo_recovery_p75_min': int(np.percentile(hypo_recovery_times, 75)) if len(hypo_recovery_times) >= 4 else np.nan,
        'hyper_events': len(hyper_recovery_times),
        'hyper_recovery_median_min': int(np.median(hyper_recovery_times)) if hyper_recovery_times else np.nan,
        'hyper_recovery_p75_min': int(np.percentile(hyper_recovery_times, 75)) if len(hyper_recovery_times) >= 4 else np.nan,
    }

    hypo_med = f"{np.median(hypo_recovery_times):.0f}" if hypo_recovery_times else "N/A"
    hyper_med = f"{np.median(hyper_recovery_times):.0f}" if hyper_recovery_times else "N/A"
    print(f"  {name}: hypo_recovery={hypo_med}min(n={len(hypo_recovery_times)}) "
          f"hyper_recovery={hyper_med}min(n={len(hyper_recovery_times)})")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    names_list = list(exp2046.keys())
    hypo_r = [exp2046[n].get('hypo_recovery_median_min', 0) or 0 for n in names_list]
    ax.barh(range(len(names_list)), hypo_r, color='steelblue', alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Median Recovery Time (min)')
    ax.set_title('Hypo Recovery (<70 → >80 mg/dL)')
    ax.axvline(30, color='green', ls='--', alpha=0.5, label='30min target')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[1]
    hyper_r = [exp2046[n].get('hyper_recovery_median_min', 0) or 0 for n in names_list]
    colors = ['red' if r > 120 else 'orange' if r > 60 else 'green' for r in hyper_r]
    ax.barh(range(len(names_list)), hyper_r, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Median Recovery Time (min)')
    ax.set_title('Hyper Recovery (>250 → <180 mg/dL)')
    ax.axvline(120, color='red', ls='--', alpha=0.5, label='2h target')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='x')

    plt.suptitle('EXP-2046: Recovery Time Analysis', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/loop-fig06-recovery.png', dpi=150)
    plt.close()
    print(f"  → Saved loop-fig06-recovery.png")

hypo_times = [exp2046[n].get('hypo_recovery_median_min', 0) for n in exp2046
              if exp2046[n].get('hypo_recovery_median_min') and not np.isnan(exp2046[n].get('hypo_recovery_median_min', np.nan))]
hyper_times = [exp2046[n].get('hyper_recovery_median_min', 0) for n in exp2046
               if exp2046[n].get('hyper_recovery_median_min') and not np.isnan(exp2046[n].get('hyper_recovery_median_min', np.nan))]
verdict_2046 = f"HYPO_REC={np.median(hypo_times):.0f}min_HYPER_REC={np.median(hyper_times):.0f}min"
results['EXP-2046'] = verdict_2046
print(f"\n  ✓ EXP-2046 verdict: {verdict_2046}")


# ══════════════════════════════════════════════════════════════
# EXP-2047: Glycemic Variability Decomposition
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2047")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2047: Glycemic Variability Decomposition")
print("=" * 70)

exp2047 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))

    # Classify each timestep
    total_var = float(np.nanvar(glucose))

    # Post-meal: within 3h of carb entry
    meal_mask = np.zeros(len(glucose), dtype=bool)
    for i in range(len(carbs)):
        if carbs[i] >= 10:
            meal_mask[i:min(i + 36, len(glucose))] = True

    # Post-correction: within 3h of correction bolus
    corr_mask = np.zeros(len(glucose), dtype=bool)
    for i in range(len(bolus)):
        if bolus[i] > 0.3:
            carb_window = carbs[max(0, i-3):min(len(carbs), i+3)]
            if np.nansum(carb_window) < 5:
                corr_mask[i:min(i + 36, len(glucose))] = True

    # Overnight
    overnight_mask = np.zeros(len(glucose), dtype=bool)
    n_days = len(glucose) // STEPS_PER_DAY
    for d in range(n_days):
        start = d * STEPS_PER_DAY
        overnight_mask[start:start + 72] = True  # midnight to 6am

    # Other
    other_mask = ~(meal_mask | corr_mask | overnight_mask)

    # Variance by context
    meal_g = glucose[meal_mask & np.isfinite(glucose)]
    corr_g = glucose[corr_mask & np.isfinite(glucose)]
    overnight_g = glucose[overnight_mask & np.isfinite(glucose)]
    other_g = glucose[other_mask & np.isfinite(glucose)]

    meal_var = float(np.var(meal_g)) if len(meal_g) > 100 else 0
    corr_var = float(np.var(corr_g)) if len(corr_g) > 100 else 0
    overnight_var = float(np.var(overnight_g)) if len(overnight_g) > 100 else 0
    other_var = float(np.var(other_g)) if len(other_g) > 100 else 0

    # Time fractions
    meal_pct = float(np.sum(meal_mask) / len(glucose) * 100)
    corr_pct = float(np.sum(corr_mask) / len(glucose) * 100)
    overnight_pct = float(np.sum(overnight_mask) / len(glucose) * 100)

    exp2047[name] = {
        'total_var': round(total_var, 0),
        'meal_var': round(meal_var, 0),
        'corr_var': round(corr_var, 0),
        'overnight_var': round(overnight_var, 0),
        'other_var': round(other_var, 0),
        'meal_time_pct': round(meal_pct, 1),
        'meal_var_ratio': round(meal_var / total_var, 2) if total_var > 0 else 0,
        'overnight_var_ratio': round(overnight_var / total_var, 2) if total_var > 0 else 0,
    }

    print(f"  {name}: total_var={total_var:.0f} meal={meal_var:.0f}({meal_var/total_var:.0%}) "
          f"overnight={overnight_var:.0f}({overnight_var/total_var:.0%}) "
          f"meal_time={meal_pct:.0f}%")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    names_list = list(exp2047.keys())
    meal_r = [exp2047[n]['meal_var_ratio'] for n in names_list]
    overnight_r = [exp2047[n]['overnight_var_ratio'] for n in names_list]
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, meal_r, width, label='Meal Variance Ratio', color='green', alpha=0.7)
    ax.bar(x + width/2, overnight_r, width, label='Overnight Variance Ratio', color='navy', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Variance / Total Variance')
    ax.set_title('Variance Source Decomposition')
    ax.axhline(1.0, color='gray', ls='--', alpha=0.3)
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    ax = axes[1]
    meal_t = [exp2047[n]['meal_time_pct'] for n in names_list]
    ax.scatter(meal_t, meal_r, s=60, zorder=3)
    for n, mt, mr in zip(names_list, meal_t, meal_r):
        ax.annotate(n, (mt, mr), fontsize=9)
    ax.set_xlabel('Time Spent Post-Meal (%)')
    ax.set_ylabel('Meal Variance / Total Variance')
    ax.set_title('Meal Time vs Meal Variance Contribution')
    ax.grid(True, alpha=0.3)

    plt.suptitle('EXP-2047: Glycemic Variability Decomposition', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/loop-fig07-variability.png', dpi=150)
    plt.close()
    print(f"  → Saved loop-fig07-variability.png")

mean_meal_ratio = np.mean([exp2047[n]['meal_var_ratio'] for n in exp2047])
mean_overnight_ratio = np.mean([exp2047[n]['overnight_var_ratio'] for n in exp2047])
verdict_2047 = f"MEAL_VAR={mean_meal_ratio:.0%}_OVERNIGHT={mean_overnight_ratio:.0%}"
results['EXP-2047'] = verdict_2047
print(f"\n  ✓ EXP-2047 verdict: {verdict_2047}")


# ══════════════════════════════════════════════════════════════
# EXP-2048: Synthesis — AID Optimization Opportunities
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2048")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2048: Synthesis — AID Optimization Opportunities")
print("=" * 70)

exp2048 = {}
for p in patients:
    name = p['name']
    profile = {}

    # Insulin distribution
    if name in exp2041:
        profile['tdi'] = exp2041[name]['total_daily_insulin']
        profile['bolus_pct'] = exp2041[name]['bolus_pct']
        profile['zero_delivery_pct'] = exp2041[name]['zero_delivery_pct']

    # Loop decisions
    if name in exp2042:
        profile['suspend_pct'] = exp2042[name]['decision_pcts'].get('suspend', 0)

    # Prediction accuracy
    if name in exp2043:
        profile['worst_prediction_ctx'] = max(exp2043[name].items(),
            key=lambda x: x[1].get('mae_30', 0) if np.isfinite(x[1].get('mae_30', 0)) else 0)[0]

    # Overcorrection
    if name in exp2044:
        profile['overcorrection_rate'] = exp2044[name]['overcorrection_rate']

    # Overnight
    if name in exp2045 and 'overnight_tir' in exp2045[name]:
        profile['overnight_tir'] = exp2045[name]['overnight_tir']
        profile['dawn_rise'] = exp2045[name].get('dawn_rise_mean', 0)

    # Recovery
    if name in exp2046:
        profile['hypo_recovery_min'] = exp2046[name].get('hypo_recovery_median_min', np.nan)
        profile['hyper_recovery_min'] = exp2046[name].get('hyper_recovery_median_min', np.nan)

    # Variability
    if name in exp2047:
        profile['meal_var_ratio'] = exp2047[name]['meal_var_ratio']

    # Opportunities
    opps = []
    if profile.get('overcorrection_rate', 0) > 15:
        opps.append('REDUCE_CORRECTION_AGGRESSIVENESS')
    if profile.get('overnight_tir', 100) < 60:
        opps.append('OPTIMIZE_OVERNIGHT_BASAL')
    if profile.get('dawn_rise', 0) > 20:
        opps.append('DAWN_BASAL_RAMP')
    if profile.get('hyper_recovery_min', 0) > 120:
        opps.append('IMPROVE_HYPER_CORRECTION')
    if profile.get('suspend_pct', 0) > 60:
        opps.append('REVIEW_BASAL_RATE')
    profile['opportunities'] = opps

    exp2048[name] = profile

    opp_str = ','.join(opps) if opps else 'NONE'
    print(f"  {name}: TDI={profile.get('tdi', '?')} overcorr={profile.get('overcorrection_rate', '?')}% "
          f"overnight_TIR={profile.get('overnight_tir', '?')}% opps={opp_str}")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    ax = axes[0, 0]
    names_list = list(exp2048.keys())
    n_opps = [len(exp2048[n].get('opportunities', [])) for n in names_list]
    colors = ['red' if o >= 3 else 'orange' if o >= 2 else 'yellow' if o >= 1 else 'green' for o in n_opps]
    ax.barh(range(len(names_list)), n_opps, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Number of Optimization Opportunities')
    ax.set_title('AID Optimization Opportunity Count')
    ax.grid(True, alpha=0.3, axis='x')

    ax = axes[0, 1]
    overcorr = [exp2048[n].get('overcorrection_rate', 0) for n in names_list]
    overnight = [exp2048[n].get('overnight_tir', 0) for n in names_list]
    ax.scatter(overcorr, overnight, s=60, zorder=3)
    for n, oc, on in zip(names_list, overcorr, overnight):
        ax.annotate(n, (oc, on), fontsize=9)
    ax.set_xlabel('Overcorrection Rate (%)')
    ax.set_ylabel('Overnight TIR (%)')
    ax.set_title('Overcorrection vs Overnight Control')
    ax.grid(True, alpha=0.3)

    ax = axes[1, 0]
    hypo_r = [exp2048[n].get('hypo_recovery_min', 0) or 0 for n in names_list]
    hyper_r = [exp2048[n].get('hyper_recovery_min', 0) or 0 for n in names_list]
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, hypo_r, width, label='Hypo Recovery', color='steelblue', alpha=0.7)
    ax.bar(x + width/2, hyper_r, width, label='Hyper Recovery', color='coral', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Median Recovery Time (min)')
    ax.set_title('Recovery Times')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    ax = axes[1, 1]
    tdis = [exp2048[n].get('tdi', 0) for n in names_list]
    suspend_pcts = [exp2048[n].get('suspend_pct', 0) for n in names_list]
    ax.scatter(tdis, suspend_pcts, s=60, zorder=3)
    for n, t, s in zip(names_list, tdis, suspend_pcts):
        ax.annotate(n, (t, s), fontsize=9)
    ax.set_xlabel('Total Daily Insulin (U)')
    ax.set_ylabel('Suspend Time (%)')
    ax.set_title('Insulin Need vs Loop Suspension')
    ax.grid(True, alpha=0.3)

    plt.suptitle('EXP-2048: AID Optimization Opportunities', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/loop-fig08-synthesis.png', dpi=150)
    plt.close()
    print(f"  → Saved loop-fig08-synthesis.png")

flagged = sum(1 for v in exp2048.values() if len(v.get('opportunities', [])) > 0)
verdict_2048 = f"FLAGGED_{flagged}/11_PATIENTS"
results['EXP-2048'] = verdict_2048
print(f"\n  ✓ EXP-2048 verdict: {verdict_2048}")


# ══════════════════════════════════════════════════════════════
# SYNTHESIS
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SYNTHESIS: AID Loop Decision Analysis")
print("=" * 70)
for k, v in sorted(results.items()):
    print(f"  {k}: {v}")

output = {
    'experiment_group': 'EXP-2041–2048',
    'title': 'AID Loop Decision Analysis',
    'results': results,
    'exp2041_insulin': exp2041,
    'exp2042_decisions': exp2042,
    'exp2043_prediction': {k: v for k, v in exp2043.items()},
    'exp2044_overcorrection': exp2044,
    'exp2045_overnight': exp2045,
    'exp2046_recovery': exp2046,
    'exp2047_variability': exp2047,
    'exp2048_synthesis': exp2048,
}

with open(f'{EXP_DIR}/exp-2041_loop_decisions.json', 'w') as f:
    json.dump(output, f, indent=2, default=str)
print(f"\nSaved results to {EXP_DIR}/exp-2041_loop_decisions.json")
