#!/usr/bin/env python3
"""EXP-1301–1310: Advanced therapy assessment with response-curve ISF,
dawn detection, reflexive simulation, and conservation augmentation.

Builds on EXP-1291-1300 findings:
1. ISF deconfounding by dividing by total_insulin FAILS (AID loop dampens corrections)
2. Dawn phenomenon detection fails (0/11) because ISF is constant in profile
3. All patients have negative physics R² — conservation underperforms constant prediction
4. 6/11 ISF too aggressive, 7/11 basal needs decrease
5. Precondition framework works well, gating unreliable patients
"""
import argparse, json, os, sys, time, warnings
import numpy as np
from pathlib import Path
from collections import defaultdict

warnings.filterwarnings('ignore')

from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_clinical_1291 import (
    assess_preconditions, check_precondition, get_fidelity_metrics,
    get_scheduled_basal_rate, get_time_blocks
)

PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent
                   / 'externals' / 'ns-data' / 'patients')

GLUCOSE_SCALE = 400.0
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
DIA_STEPS = STEPS_PER_HOUR * 5  # 5-hour DIA

BLOCK_NAMES = ['overnight(0-6)', 'morning(6-10)', 'midday(10-14)',
               'afternoon(14-18)', 'evening(18-22)', 'night(22-24)']

MEAL_BLOCK_NAMES = ['breakfast(6-10)', 'lunch(10-14)', 'dinner(14-20)', 'late(20-24)']


def get_meal_block(step_in_day):
    """Map a step within a day to a meal time block index."""
    hour = (step_in_day / STEPS_PER_HOUR) % 24
    if 6 <= hour < 10:
        return 0  # breakfast
    elif 10 <= hour < 14:
        return 1  # lunch
    elif 14 <= hour < 20:
        return 2  # dinner
    elif 20 <= hour < 24:
        return 3  # late
    return -1  # overnight — not a meal block


# ─── EXP-1301: Response Curve ISF ────────────────────────────────────
def exp_1301_response_curve_isf(patients, detail=False, preconditions=None):
    """Estimate ISF via exponential decay curve fitting on isolated corrections.

    Instead of ISF = ΔBG / total_insulin, fit the correction trajectory:
    BG(t) = BG_start - amplitude × (1 - exp(-t/tau))
    ISF_effective = amplitude / bolus_amount
    """
    results = {'name': 'EXP-1301: Response curve ISF',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'correction_validation'}

    for p in patients:
        met, reason = check_precondition(p, preconditions, 'correction_validation')
        if not met:
            results['per_patient'].append({
                'patient': p['name'], 'skipped': True, 'reason': reason})
            continue

        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        isf_profile = pk[:, 7] * 200.0
        n = len(glucose)

        corrections = []
        for i in range(n):
            if bolus[i] < 0.3:
                continue
            if np.isnan(glucose[i]) or glucose[i] <= 150:
                continue
            carb_window = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[carb_window]) > 2:
                continue
            window = 3 * STEPS_PER_HOUR  # 3-hour post-correction
            if i + window >= n:
                continue
            future_bolus = bolus[i + 1:i + window]
            if np.sum(future_bolus) > 0.5:
                continue
            future_carbs = carbs[i + 1:i + window]
            if np.sum(future_carbs) > 2:
                continue

            # Extract trajectory
            traj = glucose[i:i + window].copy()
            valid = ~np.isnan(traj)
            if valid.sum() < window * 0.5:
                continue

            bg_start = float(traj[0])
            t_steps = np.arange(window)
            t_hours = t_steps * (5.0 / 60.0)

            # Fit exponential decay: BG(t) = bg_start - amp * (1 - exp(-t/tau))
            # Linearize: for each candidate tau, fit amplitude via least squares
            best_sse = np.inf
            best_tau = 1.0
            best_amp = 0.0
            for tau_candidate in [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]:
                basis = 1.0 - np.exp(-t_hours / tau_candidate)
                basis_v = basis[valid]
                target_v = bg_start - traj[valid]
                if np.sum(basis_v ** 2) < 1e-6:
                    continue
                amp = float(np.sum(basis_v * target_v) / np.sum(basis_v ** 2))
                if amp < 5:
                    continue  # correction should lower BG
                predicted = bg_start - amp * basis
                residual = traj[valid] - predicted[valid]
                sse = float(np.sum(residual ** 2))
                if sse < best_sse:
                    best_sse = sse
                    best_tau = tau_candidate
                    best_amp = amp

            if best_amp < 5:
                continue

            bolus_amount = float(bolus[i])
            isf_curve = best_amp / bolus_amount
            isf_simple = (bg_start - float(np.nanmin(traj))) / bolus_amount
            isf_prof = float(np.mean(isf_profile[i:i + window]))

            # R² of curve fit
            mean_bg = np.nanmean(traj[valid])
            ss_tot = np.sum((traj[valid] - mean_bg) ** 2)
            ss_res = best_sse
            fit_r2 = 1 - ss_res / (ss_tot + 1e-10)

            corr_record = {
                'index': int(i),
                'bolus': round(bolus_amount, 2),
                'bg_start': round(bg_start, 1),
                'amplitude': round(best_amp, 1),
                'tau_hours': best_tau,
                'isf_curve': round(isf_curve, 1),
                'isf_simple': round(isf_simple, 1),
                'isf_profile': round(isf_prof, 1),
                'fit_r2': round(fit_r2, 3),
            }
            corrections.append(corr_record)

        if corrections:
            curve_isfs = [c['isf_curve'] for c in corrections]
            simple_isfs = [c['isf_simple'] for c in corrections]
            profile_isfs = [c['isf_profile'] for c in corrections]
            taus = [c['tau_hours'] for c in corrections]

            results['per_patient'].append({
                'patient': p['name'],
                'n_corrections': len(corrections),
                'mean_isf_curve': round(float(np.mean(curve_isfs)), 1),
                'mean_isf_simple': round(float(np.mean(simple_isfs)), 1),
                'mean_isf_profile': round(float(np.mean(profile_isfs)), 1),
                'curve_vs_profile_ratio': round(float(np.mean(curve_isfs)) /
                                                (float(np.mean(profile_isfs)) + 1e-6), 2),
                'mean_tau_hours': round(float(np.mean(taus)), 2),
                'median_tau_hours': round(float(np.median(taus)), 2),
                'mean_fit_r2': round(float(np.mean([c['fit_r2'] for c in corrections])), 3),
                'isf_iqr': round(float(np.percentile(curve_isfs, 75) -
                                       np.percentile(curve_isfs, 25)), 1),
                'corrections': corrections[:5] if detail else [],
            })
        else:
            results['per_patient'].append({
                'patient': p['name'], 'n_corrections': 0,
                'note': 'No qualifying high-BG isolated corrections'})

    with_data = [r for r in results['per_patient'] if r.get('n_corrections', 0) > 0]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        results['mean_curve_isf'] = round(
            float(np.mean([r['mean_isf_curve'] for r in with_data])), 1)
        results['mean_simple_isf'] = round(
            float(np.mean([r['mean_isf_simple'] for r in with_data])), 1)
        results['mean_tau'] = round(
            float(np.mean([r['mean_tau_hours'] for r in with_data])), 2)
        results['mean_fit_r2'] = round(
            float(np.mean([r['mean_fit_r2'] for r in with_data])), 3)
    return results


