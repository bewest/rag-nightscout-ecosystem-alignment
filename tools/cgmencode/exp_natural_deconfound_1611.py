#!/usr/bin/env python3
"""EXP-1611 through EXP-1616: Natural-Experiment Deconfounding via Supply-Demand.

Uses natural experiment windows as "controlled contexts" to separate confounded
effects in the supply-demand metabolic model. The key insight: different natural
experiment types hold different metabolic factors approximately constant, allowing
us to calibrate individual model components independently.

Strategy:
  FASTING windows:    carb_supply ≈ 0, low insulin → isolate hepatic error
  CORRECTION windows: carb_supply ≈ 0, known bolus → isolate insulin sensitivity error
  MEAL windows:       known carbs, mixed insulin → test calibrated model
  OVERNIGHT windows:  carb_supply ≈ 0, circadian baseline → validate basal + dawn
  STABLE windows:     low variability → baseline reference

Supply-demand decomposition:
  SUPPLY(t) = hepatic_modeled(t) + carb_modeled(t)
  DEMAND(t) = insulin_modeled(t)
  dBG/dt ≈ SUPPLY - DEMAND + ε(t)

Context-calibrated decomposition:
  ε_fasting    ≈ hepatic_error + basal_demand_error
  ε_correction ≈ hepatic_error + sensitivity_error
  ε_meal       ≈ hepatic_error + sensitivity_error + carb_model_error

By calibrating hepatic from fasting, then sensitivity from corrections,
the remaining meal residual is attributable to carb model error.

EXP-1611: Cross-context residual profiles (prove structure exists)
EXP-1612: Hepatic calibration from fasting windows
EXP-1613: Sensitivity calibration from correction windows
EXP-1614: Cross-validation on meal windows (does calibration help?)
EXP-1615: Temporal convergence (how much data is needed?)
EXP-1616: Therapy assessment with calibrated model

References:
  - exp_metabolic_441.py: compute_supply_demand() — core decomposition
  - exp_hypo_supply_demand_1601.py: hypo-specific decomposition showing
    opposing errors in hepatic (+) and sensitivity (-) that cancel
  - exp_clinical_1551.py: Natural experiment census (50,810 windows)
  - exp_clinical_1291.py: Therapy assessment with preconditions
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

warnings.filterwarnings('ignore', category=RuntimeWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_metabolic_441 import compute_supply_demand

# ── Constants ──────────────────────────────────────────────────────────

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

# Natural experiment detection thresholds
FASTING_MIN_STEPS = 36          # 3 hours
FASTING_CARB_THRESH = 1.0       # < 1g carbs
FASTING_BOLUS_THRESH = 0.1      # < 0.1U bolus

CORRECTION_MIN_BOLUS = 0.5      # ≥ 0.5U
CORRECTION_CARB_WINDOW = 6      # ±30 min no carbs
CORRECTION_BG_THRESH = 150      # start BG ≥ 150 mg/dL
CORRECTION_MIN_STEPS = 24       # 2h observation minimum

MEAL_MIN_CARBS = 5.0            # ≥ 5g
MEAL_OBSERVE_STEPS = 36         # 3h post-meal

OVERNIGHT_START = 0             # midnight
OVERNIGHT_END = 6               # 6 AM

STABLE_MIN_STEPS = 24           # 2h minimum
STABLE_MAX_CV = 5.0             # CV < 5%

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'
FIGURES_DIR = Path(__file__).parent.parent.parent / 'docs' / '60-research' / 'figures'


# ── Natural experiment detection ───────────────────────────────────────

def _extract_runs(mask, min_length=1):
    """Extract contiguous True runs from boolean mask."""
    runs = []
    in_run = False
    start = 0
    for i in range(len(mask)):
        if mask[i] and not in_run:
            in_run = True
            start = i
        elif not mask[i] and in_run:
            in_run = False
            if i - start >= min_length:
                runs.append((start, i))
    if in_run and len(mask) - start >= min_length:
        runs.append((start, len(mask)))
    return runs


def detect_fasting_windows(glucose, bolus, carbs, hours):
    """Detect fasting windows: ≥3h no carbs, no bolus, valid CGM."""
    N = len(glucose)
    mask = np.ones(N, dtype=bool)
    for i in range(N):
        if np.isnan(glucose[i]):
            mask[i] = False
        elif carbs[i] > FASTING_CARB_THRESH:
            mask[max(0, i - FASTING_MIN_STEPS):i + FASTING_MIN_STEPS] = False
        elif bolus[i] > FASTING_BOLUS_THRESH:
            mask[max(0, i - FASTING_MIN_STEPS):i + FASTING_MIN_STEPS] = False

    windows = []
    for start, end in _extract_runs(mask, FASTING_MIN_STEPS):
        bg_seg = glucose[start:end]
        valid = ~np.isnan(bg_seg)
        if valid.sum() < FASTING_MIN_STEPS:
            continue
        mean_bg = float(np.nanmean(bg_seg))
        cv = float(np.nanstd(bg_seg) / max(mean_bg, 1) * 100)
        drift = float((bg_seg[valid][-1] - bg_seg[valid][0]) /
                       ((end - start) / STEPS_PER_HOUR)) if valid.sum() >= 2 else 0
        mean_hour = float(np.mean(hours[start:end]) % 24)
        is_overnight = (mean_hour >= 22 or mean_hour < 6)
        windows.append({
            'type': 'fasting',
            'start': int(start), 'end': int(end),
            'duration_steps': end - start,
            'mean_bg': mean_bg, 'cv': cv,
            'drift_mg_dl_h': drift,
            'mean_hour': mean_hour,
            'is_overnight': is_overnight,
        })
    return windows


def detect_correction_windows(glucose, bolus, carbs, hours):
    """Detect correction windows: isolated bolus ≥0.5U, no carbs, BG ≥150."""
    N = len(glucose)
    windows = []
    for i in range(CORRECTION_CARB_WINDOW, N - CORRECTION_MIN_STEPS):
        if bolus[i] < CORRECTION_MIN_BOLUS:
            continue
        if np.isnan(glucose[i]) or glucose[i] < CORRECTION_BG_THRESH:
            continue
        # Check no carbs in ±30 min window
        carb_window = carbs[max(0, i - CORRECTION_CARB_WINDOW):
                            min(N, i + CORRECTION_CARB_WINDOW + 1)]
        if np.any(carb_window > FASTING_CARB_THRESH):
            continue
        # Check no other boluses in ±30 min
        bolus_window = bolus[max(0, i - CORRECTION_CARB_WINDOW):
                             min(N, i + CORRECTION_CARB_WINDOW + 1)]
        bolus_window_copy = bolus_window.copy()
        bolus_window_copy[min(CORRECTION_CARB_WINDOW, i)] = 0
        if np.any(bolus_window_copy > FASTING_BOLUS_THRESH):
            continue

        end = min(i + CORRECTION_MIN_STEPS, N)
        bg_seg = glucose[i:end]
        valid = ~np.isnan(bg_seg)
        if valid.sum() < 12:
            continue
        nadir_idx = np.nanargmin(bg_seg)
        windows.append({
            'type': 'correction',
            'start': int(i), 'end': int(end),
            'duration_steps': end - i,
            'bolus_u': float(bolus[i]),
            'start_bg': float(glucose[i]),
            'nadir_bg': float(np.nanmin(bg_seg)),
            'delta_bg': float(glucose[i] - np.nanmin(bg_seg)),
            'mean_hour': float(hours[i] % 24),
        })
    return windows


def detect_meal_windows(glucose, bolus, carbs, hours):
    """Detect meal windows: ≥5g carbs with 3h observation."""
    N = len(glucose)
    windows = []
    i = 0
    while i < N - MEAL_OBSERVE_STEPS:
        if carbs[i] < MEAL_MIN_CARBS:
            i += 1
            continue
        # Cluster carb entries within 30 min
        total_carbs = float(carbs[i])
        total_bolus = float(bolus[i])
        end_cluster = i + 1
        while end_cluster < min(i + CORRECTION_CARB_WINDOW, N):
            total_carbs += carbs[end_cluster]
            total_bolus += bolus[end_cluster]
            end_cluster += 1

        obs_end = min(i + MEAL_OBSERVE_STEPS, N)
        bg_seg = glucose[i:obs_end]
        valid = ~np.isnan(bg_seg)
        if valid.sum() < 12:
            i = end_cluster
            continue

        pre_bg = float(glucose[i]) if not np.isnan(glucose[i]) else float(np.nanmean(bg_seg[:3]))
        peak_bg = float(np.nanmax(bg_seg))
        peak_idx = int(np.nanargmax(bg_seg))
        excursion = peak_bg - pre_bg

        windows.append({
            'type': 'meal',
            'start': int(i), 'end': int(obs_end),
            'duration_steps': obs_end - i,
            'total_carbs': total_carbs,
            'total_bolus': total_bolus,
            'pre_bg': pre_bg,
            'peak_bg': peak_bg,
            'excursion': excursion,
            'peak_time_min': peak_idx * 5,
            'mean_hour': float(hours[i] % 24),
        })
        i = end_cluster + MEAL_OBSERVE_STEPS  # skip overlap
    return windows


def detect_overnight_windows(glucose, bolus, carbs, hours):
    """Detect overnight windows: 0-6 AM with fasting."""
    N = len(glucose)
    # Find contiguous overnight segments
    overnight_mask = np.zeros(N, dtype=bool)
    for i in range(N):
        h = hours[i] % 24
        if OVERNIGHT_START <= h < OVERNIGHT_END:
            if not np.isnan(glucose[i]):
                overnight_mask[i] = True
    # Require fasting during overnight
    for i in range(N):
        if overnight_mask[i]:
            if carbs[i] > FASTING_CARB_THRESH or bolus[i] > FASTING_BOLUS_THRESH:
                # Invalidate 1h around any food/bolus event
                overnight_mask[max(0, i - 12):min(N, i + 12)] = False

    windows = []
    for start, end in _extract_runs(overnight_mask, 12):  # min 1h
        bg_seg = glucose[start:end]
        valid = ~np.isnan(bg_seg)
        if valid.sum() < 12:
            continue
        mean_bg = float(np.nanmean(bg_seg))
        drift = float((bg_seg[valid][-1] - bg_seg[valid][0]) /
                       ((end - start) / STEPS_PER_HOUR)) if valid.sum() >= 2 else 0
        windows.append({
            'type': 'overnight',
            'start': int(start), 'end': int(end),
            'duration_steps': end - start,
            'mean_bg': mean_bg,
            'drift_mg_dl_h': drift,
            'mean_hour': float(np.mean(hours[start:end]) % 24),
        })
    return windows


def detect_stable_windows(glucose, bolus, carbs, hours):
    """Detect stable windows: CV < 5% over ≥2h."""
    N = len(glucose)
    windows = []
    for start in range(0, N - STABLE_MIN_STEPS, STABLE_MIN_STEPS // 2):
        end = start + STABLE_MIN_STEPS
        bg_seg = glucose[start:end]
        valid = ~np.isnan(bg_seg)
        if valid.sum() < STABLE_MIN_STEPS * 0.8:
            continue
        mean_bg = float(np.nanmean(bg_seg))
        if mean_bg < 40:
            continue
        cv = float(np.nanstd(bg_seg) / mean_bg * 100)
        if cv >= STABLE_MAX_CV:
            continue
        windows.append({
            'type': 'stable',
            'start': int(start), 'end': int(end),
            'duration_steps': end - start,
            'mean_bg': mean_bg,
            'cv': cv,
            'mean_hour': float(np.mean(hours[start:end]) % 24),
        })
    return windows


def detect_all_windows(glucose, bolus, carbs, hours):
    """Run all natural experiment detectors. Returns dict of type → list."""
    all_w = {}
    all_w['fasting'] = detect_fasting_windows(glucose, bolus, carbs, hours)
    all_w['correction'] = detect_correction_windows(glucose, bolus, carbs, hours)
    all_w['meal'] = detect_meal_windows(glucose, bolus, carbs, hours)
    all_w['overnight'] = detect_overnight_windows(glucose, bolus, carbs, hours)
    all_w['stable'] = detect_stable_windows(glucose, bolus, carbs, hours)
    return all_w


# ── Residual computation ──────────────────────────────────────────────

def compute_window_residuals(glucose, sd, window):
    """Compute residuals within a natural experiment window.

    residual(t) = actual_dBG(t) - modeled_net_flux(t)

    Returns dict with residual statistics + decomposed components.
    """
    s, e = window['start'], window['end']
    bg = glucose[s:e]
    supply = sd['supply'][s:e]
    demand = sd['demand'][s:e]
    hepatic = sd['hepatic'][s:e]
    carb_supply = sd['carb_supply'][s:e]
    net = sd['net'][s:e]

    valid = ~np.isnan(bg)
    if valid.sum() < 6:
        return None

    # Actual dBG
    actual_dbg = np.full_like(bg, np.nan)
    for i in range(1, len(bg)):
        if valid[i] and valid[i - 1]:
            actual_dbg[i] = bg[i] - bg[i - 1]

    dbg_valid = ~np.isnan(actual_dbg)
    if dbg_valid.sum() < 3:
        return None

    residual = actual_dbg[dbg_valid] - net[dbg_valid]
    supply_w = supply[dbg_valid]
    demand_w = demand[dbg_valid]
    hepatic_w = hepatic[dbg_valid]
    carb_w = carb_supply[dbg_valid]

    return {
        'residual_mean': float(np.mean(residual)),
        'residual_std': float(np.std(residual)),
        'residual_median': float(np.median(residual)),
        'supply_mean': float(np.mean(supply_w)),
        'demand_mean': float(np.mean(demand_w)),
        'hepatic_mean': float(np.mean(hepatic_w)),
        'carb_supply_mean': float(np.mean(carb_w)),
        'net_flux_mean': float(np.mean(net[dbg_valid])),
        'actual_dbg_mean': float(np.mean(actual_dbg[dbg_valid])),
        'n_steps': int(dbg_valid.sum()),
        'mean_bg': float(np.nanmean(bg)),
        # For calibration: raw arrays
        '_residual': residual,
        '_supply': supply_w,
        '_demand': demand_w,
        '_hepatic': hepatic_w,
        '_carb': carb_w,
        '_actual_dbg': actual_dbg[dbg_valid],
        '_net': net[dbg_valid],
    }


# ── EXP-1611: Cross-context residual profiles ─────────────────────────

def exp_1611_cross_context(patients_data):
    """Prove residuals have structure: differ by natural experiment type."""
    print("\n=== EXP-1611: Cross-Context Residual Profiles ===")

    context_residuals = defaultdict(list)
    context_stats = {}
    per_patient = {}

    for pname, (df, pk, sd, windows) in patients_data.items():
        glucose = df['glucose'].values.astype(np.float64)
        patient_contexts = {}

        for wtype, wlist in windows.items():
            resids = []
            for w in wlist:
                r = compute_window_residuals(glucose, sd, w)
                if r is not None:
                    resids.append(r)
                    context_residuals[wtype].append(r['residual_mean'])

            if resids:
                means = [r['residual_mean'] for r in resids]
                patient_contexts[wtype] = {
                    'n_windows': len(resids),
                    'residual_mean': float(np.mean(means)),
                    'residual_std': float(np.std(means)),
                    'supply_mean': float(np.mean([r['supply_mean'] for r in resids])),
                    'demand_mean': float(np.mean([r['demand_mean'] for r in resids])),
                    'hepatic_mean': float(np.mean([r['hepatic_mean'] for r in resids])),
                }
        per_patient[pname] = patient_contexts

    # Population-level stats
    for wtype, vals in context_residuals.items():
        if len(vals) > 0:
            context_stats[wtype] = {
                'n_windows': len(vals),
                'residual_mean': float(np.mean(vals)),
                'residual_std': float(np.std(vals)),
                'residual_median': float(np.median(vals)),
                'residual_p25': float(np.percentile(vals, 25)),
                'residual_p75': float(np.percentile(vals, 75)),
            }
            print(f"  {wtype:12s}: n={len(vals):5d}  "
                  f"residual={np.mean(vals):+.3f} ± {np.std(vals):.3f}")

    # ANOVA across context types
    groups = [np.array(context_residuals[t]) for t in context_residuals
              if len(context_residuals[t]) >= 10]
    if len(groups) >= 2:
        f_stat, p_val = stats.f_oneway(*groups)
        print(f"\n  ANOVA F={f_stat:.2f}, p={p_val:.2e}")
        context_stats['anova_f'] = float(f_stat)
        context_stats['anova_p'] = float(p_val)

    # Pairwise comparisons (fasting vs correction is key)
    pairwise = {}
    for t1 in ['fasting', 'correction', 'meal', 'overnight', 'stable']:
        for t2 in ['fasting', 'correction', 'meal', 'overnight', 'stable']:
            if t1 >= t2:
                continue
            v1 = context_residuals.get(t1, [])
            v2 = context_residuals.get(t2, [])
            if len(v1) >= 10 and len(v2) >= 10:
                t_stat, p = stats.ttest_ind(v1, v2)
                d = (np.mean(v1) - np.mean(v2)) / np.sqrt(
                    (np.std(v1)**2 + np.std(v2)**2) / 2)
                pairwise[f"{t1}_vs_{t2}"] = {
                    't_stat': float(t_stat), 'p': float(p),
                    'cohens_d': float(d),
                    'means': [float(np.mean(v1)), float(np.mean(v2))],
                }
                if p < 0.05:
                    print(f"  {t1} vs {t2}: d={d:.3f}, p={p:.3e} *")

    return {
        'experiment': 'EXP-1611',
        'title': 'Cross-Context Residual Profiles',
        'context_stats': context_stats,
        'pairwise': pairwise,
        'per_patient': per_patient,
        'context_residuals': {k: [float(v) for v in vals]
                              for k, vals in context_residuals.items()},
    }


# ── EXP-1612: Hepatic calibration from fasting ────────────────────────

def exp_1612_hepatic_calibration(patients_data):
    """Calibrate hepatic production model using fasting windows.

    In fasting: carb_supply ≈ 0, demand is basal-only.
    residual ≈ actual_dBG - (hepatic - demand)
    If residual is systematically non-zero → hepatic model is miscalibrated.

    Fit: calibrated_hepatic = hepatic × alpha + beta
    """
    print("\n=== EXP-1612: Hepatic Calibration from Fasting Windows ===")

    # Collect all fasting residuals with hepatic/demand decomposition
    all_hepatic = []
    all_demand = []
    all_actual_dbg = []
    per_patient_cal = {}

    for pname, (df, pk, sd, windows) in patients_data.items():
        glucose = df['glucose'].values.astype(np.float64)
        p_hepatic, p_demand, p_actual = [], [], []

        for w in windows.get('fasting', []):
            r = compute_window_residuals(glucose, sd, w)
            if r is None:
                continue
            p_hepatic.extend(r['_hepatic'].tolist())
            p_demand.extend(r['_demand'].tolist())
            p_actual.extend(r['_actual_dbg'].tolist())

        if len(p_hepatic) >= 20:
            h, d, a = np.array(p_hepatic), np.array(p_demand), np.array(p_actual)
            predicted = h - d  # modeled dBG in fasting
            residual = a - predicted
            # Fit alpha: calibrated = h * alpha, so predicted_cal = h * alpha - d
            # Minimize: sum((a - (h*alpha - d))^2) → alpha = sum((a+d)*h) / sum(h^2)
            if np.sum(h**2) > 0:
                alpha = float(np.sum((a + d) * h) / np.sum(h**2))
            else:
                alpha = 1.0
            cal_predicted = h * alpha - d
            cal_residual = a - cal_predicted
            r2_before = 1 - np.sum(residual**2) / max(np.sum((a - np.mean(a))**2), 1e-8)
            r2_after = 1 - np.sum(cal_residual**2) / max(np.sum((a - np.mean(a))**2), 1e-8)
            per_patient_cal[pname] = {
                'n_steps': len(h),
                'alpha': alpha,
                'residual_before': float(np.mean(np.abs(residual))),
                'residual_after': float(np.mean(np.abs(cal_residual))),
                'r2_before': float(r2_before),
                'r2_after': float(r2_after),
                'mean_hepatic': float(np.mean(h)),
                'mean_demand': float(np.mean(d)),
            }
            print(f"  {pname}: alpha={alpha:.3f}  R² {r2_before:.3f}→{r2_after:.3f}  "
                  f"n={len(h)}")

        all_hepatic.extend(p_hepatic)
        all_demand.extend(p_demand)
        all_actual_dbg.extend(p_actual)

    # Population-level calibration
    H = np.array(all_hepatic)
    D = np.array(all_demand)
    A = np.array(all_actual_dbg)
    pop_alpha = float(np.sum((A + D) * H) / np.sum(H**2)) if np.sum(H**2) > 0 else 1.0

    predicted = H - D
    cal_predicted = H * pop_alpha - D
    residual_before = A - predicted
    residual_after = A - cal_predicted
    r2_before = 1 - np.sum(residual_before**2) / max(np.sum((A - np.mean(A))**2), 1e-8)
    r2_after = 1 - np.sum(residual_after**2) / max(np.sum((A - np.mean(A))**2), 1e-8)

    print(f"\n  Population: alpha={pop_alpha:.3f}  "
          f"R² {r2_before:.4f}→{r2_after:.4f}  n={len(H)}")
    print(f"  MAE: {np.mean(np.abs(residual_before)):.3f}→"
          f"{np.mean(np.abs(residual_after)):.3f}")

    return {
        'experiment': 'EXP-1612',
        'title': 'Hepatic Calibration from Fasting Windows',
        'population_alpha': pop_alpha,
        'population_r2_before': float(r2_before),
        'population_r2_after': float(r2_after),
        'population_mae_before': float(np.mean(np.abs(residual_before))),
        'population_mae_after': float(np.mean(np.abs(residual_after))),
        'population_n_steps': len(H),
        'per_patient': per_patient_cal,
    }


# ── EXP-1613: Sensitivity calibration from corrections ────────────────

def exp_1613_sensitivity_calibration(patients_data):
    """Calibrate insulin sensitivity using correction windows.

    In corrections: known bolus, no carbs.
    predicted_dBG = hepatic - demand(bolus + basal)
    residual = actual - predicted

    If residual > 0 → insulin less effective than modeled (ISF too high)
    Fit: calibrated_demand = demand × beta
    """
    print("\n=== EXP-1613: Sensitivity Calibration from Correction Windows ===")

    all_demand = []
    all_hepatic = []
    all_actual = []
    per_patient_cal = {}

    for pname, (df, pk, sd, windows) in patients_data.items():
        glucose = df['glucose'].values.astype(np.float64)
        p_h, p_d, p_a = [], [], []

        for w in windows.get('correction', []):
            r = compute_window_residuals(glucose, sd, w)
            if r is None:
                continue
            p_h.extend(r['_hepatic'].tolist())
            p_d.extend(r['_demand'].tolist())
            p_a.extend(r['_actual_dbg'].tolist())

        if len(p_d) >= 20:
            h, d, a = np.array(p_h), np.array(p_d), np.array(p_a)
            predicted = h - d
            residual = a - predicted
            # Fit beta: calibrated = h - d * beta
            # Minimize: sum((a - (h - d*beta))^2) → beta = sum((h-a)*d) / sum(d^2)
            if np.sum(d**2) > 0:
                beta = float(np.sum((h - a) * d) / np.sum(d**2))
            else:
                beta = 1.0
            cal_predicted = h - d * beta
            cal_residual = a - cal_predicted
            r2_before = 1 - np.sum(residual**2) / max(np.sum((a - np.mean(a))**2), 1e-8)
            r2_after = 1 - np.sum(cal_residual**2) / max(np.sum((a - np.mean(a))**2), 1e-8)
            per_patient_cal[pname] = {
                'n_steps': len(d),
                'beta': beta,
                'residual_before': float(np.mean(np.abs(residual))),
                'residual_after': float(np.mean(np.abs(cal_residual))),
                'r2_before': float(r2_before),
                'r2_after': float(r2_after),
                'mean_demand': float(np.mean(d)),
                'mean_hepatic': float(np.mean(h)),
            }
            print(f"  {pname}: beta={beta:.3f}  R² {r2_before:.3f}→{r2_after:.3f}  "
                  f"n={len(d)}")

        all_demand.extend(p_d)
        all_hepatic.extend(p_h)
        all_actual.extend(p_a)

    H = np.array(all_hepatic)
    D = np.array(all_demand)
    A = np.array(all_actual)
    pop_beta = float(np.sum((H - A) * D) / np.sum(D**2)) if np.sum(D**2) > 0 else 1.0

    predicted = H - D
    cal_predicted = H - D * pop_beta
    res_before = A - predicted
    res_after = A - cal_predicted
    r2_before = 1 - np.sum(res_before**2) / max(np.sum((A - np.mean(A))**2), 1e-8)
    r2_after = 1 - np.sum(res_after**2) / max(np.sum((A - np.mean(A))**2), 1e-8)

    print(f"\n  Population: beta={pop_beta:.3f}  "
          f"R² {r2_before:.4f}→{r2_after:.4f}  n={len(D)}")

    return {
        'experiment': 'EXP-1613',
        'title': 'Sensitivity Calibration from Correction Windows',
        'population_beta': pop_beta,
        'population_r2_before': float(r2_before),
        'population_r2_after': float(r2_after),
        'population_mae_before': float(np.mean(np.abs(res_before))),
        'population_mae_after': float(np.mean(np.abs(res_after))),
        'population_n_steps': len(D),
        'per_patient': per_patient_cal,
    }


# ── EXP-1614: Cross-validation on meal windows ────────────────────────

def exp_1614_meal_crossval(patients_data, alpha, beta):
    """Test calibrated model on meal windows (out-of-context validation).

    Apply hepatic_alpha and demand_beta learned from fasting/correction
    to meal windows. If calibration helps, residual should shrink.
    """
    print(f"\n=== EXP-1614: Meal Cross-Validation (α={alpha:.3f}, β={beta:.3f}) ===")

    per_patient = {}
    all_before = []
    all_after = []

    for pname, (df, pk, sd, windows) in patients_data.items():
        glucose = df['glucose'].values.astype(np.float64)
        p_before, p_after = [], []

        for w in windows.get('meal', []):
            r = compute_window_residuals(glucose, sd, w)
            if r is None:
                continue
            h, d, a = r['_hepatic'], r['_demand'], r['_actual_dbg']
            c = r['_carb']
            # Uncalibrated: predicted = (h + c) - d
            pred_uncal = (h + c) - d
            # Calibrated: predicted = (h*alpha + c) - d*beta
            pred_cal = (h * alpha + c) - d * beta

            res_uncal = a - pred_uncal
            res_cal = a - pred_cal
            p_before.append(float(np.mean(np.abs(res_uncal))))
            p_after.append(float(np.mean(np.abs(res_cal))))

        if p_before:
            improvement = (np.mean(p_before) - np.mean(p_after)) / np.mean(p_before) * 100
            per_patient[pname] = {
                'n_meals': len(p_before),
                'mae_before': float(np.mean(p_before)),
                'mae_after': float(np.mean(p_after)),
                'improvement_pct': float(improvement),
            }
            print(f"  {pname}: MAE {np.mean(p_before):.3f}→{np.mean(p_after):.3f}  "
                  f"({improvement:+.1f}%)  n={len(p_before)} meals")
            all_before.extend(p_before)
            all_after.extend(p_after)

    if all_before:
        pop_improvement = (np.mean(all_before) - np.mean(all_after)) / np.mean(all_before) * 100
        print(f"\n  Population: MAE {np.mean(all_before):.3f}→{np.mean(all_after):.3f}  "
              f"({pop_improvement:+.1f}%)")
        # Paired t-test
        t, p = stats.ttest_rel(all_before, all_after)
        print(f"  Paired t-test: t={t:.2f}, p={p:.3e}")
    else:
        pop_improvement = 0
        t, p = 0, 1

    return {
        'experiment': 'EXP-1614',
        'title': 'Cross-Validation on Meal Windows',
        'alpha_used': alpha,
        'beta_used': beta,
        'population_mae_before': float(np.mean(all_before)) if all_before else None,
        'population_mae_after': float(np.mean(all_after)) if all_after else None,
        'population_improvement_pct': float(pop_improvement),
        'paired_t': float(t),
        'paired_p': float(p),
        'per_patient': per_patient,
    }


def exp_1614_per_patient_crossval(patients_data, r1612, r1613):
    """EXP-1614b: Per-patient calibration applied to meal windows.

    Uses each patient's own alpha and beta (learned from their fasting
    and correction windows) instead of population averages.
    Tests whether individual calibration transfers across contexts.
    """
    print("\n=== EXP-1614b: Per-Patient Calibrated Meal Cross-Validation ===")

    per_patient = {}
    all_before = []
    all_after = []

    for pname, (df, pk, sd, windows) in patients_data.items():
        glucose = df['glucose'].values.astype(np.float64)

        # Get per-patient calibration factors (fall back to 1.0 if not available)
        p_alpha = r1612['per_patient'].get(pname, {}).get('alpha', 1.0)
        p_beta = r1613['per_patient'].get(pname, {}).get('beta', 1.0)

        p_before, p_after = [], []
        for w in windows.get('meal', []):
            r = compute_window_residuals(glucose, sd, w)
            if r is None:
                continue
            h, d, a, c = r['_hepatic'], r['_demand'], r['_actual_dbg'], r['_carb']
            pred_uncal = (h + c) - d
            pred_cal = (h * p_alpha + c) - d * p_beta
            res_uncal = a - pred_uncal
            res_cal = a - pred_cal
            p_before.append(float(np.mean(np.abs(res_uncal))))
            p_after.append(float(np.mean(np.abs(res_cal))))

        if p_before:
            improvement = (np.mean(p_before) - np.mean(p_after)) / np.mean(p_before) * 100
            per_patient[pname] = {
                'n_meals': len(p_before),
                'alpha': p_alpha,
                'beta': p_beta,
                'mae_before': float(np.mean(p_before)),
                'mae_after': float(np.mean(p_after)),
                'improvement_pct': float(improvement),
            }
            print(f"  {pname}: α={p_alpha:.3f} β={p_beta:.3f}  "
                  f"MAE {np.mean(p_before):.3f}→{np.mean(p_after):.3f}  "
                  f"({improvement:+.1f}%)  n={len(p_before)}")
            all_before.extend(p_before)
            all_after.extend(p_after)

    if all_before:
        pop_improvement = (np.mean(all_before) - np.mean(all_after)) / np.mean(all_before) * 100
        t_stat, p_val = stats.ttest_rel(all_before, all_after)
        print(f"\n  Population: MAE {np.mean(all_before):.3f}→{np.mean(all_after):.3f}  "
              f"({pop_improvement:+.1f}%)")
        print(f"  Paired t-test: t={t_stat:.2f}, p={p_val:.3e}")
        n_improved = sum(1 for p in per_patient.values() if p['improvement_pct'] > 0)
        print(f"  Patients improved: {n_improved}/{len(per_patient)}")
    else:
        pop_improvement = 0
        t_stat, p_val = 0, 1
        n_improved = 0

    return {
        'experiment': 'EXP-1614b',
        'title': 'Per-Patient Calibrated Meal Cross-Validation',
        'population_mae_before': float(np.mean(all_before)) if all_before else None,
        'population_mae_after': float(np.mean(all_after)) if all_after else None,
        'population_improvement_pct': float(pop_improvement),
        'paired_t': float(t_stat),
        'paired_p': float(p_val),
        'n_improved': n_improved,
        'n_patients': len(per_patient),
        'per_patient': per_patient,
    }


# ── EXP-1615: Temporal convergence ────────────────────────────────────

def exp_1615_temporal_convergence(patients_data):
    """How many days of data are needed for stable calibration?

    Subsample data at 7, 14, 30, 60, 90, 180 day windows.
    Track alpha (hepatic) and beta (sensitivity) convergence.
    """
    print("\n=== EXP-1615: Temporal Convergence ===")

    durations_days = [7, 14, 30, 60, 90, 180]
    convergence = {d: {'alphas': [], 'betas': []} for d in durations_days}

    for pname, (df, pk, sd, windows) in patients_data.items():
        glucose = df['glucose'].values.astype(np.float64)
        N = len(glucose)
        total_days = N / STEPS_PER_DAY

        for dur in durations_days:
            dur_steps = int(dur * STEPS_PER_DAY)
            if dur_steps > N:
                continue

            # Take first `dur` days
            fasting_w = [w for w in windows.get('fasting', [])
                         if w['end'] <= dur_steps]
            correction_w = [w for w in windows.get('correction', [])
                            if w['end'] <= dur_steps]

            # Compute alpha from fasting
            h_all, d_all, a_all = [], [], []
            for w in fasting_w:
                r = compute_window_residuals(glucose, sd, w)
                if r is None:
                    continue
                h_all.extend(r['_hepatic'].tolist())
                d_all.extend(r['_demand'].tolist())
                a_all.extend(r['_actual_dbg'].tolist())

            if len(h_all) >= 10:
                H, D, A = np.array(h_all), np.array(d_all), np.array(a_all)
                alpha = float(np.sum((A + D) * H) / np.sum(H**2)) if np.sum(H**2) > 0 else 1.0
                convergence[dur]['alphas'].append(alpha)

            # Compute beta from corrections
            h_all, d_all, a_all = [], [], []
            for w in correction_w:
                r = compute_window_residuals(glucose, sd, w)
                if r is None:
                    continue
                h_all.extend(r['_hepatic'].tolist())
                d_all.extend(r['_demand'].tolist())
                a_all.extend(r['_actual_dbg'].tolist())

            if len(d_all) >= 10:
                H, D, A = np.array(h_all), np.array(d_all), np.array(a_all)
                beta = float(np.sum((H - A) * D) / np.sum(D**2)) if np.sum(D**2) > 0 else 1.0
                convergence[dur]['betas'].append(beta)

    results = {}
    for dur in durations_days:
        alphas = convergence[dur]['alphas']
        betas = convergence[dur]['betas']
        results[str(dur)] = {
            'alpha_mean': float(np.mean(alphas)) if alphas else None,
            'alpha_std': float(np.std(alphas)) if alphas else None,
            'alpha_n': len(alphas),
            'beta_mean': float(np.mean(betas)) if betas else None,
            'beta_std': float(np.std(betas)) if betas else None,
            'beta_n': len(betas),
        }
        a_str = f"α={np.mean(alphas):.3f}±{np.std(alphas):.3f}" if alphas else "α=N/A"
        b_str = f"β={np.mean(betas):.3f}±{np.std(betas):.3f}" if betas else "β=N/A"
        print(f"  {dur:3d} days: {a_str}  {b_str}  "
              f"n_α={len(alphas)}, n_β={len(betas)}")

    return {
        'experiment': 'EXP-1615',
        'title': 'Temporal Convergence of Calibration Parameters',
        'convergence': results,
    }


# ── EXP-1616: Therapy assessment with calibrated model ─────────────────

def exp_1616_therapy_assessment(patients_data, alpha, beta):
    """Compare therapy parameter estimates: uncalibrated vs calibrated.

    For each patient, extract:
    - Effective basal rate from overnight drift (uncal vs cal)
    - Effective ISF from correction windows (uncal vs cal)
    - Meal residual (proxy for CR adequacy)
    """
    print(f"\n=== EXP-1616: Therapy Assessment (α={alpha:.3f}, β={beta:.3f}) ===")

    per_patient = {}

    for pname, (df, pk, sd, windows) in patients_data.items():
        glucose = df['glucose'].values.astype(np.float64)

        # Overnight drift (basal adequacy)
        overnight_drifts_uncal = []
        overnight_drifts_cal = []
        for w in windows.get('overnight', []):
            r = compute_window_residuals(glucose, sd, w)
            if r is None:
                continue
            h, d, a = r['_hepatic'], r['_demand'], r['_actual_dbg']
            uncal_pred = h - d
            cal_pred = h * alpha - d * beta
            uncal_res = np.mean(a - uncal_pred) * STEPS_PER_HOUR  # per hour
            cal_res = np.mean(a - cal_pred) * STEPS_PER_HOUR
            overnight_drifts_uncal.append(float(uncal_res))
            overnight_drifts_cal.append(float(cal_res))

        # Correction ISF (sensitivity adequacy)
        isf_uncal = []
        isf_cal = []
        for w in windows.get('correction', []):
            r = compute_window_residuals(glucose, sd, w)
            if r is None or r['n_steps'] < 12:
                continue
            h, d, a = r['_hepatic'], r['_demand'], r['_actual_dbg']
            # Uncalibrated: how much of the glucose drop is explained?
            total_drop = np.sum(a)
            predicted_drop_uncal = np.sum(h - d)
            predicted_drop_cal = np.sum(h * alpha - d * beta)
            if abs(predicted_drop_uncal) > 0.1:
                ratio_uncal = total_drop / predicted_drop_uncal
                isf_uncal.append(float(ratio_uncal))
            if abs(predicted_drop_cal) > 0.1:
                ratio_cal = total_drop / predicted_drop_cal
                isf_cal.append(float(ratio_cal))

        # Meal residual (CR adequacy)
        meal_res_uncal = []
        meal_res_cal = []
        for w in windows.get('meal', []):
            r = compute_window_residuals(glucose, sd, w)
            if r is None:
                continue
            h, d, c, a = r['_hepatic'], r['_demand'], r['_carb'], r['_actual_dbg']
            uncal = np.mean(a - ((h + c) - d))
            cal = np.mean(a - ((h * alpha + c) - d * beta))
            meal_res_uncal.append(float(uncal))
            meal_res_cal.append(float(cal))

        result = {
            'overnight_drift_uncal': float(np.mean(overnight_drifts_uncal)) if overnight_drifts_uncal else None,
            'overnight_drift_cal': float(np.mean(overnight_drifts_cal)) if overnight_drifts_cal else None,
            'n_overnight': len(overnight_drifts_uncal),
            'isf_ratio_uncal': float(np.mean(isf_uncal)) if isf_uncal else None,
            'isf_ratio_cal': float(np.mean(isf_cal)) if isf_cal else None,
            'n_corrections': len(isf_uncal),
            'meal_residual_uncal': float(np.mean(meal_res_uncal)) if meal_res_uncal else None,
            'meal_residual_cal': float(np.mean(meal_res_cal)) if meal_res_cal else None,
            'n_meals': len(meal_res_uncal),
        }
        per_patient[pname] = result

        drift_u = f"{result['overnight_drift_uncal']:+.2f}" if result['overnight_drift_uncal'] is not None else "N/A"
        drift_c = f"{result['overnight_drift_cal']:+.2f}" if result['overnight_drift_cal'] is not None else "N/A"
        print(f"  {pname}: drift {drift_u}→{drift_c} mg/dL/h  "
              f"corrections={result['n_corrections']}  meals={result['n_meals']}")

    return {
        'experiment': 'EXP-1616',
        'title': 'Therapy Assessment with Calibrated Model',
        'alpha': alpha,
        'beta': beta,
        'per_patient': per_patient,
    }


# ── Figures ────────────────────────────────────────────────────────────

def generate_figures(results, patients_data):
    """Generate 6 visualization figures."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # Fig 1: Cross-context residual profiles
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1611 = results['EXP-1611']
    ctx_stats = r1611['context_stats']
    types_ordered = ['stable', 'overnight', 'fasting', 'correction', 'meal']
    types_present = [t for t in types_ordered if t in ctx_stats]
    means = [ctx_stats[t]['residual_mean'] for t in types_present]
    stds = [ctx_stats[t]['residual_std'] for t in types_present]
    ns = [ctx_stats[t]['n_windows'] for t in types_present]

    colors = {'stable': '#4CAF50', 'overnight': '#2196F3', 'fasting': '#FF9800',
              'correction': '#F44336', 'meal': '#9C27B0'}
    bar_colors = [colors.get(t, '#666') for t in types_present]

    axes[0].barh(range(len(types_present)), means, xerr=stds, color=bar_colors, alpha=0.8)
    axes[0].set_yticks(range(len(types_present)))
    axes[0].set_yticklabels([f"{t}\n(n={n})" for t, n in zip(types_present, ns)])
    axes[0].axvline(x=0, color='k', linestyle='--', alpha=0.5)
    axes[0].set_xlabel('Mean Residual (mg/dL per 5-min)')
    axes[0].set_title('Residual by Context Type')

    # Box plot of raw distributions
    ctx_data = [np.array(r1611['context_residuals'].get(t, []))
                for t in types_present]
    # Clip for visibility
    ctx_data_clipped = [np.clip(d, -10, 10) for d in ctx_data]
    bp = axes[1].boxplot(ctx_data_clipped, vert=True,
                          tick_labels=types_present,
                          patch_artist=True, showfliers=False)
    for patch, color in zip(bp['boxes'], bar_colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    axes[1].axhline(y=0, color='k', linestyle='--', alpha=0.5)
    axes[1].set_ylabel('Residual (mg/dL per 5-min)')
    axes[1].set_title('Residual Distribution by Context')
    axes[1].tick_params(axis='x', rotation=30)

    fig.suptitle('EXP-1611: Residuals Are Structured, Not Random', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'deconfound-fig1-context-residuals.png', dpi=150)
    plt.close()
    print(f"  Saved fig1")

    # Fig 2: Hepatic calibration — alpha by patient
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1612 = results['EXP-1612']
    pp = r1612['per_patient']
    patients_sorted = sorted(pp.keys())
    alphas = [pp[p]['alpha'] for p in patients_sorted]
    r2_before = [pp[p]['r2_before'] for p in patients_sorted]
    r2_after = [pp[p]['r2_after'] for p in patients_sorted]

    x = np.arange(len(patients_sorted))
    axes[0].bar(x, alphas, color='#FF9800', alpha=0.8)
    axes[0].axhline(y=1.0, color='k', linestyle='--', alpha=0.5, label='No correction')
    axes[0].axhline(y=r1612['population_alpha'], color='red', linestyle='-', alpha=0.7,
                    label=f"Population α={r1612['population_alpha']:.3f}")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(patients_sorted)
    axes[0].set_ylabel('Hepatic Scale Factor (α)')
    axes[0].set_title('Hepatic Calibration by Patient')
    axes[0].legend()

    width = 0.35
    axes[1].bar(x - width/2, r2_before, width, label='Before', color='#F44336', alpha=0.7)
    axes[1].bar(x + width/2, r2_after, width, label='After', color='#4CAF50', alpha=0.7)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(patients_sorted)
    axes[1].set_ylabel('R²')
    axes[1].set_title('Fasting R²: Before vs After Calibration')
    axes[1].axhline(y=0, color='k', linestyle='--', alpha=0.3)
    axes[1].legend()

    fig.suptitle('EXP-1612: Hepatic Model Calibration from Fasting Windows', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'deconfound-fig2-hepatic-calibration.png', dpi=150)
    plt.close()
    print(f"  Saved fig2")

    # Fig 3: Sensitivity calibration — beta by patient
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1613 = results['EXP-1613']
    pp = r1613['per_patient']
    patients_sorted = sorted(pp.keys())
    betas = [pp[p]['beta'] for p in patients_sorted]
    r2_before = [pp[p]['r2_before'] for p in patients_sorted]
    r2_after = [pp[p]['r2_after'] for p in patients_sorted]

    x = np.arange(len(patients_sorted))
    axes[0].bar(x, betas, color='#F44336', alpha=0.8)
    axes[0].axhline(y=1.0, color='k', linestyle='--', alpha=0.5, label='No correction')
    axes[0].axhline(y=r1613['population_beta'], color='red', linestyle='-', alpha=0.7,
                    label=f"Population β={r1613['population_beta']:.3f}")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(patients_sorted)
    axes[0].set_ylabel('Demand Scale Factor (β)')
    axes[0].set_title('Insulin Sensitivity Calibration by Patient')
    axes[0].legend()

    width = 0.35
    axes[1].bar(x - width/2, r2_before, width, label='Before', color='#F44336', alpha=0.7)
    axes[1].bar(x + width/2, r2_after, width, label='After', color='#4CAF50', alpha=0.7)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(patients_sorted)
    axes[1].set_ylabel('R²')
    axes[1].set_title('Correction R²: Before vs After Calibration')
    axes[1].axhline(y=0, color='k', linestyle='--', alpha=0.3)
    axes[1].legend()

    fig.suptitle('EXP-1613: Insulin Sensitivity Calibration from Corrections', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'deconfound-fig3-sensitivity-calibration.png', dpi=150)
    plt.close()
    print(f"  Saved fig3")

    # Fig 4: Meal cross-validation — before/after MAE
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1614 = results['EXP-1614']
    pp = r1614['per_patient']
    patients_sorted = sorted(pp.keys())
    mae_before = [pp[p]['mae_before'] for p in patients_sorted]
    mae_after = [pp[p]['mae_after'] for p in patients_sorted]
    improvements = [pp[p]['improvement_pct'] for p in patients_sorted]

    x = np.arange(len(patients_sorted))
    width = 0.35
    axes[0].bar(x - width/2, mae_before, width, label='Uncalibrated', color='#F44336', alpha=0.7)
    axes[0].bar(x + width/2, mae_after, width, label='Calibrated', color='#4CAF50', alpha=0.7)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(patients_sorted)
    axes[0].set_ylabel('MAE (mg/dL per 5-min)')
    axes[0].set_title('Meal Window MAE')
    axes[0].legend()

    imp_colors = ['#4CAF50' if i > 0 else '#F44336' for i in improvements]
    axes[1].bar(x, improvements, color=imp_colors, alpha=0.8)
    axes[1].axhline(y=0, color='k', linestyle='--', alpha=0.5)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(patients_sorted)
    axes[1].set_ylabel('Improvement (%)')
    axes[1].set_title('MAE Improvement from Calibration')

    pop_imp = r1614['population_improvement_pct']
    fig.suptitle(f'EXP-1614: Cross-Validation on Meals — {pop_imp:+.1f}% Population',
                 fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'deconfound-fig4-meal-crossval.png', dpi=150)
    plt.close()
    print(f"  Saved fig4")

    # Fig 5: Temporal convergence
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1615 = results['EXP-1615']
    conv = r1615['convergence']
    days = sorted([int(d) for d in conv.keys()])
    alpha_means = [conv[str(d)]['alpha_mean'] for d in days]
    alpha_stds = [conv[str(d)]['alpha_std'] if conv[str(d)]['alpha_std'] is not None else 0 for d in days]
    beta_means = [conv[str(d)]['beta_mean'] for d in days]
    beta_stds = [conv[str(d)]['beta_std'] if conv[str(d)]['beta_std'] is not None else 0 for d in days]

    # Filter None values
    alpha_valid = [(d, m, s) for d, m, s in zip(days, alpha_means, alpha_stds) if m is not None]
    beta_valid = [(d, m, s) for d, m, s in zip(days, beta_means, beta_stds) if m is not None]

    if alpha_valid:
        ad, am, asd = zip(*alpha_valid)
        am, asd = np.array(am), np.array(asd)
        axes[0].errorbar(ad, am, yerr=asd, marker='o', color='#FF9800',
                         capsize=5, linewidth=2, markersize=8)
        axes[0].axhline(y=1.0, color='k', linestyle='--', alpha=0.3)
        axes[0].fill_between(ad, am - asd, am + asd, alpha=0.2, color='#FF9800')
    axes[0].set_xlabel('Days of Data')
    axes[0].set_ylabel('α (Hepatic Scale Factor)')
    axes[0].set_title('Hepatic Calibration Convergence')

    if beta_valid:
        bd, bm, bsd = zip(*beta_valid)
        bm, bsd = np.array(bm), np.array(bsd)
        axes[1].errorbar(bd, bm, yerr=bsd, marker='s', color='#F44336',
                         capsize=5, linewidth=2, markersize=8)
        axes[1].axhline(y=1.0, color='k', linestyle='--', alpha=0.3)
        axes[1].fill_between(bd, bm - bsd, bm + bsd, alpha=0.2, color='#F44336')
    axes[1].set_xlabel('Days of Data')
    axes[1].set_ylabel('β (Demand Scale Factor)')
    axes[1].set_title('Sensitivity Calibration Convergence')

    fig.suptitle('EXP-1615: How Much Data Is Needed?', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'deconfound-fig5-convergence.png', dpi=150)
    plt.close()
    print(f"  Saved fig5")

    # Fig 6: Therapy assessment comparison
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    r1616 = results['EXP-1616']
    pp = r1616['per_patient']
    patients_sorted = sorted(pp.keys())

    # Overnight drift
    drift_u = [pp[p]['overnight_drift_uncal'] or 0 for p in patients_sorted]
    drift_c = [pp[p]['overnight_drift_cal'] or 0 for p in patients_sorted]
    x = np.arange(len(patients_sorted))
    width = 0.35
    axes[0].bar(x - width/2, drift_u, width, label='Uncalibrated', color='#2196F3', alpha=0.7)
    axes[0].bar(x + width/2, drift_c, width, label='Calibrated', color='#4CAF50', alpha=0.7)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(patients_sorted)
    axes[0].set_ylabel('Drift (mg/dL/h)')
    axes[0].set_title('Overnight Drift (Basal)')
    axes[0].axhline(y=0, color='k', linestyle='--', alpha=0.3)
    axes[0].legend(fontsize=8)

    # ISF ratio
    isf_u = [pp[p]['isf_ratio_uncal'] or 0 for p in patients_sorted]
    isf_c = [pp[p]['isf_ratio_cal'] or 0 for p in patients_sorted]
    axes[1].bar(x - width/2, isf_u, width, label='Uncalibrated', color='#FF9800', alpha=0.7)
    axes[1].bar(x + width/2, isf_c, width, label='Calibrated', color='#4CAF50', alpha=0.7)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(patients_sorted)
    axes[1].set_ylabel('Actual/Predicted Ratio')
    axes[1].set_title('ISF Ratio (Corrections)')
    axes[1].axhline(y=1.0, color='k', linestyle='--', alpha=0.3, label='Perfect')
    axes[1].legend(fontsize=8)

    # Meal residual
    meal_u = [pp[p]['meal_residual_uncal'] or 0 for p in patients_sorted]
    meal_c = [pp[p]['meal_residual_cal'] or 0 for p in patients_sorted]
    axes[2].bar(x - width/2, meal_u, width, label='Uncalibrated', color='#9C27B0', alpha=0.7)
    axes[2].bar(x + width/2, meal_c, width, label='Calibrated', color='#4CAF50', alpha=0.7)
    axes[2].set_xticks(x)
    axes[2].set_xticklabels(patients_sorted)
    axes[2].set_ylabel('Mean Residual (mg/dL per 5-min)')
    axes[2].set_title('Meal Residual (CR Proxy)')
    axes[2].axhline(y=0, color='k', linestyle='--', alpha=0.3)
    axes[2].legend(fontsize=8)

    fig.suptitle('EXP-1616: Therapy Assessment — Uncalibrated vs Calibrated',
                 fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'deconfound-fig6-therapy-assessment.png', dpi=150)
    plt.close()
    print(f"  Saved fig6")


# ── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Natural Experiment Deconfounding')
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    parser.add_argument('--max-patients', type=int, default=11)
    args = parser.parse_args()

    print("Loading patients...")
    raw_patients = load_patients(
        patients_dir=str(PATIENTS_DIR),
        max_patients=args.max_patients,
    )
    print(f"Loaded {len(raw_patients)} patients")

    # Precompute supply-demand and detect natural experiments for all patients
    patients_data = {}
    total_windows = defaultdict(int)

    for p in raw_patients:
        pname = p['name']
        df = p['df']
        pk = p['pk']

        glucose = df['glucose'].values.astype(np.float64)
        bolus = np.nan_to_num(df.get('bolus', np.zeros(len(df))).values.astype(np.float64)
                              if 'bolus' in df.columns else np.zeros(len(df)), nan=0.0)
        carbs_arr = np.nan_to_num(df['carbs'].values.astype(np.float64)
                                  if 'carbs' in df.columns else np.zeros(len(df)), nan=0.0)

        if hasattr(df.index, 'hour'):
            hours = df.index.hour + df.index.minute / 60.0
        else:
            hours = np.zeros(len(df))

        sd = compute_supply_demand(df, pk)
        windows = detect_all_windows(glucose, bolus, carbs_arr, hours)

        for wtype, wlist in windows.items():
            total_windows[wtype] += len(wlist)

        patients_data[pname] = (df, pk, sd, windows)

    print(f"\nNatural experiment windows detected:")
    for wtype, count in sorted(total_windows.items(), key=lambda x: -x[1]):
        print(f"  {wtype:12s}: {count:5d}")

    # Run all experiments
    results = {}

    r1611 = exp_1611_cross_context(patients_data)
    results['EXP-1611'] = r1611

    r1612 = exp_1612_hepatic_calibration(patients_data)
    results['EXP-1612'] = r1612
    alpha = r1612['population_alpha']

    r1613 = exp_1613_sensitivity_calibration(patients_data)
    results['EXP-1613'] = r1613
    beta = r1613['population_beta']

    # Population-level cross-validation
    r1614_pop = exp_1614_meal_crossval(patients_data, alpha, beta)
    results['EXP-1614'] = r1614_pop

    # Per-patient cross-validation: use each patient's own alpha and beta
    r1614_pp = exp_1614_per_patient_crossval(patients_data, r1612, r1613)
    results['EXP-1614b'] = r1614_pp

    r1615 = exp_1615_temporal_convergence(patients_data)
    results['EXP-1615'] = r1615

    r1616 = exp_1616_therapy_assessment(patients_data, alpha, beta)
    results['EXP-1616'] = r1616

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for exp_id, data in results.items():
        fname = f"exp-{exp_id.split('-')[1]}_natural_deconfound.json"
        with open(RESULTS_DIR / fname, 'w') as f:
            # Remove numpy arrays before serialization
            clean = {k: v for k, v in data.items()
                     if not isinstance(v, np.ndarray)}
            json.dump(clean, f, indent=2, default=str)
    print(f"\nSaved {len(results)} experiment JSONs to {RESULTS_DIR}")

    if args.figures:
        print("\nGenerating figures...")
        generate_figures(results, patients_data)
        print(f"Saved to {FIGURES_DIR}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Hepatic calibration α = {alpha:.3f} (1.0 = no change)")
    print(f"  Sensitivity calibration β = {beta:.3f} (1.0 = no change)")
    print(f"  Meal cross-val (population): {r1614_pop['population_improvement_pct']:+.1f}%")
    print(f"  Meal cross-val (per-patient): {r1614_pp['population_improvement_pct']:+.1f}%")
    if r1614_pop['paired_p'] is not None:
        print(f"  Paired t-test p (pop) = {r1614_pop['paired_p']:.3e}")
    if r1614_pp.get('paired_p') is not None:
        print(f"  Paired t-test p (pp) = {r1614_pp['paired_p']:.3e}")
    print(f"  Fasting R² improvement: "
          f"{r1612['population_r2_before']:.4f} → {r1612['population_r2_after']:.4f}")
    print(f"  Correction R² improvement: "
          f"{r1613['population_r2_before']:.4f} → {r1613['population_r2_after']:.4f}")


if __name__ == '__main__':
    main()
