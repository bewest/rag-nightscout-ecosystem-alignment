#!/usr/bin/env python3
"""EXP-1641 through EXP-1648: Rescue Carb Inference from Glucose Trajectory.

EXP-1635 showed that oracle rescue carbs improve hypo recovery R² from -5.4 to
+0.80 — rescue carbs are THE missing signal. This experiment series asks: can we
INFER rescue carb intake from the observable glucose trajectory alone?

Key questions:
  1. What does the post-nadir glucose curve look like parametrically?
  2. How quickly can we detect that rescue carbs were consumed?
  3. Can we estimate the magnitude from the first 10-30 min of recovery?
  4. Can we separate counter-regulatory response from rescue carb signal?
  5. Does glycogen state improve inference?
  6. Does inferred rescue carb knowledge improve glucose forecasts?
  7. Are rescue patterns consistent across patients?
  8. Is a practical real-time detector feasible?

References:
  EXP-1601–1606: Hypo supply-demand decomposition
  EXP-1621–1628: Demand diagnosis, rescue carb quantification, glycogen proxy
  EXP-1631–1636: Corrected model, information ceiling (oracle R²=0.80)
"""

import sys
import os
import json
import argparse
import warnings
from pathlib import Path
from collections import defaultdict

import numpy as np
from scipy import stats, optimize
from scipy.signal import savgol_filter