# ─── EXP-1302: Dawn Detection via Glucose Pattern ───────────────────
def exp_1302_dawn_glucose(patients, detail=False, preconditions=None):
    """Detect dawn phenomenon from glucose rate of change, not ISF.

    Find overnight fasting windows and compare pre-dawn (midnight-4AM)
    vs dawn (4-7AM) glucose slopes. Also check loop basal response.
    """
    results = {'name': 'EXP-1302: Dawn detection via glucose',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'basal_assessment'}

    n_dawn_detected = 0

    for p in patients:
        met, reason = check_precondition(p, preconditions, 'basal_assessment')
        if not met:
            results['per_patient'].append({
                'patient': p['name'], 'skipped': True, 'reason': reason})
            continue

        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        basal_ratio = pk[:, 2] * 2.0
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        pre_dawn_slopes = []
        dawn_slopes = []
        dawn_basal_ratios = []
        pre_dawn_basal_ratios = []
        night_details = []

        for day in range(n_days):
            day_start = day * STEPS_PER_DAY

            # Check fasting: no carbs/bolus from 9 PM prior day to 8 AM
            fast_start = day_start - 3 * STEPS_PER_HOUR  # 9 PM (if available)
            fast_end = day_start + 8 * STEPS_PER_HOUR  # 8 AM
            fast_start = max(0, fast_start)
            if fast_end > n:
                continue

            if np.sum(carbs[fast_start:fast_end]) > 1:
                continue
            if np.sum(bolus[fast_start:fast_end]) > 0.1:
                continue

            # Pre-dawn: midnight (step 0) to 4 AM (step 48)
            pd_start = day_start  # midnight
            pd_end = day_start + 4 * STEPS_PER_HOUR  # 4 AM
            pd_glucose = glucose[pd_start:pd_end]
            pd_valid = ~np.isnan(pd_glucose)
            if pd_valid.sum() < 2 * STEPS_PER_HOUR:
                continue

            # Dawn: 4 AM to 7 AM
            d_start = day_start + 4 * STEPS_PER_HOUR
            d_end = day_start + 7 * STEPS_PER_HOUR
            d_glucose = glucose[d_start:d_end]
            d_valid = ~np.isnan(d_glucose)
            if d_valid.sum() < 1 * STEPS_PER_HOUR:
                continue

            # Compute slopes via linear regression (mg/dL per hour)
            pd_t = np.arange(len(pd_glucose))[pd_valid] * (5.0 / 60.0)
            pd_g = pd_glucose[pd_valid]
            if len(pd_t) >= 2:
                pd_fit = np.polyfit(pd_t, pd_g, 1)
                pre_dawn_slopes.append(float(pd_fit[0]))

            d_t = np.arange(len(d_glucose))[d_valid] * (5.0 / 60.0)
            d_g = d_glucose[d_valid]
            if len(d_t) >= 2:
                d_fit = np.polyfit(d_t, d_g, 1)
                dawn_slopes.append(float(d_fit[0]))

            # Basal ratios during each window
            pd_br = basal_ratio[pd_start:pd_end]
            d_br = basal_ratio[d_start:d_end]
            pre_dawn_basal_ratios.append(float(np.mean(pd_br)))
            dawn_basal_ratios.append(float(np.mean(d_br)))

            if detail and len(night_details) < 5:
                night_details.append({
                    'day': day,
                    'pre_dawn_slope': round(float(pd_fit[0]), 2) if len(pd_t) >= 2 else None,
                    'dawn_slope': round(float(d_fit[0]), 2) if len(d_t) >= 2 else None,
                    'pre_dawn_basal_ratio': round(float(np.mean(pd_br)), 2),
                    'dawn_basal_ratio': round(float(np.mean(d_br)), 2),
                })

        n_nights = min(len(pre_dawn_slopes), len(dawn_slopes))
        if n_nights < 3:
            results['per_patient'].append({
                'patient': p['name'],
                'n_qualifying_nights': n_nights,
                'note': 'Insufficient fasting overnight windows'})
            continue

        # Paired comparison
        pd_arr = np.array(pre_dawn_slopes[:n_nights])
        d_arr = np.array(dawn_slopes[:n_nights])
        slope_diff = d_arr - pd_arr  # positive = dawn rise steeper
        mean_diff = float(np.mean(slope_diff))
        se_diff = float(np.std(slope_diff, ddof=1) / np.sqrt(n_nights)) if n_nights > 1 else 1.0

        # Simple t-statistic
        t_stat = mean_diff / (se_diff + 1e-6)
        # Dawn detected if slope increases significantly (t > 2) and positive mean diff
        dawn_detected = t_stat > 2.0 and mean_diff > 1.0  # > 1 mg/dL/hr increase
        if dawn_detected:
            n_dawn_detected += 1

        # Loop response: does loop increase basal during dawn window?
        mean_pd_br = float(np.mean(pre_dawn_basal_ratios))
        mean_d_br = float(np.mean(dawn_basal_ratios))
        loop_compensates = mean_d_br > mean_pd_br + 0.1

        rec = {
            'patient': p['name'],
            'n_qualifying_nights': n_nights,
            'mean_pre_dawn_slope': round(float(np.mean(pd_arr)), 2),
            'mean_dawn_slope': round(float(np.mean(d_arr)), 2),
            'mean_slope_diff': round(mean_diff, 2),
            't_statistic': round(t_stat, 2),
            'dawn_detected': dawn_detected,
            'mean_pre_dawn_basal_ratio': round(mean_pd_br, 2),
            'mean_dawn_basal_ratio': round(mean_d_br, 2),
            'loop_compensates': loop_compensates,
        }
        if detail:
            rec['nights'] = night_details
        results['per_patient'].append(rec)

    results['n_dawn_detected'] = n_dawn_detected
    assessed = [r for r in results['per_patient'] if 'dawn_detected' in r]
    results['n_assessed'] = len(assessed)
    results['detection_rate'] = (f"{n_dawn_detected}/{len(assessed)}"
                                 if assessed else '0/0')
    if assessed:
        results['mean_slope_diff'] = round(
            float(np.mean([r['mean_slope_diff'] for r in assessed])), 2)
    return results


