#!/usr/bin/env python3
"""
EXP-2061–2068: Glucose Prediction & Forecasting Analysis

How well can we predict glucose using the data available to AID systems?
What features actually matter? Where do predictions fail and why?
Builds on: circadian ISF (EXP-2051), meal response (EXP-2031), loop
decisions (EXP-2041), pharmacokinetics (EXP-2021).

EXP-2061: Baseline prediction accuracy (naive vs loop vs perfect)
EXP-2062: Feature importance for 30/60/120-min prediction
EXP-2063: Context-stratified prediction error (meal, correction, fasting, overnight)
EXP-2064: Prediction horizon analysis (how far ahead can we see?)
EXP-2065: Supply-demand as predictive feature (does physics help?)
EXP-2066: Circadian prediction adjustment (time-of-day correction)
EXP-2067: Patient-specific vs population prediction models
EXP-2068: Synthesis — optimal prediction strategy

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


# ── EXP-2061: Baseline Prediction Accuracy ──────────────────────────
def exp_2061_baseline_prediction():
    """Compare naive, momentum, and loop predictions against actual."""
    print("\n═══ EXP-2061: Baseline Prediction Accuracy ═══")

    results = {}
    horizons = [6, 12, 24]  # 30min, 60min, 120min
    horizon_names = ['30min', '60min', '120min']

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        pred30 = df['predicted_30'].values if 'predicted_30' in df.columns else None
        pred60 = df['predicted_60'].values if 'predicted_60' in df.columns else None

        patient_results = {}
        for hi, (h, hname) in enumerate(zip(horizons, horizon_names)):
            # Naive: glucose stays the same
            naive_errors = []
            # Momentum: linear extrapolation from last 3 readings
            momentum_errors = []
            # Loop prediction (if available)
            loop_errors = []
            # Perfect: mean reversion to 120 mg/dL
            mean_rev_errors = []

            for i in range(3, len(g) - h):
                if np.isnan(g[i]) or np.isnan(g[i + h]):
                    continue
                actual = g[i + h]

                # Naive
                naive_errors.append(abs(g[i] - actual))

                # Momentum (linear extrapolation)
                if not np.isnan(g[i-1]) and not np.isnan(g[i-2]):
                    slope = (g[i] - g[i-2]) / 2  # per-step slope
                    momentum_pred = g[i] + slope * h
                    momentum_errors.append(abs(momentum_pred - actual))

                # Mean reversion
                alpha = min(h / 48, 1.0)  # 4h to fully revert
                mr_pred = g[i] * (1 - alpha) + 120 * alpha
                mean_rev_errors.append(abs(mr_pred - actual))

                # Loop prediction
                if hname == '30min' and pred30 is not None and not np.isnan(pred30[i]):
                    loop_errors.append(abs(pred30[i] - actual))
                elif hname == '60min' and pred60 is not None and not np.isnan(pred60[i]):
                    loop_errors.append(abs(pred60[i] - actual))

            patient_results[hname] = {
                'naive_mae': float(np.mean(naive_errors)) if naive_errors else None,
                'momentum_mae': float(np.mean(momentum_errors)) if momentum_errors else None,
                'mean_rev_mae': float(np.mean(mean_rev_errors)) if mean_rev_errors else None,
                'loop_mae': float(np.mean(loop_errors)) if loop_errors else None,
                'n': len(naive_errors)
            }

        results[name] = patient_results
        r30 = patient_results.get('30min', {})
        naive_v = r30.get('naive_mae') or 0
        mom_v = r30.get('momentum_mae') or 0
        loop_v = r30.get('loop_mae') or 0
        print(f"  {name}: 30min MAE — naive={naive_v:.1f}, "
              f"momentum={mom_v:.1f}, loop={loop_v:.1f}")

    # Population averages
    pop_results = {}
    for hname in horizon_names:
        for method in ['naive_mae', 'momentum_mae', 'mean_rev_mae', 'loop_mae']:
            vals = [r[hname].get(method) for r in results.values()
                    if hname in r and r[hname].get(method) is not None]
            if vals:
                key = f"{hname}_{method}"
                pop_results[key] = float(np.mean(vals))

    print(f"\n  Population 30min: naive={pop_results.get('30min_naive_mae', 0):.1f}, "
          f"momentum={pop_results.get('30min_momentum_mae', 0):.1f}, "
          f"loop={pop_results.get('30min_loop_mae', 0):.1f}")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: method comparison at 30min
        ax = axes[0]
        methods = ['naive_mae', 'momentum_mae', 'loop_mae', 'mean_rev_mae']
        method_labels = ['Naive\n(no change)', 'Momentum\n(linear)', 'Loop\n(AID pred)', 'Mean Rev\n(→120)']
        vals = [pop_results.get(f'30min_{m}', 0) for m in methods]
        colors = ['#7f7f7f', '#ff7f0e', '#2ca02c', '#9467bd']
        bars = ax.bar(method_labels, vals, color=colors, alpha=0.7)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f'{v:.1f}', ha='center', fontsize=10)
        ax.set_ylabel('MAE (mg/dL)')
        ax.set_title('30-min Prediction MAE by Method')
        ax.grid(True, alpha=0.3, axis='y')

        # Right: horizon decay
        ax = axes[1]
        for method, label, color in [
            ('naive_mae', 'Naive', '#7f7f7f'),
            ('momentum_mae', 'Momentum', '#ff7f0e'),
            ('loop_mae', 'Loop', '#2ca02c'),
            ('mean_rev_mae', 'Mean Reversion', '#9467bd')
        ]:
            vals = [pop_results.get(f'{h}_{method}', 0) for h in horizon_names]
            if any(v > 0 for v in vals):
                ax.plot(['30', '60', '120'], vals, 'o-', label=label, color=color, linewidth=2)
        ax.set_xlabel('Horizon (minutes)')
        ax.set_ylabel('MAE (mg/dL)')
        ax.set_title('Prediction Error vs Horizon')
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/pred-fig01-baseline.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved pred-fig01-baseline.png")

    output = {'experiment': 'EXP-2061', 'title': 'Baseline Prediction Accuracy',
              'per_patient': results, 'population': pop_results}
    with open(f'{EXP_DIR}/exp-2061_baseline_prediction.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── EXP-2062: Feature Importance ─────────────────────────────────────
def exp_2062_feature_importance():
    """Which features best predict future glucose?"""
    print("\n═══ EXP-2062: Feature Importance for Glucose Prediction ═══")

    results = {}
    feature_scores = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        iob = df['iob'].values
        cob = df['cob'].values
        carbs = df['carbs'].values
        bolus = df['bolus'].values
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(g))

        # Target: glucose change in 60 min
        horizon = STEPS_PER_HOUR  # 60 min
        target = np.full(len(g), np.nan)
        for i in range(len(g) - horizon):
            if not np.isnan(g[i]) and not np.isnan(g[i + horizon]):
                target[i] = g[i + horizon] - g[i]

        # Features
        features = {}
        # Current glucose
        features['glucose'] = g.copy()
        # Recent trend (15-min slope)
        features['trend_15m'] = np.full(len(g), np.nan)
        for i in range(3, len(g)):
            if not np.isnan(g[i]) and not np.isnan(g[i-3]):
                features['trend_15m'][i] = g[i] - g[i-3]
        # IOB
        features['iob'] = iob.copy()
        # COB
        features['cob'] = cob.copy()
        # Recent carbs (last 30min)
        features['recent_carbs'] = np.full(len(g), np.nan)
        for i in range(6, len(g)):
            features['recent_carbs'][i] = np.nansum(carbs[i-6:i])
        # Recent bolus
        features['recent_bolus'] = np.full(len(g), np.nan)
        for i in range(6, len(g)):
            features['recent_bolus'][i] = np.nansum(bolus[i-6:i])
        # Hour of day (circular)
        hours = np.array([(i % STEPS_PER_DAY) / STEPS_PER_HOUR for i in range(len(g))])
        features['hour_sin'] = np.sin(2 * np.pi * hours / 24)
        features['hour_cos'] = np.cos(2 * np.pi * hours / 24)
        # Net basal
        features['net_basal'] = net_basal.copy()

        # Compute correlation of each feature with target
        patient_scores = {}
        for fname, fvals in features.items():
            valid = ~np.isnan(target) & ~np.isnan(fvals)
            if valid.sum() >= 100:
                r = np.corrcoef(fvals[valid], target[valid])[0, 1]
                patient_scores[fname] = round(float(r), 4)
                if fname not in feature_scores:
                    feature_scores[fname] = []
                feature_scores[fname].append(float(r))

        results[name] = patient_scores
        top3 = sorted(patient_scores.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        top3_str = ", ".join(f"{k}={v:.3f}" for k, v in top3)
        print(f"  {name}: {top3_str}")

    # Population feature importance
    pop_importance = {}
    for fname, scores in feature_scores.items():
        pop_importance[fname] = {
            'mean_r': float(np.mean(scores)),
            'mean_abs_r': float(np.mean(np.abs(scores))),
            'consistency': float(np.mean([1 if s > 0 else 0 for s in scores]))
                          if np.mean(scores) > 0
                          else float(np.mean([1 if s < 0 else 0 for s in scores]))
        }

    print("\n  Population feature importance (|r| with 60min ΔG):")
    sorted_feats = sorted(pop_importance.items(), key=lambda x: x[1]['mean_abs_r'], reverse=True)
    for fname, stats in sorted_feats:
        print(f"    {fname:>15}: |r|={stats['mean_abs_r']:.3f} (r={stats['mean_r']:+.3f})")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: population feature importance
        ax = axes[0]
        fnames = [f for f, _ in sorted_feats]
        abs_rs = [s['mean_abs_r'] for _, s in sorted_feats]
        signs = ['#d62728' if s['mean_r'] < 0 else '#2ca02c' for _, s in sorted_feats]
        ax.barh(fnames, abs_rs, color=signs, alpha=0.7)
        ax.set_xlabel('|Correlation| with 60min ΔGlucose')
        ax.set_title('Feature Importance (red=negative, green=positive)')
        ax.grid(True, alpha=0.3, axis='x')

        # Right: per-patient trend feature
        ax = axes[1]
        pnames = sorted(results.keys())
        trend_rs = [results[n].get('trend_15m', 0) for n in pnames]
        iob_rs = [results[n].get('iob', 0) for n in pnames]
        x = np.arange(len(pnames))
        w = 0.35
        ax.bar(x - w/2, trend_rs, w, label='15min trend', color='#ff7f0e', alpha=0.7)
        ax.bar(x + w/2, iob_rs, w, label='IOB', color='#2ca02c', alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(pnames)
        ax.set_ylabel('Correlation with 60min ΔG')
        ax.set_title('Trend vs IOB Predictive Power by Patient')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        ax.axhline(y=0, color='black', linewidth=0.5)

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/pred-fig02-features.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved pred-fig02-features.png")

    output = {'experiment': 'EXP-2062', 'title': 'Feature Importance',
              'per_patient': results, 'population': pop_importance}
    with open(f'{EXP_DIR}/exp-2062_feature_importance.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── EXP-2063: Context-Stratified Error ───────────────────────────────
def exp_2063_context_error():
    """Prediction error stratified by context: meal, correction, fasting, overnight."""
    print("\n═══ EXP-2063: Context-Stratified Prediction Error ═══")

    results = {}
    context_all = {'post_meal': [], 'post_correction': [], 'fasting': [], 'overnight': []}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        carbs = df['carbs'].values
        bolus = df['bolus'].values

        horizon = STEPS_PER_HOUR  # 60min
        context_errors = {'post_meal': [], 'post_correction': [], 'fasting': [], 'overnight': []}

        for i in range(2 * STEPS_PER_HOUR, len(g) - horizon):
            if np.isnan(g[i]) or np.isnan(g[i + horizon]):
                continue

            # Naive prediction error (baseline)
            error = abs(g[i] - g[i + horizon])

            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR

            # Classify context
            recent_carbs = np.nansum(carbs[max(0, i - 2*STEPS_PER_HOUR):i])
            recent_bolus = np.nansum(bolus[max(0, i - 2*STEPS_PER_HOUR):i])

            if recent_carbs > 5:
                context_errors['post_meal'].append(error)
                context_all['post_meal'].append(error)
            elif recent_bolus > 0.5 and recent_carbs <= 5:
                context_errors['post_correction'].append(error)
                context_all['post_correction'].append(error)
            elif 0 <= hour < 6:
                context_errors['overnight'].append(error)
                context_all['overnight'].append(error)
            else:
                context_errors['fasting'].append(error)
                context_all['fasting'].append(error)

        patient_result = {}
        for ctx, errors in context_errors.items():
            if errors:
                patient_result[ctx] = {
                    'mae': float(np.mean(errors)),
                    'median_ae': float(np.median(errors)),
                    'n': len(errors),
                    'p90': float(np.percentile(errors, 90))
                }

        results[name] = patient_result
        fasting_mae = patient_result.get('fasting', {}).get('mae', 0)
        meal_mae = patient_result.get('post_meal', {}).get('mae', 0)
        ratio = meal_mae / fasting_mae if fasting_mae > 0 else 0
        print(f"  {name}: fasting={fasting_mae:.1f}, meal={meal_mae:.1f}, ratio={ratio:.2f}×")

    # Population
    pop_results = {}
    for ctx, errors in context_all.items():
        if errors:
            pop_results[ctx] = {
                'mae': float(np.mean(errors)),
                'median_ae': float(np.median(errors)),
                'n': len(errors)
            }

    print(f"\n  Population 60min naive MAE by context:")
    for ctx in ['fasting', 'post_correction', 'post_meal', 'overnight']:
        if ctx in pop_results:
            print(f"    {ctx:>16}: {pop_results[ctx]['mae']:.1f} mg/dL (n={pop_results[ctx]['n']})")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: population context comparison
        ax = axes[0]
        contexts = ['fasting', 'overnight', 'post_correction', 'post_meal']
        ctx_labels = ['Fasting', 'Overnight', 'Post-Correction', 'Post-Meal']
        maes = [pop_results.get(c, {}).get('mae', 0) for c in contexts]
        colors = ['#2ca02c', '#1f77b4', '#ff7f0e', '#d62728']
        bars = ax.bar(ctx_labels, maes, color=colors, alpha=0.7)
        for bar, v in zip(bars, maes):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f'{v:.1f}', ha='center', fontsize=10)
        ax.set_ylabel('60min Naive MAE (mg/dL)')
        ax.set_title('Prediction Difficulty by Context')
        ax.grid(True, alpha=0.3, axis='y')

        # Right: per-patient meal/fasting ratio
        ax = axes[1]
        ratios = []
        pnames = []
        for name, pr in sorted(results.items()):
            if 'fasting' in pr and 'post_meal' in pr and pr['fasting']['mae'] > 0:
                ratio = pr['post_meal']['mae'] / pr['fasting']['mae']
                ratios.append(ratio)
                pnames.append(name)
        if ratios:
            colors = ['#d62728' if r > 1.5 else '#ff7f0e' if r > 1.2 else '#2ca02c' for r in ratios]
            ax.barh(pnames, ratios, color=colors, alpha=0.7)
            ax.axvline(x=1, color='black', linestyle='--', alpha=0.5)
            ax.set_xlabel('Post-Meal / Fasting MAE Ratio')
            ax.set_title('Meals Make Prediction Harder (>1)')
            ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/pred-fig03-context.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved pred-fig03-context.png")

    output = {'experiment': 'EXP-2063', 'title': 'Context-Stratified Error',
              'per_patient': results, 'population': pop_results}
    with open(f'{EXP_DIR}/exp-2063_context_error.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── EXP-2064: Prediction Horizon Analysis ───────────────────────────
def exp_2064_horizon_analysis():
    """How does prediction quality decay with horizon?"""
    print("\n═══ EXP-2064: Prediction Horizon Analysis ═══")

    results = {}
    horizons_min = [5, 10, 15, 30, 60, 90, 120, 180, 240]
    horizons_step = [1, 2, 3, 6, 12, 18, 24, 36, 48]

    pop_decay = {h: [] for h in horizons_min}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        patient_decay = {}
        for hmin, hstep in zip(horizons_min, horizons_step):
            errors = []
            for i in range(3, len(g) - hstep):
                if np.isnan(g[i]) or np.isnan(g[i + hstep]):
                    continue
                # Momentum prediction
                if not np.isnan(g[i-1]):
                    slope = g[i] - g[i-1]
                    pred = g[i] + slope * hstep
                    errors.append(abs(pred - g[i + hstep]))

            if errors:
                patient_decay[hmin] = {
                    'mae': float(np.mean(errors)),
                    'median': float(np.median(errors)),
                    'n': len(errors)
                }
                pop_decay[hmin].append(float(np.mean(errors)))

        results[name] = patient_decay
        mae_30 = patient_decay.get(30, {}).get('mae', 0)
        mae_120 = patient_decay.get(120, {}).get('mae', 0)
        ratio = mae_120 / mae_30 if mae_30 > 0 else 0
        print(f"  {name}: 30min={mae_30:.1f}, 120min={mae_120:.1f}, decay={ratio:.1f}×")

    # Population decay curve
    pop_results = {}
    for h in horizons_min:
        if pop_decay[h]:
            pop_results[h] = float(np.mean(pop_decay[h]))

    print(f"\n  Population momentum MAE decay:")
    for h in horizons_min:
        if h in pop_results:
            print(f"    {h:>4}min: {pop_results[h]:.1f} mg/dL")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: population decay curve
        ax = axes[0]
        hs = sorted(pop_results.keys())
        maes = [pop_results[h] for h in hs]
        ax.plot(hs, maes, 'o-', color='steelblue', linewidth=2, markersize=8)
        ax.set_xlabel('Prediction Horizon (minutes)')
        ax.set_ylabel('MAE (mg/dL)')
        ax.set_title('Prediction Error vs Horizon (Momentum Model)')
        ax.axhline(y=20, color='green', linestyle='--', alpha=0.5, label='Clinical threshold')
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Right: per-patient 30min vs 120min
        ax = axes[1]
        pnames = sorted(results.keys())
        mae30 = [results[n].get(30, {}).get('mae', 0) for n in pnames]
        mae120 = [results[n].get(120, {}).get('mae', 0) for n in pnames]
        x = np.arange(len(pnames))
        w = 0.35
        ax.bar(x - w/2, mae30, w, label='30min', color='#2ca02c', alpha=0.7)
        ax.bar(x + w/2, mae120, w, label='120min', color='#d62728', alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(pnames)
        ax.set_ylabel('MAE (mg/dL)')
        ax.set_title('Per-Patient Prediction Error by Horizon')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/pred-fig04-horizon.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved pred-fig04-horizon.png")

    output = {'experiment': 'EXP-2064', 'title': 'Horizon Analysis',
              'per_patient': results, 'population_decay': pop_results}
    with open(f'{EXP_DIR}/exp-2064_horizon_analysis.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── EXP-2065: Supply-Demand as Predictive Feature ───────────────────
def exp_2065_supply_demand_prediction():
    """Does the physics supply-demand model improve prediction?"""
    print("\n═══ EXP-2065: Supply-Demand as Predictive Feature ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        sd = compute_supply_demand(df)
        net = sd['net']

        horizon = STEPS_PER_HOUR  # 60 min

        # Compare: naive vs naive+physics
        naive_errors = []
        physics_errors = []
        physics_only_errors = []

        for i in range(3, len(g) - horizon):
            if np.isnan(g[i]) or np.isnan(g[i + horizon]) or np.isnan(net[i]):
                continue

            actual = g[i + horizon]

            # Naive (no change)
            naive_errors.append(abs(g[i] - actual))

            # Physics: predict based on net flux
            # net = supply - demand, positive means glucose rising
            physics_pred = g[i] + net[i] * horizon
            physics_errors.append(abs(physics_pred - actual))

            # Physics only (net flux predicts change directly)
            actual_change = actual - g[i]
            physics_only_errors.append(abs(net[i] * horizon - actual_change))

        if not naive_errors:
            results[name] = {'n': 0}
            continue

        naive_mae = np.mean(naive_errors)
        physics_mae = np.mean(physics_errors)
        improvement = (naive_mae - physics_mae) / naive_mae * 100

        # Correlation: net flux with actual change
        changes = []
        fluxes = []
        for i in range(3, len(g) - horizon):
            if np.isnan(g[i]) or np.isnan(g[i + horizon]) or np.isnan(net[i]):
                continue
            changes.append(g[i + horizon] - g[i])
            fluxes.append(net[i])
        r = np.corrcoef(fluxes, changes)[0, 1] if len(fluxes) > 100 else float('nan')

        results[name] = {
            'naive_mae': float(naive_mae),
            'physics_mae': float(physics_mae),
            'improvement_pct': round(improvement, 1),
            'flux_change_corr': round(r, 3) if not np.isnan(r) else None,
            'n': len(naive_errors)
        }
        print(f"  {name}: naive={naive_mae:.1f}, physics={physics_mae:.1f}, "
              f"Δ={improvement:+.1f}%, r(flux,ΔG)={r:.3f}")

    # Population
    all_improvements = [r['improvement_pct'] for r in results.values()
                        if r.get('improvement_pct') is not None]
    all_corrs = [r['flux_change_corr'] for r in results.values()
                 if r.get('flux_change_corr') is not None]

    pop = {
        'mean_improvement': float(np.mean(all_improvements)) if all_improvements else None,
        'mean_correlation': float(np.mean(all_corrs)) if all_corrs else None,
        'patients_improved': sum(1 for x in all_improvements if x > 0),
        'total_patients': len(all_improvements)
    }
    print(f"\n  Population: {pop['mean_improvement']:.1f}% improvement, "
          f"r={pop['mean_correlation']:.3f}, "
          f"{pop['patients_improved']}/{pop['total_patients']} improved")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: improvement by patient
        ax = axes[0]
        pnames = sorted([n for n, r in results.items() if r.get('improvement_pct') is not None])
        improvements = [results[n]['improvement_pct'] for n in pnames]
        colors = ['#2ca02c' if i > 0 else '#d62728' for i in improvements]
        ax.barh(pnames, improvements, color=colors, alpha=0.7)
        ax.axvline(x=0, color='black', linewidth=1)
        ax.set_xlabel('Improvement over Naive (%)')
        ax.set_title('Physics Model: Prediction Improvement')
        ax.grid(True, alpha=0.3, axis='x')

        # Right: flux vs actual change scatter (population sample)
        ax = axes[1]
        # Sample from all patients
        all_flux = []
        all_change = []
        for p in patients:
            g = p['df']['glucose'].values
            sd = compute_supply_demand(p['df'])
            net = sd['net']
            for i in range(3, min(len(g), 5000) - STEPS_PER_HOUR):
                if np.isnan(g[i]) or np.isnan(g[i + STEPS_PER_HOUR]) or np.isnan(net[i]):
                    continue
                all_flux.append(net[i] * STEPS_PER_HOUR)
                all_change.append(g[i + STEPS_PER_HOUR] - g[i])
                if len(all_flux) > 5000:
                    break

        if all_flux:
            ax.scatter(all_flux, all_change, alpha=0.05, s=5, color='steelblue')
            ax.plot([-100, 100], [-100, 100], 'r--', alpha=0.5, label='Perfect prediction')
            ax.set_xlabel('Physics Predicted ΔG (mg/dL)')
            ax.set_ylabel('Actual ΔG (mg/dL)')
            ax.set_title('Physics Model: Predicted vs Actual Change')
            ax.set_xlim(-100, 100)
            ax.set_ylim(-100, 100)
            ax.legend()
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/pred-fig05-physics.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved pred-fig05-physics.png")

    output = {'experiment': 'EXP-2065', 'title': 'Supply-Demand Prediction',
              'per_patient': results, 'population': pop}
    with open(f'{EXP_DIR}/exp-2065_supply_demand.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── EXP-2066: Circadian Prediction Adjustment ───────────────────────
def exp_2066_circadian_prediction():
    """Does time-of-day adjustment improve prediction?"""
    print("\n═══ EXP-2066: Circadian Prediction Adjustment ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        horizon = STEPS_PER_HOUR  # 60 min

        # First pass: learn hourly bias
        hourly_bias = {h: [] for h in range(24)}
        for i in range(1, len(g) - horizon):
            if np.isnan(g[i]) or np.isnan(g[i + horizon]) or np.isnan(g[i-1]):
                continue
            slope = g[i] - g[i-1]
            pred = g[i] + slope * horizon
            error = g[i + horizon] - pred  # signed error
            hour = (i % STEPS_PER_DAY) // STEPS_PER_HOUR
            hourly_bias[hour].append(error)

        hourly_correction = {}
        for h in range(24):
            if len(hourly_bias[h]) >= 50:
                hourly_correction[h] = float(np.median(hourly_bias[h]))

        # Second pass: apply correction (using leave-one-out style by splitting days)
        # Simple: use first half to learn, second half to test
        n_steps = len(g)
        split = n_steps // 2

        # Learn from first half
        train_bias = {h: [] for h in range(24)}
        for i in range(1, split - horizon):
            if np.isnan(g[i]) or np.isnan(g[i + horizon]) or np.isnan(g[i-1]):
                continue
            slope = g[i] - g[i-1]
            pred = g[i] + slope * horizon
            error = g[i + horizon] - pred
            hour = (i % STEPS_PER_DAY) // STEPS_PER_HOUR
            train_bias[hour].append(error)

        train_correction = {}
        for h in range(24):
            if len(train_bias[h]) >= 30:
                train_correction[h] = float(np.median(train_bias[h]))

        # Test on second half
        momentum_errors = []
        adjusted_errors = []
        for i in range(max(split, 1), len(g) - horizon):
            if np.isnan(g[i]) or np.isnan(g[i + horizon]) or np.isnan(g[i-1]):
                continue
            slope = g[i] - g[i-1]
            momentum_pred = g[i] + slope * horizon
            momentum_errors.append(abs(momentum_pred - g[i + horizon]))

            hour = (i % STEPS_PER_DAY) // STEPS_PER_HOUR
            correction = train_correction.get(hour, 0)
            adjusted_pred = momentum_pred + correction
            adjusted_errors.append(abs(adjusted_pred - g[i + horizon]))

        if not momentum_errors:
            results[name] = {'n': 0}
            continue

        mom_mae = np.mean(momentum_errors)
        adj_mae = np.mean(adjusted_errors)
        improvement = (mom_mae - adj_mae) / mom_mae * 100

        results[name] = {
            'momentum_mae': float(mom_mae),
            'adjusted_mae': float(adj_mae),
            'improvement_pct': round(improvement, 1),
            'hourly_correction': hourly_correction,
            'n': len(momentum_errors)
        }
        print(f"  {name}: momentum={mom_mae:.1f}, adjusted={adj_mae:.1f}, Δ={improvement:+.1f}%")

    # Population
    all_imp = [r['improvement_pct'] for r in results.values() if r.get('improvement_pct') is not None]
    pop = {
        'mean_improvement': float(np.mean(all_imp)) if all_imp else None,
        'improved_count': sum(1 for x in all_imp if x > 0),
        'total': len(all_imp)
    }
    print(f"\n  Population: {pop['mean_improvement']:.1f}% improvement, "
          f"{pop['improved_count']}/{pop['total']} improved")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: improvement per patient
        ax = axes[0]
        pnames = sorted([n for n, r in results.items() if r.get('improvement_pct') is not None])
        imps = [results[n]['improvement_pct'] for n in pnames]
        colors = ['#2ca02c' if i > 0 else '#d62728' for i in imps]
        ax.barh(pnames, imps, color=colors, alpha=0.7)
        ax.axvline(x=0, color='black', linewidth=1)
        ax.set_xlabel('Improvement over Momentum (%)')
        ax.set_title('Circadian Adjustment: Prediction Improvement')
        ax.grid(True, alpha=0.3, axis='x')

        # Right: hourly correction pattern (population average)
        ax = axes[1]
        all_corrections = {h: [] for h in range(24)}
        for r in results.values():
            hc = r.get('hourly_correction', {})
            for h, v in hc.items():
                all_corrections[int(h)].append(v)

        hours = range(24)
        mean_corr = [np.mean(all_corrections[h]) if all_corrections[h] else 0 for h in hours]
        colors = ['#d62728' if c > 2 else '#2ca02c' if c < -2 else '#7f7f7f' for c in mean_corr]
        ax.bar(hours, mean_corr, color=colors, alpha=0.7)
        ax.axhline(y=0, color='black', linewidth=1)
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('Correction Bias (mg/dL)')
        ax.set_title('Circadian Prediction Bias (Momentum Model)')
        ax.set_xticks(range(0, 24, 3))
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/pred-fig06-circadian.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved pred-fig06-circadian.png")

    output = {'experiment': 'EXP-2066', 'title': 'Circadian Prediction',
              'per_patient': {k: {kk: vv for kk, vv in v.items() if kk != 'hourly_correction'}
                             for k, v in results.items()},
              'population': pop}
    with open(f'{EXP_DIR}/exp-2066_circadian_prediction.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── EXP-2067: Patient-Specific vs Population Models ─────────────────
def exp_2067_personalization():
    """Does patient-specific modeling outperform population models?"""
    print("\n═══ EXP-2067: Patient-Specific vs Population Prediction ═══")

    # Learn population model: average momentum bias by glucose level
    pop_bias_by_level = {}  # glucose_bin -> [biases]
    results = {}

    horizon = STEPS_PER_HOUR

    # First: compute all biases
    all_patient_biases = {}
    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        biases = []
        for i in range(1, len(g) - horizon):
            if np.isnan(g[i]) or np.isnan(g[i + horizon]) or np.isnan(g[i-1]):
                continue
            slope = g[i] - g[i-1]
            pred = g[i] + slope * horizon
            bias = g[i + horizon] - pred

            glucose_bin = int(g[i] // 20) * 20  # 20 mg/dL bins
            if glucose_bin not in pop_bias_by_level:
                pop_bias_by_level[glucose_bin] = []
            pop_bias_by_level[glucose_bin].append(bias)

            biases.append((g[i], bias, glucose_bin))
        all_patient_biases[name] = biases

    # Population correction by glucose level
    pop_correction = {}
    for gbin, biases in pop_bias_by_level.items():
        if len(biases) >= 50:
            pop_correction[gbin] = float(np.median(biases))

    # Now compare: patient-specific vs population correction
    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        biases = all_patient_biases[name]

        if len(biases) < 200:
            results[name] = {'n': len(biases)}
            print(f"  {name}: insufficient data ({len(biases)})")
            continue

        # Split train/test
        split = len(biases) // 2
        train = biases[:split]
        test = biases[split:]

        # Learn patient-specific correction
        patient_correction = {}
        for _, bias, gbin in train:
            if gbin not in patient_correction:
                patient_correction[gbin] = []
            patient_correction[gbin].append(bias)
        for gbin in patient_correction:
            if len(patient_correction[gbin]) >= 5:
                patient_correction[gbin] = float(np.median(patient_correction[gbin]))
            else:
                patient_correction[gbin] = 0.0

        # Test
        naive_errors = []
        pop_errors = []
        personal_errors = []

        for glucose, bias, gbin in test:
            actual_change = bias  # bias = actual - momentum_pred, so actual = pred + bias
            # Reconstruct: momentum error = |bias|
            naive_errors.append(abs(bias))

            # Population correction
            pop_corr = pop_correction.get(gbin, 0)
            pop_errors.append(abs(bias - pop_corr))

            # Patient correction
            pers_corr = patient_correction.get(gbin, 0) if isinstance(patient_correction.get(gbin), float) else 0
            personal_errors.append(abs(bias - pers_corr))

        naive_mae = np.mean(naive_errors)
        pop_mae = np.mean(pop_errors)
        pers_mae = np.mean(personal_errors)

        pop_imp = (naive_mae - pop_mae) / naive_mae * 100
        pers_imp = (naive_mae - pers_mae) / naive_mae * 100
        pers_vs_pop = (pop_mae - pers_mae) / pop_mae * 100

        results[name] = {
            'naive_mae': float(naive_mae),
            'population_mae': float(pop_mae),
            'personal_mae': float(pers_mae),
            'pop_improvement_pct': round(pop_imp, 1),
            'personal_improvement_pct': round(pers_imp, 1),
            'personal_vs_pop_pct': round(pers_vs_pop, 1),
            'n_test': len(test)
        }
        print(f"  {name}: naive={naive_mae:.1f}, pop={pop_mae:.1f} ({pop_imp:+.1f}%), "
              f"personal={pers_mae:.1f} ({pers_imp:+.1f}%), Δ(pers-pop)={pers_vs_pop:+.1f}%")

    # Population summary
    all_pers = [r['personal_vs_pop_pct'] for r in results.values()
                if r.get('personal_vs_pop_pct') is not None]
    pop = {
        'mean_personal_advantage': float(np.mean(all_pers)) if all_pers else None,
        'personal_better_count': sum(1 for x in all_pers if x > 0),
        'total': len(all_pers)
    }
    print(f"\n  Population: personal {pop['mean_personal_advantage']:+.1f}% vs population, "
          f"{pop['personal_better_count']}/{pop['total']} prefer personal")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: three-way comparison
        ax = axes[0]
        pnames = sorted([n for n, r in results.items() if r.get('naive_mae') is not None])
        x = np.arange(len(pnames))
        w = 0.25
        naive = [results[n]['naive_mae'] for n in pnames]
        pop_v = [results[n]['population_mae'] for n in pnames]
        pers_v = [results[n]['personal_mae'] for n in pnames]
        ax.bar(x - w, naive, w, label='Naive', color='#7f7f7f', alpha=0.7)
        ax.bar(x, pop_v, w, label='Population', color='#ff7f0e', alpha=0.7)
        ax.bar(x + w, pers_v, w, label='Personal', color='#2ca02c', alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(pnames)
        ax.set_ylabel('60min MAE (mg/dL)')
        ax.set_title('Naive vs Population vs Personal Model')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')

        # Right: personal advantage
        ax = axes[1]
        advs = [results[n]['personal_vs_pop_pct'] for n in pnames]
        colors = ['#2ca02c' if a > 0 else '#d62728' for a in advs]
        ax.barh(pnames, advs, color=colors, alpha=0.7)
        ax.axvline(x=0, color='black', linewidth=1)
        ax.set_xlabel('Personal Advantage over Population (%)')
        ax.set_title('Personalization Benefit')
        ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/pred-fig07-personalization.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved pred-fig07-personalization.png")

    output = {'experiment': 'EXP-2067', 'title': 'Personalization',
              'per_patient': results, 'population': pop}
    with open(f'{EXP_DIR}/exp-2067_personalization.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── EXP-2068: Synthesis — Optimal Prediction Strategy ────────────────
def exp_2068_synthesis():
    """Combine all prediction findings into optimal strategy."""
    print("\n═══ EXP-2068: Synthesis — Optimal Prediction Strategy ═══")

    results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        iob = df['iob'].values
        cob = df['cob'].values
        carbs = df['carbs'].values

        sd = compute_supply_demand(df)
        net = sd['net']

        horizon = STEPS_PER_HOUR  # 60 min

        # Combined model: momentum + IOB adjustment + circadian + physics
        # Split: first 60% train, last 40% test
        n = len(g)
        train_end = int(n * 0.6)

        # Train: learn corrections
        hourly_bias = {h: [] for h in range(24)}
        iob_scale = []

        for i in range(3, train_end - horizon):
            if np.isnan(g[i]) or np.isnan(g[i + horizon]) or np.isnan(g[i-1]):
                continue
            slope = g[i] - g[i-1]
            mom_pred = g[i] + slope * horizon
            error = g[i + horizon] - mom_pred

            hour = (i % STEPS_PER_DAY) // STEPS_PER_HOUR
            hourly_bias[hour].append(error)

            if not np.isnan(iob[i]) and iob[i] > 0:
                iob_scale.append((iob[i], error))

        # Learn corrections
        hour_corr = {}
        for h in range(24):
            if len(hourly_bias[h]) >= 30:
                hour_corr[h] = float(np.median(hourly_bias[h]))

        # Learn IOB adjustment
        if len(iob_scale) >= 100:
            iob_vals = [x[0] for x in iob_scale]
            err_vals = [x[1] for x in iob_scale]
            iob_coeff = np.polyfit(iob_vals, err_vals, 1)[0]
        else:
            iob_coeff = 0

        # Test
        naive_errors = []
        momentum_errors = []
        combined_errors = []
        physics_errors = []

        for i in range(max(train_end, 3), n - horizon):
            if np.isnan(g[i]) or np.isnan(g[i + horizon]):
                continue

            actual = g[i + horizon]

            # Naive
            naive_errors.append(abs(g[i] - actual))

            if np.isnan(g[i-1]):
                continue

            # Momentum
            slope = g[i] - g[i-1]
            mom_pred = g[i] + slope * horizon
            momentum_errors.append(abs(mom_pred - actual))

            # Combined: momentum + circadian + IOB
            hour = (i % STEPS_PER_DAY) // STEPS_PER_HOUR
            circ_adj = hour_corr.get(hour, 0)
            iob_adj = iob_coeff * iob[i] if not np.isnan(iob[i]) else 0
            combined_pred = mom_pred + circ_adj * 0.5 + iob_adj * 0.3  # damped corrections
            combined_errors.append(abs(combined_pred - actual))

            # Physics
            if not np.isnan(net[i]):
                phys_pred = g[i] + net[i] * horizon
                physics_errors.append(abs(phys_pred - actual))

        if not momentum_errors:
            results[name] = {'n': 0}
            continue

        naive_mae = np.mean(naive_errors)
        mom_mae = np.mean(momentum_errors)
        comb_mae = np.mean(combined_errors)
        phys_mae = np.mean(physics_errors) if physics_errors else None

        best_method = 'combined' if comb_mae <= mom_mae else 'momentum'
        if phys_mae and phys_mae < comb_mae:
            best_method = 'physics'

        results[name] = {
            'naive_mae': float(naive_mae),
            'momentum_mae': float(mom_mae),
            'combined_mae': float(comb_mae),
            'physics_mae': float(phys_mae) if phys_mae else None,
            'best_method': best_method,
            'improvement_pct': round((naive_mae - min(comb_mae, mom_mae)) / naive_mae * 100, 1),
            'n': len(momentum_errors)
        }
        phys_v = phys_mae if phys_mae else 0
        print(f"  {name}: naive={naive_mae:.1f}, mom={mom_mae:.1f}, "
              f"combined={comb_mae:.1f}, physics={phys_v:.1f}, "
              f"best={best_method}")

    # Population
    all_best = [r['best_method'] for r in results.values() if r.get('best_method')]
    all_imp = [r['improvement_pct'] for r in results.values() if r.get('improvement_pct') is not None]

    from collections import Counter
    method_counts = Counter(all_best)

    pop = {
        'method_counts': dict(method_counts),
        'mean_improvement': float(np.mean(all_imp)) if all_imp else None
    }
    print(f"\n  Population: best methods = {dict(method_counts)}")
    print(f"  Mean improvement over naive: {pop['mean_improvement']:.1f}%")

    if MAKE_FIGS:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: method comparison
        ax = axes[0]
        pnames = sorted([n for n, r in results.items() if r.get('naive_mae') is not None])
        x = np.arange(len(pnames))
        w = 0.2
        naive = [results[n]['naive_mae'] for n in pnames]
        mom = [results[n]['momentum_mae'] for n in pnames]
        comb = [results[n]['combined_mae'] for n in pnames]
        phys = [results[n].get('physics_mae', 0) or 0 for n in pnames]

        ax.bar(x - 1.5*w, naive, w, label='Naive', color='#7f7f7f', alpha=0.7)
        ax.bar(x - 0.5*w, mom, w, label='Momentum', color='#ff7f0e', alpha=0.7)
        ax.bar(x + 0.5*w, comb, w, label='Combined', color='#2ca02c', alpha=0.7)
        ax.bar(x + 1.5*w, phys, w, label='Physics', color='#1f77b4', alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(pnames)
        ax.set_ylabel('60min MAE (mg/dL)')
        ax.set_title('All Methods: 60min Prediction MAE')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')

        # Right: best method pie
        ax = axes[1]
        if method_counts:
            labels = list(method_counts.keys())
            sizes = list(method_counts.values())
            colors_pie = {'momentum': '#ff7f0e', 'combined': '#2ca02c',
                         'physics': '#1f77b4', 'naive': '#7f7f7f'}
            c = [colors_pie.get(l, '#7f7f7f') for l in labels]
            wedges, texts, autotexts = ax.pie(sizes, labels=labels, autopct='%1.0f%%',
                                               colors=c, startangle=90)
            for w in wedges:
                w.set_alpha(0.7)
            ax.set_title('Best Prediction Method Distribution')

        plt.tight_layout()
        fig.savefig(f'{FIG_DIR}/pred-fig08-synthesis.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → Saved pred-fig08-synthesis.png")

    output = {'experiment': 'EXP-2068', 'title': 'Optimal Prediction Strategy',
              'per_patient': results, 'population': pop}
    with open(f'{EXP_DIR}/exp-2068_synthesis.json', 'w') as f:
        json.dump(output, f, indent=2)
    return output


# ── Main ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 60)
    print("EXP-2061–2068: Glucose Prediction & Forecasting Analysis")
    print("=" * 60)

    r1 = exp_2061_baseline_prediction()
    r2 = exp_2062_feature_importance()
    r3 = exp_2063_context_error()
    r4 = exp_2064_horizon_analysis()
    r5 = exp_2065_supply_demand_prediction()
    r6 = exp_2066_circadian_prediction()
    r7 = exp_2067_personalization()
    r8 = exp_2068_synthesis()

    print("\n" + "=" * 60)
    passed = sum(1 for r in [r1, r2, r3, r4, r5, r6, r7, r8] if r is not None)
    print(f"Results: {passed}/8 experiments completed")
    if MAKE_FIGS:
        print(f"Figures saved to {FIG_DIR}/pred-fig01–08")
    print("=" * 60)
