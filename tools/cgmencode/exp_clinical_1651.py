#!/usr/bin/env python3
"""EXP-1651 to EXP-1671: Settings Probes, AID Effectiveness & Integration.

Uses natural experiment windows (catalogued in EXP-1551, 50,810 total)
as live clinical probes to extract therapy settings, score AID effectiveness,
cross-classify patients, and build a UAM signature library.

Builds on:
  - EXP-1551–1571: Natural experiment census & characterization
  - EXP-1531–1538: Fidelity assessment (RMSE/CE grading)
  - EXP-1301: Response-curve ISF (exponential decay fit, R²=0.805)
  - EXP-1337: ISF varies 131% intra-day
  - EXP-1338: 5/11 patients drift over 6 months
  - EXP-1561: ISF normalization + spectral power (orthogonal, r=-0.039)
  - EXP-1571: Robustness archetypes (45% robust, 36% sensitive)

Experiments:
  Phase 9 — Settings Extraction
  EXP-1651: Basal adequacy from fasting windows (drift → basal too high/low)
  EXP-1653: ISF from correction windows (exp-decay fit by time-of-day)
  EXP-1655: Effective CR from meal windows (by carb range × time-of-day)
  EXP-1657: Rolling settings drift detection (30/60/90-day windows)

  Phase 10 — AID Effectiveness
  EXP-1661: AID effectiveness score per meal (spectral/excursion ratio)
  EXP-1663: AID effectiveness × archetype × time-of-day

  Phase 11 — Cross-Classification
  EXP-1665: Cross-tabulate fidelity × archetype × ISF-norm burden
  EXP-1667: Combined predictive power for outcomes

  Phase 12 — UAM Signatures
  EXP-1669: UAM glucose shape clustering (PCA on normalized traces)
  EXP-1671: UAM trajectory prediction from first 15 min

Usage:
    PYTHONPATH=tools python tools/cgmencode/exp_clinical_1651.py --exp 0
    PYTHONPATH=tools python tools/cgmencode/exp_clinical_1651.py --exp 1651
    PYTHONPATH=tools python tools/cgmencode/exp_clinical_1651.py --max-patients 3 --exp 1651
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
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from cgmencode.exp_metabolic_flux import load_patients as _load_patients
from cgmencode.exp_metabolic_flux import _extract_isf_scalar
from cgmencode.exp_metabolic_441 import compute_supply_demand

# Import detectors and helpers from EXP-1551 script
from cgmencode.exp_clinical_1551 import (
    NaturalExperiment,
    detect_fasting_windows, detect_correction_windows,
    detect_meal_windows, detect_uam_windows,
    detect_overnight_windows,
    _bg, _safe_nanmean, _safe_nanstd, _cgm_coverage,
    _linear_drift, _exp_decay_fit,
    _extract_runs, _cluster_events,
    _hours_array, _dates_array, _unique_dates,
    _hour_of_day, _day_of_week, _classify_meal_time,
    STEPS_PER_HOUR, STEPS_PER_DAY, STEP_MINUTES,
    FASTING_MIN_STEPS, FASTING_CARB_THRESH, FASTING_BOLUS_THRESH,
    MEAL_CARB_THRESH, CORRECTION_BG_THRESH,
    UAM_RESIDUAL_THRESH,
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

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
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
    """Compute supply-demand decomposition for a patient DataFrame."""
    return compute_supply_demand(df, pk)


def _get_profile_isf(df_or_attrs):
    """Extract profile ISF in mg/dL from DataFrame with attrs."""
    if hasattr(df_or_attrs, 'attrs'):
        return _extract_isf_scalar(df_or_attrs)
    # Fallback for dict
    return 40.0


def _get_profile_cr(df_or_attrs):
    """Extract profile CR (g/U) from DataFrame with attrs."""
    if hasattr(df_or_attrs, 'attrs'):
        cr_sched = df_or_attrs.attrs.get('cr_schedule', [])
    else:
        cr_sched = df_or_attrs.get('carbratio', df_or_attrs.get('cr_schedule', []))
    if isinstance(cr_sched, list) and len(cr_sched) > 0:
        vals = []
        for item in cr_sched:
            v = item.get('value', item.get('carbratio'))
            if v is not None:
                vals.append(float(v))
        if vals:
            return float(np.median(vals))
    return 10.0  # default


def _get_profile_basal(df_or_attrs):
    """Extract profile basal rate (U/h) from DataFrame with attrs."""
    if hasattr(df_or_attrs, 'attrs'):
        basal_sched = df_or_attrs.attrs.get('basal_schedule', [])
    else:
        basal_sched = df_or_attrs.get('basal', df_or_attrs.get('basalprofile', []))
    if isinstance(basal_sched, list) and len(basal_sched) > 0:
        vals = []
        for item in basal_sched:
            v = item.get('value', item.get('rate'))
            if v is not None:
                vals.append(float(v))
        if vals:
            return float(np.median(vals))
    return 1.0  # default


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
    else:
        return 'evening'


def _carb_range_label(carbs_g):
    """Classify carb amount into standard ranges."""
    if carbs_g < 10:
        return '<10g'
    elif carbs_g < 20:
        return '10-19g'
    elif carbs_g < 30:
        return '20-29g'
    elif carbs_g < 50:
        return '30-49g'
    else:
        return '≥50g'


def _spectral_power_window(bg_segment, sd_segment_net, step_min=5):
    """Compute supply×demand spectral power for a window."""
    N = min(len(bg_segment), len(sd_segment_net))
    if N < 12:
        return 0.0
    sig = sd_segment_net[:N]
    sig = sig - np.mean(sig)
    fft_vals = np.fft.rfft(sig)
    power = np.sum(np.abs(fft_vals) ** 2) / N
    return float(power)


# ---------------------------------------------------------------------------
# Load prior experiment results for cross-referencing
# ---------------------------------------------------------------------------
def _load_prior_results():
    """Load relevant prior experiment results."""
    results = {}
    for exp_id, suffix in [(1531, 'fidelity'), (1571, 'natural_experiments'),
                           (1561, 'natural_experiments')]:
        path = RESULTS_DIR / f'exp-{exp_id}_{suffix}.json'
        if path.exists():
            with open(str(path)) as f:
                results[exp_id] = json.load(f)
    return results


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 9: SETTINGS EXTRACTION FROM NATURAL EXPERIMENTS
# ═══════════════════════════════════════════════════════════════════════════

@register(1651, 'Basal Adequacy from Fasting Windows')
def exp_1651_basal_from_fasting(patients):
    """Extract basal rate adequacy from fasting natural experiments.

    Hypothesis: Fasting glucose drift (mg/dL/h) directly measures basal
    adequacy — positive drift means basal too low, negative means too high.
    This provides a continuous, per-time-of-day basal assessment without
    requiring formal basal testing.
    """
    per_patient = {}

    for pat in patients:
        name, df = pat['name'], pat['df']
        bg = _bg(df)
        bolus = np.asarray(df.get('bolus', np.zeros(len(bg))), dtype=np.float64)
        carbs = np.asarray(df.get('carbs', np.zeros(len(bg))), dtype=np.float64)
        bolus = np.nan_to_num(bolus.copy(), 0)
        carbs = np.nan_to_num(carbs.copy(), 0)
        profile = df.attrs.get('profile', {})
        profile_basal = _get_profile_basal(df)

        # Detect fasting windows
        fasting = detect_fasting_windows(name, df, bg, bolus, carbs)
        overnight = detect_overnight_windows(name, df, bg, bolus, carbs)
        # Filter overnight to fasting-only
        overnight_fasting = [w for w in overnight
                            if w.measurements.get('is_fasting', False)]

        all_windows = fasting + overnight_fasting
        if not all_windows:
            per_patient[name] = {'n_fasting': 0, 'error': 'no fasting windows'}
            continue

        # Analyze drift by time period
        by_period = defaultdict(list)
        all_drifts = []
        all_qualities = []

        for w in all_windows:
            drift = w.measurements.get('drift_mg_dl_per_hour')
            if drift is None:
                continue
            period = _time_period(w.hour_of_day)
            by_period[period].append({
                'drift': drift,
                'quality': w.quality,
                'mean_bg': w.measurements.get('mean_bg'),
                'duration_min': w.duration_minutes,
                'hour': w.hour_of_day,
            })
            all_drifts.append(drift)
            all_qualities.append(w.quality)

        if not all_drifts:
            per_patient[name] = {'n_fasting': len(all_windows),
                                 'error': 'no valid drift measurements'}
            continue

        drifts = np.array(all_drifts)
        qualities = np.array(all_qualities)

        # Quality-weighted mean drift
        weighted_drift = float(np.average(drifts, weights=qualities))

        # Basal assessment
        # Drift > +2 mg/dL/h → basal probably too low
        # Drift < -2 mg/dL/h → basal probably too high
        # -2 to +2 → adequate
        if weighted_drift > 2.0:
            assessment = 'too_low'
            suggested_change_pct = min(weighted_drift * 5, 30)  # cap at 30%
        elif weighted_drift < -2.0:
            assessment = 'too_high'
            suggested_change_pct = max(weighted_drift * 5, -30)
        else:
            assessment = 'adequate'
            suggested_change_pct = 0.0

        # Per-period breakdown
        period_summary = {}
        for period, records in by_period.items():
            p_drifts = [r['drift'] for r in records]
            p_quals = [r['quality'] for r in records]
            p_bgs = [r['mean_bg'] for r in records if r['mean_bg'] is not None]
            period_summary[period] = {
                'n_windows': len(records),
                'mean_drift': round(float(np.mean(p_drifts)), 3),
                'median_drift': round(float(np.median(p_drifts)), 3),
                'std_drift': round(float(np.std(p_drifts)), 3),
                'quality_weighted_drift': round(
                    float(np.average(p_drifts, weights=p_quals)), 3),
                'mean_bg': round(float(np.mean(p_bgs)), 1) if p_bgs else None,
                'assessment': ('too_low' if np.mean(p_drifts) > 2 else
                              'too_high' if np.mean(p_drifts) < -2 else 'adequate'),
            }

        per_patient[name] = {
            'n_fasting': len(all_windows),
            'n_valid_drift': len(all_drifts),
            'profile_basal_u_h': round(profile_basal, 3),
            'overall_drift_mg_dl_h': round(weighted_drift, 3),
            'overall_drift_std': round(float(np.std(drifts)), 3),
            'overall_assessment': assessment,
            'suggested_change_pct': round(suggested_change_pct, 1),
            'by_period': period_summary,
            'drift_distribution': {
                'mean': round(float(np.mean(drifts)), 3),
                'median': round(float(np.median(drifts)), 3),
                'p25': round(float(np.percentile(drifts, 25)), 3),
                'p75': round(float(np.percentile(drifts, 75)), 3),
                'pct_rising': round(float(np.mean(drifts > 0)) * 100, 1),
                'pct_falling': round(float(np.mean(drifts < 0)) * 100, 1),
            }
        }

    # Population summary
    assessments = [p.get('overall_assessment') for p in per_patient.values()
                   if 'overall_assessment' in p]
    pop_drifts = [p['overall_drift_mg_dl_h'] for p in per_patient.values()
                  if 'overall_drift_mg_dl_h' in p]

    return {
        'experiment': 'EXP-1651',
        'title': 'Basal Adequacy from Fasting Windows',
        'n_patients': len(per_patient),
        'population': {
            'mean_drift': round(float(np.mean(pop_drifts)), 3) if pop_drifts else None,
            'median_drift': round(float(np.median(pop_drifts)), 3) if pop_drifts else None,
            'n_adequate': assessments.count('adequate'),
            'n_too_low': assessments.count('too_low'),
            'n_too_high': assessments.count('too_high'),
        },
        'per_patient': per_patient,
    }


@register(1653, 'ISF from Correction Windows')
def exp_1653_isf_from_corrections(patients):
    """Extract ISF from correction natural experiments by time-of-day.

    Uses exponential decay fit (BG(t) = BG_start - amplitude*(1-exp(-t/τ)))
    per EXP-1301 method. Compare extracted ISF to profile ISF.
    Test EXP-1337 finding of 131% intra-day variation.
    """
    per_patient = {}

    for pat in patients:
        name, df = pat['name'], pat['df']
        bg = _bg(df)
        bolus = np.asarray(df.get('bolus', np.zeros(len(bg))), dtype=np.float64)
        carbs = np.asarray(df.get('carbs', np.zeros(len(bg))), dtype=np.float64)
        bolus = np.nan_to_num(bolus.copy(), 0)
        carbs = np.nan_to_num(carbs.copy(), 0)
        profile = df.attrs.get('profile', {})
        profile_isf = _get_profile_isf(df)

        corrections = detect_correction_windows(name, df, bg, bolus, carbs)
        if not corrections:
            per_patient[name] = {'n_corrections': 0, 'error': 'no correction windows'}
            continue

        # Extract ISF from each correction window
        by_period = defaultdict(list)
        all_isf_curve = []
        all_isf_simple = []
        all_taus = []
        all_r2s = []

        for w in corrections:
            m = w.measurements
            curve_isf = m.get('curve_isf')
            simple_isf = m.get('simple_isf')
            tau = m.get('curve_tau_hours')
            r2 = m.get('curve_r2')

            # Use curve ISF if good fit, else simple ISF
            if curve_isf and r2 and r2 > 0.3:
                isf_val = curve_isf
                method = 'curve'
                all_isf_curve.append(curve_isf)
                all_taus.append(tau)
                all_r2s.append(r2)
            elif simple_isf and simple_isf > 5:
                isf_val = simple_isf
                method = 'simple'
                all_isf_simple.append(simple_isf)
            else:
                continue

            period = _time_period(w.hour_of_day)
            by_period[period].append({
                'isf': isf_val,
                'method': method,
                'r2': r2,
                'tau': tau,
                'bolus_u': m.get('bolus_u'),
                'start_bg': m.get('start_bg'),
                'quality': w.quality,
                'hour': w.hour_of_day,
            })

        all_isf = all_isf_curve + all_isf_simple
        if not all_isf:
            per_patient[name] = {'n_corrections': len(corrections),
                                 'error': 'no valid ISF extractions'}
            continue

        isf_arr = np.array(all_isf)

        # Per-period ISF
        period_summary = {}
        for period, records in by_period.items():
            p_isf = [r['isf'] for r in records]
            period_summary[period] = {
                'n_windows': len(records),
                'mean_isf': round(float(np.mean(p_isf)), 1),
                'median_isf': round(float(np.median(p_isf)), 1),
                'std_isf': round(float(np.std(p_isf)), 1),
                'cv_pct': round(100 * float(np.std(p_isf)) / max(float(np.mean(p_isf)), 1), 1),
                'n_curve_fit': sum(1 for r in records if r['method'] == 'curve'),
            }

        # Intra-day variation
        period_means = [ps['mean_isf'] for ps in period_summary.values()
                       if ps['n_windows'] >= 3]
        intraday_range = (max(period_means) - min(period_means)) if len(period_means) >= 2 else 0
        intraday_cv = (float(np.std(period_means)) / max(float(np.mean(period_means)), 1) * 100
                      if len(period_means) >= 2 else 0)

        mismatch_ratio = float(np.median(isf_arr)) / max(profile_isf, 1)

        per_patient[name] = {
            'n_corrections': len(corrections),
            'n_valid_isf': len(all_isf),
            'n_curve_fit': len(all_isf_curve),
            'profile_isf': round(profile_isf, 1),
            'extracted_isf_median': round(float(np.median(isf_arr)), 1),
            'extracted_isf_mean': round(float(np.mean(isf_arr)), 1),
            'extracted_isf_std': round(float(np.std(isf_arr)), 1),
            'mismatch_ratio': round(mismatch_ratio, 3),
            'mean_tau_hours': round(float(np.mean(all_taus)), 2) if all_taus else None,
            'mean_curve_r2': round(float(np.mean(all_r2s)), 3) if all_r2s else None,
            'intraday_range': round(intraday_range, 1),
            'intraday_cv_pct': round(intraday_cv, 1),
            'by_period': period_summary,
        }

    # Population
    mismatch_ratios = [p['mismatch_ratio'] for p in per_patient.values()
                      if 'mismatch_ratio' in p]
    intraday_cvs = [p['intraday_cv_pct'] for p in per_patient.values()
                   if 'intraday_cv_pct' in p and p['intraday_cv_pct'] > 0]

    return {
        'experiment': 'EXP-1653',
        'title': 'ISF from Correction Windows',
        'n_patients': len(per_patient),
        'population': {
            'mean_mismatch_ratio': round(float(np.mean(mismatch_ratios)), 3) if mismatch_ratios else None,
            'median_mismatch_ratio': round(float(np.median(mismatch_ratios)), 3) if mismatch_ratios else None,
            'mean_intraday_cv': round(float(np.mean(intraday_cvs)), 1) if intraday_cvs else None,
            'pct_underestimated': round(float(np.mean(np.array(mismatch_ratios) > 1.0)) * 100, 1) if mismatch_ratios else None,
        },
        'per_patient': per_patient,
    }


@register(1655, 'Effective CR from Meal Windows')
def exp_1655_cr_from_meals(patients):
    """Extract effective CR from meal windows by carb range × time-of-day.

    For announced meals with known carbs and bolus, compute:
      effective_CR = carbs / bolus (actual delivery)
      excursion_per_gram = excursion / carbs (metabolic cost per gram)
      isf_norm_cost = excursion / (carbs × ISF) (normalized cost)

    Compare to profile CR. Test EXP-1336 dinner>lunch finding.
    """
    per_patient = {}

    for pat in patients:
        name, df = pat['name'], pat['df']
        bg = _bg(df)
        bolus = np.asarray(df.get('bolus', np.zeros(len(bg))), dtype=np.float64)
        carbs_arr = np.asarray(df.get('carbs', np.zeros(len(bg))), dtype=np.float64)
        bolus = np.nan_to_num(bolus.copy(), 0)
        carbs_arr = np.nan_to_num(carbs_arr.copy(), 0)
        profile = df.attrs.get('profile', {})
        profile_isf = _get_profile_isf(df)
        profile_cr = _get_profile_cr(df)

        try:
            sd = _get_supply_demand(df, pat.get('pk'))
        except Exception:
            sd = {'net': np.zeros(len(bg))}

        meals = detect_meal_windows(name, df, bg, bolus, carbs_arr, sd)
        if not meals:
            per_patient[name] = {'n_meals': 0, 'error': 'no meal windows'}
            continue

        by_period = defaultdict(list)
        by_carb_range = defaultdict(list)
        all_records = []

        for w in meals:
            m = w.measurements
            carbs_g = m.get('carbs_g', 0)
            bolus_u = m.get('bolus_u', 0)
            excursion = m.get('excursion_mg_dl')
            is_announced = m.get('is_announced', False)

            if not excursion or math.isnan(excursion) or carbs_g < 1:
                continue

            excursion_per_g = excursion / carbs_g
            isf_norm_exc = excursion / profile_isf  # correction equivalents

            # Compute spectral power for this window
            start_i = w.start_idx
            end_i = w.end_idx
            net_seg = sd['net'][start_i:end_i]
            spec_power = _spectral_power_window(bg[start_i:end_i], net_seg)

            rec = {
                'carbs_g': carbs_g,
                'bolus_u': bolus_u,
                'excursion': excursion,
                'excursion_per_g': round(excursion_per_g, 3),
                'isf_norm_exc': round(isf_norm_exc, 3),
                'spectral_power': round(spec_power, 2),
                'is_announced': is_announced,
                'meal_window': m.get('meal_window', 'snack'),
                'peak_time_min': m.get('peak_time_min'),
                'hour': w.hour_of_day,
                'quality': w.quality,
            }

            if is_announced and bolus_u > 0.1:
                rec['effective_cr'] = round(carbs_g / bolus_u, 1)
                rec['cr_ratio_vs_profile'] = round((carbs_g / bolus_u) / profile_cr, 3)

            period = _time_period(w.hour_of_day)
            by_period[period].append(rec)
            by_carb_range[_carb_range_label(carbs_g)].append(rec)
            all_records.append(rec)

        if not all_records:
            per_patient[name] = {'n_meals': len(meals), 'error': 'no valid measurements'}
            continue

        # Summarize by period
        period_summary = {}
        for period, recs in by_period.items():
            exc_vals = [r['excursion'] for r in recs]
            isf_vals = [r['isf_norm_exc'] for r in recs]
            spec_vals = [r['spectral_power'] for r in recs]
            cr_vals = [r['effective_cr'] for r in recs if 'effective_cr' in r]
            period_summary[period] = {
                'n_meals': len(recs),
                'mean_excursion': round(float(np.mean(exc_vals)), 1),
                'mean_isf_norm': round(float(np.mean(isf_vals)), 3),
                'mean_spectral': round(float(np.mean(spec_vals)), 2),
                'pct_announced': round(100 * sum(1 for r in recs if r['is_announced']) / len(recs), 1),
                'mean_effective_cr': round(float(np.mean(cr_vals)), 1) if cr_vals else None,
            }

        # Summarize by carb range
        carb_summary = {}
        for cr_label, recs in by_carb_range.items():
            exc_vals = [r['excursion'] for r in recs]
            isf_vals = [r['isf_norm_exc'] for r in recs]
            spec_vals = [r['spectral_power'] for r in recs]
            carb_summary[cr_label] = {
                'n_meals': len(recs),
                'mean_excursion': round(float(np.mean(exc_vals)), 1),
                'mean_isf_norm': round(float(np.mean(isf_vals)), 3),
                'mean_spectral': round(float(np.mean(spec_vals)), 2),
                'mean_excursion_per_g': round(float(np.mean([r['excursion_per_g'] for r in recs])), 3),
            }

        # Dinner vs lunch comparison (EXP-1336 validation)
        dinner_exc = [r['excursion'] for r in by_period.get('evening', [])]
        lunch_exc = [r['excursion'] for r in by_period.get('midday', [])]

        per_patient[name] = {
            'n_meals': len(all_records),
            'profile_cr': round(profile_cr, 1),
            'profile_isf': round(profile_isf, 1),
            'overall_mean_excursion': round(float(np.mean([r['excursion'] for r in all_records])), 1),
            'overall_mean_isf_norm': round(float(np.mean([r['isf_norm_exc'] for r in all_records])), 3),
            'by_period': period_summary,
            'by_carb_range': carb_summary,
            'dinner_vs_lunch': {
                'dinner_mean': round(float(np.mean(dinner_exc)), 1) if dinner_exc else None,
                'lunch_mean': round(float(np.mean(lunch_exc)), 1) if lunch_exc else None,
                'ratio': round(float(np.mean(dinner_exc)) / max(float(np.mean(lunch_exc)), 1), 3) if dinner_exc and lunch_exc else None,
            }
        }

    # Population summary
    dinner_ratios = [p['dinner_vs_lunch']['ratio'] for p in per_patient.values()
                    if p.get('dinner_vs_lunch', {}).get('ratio') is not None]

    return {
        'experiment': 'EXP-1655',
        'title': 'Effective CR from Meal Windows',
        'n_patients': len(per_patient),
        'population': {
            'mean_dinner_lunch_ratio': round(float(np.mean(dinner_ratios)), 3) if dinner_ratios else None,
            'pct_dinner_worse': round(100 * float(np.mean(np.array(dinner_ratios) > 1.0)), 1) if dinner_ratios else None,
        },
        'per_patient': per_patient,
    }


@register(1657, 'Rolling Settings Drift Detection')
def exp_1657_settings_drift(patients):
    """Detect settings drift using rolling windows of natural experiments.

    Split data into 30-day epochs. Extract basal drift and ISF per epoch.
    Test if settings are stable or trending. Compare to EXP-1338 (5/11 drift).
    """
    per_patient = {}

    for pat in patients:
        name, df = pat['name'], pat['df']
        bg = _bg(df)
        bolus = np.asarray(df.get('bolus', np.zeros(len(bg))), dtype=np.float64)
        carbs_arr = np.asarray(df.get('carbs', np.zeros(len(bg))), dtype=np.float64)
        bolus = np.nan_to_num(bolus.copy(), 0)
        carbs_arr = np.nan_to_num(carbs_arr.copy(), 0)
        profile = df.attrs.get('profile', {})
        profile_isf = _get_profile_isf(df)

        # Get dates for epoch splitting
        dates = _unique_dates(df)
        if len(dates) < 30:
            per_patient[name] = {'error': 'insufficient data', 'n_days': len(dates)}
            continue

        # Create 30-day epochs
        import datetime
        epoch_size = 30
        n_epochs = len(dates) // epoch_size
        if n_epochs < 2:
            per_patient[name] = {'error': 'need ≥2 epochs', 'n_days': len(dates)}
            continue

        epochs = []
        local_dates = _dates_array(df)

        for ei in range(n_epochs):
            epoch_start = dates[ei * epoch_size]
            epoch_end = dates[min((ei + 1) * epoch_size - 1, len(dates) - 1)]

            # Get indices for this epoch
            mask = np.array([(d >= epoch_start and d <= epoch_end) for d in local_dates])
            idx = np.where(mask)[0]
            if len(idx) < STEPS_PER_DAY * 7:  # need at least 7 days of data
                continue

            # Detect fasting windows in this epoch
            epoch_fasting = detect_fasting_windows(
                name, df.iloc[idx], bg[idx],
                bolus[idx], carbs_arr[idx])

            # Detect correction windows in this epoch
            epoch_corrections = detect_correction_windows(
                name, df.iloc[idx], bg[idx],
                bolus[idx], carbs_arr[idx])

            # Extract metrics
            fasting_drifts = [w.measurements.get('drift_mg_dl_per_hour')
                            for w in epoch_fasting
                            if w.measurements.get('drift_mg_dl_per_hour') is not None]

            isf_vals = []
            for w in epoch_corrections:
                m = w.measurements
                isf = m.get('curve_isf') if (m.get('curve_r2') or 0) > 0.3 else m.get('simple_isf')
                if isf and isf > 5:
                    isf_vals.append(isf)

            epochs.append({
                'epoch': ei,
                'start_date': str(epoch_start),
                'end_date': str(epoch_end),
                'n_fasting': len(epoch_fasting),
                'n_corrections': len(epoch_corrections),
                'mean_drift': round(float(np.mean(fasting_drifts)), 3) if fasting_drifts else None,
                'median_isf': round(float(np.median(isf_vals)), 1) if isf_vals else None,
                'n_isf_samples': len(isf_vals),
            })

        if len(epochs) < 2:
            per_patient[name] = {'error': 'insufficient epoch data', 'n_days': len(dates)}
            continue

        # Detect drift: linear trend in extracted settings
        epoch_drifts = [e['mean_drift'] for e in epochs if e['mean_drift'] is not None]
        epoch_isfs = [e['median_isf'] for e in epochs if e['median_isf'] is not None]

        basal_drifting = False
        isf_drifting = False

        if len(epoch_drifts) >= 2:
            drift_trend = np.polyfit(range(len(epoch_drifts)), epoch_drifts, 1)
            basal_drifting = abs(drift_trend[0]) > 0.5  # >0.5 mg/dL/h change per epoch

        if len(epoch_isfs) >= 2:
            isf_trend = np.polyfit(range(len(epoch_isfs)), epoch_isfs, 1)
            isf_drifting = abs(isf_trend[0]) > 3.0  # >3 mg/dL/U change per epoch

        per_patient[name] = {
            'n_days': len(dates),
            'n_epochs': len(epochs),
            'epochs': epochs,
            'basal_drifting': basal_drifting,
            'isf_drifting': isf_drifting,
            'any_drift': basal_drifting or isf_drifting,
            'basal_trend': round(float(drift_trend[0]), 3) if len(epoch_drifts) >= 2 else None,
            'isf_trend': round(float(isf_trend[0]), 1) if len(epoch_isfs) >= 2 else None,
        }

    # Population
    drifters = [name for name, p in per_patient.items() if p.get('any_drift')]
    stable = [name for name, p in per_patient.items()
              if 'any_drift' in p and not p['any_drift']]

    return {
        'experiment': 'EXP-1657',
        'title': 'Rolling Settings Drift Detection',
        'n_patients': len(per_patient),
        'population': {
            'n_drifting': len(drifters),
            'n_stable': len(stable),
            'pct_drifting': round(100 * len(drifters) / max(len(drifters) + len(stable), 1), 1),
            'drifting_patients': drifters,
        },
        'per_patient': per_patient,
    }


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 10: AID EFFECTIVENESS SCORING
# ═══════════════════════════════════════════════════════════════════════════

@register(1661, 'AID Effectiveness Score')
def exp_1661_aid_effectiveness(patients):
    """Compute AID effectiveness score per meal window.

    AID_eff = spectral_power / (isf_norm_excursion + ε)

    High score = AID working hard AND keeping excursion low
    Low score = high excursion despite AID effort (struggling)
    Score interpretation:
      - High effort + low excursion → effective AID
      - Low effort + low excursion → easy meal
      - High effort + high excursion → AID struggling
      - Low effort + high excursion → AID not engaged (missed meal)
    """
    EPS = 0.1  # avoid division by zero
    per_patient = {}

    for pat in patients:
        name, df = pat['name'], pat['df']
        bg = _bg(df)
        bolus = np.asarray(df.get('bolus', np.zeros(len(bg))), dtype=np.float64)
        carbs_arr = np.asarray(df.get('carbs', np.zeros(len(bg))), dtype=np.float64)
        bolus = np.nan_to_num(bolus.copy(), 0)
        carbs_arr = np.nan_to_num(carbs_arr.copy(), 0)
        profile = df.attrs.get('profile', {})
        profile_isf = _get_profile_isf(df)

        try:
            sd = _get_supply_demand(df, pat.get('pk'))
        except Exception:
            per_patient[name] = {'error': 'supply-demand failed'}
            continue

        meals = detect_meal_windows(name, df, bg, bolus, carbs_arr, sd)
        if not meals:
            per_patient[name] = {'n_meals': 0, 'error': 'no meals'}
            continue

        records = []
        for w in meals:
            m = w.measurements
            excursion = m.get('excursion_mg_dl')
            if not excursion or math.isnan(excursion):
                continue

            isf_norm = excursion / max(profile_isf, 1)
            start_i = w.start_idx
            end_i = w.end_idx
            spec_power = _spectral_power_window(bg[start_i:end_i],
                                                sd['net'][start_i:end_i])

            # AID effectiveness score (use absolute ISF-norm to avoid sign issues)
            aid_eff = spec_power / (abs(isf_norm) + EPS)

            # Quadrant classification
            med_spec = 50  # approximate population median, will refine
            med_isf_norm = 1.5
            if spec_power >= med_spec and isf_norm < med_isf_norm:
                quadrant = 'effective'
            elif spec_power < med_spec and isf_norm < med_isf_norm:
                quadrant = 'easy'
            elif spec_power >= med_spec and isf_norm >= med_isf_norm:
                quadrant = 'struggling'
            else:
                quadrant = 'missed'

            records.append({
                'excursion': excursion,
                'isf_norm': round(isf_norm, 3),
                'spectral_power': round(spec_power, 2),
                'aid_effectiveness': round(aid_eff, 3),
                'quadrant': quadrant,
                'carbs_g': m.get('carbs_g', 0),
                'is_announced': m.get('is_announced', False),
                'meal_window': m.get('meal_window', 'snack'),
                'hour': w.hour_of_day,
            })

        if not records:
            per_patient[name] = {'n_meals': len(meals), 'error': 'no valid records'}
            continue

        # Re-classify using patient-specific medians
        spec_vals = [r['spectral_power'] for r in records]
        isf_vals = [r['isf_norm'] for r in records]
        med_spec = float(np.median(spec_vals))
        med_isf = float(np.median(isf_vals))

        for r in records:
            if r['spectral_power'] >= med_spec and r['isf_norm'] < med_isf:
                r['quadrant'] = 'effective'
            elif r['spectral_power'] < med_spec and r['isf_norm'] < med_isf:
                r['quadrant'] = 'easy'
            elif r['spectral_power'] >= med_spec and r['isf_norm'] >= med_isf:
                r['quadrant'] = 'struggling'
            else:
                r['quadrant'] = 'missed'

        eff_scores = [r['aid_effectiveness'] for r in records]
        quadrant_counts = defaultdict(int)
        for r in records:
            quadrant_counts[r['quadrant']] += 1

        # By time of day
        by_period = defaultdict(list)
        for r in records:
            by_period[_time_period(r['hour'])].append(r['aid_effectiveness'])

        period_eff = {p: {'mean': round(float(np.mean(v)), 3),
                         'n': len(v)}
                     for p, v in by_period.items()}

        # Announced vs unannounced
        ann_eff = [r['aid_effectiveness'] for r in records if r['is_announced']]
        uam_eff = [r['aid_effectiveness'] for r in records if not r['is_announced']]

        per_patient[name] = {
            'n_meals': len(records),
            'mean_effectiveness': round(float(np.mean(eff_scores)), 3),
            'median_effectiveness': round(float(np.median(eff_scores)), 3),
            'median_spectral': round(med_spec, 2),
            'median_isf_norm': round(med_isf, 3),
            'quadrant_pct': {q: round(100 * c / len(records), 1)
                           for q, c in quadrant_counts.items()},
            'by_period': period_eff,
            'announced_mean_eff': round(float(np.mean(ann_eff)), 3) if ann_eff else None,
            'unannounced_mean_eff': round(float(np.mean(uam_eff)), 3) if uam_eff else None,
            '_records': records,
        }

    # Population
    pop_eff = [p['mean_effectiveness'] for p in per_patient.values()
               if 'mean_effectiveness' in p]

    return {
        'experiment': 'EXP-1661',
        'title': 'AID Effectiveness Score',
        'n_patients': len(per_patient),
        'population': {
            'mean_effectiveness': round(float(np.mean(pop_eff)), 3) if pop_eff else None,
            'std_effectiveness': round(float(np.std(pop_eff)), 3) if pop_eff else None,
        },
        'per_patient': per_patient,
    }


@register(1663, 'AID Effectiveness × Archetypes')
def exp_1663_aid_arch(patients):
    """Cross AID effectiveness with robustness archetypes.

    Loads EXP-1571 archetype classification and EXP-1661 effectiveness.
    Tests: do robust patients have better AID effectiveness?
    """
    # Load prior results
    prior = _load_prior_results()

    # Need EXP-1571 for archetypes
    arch_data = prior.get(1571, {})
    arch_pp = arch_data.get('per_patient', {})

    # Run EXP-1661 if not already done
    eff_result = exp_1661_aid_effectiveness(patients)
    eff_pp = eff_result.get('per_patient', {})

    tier_effectiveness = defaultdict(list)
    per_patient = {}

    for name in set(list(arch_pp.keys()) + list(eff_pp.keys())):
        arch = arch_pp.get(name, {})
        eff = eff_pp.get(name, {})

        tier = arch.get('tier', 'unknown')
        mean_eff = eff.get('mean_effectiveness')
        quadrant_pct = eff.get('quadrant_pct', {})

        if mean_eff is not None:
            tier_effectiveness[tier].append(mean_eff)

        per_patient[name] = {
            'tier': tier,
            'mean_effectiveness': mean_eff,
            'quadrant_pct': quadrant_pct,
            'n_peaks': arch.get('n_peaks'),
            'std_of_std': arch.get('std_of_std'),
        }

    # Tier comparison
    tier_summary = {}
    for tier, effs in tier_effectiveness.items():
        tier_summary[tier] = {
            'n_patients': len(effs),
            'mean_effectiveness': round(float(np.mean(effs)), 3),
            'std_effectiveness': round(float(np.std(effs)), 3),
        }

    # Correlation: n_peaks vs effectiveness
    n_peaks_vals = [p.get('n_peaks') for p in per_patient.values()
                   if p.get('n_peaks') is not None and p.get('mean_effectiveness') is not None]
    eff_vals = [p['mean_effectiveness'] for p in per_patient.values()
               if p.get('n_peaks') is not None and p.get('mean_effectiveness') is not None]

    if len(n_peaks_vals) >= 5:
        from scipy import stats
        rho, p_val = stats.spearmanr(n_peaks_vals, eff_vals)
    else:
        rho, p_val = None, None

    return {
        'experiment': 'EXP-1663',
        'title': 'AID Effectiveness × Archetypes',
        'n_patients': len(per_patient),
        'tier_summary': tier_summary,
        'correlation': {
            'n_peaks_vs_effectiveness_rho': round(rho, 3) if rho is not None else None,
            'p_value': round(p_val, 4) if p_val is not None else None,
        },
        'per_patient': per_patient,
    }


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 11: CROSS-CLASSIFICATION INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════

@register(1665, 'Cross-Classification Integration')
def exp_1665_cross_classification(patients):
    """Cross-tabulate fidelity × archetype × ISF-norm burden.

    Three independent patient classification systems:
    1. Fidelity (EXP-1531): Excellent/Good/Acceptable/Poor (RMSE)
    2. Archetype (EXP-1571): Robust/Moderate/Sensitive (n_peaks)
    3. ISF-norm burden (EXP-1561): correction-equivalents

    Test: do they capture independent dimensions?
    """
    prior = _load_prior_results()

    fid_data = prior.get(1531, {}).get('per_patient', {})
    arch_data = prior.get(1571, {}).get('per_patient', {})
    isf_data = prior.get(1561, {}).get('per_patient_isf', {})

    per_patient = {}
    classifications = []

    all_patients = set(list(fid_data.keys()) + list(arch_data.keys()) + list(isf_data.keys()))

    for name in sorted(all_patients):
        fid = fid_data.get(name, {})
        arch = arch_data.get(name, {})
        isf = isf_data.get(name, {})

        fidelity_grade = fid.get('fidelity_grade', 'unknown')
        rmse = fid.get('fidelity', {}).get('rmse') if isinstance(fid.get('fidelity'), dict) else None
        ada_grade = fid.get('ada_grade', 'unknown')
        tir = fid.get('ada', {}).get('tir') if isinstance(fid.get('ada'), dict) else None

        tier = arch.get('tier', 'unknown')
        n_peaks = arch.get('n_peaks')

        isf_norm_exc = isf.get('mean_isf_norm_excursion')
        # Burden classification
        if isf_norm_exc is not None:
            if isf_norm_exc < 1.0:
                burden = 'low'
            elif isf_norm_exc < 2.0:
                burden = 'normal'
            else:
                burden = 'high'
        else:
            burden = 'unknown'

        per_patient[name] = {
            'fidelity_grade': fidelity_grade,
            'rmse': round(rmse, 2) if rmse else None,
            'ada_grade': ada_grade,
            'tir': round(tir, 1) if tir else None,
            'archetype': tier,
            'n_peaks': n_peaks,
            'isf_norm_burden': burden,
            'isf_norm_excursion': round(isf_norm_exc, 3) if isf_norm_exc else None,
        }

        if all(v != 'unknown' for v in [fidelity_grade, tier, burden]):
            classifications.append({
                'patient': name,
                'fidelity': fidelity_grade,
                'archetype': tier,
                'burden': burden,
                'rmse': rmse,
                'tir': tir,
                'isf_norm': isf_norm_exc,
            })

    # Cross-tabulation analysis
    # Test independence using pairwise concordance
    concordance = {}
    if len(classifications) >= 5:
        # Fidelity vs Archetype
        fid_ranks = {'Excellent': 4, 'Good': 3, 'Acceptable': 2, 'Poor': 1}
        arch_ranks = {'robust': 3, 'moderate': 2, 'sensitive': 1}
        burden_ranks = {'low': 3, 'normal': 2, 'high': 1}

        fid_r = [fid_ranks.get(c['fidelity'], 0) for c in classifications]
        arch_r = [arch_ranks.get(c['archetype'], 0) for c in classifications]
        burd_r = [burden_ranks.get(c['burden'], 0) for c in classifications]

        try:
            from scipy import stats
            r1, p1 = stats.spearmanr(fid_r, arch_r)
            r2, p2 = stats.spearmanr(fid_r, burd_r)
            r3, p3 = stats.spearmanr(arch_r, burd_r)
            concordance = {
                'fidelity_vs_archetype': {'rho': round(r1, 3), 'p': round(p1, 4)},
                'fidelity_vs_burden': {'rho': round(r2, 3), 'p': round(p2, 4)},
                'archetype_vs_burden': {'rho': round(r3, 3), 'p': round(p3, 4)},
            }
        except Exception:
            pass

    return {
        'experiment': 'EXP-1665',
        'title': 'Cross-Classification Integration',
        'n_patients': len(per_patient),
        'n_fully_classified': len(classifications),
        'concordance': concordance,
        'per_patient': per_patient,
    }


@register(1667, 'Combined Predictive Power')
def exp_1667_combined_prediction(patients):
    """Test if combined classification predicts outcomes better than any single system.

    Use fidelity + archetype + burden to predict TIR and TBR.
    Compare single-predictor R² vs combined R².
    """
    prior = _load_prior_results()

    fid_data = prior.get(1531, {}).get('per_patient', {})
    arch_data = prior.get(1571, {}).get('per_patient', {})
    isf_data = prior.get(1561, {}).get('per_patient_isf', {})

    rows = []
    for name in sorted(set(fid_data.keys()) & set(arch_data.keys())):
        fid = fid_data.get(name, {})
        arch = arch_data.get(name, {})
        isf = isf_data.get(name, {})

        rmse = fid.get('fidelity', {}).get('rmse') if isinstance(fid.get('fidelity'), dict) else None
        tir = fid.get('ada', {}).get('tir') if isinstance(fid.get('ada'), dict) else None
        tbr = fid.get('ada', {}).get('tbr_l1') if isinstance(fid.get('ada'), dict) else None
        n_peaks = arch.get('n_peaks')
        std_of_std = arch.get('std_of_std')
        isf_norm = isf.get('mean_isf_norm_excursion')

        if all(v is not None for v in [rmse, tir, n_peaks]):
            rows.append({
                'patient': name,
                'rmse': rmse,
                'tir': tir,
                'tbr': tbr or 0,
                'n_peaks': n_peaks,
                'std_of_std': std_of_std or 0,
                'isf_norm': isf_norm or 0,
            })

    if len(rows) < 5:
        return {
            'experiment': 'EXP-1667',
            'title': 'Combined Predictive Power',
            'error': f'insufficient data ({len(rows)} patients)',
        }

    # Single predictor correlations with TIR
    from scipy import stats
    tir_arr = np.array([r['tir'] for r in rows])
    rmse_arr = np.array([r['rmse'] for r in rows])
    peaks_arr = np.array([r['n_peaks'] for r in rows])
    isf_arr = np.array([r['isf_norm'] for r in rows])

    single_predictors = {}
    for name, arr in [('rmse', rmse_arr), ('n_peaks', peaks_arr), ('isf_norm', isf_arr)]:
        r, p = stats.spearmanr(arr, tir_arr)
        single_predictors[name] = {
            'rho_vs_tir': round(r, 3),
            'p_value': round(p, 4),
            'r2_approx': round(r ** 2, 3),
        }

    # Combined: simple multivariate via OLS
    X = np.column_stack([rmse_arr, peaks_arr, isf_arr])
    X_centered = X - X.mean(axis=0)
    # Add intercept
    X_aug = np.column_stack([np.ones(len(X)), X_centered])
    try:
        beta = np.linalg.lstsq(X_aug, tir_arr, rcond=None)[0]
        pred = X_aug @ beta
        ss_res = np.sum((tir_arr - pred) ** 2)
        ss_tot = np.sum((tir_arr - np.mean(tir_arr)) ** 2)
        combined_r2 = 1 - ss_res / max(ss_tot, 1e-10)
    except Exception:
        combined_r2 = None

    return {
        'experiment': 'EXP-1667',
        'title': 'Combined Predictive Power',
        'n_patients': len(rows),
        'single_predictors': single_predictors,
        'combined_r2': round(combined_r2, 3) if combined_r2 is not None else None,
        'best_single': max(single_predictors.items(),
                          key=lambda x: abs(x[1]['rho_vs_tir']))[0],
        'improvement_vs_best': round(
            combined_r2 - max(abs(sp['r2_approx']) for sp in single_predictors.values()), 3
        ) if combined_r2 is not None else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 12: UAM SIGNATURE LIBRARY
# ═══════════════════════════════════════════════════════════════════════════

@register(1669, 'UAM Shape Clustering')
def exp_1669_uam_clustering(patients):
    """Cluster UAM glucose shapes using PCA on normalized traces.

    Standardize UAM windows to fixed length, normalize by ISF, apply PCA,
    then k-means cluster. Compare to EXP-1591-1598 2-phenotype finding.
    """
    TRACE_LENGTH = 36  # 3 hours at 5-min steps
    per_patient = {}
    all_traces = []
    all_meta = []

    for pat in patients:
        name, df = pat['name'], pat['df']
        bg = _bg(df)
        carbs_arr = np.asarray(df.get('carbs', np.zeros(len(bg))), dtype=np.float64)
        carbs_arr = np.nan_to_num(carbs_arr.copy(), 0)
        profile = df.attrs.get('profile', {})
        profile_isf = _get_profile_isf(df)

        try:
            sd = _get_supply_demand(df, pat.get('pk'))
        except Exception:
            continue

        uam_windows = detect_uam_windows(name, df, bg, carbs_arr, sd)

        patient_traces = []
        for w in uam_windows:
            # Need at least 15 min of UAM + 3h observation
            start_i = w.start_idx
            end_i = min(start_i + TRACE_LENGTH, len(bg))
            if end_i - start_i < 18:  # need at least 1.5h
                continue

            seg = bg[start_i:end_i].copy()
            coverage = _cgm_coverage(seg)
            if coverage < 0.7:
                continue

            # Interpolate NaN gaps
            valid = ~np.isnan(seg)
            if not np.all(valid) and np.sum(valid) >= 6:
                xp = np.where(valid)[0]
                fp = seg[valid]
                seg = np.interp(np.arange(len(seg)), xp, fp)

            # Normalize: subtract start, divide by ISF
            baseline = seg[0]
            if np.isnan(baseline):
                continue
            norm_trace = (seg - baseline) / max(profile_isf, 1)

            # Pad or truncate to fixed length
            if len(norm_trace) < TRACE_LENGTH:
                padded = np.full(TRACE_LENGTH, norm_trace[-1])
                padded[:len(norm_trace)] = norm_trace
                norm_trace = padded

            norm_trace = norm_trace[:TRACE_LENGTH]
            patient_traces.append(norm_trace)
            all_traces.append(norm_trace)
            all_meta.append({
                'patient': name,
                'hour': w.hour_of_day,
                'subtype': w.measurements.get('subtype', 'unknown') if hasattr(w.measurements, 'get') else 'unknown',
                'duration_min': w.duration_minutes,
                'peak_residual': w.measurements.get('peak_residual', 0) if isinstance(w.measurements, dict) else 0,
            })

        per_patient[name] = {
            'n_uam_windows': len(uam_windows),
            'n_valid_traces': len(patient_traces),
        }

    if len(all_traces) < 20:
        return {
            'experiment': 'EXP-1669',
            'title': 'UAM Shape Clustering',
            'error': f'insufficient traces ({len(all_traces)})',
        }

    trace_matrix = np.array(all_traces)

    # PCA
    from sklearn.decomposition import PCA as _PCA
    try:
        pca = _PCA(n_components=min(5, trace_matrix.shape[0], trace_matrix.shape[1]))
        projected = pca.fit_transform(trace_matrix)
        explained = pca.explained_variance_ratio_
    except ImportError:
        # Manual PCA via SVD
        centered = trace_matrix - trace_matrix.mean(axis=0)
        U, S, Vt = np.linalg.svd(centered, full_matrices=False)
        k = min(5, len(S))
        projected = U[:, :k] * S[:k]
        explained = (S[:k] ** 2) / np.sum(S ** 2)

    # K-means clustering (try k=2,3,4,5)
    best_k = 2
    best_score = -999
    cluster_results = {}

    for k in [2, 3, 4, 5]:
        try:
            from sklearn.cluster import KMeans as _KMeans
            km = _KMeans(n_clusters=k, n_init=10, random_state=42)
            labels = km.fit_predict(projected[:, :3])
        except ImportError:
            # Simple k-means
            labels = _simple_kmeans(projected[:, :min(3, projected.shape[1])], k)

        # Compute silhouette-like score (mean intra/inter ratio)
        intra = []
        inter = []
        for ci in range(k):
            mask = labels == ci
            if np.sum(mask) < 2:
                continue
            cluster_pts = projected[mask, :3]
            centroid = cluster_pts.mean(axis=0)
            intra.extend(np.linalg.norm(cluster_pts - centroid, axis=1))
            other_pts = projected[~mask, :3]
            if len(other_pts) > 0:
                inter.extend(np.linalg.norm(other_pts - centroid, axis=1))

        if intra and inter:
            score = float(np.mean(inter)) / max(float(np.mean(intra)), 0.01)
        else:
            score = 0

        cluster_results[k] = {
            'score': round(score, 3),
            'sizes': [int(np.sum(labels == ci)) for ci in range(k)],
        }
        if score > best_score:
            best_score = score
            best_k = k
            best_labels = labels

    # Characterize best clusters
    cluster_profiles = {}
    for ci in range(best_k):
        mask = best_labels == ci
        c_traces = trace_matrix[mask]
        c_meta = [all_meta[i] for i in range(len(all_meta)) if mask[i]]

        # Mean trace shape
        mean_trace = c_traces.mean(axis=0)
        peak_idx = np.argmax(mean_trace)
        peak_val = float(mean_trace[peak_idx])

        # Classify shape
        if peak_idx <= 6 and peak_val > 1.0:
            shape = 'fast_spike'
        elif peak_idx > 12 and peak_val > 0.5:
            shape = 'slow_rise'
        elif peak_val < 0.5:
            shape = 'minimal'
        else:
            shape = 'moderate'

        cluster_profiles[f'cluster_{ci}'] = {
            'n_traces': int(np.sum(mask)),
            'mean_peak_isf_norm': round(peak_val, 3),
            'peak_time_min': int(peak_idx * STEP_MINUTES),
            'shape_type': shape,
            'mean_trace': [round(float(v), 4) for v in mean_trace],
            'subtype_distribution': dict(defaultdict(int,
                {m.get('subtype', 'unknown'): sum(1 for m2 in c_meta if m2.get('subtype') == m.get('subtype'))
                 for m in c_meta})),
        }

    # Per-patient cluster distribution
    for name in per_patient:
        pt_mask = np.array([m['patient'] == name for m in all_meta])
        if np.sum(pt_mask) > 0:
            pt_labels = best_labels[pt_mask]
            per_patient[name]['cluster_distribution'] = {
                f'cluster_{ci}': int(np.sum(pt_labels == ci))
                for ci in range(best_k)
            }

    return {
        'experiment': 'EXP-1669',
        'title': 'UAM Shape Clustering',
        'n_traces': len(all_traces),
        'n_patients': len(per_patient),
        'pca_explained_variance': [round(float(v), 4) for v in explained],
        'best_k': best_k,
        'cluster_results': cluster_results,
        'cluster_profiles': cluster_profiles,
        'per_patient': per_patient,
    }


def _simple_kmeans(X, k, max_iter=100):
    """Simple k-means when sklearn not available."""
    n = X.shape[0]
    rng = np.random.RandomState(42)
    centroids = X[rng.choice(n, k, replace=False)]
    labels = np.zeros(n, dtype=int)
    for _ in range(max_iter):
        # Assign
        dists = np.array([np.linalg.norm(X - c, axis=1) for c in centroids])
        new_labels = np.argmin(dists, axis=0)
        if np.all(new_labels == labels):
            break
        labels = new_labels
        # Update
        for ci in range(k):
            mask = labels == ci
            if np.sum(mask) > 0:
                centroids[ci] = X[mask].mean(axis=0)
    return labels


@register(1671, 'UAM Trajectory Prediction')
def exp_1671_uam_prediction(patients):
    """Predict UAM trajectory from first 15 min using cluster templates.

    Given the first 3 steps (15 min) of a UAM rise, match to the closest
    cluster template and predict the remaining trajectory.
    Measure prediction error (RMSE) by cluster.
    """
    # First run EXP-1669 to get clusters
    cluster_result = exp_1669_uam_clustering(patients)
    if 'error' in cluster_result:
        return {
            'experiment': 'EXP-1671',
            'title': 'UAM Trajectory Prediction',
            'error': cluster_result['error'],
        }

    cluster_profiles = cluster_result.get('cluster_profiles', {})
    best_k = cluster_result.get('best_k', 2)

    # Get cluster mean traces as templates
    templates = {}
    for cname, cprof in cluster_profiles.items():
        templates[cname] = np.array(cprof['mean_trace'])

    # Now re-detect UAM windows and do leave-one-out prediction
    TRACE_LENGTH = 36
    OBSERVE_STEPS = 3  # 15 min of observation before prediction
    prediction_results = []

    for pat in patients:
        name, df = pat['name'], pat['df']
        bg = _bg(df)
        carbs_arr = np.asarray(df.get('carbs', np.zeros(len(bg))), dtype=np.float64)
        carbs_arr = np.nan_to_num(carbs_arr.copy(), 0)
        profile = df.attrs.get('profile', {})
        profile_isf = _get_profile_isf(df)

        try:
            sd = _get_supply_demand(df, pat.get('pk'))
        except Exception:
            continue

        uam_windows = detect_uam_windows(name, df, bg, carbs_arr, sd)

        for w in uam_windows:
            start_i = w.start_idx
            end_i = min(start_i + TRACE_LENGTH, len(bg))
            if end_i - start_i < 18:
                continue

            seg = bg[start_i:end_i].copy()
            coverage = _cgm_coverage(seg)
            if coverage < 0.7:
                continue

            valid = ~np.isnan(seg)
            if not np.all(valid) and np.sum(valid) >= 6:
                xp = np.where(valid)[0]
                fp = seg[valid]
                seg = np.interp(np.arange(len(seg)), xp, fp)

            baseline = seg[0]
            if np.isnan(baseline):
                continue
            norm_trace = (seg - baseline) / max(profile_isf, 1)

            if len(norm_trace) < TRACE_LENGTH:
                padded = np.full(TRACE_LENGTH, norm_trace[-1])
                padded[:len(norm_trace)] = norm_trace
                norm_trace = padded
            norm_trace = norm_trace[:TRACE_LENGTH]

            # Match first OBSERVE_STEPS to closest template
            observed = norm_trace[:OBSERVE_STEPS]
            best_dist = float('inf')
            best_template = None
            best_cluster = None

            for cname, tmpl in templates.items():
                dist = float(np.sum((observed - tmpl[:OBSERVE_STEPS]) ** 2))
                if dist < best_dist:
                    best_dist = dist
                    best_template = tmpl
                    best_cluster = cname

            # Predict remaining trajectory using template
            predicted = best_template[OBSERVE_STEPS:]
            actual = norm_trace[OBSERVE_STEPS:]
            rmse = float(np.sqrt(np.mean((predicted - actual) ** 2)))

            # Also compute naive baseline: just extend last observed value
            naive_pred = np.full(len(actual), observed[-1])
            naive_rmse = float(np.sqrt(np.mean((naive_pred - actual) ** 2)))

            prediction_results.append({
                'patient': name,
                'cluster': best_cluster,
                'rmse': round(rmse, 4),
                'naive_rmse': round(naive_rmse, 4),
                'improvement': round(naive_rmse - rmse, 4),
                'pct_improvement': round(100 * (naive_rmse - rmse) / max(naive_rmse, 0.001), 1),
            })

    if not prediction_results:
        return {
            'experiment': 'EXP-1671',
            'title': 'UAM Trajectory Prediction',
            'error': 'no valid predictions',
        }

    # Summary
    rmses = [r['rmse'] for r in prediction_results]
    naive_rmses = [r['naive_rmse'] for r in prediction_results]
    improvements = [r['pct_improvement'] for r in prediction_results]

    # By cluster
    by_cluster = defaultdict(list)
    for r in prediction_results:
        by_cluster[r['cluster']].append(r)

    cluster_accuracy = {}
    for cname, recs in by_cluster.items():
        c_rmses = [r['rmse'] for r in recs]
        c_naive = [r['naive_rmse'] for r in recs]
        cluster_accuracy[cname] = {
            'n_predictions': len(recs),
            'mean_rmse': round(float(np.mean(c_rmses)), 4),
            'mean_naive_rmse': round(float(np.mean(c_naive)), 4),
            'pct_improvement': round(100 * (np.mean(c_naive) - np.mean(c_rmses)) / max(np.mean(c_naive), 0.001), 1),
            'pct_beats_naive': round(100 * float(np.mean(np.array(c_rmses) < np.array(c_naive))), 1),
        }

    return {
        'experiment': 'EXP-1671',
        'title': 'UAM Trajectory Prediction',
        'n_predictions': len(prediction_results),
        'overall': {
            'mean_rmse': round(float(np.mean(rmses)), 4),
            'mean_naive_rmse': round(float(np.mean(naive_rmses)), 4),
            'mean_pct_improvement': round(float(np.mean(improvements)), 1),
            'pct_beats_naive': round(100 * float(np.mean(np.array(rmses) < np.array(naive_rmses))), 1),
        },
        'by_cluster': cluster_accuracy,
    }


# ═══════════════════════════════════════════════════════════════════════════
# VISUALIZATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_phase9_visualizations(results):
    """Generate fig44-47 for settings extraction experiments."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(str(VIZ_DIR), exist_ok=True)

    # fig44: Basal adequacy by patient and time period
    if 1651 in results:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        pp = results[1651].get('per_patient', {})
        patients = sorted([n for n in pp if 'overall_drift_mg_dl_h' in pp[n]])
        drifts = [pp[n]['overall_drift_mg_dl_h'] for n in patients]
        colors = ['#e74c3c' if d > 2 else '#2ecc71' if abs(d) <= 2 else '#3498db' for d in drifts]

        axes[0].barh(patients, drifts, color=colors)
        axes[0].axvline(x=0, color='black', linewidth=0.5)
        axes[0].axvline(x=2, color='red', linewidth=0.5, linestyle='--', alpha=0.5)
        axes[0].axvline(x=-2, color='blue', linewidth=0.5, linestyle='--', alpha=0.5)
        axes[0].set_xlabel('Fasting Drift (mg/dL/h)')
        axes[0].set_title('Basal Adequacy from Fasting Windows')
        axes[0].text(2.2, len(patients) - 0.5, 'basal\ntoo low', fontsize=8, color='red', alpha=0.7)
        axes[0].text(-4.5, len(patients) - 0.5, 'basal\ntoo high', fontsize=8, color='blue', alpha=0.7)

        # By period heatmap
        periods = ['overnight', 'morning', 'midday', 'afternoon', 'evening']
        matrix = []
        for n in patients:
            row = []
            bp = pp[n].get('by_period', {})
            for p in periods:
                row.append(bp.get(p, {}).get('quality_weighted_drift', 0))
            matrix.append(row)
        matrix = np.array(matrix)

        im = axes[1].imshow(matrix, aspect='auto', cmap='RdBu_r', vmin=-5, vmax=5)
        axes[1].set_xticks(range(len(periods)))
        axes[1].set_xticklabels(periods, rotation=45, ha='right')
        axes[1].set_yticks(range(len(patients)))
        axes[1].set_yticklabels(patients)
        axes[1].set_title('Drift by Time Period')
        plt.colorbar(im, ax=axes[1], label='mg/dL/h')

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig44_basal_adequacy.png'), dpi=150)
        plt.close()
        print('  ✓ fig44_basal_adequacy.png')

    # fig45: ISF by time of day
    if 1653 in results:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        pp = results[1653].get('per_patient', {})
        patients = sorted([n for n in pp if 'mismatch_ratio' in pp[n]])

        # Mismatch ratios
        ratios = [pp[n]['mismatch_ratio'] for n in patients]
        colors = ['#e74c3c' if r > 1.5 else '#f39c12' if r > 1.2 else '#2ecc71' for r in ratios]
        axes[0].barh(patients, ratios, color=colors)
        axes[0].axvline(x=1.0, color='black', linewidth=1, linestyle='--')
        axes[0].set_xlabel('Extracted ISF / Profile ISF')
        axes[0].set_title('ISF Mismatch: Natural Experiments vs Profile')
        axes[0].text(1.02, -0.5, 'profile\nunderestimates', fontsize=8, alpha=0.7)

        # ISF by time period
        periods = ['overnight', 'morning', 'midday', 'afternoon', 'evening']
        for i, n in enumerate(patients):
            bp = pp[n].get('by_period', {})
            means = [bp.get(p, {}).get('mean_isf', None) for p in periods]
            valid_x = [j for j, m in enumerate(means) if m is not None]
            valid_y = [m for m in means if m is not None]
            if valid_y:
                axes[1].plot(valid_x, valid_y, 'o-', label=n, alpha=0.7)

        axes[1].set_xticks(range(len(periods)))
        axes[1].set_xticklabels(periods, rotation=45, ha='right')
        axes[1].set_ylabel('Extracted ISF (mg/dL/U)')
        axes[1].set_title('ISF Variation by Time of Day')
        axes[1].legend(fontsize=7, ncol=2)

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig45_isf_extraction.png'), dpi=150)
        plt.close()
        print('  ✓ fig45_isf_extraction.png')

    # fig46: CR by carb range × time
    if 1655 in results:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        pp = results[1655].get('per_patient', {})
        patients = sorted([n for n in pp if 'dinner_vs_lunch' in pp[n] and
                         pp[n].get('dinner_vs_lunch', {}).get('ratio') is not None])

        if patients:
            # Dinner vs lunch ratios
            ratios = [pp[n]['dinner_vs_lunch']['ratio'] for n in patients]
            colors = ['#e74c3c' if r > 1.3 else '#f39c12' if r > 1.1 else '#2ecc71' for r in ratios]
            axes[0].barh(patients, ratios, color=colors)
            axes[0].axvline(x=1.0, color='black', linewidth=1, linestyle='--')
            axes[0].set_xlabel('Dinner / Lunch Excursion Ratio')
            axes[0].set_title('Dinner vs Lunch Excursion')

            # Excursion by carb range (population)
            carb_ranges = ['<10g', '10-19g', '20-29g', '30-49g', '≥50g']
            for n in patients[:6]:  # top 6 for readability
                by_cr = pp[n].get('by_carb_range', {})
                exc_vals = [by_cr.get(cr, {}).get('mean_excursion', 0) for cr in carb_ranges]
                axes[1].plot(carb_ranges, exc_vals, 'o-', label=n, alpha=0.7)

            axes[1].set_xlabel('Carb Range')
            axes[1].set_ylabel('Mean Excursion (mg/dL)')
            axes[1].set_title('Excursion by Carb Range')
            axes[1].legend(fontsize=7)

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig46_cr_extraction.png'), dpi=150)
        plt.close()
        print('  ✓ fig46_cr_extraction.png')

    # fig47: Settings drift timeline
    if 1657 in results:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        pp = results[1657].get('per_patient', {})
        patients = sorted([n for n in pp if 'epochs' in pp[n] and len(pp[n].get('epochs', [])) >= 2])

        for n in patients:
            epochs = pp[n]['epochs']
            x = list(range(len(epochs)))
            drifts = [e.get('mean_drift') for e in epochs]
            valid_x = [xi for xi, d in zip(x, drifts) if d is not None]
            valid_d = [d for d in drifts if d is not None]
            if valid_d:
                style = '--' if pp[n].get('basal_drifting') else '-'
                axes[0].plot(valid_x, valid_d, f'o{style}', label=n, alpha=0.7)

        axes[0].axhline(y=0, color='black', linewidth=0.5)
        axes[0].axhline(y=2, color='red', linewidth=0.5, linestyle=':', alpha=0.5)
        axes[0].axhline(y=-2, color='blue', linewidth=0.5, linestyle=':', alpha=0.5)
        axes[0].set_xlabel('30-day Epoch')
        axes[0].set_ylabel('Mean Fasting Drift (mg/dL/h)')
        axes[0].set_title('Basal Drift Over Time')
        axes[0].legend(fontsize=7, ncol=2)

        # ISF drift
        for n in patients:
            epochs = pp[n]['epochs']
            x = list(range(len(epochs)))
            isfs = [e.get('median_isf') for e in epochs]
            valid_x = [xi for xi, d in zip(x, isfs) if d is not None]
            valid_isf = [d for d in isfs if d is not None]
            if valid_isf:
                style = '--' if pp[n].get('isf_drifting') else '-'
                axes[1].plot(valid_x, valid_isf, f'o{style}', label=n, alpha=0.7)

        axes[1].set_xlabel('30-day Epoch')
        axes[1].set_ylabel('Median Extracted ISF (mg/dL/U)')
        axes[1].set_title('ISF Drift Over Time')
        axes[1].legend(fontsize=7, ncol=2)

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig47_settings_drift.png'), dpi=150)
        plt.close()
        print('  ✓ fig47_settings_drift.png')


