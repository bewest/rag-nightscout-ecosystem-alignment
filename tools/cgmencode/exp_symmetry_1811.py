#!/usr/bin/env python3
"""EXP-1811 to EXP-1818: Glucose Signal Symmetry and Information Decomposition.

Motivated by the question: Can we structurally identify TWO independent
information sources (supply vs demand) in the glucose trace, even though
we only measure their sum (blood glucose)?

Key insight: glucose obeys an approximate conservation law:
    dBG/dt ≈ supply(t) - demand(t)

where supply = hepatic output + carb absorption, demand = insulin-mediated uptake.
These two processes have DIFFERENT generating mechanisms, timescales, and statistical
properties.  If we can characterize their signatures, we know WHERE information
lives in the data — crucial for model architecture decisions (e.g., should a
forecaster use long windows for demand and short windows for supply?).

  EXP-1811: Time-Reversal Asymmetry (TRA)
    - If supply and demand have identical dynamics, glucose played forward is
      statistically indistinguishable from glucose played backward.
    - TRA measures this: if the signal has a preferred temporal direction, the
      processes generating it have asymmetric dynamics.
    - Method: compute TRA statistic (skewness of velocity increments), compare
      to shuffled null.  Break down by metabolic context.

  EXP-1812: Rising vs Falling Spectral Signatures
    - Separate glucose into rising segments (supply > demand) and falling segments
      (demand > supply).  Compute power spectral density for each.
    - Hypothesis: supply-dominated rises have more high-frequency content (meals
      are sudden) while demand-dominated falls are lower-frequency (insulin is slow).
    - Method: segment by sign of dBG, compute Welch PSD, compare spectral slopes.

  EXP-1813: Information Horizon by Channel
    - How far into the past does supply vs demand carry useful information?
    - Method: compute mutual information between current dBG and lagged features
      (insulin, carbs, glucose itself) at lags from 5min to 7 days.
    - Hypothesis: insulin information decays over ~6h (DIA), carb information
      decays over ~3h, but cumulative supply/demand balance has longer memory.

  EXP-1814: Supply-Demand Cross-Predictability
    - Does past supply predict future demand?  Does past demand predict future
      supply?  (via Granger-like conditional mutual information)
    - Key: the AID loop creates a deliberate coupling — insulin responds to
      glucose, which responds to supply.  This is the "closed-loop signature".
    - Method: compute directed information S→D and D→S at various lags.

  EXP-1815: Multi-Scale Variance Ratio
    - At different timescales (5min to 7 days), what fraction of glucose variance
      is attributable to supply vs demand?
    - Method: Haar wavelet decomposition, attribute wavelet coefficients to supply
      proxy (positive dBG - modeled insulin effect) and demand proxy (negative
      dBG + modeled hepatic output).
    - Hypothesis: supply dominates at short scales (<2h, meals), demand dominates
      at medium scales (2-8h, insulin), both mix at long scales (>24h, patterns).

  EXP-1816: Conservation Law Residual Analysis
    - Using our physics model: residual = dBG/dt - (supply_model - demand_model).
    - If the model is complete, residuals should be white noise.
    - Analyze residual autocorrelation, spectral content, and cross-correlation
      with supply/demand to identify MISSING channels.
    - Method: compute model residuals, test for whiteness, decompose remaining
      structure.

  EXP-1817: Split-Loss Information Experiment
    - Train two simple models with DIFFERENT loss functions:
      a) Supply-loss: penalize only errors during glucose RISES (supply-active periods)
      b) Demand-loss: penalize only errors during glucose FALLS (demand-active periods)
    - Compare what features each model learns to rely on.
    - At different history window lengths (1h, 6h, 24h, 7d), does the supply
      model and demand model extract different amounts of information?
    - This directly tests the user's hypothesis about split losses.

  EXP-1818: Symmetry Breaking Points
    - Identify specific events/contexts where supply and demand information
      DIVERGE most (i.e., where knowing one channel doesn't help predict the other).
    - Method: sliding window cross-correlation between supply and demand proxies.
      Windows where correlation breaks down are "symmetry breaking points".
    - Hypothesis: these correspond to meals, exercise, and site changes — events
      where one channel changes independently.

Run: PYTHONPATH=tools python3 tools/cgmencode/exp_symmetry_1811.py --figures
"""

import argparse
import json
import os
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import signal as sig
from scipy import stats

warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288


def load_patients(data_dir='externals/ns-data/patients/'):
    from cgmencode.exp_metabolic_flux import load_patients as _lp
    return _lp(data_dir)


def compute_supply_demand(df):
    """Load supply/demand from metabolic engine."""
    from cgmencode.exp_metabolic_441 import compute_supply_demand as _csd
    return _csd(df)


def safe_corr(x, y):
    """Pearson correlation with NaN safety."""
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 10:
        return np.nan
    return float(np.corrcoef(x[mask], y[mask])[0, 1])


def safe_mi_binned(x, y, bins=20):
    """Estimate mutual information via histogram binning (bits)."""
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 50:
        return np.nan
    xv, yv = x[mask], y[mask]
    # Discretize
    xd = np.digitize(xv, np.linspace(np.percentile(xv, 1), np.percentile(xv, 99), bins))
    yd = np.digitize(yv, np.linspace(np.percentile(yv, 1), np.percentile(yv, 99), bins))
    # Joint and marginals
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


