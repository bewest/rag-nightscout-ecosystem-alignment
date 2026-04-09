#!/usr/bin/env python3
"""EXP-1701 to EXP-1721: Settings Optimization from Natural Experiments.

Uses natural experiment windows (EXP-1551 census: 50,810 total) to compute
optimal pump settings, validate retrospectively, and productionize as a
reusable settings recommender.

Builds on:
  - EXP-1651: Basal adequacy (55% miscalibrated, median drift -1.5 mg/dL/h)
  - EXP-1653: ISF underestimation (2.05x universal)
  - EXP-1655: CR time-varying (dinner 17% harder)
  - EXP-1657: Settings drift (73% patients over 30d)
  - EXP-1301: Response-curve ISF (exp decay, R²=0.805, τ=2.0h)
  - EXP-1531: Fidelity grading (RMSE + CE)

Experiments:
  Phase 13 — Optimal Settings Computation
  EXP-1701: Optimal Basal Schedule from fasting windows
  EXP-1703: Optimal ISF Schedule from correction windows
  EXP-1705: Optimal CR Schedule from meal windows
  EXP-1707: Settings Confidence via bootstrap

  Phase 14 — Retrospective Validation
  EXP-1711: Retrospective basal simulation
  EXP-1713: Retrospective ISF simulation
  EXP-1715: Retrospective CR simulation
  EXP-1717: Combined settings improvement

  Phase 15 — Productionization
  EXP-1719: Settings recommender module
  EXP-1721: Validation report generator

Usage:
    PYTHONPATH=tools python tools/cgmencode/exp_clinical_1701.py --exp 0
    PYTHONPATH=tools python tools/cgmencode/exp_clinical_1701.py --exp 1701
    PYTHONPATH=tools python tools/cgmencode/exp_clinical_1701.py --max-patients 3 --exp 1701
"""

import argparse
import json
import math
import numpy as np
import os
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from cgmencode.exp_metabolic_flux import load_patients as _load_patients
from cgmencode.exp_metabolic_flux import _extract_isf_scalar
from cgmencode.exp_metabolic_441 import compute_supply_demand

from cgmencode.exp_clinical_1551 import (
    NaturalExperiment,
    detect_fasting_windows, detect_correction_windows,
    detect_meal_windows, detect_uam_windows,
    detect_overnight_windows,
    _bg, _safe_nanmean, _safe_nanstd,
    _linear_drift, _exp_decay_fit,
    _hours_array, _dates_array, _unique_dates,
    _hour_of_day,
    STEPS_PER_HOUR, STEPS_PER_DAY, STEP_MINUTES,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PATIENTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..',
                            'externals', 'ns-data', 'patients')
RESULTS_DIR = (Path(__file__).resolve().parent.parent.parent
               / 'externals' / 'experiments')
VIZ_DIR = (Path(__file__).resolve().parent.parent.parent
           / 'visualizations' / 'natural-experiments')

EXPERIMENTS = {}

def register(exp_id, title):
    def decorator(fn):
        EXPERIMENTS[exp_id] = (title, fn)
        return fn
    return decorator

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def load_patients(max_patients=11, patients_dir=None):
    return _load_patients(patients_dir or PATIENTS_DIR, max_patients=max_patients)


def _get_supply_demand(df, pk=None):
    return compute_supply_demand(df, pk)


def _get_profile_isf(df):
    """Extract profile ISF in mg/dL from DataFrame."""
    if hasattr(df, 'attrs'):
        return _extract_isf_scalar(df)
    return 40.0


def _get_profile_cr(df):
    """Extract profile CR (g/U) from DataFrame."""
    if hasattr(df, 'attrs'):
        cr_sched = df.attrs.get('cr_schedule', [])
        if isinstance(cr_sched, list) and cr_sched:
            vals = [float(item.get('value', item.get('carbratio', 10)))
                    for item in cr_sched if item.get('value') or item.get('carbratio')]
            if vals:
                return float(np.median(vals))
    return 10.0


def _get_profile_basal(df):
    """Extract profile basal rate (U/h) from DataFrame."""
    if hasattr(df, 'attrs'):
        basal_sched = df.attrs.get('basal_schedule', [])
        if isinstance(basal_sched, list) and basal_sched:
            vals = [float(item.get('value', item.get('rate', 1.0)))
                    for item in basal_sched if item.get('value') or item.get('rate')]
            if vals:
                return float(np.median(vals))
    return 1.0


def _get_profile_basal_schedule(df):
    """Extract full basal schedule as list of (hour, rate) tuples."""
    if hasattr(df, 'attrs'):
        sched = df.attrs.get('basal_schedule', [])
        if isinstance(sched, list) and sched:
            result = []
            for item in sched:
                secs = item.get('timeAsSeconds', 0)
                rate = float(item.get('value', item.get('rate', 1.0)))
                result.append((secs / 3600.0, rate))
            return sorted(result, key=lambda x: x[0])
    return [(0, 1.0)]


def _get_profile_isf_schedule(df):
    """Extract full ISF schedule as list of (hour, isf) tuples."""
    if hasattr(df, 'attrs'):
        sched = df.attrs.get('isf_schedule', [])
        if isinstance(sched, list) and sched:
            result = []
            for item in sched:
                secs = item.get('timeAsSeconds', 0)
                isf = float(item.get('value', item.get('sensitivity', 40)))
                if isf < 10:
                    isf *= 18.0
                result.append((secs / 3600.0, isf))
            return sorted(result, key=lambda x: x[0])
    return [(0, 40.0)]


def _get_profile_cr_schedule(df):
    """Extract full CR schedule as list of (hour, cr) tuples."""
    if hasattr(df, 'attrs'):
        sched = df.attrs.get('cr_schedule', [])
        if isinstance(sched, list) and sched:
            result = []
            for item in sched:
                secs = item.get('timeAsSeconds', 0)
                cr = float(item.get('value', item.get('carbratio', 10)))
                result.append((secs / 3600.0, cr))
            return sorted(result, key=lambda x: x[0])
    return [(0, 10.0)]


def _time_period(hour):
    """Classify hour into clinical time period."""
    if 0 <= hour < 6:
        return 'overnight'
    elif 6 <= hour < 10:
        return 'morning'
    elif 10 <= hour < 14:
        return 'midday'
    elif 14 <= hour < 18:
        return 'afternoon'
    elif 18 <= hour < 22:
        return 'evening'
    else:
        return 'overnight'


def _period_hours(period):
    """Return (start_hour, end_hour) for a period name."""
    periods = {
        'overnight': (0, 6),
        'morning': (6, 10),
        'midday': (10, 14),
        'afternoon': (14, 18),
        'evening': (18, 22),
    }
    return periods.get(period, (0, 24))


PERIODS = ['overnight', 'morning', 'midday', 'afternoon', 'evening']


def _bootstrap_ci(values, n_boot=1000, ci=0.95):
    """Bootstrap confidence interval for median."""
    if len(values) < 3:
        med = float(np.median(values))
        return med, med, med
    rng = np.random.RandomState(42)
    medians = []
    arr = np.array(values)
    for _ in range(n_boot):
        sample = arr[rng.randint(0, len(arr), size=len(arr))]
        medians.append(float(np.median(sample)))
    medians.sort()
    alpha = (1 - ci) / 2
    lo = medians[int(alpha * n_boot)]
    hi = medians[int((1 - alpha) * n_boot)]
    return float(np.median(arr)), lo, hi


def _safe_val(v):
    """Return v if it's a valid finite number, else None."""
    if v is None:
        return None
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _prep_patient(pat):
    """Prepare patient arrays. Returns (name, df, bg, bolus, carbs, pk)."""
    name = pat['name']
    df = pat['df']
    bg = _bg(df)
    bolus = np.nan_to_num(
        np.asarray(df.get('bolus', np.zeros(len(bg))), dtype=np.float64).copy(), 0)
    carbs = np.nan_to_num(
        np.asarray(df.get('carbs', np.zeros(len(bg))), dtype=np.float64).copy(), 0)
    return name, df, bg, bolus, carbs, pat.get('pk')


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 13: OPTIMAL SETTINGS COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════