def generate_phase10_visualizations(results):
    """Generate fig48-49 for AID effectiveness experiments."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(str(VIZ_DIR), exist_ok=True)

    # fig48: AID effectiveness quadrants
    if 1661 in results:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        pp = results[1661].get('per_patient', {})
        patients = sorted([n for n in pp if 'quadrant_pct' in pp[n]])

        tier_colors = {'robust': '#2ecc71', 'moderate': '#f39c12', 'sensitive': '#e74c3c'}

        # Scatter of all meals (from a sample patient)
        for pi, n in enumerate(patients):
            recs = pp[n].get('_records', [])
            if recs:
                spec = [r['spectral_power'] for r in recs[:200]]
                isf_n = [r['isf_norm'] for r in recs[:200]]
                axes[0].scatter(spec, isf_n, alpha=0.3, s=10, label=n)

        axes[0].set_xlabel('Spectral Power (AID Effort)')
        axes[0].set_ylabel('ISF-Normalized Excursion')
        axes[0].set_title('AID Effectiveness: Effort vs Outcome')
        axes[0].legend(fontsize=6, ncol=2)

        # Quadrant distribution by patient
        quadrants = ['effective', 'easy', 'struggling', 'missed']
        q_colors = ['#2ecc71', '#3498db', '#e74c3c', '#f39c12']
        x = np.arange(len(patients))
        bottoms = np.zeros(len(patients))

        for qi, q in enumerate(quadrants):
            vals = [pp[n].get('quadrant_pct', {}).get(q, 0) for n in patients]
            axes[1].bar(x, vals, bottom=bottoms, color=q_colors[qi], label=q)
            bottoms += np.array(vals)

        axes[1].set_xticks(x)
        axes[1].set_xticklabels(patients, rotation=45, ha='right')
        axes[1].set_ylabel('% of Meals')
        axes[1].set_title('AID Response Quadrant Distribution')
        axes[1].legend()

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig48_aid_effectiveness.png'), dpi=150)
        plt.close()
        print('  ✓ fig48_aid_effectiveness.png')

    # fig49: Archetype × effectiveness
    if 1663 in results:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        ts = results[1663].get('tier_summary', {})
        pp = results[1663].get('per_patient', {})

        tier_colors = {'robust': '#2ecc71', 'moderate': '#f39c12', 'sensitive': '#e74c3c', 'unknown': '#999'}

        if ts:
            tiers = sorted(ts.keys())
            means = [ts[t]['mean_effectiveness'] for t in tiers]
            stds = [ts[t]['std_effectiveness'] for t in tiers]
            colors = [tier_colors.get(t, '#999') for t in tiers]
            axes[0].bar(tiers, means, yerr=stds, color=colors, capsize=5)
            axes[0].set_ylabel('Mean AID Effectiveness')
            axes[0].set_title('AID Effectiveness by Archetype')

        # n_peaks vs effectiveness scatter
        peaks = [p['n_peaks'] for p in pp.values() if p.get('n_peaks') and p.get('mean_effectiveness')]
        effs = [p['mean_effectiveness'] for p in pp.values() if p.get('n_peaks') and p.get('mean_effectiveness')]
        tiers = [p.get('tier', 'unknown') for p in pp.values() if p.get('n_peaks') and p.get('mean_effectiveness')]
        colors = [tier_colors.get(t, '#999') for t in tiers]

        if peaks and effs:
            axes[1].scatter(peaks, effs, c=colors, s=80, edgecolors='black', linewidth=0.5)
            for i, name in enumerate([n for n, p in pp.items() if p.get('n_peaks') and p.get('mean_effectiveness')]):
                axes[1].annotate(name, (peaks[i], effs[i]), fontsize=8, ha='center', va='bottom')

        corr = results[1663].get('correlation', {})
        rho = corr.get('n_peaks_vs_effectiveness_rho')
        if rho is not None:
            axes[1].set_title(f'n_peaks vs AID Effectiveness (ρ={rho})')
        else:
            axes[1].set_title('n_peaks vs AID Effectiveness')
        axes[1].set_xlabel('Number of Meal Peaks (n_peaks)')
        axes[1].set_ylabel('Mean AID Effectiveness')

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig49_aid_archetypes.png'), dpi=150)
        plt.close()
        print('  ✓ fig49_aid_archetypes.png')


def generate_phase11_visualizations(results):
    """Generate fig50-51 for cross-classification experiments."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(str(VIZ_DIR), exist_ok=True)

    # fig50: Cross-classification heatmap
    if 1665 in results:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        pp = results[1665].get('per_patient', {})
        patients = sorted(pp.keys())

        # Multi-classification comparison table
        categories = ['fidelity_grade', 'archetype', 'isf_norm_burden']
        cat_labels = ['Fidelity', 'Archetype', 'Burden']
        grade_colors = {
            'Excellent': '#2ecc71', 'Good': '#27ae60', 'Acceptable': '#f39c12', 'Poor': '#e74c3c',
            'robust': '#2ecc71', 'moderate': '#f39c12', 'sensitive': '#e74c3c',
            'low': '#2ecc71', 'normal': '#f39c12', 'high': '#e74c3c',
            'unknown': '#cccccc',
        }

        for pi, n in enumerate(patients):
            for ci, cat in enumerate(categories):
                val = pp[n].get(cat, 'unknown')
                color = grade_colors.get(val, '#cccccc')
                axes[0].add_patch(plt.Rectangle((ci, pi), 1, 1, facecolor=color, edgecolor='white'))
                axes[0].text(ci + 0.5, pi + 0.5, val[:4], ha='center', va='center', fontsize=7)

        axes[0].set_xlim(0, len(categories))
        axes[0].set_ylim(0, len(patients))
        axes[0].set_xticks([i + 0.5 for i in range(len(categories))])
        axes[0].set_xticklabels(cat_labels)
        axes[0].set_yticks([i + 0.5 for i in range(len(patients))])
        axes[0].set_yticklabels(patients)
        axes[0].set_title('Three Classification Systems')

        # Concordance matrix
        conc = results[1665].get('concordance', {})
        pairs = list(conc.keys())
        rhos = [conc[p].get('rho', 0) for p in pairs]
        if pairs:
            colors = ['#2ecc71' if abs(r) < 0.3 else '#f39c12' if abs(r) < 0.6 else '#e74c3c' for r in rhos]
            bars = axes[1].barh(pairs, rhos, color=colors)
            axes[1].axvline(x=0, color='black', linewidth=0.5)
            axes[1].set_xlabel('Spearman ρ')
            axes[1].set_title('Pairwise Concordance (low ρ = independent)')
            for i, (p, r) in enumerate(zip(pairs, rhos)):
                axes[1].text(r + 0.02, i, f'{r:.3f}', va='center', fontsize=9)

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig50_cross_classification.png'), dpi=150)
        plt.close()
        print('  ✓ fig50_cross_classification.png')

    # fig51: Combined predictive power
    if 1667 in results and 'single_predictors' in results[1667]:
        fig, ax = plt.subplots(figsize=(8, 5))

        sp = results[1667]['single_predictors']
        combined = results[1667].get('combined_r2')

        names = list(sp.keys()) + ['combined']
        r2s = [abs(sp[k]['r2_approx']) for k in sp] + [combined if combined else 0]
        colors = ['#3498db'] * len(sp) + ['#e74c3c']

        ax.bar(names, r2s, color=colors)
        ax.set_ylabel('R² (TIR prediction)')
        ax.set_title('Single vs Combined Predictive Power')
        for i, v in enumerate(r2s):
            ax.text(i, v + 0.01, f'{v:.3f}', ha='center', fontsize=9)

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig51_combined_prediction.png'), dpi=150)
        plt.close()
        print('  ✓ fig51_combined_prediction.png')


