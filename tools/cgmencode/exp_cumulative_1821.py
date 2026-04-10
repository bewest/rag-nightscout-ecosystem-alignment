#!/usr/bin/env python3
"""EXP-1821 to EXP-1826: Cumulative Integral Information & Slow State Detection.

Motivated by the finding (EXP-1813) that raw signal MI hits noise floor by 6h,
BUT the user's insight that CUMULATIVE integrals of supply and demand might
preserve low-rank structure at 12-24h+ timescales.

Key idea: integration is a low-pass filter. Even a tiny per-step bias in
supply vs demand becomes a large cumulative drift over hours/days. If glycogen
pool filling and insulin sensitivity operate on different timescales, their
signatures should be more visible in the integrated (cumulative) domain than
in the raw (differential) domain.

  EXP-1821: Cumulative Supply-Demand Balance Information
    - Compute rolling integrals: ∫supply dt, ∫demand dt, and their difference
      (cumulative balance) at windows from 1h to 7 days.
    - Measure MI between cumulative balance and future glucose outcomes
      (mean glucose in next 2h, next 6h, next 24h).
    - Hypothesis: cumulative balance carries MORE information at long
      timescales than raw signals do.

  EXP-1822: Supply vs Demand Integral Divergence
    - Track ∫(supply - demand) dt as a running sum.
    - Decompose its variance at different timescales (wavelet analysis).
    - Compare to raw signal variance decomposition (EXP-1815).
    - Hypothesis: the integral shows a DIFFERENT variance profile with
      more power at long timescales (12-48h).

  EXP-1823: Slow State Feature Engineering
    - Construct explicit slow state features:
      a) Cumulative carb balance (rolling 24h carbs - rolling 24h insulin effect)
      b) Time-above-range integral (∫max(0, glucose-180) dt over 12h, 24h, 48h)
      c) Rolling ISF estimate (correction response measured over 24h windows)
      d) Insulin load integral (∫IOB dt over 12h, 24h)
    - Measure each feature's MI with future glucose at 6h, 12h, 24h horizons.
    - Hypothesis: these carry MORE long-range information than raw channels.

  EXP-1824: Integral Asymmetry Detection
    - Compute ∫supply dt and ∫demand dt separately.
    - At each timescale (1h to 7d), measure:
      a) R² of ∫supply with future glucose
      b) R² of ∫demand with future glucose
      c) Whether one integral is more informative than the other at long scales
    - Tests the user's specific hypothesis: glycogen (supply integral) and
      insulin sensitivity (demand integral) operate on different phases
      detectable as different sources of loss.

  EXP-1825: Cumulative Balance → Metabolic Context Prediction
    - Can cumulative S-D balance predict WHICH metabolic context comes next?
    - Method: at each timestep, use 24h cumulative balance to predict whether
      the next 2h will be fasting, post-meal, hypo, or correction.
    - Tests whether the "glycogen pool state" (approximated by cumulative
      balance) determines what KIND of event is likely.

  EXP-1826: Low-Rank Structure in Long Windows
    - PCA/SVD on sliding window features at 12h, 24h, and 48h scales.
    - How many principal components capture 80% of variance?
    - Do the top components align with supply or demand integrals?
    - Tests whether there IS low-dimensional structure at long timescales
      even though MI is low — MI measures nonlinear dependence, but linear
      PCA might find structure MI misses in high dimensions.

Run: PYTHONPATH=tools python3 tools/cgmencode/exp_cumulative_1821.py --figures
"""

import argparse
import json
import os
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

warnings.filterwarnings('ignore')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288


def load_patients(data_dir='externals/ns-data/patients/'):
    from cgmencode.exp_metabolic_flux import load_patients as _lp
    return _lp(data_dir)


def compute_supply_demand(df):
    from cgmencode.exp_metabolic_441 import compute_supply_demand as _csd
    return _csd(df)


def safe_corr(x, y):
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 10:
        return np.nan
    return float(np.corrcoef(x[mask], y[mask])[0, 1])


def safe_mi_binned(x, y, bins=20):
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 50:
        return np.nan
    xv, yv = x[mask], y[mask]
    xd = np.digitize(xv, np.linspace(np.percentile(xv, 1), np.percentile(xv, 99), bins))
    yd = np.digitize(yv, np.linspace(np.percentile(yv, 1), np.percentile(yv, 99), bins))
    joint = np.zeros((bins + 1, bins + 1))
    for xi, yi in zip(xd, yd):
        joint[xi, yi] += 1
    joint /= joint.sum()
    px = joint.sum(axis=1)
    py = joint.sum(axis=0)
    mi = 0.0
    for i in range(bins + 1):
        for j in range(bins + 1):
            if joint[i, j] > 0 and px[i] > 0 and py[j] > 0:
                mi += joint[i, j] * np.log2(joint[i, j] / (px[i] * py[j]))
    return float(mi)


def rolling_sum(arr, window):
    """Efficient rolling sum using cumsum."""
    cs = np.nancumsum(arr)
    result = np.full(len(arr), np.nan)
    result[window:] = cs[window:] - cs[:-window]
    return result


def classify_metabolic_context(df, sd):
    """Classify each timestep into metabolic context."""
    n = len(df)
    ctx = np.full(n, 'other', dtype=object)
    glucose = df['glucose'].values.astype(np.float64)
    carbs = df['carbs'].values.astype(np.float64) if 'carbs' in df.columns else np.zeros(n)
    iob = df['iob'].values.astype(np.float64) if 'iob' in df.columns else np.zeros(n)

    meal_mask = np.zeros(n, dtype=bool)
    carb_indices = np.where(carbs > 1)[0]
    for ci in carb_indices:
        meal_mask[ci:min(ci + 36, n)] = True

    fasting_mask = np.zeros(n, dtype=bool)
    for i in range(48, n):
        if not np.any(carbs[max(0, i - 48):i] > 1):
            fasting_mask[i] = True

    iob_75 = np.nanpercentile(iob, 75)
    correction_mask = (iob > iob_75) & (glucose > 180) & ~meal_mask

    hypo_mask = np.zeros(n, dtype=bool)
    hypo_indices = np.where(glucose < 70)[0]
    for hi in hypo_indices:
        hypo_mask[hi:min(hi + 6, n)] = True

    ctx[meal_mask] = 'post_meal'
    ctx[correction_mask & ~meal_mask] = 'correction'
    ctx[hypo_mask & ~meal_mask & ~correction_mask] = 'hypo_recovery'
    ctx[fasting_mask & ~meal_mask & ~correction_mask & ~hypo_mask] = 'fasting'
    return ctx


