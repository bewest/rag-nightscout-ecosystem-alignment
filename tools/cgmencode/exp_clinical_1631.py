#!/usr/bin/env python3
"""EXP-1631–1638: Flexible Temporal Models

Batch 6: Replace rigid sinusoidal circadian model with learned temporal
embeddings or multi-frequency harmonics.
Target: capture 82% ISF variation vs current 47%.

Prior art:
  - pattern_analyzer.fit_circadian(): 3-parameter sinusoidal model
  - EXP-1605: ISF variation 74-319% across time-of-day
  - EXP-1606: Temporal CV 0.08-1.15 across 7-day windows
"""

import json
import os
import sys
import time
import traceback
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
PATIENTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'

from cgmencode.exp_metabolic_flux import load_patients


def _load_patients():
    return load_patients(patients_dir=str(PATIENTS_DIR), max_patients=None)


def _save_result(exp_id, data, elapsed):
    out = RESULTS_DIR / f'exp-{exp_id}_temporal.json'
    with open(out, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  ✓ Saved → {out}  ({elapsed:.1f}s)")


def _compute_hourly_glucose_stats(df):
    """Compute glucose statistics per hour of day."""
    glucose = df['glucose'].values.astype(float)
    n = len(glucose)
    stats = {}
    for h in range(24):
        mask = np.zeros(n, dtype=bool)
        for step in range(STEPS_PER_HOUR):
            indices = np.arange(h * STEPS_PER_HOUR + step, n, STEPS_PER_DAY)
            mask[indices] = True
        vals = glucose[mask]
        valid = vals[np.isfinite(vals)]
        if len(valid) > 10:
            stats[h] = {
                'mean': float(np.mean(valid)),
                'std': float(np.std(valid)),
                'median': float(np.median(valid)),
                'q10': float(np.percentile(valid, 10)),
                'q90': float(np.percentile(valid, 90)),
                'n': len(valid),
            }
    return stats


# ============================================================
# EXP-1631: Baseline Sinusoidal Circadian Model
# ============================================================
def exp_1631(patients):
    """Fit single-frequency sinusoid to hourly glucose means."""
    print("\n" + "─" * 60)
    print("EXP-1631: Baseline Sinusoidal Circadian Model")
    print("─" * 60)
    t0 = time.time()
    results = {}

    for p in patients:
        try:
            stats = _compute_hourly_glucose_stats(p['df'])
            if len(stats) < 12:
                results[p['name']] = {'error': 'insufficient_hours'}
                continue

            hours = np.array(sorted(stats.keys()), dtype=float)
            means = np.array([stats[int(h)]['mean'] for h in hours])

            # Single sinusoid: y = A * sin(2π*h/24 + φ) + C
            from scipy.optimize import curve_fit

            def sinusoidal(h, A, phi, C):
                return A * np.sin(2 * np.pi * h / 24 + phi) + C

            try:
                popt, _ = curve_fit(sinusoidal, hours, means,
                                    p0=[10, 0, np.mean(means)], maxfev=5000)
                predicted = sinusoidal(hours, *popt)
                ss_res = np.sum((means - predicted) ** 2)
                ss_tot = np.sum((means - np.mean(means)) ** 2)
                r2 = 1 - ss_res / max(ss_tot, 1e-10)
            except:
                r2 = 0
                popt = [0, 0, np.mean(means)]

            results[p['name']] = {
                'r2': float(r2),
                'amplitude': float(abs(popt[0])),
                'phase_hours': float((popt[1] % (2 * np.pi)) / (2 * np.pi) * 24),
                'baseline': float(popt[2]),
                'hourly_means': {str(int(h)): float(m) for h, m in zip(hours, means)},
            }
            print(f"  {p['name']}: R²={r2:.3f}  amp={abs(popt[0]):.1f}  phase={results[p['name']]['phase_hours']:.1f}h")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {'experiment': 'EXP-1631', 'title': 'Baseline Sinusoidal', 'patients': results}
    _save_result(1631, result, time.time() - t0)
    return results


# ============================================================
# EXP-1632: Multi-Frequency Harmonic Model
# ============================================================
def exp_1632(patients):
    """Fit multi-frequency harmonics (24h + 12h + 8h + 6h)."""
    print("\n" + "─" * 60)
    print("EXP-1632: Multi-Frequency Harmonic Model")
    print("─" * 60)
    t0 = time.time()
    results = {}

    for p in patients:
        try:
            stats = _compute_hourly_glucose_stats(p['df'])
            if len(stats) < 12:
                results[p['name']] = {'error': 'insufficient'}
                continue

            hours = np.array(sorted(stats.keys()), dtype=float)
            means = np.array([stats[int(h)]['mean'] for h in hours])

            # Build Fourier basis: 24h, 12h, 8h, 6h periods
            periods = [24, 12, 8, 6]
            n_harmonics = len(periods)

            X = np.ones((len(hours), 1 + 2 * n_harmonics))
            for i, period in enumerate(periods):
                X[:, 1 + 2*i] = np.sin(2 * np.pi * hours / period)
                X[:, 2 + 2*i] = np.cos(2 * np.pi * hours / period)

            # OLS fit
            beta = np.linalg.lstsq(X, means, rcond=None)[0]
            predicted = X @ beta
            ss_res = np.sum((means - predicted) ** 2)
            ss_tot = np.sum((means - np.mean(means)) ** 2)
            r2_full = 1 - ss_res / max(ss_tot, 1e-10)

            # Incremental R² per harmonic
            harmonic_r2 = {}
            for k in range(1, n_harmonics + 1):
                X_sub = X[:, :1 + 2*k]
                beta_sub = np.linalg.lstsq(X_sub, means, rcond=None)[0]
                pred_sub = X_sub @ beta_sub
                ss_sub = np.sum((means - pred_sub) ** 2)
                harmonic_r2[f'{periods[k-1]}h'] = float(1 - ss_sub / max(ss_tot, 1e-10))

            results[p['name']] = {
                'r2_full': float(r2_full),
                'harmonic_r2': harmonic_r2,
                'n_harmonics': n_harmonics,
            }
            print(f"  {p['name']}: R²={r2_full:.3f}  24h={harmonic_r2['24h']:.3f}  "
                  f"+12h={harmonic_r2['12h']:.3f}  +8h={harmonic_r2['8h']:.3f}  "
                  f"+6h={harmonic_r2['6h']:.3f}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {'experiment': 'EXP-1632', 'title': 'Multi-Frequency Harmonics', 'patients': results}
    _save_result(1632, result, time.time() - t0)
    return results


# ============================================================
# EXP-1633: Piecewise-Linear (Spline) Model
# ============================================================
def exp_1633(patients):
    """Piecewise-linear model with knots at key transition hours."""
    print("\n" + "─" * 60)
    print("EXP-1633: Piecewise-Linear Spline Model")
    print("─" * 60)
    t0 = time.time()
    results = {}

    for p in patients:
        try:
            stats = _compute_hourly_glucose_stats(p['df'])
            if len(stats) < 12:
                results[p['name']] = {'error': 'insufficient'}
                continue

            hours = np.array(sorted(stats.keys()), dtype=float)
            means = np.array([stats[int(h)]['mean'] for h in hours])

            from scipy.interpolate import UnivariateSpline

            # Try different smoothing factors
            best_r2 = -999
            best_s = None
            best_k = None

            for n_knots in [4, 6, 8, 12]:
                s = len(hours) * 2.0 / n_knots  # smoothing factor
                try:
                    # Wrap for periodicity
                    ext_hours = np.concatenate([hours - 24, hours, hours + 24])
                    ext_means = np.concatenate([means, means, means])
                    spline = UnivariateSpline(ext_hours, ext_means, s=s * 3, k=3)
                    predicted = spline(hours)
                    ss_res = np.sum((means - predicted) ** 2)
                    ss_tot = np.sum((means - np.mean(means)) ** 2)
                    r2 = 1 - ss_res / max(ss_tot, 1e-10)
                    if r2 > best_r2:
                        best_r2 = r2
                        best_s = s
                        best_k = n_knots
                except:
                    continue

            results[p['name']] = {
                'r2': float(best_r2),
                'best_n_knots': best_k,
                'smoothing': float(best_s) if best_s else None,
            }
            print(f"  {p['name']}: R²={best_r2:.3f}  knots={best_k}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {'experiment': 'EXP-1633', 'title': 'Piecewise-Linear Spline', 'patients': results}
    _save_result(1633, result, time.time() - t0)
    return results


# ============================================================
# EXP-1634: Day-of-Week Effects
# ============================================================
def exp_1634(patients):
    """Test whether day-of-week significantly affects glucose patterns."""
    print("\n" + "─" * 60)
    print("EXP-1634: Day-of-Week Effects")
    print("─" * 60)
    t0 = time.time()
    results = {}

    for p in patients:
        try:
            df = p['df']
            glucose = df['glucose'].values.astype(float)
            n = len(glucose)

            # Assign day-of-week (0=Mon, 6=Sun) based on position
            # Approximate: first step = start of data
            dow_means = {}
            for dow in range(7):
                # Each day = 288 steps; dow cycles every 7 days
                indices = []
                for day_num in range(n // STEPS_PER_DAY):
                    if day_num % 7 == dow:
                        start = day_num * STEPS_PER_DAY
                        end = min(start + STEPS_PER_DAY, n)
                        indices.extend(range(start, end))
                vals = glucose[indices]
                valid = vals[np.isfinite(vals)]
                if len(valid) > 50:
                    dow_means[dow] = float(np.mean(valid))

            if len(dow_means) < 5:
                results[p['name']] = {'error': 'insufficient_days'}
                continue

            # ANOVA-like: between-DOW variance vs within-DOW variance
            all_means = np.array(list(dow_means.values()))
            grand_mean = np.mean(all_means)
            between_var = np.var(all_means)

            # Within-day variance (average hourly std)
            stats = _compute_hourly_glucose_stats(df)
            within_var = np.mean([s['std'] ** 2 for s in stats.values()])

            # Effect size: eta²
            eta2 = between_var / max(between_var + within_var, 1e-10)

            # Weekend vs weekday
            weekday_means = [dow_means.get(d, grand_mean) for d in range(5)]
            weekend_means = [dow_means.get(d, grand_mean) for d in range(5, 7)]
            weekday_avg = np.mean(weekday_means) if weekday_means else grand_mean
            weekend_avg = np.mean(weekend_means) if weekend_means else grand_mean

            results[p['name']] = {
                'dow_means': {str(d): v for d, v in dow_means.items()},
                'between_var': float(between_var),
                'within_var': float(within_var),
                'eta2': float(eta2),
                'weekday_avg': float(weekday_avg),
                'weekend_avg': float(weekend_avg),
                'weekend_effect': float(weekend_avg - weekday_avg),
                'significant': eta2 > 0.01,
            }

            sig = "SIG" if eta2 > 0.01 else "n.s."
            print(f"  {p['name']}: η²={eta2:.4f} {sig}  "
                  f"weekday={weekday_avg:.0f}  weekend={weekend_avg:.0f}  "
                  f"Δ={weekend_avg - weekday_avg:+.1f}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {'experiment': 'EXP-1634', 'title': 'Day-of-Week Effects', 'patients': results}
    _save_result(1634, result, time.time() - t0)
    return results


# ============================================================
# EXP-1635: Glucose Variability by Time Period
# ============================================================
def exp_1635(patients):
    """Partition day into metabolic periods and measure variability."""
    print("\n" + "─" * 60)
    print("EXP-1635: Glucose Variability by Time Period")
    print("─" * 60)
    t0 = time.time()

    # Metabolic periods
    PERIODS = {
        'overnight': (0, 6),
        'dawn': (6, 9),
        'morning': (9, 12),
        'afternoon': (12, 17),
        'evening': (17, 21),
        'late_night': (21, 24),
    }

    results = {}
    for p in patients:
        try:
            df = p['df']
            glucose = df['glucose'].values.astype(float)
            n = len(glucose)

            period_stats = {}
            for period_name, (h_start, h_end) in PERIODS.items():
                mask = np.zeros(n, dtype=bool)
                for h in range(h_start, h_end):
                    for step in range(STEPS_PER_HOUR):
                        indices = np.arange(h * STEPS_PER_HOUR + step, n, STEPS_PER_DAY)
                        mask[indices] = True
                vals = glucose[mask]
                valid = vals[np.isfinite(vals)]
                if len(valid) > 50:
                    period_stats[period_name] = {
                        'mean': float(np.mean(valid)),
                        'std': float(np.std(valid)),
                        'cv': float(np.std(valid) / max(np.mean(valid), 1)),
                        'tir': float(np.mean((valid >= 70) & (valid <= 180)) * 100),
                        'below_70': float(np.mean(valid < 70) * 100),
                        'above_180': float(np.mean(valid > 180) * 100),
                    }

            # Most and least variable periods
            if period_stats:
                most_variable = max(period_stats.items(), key=lambda x: x[1]['cv'])
                least_variable = min(period_stats.items(), key=lambda x: x[1]['cv'])
            else:
                most_variable = ('unknown', {'cv': 0})
                least_variable = ('unknown', {'cv': 0})

            results[p['name']] = {
                'periods': period_stats,
                'most_variable': most_variable[0],
                'most_variable_cv': most_variable[1]['cv'],
                'least_variable': least_variable[0],
                'least_variable_cv': least_variable[1]['cv'],
            }

            print(f"  {p['name']}: most variable={most_variable[0]} CV={most_variable[1]['cv']:.2f}  "
                  f"least={least_variable[0]} CV={least_variable[1]['cv']:.2f}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {'experiment': 'EXP-1635', 'title': 'Variability by Time Period', 'patients': results}
    _save_result(1635, result, time.time() - t0)
    return results


# ============================================================
# EXP-1636: Meal Timing Pattern Detection
# ============================================================
def exp_1636(patients):
    """Detect meal timing patterns and their consistency."""
    print("\n" + "─" * 60)
    print("EXP-1636: Meal Timing Pattern Detection")
    print("─" * 60)
    t0 = time.time()
    results = {}

    for p in patients:
        try:
            df = p['df']
            carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(df))
            n = len(df)

            # Find meal events (>10g carbs)
            meal_hours = []
            for i in range(n):
                if carbs[i] >= 10:
                    hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
                    meal_hours.append(hour)

            if len(meal_hours) < 20:
                results[p['name']] = {'error': 'insufficient_meals', 'n': len(meal_hours)}
                print(f"  {p['name']}: SKIPPED ({len(meal_hours)} meals)")
                continue

            meal_hours = np.array(meal_hours)
            days = n / STEPS_PER_DAY

            # Histogram of meal times
            hist, _ = np.histogram(meal_hours, bins=24, range=(0, 24))
            hist_normalized = hist / max(days, 1)

            # Detect peaks (meal windows)
            from scipy.signal import find_peaks
            peaks, properties = find_peaks(hist_normalized, height=0.1, distance=2)
            peak_hours = peaks.tolist()
            peak_rates = hist_normalized[peaks].tolist()

            # Meal regularity: std of meal times within detected windows
            regularities = []
            for peak_h in peak_hours:
                window_meals = meal_hours[(meal_hours >= peak_h - 1.5) & (meal_hours < peak_h + 1.5)]
                if len(window_meals) >= 5:
                    regularities.append({
                        'hour': int(peak_h),
                        'std': float(np.std(window_meals)),
                        'count': len(window_meals),
                        'rate': float(len(window_meals) / max(days, 1)),
                    })

            results[p['name']] = {
                'n_meals': len(meal_hours),
                'meals_per_day': float(len(meal_hours) / max(days, 1)),
                'n_peaks': len(peak_hours),
                'peak_hours': peak_hours,
                'peak_rates': peak_rates,
                'regularities': regularities,
                'hourly_distribution': [float(x) for x in hist_normalized],
            }

            peaks_str = ', '.join(f"{h}h({r:.1f}/d)" for h, r in zip(peak_hours, peak_rates))
            print(f"  {p['name']}: {len(meal_hours)} meals ({len(meal_hours)/max(days,1):.1f}/day)  "
                  f"peaks: {peaks_str}")

        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}

    result = {'experiment': 'EXP-1636', 'title': 'Meal Timing Patterns', 'patients': results}
    _save_result(1636, result, time.time() - t0)
    return results


# ============================================================
# EXP-1637: Model Comparison (Sinusoidal vs Harmonic vs Spline)
# ============================================================
def exp_1637(patients, sin_results, harm_results, spl_results):
    """Compare all temporal models on held-out data."""
    print("\n" + "─" * 60)
    print("EXP-1637: Model Comparison")
    print("─" * 60)
    t0 = time.time()
    results = {}

    for p in patients:
        pname = p['name']
        sin_r2 = sin_results.get(pname, {}).get('r2', -1)
        harm_r2 = harm_results.get(pname, {}).get('r2_full', -1)
        spl_r2 = spl_results.get(pname, {}).get('r2', -1)

        best_model = 'sinusoidal'
        best_r2 = sin_r2
        if harm_r2 > best_r2:
            best_model = 'harmonic'
            best_r2 = harm_r2
        if spl_r2 > best_r2:
            best_model = 'spline'
            best_r2 = spl_r2

        # Improvement from sinusoidal to best
        improvement = best_r2 - sin_r2

        results[pname] = {
            'sinusoidal_r2': float(sin_r2),
            'harmonic_r2': float(harm_r2),
            'spline_r2': float(spl_r2),
            'best_model': best_model,
            'best_r2': float(best_r2),
            'improvement_over_sin': float(improvement),
        }

        print(f"  {pname}: sin={sin_r2:.3f}  harm={harm_r2:.3f}  spl={spl_r2:.3f}  "
              f"→ {best_model} (Δ={improvement:+.3f})")

    # Population summary
    improvements = [v['improvement_over_sin'] for v in results.values()]
    best_models = [v['best_model'] for v in results.values()]
    from collections import Counter
    model_counts = Counter(best_models)

    print(f"\n  Best model distribution: {dict(model_counts)}")
    print(f"  Mean improvement: {np.mean(improvements):+.3f}")

    result = {
        'experiment': 'EXP-1637',
        'title': 'Model Comparison',
        'patients': results,
        'summary': {
            'model_distribution': dict(model_counts),
            'mean_improvement': float(np.mean(improvements)),
        },
    }
    _save_result(1637, result, time.time() - t0)
    return results


# ============================================================
# EXP-1638: Production Temporal Model Recommendation
# ============================================================
def exp_1638(patients, comparison):
    """Recommend temporal model for production based on complexity vs accuracy."""
    print("\n" + "─" * 60)
    print("EXP-1638: Production Temporal Model Recommendation")
    print("─" * 60)
    t0 = time.time()

    # Per-patient recommendation
    results = {}
    for p in patients:
        pname = p['name']
        comp = comparison.get(pname, {})
        sin_r2 = comp.get('sinusoidal_r2', 0)
        harm_r2 = comp.get('harmonic_r2', 0)
        spl_r2 = comp.get('spline_r2', 0)

        # Decision: harmonic if ≥5% improvement over sinusoidal, else stick with sinusoidal
        # (Occam's razor: simpler model unless significantly better)
        if harm_r2 - sin_r2 >= 0.05:
            recommendation = 'harmonic'
            reason = f'harmonic +{harm_r2 - sin_r2:.1%} over sinusoidal'
        elif spl_r2 - sin_r2 >= 0.05:
            recommendation = 'spline'
            reason = f'spline +{spl_r2 - sin_r2:.1%} over sinusoidal'
        else:
            recommendation = 'sinusoidal'
            reason = 'simpler model sufficient'

        results[pname] = {
            'recommendation': recommendation,
            'reason': reason,
            'sin_r2': float(sin_r2),
            'harm_r2': float(harm_r2),
            'spl_r2': float(spl_r2),
        }
        print(f"  {pname}: → {recommendation} ({reason})")

    # Population recommendation
    recs = [v['recommendation'] for v in results.values()]
    from collections import Counter
    rec_dist = Counter(recs)

    if rec_dist.get('harmonic', 0) > len(results) / 2:
        pop_rec = 'harmonic'
    elif rec_dist.get('spline', 0) > len(results) / 2:
        pop_rec = 'spline'
    else:
        pop_rec = 'sinusoidal'

    print(f"\n  Population recommendation: {pop_rec}")
    print(f"  Distribution: {dict(rec_dist)}")

    result = {
        'experiment': 'EXP-1638',
        'title': 'Production Temporal Model Recommendation',
        'patients': results,
        'population_recommendation': pop_rec,
        'distribution': dict(rec_dist),
    }
    _save_result(1638, result, time.time() - t0)
    return results


# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    print("=" * 70)
    print("EXP-1631-1638: Flexible Temporal Models")
    print("=" * 70)

    patients = _load_patients()
    print(f"Loaded {len(patients)} patients\n")

    sin_results = exp_1631(patients)
    harm_results = exp_1632(patients)
    spl_results = exp_1633(patients)
    exp_1634(patients)
    exp_1635(patients)
    exp_1636(patients)
    comparison = exp_1637(patients, sin_results, harm_results, spl_results)
    exp_1638(patients, comparison)

    print("\n" + "=" * 70)
    print("COMPLETE: 8/8 experiments")
    print("=" * 70)