def generate_phase12_visualizations(results):
    """Generate fig52-53 for UAM signature experiments."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(str(VIZ_DIR), exist_ok=True)

    # fig52: UAM cluster shapes
    if 1669 in results and 'cluster_profiles' in results[1669]:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        cp = results[1669]['cluster_profiles']
        colors = ['#2ecc71', '#3498db', '#e74c3c', '#f39c12', '#9b59b6']

        for ci, (cname, cprof) in enumerate(sorted(cp.items())):
            trace = cprof['mean_trace']
            x = np.arange(len(trace)) * 5  # minutes
            label = f'{cname}: {cprof["shape_type"]} (n={cprof["n_traces"]})'
            axes[0].plot(x, trace, color=colors[ci % len(colors)],
                        linewidth=2, label=label)

        axes[0].set_xlabel('Time (minutes)')
        axes[0].set_ylabel('ISF-Normalized Glucose Change')
        axes[0].set_title('UAM Cluster Mean Traces')
        axes[0].legend()
        axes[0].axhline(y=0, color='black', linewidth=0.5)

        # Cluster sizes
        pca_var = results[1669].get('pca_explained_variance', [])
        if pca_var:
            cum_var = np.cumsum(pca_var)
            axes[1].bar(range(len(pca_var)), pca_var, color='#3498db', alpha=0.7, label='Individual')
            axes[1].plot(range(len(cum_var)), cum_var, 'ro-', label='Cumulative')
            axes[1].set_xlabel('Principal Component')
            axes[1].set_ylabel('Explained Variance Ratio')
            axes[1].set_title('PCA Variance Explained')
            axes[1].legend()

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig52_uam_clusters.png'), dpi=150)
        plt.close()
        print('  ✓ fig52_uam_clusters.png')

    # fig53: UAM prediction accuracy
    if 1671 in results and 'by_cluster' in results[1671]:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        overall = results[1671].get('overall', {})
        by_cluster = results[1671]['by_cluster']

        # Overall: template vs naive
        names = ['Template\nPrediction', 'Naive\n(flat line)']
        rmses = [overall.get('mean_rmse', 0), overall.get('mean_naive_rmse', 0)]
        colors = ['#2ecc71', '#e74c3c']
        axes[0].bar(names, rmses, color=colors)
        axes[0].set_ylabel('Mean RMSE (ISF-normalized)')
        axes[0].set_title(f'Template vs Naive Prediction\n'
                         f'({overall.get("pct_beats_naive", 0):.0f}% beats naive)')

        # By cluster
        clusters = sorted(by_cluster.keys())
        rmse_vals = [by_cluster[c]['mean_rmse'] for c in clusters]
        naive_vals = [by_cluster[c]['mean_naive_rmse'] for c in clusters]
        x = np.arange(len(clusters))
        w = 0.35
        axes[1].bar(x - w/2, rmse_vals, w, label='Template', color='#2ecc71')
        axes[1].bar(x + w/2, naive_vals, w, label='Naive', color='#e74c3c')
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(clusters, rotation=45, ha='right')
        axes[1].set_ylabel('Mean RMSE')
        axes[1].set_title('Prediction Accuracy by Cluster')
        axes[1].legend()

        plt.tight_layout()
        plt.savefig(str(VIZ_DIR / 'fig53_uam_prediction.png'), dpi=150)
        plt.close()
        print('  ✓ fig53_uam_prediction.png')


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='EXP-1651-1671: Settings Probes, AID Effectiveness & Integration')
    parser.add_argument('--exp', type=int, default=0, help='Run single experiment (0=all)')
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--patients-dir', type=str, default=None)
    parser.add_argument('--no-viz', action='store_true', help='Skip visualizations')
    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"EXP-1651-1671: Settings Probes, AID Effectiveness & Integration")
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

            # Save — skip large internal fields
            skip_keys = {'_records', '_traces', '_all_traces'}
            out_path = RESULTS_DIR / f'exp-{exp_id}_settings_probes.json'
            filtered = {k: v for k, v in result.items() if k not in skip_keys}

            with open(str(out_path), 'w') as f:
                json.dump(filtered, f, indent=2, default=str)
            print(f"  ✓ Saved to {out_path.name} ({elapsed:.1f}s)")

            # Print summary
            if 'population' in result:
                print(f"  Population: {json.dumps(result['population'], indent=2, default=str)[:300]}")
            elif 'overall' in result:
                print(f"  Overall: {json.dumps(result['overall'], indent=2, default=str)[:300]}")
            elif 'tier_summary' in result:
                print(f"  Tiers: {json.dumps(result['tier_summary'], indent=2, default=str)[:300]}")

        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            traceback.print_exc()
            all_results[exp_id] = {'error': str(e)}

    # Visualizations
    if not args.no_viz and all_results:
        print(f"\n{'─'*60}")
        print("Generating visualizations...")
        print(f"{'─'*60}")

        try:
            generate_phase9_visualizations(all_results)
        except Exception as e:
            print(f"  ✗ Phase 9 viz failed: {e}")
            traceback.print_exc()

        try:
            generate_phase10_visualizations(all_results)
        except Exception as e:
            print(f"  ✗ Phase 10 viz failed: {e}")
            traceback.print_exc()

        try:
            generate_phase11_visualizations(all_results)
        except Exception as e:
            print(f"  ✗ Phase 11 viz failed: {e}")
            traceback.print_exc()

        try:
            generate_phase12_visualizations(all_results)
        except Exception as e:
            print(f"  ✗ Phase 12 viz failed: {e}")
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