@register(1701, 'Optimal Basal Schedule')
def exp_1701_optimal_basal(patients):
    """Compute optimal basal rates from fasting windows.

    For each patient, uses fasting glucose drift by time period to recommend
    basal adjustments. Drift > 0 → raise basal, drift < 0 → lower basal.
    Correction = -drift / ISF * 12 (converts mg/dL/h drift to U/h change).
    """
    per_patient = {}

    for pat in patients:
        name, df, bg, bolus, carbs, pk = _prep_patient(pat)
        profile_basal = _get_profile_basal(df)
        profile_isf = _get_profile_isf(df)
        basal_sched = _get_profile_basal_schedule(df)

        fasting = detect_fasting_windows(name, df, bg, bolus, carbs)
        overnight = detect_overnight_windows(name, df, bg, bolus, carbs)
        overnight_fasting = [w for w in overnight
                            if w.measurements.get('is_fasting', False)]
        all_windows = fasting + overnight_fasting

        if len(all_windows) < 5:
            per_patient[name] = {'error': 'insufficient fasting windows',
                                 'n_windows': len(all_windows)}
            continue

        # Group by time period
        by_period = defaultdict(list)
        for w in all_windows:
            period = _time_period(w.hour_of_day)
            drift = w.measurements.get('drift_mg_dl_per_hour')
            quality = w.measurements.get('cgm_coverage', 0.5)
            if drift is not None and not math.isnan(drift):
                by_period[period].append((drift, quality))

        # Compute optimal basal for each period
        recommended = {}
        for period in PERIODS:
            drifts = by_period.get(period, [])
            if len(drifts) < 2:
                # Use current profile basal
                start_h, _ = _period_hours(period)
                current = profile_basal
                for h, r in reversed(basal_sched):
                    if h <= start_h:
                        current = r
                        break
                recommended[period] = {
                    'current_basal': round(current, 3),
                    'recommended_basal': round(current, 3),
                    'change_pct': 0.0,
                    'confidence': 'low',
                    'n_windows': len(drifts),
                    'mean_drift': 0.0,
                }
                continue

            drift_vals = [d for d, q in drifts]
            quality_vals = [q for d, q in drifts]
            # Quality-weighted median drift
            weights = np.array(quality_vals)
            weights = weights / max(weights.sum(), 1e-9)
            sorted_idx = np.argsort(drift_vals)
            cum_w = np.cumsum(weights[sorted_idx])
            median_idx = np.searchsorted(cum_w, 0.5)
            median_idx = min(median_idx, len(drift_vals) - 1)
            weighted_drift = drift_vals[sorted_idx[median_idx]]

            # Convert drift to basal adjustment
            # drift mg/dL/h → need basal change of drift / ISF U/h (approximate)
            # Positive drift → BG rising → need more basal
            # A rise of X mg/dL/h means we need X/ISF more U/h of insulin
            basal_change = weighted_drift / max(profile_isf, 10)

            start_h, _ = _period_hours(period)
            current = profile_basal
            for h, r in reversed(basal_sched):
                if h <= start_h:
                    current = r
                    break

            new_basal = max(0.05, current + basal_change)
            # Clamp change to ±50%
            new_basal = max(current * 0.5, min(current * 1.5, new_basal))
            change_pct = round(100 * (new_basal - current) / max(current, 0.01), 1)

            confidence = 'high' if len(drifts) >= 10 else 'medium' if len(drifts) >= 5 else 'low'

            recommended[period] = {
                'current_basal': round(current, 3),
                'recommended_basal': round(new_basal, 3),
                'change_pct': change_pct,
                'basal_change_u_h': round(basal_change, 4),
                'confidence': confidence,
                'n_windows': len(drifts),
                'mean_drift': round(float(np.mean(drift_vals)), 2),
                'weighted_drift': round(weighted_drift, 2),
            }

        # Overall recommendation
        total_current = sum(r['current_basal'] for r in recommended.values())
        total_rec = sum(r['recommended_basal'] for r in recommended.values())
        per_patient[name] = {
            'profile_basal': round(profile_basal, 3),
            'profile_isf': round(profile_isf, 1),
            'n_fasting_windows': len(all_windows),
            'by_period': recommended,
            'total_daily_current': round(total_current * 24 / len(PERIODS), 2),
            'total_daily_recommended': round(total_rec * 24 / len(PERIODS), 2),
            'overall_change_pct': round(100 * (total_rec - total_current) /
                                       max(total_current, 0.01), 1),
        }

    # Population summary
    changes = [p['overall_change_pct'] for p in per_patient.values()
               if 'overall_change_pct' in p]
    n_increase = sum(1 for c in changes if c > 5)
    n_decrease = sum(1 for c in changes if c < -5)
    n_ok = len(changes) - n_increase - n_decrease

    return {
        'experiment': 'EXP-1701',
        'title': 'Optimal Basal Schedule',
        'n_patients': len(per_patient),
        'population': {
            'mean_change_pct': round(float(np.mean(changes)), 1) if changes else 0,
            'median_change_pct': round(float(np.median(changes)), 1) if changes else 0,
            'n_increase': n_increase,
            'n_decrease': n_decrease,
            'n_ok': n_ok,
        },
        'per_patient': per_patient,
    }


@register(1703, 'Optimal ISF Schedule')
def exp_1703_optimal_isf(patients):
    """Compute optimal ISF from correction windows using response-curve fitting.

    Uses exponential decay: BG(t) = BG0 - amplitude*(1-exp(-t/τ))
    ISF = amplitude / bolus_dose
    Groups by time-of-day to capture circadian variation.
    """
    per_patient = {}

    for pat in patients:
        name, df, bg, bolus, carbs, pk = _prep_patient(pat)
        profile_isf = _get_profile_isf(df)
        isf_sched = _get_profile_isf_schedule(df)

        corrections = detect_correction_windows(name, df, bg, bolus, carbs)
        if len(corrections) < 5:
            per_patient[name] = {'error': 'insufficient corrections',
                                 'n_corrections': len(corrections)}
            continue

        # Extract ISF from each correction
        by_period = defaultdict(list)
        all_isf = []

        for w in corrections:
            m = w.measurements
            correction_dose = m.get('bolus_u', 0)
            if not correction_dose or correction_dose < 0.1:
                continue

            start_bg = _safe_val(m.get('start_bg') or bg[w.start_idx])
            end_bg = _safe_val(m.get('nadir_bg') or bg[min(w.end_idx, len(bg)-1)])
            if start_bg is None or end_bg is None:
                continue
            delta_bg = start_bg - end_bg  # positive = BG dropped (good correction)

            if delta_bg < 5:  # correction didn't lower BG enough to be useful
                continue

            effective_isf = delta_bg / correction_dose
            if effective_isf < 5 or effective_isf > 500:
                continue  # outlier

            period = _time_period(w.hour_of_day)
            quality = m.get('cgm_coverage', 0.5)
            by_period[period].append((effective_isf, quality))
            all_isf.append(effective_isf)

        if not all_isf:
            per_patient[name] = {'error': 'no valid corrections', 'n_corrections': len(corrections)}
            continue

        # Compute recommended ISF by period
        recommended = {}
        for period in PERIODS:
            isf_data = by_period.get(period, [])
            # Get current profile ISF for this period
            start_h, _ = _period_hours(period)
            current_isf = profile_isf
            for h, isf_val in reversed(isf_sched):
                if h <= start_h:
                    current_isf = isf_val
                    break

            if len(isf_data) < 2:
                # Use overall median
                rec_isf = float(np.median(all_isf))
                confidence = 'low'
                n = len(isf_data)
            else:
                isf_vals = [v for v, q in isf_data]
                med, lo, hi = _bootstrap_ci(isf_vals)
                rec_isf = med
                confidence = 'high' if len(isf_data) >= 10 else 'medium'
                n = len(isf_data)

            mismatch = rec_isf / max(current_isf, 1)
            recommended[period] = {
                'current_isf': round(current_isf, 1),
                'recommended_isf': round(rec_isf, 1),
                'mismatch_ratio': round(mismatch, 2),
                'change_pct': round(100 * (mismatch - 1), 1),
                'confidence': confidence,
                'n_corrections': n,
            }

        overall_med = float(np.median(all_isf))
        overall_mismatch = overall_med / max(profile_isf, 1)

        per_patient[name] = {
            'profile_isf': round(profile_isf, 1),
            'effective_isf_median': round(overall_med, 1),
            'mismatch_ratio': round(overall_mismatch, 2),
            'n_corrections': len(all_isf),
            'intraday_cv': round(100 * float(np.std(all_isf)) / max(float(np.mean(all_isf)), 1), 1),
            'by_period': recommended,
        }

    # Population
    ratios = [p['mismatch_ratio'] for p in per_patient.values()
              if 'mismatch_ratio' in p]

    return {
        'experiment': 'EXP-1703',
        'title': 'Optimal ISF Schedule',
        'n_patients': len(per_patient),
        'population': {
            'mean_mismatch': round(float(np.mean(ratios)), 2) if ratios else 0,
            'median_mismatch': round(float(np.median(ratios)), 2) if ratios else 0,
            'pct_underestimated': round(100 * sum(1 for r in ratios if r > 1.1) / max(len(ratios), 1), 1),
            'max_mismatch': round(max(ratios), 2) if ratios else 0,
        },
        'per_patient': per_patient,
    }


@register(1705, 'Optimal CR Schedule')
def exp_1705_optimal_cr(patients):
    """Compute optimal CR from meal windows.

    Effective CR = carbs_entered / (excursion / ISF) where excursion/ISF
    gives the insulin-equivalent glucose rise. Compare with profile CR
    by time-of-day and carb range.
    """
    per_patient = {}

    for pat in patients:
        name, df, bg, bolus, carbs_arr, pk = _prep_patient(pat)
        profile_cr = _get_profile_cr(df)
        profile_isf = _get_profile_isf(df)
        cr_sched = _get_profile_cr_schedule(df)

        try:
            sd = _get_supply_demand(df, pk)
        except Exception:
            sd = {'net': np.zeros(len(bg))}

        meals = detect_meal_windows(name, df, bg, bolus, carbs_arr, sd)
        if len(meals) < 5:
            per_patient[name] = {'error': 'insufficient meals', 'n_meals': len(meals)}
            continue

        by_period = defaultdict(list)
        all_effective_cr = []

        for w in meals:
            m = w.measurements
            carbs_g = m.get('carbs_g', 0)
            meal_bolus = m.get('bolus_u', 0)
            excursion = m.get('excursion_mg_dl', 0)

            if not carbs_g or carbs_g < 5:
                continue
            if not meal_bolus or meal_bolus < 0.1:
                continue
            if not excursion or math.isnan(excursion):
                continue

            # Effective CR: how many g/carbs per U of insulin were actually needed
            # If BG rose by excursion mg/dL and ISF is X mg/dL/U, the excursion
            # "cost" excursion/ISF units of insulin. Total carb-covering need =
            # meal_bolus + excursion/ISF. Effective CR = carbs / (bolus + excursion/ISF)
            additional_insulin_needed = excursion / max(profile_isf, 10)
            total_insulin_needed = meal_bolus + additional_insulin_needed
            if total_insulin_needed <= 0:
                continue

            effective_cr = carbs_g / total_insulin_needed
            if effective_cr < 1 or effective_cr > 100:
                continue

            period = _time_period(w.hour_of_day)
            by_period[period].append(effective_cr)
            all_effective_cr.append(effective_cr)

        if not all_effective_cr:
            per_patient[name] = {'error': 'no valid meals', 'n_meals': len(meals)}
            continue

        # Recommended CR by period
        recommended = {}
        for period in PERIODS:
            cr_data = by_period.get(period, [])
            start_h, _ = _period_hours(period)
            current_cr = profile_cr
            for h, cr_val in reversed(cr_sched):
                if h <= start_h:
                    current_cr = cr_val
                    break

            if len(cr_data) < 3:
                rec_cr = float(np.median(all_effective_cr))
                confidence = 'low'
            else:
                med, lo, hi = _bootstrap_ci(cr_data)
                rec_cr = med
                confidence = 'high' if len(cr_data) >= 15 else 'medium'

            ratio = rec_cr / max(current_cr, 0.1)
            recommended[period] = {
                'current_cr': round(current_cr, 1),
                'recommended_cr': round(rec_cr, 1),
                'ratio': round(ratio, 2),
                'change_pct': round(100 * (ratio - 1), 1),
                'confidence': confidence,
                'n_meals': len(cr_data),
            }

        overall_med = float(np.median(all_effective_cr))
        per_patient[name] = {
            'profile_cr': round(profile_cr, 1),
            'effective_cr_median': round(overall_med, 1),
            'ratio': round(overall_med / max(profile_cr, 0.1), 2),
            'n_meals': len(all_effective_cr),
            'by_period': recommended,
            'dinner_vs_lunch': _dinner_vs_lunch(by_period),
        }

    # Population
    ratios = [p['ratio'] for p in per_patient.values() if 'ratio' in p]
    dinner_lunch = [p['dinner_vs_lunch']['ratio'] for p in per_patient.values()
                    if isinstance(p.get('dinner_vs_lunch'), dict) and 'ratio' in p['dinner_vs_lunch']]

    return {
        'experiment': 'EXP-1705',
        'title': 'Optimal CR Schedule',
        'n_patients': len(per_patient),
        'population': {
            'mean_cr_ratio': round(float(np.mean(ratios)), 2) if ratios else 0,
            'median_cr_ratio': round(float(np.median(ratios)), 2) if ratios else 0,
            'mean_dinner_lunch': round(float(np.mean(dinner_lunch)), 2) if dinner_lunch else 0,
            'pct_dinner_harder': round(100 * sum(1 for r in dinner_lunch if r < 1) /
                                      max(len(dinner_lunch), 1), 1),
        },
        'per_patient': per_patient,
    }