# ─── EXP-1303: Reflexive Basal Simulation ───────────────────────────
def exp_1303_reflexive_simulation(patients, detail=False, preconditions=None):
    """Simulate basal changes accounting for AID loop reflexive behavior.

    Model: if scheduled rate changes by X%, the loop adjustment stays the same,
    so new_temp_rate = (R × (1+X%)) + loop_adjustment. Find X that minimizes
    the residual supply-demand gap.
    """
    results = {'name': 'EXP-1303: Reflexive basal simulation',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'basal_assessment'}

    for p in patients:
        met, reason = check_precondition(p, preconditions, 'basal_assessment')
        if not met:
            results['per_patient'].append({
                'patient': p['name'], 'skipped': True, 'reason': reason})
            continue

        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        temp_rate = df['temp_rate'].values
        basal_ratio = pk[:, 2] * 2.0
        n = len(glucose)

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']
        demand = sd['demand']
        supply = sd['supply']

        scheduled_rate = get_scheduled_basal_rate(p)

        # Identify fasting windows for clean simulation
        fasting = np.ones(n, dtype=bool)
        for i in range(n):
            ws = max(0, i - STEPS_PER_HOUR * 2)
            we = min(n, i + STEPS_PER_HOUR * 2)
            if np.sum(bolus[ws:we]) > 0.1 or np.sum(carbs[ws:we]) > 1:
                fasting[i] = False
        valid = fasting & ~np.isnan(glucose)

        if valid.sum() < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'],
                'note': 'Insufficient fasting data for simulation'})
            continue

        # Compute scheduled fraction: what % of total insulin is from basal?
        total_insulin_hourly = pk[:, 0] * 0.05 * STEPS_PER_HOUR  # U/hr
        total_insulin_hourly = np.maximum(total_insulin_hourly, 1e-6)
        scheduled_delivery = scheduled_rate * np.ones(n)
        sched_frac = np.clip(scheduled_delivery / (total_insulin_hourly + 1e-6), 0, 1)
        mean_sched_frac = float(np.mean(sched_frac[valid]))

        # Scan X% from -50% to +50% in 5% steps
        best_x = 0.0
        best_residual = np.inf
        scan_results = []
        for x_pct in range(-50, 55, 5):
            x = x_pct / 100.0
            # New demand: loop adjustment stays same, only scheduled part changes
            new_demand = demand.copy()
            new_demand[valid] = demand[valid] * (1 + x * sched_frac[valid])
            new_net = supply[valid] - new_demand[valid]
            # Compute residual: how well does dBG/dt match new net flux?
            dg = np.diff(glucose)
            dg = np.append(dg, 0)
            residual_rms = float(np.sqrt(np.mean((dg[valid] - new_net) ** 2)))
            scan_results.append({'x_pct': x_pct, 'residual_rms': round(residual_rms, 3)})
            if residual_rms < best_residual:
                best_residual = residual_rms
                best_x = x_pct

        # Also compute current residual (x=0)
        baseline_residual = float(np.sqrt(np.mean((
            np.diff(glucose, append=glucose[-1])[valid] - net_flux[valid]) ** 2)))

        rec = {
            'patient': p['name'],
            'scheduled_rate': round(scheduled_rate, 3),
            'scheduled_fraction': round(mean_sched_frac, 2),
            'n_fasting_steps': int(valid.sum()),
            'optimal_adjustment_pct': best_x,
            'optimal_residual_rms': round(best_residual, 3),
            'baseline_residual_rms': round(baseline_residual, 3),
            'improvement_pct': round((1 - best_residual / (baseline_residual + 1e-6)) * 100, 1)
                if baseline_residual > 1e-3 else 0.0,
        }
        if detail:
            rec['scan'] = scan_results
        results['per_patient'].append(rec)

    with_data = [r for r in results['per_patient']
                 if 'optimal_adjustment_pct' in r]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        results['mean_optimal_adjustment'] = round(
            float(np.mean([r['optimal_adjustment_pct'] for r in with_data])), 1)
        results['mean_improvement_pct'] = round(
            float(np.mean([r['improvement_pct'] for r in with_data])), 1)
        dist = defaultdict(int)
        for r in with_data:
            if r['optimal_adjustment_pct'] < -10:
                dist['decrease'] += 1
            elif r['optimal_adjustment_pct'] > 10:
                dist['increase'] += 1
            else:
                dist['unchanged'] += 1
        results['direction_distribution'] = dict(dist)
    return results


# ─── EXP-1304: Multi-Week Recommendation Stability ──────────────────
def exp_1304_stability(patients, detail=False, preconditions=None):
    """Track recommendation consistency over 2-week rolling windows.

    Compute basal/ISF recommendations per window and measure coefficient
    of variation. Stable recommendations → high confidence.
    """
    results = {'name': 'EXP-1304: Multi-week recommendation stability',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'multiday_tracking'}

    WINDOW_DAYS = 14
    WINDOW_STEPS = WINDOW_DAYS * STEPS_PER_DAY
    STRIDE_DAYS = 7
    STRIDE_STEPS = STRIDE_DAYS * STEPS_PER_DAY

    for p in patients:
        met, reason = check_precondition(p, preconditions, 'multiday_tracking')
        if not met:
            results['per_patient'].append({
                'patient': p['name'], 'skipped': True, 'reason': reason})
            continue

        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        basal_ratio = pk[:, 2] * 2.0
        temp_rate = df['temp_rate'].values
        n = len(glucose)

        scheduled_rate = get_scheduled_basal_rate(p)
        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']

        window_recs = []
        start = 0
        while start + WINDOW_STEPS <= n:
            end = start + WINDOW_STEPS
            w_glucose = glucose[start:end]
            w_bolus = bolus[start:end]
            w_carbs = carbs[start:end]
            w_br = basal_ratio[start:end]
            w_net = net_flux[start:end]
            w_valid = ~np.isnan(w_glucose)

            if w_valid.sum() < WINDOW_STEPS * 0.5:
                start += STRIDE_STEPS
                continue

            # Fasting flux → basal recommendation
            w_fasting = np.ones(len(w_glucose), dtype=bool)
            for i in range(len(w_glucose)):
                ws = max(0, i - STEPS_PER_HOUR * 2)
                we = min(len(w_glucose), i + STEPS_PER_HOUR * 2)
                if np.sum(w_bolus[ws:we]) > 0.1 or np.sum(w_carbs[ws:we]) > 1:
                    w_fasting[i] = False
            fasting_valid = w_fasting & w_valid

            if fasting_valid.sum() > STEPS_PER_HOUR * 4:
                mean_fasting_net = float(np.mean(w_net[fasting_valid]))
                # If net > 0 → supply > demand → basal should increase
                # Change proportional to residual: change_pct = net * scale
                basal_change_pct = mean_fasting_net * 10.0  # heuristic scale
                basal_change_pct = np.clip(basal_change_pct, -50, 50)
            else:
                basal_change_pct = 0.0

            # ISF from corrections in this window
            isf_estimates = []
            for i in range(len(w_glucose)):
                if w_bolus[i] < 0.3:
                    continue
                cw = slice(max(0, i - 6), min(len(w_glucose), i + 6))
                if np.sum(w_carbs[cw]) > 2:
                    continue
                if np.isnan(w_glucose[i]) or w_glucose[i] <= 120:
                    continue
                future_end = min(len(w_glucose), i + DIA_STEPS)
                if future_end - i < STEPS_PER_HOUR * 2:
                    continue
                future_bg = w_glucose[i:future_end]
                if np.sum(~np.isnan(future_bg)) < len(future_bg) * 0.4:
                    continue
                delta = w_glucose[i] - np.nanmin(future_bg)
                if delta > 10:
                    isf_estimates.append(delta / w_bolus[i])

            mean_isf = float(np.mean(isf_estimates)) if isf_estimates else None

            window_recs.append({
                'window_start_day': start // STEPS_PER_DAY,
                'basal_change_pct': round(float(basal_change_pct), 1),
                'mean_isf': round(mean_isf, 1) if mean_isf else None,
                'n_corrections': len(isf_estimates),
            })
            start += STRIDE_STEPS

        if len(window_recs) < 2:
            results['per_patient'].append({
                'patient': p['name'],
                'n_windows': len(window_recs),
                'note': 'Insufficient windows for stability assessment'})
            continue

        basal_changes = [w['basal_change_pct'] for w in window_recs]
        basal_cv = (float(np.std(basal_changes, ddof=1)) /
                    (abs(float(np.mean(basal_changes))) + 1e-6))

        isf_vals = [w['mean_isf'] for w in window_recs if w['mean_isf'] is not None]
        isf_cv = (float(np.std(isf_vals, ddof=1)) /
                  (float(np.mean(isf_vals)) + 1e-6)) if len(isf_vals) >= 2 else None

        # Stability flag: CV < 0.3 means consistent
        stable_basal = basal_cv < 0.3
        stable_isf = isf_cv is not None and isf_cv < 0.3

        # Max window-to-window change
        max_basal_jump = max(abs(basal_changes[i+1] - basal_changes[i])
                            for i in range(len(basal_changes) - 1))

        rec = {
            'patient': p['name'],
            'n_windows': len(window_recs),
            'basal_change_mean': round(float(np.mean(basal_changes)), 1),
            'basal_change_cv': round(basal_cv, 2),
            'basal_stable': stable_basal,
            'max_basal_jump_pct': round(float(max_basal_jump), 1),
            'isf_cv': round(isf_cv, 2) if isf_cv is not None else None,
            'isf_stable': stable_isf,
            'confidence': ('high' if stable_basal and (stable_isf or isf_cv is None)
                          else 'low'),
        }
        if detail:
            rec['windows'] = window_recs
        results['per_patient'].append(rec)

    assessed = [r for r in results['per_patient'] if 'confidence' in r]
    results['n_assessed'] = len(assessed)
    if assessed:
        results['n_high_confidence'] = sum(1 for r in assessed if r['confidence'] == 'high')
        results['n_low_confidence'] = sum(1 for r in assessed if r['confidence'] == 'low')
        results['mean_basal_cv'] = round(
            float(np.mean([r['basal_change_cv'] for r in assessed])), 2)
    return results