def classify_metabolic_context(df, sd):
    """Classify each timestep into metabolic context."""
    n = len(df)
    ctx = np.full(n, 'other', dtype=object)
    glucose = df['glucose'].values.astype(np.float64)
    carbs = df['carbs'].values.astype(np.float64) if 'carbs' in df.columns else np.zeros(n)
    iob = df['iob'].values.astype(np.float64) if 'iob' in df.columns else np.zeros(n)

    # Post-meal: within 3h of carbs > 1g
    meal_mask = np.zeros(n, dtype=bool)
    carb_indices = np.where(carbs > 1)[0]
    for ci in carb_indices:
        meal_mask[ci:min(ci + 36, n)] = True  # 3h

    # Fasting: no carbs for 4h, IOB < median, glucose relatively stable
    fasting_mask = np.zeros(n, dtype=bool)
    for i in range(48, n):
        if not np.any(carbs[max(0, i - 48):i] > 1):
            fasting_mask[i] = True

    # Correction: IOB > 75th percentile, glucose > 180
    iob_75 = np.nanpercentile(iob, 75)
    correction_mask = (iob > iob_75) & (glucose > 180) & ~meal_mask

    # Hypo recovery: glucose < 70 or within 30min after
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
# EXP-1811: Time-Reversal Asymmetry
# ============================================================================
def exp_1811(patients, figures_dir=None):
    """Time-reversal asymmetry test.

    A stationary Gaussian process has zero time-reversal asymmetry.
    Non-zero TRA implies the generating process has a preferred direction
    (as conservation-law systems do).

    TRA statistic: <(x(t+τ) - x(t))³> / <(x(t+τ) - x(t))²>^(3/2)
    This is the skewness of velocity increments at lag τ.
    """
    print("\n" + "=" * 70)
    print("EXP-1811: Time-Reversal Asymmetry")
    print("=" * 70)

    results = {}
    lags = [1, 3, 6, 12, 24, 36, 72, 144, 288]  # 5min to 24h
    lag_labels = ['5m', '15m', '30m', '1h', '2h', '3h', '6h', '12h', '24h']

    all_tra = []  # patients × lags
    all_tra_by_ctx = defaultdict(lambda: defaultdict(list))  # ctx → lag → values
    n_shuffles = 200

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values.astype(np.float64)
        valid = np.isfinite(glucose)

        sd = compute_supply_demand(df)
        ctx = classify_metabolic_context(df, sd)

        patient_tra = []
        for lag in lags:
            # Forward increments
            inc = glucose[lag:] - glucose[:-lag]
            inc_valid = inc[valid[lag:] & valid[:-lag]]
            if len(inc_valid) < 100:
                patient_tra.append(np.nan)
                continue

            # TRA = skewness of increments
            mu2 = np.nanmean(inc_valid ** 2)
            mu3 = np.nanmean(inc_valid ** 3)
            tra = mu3 / (mu2 ** 1.5) if mu2 > 0 else 0.0

            # Null distribution: shuffle time series
            null_tra = []
            for _ in range(n_shuffles):
                shuf = np.random.permutation(glucose[valid])
                sinc = shuf[lag:] - shuf[:-lag]
                smu2 = np.mean(sinc ** 2)
                smu3 = np.mean(sinc ** 3)
                null_tra.append(smu3 / (smu2 ** 1.5) if smu2 > 0 else 0.0)
            null_tra = np.array(null_tra)
            p_value = float(np.mean(np.abs(null_tra) >= np.abs(tra)))

            patient_tra.append(tra)
            print(f"  {name} lag={lag:3d} ({lag*5:5d}min): TRA={tra:+.4f}  p={p_value:.3f}"
                  f"  {'***' if p_value < 0.01 else '**' if p_value < 0.05 else ''}")

            # By context
            for c in ['fasting', 'post_meal', 'correction', 'hypo_recovery']:
                cmask = (ctx[lag:] == c) | (ctx[:-lag] == c)
                cinc = inc[cmask & valid[lag:] & valid[:-lag]]
                if len(cinc) > 50:
                    cmu2 = np.mean(cinc ** 2)
                    cmu3 = np.mean(cinc ** 3)
                    ctra = cmu3 / (cmu2 ** 1.5) if cmu2 > 0 else 0.0
                    all_tra_by_ctx[c][lag].append(ctra)

        all_tra.append(patient_tra)

    all_tra = np.array(all_tra)
    mean_tra = np.nanmean(all_tra, axis=0)

    print("\n  Population mean TRA by lag:")
    for i, (lag, label) in enumerate(zip(lags, lag_labels)):
        sig_count = np.sum(np.abs(all_tra[:, i]) > 0.1)
        print(f"    {label:>4s}: TRA={mean_tra[i]:+.4f}  ({sig_count}/11 patients |TRA|>0.1)")

    print("\n  Context-specific TRA (lag=6, 30min):")
    for c in ['fasting', 'post_meal', 'correction', 'hypo_recovery']:
        vals = all_tra_by_ctx[c].get(6, [])
        if vals:
            print(f"    {c:15s}: TRA={np.mean(vals):+.4f} ± {np.std(vals):.4f}  (n={len(vals)})")

    results = {
        'mean_tra_by_lag': {l: float(m) for l, m in zip(lag_labels, mean_tra)},
        'context_tra_30min': {
            c: float(np.mean(all_tra_by_ctx[c].get(6, [np.nan])))
            for c in ['fasting', 'post_meal', 'correction', 'hypo_recovery']
        },
        'verdict': 'TRA_PRESENT' if np.abs(mean_tra[2]) > 0.05 else 'TRA_ABSENT'
    }

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        # Left: TRA by lag (population)
        ax = axes[0]
        for i, row in enumerate(all_tra):
            ax.plot(range(len(lags)), row, 'o-', alpha=0.3, markersize=3)
        ax.plot(range(len(lags)), mean_tra, 'k-o', linewidth=2.5, markersize=6, label='Population mean')
        ax.axhline(0, color='gray', linestyle='--', alpha=0.5)
        ax.set_xticks(range(len(lags)))
        ax.set_xticklabels(lag_labels, rotation=45)
        ax.set_xlabel('Lag')
        ax.set_ylabel('Time-Reversal Asymmetry (TRA)')
        ax.set_title('EXP-1811: Glucose Has Preferred Time Direction')
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Right: TRA by context at 30min lag
        ax = axes[1]
        contexts = ['fasting', 'post_meal', 'correction', 'hypo_recovery']
        ctx_labels = ['Fasting', 'Post-Meal', 'Correction', 'Hypo Recovery']
        ctx_means = []
        ctx_stds = []
        for c in contexts:
            vals = all_tra_by_ctx[c].get(6, [0])
            ctx_means.append(np.mean(vals))
            ctx_stds.append(np.std(vals))
        colors = ['#2ecc71', '#e74c3c', '#3498db', '#f39c12']
        bars = ax.bar(range(len(contexts)), ctx_means, yerr=ctx_stds, capsize=5,
                      color=colors, alpha=0.7, edgecolor='black')
        ax.axhline(0, color='gray', linestyle='--', alpha=0.5)
        ax.set_xticks(range(len(contexts)))
        ax.set_xticklabels(ctx_labels)
        ax.set_ylabel('TRA at 30-min lag')
        ax.set_title('Time Asymmetry by Metabolic Context')
        ax.grid(True, alpha=0.3, axis='y')

        fig.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'symmetry-fig01-time-reversal.png'), dpi=150)
        plt.close(fig)
        print(f"  → Saved symmetry-fig01-time-reversal.png")

    return results


