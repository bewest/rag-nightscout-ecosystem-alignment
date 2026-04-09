#!/usr/bin/env python3
"""EXP-1321–1330: Basal ground truth, UAM-aware ISF, hepatic rhythm,
sensor artifact detection, overnight titration, therapy simulation.

Builds on EXP-1311-1320 breakthroughs:
1. UAM augmentation: R² from -0.508 to +0.351 (EXP-1309)
2. Response-curve ISF: Exponential decay R²=0.805, τ=2.0h (EXP-1301)
3. UAM classification: 82% meal, 8% hepatic, 7% artifact, 3% slow (EXP-1313)
4. Critical finding: UAM-aware reverses basal recs for 8/11 patients (EXP-1315)
5. Universal UAM threshold 1.0 mg/dL/5min works for 100% (EXP-1320)
6. 3 archetypes: well-calibrated (d,h,j,k), needs-tuning, miscalibrated (EXP-1310)
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
BLOCK_RANGES = [(0, 6), (6, 10), (10, 14), (14, 18), (18, 22), (22, 24)]

UAM_THRESHOLD = 1.0  # Universal UAM threshold from EXP-1320

# Archetype assignments from EXP-1310
ARCHETYPES = {
    'well-calibrated': ['d', 'h', 'j', 'k'],
    'needs-tuning': ['b', 'c', 'e', 'f', 'g', 'i'],
    'miscalibrated': ['a'],
}
PATIENT_ARCHETYPE = {}
for _arch, _members in ARCHETYPES.items():
    for _m in _members:
        PATIENT_ARCHETYPE[_m] = _arch

WELL_CALIBRATED = {'d', 'h', 'j', 'k'}
NEEDS_TUNING = {'b', 'c', 'e', 'f', 'g', 'i'}
MISCALIBRATED = {'a'}

TAU_CANDIDATES = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]


def get_time_block(step_in_day):
    """Map a step within a day to a 6-block time block index."""
    hour = (step_in_day / STEPS_PER_HOUR) % 24
    for i, (lo, hi) in enumerate(BLOCK_RANGES):
        if lo <= hour < hi:
            return i
    return 5


def compute_uam_supply(df, pk):
    """Compute UAM supply: max(0, actual_dBG/dt - net_flux) when no carbs.

    Returns (sd_dict, uam_supply, uam_mask, augmented_supply).
    """
    sd = compute_supply_demand(df, pk)
    glucose = df['glucose'].values.astype(float)
    carbs = df['carbs'].values
    n = len(glucose)

    dg = np.diff(glucose)
    dg = np.append(dg, 0)
    net_flux = sd['net']

    residual = dg - net_flux
    no_carbs = np.ones(n, dtype=bool)
    for i in range(n):
        if carbs[i] >= 2:
            s, e = max(0, i - 6), min(n, i + 36)
            no_carbs[s:e] = False

    uam_supply = np.where(
        no_carbs & (residual > UAM_THRESHOLD) & ~np.isnan(glucose) & ~np.isnan(dg),
        residual, 0.0)
    uam_mask = uam_supply > 0
    augmented_supply = sd['supply'] + uam_supply
    return sd, uam_supply, uam_mask, augmented_supply


def find_corrections(p, min_bolus=0.3, carb_window=6, min_bg=150):
    """Find isolated correction events. Returns list of indices."""
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    bolus = df['bolus'].values
    carbs = df['carbs'].values
    n = len(glucose)
    corrections = []
    for i in range(n):
        if bolus[i] >= min_bolus and not np.isnan(glucose[i]) and glucose[i] > min_bg:
            cw = slice(max(0, i - carb_window), min(n, i + carb_window))
            if np.sum(carbs[cw]) < 2:
                corrections.append(i)
    return corrections


def fit_response_curve(glucose, bolus_amount, start_idx, n_steps=36):
    """Fit exponential decay to post-correction glucose using tau grid search.
    Returns (isf, tau_hours, fit_r2) or None.
    """
    n = len(glucose)
    end_idx = min(start_idx + n_steps, n)
    window = glucose[start_idx:end_idx]
    tv = ~np.isnan(window)
    if tv.sum() < n_steps * 0.5:
        return None
    bg_start = float(window[0])
    t_hours = np.arange(len(window)) * (5.0 / 60.0)

    best_sse, best_tau, best_amp = np.inf, 1.0, 0.0
    for tau_c in TAU_CANDIDATES:
        basis = 1.0 - np.exp(-t_hours / tau_c)
        bv = basis[tv]
        target = bg_start - window[tv]
        denom = float(np.sum(bv ** 2))
        if denom < 1e-6:
            continue
        amp = float(np.sum(bv * target) / denom)
        if amp < 5:
            continue
        predicted = bg_start - amp * basis
        sse = float(np.sum((window[tv] - predicted[tv]) ** 2))
        if sse < best_sse:
            best_sse, best_tau, best_amp = sse, tau_c, amp

    if best_amp < 5:
        return None
    mean_bg = float(np.nanmean(window[tv]))
    ss_tot = float(np.sum((window[tv] - mean_bg) ** 2))
    fit_r2 = 1 - best_sse / (ss_tot + 1e-10)
    isf = best_amp / float(bolus_amount)
    return isf, best_tau, fit_r2


# ─── EXP-1321: Basal Ground Truth via Well-Calibrated Patients ───────
def exp_1321_basal_ground_truth(patients, detail=False, preconditions=None):
    """Use well-calibrated archetype patients (d,h,j,k) as ground truth.

    For each well-calibrated patient, compute what basal rate would match
    actual average delivery during fasting overnight windows.  Compare
    profile_basal, actual_delivery, UAM-filtered rec, and raw rec.
    """
    results = {'name': 'EXP-1321: Basal ground truth via well-calibrated patients',
               'n_patients': len(patients), 'per_patient': []}

    gt_basals = []
    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        temp_rate = df['temp_rate'].values
        n = len(glucose)
        n_days = n // STEPS_PER_DAY
        is_gt = p['name'] in WELL_CALIBRATED

        sd, uam_sup, uam_mask, _ = compute_uam_supply(df, pk)
        net_flux = sd['net']
        demand = sd['demand']
        scheduled_rate = get_scheduled_basal_rate(p)

        # Fasting overnight delivery — actual delivery during fasting 0-6 AM
        overnight_rates = []
        overnight_drifts = []
        for d in range(n_days):
            start = d * STEPS_PER_DAY
            end = start + STEPS_PER_HOUR * 6
            if end > n:
                break
            ng = glucose[start:end]
            nb = bolus[start:end]
            nc = carbs[start:end]
            if np.sum(nb) > 0.1 or np.sum(nc) > 1:
                continue
            valid_g = ~np.isnan(ng)
            if valid_g.sum() < STEPS_PER_HOUR * 3:
                continue
            night_rates = temp_rate[start:end]
            nonzero = night_rates[night_rates > 0]
            if len(nonzero) == 0:
                continue
            night_rate = float(np.mean(nonzero))
            overnight_rates.append(night_rate)
            # Drift rate (mg/dL per hour)
            x = np.arange(len(ng))[valid_g] * (5.0 / 60.0)
            y = ng[valid_g]
            if len(x) >= 10:
                slope = float(np.polyfit(x, y, 1)[0])
                overnight_drifts.append(slope)

        if not overnight_rates:
            results['per_patient'].append({
                'patient': p['name'], 'archetype': PATIENT_ARCHETYPE.get(p['name'], 'unknown'),
                'note': 'No qualifying fasting nights'})
            continue

        actual_delivery = float(np.mean(overnight_rates))
        mean_drift = float(np.mean(overnight_drifts)) if overnight_drifts else 0.0

        # Raw basal recommendation
        fasting = np.ones(n, dtype=bool)
        for i in range(n):
            ws, we = max(0, i - STEPS_PER_HOUR * 2), min(n, i + STEPS_PER_HOUR * 2)
            if np.any(bolus[ws:we] > 0) or np.any(carbs[ws:we] > 0):
                fasting[i] = False
        fv = fasting & ~np.isnan(glucose)
        if fv.sum() > STEPS_PER_HOUR:
            raw_net = float(np.mean(net_flux[fv]))
            raw_demand = float(np.mean(demand[fv]))
            raw_change = -raw_net / (raw_demand + 1e-6)
            raw_change = max(-0.5, min(0.5, raw_change))
        else:
            raw_change = 0.0
        raw_rec = scheduled_rate * (1 + raw_change)

        # UAM-filtered recommendation
        clean = fasting & ~uam_mask & ~np.isnan(glucose)
        if clean.sum() > STEPS_PER_HOUR:
            clean_net = float(np.mean(net_flux[clean]))
            clean_demand = float(np.mean(demand[clean]))
            uam_change = -clean_net / (clean_demand + 1e-6)
            uam_change = max(-0.5, min(0.5, uam_change))
        else:
            uam_change = 0.0
        uam_rec = scheduled_rate * (1 + uam_change)

        rec = {
            'patient': p['name'],
            'archetype': PATIENT_ARCHETYPE.get(p['name'], 'unknown'),
            'is_ground_truth': is_gt,
            'scheduled_rate': round(scheduled_rate, 3),
            'actual_delivery': round(actual_delivery, 3),
            'overnight_drift_mg_dl_h': round(mean_drift, 2),
            'n_fasting_nights': len(overnight_rates),
            'raw_rec_rate': round(raw_rec, 3),
            'raw_change_pct': round(raw_change * 100, 1),
            'uam_rec_rate': round(uam_rec, 3),
            'uam_change_pct': round(uam_change * 100, 1),
        }

        if is_gt:
            gt_basal = actual_delivery
            gt_basals.append(gt_basal)
            rec['ground_truth_basal'] = round(gt_basal, 3)
            rec['raw_vs_gt_error'] = round(abs(raw_rec - gt_basal), 3)
            rec['uam_vs_gt_error'] = round(abs(uam_rec - gt_basal), 3)
            rec['raw_closer'] = abs(raw_rec - gt_basal) < abs(uam_rec - gt_basal)

        results['per_patient'].append(rec)

    # Summary: which method is closer to ground truth?
    gt_recs = [r for r in results['per_patient'] if r.get('is_ground_truth')]
    results['n_ground_truth'] = len(gt_recs)
    if gt_recs:
        raw_errors = [r['raw_vs_gt_error'] for r in gt_recs]
        uam_errors = [r['uam_vs_gt_error'] for r in gt_recs]
        results['mean_raw_error'] = round(float(np.mean(raw_errors)), 3)
        results['mean_uam_error'] = round(float(np.mean(uam_errors)), 3)
        results['raw_wins'] = sum(1 for r in gt_recs if r.get('raw_closer'))
        results['uam_wins'] = len(gt_recs) - results['raw_wins']
        results['winning_method'] = 'raw' if results['raw_wins'] > results['uam_wins'] else 'uam_filtered'
    return results


# ─── EXP-1322: UAM-Aware Response Curve ISF ──────────────────────────
def exp_1322_uam_clean_isf(patients, detail=False, preconditions=None):
    """Run response-curve ISF (EXP-1301 method) on UAM-filtered corrections.

    A correction is "UAM-clean" if no UAM events occur in the 3h post-correction
    window.  Compare UAM-clean ISF vs all-corrections ISF.
    """
    results = {'name': 'EXP-1322: UAM-aware response curve ISF',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'correction_validation'}

    CORRECTION_WINDOW = 3 * STEPS_PER_HOUR

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
        n = len(glucose)

        _, _, uam_mask, _ = compute_uam_supply(df, pk)

        all_isfs = []
        clean_isfs = []

        for i in range(n):
            if bolus[i] < 0.3 or np.isnan(glucose[i]) or glucose[i] <= 150:
                continue
            cw = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[cw]) > 2:
                continue
            if i + CORRECTION_WINDOW >= n:
                continue
            if np.sum(bolus[i + 1:i + CORRECTION_WINDOW]) > 0.5:
                continue
            if np.sum(carbs[i + 1:i + CORRECTION_WINDOW]) > 2:
                continue

            fit = fit_response_curve(glucose, bolus[i], i, CORRECTION_WINDOW)
            if fit is None:
                continue
            isf, tau, r2 = fit
            all_isfs.append({'isf': isf, 'tau': tau, 'r2': r2})

            # Check if UAM-clean: no UAM events in post-correction window
            post_uam = uam_mask[i:i + CORRECTION_WINDOW]
            if np.sum(post_uam) == 0:
                clean_isfs.append({'isf': isf, 'tau': tau, 'r2': r2})

        if not all_isfs:
            results['per_patient'].append({
                'patient': p['name'], 'n_all': 0, 'n_clean': 0,
                'note': 'No qualifying corrections'})
            continue

        all_isf_vals = [c['isf'] for c in all_isfs]
        rec = {
            'patient': p['name'],
            'n_all_corrections': len(all_isfs),
            'n_clean_corrections': len(clean_isfs),
            'pct_clean': round(len(clean_isfs) / len(all_isfs) * 100, 1),
            'all_median_isf': round(float(np.median(all_isf_vals)), 1),
            'all_mean_isf': round(float(np.mean(all_isf_vals)), 1),
            'all_mean_tau': round(float(np.mean([c['tau'] for c in all_isfs])), 2),
            'all_mean_r2': round(float(np.mean([c['r2'] for c in all_isfs])), 3),
        }
        if clean_isfs:
            clean_isf_vals = [c['isf'] for c in clean_isfs]
            rec['clean_median_isf'] = round(float(np.median(clean_isf_vals)), 1)
            rec['clean_mean_isf'] = round(float(np.mean(clean_isf_vals)), 1)
            rec['clean_mean_tau'] = round(float(np.mean([c['tau'] for c in clean_isfs])), 2)
            rec['clean_mean_r2'] = round(float(np.mean([c['r2'] for c in clean_isfs])), 3)
            rec['isf_delta'] = round(rec['clean_median_isf'] - rec['all_median_isf'], 1)
            rec['uam_inflates_isf'] = rec['clean_median_isf'] < rec['all_median_isf']
        else:
            rec['note'] = 'No UAM-clean corrections found'
        results['per_patient'].append(rec)

    with_data = [r for r in results['per_patient']
                 if r.get('n_all_corrections', 0) > 0]
    results['n_patients_with_data'] = len(with_data)
    with_clean = [r for r in with_data if 'clean_median_isf' in r]
    if with_clean:
        results['mean_isf_delta'] = round(
            float(np.mean([r['isf_delta'] for r in with_clean])), 1)
        results['n_uam_inflates'] = sum(1 for r in with_clean
                                        if r.get('uam_inflates_isf'))
        results['hypothesis_supported'] = results['n_uam_inflates'] > len(with_clean) / 2
    return results


# ─── EXP-1323: Hepatic Rhythm Modeling ───────────────────────────────
def exp_1323_hepatic_rhythm(patients, detail=False, preconditions=None):
    """Fit circadian sine curve to hepatic UAM events (EXP-1313 found 8.1%).

    hepatic_rate(t) = A × sin(2π × (t - phase) / 24) + baseline
    """
    results = {'name': 'EXP-1323: Hepatic rhythm modeling',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        carbs = df['carbs'].values
        n = len(glucose)

        sd, uam_sup, uam_mask, _ = compute_uam_supply(df, pk)
        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg)

        if valid.sum() < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient data'})
            continue

        # Identify hepatic UAM events: pre-dawn 4-7 AM
        hepatic_hours = []
        hepatic_magnitudes = []
        in_run = False
        run_start = 0
        for i in range(n):
            if uam_mask[i] and valid[i]:
                if not in_run:
                    in_run = True
                    run_start = i
            else:
                if in_run:
                    step_in_day = run_start % STEPS_PER_DAY
                    hour = step_in_day / STEPS_PER_HOUR
                    seg_dg = dg[run_start:i]
                    mean_rate = float(np.nanmean(seg_dg))
                    if 4 <= hour < 7:
                        hepatic_hours.append(hour)
                        hepatic_magnitudes.append(abs(mean_rate))
                    in_run = False
        if in_run:
            step_in_day = run_start % STEPS_PER_DAY
            hour = step_in_day / STEPS_PER_HOUR
            if 4 <= hour < 7:
                hepatic_hours.append(hour)
                hepatic_magnitudes.append(abs(float(np.nanmean(dg[run_start:]))))

        n_hepatic = len(hepatic_hours)
        if n_hepatic < 3:
            results['per_patient'].append({
                'patient': p['name'], 'n_hepatic_events': n_hepatic,
                'note': 'Too few hepatic events for fitting'})
            continue

        # Aggregate hourly UAM event rate for sine fitting
        uam_counts = np.zeros(24)
        for i in range(n):
            if uam_mask[i] and valid[i]:
                h = int((i % STEPS_PER_DAY) / STEPS_PER_HOUR) % 24
                uam_counts[h] += 1

        n_days = max(1, n // STEPS_PER_DAY)
        hourly_rate = uam_counts / n_days

        # Fit sine: rate(t) = A × sin(2π(t - phase)/24) + baseline
        t = np.arange(24).astype(float)
        best_sse, best_A, best_phase, best_baseline = np.inf, 0, 5, 0
        for phase_c in np.arange(0, 24, 0.5):
            sin_basis = np.sin(2.0 * np.pi * (t - phase_c) / 24.0)
            X = np.column_stack([sin_basis, np.ones(24)])
            XtX = X.T @ X
            if np.linalg.det(XtX) < 1e-10:
                continue
            beta = np.linalg.solve(XtX, X.T @ hourly_rate)
            A_c, base_c = float(beta[0]), float(beta[1])
            fitted = A_c * sin_basis + base_c
            sse = float(np.sum((hourly_rate - fitted) ** 2))
            if sse < best_sse:
                best_sse = sse
                best_A, best_phase, best_baseline = A_c, phase_c, base_c

        ss_tot = float(np.sum((hourly_rate - np.mean(hourly_rate)) ** 2))
        fit_r2 = 1 - best_sse / (ss_tot + 1e-10) if ss_tot > 1e-6 else 0.0
        strong_rhythm = fit_r2 > 0.3 and abs(best_A) > 0.5

        rec = {
            'patient': p['name'],
            'n_hepatic_events': n_hepatic,
            'mean_hepatic_hour': round(float(np.mean(hepatic_hours)), 1),
            'mean_hepatic_magnitude': round(float(np.mean(hepatic_magnitudes)), 2),
            'sine_amplitude': round(abs(best_A), 3),
            'sine_phase_hour': round(best_phase % 24, 1),
            'sine_baseline': round(best_baseline, 3),
            'fit_r2': round(fit_r2, 3),
            'strong_rhythm': strong_rhythm,
        }
        if detail:
            rec['hourly_rate'] = [round(float(v), 2) for v in hourly_rate]
        results['per_patient'].append(rec)

    with_data = [r for r in results['per_patient']
                 if r.get('n_hepatic_events', 0) >= 3]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        results['n_strong_rhythm'] = sum(1 for r in with_data if r.get('strong_rhythm'))
        phases = [r['sine_phase_hour'] for r in with_data]
        results['mean_phase_hour'] = round(float(np.mean(phases)), 1)
        results['mean_fit_r2'] = round(
            float(np.mean([r['fit_r2'] for r in with_data])), 3)
    return results


# ─── EXP-1324: Sensor Artifact Auto-Detection ───────────────────────
def exp_1324_artifact_detection(patients, detail=False, preconditions=None):
    """Build artifact detector from EXP-1313 findings.

    Flag: |dBG/dt| > 5 mg/dL per 5min that reverses within 30min.
    Test: does removing artifacts improve fidelity R²?
    """
    results = {'name': 'EXP-1324: Sensor artifact auto-detection',
               'n_patients': len(patients), 'per_patient': []}

    SPIKE_THRESHOLD = 5.0  # mg/dL per 5-min step
    REVERSAL_WINDOW = 6    # steps = 30min

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        n = len(glucose)

        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)

        if valid.sum() < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient data'})
            continue

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']

        # Detect spike-and-reversal artifacts
        artifact_mask = np.zeros(n, dtype=bool)
        n_artifacts = 0
        for i in range(n - REVERSAL_WINDOW):
            if not valid[i]:
                continue
            if abs(dg[i]) > SPIKE_THRESHOLD:
                reversal_end = min(n, i + REVERSAL_WINDOW)
                post_dg = dg[i + 1:reversal_end]
                post_valid = valid[i + 1:reversal_end]
                if len(post_dg[post_valid]) == 0:
                    continue
                mean_post = float(np.mean(post_dg[post_valid]))
                if dg[i] > SPIKE_THRESHOLD and mean_post < -SPIKE_THRESHOLD * 0.4:
                    artifact_mask[i:reversal_end] = True
                    n_artifacts += 1
                elif dg[i] < -SPIKE_THRESHOLD and mean_post > SPIKE_THRESHOLD * 0.4:
                    artifact_mask[i:reversal_end] = True
                    n_artifacts += 1

        pct_artifact = float(artifact_mask.sum()) / (valid.sum() + 1e-6) * 100

        # Fidelity R² with all data
        ss_tot = float(np.sum((dg[valid] - np.mean(dg[valid])) ** 2))
        residual_all = dg[valid] - net_flux[valid]
        r2_all = 1 - float(np.sum(residual_all ** 2)) / (ss_tot + 1e-10)

        # Fidelity R² without artifacts
        clean = valid & ~artifact_mask
        if clean.sum() > STEPS_PER_DAY * 0.5:
            ss_tot_clean = float(np.sum((dg[clean] - np.mean(dg[clean])) ** 2))
            residual_clean = dg[clean] - net_flux[clean]
            r2_clean = 1 - float(np.sum(residual_clean ** 2)) / (ss_tot_clean + 1e-10)
        else:
            r2_clean = r2_all

        results['per_patient'].append({
            'patient': p['name'],
            'n_spike_events': n_artifacts,
            'n_artifact_steps': int(artifact_mask.sum()),
            'pct_artifact': round(pct_artifact, 1),
            'r2_all_data': round(r2_all, 3),
            'r2_clean': round(r2_clean, 3),
            'r2_improvement': round(r2_clean - r2_all, 3),
            'removal_helps': r2_clean > r2_all + 0.01,
        })

    with_data = [r for r in results['per_patient'] if 'n_spike_events' in r]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        results['mean_pct_artifact'] = round(
            float(np.mean([r['pct_artifact'] for r in with_data])), 1)
        results['mean_r2_improvement'] = round(
            float(np.mean([r['r2_improvement'] for r in with_data])), 3)
        results['n_improved'] = sum(1 for r in with_data if r.get('removal_helps'))
        worst = max(with_data, key=lambda r: r['pct_artifact'])
        results['worst_artifact_patient'] = worst['patient']
        results['worst_artifact_pct'] = worst['pct_artifact']
    return results


# ─── EXP-1325: Overnight Basal Titration Protocol ───────────────────
def exp_1325_basal_titration(patients, detail=False, preconditions=None):
    """Clinical protocol: use overnight fasting glucose drift to titrate basal.

    Target drift within ±1 mg/dL/h.  Compute exact rate change needed using
    response-curve ISF (EXP-1301) and DIA fraction.
    """
    results = {'name': 'EXP-1325: Overnight basal titration protocol',
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
        isf_profile = pk[:, 7] * 200.0
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        # Estimate ISF from response curves
        corrections = find_corrections(p)
        isf_estimates = []
        for ci in corrections:
            if ci + 3 * STEPS_PER_HOUR >= n:
                continue
            if np.sum(bolus[ci + 1:ci + 3 * STEPS_PER_HOUR]) > 0.5:
                continue
            fit = fit_response_curve(glucose, bolus[ci], ci, 3 * STEPS_PER_HOUR)
            if fit is not None:
                isf_estimates.append(fit[0])
        if isf_estimates:
            response_isf = float(np.median(isf_estimates))
        else:
            response_isf = float(np.median(isf_profile[~np.isnan(glucose)]))

        scheduled_rate = get_scheduled_basal_rate(p)

        # Steady-state DIA fraction: ~1/5 of hourly delivery active at any time
        dia_fraction = 1.0 / (DIA_STEPS / STEPS_PER_HOUR)  # 0.2

        # Compute drift on qualifying fasting nights
        night_drifts = []
        night_details = []
        for d in range(n_days):
            start = d * STEPS_PER_DAY
            end = start + STEPS_PER_HOUR * 6
            if end > n:
                break
            ng = glucose[start:end]
            nb = bolus[start:end]
            nc = carbs[start:end]
            pre_start = max(0, start - STEPS_PER_HOUR * 3)
            if np.sum(bolus[pre_start:end]) > 0.1 or np.sum(carbs[pre_start:end]) > 1:
                continue
            valid_g = ~np.isnan(ng)
            if valid_g.sum() < STEPS_PER_HOUR * 3:
                continue
            x = np.arange(len(ng))[valid_g] * (5.0 / 60.0)
            y = ng[valid_g]
            if len(x) < 10:
                continue
            slope = float(np.polyfit(x, y, 1)[0])
            night_drifts.append(slope)
            if detail:
                night_details.append({
                    'night': d, 'drift_mg_dl_h': round(slope, 2),
                    'mean_bg': round(float(np.mean(y)), 1),
                    'n_readings': int(valid_g.sum()),
                })

        if not night_drifts:
            results['per_patient'].append({
                'patient': p['name'], 'n_qualifying_nights': 0,
                'note': 'No qualifying fasting nights'})
            continue

        mean_drift = float(np.mean(night_drifts))
        # delta_rate = drift / (ISF × DIA_fraction)
        delta_rate = mean_drift / (response_isf * dia_fraction)
        new_rate = max(0.05, scheduled_rate + delta_rate)

        on_target = abs(mean_drift) <= 1.0

        rec = {
            'patient': p['name'],
            'n_qualifying_nights': len(night_drifts),
            'mean_drift_mg_dl_h': round(mean_drift, 2),
            'median_drift_mg_dl_h': round(float(np.median(night_drifts)), 2),
            'drift_sd': round(float(np.std(night_drifts)), 2) if len(night_drifts) > 1 else 0.0,
            'response_isf': round(response_isf, 1),
            'n_isf_corrections': len(isf_estimates),
            'scheduled_rate': round(scheduled_rate, 3),
            'delta_rate_u_h': round(delta_rate, 3),
            'recommended_rate': round(new_rate, 3),
            'change_pct': round((new_rate / scheduled_rate - 1) * 100, 1),
            'on_target': on_target,
            'assessment': 'on_target' if on_target else (
                'increase_basal' if mean_drift > 1.0 else 'decrease_basal'),
        }
        if detail and night_details:
            rec['nights'] = night_details[:10]
        results['per_patient'].append(rec)

    with_data = [r for r in results['per_patient']
                 if r.get('n_qualifying_nights', 0) > 0]
    results['n_patients_assessed'] = len(with_data)
    if with_data:
        results['n_on_target'] = sum(1 for r in with_data if r.get('on_target'))
        results['n_increase'] = sum(1 for r in with_data
                                    if r.get('assessment') == 'increase_basal')
        results['n_decrease'] = sum(1 for r in with_data
                                    if r.get('assessment') == 'decrease_basal')
        results['mean_drift'] = round(
            float(np.mean([r['mean_drift_mg_dl_h'] for r in with_data])), 2)
        results['mean_delta_rate'] = round(
            float(np.mean([r['delta_rate_u_h'] for r in with_data])), 3)
    return results


# ─── EXP-1326: Supply-Demand Balance by Time Block ──────────────────
def exp_1326_supply_demand_blocks(patients, detail=False, preconditions=None):
    """Compute UAM-augmented supply vs demand per 4-hour time block.

    Identify blocks where supply >> demand (rising) or demand >> supply (falling).
    Recommend per-block basal adjustments.
    """
    results = {'name': 'EXP-1326: Supply-demand balance by time block',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        n = len(glucose)

        sd, uam_sup, uam_mask, aug_supply = compute_uam_supply(df, pk)
        demand = sd['demand']
        valid = ~np.isnan(glucose)

        if valid.sum() < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient data'})
            continue

        blocks = get_time_blocks(n)
        temp_rate = df['temp_rate'].values
        scheduled_rate = get_scheduled_basal_rate(p)

        block_data = {}
        for b in range(6):
            bmask = (blocks == b) & valid
            if bmask.sum() < STEPS_PER_HOUR:
                block_data[BLOCK_NAMES[b]] = {'n_steps': int(bmask.sum()),
                                              'note': 'Insufficient data'}
                continue
            mean_supply = float(np.mean(aug_supply[bmask]))
            mean_demand = float(np.mean(demand[bmask]))
            mean_raw_supply = float(np.mean(sd['supply'][bmask]))
            mean_uam = float(np.mean(uam_sup[bmask]))
            ratio = mean_supply / (mean_demand + 1e-6)
            net = mean_supply - mean_demand

            block_rates = temp_rate[bmask]
            mean_delivery = float(np.mean(block_rates[block_rates > 0])) if np.any(
                block_rates > 0) else scheduled_rate

            adjustment_factor = max(-0.3, min(0.3, (ratio - 1.0) * 0.5))
            rec_rate = scheduled_rate * (1 + adjustment_factor)

            block_data[BLOCK_NAMES[b]] = {
                'n_steps': int(bmask.sum()),
                'mean_supply': round(mean_supply, 3),
                'mean_demand': round(mean_demand, 3),
                'mean_raw_supply': round(mean_raw_supply, 3),
                'mean_uam_supply': round(mean_uam, 3),
                'supply_demand_ratio': round(ratio, 2),
                'net_balance': round(net, 3),
                'mean_delivery': round(mean_delivery, 3),
                'adjustment_pct': round(adjustment_factor * 100, 1),
                'recommended_rate': round(rec_rate, 3),
                'balance_assessment': ('rising' if ratio > 1.15
                                       else 'falling' if ratio < 0.85
                                       else 'balanced'),
            }

        assessed_blocks = {k: v for k, v in block_data.items()
                          if 'supply_demand_ratio' in v}
        if assessed_blocks:
            worst_block = max(assessed_blocks,
                              key=lambda k: abs(assessed_blocks[k]['supply_demand_ratio'] - 1))
        else:
            worst_block = None

        results['per_patient'].append({
            'patient': p['name'],
            'blocks': block_data,
            'worst_imbalance_block': worst_block,
            'scheduled_rate': round(scheduled_rate, 3),
        })

    with_data = [r for r in results['per_patient'] if 'blocks' in r]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        block_ratios = defaultdict(list)
        for r in with_data:
            for bname, bdata in r['blocks'].items():
                if 'supply_demand_ratio' in bdata:
                    block_ratios[bname].append(bdata['supply_demand_ratio'])
        results['population_block_balance'] = {
            bname: round(float(np.mean(vals)), 2)
            for bname, vals in block_ratios.items()
        }
        worst_pop = max(block_ratios,
                        key=lambda k: abs(float(np.mean(block_ratios[k])) - 1))
        results['worst_population_block'] = worst_pop
    return results


# ─── EXP-1327: Correction Response Consistency ──────────────────────
def exp_1327_correction_consistency(patients, detail=False, preconditions=None):
    """How consistent are correction responses within a patient?

    Compute CV of ISF and tau across corrections.  Test whether
    well-calibrated patients have more consistent ISF.
    """
    results = {'name': 'EXP-1327: Correction response consistency',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'correction_validation'}

    CORRECTION_WINDOW = 3 * STEPS_PER_HOUR

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
        n = len(glucose)

        isf_vals = []
        tau_vals = []

        for i in range(n):
            if bolus[i] < 0.3 or np.isnan(glucose[i]) or glucose[i] <= 150:
                continue
            cw = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[cw]) > 2:
                continue
            if i + CORRECTION_WINDOW >= n:
                continue
            if np.sum(bolus[i + 1:i + CORRECTION_WINDOW]) > 0.5:
                continue
            if np.sum(carbs[i + 1:i + CORRECTION_WINDOW]) > 2:
                continue

            fit = fit_response_curve(glucose, bolus[i], i, CORRECTION_WINDOW)
            if fit is None:
                continue
            isf, tau, r2 = fit
            if r2 > 0.1:
                isf_vals.append(isf)
                tau_vals.append(tau)

        if len(isf_vals) < 3:
            results['per_patient'].append({
                'patient': p['name'], 'n_corrections': len(isf_vals),
                'note': 'Too few corrections for consistency analysis'})
            continue

        isf_arr = np.array(isf_vals)
        tau_arr = np.array(tau_vals)
        isf_mean = float(np.mean(isf_arr))
        isf_std = float(np.std(isf_arr, ddof=1))
        isf_cv = isf_std / (isf_mean + 1e-6)
        tau_mean = float(np.mean(tau_arr))
        tau_std = float(np.std(tau_arr, ddof=1))
        tau_cv = tau_std / (tau_mean + 1e-6)

        isf_outliers = int(np.sum(np.abs(isf_arr - isf_mean) > 2 * isf_std))
        tau_outliers = int(np.sum(np.abs(tau_arr - tau_mean) > 2 * tau_std))

        archetype = PATIENT_ARCHETYPE.get(p['name'], 'unknown')
        results['per_patient'].append({
            'patient': p['name'],
            'archetype': archetype,
            'n_corrections': len(isf_vals),
            'isf_mean': round(isf_mean, 1),
            'isf_std': round(isf_std, 1),
            'isf_cv': round(isf_cv, 2),
            'isf_iqr': round(float(np.percentile(isf_arr, 75) -
                                   np.percentile(isf_arr, 25)), 1),
            'isf_outliers': isf_outliers,
            'tau_mean': round(tau_mean, 2),
            'tau_std': round(tau_std, 2),
            'tau_cv': round(tau_cv, 2),
            'tau_outliers': tau_outliers,
        })

    with_data = [r for r in results['per_patient']
                 if r.get('n_corrections', 0) >= 3]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        results['mean_isf_cv'] = round(
            float(np.mean([r['isf_cv'] for r in with_data])), 2)
        results['mean_tau_cv'] = round(
            float(np.mean([r['tau_cv'] for r in with_data])), 2)
        wc = [r for r in with_data if r.get('archetype') == 'well-calibrated']
        nt = [r for r in with_data if r.get('archetype') == 'needs-tuning']
        if wc and nt:
            wc_cv = float(np.mean([r['isf_cv'] for r in wc]))
            nt_cv = float(np.mean([r['isf_cv'] for r in nt]))
            results['wc_mean_isf_cv'] = round(wc_cv, 2)
            results['nt_mean_isf_cv'] = round(nt_cv, 2)
            results['hypothesis_wc_more_consistent'] = wc_cv < nt_cv
    return results


# ─── EXP-1328: Post-Meal Recovery Time ──────────────────────────────
def exp_1328_meal_recovery(patients, detail=False, preconditions=None):
    """How long does glucose take to return to pre-meal level after a meal?

    Flag meals with recovery > 4h as "slow recovery" (possible CR issue).
    """
    results = {'name': 'EXP-1328: Post-meal recovery time',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'cr_assessment'}

    RECOVERY_TOLERANCE = 10.0  # mg/dL
    SLOW_RECOVERY_HOURS = 4.0
    MAX_RECOVERY_STEPS = 6 * STEPS_PER_HOUR

    for p in patients:
        met, reason = check_precondition(p, preconditions, 'cr_assessment')
        if not met:
            results['per_patient'].append({
                'patient': p['name'], 'skipped': True, 'reason': reason})
            continue

        df = p['df']
        glucose = df['glucose'].values.astype(float)
        carbs = df['carbs'].values
        bolus = df['bolus'].values
        n = len(glucose)

        meals = []
        last_meal = -STEPS_PER_HOUR * 3
        for i in range(n):
            if carbs[i] < 5 or (i - last_meal) < STEPS_PER_HOUR * 2:
                continue
            last_meal = i

            pre_window = glucose[max(0, i - 3):i + 1]
            pre_valid = pre_window[~np.isnan(pre_window)]
            if len(pre_valid) == 0:
                continue
            pre_bg = float(np.mean(pre_valid))

            post_end = min(n, i + MAX_RECOVERY_STEPS)
            if post_end - i < STEPS_PER_HOUR:
                continue
            post_g = glucose[i:post_end]
            post_valid = ~np.isnan(post_g)
            if post_valid.sum() < STEPS_PER_HOUR:
                continue

            peak_bg = float(np.nanmax(post_g))
            excursion = peak_bg - pre_bg

            peak_idx = int(np.nanargmax(post_g))
            recovery_steps = None
            for j in range(peak_idx, len(post_g)):
                if not np.isnan(post_g[j]) and abs(post_g[j] - pre_bg) <= RECOVERY_TOLERANCE:
                    recovery_steps = j
                    break
            if recovery_steps is not None:
                recovery_hours = recovery_steps * (5.0 / 60.0)
            else:
                recovery_hours = float(MAX_RECOVERY_STEPS * (5.0 / 60.0))

            meal_size = float(carbs[i])
            if meal_size < 20:
                size_cat = 'small'
            elif meal_size < 45:
                size_cat = 'medium'
            else:
                size_cat = 'large'

            meals.append({
                'pre_bg': round(pre_bg, 1),
                'peak_bg': round(peak_bg, 1),
                'excursion': round(excursion, 1),
                'recovery_hours': round(recovery_hours, 2),
                'slow_recovery': recovery_hours > SLOW_RECOVERY_HOURS,
                'meal_size_g': round(meal_size, 1),
                'size_category': size_cat,
            })

        if not meals:
            results['per_patient'].append({
                'patient': p['name'], 'n_meals': 0,
                'note': 'No qualifying meals'})
            continue

        recovery_times = [m['recovery_hours'] for m in meals]
        n_slow = sum(1 for m in meals if m['slow_recovery'])

        size_stats = {}
        for cat in ['small', 'medium', 'large']:
            cat_meals = [m for m in meals if m['size_category'] == cat]
            if cat_meals:
                cat_rt = [m['recovery_hours'] for m in cat_meals]
                size_stats[cat] = {
                    'n_meals': len(cat_meals),
                    'mean_recovery_h': round(float(np.mean(cat_rt)), 2),
                    'mean_excursion': round(
                        float(np.mean([m['excursion'] for m in cat_meals])), 1),
                }

        sizes = np.array([m['meal_size_g'] for m in meals])
        rts = np.array(recovery_times)
        if len(sizes) > 3 and np.std(sizes) > 0 and np.std(rts) > 0:
            corr = float(np.corrcoef(sizes, rts)[0, 1])
        else:
            corr = 0.0

        rec = {
            'patient': p['name'],
            'n_meals': len(meals),
            'mean_recovery_h': round(float(np.mean(recovery_times)), 2),
            'median_recovery_h': round(float(np.median(recovery_times)), 2),
            'n_slow_recovery': n_slow,
            'pct_slow': round(n_slow / len(meals) * 100, 1),
            'mean_excursion': round(
                float(np.mean([m['excursion'] for m in meals])), 1),
            'size_category_stats': size_stats,
            'size_recovery_corr': round(corr, 2),
        }
        if detail:
            rec['meals'] = meals[:20]
        results['per_patient'].append(rec)

    with_data = [r for r in results['per_patient'] if r.get('n_meals', 0) > 0]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        results['mean_recovery_h'] = round(
            float(np.mean([r['mean_recovery_h'] for r in with_data])), 2)
        results['mean_pct_slow'] = round(
            float(np.mean([r['pct_slow'] for r in with_data])), 1)
        results['mean_size_recovery_corr'] = round(
            float(np.mean([r['size_recovery_corr'] for r in with_data])), 2)
    return results


# ─── EXP-1329: Insulin Resistance Score ─────────────────────────────
def exp_1329_insulin_resistance(patients, detail=False, preconditions=None):
    """Composite insulin resistance metric per patient.

    Combines TDI, ISF_curve, CR effectiveness, and basal-to-bolus ratio.
    """
    results = {'name': 'EXP-1329: Insulin resistance score',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        temp_rate = df['temp_rate'].values
        isf_profile = pk[:, 7] * 200.0
        n = len(glucose)
        n_days = max(1, n / STEPS_PER_DAY)

        valid = ~np.isnan(glucose)
        if valid.sum() < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient data'})
            continue

        # Total daily insulin
        total_bolus = float(np.sum(bolus))
        total_basal = float(np.sum(temp_rate)) * (5.0 / 60.0)
        tdi = (total_bolus + total_basal) / n_days
        daily_bolus = total_bolus / n_days
        daily_basal = total_basal / n_days
        basal_fraction = daily_basal / (tdi + 1e-6)

        # ISF from response curve
        corrections = find_corrections(p)
        isf_estimates = []
        for ci in corrections:
            if ci + 3 * STEPS_PER_HOUR >= n:
                continue
            if np.sum(bolus[ci + 1:ci + 3 * STEPS_PER_HOUR]) > 0.5:
                continue
            fit = fit_response_curve(glucose, bolus[ci], ci, 3 * STEPS_PER_HOUR)
            if fit is not None:
                isf_estimates.append(fit[0])
        if isf_estimates:
            measured_isf = float(np.median(isf_estimates))
        else:
            measured_isf = float(np.median(isf_profile[valid]))

        # CR effectiveness: mean excursion per gram of carbs
        excursions_per_g = []
        last_meal = -STEPS_PER_HOUR * 3
        for i in range(n):
            if carbs[i] < 5 or (i - last_meal) < STEPS_PER_HOUR * 2:
                continue
            last_meal = i
            post_end = min(n, i + 3 * STEPS_PER_HOUR)
            if post_end - i < STEPS_PER_HOUR:
                continue
            pre_g = glucose[max(0, i - 3):i + 1]
            pre_g = pre_g[~np.isnan(pre_g)]
            if len(pre_g) == 0:
                continue
            pre_bg = float(np.mean(pre_g))
            peak = float(np.nanmax(glucose[i:post_end]))
            if not np.isnan(peak):
                excursion_per_g = (peak - pre_bg) / float(carbs[i])
                excursions_per_g.append(excursion_per_g)

        cr_sensitivity = float(np.median(excursions_per_g)) if excursions_per_g else 3.0

        # Composite IR score (0-100, higher = more resistant)
        tdi_score = min(1.0, tdi / 80.0)
        isf_score = 1.0 - min(1.0, measured_isf / 200.0)
        cr_score = min(1.0, cr_sensitivity / 10.0)
        basal_score = min(1.0, basal_fraction / 0.6)

        ir_score = (tdi_score * 30 + isf_score * 30 +
                    cr_score * 20 + basal_score * 20)
        ir_label = ('low' if ir_score < 30 else
                    'moderate' if ir_score < 55 else 'high')

        results['per_patient'].append({
            'patient': p['name'],
            'tdi': round(tdi, 1),
            'daily_bolus': round(daily_bolus, 1),
            'daily_basal': round(daily_basal, 1),
            'basal_fraction': round(basal_fraction, 2),
            'measured_isf': round(measured_isf, 1),
            'n_corrections': len(isf_estimates),
            'cr_sensitivity_mg_per_g': round(cr_sensitivity, 2),
            'n_meals': len(excursions_per_g),
            'tdi_score': round(tdi_score, 2),
            'isf_score': round(isf_score, 2),
            'cr_score': round(cr_score, 2),
            'basal_score': round(basal_score, 2),
            'ir_score': round(ir_score, 1),
            'ir_label': ir_label,
        })

    with_data = [r for r in results['per_patient'] if 'ir_score' in r]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        sorted_ir = sorted(with_data, key=lambda r: -r['ir_score'])
        results['rank_ordering'] = [
            {'patient': r['patient'], 'ir_score': r['ir_score'],
             'ir_label': r['ir_label']}
            for r in sorted_ir
        ]
        results['ir_distribution'] = {
            lbl: sum(1 for r in with_data if r.get('ir_label') == lbl)
            for lbl in ['low', 'moderate', 'high']
        }
        results['mean_ir_score'] = round(
            float(np.mean([r['ir_score'] for r in with_data])), 1)
    return results


# ─── EXP-1330: Therapy Improvement Simulation ───────────────────────
def exp_1330_therapy_simulation(patients, detail=False, preconditions=None):
    """Simulate outcomes if recommended settings are applied.

    For each patient, apply EXP-1315-style recommendations and simulate
    glucose using supply-demand model with new settings.
    """
    results = {'name': 'EXP-1330: Therapy improvement simulation',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        temp_rate = df['temp_rate'].values
        isf_profile = pk[:, 7] * 200.0
        n = len(glucose)

        valid = ~np.isnan(glucose)
        if valid.sum() < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient data'})
            continue

        sd, uam_sup, uam_mask, _ = compute_uam_supply(df, pk)
        net_flux = sd['net']
        demand = sd['demand']
        supply = sd['supply']

        valid_g = glucose[valid]

        # Current metrics
        tir_current = float(np.mean((valid_g >= 70) & (valid_g <= 180)) * 100)
        tbr_current = float(np.mean(valid_g < 70) * 100)
        tar_current = float(np.mean(valid_g > 180) * 100)
        mean_bg_current = float(np.mean(valid_g))

        scheduled_rate = get_scheduled_basal_rate(p)

        # Basal change (UAM-filtered)
        fasting = np.ones(n, dtype=bool)
        for i in range(n):
            ws, we = max(0, i - STEPS_PER_HOUR * 2), min(n, i + STEPS_PER_HOUR * 2)
            if np.any(bolus[ws:we] > 0) or np.any(carbs[ws:we] > 0):
                fasting[i] = False
        clean = fasting & ~uam_mask & valid
        if clean.sum() > STEPS_PER_HOUR:
            clean_net = float(np.mean(net_flux[clean]))
            clean_demand = float(np.mean(demand[clean]))
            basal_change = -clean_net / (clean_demand + 1e-6)
            basal_change = max(-0.5, min(0.5, basal_change))
        else:
            basal_change = 0.0

        # ISF change
        isf_estimates = []
        for i in range(n):
            if bolus[i] < 0.3 or np.isnan(glucose[i]) or glucose[i] <= 150:
                continue
            cw = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[cw]) > 2:
                continue
            window = 3 * STEPS_PER_HOUR
            if i + window >= n:
                continue
            if np.sum(bolus[i + 1:i + window]) > 0.5:
                continue
            if np.sum(carbs[i + 1:i + window]) > 2:
                continue
            fit = fit_response_curve(glucose, bolus[i], i, window)
            if fit is not None:
                isf_estimates.append(fit[0])

        mean_isf_profile = float(np.mean(isf_profile[valid]))
        if isf_estimates:
            measured_isf = float(np.median(isf_estimates))
            isf_ratio = measured_isf / (mean_isf_profile + 1e-6)
        else:
            measured_isf = mean_isf_profile
            isf_ratio = 1.0

        # Simulate: adjust demand by basal_change and ISF correction
        demand_adjustment = 1.0 + basal_change
        isf_adjustment = 1.0 / (isf_ratio + 1e-6) if abs(isf_ratio - 1.0) > 0.1 else 1.0
        isf_adjustment = max(0.5, min(2.0, isf_adjustment))

        adjusted_demand = demand * demand_adjustment * isf_adjustment
        adjusted_net = supply + uam_sup - adjusted_demand
        sim_glucose = np.full(n, np.nan)
        sim_glucose[0] = glucose[0] if not np.isnan(glucose[0]) else mean_bg_current
        for i in range(1, n):
            if np.isnan(sim_glucose[i - 1]):
                sim_glucose[i] = glucose[i] if not np.isnan(glucose[i]) else mean_bg_current
                continue
            delta = adjusted_net[i]
            if np.isnan(delta):
                sim_glucose[i] = sim_glucose[i - 1]
            else:
                sim_glucose[i] = sim_glucose[i - 1] + delta
            sim_glucose[i] = max(40, min(400, sim_glucose[i]))

        sim_valid = ~np.isnan(sim_glucose)
        sim_g = sim_glucose[sim_valid]
        if len(sim_g) < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Simulation failed'})
            continue

        tir_sim = float(np.mean((sim_g >= 70) & (sim_g <= 180)) * 100)
        tbr_sim = float(np.mean(sim_g < 70) * 100)
        tar_sim = float(np.mean(sim_g > 180) * 100)
        mean_bg_sim = float(np.mean(sim_g))

        tir_delta = tir_sim - tir_current
        tbr_delta = tbr_sim - tbr_current

        hypo_risk = ('increased' if tbr_delta > 1.0 else
                     'decreased' if tbr_delta < -1.0 else 'unchanged')
        if tir_delta > 2.0 and hypo_risk != 'increased':
            overall = 'beneficial'
        elif hypo_risk == 'increased':
            overall = 'risky'
        else:
            overall = 'neutral'

        results['per_patient'].append({
            'patient': p['name'],
            'basal_change_pct': round(basal_change * 100, 1),
            'isf_ratio': round(isf_ratio, 2),
            'isf_adjustment': round(isf_adjustment, 2),
            'n_corrections': len(isf_estimates),
            'current_tir': round(tir_current, 1),
            'current_tbr': round(tbr_current, 1),
            'current_tar': round(tar_current, 1),
            'current_mean_bg': round(mean_bg_current, 1),
            'simulated_tir': round(tir_sim, 1),
            'simulated_tbr': round(tbr_sim, 1),
            'simulated_tar': round(tar_sim, 1),
            'simulated_mean_bg': round(mean_bg_sim, 1),
            'tir_change': round(tir_delta, 1),
            'tbr_change': round(tbr_delta, 1),
            'hypo_risk': hypo_risk,
            'overall_assessment': overall,
        })

    with_data = [r for r in results['per_patient'] if 'current_tir' in r]
    results['n_patients_simulated'] = len(with_data)
    if with_data:
        results['mean_tir_change'] = round(
            float(np.mean([r['tir_change'] for r in with_data])), 1)
        results['mean_tbr_change'] = round(
            float(np.mean([r['tbr_change'] for r in with_data])), 1)
        results['n_beneficial'] = sum(1 for r in with_data
                                      if r.get('overall_assessment') == 'beneficial')
        results['n_risky'] = sum(1 for r in with_data
                                 if r.get('overall_assessment') == 'risky')
        results['n_neutral'] = sum(1 for r in with_data
                                   if r.get('overall_assessment') == 'neutral')
        results['assessment_summary'] = {
            'beneficial': results['n_beneficial'],
            'risky': results['n_risky'],
            'neutral': results['n_neutral'],
        }
    return results


# ─── Experiment Registry ─────────────────────────────────────────────
EXPERIMENTS = {
    1321: ('Basal ground truth (well-calibrated)', exp_1321_basal_ground_truth),
    1322: ('UAM-aware response curve ISF', exp_1322_uam_clean_isf),
    1323: ('Hepatic rhythm modeling', exp_1323_hepatic_rhythm),
    1324: ('Sensor artifact auto-detection', exp_1324_artifact_detection),
    1325: ('Overnight basal titration', exp_1325_basal_titration),
    1326: ('Supply-demand by time block', exp_1326_supply_demand_blocks),
    1327: ('Correction response consistency', exp_1327_correction_consistency),
    1328: ('Post-meal recovery time', exp_1328_meal_recovery),
    1329: ('Insulin resistance score', exp_1329_insulin_resistance),
    1330: ('Therapy improvement simulation', exp_1330_therapy_simulation),
}


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1321-1330: Basal ground truth, UAM-aware ISF, '
                    'hepatic rhythm, therapy simulation')
    parser.add_argument('--exp', type=int, help='Run single experiment')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    args = parser.parse_args()

    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    # Precondition assessment
    precond_results = {}
    for p in patients:
        precond_results[p['name']] = assess_preconditions(p)

    # Run experiments
    exps_to_run = [args.exp] if args.exp else sorted(EXPERIMENTS.keys())
    all_results = {}
    for eid in exps_to_run:
        if eid not in EXPERIMENTS:
            print(f"Unknown experiment: {eid}")
            continue
        name, func = EXPERIMENTS[eid]
        print(f"\nEXP-{eid}: {name}")
        t0 = time.time()
        try:
            result = func(patients, detail=args.detail,
                          preconditions=precond_results)
            result['elapsed_sec'] = round(time.time() - t0, 1)
            all_results[eid] = result
            # Print summary
            n_pp = len(result.get('per_patient', []))
            print(f"  {n_pp} patients processed in {result['elapsed_sec']}s")
            if args.save:
                fname = f'exp-{eid}_therapy.json'
                with open(fname, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved \u2192 {fname}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            all_results[eid] = {'error': str(e)}

    return all_results


if __name__ == '__main__':
    main()