# ─── EXP-1305: Conservation Violation Decomposition ─────────────────
def exp_1305_violation_decomp(patients, detail=False, preconditions=None):
    """Decompose conservation violations into UAM, exercise, compression,
    and unexplained categories.

    Positive violations (actual dBG > predicted): likely UAM meals.
    Negative violations (actual dBG < predicted): likely exercise/compression.
    """
    results = {'name': 'EXP-1305: Conservation violation decomposition',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'physics_model_valid'}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        basal_ratio = pk[:, 2] * 2.0
        n = len(glucose)

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']

        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)

        if valid.sum() < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'],
                'note': 'Insufficient valid data'})
            continue

        residual = dg[valid] - net_flux[valid]
        # Violation threshold: |residual| > 5 mg/dL per 5-min step
        threshold = 5.0
        positive_mask = residual > threshold
        negative_mask = residual < -threshold

        n_positive = int(positive_mask.sum())
        n_negative = int(negative_mask.sum())
        n_total_violations = n_positive + n_negative
        n_valid = int(valid.sum())

        # Map valid indices back to original array
        valid_indices = np.where(valid)[0]

        # Categorize positive violations (actual BG rising more than predicted)
        uam_count = 0
        uam_with_delayed_carbs = 0
        uam_with_loop_response = 0
        pos_indices = valid_indices[positive_mask]
        for idx in pos_indices:
            # Check for carbs within 30-60min AFTER
            future_start = idx + 6   # 30 min
            future_end = min(n, idx + 12)  # 60 min
            if future_start < n and np.sum(carbs[future_start:future_end]) > 2:
                uam_with_delayed_carbs += 1
            # Check if loop increases insulin within 30 min
            future_ins = min(n, idx + 6)
            if idx + 1 < n and np.mean(basal_ratio[idx:future_ins]) > 1.2:
                uam_with_loop_response += 1
            uam_count += 1

        # Categorize negative violations (actual BG dropping more than predicted)
        exercise_count = 0
        compression_count = 0
        neg_indices = valid_indices[negative_mask]
        blocks = get_time_blocks(n)
        evening_exercise = 0
        loop_suspend = 0

        for idx in neg_indices:
            exercise_count += 1
            # Time-of-day: evening exercise pattern
            if blocks[idx] == 4:  # evening(18-22)
                evening_exercise += 1
            # Check if loop suspends within 30min
            future_ins = min(n, idx + 6)
            if idx + 1 < n and np.mean(basal_ratio[idx:future_ins]) < 0.3:
                loop_suspend += 1
                compression_count += 1

        unexplained = n_total_violations - (uam_count + exercise_count)
        unexplained = max(0, unexplained)

        pct_total = n_total_violations / (n_valid + 1e-6) * 100

        rec = {
            'patient': p['name'],
            'n_valid_steps': n_valid,
            'n_total_violations': n_total_violations,
            'pct_violated': round(pct_total, 1),
            'n_positive_violations': n_positive,
            'n_negative_violations': n_negative,
            'uam_events': uam_count,
            'uam_with_delayed_carbs': uam_with_delayed_carbs,
            'uam_with_loop_response': uam_with_loop_response,
            'pct_uam': round(uam_count / (n_total_violations + 1e-6) * 100, 1),
            'exercise_events': exercise_count,
            'evening_exercise': evening_exercise,
            'loop_suspend_events': loop_suspend,
            'pct_exercise': round(exercise_count / (n_total_violations + 1e-6) * 100, 1),
            'compression_events': compression_count,
            'pct_compression': round(compression_count / (n_total_violations + 1e-6) * 100, 1),
            'unexplained': unexplained,
            'pct_unexplained': round(unexplained / (n_total_violations + 1e-6) * 100, 1),
        }
        results['per_patient'].append(rec)

    with_data = [r for r in results['per_patient'] if 'n_total_violations' in r]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        results['mean_pct_violated'] = round(
            float(np.mean([r['pct_violated'] for r in with_data])), 1)
        results['mean_pct_uam'] = round(
            float(np.mean([r['pct_uam'] for r in with_data])), 1)
        results['mean_pct_exercise'] = round(
            float(np.mean([r['pct_exercise'] for r in with_data])), 1)
        results['mean_pct_unexplained'] = round(
            float(np.mean([r['pct_unexplained'] for r in with_data])), 1)
    return results