# ============================================================================
# EXP-1812: Rising vs Falling Spectral Signatures
# ============================================================================
def exp_1812(patients, figures_dir=None):
    """Compare power spectral density of rising vs falling glucose segments."""
    print("\n" + "=" * 70)
    print("EXP-1812: Rising vs Falling Spectral Signatures")
    print("=" * 70)

    all_psd_rising = []
    all_psd_falling = []
    psd_freqs = None

    slope_comparisons = []

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values.astype(np.float64)
        dbg = np.diff(glucose)

        # Rising segments: contiguous runs of positive dBG
        rising_segs = []
        falling_segs = []
        current_seg = [glucose[0]]
        is_rising = True

        for i in range(len(dbg)):
            if np.isnan(dbg[i]):
                if len(current_seg) > 6:  # Minimum 30min segment
                    if is_rising:
                        rising_segs.append(np.array(current_seg))
                    else:
                        falling_segs.append(np.array(current_seg))
                current_seg = [glucose[i + 1]]
                continue

            if (dbg[i] > 0) == is_rising:
                current_seg.append(glucose[i + 1])
            else:
                if len(current_seg) > 6:
                    if is_rising:
                        rising_segs.append(np.array(current_seg))
                    else:
                        falling_segs.append(np.array(current_seg))
                current_seg = [glucose[i + 1]]
                is_rising = dbg[i] > 0

        # Compute PSD for each direction using Welch's method
        # Concatenate segments with zero-mean for each
        if rising_segs:
            rise_cat = np.concatenate([s - np.nanmean(s) for s in rising_segs if len(s) > 6])
            rise_cat = rise_cat[np.isfinite(rise_cat)]
            if len(rise_cat) > 64:
                fr, pr = sig.welch(rise_cat, fs=12.0, nperseg=min(256, len(rise_cat) // 2))
                all_psd_rising.append(pr)
                if psd_freqs is None:
                    psd_freqs = fr

        if falling_segs:
            fall_cat = np.concatenate([s - np.nanmean(s) for s in falling_segs if len(s) > 6])
            fall_cat = fall_cat[np.isfinite(fall_cat)]
            if len(fall_cat) > 64:
                ff, pf = sig.welch(fall_cat, fs=12.0, nperseg=min(256, len(fall_cat) // 2))
                all_psd_falling.append(pf)

        # Spectral slope (log-log regression)
        if all_psd_rising and all_psd_falling:
            pr = all_psd_rising[-1]
            pf = all_psd_falling[-1]
            fr = psd_freqs
            mask = fr > 0.1  # above 0.1 cycles/hour
            if mask.sum() > 3:
                slope_r = np.polyfit(np.log10(fr[mask]), np.log10(pr[mask] + 1e-10), 1)[0]
                slope_f = np.polyfit(np.log10(fr[mask]), np.log10(pf[mask] + 1e-10), 1)[0]
                slope_comparisons.append({
                    'name': name,
                    'rise_segments': len(rising_segs),
                    'fall_segments': len(falling_segs),
                    'spectral_slope_rising': slope_r,
                    'spectral_slope_falling': slope_f,
                    'slope_diff': slope_r - slope_f
                })
                print(f"  {name}: rise_slope={slope_r:.3f}  fall_slope={slope_f:.3f}"
                      f"  Δ={slope_r - slope_f:+.3f}  (n_rise={len(rising_segs)}, n_fall={len(falling_segs)})")

    mean_slope_rising = np.mean([s['spectral_slope_rising'] for s in slope_comparisons])
    mean_slope_falling = np.mean([s['spectral_slope_falling'] for s in slope_comparisons])
    print(f"\n  Population: rise_slope={mean_slope_rising:.3f}  fall_slope={mean_slope_falling:.3f}"
          f"  Δ={mean_slope_rising - mean_slope_falling:+.3f}")

    results = {
        'per_patient': slope_comparisons,
        'population_slope_rising': float(mean_slope_rising),
        'population_slope_falling': float(mean_slope_falling),
        'slope_difference': float(mean_slope_rising - mean_slope_falling),
        'verdict': ('SPECTRALLY_DISTINCT' if abs(mean_slope_rising - mean_slope_falling) > 0.3
                    else 'SPECTRALLY_SIMILAR')
    }

    if figures_dir and psd_freqs is not None:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: mean PSD
        ax = axes[0]
        mean_psd_r = np.mean(all_psd_rising, axis=0) if all_psd_rising else None
        mean_psd_f = np.mean(all_psd_falling, axis=0) if all_psd_falling else None
        if mean_psd_r is not None:
            ax.loglog(psd_freqs[1:], mean_psd_r[1:], 'r-', linewidth=2, label='Rising (supply-dominated)')
        if mean_psd_f is not None:
            ax.loglog(psd_freqs[1:], mean_psd_f[1:], 'b-', linewidth=2, label='Falling (demand-dominated)')
        ax.set_xlabel('Frequency (cycles/hour)')
        ax.set_ylabel('Power Spectral Density')
        ax.set_title('EXP-1812: Rising vs Falling PSD')
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Mark key frequencies
        for period, label in [(1.0, '1h'), (0.5, '2h'), (1/6, '6h')]:
            ax.axvline(period, color='gray', linestyle=':', alpha=0.3)
            ax.text(period, ax.get_ylim()[1] * 0.5, label, fontsize=8, alpha=0.5)

        # Right: spectral slope comparison
        ax = axes[1]
        names = [s['name'] for s in slope_comparisons]
        x = np.arange(len(names))
        w = 0.35
        ax.bar(x - w/2, [s['spectral_slope_rising'] for s in slope_comparisons],
               w, label='Rising (supply)', color='#e74c3c', alpha=0.7)
        ax.bar(x + w/2, [s['spectral_slope_falling'] for s in slope_comparisons],
               w, label='Falling (demand)', color='#3498db', alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('Spectral Slope (log-log)')
        ax.set_title('Spectral Slope: Supply vs Demand Direction')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        ax.axhline(0, color='gray', linestyle='--', alpha=0.3)

        fig.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'symmetry-fig02-spectral.png'), dpi=150)
        plt.close(fig)
        print(f"  → Saved symmetry-fig02-spectral.png")

    return results


# ============================================================================
# EXP-1813: Information Horizon by Channel
# ============================================================================
def exp_1813(patients, figures_dir=None):
    """Measure how far into the past different channels carry information.

    For each channel (glucose, insulin/IOB, carbs, supply proxy, demand proxy),
    compute mutual information with current dBG at increasing lags.
    """
    print("\n" + "=" * 70)
    print("EXP-1813: Information Horizon by Channel")
    print("=" * 70)

    lags = [1, 3, 6, 12, 24, 48, 72, 144, 288, 576, 864, 2016]
    lag_hours = [l * 5 / 60 for l in lags]
    lag_labels = [f'{h:.1f}h' if h < 24 else f'{h/24:.0f}d' for h in lag_hours]

    channels = ['glucose', 'iob', 'carbs', 'supply_proxy', 'demand_proxy']
    # MI[channel][lag] = list of per-patient values
    mi_by_channel = {c: {l: [] for l in lags} for c in channels}

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values.astype(np.float64)
        dbg = np.concatenate([[0], np.diff(glucose)])
        iob = df['iob'].values.astype(np.float64) if 'iob' in df.columns else np.zeros(len(df))
        carbs = df['carbs'].values.astype(np.float64) if 'carbs' in df.columns else np.zeros(len(df))

        # Supply proxy: positive dBG + insulin contribution (glucose is rising despite insulin)
        # demand proxy: negative dBG (insulin winning)
        supply_proxy = np.where(dbg > 0, dbg, 0) + 0.5 * iob  # crude: rise + insulin that was overcoming
        demand_proxy = np.where(dbg < 0, -dbg, 0)  # how fast glucose falls

        data = {
            'glucose': glucose,
            'iob': iob,
            'carbs': carbs,
            'supply_proxy': supply_proxy,
            'demand_proxy': demand_proxy
        }

        target = dbg  # current rate of change

        for ch_name, ch_data in data.items():
            for lag in lags:
                if lag >= len(target) - 10:
                    continue
                x = ch_data[:-lag]
                y = target[lag:]
                mi = safe_mi_binned(x, y)
                mi_by_channel[ch_name][lag].append(mi)

        print(f"  {name}: computed MI at {len(lags)} lags × {len(channels)} channels")

    # Summarize
    print("\n  Mean MI (bits) with current dBG/dt:")
    print(f"  {'Lag':>8s}", end='')
    for ch in channels:
        print(f"  {ch:>14s}", end='')
    print()

    mi_curves = {ch: [] for ch in channels}
    for i, (lag, label) in enumerate(zip(lags, lag_labels)):
        print(f"  {label:>8s}", end='')
        for ch in channels:
            vals = mi_by_channel[ch][lag]
            mean_val = np.nanmean(vals) if vals else np.nan
            mi_curves[ch].append(mean_val)
            print(f"  {mean_val:>14.4f}", end='')
        print()

    # Find information horizon: lag where MI drops below 50% of peak
    horizons = {}
    for ch in channels:
        curve = mi_curves[ch]
        if not curve or all(np.isnan(curve)):
            horizons[ch] = np.nan
            continue
        peak = np.nanmax(curve)
        threshold = peak * 0.5
        horizon_idx = len(curve) - 1
        for j, v in enumerate(curve):
            if not np.isnan(v) and v < threshold and j > np.nanargmax(curve):
                horizon_idx = j
                break
        horizons[ch] = lag_hours[horizon_idx]

    print("\n  Information half-life (hours where MI drops to 50% of peak):")
    for ch in channels:
        print(f"    {ch:>14s}: {horizons[ch]:.1f}h")

    results = {
        'mi_curves': {ch: [float(v) for v in mi_curves[ch]] for ch in channels},
        'lag_hours': [float(h) for h in lag_hours],
        'information_horizons_hours': {ch: float(horizons[ch]) for ch in channels},
        'verdict': 'DIFFERENT_HORIZONS' if abs(horizons.get('supply_proxy', 0) - horizons.get('demand_proxy', 0)) > 1.0 else 'SIMILAR_HORIZONS'
    }

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: MI curves
        ax = axes[0]
        colors = {'glucose': '#2c3e50', 'iob': '#3498db', 'carbs': '#e74c3c',
                  'supply_proxy': '#e67e22', 'demand_proxy': '#9b59b6'}
        for ch in channels:
            ax.plot(lag_hours, mi_curves[ch], 'o-', color=colors[ch],
                    linewidth=2, markersize=4, label=ch)
        ax.set_xlabel('Lag (hours)')
        ax.set_ylabel('Mutual Information with dBG/dt (bits)')
        ax.set_title('EXP-1813: Information Horizon by Channel')
        ax.set_xscale('log')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        # Mark key timescales
        for h, label in [(1, '1h'), (6, '6h (DIA)'), (24, '24h'), (168, '7d')]:
            ax.axvline(h, color='gray', linestyle=':', alpha=0.3)

        # Right: Information horizon comparison
        ax = axes[1]
        ch_labels = ['Glucose', 'IOB', 'Carbs', 'Supply\nProxy', 'Demand\nProxy']
        horizon_vals = [horizons[ch] for ch in channels]
        bars = ax.barh(range(len(channels)), horizon_vals,
                       color=[colors[ch] for ch in channels], alpha=0.7, edgecolor='black')
        ax.set_yticks(range(len(channels)))
        ax.set_yticklabels(ch_labels)
        ax.set_xlabel('Information Half-Life (hours)')
        ax.set_title('How Far Back Does Each Channel Carry Information?')
        ax.grid(True, alpha=0.3, axis='x')
        # DIA reference
        ax.axvline(6, color='gray', linestyle='--', alpha=0.5, label='DIA (6h)')
        ax.legend()

        fig.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'symmetry-fig03-info-horizon.png'), dpi=150)
        plt.close(fig)
        print(f"  → Saved symmetry-fig03-info-horizon.png")

    return results


# ============================================================================
# EXP-1814: Supply-Demand Cross-Predictability
# ============================================================================
def exp_1814(patients, figures_dir=None):
    """Directed information: does supply predict demand, or vice versa?

    Uses conditional MI: I(S_past; D_future | D_past) measures how much EXTRA
    information past supply gives about future demand beyond what past demand
    already provides.
    """
    print("\n" + "=" * 70)
    print("EXP-1814: Supply-Demand Cross-Predictability")
    print("=" * 70)

    lags = [3, 6, 12, 24, 48, 72]  # 15min to 6h
    lag_labels = [f'{l*5/60:.1f}h' for l in lags]

    # Directed MI: S→D and D→S
    smi_s_to_d = {l: [] for l in lags}
    smi_d_to_s = {l: [] for l in lags}
    # Also: raw cross-correlation for comparison
    xcorr_results = []

    for p in patients:
        name = p['name']
        df = p['df']

        sd = compute_supply_demand(df)
        supply = sd['supply']
        demand = sd['demand']

        # Cross-correlation
        valid = np.isfinite(supply) & np.isfinite(demand)
        s_clean = supply[valid] - np.mean(supply[valid])
        d_clean = demand[valid] - np.mean(demand[valid])

        # Normalized cross-correlation at different lags
        xcorrs = {}
        for lag in lags:
            if lag >= len(s_clean) - 10:
                continue
            # S_past → D_future
            r_sd = safe_corr(s_clean[:-lag], d_clean[lag:])
            # D_past → S_future
            r_ds = safe_corr(d_clean[:-lag], s_clean[lag:])
            xcorrs[lag] = (r_sd, r_ds)

            # Directed MI via binned estimation
            # I(S_past; D_future | D_past) ≈ I(S_past; D_future) - I(D_past; D_future)
            mi_sd = safe_mi_binned(s_clean[:-lag], d_clean[lag:])
            mi_dd = safe_mi_binned(d_clean[:-lag], d_clean[lag:])
            mi_ds = safe_mi_binned(d_clean[:-lag], s_clean[lag:])
            mi_ss = safe_mi_binned(s_clean[:-lag], s_clean[lag:])

            directed_s_to_d = max(0, (mi_sd or 0) - (mi_dd or 0))
            directed_d_to_s = max(0, (mi_ds or 0) - (mi_ss or 0))

            smi_s_to_d[lag].append(directed_s_to_d)
            smi_d_to_s[lag].append(directed_d_to_s)

        xcorr_results.append({'name': name, 'xcorrs': xcorrs})

        # Print summary for this patient
        if 12 in xcorrs:
            r_sd, r_ds = xcorrs[12]
            print(f"  {name}: S→D r={r_sd:+.3f}  D→S r={r_ds:+.3f}  "
                  f"(at 1h lag)")

    # Population summary
    print("\n  Population Directed Information (bits):")
    print(f"  {'Lag':>6s}  {'S→D':>8s}  {'D→S':>8s}  {'Direction':>12s}")
    directions = []
    for lag, label in zip(lags, lag_labels):
        sd_mean = np.nanmean(smi_s_to_d[lag]) if smi_s_to_d[lag] else 0
        ds_mean = np.nanmean(smi_d_to_s[lag]) if smi_d_to_s[lag] else 0
        direction = 'S→D' if sd_mean > ds_mean else 'D→S'
        ratio = sd_mean / (ds_mean + 1e-6)
        directions.append({'lag': label, 's_to_d': sd_mean, 'd_to_s': ds_mean,
                           'direction': direction, 'ratio': ratio})
        print(f"  {label:>6s}  {sd_mean:>8.4f}  {ds_mean:>8.4f}  {direction:>12s}")

    results = {
        'directed_info': directions,
        'xcorr_population': {
            str(lag): {
                's_to_d': float(np.nanmean([x['xcorrs'].get(lag, (np.nan, np.nan))[0]
                                             for x in xcorr_results])),
                'd_to_s': float(np.nanmean([x['xcorrs'].get(lag, (np.nan, np.nan))[1]
                                             for x in xcorr_results]))
            } for lag in lags
        },
        'verdict': ('AID_LOOP_VISIBLE' if any(d['s_to_d'] > 0.01 for d in directions)
                    else 'NO_DIRECTED_INFO')
    }

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: Directed info
        ax = axes[0]
        x = np.arange(len(lags))
        w = 0.35
        sd_vals = [np.nanmean(smi_s_to_d[l]) for l in lags]
        ds_vals = [np.nanmean(smi_d_to_s[l]) for l in lags]
        ax.bar(x - w/2, sd_vals, w, label='Supply → Demand', color='#e74c3c', alpha=0.7)
        ax.bar(x + w/2, ds_vals, w, label='Demand → Supply', color='#3498db', alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(lag_labels)
        ax.set_xlabel('Prediction Horizon')
        ax.set_ylabel('Directed Information (bits)')
        ax.set_title('EXP-1814: Supply↔Demand Cross-Prediction')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')

        # Right: Cross-correlation structure
        ax = axes[1]
        for xr in xcorr_results:
            sd_line = [xr['xcorrs'].get(l, (np.nan, np.nan))[0] for l in lags]
            ds_line = [xr['xcorrs'].get(l, (np.nan, np.nan))[1] for l in lags]
            ax.plot(lag_labels, sd_line, 'r-', alpha=0.2)
            ax.plot(lag_labels, ds_line, 'b-', alpha=0.2)
        # Population means
        sd_mean_line = [np.nanmean([xr['xcorrs'].get(l, (np.nan, np.nan))[0]
                                     for xr in xcorr_results]) for l in lags]
        ds_mean_line = [np.nanmean([xr['xcorrs'].get(l, (np.nan, np.nan))[1]
                                     for xr in xcorr_results]) for l in lags]
        ax.plot(lag_labels, sd_mean_line, 'r-o', linewidth=2.5, label='S→D (mean)')
        ax.plot(lag_labels, ds_mean_line, 'b-o', linewidth=2.5, label='D→S (mean)')
        ax.axhline(0, color='gray', linestyle='--', alpha=0.5)
        ax.set_xlabel('Lag')
        ax.set_ylabel('Cross-Correlation')
        ax.set_title('Cross-Correlation Structure (AID Loop Signature)')
        ax.legend()
        ax.grid(True, alpha=0.3)

        fig.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'symmetry-fig04-cross-predict.png'), dpi=150)
        plt.close(fig)
        print(f"  → Saved symmetry-fig04-cross-predict.png")

    return results