warnings.filterwarnings('ignore', category=RuntimeWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.exp_metabolic_flux import load_patients, _extract_isf_scalar
from cgmencode.exp_metabolic_441 import compute_supply_demand

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'
FIGURES_DIR = Path(__file__).parent.parent.parent / 'docs' / '60-research' / 'figures'


# ── Hypo episode detection (refined from EXP-1621) ────────────────────

def find_hypo_episodes(glucose, carbs, iob, sd_dict, threshold=70,
                       pre_window=36, post_window=36):
    """Find hypo episodes with rich context for rescue carb analysis.

    Returns episodes with pre/post windows, supply-demand context,
    and detailed recovery trajectory.

    Args:
        glucose: (N,) glucose values
        carbs: (N,) entered carb values
        iob: (N,) insulin on board
        sd_dict: output from compute_supply_demand()
        threshold: BG threshold for hypo (mg/dL)
        pre_window: steps before nadir to capture (default 3h)
        post_window: steps after nadir to capture (default 3h)
    """
    N = len(glucose)
    episodes = []
    i = 0
    min_gap = 12  # 1h between episodes

    while i < N - post_window:
        if np.isnan(glucose[i]) or glucose[i] >= threshold:
            i += 1
            continue

        # Find nadir within this hypo excursion
        nadir_idx = i
        nadir_bg = glucose[i]
        j = i + 1
        while j < min(i + post_window, N):
            if np.isnan(glucose[j]):
                j += 1
                continue
            if glucose[j] < nadir_bg:
                nadir_bg = glucose[j]
                nadir_idx = j
            if glucose[j] > threshold + 30:
                break
            j += 1

        # Ensure valid windows
        pre_start = max(0, nadir_idx - pre_window)
        post_end = min(N, nadir_idx + post_window)

        if post_end - nadir_idx < 6:
            i = j + min_gap
            continue

        # Extract trajectories
        pre_bg = glucose[pre_start:nadir_idx + 1]
        post_bg = glucose[nadir_idx:post_end]
        post_carbs = carbs[nadir_idx:post_end]

        # Check data quality
        valid_post = ~np.isnan(post_bg)
        if valid_post.sum() < 6:
            i = j + min_gap
            continue

        # Recovery metrics
        peak_recovery = float(np.nanmax(post_bg))
        rebound = peak_recovery - nadir_bg

        # Time to recover above threshold
        recovery_steps = post_window
        for k in range(1, len(post_bg)):
            if not np.isnan(post_bg[k]) and post_bg[k] >= threshold:
                recovery_steps = k
                break

        # Entered carbs in recovery
        announced = float(np.nansum(post_carbs))

        # Pre-hypo context
        pre_iob = float(np.nanmean(iob[pre_start:nadir_idx + 1]))

        # Supply-demand at nadir
        supply_at_nadir = float(sd_dict['supply'][nadir_idx])
        demand_at_nadir = float(sd_dict['demand'][nadir_idx])
        net_at_nadir = float(sd_dict['net'][nadir_idx])

        # Recovery rate: dBG/dt in first 30 min post-nadir
        rec_30 = post_bg[:7]  # 6 steps = 30 min + nadir
        valid_30 = ~np.isnan(rec_30)
        if valid_30.sum() >= 3:
            # Linear fit for initial recovery rate
            t = np.arange(len(rec_30))[valid_30]
            bg = rec_30[valid_30]
            if len(t) >= 2:
                slope = np.polyfit(t, bg, 1)[0]
                recovery_rate_30 = float(slope)  # mg/dL per step
            else:
                recovery_rate_30 = float('nan')
        else:
            recovery_rate_30 = float('nan')

        # Actual dBG/dt trajectory (smoothed)
        post_dbg = np.full(len(post_bg), np.nan)
        for k in range(1, len(post_bg)):
            if not np.isnan(post_bg[k]) and not np.isnan(post_bg[k - 1]):
                post_dbg[k] = post_bg[k] - post_bg[k - 1]

        # Residual trajectory (actual dBG - predicted dBG from S×D model)
        post_net = sd_dict['net'][nadir_idx:post_end]
        residual = np.full(len(post_bg), np.nan)
        for k in range(1, len(post_bg)):
            if not np.isnan(post_dbg[k]):
                residual[k] = post_dbg[k] - post_net[k]

        episodes.append({
            'nadir_idx': nadir_idx,
            'nadir_bg': float(nadir_bg),
            'pre_start': pre_start,
            'post_end': post_end,
            'rebound_mg': float(rebound),
            'peak_recovery_bg': peak_recovery,
            'recovery_steps': recovery_steps,
            'announced_carbs': announced,
            'has_announced': announced > 1.0,
            'pre_iob': pre_iob,
            'supply_at_nadir': supply_at_nadir,
            'demand_at_nadir': demand_at_nadir,
            'net_at_nadir': net_at_nadir,
            'recovery_rate_30': recovery_rate_30,
            'post_bg': post_bg.copy(),
            'post_dbg': post_dbg.copy(),
            'post_net': post_net.copy(),
            'residual': residual.copy(),
        })
        i = j + min_gap

    return episodes


def compute_glycogen_proxy(glucose, carbs, iob, window_hours=6):
    """Glycogen pool proxy (from EXP-1626)."""
    N = len(glucose)
    window = window_hours * STEPS_PER_HOUR
    proxy = np.full(N, np.nan)
    for i in range(window, N):
        bg_w = glucose[i - window:i]
        carb_w = carbs[i - window:i]
        iob_w = iob[i - window:i]
        valid = ~np.isnan(bg_w)
        if valid.sum() < window // 2:
            continue
        bg_score = np.clip((float(np.nanmean(bg_w)) - 70) / 110, 0, 1.5)
        carb_score = np.clip(float(np.nansum(carb_w)) / 100, 0, 2.0)
        depletion = float(np.nansum(bg_w[valid] < 70)) / max(valid.sum(), 1) * 3
        iob_pen = np.clip(float(np.nanmean(np.abs(iob_w))) / 5.0, 0, 0.5)
        proxy[i] = np.clip(0.4 * bg_score + 0.3 * carb_score - 0.2 * depletion - 0.1 * iob_pen, 0, 1)
    return proxy


# ── EXP-1641: Post-Nadir Trajectory Characterization ─────────────────

def exp_1641_trajectory_characterization(patients):
    """Fit parametric models to post-nadir glucose trajectories.

    Three models compared:
      1. Linear: BG(t) = nadir + rate × t
      2. Exponential saturation: BG(t) = nadir + A × (1 - exp(-t/τ))
      3. Logistic: BG(t) = nadir + A / (1 + exp(-(t - t_half)/k))

    If rescue carbs dominate recovery, the trajectory should follow carb
    absorption kinetics (exponential saturation). If counter-regulatory
    response dominates, it may be more linear/gradual.
    """
    print("\n=== EXP-1641: Post-Nadir Trajectory Characterization ===")

    all_episodes = []
    per_patient = {}

    for p in patients:
        name = p['name']
        df, pk = p['df'], p['pk']
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)
        sd = compute_supply_demand(df, pk)

        episodes = find_hypo_episodes(glucose, carbs, iob, sd)
        if not episodes:
            continue

        linear_r2s, exp_r2s, logistic_r2s = [], [], []
        rise_rates, plateaus, taus = [], [], []
        announced_rates, unannounced_rates = [], []

        for ep in episodes:
            post_bg = ep['post_bg']
            nadir = ep['nadir_bg']
            valid = ~np.isnan(post_bg)
            if valid.sum() < 8:
                continue

            t = np.arange(len(post_bg))[valid].astype(float)
            bg = post_bg[valid]
            y = bg - nadir  # normalize to rise from nadir

            if len(t) < 4 or np.std(y) < 1:
                continue

            # Model 1: Linear
            try:
                p_lin = np.polyfit(t, y, 1)
                pred_lin = np.polyval(p_lin, t)
                ss_res = np.sum((y - pred_lin) ** 2)
                ss_tot = np.sum((y - y.mean()) ** 2)
                r2_lin = 1 - ss_res / ss_tot if ss_tot > 0 else 0
                linear_r2s.append(r2_lin)
                rise_rates.append(p_lin[0])
            except:
                r2_lin = float('nan')

            # Model 2: Exponential saturation: y = A × (1 - exp(-t/τ))
            try:
                def exp_model(t, A, tau):
                    return A * (1 - np.exp(-t / max(tau, 0.1)))
                popt, _ = optimize.curve_fit(exp_model, t, y,
                                             p0=[max(y), 6.0],
                                             bounds=([0, 0.5], [300, 60]),
                                             maxfev=2000)
                pred_exp = exp_model(t, *popt)
                ss_res = np.sum((y - pred_exp) ** 2)
                r2_exp = 1 - ss_res / ss_tot if ss_tot > 0 else 0
                exp_r2s.append(r2_exp)
                plateaus.append(popt[0])
                taus.append(popt[1])
            except:
                r2_exp = float('nan')

            # Model 3: Logistic: y = A / (1 + exp(-(t - t_half) / k))
            try:
                def logistic_model(t, A, t_half, k):
                    return A / (1 + np.exp(-(t - t_half) / max(k, 0.1)))
                popt_log, _ = optimize.curve_fit(logistic_model, t, y,
                                                  p0=[max(y), 6.0, 2.0],
                                                  bounds=([0, 0, 0.1], [300, 40, 20]),
                                                  maxfev=2000)
                pred_log = logistic_model(t, *popt_log)
                ss_res = np.sum((y - pred_log) ** 2)
                r2_log = 1 - ss_res / ss_tot if ss_tot > 0 else 0
                logistic_r2s.append(r2_log)
            except:
                r2_log = float('nan')

            # Separate by announced vs unannounced
            if ep['has_announced']:
                announced_rates.append(ep['recovery_rate_30'])
            else:
                unannounced_rates.append(ep['recovery_rate_30'])

            ep['r2_linear'] = r2_lin
            ep['r2_exp'] = r2_exp if not np.isnan(r2_exp) else None
            ep['r2_logistic'] = r2_log if not np.isnan(r2_log) else None
            all_episodes.append(ep)

        n_ep = len(episodes)
        per_patient[name] = {
            'n_episodes': n_ep,
            'linear_r2': float(np.nanmedian(linear_r2s)) if linear_r2s else None,
            'exp_r2': float(np.nanmedian(exp_r2s)) if exp_r2s else None,
            'logistic_r2': float(np.nanmedian(logistic_r2s)) if logistic_r2s else None,
            'median_rise_rate': float(np.nanmedian(rise_rates)) if rise_rates else None,
            'median_plateau': float(np.nanmedian(plateaus)) if plateaus else None,
            'median_tau': float(np.nanmedian(taus)) if taus else None,
            'n_announced': len(announced_rates),
            'n_unannounced': len(unannounced_rates),
        }

        if linear_r2s:
            print(f"  {name}: {n_ep} episodes, R² linear={np.nanmedian(linear_r2s):.3f} "
                  f"exp={np.nanmedian(exp_r2s):.3f} logistic={np.nanmedian(logistic_r2s):.3f} "
                  f"τ={np.nanmedian(taus):.1f} steps")

    # Population summary
    all_lin = [v['linear_r2'] for v in per_patient.values() if v['linear_r2'] is not None]
    all_exp = [v['exp_r2'] for v in per_patient.values() if v['exp_r2'] is not None]
    all_log = [v['logistic_r2'] for v in per_patient.values() if v['logistic_r2'] is not None]

    print(f"\n  Population median R²: linear={np.median(all_lin):.3f} "
          f"exp={np.median(all_exp):.3f} logistic={np.median(all_log):.3f}")
    best = ['linear', 'exponential', 'logistic'][np.argmax([np.median(all_lin), np.median(all_exp), np.median(all_log)])]
    print(f"  Best model: {best}")

    result = {
        'experiment': 'EXP-1641',
        'title': 'Post-Nadir Trajectory Characterization',
        'n_total_episodes': len(all_episodes),
        'population_r2': {
            'linear': float(np.median(all_lin)),
            'exponential': float(np.median(all_exp)),
            'logistic': float(np.median(all_log)),
        },
        'best_model': best,
        'per_patient': per_patient,
    }
    return result, all_episodes


# ── EXP-1642: Rescue Carb Onset Detection ─────────────────────────────