# ─── EXP-1306: Calm-Window ISF ──────────────────────────────────────
def exp_1306_calm_isf(patients, detail=False, preconditions=None):
    """Estimate ISF only during calm loop windows (basal_ratio 0.8-1.2).

    These rare windows give unconfounded ISF measurements since the loop
    is not actively compensating.
    """
    results = {'name': 'EXP-1306: Calm-window ISF',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'isf_estimation'}

    for p in patients:
        met, reason = check_precondition(p, preconditions, 'isf_estimation')
        if not met:
            results['per_patient'].append({
                'patient': p['name'], 'skipped': True, 'reason': reason})
            continue

        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        basal_ratio = pk[:, 2] * 2.0
        isf_profile = pk[:, 7] * 200.0
        n = len(glucose)

        calm_corrections = []
        all_corrections = []

        for i in range(n):
            if bolus[i] < 0.3:
                continue
            if np.isnan(glucose[i]) or glucose[i] <= 120:
                continue
            carb_window = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[carb_window]) > 2:
                continue
            future_end = min(n, i + DIA_STEPS)
            if future_end - i < STEPS_PER_HOUR * 2:
                continue
            # Check for interfering boluses
            if np.sum(bolus[i + 1:future_end]) > 0.5:
                continue
            future_bg = glucose[i:future_end]
            valid_future = ~np.isnan(future_bg)
            if valid_future.sum() < len(future_bg) * 0.4:
                continue

            delta_bg = glucose[i] - np.nanmin(future_bg)
            if delta_bg < 10:
                continue

            isf = delta_bg / bolus[i]
            prof_isf = float(np.mean(isf_profile[i:future_end]))

            all_corrections.append({
                'index': int(i),
                'isf': round(float(isf), 1),
                'isf_profile': round(prof_isf, 1),
            })

            # Check calm window: basal_ratio 0.8-1.2 for full DIA window
            window_br = basal_ratio[i:future_end]
            is_calm = np.all((window_br >= 0.8) & (window_br <= 1.2))
            if is_calm:
                calm_corrections.append({
                    'index': int(i),
                    'isf': round(float(isf), 1),
                    'isf_profile': round(prof_isf, 1),
                    'mean_basal_ratio': round(float(np.mean(window_br)), 3),
                })

        if all_corrections:
            all_isfs = [c['isf'] for c in all_corrections]
            calm_isfs = [c['isf'] for c in calm_corrections]

            all_iqr = float(np.percentile(all_isfs, 75) - np.percentile(all_isfs, 25)) if len(all_isfs) >= 4 else None
            all_cv = (float(np.std(all_isfs, ddof=1)) /
                      (float(np.mean(all_isfs)) + 1e-6)) if len(all_isfs) >= 2 else None

            rec = {
                'patient': p['name'],
                'n_all_corrections': len(all_corrections),
                'n_calm_corrections': len(calm_corrections),
                'calm_fraction': round(len(calm_corrections) /
                                       (len(all_corrections) + 1e-6), 2),
                'mean_isf_all': round(float(np.mean(all_isfs)), 1),
                'mean_isf_profile': round(float(np.mean([c['isf_profile']
                                                         for c in all_corrections])), 1),
                'isf_iqr_all': round(all_iqr, 1) if all_iqr else None,
                'isf_cv_all': round(all_cv, 2) if all_cv else None,
            }
            if calm_isfs:
                calm_iqr = (float(np.percentile(calm_isfs, 75) -
                                  np.percentile(calm_isfs, 25))
                            if len(calm_isfs) >= 4 else None)
                calm_cv = (float(np.std(calm_isfs, ddof=1)) /
                           (float(np.mean(calm_isfs)) + 1e-6)
                           ) if len(calm_isfs) >= 2 else None
                rec['mean_isf_calm'] = round(float(np.mean(calm_isfs)), 1)
                rec['isf_iqr_calm'] = round(calm_iqr, 1) if calm_iqr else None
                rec['isf_cv_calm'] = round(calm_cv, 2) if calm_cv else None
                rec['calm_vs_all_ratio'] = round(
                    float(np.mean(calm_isfs)) / (float(np.mean(all_isfs)) + 1e-6), 2)
            if detail:
                rec['calm_corrections'] = calm_corrections[:5]
            results['per_patient'].append(rec)
        else:
            results['per_patient'].append({
                'patient': p['name'], 'n_all_corrections': 0,
                'note': 'No isolated corrections found'})

    with_data = [r for r in results['per_patient'] if r.get('n_all_corrections', 0) > 0]
    results['n_patients_with_data'] = len(with_data)
    with_calm = [r for r in with_data if r.get('n_calm_corrections', 0) > 0]
    results['n_patients_with_calm'] = len(with_calm)
    if with_calm:
        results['mean_calm_fraction'] = round(
            float(np.mean([r['calm_fraction'] for r in with_calm])), 2)
        results['mean_isf_calm'] = round(
            float(np.mean([r['mean_isf_calm'] for r in with_calm])), 1)
    if with_data:
        results['mean_isf_all'] = round(
            float(np.mean([r['mean_isf_all'] for r in with_data])), 1)
    return results


# ─── EXP-1307: CR by Time-of-Day ────────────────────────────────────
def exp_1307_cr_timeblock(patients, detail=False, preconditions=None):
    """Analyze carb ratio effectiveness by meal time block.

    Group meals into breakfast, lunch, dinner, late. Compute post-meal
    glucose rise / carbs as effective CR impact. Flag time blocks with
    consistent excursions >180 mg/dL.
    """
    results = {'name': 'EXP-1307: CR by time-of-day',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'cr_assessment'}

    POST_MEAL_WINDOW = 3 * STEPS_PER_HOUR  # 3 hours

    for p in patients:
        met, reason = check_precondition(p, preconditions, 'cr_assessment')
        if not met:
            results['per_patient'].append({
                'patient': p['name'], 'skipped': True, 'reason': reason})
            continue

        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)

        # Collect meals by time block
        block_meals = defaultdict(list)
        last_meal_step = -STEPS_PER_HOUR * 3

        for i in range(n):
            if carbs[i] < 5:
                continue
            if i - last_meal_step < STEPS_PER_HOUR * 2:
                continue  # too close to previous meal
            last_meal_step = i

            step_in_day = i % STEPS_PER_DAY
            mb = get_meal_block(step_in_day)
            if mb < 0:
                continue  # overnight meal — skip

            if i + POST_MEAL_WINDOW >= n:
                continue
            post_glucose = glucose[i:i + POST_MEAL_WINDOW]
            valid_post = ~np.isnan(post_glucose)
            if valid_post.sum() < POST_MEAL_WINDOW * 0.4:
                continue

            pre_bg = glucose[max(0, i - 3):i + 1]
            pre_bg = pre_bg[~np.isnan(pre_bg)]
            if len(pre_bg) == 0:
                continue
            bg_start = float(np.mean(pre_bg))
            bg_peak = float(np.nanmax(post_glucose))
            bg_rise = bg_peak - bg_start

            meal_bolus = float(np.sum(bolus[max(0, i - 3):min(n, i + 6)]))

            block_meals[mb].append({
                'carbs': float(carbs[i]),
                'bolus': round(meal_bolus, 2),
                'bg_start': round(bg_start, 1),
                'bg_peak': round(bg_peak, 1),
                'bg_rise': round(bg_rise, 1),
                'rise_per_carb': round(bg_rise / (carbs[i] + 1e-6), 2),
                'exceeded_180': bg_peak > 180,
            })

        if not any(block_meals.values()):
            results['per_patient'].append({
                'patient': p['name'], 'n_meals': 0,
                'note': 'No qualifying meals found'})
            continue

        block_summary = {}
        flagged_blocks = []
        for mb in range(4):
            meals = block_meals.get(mb, [])
            if not meals:
                block_summary[MEAL_BLOCK_NAMES[mb]] = {'n_meals': 0}
                continue
            rises = [m['bg_rise'] for m in meals]
            rise_per_carb = [m['rise_per_carb'] for m in meals]
            pct_exceed = sum(1 for m in meals if m['exceeded_180']) / len(meals) * 100

            block_summary[MEAL_BLOCK_NAMES[mb]] = {
                'n_meals': len(meals),
                'mean_bg_rise': round(float(np.mean(rises)), 1),
                'median_bg_rise': round(float(np.median(rises)), 1),
                'mean_rise_per_carb': round(float(np.mean(rise_per_carb)), 2),
                'pct_exceed_180': round(pct_exceed, 1),
                'mean_carbs': round(float(np.mean([m['carbs'] for m in meals])), 1),
                'mean_bolus': round(float(np.mean([m['bolus'] for m in meals])), 2),
            }
            if pct_exceed > 50:
                flagged_blocks.append(MEAL_BLOCK_NAMES[mb])

        total_meals = sum(len(v) for v in block_meals.values())
        rec = {
            'patient': p['name'],
            'n_meals': total_meals,
            'block_summary': block_summary,
            'flagged_blocks': flagged_blocks,
        }
        if detail:
            rec['meals_by_block'] = {MEAL_BLOCK_NAMES[k]: v[:3]
                                     for k, v in block_meals.items() if v}
        results['per_patient'].append(rec)

    with_data = [r for r in results['per_patient'] if r.get('n_meals', 0) > 0]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        results['total_meals_analyzed'] = sum(r['n_meals'] for r in with_data)
        # Aggregate which blocks are most problematic
        block_flag_counts = defaultdict(int)
        for r in with_data:
            for b in r.get('flagged_blocks', []):
                block_flag_counts[b] += 1
        results['block_flag_counts'] = dict(block_flag_counts)
    return results