# ============================================================================
# EXP-1815: Multi-Scale Variance Ratio
# ============================================================================
def exp_1815(patients, figures_dir=None):
    """Decompose glucose variance by timescale and attribute to supply vs demand.

    Uses Haar wavelet decomposition at multiple scales.  At each scale, compute
    what fraction of wavelet coefficients correlate with supply vs demand proxies.
    """
    print("\n" + "=" * 70)
    print("EXP-1815: Multi-Scale Variance Ratio")
    print("=" * 70)

    # Scales in powers of 2 (in steps)
    scales = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]
    scale_hours = [s * 5 / 60 for s in scales]
    scale_labels = [f'{h:.1f}h' if h < 24 else f'{h/24:.0f}d' for h in scale_hours]

    variance_ratios = []  # per patient: {scale: (supply_frac, demand_frac)}

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values.astype(np.float64)

        sd = compute_supply_demand(df)
        supply = sd['supply']
        demand = sd['demand']

        patient_ratios = {}

        for scale in scales:
            # Haar wavelet: difference of adjacent averages at this scale
            n = len(glucose) - len(glucose) % (2 * scale)
            if n < 4 * scale:
                continue

            # Compute wavelet coefficients at this scale
            g = glucose[:n]
            s = supply[:n]
            d = demand[:n]

            # Reshape into blocks of size 2*scale
            g_blocks = g[:n].reshape(-1, 2 * scale)
            s_blocks = s[:n].reshape(-1, 2 * scale)
            d_blocks = d[:n].reshape(-1, 2 * scale)

            # Haar wavelet coeff = mean(second half) - mean(first half)
            g_coeffs = np.nanmean(g_blocks[:, scale:], axis=1) - np.nanmean(g_blocks[:, :scale], axis=1)
            s_coeffs = np.nanmean(s_blocks[:, scale:], axis=1) - np.nanmean(s_blocks[:, :scale], axis=1)
            d_coeffs = np.nanmean(d_blocks[:, scale:], axis=1) - np.nanmean(d_blocks[:, :scale], axis=1)

            valid = np.isfinite(g_coeffs) & np.isfinite(s_coeffs) & np.isfinite(d_coeffs)
            if valid.sum() < 10:
                continue

            # Variance at this scale
            g_var = np.var(g_coeffs[valid])
            if g_var < 1e-6:
                continue

            # R² of supply and demand with glucose wavelet coeffs
            r_supply = safe_corr(s_coeffs[valid], g_coeffs[valid]) ** 2
            r_demand = safe_corr(d_coeffs[valid], g_coeffs[valid]) ** 2

            patient_ratios[scale] = {
                'supply_r2': float(r_supply),
                'demand_r2': float(r_demand),
                'total_variance': float(g_var)
            }

        variance_ratios.append({'name': name, 'ratios': patient_ratios})

    # Population summary
    print("\n  Supply vs Demand R² with Glucose Wavelet Coefficients:")
    print(f"  {'Scale':>8s}  {'Supply R²':>10s}  {'Demand R²':>10s}  {'Dominant':>10s}")

    pop_supply_r2 = []
    pop_demand_r2 = []
    valid_scale_labels = []
    for scale, label in zip(scales, scale_labels):
        sr2_vals = [vr['ratios'].get(scale, {}).get('supply_r2', np.nan) for vr in variance_ratios]
        dr2_vals = [vr['ratios'].get(scale, {}).get('demand_r2', np.nan) for vr in variance_ratios]
        sr2 = np.nanmean(sr2_vals)
        dr2 = np.nanmean(dr2_vals)
        if np.isnan(sr2) or np.isnan(dr2):
            continue
        pop_supply_r2.append(sr2)
        pop_demand_r2.append(dr2)
        valid_scale_labels.append(label)
        dominant = 'SUPPLY' if sr2 > dr2 else 'DEMAND'
        print(f"  {label:>8s}  {sr2:>10.3f}  {dr2:>10.3f}  {dominant:>10s}")

    # Find crossover point
    crossover = None
    for i in range(1, len(pop_supply_r2)):
        if pop_supply_r2[i - 1] > pop_demand_r2[i - 1] and pop_supply_r2[i] <= pop_demand_r2[i]:
            crossover = valid_scale_labels[i]
            break
        elif pop_supply_r2[i - 1] <= pop_demand_r2[i - 1] and pop_supply_r2[i] > pop_demand_r2[i]:
            crossover = valid_scale_labels[i]
            break

    if crossover:
        print(f"\n  → Crossover point: ~{crossover} (where dominant channel switches)")
    else:
        print(f"\n  → No clear crossover detected")

    results = {
        'scale_labels': valid_scale_labels,
        'supply_r2': [float(v) for v in pop_supply_r2],
        'demand_r2': [float(v) for v in pop_demand_r2],
        'crossover': crossover,
        'verdict': 'SCALE_DEPENDENT' if crossover else 'SINGLE_DOMINANT'
    }

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: Supply vs demand R² by scale
        ax = axes[0]
        x = np.arange(len(valid_scale_labels))
        ax.plot(x, pop_supply_r2, 'r-o', linewidth=2, markersize=6, label='Supply R²')
        ax.plot(x, pop_demand_r2, 'b-o', linewidth=2, markersize=6, label='Demand R²')
        if crossover:
            ci = valid_scale_labels.index(crossover)
            ax.axvline(ci, color='green', linestyle='--', alpha=0.7, label=f'Crossover (~{crossover})')
        ax.fill_between(x, pop_supply_r2, pop_demand_r2,
                        where=[s > d for s, d in zip(pop_supply_r2, pop_demand_r2)],
                        alpha=0.1, color='red', label='Supply dominant')
        ax.fill_between(x, pop_supply_r2, pop_demand_r2,
                        where=[s <= d for s, d in zip(pop_supply_r2, pop_demand_r2)],
                        alpha=0.1, color='blue', label='Demand dominant')
        ax.set_xticks(x)
        ax.set_xticklabels(valid_scale_labels, rotation=45)
        ax.set_xlabel('Timescale')
        ax.set_ylabel('R² with Glucose Wavelet Coefficients')
        ax.set_title('EXP-1815: Who Controls Glucose at Each Timescale?')
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

        # Right: Per-patient variance decomposition at 1h scale
        ax = axes[1]
        target_scale = 12  # 1h
        names = []
        sr2_vals = []
        dr2_vals = []
        for vr in variance_ratios:
            if target_scale in vr['ratios']:
                names.append(vr['name'])
                sr2_vals.append(vr['ratios'][target_scale]['supply_r2'])
                dr2_vals.append(vr['ratios'][target_scale]['demand_r2'])
        if names:
            x = np.arange(len(names))
            ax.bar(x - 0.175, sr2_vals, 0.35, label='Supply R²', color='#e74c3c', alpha=0.7)
            ax.bar(x + 0.175, dr2_vals, 0.35, label='Demand R²', color='#3498db', alpha=0.7)
            ax.set_xticks(x)
            ax.set_xticklabels(names)
            ax.set_ylabel('R² at 1-hour Scale')
            ax.set_title('Per-Patient: Supply vs Demand at 1h Timescale')
            ax.legend()
            ax.grid(True, alpha=0.3, axis='y')

        fig.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'symmetry-fig05-multiscale.png'), dpi=150)
        plt.close(fig)
        print(f"  → Saved symmetry-fig05-multiscale.png")

    return results


