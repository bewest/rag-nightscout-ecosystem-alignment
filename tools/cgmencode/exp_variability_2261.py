#!/usr/bin/env python3
"""
EXP-2261 through EXP-2268: Variability Source Decomposition
============================================================

Uses GPU-accelerated spectral analysis and parallel simulation to
decompose month-to-month therapy estimate variability into identifiable
sources: circadian, meal patterns, insulin sensitivity shifts.

EXP-2261: Spectral decomposition of glucose signal (GPU FFT)
EXP-2262: Supply vs demand variability separation
EXP-2263: Circadian harmonic encoding (4-harmonic time features)
EXP-2264: Autocorrelation across time scales (hours→months)
EXP-2265: Meal pattern regularity and its impact on estimates
EXP-2266: GPU Monte Carlo: parameter sensitivity landscape
EXP-2267: Information content by time scale (mutual information)
EXP-2268: Integrated variability attribution

Usage:
    PYTHONPATH=tools python3 tools/cgmencode/exp_variability_2261.py --figures
"""

import json
import os
import sys
import argparse
import warnings
import numpy as np
import time

warnings.filterwarnings('ignore')

# Try GPU
try:
    import torch
    HAS_CUDA = torch.cuda.is_available()
    if HAS_CUDA:
        DEVICE = torch.device('cuda')
        print(f'GPU: {torch.cuda.get_device_name(0)}')
    else:
        DEVICE = torch.device('cpu')
        print('No GPU available, using CPU')
except ImportError:
    HAS_CUDA = False
    DEVICE = None
    print('PyTorch not available, using numpy')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)


def load_patients(data_dir='externals/ns-data/patients/'):
    from cgmencode.exp_metabolic_441 import load_patients as _lp
    return _lp(data_dir)


def get_schedule_value(schedule, hour):
    if not schedule:
        return None
    val = None
    for entry in schedule:
        t = entry.get('timeAsSeconds', entry.get('time', 0))
        if isinstance(t, str):
            parts = t.split(':')
            t = int(parts[0]) * 3600
        entry_hour = t / 3600
        if entry_hour <= hour:
            val = entry.get('value', entry.get('rate', None))
    return val


def build_scheduled_array(schedule, hours):
    result = np.zeros(len(hours), dtype=np.float64)
    if not schedule:
        return result
    entries = []
    for entry in schedule:
        t = entry.get('timeAsSeconds', entry.get('time', 0))
        if isinstance(t, str):
            parts = t.split(':')
            t = int(parts[0]) * 3600
        entry_hour = t / 3600
        val = entry.get('value', entry.get('rate', 0))
        entries.append((entry_hour, val))
    entries.sort(key=lambda x: x[0])
    h_mod = hours % 24
    for i, (eh, ev) in enumerate(entries):
        if i < len(entries) - 1:
            mask = (h_mod >= eh) & (h_mod < entries[i + 1][0])
        else:
            mask = h_mod >= eh
        result[mask] = ev
    return result


def compute_actual_delivery(df_slice, scheduled):
    n = len(scheduled)
    actual = np.full(n, np.nan)
    if 'enacted_rate' in df_slice.columns:
        enacted = df_slice['enacted_rate'].values[:n]
        valid = ~np.isnan(enacted)
        actual[valid] = enacted[valid]
    if 'net_basal' in df_slice.columns:
        net = df_slice['net_basal'].values[:n]
        missing = np.isnan(actual)
        valid_net = ~np.isnan(net) & missing
        actual[valid_net] = scheduled[valid_net] + net[valid_net]
    still_missing = np.isnan(actual)
    actual[still_missing] = scheduled[still_missing]
    return actual


def interpolate_gaps(signal, max_gap=6):
    """Linear interpolation for small gaps in glucose signal."""
    result = signal.copy()
    nans = np.isnan(result)
    if not nans.any():
        return result
    not_nan = ~nans
    if not_nan.sum() < 2:
        return result
    indices = np.arange(len(result))
    result[nans] = np.interp(indices[nans], indices[not_nan], result[not_nan])
    # Zero out large gaps
    gap_starts = np.where(nans & ~np.roll(nans, 1))[0]
    for gs in gap_starts:
        ge = gs
        while ge < len(nans) and nans[ge]:
            ge += 1
        if ge - gs > max_gap:
            result[gs:ge] = 0
    return result