# ─── EXP-1308: Fidelity Improvement Tracking ────────────────────────
def exp_1308_fidelity_tracking(patients, detail=False, preconditions=None):
    """Track weekly fidelity metrics over time to detect improvement/degradation.

    Compute R², RMSE, conservation % per week. Detect when fidelity crosses
    the reliable threshold and whether trend is improving.
    """
    results = {'name': 'EXP-1308: Fidelity improvement tracking',
               'n_patients': len(patients), 'per_patient': []}

    WEEK_STEPS = 7 * STEPS_PER_DAY
    RELIABLE_R2 = -0.5  # threshold from precondition framework

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        n = len(glucose)
        n_weeks = n // WEEK_STEPS

        if n_weeks < 3:
            results['per_patient'].append({
                'patient': p['name'], 'n_weeks': n_weeks,
                'note': 'Insufficient data for weekly tracking'})
            continue

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']
        dg = np.diff(glucose)
        dg = np.append(dg, 0)

        weekly_metrics = []
        for week in range(n_weeks):
            ws = week * WEEK_STEPS
            we = ws + WEEK_STEPS

            w_dg = dg[ws:we]
            w_net = net_flux[ws:we]
            w_glucose = glucose[ws:we]
            valid = (~np.isnan(w_glucose) & ~np.isnan(w_dg) &
                     (np.abs(w_dg) < 50))

            if valid.sum() < STEPS_PER_DAY:
                weekly_metrics.append({
                    'week': week, 'r2': None, 'rmse': None,
                    'pct_conserved': None, 'cgm_coverage': None})
                continue

            residual = w_dg[valid] - w_net[valid]
            rmse = float(np.sqrt(np.mean(residual ** 2)))
            ss_res = float(np.sum(residual ** 2))
            ss_tot = float(np.sum((w_dg[valid] - np.mean(w_dg[valid])) ** 2))
            r2 = 1 - ss_res / (ss_tot + 1e-10)
            pct_conserved = float(np.mean(np.abs(residual) < 5) * 100)
            cgm_cov = float(np.mean(~np.isnan(w_glucose)) * 100)

            weekly_metrics.append({
                'week': week,
                'r2': round(float(r2), 3),
                'rmse': round(rmse, 2),
                'pct_conserved': round(pct_conserved, 1),
                'cgm_coverage': round(cgm_cov, 1),
            })

        # Trend analysis: linear fit on R² over weeks
        valid_weeks = [w for w in weekly_metrics if w['r2'] is not None]
        if len(valid_weeks) >= 3:
            week_nums = np.array([w['week'] for w in valid_weeks], dtype=float)
            r2_vals = np.array([w['r2'] for w in valid_weeks])
            rmse_vals = np.array([w['rmse'] for w in valid_weeks])

            r2_trend = np.polyfit(week_nums, r2_vals, 1)
            rmse_trend = np.polyfit(week_nums, rmse_vals, 1)

            # When does R² cross the reliable threshold?
            crossed_weeks = [w['week'] for w in valid_weeks
                            if w['r2'] is not None and w['r2'] > RELIABLE_R2]
            first_reliable = min(crossed_weeks) if crossed_weeks else None

            # Classification
            if r2_trend[0] > 0.01:
                trend_class = 'improving'
            elif r2_trend[0] < -0.01:
                trend_class = 'degrading'
            else:
                trend_class = 'stable'

            rec = {
                'patient': p['name'],
                'n_weeks': len(valid_weeks),
                'r2_first': round(float(r2_vals[0]), 3),
                'r2_last': round(float(r2_vals[-1]), 3),
                'r2_trend_slope': round(float(r2_trend[0]), 4),
                'rmse_trend_slope': round(float(rmse_trend[0]), 4),
                'trend_class': trend_class,
                'first_reliable_week': first_reliable,
                'n_reliable_weeks': len(crossed_weeks),
                'mean_r2': round(float(np.mean(r2_vals)), 3),
                'mean_rmse': round(float(np.mean(rmse_vals)), 2),
            }
            if detail:
                rec['weekly'] = weekly_metrics
            results['per_patient'].append(rec)
        else:
            results['per_patient'].append({
                'patient': p['name'], 'n_weeks': len(valid_weeks),
                'note': 'Insufficient valid weeks for trend analysis'})

    with_data = [r for r in results['per_patient'] if 'trend_class' in r]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        trend_dist = defaultdict(int)
        for r in with_data:
            trend_dist[r['trend_class']] += 1
        results['trend_distribution'] = dict(trend_dist)
        results['mean_r2_trend'] = round(
            float(np.mean([r['r2_trend_slope'] for r in with_data])), 4)
        results['n_ever_reliable'] = sum(
            1 for r in with_data if r['first_reliable_week'] is not None)
    return results