# ============================================================================
# EXP-1821: Cumulative Supply-Demand Balance Information
# ============================================================================
def exp_1821(patients, figures_dir=None):
    """Does cumulative S-D balance carry more long-range information than raw signals?"""
    print("\n" + "=" * 70)
    print("EXP-1821: Cumulative Supply-Demand Balance Information")
    print("=" * 70)

    # Integration windows
    int_windows = [12, 36, 72, 144, 288, 576, 864, 2016]  # 1h to 7d
    int_labels = [f'{w*5/60:.0f}h' if w < 288 else f'{w/288:.0f}d' for w in int_windows]

    # Prediction horizons
    pred_horizons = [24, 72, 288]  # 2h, 6h, 24h
    pred_labels = ['2h', '6h', '24h']

    # MI[int_window][pred_horizon] = list of per-patient values
    mi_balance = {w: {h: [] for h in pred_horizons} for w in int_windows}
    mi_raw_glucose = {w: {h: [] for h in pred_horizons} for w in int_windows}  # comparison

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values.astype(np.float64)
        sd = compute_supply_demand(df)
        supply = sd['supply']
        demand = sd['demand']
        balance = supply - demand  # instantaneous S-D

        for int_w in int_windows:
            # Cumulative balance over window
            cum_bal = rolling_sum(balance, int_w)
            # Raw glucose mean over same window (comparison)
            cum_gluc = rolling_sum(glucose, int_w) / int_w

            for pred_h in pred_horizons:
                # Future mean glucose as target
                future_gluc = np.full(len(glucose), np.nan)
                for i in range(len(glucose) - pred_h):
                    future_gluc[i] = np.nanmean(glucose[i:i + pred_h])

                # MI: cumulative balance → future glucose
                mi_b = safe_mi_binned(cum_bal, future_gluc)
                mi_g = safe_mi_binned(cum_gluc, future_gluc)

                mi_balance[int_w][pred_h].append(mi_b)
                mi_raw_glucose[int_w][pred_h].append(mi_g)

        print(f"  {name}: computed cumulative MI at {len(int_windows)} windows × {len(pred_horizons)} horizons")

    # Summarize: key comparison at 24h prediction horizon
    print(f"\n  MI (bits) predicting mean glucose in next 24h:")
    print(f"  {'Window':>8s}  {'Cum Balance':>12s}  {'Raw Glucose':>12s}  {'Δ (Bal-Raw)':>12s}")

    summary = {}
    for w, label in zip(int_windows, int_labels):
        bal = np.nanmean(mi_balance[w][288])
        raw = np.nanmean(mi_raw_glucose[w][288])
        delta = bal - raw
        summary[label] = {'balance': float(bal), 'raw': float(raw), 'delta': float(delta)}
        print(f"  {label:>8s}  {bal:>12.4f}  {raw:>12.4f}  {delta:>+12.4f}"
              f"  {'✓ BAL WINS' if delta > 0.005 else ''}")

    # Find best integration window for balance
    best_w = max(summary.items(), key=lambda x: x[1]['balance'])
    print(f"\n  Best integration window for cumulative balance: {best_w[0]} "
          f"(MI={best_w[1]['balance']:.4f} bits)")

    # Check if balance info increases with longer windows (unlike raw)
    balance_trend = [summary[l]['balance'] for l in int_labels]
    raw_trend = [summary[l]['raw'] for l in int_labels]

    results = {
        'summary_24h_horizon': summary,
        'balance_increases_with_window': bool(balance_trend[-1] > balance_trend[0]),
        'raw_increases_with_window': bool(raw_trend[-1] > raw_trend[0]),
        'best_window': best_w[0],
        'full_mi': {
            label: {
                pl: {
                    'balance': float(np.nanmean(mi_balance[w][ph])),
                    'raw': float(np.nanmean(mi_raw_glucose[w][ph]))
                }
                for ph, pl in zip(pred_horizons, pred_labels)
            }
            for w, label in zip(int_windows, int_labels)
        },
        'verdict': ('CUMULATIVE_WINS' if best_w[1]['delta'] > 0.005
                    else 'RAW_SUFFICIENT')
    }

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(18, 5))

        for ax_idx, (ph, pl) in enumerate(zip(pred_horizons, pred_labels)):
            ax = axes[ax_idx]
            bal_vals = [np.nanmean(mi_balance[w][ph]) for w in int_windows]
            raw_vals = [np.nanmean(mi_raw_glucose[w][ph]) for w in int_windows]

            ax.plot(range(len(int_labels)), bal_vals, 'r-o', linewidth=2, markersize=6,
                    label='Cumulative S-D Balance')
            ax.plot(range(len(int_labels)), raw_vals, 'b-s', linewidth=2, markersize=6,
                    label='Raw Glucose Mean')
            ax.set_xticks(range(len(int_labels)))
            ax.set_xticklabels(int_labels, rotation=45)
            ax.set_xlabel('Integration Window')
            ax.set_ylabel('MI with Future Glucose (bits)')
            ax.set_title(f'Predicting Next {pl} Mean Glucose')
            ax.legend(fontsize=8)
            ax.grid(True, alpha=0.3)

        fig.suptitle('EXP-1821: Does Cumulative Balance Carry Long-Range Info?',
                      fontsize=14, fontweight='bold')
        fig.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'cumulative-fig01-balance-mi.png'), dpi=150)
        plt.close(fig)
        print(f"  → Saved cumulative-fig01-balance-mi.png")

    return results