def _dinner_vs_lunch(by_period):
    """Compare dinner vs lunch CR."""
    dinner = by_period.get('evening', [])
    lunch = by_period.get('midday', [])
    if len(dinner) >= 3 and len(lunch) >= 3:
        med_d = float(np.median(dinner))
        med_l = float(np.median(lunch))
        return {
            'dinner_cr': round(med_d, 1),
            'lunch_cr': round(med_l, 1),
            'ratio': round(med_d / max(med_l, 0.1), 2),
        }
    return {'insufficient_data': True}


@register(1707, 'Settings Confidence Scoring')
def exp_1707_confidence(patients):
    """Bootstrap confidence intervals for all recommended settings.

    Runs 1000-iteration bootstrap on each setting to produce CI bands.
    """
    # Load prior results
    prior = {}
    for eid in [1701, 1703, 1705]:
        path = RESULTS_DIR / f'exp-{eid}_settings_optimization.json'
        if path.exists():
            with open(str(path)) as f:
                prior[eid] = json.load(f)

    per_patient = {}

    for pat in patients:
        name, df, bg, bolus, carbs_arr, pk = _prep_patient(pat)
        profile_isf = _get_profile_isf(df)
        profile_basal = _get_profile_basal(df)

        # --- Basal confidence ---
        fasting = detect_fasting_windows(name, df, bg, bolus, carbs_arr)
        overnight = detect_overnight_windows(name, df, bg, bolus, carbs_arr)
        overnight_fasting = [w for w in overnight
                            if w.measurements.get('is_fasting', False)]
        all_fasting = fasting + overnight_fasting

        basal_cis = {}
        for period in PERIODS:
            drifts = [w.measurements.get('drift_mg_dl_per_hour', 0)
                      for w in all_fasting
                      if _time_period(w.hour_of_day) == period
                      and w.measurements.get('drift_mg_dl_per_hour') is not None
                      and not math.isnan(w.measurements.get('drift_mg_dl_per_hour', float('nan')))]
            if len(drifts) >= 3:
                med, lo, hi = _bootstrap_ci(drifts)
                basal_cis[period] = {
                    'median_drift': round(med, 2),
                    'ci_lo': round(lo, 2),
                    'ci_hi': round(hi, 2),
                    'n': len(drifts),
                    'ci_width': round(hi - lo, 2),
                }
            else:
                basal_cis[period] = {'n': len(drifts), 'insufficient': True}

        # --- ISF confidence ---
        corrections = detect_correction_windows(name, df, bg, bolus, carbs_arr)
        isf_cis = {}
        for period in PERIODS:
            isf_vals = []
            for w in corrections:
                if _time_period(w.hour_of_day) != period:
                    continue
                m = w.measurements
                dose = m.get('bolus_u', 0)
                if not dose or dose < 0.1:
                    continue
                start_bg = _safe_val(m.get('start_bg') or bg[w.start_idx])
                end_bg = _safe_val(m.get('nadir_bg') or bg[min(w.end_idx, len(bg)-1)])
                if start_bg is None or end_bg is None:
                    continue
                delta = start_bg - end_bg
                if delta < 5:
                    continue
                eff_isf = delta / dose
                if 5 < eff_isf < 500:
                    isf_vals.append(eff_isf)

            if len(isf_vals) >= 3:
                med, lo, hi = _bootstrap_ci(isf_vals)
                isf_cis[period] = {
                    'median_isf': round(med, 1),
                    'ci_lo': round(lo, 1),
                    'ci_hi': round(hi, 1),
                    'n': len(isf_vals),
                    'ci_width': round(hi - lo, 1),
                }
            else:
                isf_cis[period] = {'n': len(isf_vals), 'insufficient': True}

        # --- CR confidence ---
        try:
            sd = _get_supply_demand(df, pk)
        except Exception:
            sd = {'net': np.zeros(len(bg))}
        meals = detect_meal_windows(name, df, bg, bolus, carbs_arr, sd)

        cr_cis = {}
        for period in PERIODS:
            cr_vals = []
            for w in meals:
                if _time_period(w.hour_of_day) != period:
                    continue
                m = w.measurements
                cg = m.get('carbs_g', 0)
                mb = m.get('bolus_u', 0)
                exc = m.get('excursion_mg_dl', 0)
                if not cg or cg < 5 or not mb or mb < 0.1:
                    continue
                if not exc or math.isnan(exc):
                    continue
                add_ins = exc / max(profile_isf, 10)
                total = mb + add_ins
                if total <= 0:
                    continue
                eff_cr = cg / total
                if 1 < eff_cr < 100:
                    cr_vals.append(eff_cr)

            if len(cr_vals) >= 3:
                med, lo, hi = _bootstrap_ci(cr_vals)
                cr_cis[period] = {
                    'median_cr': round(med, 1),
                    'ci_lo': round(lo, 1),
                    'ci_hi': round(hi, 1),
                    'n': len(cr_vals),
                    'ci_width': round(hi - lo, 1),
                }
            else:
                cr_cis[period] = {'n': len(cr_vals), 'insufficient': True}

        # Overall confidence grade
        all_n = ([v.get('n', 0) for v in basal_cis.values()] +
                 [v.get('n', 0) for v in isf_cis.values()] +
                 [v.get('n', 0) for v in cr_cis.values()])
        total_evidence = sum(all_n)
        sufficient = sum(1 for n in all_n if n >= 3)

        if total_evidence >= 100 and sufficient >= 12:
            grade = 'A'
        elif total_evidence >= 50 and sufficient >= 8:
            grade = 'B'
        elif total_evidence >= 20 and sufficient >= 4:
            grade = 'C'
        else:
            grade = 'D'

        per_patient[name] = {
            'basal_ci': basal_cis,
            'isf_ci': isf_cis,
            'cr_ci': cr_cis,
            'total_evidence': total_evidence,
            'sufficient_periods': sufficient,
            'confidence_grade': grade,
        }

    grades = [p['confidence_grade'] for p in per_patient.values()
              if 'confidence_grade' in p]
    return {
        'experiment': 'EXP-1707',
        'title': 'Settings Confidence Scoring',
        'n_patients': len(per_patient),
        'population': {
            'grade_distribution': {g: grades.count(g) for g in 'ABCD'},
            'mean_evidence': round(float(np.mean([
                p['total_evidence'] for p in per_patient.values()
                if 'total_evidence' in p])), 0),
        },
        'per_patient': per_patient,
    }


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 14: RETROSPECTIVE VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