# ============================================================================
# EXP-1816: Conservation Law Residual Analysis
# ============================================================================
def exp_1816(patients, figures_dir=None):
    """Analyze residuals from the conservation law: dBG/dt - (supply - demand).

    If the physics model captures all supply and demand, residuals should be
    white noise.  Any remaining structure reveals missing channels.
    """
    print("\n" + "=" * 70)
    print("EXP-1816: Conservation Law Residual Analysis")
    print("=" * 70)

    residual_stats = []

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values.astype(np.float64)
        dbg = np.concatenate([[0], np.diff(glucose)])

        sd = compute_supply_demand(df)
        net_model = sd['net']  # supply - demand from model
        residual = dbg - net_model

        valid = np.isfinite(residual)
        r = residual[valid]

        if len(r) < 100:
            continue

        # Test for whiteness: Ljung-Box-like via autocorrelation
        acf = np.correlate(r - np.mean(r), r - np.mean(r), 'full')
        acf = acf[len(acf)//2:] / acf[len(acf)//2]

        # Spectral analysis of residuals
        freqs, psd = sig.welch(r, fs=12.0, nperseg=min(512, len(r) // 4))
        # Spectral slope: white noise = 0, colored noise != 0
        mask = freqs > 0.01
        if mask.sum() > 3:
            spectral_slope = np.polyfit(np.log10(freqs[mask]), np.log10(psd[mask] + 1e-10), 1)[0]
        else:
            spectral_slope = np.nan

        # Cross-correlation with supply/demand (should be ~0 if model is complete)
        supply_xcorr = safe_corr(r, sd['supply'][valid])
        demand_xcorr = safe_corr(r, sd['demand'][valid])

        # Autocorrelation at key lags
        acf_summary = {}
        for lag in [1, 6, 12, 36, 72, 288]:
            if lag < len(acf):
                acf_summary[lag] = float(acf[lag])

        stat = {
            'name': name,
            'mean_residual': float(np.mean(r)),
            'std_residual': float(np.std(r)),
            'skewness': float(stats.skew(r)),
            'kurtosis': float(stats.kurtosis(r)),
            'spectral_slope': float(spectral_slope),
            'supply_xcorr': float(supply_xcorr),
            'demand_xcorr': float(demand_xcorr),
            'acf': acf_summary,
            'whiteness': 'white' if np.abs(spectral_slope) < 0.3 else 'colored'
        }
        residual_stats.append(stat)

        print(f"  {name}: μ={np.mean(r):.2f}  σ={np.std(r):.2f}  slope={spectral_slope:.3f}"
              f"  r(supply)={supply_xcorr:.3f}  r(demand)={demand_xcorr:.3f}"
              f"  {'WHITE' if abs(spectral_slope) < 0.3 else 'COLORED'}")

    # Population summary
    white_count = sum(1 for s in residual_stats if s['whiteness'] == 'white')
    mean_slope = np.mean([s['spectral_slope'] for s in residual_stats])
    mean_supply_xcorr = np.mean([s['supply_xcorr'] for s in residual_stats])
    mean_demand_xcorr = np.mean([s['demand_xcorr'] for s in residual_stats])

    print(f"\n  Population: {white_count}/{len(residual_stats)} patients have white residuals")
    print(f"  Mean spectral slope: {mean_slope:.3f} (0=white noise)")
    print(f"  Mean residual×supply correlation: {mean_supply_xcorr:.3f}")
    print(f"  Mean residual×demand correlation: {mean_demand_xcorr:.3f}")

    if abs(mean_supply_xcorr) > 0.1:
        print(f"  ⚠ Residuals correlate with supply → model UNDER-estimates supply")
    if abs(mean_demand_xcorr) > 0.1:
        print(f"  ⚠ Residuals correlate with demand → model UNDER-estimates demand")

    results = {
        'per_patient': residual_stats,
        'white_fraction': white_count / len(residual_stats),
        'mean_spectral_slope': float(mean_slope),
        'mean_supply_xcorr': float(mean_supply_xcorr),
        'mean_demand_xcorr': float(mean_demand_xcorr),
        'missing_channel': ('supply' if abs(mean_supply_xcorr) > abs(mean_demand_xcorr)
                            else 'demand'),
        'verdict': 'MODEL_INCOMPLETE' if abs(mean_slope) > 0.3 else 'MODEL_ADEQUATE'
    }

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        # Top-left: residual spectral slope
        ax = axes[0, 0]
        names = [s['name'] for s in residual_stats]
        slopes = [s['spectral_slope'] for s in residual_stats]
        colors = ['#2ecc71' if abs(s) < 0.3 else '#e74c3c' for s in slopes]
        ax.barh(range(len(names)), slopes, color=colors, alpha=0.7, edgecolor='black')
        ax.axvline(0, color='black', linewidth=0.5)
        ax.axvline(-0.3, color='gray', linestyle='--', alpha=0.5)
        ax.axvline(0.3, color='gray', linestyle='--', alpha=0.5)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names)
        ax.set_xlabel('Spectral Slope (0 = white noise)')
        ax.set_title('EXP-1816: Residual Spectral Slope')

        # Top-right: residual correlation with supply/demand
        ax = axes[0, 1]
        x = np.arange(len(names))
        w = 0.35
        ax.bar(x - w/2, [s['supply_xcorr'] for s in residual_stats],
               w, label='r(residual, supply)', color='#e74c3c', alpha=0.7)
        ax.bar(x + w/2, [s['demand_xcorr'] for s in residual_stats],
               w, label='r(residual, demand)', color='#3498db', alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.axhline(0, color='gray', linestyle='--', alpha=0.5)
        ax.set_ylabel('Correlation')
        ax.set_title('Residual × Model Channel Correlation')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')

        # Bottom-left: ACF of residuals (population mean)
        ax = axes[1, 0]
        lag_range = [1, 3, 6, 12, 24, 36, 72, 144, 288]
        lag_mins = [l * 5 for l in lag_range]
        for s in residual_stats:
            acf_vals = [s['acf'].get(l, np.nan) for l in lag_range]
            ax.plot(lag_mins, acf_vals, 'o-', alpha=0.3, markersize=3)
        ax.axhline(0, color='gray', linestyle='--', alpha=0.5)
        ax.set_xlabel('Lag (minutes)')
        ax.set_ylabel('Autocorrelation')
        ax.set_title('Residual Autocorrelation (should be ~0 for complete model)')
        ax.grid(True, alpha=0.3)

        # Bottom-right: kurtosis vs skewness
        ax = axes[1, 1]
        skews = [s['skewness'] for s in residual_stats]
        kurts = [s['kurtosis'] for s in residual_stats]
        ax.scatter(skews, kurts, s=80, c='#3498db', alpha=0.7, edgecolor='black')
        for i, name in enumerate(names):
            ax.annotate(name, (skews[i], kurts[i]), fontsize=8, ha='center', va='bottom')
        ax.axvline(0, color='gray', linestyle='--', alpha=0.3)
        ax.axhline(0, color='gray', linestyle='--', alpha=0.3)
        ax.set_xlabel('Skewness')
        ax.set_ylabel('Excess Kurtosis')
        ax.set_title('Residual Distribution Shape\n(Gaussian = 0,0)')
        ax.grid(True, alpha=0.3)

        fig.suptitle('EXP-1816: Conservation Law Residual Analysis', fontsize=14, fontweight='bold', y=1.01)
        fig.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'symmetry-fig06-residuals.png'), dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  → Saved symmetry-fig06-residuals.png")

    return results


# ============================================================================
# EXP-1817: Split-Loss Information Experiment
# ============================================================================
def exp_1817(patients, figures_dir=None):
    """Train simple linear models with supply-only and demand-only loss.

    Instead of training ML models (expensive), we use a tractable proxy:
    linear regression with different WEIGHTING of samples.
    - Supply-weighted: weight ∝ max(0, dBG) (upweight rising glucose)
    - Demand-weighted: weight ∝ max(0, -dBG) (upweight falling glucose)

    For each weighting, at different history windows, compute R² on held-out
    data for both rising and falling periods.  This tells us:
    1. Do supply and demand models learn different features?
    2. At what window lengths does each model perform best?
    3. Is there complementary information?
    """
    print("\n" + "=" * 70)
    print("EXP-1817: Split-Loss Information Experiment")
    print("=" * 70)

    windows = [12, 36, 72, 144, 288, 576, 864]  # 1h to 3d
    window_labels = [f'{w*5/60:.0f}h' if w < 288 else f'{w/288:.0f}d' for w in windows]

    results_by_window = {w: {'supply_on_rise': [], 'supply_on_fall': [],
                              'demand_on_rise': [], 'demand_on_fall': [],
                              'uniform_on_rise': [], 'uniform_on_fall': []}
                         for w in windows}

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values.astype(np.float64)
        iob = df['iob'].values.astype(np.float64) if 'iob' in df.columns else np.zeros(len(df))
        carbs = df['carbs'].values.astype(np.float64) if 'carbs' in df.columns else np.zeros(len(df))
        cob = df['cob'].values.astype(np.float64) if 'cob' in df.columns else np.zeros(len(df))

        dbg = np.concatenate([[0], np.diff(glucose)])
        target = dbg  # predict rate of change

        for window in windows:
            if window >= len(glucose) - 100:
                continue

            # Build feature matrix: aggregated features over window
            n = len(glucose) - window
            X = np.zeros((n, 6))
            for i in range(n):
                idx = slice(i, i + window)
                g = glucose[idx]
                valid_g = g[np.isfinite(g)]
                if len(valid_g) < 3:
                    X[i] = np.nan
                    continue
                X[i, 0] = np.nanmean(g)  # mean glucose in window
                X[i, 1] = np.nanstd(g)   # glucose variability
                X[i, 2] = np.nanmean(iob[idx])  # mean IOB
                X[i, 3] = np.nansum(carbs[idx])  # total carbs
                X[i, 4] = g[-1] - g[0] if np.isfinite(g[-1]) and np.isfinite(g[0]) else 0  # trend
                X[i, 5] = np.nanmean(cob[idx])  # mean COB

            y = target[window:]
            valid = np.all(np.isfinite(X), axis=1) & np.isfinite(y)
            if valid.sum() < 100:
                continue

            X_v = X[valid]
            y_v = y[valid]

            # Split train/test
            n_train = int(0.7 * len(X_v))
            X_train, X_test = X_v[:n_train], X_v[n_train:]
            y_train, y_test = y_v[:n_train], y_v[n_train:]

            # Rising/falling masks for evaluation
            rise_test = y_test > 0
            fall_test = y_test < 0

            if rise_test.sum() < 20 or fall_test.sum() < 20:
                continue

            # Three models: supply-weighted, demand-weighted, uniform
            def weighted_lstsq(X, y, w):
                Xw = X * np.sqrt(w)[:, None]
                yw = y * np.sqrt(w)
                try:
                    beta = np.linalg.lstsq(Xw, yw, rcond=None)[0]
                    return beta
                except:
                    return np.zeros(X.shape[1])

            # Supply weight: upweight rising
            w_supply = np.maximum(y_train, 0) + 0.1  # minimum weight
            # Demand weight: upweight falling
            w_demand = np.maximum(-y_train, 0) + 0.1
            # Uniform
            w_uniform = np.ones(len(y_train))

            beta_supply = weighted_lstsq(X_train, y_train, w_supply)
            beta_demand = weighted_lstsq(X_train, y_train, w_demand)
            beta_uniform = weighted_lstsq(X_train, y_train, w_uniform)

            # Evaluate on test set
            pred_supply = X_test @ beta_supply
            pred_demand = X_test @ beta_demand
            pred_uniform = X_test @ beta_uniform

            def r2(y_true, y_pred):
                ss_res = np.sum((y_true - y_pred) ** 2)
                ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
                return 1 - ss_res / ss_tot if ss_tot > 0 else 0

            results_by_window[window]['supply_on_rise'].append(r2(y_test[rise_test], pred_supply[rise_test]))
            results_by_window[window]['supply_on_fall'].append(r2(y_test[fall_test], pred_supply[fall_test]))
            results_by_window[window]['demand_on_rise'].append(r2(y_test[rise_test], pred_demand[rise_test]))
            results_by_window[window]['demand_on_fall'].append(r2(y_test[fall_test], pred_demand[fall_test]))
            results_by_window[window]['uniform_on_rise'].append(r2(y_test[rise_test], pred_uniform[rise_test]))
            results_by_window[window]['uniform_on_fall'].append(r2(y_test[fall_test], pred_uniform[fall_test]))

        print(f"  {name}: computed split-loss R² at {len(windows)} windows")

    # Summarize
    print("\n  Split-Loss R² by Window Length:")
    print(f"  {'Window':>8s}  {'S→Rise':>8s}  {'S→Fall':>8s}  {'D→Rise':>8s}  {'D→Fall':>8s}  {'U→Rise':>8s}  {'U→Fall':>8s}")

    summary = {}
    for w, label in zip(windows, window_labels):
        r = results_by_window[w]
        row = {}
        for key in ['supply_on_rise', 'supply_on_fall', 'demand_on_rise', 'demand_on_fall',
                     'uniform_on_rise', 'uniform_on_fall']:
            row[key] = float(np.nanmean(r[key])) if r[key] else np.nan
        summary[label] = row
        print(f"  {label:>8s}  {row['supply_on_rise']:>8.3f}  {row['supply_on_fall']:>8.3f}"
              f"  {row['demand_on_rise']:>8.3f}  {row['demand_on_fall']:>8.3f}"
              f"  {row['uniform_on_rise']:>8.3f}  {row['uniform_on_fall']:>8.3f}")

    # Key metric: does supply model improve with longer windows differently than demand?
    supply_horizon_benefit = []
    demand_horizon_benefit = []
    for w, label in zip(windows, window_labels):
        r = summary[label]
        # Supply model's advantage on rise vs fall
        if not np.isnan(r.get('supply_on_rise', np.nan)) and not np.isnan(r.get('supply_on_fall', np.nan)):
            supply_horizon_benefit.append(r['supply_on_rise'] - r['supply_on_fall'])
            demand_horizon_benefit.append(r['demand_on_fall'] - r['demand_on_rise'])

    print(f"\n  Supply model specialization (rise-fall R²): "
          f"{np.mean(supply_horizon_benefit):.3f} avg")
    print(f"  Demand model specialization (fall-rise R²): "
          f"{np.mean(demand_horizon_benefit):.3f} avg")

    results = {
        'summary': summary,
        'supply_specialization': float(np.mean(supply_horizon_benefit)),
        'demand_specialization': float(np.mean(demand_horizon_benefit)),
        'verdict': ('COMPLEMENTARY' if (np.mean(supply_horizon_benefit) > 0.01 and
                                         np.mean(demand_horizon_benefit) > 0.01)
                    else 'NO_SPECIALIZATION')
    }

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(18, 5))

        # Left: Supply model on rise vs fall
        ax = axes[0]
        x = np.arange(len(window_labels))
        rise_vals = [summary.get(l, {}).get('supply_on_rise', np.nan) for l in window_labels]
        fall_vals = [summary.get(l, {}).get('supply_on_fall', np.nan) for l in window_labels]
        ax.plot(x, rise_vals, 'r-o', linewidth=2, label='Supply model → rising BG')
        ax.plot(x, fall_vals, 'r--s', linewidth=2, alpha=0.5, label='Supply model → falling BG')
        ax.set_xticks(x)
        ax.set_xticklabels(window_labels, rotation=45)
        ax.set_ylabel('R²')
        ax.set_title('Supply-Weighted Model')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        # Middle: Demand model
        ax = axes[1]
        rise_vals = [summary.get(l, {}).get('demand_on_rise', np.nan) for l in window_labels]
        fall_vals = [summary.get(l, {}).get('demand_on_fall', np.nan) for l in window_labels]
        ax.plot(x, rise_vals, 'b--s', linewidth=2, alpha=0.5, label='Demand model → rising BG')
        ax.plot(x, fall_vals, 'b-o', linewidth=2, label='Demand model → falling BG')
        ax.set_xticks(x)
        ax.set_xticklabels(window_labels, rotation=45)
        ax.set_ylabel('R²')
        ax.set_title('Demand-Weighted Model')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        # Right: Specialization by window
        ax = axes[2]
        if supply_horizon_benefit and demand_horizon_benefit:
            valid_labels = window_labels[:len(supply_horizon_benefit)]
            x2 = np.arange(len(valid_labels))
            w = 0.35
            ax.bar(x2 - w/2, supply_horizon_benefit, w, label='Supply specialization',
                   color='#e74c3c', alpha=0.7)
            ax.bar(x2 + w/2, demand_horizon_benefit, w, label='Demand specialization',
                   color='#3498db', alpha=0.7)
            ax.set_xticks(x2)
            ax.set_xticklabels(valid_labels, rotation=45)
        ax.axhline(0, color='gray', linestyle='--', alpha=0.5)
        ax.set_ylabel('R² Advantage on Matched Direction')
        ax.set_title('Do Split Losses Learn Different Things?')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')

        fig.suptitle('EXP-1817: Split-Loss Supply vs Demand Models', fontsize=14, fontweight='bold')
        fig.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'symmetry-fig07-split-loss.png'), dpi=150)
        plt.close(fig)
        print(f"  → Saved symmetry-fig07-split-loss.png")

    return results