# ============================================================================
# EXP-1822: Supply vs Demand Integral Divergence
# ============================================================================
def exp_1822(patients, figures_dir=None):
    """Wavelet variance of cumulative integrals vs raw signals."""
    print("\n" + "=" * 70)
    print("EXP-1822: Supply vs Demand Integral Divergence")
    print("=" * 70)

    from scipy import signal as sig

    scales = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]
    scale_hours = [s * 5 / 60 for s in scales]
    scale_labels = [f'{h:.1f}h' if h < 24 else f'{h/24:.0f}d' for h in scale_hours]

    # Variance at each scale for: raw glucose, cumulative supply, cumulative demand, cumulative balance
    var_raw = {s: [] for s in scales}
    var_cum_supply = {s: [] for s in scales}
    var_cum_demand = {s: [] for s in scales}
    var_cum_balance = {s: [] for s in scales}

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values.astype(np.float64)
        sd_data = compute_supply_demand(df)
        supply = sd_data['supply']
        demand = sd_data['demand']

        # Cumulative integrals (running sum)
        cum_supply = np.nancumsum(np.nan_to_num(supply))
        cum_demand = np.nancumsum(np.nan_to_num(demand))
        cum_balance = cum_supply - cum_demand

        signals = {
            'raw': glucose,
            'cum_supply': cum_supply,
            'cum_demand': cum_demand,
            'cum_balance': cum_balance
        }

        for scale in scales:
            n = len(glucose) - len(glucose) % (2 * scale)
            if n < 4 * scale:
                continue

            for sig_name, sig_data in signals.items():
                blocks = sig_data[:n].reshape(-1, 2 * scale)
                coeffs = np.nanmean(blocks[:, scale:], axis=1) - np.nanmean(blocks[:, :scale], axis=1)
                valid_coeffs = coeffs[np.isfinite(coeffs)]
                if len(valid_coeffs) < 5:
                    continue
                v = float(np.var(valid_coeffs))

                if sig_name == 'raw':
                    var_raw[scale].append(v)
                elif sig_name == 'cum_supply':
                    var_cum_supply[scale].append(v)
                elif sig_name == 'cum_demand':
                    var_cum_demand[scale].append(v)
                elif sig_name == 'cum_balance':
                    var_cum_balance[scale].append(v)

        print(f"  {name}: wavelet variance computed")

    # Normalize to see relative scaling
    print(f"\n  Wavelet variance by timescale (normalized to 1h scale):")
    print(f"  {'Scale':>8s}  {'Raw Gluc':>10s}  {'∫Supply':>10s}  {'∫Demand':>10s}  {'∫Balance':>10s}")

    ref_scale = scales[0]  # smallest scale as reference
    def norm(d, scale, ref):
        v = np.nanmean(d[scale]) if d.get(scale) else np.nan
        r = np.nanmean(d[ref]) if d.get(ref) else 1.0
        return v / r if r > 0 else np.nan

    scaling_exponents = {'raw': [], 'cum_supply': [], 'cum_demand': [], 'cum_balance': []}

    for scale, label in zip(scales, scale_labels):
        nr = norm(var_raw, scale, ref_scale)
        ns = norm(var_cum_supply, scale, ref_scale)
        nd = norm(var_cum_demand, scale, ref_scale)
        nb = norm(var_cum_balance, scale, ref_scale)
        print(f"  {label:>8s}  {nr:>10.3f}  {ns:>10.3f}  {nd:>10.3f}  {nb:>10.3f}")

    # Compute scaling exponents (how does variance grow with scale?)
    for sig_name, var_dict in [('raw', var_raw), ('cum_supply', var_cum_supply),
                                ('cum_demand', var_cum_demand), ('cum_balance', var_cum_balance)]:
        log_scales = []
        log_vars = []
        for s in scales:
            v = np.nanmean(var_dict[s]) if var_dict[s] else np.nan
            if not np.isnan(v) and v > 0:
                log_scales.append(np.log2(s))
                log_vars.append(np.log2(v))
        if len(log_scales) > 3:
            slope = np.polyfit(log_scales, log_vars, 1)[0]
            scaling_exponents[sig_name] = float(slope)
            print(f"\n  Scaling exponent (H) for {sig_name}: {slope:.3f}")
            # H=0.5 = random walk, H>0.5 = persistent, H<0.5 = anti-persistent

    results = {
        'scaling_exponents': scaling_exponents,
        'interpretation': {
            'raw': 'anti-persistent' if scaling_exponents.get('raw', 0.5) < 0.4 else 'persistent',
            'cum_balance': 'persistent' if scaling_exponents.get('cum_balance', 0.5) > 0.6 else 'anti-persistent'
        },
        'verdict': ('INTEGRAL_REVEALS_MORE' if scaling_exponents.get('cum_balance', 0) > scaling_exponents.get('raw', 0) + 0.3
                    else 'SIMILAR_SCALING')
    }

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: Log-log variance scaling
        ax = axes[0]
        for sig_name, var_dict, color, ls in [
            ('Raw Glucose', var_raw, '#2c3e50', '-'),
            ('∫Supply dt', var_cum_supply, '#e74c3c', '--'),
            ('∫Demand dt', var_cum_demand, '#3498db', '--'),
            ('∫(S−D) dt', var_cum_balance, '#27ae60', '-')
        ]:
            vals = [np.nanmean(var_dict[s]) if var_dict[s] else np.nan for s in scales]
            valid = [(sh, v) for sh, v in zip(scale_hours, vals) if not np.isnan(v) and v > 0]
            if valid:
                ax.loglog([v[0] for v in valid], [v[1] for v in valid],
                          'o-', color=color, linestyle=ls, linewidth=2, markersize=5,
                          label=sig_name)

        ax.set_xlabel('Timescale (hours)')
        ax.set_ylabel('Wavelet Variance')
        ax.set_title('Variance Scaling: Raw vs Cumulative Integrals')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        # Right: Scaling exponents comparison
        ax = axes[1]
        names = list(scaling_exponents.keys())
        exps = [scaling_exponents[n] if isinstance(scaling_exponents[n], float) else 0 for n in names]
        nice_names = ['Raw\nGlucose', '∫Supply', '∫Demand', '∫(S−D)\nBalance']
        colors = ['#2c3e50', '#e74c3c', '#3498db', '#27ae60']
        bars = ax.bar(range(len(names)), exps, color=colors, alpha=0.7, edgecolor='black')
        ax.axhline(0.5, color='gray', linestyle='--', alpha=0.5, label='Random walk (H=0.5)')
        ax.axhline(1.0, color='gray', linestyle=':', alpha=0.3, label='Brownian motion (H=1.0)')
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(nice_names)
        ax.set_ylabel('Scaling Exponent (Hurst-like)')
        ax.set_title('How Does Variance Grow with Timescale?')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')

        fig.suptitle('EXP-1822: Do Integrals Reveal Long-Range Structure?',
                      fontsize=14, fontweight='bold')
        fig.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'cumulative-fig02-integral-scaling.png'), dpi=150)
        plt.close(fig)
        print(f"  → Saved cumulative-fig02-integral-scaling.png")

    return results


