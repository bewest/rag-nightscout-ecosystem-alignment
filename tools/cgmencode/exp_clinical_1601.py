#!/usr/bin/env python3
"""EXP-1601–1608: ISF Estimation Under AID Feedback

Batch 3: State-space models to disentangle AID loop feedback from true ISF.
Target: recover usable ISF for the 45% of patients currently gated out.

Prior art:
  - EXP-1301: Response-curve ISF (R²=0.805, τ=2.0h) — current SOTA
  - EXP-1291: Deconfounding failed (total_insulin denominator degeneracy)
  - EXP-1551: Natural experiment census with quality scoring
  - ISF mismatch: effective=1.36× profile (mean across patients)
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

from cgmencode import exp_metabolic_441
from cgmencode.exp_metabolic_flux import load_patients


def _load_patients():
    return load_patients(patients_dir=str(PATIENTS_DIR), max_patients=None)


TAU_CANDIDATES = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]


def _find_corrections(df):
    """Find isolated correction boluses (carb-free, high BG)."""
    glucose = df['glucose'].values.astype(float)
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))
    n = len(glucose)

    corrections = []
    for i in range(12, n - 36):
        if bolus[i] < 0.3:
            continue
        if glucose[i] <= 150:
            continue
        # No carbs ±30 min
        carb_window = slice(max(0, i - 6), min(n, i + 6))
        if np.nansum(carbs[carb_window]) > 2:
            continue
        # No future boluses 3h
        if np.nansum(bolus[i+1:min(n, i + 36)]) > 0.5:
            continue
        # No future carbs 3h
        if np.nansum(carbs[i+1:min(n, i + 36)]) > 2:
            continue
        # Trajectory
        traj = glucose[i:min(n, i + 36)]
        valid = np.isfinite(traj)
        if valid.sum() < 18:
            continue
        corrections.append({
            'index': i,
            'bolus': float(bolus[i]),
            'bg_start': float(glucose[i]),
            'trajectory': traj,
            'valid_mask': valid,
        })
    return corrections


def _fit_response_curve(correction):
    """Fit exponential decay to correction trajectory. Returns best params."""
    traj = correction['trajectory']
    valid = correction['valid_mask']
    bg_start = correction['bg_start']
    bolus_size = correction['bolus']
    n = len(traj)
    t_hours = np.arange(n) * 5.0 / 60.0

    best_sse = np.inf
    best_tau = 2.0
    best_amp = 0.0

    for tau in TAU_CANDIDATES:
        basis = 1.0 - np.exp(-t_hours / tau)
        bv = basis[valid]
        tv = traj[valid] - bg_start
        denom = np.sum(bv ** 2)
        if denom < 1e-10:
            continue
        amp = -np.sum(bv * tv) / denom  # negative because corrections lower BG
        predicted = bg_start - amp * basis
        residuals = traj[valid] - predicted[valid]
        sse = float(np.sum(residuals ** 2))
        if sse < best_sse:
            best_sse = sse
            best_tau = tau
            best_amp = amp

    # R² of fit
    ss_tot = np.sum((traj[valid] - np.mean(traj[valid])) ** 2)
    r2 = 1 - best_sse / max(ss_tot, 1e-10)
    isf = best_amp / max(bolus_size, 0.01)

    return {
        'tau': best_tau,
        'amplitude': best_amp,
        'r2': float(r2),
        'isf': float(isf),
        'bolus': bolus_size,
        'bg_start': bg_start,
    }


def _get_basal_deviation(df, correction_idx, window_steps=36):
    """Compute total basal deviation from scheduled during correction window.
    
    Uses net_basal (actual - scheduled) if available, else temp_rate - median.
    """
    n = len(df)
    end = min(n, correction_idx + window_steps)
    
    if 'net_basal' in df.columns:
        net = df['net_basal'].values.astype(float)
        window = net[correction_idx:end]
        deviation = float(np.nansum(window) * 5.0 / 60.0)  # U over window
        scheduled = 0.0  # net_basal is already relative
        return deviation, scheduled
    elif 'temp_rate' in df.columns:
        rate = df['temp_rate'].values.astype(float)
        scheduled = float(np.nanmedian(rate))
        actual = rate[correction_idx:end]
        deviation = float(np.nansum(actual - scheduled) * 5.0 / 60.0)
        return deviation, scheduled
    return 0.0, 0.0


def _save_result(exp_id, data, elapsed):
    out = RESULTS_DIR / f'exp-{exp_id}_isf_aid.json'
    with open(out, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  ✓ Saved → {out}  ({elapsed:.1f}s)")


# ============================================================
# EXP-1601: Correction Census Under AID
# ============================================================
def exp_1601(patients):
    """Census of isolated correction events and AID loop interference."""
    print("\n" + "─" * 60)
    print("EXP-1601: Correction Census Under AID")
    print("─" * 60)
    t0 = time.time()

    results = {}
    all_corrections = {}

    for p in patients:
        try:
            df = p['df']
            corrections = _find_corrections(df)
            n_corr = len(corrections)

            # Compute basal deviations for each correction
            deviations = []
            for c in corrections:
                dev, sched = _get_basal_deviation(df, c['index'])
                c['basal_deviation'] = dev
                c['scheduled_basal'] = sched
                deviations.append(dev)

            # Characterize AID interference
            if deviations:
                mean_dev = float(np.mean(deviations))
                pct_negative = float(np.mean(np.array(deviations) < -0.05)) * 100
                pct_positive = float(np.mean(np.array(deviations) > 0.05)) * 100
            else:
                mean_dev = 0
                pct_negative = 0
                pct_positive = 0

            # Hours per correction (density)
            days = len(df) / STEPS_PER_DAY
            corr_per_day = n_corr / max(days, 1)

            results[p['name']] = {
                'n_corrections': n_corr,
                'corrections_per_day': corr_per_day,
                'mean_basal_deviation': mean_dev,
                'pct_basal_reduced': pct_negative,
                'pct_basal_increased': pct_positive,
                'mean_bolus_size': float(np.mean([c['bolus'] for c in corrections])) if corrections else 0,
                'mean_bg_start': float(np.mean([c['bg_start'] for c in corrections])) if corrections else 0,
            }
            all_corrections[p['name']] = corrections

            print(f"  {p['name']}: {n_corr} corrections ({corr_per_day:.1f}/day)  "
                  f"AID reduces basal {pct_negative:.0f}% of time  "
                  f"mean deviation={mean_dev:+.2f}U")
        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()
            results[p['name']] = {'error': str(e)}
            all_corrections[p['name']] = []

    result = {
        'experiment': 'EXP-1601',
        'title': 'Correction Census Under AID',
        'patients': results,
    }
    _save_result(1601, result, time.time() - t0)
    return all_corrections


# ============================================================
# EXP-1602: Response-Curve ISF Fitting
# ============================================================
def exp_1602(all_corrections):
    """Fit response curves to all corrections and characterize ISF."""
    print("\n" + "─" * 60)
    print("EXP-1602: Response-Curve ISF Fitting")
    print("─" * 60)
    t0 = time.time()

    results = {}
    all_fits = {}

    for pname, corrections in sorted(all_corrections.items()):
        fits = []
        for c in corrections:
            fit = _fit_response_curve(c)
            fit['basal_deviation'] = c.get('basal_deviation', 0)
            fits.append(fit)

        # Quality filter
        good_fits = [f for f in fits if f['r2'] > 0.3 and f['isf'] > 5 and f['isf'] < 500]
        all_fits[pname] = good_fits

        if good_fits:
            isfs = [f['isf'] for f in good_fits]
            taus = [f['tau'] for f in good_fits]
            r2s = [f['r2'] for f in good_fits]
            results[pname] = {
                'n_total': len(fits),
                'n_good': len(good_fits),
                'pass_rate': len(good_fits) / max(len(fits), 1),
                'isf_mean': float(np.mean(isfs)),
                'isf_median': float(np.median(isfs)),
                'isf_std': float(np.std(isfs)),
                'tau_mean': float(np.mean(taus)),
                'tau_median': float(np.median(taus)),
                'r2_mean': float(np.mean(r2s)),
                'r2_median': float(np.median(r2s)),
            }
            print(f"  {pname}: {len(good_fits)}/{len(fits)} good fits  "
                  f"ISF={np.median(isfs):.0f}±{np.std(isfs):.0f}  "
                  f"τ={np.median(taus):.1f}h  R²={np.median(r2s):.3f}")
        else:
            results[pname] = {'n_total': len(fits), 'n_good': 0, 'pass_rate': 0}
            print(f"  {pname}: 0/{len(fits)} good fits")

    result = {
        'experiment': 'EXP-1602',
        'title': 'Response-Curve ISF Fitting',
        'patients': results,
    }
    _save_result(1602, result, time.time() - t0)
    return all_fits


# ============================================================
# EXP-1603: AID Loop Feedback Quantification
# ============================================================
def exp_1603(all_corrections, all_fits):
    """Quantify how AID loop feedback biases ISF estimates."""
    print("\n" + "─" * 60)
    print("EXP-1603: AID Loop Feedback Quantification")
    print("─" * 60)
    t0 = time.time()

    results = {}

    for pname in sorted(all_fits.keys()):
        fits = all_fits[pname]
        if len(fits) < 5:
            results[pname] = {'error': 'insufficient_fits'}
            continue

        # Split by basal deviation: AID-damped vs AID-neutral
        deviations = np.array([f['basal_deviation'] for f in fits])
        isfs = np.array([f['isf'] for f in fits])
        taus = np.array([f['tau'] for f in fits])

        # AID damped: basal reduced by ≥0.05U during correction window
        damped_mask = deviations < -0.05
        neutral_mask = np.abs(deviations) <= 0.05
        boosted_mask = deviations > 0.05

        damped_isf = isfs[damped_mask] if damped_mask.sum() > 2 else np.array([])
        neutral_isf = isfs[neutral_mask] if neutral_mask.sum() > 2 else np.array([])
        boosted_isf = isfs[boosted_mask] if boosted_mask.sum() > 2 else np.array([])

        # ISF bias from AID feedback
        damped_mean = float(np.median(damped_isf)) if len(damped_isf) > 0 else None
        neutral_mean = float(np.median(neutral_isf)) if len(neutral_isf) > 0 else None
        boosted_mean = float(np.median(boosted_isf)) if len(boosted_isf) > 0 else None

        # Correlation: basal_deviation vs ISF estimate
        from scipy import stats as sp_stats
        if len(deviations) > 5:
            corr, pval = sp_stats.pearsonr(deviations, isfs)
        else:
            corr, pval = 0, 1

        # Feedback gain: how much does 1U basal reduction bias ISF?
        if len(deviations) > 5:
            from sklearn.linear_model import LinearRegression
            lr = LinearRegression().fit(deviations.reshape(-1, 1), isfs)
            feedback_gain = float(lr.coef_[0])
        else:
            feedback_gain = 0

        results[pname] = {
            'n_damped': int(damped_mask.sum()),
            'n_neutral': int(neutral_mask.sum()),
            'n_boosted': int(boosted_mask.sum()),
            'damped_isf_median': damped_mean,
            'neutral_isf_median': neutral_mean,
            'boosted_isf_median': boosted_mean,
            'aid_bias': (damped_mean - neutral_mean) if damped_mean and neutral_mean else None,
            'deviation_isf_corr': float(corr),
            'deviation_isf_pval': float(pval),
            'feedback_gain': feedback_gain,
        }

        bias_str = f"AID bias={results[pname]['aid_bias']:+.0f}" if results[pname]['aid_bias'] else "insufficient"
        print(f"  {pname}: damped={int(damped_mask.sum())} neutral={int(neutral_mask.sum())}  "
              f"r={corr:.3f} p={pval:.3f}  {bias_str}  gain={feedback_gain:.1f}")

    result = {
        'experiment': 'EXP-1603',
        'title': 'AID Loop Feedback Quantification',
        'patients': results,
    }
    _save_result(1603, result, time.time() - t0)
    return results


# ============================================================
# EXP-1604: State-Space ISF Estimation
# ============================================================
def exp_1604(patients, all_corrections, feedback_results):
    """State-space model: estimate true ISF correcting for AID feedback."""
    print("\n" + "─" * 60)
    print("EXP-1604: State-Space ISF Estimation")
    print("─" * 60)
    t0 = time.time()

    results = {}

    for p in patients:
        pname = p['name']
        fits = all_corrections.get(pname, [])
        fb = feedback_results.get(pname, {})

        if fb.get('error') or len(fits) < 5:
            results[pname] = {'error': 'insufficient_data'}
            print(f"  {pname}: SKIPPED — insufficient data")
            continue

        try:
            df = p['df']
            glucose = df['glucose'].values.astype(float)
            corrections = _find_corrections(df)

            # For each correction, compute AID-corrected ISF
            corrected_isfs = []
            raw_isfs = []

            for c in corrections:
                fit = _fit_response_curve(c)
                if fit['r2'] < 0.3 or fit['isf'] < 5 or fit['isf'] > 500:
                    continue

                raw_isfs.append(fit['isf'])

                # Correction: account for basal deviation
                # True insulin effect = bolus + basal_deviation (can be negative)
                dev, _ = _get_basal_deviation(df, c['index'])
                total_insulin = c['bolus'] + dev
                if total_insulin > 0.1:
                    # Corrected ISF: use amplitude / total_insulin
                    corrected_isf = fit['amplitude'] / total_insulin
                    if 5 < corrected_isf < 500:
                        corrected_isfs.append(corrected_isf)
                else:
                    # Denominator too small — use response-curve ISF
                    corrected_isfs.append(fit['isf'])

            if not corrected_isfs:
                results[pname] = {'error': 'no_valid_corrections'}
                print(f"  {pname}: no valid corrections after filtering")
                continue

            raw_median = float(np.median(raw_isfs))
            corrected_median = float(np.median(corrected_isfs))
            correction_factor = corrected_median / max(raw_median, 1)

            # Confidence based on sample size and consistency
            n = len(corrected_isfs)
            cv = np.std(corrected_isfs) / max(np.mean(corrected_isfs), 1)
            confidence = min(0.9, n / 30) * max(0.3, 1 - cv)

            results[pname] = {
                'n_corrections': n,
                'raw_isf_median': raw_median,
                'corrected_isf_median': corrected_median,
                'correction_factor': correction_factor,
                'raw_isf_std': float(np.std(raw_isfs)),
                'corrected_isf_std': float(np.std(corrected_isfs)),
                'cv': float(cv),
                'confidence': float(confidence),
            }

            print(f"  {pname}: raw ISF={raw_median:.0f}  corrected={corrected_median:.0f}  "
                  f"factor={correction_factor:.2f}  n={n}  conf={confidence:.2f}")

        except Exception as e:
            print(f"  {pname}: FAILED — {e}")
            traceback.print_exc()
            results[pname] = {'error': str(e)}

    result = {
        'experiment': 'EXP-1604',
        'title': 'State-Space ISF Estimation',
        'patients': results,
    }
    _save_result(1604, result, time.time() - t0)
    return results


# ============================================================
# EXP-1605: ISF by Time-of-Day Under AID
# ============================================================
def exp_1605(patients, all_corrections):
    """Estimate circadian ISF variation accounting for AID feedback."""
    print("\n" + "─" * 60)
    print("EXP-1605: ISF by Time-of-Day Under AID")
    print("─" * 60)
    t0 = time.time()

    results = {}

    for p in patients:
        pname = p['name']
        corrections = _find_corrections(p['df'])

        if len(corrections) < 10:
            results[pname] = {'error': 'insufficient_corrections'}
            print(f"  {pname}: SKIPPED — {len(corrections)} corrections")
            continue

        df = p['df']
        # Fit each correction
        hour_isf = {}  # hour -> list of ISFs
        for c in corrections:
            fit = _fit_response_curve(c)
            if fit['r2'] < 0.3 or fit['isf'] < 5 or fit['isf'] > 500:
                continue
            hour = int((c['index'] % STEPS_PER_DAY) / STEPS_PER_HOUR)
            if hour not in hour_isf:
                hour_isf[hour] = []
            hour_isf[hour].append(fit['isf'])

        # Compute ISF schedule
        isf_schedule = np.full(24, np.nan)
        isf_counts = np.zeros(24)
        for h in range(24):
            if h in hour_isf and len(hour_isf[h]) >= 2:
                isf_schedule[h] = float(np.median(hour_isf[h]))
                isf_counts[h] = len(hour_isf[h])

        # Fill gaps via interpolation
        valid = ~np.isnan(isf_schedule)
        if valid.sum() >= 3:
            from scipy.interpolate import interp1d
            valid_hours = np.where(valid)[0]
            valid_vals = isf_schedule[valid]
            # Wrap-around interpolation
            ext_hours = np.concatenate([valid_hours - 24, valid_hours, valid_hours + 24])
            ext_vals = np.concatenate([valid_vals, valid_vals, valid_vals])
            interp = interp1d(ext_hours, ext_vals, kind='linear', fill_value='extrapolate')
            isf_filled = interp(np.arange(24))
        else:
            isf_filled = isf_schedule.copy()

        # ISF variation
        valid_filled = isf_filled[np.isfinite(isf_filled)]
        if len(valid_filled) > 0:
            variation_pct = float((np.max(valid_filled) - np.min(valid_filled)) / np.mean(valid_filled) * 100)
            dawn_isf = float(np.nanmean(isf_filled[4:8]))
            evening_isf = float(np.nanmean(isf_filled[18:22]))
            dawn_phenomenon = dawn_isf < evening_isf * 0.8
        else:
            variation_pct = 0
            dawn_isf = 0
            evening_isf = 0
            dawn_phenomenon = False

        results[pname] = {
            'n_corrections': len(corrections),
            'hours_with_data': int(valid.sum()),
            'isf_schedule': [float(x) if np.isfinite(x) else None for x in isf_filled],
            'variation_pct': variation_pct,
            'dawn_isf': dawn_isf,
            'evening_isf': evening_isf,
            'dawn_phenomenon': dawn_phenomenon,
            'counts_by_hour': {str(h): int(c) for h, c in enumerate(isf_counts)},
        }

        dawn_str = "DAWN" if dawn_phenomenon else "none"
        print(f"  {pname}: {int(valid.sum())} hours covered  "
              f"variation={variation_pct:.0f}%  "
              f"dawn={dawn_isf:.0f} evening={evening_isf:.0f}  {dawn_str}")

    result = {
        'experiment': 'EXP-1605',
        'title': 'ISF by Time-of-Day Under AID',
        'patients': results,
    }
    _save_result(1605, result, time.time() - t0)
    return results


# ============================================================
# EXP-1606: ISF Stability Across Time Windows
# ============================================================
def exp_1606(patients, all_corrections):
    """Test ISF stability: compare 7-day sliding windows."""
    print("\n" + "─" * 60)
    print("EXP-1606: ISF Stability Across Time Windows")
    print("─" * 60)
    t0 = time.time()

    results = {}

    for p in patients:
        pname = p['name']
        corrections = _find_corrections(p['df'])

        if len(corrections) < 10:
            results[pname] = {'error': 'insufficient'}
            print(f"  {pname}: SKIPPED")
            continue

        # Fit all corrections with timestamps
        fits_with_time = []
        for c in corrections:
            fit = _fit_response_curve(c)
            if fit['r2'] > 0.3 and 5 < fit['isf'] < 500:
                fit['day'] = c['index'] / STEPS_PER_DAY
                fits_with_time.append(fit)

        if len(fits_with_time) < 5:
            results[pname] = {'error': 'insufficient_good_fits'}
            print(f"  {pname}: SKIPPED (good fits)")
            continue

        # Sliding 7-day windows
        days = np.array([f['day'] for f in fits_with_time])
        isfs = np.array([f['isf'] for f in fits_with_time])
        max_day = days.max()

        window_size = 7  # days
        step = 7  # days
        window_medians = []
        window_centers = []

        d = 0
        while d + window_size <= max_day:
            mask = (days >= d) & (days < d + window_size)
            if mask.sum() >= 3:
                window_medians.append(float(np.median(isfs[mask])))
                window_centers.append(d + window_size / 2)
            d += step

        if len(window_medians) >= 2:
            temporal_cv = float(np.std(window_medians) / max(np.mean(window_medians), 1))
            drift = float(np.corrcoef(window_centers, window_medians)[0, 1])
            stable = temporal_cv < 0.3
        else:
            temporal_cv = 0
            drift = 0
            stable = True

        results[pname] = {
            'n_windows': len(window_medians),
            'window_medians': window_medians,
            'temporal_cv': temporal_cv,
            'drift_correlation': drift,
            'stable': stable,
        }

        print(f"  {pname}: {len(window_medians)} windows  CV={temporal_cv:.2f}  "
              f"drift r={drift:.2f}  {'STABLE' if stable else 'UNSTABLE'}")

    result = {
        'experiment': 'EXP-1606',
        'title': 'ISF Stability Across Time Windows',
        'patients': results,
    }
    _save_result(1606, result, time.time() - t0)
    return results


# ============================================================
# EXP-1607: Profile ISF vs Effective ISF Comparison
# ============================================================
def exp_1607(patients, all_corrections, ss_results):
    """Compare profile ISF, raw curve ISF, and AID-corrected ISF."""
    print("\n" + "─" * 60)
    print("EXP-1607: Profile vs Effective ISF Comparison")
    print("─" * 60)
    t0 = time.time()

    results = {}

    for p in patients:
        pname = p['name']
        df = p['df']

        # Profile ISF from schedule
        isf_schedule = df.attrs.get('isf_schedule', [{'time': '00:00', 'value': 50}])
        if isinstance(isf_schedule, list):
            profile_isf = float(np.median([s['value'] for s in isf_schedule]))
        else:
            profile_isf = float(isf_schedule)

        # Raw response-curve ISF
        corrections = _find_corrections(df)
        raw_isfs = []
        for c in corrections:
            fit = _fit_response_curve(c)
            if fit['r2'] > 0.3 and 5 < fit['isf'] < 500:
                raw_isfs.append(fit['isf'])

        raw_median = float(np.median(raw_isfs)) if raw_isfs else None

        # AID-corrected ISF from EXP-1604
        ss = ss_results.get(pname, {})
        corrected_median = ss.get('corrected_isf_median', None)

        # Compute ratios
        raw_ratio = raw_median / max(profile_isf, 1) if raw_median else None
        corrected_ratio = corrected_median / max(profile_isf, 1) if corrected_median else None

        # Which ISF predicts fidelity better?
        # Use RMSE from supply-demand with each ISF
        results[pname] = {
            'profile_isf': profile_isf,
            'raw_curve_isf': raw_median,
            'corrected_isf': corrected_median,
            'raw_ratio': raw_ratio,
            'corrected_ratio': corrected_ratio,
            'n_corrections': len(raw_isfs),
            'mismatch_severity': 'high' if raw_ratio and raw_ratio > 2.0 else
                                 'moderate' if raw_ratio and raw_ratio > 1.5 else 'low',
        }

        rc = raw_ratio or 0
        raw_str = f"{raw_median:.0f}" if raw_median else "N/A"
        corr_str = f"{corrected_median:.0f}" if corrected_median else "N/A"
        print(f"  {pname}: profile={profile_isf:.0f}  raw_curve={raw_str:>5}  "
              f"corrected={corr_str:>5}  "
              f"ratio={rc:.2f}  mismatch={results[pname]['mismatch_severity']}")

    # Population summary
    raw_ratios = [v['raw_ratio'] for v in results.values() if v.get('raw_ratio')]
    corrected_ratios = [v['corrected_ratio'] for v in results.values() if v.get('corrected_ratio')]

    result = {
        'experiment': 'EXP-1607',
        'title': 'Profile vs Effective ISF Comparison',
        'patients': results,
        'population': {
            'mean_raw_ratio': float(np.mean(raw_ratios)) if raw_ratios else None,
            'mean_corrected_ratio': float(np.mean(corrected_ratios)) if corrected_ratios else None,
            'high_mismatch_count': sum(1 for v in results.values() if v.get('mismatch_severity') == 'high'),
        },
    }
    _save_result(1607, result, time.time() - t0)
    return results


# ============================================================
# EXP-1608: ISF Recovery for Gated Patients
# ============================================================
def exp_1608(patients, all_corrections, ss_results, feedback_results):
    """Attempt ISF recovery for patients who fail standard preconditions."""
    print("\n" + "─" * 60)
    print("EXP-1608: ISF Recovery for Gated Patients")
    print("─" * 60)
    t0 = time.time()

    # Preconditions from EXP-492/454/490: need ≥5 corrections
    STANDARD_MIN_CORRECTIONS = 5
    RELAXED_MIN_CORRECTIONS = 3

    results = {}

    for p in patients:
        pname = p['name']
        corrections = _find_corrections(p['df'])

        all_fits = []
        for c in corrections:
            fit = _fit_response_curve(c)
            fit['basal_deviation'] = c.get('basal_deviation', 0)
            all_fits.append(fit)

        good_standard = [f for f in all_fits if f['r2'] > 0.3 and 5 < f['isf'] < 500]
        good_relaxed = [f for f in all_fits if f['r2'] > 0.1 and 5 < f['isf'] < 800]

        passes_standard = len(good_standard) >= STANDARD_MIN_CORRECTIONS
        passes_relaxed = len(good_relaxed) >= RELAXED_MIN_CORRECTIONS

        # Recovery strategy: use AID-corrected ISF with relaxed quality
        recovered_isf = None
        recovery_method = 'none'
        confidence = 0.0

        if passes_standard:
            recovery_method = 'standard'
            recovered_isf = float(np.median([f['isf'] for f in good_standard]))
            confidence = min(0.9, len(good_standard) / 15)
        elif passes_relaxed:
            recovery_method = 'relaxed_quality'
            recovered_isf = float(np.median([f['isf'] for f in good_relaxed]))
            confidence = min(0.6, len(good_relaxed) / 15)
        elif len(all_fits) >= 2:
            # Last resort: use all fits with Winsorized median
            all_isfs = [f['isf'] for f in all_fits if f['isf'] > 0]
            if all_isfs:
                recovery_method = 'winsorized'
                # Winsorize: clip to [10th, 90th percentile]
                low = np.percentile(all_isfs, 10)
                high = np.percentile(all_isfs, 90)
                clipped = [max(low, min(high, x)) for x in all_isfs]
                recovered_isf = float(np.median(clipped))
                confidence = 0.3

        results[pname] = {
            'n_total_corrections': len(corrections),
            'n_good_standard': len(good_standard),
            'n_good_relaxed': len(good_relaxed),
            'passes_standard': passes_standard,
            'passes_relaxed': passes_relaxed,
            'recovery_method': recovery_method,
            'recovered_isf': recovered_isf,
            'confidence': confidence,
        }

        status = "✓" if passes_standard else "~" if passes_relaxed else "✗"
        isf_str = f"{recovered_isf:.0f}" if recovered_isf else "N/A"
        print(f"  {pname}: {status} {recovery_method}  "
              f"ISF={isf_str:>5}  "
              f"conf={confidence:.2f}  "
              f"({len(good_standard)} std / {len(good_relaxed)} relaxed)")

    # Recovery rates
    std_pass = sum(1 for v in results.values() if v['passes_standard'])
    relaxed_pass = sum(1 for v in results.values() if v['passes_relaxed'])
    any_recovery = sum(1 for v in results.values() if v['recovered_isf'] is not None)

    print(f"\n  Standard pass: {std_pass}/{len(results)}")
    print(f"  Relaxed pass: {relaxed_pass}/{len(results)}")
    print(f"  Any recovery: {any_recovery}/{len(results)}")

    result = {
        'experiment': 'EXP-1608',
        'title': 'ISF Recovery for Gated Patients',
        'patients': results,
        'summary': {
            'standard_pass_rate': std_pass / max(len(results), 1),
            'relaxed_pass_rate': relaxed_pass / max(len(results), 1),
            'any_recovery_rate': any_recovery / max(len(results), 1),
        },
    }
    _save_result(1608, result, time.time() - t0)
    return results


# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    print("=" * 70)
    print("EXP-1601-1608: ISF Estimation Under AID Feedback")
    print("=" * 70)

    patients = _load_patients()
    print(f"Loaded {len(patients)} patients\n")

    # EXP-1601: Census
    all_corrections = exp_1601(patients)

    # EXP-1602: Fit response curves
    all_fits = exp_1602(all_corrections)

    # EXP-1603: Quantify AID feedback
    feedback_results = exp_1603(all_corrections, all_fits)

    # EXP-1604: State-space ISF
    ss_results = exp_1604(patients, all_fits, feedback_results)

    # EXP-1605: ISF by time of day
    exp_1605(patients, all_corrections)

    # EXP-1606: ISF stability
    exp_1606(patients, all_corrections)

    # EXP-1607: Profile comparison
    exp_1607(patients, all_corrections, ss_results)

    # EXP-1608: Recovery for gated patients
    exp_1608(patients, all_corrections, ss_results, feedback_results)

    print("\n" + "=" * 70)
    print("COMPLETE: 8/8 experiments")
    print("=" * 70)