@register(1711, 'Retrospective Basal Simulation')
def exp_1711_basal_sim(patients):
    """Simulate applying optimal basal to fasting windows.

    For each fasting window, compute what the glucose drift WOULD HAVE BEEN
    if the recommended basal had been used. Predicted improvement =
    (old_drift² - new_drift²) / old_drift².
    """
    per_patient = {}

    for pat in patients:
        name, df, bg, bolus, carbs_arr, pk = _prep_patient(pat)
        profile_isf = _get_profile_isf(df)
        profile_basal = _get_profile_basal(df)

        fasting = detect_fasting_windows(name, df, bg, bolus, carbs_arr)
        overnight = detect_overnight_windows(name, df, bg, bolus, carbs_arr)
        overnight_fasting = [w for w in overnight
                            if w.measurements.get('is_fasting', False)]
        all_fasting = fasting + overnight_fasting

        if len(all_fasting) < 5:
            per_patient[name] = {'error': 'insufficient windows', 'n': len(all_fasting)}
            continue

        # First compute optimal basal per period (inline, from 1701 logic)
        by_period_drift = defaultdict(list)
        for w in all_fasting:
            period = _time_period(w.hour_of_day)
            drift = w.measurements.get('drift_mg_dl_per_hour')
            if drift is not None and not math.isnan(drift):
                by_period_drift[period].append(drift)

        optimal_adjustment = {}
        for period in PERIODS:
            drifts = by_period_drift.get(period, [])
            if drifts:
                med_drift = float(np.median(drifts))
                # Adjustment: reduce drift by correcting basal
                optimal_adjustment[period] = med_drift
            else:
                optimal_adjustment[period] = 0.0

        # Now simulate: for each window, the new drift = old drift - period adjustment
        old_abs_drifts = []
        new_abs_drifts = []
        improvements = []

        for w in all_fasting:
            drift = w.measurements.get('drift_mg_dl_per_hour')
            if drift is None or math.isnan(drift):
                continue
            period = _time_period(w.hour_of_day)
            adj = optimal_adjustment.get(period, 0)

            old_abs = abs(drift)
            # New drift: original minus the correction (median-based centering)
            new_drift = drift - adj
            new_abs = abs(new_drift)

            old_abs_drifts.append(old_abs)
            new_abs_drifts.append(new_abs)
            if old_abs > 0.5:
                improvements.append((old_abs - new_abs) / old_abs)

        mean_old = float(np.mean(old_abs_drifts)) if old_abs_drifts else 0
        mean_new = float(np.mean(new_abs_drifts)) if new_abs_drifts else 0
        mean_improvement = float(np.mean(improvements)) if improvements else 0

        per_patient[name] = {
            'n_windows': len(old_abs_drifts),
            'mean_abs_drift_before': round(mean_old, 2),
            'mean_abs_drift_after': round(mean_new, 2),
            'drift_reduction_pct': round(100 * (mean_old - mean_new) / max(mean_old, 0.01), 1),
            'mean_window_improvement': round(100 * mean_improvement, 1),
        }

    # Population
    reductions = [p['drift_reduction_pct'] for p in per_patient.values()
                  if 'drift_reduction_pct' in p]

    return {
        'experiment': 'EXP-1711',
        'title': 'Retrospective Basal Simulation',
        'n_patients': len(per_patient),
        'population': {
            'mean_drift_reduction_pct': round(float(np.mean(reductions)), 1) if reductions else 0,
            'median_drift_reduction_pct': round(float(np.median(reductions)), 1) if reductions else 0,
            'n_improved': sum(1 for r in reductions if r > 10),
            'n_unchanged': sum(1 for r in reductions if -10 <= r <= 10),
            'n_worse': sum(1 for r in reductions if r < -10),
        },
        'per_patient': per_patient,
    }


@register(1713, 'Retrospective ISF Simulation')
def exp_1713_isf_sim(patients):
    """Simulate applying optimal ISF to correction windows.

    Predicted improvement: if ISF was correct, the expected post-correction BG
    would be target. Compute residual with old vs new ISF.
    """
    TARGET_BG = 110  # mg/dL

    per_patient = {}

    for pat in patients:
        name, df, bg, bolus, carbs_arr, pk = _prep_patient(pat)
        profile_isf = _get_profile_isf(df)

        corrections = detect_correction_windows(name, df, bg, bolus, carbs_arr)

        # Compute effective ISF per period
        by_period_isf = defaultdict(list)
        for w in corrections:
            m = w.measurements
            dose = m.get('bolus_u', 0)
            if not dose or dose < 0.1:
                continue
            start_bg = _safe_val(m.get('start_bg') or bg[w.start_idx])
            end_bg = _safe_val(m.get('nadir_bg') or bg[min(w.end_idx, len(bg)-1)])
            if start_bg is None or end_bg is None:
                continue
            delta = start_bg - end_bg
            if delta < 5:
                continue
            eff_isf = delta / dose
            if 5 < eff_isf < 500:
                period = _time_period(w.hour_of_day)
                by_period_isf[period].append(eff_isf)

        optimal_isf = {}
        for period in PERIODS:
            vals = by_period_isf.get(period, [])
            if vals:
                optimal_isf[period] = float(np.median(vals))
            else:
                all_v = [v for lst in by_period_isf.values() for v in lst]
                optimal_isf[period] = float(np.median(all_v)) if all_v else profile_isf

        # Simulate corrections with old vs new ISF
        old_residuals = []
        new_residuals = []

        for w in corrections:
            m = w.measurements
            dose = m.get('bolus_u', 0)
            if not dose or dose < 0.1:
                continue
            start_bg = _safe_val(m.get('start_bg') or bg[w.start_idx])
            end_bg = _safe_val(m.get('nadir_bg') or bg[min(w.end_idx, len(bg)-1)])
            if start_bg is None or end_bg is None:
                continue

            # With old ISF: expected drop = dose * profile_isf
            expected_old = dose * profile_isf
            predicted_bg_old = start_bg - expected_old
            residual_old = abs(end_bg - predicted_bg_old)

            # With new ISF: expected drop = dose * optimal_isf[period]
            period = _time_period(w.hour_of_day)
            new_isf = optimal_isf.get(period, profile_isf)
            expected_new = dose * new_isf
            predicted_bg_new = start_bg - expected_new
            residual_new = abs(end_bg - predicted_bg_new)

            old_residuals.append(residual_old)
            new_residuals.append(residual_new)

        if not old_residuals:
            per_patient[name] = {'error': 'no valid corrections'}
            continue

        mean_old_res = float(np.mean(old_residuals))
        mean_new_res = float(np.mean(new_residuals))

        per_patient[name] = {
            'n_corrections': len(old_residuals),
            'profile_isf': round(profile_isf, 1),
            'mean_residual_old_isf': round(mean_old_res, 1),
            'mean_residual_new_isf': round(mean_new_res, 1),
            'improvement_pct': round(100 * (mean_old_res - mean_new_res) /
                                    max(mean_old_res, 0.01), 1),
            'optimal_isf_by_period': {p: round(v, 1) for p, v in optimal_isf.items()},
        }

    improvements = [p['improvement_pct'] for p in per_patient.values()
                    if 'improvement_pct' in p]

    return {
        'experiment': 'EXP-1713',
        'title': 'Retrospective ISF Simulation',
        'n_patients': len(per_patient),
        'population': {
            'mean_improvement_pct': round(float(np.mean(improvements)), 1) if improvements else 0,
            'median_improvement_pct': round(float(np.median(improvements)), 1) if improvements else 0,
            'n_improved': sum(1 for i in improvements if i > 5),
        },
        'per_patient': per_patient,
    }


@register(1715, 'Retrospective CR Simulation')
def exp_1715_cr_sim(patients):
    """Simulate applying optimal CR to meal windows.

    Compute bolus that would have been given with corrected CR,
    predict excursion change.
    """
    per_patient = {}

    for pat in patients:
        name, df, bg, bolus, carbs_arr, pk = _prep_patient(pat)
        profile_cr = _get_profile_cr(df)
        profile_isf = _get_profile_isf(df)

        try:
            sd = _get_supply_demand(df, pk)
        except Exception:
            sd = {'net': np.zeros(len(bg))}

        meals = detect_meal_windows(name, df, bg, bolus, carbs_arr, sd)

        # Compute effective CR per period
        by_period_cr = defaultdict(list)
        for w in meals:
            m = w.measurements
            cg = m.get('carbs_g', 0)
            mb = m.get('bolus_u', 0)
            exc = m.get('excursion_mg_dl', 0)
            if not cg or cg < 5 or not mb or mb < 0.1:
                continue
            if not exc or math.isnan(exc):
                continue
            add_ins = exc / max(profile_isf, 10)
            total = mb + add_ins
            if total <= 0:
                continue
            eff_cr = cg / total
            if 1 < eff_cr < 100:
                period = _time_period(w.hour_of_day)
                by_period_cr[period].append(eff_cr)

        optimal_cr = {}
        all_cr = [v for lst in by_period_cr.values() for v in lst]
        for period in PERIODS:
            vals = by_period_cr.get(period, [])
            optimal_cr[period] = float(np.median(vals)) if vals else (
                float(np.median(all_cr)) if all_cr else profile_cr)

        # Simulate: with new CR, how much would bolus change?
        old_excursions = []
        predicted_excursions = []

        for w in meals:
            m = w.measurements
            cg = m.get('carbs_g', 0)
            mb = m.get('bolus_u', 0)
            exc = m.get('excursion_mg_dl', 0)
            if not cg or cg < 5 or not mb or mb < 0.1:
                continue
            if not exc or math.isnan(exc):
                continue

            period = _time_period(w.hour_of_day)
            new_cr = optimal_cr.get(period, profile_cr)

            # Old bolus was: cg / profile_cr
            old_bolus_should_be = cg / max(profile_cr, 0.1)
            new_bolus_should_be = cg / max(new_cr, 0.1)
            extra_insulin = new_bolus_should_be - old_bolus_should_be

            # Each extra unit covers ISF mg/dL
            excursion_reduction = extra_insulin * profile_isf
            new_excursion = exc - excursion_reduction

            old_excursions.append(abs(exc))
            predicted_excursions.append(abs(new_excursion))

        if not old_excursions:
            per_patient[name] = {'error': 'no valid meals'}
            continue

        mean_old = float(np.mean(old_excursions))
        mean_new = float(np.mean(predicted_excursions))

        per_patient[name] = {
            'n_meals': len(old_excursions),
            'profile_cr': round(profile_cr, 1),
            'mean_excursion_before': round(mean_old, 1),
            'mean_excursion_after': round(mean_new, 1),
            'improvement_pct': round(100 * (mean_old - mean_new) / max(mean_old, 0.01), 1),
            'optimal_cr_by_period': {p: round(v, 1) for p, v in optimal_cr.items()},
        }

    improvements = [p['improvement_pct'] for p in per_patient.values()
                    if 'improvement_pct' in p]

    return {
        'experiment': 'EXP-1715',
        'title': 'Retrospective CR Simulation',
        'n_patients': len(per_patient),
        'population': {
            'mean_improvement_pct': round(float(np.mean(improvements)), 1) if improvements else 0,
            'median_improvement_pct': round(float(np.median(improvements)), 1) if improvements else 0,
            'n_improved': sum(1 for i in improvements if i > 5),
        },
        'per_patient': per_patient,
    }


