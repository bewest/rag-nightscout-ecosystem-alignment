#!/usr/bin/env python3
"""EXP-1531 to EXP-1538: Physics-Model Fidelity as Primary Therapy Metric.

Hypothesis: ADA 2019 consensus targets (TIR≥70%, TBR<4%, CV<36%) grade
outcomes but not therapy quality. A patient can meet ADA targets while
their AID loop compensates for badly calibrated settings. Physics-model
fidelity — how closely the PK supply-demand model predicts actual glucose
dynamics — measures therapy calibration independent of outcome judgment.

Shifting from "how good are your numbers" to "how well do your settings
match the science" respects patient autonomy in balancing disease mgmt
with quality of life, while providing actionable settings feedback.

Builds on:
  - EXP-495: ISF fidelity (effective ISF = 2.91× profile ISF)
  - EXP-500: Weekly fidelity trend (composite score)
  - EXP-559: Correction energy (r=-0.353 with TIR)
  - EXP-747: AID compensation detection
  - EXP-1521-1528: Holdout validation (25-35% recommendation drift)

EXP-1531: Compute per-patient fidelity metrics (R², RMSE, conservation)
EXP-1532: Fidelity vs ADA concordance/discordance analysis
EXP-1533: Fidelity-based grading system (replace A/B/C/D)
EXP-1534: Correction energy as fidelity signal
EXP-1535: Temporal stability of fidelity vs ADA metrics
EXP-1536: Event-type decomposition of fidelity (fasting vs postprandial)
EXP-1537: Production integration — FidelityAssessment dataclass
EXP-1538: Visualization — fidelity dashboard per patient
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
from cgmencode.exp_metabolic_441 import compute_supply_demand

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PATIENTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..',
                            'externals', 'ns-data', 'patients')
RESULTS_DIR = (Path(__file__).resolve().parent.parent.parent
               / 'externals' / 'experiments')

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 24 * STEPS_PER_HOUR
TIR_LO, TIR_HI = 70, 180
HYPO_THRESHOLD = 70
SEVERE_HYPO_THRESHOLD = 54

# Fidelity thresholds (calibrated from EXP-1531 empirical distribution)
# Note: R² is universally negative for raw physics dBG/dt prediction — this
# is expected because unmeasured meals (46.5%) and CGM noise dominate.
# Fidelity grading uses RMSE + correction_energy as primary signals.
FIDELITY_EXCELLENT_RMSE = 6.0     # mg/dL per 5-min step (top quartile)
FIDELITY_GOOD_RMSE = 9.0          # median range
FIDELITY_ACCEPTABLE_RMSE = 11.0   # below median
FIDELITY_EXCELLENT_ENERGY = 600   # daily correction energy (low = settings aligned)
FIDELITY_GOOD_ENERGY = 1000
FIDELITY_ACCEPTABLE_ENERGY = 1600

EXPERIMENTS = {}


def register(exp_id, title):
    """Register experiment function."""
    def decorator(fn):
        EXPERIMENTS[exp_id] = (title, fn)
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def load_patients(max_patients=11, patients_dir=None):
    """Load patient data with CGM + PK channels."""
    return _load_patients(patients_dir or PATIENTS_DIR, max_patients=max_patients)


def _get_bg(df):
    col = 'glucose' if 'glucose' in df.columns else 'sgv'
    return np.asarray(df[col], dtype=np.float64)


def _compute_fidelity_metrics(bg, flux_dict, window_steps=STEPS_PER_HOUR):
    """Core fidelity computation: how well does the physics model explain
    observed glucose changes?

    Returns dict with R², RMSE, bias, conservation integral, and
    per-window breakdown.
    """
    supply = flux_dict['supply']
    demand = flux_dict['demand']
    net_flux = supply - demand
    N = min(len(bg), len(net_flux))
    bg, net_flux, supply, demand = bg[:N], net_flux[:N], supply[:N], demand[:N]

    # Actual glucose rate of change (dBG/dt in mg/dL per 5-min step)
    actual_dbg = np.diff(bg)
    predicted_dbg = net_flux[:-1]  # net_flux predicts dBG/dt

    # Remove NaN
    valid = ~(np.isnan(actual_dbg) | np.isnan(predicted_dbg))
    actual_v = actual_dbg[valid]
    pred_v = predicted_dbg[valid]

    if len(actual_v) < 100:
        return None

    # Residuals
    residual = actual_v - pred_v

    # R² — variance explained by physics model
    ss_res = np.sum(residual ** 2)
    ss_tot = np.sum((actual_v - np.mean(actual_v)) ** 2)
    r2 = 1.0 - ss_res / max(ss_tot, 1e-10)

    # RMSE
    rmse = float(np.sqrt(np.mean(residual ** 2)))

    # Bias (systematic over/under-prediction)
    bias = float(np.mean(residual))

    # Conservation integral: cumulative predicted vs actual over 24h windows
    # Perfect fidelity → conservation integral ≈ 0
    conservation_integrals = []
    for start in range(0, len(actual_v) - STEPS_PER_DAY, STEPS_PER_DAY):
        end = start + STEPS_PER_DAY
        cum_actual = np.sum(actual_v[start:end])
        cum_pred = np.sum(pred_v[start:end])
        conservation_integrals.append(float(abs(cum_actual - cum_pred)))

    conservation_mean = float(np.mean(conservation_integrals)) if conservation_integrals else 0.0

    # Correction energy: daily integral of |net_flux| — how hard AID works
    correction_energies = []
    for start in range(0, N - STEPS_PER_DAY, STEPS_PER_DAY):
        end = start + STEPS_PER_DAY
        correction_energies.append(float(np.sum(np.abs(net_flux[start:end]))))

    correction_energy_mean = float(np.mean(correction_energies)) if correction_energies else 0.0

    # Effective ISF ratio proxy: |actual response| / |predicted response|
    # during correction events (high insulin, no carbs)
    isf_ratio_samples = []
    for i in range(len(actual_v) - 36):
        if demand[i] > np.percentile(demand[demand > 0], 70) if np.any(demand > 0) else False:
            if supply[i] < np.median(supply):  # low carb period
                if abs(pred_v[i]) > 0.5:
                    isf_ratio_samples.append(actual_v[i] / pred_v[i])
    isf_ratio = float(np.median(isf_ratio_samples)) if len(isf_ratio_samples) > 10 else float('nan')

    return {
        'r2': float(r2),
        'rmse': rmse,
        'bias': bias,
        'conservation_integral': conservation_mean,
        'correction_energy': correction_energy_mean,
        'isf_ratio': isf_ratio,
        'n_samples': int(len(actual_v)),
        'residual_p5': float(np.percentile(residual, 5)),
        'residual_p95': float(np.percentile(residual, 95)),
        'residual_std': float(np.std(residual)),
    }


def _compute_tir_metrics(bg):
    """Standard TIR/TBR/TAR/CV from glucose array."""
    valid = bg[~np.isnan(bg)]
    if len(valid) < 100:
        return None
    tir = float(np.mean((valid >= TIR_LO) & (valid <= TIR_HI)) * 100)
    tbr_l1 = float(np.mean((valid >= SEVERE_HYPO_THRESHOLD) & (valid < HYPO_THRESHOLD)) * 100)
    tbr_l2 = float(np.mean(valid < SEVERE_HYPO_THRESHOLD) * 100)
    tar_l1 = float(np.mean((valid > TIR_HI) & (valid <= 250)) * 100)
    tar_l2 = float(np.mean(valid > 250) * 100)
    cv = float(np.std(valid) / np.mean(valid) * 100) if np.mean(valid) > 0 else 0.0
    mean_bg = float(np.mean(valid))
    gmi = (mean_bg + 46.7) / 28.7
    return {
        'tir': tir, 'tbr_l1': tbr_l1, 'tbr_l2': tbr_l2,
        'tar_l1': tar_l1, 'tar_l2': tar_l2, 'cv': cv,
        'mean_glucose': mean_bg, 'gmi': round(gmi, 2),
    }


def _ada_grade(tir, tbr_total):
    """Legacy ADA-based grade for comparison."""
    if tir >= 70 and tbr_total < 4:
        return 'A'
    elif tir >= 60 and tbr_total < 5:
        return 'B'
    elif tir >= 50:
        return 'C'
    return 'D'


def _fidelity_grade(rmse, correction_energy):
    """Fidelity grade based on RMSE and correction energy.

    R² is universally negative for raw physics prediction (expected —
    unmeasured meals dominate), so grading uses RMSE (model error magnitude)
    and correction energy (how hard AID works to compensate).
    """
    if rmse is None or correction_energy is None:
        return 'Unknown'
    if rmse <= FIDELITY_EXCELLENT_RMSE and correction_energy <= FIDELITY_EXCELLENT_ENERGY:
        return 'Excellent'
    elif rmse <= FIDELITY_GOOD_RMSE and correction_energy <= FIDELITY_GOOD_ENERGY:
        return 'Good'
    elif rmse <= FIDELITY_ACCEPTABLE_RMSE and correction_energy <= FIDELITY_ACCEPTABLE_ENERGY:
        return 'Acceptable'
    return 'Poor'


# ── EXP-1531: Per-Patient Fidelity Metrics ────────────────────────────────

@register(1531, 'Per-Patient Physics Fidelity Metrics')
def exp_1531(patients):
    """Hypothesis: Physics-model fidelity (R², RMSE, conservation) provides
    a meaningful per-patient therapy quality metric independent of ADA targets.

    Protocol:
      1. For each patient, compute supply-demand decomposition
      2. Compute fidelity metrics: R², RMSE, bias, conservation integral
      3. Compute traditional ADA metrics for comparison
      4. Report fidelity distribution across cohort
    """
    results = {}
    for p in patients:
        try:
            bg = _get_bg(p['df'])
            fd = compute_supply_demand(p['df'], p['pk'])
            fidelity = _compute_fidelity_metrics(bg, fd)
            tir_metrics = _compute_tir_metrics(bg)
            if fidelity is None or tir_metrics is None:
                continue
            results[p['name']] = {
                'fidelity': fidelity,
                'ada': tir_metrics,
                'ada_grade': _ada_grade(tir_metrics['tir'],
                                        tir_metrics['tbr_l1'] + tir_metrics['tbr_l2']),
                'fidelity_grade': _fidelity_grade(fidelity['rmse'],
                                                  fidelity['correction_energy']),
            }
            print(f"  {p['name']}: R²={fidelity['r2']:.3f}  RMSE={fidelity['rmse']:.2f}  "
                  f"TIR={tir_metrics['tir']:.1f}%  "
                  f"ADA={results[p['name']]['ada_grade']}  "
                  f"Fidelity={results[p['name']]['fidelity_grade']}")
        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")
            traceback.print_exc()

    # Population summary
    r2s = [v['fidelity']['r2'] for v in results.values()]
    rmses = [v['fidelity']['rmse'] for v in results.values()]
    ada_grades = [v['ada_grade'] for v in results.values()]
    fidelity_grades = [v['fidelity_grade'] for v in results.values()]

    summary = {
        'experiment': 'EXP-1531: Per-Patient Physics Fidelity Metrics',
        'hypothesis': 'Physics-model fidelity provides meaningful therapy quality independent of ADA',
        'n_patients': len(results),
        'population': {
            'r2_mean': float(np.mean(r2s)),
            'r2_median': float(np.median(r2s)),
            'r2_std': float(np.std(r2s)),
            'rmse_mean': float(np.mean(rmses)),
            'rmse_median': float(np.median(rmses)),
            'ada_grade_distribution': {g: ada_grades.count(g) for g in 'ABCD'},
            'fidelity_grade_distribution': {g: fidelity_grades.count(g)
                                             for g in ['Excellent', 'Good', 'Acceptable', 'Poor']},
        },
        'per_patient': results,
    }
    return summary


# ── EXP-1532: Fidelity vs ADA Concordance/Discordance ─────────────────────

@register(1532, 'Fidelity vs ADA Concordance Analysis')
def exp_1532(patients):
    """Hypothesis: Fidelity and ADA grades will discordant for patients where
    AID compensates for bad settings (good TIR but poor model fit) or where
    settings are well-calibrated but outcomes are limited by physiology.

    Protocol:
      1. Run EXP-1531 metrics for all patients
      2. Identify concordant (both good or both poor) vs discordant pairs
      3. Characterize discordant patients: what explains the disagreement?
    """
    base = exp_1531(patients)
    if base is None:
        return None

    concordance = {'concordant': [], 'discordant_ada_better': [],
                   'discordant_fidelity_better': []}
    ada_rank = {'A': 4, 'B': 3, 'C': 2, 'D': 1}
    fid_rank = {'Excellent': 4, 'Good': 3, 'Acceptable': 2, 'Poor': 1}

    for name, data in base['per_patient'].items():
        ada_r = ada_rank.get(data['ada_grade'], 0)
        fid_r = fid_rank.get(data['fidelity_grade'], 0)
        diff = ada_r - fid_r

        entry = {
            'patient': name,
            'ada_grade': data['ada_grade'],
            'fidelity_grade': data['fidelity_grade'],
            'r2': data['fidelity']['r2'],
            'rmse': data['fidelity']['rmse'],
            'tir': data['ada']['tir'],
            'correction_energy': data['fidelity']['correction_energy'],
            'isf_ratio': data['fidelity']['isf_ratio'],
            'interpretation': '',
        }

        if abs(diff) <= 1:
            entry['interpretation'] = 'Grades agree: settings align with outcomes'
            concordance['concordant'].append(entry)
        elif diff > 1:
            entry['interpretation'] = ('ADA grade better than fidelity: '
                                       'AID likely compensating for miscalibrated settings')
            concordance['discordant_ada_better'].append(entry)
        else:
            entry['interpretation'] = ('Fidelity better than ADA: '
                                       'Settings well-calibrated but physiology limits outcomes')
            concordance['discordant_fidelity_better'].append(entry)

    result = {
        'experiment': 'EXP-1532: Fidelity vs ADA Concordance Analysis',
        'hypothesis': 'AID compensation creates discordance between outcome and calibration quality',
        'concordant_count': len(concordance['concordant']),
        'discordant_ada_better': len(concordance['discordant_ada_better']),
        'discordant_fidelity_better': len(concordance['discordant_fidelity_better']),
        'concordance_rate': (len(concordance['concordant']) /
                             max(1, sum(len(v) for v in concordance.values()))),
        'details': concordance,
        'base_results': base,
    }
    return result


# ── EXP-1533: Fidelity-Based Grading System ───────────────────────────────

@register(1533, 'Fidelity Grading System Design')
def exp_1533(patients):
    """Design a fidelity-based grading system that replaces ADA A/B/C/D.

    Protocol:
      1. Compute all fidelity metrics across patients
      2. Find natural breakpoints via percentile analysis
      3. Define grade boundaries from data distribution
      4. Validate grades are stable across temporal splits
    """
    base = exp_1531(patients)
    if base is None:
        return None

    # Collect all per-patient metrics
    r2s = [v['fidelity']['r2'] for v in base['per_patient'].values()]
    rmses = [v['fidelity']['rmse'] for v in base['per_patient'].values()]
    corrections = [v['fidelity']['correction_energy'] for v in base['per_patient'].values()]
    conservations = [v['fidelity']['conservation_integral'] for v in base['per_patient'].values()]
    biases = [abs(v['fidelity']['bias']) for v in base['per_patient'].values()]

    # Composite fidelity score: weighted combination
    # Higher R² is better, lower RMSE/bias/correction_energy/conservation is better
    composite_scores = {}
    for name, data in base['per_patient'].items():
        f = data['fidelity']
        # Normalize each component to 0-100 scale
        r2_score = max(0, min(100, f['r2'] * 100))                     # 0-100
        rmse_score = max(0, min(100, 100 - f['rmse'] * 10))             # lower=better
        bias_score = max(0, min(100, 100 - abs(f['bias']) * 20))        # lower=better
        conservation_score = max(0, min(100, 100 - f['conservation_integral'] * 0.5))
        energy_score = max(0, min(100, 100 - f['correction_energy'] * 0.05))

        # Weighted composite
        composite = (r2_score * 0.35 +
                     rmse_score * 0.25 +
                     bias_score * 0.15 +
                     conservation_score * 0.10 +
                     energy_score * 0.15)

        composite_scores[name] = {
            'composite': float(composite),
            'r2_score': float(r2_score),
            'rmse_score': float(rmse_score),
            'bias_score': float(bias_score),
            'conservation_score': float(conservation_score),
            'energy_score': float(energy_score),
        }

    scores = [v['composite'] for v in composite_scores.values()]

    # Grade boundaries from distribution
    p25 = float(np.percentile(scores, 25))
    p50 = float(np.percentile(scores, 50))
    p75 = float(np.percentile(scores, 75))

    grade_map = {}
    for name, data in composite_scores.items():
        s = data['composite']
        if s >= p75:
            grade_map[name] = 'Excellent'
        elif s >= p50:
            grade_map[name] = 'Good'
        elif s >= p25:
            grade_map[name] = 'Acceptable'
        else:
            grade_map[name] = 'Poor'

    # Temporal stability: split each patient 50/50
    stability_results = {}
    for p in patients:
        try:
            bg = _get_bg(p['df'])
            fd = compute_supply_demand(p['df'], p['pk'])
            n = len(bg)
            mid = n // 2

            bg_1, bg_2 = bg[:mid], bg[mid:]
            fd_1 = {k: v[:mid] for k, v in fd.items() if isinstance(v, np.ndarray) and len(v) == n}
            fd_2 = {k: v[mid:] for k, v in fd.items() if isinstance(v, np.ndarray) and len(v) == n}

            f1 = _compute_fidelity_metrics(bg_1, fd_1)
            f2 = _compute_fidelity_metrics(bg_2, fd_2)
            if f1 and f2:
                stability_results[p['name']] = {
                    'r2_first_half': f1['r2'],
                    'r2_second_half': f2['r2'],
                    'r2_drift': f2['r2'] - f1['r2'],
                    'rmse_first_half': f1['rmse'],
                    'rmse_second_half': f2['rmse'],
                    'rmse_drift': f2['rmse'] - f1['rmse'],
                }
        except Exception:
            pass

    r2_drifts = [v['r2_drift'] for v in stability_results.values()]
    rmse_drifts = [v['rmse_drift'] for v in stability_results.values()]

    result = {
        'experiment': 'EXP-1533: Fidelity Grading System Design',
        'hypothesis': 'Composite fidelity score produces stable, meaningful grades',
        'weights': {'r2': 0.35, 'rmse': 0.25, 'bias': 0.15, 'conservation': 0.10, 'energy': 0.15},
        'grade_boundaries': {'p25': p25, 'p50': p50, 'p75': p75},
        'per_patient_scores': composite_scores,
        'per_patient_grades': grade_map,
        'temporal_stability': {
            'per_patient': stability_results,
            'r2_drift_mean': float(np.mean(r2_drifts)) if r2_drifts else None,
            'r2_drift_std': float(np.std(r2_drifts)) if r2_drifts else None,
            'rmse_drift_mean': float(np.mean(rmse_drifts)) if rmse_drifts else None,
        },
        'base_results': base,
    }
    return result


# ── EXP-1534: Correction Energy as Fidelity Signal ────────────────────────

@register(1534, 'Correction Energy as Fidelity Signal')
def exp_1534(patients):
    """Hypothesis: Correction energy (daily ∫|net_flux|) correlates with
    fidelity metrics better than with TIR, because it measures how hard
    the AID works rather than the outcome achieved.

    Protocol:
      1. Compute daily correction energy + fidelity + TIR for each patient
      2. Correlate correction_energy with R², RMSE, TIR
      3. Test: does high correction_energy predict poor fidelity or poor TIR better?
    """
    from scipy import stats as sp_stats

    results = {}
    all_ce, all_r2, all_rmse, all_tir = [], [], [], []

    for p in patients:
        try:
            bg = _get_bg(p['df'])
            fd = compute_supply_demand(p['df'], p['pk'])
            fidelity = _compute_fidelity_metrics(bg, fd)
            tir_m = _compute_tir_metrics(bg)
            if fidelity is None or tir_m is None:
                continue
            results[p['name']] = {
                'correction_energy': fidelity['correction_energy'],
                'r2': fidelity['r2'],
                'rmse': fidelity['rmse'],
                'tir': tir_m['tir'],
            }
            all_ce.append(fidelity['correction_energy'])
            all_r2.append(fidelity['r2'])
            all_rmse.append(fidelity['rmse'])
            all_tir.append(tir_m['tir'])
        except Exception:
            pass

    # Correlations
    corr_ce_r2 = sp_stats.pearsonr(all_ce, all_r2) if len(all_ce) >= 3 else (0, 1)
    corr_ce_rmse = sp_stats.pearsonr(all_ce, all_rmse) if len(all_ce) >= 3 else (0, 1)
    corr_ce_tir = sp_stats.pearsonr(all_ce, all_tir) if len(all_ce) >= 3 else (0, 1)
    corr_r2_tir = sp_stats.pearsonr(all_r2, all_tir) if len(all_r2) >= 3 else (0, 1)

    return {
        'experiment': 'EXP-1534: Correction Energy as Fidelity Signal',
        'hypothesis': 'Correction energy better predicts fidelity than TIR',
        'n_patients': len(results),
        'correlations': {
            'ce_vs_r2': {'r': float(corr_ce_r2[0]), 'p': float(corr_ce_r2[1])},
            'ce_vs_rmse': {'r': float(corr_ce_rmse[0]), 'p': float(corr_ce_rmse[1])},
            'ce_vs_tir': {'r': float(corr_ce_tir[0]), 'p': float(corr_ce_tir[1])},
            'r2_vs_tir': {'r': float(corr_r2_tir[0]), 'p': float(corr_r2_tir[1])},
        },
        'interpretation': {
            'ce_stronger_for_fidelity': abs(corr_ce_r2[0]) > abs(corr_ce_tir[0]),
            'fidelity_independent_of_tir': abs(corr_r2_tir[0]) < 0.5,
        },
        'per_patient': results,
    }


# ── EXP-1535: Temporal Stability Comparison ────────────────────────────────

@register(1535, 'Temporal Stability: Fidelity vs ADA')
def exp_1535(patients):
    """Hypothesis: Fidelity metrics are more temporally stable than ADA TIR
    across weekly windows, because physics relationships are more constant
    than glucose outcomes (which vary with meals, stress, activity).

    Protocol:
      1. Compute weekly fidelity (R², RMSE) and weekly TIR for each patient
      2. Measure coefficient of variation across weeks
      3. Compare: which metric has lower week-to-week variability?
    """
    results = {}

    for p in patients:
        try:
            bg = _get_bg(p['df'])
            fd = compute_supply_demand(p['df'], p['pk'])
            n = min(len(bg), min(len(v) for v in fd.values()
                                  if isinstance(v, np.ndarray)))
            weekly_steps = 7 * STEPS_PER_DAY

            weekly_r2, weekly_rmse, weekly_tir = [], [], []
            for start in range(0, n - weekly_steps, weekly_steps):
                end = start + weekly_steps
                bg_w = bg[start:end]
                fd_w = {k: v[start:end] for k, v in fd.items()
                        if isinstance(v, np.ndarray) and len(v) >= n}

                f = _compute_fidelity_metrics(bg_w, fd_w)
                t = _compute_tir_metrics(bg_w)
                if f and t:
                    weekly_r2.append(f['r2'])
                    weekly_rmse.append(f['rmse'])
                    weekly_tir.append(t['tir'])

            if len(weekly_r2) >= 3:
                def _cv(vals):
                    m = np.mean(vals)
                    return float(np.std(vals) / abs(m)) if abs(m) > 1e-6 else float('inf')

                results[p['name']] = {
                    'n_weeks': len(weekly_r2),
                    'r2_cv': _cv(weekly_r2),
                    'rmse_cv': _cv(weekly_rmse),
                    'tir_cv': _cv(weekly_tir),
                    'r2_mean': float(np.mean(weekly_r2)),
                    'rmse_mean': float(np.mean(weekly_rmse)),
                    'tir_mean': float(np.mean(weekly_tir)),
                    'r2_values': [float(x) for x in weekly_r2],
                    'rmse_values': [float(x) for x in weekly_rmse],
                    'tir_values': [float(x) for x in weekly_tir],
                }
        except Exception:
            pass

    r2_cvs = [v['r2_cv'] for v in results.values() if v['r2_cv'] < float('inf')]
    tir_cvs = [v['tir_cv'] for v in results.values() if v['tir_cv'] < float('inf')]

    return {
        'experiment': 'EXP-1535: Temporal Stability Comparison',
        'hypothesis': 'Fidelity metrics have lower week-to-week variability than TIR',
        'n_patients': len(results),
        'population': {
            'r2_cv_mean': float(np.mean(r2_cvs)) if r2_cvs else None,
            'tir_cv_mean': float(np.mean(tir_cvs)) if tir_cvs else None,
            'fidelity_more_stable': (float(np.mean(r2_cvs)) < float(np.mean(tir_cvs)))
            if r2_cvs and tir_cvs else None,
        },
        'per_patient': results,
    }


# ── EXP-1536: Event-Type Fidelity Decomposition ───────────────────────────

@register(1536, 'Event-Type Fidelity Decomposition')
def exp_1536(patients):
    """Hypothesis: Fidelity differs dramatically between fasting (basal-only)
    and postprandial (meal) windows. Decomposing fidelity by event type
    reveals which therapy setting is miscalibrated.

    Protocol:
      1. Classify each timestep as fasting vs postprandial (COB-based)
      2. Compute fidelity separately for each
      3. Report: basal fidelity (fasting R²) vs CR fidelity (postprandial R²)
    """
    results = {}

    for p in patients:
        try:
            bg = _get_bg(p['df'])
            fd = compute_supply_demand(p['df'], p['pk'])
            supply = fd['supply']
            demand = fd['demand']
            carb_supply = fd.get('carb_supply', np.zeros(len(bg)))
            n = min(len(bg), len(supply))
            bg, supply, demand = bg[:n], supply[:n], demand[:n]
            carb_supply = carb_supply[:n]

            # Classify periods
            # Fasting: carb_supply near zero for ≥2h
            carb_smooth = np.convolve(np.abs(carb_supply),
                                       np.ones(STEPS_PER_HOUR * 2) / (STEPS_PER_HOUR * 2),
                                       mode='same')
            is_fasting = carb_smooth < 0.05
            is_postprandial = ~is_fasting

            net_flux = supply - demand
            actual_dbg = np.diff(bg)
            pred_dbg = net_flux[:-1]
            valid = ~(np.isnan(actual_dbg) | np.isnan(pred_dbg))

            fasting_mask = is_fasting[:-1] & valid
            postprandial_mask = is_postprandial[:-1] & valid

            def _r2_rmse(mask):
                a = actual_dbg[mask]
                p_v = pred_dbg[mask]
                if len(a) < 50:
                    return None, None
                ss_res = np.sum((a - p_v) ** 2)
                ss_tot = np.sum((a - np.mean(a)) ** 2)
                r2 = 1.0 - ss_res / max(ss_tot, 1e-10)
                rmse = float(np.sqrt(np.mean((a - p_v) ** 2)))
                return float(r2), rmse

            fasting_r2, fasting_rmse = _r2_rmse(fasting_mask)
            pp_r2, pp_rmse = _r2_rmse(postprandial_mask)

            # Per-period correction energy
            fasting_ce = float(np.sum(np.abs(net_flux[:-1][fasting_mask])))
            pp_ce = float(np.sum(np.abs(net_flux[:-1][postprandial_mask])))
            fasting_days = max(1, np.sum(fasting_mask) / STEPS_PER_DAY)
            pp_days = max(1, np.sum(postprandial_mask) / STEPS_PER_DAY)

            results[p['name']] = {
                'fasting_r2': fasting_r2,
                'fasting_rmse': fasting_rmse,
                'fasting_fraction': float(np.mean(is_fasting)),
                'postprandial_r2': pp_r2,
                'postprandial_rmse': pp_rmse,
                'postprandial_fraction': float(np.mean(is_postprandial)),
                'basal_settings_quality': _fidelity_grade(
                    fasting_rmse, fasting_ce / fasting_days)
                if fasting_rmse is not None else 'Insufficient data',
                'cr_settings_quality': _fidelity_grade(
                    pp_rmse, pp_ce / pp_days)
                if pp_rmse is not None else 'Insufficient data',
            }
            print(f"  {p['name']}: Fasting R²={fasting_r2 if fasting_r2 is not None else 0:.3f}  "
                  f"Postprandial R²={pp_r2 if pp_r2 is not None else 0:.3f}")
        except Exception as e:
            print(f"  {p['name']}: FAILED — {e}")

    return {
        'experiment': 'EXP-1536: Event-Type Fidelity Decomposition',
        'hypothesis': 'Fidelity differs between fasting and postprandial windows',
        'n_patients': len(results),
        'per_patient': results,
    }


# ── EXP-1537: Production FidelityAssessment Dataclass ──────────────────────

@register(1537, 'Production FidelityAssessment Design')
def exp_1537(patients):
    """Design and validate the FidelityAssessment dataclass for production.

    Protocol:
      1. Run full fidelity analysis for all patients
      2. Define the production dataclass fields
      3. Validate all fields are computable in production context
      4. Output example FidelityAssessment objects
    """
    base = exp_1531(patients)
    decomp = exp_1536(patients)
    stability = exp_1535(patients)

    production_assessments = {}
    for name, data in base['per_patient'].items():
        f = data['fidelity']
        decomp_data = decomp.get('per_patient', {}).get(name, {})
        stab_data = stability.get('per_patient', {}).get(name, {})

        assessment = {
            # Primary fidelity metrics
            'r2': f['r2'],
            'rmse': f['rmse'],
            'bias': f['bias'],
            'conservation_integral': f['conservation_integral'],
            'correction_energy': f['correction_energy'],
            'isf_ratio': f['isf_ratio'],

            # Decomposed fidelity
            'fasting_r2': decomp_data.get('fasting_r2'),
            'postprandial_r2': decomp_data.get('postprandial_r2'),
            'basal_quality': decomp_data.get('basal_settings_quality', 'Unknown'),
            'cr_quality': decomp_data.get('cr_settings_quality', 'Unknown'),

            # Stability
            'weekly_r2_cv': stab_data.get('r2_cv'),
            'weekly_rmse_cv': stab_data.get('rmse_cv'),

            # Grade (fidelity-based, not ADA)
            'fidelity_grade': data['fidelity_grade'],

            # Safety floor (ADA as constraint, not primary)
            'ada_safety': {
                'tbr_meets_constraint': data['ada']['tbr_l1'] + data['ada']['tbr_l2'] < 4.0,
                'tbr_total': data['ada']['tbr_l1'] + data['ada']['tbr_l2'],
            },
        }
        production_assessments[name] = assessment

    return {
        'experiment': 'EXP-1537: Production FidelityAssessment Design',
        'hypothesis': 'FidelityAssessment captures therapy quality without ADA judgment',
        'n_patients': len(production_assessments),
        'dataclass_fields': list(next(iter(production_assessments.values())).keys()),
        'assessments': production_assessments,
    }


# ── EXP-1538: Visualization Data ──────────────────────────────────────────

@register(1538, 'Fidelity Dashboard Visualization Data')
def exp_1538(patients):
    """Generate visualization-ready data for the fidelity dashboard.

    Protocol:
      1. Collect all metrics from EXP-1531-1537
      2. Format for matplotlib/ASCII visualization
      3. Output comparison tables and chart data
    """
    base = exp_1531(patients)
    concordance = exp_1532(patients)
    grading = exp_1533(patients)
    energy = exp_1534(patients)

    # Build comparison table
    comparison_table = []
    for name in sorted(base['per_patient'].keys()):
        d = base['per_patient'][name]
        grade_data = grading['per_patient_scores'].get(name, {})
        comparison_table.append({
            'patient': name,
            'ada_grade': d['ada_grade'],
            'fidelity_grade': d['fidelity_grade'],
            'composite_score': grade_data.get('composite', 0),
            'r2': d['fidelity']['r2'],
            'rmse': d['fidelity']['rmse'],
            'tir': d['ada']['tir'],
            'correction_energy': d['fidelity']['correction_energy'],
            'concordant': d['ada_grade'] == d['fidelity_grade'] or
                          abs(ord(d['ada_grade']) - {'Excellent': 65, 'Good': 66,
                               'Acceptable': 67, 'Poor': 68}.get(d['fidelity_grade'], 70)) <= 1,
        })

    return {
        'experiment': 'EXP-1538: Fidelity Dashboard Visualization Data',
        'comparison_table': comparison_table,
        'concordance_summary': {
            'concordant': concordance['concordant_count'],
            'discordant_ada_better': concordance['discordant_ada_better'],
            'discordant_fidelity_better': concordance['discordant_fidelity_better'],
        },
        'correlations': energy['correlations'],
    }


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-1531-1538: Physics-Model Fidelity as Primary Therapy Metric')
    parser.add_argument('--exp', type=int, default=0,
                        help='Run specific experiment (0=all)')
    parser.add_argument('--patients-dir', default=PATIENTS_DIR)
    parser.add_argument('--max-patients', type=int, default=11)
    args = parser.parse_args()

    _patients_dir = args.patients_dir

    print(f"\n{'='*70}")
    print(f"EXP-1531-1538: Physics-Model Fidelity Therapy Assessment")
    print(f"{'='*70}\n")

    patients = load_patients(args.max_patients, _patients_dir)
    print(f"Loaded {len(patients)} patients\n")

    os.makedirs(str(RESULTS_DIR), exist_ok=True)
    all_results = {}

    if args.exp == 0:
        run_ids = sorted(EXPERIMENTS.keys())
    else:
        run_ids = [args.exp]

    for exp_id in run_ids:
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

            out_path = RESULTS_DIR / f'exp-{exp_id}_fidelity.json'
            with open(str(out_path), 'w') as f:
                json.dump(result, f, indent=2, default=str)
            print(f"  ✓ Saved → {out_path}  ({elapsed:.1f}s)")
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            traceback.print_exc()

    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY: {len(all_results)}/{len(run_ids)} experiments completed")
    print(f"{'='*70}")

    if 1531 in all_results:
        pop = all_results[1531]['population']
        print(f"  R² mean={pop['r2_mean']:.3f} ± {pop['r2_std']:.3f}")
        print(f"  RMSE mean={pop['rmse_mean']:.2f} mg/dL")
        print(f"  ADA grades: {pop['ada_grade_distribution']}")
        print(f"  Fidelity grades: {pop['fidelity_grade_distribution']}")

    # Save combined results
    combined_path = RESULTS_DIR / 'exp-1531_fidelity_combined.json'
    with open(str(combined_path), 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nCombined results → {combined_path}")


if __name__ == '__main__':
    main()