# ─── EXP-1309: UAM-Augmented Conservation ────────────────────────────
def exp_1309_uam_augmented(patients, detail=False, preconditions=None):
    """Improve the physics model by detecting and adding UAM supply.

    When actual dBG/dt >> predicted net_flux AND no carbs logged,
    estimate UAM supply and add it to the supply term. Recompute R².
    """
    results = {'name': 'EXP-1309: UAM-augmented conservation',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        carbs = df['carbs'].values
        n = len(glucose)

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']
        supply = sd['supply']
        demand = sd['demand']

        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)

        if valid.sum() < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'],
                'note': 'Insufficient valid data'})
            continue

        # Baseline R²
        residual_base = dg[valid] - net_flux[valid]
        ss_res_base = float(np.sum(residual_base ** 2))
        ss_tot = float(np.sum((dg[valid] - np.mean(dg[valid])) ** 2))
        r2_base = 1 - ss_res_base / (ss_tot + 1e-10)

        # Detect UAM events: dBG/dt >> net_flux AND no carbs in ±1h window
        uam_supply = np.zeros(n)
        uam_threshold = 3.0  # mg/dL per 5min = ~36 mg/dL/hr unexplained rise
        n_uam_events = 0
        uam_magnitudes = []

        for i in range(n):
            if not valid[i]:
                continue
            excess = dg[i] - net_flux[i]
            if excess <= uam_threshold:
                continue
            # Check no carbs in ±1h
            cw_start = max(0, i - STEPS_PER_HOUR)
            cw_end = min(n, i + STEPS_PER_HOUR)
            if np.sum(carbs[cw_start:cw_end]) > 1:
                continue
            uam_supply[i] = excess
            n_uam_events += 1
            uam_magnitudes.append(float(excess))

        # Augmented conservation: add UAM supply
        augmented_flux = net_flux + uam_supply
        residual_aug = dg[valid] - augmented_flux[valid]
        ss_res_aug = float(np.sum(residual_aug ** 2))
        r2_aug = 1 - ss_res_aug / (ss_tot + 1e-10)

        # RMSE comparison
        rmse_base = float(np.sqrt(np.mean(residual_base ** 2)))
        rmse_aug = float(np.sqrt(np.mean(residual_aug ** 2)))

        rec = {
            'patient': p['name'],
            'n_valid': int(valid.sum()),
            'r2_baseline': round(float(r2_base), 3),
            'r2_augmented': round(float(r2_aug), 3),
            'r2_improvement': round(float(r2_aug - r2_base), 3),
            'rmse_baseline': round(rmse_base, 2),
            'rmse_augmented': round(rmse_aug, 2),
            'n_uam_events': n_uam_events,
            'uam_rate_per_day': round(n_uam_events / (valid.sum() / STEPS_PER_DAY + 1e-6), 1),
            'mean_uam_magnitude': round(float(np.mean(uam_magnitudes)), 2) if uam_magnitudes else 0,
            'total_uam_supply': round(float(np.sum(uam_supply)), 1),
        }
        results['per_patient'].append(rec)

    with_data = [r for r in results['per_patient'] if 'r2_baseline' in r]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        results['mean_r2_baseline'] = round(
            float(np.mean([r['r2_baseline'] for r in with_data])), 3)
        results['mean_r2_augmented'] = round(
            float(np.mean([r['r2_augmented'] for r in with_data])), 3)
        results['mean_r2_improvement'] = round(
            float(np.mean([r['r2_improvement'] for r in with_data])), 3)
        results['mean_uam_per_day'] = round(
            float(np.mean([r['uam_rate_per_day'] for r in with_data])), 1)
        results['n_with_uam'] = sum(1 for r in with_data if r['n_uam_events'] > 0)
    return results


# ─── EXP-1310: Patient Archetype Clustering ──────────────────────────
def exp_1310_clustering(patients, detail=False, preconditions=None):
    """Cluster patients by therapy profile into archetypes.

    Features: mean basal change%, ISF ratio, CR score, TIR, CV,
    loop aggressiveness, fidelity R². K-means with k=3.
    """
    results = {'name': 'EXP-1310: Patient archetype clustering',
               'n_patients': len(patients), 'per_patient': []}

    # Compute features for each patient
    feature_names = ['mean_basal_ratio', 'isf_ratio', 'tir', 'glucose_cv',
                     'loop_aggressiveness', 'fidelity_r2', 'mean_bg']
    patient_features = []
    patient_names = []

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        basal_ratio = pk[:, 2] * 2.0
        isf_profile = pk[:, 7] * 200.0
        n = len(glucose)

        valid_g = glucose[~np.isnan(glucose)]
        if len(valid_g) < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'],
                'note': 'Insufficient data for clustering'})
            continue

        # TIR: 70-180 mg/dL
        tir = float(np.mean((valid_g >= 70) & (valid_g <= 180)) * 100)
        # Glucose CV
        glucose_cv = float(np.std(valid_g) / (np.mean(valid_g) + 1e-6))
        mean_bg = float(np.mean(valid_g))

        # Mean basal ratio (how much loop adjusts)
        valid_br = basal_ratio[~np.isnan(glucose)]
        mean_br = float(np.mean(valid_br)) if len(valid_br) > 0 else 1.0

        # Loop aggressiveness: std of basal_ratio (more variable = more aggressive)
        loop_agg = float(np.std(valid_br)) if len(valid_br) > 0 else 0.0

        # ISF ratio: measured ISF / profile ISF
        # Quick estimation from corrections
        isf_measured = []
        for i in range(n):
            if bolus[i] < 0.3:
                continue
            if np.isnan(glucose[i]) or glucose[i] <= 120:
                continue
            cw = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[cw]) > 2:
                continue
            future_end = min(n, i + DIA_STEPS)
            if future_end - i < STEPS_PER_HOUR * 2:
                continue
            future_bg = glucose[i:future_end]
            if np.sum(~np.isnan(future_bg)) < len(future_bg) * 0.3:
                continue
            delta = glucose[i] - np.nanmin(future_bg)
            if delta > 10:
                isf_measured.append(delta / bolus[i])

        if isf_measured:
            mean_isf_measured = float(np.mean(isf_measured))
            mean_isf_prof = float(np.mean(isf_profile[~np.isnan(glucose)]))
            isf_ratio = mean_isf_measured / (mean_isf_prof + 1e-6)
        else:
            isf_ratio = 1.0  # assume nominal if no corrections

        # Fidelity R²
        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']
        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid_both = (~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50))
        if valid_both.sum() > 100:
            residual = dg[valid_both] - net_flux[valid_both]
            ss_res = float(np.sum(residual ** 2))
            ss_tot = float(np.sum((dg[valid_both] - np.mean(dg[valid_both])) ** 2))
            fidelity_r2 = 1 - ss_res / (ss_tot + 1e-10)
        else:
            fidelity_r2 = -1.0

        features = [mean_br, isf_ratio, tir, glucose_cv,
                    loop_agg, fidelity_r2, mean_bg]
        patient_features.append(features)
        patient_names.append(p['name'])

        results['per_patient'].append({
            'patient': p['name'],
            'mean_basal_ratio': round(mean_br, 2),
            'isf_ratio': round(isf_ratio, 2),
            'tir': round(tir, 1),
            'glucose_cv': round(glucose_cv, 3),
            'loop_aggressiveness': round(loop_agg, 2),
            'fidelity_r2': round(float(fidelity_r2), 3),
            'mean_bg': round(mean_bg, 1),
        })

    if len(patient_features) < 3:
        results['note'] = 'Too few patients for clustering'
        return results

    # K-means clustering (manual implementation — no sklearn dependency)
    X = np.array(patient_features)
    # Normalize features to [0, 1]
    X_min = X.min(axis=0)
    X_max = X.max(axis=0)
    X_range = X_max - X_min
    X_range[X_range < 1e-10] = 1.0
    X_norm = (X - X_min) / X_range

    k = min(3, len(patient_features))

    # Initialize centroids by spreading across data
    np.random.seed(42)
    indices = np.linspace(0, len(X_norm) - 1, k, dtype=int)
    centroids = X_norm[indices].copy()

    # Run K-means for 50 iterations
    labels = np.zeros(len(X_norm), dtype=int)
    for iteration in range(50):
        # Assign labels
        for i in range(len(X_norm)):
            dists = np.sum((centroids - X_norm[i]) ** 2, axis=1)
            labels[i] = int(np.argmin(dists))
        # Update centroids
        new_centroids = centroids.copy()
        for c in range(k):
            members = X_norm[labels == c]
            if len(members) > 0:
                new_centroids[c] = members.mean(axis=0)
        if np.allclose(centroids, new_centroids, atol=1e-6):
            break
        centroids = new_centroids

    # Name clusters by mean TIR (feature index 2) and mean fidelity (index 5)
    cluster_profiles = {}
    archetype_names = ['well-calibrated', 'needs-tuning', 'miscalibrated']
    # Sort clusters by TIR (descending) to assign names
    cluster_tirs = []
    for c in range(k):
        members = X[labels == c]
        if len(members) > 0:
            cluster_tirs.append((c, float(np.mean(members[:, 2]))))
        else:
            cluster_tirs.append((c, 0.0))
    cluster_tirs.sort(key=lambda x: -x[1])
    cluster_name_map = {}
    for rank, (c, _) in enumerate(cluster_tirs):
        name = archetype_names[rank] if rank < len(archetype_names) else f'cluster-{c}'
        cluster_name_map[c] = name

    for c in range(k):
        members = X[labels == c]
        member_names = [patient_names[i] for i in range(len(labels)) if labels[i] == c]
        if len(members) == 0:
            continue
        profile = {fn: round(float(np.mean(members[:, fi])), 2)
                   for fi, fn in enumerate(feature_names)}
        cluster_profiles[cluster_name_map[c]] = {
            'n_patients': len(members),
            'members': member_names,
            'profile': profile,
        }

    # Add cluster assignment to per-patient results
    for i, rec in enumerate(results['per_patient']):
        if rec['patient'] in patient_names:
            idx = patient_names.index(rec['patient'])
            rec['cluster'] = cluster_name_map[int(labels[idx])]
            rec['cluster_id'] = int(labels[idx])

    results['clusters'] = cluster_profiles
    results['n_clusters'] = k
    results['feature_names'] = feature_names
    return results