# ─────────────────────────────────────────────────────────────────
# EXP-2261: Spectral Decomposition (GPU FFT)
# ─────────────────────────────────────────────────────────────────
def exp_2261_spectral(patients):
    """Decompose glucose signal into frequency bands using GPU FFT."""
    results = {}
    t0 = time.time()

    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values.astype(np.float64)
        n = len(glucose)

        # Interpolate gaps for FFT
        signal = interpolate_gaps(glucose)
        signal = signal - np.mean(signal[signal != 0])  # zero-mean

        # Use GPU if available
        if HAS_CUDA:
            sig_t = torch.tensor(signal, dtype=torch.float32, device=DEVICE)
            fft_result = torch.fft.rfft(sig_t)
            power = torch.abs(fft_result).cpu().numpy() ** 2
        else:
            fft_result = np.fft.rfft(signal)
            power = np.abs(fft_result) ** 2

        freqs = np.fft.rfftfreq(n, d=1.0 / STEPS_PER_HOUR)  # cycles per hour

        # Define frequency bands
        # Ultra-low: <1/48h (multi-day patterns)
        # Circadian: 1/24h ± 50%
        # Meal: 1/4h to 1/1h (meal responses)
        # Fast: >1h (CGM noise, rapid glucose changes)
        total_power = np.sum(power[1:])  # exclude DC

        bands = {
            'ultra_low': (0, 1 / 48),       # >48h periods
            'circadian': (1 / 48, 1 / 8),   # 8-48h periods
            'meal': (1 / 8, 1 / 1),         # 1-8h periods
            'fast': (1 / 1, np.inf),         # <1h periods
        }

        band_power = {}
        for bname, (flo, fhi) in bands.items():
            mask = (freqs > flo) & (freqs <= fhi)
            bp = np.sum(power[mask])
            band_power[bname] = round(float(bp / total_power * 100), 1)

        # Dominant circadian harmonic
        circ_mask = (freqs > 1 / 30) & (freqs < 1 / 20)
        if circ_mask.any():
            circ_power_arr = power[circ_mask]
            circ_freqs = freqs[circ_mask]
            peak_idx = np.argmax(circ_power_arr)
            peak_period = 1 / circ_freqs[peak_idx] if circ_freqs[peak_idx] > 0 else 0
        else:
            peak_period = 0

        # Harmonic peaks (1/24h, 2/24h, 3/24h, 4/24h)
        harmonics = []
        for h in range(1, 5):
            target_freq = h / 24.0
            closest = np.argmin(np.abs(freqs - target_freq))
            harmonics.append({
                'harmonic': h,
                'period_hours': round(24.0 / h, 1),
                'power_pct': round(float(power[closest] / total_power * 100), 3),
            })

        results[name] = {
            'band_power': band_power,
            'dominant_circadian_period': round(float(peak_period), 1),
            'harmonics': harmonics,
            'total_power': round(float(total_power), 0),
            'cgm_coverage': round(float(np.mean(~np.isnan(glucose)) * 100), 1),
        }

    elapsed = time.time() - t0
    results['_meta'] = {'elapsed_seconds': round(elapsed, 2), 'device': 'cuda' if HAS_CUDA else 'cpu'}
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2262: Supply vs Demand Variability
# ─────────────────────────────────────────────────────────────────
def exp_2262_supply_demand(patients):
    """Separate insulin supply variability from glucose demand variability."""
    results = {}

    for pat in patients:
        name = pat['name']
        df = pat['df']
        n = len(df)
        attrs = df.attrs
        glucose = df['glucose'].values.astype(np.float64)
        n_days = int(n / STEPS_PER_DAY)

        # Supply: total insulin per day (bolus + basal)
        bolus = df['bolus'].values.astype(np.float64)
        bolus = np.where(np.isnan(bolus), 0, bolus)
        basal_sched = attrs.get('basal_schedule', [])
        hours = np.arange(n) / STEPS_PER_HOUR
        hod = hours % 24
        scheduled = build_scheduled_array(basal_sched, hod)
        actual_basal = compute_actual_delivery(df, scheduled)
        actual_basal = np.where(np.isnan(actual_basal), 0, actual_basal)

        daily_supply = []
        daily_demand = []
        daily_tir = []

        for d in range(n_days):
            s = d * STEPS_PER_DAY
            e = min(s + STEPS_PER_DAY, n)
            # Supply = total insulin (bolus + basal rate * 5min/60)
            day_bolus = np.sum(bolus[s:e])
            day_basal = np.sum(actual_basal[s:e]) / STEPS_PER_HOUR  # U/hr * steps / steps_per_hour = Units
            day_supply = day_bolus + day_basal

            # Demand = mean glucose (proxy for glucose excursion demand)
            g_day = glucose[s:e]
            valid_g = g_day[~np.isnan(g_day)]
            if len(valid_g) > STEPS_PER_HOUR:
                day_demand = float(np.mean(valid_g))
                day_tir = float(np.mean((valid_g >= 70) & (valid_g <= 180)) * 100)
            else:
                day_demand = np.nan
                day_tir = np.nan

            daily_supply.append(day_supply)
            daily_demand.append(day_demand)
            daily_tir.append(day_tir)

        supply = np.array(daily_supply)
        demand = np.array(daily_demand)
        tir = np.array(daily_tir)

        valid = ~np.isnan(demand) & (supply > 0)
        if valid.sum() < 7:
            results[name] = {'skip': True, 'reason': 'insufficient valid days'}
            continue

        supply_v = supply[valid]
        demand_v = demand[valid]
        tir_v = tir[valid]

        # Variability metrics
        supply_cv = float(np.std(supply_v) / np.mean(supply_v))
        demand_cv = float(np.std(demand_v) / np.mean(demand_v))

        # Correlation: does supply track demand?
        corr = float(np.corrcoef(supply_v, demand_v)[0, 1])

        # Weekly rolling supply/demand ratio
        weekly_ratio = []
        for w in range(0, len(supply_v) - 6):
            s_week = np.mean(supply_v[w:w + 7])
            d_week = np.mean(demand_v[w:w + 7])
            weekly_ratio.append(s_week / d_week if d_week > 0 else np.nan)

        ratio_cv = float(np.nanstd(weekly_ratio) / np.nanmean(weekly_ratio)) if weekly_ratio else None

        # Granger-like: does supply predict next-day demand?
        if len(supply_v) > 14:
            lag1_corr = float(np.corrcoef(supply_v[:-1], demand_v[1:])[0, 1])
            lag7_corr = float(np.corrcoef(supply_v[:-7], demand_v[7:])[0, 1])
        else:
            lag1_corr = None
            lag7_corr = None

        results[name] = {
            'n_days': int(valid.sum()),
            'supply_mean': round(float(np.mean(supply_v)), 1),
            'supply_cv': round(supply_cv, 3),
            'demand_mean': round(float(np.mean(demand_v)), 1),
            'demand_cv': round(demand_cv, 3),
            'supply_demand_corr': round(corr, 3),
            'ratio_cv': round(ratio_cv, 3) if ratio_cv else None,
            'lag1_corr': round(lag1_corr, 3) if lag1_corr is not None else None,
            'lag7_corr': round(lag7_corr, 3) if lag7_corr is not None else None,
            'tir_mean': round(float(np.mean(tir_v)), 1),
            'tir_cv': round(float(np.std(tir_v) / max(np.mean(tir_v), 1)), 3),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2263: Circadian Harmonic Encoding
# ─────────────────────────────────────────────────────────────────
def exp_2263_harmonic_encoding(patients):
    """Test if 4-harmonic time encoding improves therapy estimation."""
    results = {}

    for pat in patients:
        name = pat['name']
        df = pat['df']
        n = len(df)
        attrs = df.attrs
        glucose = df['glucose'].values.astype(np.float64)
        bolus = df['bolus'].values.astype(np.float64) if 'bolus' in df.columns else None
        carbs = df['carbs'].values.astype(np.float64) if 'carbs' in df.columns else np.zeros(n)

        if bolus is None:
            results[name] = {'skip': True}
            continue

        hours = np.arange(n) / STEPS_PER_HOUR
        hod = hours % 24

        # Build harmonic features
        harmonic_features = np.zeros((n, 8))
        for h in range(4):
            freq = (h + 1) * 2 * np.pi / 24.0
            harmonic_features[:, h * 2] = np.sin(freq * hod)
            harmonic_features[:, h * 2 + 1] = np.cos(freq * hod)

        # Find corrections (vectorized)
        valid_range = np.zeros(n, dtype=bool)
        valid_range[STEPS_PER_HOUR:n - STEPS_PER_HOUR * 4] = True
        has_bolus = ~np.isnan(bolus) & (bolus >= 0.1)
        has_glucose = ~np.isnan(glucose) & (glucose >= 120)
        candidates = np.where(valid_range & has_bolus & has_glucose)[0]

        carbs_safe = np.where(np.isnan(carbs), 0, carbs)
        carb_cs = np.cumsum(carbs_safe)

        corrections = []
        for i in candidates:
            lo = max(0, i - 6)
            hi = min(i + 6, n)
            c_sum = carb_cs[hi - 1] - (carb_cs[lo - 1] if lo > 0 else 0)
            if c_sum > 1:
                continue
            g3h = glucose[min(i + STEPS_PER_HOUR * 3, n - 1)]
            if np.isnan(g3h):
                continue
            isf_eff = (glucose[i] - g3h) / bolus[i]
            if isf_eff > 0:
                corrections.append({
                    'idx': i,
                    'hour': float(hod[i]),
                    'isf': isf_eff,
                    'harmonics': harmonic_features[i].tolist(),
                })

        if len(corrections) < 10:
            results[name] = {'skip': True, 'n_corrections': len(corrections)}
            continue

        # Fit linear regression: ISF ~ harmonics
        X = np.array([c['harmonics'] for c in corrections])
        y = np.array([c['isf'] for c in corrections])

        # Use GPU for regression if available
        if HAS_CUDA and len(corrections) > 50:
            X_t = torch.tensor(np.column_stack([np.ones(len(y)), X]), dtype=torch.float32, device=DEVICE)
            y_t = torch.tensor(y, dtype=torch.float32, device=DEVICE)
            # Normal equation: beta = (X'X)^-1 X'y
            beta = torch.linalg.lstsq(X_t, y_t).solution
            y_pred = (X_t @ beta).cpu().numpy()
            beta_np = beta.cpu().numpy()
        else:
            X_aug = np.column_stack([np.ones(len(y)), X])
            beta_np, _, _, _ = np.linalg.lstsq(X_aug, y, rcond=None)
            y_pred = X_aug @ beta_np

        # R² of harmonic model
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2_harmonic = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        # Compare with simple hour-of-day binning (24 bins)
        hourly_means = np.zeros(24)
        hourly_counts = np.zeros(24)
        for c in corrections:
            h = int(c['hour'])
            hourly_means[h] += c['isf']
            hourly_counts[h] += 1
        for h in range(24):
            if hourly_counts[h] > 0:
                hourly_means[h] /= hourly_counts[h]
            else:
                hourly_means[h] = np.mean(y)

        y_pred_hourly = np.array([hourly_means[int(c['hour'])] for c in corrections])
        ss_res_hourly = np.sum((y - y_pred_hourly) ** 2)
        r2_hourly = 1 - ss_res_hourly / ss_tot if ss_tot > 0 else 0

        # Harmonic amplitudes
        amplitudes = []
        for h in range(4):
            sin_coef = beta_np[1 + h * 2]
            cos_coef = beta_np[2 + h * 2]
            amp = float(np.sqrt(sin_coef ** 2 + cos_coef ** 2))
            phase = float(np.arctan2(sin_coef, cos_coef) * 24 / (2 * np.pi)) % 24
            amplitudes.append({
                'harmonic': h + 1,
                'amplitude': round(amp, 2),
                'phase_hour': round(phase, 1),
                'pct_of_mean': round(amp / max(np.mean(y), 0.01) * 100, 1),
            })

        results[name] = {
            'n_corrections': len(corrections),
            'r2_harmonic': round(float(r2_harmonic), 4),
            'r2_hourly': round(float(r2_hourly), 4),
            'harmonic_better': r2_harmonic > r2_hourly,
            'mean_isf': round(float(np.mean(y)), 1),
            'isf_cv': round(float(np.std(y) / np.mean(y)), 3),
            'amplitudes': amplitudes,
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2264: Autocorrelation Across Time Scales
# ─────────────────────────────────────────────────────────────────
def exp_2264_autocorrelation(patients):
    """Compute autocorrelation of glucose/insulin at multiple time scales."""
    results = {}
    lags_hours = [1, 2, 4, 8, 12, 24, 48, 72, 168, 336, 720]  # up to 30 days

    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values.astype(np.float64)
        n = len(glucose)

        signal = interpolate_gaps(glucose)
        signal = signal - np.mean(signal[signal != 0])

        # GPU-accelerated autocorrelation via FFT
        if HAS_CUDA:
            sig_t = torch.tensor(signal, dtype=torch.float32, device=DEVICE)
            # Autocorrelation via FFT: R(τ) = IFFT(|FFT(x)|²)
            n_fft = 2 * n  # zero-pad to avoid circular correlation
            fft_sig = torch.fft.rfft(sig_t, n=n_fft)
            power_spec = torch.abs(fft_sig) ** 2
            autocorr_full = torch.fft.irfft(power_spec, n=n_fft)[:n]
            autocorr_full = (autocorr_full / autocorr_full[0]).cpu().numpy()
        else:
            fft_sig = np.fft.rfft(signal, n=2 * n)
            power_spec = np.abs(fft_sig) ** 2
            autocorr_full = np.fft.irfft(power_spec, n=2 * n)[:n]
            autocorr_full = autocorr_full / autocorr_full[0]

        # Sample at specific lags
        acf_values = []
        for lag_h in lags_hours:
            lag_steps = lag_h * STEPS_PER_HOUR
            if lag_steps < n:
                acf_values.append({
                    'lag_hours': lag_h,
                    'autocorrelation': round(float(autocorr_full[lag_steps]), 4),
                })

        # Decorrelation time: first zero crossing
        zero_crossings = np.where(np.diff(np.sign(autocorr_full)))[0]
        decorr_hours = float(zero_crossings[0] / STEPS_PER_HOUR) if len(zero_crossings) > 0 else None

        # Periodicity: peak in autocorrelation beyond 12h
        beyond_12h = autocorr_full[12 * STEPS_PER_HOUR:min(48 * STEPS_PER_HOUR, n)]
        if len(beyond_12h) > 0:
            peak_idx = np.argmax(beyond_12h)
            peak_period = (peak_idx + 12 * STEPS_PER_HOUR) / STEPS_PER_HOUR
            peak_strength = float(beyond_12h[peak_idx])
        else:
            peak_period = None
            peak_strength = None

        results[name] = {
            'acf': acf_values,
            'decorrelation_hours': round(decorr_hours, 1) if decorr_hours else None,
            'dominant_period_hours': round(float(peak_period), 1) if peak_period else None,
            'period_strength': round(peak_strength, 4) if peak_strength else None,
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2265: Meal Pattern Regularity
# ─────────────────────────────────────────────────────────────────
def exp_2265_meal_regularity(patients):
    """Quantify meal timing regularity and its impact on estimate stability."""
    results = {}

    for pat in patients:
        name = pat['name']
        df = pat['df']
        n = len(df)
        carbs = df['carbs'].values.astype(np.float64) if 'carbs' in df.columns else None

        if carbs is None:
            results[name] = {'skip': True}
            continue

        carbs_safe = np.where(np.isnan(carbs), 0, carbs)
        n_days = int(n / STEPS_PER_DAY)
        hours = np.arange(n) / STEPS_PER_HOUR
        hod = hours % 24

        # Find meal events (carbs > 5g)
        meal_mask = carbs_safe > 5
        meal_indices = np.where(meal_mask)[0]
        meal_hours = hod[meal_indices]

        if len(meal_indices) < 10:
            results[name] = {'skip': True, 'reason': 'too few meals'}
            continue

        meals_per_day = len(meal_indices) / max(n_days, 1)

        # Meal timing distribution by hour
        meal_hist = np.histogram(meal_hours, bins=24, range=(0, 24))[0]
        meal_hist_pct = meal_hist / max(meal_hist.sum(), 1) * 100

        # Entropy of meal timing (uniformity measure)
        probs = meal_hist / max(meal_hist.sum(), 1)
        probs = probs[probs > 0]
        entropy = -np.sum(probs * np.log2(probs))
        max_entropy = np.log2(24)
        regularity = 1 - entropy / max_entropy  # 1 = perfectly regular, 0 = uniform

        # Day-to-day meal timing consistency
        daily_meal_times = []
        for d in range(n_days):
            s = d * STEPS_PER_DAY
            e = min(s + STEPS_PER_DAY, n)
            day_meals = meal_hours[
                (meal_indices >= s) & (meal_indices < e)
            ]
            if len(day_meals) > 0:
                daily_meal_times.append(day_meals.tolist())

        # Coefficient of variation of first meal time
        first_meals = [dm[0] for dm in daily_meal_times if dm]
        first_meal_cv = float(np.std(first_meals) / max(np.mean(first_meals), 0.01)) if len(first_meals) > 5 else None

        # Largest meal time
        largest_meal_times = []
        for d in range(n_days):
            s = d * STEPS_PER_DAY
            e = min(s + STEPS_PER_DAY, n)
            day_carbs = carbs_safe[s:e]
            if np.max(day_carbs) > 5:
                largest_idx = np.argmax(day_carbs)
                largest_meal_times.append(float(hod[s + largest_idx]))
        largest_meal_cv = float(np.std(largest_meal_times) / max(np.mean(largest_meal_times), 0.01)) if len(largest_meal_times) > 5 else None

        # Peak meal hours (top 3)
        peak_hours = np.argsort(meal_hist)[-3:][::-1].tolist()

        results[name] = {
            'n_meals': len(meal_indices),
            'meals_per_day': round(meals_per_day, 1),
            'regularity': round(regularity, 3),
            'entropy': round(float(entropy), 3),
            'first_meal_cv': round(first_meal_cv, 3) if first_meal_cv else None,
            'largest_meal_cv': round(largest_meal_cv, 3) if largest_meal_cv else None,
            'peak_hours': peak_hours,
            'meal_hist_pct': [round(float(x), 1) for x in meal_hist_pct],
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2266: GPU Monte Carlo Parameter Sensitivity
# ─────────────────────────────────────────────────────────────────
def exp_2266_monte_carlo(patients):
    """GPU-parallel Monte Carlo: sensitivity of TIR to parameter changes."""
    results = {}
    n_simulations = 10000 if HAS_CUDA else 1000
    t0 = time.time()

    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values.astype(np.float64)
        n = len(df)
        attrs = df.attrs

        valid_g = glucose[~np.isnan(glucose)]
        if len(valid_g) < STEPS_PER_DAY:
            results[name] = {'skip': True}
            continue

        mean_g = float(np.mean(valid_g))
        std_g = float(np.std(valid_g))

        # Simulate: what happens to TIR if we shift glucose by Δ?
        # Δ comes from: basal change (slow drift), ISF change (bolus effect), CR change (meal effect)
        if HAS_CUDA:
            g_tensor = torch.tensor(valid_g, dtype=torch.float32, device=DEVICE)

            # Parameter perturbations (uniform sampling)
            basal_delta = torch.linspace(-30, 30, 50, device=DEVICE)
            isf_delta = torch.linspace(-50, 50, 50, device=DEVICE)
            cr_delta = torch.linspace(-40, 40, 50, device=DEVICE)

            # Compute TIR for each perturbation (batched to avoid OOM)
            def tir_at_shift(g, shifts, batch_size=500):
                results = []
                for start in range(0, len(shifts), batch_size):
                    batch = shifts[start:start + batch_size]
                    shifted = g.unsqueeze(0) + batch.unsqueeze(1)  # (B, N)
                    in_range = (shifted >= 70) & (shifted <= 180)
                    results.append(in_range.float().mean(dim=1) * 100)
                    del shifted, in_range
                return torch.cat(results)

            tir_basal = tir_at_shift(g_tensor, basal_delta).cpu().numpy()
            tir_isf = tir_at_shift(g_tensor, isf_delta).cpu().numpy()
            tir_cr = tir_at_shift(g_tensor, cr_delta).cpu().numpy()

            basal_delta_np = basal_delta.cpu().numpy()
            isf_delta_np = isf_delta.cpu().numpy()
            cr_delta_np = cr_delta.cpu().numpy()

            # Monte Carlo: random simultaneous perturbations (batched)
            rng = torch.Generator(device=DEVICE)
            rng.manual_seed(42)
            mc_basal = torch.randn(n_simulations, device=DEVICE) * 15
            mc_isf = torch.randn(n_simulations, device=DEVICE) * 25
            mc_cr = torch.randn(n_simulations, device=DEVICE) * 20
            mc_total = mc_basal + mc_isf + mc_cr

            mc_tir = tir_at_shift(g_tensor, mc_total, batch_size=500).cpu().numpy()
            mc_total_np = mc_total.cpu().numpy()
            del g_tensor; torch.cuda.empty_cache()
        else:
            basal_delta_np = np.linspace(-30, 30, 50)
            isf_delta_np = np.linspace(-50, 50, 50)
            cr_delta_np = np.linspace(-40, 40, 50)

            tir_basal = np.array([np.mean(((valid_g + d) >= 70) & ((valid_g + d) <= 180)) * 100 for d in basal_delta_np])
            tir_isf = np.array([np.mean(((valid_g + d) >= 70) & ((valid_g + d) <= 180)) * 100 for d in isf_delta_np])
            tir_cr = np.array([np.mean(((valid_g + d) >= 70) & ((valid_g + d) <= 180)) * 100 for d in cr_delta_np])

            rng = np.random.RandomState(42)
            mc_total_np = rng.randn(n_simulations) * 15 + rng.randn(n_simulations) * 25 + rng.randn(n_simulations) * 20
            mc_tir = np.array([np.mean(((valid_g + d) >= 70) & ((valid_g + d) <= 180)) * 100 for d in mc_total_np])

        # Sensitivity: TIR change per mg/dL shift
        current_tir = float(np.mean((valid_g >= 70) & (valid_g <= 180)) * 100)
        basal_sensitivity = float((tir_basal[-1] - tir_basal[0]) / 60)  # TIR%/mg/dL
        isf_sensitivity = float((tir_isf[-1] - tir_isf[0]) / 100)
        cr_sensitivity = float((tir_cr[-1] - tir_cr[0]) / 80)

        # Monte Carlo uncertainty
        mc_tir_std = float(np.std(mc_tir))
        mc_tir_p5 = float(np.percentile(mc_tir, 5))
        mc_tir_p95 = float(np.percentile(mc_tir, 95))

        results[name] = {
            'current_tir': round(current_tir, 1),
            'mean_glucose': round(mean_g, 1),
            'glucose_std': round(std_g, 1),
            'basal_sensitivity': round(basal_sensitivity, 3),
            'isf_sensitivity': round(isf_sensitivity, 3),
            'cr_sensitivity': round(cr_sensitivity, 3),
            'mc_tir_mean': round(float(np.mean(mc_tir)), 1),
            'mc_tir_std': round(mc_tir_std, 1),
            'mc_tir_90ci': [round(mc_tir_p5, 1), round(mc_tir_p95, 1)],
            'n_simulations': n_simulations,
        }

    elapsed = time.time() - t0
    results['_meta'] = {'elapsed_seconds': round(elapsed, 2), 'device': 'cuda' if HAS_CUDA else 'cpu',
                        'n_simulations': n_simulations}
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2267: Information Content by Time Scale
# ─────────────────────────────────────────────────────────────────
def exp_2267_information(patients):
    """Mutual information between glucose features at different time scales."""
    results = {}

    for pat in patients:
        name = pat['name']
        df = pat['df']
        n = len(df)
        glucose = df['glucose'].values.astype(np.float64)
        iob = df['iob'].values.astype(np.float64) if 'iob' in df.columns else None

        valid = ~np.isnan(glucose)
        if valid.sum() < STEPS_PER_DAY * 7 or iob is None:
            results[name] = {'skip': True}
            continue

        # Compute features at different aggregation scales
        scales_hours = [1, 4, 8, 24, 48, 168]  # 1h to 1 week
        scale_results = []

        for scale_h in scales_hours:
            window = scale_h * STEPS_PER_HOUR
            n_blocks = n // window

            if n_blocks < 10:
                continue

            # Block means
            g_blocks = np.array([np.nanmean(glucose[i * window:(i + 1) * window])
                                 for i in range(n_blocks)])
            iob_blocks = np.array([np.nanmean(iob[i * window:(i + 1) * window])
                                   for i in range(n_blocks)])

            valid_blocks = ~np.isnan(g_blocks) & ~np.isnan(iob_blocks)
            g_v = g_blocks[valid_blocks]
            iob_v = iob_blocks[valid_blocks]

            if len(g_v) < 10:
                continue

            # Correlation at this scale
            corr = float(np.corrcoef(g_v, iob_v)[0, 1])

            # Variance at this scale
            g_var = float(np.var(g_v))
            iob_var = float(np.var(iob_v))

            # Binned mutual information estimate (8 bins)
            n_bins = 8
            g_bins = np.digitize(g_v, np.linspace(g_v.min(), g_v.max(), n_bins + 1)[:-1]) - 1
            iob_bins = np.digitize(iob_v, np.linspace(iob_v.min(), iob_v.max(), n_bins + 1)[:-1]) - 1

            # Joint distribution
            joint = np.zeros((n_bins, n_bins))
            for gi, ii in zip(g_bins, iob_bins):
                gi = min(gi, n_bins - 1)
                ii = min(ii, n_bins - 1)
                joint[gi, ii] += 1
            joint /= joint.sum()

            # Marginals
            p_g = joint.sum(axis=1)
            p_iob = joint.sum(axis=0)

            # MI = Σ p(g,i) log(p(g,i) / (p(g)*p(i)))
            mi = 0
            for i in range(n_bins):
                for j in range(n_bins):
                    if joint[i, j] > 0 and p_g[i] > 0 and p_iob[j] > 0:
                        mi += joint[i, j] * np.log2(joint[i, j] / (p_g[i] * p_iob[j]))

            scale_results.append({
                'scale_hours': scale_h,
                'correlation': round(corr, 3),
                'mutual_information': round(float(mi), 4),
                'glucose_variance': round(g_var, 1),
                'iob_variance': round(iob_var, 4),
                'n_blocks': int(valid_blocks.sum()),
            })

        results[name] = {
            'scales': scale_results,
            'best_mi_scale': max(scale_results, key=lambda x: x['mutual_information'])['scale_hours'] if scale_results else None,
            'best_corr_scale': max(scale_results, key=lambda x: abs(x['correlation']))['scale_hours'] if scale_results else None,
        }
    return results


# ─────────────────────────────────────────────────────────────────
# EXP-2268: Integrated Variability Attribution
# ─────────────────────────────────────────────────────────────────
def exp_2268_attribution(patients, all_results):
    """Attribute sources of month-to-month estimate variability."""
    results = {}

    for pat in patients:
        name = pat['name']

        # Gather evidence from all experiments
        spectral = all_results.get('exp_2261', {}).get(name, {})
        supply_demand = all_results.get('exp_2262', {}).get(name, {})
        harmonic = all_results.get('exp_2263', {}).get(name, {})
        autocorr = all_results.get('exp_2264', {}).get(name, {})
        meal_reg = all_results.get('exp_2265', {}).get(name, {})
        mc = all_results.get('exp_2266', {}).get(name, {})
        info = all_results.get('exp_2267', {}).get(name, {})

        if any(r.get('skip') for r in [spectral, supply_demand, meal_reg, mc]):
            results[name] = {'skip': True}
            continue

        # Attribution scores (0-1)
        # Circadian: how much of glucose variance is in circadian band?
        circ_pct = spectral.get('band_power', {}).get('circadian', 0)
        circ_score = min(circ_pct / 30, 1.0)  # 30% = max

        # Meal irregularity: does meal timing vary?
        reg = meal_reg.get('regularity', 0.5)
        meal_score = 1 - reg  # less regular = more variability attributed to meals

        # Supply tracking: does insulin track glucose demand?
        sd_corr = abs(supply_demand.get('supply_demand_corr', 0))
        supply_score = 1 - sd_corr  # low correlation = supply doesn't track demand

        # ISF circadian variation
        isf_cv = harmonic.get('isf_cv', 0)
        isf_score = min(isf_cv, 1.0)

        # Sensitivity to perturbation
        mc_std = mc.get('mc_tir_std', 0)
        sensitivity_score = min(mc_std / 10, 1.0)

        total_score = circ_score + meal_score + supply_score + isf_score + sensitivity_score
        if total_score > 0:
            attribution = {
                'circadian': round(circ_score / total_score * 100, 1),
                'meal_irregularity': round(meal_score / total_score * 100, 1),
                'supply_mismatch': round(supply_score / total_score * 100, 1),
                'isf_variability': round(isf_score / total_score * 100, 1),
                'sensitivity': round(sensitivity_score / total_score * 100, 1),
            }
        else:
            attribution = {'circadian': 20, 'meal_irregularity': 20, 'supply_mismatch': 20,
                           'isf_variability': 20, 'sensitivity': 20}

        # Primary variability source
        primary = max(attribution, key=attribution.get)

        results[name] = {
            'attribution': attribution,
            'primary_source': primary,
            'circadian_power_pct': circ_pct,
            'meal_regularity': round(reg, 3),
            'supply_demand_corr': supply_demand.get('supply_demand_corr'),
            'isf_cv': round(isf_cv, 3) if isf_cv else None,
            'mc_tir_std': mc.get('mc_tir_std'),
        }
    return results


# ─────────────────────────────────────────────────────────────────
# Figures
# ─────────────────────────────────────────────────────────────────
def generate_figures(all_results, fig_dir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(fig_dir, exist_ok=True)
    patients_list = sorted([k for k in all_results.get('exp_2261', {}).keys() if not k.startswith('_')])

    # ── Figure 1: Spectral Power Bands ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    spec = all_results['exp_2261']

    ax = axes[0]
    bands = ['ultra_low', 'circadian', 'meal', 'fast']
    band_labels = ['Ultra-Low\n(>48h)', 'Circadian\n(8-48h)', 'Meal\n(1-8h)', 'Fast\n(<1h)']
    x = np.arange(len(patients_list))
    bottom = np.zeros(len(patients_list))
    colors = ['#2c3e50', '#3498db', '#e74c3c', '#95a5a6']
    for bi, band in enumerate(bands):
        vals = [spec.get(n, {}).get('band_power', {}).get(band, 0) for n in patients_list]
        ax.bar(x, vals, bottom=bottom, label=band_labels[bi], color=colors[bi])
        bottom += np.array(vals)
    ax.set_xticks(x)
    ax.set_xticklabels(patients_list)
    ax.set_ylabel('Power (%)')
    ax.set_title('Glucose Signal: Spectral Power Distribution')
    ax.legend(fontsize=8)

    ax = axes[1]
    for n in patients_list:
        harms = spec.get(n, {}).get('harmonics', [])
        if harms:
            h_nums = [h['harmonic'] for h in harms]
            h_pcts = [h['power_pct'] for h in harms]
            ax.plot(h_nums, h_pcts, 'o-', label=n, markersize=5)
    ax.set_xlabel('Harmonic (1=24h, 2=12h, 3=8h, 4=6h)')
    ax.set_ylabel('Power (%)')
    ax.set_title('Circadian Harmonics')
    ax.legend(fontsize=7, ncol=2)

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'var-fig01-spectral-bands.png'), dpi=150)
    plt.close()
    print('  Figure 1: spectral bands')

    # ── Figure 2: Supply vs Demand ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    sd = all_results['exp_2262']

    ax = axes[0]
    supply_cvs = [sd.get(n, {}).get('supply_cv', 0) for n in patients_list]
    demand_cvs = [sd.get(n, {}).get('demand_cv', 0) for n in patients_list]
    x = np.arange(len(patients_list))
    ax.bar(x - 0.15, supply_cvs, 0.3, label='Supply (insulin) CV', color='steelblue')
    ax.bar(x + 0.15, demand_cvs, 0.3, label='Demand (glucose) CV', color='coral')
    ax.set_xticks(x)
    ax.set_xticklabels(patients_list)
    ax.set_ylabel('Coefficient of Variation')
    ax.set_title('Daily Supply vs Demand Variability')
    ax.legend()

    ax = axes[1]
    corrs = [sd.get(n, {}).get('supply_demand_corr', 0) for n in patients_list]
    colors = ['green' if abs(c) > 0.3 else 'orange' if abs(c) > 0.1 else 'red' for c in corrs]
    ax.bar(range(len(patients_list)), corrs, color=colors)
    ax.set_xticks(range(len(patients_list)))
    ax.set_xticklabels(patients_list)
    ax.set_ylabel('Correlation')
    ax.set_title('Supply-Demand Correlation')
    ax.axhline(y=0, color='gray', linestyle='--')

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'var-fig02-supply-demand.png'), dpi=150)
    plt.close()
    print('  Figure 2: supply-demand')

    # ── Figure 3: Harmonic ISF Model ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    harm = all_results['exp_2263']

    ax = axes[0]
    r2_harm = []
    r2_hour = []
    harm_names = []
    for n in patients_list:
        r = harm.get(n, {})
        if r.get('skip'):
            continue
        harm_names.append(n)
        r2_harm.append(r.get('r2_harmonic', 0))
        r2_hour.append(r.get('r2_hourly', 0))
    x = np.arange(len(harm_names))
    ax.bar(x - 0.15, r2_harm, 0.3, label='4-Harmonic', color='steelblue')
    ax.bar(x + 0.15, r2_hour, 0.3, label='Hourly bins', color='coral')
    ax.set_xticks(x)
    ax.set_xticklabels(harm_names)
    ax.set_ylabel('R²')
    ax.set_title('ISF Circadian Model: Harmonic vs Hourly')
    ax.legend()

    ax = axes[1]
    for n in harm_names:
        r = harm.get(n, {})
        amps = r.get('amplitudes', [])
        if amps:
            ax.plot([a['harmonic'] for a in amps],
                    [a['pct_of_mean'] for a in amps],
                    'o-', label=n, markersize=5)
    ax.set_xlabel('Harmonic')
    ax.set_ylabel('Amplitude (% of mean ISF)')
    ax.set_title('ISF Harmonic Amplitudes')
    ax.legend(fontsize=7, ncol=2)

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'var-fig03-harmonic-isf.png'), dpi=150)
    plt.close()
    print('  Figure 3: harmonic ISF')

    # ── Figure 4: Autocorrelation ──
    fig, ax = plt.subplots(figsize=(12, 5))
    acorr = all_results['exp_2264']

    for n in patients_list:
        r = acorr.get(n, {})
        acf = r.get('acf', [])
        if acf:
            lags = [a['lag_hours'] for a in acf]
            vals = [a['autocorrelation'] for a in acf]
            ax.plot(lags, vals, 'o-', label=n, markersize=4)
    ax.set_xscale('log')
    ax.set_xlabel('Lag (hours)')
    ax.set_ylabel('Autocorrelation')
    ax.set_title('Glucose Autocorrelation Across Time Scales')
    ax.axhline(y=0, color='gray', linestyle='--')
    ax.legend(fontsize=7, ncol=2)

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'var-fig04-autocorrelation.png'), dpi=150)
    plt.close()
    print('  Figure 4: autocorrelation')

    # ── Figure 5: Meal Regularity ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    meals = all_results['exp_2265']

    ax = axes[0]
    regs = [meals.get(n, {}).get('regularity', 0) for n in patients_list]
    mpd = [meals.get(n, {}).get('meals_per_day', 0) for n in patients_list]
    ax.bar(range(len(patients_list)), regs, color='steelblue')
    ax.set_xticks(range(len(patients_list)))
    ax.set_xticklabels(patients_list)
    ax.set_ylabel('Regularity (1=fixed times)')
    ax.set_title('Meal Timing Regularity')

    ax = axes[1]
    # Heatmap of meal timing
    heatmap = np.zeros((len(patients_list), 24))
    for i, n in enumerate(patients_list):
        hist = meals.get(n, {}).get('meal_hist_pct', [0] * 24)
        heatmap[i, :len(hist)] = hist[:24]
    im = ax.imshow(heatmap, cmap='YlOrRd', aspect='auto')
    ax.set_yticks(range(len(patients_list)))
    ax.set_yticklabels(patients_list)
    ax.set_xlabel('Hour of day')
    ax.set_title('Meal Timing Distribution (%)')
    plt.colorbar(im, ax=ax)

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'var-fig05-meal-regularity.png'), dpi=150)
    plt.close()
    print('  Figure 5: meal regularity')

    # ── Figure 6: Monte Carlo Sensitivity ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    mc = all_results['exp_2266']

    ax = axes[0]
    sensitivities = ['basal_sensitivity', 'isf_sensitivity', 'cr_sensitivity']
    sens_labels = ['Basal', 'ISF', 'CR']
    x = np.arange(len(patients_list))
    for si, (skey, slabel) in enumerate(zip(sensitivities, sens_labels)):
        vals = [mc.get(n, {}).get(skey, 0) for n in patients_list]
        ax.bar(x + si * 0.25 - 0.25, vals, 0.25, label=slabel)
    ax.set_xticks(x)
    ax.set_xticklabels(patients_list)
    ax.set_ylabel('TIR sensitivity (%/mg/dL)')
    ax.set_title('Parameter Sensitivity')
    ax.legend()

    ax = axes[1]
    for n in patients_list:
        r = mc.get(n, {})
        if r.get('skip'):
            continue
        ci = r.get('mc_tir_90ci', [0, 0])
        ax.barh(n, ci[1] - ci[0], left=ci[0], color='steelblue', alpha=0.6)
        ax.plot(r.get('current_tir', 0), n, 'ko', markersize=6)
    ax.set_xlabel('TIR (%)')
    ax.set_title('TIR: Current (●) vs Monte Carlo 90% CI')
    ax.axvline(x=70, color='red', linestyle='--', alpha=0.5, label='Target')
    ax.legend()

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'var-fig06-monte-carlo.png'), dpi=150)
    plt.close()
    print('  Figure 6: monte carlo')

    # ── Figure 7: Information by Scale ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    info = all_results['exp_2267']

    ax = axes[0]
    for n in patients_list:
        r = info.get(n, {})
        if r.get('skip'):
            continue
        scales = r.get('scales', [])
        if scales:
            ax.plot([s['scale_hours'] for s in scales],
                    [s['mutual_information'] for s in scales],
                    'o-', label=n, markersize=4)
    ax.set_xscale('log')
    ax.set_xlabel('Aggregation Scale (hours)')
    ax.set_ylabel('Mutual Information (bits)')
    ax.set_title('Glucose-IOB Mutual Information by Scale')
    ax.legend(fontsize=7, ncol=2)

    ax = axes[1]
    for n in patients_list:
        r = info.get(n, {})
        if r.get('skip'):
            continue
        scales = r.get('scales', [])
        if scales:
            ax.plot([s['scale_hours'] for s in scales],
                    [abs(s['correlation']) for s in scales],
                    'o-', label=n, markersize=4)
    ax.set_xscale('log')
    ax.set_xlabel('Aggregation Scale (hours)')
    ax.set_ylabel('|Correlation|')
    ax.set_title('Glucose-IOB Correlation by Scale')
    ax.legend(fontsize=7, ncol=2)

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'var-fig07-information-scale.png'), dpi=150)
    plt.close()
    print('  Figure 7: information scale')

    # ── Figure 8: Variability Attribution ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    attr = all_results['exp_2268']

    ax = axes[0]
    sources = ['circadian', 'meal_irregularity', 'supply_mismatch', 'isf_variability', 'sensitivity']
    source_labels = ['Circadian', 'Meal Irreg.', 'Supply\nMismatch', 'ISF\nVariability', 'Sensitivity']
    source_colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6']
    x = np.arange(len([n for n in patients_list if not attr.get(n, {}).get('skip')]))
    attr_names = [n for n in patients_list if not attr.get(n, {}).get('skip')]
    bottom = np.zeros(len(attr_names))
    for si, (src, slabel) in enumerate(zip(sources, source_labels)):
        vals = [attr.get(n, {}).get('attribution', {}).get(src, 0) for n in attr_names]
        ax.bar(x, vals, bottom=bottom, label=slabel, color=source_colors[si])
        bottom += np.array(vals)
    ax.set_xticks(x)
    ax.set_xticklabels(attr_names)
    ax.set_ylabel('Attribution (%)')
    ax.set_title('Variability Source Attribution')
    ax.legend(fontsize=8)

    ax = axes[1]
    primary_sources = [attr.get(n, {}).get('primary_source', 'unknown') for n in attr_names]
    unique_sources = list(set(primary_sources))
    counts = [primary_sources.count(s) for s in unique_sources]
    ax.pie(counts, labels=unique_sources, autopct='%1.0f%%', colors=source_colors[:len(unique_sources)])
    ax.set_title('Primary Variability Source Distribution')

    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, 'var-fig08-attribution.png'), dpi=150)
    plt.close()
    print('  Figure 8: attribution')


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    parser.add_argument('--data-dir', default='externals/ns-data/patients/')
    args = parser.parse_args()

    print('Loading patients...')
    patients = load_patients(args.data_dir)
    print(f'Loaded {len(patients)} patients\n')

    all_results = {}

    experiments = [
        ('exp_2261', 'Spectral Decomposition (GPU FFT)', exp_2261_spectral),
        ('exp_2262', 'Supply vs Demand Variability', exp_2262_supply_demand),
        ('exp_2263', 'Circadian Harmonic Encoding', exp_2263_harmonic_encoding),
        ('exp_2264', 'Autocorrelation Across Time Scales', exp_2264_autocorrelation),
        ('exp_2265', 'Meal Pattern Regularity', exp_2265_meal_regularity),
        ('exp_2266', 'GPU Monte Carlo Sensitivity', exp_2266_monte_carlo),
        ('exp_2267', 'Information Content by Scale', exp_2267_information),
    ]

    for key, title, func in experiments:
        print(f'Running {key}: {title}...')
        try:
            result = func(patients)
            all_results[key] = result
            n_ok = sum(1 for k, v in result.items()
                       if not k.startswith('_') and isinstance(v, dict) and not v.get('skip'))
            print(f'  ✓ {n_ok} patients processed')
        except Exception as e:
            print(f'  ✗ FAILED: {e}')
            import traceback
            traceback.print_exc()
            all_results[key] = {'error': str(e)}

    # EXP-2268 depends on all results
    print('Running exp_2268: Integrated Variability Attribution...')
    try:
        all_results['exp_2268'] = exp_2268_attribution(patients, all_results)
        attr = all_results['exp_2268']
        for name in sorted(k for k in attr.keys() if not k.startswith('_')):
            r = attr[name]
            if r.get('skip'):
                continue
            print(f'  {name}: primary={r["primary_source"]} | {r["attribution"]}')
    except Exception as e:
        print(f'  ✗ FAILED: {e}')
        import traceback
        traceback.print_exc()

    # Save
    out_path = 'externals/experiments/exp-2261-2268_variability.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)
    print(f'\nResults saved to {out_path}')

    if args.figures:
        print('\nGenerating figures...')
        fig_dir = 'docs/60-research/figures'
        generate_figures(all_results, fig_dir)
        print('All figures generated.')


if __name__ == '__main__':
    main()