# ============================================================================
# EXP-1818: Symmetry Breaking Points
# ============================================================================
def exp_1818(patients, figures_dir=None):
    """Identify when supply and demand information DIVERGE most.

    Sliding window cross-correlation between supply and demand proxies.
    Windows where correlation drops indicate "symmetry breaking events"
    where one channel changes independently.
    """
    print("\n" + "=" * 70)
    print("EXP-1818: Symmetry Breaking Points")
    print("=" * 70)

    window_size = 72  # 6h sliding window
    event_types = defaultdict(list)

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values.astype(np.float64)
        carbs = df['carbs'].values.astype(np.float64) if 'carbs' in df.columns else np.zeros(len(df))
        iob = df['iob'].values.astype(np.float64) if 'iob' in df.columns else np.zeros(len(df))

        sd = compute_supply_demand(df)
        supply = sd['supply']
        demand = sd['demand']
        ctx = classify_metabolic_context(df, sd)

        # Sliding window correlation
        n = len(supply)
        correlations = np.full(n, np.nan)
        for i in range(window_size, n):
            s_win = supply[i - window_size:i]
            d_win = demand[i - window_size:i]
            valid = np.isfinite(s_win) & np.isfinite(d_win)
            if valid.sum() > 20:
                correlations[i] = safe_corr(s_win[valid], d_win[valid])

        # Find symmetry breaking events: correlation drops below -0.2 or above 0.8
        # (high positive = coupled AID response; negative/low = decoupled)
        valid_corr = correlations[np.isfinite(correlations)]
        if len(valid_corr) < 100:
            continue

        q25 = np.percentile(valid_corr, 25)
        q75 = np.percentile(valid_corr, 75)

        # Classify events at correlation extremes
        for i in range(window_size, n):
            if np.isnan(correlations[i]):
                continue
            if correlations[i] < q25:  # Low correlation = decoupled
                event_types['decoupled'].append({
                    'patient': name,
                    'context': ctx[i],
                    'correlation': float(correlations[i]),
                    'glucose': float(glucose[i]) if np.isfinite(glucose[i]) else np.nan,
                    'has_carbs': bool(np.any(carbs[max(0, i-36):i] > 1)),
                    'iob': float(iob[i]) if np.isfinite(iob[i]) else np.nan
                })
            elif correlations[i] > q75:  # High correlation = tightly coupled
                event_types['coupled'].append({
                    'patient': name,
                    'context': ctx[i],
                    'correlation': float(correlations[i]),
                    'glucose': float(glucose[i]) if np.isfinite(glucose[i]) else np.nan,
                    'has_carbs': bool(np.any(carbs[max(0, i-36):i] > 1)),
                    'iob': float(iob[i]) if np.isfinite(iob[i]) else np.nan
                })

        print(f"  {name}: median r(S,D)={np.nanmedian(valid_corr):.3f}"
              f"  IQR=[{q25:.3f}, {q75:.3f}]"
              f"  n_decoupled={sum(1 for e in event_types['decoupled'] if e['patient'] == name)}")

    # Analyze what contexts produce decoupled vs coupled
    print("\n  Context distribution at symmetry breaking points:")
    for event_type in ['decoupled', 'coupled']:
        events = event_types[event_type]
        if not events:
            continue
        ctx_counts = defaultdict(int)
        for e in events:
            ctx_counts[e['context']] += 1
        total = sum(ctx_counts.values())
        print(f"\n  {event_type.upper()} events (n={total}):")
        for ctx, count in sorted(ctx_counts.items(), key=lambda x: -x[1]):
            print(f"    {ctx:15s}: {count:6d} ({count/total*100:5.1f}%)")

    # Glucose level at decoupled vs coupled
    decoupled_glucose = [e['glucose'] for e in event_types['decoupled'] if np.isfinite(e['glucose'])]
    coupled_glucose = [e['glucose'] for e in event_types['coupled'] if np.isfinite(e['glucose'])]
    print(f"\n  Glucose at decoupled events: {np.nanmean(decoupled_glucose):.0f} mg/dL"
          f" (vs coupled: {np.nanmean(coupled_glucose):.0f} mg/dL)")

    # Meal involvement
    decoupled_meal_frac = np.mean([e['has_carbs'] for e in event_types['decoupled']])
    coupled_meal_frac = np.mean([e['has_carbs'] for e in event_types['coupled']])
    print(f"  Meal-involved: decoupled {decoupled_meal_frac:.0%} vs coupled {coupled_meal_frac:.0%}")

    results = {
        'n_decoupled': len(event_types['decoupled']),
        'n_coupled': len(event_types['coupled']),
        'decoupled_mean_glucose': float(np.nanmean(decoupled_glucose)) if decoupled_glucose else np.nan,
        'coupled_mean_glucose': float(np.nanmean(coupled_glucose)) if coupled_glucose else np.nan,
        'decoupled_meal_fraction': float(decoupled_meal_frac),
        'coupled_meal_fraction': float(coupled_meal_frac),
        'context_distribution': {
            event_type: dict(sorted(
                {ctx: sum(1 for e in events if e['context'] == ctx)
                 for ctx in set(e['context'] for e in events)}.items(),
                key=lambda x: -x[1]))
            for event_type, events in event_types.items()
        },
        'verdict': ('MEALS_BREAK_SYMMETRY' if decoupled_meal_frac > coupled_meal_frac + 0.1
                    else 'SYMMETRY_CONTEXT_INDEPENDENT')
    }

    if figures_dir:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: Context distribution at symmetry breaking
        ax = axes[0]
        contexts = ['fasting', 'post_meal', 'correction', 'hypo_recovery', 'other']
        ctx_labels = ['Fasting', 'Post-Meal', 'Correction', 'Hypo', 'Other']
        decoupled_fracs = []
        coupled_fracs = []
        for c in contexts:
            d_count = sum(1 for e in event_types['decoupled'] if e['context'] == c)
            c_count = sum(1 for e in event_types['coupled'] if e['context'] == c)
            d_total = len(event_types['decoupled']) or 1
            c_total = len(event_types['coupled']) or 1
            decoupled_fracs.append(d_count / d_total)
            coupled_fracs.append(c_count / c_total)
        x = np.arange(len(contexts))
        w = 0.35
        ax.bar(x - w/2, decoupled_fracs, w, label='Decoupled (symmetry broken)',
               color='#e74c3c', alpha=0.7)
        ax.bar(x + w/2, coupled_fracs, w, label='Coupled (symmetric)',
               color='#3498db', alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(ctx_labels, rotation=15)
        ax.set_ylabel('Fraction of Events')
        ax.set_title('What Breaks Supply-Demand Symmetry?')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')

        # Right: Glucose distribution at breaking points
        ax = axes[1]
        if decoupled_glucose and coupled_glucose:
            bins = np.linspace(40, 350, 50)
            ax.hist(decoupled_glucose, bins=bins, alpha=0.6, color='#e74c3c',
                    density=True, label=f'Decoupled (μ={np.nanmean(decoupled_glucose):.0f})')
            ax.hist(coupled_glucose, bins=bins, alpha=0.6, color='#3498db',
                    density=True, label=f'Coupled (μ={np.nanmean(coupled_glucose):.0f})')
            ax.axvline(70, color='red', linestyle='--', alpha=0.5, label='Hypo threshold')
            ax.axvline(180, color='orange', linestyle='--', alpha=0.5, label='Hyper threshold')
        ax.set_xlabel('Glucose (mg/dL)')
        ax.set_ylabel('Density')
        ax.set_title('Glucose Level at Symmetry Breaking')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        fig.suptitle('EXP-1818: Where Supply and Demand Decouple', fontsize=14, fontweight='bold')
        fig.tight_layout()
        fig.savefig(os.path.join(figures_dir, 'symmetry-fig08-breaking.png'), dpi=150)
        plt.close(fig)
        print(f"  → Saved symmetry-fig08-breaking.png")

    return results


# ============================================================================
# Main
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description="EXP-1811–1818: Glucose Symmetry & Information Decomposition")
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    parser.add_argument('--exp', type=int, nargs='*', help='Run specific experiments (e.g., --exp 1811 1812)')
    parser.add_argument('--data-dir', default='externals/ns-data/patients/', help='Patient data directory')
    args = parser.parse_args()

    figures_dir = None
    if args.figures:
        figures_dir = 'docs/60-research/figures'
        os.makedirs(figures_dir, exist_ok=True)

    print("=" * 70)
    print("EXP-1811–1818: Glucose Signal Symmetry & Information Decomposition")
    print("=" * 70)

    patients = load_patients(args.data_dir)
    print(f"Loaded {len(patients)} patients\n")

    experiments = {
        1811: ('Time-Reversal Asymmetry', exp_1811),
        1812: ('Rising vs Falling Spectral Signatures', exp_1812),
        1813: ('Information Horizon by Channel', exp_1813),
        1814: ('Supply-Demand Cross-Predictability', exp_1814),
        1815: ('Multi-Scale Variance Ratio', exp_1815),
        1816: ('Conservation Law Residual Analysis', exp_1816),
        1817: ('Split-Loss Information Experiment', exp_1817),
        1818: ('Symmetry Breaking Points', exp_1818),
    }

    run_ids = args.exp if args.exp else sorted(experiments.keys())

    all_results = {}
    for eid in run_ids:
        if eid not in experiments:
            print(f"Unknown experiment: EXP-{eid}")
            continue
        name, func = experiments[eid]
        print(f"\n{'#' * 70}")
        print(f"# Running EXP-{eid}: {name}")
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
    output_path = 'externals/experiments/exp-1811_symmetry_info_decomposition.json'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Convert numpy types for JSON
    def convert(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, dict): return {k: convert(v) for k, v in obj.items()}
        if isinstance(obj, list): return [convert(v) for v in obj]
        return obj

    with open(output_path, 'w') as f:
        json.dump(convert({
            'experiment': 'EXP-1811 to EXP-1818',
            'title': 'Glucose Signal Symmetry and Information Decomposition',
            'results': all_results
        }), f, indent=2)
    print(f"\n✓ Results saved to {output_path}")

    # Print synthesis
    print("\n" + "=" * 70)
    print("SYNTHESIS: Information Structure of Glucose Data")
    print("=" * 70)
    for eid, result in all_results.items():
        verdict = result.get('verdict', result.get('error', 'N/A'))
        print(f"  {eid}: {verdict}")

    print("\n✓ All experiments complete")


if __name__ == '__main__':
    main()
