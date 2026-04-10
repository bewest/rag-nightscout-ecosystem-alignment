#!/usr/bin/env python3
"""
EXP-1901 series: Retrospective Split-Half Validation of Settings Recommendations

Validates that settings computed from training data (163 days) predict
held-out verification day (18 days) outcomes. Uses the pre-existing
training/verification split (every 10th day held out).

Sub-experiments:
  EXP-1901: Train/Verify Settings Concordance
    - Compute optimal settings from training NEs and verification NEs
    - Measure concordance: are settings temporally stable?

  EXP-1903: Rolling Window Stability
    - Within training data, compute settings from 60-day sliding windows
    - Measure temporal drift and autocorrelation

  EXP-1905: Mismatch → TIR Relationship (KEY EXPERIMENT)
    - For each patient, compute ISF/basal/CR mismatch from optimal
    - Correlate mismatch with per-window TIR
    - If larger mismatch → worse TIR, recommendations are validated

  EXP-1907: 5-Fold Temporal Cross-Validation
    - 5-fold temporal CV within training data
    - Measure settings prediction stability across folds

  EXP-1909: Verification Day TIR Prediction
    - Use training-derived settings mismatch to predict verification TIR
    - Compare high-mismatch vs low-mismatch verification days

Usage:
    PYTHONPATH=tools python tools/cgmencode/exp_clinical_1901.py
    PYTHONPATH=tools python tools/cgmencode/exp_clinical_1901.py --max-patients 3
    PYTHONPATH=tools python tools/cgmencode/exp_clinical_1901.py --experiment 1901
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

warnings.filterwarnings('ignore', category=RuntimeWarning)

# ── Paths ─────────────────────────────────────────────────────────────

PATIENTS_DIR = os.path.join(PROJECT_ROOT, 'externals', 'ns-data', 'patients')
RESULTS_DIR = Path(PROJECT_ROOT) / 'externals' / 'experiments'
VIZ_DIR = Path(PROJECT_ROOT) / 'visualizations' / 'natural-experiments'

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
VIZ_DIR.mkdir(parents=True, exist_ok=True)

# ── Data Loading ──────────────────────────────────────────────────────

from cgmencode.exp_metabolic_flux import (
    find_patient_dirs,
    _extract_isf_scalar,
    _extract_cr_scalar,
)
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features


def load_patients_split(max_patients=11, patients_dir=None, split='training'):
    """Load patients from training or verification split.

    Args:
        split: 'training' or 'verification'
    """
    patients_dir = patients_dir or PATIENTS_DIR
    pdirs = find_patient_dirs(patients_dir)
    if max_patients:
        pdirs = pdirs[:max_patients]

    patients = []
    for pdir in pdirs:
        data_dir = str(pdir / split)
        if not os.path.isdir(data_dir):
            print(f"  Skip {pdir.name}: no {split}/ directory")
            continue
        try:
            result = build_nightscout_grid(data_dir, verbose=False)
            if result is None:
                continue
            df, features = result
            if df is None or len(df) < 50:
                continue
            pk = build_continuous_pk_features(df)
            if pk is None:
                continue
            n = min(len(features), len(pk))
            patients.append({
                'name': pdir.name,
                'df': df.iloc[:n],
                'grid': features[:n],
                'pk': pk[:n],
            })
            print(f"  Loaded {pdir.name}/{split}: {n} steps ({n/288:.1f} days)")
        except Exception as exc:
            print(f"  Skip {pdir.name}/{split}: {exc}")
    return patients


# ── Shared Helpers ────────────────────────────────────────────────────

PERIODS = ['overnight', 'morning', 'midday', 'afternoon', 'evening']
PERIOD_HOURS = {
    'overnight': (0, 6), 'morning': (6, 10), 'midday': (10, 14),
    'afternoon': (14, 18), 'evening': (18, 24),
}


def _time_period(hour: float) -> str:
    for name, (lo, hi) in PERIOD_HOURS.items():
        if lo <= hour < hi:
            return name
    return 'overnight'


def _safe_val(v):
    if v is None:
        return None
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _bootstrap_ci(values, n_boot=1000, ci=0.95, seed=42):
    rng = np.random.RandomState(seed)
    arr = np.array(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return 0.0, 0.0, 0.0
    medians = np.array([np.median(rng.choice(arr, size=len(arr), replace=True))
                        for _ in range(n_boot)])
    alpha = (1 - ci) / 2
    return float(np.median(arr)), float(np.percentile(medians, 100*alpha)), float(np.percentile(medians, 100*(1-alpha)))


def _compute_tir(glucose, lo=70, hi=180):
    """TIR for a glucose array (70-180 mg/dL range)."""
    arr = np.array(glucose, dtype=float)
    valid = arr[np.isfinite(arr)]
    if len(valid) == 0:
        return float('nan')
    return float(np.mean((valid >= lo) & (valid <= hi)) * 100)


def _compute_tbr(glucose, lo=70):
    arr = np.array(glucose, dtype=float)
    valid = arr[np.isfinite(arr)]
    if len(valid) == 0:
        return float('nan')
    return float(np.mean(valid < lo) * 100)


def _compute_tar(glucose, hi=180):
    arr = np.array(glucose, dtype=float)
    valid = arr[np.isfinite(arr)]
    if len(valid) == 0:
        return float('nan')
    return float(np.mean(valid > hi) * 100)


def _compute_cv(glucose):
    arr = np.array(glucose, dtype=float)
    valid = arr[np.isfinite(arr)]
    if len(valid) < 2:
        return float('nan')
    m = np.mean(valid)
    if m < 1:
        return float('nan')
    return float(np.std(valid) / m * 100)


def _get_profile_isf(df):
    return _extract_isf_scalar(df)


def _get_profile_cr(df):
    return _extract_cr_scalar(df)


def _get_profile_basal(df):
    basal_sched = df.attrs.get('basal_schedule', [])
    if isinstance(basal_sched, list) and basal_sched:
        vals = [float(item.get('value', item.get('rate', 1.0)))
                for item in basal_sched if item.get('value') or item.get('rate')]
        if vals:
            return float(np.median(vals))
    return 1.0


# ── Natural Experiment Detection (reuse research detectors) ──────────

def _detect_fasting_windows(df, bg, bolus, carbs):
    """Detect fasting windows: ≥3h no food/bolus, stable insulin."""
    N = len(bg)
    windows = []
    STEPS_PER_HOUR = 12
    MIN_FASTING_STEPS = 3 * STEPS_PER_HOUR

    is_eating = np.zeros(N, dtype=bool)
    is_bolusing = np.zeros(N, dtype=bool)

    if carbs is not None:
        is_eating = carbs > 0
    if bolus is not None:
        is_bolusing = bolus > 0.05

    active = is_eating | is_bolusing
    i = 0
    while i < N:
        if active[i]:
            i += 1
            continue
        j = i
        while j < N and not active[j]:
            j += 1
        duration = j - i
        if duration >= MIN_FASTING_STEPS:
            seg = bg[i:j]
            valid = np.isfinite(seg)
            coverage = np.mean(valid) if len(valid) > 0 else 0
            if coverage > 0.8:
                finite_seg = seg[valid]
                drift_per_step = (finite_seg[-1] - finite_seg[0]) / max(len(finite_seg)-1, 1)
                drift_per_hour = drift_per_step * STEPS_PER_HOUR
                hour = (i % (288)) / 12.0
                windows.append({
                    'start_idx': i, 'end_idx': j,
                    'hour': hour,
                    'duration_h': duration / STEPS_PER_HOUR,
                    'drift_mg_dl_per_hour': float(drift_per_hour),
                    'mean_bg': float(np.nanmean(seg)),
                    'coverage': float(coverage),
                    'type': 'fasting',
                })
        i = j
    return windows


def _detect_correction_windows(df, bg, bolus, carbs):
    """Detect correction bolus windows: bolus with no carbs nearby, BG drops."""
    N = len(bg)
    windows = []
    if bolus is None:
        return windows

    STEPS_PER_HOUR = 12
    OBSERVE_STEPS = 4 * STEPS_PER_HOUR  # 4h observation

    bolus_idxs = np.where(bolus > 0.05)[0]
    for bi in bolus_idxs:
        # Check no carbs within ±1h
        carb_window_start = max(0, bi - STEPS_PER_HOUR)
        carb_window_end = min(N, bi + STEPS_PER_HOUR)
        if carbs is not None and np.nansum(carbs[carb_window_start:carb_window_end]) > 1:
            continue

        end = min(bi + OBSERVE_STEPS, N)
        if end - bi < 12:
            continue

        seg = bg[bi:end]
        valid = np.isfinite(seg)
        coverage = np.mean(valid) if len(valid) > 0 else 0
        if coverage < 0.7:
            continue

        start_bg = float(bg[bi]) if np.isfinite(bg[bi]) else None
        if start_bg is None:
            continue

        # Find nadir
        finite_seg = seg.copy()
        finite_seg[~valid] = 999
        nadir_rel = np.argmin(finite_seg)
        nadir_bg = float(finite_seg[nadir_rel])
        delta = start_bg - nadir_bg

        if delta < 5:
            continue

        dose = float(bolus[bi])
        if dose < 0.1:
            continue

        simple_isf = delta / dose
        # Response curve ISF (exponential fit)
        curve_isf = _fit_response_curve(seg, dose, STEPS_PER_HOUR)

        hour = (bi % 288) / 12.0
        windows.append({
            'start_idx': bi, 'end_idx': end,
            'hour': hour,
            'start_bg': start_bg,
            'nadir_bg': nadir_bg,
            'delta_mg_dl': float(delta),
            'bolus_u': dose,
            'simple_isf': float(simple_isf) if 5 < simple_isf < 500 else None,
            'curve_isf': float(curve_isf) if curve_isf and 5 < curve_isf < 500 else None,
            'coverage': float(coverage),
            'type': 'correction',
        })
    return windows


def _fit_response_curve(seg, dose, steps_per_hour):
    """Fit exponential decay: BG(t) = BG0 - amplitude*(1 - exp(-t/τ))."""
    valid = np.isfinite(seg)
    if np.sum(valid) < 6:
        return None

    t = np.arange(len(seg))[valid] / steps_per_hour
    bg = seg[valid]
    bg0 = bg[0]
    delta_bg = bg0 - bg

    # Grid search for τ
    best_r2, best_tau, best_amp = -999, 1.5, 0
    for tau in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]:
        basis = 1 - np.exp(-t / tau)
        denom = np.dot(basis, basis)
        if denom < 1e-10:
            continue
        amp = np.dot(basis, delta_bg) / denom
        if amp <= 0:
            continue
        pred = amp * basis
        ss_res = np.sum((delta_bg - pred)**2)
        ss_tot = np.sum((delta_bg - np.mean(delta_bg))**2)
        r2 = 1 - ss_res / max(ss_tot, 1e-10)
        if r2 > best_r2:
            best_r2, best_tau, best_amp = r2, tau, amp

    if best_amp > 0 and best_r2 > 0.1:
        return best_amp / dose
    return None


def _detect_meal_windows(df, bg, bolus, carbs):
    """Detect meal windows: carb entries with observable excursion."""
    N = len(bg)
    windows = []
    if carbs is None:
        return windows

    STEPS_PER_HOUR = 12
    OBSERVE_STEPS = 4 * STEPS_PER_HOUR

    carb_idxs = np.where(carbs > 2)[0]
    for ci in carb_idxs:
        end = min(ci + OBSERVE_STEPS, N)
        if end - ci < 12:
            continue

        seg = bg[ci:end]
        valid = np.isfinite(seg)
        coverage = np.mean(valid) if len(valid) > 0 else 0
        if coverage < 0.6:
            continue

        start_bg = float(bg[ci]) if np.isfinite(bg[ci]) else None
        if start_bg is None:
            continue

        finite_seg = seg.copy()
        finite_seg[~valid] = -999
        peak_rel = np.argmax(finite_seg)
        peak_bg = float(finite_seg[peak_rel])
        excursion = peak_bg - start_bg

        cg = float(carbs[ci])
        dose = float(bolus[ci]) if bolus is not None and ci < len(bolus) else 0

        hour = (ci % 288) / 12.0
        windows.append({
            'start_idx': ci, 'end_idx': end,
            'hour': hour,
            'start_bg': start_bg,
            'peak_bg': peak_bg,
            'excursion_mg_dl': float(excursion),
            'carbs_g': cg,
            'bolus_u': dose,
            'coverage': float(coverage),
            'type': 'meal',
        })
    return windows


def _prep_patient(pat):
    """Prepare patient data arrays."""
    df = pat['df']
    bg = df['glucose'].values.astype(float) if 'glucose' in df.columns else None
    if bg is None:
        return None
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else None
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else None
    return df, bg, bolus, carbs


# ── Settings Extraction ───────────────────────────────────────────────

def extract_settings(pat):
    """Extract optimal settings from a patient's natural experiment windows.

    Returns dict with per-period ISF, basal, CR recommendations + metadata.
    """
    prep = _prep_patient(pat)
    if prep is None:
        return None
    df, bg, bolus, carbs = prep

    profile_isf = _get_profile_isf(df)
    profile_basal = _get_profile_basal(df)
    profile_cr = _get_profile_cr(df)

    fasting = _detect_fasting_windows(df, bg, bolus, carbs)
    corrections = _detect_correction_windows(df, bg, bolus, carbs)
    meals = _detect_meal_windows(df, bg, bolus, carbs)

    result = {
        'profile_isf': profile_isf,
        'profile_basal': profile_basal,
        'profile_cr': profile_cr,
        'n_fasting': len(fasting),
        'n_corrections': len(corrections),
        'n_meals': len(meals),
        'periods': {},
    }

    # Per-period settings
    for period in PERIODS:
        lo, hi = PERIOD_HOURS[period]
        p_result = {'period': period, 'start_hour': lo}

        # ISF from corrections
        isf_vals = []
        for w in corrections:
            if _time_period(w['hour']) != period:
                continue
            isf = w.get('curve_isf') or w.get('simple_isf')
            if isf and 5 < isf < 500:
                isf_vals.append(isf)

        if len(isf_vals) >= 3:
            med, ci_lo, ci_hi = _bootstrap_ci(isf_vals)
            p_result['isf'] = round(med, 1)
            p_result['isf_ci'] = (round(ci_lo, 1), round(ci_hi, 1))
            p_result['isf_n'] = len(isf_vals)
        elif isf_vals:
            p_result['isf'] = round(float(np.median(isf_vals)), 1)
            p_result['isf_ci'] = None
            p_result['isf_n'] = len(isf_vals)
        else:
            # Fallback: use all corrections regardless of period
            all_isf = [w.get('curve_isf') or w.get('simple_isf') for w in corrections]
            all_isf = [v for v in all_isf if v and 5 < v < 500]
            if all_isf:
                p_result['isf'] = round(float(np.median(all_isf)), 1)
            else:
                p_result['isf'] = profile_isf
            p_result['isf_ci'] = None
            p_result['isf_n'] = 0

        # Basal from fasting drift
        drifts = [w['drift_mg_dl_per_hour'] for w in fasting
                  if _time_period(w['hour']) == period
                  and w.get('drift_mg_dl_per_hour') is not None
                  and math.isfinite(w['drift_mg_dl_per_hour'])]

        if len(drifts) >= 3:
            med_drift = float(np.median(drifts))
            adj = med_drift / max(profile_isf, 10)
            new_basal = max(0.05, profile_basal + adj)
            new_basal = max(profile_basal * 0.5, min(profile_basal * 1.5, new_basal))
            p_result['basal'] = round(new_basal, 3)
            p_result['basal_drift'] = round(med_drift, 2)
            p_result['basal_n'] = len(drifts)
        else:
            p_result['basal'] = profile_basal
            p_result['basal_drift'] = None
            p_result['basal_n'] = len(drifts)

        # CR from meals
        cr_vals = []
        for w in meals:
            if _time_period(w['hour']) != period:
                continue
            cg = w.get('carbs_g', 0)
            dose = w.get('bolus_u', 0)
            exc = w.get('excursion_mg_dl', 0)
            if not cg or cg < 5 or not dose or dose < 0.1:
                continue
            if exc is None or not math.isfinite(exc):
                continue
            add_ins = exc / max(profile_isf, 10)
            total = dose + add_ins
            if total > 0:
                eff_cr = cg / total
                if 1 < eff_cr < 100:
                    cr_vals.append(eff_cr)

        if len(cr_vals) >= 3:
            med, ci_lo, ci_hi = _bootstrap_ci(cr_vals)
            p_result['cr'] = round(med, 1)
            p_result['cr_ci'] = (round(ci_lo, 1), round(ci_hi, 1))
            p_result['cr_n'] = len(cr_vals)
        elif cr_vals:
            p_result['cr'] = round(float(np.median(cr_vals)), 1)
            p_result['cr_ci'] = None
            p_result['cr_n'] = len(cr_vals)
        else:
            p_result['cr'] = profile_cr
            p_result['cr_ci'] = None
            p_result['cr_n'] = 0

        result['periods'][period] = p_result

    # Global aggregates
    all_isf = [result['periods'][p]['isf'] for p in PERIODS if result['periods'][p].get('isf_n', 0) > 0]
    all_basal_n = [result['periods'][p]['basal_n'] for p in PERIODS]
    all_cr_n = [result['periods'][p].get('cr_n', 0) for p in PERIODS]

    result['global_isf'] = round(float(np.median(all_isf)), 1) if all_isf else profile_isf
    result['isf_ratio'] = round(result['global_isf'] / max(profile_isf, 1), 2)
    result['total_evidence'] = sum(all_basal_n) + sum(n for n in [result['n_corrections']] + all_cr_n)

    return result


def extract_settings_for_window(pat, start_idx, end_idx):
    """Extract settings from a sub-window of patient data."""
    import copy
    sub_pat = copy.deepcopy(pat)
    sub_pat['df'] = pat['df'].iloc[start_idx:end_idx].copy()
    sub_pat['df'].attrs = pat['df'].attrs.copy()
    return extract_settings(sub_pat)


# ── Mismatch Score ────────────────────────────────────────────────────

def compute_mismatch_score(settings, profile_isf, profile_basal, profile_cr):
    """Compute a scalar mismatch score between optimal and profile settings.

    Higher score = larger discrepancy between what the data says and what's configured.
    """
    if settings is None:
        return float('nan'), {}

    # ISF mismatch: ratio of effective to profile (>1 = underestimated)
    isf_ratio = settings.get('isf_ratio', 1.0)
    isf_mismatch = abs(isf_ratio - 1.0)  # 0 = perfect match

    # Basal mismatch: average absolute drift across periods
    basal_drifts = []
    for p in PERIODS:
        pd = settings['periods'].get(p, {})
        drift = pd.get('basal_drift')
        if drift is not None and math.isfinite(drift):
            basal_drifts.append(abs(drift))
    basal_mismatch = float(np.mean(basal_drifts)) if basal_drifts else 0.0

    # CR mismatch: ratio of effective to profile
    cr_vals = [settings['periods'][p]['cr'] for p in PERIODS
               if settings['periods'].get(p, {}).get('cr_n', 0) >= 3]
    if cr_vals:
        cr_ratio = float(np.median(cr_vals)) / max(profile_cr, 1)
        cr_mismatch = abs(cr_ratio - 1.0)
    else:
        cr_ratio = 1.0
        cr_mismatch = 0.0

    # Combined score (ISF-weighted since it contributes 85% of TIR gain)
    combined = 0.6 * isf_mismatch + 0.25 * (basal_mismatch / 5.0) + 0.15 * cr_mismatch

    details = {
        'isf_mismatch': round(isf_mismatch, 3),
        'isf_ratio': round(isf_ratio, 2),
        'basal_mismatch_mg_dl_h': round(basal_mismatch, 2),
        'cr_mismatch': round(cr_mismatch, 3),
        'cr_ratio': round(cr_ratio, 2),
        'combined_mismatch': round(combined, 3),
    }
    return combined, details


# ── Per-day metrics ───────────────────────────────────────────────────

def compute_daily_metrics(bg):
    """Compute per-day TIR/TBR/TAR/CV for a glucose array (288 steps/day)."""
    N = len(bg)
    STEPS_PER_DAY = 288
    days = []
    for d_start in range(0, N - STEPS_PER_DAY + 1, STEPS_PER_DAY):
        d_end = d_start + STEPS_PER_DAY
        seg = bg[d_start:d_end]
        valid_frac = np.mean(np.isfinite(seg))
        if valid_frac < 0.7:
            continue
        days.append({
            'start_idx': d_start,
            'end_idx': d_end,
            'tir': _compute_tir(seg),
            'tbr': _compute_tbr(seg),
            'tar': _compute_tar(seg),
            'cv': _compute_cv(seg),
            'mean_bg': float(np.nanmean(seg)),
            'valid_frac': float(valid_frac),
        })
    return days


# ══════════════════════════════════════════════════════════════════════
# EXP-1901: Train/Verify Settings Concordance
# ══════════════════════════════════════════════════════════════════════

def exp_1901_concordance(train_patients, verify_patients, verbose=True):
    """Compare settings derived from training vs verification data."""
    print("\n═══ EXP-1901: Train/Verify Settings Concordance ═══")

    results = []
    for tp in train_patients:
        name = tp['name']
        vp = next((v for v in verify_patients if v['name'] == name), None)
        if vp is None:
            if verbose:
                print(f"  {name}: no verification data, skip")
            continue

        if verbose:
            print(f"  {name}: extracting train settings...", end='', flush=True)
        train_settings = extract_settings(tp)
        if verbose:
            print(f" verify...", end='', flush=True)
        verify_settings = extract_settings(vp)
        if verbose:
            print(f" done")

        if train_settings is None or verify_settings is None:
            continue

        # Compare ISF
        train_isf = train_settings['global_isf']
        verify_isf = verify_settings['global_isf']
        isf_concordance = 1.0 - abs(train_isf - verify_isf) / max(train_isf, verify_isf, 1)

        # Compare per-period ISF
        period_isf_diffs = []
        for p in PERIODS:
            t_isf = train_settings['periods'].get(p, {}).get('isf')
            v_isf = verify_settings['periods'].get(p, {}).get('isf')
            if t_isf and v_isf and t_isf > 0 and v_isf > 0:
                period_isf_diffs.append(abs(t_isf - v_isf) / max(t_isf, v_isf))

        # Compare basal direction
        basal_agree = 0
        basal_total = 0
        for p in PERIODS:
            t_drift = train_settings['periods'].get(p, {}).get('basal_drift')
            v_drift = verify_settings['periods'].get(p, {}).get('basal_drift')
            if t_drift is not None and v_drift is not None:
                basal_total += 1
                if (t_drift > 0 and v_drift > 0) or (t_drift < 0 and v_drift < 0) or (abs(t_drift) < 1 and abs(v_drift) < 1):
                    basal_agree += 1

        r = {
            'patient': name,
            'train_isf': round(train_isf, 1),
            'verify_isf': round(verify_isf, 1),
            'isf_concordance': round(isf_concordance, 3),
            'period_isf_mean_diff': round(float(np.mean(period_isf_diffs)), 3) if period_isf_diffs else None,
            'train_isf_ratio': train_settings['isf_ratio'],
            'verify_isf_ratio': verify_settings['isf_ratio'],
            'basal_direction_agree': f"{basal_agree}/{basal_total}" if basal_total > 0 else "N/A",
            'train_evidence': train_settings['total_evidence'],
            'verify_evidence': verify_settings['total_evidence'],
            'train_n_fasting': train_settings['n_fasting'],
            'verify_n_fasting': verify_settings['n_fasting'],
            'train_n_corrections': train_settings['n_corrections'],
            'verify_n_corrections': verify_settings['n_corrections'],
        }
        results.append(r)

    # Summary
    if results:
        concordances = [r['isf_concordance'] for r in results]
        print(f"\n  ISF concordance: {np.mean(concordances):.3f} ± {np.std(concordances):.3f}")
        print(f"  Range: [{min(concordances):.3f}, {max(concordances):.3f}]")
        print(f"  Patients with concordance > 0.8: {sum(1 for c in concordances if c > 0.8)}/{len(concordances)}")

    return {
        'experiment': 'EXP-1901',
        'description': 'Train/Verify Settings Concordance',
        'n_patients': len(results),
        'mean_isf_concordance': round(float(np.mean([r['isf_concordance'] for r in results])), 3) if results else None,
        'patients': results,
    }


# ══════════════════════════════════════════════════════════════════════
# EXP-1903: Rolling Window Stability
# ══════════════════════════════════════════════════════════════════════

def exp_1903_rolling_stability(train_patients, verbose=True):
    """Measure temporal stability of settings across rolling 60-day windows."""
    print("\n═══ EXP-1903: Rolling Window Stability ═══")

    WINDOW_DAYS = 60
    STRIDE_DAYS = 30
    STEPS_PER_DAY = 288
    WINDOW_STEPS = WINDOW_DAYS * STEPS_PER_DAY
    STRIDE_STEPS = STRIDE_DAYS * STEPS_PER_DAY

    results = []
    for pat in train_patients:
        name = pat['name']
        N = len(pat['df'])

        if verbose:
            print(f"  {name}: {N/288:.0f} days, rolling windows...", end='', flush=True)

        windows = []
        for start in range(0, N - WINDOW_STEPS + 1, STRIDE_STEPS):
            end = start + WINDOW_STEPS
            settings = extract_settings_for_window(pat, start, end)
            if settings:
                windows.append({
                    'start_day': start // STEPS_PER_DAY,
                    'end_day': end // STEPS_PER_DAY,
                    'global_isf': settings['global_isf'],
                    'isf_ratio': settings['isf_ratio'],
                    'n_corrections': settings['n_corrections'],
                    'n_fasting': settings['n_fasting'],
                })

        if verbose:
            print(f" {len(windows)} windows")

        if len(windows) < 2:
            continue

        # Measure stability: coefficient of variation of ISF across windows
        isf_values = [w['global_isf'] for w in windows]
        isf_cv = float(np.std(isf_values) / max(np.mean(isf_values), 1) * 100)

        # Serial correlation: does ISF trend over time?
        if len(isf_values) >= 3:
            from scipy.stats import pearsonr
            days = [w['start_day'] for w in windows]
            corr, pval = pearsonr(days, isf_values)
        else:
            corr, pval = 0.0, 1.0

        # ISF range
        isf_range = max(isf_values) - min(isf_values)

        results.append({
            'patient': name,
            'n_windows': len(windows),
            'isf_cv_pct': round(isf_cv, 1),
            'isf_temporal_corr': round(float(corr), 3),
            'isf_temporal_pval': round(float(pval), 4),
            'isf_range': round(isf_range, 1),
            'isf_mean': round(float(np.mean(isf_values)), 1),
            'isf_values': [round(v, 1) for v in isf_values],
            'windows': windows,
        })

    # Summary
    if results:
        cvs = [r['isf_cv_pct'] for r in results]
        print(f"\n  ISF CV across windows: {np.mean(cvs):.1f}% ± {np.std(cvs):.1f}%")
        print(f"  Stable (CV < 10%): {sum(1 for c in cvs if c < 10)}/{len(cvs)}")
        sig_drift = sum(1 for r in results if r['isf_temporal_pval'] < 0.05)
        print(f"  Significant temporal drift (p<0.05): {sig_drift}/{len(results)}")

    return {
        'experiment': 'EXP-1903',
        'description': 'Rolling 60-day window settings stability',
        'n_patients': len(results),
        'mean_isf_cv_pct': round(float(np.mean([r['isf_cv_pct'] for r in results])), 1) if results else None,
        'patients': results,
    }


# ══════════════════════════════════════════════════════════════════════
# EXP-1905: Mismatch → TIR Relationship (KEY EXPERIMENT)
# ══════════════════════════════════════════════════════════════════════

def exp_1905_mismatch_tir(train_patients, verbose=True):
    """Correlate settings mismatch with per-window TIR.

    For each patient, compute optimal settings from full training data,
    then measure per-30-day-window mismatch and TIR. If larger mismatch
    corresponds to worse TIR, our recommendations are validated.
    """
    print("\n═══ EXP-1905: Mismatch → TIR Relationship ═══")

    WINDOW_DAYS = 30
    STRIDE_DAYS = 15
    STEPS_PER_DAY = 288
    WINDOW_STEPS = WINDOW_DAYS * STEPS_PER_DAY
    STRIDE_STEPS = STRIDE_DAYS * STEPS_PER_DAY

    results = []
    all_mismatch = []
    all_tir = []

    for pat in train_patients:
        name = pat['name']
        df = pat['df']
        bg = df['glucose'].values.astype(float) if 'glucose' in df.columns else None
        if bg is None:
            continue
        N = len(bg)

        profile_isf = _get_profile_isf(df)
        profile_basal = _get_profile_basal(df)
        profile_cr = _get_profile_cr(df)

        if verbose:
            print(f"  {name}: computing full-data optimal settings...", end='', flush=True)

        full_settings = extract_settings(pat)
        if full_settings is None:
            if verbose:
                print(" failed")
            continue

        # Full-data optimal ISF for optimal-relative mismatch
        optimal_isf = full_settings['global_isf']

        # Now compute per-window mismatch and TIR
        windows = []
        for start in range(0, N - WINDOW_STEPS + 1, STRIDE_STEPS):
            end = start + WINDOW_STEPS
            seg = bg[start:end]
            valid_frac = np.mean(np.isfinite(seg))
            if valid_frac < 0.7:
                continue

            tir = _compute_tir(seg)
            tbr = _compute_tbr(seg)
            tar = _compute_tar(seg)
            cv = _compute_cv(seg)

            # Per-window effective settings
            window_settings = extract_settings_for_window(pat, start, end)
            if window_settings is None:
                continue

            # Profile-relative mismatch (original)
            mismatch, details = compute_mismatch_score(
                window_settings, profile_isf, profile_basal, profile_cr)

            # Optimal-relative mismatch: how far is this window from full-data optimal?
            window_isf = window_settings['global_isf']
            opt_isf_deviation = abs(window_isf - optimal_isf) / max(optimal_isf, 1)
            details['opt_isf_deviation'] = round(opt_isf_deviation, 3)
            details['window_isf'] = round(window_isf, 1)

            windows.append({
                'start_day': start // STEPS_PER_DAY,
                'end_day': end // STEPS_PER_DAY,
                'tir': round(tir, 1),
                'tbr': round(tbr, 1),
                'tar': round(tar, 1),
                'cv': round(cv, 1),
                'mismatch': round(mismatch, 3),
                'opt_mismatch': round(opt_isf_deviation, 3),
                **details,
            })
            all_mismatch.append(mismatch)
            all_tir.append(tir)

        if verbose:
            print(f" {len(windows)} windows")

        if len(windows) < 3:
            continue

        # Within-patient correlation
        w_mismatch = [w['mismatch'] for w in windows]
        w_tir = [w['tir'] for w in windows]

        from scipy.stats import pearsonr, spearmanr
        if len(w_mismatch) >= 3:
            pr, p_pval = pearsonr(w_mismatch, w_tir)
            sr, s_pval = spearmanr(w_mismatch, w_tir)
        else:
            pr, p_pval, sr, s_pval = 0, 1, 0, 1

        # ISF mismatch specifically
        w_isf_mm = [w['isf_mismatch'] for w in windows]
        w_tar = [w['tar'] for w in windows]
        w_opt_mm = [w['opt_mismatch'] for w in windows]
        if len(w_isf_mm) >= 3:
            isf_r, isf_p = pearsonr(w_isf_mm, w_tir)
            isf_tar_r, isf_tar_p = pearsonr(w_isf_mm, w_tar)
        else:
            isf_r, isf_p, isf_tar_r, isf_tar_p = 0, 1, 0, 1

        # Optimal-relative mismatch (KEY: does deviation from optimal predict TIR?)
        if len(w_opt_mm) >= 3:
            opt_r, opt_p = pearsonr(w_opt_mm, w_tir)
            opt_sr, opt_sp = spearmanr(w_opt_mm, w_tir)
        else:
            opt_r, opt_p, opt_sr, opt_sp = 0, 1, 0, 1

        results.append({
            'patient': name,
            'n_windows': len(windows),
            'pearson_r': round(float(pr), 3),
            'pearson_p': round(float(p_pval), 4),
            'spearman_r': round(float(sr), 3),
            'spearman_p': round(float(s_pval), 4),
            'isf_tir_r': round(float(isf_r), 3),
            'isf_tir_p': round(float(isf_p), 4),
            'isf_tar_r': round(float(isf_tar_r), 3),
            'isf_tar_p': round(float(isf_tar_p), 4),
            'opt_mismatch_tir_r': round(float(opt_r), 3),
            'opt_mismatch_tir_p': round(float(opt_p), 4),
            'opt_mismatch_tir_sr': round(float(opt_sr), 3),
            'mean_tir': round(float(np.mean(w_tir)), 1),
            'mean_mismatch': round(float(np.mean(w_mismatch)), 3),
            'profile_isf': profile_isf,
            'optimal_isf': full_settings['global_isf'],
            'isf_ratio': full_settings['isf_ratio'],
            'windows': windows,
        })

    # Population-level analysis
    if all_mismatch and len(all_mismatch) >= 5:
        from scipy.stats import pearsonr, spearmanr
        pop_pr, pop_pp = pearsonr(all_mismatch, all_tir)
        pop_sr, pop_sp = spearmanr(all_mismatch, all_tir)
    else:
        pop_pr, pop_pp, pop_sr, pop_sp = 0, 1, 0, 1

    # Tercile analysis: top/bottom third of mismatch
    if all_mismatch:
        sorted_pairs = sorted(zip(all_mismatch, all_tir))
        n = len(sorted_pairs)
        low_mm = sorted_pairs[:n//3]
        high_mm = sorted_pairs[-n//3:]
        low_tir = float(np.mean([p[1] for p in low_mm]))
        high_tir = float(np.mean([p[1] for p in high_mm]))
        tir_gap = low_tir - high_tir
    else:
        low_tir, high_tir, tir_gap = 0, 0, 0

    print(f"\n  Population mismatch→TIR: r={pop_pr:.3f} (p={pop_pp:.4f})")
    print(f"  Low-mismatch TIR: {low_tir:.1f}%, High-mismatch TIR: {high_tir:.1f}%, Gap: {tir_gap:+.1f}pp")
    within_neg = sum(1 for r in results if r['pearson_r'] < 0)
    within_opt_neg = sum(1 for r in results if r.get('opt_mismatch_tir_r', 0) < 0)
    print(f"  Within-patient negative (profile mismatch): {within_neg}/{len(results)}")
    print(f"  Within-patient negative (optimal mismatch): {within_opt_neg}/{len(results)}")

    return {
        'experiment': 'EXP-1905',
        'description': 'Mismatch → TIR relationship (key validation)',
        'n_patients': len(results),
        'n_windows_total': len(all_mismatch),
        'population_pearson_r': round(float(pop_pr), 3),
        'population_pearson_p': round(float(pop_pp), 4),
        'population_spearman_r': round(float(pop_sr), 3),
        'population_spearman_p': round(float(pop_sp), 4),
        'low_mismatch_tir': round(low_tir, 1),
        'high_mismatch_tir': round(high_tir, 1),
        'tir_gap_pp': round(tir_gap, 1),
        'within_patient_negative': within_neg,
        'within_patient_opt_negative': within_opt_neg,
        'patients': results,
    }


# ══════════════════════════════════════════════════════════════════════
# EXP-1907: 5-Fold Temporal Cross-Validation
# ══════════════════════════════════════════════════════════════════════

def exp_1907_temporal_cv(train_patients, verbose=True):
    """5-fold temporal CV: train settings on 4 folds, measure stability on 5th."""
    print("\n═══ EXP-1907: 5-Fold Temporal Cross-Validation ═══")

    N_FOLDS = 5
    results = []

    for pat in train_patients:
        name = pat['name']
        N = len(pat['df'])
        fold_size = N // N_FOLDS

        if verbose:
            print(f"  {name}: {N_FOLDS}-fold CV ({fold_size/288:.0f} days/fold)...", end='', flush=True)

        fold_settings = []
        for fold in range(N_FOLDS):
            # Test fold
            test_start = fold * fold_size
            test_end = test_start + fold_size

            # Train on everything except this fold
            import copy
            train_df_parts = []
            if test_start > 0:
                train_df_parts.append(pat['df'].iloc[:test_start])
            if test_end < N:
                train_df_parts.append(pat['df'].iloc[test_end:])

            if not train_df_parts:
                continue

            import pandas as pd
            train_df = pd.concat(train_df_parts)
            train_df.attrs = pat['df'].attrs.copy()

            train_pat = copy.deepcopy(pat)
            train_pat['df'] = train_df

            settings = extract_settings(train_pat)
            if settings is None:
                continue

            # Also compute TIR on test fold
            test_bg = pat['df'].iloc[test_start:test_end]['glucose'].values.astype(float)
            test_tir = _compute_tir(test_bg)

            fold_settings.append({
                'fold': fold,
                'train_days': len(train_df) / 288,
                'test_days': fold_size / 288,
                'global_isf': settings['global_isf'],
                'isf_ratio': settings['isf_ratio'],
                'n_corrections': settings['n_corrections'],
                'test_tir': round(test_tir, 1),
            })

        if verbose:
            print(f" done ({len(fold_settings)} folds)")

        if len(fold_settings) < 3:
            continue

        isf_values = [f['global_isf'] for f in fold_settings]
        isf_cv = float(np.std(isf_values) / max(np.mean(isf_values), 1) * 100)
        isf_range = max(isf_values) - min(isf_values)

        results.append({
            'patient': name,
            'n_folds': len(fold_settings),
            'isf_cv_pct': round(isf_cv, 1),
            'isf_range': round(isf_range, 1),
            'isf_mean': round(float(np.mean(isf_values)), 1),
            'isf_std': round(float(np.std(isf_values)), 1),
            'folds': fold_settings,
        })

    if results:
        cvs = [r['isf_cv_pct'] for r in results]
        print(f"\n  ISF CV across folds: {np.mean(cvs):.1f}% ± {np.std(cvs):.1f}%")
        stable = sum(1 for c in cvs if c < 15)
        print(f"  Stable (CV < 15%): {stable}/{len(cvs)}")

    return {
        'experiment': 'EXP-1907',
        'description': '5-fold temporal cross-validation of settings',
        'n_patients': len(results),
        'mean_isf_cv_pct': round(float(np.mean([r['isf_cv_pct'] for r in results])), 1) if results else None,
        'patients': results,
    }


# ══════════════════════════════════════════════════════════════════════
# EXP-1909: Verification Day TIR Prediction
# ══════════════════════════════════════════════════════════════════════

def exp_1909_verification_prediction(train_patients, verify_patients, verbose=True):
    """Predict verification-day TIR using training-derived settings mismatch.

    If patients with larger ISF mismatch (profile vs optimal) also have
    worse TIR on held-out verification days, the relationship is real.
    """
    print("\n═══ EXP-1909: Verification Day TIR Prediction ═══")

    results = []
    patient_mismatches = []
    patient_verify_tirs = []
    patient_train_tirs = []

    for tp in train_patients:
        name = tp['name']
        vp = next((v for v in verify_patients if v['name'] == name), None)
        if vp is None:
            continue

        df = tp['df']
        profile_isf = _get_profile_isf(df)
        profile_basal = _get_profile_basal(df)
        profile_cr = _get_profile_cr(df)

        if verbose:
            print(f"  {name}: train settings + verify TIR...", end='', flush=True)

        # Training-derived optimal settings
        train_settings = extract_settings(tp)
        if train_settings is None:
            if verbose:
                print(" skip")
            continue

        # Training TIR
        train_bg = df['glucose'].values.astype(float) if 'glucose' in df.columns else None
        train_tir = _compute_tir(train_bg) if train_bg is not None else float('nan')

        # Verification TIR
        verify_bg = vp['df']['glucose'].values.astype(float) if 'glucose' in vp['df'].columns else None
        verify_tir = _compute_tir(verify_bg) if verify_bg is not None else float('nan')
        verify_tbr = _compute_tbr(verify_bg) if verify_bg is not None else float('nan')
        verify_tar = _compute_tar(verify_bg) if verify_bg is not None else float('nan')
        verify_cv = _compute_cv(verify_bg) if verify_bg is not None else float('nan')

        # Mismatch score
        mismatch, details = compute_mismatch_score(
            train_settings, profile_isf, profile_basal, profile_cr)

        if verbose:
            print(f" TIR={verify_tir:.1f}%, mismatch={mismatch:.3f}")

        r = {
            'patient': name,
            'train_tir': round(train_tir, 1),
            'verify_tir': round(verify_tir, 1),
            'verify_tbr': round(verify_tbr, 1),
            'verify_tar': round(verify_tar, 1),
            'verify_cv': round(verify_cv, 1),
            'mismatch': round(mismatch, 3),
            'isf_ratio': train_settings['isf_ratio'],
            'profile_isf': profile_isf,
            'optimal_isf': train_settings['global_isf'],
            **details,
        }
        results.append(r)

        if math.isfinite(mismatch) and math.isfinite(verify_tir):
            patient_mismatches.append(mismatch)
            patient_verify_tirs.append(verify_tir)
            patient_train_tirs.append(train_tir)

    # Cross-patient correlation
    if len(patient_mismatches) >= 4:
        from scipy.stats import pearsonr, spearmanr
        pr, pp = pearsonr(patient_mismatches, patient_verify_tirs)
        sr, sp = spearmanr(patient_mismatches, patient_verify_tirs)

        # Also: does train TIR predict verify TIR?
        tir_pr, tir_pp = pearsonr(patient_train_tirs, patient_verify_tirs)
    else:
        pr, pp, sr, sp = 0, 1, 0, 1
        tir_pr, tir_pp = 0, 1

    # ISF ratio → verify TIR
    isf_ratios = [r['isf_ratio'] for r in results if math.isfinite(r.get('verify_tir', float('nan')))]
    verify_tirs = [r['verify_tir'] for r in results if math.isfinite(r.get('verify_tir', float('nan')))]
    if len(isf_ratios) >= 4:
        from scipy.stats import pearsonr
        isf_r, isf_p = pearsonr(isf_ratios, verify_tirs)
    else:
        isf_r, isf_p = 0, 1

    print(f"\n  Mismatch → Verify TIR: r={pr:.3f} (p={pp:.4f})")
    print(f"  ISF ratio → Verify TIR: r={isf_r:.3f} (p={isf_p:.4f})")
    print(f"  Train TIR → Verify TIR: r={tir_pr:.3f} (p={tir_pp:.4f})")

    return {
        'experiment': 'EXP-1909',
        'description': 'Verification day TIR prediction from training mismatch',
        'n_patients': len(results),
        'mismatch_verify_tir_r': round(float(pr), 3),
        'mismatch_verify_tir_p': round(float(pp), 4),
        'isf_ratio_verify_tir_r': round(float(isf_r), 3),
        'isf_ratio_verify_tir_p': round(float(isf_p), 4),
        'train_verify_tir_r': round(float(tir_pr), 3),
        'train_verify_tir_p': round(float(tir_pp), 4),
        'patients': results,
    }


# ══════════════════════════════════════════════════════════════════════
# Visualizations
# ══════════════════════════════════════════════════════════════════════

def generate_visualizations(r1901, r1903, r1905, r1907, r1909):
    """Generate fig66-fig70 visualizations."""
    print("\n═══ Generating Visualizations ═══")

    # fig66: Train/Verify ISF Concordance
    if r1901 and r1901['patients']:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        # Left: scatter plot train vs verify ISF
        ax = axes[0]
        patients = r1901['patients']
        train_isf = [p['train_isf'] for p in patients]
        verify_isf = [p['verify_isf'] for p in patients]
        names = [p['patient'] for p in patients]

        ax.scatter(train_isf, verify_isf, s=80, c='steelblue', edgecolors='black', zorder=3)
        for i, name in enumerate(names):
            ax.annotate(name, (train_isf[i], verify_isf[i]),
                       textcoords="offset points", xytext=(5, 5), fontsize=9)

        lims = [min(min(train_isf), min(verify_isf)) * 0.8,
                max(max(train_isf), max(verify_isf)) * 1.2]
        ax.plot(lims, lims, 'k--', alpha=0.3, label='Perfect concordance')
        ax.set_xlabel('Training ISF (mg/dL/U)')
        ax.set_ylabel('Verification ISF (mg/dL/U)')
        ax.set_title(f'EXP-1901: Train vs Verify ISF\n(concordance={r1901["mean_isf_concordance"]:.3f})')
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Right: concordance bar chart
        ax = axes[1]
        concs = [p['isf_concordance'] for p in patients]
        colors = ['forestgreen' if c > 0.8 else 'orange' if c > 0.6 else 'red' for c in concs]
        ax.barh(names, concs, color=colors, edgecolor='black')
        ax.axvline(0.8, color='green', linestyle='--', alpha=0.5, label='Good (>0.8)')
        ax.set_xlabel('ISF Concordance')
        ax.set_title('Per-Patient Concordance')
        ax.set_xlim(0, 1.05)
        ax.legend()
        ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        path = VIZ_DIR / 'fig66_train_verify_concordance.png'
        plt.savefig(path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → {path}")

    # fig67: Rolling stability
    if r1903 and r1903['patients']:
        n_patients = len(r1903['patients'])
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        # Left: ISF trajectories over time
        ax = axes[0]
        for pr in r1903['patients']:
            windows = pr['windows']
            days = [w['start_day'] for w in windows]
            isf_vals = [w['global_isf'] for w in windows]
            ax.plot(days, isf_vals, 'o-', label=pr['patient'], markersize=4)
        ax.set_xlabel('Start Day')
        ax.set_ylabel('Effective ISF (mg/dL/U)')
        ax.set_title('EXP-1903: ISF Temporal Stability')
        ax.legend(fontsize=8, ncol=2)
        ax.grid(True, alpha=0.3)

        # Right: CV distribution
        ax = axes[1]
        cvs = [pr['isf_cv_pct'] for pr in r1903['patients']]
        names = [pr['patient'] for pr in r1903['patients']]
        colors = ['forestgreen' if c < 10 else 'orange' if c < 20 else 'red' for c in cvs]
        ax.barh(names, cvs, color=colors, edgecolor='black')
        ax.axvline(10, color='green', linestyle='--', alpha=0.5, label='Stable (<10%)')
        ax.axvline(20, color='orange', linestyle='--', alpha=0.5, label='Moderate (<20%)')
        ax.set_xlabel('ISF CV (%)')
        ax.set_title(f'ISF Variability (mean={r1903["mean_isf_cv_pct"]:.1f}%)')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        path = VIZ_DIR / 'fig67_rolling_stability.png'
        plt.savefig(path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → {path}")

    # fig68: Mismatch → TIR (KEY FIGURE)
    if r1905 and r1905['patients']:
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))

        # Left: Population scatter
        ax = axes[0]
        all_mm, all_tir = [], []
        for pr in r1905['patients']:
            mm = [w['mismatch'] for w in pr['windows']]
            tir = [w['tir'] for w in pr['windows']]
            ax.scatter(mm, tir, s=20, alpha=0.4, label=pr['patient'])
            all_mm.extend(mm)
            all_tir.extend(tir)

        if all_mm:
            z = np.polyfit(all_mm, all_tir, 1)
            x_line = np.linspace(min(all_mm), max(all_mm), 50)
            ax.plot(x_line, np.polyval(z, x_line), 'r-', linewidth=2,
                   label=f'r={r1905["population_pearson_r"]:.3f}')

        ax.set_xlabel('Settings Mismatch Score')
        ax.set_ylabel('TIR (%)')
        ax.set_title(f'EXP-1905: Mismatch → TIR\n(r={r1905["population_pearson_r"]:.3f}, p={r1905["population_pearson_p"]:.4f})')
        ax.legend(fontsize=7, ncol=2)
        ax.grid(True, alpha=0.3)

        # Middle: Tercile comparison
        ax = axes[1]
        ax.bar(['Low\nMismatch', 'High\nMismatch'],
               [r1905['low_mismatch_tir'], r1905['high_mismatch_tir']],
               color=['forestgreen', 'tomato'], edgecolor='black')
        ax.set_ylabel('TIR (%)')
        gap = r1905['tir_gap_pp']
        ax.set_title(f'Tercile Comparison\nGap: {gap:+.1f}pp')
        ax.grid(True, alpha=0.3, axis='y')

        # Right: Per-patient within-correlation
        ax = axes[2]
        names = [pr['patient'] for pr in r1905['patients']]
        corrs = [pr['pearson_r'] for pr in r1905['patients']]
        pvals = [pr['pearson_p'] for pr in r1905['patients']]
        colors = ['forestgreen' if r < -0.1 and p < 0.1 else
                  'lightgreen' if r < 0 else
                  'tomato' for r, p in zip(corrs, pvals)]
        ax.barh(names, corrs, color=colors, edgecolor='black')
        ax.axvline(0, color='black', linewidth=0.5)
        ax.set_xlabel('Mismatch-TIR Correlation (r)')
        ax.set_title('Within-Patient Correlations\n(negative = validation)')
        ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        path = VIZ_DIR / 'fig68_mismatch_tir.png'
        plt.savefig(path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → {path}")

    # fig69: Cross-validation stability
    if r1907 and r1907['patients']:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        ax = axes[0]
        for pr in r1907['patients']:
            folds = pr['folds']
            fold_nums = [f['fold'] for f in folds]
            isf_vals = [f['global_isf'] for f in folds]
            ax.plot(fold_nums, isf_vals, 'o-', label=pr['patient'], markersize=6)
        ax.set_xlabel('Fold')
        ax.set_ylabel('ISF (mg/dL/U)')
        ax.set_title(f'EXP-1907: 5-Fold CV ISF Stability\n(mean CV={r1907["mean_isf_cv_pct"]:.1f}%)')
        ax.legend(fontsize=8, ncol=2)
        ax.grid(True, alpha=0.3)

        ax = axes[1]
        cvs = [pr['isf_cv_pct'] for pr in r1907['patients']]
        names = [pr['patient'] for pr in r1907['patients']]
        colors = ['forestgreen' if c < 15 else 'orange' if c < 25 else 'red' for c in cvs]
        ax.barh(names, cvs, color=colors, edgecolor='black')
        ax.axvline(15, color='green', linestyle='--', alpha=0.5, label='Stable (<15%)')
        ax.set_xlabel('ISF CV across folds (%)')
        ax.set_title('Per-Patient Fold Stability')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='x')

        plt.tight_layout()
        path = VIZ_DIR / 'fig69_cv_stability.png'
        plt.savefig(path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → {path}")

    # fig70: Verification prediction dashboard
    if r1909 and r1909['patients']:
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))

        patients = r1909['patients']
        names = [p['patient'] for p in patients]
        mismatches = [p['mismatch'] for p in patients]
        verify_tirs = [p['verify_tir'] for p in patients]
        train_tirs = [p['train_tir'] for p in patients]
        isf_ratios = [p['isf_ratio'] for p in patients]

        # Left: mismatch vs verify TIR
        ax = axes[0]
        ax.scatter(mismatches, verify_tirs, s=80, c='steelblue', edgecolors='black', zorder=3)
        for i, name in enumerate(names):
            ax.annotate(name, (mismatches[i], verify_tirs[i]),
                       textcoords="offset points", xytext=(5, 5), fontsize=9)
        if len(mismatches) >= 3:
            z = np.polyfit(mismatches, verify_tirs, 1)
            x_line = np.linspace(min(mismatches), max(mismatches), 50)
            ax.plot(x_line, np.polyval(z, x_line), 'r-', linewidth=2)
        ax.set_xlabel('Settings Mismatch')
        ax.set_ylabel('Verification TIR (%)')
        ax.set_title(f'EXP-1909: Mismatch → Verify TIR\n(r={r1909["mismatch_verify_tir_r"]:.3f})')
        ax.grid(True, alpha=0.3)

        # Middle: train vs verify TIR
        ax = axes[1]
        ax.scatter(train_tirs, verify_tirs, s=80, c='darkorange', edgecolors='black', zorder=3)
        for i, name in enumerate(names):
            ax.annotate(name, (train_tirs[i], verify_tirs[i]),
                       textcoords="offset points", xytext=(5, 5), fontsize=9)
        lims = [min(min(train_tirs), min(verify_tirs)) - 5,
                max(max(train_tirs), max(verify_tirs)) + 5]
        ax.plot(lims, lims, 'k--', alpha=0.3)
        ax.set_xlabel('Training TIR (%)')
        ax.set_ylabel('Verification TIR (%)')
        ax.set_title(f'Train vs Verify TIR\n(r={r1909["train_verify_tir_r"]:.3f})')
        ax.grid(True, alpha=0.3)

        # Right: ISF ratio vs verify TIR
        ax = axes[2]
        colors = ['tomato' if r > 2 else 'orange' if r > 1.5 else 'forestgreen' for r in isf_ratios]
        ax.scatter(isf_ratios, verify_tirs, s=80, c=colors, edgecolors='black', zorder=3)
        for i, name in enumerate(names):
            ax.annotate(name, (isf_ratios[i], verify_tirs[i]),
                       textcoords="offset points", xytext=(5, 5), fontsize=9)
        ax.axvline(1.0, color='green', linestyle='--', alpha=0.5, label='Perfect calibration')
        ax.set_xlabel('ISF Ratio (effective/profile)')
        ax.set_ylabel('Verification TIR (%)')
        ax.set_title(f'ISF Calibration → Verify TIR\n(r={r1909["isf_ratio_verify_tir_r"]:.3f})')
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        path = VIZ_DIR / 'fig70_verification_prediction.png'
        plt.savefig(path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"  → {path}")


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='EXP-1901: Retrospective Validation')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--experiment', type=int, default=0,
                       help='Run specific experiment (1901/1903/1905/1907/1909) or 0 for all')
    args = parser.parse_args()

    print("═══ EXP-1901 Series: Retrospective Split-Half Validation ═══")
    print(f"  Max patients: {args.max_patients}")

    # Load both splits
    print("\n── Loading training data ──")
    train_patients = load_patients_split(args.max_patients, split='training')
    print(f"  Loaded {len(train_patients)} training patients")

    print("\n── Loading verification data ──")
    verify_patients = load_patients_split(args.max_patients, split='verification')
    print(f"  Loaded {len(verify_patients)} verification patients")

    all_results = {}

    if args.experiment == 0 or args.experiment == 1901:
        r1901 = exp_1901_concordance(train_patients, verify_patients)
        all_results['EXP-1901'] = r1901
    else:
        r1901 = None

    if args.experiment == 0 or args.experiment == 1903:
        r1903 = exp_1903_rolling_stability(train_patients)
        all_results['EXP-1903'] = r1903
    else:
        r1903 = None

    if args.experiment == 0 or args.experiment == 1905:
        r1905 = exp_1905_mismatch_tir(train_patients)
        all_results['EXP-1905'] = r1905
    else:
        r1905 = None

    if args.experiment == 0 or args.experiment == 1907:
        r1907 = exp_1907_temporal_cv(train_patients)
        all_results['EXP-1907'] = r1907
    else:
        r1907 = None

    if args.experiment == 0 or args.experiment == 1909:
        r1909 = exp_1909_verification_prediction(train_patients, verify_patients)
        all_results['EXP-1909'] = r1909
    else:
        r1909 = None

    # Generate visualizations
    generate_visualizations(r1901, r1903, r1905, r1907, r1909)

    # Save results
    results_path = RESULTS_DIR / 'exp-1901_retrospective_validation.json'
    with open(results_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  → Saved {results_path}")

    # Print summary
    print("\n" + "═" * 60)
    print("SUMMARY")
    print("═" * 60)

    if r1901:
        print(f"\n  EXP-1901 Concordance: {r1901['mean_isf_concordance']:.3f}")

    if r1903:
        print(f"  EXP-1903 Stability: ISF CV = {r1903['mean_isf_cv_pct']:.1f}%")

    if r1905:
        print(f"  EXP-1905 Mismatch→TIR: r={r1905['population_pearson_r']:.3f} (p={r1905['population_pearson_p']:.4f})")
        print(f"    Low-mismatch TIR: {r1905['low_mismatch_tir']:.1f}% vs High: {r1905['high_mismatch_tir']:.1f}% (Δ={r1905['tir_gap_pp']:+.1f}pp)")

    if r1907:
        print(f"  EXP-1907 5-Fold CV: ISF CV = {r1907['mean_isf_cv_pct']:.1f}%")

    if r1909:
        print(f"  EXP-1909 Verify Prediction: mismatch→TIR r={r1909['mismatch_verify_tir_r']:.3f}")
        print(f"    Train→Verify TIR: r={r1909['train_verify_tir_r']:.3f}")

    print("\n  VALIDATION VERDICT:")
    if r1905 and r1905['population_pearson_r'] < -0.1:
        print("  ✓ Settings mismatch NEGATIVELY correlated with TIR")
        print("    → Recommendations are VALIDATED: closer to optimal = better outcomes")
    elif r1905:
        print(f"  ? Mismatch→TIR r={r1905['population_pearson_r']:.3f} — inconclusive")
    if r1909 and r1909['mismatch_verify_tir_r'] < -0.1:
        print("  ✓ Training mismatch predicts verification TIR")
        print("    → Out-of-sample validation PASSED")
    elif r1909:
        print(f"  ? Out-of-sample r={r1909['mismatch_verify_tir_r']:.3f} — inconclusive")

    return all_results


if __name__ == '__main__':
    main()