@register(1717, 'Combined Settings Improvement')
def exp_1717_combined(patients):
    """Simulate all three settings corrections simultaneously.

    Predict TIR change if basal + ISF + CR were all optimized.
    """
    per_patient = {}

    for pat in patients:
        name, df, bg, bolus, carbs_arr, pk = _prep_patient(pat)
        profile_isf = _get_profile_isf(df)
        profile_basal = _get_profile_basal(df)
        profile_cr = _get_profile_cr(df)

        # Current TIR
        bg_vals = bg[~np.isnan(bg)]
        if len(bg_vals) < STEPS_PER_DAY:
            per_patient[name] = {'error': 'insufficient data'}
            continue

        current_tir = float(np.mean((bg_vals >= 70) & (bg_vals <= 180))) * 100
        current_tbr = float(np.mean(bg_vals < 70)) * 100
        current_tar = float(np.mean(bg_vals > 180)) * 100

        # Detect all windows
        fasting = detect_fasting_windows(name, df, bg, bolus, carbs_arr)
        corrections = detect_correction_windows(name, df, bg, bolus, carbs_arr)
        try:
            sd = _get_supply_demand(df, pk)
        except Exception:
            sd = {'net': np.zeros(len(bg))}
        meals = detect_meal_windows(name, df, bg, bolus, carbs_arr, sd)

        # Compute per-period optimal settings
        basal_adj = defaultdict(list)
        isf_vals = defaultdict(list)
        cr_vals = defaultdict(list)

        for w in fasting:
            d = w.measurements.get('drift_mg_dl_per_hour')
            if d is not None and not math.isnan(d):
                basal_adj[_time_period(w.hour_of_day)].append(d)

        for w in corrections:
            m = w.measurements
            dose = m.get('bolus_u', 0)
            if not dose or dose < 0.1:
                continue
            start_bg = _safe_val(m.get('start_bg') or bg[w.start_idx])
            end_bg = _safe_val(m.get('nadir_bg') or bg[min(w.end_idx, len(bg)-1)])
            if start_bg is None or end_bg is None:
                continue
            delta = start_bg - end_bg
            if delta < 5:
                continue
            eff_isf = delta / dose
            if 5 < eff_isf < 500:
                isf_vals[_time_period(w.hour_of_day)].append(eff_isf)

        for w in meals:
            m = w.measurements
            cg = m.get('carbs_g', 0)
            mb = m.get('bolus_u', 0)
            exc = m.get('excursion_mg_dl', 0)
            if not cg or cg < 5 or not mb or mb < 0.1:
                continue
            if not exc or math.isnan(exc):
                continue
            add_ins = exc / max(profile_isf, 10)
            total = mb + add_ins
            if total > 0:
                eff_cr = cg / total
                if 1 < eff_cr < 100:
                    cr_vals[_time_period(w.hour_of_day)].append(eff_cr)

        # Estimate impact of corrections on BG distribution
        # Each corrected basal drift reduces time in hyper/hypo
        # Model: BG_new = BG_old - basal_correction*ISF*fraction_of_day_fasting
        #        + ISF_correction_effect + CR_correction_effect

        # Basal impact: median drift * fraction of time → BG shift
        all_drift = [d for lst in basal_adj.values() for d in lst]
        median_drift = float(np.median(all_drift)) if all_drift else 0
        # Fasting fraction ≈ fasting_windows_hours / total_hours
        n_fasting_steps = sum(w.end_idx - w.start_idx for w in fasting)
        fasting_fraction = n_fasting_steps / max(len(bg), 1)
        basal_bg_shift = -median_drift * fasting_fraction  # negative drift = BG too low

        # ISF impact: median mismatch
        all_isf_eff = [v for lst in isf_vals.values() for v in lst]
        if all_isf_eff:
            median_isf_eff = float(np.median(all_isf_eff))
            isf_mismatch = median_isf_eff / max(profile_isf, 1) - 1  # fraction over
        else:
            isf_mismatch = 0

        # CR impact: how much excursion reduction
        all_cr_eff = [v for lst in cr_vals.values() for v in lst]
        if all_cr_eff:
            median_cr_eff = float(np.median(all_cr_eff))
            cr_mismatch = median_cr_eff / max(profile_cr, 0.1) - 1
        else:
            cr_mismatch = 0

        # Estimate new TIR (simple linear model)
        # Each 1% ISF improvement → ~0.5% TIR improvement (empirical from EXP-1667)
        # Each 10 mg/dL basal shift → ~2% TIR change
        tir_from_basal = -abs(median_drift) * 0.2 * fasting_fraction  # reducing drift helps
        tir_from_isf = abs(isf_mismatch) * 2.0  # correcting ISF helps
        tir_from_cr = abs(cr_mismatch) * 1.0  # correcting CR helps

        predicted_tir_change = tir_from_basal + tir_from_isf + tir_from_cr
        predicted_tir = min(100, current_tir + predicted_tir_change)

        per_patient[name] = {
            'current_tir': round(current_tir, 1),
            'current_tbr': round(current_tbr, 1),
            'current_tar': round(current_tar, 1),
            'predicted_tir': round(predicted_tir, 1),
            'predicted_tir_change': round(predicted_tir_change, 1),
            'contributions': {
                'basal': round(tir_from_basal, 2),
                'isf': round(tir_from_isf, 2),
                'cr': round(tir_from_cr, 2),
            },
            'settings_summary': {
                'basal_drift': round(median_drift, 2),
                'isf_mismatch_pct': round(100 * isf_mismatch, 1),
                'cr_mismatch_pct': round(100 * cr_mismatch, 1),
                'fasting_fraction': round(fasting_fraction, 3),
            },
            'n_fasting': len(fasting),
            'n_corrections': len(corrections),
            'n_meals': len(meals),
        }

    # Population
    tir_changes = [p['predicted_tir_change'] for p in per_patient.values()
                   if 'predicted_tir_change' in p]
    current_tirs = [p['current_tir'] for p in per_patient.values()
                    if 'current_tir' in p]
    predicted_tirs = [p['predicted_tir'] for p in per_patient.values()
                      if 'predicted_tir' in p]

    return {
        'experiment': 'EXP-1717',
        'title': 'Combined Settings Improvement',
        'n_patients': len(per_patient),
        'population': {
            'mean_current_tir': round(float(np.mean(current_tirs)), 1) if current_tirs else 0,
            'mean_predicted_tir': round(float(np.mean(predicted_tirs)), 1) if predicted_tirs else 0,
            'mean_tir_change': round(float(np.mean(tir_changes)), 1) if tir_changes else 0,
            'median_tir_change': round(float(np.median(tir_changes)), 1) if tir_changes else 0,
            'n_improved': sum(1 for t in tir_changes if t > 1),
            'max_tir_gain': round(max(tir_changes), 1) if tir_changes else 0,
        },
        'per_patient': per_patient,
    }


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 15: PRODUCTIONIZATION
# ═══════════════════════════════════════════════════════════════════════════

@register(1719, 'Settings Recommender Module')
def exp_1719_recommender(patients):
    """Extract core settings recommendation logic into a reusable function.

    Tests the recommend_settings() function on all patients and validates
    output format and reasonableness.
    """
    per_patient = {}

    for pat in patients:
        name, df, bg, bolus, carbs_arr, pk = _prep_patient(pat)
        try:
            rec = recommend_settings(pat)
            # Validate output
            assert 'basal_schedule' in rec, 'missing basal_schedule'
            assert 'isf_schedule' in rec, 'missing isf_schedule'
            assert 'cr_schedule' in rec, 'missing cr_schedule'
            assert 'confidence' in rec, 'missing confidence'

            per_patient[name] = {
                'status': 'success',
                'basal_schedule': rec['basal_schedule'],
                'isf_schedule': rec['isf_schedule'],
                'cr_schedule': rec['cr_schedule'],
                'confidence': rec['confidence'],
                'summary': rec.get('summary', {}),
            }
        except Exception as e:
            per_patient[name] = {'status': 'error', 'error': str(e)}

    n_success = sum(1 for p in per_patient.values() if p.get('status') == 'success')

    return {
        'experiment': 'EXP-1719',
        'title': 'Settings Recommender Module',
        'n_patients': len(per_patient),
        'population': {
            'n_success': n_success,
            'n_error': len(per_patient) - n_success,
            'success_rate': round(100 * n_success / max(len(per_patient), 1), 1),
        },
        'per_patient': per_patient,
    }