# ============================================================================
# EXP-1823: Slow State Feature Engineering
# ============================================================================
def exp_1823(patients, figures_dir=None):
    """Construct explicit slow state features and measure their long-range MI."""
    print("\n" + "=" * 70)
    print("EXP-1823: Slow State Feature Engineering")
    print("=" * 70)

    # Prediction horizons
    horizons = [72, 144, 288]  # 6h, 12h, 24h
    h_labels = ['6h', '12h', '24h']

    # Feature definitions
    feature_names = [
        'cum_carb_balance_24h',     # ∫carbs - ∫insulin_effect over 24h
        'time_above_range_12h',     # ∫max(0, glucose-180) over 12h
        'time_above_range_24h',     # ∫max(0, glucose-180) over 24h
        'time_below_range_12h',     # ∫max(0, 70-glucose) over 12h
        'insulin_load_12h',         # ∫IOB over 12h
        'insulin_load_24h',         # ∫IOB over 24h
        'glucose_volatility_12h',   # rolling std of glucose over 12h
        'supply_integral_24h',      # ∫supply over 24h
        'demand_integral_24h',      # ∫demand over 24h
        'balance_integral_24h',     # ∫(supply-demand) over 24h
        'raw_glucose',              # current glucose (comparison)
        'raw_iob',                  # current IOB (comparison)
    ]

    mi_results = {f: {h: [] for h in h_labels} for f in feature_names}

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values.astype(np.float64)
        carbs = df['carbs'].values.astype(np.float64) if 'carbs' in df.columns else np.zeros(len(df))
        iob = df['iob'].values.astype(np.float64) if 'iob' in df.columns else np.zeros(len(df))
        bolus = df['bolus'].values.astype(np.float64) if 'bolus' in df.columns else np.zeros(len(df))

        sd = compute_supply_demand(df)
        supply = sd['supply']
        demand = sd['demand']

        n = len(glucose)

        # Construct features
        features = {}
        features['cum_carb_balance_24h'] = rolling_sum(carbs, 288) - rolling_sum(bolus * 10, 288)  # crude: 1U ≈ 10g effect
        features['time_above_range_12h'] = rolling_sum(np.maximum(0, glucose - 180), 144)
        features['time_above_range_24h'] = rolling_sum(np.maximum(0, glucose - 180), 288)
        features['time_below_range_12h'] = rolling_sum(np.maximum(0, 70 - glucose), 144)
        features['insulin_load_12h'] = rolling_sum(iob, 144)
        features['insulin_load_24h'] = rolling_sum(iob, 288)
        features['glucose_volatility_12h'] = np.array([np.nanstd(glucose[max(0,i-144):i]) if i >= 144 else np.nan for i in range(n)])
        features['supply_integral_24h'] = rolling_sum(supply, 288)
        features['demand_integral_24h'] = rolling_sum(demand, 288)
        features['balance_integral_24h'] = rolling_sum(supply - demand, 288)
        features['raw_glucose'] = glucose
        features['raw_iob'] = iob

        # Compute future mean glucose targets
        for h_steps, h_label in zip(horizons, h_labels):
            future = np.full(n, np.nan)
            for i in range(n - h_steps):
                future[i] = np.nanmean(glucose[i:i + h_steps])

            for fname in feature_names:
                mi = safe_mi_binned(features[fname], future)
                mi_results[fname][h_label].append(mi)

        print(f"  {name}: {len(feature_names)} features × {len(horizons)} horizons")

    # Summary table
    print(f"\n  MI (bits) with future mean glucose:")
    print(f"  {'Feature':>30s}  {'6h':>8s}  {'12h':>8s}  {'24h':>8s}  {'24h rank':>8s}")

    rank_24h = {}
    for fname in feature_names:
        vals = [np.nanmean(mi_results[fname][h]) for h in h_labels]
        rank_24h[fname] = vals[-1]
        print(f"  {fname:>30s}  {vals[0]:>8.4f}  {vals[1]:>8.4f}  {vals[2]:>8.4f}")

    # Rank features by 24h MI
    ranked = sorted(rank_24h.items(), key=lambda x: -x[1])
    print(f"\n  Features ranked by 24h predictive power:")
    for i, (fname, mi) in enumerate(ranked):
        marker = '★' if fname not in ['raw_glucose', 'raw_iob'] and mi > rank_24h['raw_glucose'] else ''
        print(f"    {i+1:2d}. {fname:>30s}: {mi:.4f} {marker}")

    # Key metric: do slow features beat raw at long horizons?
    best_slow = max(mi for f, mi in rank_24h.items() if 'raw' not in f)
    best_raw = max(rank_24h['raw_glucose'], rank_24h['raw_iob'])

    print(f"\n  Best slow feature (24h): {best_slow:.4f}")
    print(f"  Best raw feature (24h): {best_raw:.4f}")
    print(f"  Slow > Raw: {'YES ✓' if best_slow > best_raw else 'NO'}")

    results = {
        'mi_table': {fname: {h: float(np.nanmean(mi_results[fname][h])) for h in h_labels}
                     for fname in feature_names},
        'ranking_24h': [(f, float(m)) for f, m in ranked],
        'slow_beats_raw': bool(best_slow > best_raw),
        'best_slow_feature': ranked[0][0] if 'raw' not in ranked[0][0] else ranked[1][0],
        'verdict': 'SLOW_FEATURES_WIN' if best_slow > best_raw * 1.05 else 'RAW_COMPETITIVE'
    }

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(16, 6))

        # Left: MI by horizon for top features
        ax = axes[0]
        top_features = [f for f, _ in ranked[:6]]
        colors = ['#e74c3c', '#3498db', '#27ae60', '#f39c12', '#9b59b6', '#2c3e50']
        for i, fname in enumerate(top_features):
            vals = [np.nanmean(mi_results[fname][h]) for h in h_labels]
            style = '--' if 'raw' in fname else '-'
            ax.plot(h_labels, vals, f'{style}o', color=colors[i], linewidth=2,
                    markersize=6, label=fname.replace('_', ' '))
        ax.set_xlabel('Prediction Horizon')
        ax.set_ylabel('MI with Future Mean Glucose (bits)')
        ax.set_title('Slow State Features vs Raw Signals')
        ax.legend(fontsize=7, loc='best')
        ax.grid(True, alpha=0.3)

        # Right: Feature ranking at 24h
        ax = axes[1]
        fnames = [f.replace('_', '\n') for f, _ in ranked]
        mi_vals = [m for _, m in ranked]
        bar_colors = ['#e74c3c' if 'raw' in f else '#3498db' for f, _ in ranked]
        ax.barh(range(len(ranked)), mi_vals, color=bar_colors, alpha=0.7, edgecolor='black')
        ax.set_yticks(range(len(ranked)))
        ax.set_yticklabels(fnames, fontsize=7)
        ax.set_xlabel('MI at 24h Horizon (bits)')
        ax.set_title('Feature Ranking: Who Predicts Best at 24h?')
        ax.grid(True, alpha=0.3, axis='x')
        # Legend
        from matplotlib.patches import Patch
        ax.legend([Patch(color='#e74c3c', alpha=0.7), Patch(color='#3498db', alpha=0.7)],
                  ['Raw (point) features', 'Slow (cumulative) features'], fontsize=8)

        fig.suptitle('EXP-1823: Slow State Feature Engineering',
                      fontsize=14, fontweight='bold')
        fig.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'cumulative-fig03-slow-features.png'), dpi=150)
        plt.close(fig)
        print(f"  → Saved cumulative-fig03-slow-features.png")

    return results


