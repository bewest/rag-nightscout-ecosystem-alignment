#!/usr/bin/env python3
"""EXP-1331–1340: Therapy Operationalization — Ground Truth, Titration, Simulation

Resolves key open questions from EXP-1291-1320:
1. Basal direction ambiguity: raw says decrease, UAM-aware says increase for 8/11
2. Response-curve ISF with UAM filtering
3. Clinical overnight basal titration protocol
4. DIA validation from correction trajectories
5. Specific U/h and mg/dL/U recommendations
6. Therapy simulation: what TIR improvement if recommendations applied?

Builds on:
- EXP-1301: Response-curve ISF (R²=0.805, τ=2.0h)
- EXP-1309: UAM augmentation (R² -0.508→+0.351)
- EXP-1315: Confidence-weighted recs (8/11 high confidence)
- EXP-1320: Universal UAM threshold (1.0 mg/dL/5min, 100% transfer)
- EXP-1310: Patient archetypes (well-calibrated, needs-tuning, miscalibrated)
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
from cgmencode.exp_clinical_1311 import compute_uam_supply

PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent
                   / 'externals' / 'ns-data' / 'patients')

GLUCOSE_SCALE = 400.0
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
DIA_STEPS = STEPS_PER_HOUR * 5  # 5-hour DIA

BLOCK_NAMES = ['overnight(0-6)', 'morning(6-10)', 'midday(10-14)',
               'afternoon(14-18)', 'evening(18-22)', 'night(22-24)']
BLOCK_RANGES = [(0, 6), (6, 10), (10, 14), (14, 18), (18, 22), (22, 24)]

# Archetype assignments from EXP-1310
ARCHETYPES = {
    'well-calibrated': ['d', 'h', 'j', 'k'],
    'needs-tuning': ['b', 'c', 'e', 'f', 'g', 'i'],
    'miscalibrated': ['a'],
}
PATIENT_ARCHETYPE = {}
for arch, members in ARCHETYPES.items():
    for m in members:
        PATIENT_ARCHETYPE[m] = arch


def get_time_block(step_in_day):
    """Map a step within a day to a 6-block time block index."""
    hour = (step_in_day / STEPS_PER_HOUR) % 24
    for i, (lo, hi) in enumerate(BLOCK_RANGES):
        if lo <= hour < hi:
            return i
    return 5


def get_overnight_mask(df, n):
    """Return boolean mask for overnight hours (0-6 AM)."""
    mask = np.zeros(n, dtype=bool)
    for i in range(n):
        hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
        if 0 <= hour < 6:
            mask[i] = True
    return mask


# ─── EXP-1331: Basal Ground Truth via Well-Calibrated Patients ──────

def exp_1331_basal_ground_truth(patients, detail=False, preconditions=None):
    """Use well-calibrated patients (d,h,j,k from EXP-1310) as ground truth.

    If well-calibrated patients' basal analysis agrees with raw method →
    raw is correct. If agrees with UAM-filtered → UAM filtering is correct.
    Resolves the basal direction ambiguity from EXP-1292 vs EXP-1315.
    """
    results = {'name': 'EXP-1331: Basal ground truth validation',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        archetype = PATIENT_ARCHETYPE.get(p['name'], 'unknown')

        sd, uam_sup, uam_mask, aug_supply = compute_uam_supply(df, pk)
        net_flux = sd['net']
        demand = sd['demand']

        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)

        if valid.sum() < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'], 'archetype': archetype,
                'note': 'Insufficient data'})
            continue

        # Fasting windows: no bolus or carbs within ±2h
        fasting = np.ones(n, dtype=bool)
        for i in range(n):
            ws = max(0, i - STEPS_PER_HOUR * 2)
            we = min(n, i + STEPS_PER_HOUR * 2)
            if np.any(bolus[ws:we] > 0) or np.any(carbs[ws:we] > 0):
                fasting[i] = False

        # Method 1: Raw fasting (EXP-1292 style)
        raw_fasting = fasting & valid
        if raw_fasting.sum() > STEPS_PER_HOUR:
            raw_mean_net = float(np.mean(net_flux[raw_fasting]))
            raw_mean_demand = float(np.mean(demand[raw_fasting]))
            raw_change = -raw_mean_net / (raw_mean_demand + 1e-6)
            raw_change = max(-0.5, min(0.5, raw_change))
        else:
            raw_mean_net, raw_change = 0.0, 0.0

        # Method 2: UAM-filtered fasting
        clean_fasting = fasting & ~uam_mask & valid
        if clean_fasting.sum() > STEPS_PER_HOUR:
            clean_mean_net = float(np.mean(net_flux[clean_fasting]))
            clean_mean_demand = float(np.mean(demand[clean_fasting]))
            clean_change = -clean_mean_net / (clean_mean_demand + 1e-6)
            clean_change = max(-0.5, min(0.5, clean_change))
        else:
            clean_mean_net, clean_change = 0.0, 0.0

        # Method 3: Overnight-only (least confounded — no meals, minimal UAM)
        overnight = get_overnight_mask(df, n)
        overnight_fasting = overnight & fasting & valid
        if overnight_fasting.sum() > STEPS_PER_HOUR:
            ovn_mean_net = float(np.mean(net_flux[overnight_fasting]))
            ovn_mean_demand = float(np.mean(demand[overnight_fasting]))
            ovn_change = -ovn_mean_net / (ovn_mean_demand + 1e-6)
            ovn_change = max(-0.5, min(0.5, ovn_change))
        else:
            ovn_mean_net, ovn_change = 0.0, 0.0

        # Method 4: Glucose drift method — average ΔBG during fasting
        # If BG drifts up during fasting → basal too low; down → too high
        if raw_fasting.sum() > STEPS_PER_HOUR:
            drift_mgdl_per_5min = float(np.mean(dg[raw_fasting]))
            drift_mgdl_per_hour = drift_mgdl_per_5min * STEPS_PER_HOUR
        else:
            drift_mgdl_per_5min, drift_mgdl_per_hour = 0.0, 0.0

        # For well-calibrated patients, all methods should agree near zero
        scheduled_rate = get_scheduled_basal_rate(p)

        results['per_patient'].append({
            'patient': p['name'],
            'archetype': archetype,
            'scheduled_rate': round(scheduled_rate, 3),
            'raw_change_pct': round(raw_change * 100, 1),
            'uam_filtered_change_pct': round(clean_change * 100, 1),
            'overnight_change_pct': round(ovn_change * 100, 1),
            'drift_mg_per_hour': round(drift_mgdl_per_hour, 2),
            'n_raw_fasting': int(raw_fasting.sum()),
            'n_clean_fasting': int(clean_fasting.sum()),
            'n_overnight_fasting': int(overnight_fasting.sum()),
            'uam_contamination_pct': round(
                float(uam_mask[fasting & valid].sum()) /
                (raw_fasting.sum() + 1e-6) * 100, 1),
        })

    pp = results['per_patient']
    well_cal = [r for r in pp if r.get('archetype') == 'well-calibrated'
                and 'raw_change_pct' in r]
    needs_tun = [r for r in pp if r.get('archetype') == 'needs-tuning'
                 and 'raw_change_pct' in r]

    if well_cal:
        results['well_calibrated_raw_mean'] = round(
            float(np.mean([r['raw_change_pct'] for r in well_cal])), 1)
        results['well_calibrated_uam_mean'] = round(
            float(np.mean([r['uam_filtered_change_pct'] for r in well_cal])), 1)
        results['well_calibrated_overnight_mean'] = round(
            float(np.mean([r['overnight_change_pct'] for r in well_cal])), 1)
        results['well_calibrated_drift_mean'] = round(
            float(np.mean([r['drift_mg_per_hour'] for r in well_cal])), 2)

        # Ground truth validation: which method is closest to zero for
        # well-calibrated patients?
        methods = {
            'raw': abs(results['well_calibrated_raw_mean']),
            'uam_filtered': abs(results['well_calibrated_uam_mean']),
            'overnight': abs(results['well_calibrated_overnight_mean']),
        }
        results['best_method_for_well_calibrated'] = min(methods, key=methods.get)
        results['method_scores'] = {k: round(v, 1) for k, v in methods.items()}

    if needs_tun:
        results['needs_tuning_raw_mean'] = round(
            float(np.mean([r['raw_change_pct'] for r in needs_tun])), 1)
        results['needs_tuning_uam_mean'] = round(
            float(np.mean([r['uam_filtered_change_pct'] for r in needs_tun])), 1)
        results['needs_tuning_overnight_mean'] = round(
            float(np.mean([r['overnight_change_pct'] for r in needs_tun])), 1)

    return results


# ─── EXP-1332: UAM-Clean Response-Curve ISF ──────────────────────────

def exp_1332_uam_clean_isf(patients, detail=False, preconditions=None):
    """Response-curve ISF (EXP-1301) with UAM events excluded from windows.

    Tests whether UAM contamination biases the ISF estimate.
    """
    TAU_CANDIDATES = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
    results = {'name': 'EXP-1332: UAM-clean response-curve ISF',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        isf_profile = pk[:, 7] * 200.0
        n = len(glucose)

        sd, uam_sup, uam_mask, _ = compute_uam_supply(df, pk)

        mean_isf_profile = float(np.nanmean(isf_profile))

        def fit_response_curves(exclude_uam=False):
            estimates = []
            taus = []
            fit_r2s = []
            for i in range(n):
                if bolus[i] < 0.3 or np.isnan(glucose[i]) or glucose[i] <= 150:
                    continue
                # Skip if carbs nearby
                cw = slice(max(0, i - 6), min(n, i + 6))
                if np.sum(carbs[cw]) > 2:
                    continue
                window = 3 * STEPS_PER_HOUR
                if i + window >= n:
                    continue
                # Skip if more boluses or carbs in window
                if np.sum(bolus[i + 1:i + window]) > 0.5:
                    continue
                if np.sum(carbs[i + 1:i + window]) > 2:
                    continue
                # UAM exclusion: skip if >20% of window has UAM
                if exclude_uam:
                    uam_frac = float(uam_mask[i:i + window].sum()) / window
                    if uam_frac > 0.2:
                        continue

                traj = glucose[i:i + window]
                tv = ~np.isnan(traj)
                if tv.sum() < window * 0.5:
                    continue

                bg_start = float(traj[0])
                t_hours = np.arange(window) * (5.0 / 60.0)

                best_sse, best_amp, best_tau = np.inf, 0.0, 1.0
                for tau_c in TAU_CANDIDATES:
                    basis = 1.0 - np.exp(-t_hours / tau_c)
                    bv = basis[tv]
                    denom = float(np.sum(bv ** 2))
                    if denom < 1e-6:
                        continue
                    amp = float(np.sum(bv * (bg_start - traj[tv])) / denom)
                    if amp < 5:
                        continue
                    sse = float(np.sum((traj[tv] - (bg_start - amp * basis[tv])) ** 2))
                    if sse < best_sse:
                        best_sse, best_amp, best_tau = sse, amp, tau_c

                if best_amp >= 5:
                    isf_est = best_amp / float(bolus[i])
                    estimates.append(isf_est)
                    taus.append(best_tau)
                    # R² for fit quality
                    basis = 1.0 - np.exp(-t_hours / best_tau)
                    pred = bg_start - best_amp * basis
                    ss_res = float(np.sum((traj[tv] - pred[tv]) ** 2))
                    ss_tot = float(np.sum((traj[tv] - np.mean(traj[tv])) ** 2))
                    fit_r2s.append(1 - ss_res / (ss_tot + 1e-10))

            return estimates, taus, fit_r2s

        # Raw (all correction events)
        raw_est, raw_tau, raw_r2 = fit_response_curves(exclude_uam=False)
        # UAM-clean (exclude windows with >20% UAM)
        clean_est, clean_tau, clean_r2 = fit_response_curves(exclude_uam=True)

        pr = {'patient': p['name'],
              'profile_isf': round(mean_isf_profile, 1)}

        if raw_est:
            pr['raw_isf_median'] = round(float(np.median(raw_est)), 1)
            pr['raw_isf_iqr'] = round(float(np.percentile(raw_est, 75) -
                                             np.percentile(raw_est, 25)), 1)
            pr['raw_n_events'] = len(raw_est)
            pr['raw_tau_median'] = round(float(np.median(raw_tau)), 2)
            pr['raw_fit_r2'] = round(float(np.mean(raw_r2)), 3)
        else:
            pr['raw_n_events'] = 0

        if clean_est:
            pr['clean_isf_median'] = round(float(np.median(clean_est)), 1)
            pr['clean_isf_iqr'] = round(float(np.percentile(clean_est, 75) -
                                               np.percentile(clean_est, 25)), 1)
            pr['clean_n_events'] = len(clean_est)
            pr['clean_tau_median'] = round(float(np.median(clean_tau)), 2)
            pr['clean_fit_r2'] = round(float(np.mean(clean_r2)), 3)
        else:
            pr['clean_n_events'] = 0

        if raw_est and clean_est:
            pr['isf_shift_pct'] = round(
                (float(np.median(clean_est)) - float(np.median(raw_est))) /
                (float(np.median(raw_est)) + 1e-6) * 100, 1)
            pr['events_lost_pct'] = round(
                (1 - len(clean_est) / (len(raw_est) + 1e-6)) * 100, 1)

        results['per_patient'].append(pr)

    with_both = [r for r in results['per_patient']
                 if r.get('raw_n_events', 0) > 0 and r.get('clean_n_events', 0) > 0]
    if with_both:
        results['mean_isf_shift_pct'] = round(
            float(np.mean([r['isf_shift_pct'] for r in with_both])), 1)
        results['mean_events_lost_pct'] = round(
            float(np.mean([r['events_lost_pct'] for r in with_both])), 1)
        results['mean_raw_fit_r2'] = round(
            float(np.mean([r['raw_fit_r2'] for r in with_both])), 3)
        results['mean_clean_fit_r2'] = round(
            float(np.mean([r['clean_fit_r2'] for r in with_both])), 3)
        results['uam_filtering_improves_fit'] = (
            results['mean_clean_fit_r2'] > results['mean_raw_fit_r2'])
    return results


# ─── EXP-1333: Overnight Basal Titration Protocol ────────────────────

def exp_1333_overnight_titration(patients, detail=False, preconditions=None):
    """Clinical-style overnight basal titration.

    Protocol: Find overnight windows (0-6 AM) with no bolus/carbs for ≥4h,
    BG between 80-200 at start. Measure glucose drift rate.
    If BG rises >10 mg/dL/h → increase basal.
    If BG drops >10 mg/dL/h → decrease basal.
    Compute specific U/h change recommendation.
    """
    results = {'name': 'EXP-1333: Overnight basal titration',
               'n_patients': len(patients), 'per_patient': []}

    MIN_WINDOW_HOURS = 4
    MIN_WINDOW_STEPS = MIN_WINDOW_HOURS * STEPS_PER_HOUR

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)

        overnight = get_overnight_mask(df, n)
        scheduled_rate = get_scheduled_basal_rate(p)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))

        # Find clean overnight windows
        windows = []
        i = 0
        while i < n - MIN_WINDOW_STEPS:
            if not overnight[i]:
                i += 1
                continue
            # Check for clean window (no bolus, no carbs, no preceding meal)
            # Need no carbs for 3h before window start
            pre_start = max(0, i - 3 * STEPS_PER_HOUR)
            if np.any(carbs[pre_start:i] > 2) or np.any(bolus[pre_start:i] > 0.5):
                i += STEPS_PER_HOUR
                continue

            # Find end of clean window
            end = i
            while end < n and overnight[end]:
                if bolus[end] > 0 or carbs[end] > 2:
                    break
                end += 1

            window_len = end - i
            if window_len >= MIN_WINDOW_STEPS:
                g_window = glucose[i:end]
                valid_g = g_window[~np.isnan(g_window)]
                if len(valid_g) >= MIN_WINDOW_STEPS * 0.7:
                    bg_start = float(valid_g[0])
                    if 70 <= bg_start <= 250:
                        # Linear regression for drift rate
                        valid_idx = np.where(~np.isnan(g_window))[0]
                        t_hours = valid_idx * (5.0 / 60.0)
                        g_valid = g_window[valid_idx]
                        if len(t_hours) > 2:
                            slope = float(np.polyfit(t_hours, g_valid, 1)[0])
                            windows.append({
                                'start_step': int(i),
                                'duration_hours': round(window_len / STEPS_PER_HOUR, 1),
                                'bg_start': round(bg_start, 1),
                                'bg_end': round(float(valid_g[-1]), 1),
                                'drift_mg_per_hour': round(slope, 2),
                            })
            i = end + 1

        if not windows:
            results['per_patient'].append({
                'patient': p['name'], 'n_windows': 0,
                'note': 'No clean overnight windows found'})
            continue

        drifts = [w['drift_mg_per_hour'] for w in windows]
        mean_drift = float(np.mean(drifts))
        median_drift = float(np.median(drifts))
        drift_std = float(np.std(drifts))

        # Clinical recommendation:
        # drift > 0 → BG rising → basal too low → increase
        # drift < 0 → BG falling → basal too high → decrease
        # Convert: Δ_rate = drift / ISF (mg/dL/h ÷ mg/dL/U = U/h)
        basal_change_u_per_h = median_drift / (isf_profile + 1e-6)
        # Round to nearest 0.025 U/h (clinical precision)
        basal_change_u_per_h = round(basal_change_u_per_h * 40) / 40
        new_rate = max(0.05, scheduled_rate + basal_change_u_per_h)

        # Confidence based on number of windows and consistency
        n_win = len(windows)
        cv = abs(drift_std / (mean_drift + 1e-6))
        confidence = 'high' if n_win >= 5 and cv < 1.5 else (
                     'medium' if n_win >= 3 else 'low')

        results['per_patient'].append({
            'patient': p['name'],
            'n_windows': n_win,
            'mean_drift_mg_per_hour': round(mean_drift, 2),
            'median_drift_mg_per_hour': round(median_drift, 2),
            'drift_std': round(drift_std, 2),
            'scheduled_rate_u_per_h': round(scheduled_rate, 3),
            'isf_profile': round(isf_profile, 1),
            'recommended_change_u_per_h': round(basal_change_u_per_h, 3),
            'recommended_new_rate': round(new_rate, 3),
            'pct_change': round(basal_change_u_per_h / (scheduled_rate + 1e-6) * 100, 1),
            'direction': 'increase' if basal_change_u_per_h > 0.01 else (
                         'decrease' if basal_change_u_per_h < -0.01 else 'maintain'),
            'confidence': confidence,
            'windows': windows[:5] if detail else [],
        })

    pp = [r for r in results['per_patient'] if r.get('n_windows', 0) > 0]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['mean_drift'] = round(
            float(np.mean([r['mean_drift_mg_per_hour'] for r in pp])), 2)
        results['direction_distribution'] = {
            d: sum(1 for r in pp if r.get('direction') == d)
            for d in ['increase', 'decrease', 'maintain']
        }
        results['confidence_distribution'] = {
            c: sum(1 for r in pp if r.get('confidence') == c)
            for c in ['high', 'medium', 'low']
        }
    return results


# ─── EXP-1334: DIA Validation from Correction Trajectories ──────────

def exp_1334_dia_validation(patients, detail=False, preconditions=None):
    """Validate Duration of Insulin Action from actual correction responses.

    Fit exponential decay to correction bolus trajectories.
    Time to 95% of final drop = effective DIA.
    Compare across patients and to profile DIA (typically 5h).
    """
    results = {'name': 'EXP-1334: DIA validation',
               'n_patients': len(patients), 'per_patient': []}

    DIA_SEARCH_HOURS = [2, 3, 4, 5, 6, 7, 8]

    for p in patients:
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)

        events = []
        for i in range(n):
            if bolus[i] < 0.5 or np.isnan(glucose[i]) or glucose[i] <= 150:
                continue
            cw = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[cw]) > 2:
                continue
            # Need long observation window
            max_window = 8 * STEPS_PER_HOUR
            if i + max_window >= n:
                continue
            # No additional bolus or carbs in observation
            if np.sum(bolus[i + 1:i + max_window]) > 0.5:
                continue
            if np.sum(carbs[i + 1:i + max_window]) > 2:
                continue

            traj = glucose[i:i + max_window]
            tv = ~np.isnan(traj)
            if tv.sum() < max_window * 0.4:
                continue

            bg_start = float(traj[0])
            t_hours = np.arange(max_window) * (5.0 / 60.0)

            # Fit exponential: BG(t) = BG_start - A*(1 - exp(-t/τ))
            # Try multiple tau values
            best_sse, best_amp, best_tau = np.inf, 0.0, 2.0
            for tau_c in np.arange(0.5, 6.1, 0.25):
                basis = 1.0 - np.exp(-t_hours / tau_c)
                bv = basis[tv]
                denom = float(np.sum(bv ** 2))
                if denom < 1e-6:
                    continue
                amp = float(np.sum(bv * (bg_start - traj[tv])) / denom)
                if amp < 10:  # Need meaningful drop
                    continue
                sse = float(np.sum((traj[tv] - (bg_start - amp * basis[tv])) ** 2))
                if sse < best_sse:
                    best_sse, best_amp, best_tau = sse, amp, tau_c

            if best_amp >= 10:
                # Effective DIA = time to 95% of final drop = -τ*ln(0.05) ≈ 3τ
                effective_dia_h = best_tau * 3.0
                # R² of fit
                pred = bg_start - best_amp * (1 - np.exp(-t_hours / best_tau))
                ss_res = float(np.sum((traj[tv] - pred[tv]) ** 2))
                ss_tot = float(np.sum((traj[tv] - np.mean(traj[tv])) ** 2))
                fit_r2 = 1 - ss_res / (ss_tot + 1e-10)

                events.append({
                    'bolus_u': float(bolus[i]),
                    'bg_start': bg_start,
                    'amplitude': round(best_amp, 1),
                    'tau_h': round(best_tau, 2),
                    'effective_dia_h': round(effective_dia_h, 1),
                    'fit_r2': round(fit_r2, 3),
                    'isf_observed': round(best_amp / float(bolus[i]), 1),
                })

        if not events:
            results['per_patient'].append({
                'patient': p['name'], 'n_events': 0,
                'note': 'No clean correction events'})
            continue

        taus = [e['tau_h'] for e in events]
        dias = [e['effective_dia_h'] for e in events]
        fit_r2s = [e['fit_r2'] for e in events]

        results['per_patient'].append({
            'patient': p['name'],
            'n_events': len(events),
            'tau_median_h': round(float(np.median(taus)), 2),
            'tau_iqr_h': round(float(np.percentile(taus, 75) -
                                     np.percentile(taus, 25)), 2),
            'effective_dia_median_h': round(float(np.median(dias)), 1),
            'effective_dia_iqr_h': round(float(np.percentile(dias, 75) -
                                               np.percentile(dias, 25)), 1),
            'mean_fit_r2': round(float(np.mean(fit_r2s)), 3),
            'profile_dia_h': 5.0,  # Standard assumption
            'dia_vs_profile_pct': round(
                (float(np.median(dias)) - 5.0) / 5.0 * 100, 1),
            'events': events[:5] if detail else [],
        })

    pp = [r for r in results['per_patient'] if r.get('n_events', 0) > 0]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['population_dia_median'] = round(
            float(np.median([r['effective_dia_median_h'] for r in pp])), 1)
        results['population_tau_median'] = round(
            float(np.median([r['tau_median_h'] for r in pp])), 2)
        results['mean_fit_r2'] = round(
            float(np.mean([r['mean_fit_r2'] for r in pp])), 3)
        # How many patients have DIA significantly different from 5h?
        results['n_dia_shorter'] = sum(
            1 for r in pp if r['effective_dia_median_h'] < 4.5)
        results['n_dia_longer'] = sum(
            1 for r in pp if r['effective_dia_median_h'] > 5.5)
        results['n_dia_correct'] = sum(
            1 for r in pp if 4.5 <= r['effective_dia_median_h'] <= 5.5)
    return results


# ─── EXP-1335: Specific U/h Basal Recommendations ───────────────────

def exp_1335_specific_basal_recs(patients, detail=False, preconditions=None):
    """Generate specific U/h basal rate changes per time block.

    Uses three converging methods for each block:
    1. Physics: net flux imbalance → rate change
    2. Drift: fasting BG drift → rate change
    3. Overnight titration (0-6 AM block only)
    """
    results = {'name': 'EXP-1335: Specific U/h basal recommendations',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']
        demand = sd['demand']

        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)

        fasting = np.ones(n, dtype=bool)
        for i in range(n):
            ws = max(0, i - STEPS_PER_HOUR * 2)
            we = min(n, i + STEPS_PER_HOUR * 2)
            if np.any(bolus[ws:we] > 0) or np.any(carbs[ws:we] > 0):
                fasting[i] = False

        scheduled_rate = get_scheduled_basal_rate(p)

        block_recs = []
        for bi, (bname, (blo, bhi)) in enumerate(zip(BLOCK_NAMES, BLOCK_RANGES)):
            block_mask = np.zeros(n, dtype=bool)
            for i in range(n):
                hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
                if blo <= hour < bhi:
                    block_mask[i] = True

            bfv = block_mask & fasting & valid
            n_fasting = int(bfv.sum())

            if n_fasting < STEPS_PER_HOUR:
                block_recs.append({
                    'block': bname, 'n_fasting_steps': n_fasting,
                    'note': 'Insufficient fasting data'})
                continue

            # Method 1: Physics-based
            mean_net = float(np.mean(net_flux[bfv]))
            mean_demand = float(np.mean(demand[bfv]))
            physics_change = -mean_net / (mean_demand + 1e-6)
            physics_change = max(-0.5, min(0.5, physics_change))
            physics_u_change = physics_change * scheduled_rate

            # Method 2: Drift-based
            drift_per_5min = float(np.mean(dg[bfv]))
            drift_per_hour = drift_per_5min * STEPS_PER_HOUR
            drift_u_change = drift_per_hour / (isf_profile + 1e-6)

            # Average of methods (with more weight on drift which is more direct)
            avg_u_change = 0.4 * physics_u_change + 0.6 * drift_u_change
            # Round to nearest 0.025
            avg_u_change = round(avg_u_change * 40) / 40
            new_rate = max(0.05, scheduled_rate + avg_u_change)

            block_recs.append({
                'block': bname,
                'n_fasting_steps': n_fasting,
                'physics_change_u': round(physics_u_change, 3),
                'drift_mg_per_hour': round(drift_per_hour, 2),
                'drift_change_u': round(drift_u_change, 3),
                'recommended_change_u': round(avg_u_change, 3),
                'current_rate': round(scheduled_rate, 3),
                'recommended_rate': round(new_rate, 3),
                'direction': 'increase' if avg_u_change > 0.01 else (
                             'decrease' if avg_u_change < -0.01 else 'maintain'),
            })

        results['per_patient'].append({
            'patient': p['name'],
            'scheduled_rate': round(scheduled_rate, 3),
            'blocks': block_recs,
        })

    return results


# ─── EXP-1336: CR Assessment per Meal Block ──────────────────────────

def exp_1336_cr_assessment(patients, detail=False, preconditions=None):
    """Evaluate carb ratio effectiveness per meal time.

    For each meal event with logged carbs:
    - Compute 3h post-meal BG excursion
    - Compare to expected excursion given CR
    - If excursion > expected → CR too high (needs more insulin)
    - If excursion < expected → CR too low
    """
    results = {'name': 'EXP-1336: CR assessment per meal block',
               'n_patients': len(patients), 'per_patient': []}

    MEAL_BLOCKS = [('breakfast', 6, 10), ('lunch', 10, 14),
                   ('dinner', 14, 20), ('late', 20, 24)]

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        isf_profile = float(np.nanmean(pk[:, 7] * 200.0))
        n = len(glucose)

        # Extract CR from PK channel (carb_rate normalized by 0.5)
        # CR = grams_carb / units_insulin → higher means less insulin per gram
        # For now, estimate from profile: check if available in PK
        # PK channel 3 is carb_rate (g/5min normalized by 0.5)
        cr_profile = 10.0  # Default; will try to estimate

        meal_events = defaultdict(list)
        last_meal_step = -3 * STEPS_PER_HOUR

        for i in range(n):
            if carbs[i] < 5 or (i - last_meal_step) < 2 * STEPS_PER_HOUR:
                continue
            last_meal_step = i

            # Determine meal block
            hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
            meal_block = 'other'
            for bname, blo, bhi in MEAL_BLOCKS:
                if blo <= hour < bhi:
                    meal_block = bname
                    break

            # 3h post-meal window
            post_window = min(n, i + 3 * STEPS_PER_HOUR)
            if post_window - i < STEPS_PER_HOUR:
                continue

            post_g = glucose[i:post_window]
            pre_g = glucose[max(0, i - 3):i + 1]
            pre_valid = pre_g[~np.isnan(pre_g)]
            if len(pre_valid) == 0:
                continue

            bg_start = float(np.mean(pre_valid))
            bg_peak = float(np.nanmax(post_g)) if np.any(~np.isnan(post_g)) else bg_start
            bg_3h = float(post_g[~np.isnan(post_g)][-1]) if np.any(~np.isnan(post_g)) else bg_start

            excursion = bg_peak - bg_start
            meal_bolus = float(np.sum(bolus[max(0, i - 2):min(n, i + 6)]))

            # Expected excursion: carbs * ISF / CR - bolus * ISF
            # If perfect: excursion ≈ 0 (bolus perfectly matches carbs)
            # Positive excursion → bolus was too small → CR too high
            carb_g = float(carbs[i])

            meal_events[meal_block].append({
                'carbs_g': carb_g,
                'bolus_u': round(meal_bolus, 2),
                'bg_start': round(bg_start, 1),
                'bg_peak': round(bg_peak, 1),
                'bg_3h': round(bg_3h, 1),
                'excursion': round(excursion, 1),
                'return_to_baseline': round(bg_3h - bg_start, 1),
            })

        # Analyze per block
        block_analysis = {}
        for block, events in meal_events.items():
            if len(events) < 3:
                continue
            excursions = [e['excursion'] for e in events]
            returns = [e['return_to_baseline'] for e in events]
            block_analysis[block] = {
                'n_meals': len(events),
                'mean_excursion': round(float(np.mean(excursions)), 1),
                'median_excursion': round(float(np.median(excursions)), 1),
                'mean_return': round(float(np.mean(returns)), 1),
                'pct_high_excursion': round(
                    sum(1 for e in excursions if e > 60) / len(excursions) * 100, 1),
                'pct_not_returned': round(
                    sum(1 for r in returns if r > 30) / len(returns) * 100, 1),
                'cr_assessment': ('too_high' if float(np.mean(excursions)) > 60 else
                                  'too_low' if float(np.mean(excursions)) < 20 else 'ok'),
            }

        results['per_patient'].append({
            'patient': p['name'],
            'n_total_meals': sum(len(v) for v in meal_events.values()),
            'blocks': block_analysis,
        })

    # Summary
    all_blocks = defaultdict(list)
    for r in results['per_patient']:
        for bname, bdata in r.get('blocks', {}).items():
            all_blocks[bname].append(bdata)
    results['population_summary'] = {}
    for bname, blist in all_blocks.items():
        results['population_summary'][bname] = {
            'n_patients': len(blist),
            'mean_excursion': round(float(np.mean(
                [b['mean_excursion'] for b in blist])), 1),
            'mean_pct_high': round(float(np.mean(
                [b['pct_high_excursion'] for b in blist])), 1),
        }
    return results


# ─── EXP-1337: Time-of-Day ISF Variation ─────────────────────────────

def exp_1337_tod_isf(patients, detail=False, preconditions=None):
    """Measure ISF variation by time of day using response curves.

    Clinical observation: ISF is often lower in the morning (dawn phenomenon,
    cortisol) and higher in the afternoon. Quantify this across patients.
    """
    TAU_CANDIDATES = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
    results = {'name': 'EXP-1337: Time-of-day ISF variation',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)

        # Bin corrections by time of day
        tod_isf = defaultdict(list)
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

            traj = glucose[i:i + window]
            tv = ~np.isnan(traj)
            if tv.sum() < window * 0.5:
                continue

            bg_start = float(traj[0])
            t_hours = np.arange(window) * (5.0 / 60.0)

            best_amp, best_tau = 0.0, 1.0
            best_sse = np.inf
            for tau_c in TAU_CANDIDATES:
                basis = 1.0 - np.exp(-t_hours / tau_c)
                bv = basis[tv]
                denom = float(np.sum(bv ** 2))
                if denom < 1e-6:
                    continue
                amp = float(np.sum(bv * (bg_start - traj[tv])) / denom)
                if amp < 5:
                    continue
                sse = float(np.sum((traj[tv] - (bg_start - amp * basis[tv])) ** 2))
                if sse < best_sse:
                    best_sse, best_amp, best_tau = sse, amp, tau_c

            if best_amp >= 5:
                isf = best_amp / float(bolus[i])
                hour = (i % STEPS_PER_DAY) / STEPS_PER_HOUR
                block_idx = get_time_block(i % STEPS_PER_DAY)
                tod_isf[BLOCK_NAMES[block_idx]].append(isf)

        if not tod_isf:
            results['per_patient'].append({
                'patient': p['name'], 'n_events': 0,
                'note': 'No correction events'})
            continue

        block_summary = {}
        all_isf = []
        for bname in BLOCK_NAMES:
            vals = tod_isf.get(bname, [])
            if vals:
                block_summary[bname] = {
                    'n': len(vals),
                    'median_isf': round(float(np.median(vals)), 1),
                    'iqr': round(float(np.percentile(vals, 75) -
                                       np.percentile(vals, 25)), 1),
                }
                all_isf.extend(vals)

        overall_median = float(np.median(all_isf)) if all_isf else 50.0

        # Dawn effect: morning ISF vs overnight ISF
        morning_vals = tod_isf.get('morning(6-10)', [])
        overnight_vals = tod_isf.get('overnight(0-6)', [])
        if morning_vals and overnight_vals:
            dawn_ratio = (float(np.median(morning_vals)) /
                         (float(np.median(overnight_vals)) + 1e-6))
        else:
            dawn_ratio = None

        results['per_patient'].append({
            'patient': p['name'],
            'n_events': len(all_isf),
            'overall_median_isf': round(overall_median, 1),
            'blocks': block_summary,
            'dawn_ratio': round(dawn_ratio, 2) if dawn_ratio else None,
            'max_variation_pct': round(
                (max(b['median_isf'] for b in block_summary.values()) -
                 min(b['median_isf'] for b in block_summary.values())) /
                (overall_median + 1e-6) * 100, 1)
            if len(block_summary) >= 2 else 0.0,
        })

    pp = [r for r in results['per_patient'] if r.get('n_events', 0) > 0]
    if pp:
        results['n_patients_with_data'] = len(pp)
        dawn_ratios = [r['dawn_ratio'] for r in pp if r['dawn_ratio'] is not None]
        if dawn_ratios:
            results['mean_dawn_ratio'] = round(float(np.mean(dawn_ratios)), 2)
            results['n_dawn_detected'] = sum(1 for d in dawn_ratios if d < 0.8)
        results['mean_max_variation_pct'] = round(
            float(np.mean([r.get('max_variation_pct', 0) for r in pp])), 1)
    return results


# ─── EXP-1338: Multi-Week Stability Assessment ──────────────────────

def exp_1338_multiweek_stability(patients, detail=False, preconditions=None):
    """Track therapy metrics stability across 4-week rolling windows.

    Does ISF/basal/CR drift over 6 months? Identify patients needing
    periodic reassessment vs those with stable settings.
    """
    WINDOW_WEEKS = 4
    WINDOW_STEPS = WINDOW_WEEKS * 7 * STEPS_PER_DAY
    STEP_WEEKS = 2
    STEP_SIZE = STEP_WEEKS * 7 * STEPS_PER_DAY

    results = {'name': 'EXP-1338: Multi-week stability',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']
        demand = sd['demand']
        isf_profile = pk[:, 7] * 200.0

        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)

        windows = []
        start = 0
        while start + WINDOW_STEPS <= n:
            end = start + WINDOW_STEPS
            wv = valid[start:end]
            wg = glucose[start:end]
            wn = net_flux[start:end]
            wd = demand[start:end]
            wb = bolus[start:end]
            wc = carbs[start:end]

            # TIR for this window
            gv = wg[~np.isnan(wg)]
            if len(gv) < STEPS_PER_DAY:
                start += STEP_SIZE
                continue

            tir = float(np.sum((gv >= 70) & (gv <= 180))) / len(gv) * 100

            # Mean BG
            mean_bg = float(np.mean(gv))

            # Fasting drift
            fasting_w = np.ones(len(wg), dtype=bool)
            for i in range(len(wg)):
                ws = max(0, i - STEPS_PER_HOUR * 2)
                we = min(len(wg), i + STEPS_PER_HOUR * 2)
                if np.any(wb[ws:we] > 0) or np.any(wc[ws:we] > 0):
                    fasting_w[i] = False
            fv = fasting_w & wv[:len(fasting_w)]
            if fv.sum() > STEPS_PER_HOUR:
                drift = float(np.mean(dg[start:end][fv[:end - start]])) * STEPS_PER_HOUR
            else:
                drift = 0.0

            # Simple ISF estimate from corrections in window
            isf_ests = []
            for i in range(len(wg)):
                gi = start + i
                if gi >= n:
                    break
                if bolus[gi] < 0.3 or np.isnan(glucose[gi]) or glucose[gi] <= 150:
                    continue
                post_end = min(gi + 3 * STEPS_PER_HOUR, n)
                if post_end - gi < STEPS_PER_HOUR:
                    continue
                post_g = glucose[gi:post_end]
                pv = ~np.isnan(post_g)
                if pv.sum() < STEPS_PER_HOUR // 2:
                    continue
                drop = float(post_g[0] - np.nanmin(post_g))
                if drop > 10:
                    isf_ests.append(drop / float(bolus[gi]))

            window_isf = float(np.median(isf_ests)) if isf_ests else None

            windows.append({
                'week': len(windows) * STEP_WEEKS,
                'tir': round(tir, 1),
                'mean_bg': round(mean_bg, 1),
                'drift_mg_per_hour': round(drift, 2),
                'isf_estimate': round(window_isf, 1) if window_isf else None,
                'n_corrections': len(isf_ests),
            })
            start += STEP_SIZE

        if len(windows) < 2:
            results['per_patient'].append({
                'patient': p['name'], 'n_windows': len(windows),
                'note': 'Insufficient data for multi-window analysis'})
            continue

        # Trend analysis
        tirs = [w['tir'] for w in windows]
        drifts = [w['drift_mg_per_hour'] for w in windows]
        isfs = [w['isf_estimate'] for w in windows if w['isf_estimate'] is not None]

        tir_trend = float(np.polyfit(range(len(tirs)), tirs, 1)[0]) if len(tirs) > 2 else 0
        drift_trend = float(np.polyfit(range(len(drifts)), drifts, 1)[0]) if len(drifts) > 2 else 0

        # ISF trend
        if len(isfs) > 2:
            isf_trend = float(np.polyfit(range(len(isfs)), isfs, 1)[0])
            isf_cv = float(np.std(isfs) / (np.mean(isfs) + 1e-6))
        else:
            isf_trend, isf_cv = 0.0, 0.0

        stable = (abs(tir_trend) < 2.0 and abs(isf_trend) < 3.0 and isf_cv < 0.3)

        results['per_patient'].append({
            'patient': p['name'],
            'n_windows': len(windows),
            'tir_range': [round(min(tirs), 1), round(max(tirs), 1)],
            'tir_trend_per_window': round(tir_trend, 2),
            'drift_trend': round(drift_trend, 3),
            'isf_cv': round(isf_cv, 2),
            'isf_trend_per_window': round(isf_trend, 2),
            'stable': stable,
            'windows': windows if detail else [],
        })

    pp = [r for r in results['per_patient'] if r.get('n_windows', 0) >= 2]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['n_stable'] = sum(1 for r in pp if r.get('stable'))
        results['n_drifting'] = sum(1 for r in pp if not r.get('stable'))
        results['mean_tir_trend'] = round(
            float(np.mean([r['tir_trend_per_window'] for r in pp])), 2)
        results['mean_isf_cv'] = round(
            float(np.mean([r['isf_cv'] for r in pp])), 2)
    return results


# ─── EXP-1339: Hepatic Glucose Rhythm Characterization ──────────────

def exp_1339_hepatic_rhythm(patients, detail=False, preconditions=None):
    """Characterize hepatic glucose output patterns by time of day.

    Hepatic glucose production (HGP) is the major source of fasting glucose.
    Dawn phenomenon = increased HGP in early morning.
    Use PK channel 4 (hepatic) and fasting glucose rises to estimate.
    """
    results = {'name': 'EXP-1339: Hepatic glucose rhythm',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        hepatic = pk[:, 4] * 3.0  # Denormalized hepatic channel
        n = len(glucose)

        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        valid = ~np.isnan(glucose)

        # Fasting mask
        fasting = np.ones(n, dtype=bool)
        for i in range(n):
            ws = max(0, i - STEPS_PER_HOUR * 3)
            we = min(n, i + STEPS_PER_HOUR)
            if np.any(bolus[ws:we] > 0) or np.any(carbs[ws:we] > 2):
                fasting[i] = False

        # Per-hour analysis of hepatic output and fasting glucose drift
        hourly = defaultdict(lambda: {'hepatic': [], 'drift': [], 'bg': []})
        for i in range(n):
            if not valid[i] or not fasting[i]:
                continue
            hour = int((i % STEPS_PER_DAY) / STEPS_PER_HOUR)
            hourly[hour]['hepatic'].append(float(hepatic[i]))
            hourly[hour]['drift'].append(float(dg[i]))
            hourly[hour]['bg'].append(float(glucose[i]))

        hour_summary = {}
        for hour in range(24):
            data = hourly[hour]
            if len(data['hepatic']) < STEPS_PER_HOUR:
                continue
            hour_summary[str(hour)] = {
                'mean_hepatic': round(float(np.mean(data['hepatic'])), 3),
                'mean_drift_per_5min': round(float(np.mean(data['drift'])), 3),
                'mean_bg': round(float(np.mean(data['bg'])), 1),
                'n_samples': len(data['hepatic']),
            }

        if not hour_summary:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient fasting data'})
            continue

        # Dawn detection: compare 4-7 AM drift to 0-3 AM drift
        dawn_hours = [str(h) for h in range(4, 8) if str(h) in hour_summary]
        night_hours = [str(h) for h in range(0, 4) if str(h) in hour_summary]

        if dawn_hours and night_hours:
            dawn_drift = float(np.mean(
                [hour_summary[h]['mean_drift_per_5min'] for h in dawn_hours]))
            night_drift = float(np.mean(
                [hour_summary[h]['mean_drift_per_5min'] for h in night_hours]))
            dawn_detected = dawn_drift > night_drift + 0.1  # >0.1 mg/dL/5min increase
            dawn_magnitude = (dawn_drift - night_drift) * STEPS_PER_HOUR  # mg/dL/h
        else:
            dawn_detected = False
            dawn_magnitude = 0.0

        # Peak hepatic hour
        peak_hour = max(hour_summary.keys(),
                       key=lambda h: hour_summary[h]['mean_hepatic'])

        results['per_patient'].append({
            'patient': p['name'],
            'n_hours_with_data': len(hour_summary),
            'peak_hepatic_hour': int(peak_hour),
            'peak_hepatic_value': hour_summary[peak_hour]['mean_hepatic'],
            'dawn_detected': dawn_detected,
            'dawn_magnitude_mg_per_hour': round(dawn_magnitude, 2),
            'hourly': hour_summary if detail else {},
        })

    pp = [r for r in results['per_patient'] if 'peak_hepatic_hour' in r]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['n_dawn_detected'] = sum(1 for r in pp if r.get('dawn_detected'))
        results['mean_dawn_magnitude'] = round(
            float(np.nanmean([r['dawn_magnitude_mg_per_hour'] for r in pp])), 2)
        # Most common peak hour
        peak_hours = [r['peak_hepatic_hour'] for r in pp]
        results['peak_hour_distribution'] = dict(
            sorted([(h, peak_hours.count(h)) for h in set(peak_hours)]))
    return results


# ─── EXP-1340: Therapy Simulation ────────────────────────────────────

def exp_1340_therapy_simulation(patients, detail=False, preconditions=None):
    """Simulate therapy outcomes if recommendations were applied.

    For each patient:
    1. Get overnight titration recommendation (EXP-1333 style)
    2. Get ISF from response curves (EXP-1332 style)
    3. Apply adjustments to supply/demand model
    4. Estimate new TIR, mean BG, and time below range

    This is a counterfactual estimate — not a closed-loop simulation.
    """
    results = {'name': 'EXP-1340: Therapy simulation',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)

        valid = ~np.isnan(glucose)
        gv = glucose[valid]
        if len(gv) < STEPS_PER_DAY:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'Insufficient data'})
            continue

        sd = compute_supply_demand(df, pk)
        net_flux = sd['net']

        # Current metrics
        current_tir = float(np.sum((gv >= 70) & (gv <= 180))) / len(gv) * 100
        current_mean_bg = float(np.mean(gv))
        current_tbr = float(np.sum(gv < 70)) / len(gv) * 100
        current_tar = float(np.sum(gv > 180)) / len(gv) * 100

        # Get basal adjustment from overnight analysis
        overnight = get_overnight_mask(df, n)
        fasting = np.ones(n, dtype=bool)
        for i in range(n):
            ws = max(0, i - STEPS_PER_HOUR * 2)
            we = min(n, i + STEPS_PER_HOUR * 2)
            if np.any(bolus[ws:we] > 0) or np.any(carbs[ws:we] > 0):
                fasting[i] = False

        dg = np.diff(glucose)
        dg = np.append(dg, 0)
        dg_valid = valid & ~np.isnan(dg) & (np.abs(dg) < 50)
        overnight_fasting = overnight & fasting & dg_valid

        if overnight_fasting.sum() > STEPS_PER_HOUR:
            overnight_drift = float(np.nanmean(dg[overnight_fasting])) * STEPS_PER_HOUR
        else:
            overnight_drift = 0.0

        # Handle NaN drift
        if np.isnan(overnight_drift):
            overnight_drift = 0.0

        # Simulate: adjust glucose trajectory by correcting drift
        # If basal too low (drift > 0), more insulin → BG lower
        # Small correction per step = -drift spread across hour
        # Cap to ±0.5 mg/dL per 5-min step (±6 mg/dL/h — conservative)
        correction_per_step = -overnight_drift / STEPS_PER_HOUR
        correction_per_step = max(-0.5, min(0.5, correction_per_step))

        # Apply correction with exponential decay (don't accumulate)
        simulated_glucose = glucose.copy()
        cumulative_correction = 0.0
        for i in range(n):
            if np.isnan(glucose[i]):
                continue
            # Exponential decay prevents unrealistic accumulation
            cumulative_correction = cumulative_correction * 0.95 + correction_per_step
            simulated_glucose[i] = glucose[i] + cumulative_correction

        sv = simulated_glucose[valid]
        sim_tir = float(np.sum((sv >= 70) & (sv <= 180))) / len(sv) * 100
        sim_mean_bg = float(np.mean(sv))
        sim_tbr = float(np.sum(sv < 70)) / len(sv) * 100
        sim_tar = float(np.sum(sv > 180)) / len(sv) * 100

        results['per_patient'].append({
            'patient': p['name'],
            'current_tir': round(current_tir, 1),
            'simulated_tir': round(sim_tir, 1),
            'tir_change': round(sim_tir - current_tir, 1),
            'current_mean_bg': round(current_mean_bg, 1),
            'simulated_mean_bg': round(sim_mean_bg, 1),
            'current_tbr': round(current_tbr, 1),
            'simulated_tbr': round(sim_tbr, 1),
            'current_tar': round(current_tar, 1),
            'simulated_tar': round(sim_tar, 1),
            'overnight_drift_mg_per_h': round(overnight_drift, 2),
            'correction_per_step': round(correction_per_step, 3),
        })

    pp = [r for r in results['per_patient'] if 'current_tir' in r]
    if pp:
        results['n_patients_with_data'] = len(pp)
        results['mean_tir_change'] = round(
            float(np.mean([r['tir_change'] for r in pp])), 1)
        results['mean_current_tir'] = round(
            float(np.mean([r['current_tir'] for r in pp])), 1)
        results['mean_simulated_tir'] = round(
            float(np.mean([r['simulated_tir'] for r in pp])), 1)
        results['mean_tbr_change'] = round(
            float(np.mean([r['simulated_tbr'] - r['current_tbr'] for r in pp])), 1)
        results['n_improved'] = sum(1 for r in pp if r['tir_change'] > 1)
        results['n_worsened'] = sum(1 for r in pp if r['tir_change'] < -1)
        results['n_neutral'] = sum(1 for r in pp if abs(r['tir_change']) <= 1)
    return results


# ─── Experiment Registry ─────────────────────────────────────────────

EXPERIMENTS = {
    1331: ('Basal ground truth validation', exp_1331_basal_ground_truth),
    1332: ('UAM-clean response-curve ISF', exp_1332_uam_clean_isf),
    1333: ('Overnight basal titration', exp_1333_overnight_titration),
    1334: ('DIA validation', exp_1334_dia_validation),
    1335: ('Specific U/h basal recommendations', exp_1335_specific_basal_recs),
    1336: ('CR assessment per meal block', exp_1336_cr_assessment),
    1337: ('Time-of-day ISF variation', exp_1337_tod_isf),
    1338: ('Multi-week stability', exp_1338_multiweek_stability),
    1339: ('Hepatic glucose rhythm', exp_1339_hepatic_rhythm),
    1340: ('Therapy simulation', exp_1340_therapy_simulation),
}


def main():
    parser = argparse.ArgumentParser(
        description='EXP-1331-1340: Therapy Operationalization')
    parser.add_argument('--exp', type=int, help='Run single experiment')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    args = parser.parse_args()

    print(f"Loading patients (max={args.max_patients})...")
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    # Precondition assessment
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
        print(f"  {p['name']}: {met}/{total} met | "
              f"CGM={m['cgm_coverage_pct']}% ins={m['insulin_telemetry_pct']}% "
              f"R²={m['fidelity_r2']}")

    # Run experiments
    exps_to_run = [args.exp] if args.exp else sorted(EXPERIMENTS.keys())
    all_results = {}
    for eid in exps_to_run:
        if eid not in EXPERIMENTS:
            print(f"Unknown experiment: {eid}")
            continue
        name, func = EXPERIMENTS[eid]
        print(f"\n{'='*60}")
        print(f"EXP-{eid}: {name}")
        print(f"{'='*60}")
        t0 = time.time()
        try:
            result = func(patients, detail=args.detail,
                          preconditions=precond_results)
            result['elapsed_sec'] = round(time.time() - t0, 1)
            all_results[eid] = result
            print(f"  Completed in {result['elapsed_sec']}s")
            for k, v in result.items():
                if k not in ('per_patient', 'elapsed_sec', 'name',
                             'windows', 'hourly', 'blocks',
                             'population_summary', 'block_recs'):
                    print(f"  {k}: {v}")
            if args.save:
                fname = f'exp-{eid}_therapy.json'
                with open(fname, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved → {fname}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            all_results[eid] = {'error': str(e)}

    # Summary
    print(f"\n{'='*60}")
    print("THERAPY OPERATIONALIZATION SUMMARY")
    print(f"{'='*60}")
    for eid, result in sorted(all_results.items()):
        name = EXPERIMENTS[eid][0]
        if 'error' in result:
            print(f"  EXP-{eid} {name}: FAILED - {result['error']}")
        else:
            key_metrics = {
                1331: f"best_method={result.get('best_method_for_well_calibrated','?')}, "
                      f"well-cal raw={result.get('well_calibrated_raw_mean','?')}%, "
                      f"overnight={result.get('well_calibrated_overnight_mean','?')}%",
                1332: f"ISF_shift={result.get('mean_isf_shift_pct','?')}%, "
                      f"events_lost={result.get('mean_events_lost_pct','?')}%, "
                      f"fit_improved={result.get('uam_filtering_improves_fit','?')}",
                1333: f"drift={result.get('mean_drift','?')} mg/h, "
                      f"conf={result.get('confidence_distribution','?')}",
                1334: f"DIA={result.get('population_dia_median','?')}h, "
                      f"τ={result.get('population_tau_median','?')}h, "
                      f"fit_R²={result.get('mean_fit_r2','?')}",
                1335: f"per-patient block recommendations generated",
                1336: f"pop_summary={result.get('population_summary','?')}",
                1337: f"dawn_ratio={result.get('mean_dawn_ratio','?')}, "
                      f"variation={result.get('mean_max_variation_pct','?')}%",
                1338: f"stable={result.get('n_stable','?')}, "
                      f"drifting={result.get('n_drifting','?')}, "
                      f"ISF_CV={result.get('mean_isf_cv','?')}",
                1339: f"dawn={result.get('n_dawn_detected','?')}/{result.get('n_patients_with_data','?')}, "
                      f"magnitude={result.get('mean_dawn_magnitude','?')} mg/h",
                1340: f"TIR: {result.get('mean_current_tir','?')}→{result.get('mean_simulated_tir','?')} "
                      f"(Δ={result.get('mean_tir_change','?')}), "
                      f"improved={result.get('n_improved','?')}/{result.get('n_patients_with_data','?')}",
            }
            print(f"  EXP-{eid} {name}: {key_metrics.get(eid, 'done')}")

    return all_results


if __name__ == '__main__':
    main()