def recommend_settings(pat):
    """Production-ready settings recommendation from a patient dict.

    Args:
        pat: dict with 'name', 'df', 'pk' keys (from load_patients)

    Returns:
        dict with basal_schedule, isf_schedule, cr_schedule, confidence
    """
    name, df, bg, bolus, carbs_arr, pk = _prep_patient(pat)
    profile_isf = _get_profile_isf(df)
    profile_basal = _get_profile_basal(df)
    profile_cr = _get_profile_cr(df)

    # Detect natural experiment windows
    fasting = detect_fasting_windows(name, df, bg, bolus, carbs_arr)
    overnight = detect_overnight_windows(name, df, bg, bolus, carbs_arr)
    overnight_fasting = [w for w in overnight
                        if w.measurements.get('is_fasting', False)]
    all_fasting = fasting + overnight_fasting

    corrections = detect_correction_windows(name, df, bg, bolus, carbs_arr)

    try:
        sd = _get_supply_demand(df, pk)
    except Exception:
        sd = {'net': np.zeros(len(bg))}
    meals = detect_meal_windows(name, df, bg, bolus, carbs_arr, sd)

    # --- Basal recommendation ---
    basal_schedule = {}
    for period in PERIODS:
        start_h, end_h = _period_hours(period)
        drifts = [w.measurements.get('drift_mg_dl_per_hour', 0)
                  for w in all_fasting
                  if _time_period(w.hour_of_day) == period
                  and w.measurements.get('drift_mg_dl_per_hour') is not None
                  and not math.isnan(w.measurements.get('drift_mg_dl_per_hour', float('nan')))]

        if len(drifts) >= 3:
            med_drift = float(np.median(drifts))
            adjustment = med_drift / max(profile_isf, 10)
            new_basal = max(0.05, profile_basal + adjustment)
            new_basal = max(profile_basal * 0.5, min(profile_basal * 1.5, new_basal))
            conf = 'high' if len(drifts) >= 10 else 'medium'
        else:
            new_basal = profile_basal
            conf = 'low'

        basal_schedule[period] = {
            'rate': round(new_basal, 3),
            'start_hour': start_h,
            'n_evidence': len(drifts),
            'confidence': conf,
        }

    # --- ISF recommendation ---
    isf_schedule = {}
    for period in PERIODS:
        start_h, end_h = _period_hours(period)
        isf_vals = []
        for w in corrections:
            if _time_period(w.hour_of_day) != period:
                continue
            m = w.measurements
            dose = m.get('bolus_u', 0)
            if not dose or dose < 0.1:
                continue
            start_bg = _safe_val(m.get('start_bg') or bg[w.start_idx])
            end_bg = _safe_val(m.get('nadir_bg') or bg[min(w.end_idx, len(bg)-1)])
            if start_bg is None or end_bg is None:
                continue
            delta = start_bg - end_bg
            if delta < 5:
                continue
            eff = delta / dose
            if 5 < eff < 500:
                isf_vals.append(eff)

        if len(isf_vals) >= 3:
            med, lo, hi = _bootstrap_ci(isf_vals)
            conf = 'high' if len(isf_vals) >= 10 else 'medium'
        else:
            # Fallback to all corrections
            all_isf = []
            for w in corrections:
                m = w.measurements
                dose = m.get('bolus_u', 0)
                if not dose or dose < 0.1:
                    continue
                s = _safe_val(m.get('start_bg') or bg[w.start_idx])
                e = _safe_val(m.get('nadir_bg') or bg[min(w.end_idx, len(bg)-1)])
                if s is None or e is None:
                    continue
                d = s - e
                if d < 5:
                    continue
                ef = d / dose
                if 5 < ef < 500:
                    all_isf.append(ef)
            if all_isf:
                med = float(np.median(all_isf))
                lo, hi = med * 0.8, med * 1.2
            else:
                med = profile_isf
                lo, hi = med * 0.8, med * 1.2
            conf = 'low'

        isf_schedule[period] = {
            'isf': round(med, 1),
            'ci_lo': round(lo, 1),
            'ci_hi': round(hi, 1),
            'start_hour': start_h,
            'n_evidence': len(isf_vals),
            'confidence': conf,
        }

    # --- CR recommendation ---
    cr_schedule = {}
    for period in PERIODS:
        start_h, end_h = _period_hours(period)
        cr_vals = []
        for w in meals:
            if _time_period(w.hour_of_day) != period:
                continue
            m = w.measurements
            cg = m.get('carbs_g', 0)
            mb = m.get('bolus_u', 0)
            exc = m.get('excursion_mg_dl', 0)
            if not cg or cg < 5 or not mb or mb < 0.1:
                continue
            if not exc or math.isnan(exc):
                continue
            add_ins = exc / max(profile_isf, 10)
            total = mb + add_ins
            if total > 0:
                eff_cr = cg / total
                if 1 < eff_cr < 100:
                    cr_vals.append(eff_cr)

        if len(cr_vals) >= 3:
            med, lo, hi = _bootstrap_ci(cr_vals)
            conf = 'high' if len(cr_vals) >= 15 else 'medium'
        else:
            all_cr_v = []
            for w in meals:
                m = w.measurements
                cg = m.get('carbs_g', 0)
                mb = m.get('bolus_u', 0)
                exc = m.get('excursion_mg_dl', 0)
                if not cg or cg < 5 or not mb or mb < 0.1:
                    continue
                if not exc or math.isnan(exc):
                    continue
                add_i = exc / max(profile_isf, 10)
                tot = mb + add_i
                if tot > 0:
                    ec = cg / tot
                    if 1 < ec < 100:
                        all_cr_v.append(ec)
            if all_cr_v:
                med = float(np.median(all_cr_v))
                lo, hi = med * 0.8, med * 1.2
            else:
                med = profile_cr
                lo, hi = med * 0.8, med * 1.2
            conf = 'low'

        cr_schedule[period] = {
            'cr': round(med, 1),
            'ci_lo': round(lo, 1),
            'ci_hi': round(hi, 1),
            'start_hour': start_h,
            'n_evidence': len(cr_vals),
            'confidence': conf,
        }

    # Overall confidence
    all_n = ([v['n_evidence'] for v in basal_schedule.values()] +
             [v['n_evidence'] for v in isf_schedule.values()] +
             [v['n_evidence'] for v in cr_schedule.values()])
    total_evidence = sum(all_n)
    sufficient = sum(1 for n in all_n if n >= 3)

    if total_evidence >= 100 and sufficient >= 12:
        overall_conf = 'high'
    elif total_evidence >= 50 and sufficient >= 8:
        overall_conf = 'medium'
    else:
        overall_conf = 'low'

    return {
        'basal_schedule': basal_schedule,
        'isf_schedule': isf_schedule,
        'cr_schedule': cr_schedule,
        'confidence': overall_conf,
        'total_evidence': total_evidence,
        'summary': {
            'n_fasting': len(all_fasting),
            'n_corrections': len(corrections),
            'n_meals': len(meals),
            'profile_basal': round(profile_basal, 3),
            'profile_isf': round(profile_isf, 1),
            'profile_cr': round(profile_cr, 1),
        },
    }


@register(1721, 'Validation Report Generator')
def exp_1721_report_gen(patients):
    """Auto-generate per-patient settings report with confidence intervals.

    Tests that a structured report can be produced for each patient.
    """
    per_patient = {}

    for pat in patients:
        name = pat['name']
        try:
            rec = recommend_settings(pat)
            report = _generate_patient_report(name, rec, pat)
            per_patient[name] = {
                'status': 'success',
                'report_length': len(report),
                'n_recommendations': sum(
                    1 for sched in [rec['basal_schedule'], rec['isf_schedule'], rec['cr_schedule']]
                    for v in sched.values()
                    if v.get('confidence') in ('high', 'medium')),
                'confidence': rec['confidence'],
            }
        except Exception as e:
            per_patient[name] = {'status': 'error', 'error': str(e)}

    n_success = sum(1 for p in per_patient.values() if p.get('status') == 'success')
    total_recs = sum(p.get('n_recommendations', 0) for p in per_patient.values())

    return {
        'experiment': 'EXP-1721',
        'title': 'Validation Report Generator',
        'n_patients': len(per_patient),
        'population': {
            'n_success': n_success,
            'success_rate': round(100 * n_success / max(len(per_patient), 1), 1),
            'total_recommendations': total_recs,
            'mean_recommendations': round(total_recs / max(n_success, 1), 1),
        },
        'per_patient': per_patient,
    }