# ============================================================================
# EXP-1824: Integral Asymmetry Detection
# ============================================================================
def exp_1824(patients, figures_dir=None):
    """Do ∫supply and ∫demand predict future glucose at different timescales?"""
    print("\n" + "=" * 70)
    print("EXP-1824: Integral Asymmetry — Supply vs Demand at Long Horizons")
    print("=" * 70)

    int_windows = [12, 36, 72, 144, 288, 576, 864]
    int_labels = [f'{w*5/60:.0f}h' if w < 288 else f'{w/288:.0f}d' for w in int_windows]

    # For each integration window, predict mean glucose in next 24h
    pred_horizon = 288  # 24h

    r2_supply = {w: [] for w in int_windows}
    r2_demand = {w: [] for w in int_windows}
    r2_balance = {w: [] for w in int_windows}
    r2_raw = {w: [] for w in int_windows}

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values.astype(np.float64)
        sd = compute_supply_demand(df)
        supply = sd['supply']
        demand = sd['demand']

        # Future target
        n = len(glucose)
        future = np.full(n, np.nan)
        for i in range(n - pred_horizon):
            future[i] = np.nanmean(glucose[i:i + pred_horizon])

        for int_w in int_windows:
            cum_s = rolling_sum(supply, int_w)
            cum_d = rolling_sum(demand, int_w)
            cum_b = cum_s - cum_d  # rolling_sum is already separate
            # Actually compute the balance integral
            cum_b = rolling_sum(supply - demand, int_w)
            cum_g = rolling_sum(glucose, int_w) / int_w  # mean glucose

            valid = np.isfinite(cum_s) & np.isfinite(cum_d) & np.isfinite(future)
            if valid.sum() < 100:
                continue

            # Simple linear R²
            def linear_r2(x, y, mask):
                xv, yv = x[mask], y[mask]
                if len(xv) < 50:
                    return np.nan
                r = safe_corr(xv, yv)
                return r ** 2 if not np.isnan(r) else np.nan

            r2_supply[int_w].append(linear_r2(cum_s, future, valid))
            r2_demand[int_w].append(linear_r2(cum_d, future, valid))
            r2_balance[int_w].append(linear_r2(cum_b, future, valid))
            r2_raw[int_w].append(linear_r2(cum_g, future, valid))

        print(f"  {name}: integral R² computed")

    # Summary
    print(f"\n  R² predicting next-24h mean glucose:")
    print(f"  {'Window':>8s}  {'∫Supply':>10s}  {'∫Demand':>10s}  {'∫Balance':>10s}  {'Raw Mean':>10s}  {'Winner':>10s}")

    supply_wins = 0
    demand_wins = 0
    for w, label in zip(int_windows, int_labels):
        rs = np.nanmean(r2_supply[w]) if r2_supply[w] else np.nan
        rd = np.nanmean(r2_demand[w]) if r2_demand[w] else np.nan
        rb = np.nanmean(r2_balance[w]) if r2_balance[w] else np.nan
        rr = np.nanmean(r2_raw[w]) if r2_raw[w] else np.nan

        best = max([(rs, '∫Supply'), (rd, '∫Demand'), (rb, '∫Balance'), (rr, 'Raw')],
                   key=lambda x: x[0] if not np.isnan(x[0]) else -1)
        if '∫Supply' in best[1]:
            supply_wins += 1
        elif '∫Demand' in best[1]:
            demand_wins += 1

        print(f"  {label:>8s}  {rs:>10.4f}  {rd:>10.4f}  {rb:>10.4f}  {rr:>10.4f}  {best[1]:>10s}")

    # Key finding: does supply or demand integral diverge at long scales?
    long_supply = np.nanmean(r2_supply[864]) if r2_supply[864] else np.nan
    long_demand = np.nanmean(r2_demand[864]) if r2_demand[864] else np.nan
    short_supply = np.nanmean(r2_supply[12]) if r2_supply[12] else np.nan
    short_demand = np.nanmean(r2_demand[12]) if r2_demand[12] else np.nan

    supply_growth = long_supply - short_supply if not (np.isnan(long_supply) or np.isnan(short_supply)) else np.nan
    demand_growth = long_demand - short_demand if not (np.isnan(long_demand) or np.isnan(short_demand)) else np.nan

    print(f"\n  Supply R² growth (1h→3d): {supply_growth:+.4f}")
    print(f"  Demand R² growth (1h→3d): {demand_growth:+.4f}")

    if not np.isnan(supply_growth) and not np.isnan(demand_growth):
        if supply_growth > demand_growth + 0.01:
            print(f"  → SUPPLY integral grows faster → glycogen/hepatic state accumulates")
        elif demand_growth > supply_growth + 0.01:
            print(f"  → DEMAND integral grows faster → insulin sensitivity accumulates")
        else:
            print(f"  → Both grow similarly → no clear phase separation")

    results = {
        'supply_growth': float(supply_growth) if not np.isnan(supply_growth) else None,
        'demand_growth': float(demand_growth) if not np.isnan(demand_growth) else None,
        'supply_wins_at_scales': supply_wins,
        'demand_wins_at_scales': demand_wins,
        'verdict': ('SUPPLY_PHASE_DETECTED' if (supply_growth or 0) > (demand_growth or 0) + 0.01
                    else 'DEMAND_PHASE_DETECTED' if (demand_growth or 0) > (supply_growth or 0) + 0.01
                    else 'NO_PHASE_SEPARATION')
    }

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: R² by integration window
        ax = axes[0]
        x = range(len(int_labels))
        for name_sig, data, color, marker in [
            ('∫Supply', r2_supply, '#e74c3c', 'o'),
            ('∫Demand', r2_demand, '#3498db', 's'),
            ('∫Balance', r2_balance, '#27ae60', '^'),
            ('Raw Mean', r2_raw, '#2c3e50', 'D')
        ]:
            vals = [np.nanmean(data[w]) if data[w] else np.nan for w in int_windows]
            ax.plot(x, vals, f'-{marker}', color=color, linewidth=2, markersize=6, label=name_sig)
        ax.set_xticks(list(x))
        ax.set_xticklabels(int_labels, rotation=45)
        ax.set_xlabel('Integration Window')
        ax.set_ylabel('R² with Next-24h Mean Glucose')
        ax.set_title('Supply vs Demand: Who Predicts Better at Each Scale?')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        # Right: Growth comparison
        ax = axes[1]
        categories = ['∫Supply\nR² growth', '∫Demand\nR² growth']
        growths = [supply_growth if not np.isnan(supply_growth) else 0,
                   demand_growth if not np.isnan(demand_growth) else 0]
        colors_bar = ['#e74c3c', '#3498db']
        ax.bar(range(2), growths, color=colors_bar, alpha=0.7, edgecolor='black', width=0.5)
        ax.axhline(0, color='gray', linestyle='--', alpha=0.5)
        ax.set_xticks(range(2))
        ax.set_xticklabels(categories)
        ax.set_ylabel('R² Growth (1h → 3d)')
        ax.set_title('Which Channel Accumulates More Predictive Power?')
        ax.grid(True, alpha=0.3, axis='y')

        fig.suptitle('EXP-1824: Do Supply and Demand Operate on Different Phases?',
                      fontsize=14, fontweight='bold')
        fig.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'cumulative-fig04-integral-asymmetry.png'), dpi=150)
        plt.close(fig)
        print(f"  → Saved cumulative-fig04-integral-asymmetry.png")

    return results