# ─── Experiment Registry ────────────────────────────────────────────

EXPERIMENTS = {
    1301: ('Response curve ISF', exp_1301_response_curve_isf),
    1302: ('Dawn detection via glucose', exp_1302_dawn_glucose),
    1303: ('Reflexive basal simulation', exp_1303_reflexive_simulation),
    1304: ('Multi-week recommendation stability', exp_1304_stability),
    1305: ('Conservation violation decomposition', exp_1305_violation_decomp),
    1306: ('Calm-window ISF', exp_1306_calm_isf),
    1307: ('CR by time-of-day', exp_1307_cr_timeblock),
    1308: ('Fidelity improvement tracking', exp_1308_fidelity_tracking),
    1309: ('UAM-augmented conservation', exp_1309_uam_augmented),
    1310: ('Patient archetype clustering', exp_1310_clustering),
}


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1301-1310: Advanced Therapy Assessment')
    parser.add_argument('--exp', type=int, help='Run single experiment')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    args = parser.parse_args()

    print(f"Loading patients (max={args.max_patients})...")
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    # ── Precondition Assessment (always runs first) ──────────────
    print(f"\n{'='*60}")
    print("PRECONDITION ASSESSMENT")
    print(f"{'='*60}")
    precond_results = {}
    for p in patients:
        pc = assess_preconditions(p)
        precond_results[p['name']] = pc
        met = sum(1 for v in pc['preconditions'].values() if v['met'])
        total = len(pc['preconditions'])
        m = pc['metrics']
        print(f"  {p['name']}: {met}/{total} preconditions met | "
              f"CGM={m['cgm_coverage_pct']}% insulin={m['insulin_telemetry_pct']}% "
              f"fidelity_R²={m['fidelity_r2']} conserved={m['pct_conserved']}% "
              f"corr={m.get('n_corrections', 0)} meals={m.get('n_bolused_meals', 0)}")
        for pname, pdata in pc['preconditions'].items():
            if not pdata['met']:
                print(f"    ✗ {pname}: {pdata['reason']}")

    if args.save:
        with open('preconditions.json', 'w') as f:
            json.dump(precond_results, f, indent=2, default=str)
        print(f"\n  Saved: preconditions.json")

    # ── Run Experiments ──────────────────────────────────────────
    exps_to_run = [args.exp] if args.exp else sorted(EXPERIMENTS.keys())

    all_results = {}
    for eid in exps_to_run:
        name, func = EXPERIMENTS[eid]
        print(f"\n{'='*60}")
        print(f"EXP-{eid}: {name}")
        print(f"{'='*60}")
        t0 = time.time()
        try:
            result = func(patients, detail=args.detail,
                         preconditions=precond_results)
            elapsed = time.time() - t0
            result['elapsed_sec'] = round(elapsed, 1)
            all_results[eid] = result

            print(f"  Completed in {elapsed:.1f}s")
            for k, v in result.items():
                if k not in ('per_patient', 'elapsed_sec', 'name',
                             'clusters', 'feature_names', 'block_flag_counts',
                             'weekly', 'windows', 'scan'):
                    print(f"  {k}: {v}")

            if args.save:
                fn = f"exp-{eid}_therapy.json"
                with open(fn, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved: {fn}")

        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback
            traceback.print_exc()
            all_results[eid] = {'error': str(e)}

    print(f"\n{'='*60}")
    print("THERAPY ASSESSMENT SUMMARY")
    print(f"{'='*60}")
    for eid, result in all_results.items():
        name = EXPERIMENTS[eid][0]
        if 'error' in result:
            print(f"  EXP-{eid} {name}: FAILED - {result['error']}")
        else:
            key_metrics = {
                1301: f"curve_ISF={result.get('mean_curve_isf','?')}, tau={result.get('mean_tau','?')}h, fit_R²={result.get('mean_fit_r2','?')}",
                1302: f"dawn={result.get('detection_rate','?')}, slope_diff={result.get('mean_slope_diff','?')} mg/dL/h",
                1303: f"optimal_adj={result.get('mean_optimal_adjustment','?')}%, improvement={result.get('mean_improvement_pct','?')}%",
                1304: f"high_conf={result.get('n_high_confidence','?')}, low_conf={result.get('n_low_confidence','?')}, basal_CV={result.get('mean_basal_cv','?')}",
                1305: f"violated={result.get('mean_pct_violated','?')}%, UAM={result.get('mean_pct_uam','?')}%, exercise={result.get('mean_pct_exercise','?')}%",
                1306: f"calm_frac={result.get('mean_calm_fraction','?')}, calm_ISF={result.get('mean_isf_calm','?')}, all_ISF={result.get('mean_isf_all','?')}",
                1307: f"meals={result.get('total_meals_analyzed','?')}, flags={result.get('block_flag_counts','?')}",
                1308: f"trends={result.get('trend_distribution','?')}, mean_R²_trend={result.get('mean_r2_trend','?')}",
                1309: f"R²_base={result.get('mean_r2_baseline','?')}, R²_aug={result.get('mean_r2_augmented','?')}, Δ={result.get('mean_r2_improvement','?')}",
                1310: f"clusters={result.get('n_clusters','?')}, archetypes={list(result.get('clusters',{}).keys())}",
            }
            print(f"  EXP-{eid} {name}: {key_metrics.get(eid, 'done')}")

    return all_results


if __name__ == '__main__':
    main()