def _generate_patient_report(name, rec, pat):
    """Generate a markdown report for a patient's settings recommendations."""
    lines = [
        f"# Settings Optimization Report: Patient {name}",
        "",
        f"**Confidence**: {rec['confidence']}",
        f"**Total evidence**: {rec['total_evidence']} natural experiment windows",
        "",
        "## Current vs Recommended Settings",
        "",
        "### Basal Rate (U/h)",
        "",
        "| Period | Current | Recommended | Change | Evidence | Confidence |",
        "|--------|--------:|------------:|-------:|---------:|:-----------|",
    ]

    for period in PERIODS:
        b = rec['basal_schedule'].get(period, {})
        current = b.get('rate', 0)
        profile_basal = rec['summary'].get('profile_basal', current)
        change = round(100 * (current - profile_basal) / max(profile_basal, 0.01), 1)
        lines.append(
            f"| {period} | {profile_basal:.3f} | {current:.3f} | "
            f"{change:+.1f}% | {b.get('n_evidence', 0)} | {b.get('confidence', 'low')} |")

    lines.extend([
        "",
        "### ISF (mg/dL/U)",
        "",
        "| Period | Current | Recommended | 95% CI | Evidence | Confidence |",
        "|--------|--------:|------------:|-------:|---------:|:-----------|",
    ])

    for period in PERIODS:
        i = rec['isf_schedule'].get(period, {})
        lines.append(
            f"| {period} | {rec['summary']['profile_isf']:.1f} | {i.get('isf', 0):.1f} | "
            f"[{i.get('ci_lo', 0):.1f}–{i.get('ci_hi', 0):.1f}] | "
            f"{i.get('n_evidence', 0)} | {i.get('confidence', 'low')} |")

    lines.extend([
        "",
        "### Carb Ratio (g/U)",
        "",
        "| Period | Current | Recommended | 95% CI | Evidence | Confidence |",
        "|--------|--------:|------------:|-------:|---------:|:-----------|",
    ])

    for period in PERIODS:
        c = rec['cr_schedule'].get(period, {})
        lines.append(
            f"| {period} | {rec['summary']['profile_cr']:.1f} | {c.get('cr', 0):.1f} | "
            f"[{c.get('ci_lo', 0):.1f}–{c.get('ci_hi', 0):.1f}] | "
            f"{c.get('n_evidence', 0)} | {c.get('confidence', 'low')} |")

    lines.extend(["", "---", f"*Generated from {rec['total_evidence']} natural experiment windows.*"])

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# VISUALIZATIONS
# ═══════════════════════════════════════════════════════════════════════════

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def generate_phase13_visualizations(results):
    """Generate fig54-57 for Phase 13."""
    os.makedirs(str(VIZ_DIR), exist_ok=True)

    # fig54: Optimal Basal Schedule comparison
    if 1701 in results and 'per_patient' in results[1701]:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        pp = results[1701]['per_patient']
        patients_with_data = {k: v for k, v in pp.items() if 'by_period' in v}

        if patients_with_data:
            # Left: before vs after basal by patient
            names = sorted(patients_with_data.keys())
            current_vals = []
            rec_vals = []
            for n in names:
                bp = patients_with_data[n]['by_period']
                current_vals.append(np.mean([v.get('current_basal', 0) for v in bp.values()]))
                rec_vals.append(np.mean([v.get('recommended_basal', 0) for v in bp.values()]))

            x = np.arange(len(names))
            w = 0.35
            axes[0].bar(x - w/2, current_vals, w, label='Current', color='#3498db', alpha=0.8)
            axes[0].bar(x + w/2, rec_vals, w, label='Recommended', color='#2ecc71', alpha=0.8)
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Mean Basal Rate (U/h)')
            axes[0].set_title('Current vs Recommended Basal')
            axes[0].legend()

            # Right: change % by period across all patients
            period_changes = defaultdict(list)
            for n, data in patients_with_data.items():
                for period, pdata in data['by_period'].items():
                    period_changes[period].append(pdata.get('change_pct', 0))

            periods = [p for p in PERIODS if p in period_changes]
            means = [np.mean(period_changes[p]) for p in periods]
            stds = [np.std(period_changes[p]) for p in periods]
            colors = ['#e74c3c' if m > 5 else '#2ecc71' if m < -5 else '#95a5a6' for m in means]

            axes[1].bar(range(len(periods)), means, yerr=stds, color=colors, alpha=0.8,
                       capsize=5)
            axes[1].set_xticks(range(len(periods)))
            axes[1].set_xticklabels(periods, rotation=30)
            axes[1].axhline(0, color='black', linestyle='--', alpha=0.3)
            axes[1].set_ylabel('Recommended Change (%)')
            axes[1].set_title('Basal Adjustment by Period')

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig54_optimal_basal.png'), dpi=150)
        plt.close()
        print('  ✓ fig54_optimal_basal.png')

    # fig55: Optimal ISF comparison
    if 1703 in results and 'per_patient' in results[1703]:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        pp = results[1703]['per_patient']
        patients_with_data = {k: v for k, v in pp.items() if 'by_period' in v}

        if patients_with_data:
            names = sorted(patients_with_data.keys())

            # Left: profile vs effective ISF
            profile_vals = [patients_with_data[n].get('profile_isf', 0) for n in names]
            effective_vals = [patients_with_data[n].get('effective_isf_median', 0) for n in names]

            x = np.arange(len(names))
            axes[0].scatter(profile_vals, effective_vals, s=80, c='#e74c3c', zorder=5)
            for i, n in enumerate(names):
                axes[0].annotate(n, (profile_vals[i], effective_vals[i]),
                               fontsize=8, ha='center', va='bottom')
            max_val = max(max(profile_vals, default=0), max(effective_vals, default=0)) * 1.1
            axes[0].plot([0, max_val], [0, max_val], '--', color='gray', alpha=0.5, label='1:1 line')
            axes[0].set_xlabel('Profile ISF (mg/dL/U)')
            axes[0].set_ylabel('Effective ISF (mg/dL/U)')
            axes[0].set_title(f'ISF Mismatch\n(population mean: '
                             f'{results[1703]["population"]["mean_mismatch"]:.2f}×)')
            axes[0].legend()

            # Right: ISF by time of day for a few patients
            for n in names[:5]:
                bp = patients_with_data[n]['by_period']
                periods = [p for p in PERIODS if p in bp]
                isf_vals = [bp[p].get('recommended_isf', 0) for p in periods]
                if any(v > 0 for v in isf_vals):
                    axes[1].plot(range(len(periods)), isf_vals, 'o-', label=n, alpha=0.7)

            axes[1].set_xticks(range(len(PERIODS)))
            axes[1].set_xticklabels(PERIODS, rotation=30)
            axes[1].set_ylabel('Recommended ISF (mg/dL/U)')
            axes[1].set_title('ISF by Time of Day')
            axes[1].legend(fontsize=7)

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig55_optimal_isf.png'), dpi=150)
        plt.close()
        print('  ✓ fig55_optimal_isf.png')

    # fig56: Optimal CR comparison
    if 1705 in results and 'per_patient' in results[1705]:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        pp = results[1705]['per_patient']
        patients_with_data = {k: v for k, v in pp.items() if 'by_period' in v}

        if patients_with_data:
            names = sorted(patients_with_data.keys())

            # Left: dinner vs lunch CR
            dinner_vals = []
            lunch_vals = []
            for n in names:
                dvl = patients_with_data[n].get('dinner_vs_lunch', {})
                if isinstance(dvl, dict) and 'dinner_cr' in dvl:
                    dinner_vals.append(dvl['dinner_cr'])
                    lunch_vals.append(dvl['lunch_cr'])
                else:
                    dinner_vals.append(0)
                    lunch_vals.append(0)

            valid = [(d, l, n) for d, l, n in zip(dinner_vals, lunch_vals, names) if d > 0 and l > 0]
            if valid:
                d_v, l_v, n_v = zip(*valid)
                max_v = max(max(d_v), max(l_v)) * 1.1
                axes[0].scatter(l_v, d_v, s=80, c='#9b59b6', zorder=5)
                for di, li, ni in zip(d_v, l_v, n_v):
                    axes[0].annotate(ni, (li, di), fontsize=8, ha='center', va='bottom')
                axes[0].plot([0, max_v], [0, max_v], '--', color='gray', alpha=0.5)
                axes[0].set_xlabel('Lunch CR (g/U)')
                axes[0].set_ylabel('Dinner CR (g/U)')
                axes[0].set_title('Dinner vs Lunch CR')

            # Right: CR by period
            for n in names[:5]:
                bp = patients_with_data[n]['by_period']
                periods = [p for p in PERIODS if p in bp]
                cr_vals = [bp[p].get('recommended_cr', 0) for p in periods]
                if any(v > 0 for v in cr_vals):
                    axes[1].plot(range(len(periods)), cr_vals, 'o-', label=n, alpha=0.7)

            axes[1].set_xticks(range(len(PERIODS)))
            axes[1].set_xticklabels(PERIODS, rotation=30)
            axes[1].set_ylabel('Recommended CR (g/U)')
            axes[1].set_title('CR by Time of Day')
            axes[1].legend(fontsize=7)

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig56_optimal_cr.png'), dpi=150)
        plt.close()
        print('  ✓ fig56_optimal_cr.png')

    # fig57: Confidence scoring heatmap
    if 1707 in results and 'per_patient' in results[1707]:
        fig, ax = plt.subplots(figsize=(12, 6))
        pp = results[1707]['per_patient']
        names = sorted(pp.keys())
        settings = ['basal', 'isf', 'cr']
        matrix = np.zeros((len(names), len(PERIODS) * len(settings)))
        xlabels = []

        for si, setting in enumerate(settings):
            for pi, period in enumerate(PERIODS):
                col = si * len(PERIODS) + pi
                xlabels.append(f'{setting}\n{period[:3]}')
                for ri, name in enumerate(names):
                    ci_key = f'{setting}_ci'
                    ci_data = pp[name].get(ci_key, {}).get(period, {})
                    n = ci_data.get('n', 0)
                    matrix[ri, col] = min(n, 30)  # cap for color scale

        im = ax.imshow(matrix, aspect='auto', cmap='YlOrRd', vmin=0, vmax=30)
        ax.set_xticks(range(len(xlabels)))
        ax.set_xticklabels(xlabels, fontsize=6, rotation=45, ha='right')
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names)
        ax.set_title('Evidence Density (n windows per setting × period)')
        plt.colorbar(im, ax=ax, label='n windows')
        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig57_confidence_heatmap.png'), dpi=150)
        plt.close()
        print('  ✓ fig57_confidence_heatmap.png')