def exp_1642_onset_detection(all_episodes):
    """Determine how quickly we can detect rescue carb consumption.

    Approach: at each time point post-nadir (5, 10, 15, 20, 25, 30 min),
    classify episodes as "rescue consumed" vs "no rescue" using only the
    recovery rate up to that point.

    Ground truth: unannounced episodes with rebound > 40 mg/dL are labeled
    as 'rescue consumed'; episodes with rebound < 15 mg/dL as 'no rescue'.
    (This is an imperfect proxy but the best we have.)
    """
    print("\n=== EXP-1642: Rescue Carb Onset Detection ===")

    checkpoints = [2, 4, 6, 8, 10, 12]  # steps = 10, 20, 30, 40, 50, 60 min

    results_by_time = {}

    for cp in checkpoints:
        minutes = cp * 5
        features, labels = [], []

        for ep in all_episodes:
            post_bg = ep['post_bg']
            rebound = ep['rebound_mg']

            # Label: high rebound = rescue, low rebound = no rescue
            if rebound > 40:
                label = 1  # rescue consumed
            elif rebound < 15:
                label = 0  # no rescue (or minimal)
            else:
                continue  # ambiguous, skip

            # Feature: recovery rate at this checkpoint
            if cp >= len(post_bg):
                continue
            window = post_bg[:cp + 1]
            valid = ~np.isnan(window)
            if valid.sum() < 2:
                continue

            t = np.arange(len(window))[valid].astype(float)
            bg = window[valid]
            if len(t) < 2:
                continue

            # Rate of rise
            rate = (bg[-1] - bg[0]) / max(t[-1] - t[0], 1)
            # Total rise
            total_rise = bg[-1] - bg[0]
            # Acceleration (second derivative)
            if len(bg) >= 3:
                accel = (bg[-1] - 2 * bg[len(bg) // 2] + bg[0]) / max((t[-1] / 2) ** 2, 1)
            else:
                accel = 0

            features.append([rate, total_rise, accel])
            labels.append(label)

        features = np.array(features) if features else np.empty((0, 3))
        labels = np.array(labels)

        if len(labels) < 20 or labels.sum() < 5 or (1 - labels).sum() < 5:
            results_by_time[minutes] = {'n': len(labels), 'auc': None, 'accuracy': None}
            continue

        # Simple threshold classifier on total_rise
        total_rises = features[:, 1]
        # Find optimal threshold via AUC
        thresholds = np.percentile(total_rises, np.arange(5, 96, 5))
        best_acc, best_thresh = 0, 0

        for thresh in thresholds:
            pred = (total_rises >= thresh).astype(int)
            acc = np.mean(pred == labels)
            if acc > best_acc:
                best_acc = acc
                best_thresh = thresh

        # Compute AUC
        # Manual AUC via sorting
        sorted_idx = np.argsort(-total_rises)
        sorted_labels = labels[sorted_idx]
        n_pos = labels.sum()
        n_neg = len(labels) - n_pos
        tp, fp = 0, 0
        auc = 0.0
        for lab in sorted_labels:
            if lab == 1:
                tp += 1
            else:
                fp += 1
                auc += tp
        auc = auc / max(n_pos * n_neg, 1)

        results_by_time[minutes] = {
            'n': int(len(labels)),
            'n_rescue': int(labels.sum()),
            'n_no_rescue': int(len(labels) - labels.sum()),
            'auc': float(auc),
            'accuracy': float(best_acc),
            'threshold_mg': float(best_thresh),
        }
        print(f"  {minutes:2d} min: n={len(labels)} AUC={auc:.3f} acc={best_acc:.3f} "
              f"(threshold={best_thresh:.1f} mg/dL rise)")

    # Find minimum detection time
    first_good = None
    for cp in checkpoints:
        m = cp * 5
        r = results_by_time.get(m, {})
        if r.get('auc') and r['auc'] >= 0.75:
            first_good = m
            break

    print(f"\n  Earliest reliable detection (AUC≥0.75): {first_good} min" if first_good
          else "\n  No reliable detection point found")

    return {
        'experiment': 'EXP-1642',
        'title': 'Rescue Carb Onset Detection',
        'results_by_time': results_by_time,
        'earliest_detection_min': first_good,
    }


# ── EXP-1643: Magnitude Estimation ───────────────────────────────────

def exp_1643_magnitude_estimation(all_episodes, patients):
    """Estimate rescue carb magnitude from early glucose recovery.

    Use the residual trajectory (actual dBG/dt - model-predicted dBG/dt) to
    estimate grams of rescue carbs consumed. The residual captures everything
    the model doesn't explain — primarily rescue carbs + counter-regulatory.

    Approach:
      1. Compute cumulative residual in first 30/60/90 min post-nadir
      2. Convert to estimated grams using ISF/CR ratio
      3. Validate against episodes with announced carbs
    """
    print("\n=== EXP-1643: Rescue Carb Magnitude Estimation ===")

    # Build patient ISF/CR lookup
    patient_isf_cr = {}
    for p in patients:
        isf = _extract_isf_scalar(p['df'])
        cr_sched = p['df'].attrs.get('cr_schedule', [])
        if cr_sched:
            cr_vals = [e.get('value', e.get('carbratio', 10)) for e in cr_sched]
            cr = float(np.median(cr_vals))
        else:
            cr = 10.0
        patient_isf_cr[p['name']] = {'isf': isf, 'cr': cr, 'mg_per_g': isf / max(cr, 1)}

    horizons = [6, 12, 18]  # 30, 60, 90 min
    horizon_results = {}

    for h in horizons:
        minutes = h * 5
        estimates = []  # (estimated_g, announced_g, patient)
        unannounced_estimates = []

        for ep in all_episodes:
            residual = ep['residual']
            if h >= len(residual):
                continue

            # Cumulative residual = total unexplained glucose rise
            res_window = residual[1:h + 1]  # skip nadir itself
            valid = ~np.isnan(res_window)
            if valid.sum() < h // 2:
                continue

            cum_residual = float(np.nansum(res_window))  # mg/dL total

            # Convert mg/dL to estimated grams: grams = cum_residual / (ISF/CR)
            # ISF/CR = mg/dL rise per gram of carbs
            # We don't have patient name in episode; use population median
            mg_per_g = 5.0  # rough population estimate
            est_grams = max(cum_residual / mg_per_g, 0)

            if ep['has_announced'] and ep['announced_carbs'] > 0:
                estimates.append({
                    'estimated_g': est_grams,
                    'announced_g': ep['announced_carbs'],
                    'cum_residual': cum_residual,
                    'rebound_mg': ep['rebound_mg'],
                })
            else:
                unannounced_estimates.append({
                    'estimated_g': est_grams,
                    'cum_residual': cum_residual,
                    'rebound_mg': ep['rebound_mg'],
                })

        # Correlation with announced carbs (validation)
        if len(estimates) >= 10:
            est = np.array([e['estimated_g'] for e in estimates])
            ann = np.array([e['announced_g'] for e in estimates])
            r, p = stats.pearsonr(est, ann)
            ratio = float(np.median(est / np.maximum(ann, 1)))
        else:
            r, p, ratio = float('nan'), float('nan'), float('nan')

        # Unannounced statistics
        if unannounced_estimates:
            unanno_est = [e['estimated_g'] for e in unannounced_estimates]
            unanno_median = float(np.median(unanno_est))
            unanno_iqr = (float(np.percentile(unanno_est, 25)),
                          float(np.percentile(unanno_est, 75)))
        else:
            unanno_median = float('nan')
            unanno_iqr = (float('nan'), float('nan'))

        horizon_results[minutes] = {
            'n_announced': len(estimates),
            'n_unannounced': len(unannounced_estimates),
            'correlation_r': float(r),
            'correlation_p': float(p),
            'est_ann_ratio': ratio,
            'unannounced_median_g': unanno_median,
            'unannounced_iqr_g': unanno_iqr,
        }

        print(f"  {minutes} min horizon: r={r:.3f} (n_ann={len(estimates)}) "
              f"unanno median={unanno_median:.1f}g [{unanno_iqr[0]:.0f}-{unanno_iqr[1]:.0f}]")

    return {
        'experiment': 'EXP-1643',
        'title': 'Rescue Carb Magnitude Estimation',
        'horizons': horizon_results,
    }


# ── EXP-1644: Counter-Regulatory vs Rescue Decomposition ─────────────

def exp_1644_counterreg_decomposition(all_episodes):
    """Decompose post-nadir recovery into rescue carb vs counter-regulatory.

    Key insight: counter-regulatory response (glucagon, epinephrine, cortisol)
    starts BEFORE the nadir and has a characteristic time course:
    - Glucagon: rapid onset (minutes), peaks at 20-30 min, decays by 60 min
    - Epinephrine: similar to glucagon but more sustained
    - Cortisol: slow (30-60 min onset), lasts hours

    Rescue carbs follow absorption kinetics:
    - Fast carbs (juice, glucose tabs): onset 5-10 min, peak 15-30 min
    - Slower carbs: onset 15-20 min, peak 30-60 min

    We can separate them by looking at:
    1. Recovery that starts BEFORE any possible carb absorption (< 5 min) = counter-regulatory
    2. Recovery acceleration at 10-15 min = rescue carb bolus arriving
    3. Late sustained rise (> 60 min) = slower carb absorption + cortisol

    The approach: fit a two-component model:
      dBG/dt = CR_component(t) + rescue_component(t)
    where CR follows an exponential decay from nadir, and rescue follows
    an exponential saturation with a delay.
    """
    print("\n=== EXP-1644: Counter-Regulatory vs Rescue Decomposition ===")

    early_rates = []     # dBG/dt in first 5 min (mostly counter-regulatory)
    mid_rates = []       # dBG/dt at 10-20 min (rescue carbs arriving)
    late_rates = []      # dBG/dt at 30-60 min (sustained)
    acceleration_at_10 = []  # change in dBG/dt between 5-15 min

    per_severity = {'severe': [], 'moderate': [], 'mild': []}

    for ep in all_episodes:
        post_dbg = ep['post_dbg']
        nadir_bg = ep['nadir_bg']

        if len(post_dbg) < 13:  # need at least 60 min
            continue

        # Classify severity
        if nadir_bg < 54:
            severity = 'severe'
        elif nadir_bg < 60:
            severity = 'moderate'
        else:
            severity = 'mild'

        # Early recovery (0-5 min, steps 1-2): mostly counter-regulatory
        early = post_dbg[1:3]
        valid_early = ~np.isnan(early)
        if valid_early.sum() > 0:
            early_rate = float(np.nanmean(early))
            early_rates.append(early_rate)
        else:
            early_rate = float('nan')

        # Mid recovery (10-20 min, steps 3-5): rescue carbs arriving
        mid = post_dbg[3:5]
        valid_mid = ~np.isnan(mid)
        if valid_mid.sum() > 0:
            mid_rate = float(np.nanmean(mid))
            mid_rates.append(mid_rate)
        else:
            mid_rate = float('nan')

        # Late recovery (30-60 min, steps 7-13): sustained
        late = post_dbg[7:13]
        valid_late = ~np.isnan(late)
        if valid_late.sum() > 0:
            late_rate = float(np.nanmean(late))
            late_rates.append(late_rate)
        else:
            late_rate = float('nan')

        # Acceleration: mid rate - early rate = rescue carb bolus signal
        if not np.isnan(early_rate) and not np.isnan(mid_rate):
            accel = mid_rate - early_rate
            acceleration_at_10.append(accel)
            per_severity[severity].append({
                'early_rate': early_rate,
                'mid_rate': mid_rate,
                'late_rate': late_rate,
                'acceleration': accel,
                'rebound': ep['rebound_mg'],
                'nadir_bg': nadir_bg,
            })

    print(f"  Early rate (0-10min, counter-reg): {np.nanmean(early_rates):.2f} ± {np.nanstd(early_rates):.2f} mg/dL/step")
    print(f"  Mid rate (10-20min, rescue+CR):     {np.nanmean(mid_rates):.2f} ± {np.nanstd(mid_rates):.2f} mg/dL/step")
    print(f"  Late rate (30-60min, sustained):    {np.nanmean(late_rates):.2f} ± {np.nanstd(late_rates):.2f} mg/dL/step")
    print(f"  Acceleration at 10min:              {np.nanmean(acceleration_at_10):.2f} ± {np.nanstd(acceleration_at_10):.2f}")

    # The acceleration tells us if recovery SPEEDS UP (rescue carbs) or SLOWS DOWN (just CR)
    accel_positive = sum(1 for a in acceleration_at_10 if a > 0)
    accel_negative = sum(1 for a in acceleration_at_10 if a <= 0)
    print(f"  Acceleration positive (rescue signal): {accel_positive}/{len(acceleration_at_10)} "
          f"({100*accel_positive/max(len(acceleration_at_10),1):.0f}%)")

    # Counter-regulatory floor estimate: episodes where recovery < 15 mg/dL
    # (likely pure counter-regulatory, minimal rescue)
    low_rebound = [e for eps in per_severity.values() for e in eps if e['rebound'] < 15]
    if low_rebound:
        cr_floor = float(np.mean([e['early_rate'] for e in low_rebound]))
        print(f"  Counter-regulatory floor (rebound<15): {cr_floor:.2f} mg/dL/step ({cr_floor*12:.1f} mg/dL/h)")
    else:
        cr_floor = 0.5

    # By severity
    for sev in ['severe', 'moderate', 'mild']:
        eps = per_severity[sev]
        if not eps:
            continue
        print(f"  {sev:>10}: n={len(eps)} early={np.mean([e['early_rate'] for e in eps]):.2f} "
              f"mid={np.mean([e['mid_rate'] for e in eps]):.2f} "
              f"accel={np.mean([e['acceleration'] for e in eps]):.2f}")

    return {
        'experiment': 'EXP-1644',
        'title': 'Counter-Regulatory vs Rescue Decomposition',
        'early_rate_mean': float(np.nanmean(early_rates)),
        'mid_rate_mean': float(np.nanmean(mid_rates)),
        'late_rate_mean': float(np.nanmean(late_rates)),
        'acceleration_mean': float(np.nanmean(acceleration_at_10)),
        'pct_acceleration_positive': float(accel_positive / max(len(acceleration_at_10), 1)),
        'cr_floor_estimate': cr_floor,
        'per_severity': {
            sev: {
                'n': len(eps),
                'early': float(np.mean([e['early_rate'] for e in eps])) if eps else None,
                'mid': float(np.mean([e['mid_rate'] for e in eps])) if eps else None,
                'accel': float(np.mean([e['acceleration'] for e in eps])) if eps else None,
            }
            for sev, eps in per_severity.items()
        },
    }


# ── EXP-1645: Glycogen-Aware Rescue Model ────────────────────────────

def exp_1645_glycogen_rescue(all_episodes, patients):
    """Test whether glycogen proxy improves rescue carb inference.

    From EXP-1634: glycogen proxy survives deconfounding (39× β range).
    From EXP-1635: glycogen coefficient = 493 (strongest predictor).

    Here we test: does adding glycogen to a trajectory-based rescue model
    improve estimation of rebound magnitude and rescue carb size?
    """
    print("\n=== EXP-1645: Glycogen-Aware Rescue Model ===")

    # Collect features for each episode
    records = []

    for p in patients:
        name = p['name']
        df, pk = p['df'], p['pk']
        glucose = df['glucose'].values.astype(float)
        carbs_col = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        glyc = compute_glycogen_proxy(glucose, carbs_col, iob)
        sd = compute_supply_demand(df, pk)

        episodes = find_hypo_episodes(glucose, carbs_col, iob, sd)

        for ep in episodes:
            nidx = ep['nadir_idx']
            if np.isnan(glyc[nidx]):
                continue

            post_bg = ep['post_bg']
            # Early rise (first 15 min)
            early_bg = post_bg[:4]
            valid_e = ~np.isnan(early_bg)
            if valid_e.sum() < 2:
                continue
            early_rise = float(early_bg[valid_e][-1] - early_bg[valid_e][0])

            # Feature vector
            records.append({
                'patient': name,
                'nadir_bg': ep['nadir_bg'],
                'glycogen': float(glyc[nidx]),
                'pre_iob': ep['pre_iob'],
                'demand_at_nadir': ep['demand_at_nadir'],
                'supply_at_nadir': ep['supply_at_nadir'],
                'early_rise_15': early_rise,
                'recovery_rate_30': ep['recovery_rate_30'],
                'rebound_mg': ep['rebound_mg'],
                'announced_carbs': ep['announced_carbs'],
            })

    if len(records) < 50:
        print("  Insufficient episodes for regression")
        return {'experiment': 'EXP-1645', 'title': 'Glycogen-Aware Rescue', 'n': len(records)}

    # Convert to arrays
    X_base = np.array([[r['nadir_bg'], r['pre_iob'], r['early_rise_15'],
                         r['demand_at_nadir']] for r in records])
    X_glyc = np.array([[r['nadir_bg'], r['pre_iob'], r['early_rise_15'],
                         r['demand_at_nadir'], r['glycogen']] for r in records])
    y = np.array([r['rebound_mg'] for r in records])

    # Remove NaN rows
    valid = np.all(np.isfinite(X_glyc), axis=1) & np.isfinite(y)
    X_base, X_glyc, y = X_base[valid], X_glyc[valid], y[valid]

    if len(y) < 50:
        print("  Insufficient valid episodes after NaN removal")
        return {'experiment': 'EXP-1645', 'title': 'Glycogen-Aware Rescue', 'n': len(y)}

    # Linear regression: base model (no glycogen)
    X_base_aug = np.column_stack([np.ones(len(X_base)), X_base])
    try:
        beta_base = np.linalg.lstsq(X_base_aug, y, rcond=None)[0]
        pred_base = X_base_aug @ beta_base
        ss_res_base = np.sum((y - pred_base) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2_base = 1 - ss_res_base / ss_tot
    except:
        r2_base = float('nan')

    # Linear regression: with glycogen
    X_glyc_aug = np.column_stack([np.ones(len(X_glyc)), X_glyc])
    try:
        beta_glyc = np.linalg.lstsq(X_glyc_aug, y, rcond=None)[0]
        pred_glyc = X_glyc_aug @ beta_glyc
        ss_res_glyc = np.sum((y - pred_glyc) ** 2)
        r2_glyc = 1 - ss_res_glyc / ss_tot
    except:
        r2_glyc = float('nan')

    delta_r2 = r2_glyc - r2_base

    print(f"  n = {len(y)} episodes")
    print(f"  R² without glycogen: {r2_base:.4f}")
    print(f"  R² with glycogen:    {r2_glyc:.4f}")
    print(f"  Δ R² from glycogen:  {delta_r2:+.4f}")
    if not np.isnan(r2_glyc):
        print(f"  Glycogen coefficient: {beta_glyc[5]:.2f}")

    # Cross-patient consistency
    patient_deltas = {}
    for pname in set(r['patient'] for r in records):
        p_idx = np.array([i for i, r in enumerate(records) if r['patient'] == pname and valid[i]])
        if len(p_idx) < 20:
            continue
        # Map p_idx to positions in the valid arrays
        p_mask = np.zeros(len(y), dtype=bool)
        valid_idx = np.where(valid)[0]
        for idx in p_idx:
            pos = np.where(valid_idx == idx)[0]
            if len(pos):
                p_mask[pos[0]] = True
        if p_mask.sum() < 20:
            continue

        p_y = y[p_mask]
        p_ss_tot = np.sum((p_y - p_y.mean()) ** 2)
        if p_ss_tot < 1:
            continue
        p_r2_base = 1 - np.sum((p_y - pred_base[p_mask]) ** 2) / p_ss_tot
        p_r2_glyc = 1 - np.sum((p_y - pred_glyc[p_mask]) ** 2) / p_ss_tot
        patient_deltas[pname] = float(p_r2_glyc - p_r2_base)

    n_improved = sum(1 for d in patient_deltas.values() if d > 0)
    print(f"  Per-patient: {n_improved}/{len(patient_deltas)} improved with glycogen")

    return {
        'experiment': 'EXP-1645',
        'title': 'Glycogen-Aware Rescue Model',
        'n': int(len(y)),
        'r2_base': float(r2_base),
        'r2_with_glycogen': float(r2_glyc),
        'delta_r2': float(delta_r2),
        'glycogen_coefficient': float(beta_glyc[5]) if not np.isnan(r2_glyc) else None,
        'per_patient_delta': patient_deltas,
        'n_patients_improved': n_improved,
    }


# ── EXP-1646: Forecasting Improvement ────────────────────────────────

def exp_1646_forecast_improvement(all_episodes):
    """Test: does inferred rescue carb knowledge improve glucose forecasts?

    Compare three forecasting strategies during hypo recovery:
      1. Naive: BG(t+h) = BG(t) (persistence)
      2. Model-only: BG(t+h) = BG(t) + Σ net_flux (supply-demand model)
      3. Model + inferred rescue: BG(t+h) = BG(t) + Σ net_flux + rescue_rate × h

    The rescue rate is estimated from the first 10 minutes of recovery.
    Forecast horizons: 15, 30, 60 min.
    """
    print("\n=== EXP-1646: Forecasting Improvement ===")

    horizons = [3, 6, 12]  # 15, 30, 60 min
    estimation_window = 2  # use first 10 min to estimate rescue rate

    results = {}

    for h in horizons:
        minutes = h * 5
        naive_errors, model_errors, rescue_errors = [], [], []

        for ep in all_episodes:
            post_bg = ep['post_bg']
            post_net = ep['post_net']

            # Forecast from nadir + estimation_window
            forecast_origin = estimation_window
            forecast_target = forecast_origin + h

            if forecast_target >= len(post_bg):
                continue
            if np.isnan(post_bg[forecast_origin]) or np.isnan(post_bg[forecast_target]):
                continue

            actual = post_bg[forecast_target]
            origin_bg = post_bg[forecast_origin]

            # Strategy 1: Naive persistence
            naive_pred = origin_bg
            naive_errors.append(actual - naive_pred)

            # Strategy 2: Model-only
            net_sum = 0
            valid_net = True
            for k in range(forecast_origin, forecast_target):
                if k < len(post_net) and np.isfinite(post_net[k]):
                    net_sum += post_net[k]
                else:
                    valid_net = False
                    break
            if valid_net:
                model_pred = origin_bg + net_sum
                model_errors.append(actual - model_pred)

            # Strategy 3: Model + inferred rescue rate
            # Estimate rescue rate from first estimation_window steps
            early_bg = post_bg[:forecast_origin + 1]
            valid_early = ~np.isnan(early_bg)
            if valid_early.sum() >= 2:
                t_e = np.arange(len(early_bg))[valid_early]
                bg_e = early_bg[valid_early]
                rescue_rate = (bg_e[-1] - bg_e[0]) / max(t_e[-1] - t_e[0], 1)
                # Subtract model-predicted rate to isolate rescue component
                model_rate = np.nanmean(post_net[:forecast_origin + 1])
                inferred_rescue_rate = max(rescue_rate - model_rate, 0)
                rescue_pred = origin_bg + net_sum + inferred_rescue_rate * h
                rescue_errors.append(actual - rescue_pred)

        # Compute metrics
        def metrics(errors):
            if not errors:
                return {'mae': float('nan'), 'rmse': float('nan'), 'bias': float('nan'), 'n': 0}
            e = np.array(errors)
            return {
                'mae': float(np.mean(np.abs(e))),
                'rmse': float(np.sqrt(np.mean(e ** 2))),
                'bias': float(np.mean(e)),
                'n': len(e),
            }

        r = {
            'naive': metrics(naive_errors),
            'model': metrics(model_errors),
            'rescue': metrics(rescue_errors),
        }
        results[minutes] = r

        print(f"  {minutes:2d} min: naive MAE={r['naive']['mae']:.1f}  "
              f"model MAE={r['model']['mae']:.1f}  "
              f"rescue MAE={r['rescue']['mae']:.1f} mg/dL")

    # Summary: relative improvement
    print(f"\n  Relative improvement over naive:")
    for h in horizons:
        m = h * 5
        r = results[m]
        if r['naive']['mae'] > 0 and r['rescue']['mae'] > 0:
            improvement = (r['naive']['mae'] - r['rescue']['mae']) / r['naive']['mae'] * 100
            print(f"    {m} min: {improvement:+.1f}%")

    return {
        'experiment': 'EXP-1646',
        'title': 'Forecasting Improvement with Inferred Rescue',
        'results': results,
    }


# ── EXP-1647: Cross-Patient Rescue Consistency ───────────────────────

def exp_1647_cross_patient(patients):
    """Test: are rescue carb behaviors consistent enough for a universal model?

    Train a rescue magnitude model on N-1 patients, test on the held-out one.
    If rescue behavior is patient-specific, cross-patient transfer will fail.
    If universal, it should work across patients.
    """
    print("\n=== EXP-1647: Cross-Patient Rescue Consistency ===")

    # Collect all episodes with features per patient
    patient_data = {}
    for p in patients:
        name = p['name']
        df, pk = p['df'], p['pk']
        glucose = df['glucose'].values.astype(float)
        carbs_col = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)
        sd = compute_supply_demand(df, pk)

        episodes = find_hypo_episodes(glucose, carbs_col, iob, sd)
        if len(episodes) < 10:
            continue

        X, y = [], []
        for ep in episodes:
            if np.isnan(ep['recovery_rate_30']) or np.isnan(ep['pre_iob']):
                continue
            X.append([ep['nadir_bg'], ep['pre_iob'], ep['recovery_rate_30'],
                      ep['supply_at_nadir']])
            y.append(ep['rebound_mg'])

        if len(X) >= 10:
            patient_data[name] = {'X': np.array(X), 'y': np.array(y)}

    if len(patient_data) < 3:
        print("  Insufficient patients for LOPO")
        return {'experiment': 'EXP-1647', 'title': 'Cross-Patient Consistency', 'n_patients': len(patient_data)}

    # Leave-one-patient-out cross-validation
    lopo_results = {}
    for test_name in patient_data:
        # Train on all others
        X_train = np.vstack([v['X'] for k, v in patient_data.items() if k != test_name])
        y_train = np.concatenate([v['y'] for k, v in patient_data.items() if k != test_name])
        X_test = patient_data[test_name]['X']
        y_test = patient_data[test_name]['y']

        # Add intercept
        X_tr_aug = np.column_stack([np.ones(len(X_train)), X_train])
        X_te_aug = np.column_stack([np.ones(len(X_test)), X_test])

        try:
            beta = np.linalg.lstsq(X_tr_aug, y_train, rcond=None)[0]
            pred = X_te_aug @ beta
            ss_res = np.sum((y_test - pred) ** 2)
            ss_tot = np.sum((y_test - y_test.mean()) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        except:
            r2 = float('nan')

        lopo_results[test_name] = {
            'r2': float(r2),
            'n_train': int(len(y_train)),
            'n_test': int(len(y_test)),
        }
        print(f"  {test_name}: R²={r2:.3f} (train={len(y_train)}, test={len(y_test)})")

    # Summary
    r2s = [v['r2'] for v in lopo_results.values() if not np.isnan(v['r2'])]
    mean_r2 = float(np.mean(r2s)) if r2s else float('nan')
    n_positive = sum(1 for r in r2s if r > 0)

    print(f"\n  LOPO mean R²: {mean_r2:.3f}")
    print(f"  Patients with positive R²: {n_positive}/{len(r2s)}")
    transferable = mean_r2 > 0 and n_positive > len(r2s) // 2

    print(f"  Cross-patient transfer {'SUCCEEDS' if transferable else 'FAILS'}")

    return {
        'experiment': 'EXP-1647',
        'title': 'Cross-Patient Rescue Consistency',
        'lopo_results': lopo_results,
        'mean_r2': mean_r2,
        'n_positive': n_positive,
        'transferable': transferable,
    }


# ── EXP-1648: Practical Real-Time Detector ───────────────────────────

def exp_1648_realtime_detector(all_episodes):
    """Simulate a practical real-time rescue carb detector.

    Operating scenario: patient's glucose drops below 70 mg/dL. The system
    monitors the glucose trajectory and attempts to:
    1. Detect whether rescue carbs were consumed (binary)
    2. Estimate magnitude (grams)
    3. Alert if rebound will exceed 180 mg/dL (hyperglycemia)

    Performance metrics:
    - Detection latency (time to first correct classification)
    - False positive rate (declared rescue when none)
    - Rebound prediction accuracy
    """
    print("\n=== EXP-1648: Practical Real-Time Detector ===")

    # Binary classification at each checkpoint
    checkpoints_min = [10, 15, 20, 30]
    checkpoints = [m // 5 for m in checkpoints_min]

    # Define ground truth bins
    # Heavy rescue: rebound > 80 mg/dL (likely >30g carbs)
    # Standard rescue: 30 < rebound < 80 (likely 15-30g)
    # Minimal/none: rebound < 30

    for cp_min, cp in zip(checkpoints_min, checkpoints):
        tp, fp, tn, fn = 0, 0, 0, 0
        rebound_preds, rebound_actuals = [], []

        for ep in all_episodes:
            post_bg = ep['post_bg']
            if cp + 1 >= len(post_bg):
                continue
            if np.isnan(post_bg[0]) or np.isnan(post_bg[cp]):
                continue

            # Feature: rise at checkpoint
            rise = post_bg[cp] - post_bg[0]
            rate = rise / max(cp, 1)

            # Prediction: "rescue consumed" if rise > 5 mg/dL
            pred_rescue = rise > 5

            # Ground truth
            actual_rescue = ep['rebound_mg'] > 30

            if pred_rescue and actual_rescue: tp += 1
            elif pred_rescue and not actual_rescue: fp += 1
            elif not pred_rescue and actual_rescue: fn += 1
            else: tn += 1

            # Rebound prediction: simple linear extrapolation
            if rate > 0:
                # Predict rebound = observed rise + rate × remaining time
                remaining = 24 - cp  # total 2h window
                pred_rebound = rise + rate * remaining * 0.5  # decelerating
                rebound_preds.append(pred_rebound)
                rebound_actuals.append(ep['rebound_mg'])

        n_total = tp + fp + tn + fn
        if n_total == 0:
            continue

        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-6)
        accuracy = (tp + tn) / n_total

        # Rebound prediction correlation
        if len(rebound_preds) >= 10:
            r, _ = stats.pearsonr(rebound_preds, rebound_actuals)
            reb_mae = float(np.mean(np.abs(np.array(rebound_preds) - np.array(rebound_actuals))))
        else:
            r = float('nan')
            reb_mae = float('nan')

        print(f"  {cp_min:2d} min: acc={accuracy:.3f} prec={precision:.3f} rec={recall:.3f} "
              f"F1={f1:.3f} | rebound r={r:.3f} MAE={reb_mae:.1f} mg/dL")

    # Hyperglycemia alert: predict if rebound will exceed 180
    print(f"\n  Hyperglycemia alert (rebound > 110 mg/dL from nadir):")
    hyper_episodes = [e for e in all_episodes if e['rebound_mg'] > 110]
    non_hyper = [e for e in all_episodes if e['rebound_mg'] <= 110]
    print(f"  {len(hyper_episodes)}/{len(all_episodes)} episodes cause post-hypo hyperglycemia "
          f"({100*len(hyper_episodes)/max(len(all_episodes),1):.0f}%)")

    if hyper_episodes:
        hyper_rates = [e['recovery_rate_30'] for e in hyper_episodes if not np.isnan(e['recovery_rate_30'])]
        non_rates = [e['recovery_rate_30'] for e in non_hyper if not np.isnan(e['recovery_rate_30'])]
        if hyper_rates and non_rates:
            t_stat, p_val = stats.mannwhitneyu(hyper_rates, non_rates, alternative='greater')
            print(f"  Hyper recovery rate: {np.mean(hyper_rates):.2f} vs non-hyper: {np.mean(non_rates):.2f} "
                  f"(p={p_val:.2e})")

    return {
        'experiment': 'EXP-1648',
        'title': 'Practical Real-Time Detector',
        'n_episodes': len(all_episodes),
        'n_hyper_rebound': len(hyper_episodes),
        'pct_hyper': float(len(hyper_episodes) / max(len(all_episodes), 1)),
    }


# ── Visualization ────────────────────────────────────────────────────

def generate_figures(results, all_episodes, save_dir):
    """Generate 6 figures for the rescue carb inference report."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(save_dir, exist_ok=True)

    # Fig 1: Population mean post-nadir trajectory with model fits
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: mean trajectory with confidence bands
    ax = axes[0]
    max_steps = 24  # 2h
    all_traces = []
    for ep in all_episodes:
        post_bg = ep['post_bg']
        nadir = ep['nadir_bg']
        trace = np.full(max_steps, np.nan)
        for k in range(min(len(post_bg), max_steps)):
            if not np.isnan(post_bg[k]):
                trace[k] = post_bg[k] - nadir  # normalize to rise
        all_traces.append(trace)

    traces = np.array(all_traces)
    t_min = np.arange(max_steps) * 5

    mean_trace = np.nanmean(traces, axis=0)
    p25 = np.nanpercentile(traces, 25, axis=0)
    p75 = np.nanpercentile(traces, 75, axis=0)

    ax.fill_between(t_min, p25, p75, alpha=0.3, color='steelblue', label='IQR')
    ax.plot(t_min, mean_trace, 'b-', linewidth=2, label='Mean recovery')

    # Fit exponential saturation to mean
    valid_m = ~np.isnan(mean_trace)
    t_fit = t_min[valid_m] / 5.0  # in steps
    y_fit = mean_trace[valid_m]
    try:
        def exp_sat(t, A, tau):
            return A * (1 - np.exp(-t / max(tau, 0.1)))
        popt, _ = optimize.curve_fit(exp_sat, t_fit, y_fit, p0=[80, 6], bounds=([0, 0.5], [200, 60]))
        ax.plot(t_min, exp_sat(t_min / 5.0, *popt), 'r--', linewidth=2,
                label=f'Exp fit: A={popt[0]:.0f}, τ={popt[1]*5:.0f}min')
    except:
        pass

    ax.axhline(0, color='gray', linestyle=':', alpha=0.5)
    ax.set_xlabel('Minutes after nadir')
    ax.set_ylabel('Glucose rise from nadir (mg/dL)')
    ax.set_title(f'Post-Nadir Recovery Trajectory (n={len(all_episodes)})')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # Right: announced vs unannounced comparison
    ax = axes[1]
    announced = [ep for ep in all_episodes if ep['has_announced']]
    unannounced = [ep for ep in all_episodes if not ep['has_announced']]

    for label, subset, color in [('Announced carbs', announced, 'green'),
                                   ('Unannounced', unannounced, 'red')]:
        traces_sub = []
        for ep in subset:
            post_bg = ep['post_bg']
            nadir = ep['nadir_bg']
            trace = np.full(max_steps, np.nan)
            for k in range(min(len(post_bg), max_steps)):
                if not np.isnan(post_bg[k]):
                    trace[k] = post_bg[k] - nadir
            traces_sub.append(trace)
        if traces_sub:
            m = np.nanmean(traces_sub, axis=0)
            ax.plot(t_min, m, linewidth=2, color=color, label=f'{label} (n={len(subset)})')

    ax.axhline(0, color='gray', linestyle=':', alpha=0.5)
    ax.set_xlabel('Minutes after nadir')
    ax.set_ylabel('Glucose rise from nadir (mg/dL)')
    ax.set_title('Announced vs Unannounced Recovery')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, 'rescue-fig1-trajectory.png'), dpi=150)
    plt.close()
    print("  Saved fig1")

    # Fig 2: Onset detection AUC over time
    r1642 = results.get('EXP-1642', {})
    rbt = r1642.get('results_by_time', {})
    if rbt:
        fig, ax = plt.subplots(figsize=(8, 5))
        times = sorted(rbt.keys())
        aucs = [rbt[t].get('auc', float('nan')) for t in times]
        accs = [rbt[t].get('accuracy', float('nan')) for t in times]

        ax.plot(times, aucs, 'bo-', linewidth=2, markersize=8, label='AUC')
        ax.plot(times, accs, 'rs--', linewidth=2, markersize=8, label='Accuracy')
        ax.axhline(0.75, color='green', linestyle=':', alpha=0.7, label='AUC=0.75 threshold')
        ax.axhline(0.5, color='gray', linestyle=':', alpha=0.5)

        ax.set_xlabel('Minutes after nadir')
        ax.set_ylabel('Score')
        ax.set_title('Rescue Carb Detection Performance vs Time')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_ylim(0.3, 1.0)

        plt.tight_layout()
        plt.savefig(os.path.join(save_dir, 'rescue-fig2-onset-detection.png'), dpi=150)
        plt.close()
        print("  Saved fig2")

    # Fig 3: Counter-regulatory decomposition (early/mid/late rates)
    r1644 = results.get('EXP-1644', {})
    if r1644 and 'per_severity' in r1644:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Left: rate by time window
        ax = axes[0]
        phases = ['0-10 min\n(Counter-reg)', '10-20 min\n(Rescue arriving)', '30-60 min\n(Sustained)']
        rates = [r1644.get('early_rate_mean', 0), r1644.get('mid_rate_mean', 0), r1644.get('late_rate_mean', 0)]
        colors = ['#2196F3', '#FF9800', '#4CAF50']
        ax.bar(phases, rates, color=colors, edgecolor='black', alpha=0.8)
        ax.set_ylabel('Recovery rate (mg/dL per 5-min step)')
        ax.set_title('Recovery Rate by Phase')
        ax.grid(True, alpha=0.3, axis='y')

        # Right: by severity
        ax = axes[1]
        sev_data = r1644.get('per_severity', {})
        x = np.arange(3)
        width = 0.25
        for i, (sev, color) in enumerate(zip(['severe', 'moderate', 'mild'],
                                              ['#D32F2F', '#FF9800', '#4CAF50'])):
            sd = sev_data.get(sev, {})
            vals = [sd.get('early', 0) or 0, sd.get('mid', 0) or 0, sd.get('accel', 0) or 0]
            ax.bar(x + i * width, vals, width, label=f'{sev} (n={sd.get("n", 0)})',
                   color=color, alpha=0.8)

        ax.set_xticks(x + width)
        ax.set_xticklabels(['Early rate', 'Mid rate', 'Acceleration'])
        ax.set_ylabel('mg/dL per step')
        ax.set_title('Recovery Dynamics by Severity')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(os.path.join(save_dir, 'rescue-fig3-counterreg.png'), dpi=150)
        plt.close()
        print("  Saved fig3")

    # Fig 4: Forecast improvement
    r1646 = results.get('EXP-1646', {})
    if r1646 and 'results' in r1646:
        fig, ax = plt.subplots(figsize=(8, 5))
        horizons_m = sorted(r1646['results'].keys())
        naive_mae = [r1646['results'][h]['naive']['mae'] for h in horizons_m]
        model_mae = [r1646['results'][h]['model']['mae'] for h in horizons_m]
        rescue_mae = [r1646['results'][h]['rescue']['mae'] for h in horizons_m]

        x = np.arange(len(horizons_m))
        width = 0.25
        ax.bar(x - width, naive_mae, width, label='Naive (persistence)', color='#9E9E9E', alpha=0.8)
        ax.bar(x, model_mae, width, label='S×D model only', color='#2196F3', alpha=0.8)
        ax.bar(x + width, rescue_mae, width, label='Model + inferred rescue', color='#4CAF50', alpha=0.8)

        ax.set_xticks(x)
        ax.set_xticklabels([f'{h} min' for h in horizons_m])
        ax.set_ylabel('MAE (mg/dL)')
        ax.set_title('Glucose Forecast Error During Hypo Recovery')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(os.path.join(save_dir, 'rescue-fig4-forecast.png'), dpi=150)
        plt.close()
        print("  Saved fig4")

    # Fig 5: Cross-patient LOPO R²
    r1647 = results.get('EXP-1647', {})
    if r1647 and 'lopo_results' in r1647:
        fig, ax = plt.subplots(figsize=(8, 5))
        names = sorted(r1647['lopo_results'].keys())
        r2s = [r1647['lopo_results'][n]['r2'] for n in names]
        colors = ['#4CAF50' if r > 0 else '#D32F2F' for r in r2s]

        ax.bar(names, r2s, color=colors, edgecolor='black', alpha=0.8)
        ax.axhline(0, color='black', linewidth=1)
        ax.set_ylabel('R² (leave-one-patient-out)')
        ax.set_title('Cross-Patient Rescue Carb Model Transfer')
        ax.grid(True, alpha=0.3, axis='y')
        mean_r2 = r1647.get('mean_r2', 0)
        ax.axhline(mean_r2, color='blue', linestyle='--', label=f'Mean R²={mean_r2:.3f}')
        ax.legend()

        plt.tight_layout()
        plt.savefig(os.path.join(save_dir, 'rescue-fig5-cross-patient.png'), dpi=150)
        plt.close()
        print("  Saved fig5")

    # Fig 6: Rebound magnitude distribution + hyper risk
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    rebounds = [ep['rebound_mg'] for ep in all_episodes]
    ax.hist(rebounds, bins=40, color='steelblue', edgecolor='black', alpha=0.8)
    ax.axvline(110, color='red', linestyle='--', linewidth=2, label='Hyper risk (>110 mg/dL rise)')
    ax.axvline(30, color='orange', linestyle='--', linewidth=1.5, label='Standard rescue (30)')
    ax.set_xlabel('Rebound magnitude (mg/dL)')
    ax.set_ylabel('Count')
    ax.set_title('Post-Hypo Rebound Distribution')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # Right: rebound vs nadir depth
    ax = axes[1]
    nadirs = [ep['nadir_bg'] for ep in all_episodes]
    ax.scatter(nadirs, rebounds, alpha=0.3, s=10, c='steelblue')
    ax.set_xlabel('Nadir BG (mg/dL)')
    ax.set_ylabel('Rebound magnitude (mg/dL)')
    ax.set_title('Rebound vs Hypo Severity')
    ax.axhline(110, color='red', linestyle='--', alpha=0.7)
    ax.axvline(54, color='orange', linestyle='--', alpha=0.7, label='Severe (<54)')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(save_dir, 'rescue-fig6-rebound.png'), dpi=150)
    plt.close()
    print("  Saved fig6")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-1641–1648: Rescue carb inference')
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    parser.add_argument('--patient', type=str, default=None, help='Single patient filter')
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients(PATIENTS_DIR, patient_filter=args.patient)
    print(f"Loaded {len(patients)} patients")

    # EXP-1641: Trajectory characterization
    r1641, all_episodes = exp_1641_trajectory_characterization(patients)

    print(f"\n  Total episodes across all patients: {len(all_episodes)}")

    # EXP-1642: Onset detection
    r1642 = exp_1642_onset_detection(all_episodes)

    # EXP-1643: Magnitude estimation
    r1643 = exp_1643_magnitude_estimation(all_episodes, patients)

    # EXP-1644: Counter-regulatory decomposition
    r1644 = exp_1644_counterreg_decomposition(all_episodes)

    # EXP-1645: Glycogen-aware rescue model
    r1645 = exp_1645_glycogen_rescue(all_episodes, patients)

    # EXP-1646: Forecasting improvement
    r1646 = exp_1646_forecast_improvement(all_episodes)

    # EXP-1647: Cross-patient consistency
    r1647 = exp_1647_cross_patient(patients)

    # EXP-1648: Real-time detector
    r1648 = exp_1648_realtime_detector(all_episodes)

    # Save results
    os.makedirs(RESULTS_DIR, exist_ok=True)
    results = {
        'EXP-1641': r1641, 'EXP-1642': r1642, 'EXP-1643': r1643,
        'EXP-1644': r1644, 'EXP-1645': r1645, 'EXP-1646': r1646,
        'EXP-1647': r1647, 'EXP-1648': r1648,
    }

    for exp_id, data in results.items():
        fname = f"exp-{exp_id.split('-')[1]}_rescue_inference.json"
        with open(RESULTS_DIR / fname, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    print(f"\nSaved {len(results)} experiment JSONs")

    if args.figures:
        print("\nGenerating figures...")
        generate_figures(results, all_episodes, FIGURES_DIR)

    # Summary
    print(f"""
======================================================================
SUMMARY
======================================================================
  Total hypo episodes: {len(all_episodes)}
  Best trajectory model: {r1641.get('best_model', '?')}
  Earliest detection: {r1642.get('earliest_detection_min', '?')} min (AUC≥0.75)
  Counter-regulatory floor: {r1644.get('cr_floor_estimate', '?'):.2f} mg/dL/step
  Glycogen Δ R²: {r1645.get('delta_r2', '?')}
  Cross-patient transfer: {'YES' if r1647.get('transferable') else 'NO'}
  Post-hypo hyperglycemia rate: {r1648.get('pct_hyper', 0)*100:.0f}%
""")


if __name__ == '__main__':
    main()