# ============================================================================
# EXP-1825: Cumulative Balance → Context Prediction
# ============================================================================
def exp_1825(patients, figures_dir=None):
    """Can cumulative S-D balance predict what metabolic context comes next?"""
    print("\n" + "=" * 70)
    print("EXP-1825: Cumulative Balance → Context Prediction")
    print("=" * 70)

    context_accuracy = []
    context_auc = defaultdict(list)

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values.astype(np.float64)
        sd = compute_supply_demand(df)
        ctx = classify_metabolic_context(df, sd)
        supply = sd['supply']
        demand = sd['demand']

        # 24h cumulative balance
        cum_bal = rolling_sum(supply - demand, 288)

        # For each timestep with valid balance, what context comes in the next 2h?
        n = len(glucose)
        future_ctx = np.full(n, 'unknown', dtype=object)
        for i in range(n - 24):
            # Majority context in next 2h
            window = ctx[i:i + 24]
            unique, counts = np.unique(window, return_counts=True)
            future_ctx[i] = unique[np.argmax(counts)]

        valid = np.isfinite(cum_bal) & (future_ctx != 'unknown')

        if valid.sum() < 200:
            continue

        # For each context, compute mean cumulative balance when that context follows
        ctx_balances = defaultdict(list)
        for i in np.where(valid)[0]:
            ctx_balances[future_ctx[i]].append(cum_bal[i])

        print(f"  {name}:")
        for ctx_name in ['fasting', 'post_meal', 'correction', 'hypo_recovery', 'other']:
            vals = ctx_balances.get(ctx_name, [])
            if vals:
                print(f"    {ctx_name:15s}: n={len(vals):5d}  balance={np.mean(vals):+8.1f} ± {np.std(vals):.1f}")

        # AUC: can balance discriminate each context vs rest?
        for ctx_name in ['fasting', 'post_meal', 'hypo_recovery', 'correction']:
            target = (future_ctx[valid] == ctx_name).astype(float)
            predictor = cum_bal[valid]
            if target.sum() < 20 or target.sum() > len(target) - 20:
                continue
            # Simple AUC via rank correlation
            try:
                from scipy.stats import rankdata
                r = rankdata(predictor)
                pos_ranks = r[target == 1]
                n_pos = int(target.sum())
                n_neg = int(len(target) - target.sum())
                auc = (pos_ranks.sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
                context_auc[ctx_name].append(auc)
            except:
                pass

    # Population AUC
    print(f"\n  AUC for predicting next-2h context from 24h cumulative balance:")
    for ctx_name in ['fasting', 'post_meal', 'hypo_recovery', 'correction']:
        vals = context_auc[ctx_name]
        if vals:
            mean_auc = np.mean(vals)
            print(f"    {ctx_name:15s}: AUC={mean_auc:.3f} ± {np.std(vals):.3f}  (n={len(vals)} patients)"
                  f"  {'★' if abs(mean_auc - 0.5) > 0.1 else ''}")

    results = {
        'context_auc': {c: float(np.mean(v)) for c, v in context_auc.items() if v},
        'verdict': ('BALANCE_PREDICTS_CONTEXT'
                    if any(abs(np.mean(v) - 0.5) > 0.1 for v in context_auc.values() if v)
                    else 'BALANCE_UNINFORMATIVE')
    }

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(1, 1, figsize=(8, 5))

        contexts = ['fasting', 'post_meal', 'hypo_recovery', 'correction']
        ctx_labels = ['Fasting', 'Post-Meal', 'Hypo\nRecovery', 'Correction']
        auc_means = [np.mean(context_auc.get(c, [0.5])) for c in contexts]
        auc_stds = [np.std(context_auc.get(c, [0])) for c in contexts]
        colors = ['#2ecc71', '#e74c3c', '#f39c12', '#3498db']

        bars = ax.bar(range(len(contexts)), auc_means, yerr=auc_stds, capsize=5,
                      color=colors, alpha=0.7, edgecolor='black')
        ax.axhline(0.5, color='gray', linestyle='--', alpha=0.7, label='Random (AUC=0.5)')
        ax.set_xticks(range(len(contexts)))
        ax.set_xticklabels(ctx_labels)
        ax.set_ylabel('AUC')
        ax.set_title('EXP-1825: Can 24h Cumulative Balance\nPredict Next Metabolic Context?')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        ax.set_ylim(0.3, 0.8)

        fig.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'cumulative-fig05-context-prediction.png'), dpi=150)
        plt.close(fig)
        print(f"  → Saved cumulative-fig05-context-prediction.png")

    return results