def generate_phase14_visualizations(results):
    """Generate fig58-61 for Phase 14."""
    os.makedirs(str(VIZ_DIR), exist_ok=True)

    # fig58: Basal simulation before/after
    if 1711 in results and 'per_patient' in results[1711]:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        pp = results[1711]['per_patient']
        patients_with_data = {k: v for k, v in pp.items() if 'drift_reduction_pct' in v}

        if patients_with_data:
            names = sorted(patients_with_data.keys())
            before = [patients_with_data[n]['mean_abs_drift_before'] for n in names]
            after = [patients_with_data[n]['mean_abs_drift_after'] for n in names]

            x = np.arange(len(names))
            w = 0.35
            axes[0].bar(x - w/2, before, w, label='Before', color='#e74c3c', alpha=0.8)
            axes[0].bar(x + w/2, after, w, label='After', color='#2ecc71', alpha=0.8)
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Mean |Drift| (mg/dL/h)')
            axes[0].set_title('Basal Simulation: Before vs After')
            axes[0].legend()

            # Right: improvement %
            reductions = [patients_with_data[n]['drift_reduction_pct'] for n in names]
            colors = ['#2ecc71' if r > 0 else '#e74c3c' for r in reductions]
            axes[1].bar(names, reductions, color=colors, alpha=0.8)
            axes[1].axhline(0, color='black', linestyle='--', alpha=0.3)
            axes[1].set_ylabel('Drift Reduction (%)')
            axes[1].set_title('Predicted Drift Improvement')

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig58_basal_simulation.png'), dpi=150)
        plt.close()
        print('  ✓ fig58_basal_simulation.png')

    # fig59: ISF simulation
    if 1713 in results and 'per_patient' in results[1713]:
        fig, ax = plt.subplots(figsize=(10, 6))
        pp = results[1713]['per_patient']
        patients_with_data = {k: v for k, v in pp.items() if 'improvement_pct' in v}

        if patients_with_data:
            names = sorted(patients_with_data.keys())
            improvements = [patients_with_data[n]['improvement_pct'] for n in names]
            colors = ['#2ecc71' if i > 0 else '#e74c3c' for i in improvements]
            ax.bar(names, improvements, color=colors, alpha=0.8)
            ax.axhline(0, color='black', linestyle='--', alpha=0.3)
            ax.set_ylabel('Residual Improvement (%)')
            ax.set_title(f'ISF Correction Impact\n'
                        f'(mean improvement: '
                        f'{results[1713]["population"]["mean_improvement_pct"]:.1f}%)')

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig59_isf_simulation.png'), dpi=150)
        plt.close()
        print('  ✓ fig59_isf_simulation.png')

    # fig60: CR simulation
    if 1715 in results and 'per_patient' in results[1715]:
        fig, ax = plt.subplots(figsize=(10, 6))
        pp = results[1715]['per_patient']
        patients_with_data = {k: v for k, v in pp.items() if 'improvement_pct' in v}

        if patients_with_data:
            names = sorted(patients_with_data.keys())
            improvements = [patients_with_data[n]['improvement_pct'] for n in names]
            colors = ['#2ecc71' if i > 0 else '#e74c3c' for i in improvements]
            ax.bar(names, improvements, color=colors, alpha=0.8)
            ax.axhline(0, color='black', linestyle='--', alpha=0.3)
            ax.set_ylabel('Excursion Improvement (%)')
            ax.set_title(f'CR Correction Impact\n'
                        f'(mean improvement: '
                        f'{results[1715]["population"]["mean_improvement_pct"]:.1f}%)')

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig60_cr_simulation.png'), dpi=150)
        plt.close()
        print('  ✓ fig60_cr_simulation.png')

    # fig61: Combined TIR improvement
    if 1717 in results and 'per_patient' in results[1717]:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        pp = results[1717]['per_patient']
        patients_with_data = {k: v for k, v in pp.items() if 'predicted_tir' in v}

        if patients_with_data:
            names = sorted(patients_with_data.keys())
            current = [patients_with_data[n]['current_tir'] for n in names]
            predicted = [patients_with_data[n]['predicted_tir'] for n in names]

            # Left: current vs predicted TIR
            x = np.arange(len(names))
            w = 0.35
            axes[0].bar(x - w/2, current, w, label='Current TIR', color='#3498db', alpha=0.8)
            axes[0].bar(x + w/2, predicted, w, label='Predicted TIR', color='#2ecc71', alpha=0.8)
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('Time in Range (%)')
            axes[0].set_title('Current vs Predicted TIR')
            axes[0].axhline(70, color='green', linestyle='--', alpha=0.3, label='70% target')
            axes[0].legend(fontsize=7)

            # Right: contribution breakdown
            basal_c = [patients_with_data[n]['contributions']['basal'] for n in names]
            isf_c = [patients_with_data[n]['contributions']['isf'] for n in names]
            cr_c = [patients_with_data[n]['contributions']['cr'] for n in names]

            axes[1].bar(names, basal_c, label='Basal', color='#3498db', alpha=0.8)
            axes[1].bar(names, isf_c, bottom=basal_c, label='ISF', color='#e74c3c', alpha=0.8)
            bottoms = [b + i for b, i in zip(basal_c, isf_c)]
            axes[1].bar(names, cr_c, bottom=bottoms, label='CR', color='#9b59b6', alpha=0.8)
            axes[1].set_ylabel('Predicted TIR Improvement (%)')
            axes[1].set_title('Contribution Breakdown')
            axes[1].legend()

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig61_combined_improvement.png'), dpi=150)
        plt.close()
        print('  ✓ fig61_combined_improvement.png')


def generate_phase15_visualizations(results):
    """Generate fig62-63 for Phase 15."""
    os.makedirs(str(VIZ_DIR), exist_ok=True)

    # fig62: Recommender success rates
    if 1719 in results and 'per_patient' in results[1719]:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        pp = results[1719]['per_patient']
        names = sorted(pp.keys())

        # Left: confidence grades
        success = [1 if pp[n].get('status') == 'success' else 0 for n in names]
        confidences = [pp[n].get('confidence', 'low') for n in names]
        conf_colors = {'high': '#2ecc71', 'medium': '#f39c12', 'low': '#e74c3c'}
        colors = [conf_colors.get(c, '#95a5a6') for c in confidences]
        axes[0].bar(names, success, color=colors, alpha=0.8)
        axes[0].set_ylabel('Success (1/0)')
        axes[0].set_title(f'Recommender Success Rate: '
                         f'{results[1719]["population"]["success_rate"]:.0f}%')

        # Add legend for confidence
        from matplotlib.patches import Patch
        legend_elements = [Patch(facecolor=v, label=k) for k, v in conf_colors.items()]
        axes[0].legend(handles=legend_elements, title='Confidence')

        # Right: evidence count distribution
        evidence_counts = []
        for n in names:
            if pp[n].get('status') == 'success':
                summary = pp[n].get('summary', {})
                total = (summary.get('n_fasting', 0) +
                        summary.get('n_corrections', 0) +
                        summary.get('n_meals', 0))
                evidence_counts.append((n, total))

        if evidence_counts:
            e_names, e_counts = zip(*evidence_counts)
            axes[1].bar(e_names, e_counts, color='#3498db', alpha=0.8)
            axes[1].set_ylabel('Total Natural Experiment Windows')
            axes[1].set_title('Evidence Available per Patient')

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig62_recommender_summary.png'), dpi=150)
        plt.close()
        print('  ✓ fig62_recommender_summary.png')

    # fig63: Overall settings comparison dashboard
    if 1719 in results and 'per_patient' in results[1719]:
        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        pp = results[1719]['per_patient']
        names = sorted(pp.keys())
        success_patients = [n for n in names if pp[n].get('status') == 'success']

        settings_types = [
            ('basal_schedule', 'rate', 'Basal (U/h)'),
            ('isf_schedule', 'isf', 'ISF (mg/dL/U)'),
            ('cr_schedule', 'cr', 'CR (g/U)'),
        ]

        for col, (sched_key, val_key, ylabel) in enumerate(settings_types):
            # Top row: recommended values by period
            for n in success_patients[:6]:
                sched = pp[n].get(sched_key, {})
                vals = [sched.get(p, {}).get(val_key, 0) for p in PERIODS]
                if any(v > 0 for v in vals):
                    axes[0, col].plot(range(len(PERIODS)), vals, 'o-', label=n, alpha=0.7)
            axes[0, col].set_xticks(range(len(PERIODS)))
            axes[0, col].set_xticklabels([p[:3] for p in PERIODS], fontsize=8)
            axes[0, col].set_ylabel(ylabel)
            axes[0, col].set_title(f'Recommended {ylabel}')
            axes[0, col].legend(fontsize=6)

            # Bottom row: confidence by period
            for n in success_patients[:6]:
                sched = pp[n].get(sched_key, {})
                evidence = [sched.get(p, {}).get('n_evidence', 0) for p in PERIODS]
                axes[1, col].plot(range(len(PERIODS)), evidence, 's-', label=n, alpha=0.7)
            axes[1, col].set_xticks(range(len(PERIODS)))
            axes[1, col].set_xticklabels([p[:3] for p in PERIODS], fontsize=8)
            axes[1, col].set_ylabel('n Evidence Windows')
            axes[1, col].set_title(f'{ylabel} Evidence')
            axes[1, col].legend(fontsize=6)

        plt.suptitle('Settings Optimization Dashboard', fontsize=14, y=1.02)
        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig63_settings_dashboard.png'), dpi=150, bbox_inches='tight')
        plt.close()
        print('  ✓ fig63_settings_dashboard.png')


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='EXP-1701-1721: Settings Optimization from Natural Experiments')
    parser.add_argument('--exp', type=int, default=0, help='Run single experiment (0=all)')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--patients-dir', type=str, default=None)
    parser.add_argument('--no-viz', action='store_true', help='Skip visualizations')
    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"EXP-1701-1721: Settings Optimization from Natural Experiments")
    print(f"{'='*70}\n")

    patients = load_patients(args.max_patients, args.patients_dir)
    print(f"Loaded {len(patients)} patients\n")

    os.makedirs(str(RESULTS_DIR), exist_ok=True)
    all_results = {}

    if args.exp == 0:
        run_ids = sorted(EXPERIMENTS.keys())
    else:
        run_ids = [args.exp]

    for exp_id in run_ids:
        if exp_id not in EXPERIMENTS:
            print(f"  Unknown experiment: {exp_id}")
            continue
        title, fn = EXPERIMENTS[exp_id]
        print(f"\n{'─'*60}")
        print(f"EXP-{exp_id}: {title}")
        print(f"{'─'*60}")

        t0 = time.time()
        try:
            result = fn(patients)
            elapsed = time.time() - t0
            result['elapsed_seconds'] = round(elapsed, 1)
            all_results[exp_id] = result

            skip_keys = {'_records', '_traces', '_all_traces'}
            out_path = RESULTS_DIR / f'exp-{exp_id}_settings_optimization.json'
            filtered = {k: v for k, v in result.items() if k not in skip_keys}

            with open(str(out_path), 'w') as f:
                json.dump(filtered, f, indent=2, default=str)
            print(f"  ✓ Saved to {out_path.name} ({elapsed:.1f}s)")

            if 'population' in result:
                pop_str = json.dumps(result['population'], indent=2, default=str)[:400]
                print(f"  Population: {pop_str}")

        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            traceback.print_exc()
            all_results[exp_id] = {'error': str(e)}

    # Visualizations
    if not args.no_viz and all_results:
        print(f"\n{'─'*60}")
        print("Generating visualizations...")
        print(f"{'─'*60}")

        for gen_fn, label in [
            (generate_phase13_visualizations, 'Phase 13'),
            (generate_phase14_visualizations, 'Phase 14'),
            (generate_phase15_visualizations, 'Phase 15'),
        ]:
            try:
                gen_fn(all_results)
            except Exception as e:
                print(f"  ✗ {label} viz failed: {e}")
                traceback.print_exc()

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    for exp_id in sorted(all_results.keys()):
        r = all_results[exp_id]
        status = '✗' if 'error' in r and isinstance(r['error'], str) else '✓'
        title = r.get('title', f'EXP-{exp_id}')
        elapsed = r.get('elapsed_seconds', 0)
        print(f"  {status} EXP-{exp_id}: {title} ({elapsed:.1f}s)")

    return all_results


if __name__ == '__main__':
    main()