# ============================================================================
# EXP-1826: Low-Rank Structure in Long Windows
# ============================================================================
def exp_1826(patients, figures_dir=None):
    """Is there low-dimensional structure at 12-48h timescales?"""
    print("\n" + "=" * 70)
    print("EXP-1826: Low-Rank Structure in Long Windows")
    print("=" * 70)

    window_sizes = [144, 288, 576]  # 12h, 24h, 48h
    window_labels = ['12h', '24h', '48h']

    pca_results = {w: {'n_components_80': [], 'top_component_var': [],
                        'alignment_supply': [], 'alignment_demand': []}
                   for w in window_sizes}

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values.astype(np.float64)
        sd = compute_supply_demand(df)
        supply = sd['supply']
        demand = sd['demand']

        for win_size in window_sizes:
            # Build feature matrix: sliding windows of glucose
            n = len(glucose) - win_size
            step = max(1, win_size // 4)  # stride to avoid too many windows
            indices = list(range(0, n, step))

            X = np.zeros((len(indices), win_size))
            supply_sum = np.zeros(len(indices))
            demand_sum = np.zeros(len(indices))

            for j, i in enumerate(indices):
                window = glucose[i:i + win_size]
                X[j] = window
                supply_sum[j] = np.nansum(supply[i:i + win_size])
                demand_sum[j] = np.nansum(demand[i:i + win_size])

            # Remove NaN rows
            valid = np.all(np.isfinite(X), axis=1) & np.isfinite(supply_sum) & np.isfinite(demand_sum)
            X = X[valid]
            supply_sum = supply_sum[valid]
            demand_sum = demand_sum[valid]

            if len(X) < 50:
                continue

            # Center
            X = X - X.mean(axis=0)

            # SVD
            try:
                U, S, Vt = np.linalg.svd(X, full_matrices=False)
            except:
                continue

            # Variance explained
            var_explained = S ** 2 / np.sum(S ** 2)
            cumulative = np.cumsum(var_explained)
            n_80 = int(np.searchsorted(cumulative, 0.8)) + 1

            # Alignment: do top PCs correlate with supply or demand integrals?
            pc1_scores = U[:, 0] * S[0]
            align_supply = abs(safe_corr(pc1_scores, supply_sum))
            align_demand = abs(safe_corr(pc1_scores, demand_sum))

            pca_results[win_size]['n_components_80'].append(n_80)
            pca_results[win_size]['top_component_var'].append(float(var_explained[0]))
            pca_results[win_size]['alignment_supply'].append(float(align_supply))
            pca_results[win_size]['alignment_demand'].append(float(align_demand))

        print(f"  {name}: PCA at {len(window_sizes)} window sizes")

    # Summary
    print(f"\n  PCA Summary:")
    print(f"  {'Window':>8s}  {'PCs for 80%':>12s}  {'PC1 Var%':>10s}  {'PC1↔Supply':>11s}  {'PC1↔Demand':>11s}")

    for w, label in zip(window_sizes, window_labels):
        r = pca_results[w]
        if not r['n_components_80']:
            continue
        n80 = np.mean(r['n_components_80'])
        pc1v = np.mean(r['top_component_var']) * 100
        as_ = np.mean(r['alignment_supply'])
        ad = np.mean(r['alignment_demand'])
        print(f"  {label:>8s}  {n80:>12.1f}  {pc1v:>9.1f}%  {as_:>11.3f}  {ad:>11.3f}")

    # Key finding: does dimensionality decrease at longer windows?
    if pca_results[144]['n_components_80'] and pca_results[576]['n_components_80']:
        dim_12h = np.mean(pca_results[144]['n_components_80'])
        dim_48h = np.mean(pca_results[576]['n_components_80'])
        ratio = dim_48h / dim_12h
        print(f"\n  Dimensionality ratio (48h/12h): {ratio:.2f}")
        if ratio < 0.8:
            print(f"  → Long windows ARE lower-rank — structure compresses at longer timescales")
        else:
            print(f"  → No dimensionality reduction — long windows are as complex as short ones")

    results = {
        'summary': {
            label: {
                'n_components_80': float(np.mean(pca_results[w]['n_components_80'])) if pca_results[w]['n_components_80'] else np.nan,
                'pc1_variance': float(np.mean(pca_results[w]['top_component_var'])) if pca_results[w]['top_component_var'] else np.nan,
                'pc1_supply_alignment': float(np.mean(pca_results[w]['alignment_supply'])) if pca_results[w]['alignment_supply'] else np.nan,
                'pc1_demand_alignment': float(np.mean(pca_results[w]['alignment_demand'])) if pca_results[w]['alignment_demand'] else np.nan,
            }
            for w, label in zip(window_sizes, window_labels)
        },
        'verdict': 'LOW_RANK_DETECTED' if (pca_results[576]['n_components_80'] and np.mean(pca_results[576]['n_components_80']) < np.mean(pca_results[144]['n_components_80']) * 0.8) else 'NO_LOW_RANK'
    }

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(18, 5))

        # Left: Components needed for 80% variance
        ax = axes[0]
        for w, label in zip(window_sizes, window_labels):
            vals = pca_results[w]['n_components_80']
            if vals:
                ax.bar(window_labels.index(label), np.mean(vals),
                       yerr=np.std(vals), capsize=5,
                       color=['#3498db', '#27ae60', '#e74c3c'][window_labels.index(label)],
                       alpha=0.7, edgecolor='black')
        ax.set_xlabel('Window Size')
        ax.set_ylabel('PCs for 80% Variance')
        ax.set_title('Effective Dimensionality\n(fewer = more structured)')
        ax.grid(True, alpha=0.3, axis='y')

        # Middle: PC1 alignment with supply vs demand
        ax = axes[1]
        x = np.arange(len(window_labels))
        w_bar = 0.35
        supply_align = [np.mean(pca_results[w]['alignment_supply']) if pca_results[w]['alignment_supply'] else 0
                        for w in window_sizes]
        demand_align = [np.mean(pca_results[w]['alignment_demand']) if pca_results[w]['alignment_demand'] else 0
                        for w in window_sizes]
        ax.bar(x - w_bar/2, supply_align, w_bar, label='PC1 ↔ ∫Supply', color='#e74c3c', alpha=0.7)
        ax.bar(x + w_bar/2, demand_align, w_bar, label='PC1 ↔ ∫Demand', color='#3498db', alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(window_labels)
        ax.set_ylabel('|Correlation| with PC1')
        ax.set_title('Does PC1 Align with Supply or Demand?')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')

        # Right: PC1 variance explained
        ax = axes[2]
        pc1_vars = [np.mean(pca_results[w]['top_component_var']) * 100 if pca_results[w]['top_component_var'] else 0
                    for w in window_sizes]
        ax.bar(range(len(window_labels)), pc1_vars,
               color=['#3498db', '#27ae60', '#e74c3c'], alpha=0.7, edgecolor='black')
        ax.set_xticks(range(len(window_labels)))
        ax.set_xticklabels(window_labels)
        ax.set_ylabel('PC1 Variance Explained (%)')
        ax.set_title('How Much Does the Top Component Capture?')
        ax.grid(True, alpha=0.3, axis='y')

        fig.suptitle('EXP-1826: Is There Low-Rank Structure at Long Timescales?',
                      fontsize=14, fontweight='bold')
        fig.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'cumulative-fig06-low-rank.png'), dpi=150)
        plt.close(fig)
        print(f"  → Saved cumulative-fig06-low-rank.png")

    return results


# ============================================================================
# Main
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description="EXP-1821–1826: Cumulative Integral Information")
    parser.add_argument('--figures', action='store_true')
    parser.add_argument('--exp', type=int, nargs='*')
    parser.add_argument('--data-dir', default='externals/ns-data/patients/')
    args = parser.parse_args()

    figures_dir = None
    if args.figures:
        figures_dir = 'docs/60-research/figures'
        os.makedirs(figures_dir, exist_ok=True)

    print("=" * 70)
    print("EXP-1821–1826: Cumulative Integral Information & Slow State Detection")
    print("=" * 70)

    patients = load_patients(args.data_dir)
    print(f"Loaded {len(patients)} patients\n")

    experiments = {
        1821: ('Cumulative Supply-Demand Balance Information', exp_1821),
        1822: ('Supply vs Demand Integral Divergence', exp_1822),
        1823: ('Slow State Feature Engineering', exp_1823),
        1824: ('Integral Asymmetry Detection', exp_1824),
        1825: ('Cumulative Balance → Context Prediction', exp_1825),
        1826: ('Low-Rank Structure in Long Windows', exp_1826),
    }

    run_ids = args.exp if args.exp else sorted(experiments.keys())

    all_results = {}
    for eid in run_ids:
        if eid not in experiments:
            print(f"Unknown experiment: EXP-{eid}")
            continue
        exp_name, func = experiments[eid]
        print(f"\n{'#' * 70}")
        print(f"# Running EXP-{eid}: {exp_name}")
        print(f"{'#' * 70}")
        try:
            result = func(patients, figures_dir)
            all_results[f'EXP-{eid}'] = result
            print(f"\n  ✓ EXP-{eid} verdict: {result.get('verdict', 'N/A')}")
        except Exception as e:
            import traceback
            print(f"\n  ✗ EXP-{eid} FAILED: {e}")
            traceback.print_exc()
            all_results[f'EXP-{eid}'] = {'error': str(e)}

    # Save results
    output_path = 'externals/experiments/exp-1821_cumulative_integral_info.json'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    def convert(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, dict): return {k: convert(v) for k, v in obj.items()}
        if isinstance(obj, list): return [convert(v) for v in obj]
        return obj

    with open(output_path, 'w') as f:
        json.dump(convert({
            'experiment': 'EXP-1821 to EXP-1826',
            'title': 'Cumulative Integral Information and Slow State Detection',
            'results': all_results
        }), f, indent=2)
    print(f"\n✓ Results saved to {output_path}")

    # Synthesis
    print("\n" + "=" * 70)
    print("SYNTHESIS: Cumulative Integrals and Slow State")
    print("=" * 70)
    for eid, result in all_results.items():
        verdict = result.get('verdict', result.get('error', 'N/A'))
        print(f"  {eid}: {verdict}")

    print("\n✓ All experiments complete")


if __name__ == '__main__':
    main()
