#!/usr/bin/env python3
"""EXP-1501 to EXP-1510: v10 Pipeline Comprehensive Validation & Safety Refinement.

Final validation batch for the therapy detection campaign (230 total).
Follows up on EXP-1491-1500 TBR integration with:
- Per-patient safety protocol impact simulation
- TBR trajectory analysis (monthly windows)
- Insulin-hypo causal analysis
- Post-meal vs fasting hypo classification
- TBR-specific numeric recommendation refinement
- Hypo cluster detection
- Recovery time vs setting mismatch correlation
- Cross-patient safety benchmarking
- TBR impact on A1C estimation
- Pipeline v10 bootstrap stress test
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
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from cgmencode.exp_metabolic_flux import load_patients as _load_patients

# ---------------------------------------------------------------------------
# Paths & results directory
# ---------------------------------------------------------------------------
PATIENTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..',
                            'externals', 'ns-data', 'patients')

RESULTS_DIR = (Path(__file__).resolve().parent.parent.parent
               / 'externals' / 'experiments')

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 24 * STEPS_PER_HOUR        # 288
WEEKLY_STEPS = 7 * STEPS_PER_DAY

TIR_LO = 70    # mg/dL
TIR_HI = 180   # mg/dL

# ADA thresholds
TBR_L1_LO = 54
TBR_L1_HI = 69
TBR_L2_HI = 53
TAR_L1_LO = 181
TAR_L1_HI = 250
TAR_L2_LO = 251

ADA_TBR_L1_TARGET = 4.0
ADA_TBR_L2_TARGET = 1.0
ADA_CV_TARGET = 36.0

# Grade boundaries
GRADE_D_CEIL = 50
GRADE_C_CEIL = 65
GRADE_B_CEIL = 80

# Therapy adjustment constants
CONSERVATIVE_BASAL_PCT = 10
CR_ADJUST_STANDARD = 30
CR_ADJUST_GRADE_D = 50
ISF_ADJUST_PCT = 10
DIA_DEFAULT = 6.0
DIA_STEPS = int(DIA_DEFAULT * STEPS_PER_HOUR)

# Hypo detection
HYPO_THRESHOLD = 70
SEVERE_HYPO_THRESHOLD = 54
HYPO_MIN_DURATION_STEPS = 3

# ISF estimation
MIN_BOLUS_ISF = 2.0
MIN_ISF_EVENTS = 5
DEFAULT_ISF = 50.0
DEFAULT_CR = 10.0
DEFAULT_BASAL_RATE = 1.0

# Score weights v9
SCORE_WEIGHTS = {'tir': 60, 'basal': 15, 'cr': 15, 'isf': 5, 'cv': 5}
DRIFT_THRESHOLD = 5.0
EXCURSION_THRESHOLD = 70
CV_THRESHOLD = 36

# Bootstrap
N_BOOTSTRAP_STRESS = 100
RNG_SEED = 42

EXPERIMENTS = {}


def _safe_round(val, decimals=2):
    """Round safely, handling NaN/Inf."""
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return 0.0
    return round(float(val), decimals)


# ---------------------------------------------------------------------------
# Experiment registration
# ---------------------------------------------------------------------------

def register(exp_id, title):
    """Decorator to register experiment functions."""
    def decorator(fn):
        EXPERIMENTS[exp_id] = (title, fn)
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_patients(max_patients=11):
    """Load patient data with CGM + insulin channels."""
    raw = _load_patients(PATIENTS_DIR, max_patients=max_patients)
    result = {}
    for p in raw:
        pid = p['name']
        df = p['df']
        glucose = df['glucose'].values
        valid = ~np.isnan(glucose)
        if valid.sum() < 1000:
            continue
        result[pid] = {
            'df': df,
            'glucose': glucose,
            'valid': valid,
            'timestamps': df.index,
            'bolus': (df['bolus'].values if 'bolus' in df.columns
                      else np.zeros(len(df))),
            'carbs': (df['carbs'].values if 'carbs' in df.columns
                      else np.zeros(len(df))),
            'temp_rate': (df['temp_rate'].values if 'temp_rate' in df.columns
                          else np.zeros(len(df))),
            'iob': (df['iob'].values if 'iob' in df.columns
                    else np.zeros(len(df))),
            'cob': (df['cob'].values if 'cob' in df.columns
                    else np.zeros(len(df))),
        }
        if 'pk' in p and p['pk'] is not None:
            result[pid]['pk'] = p['pk']
    return result


# ---------------------------------------------------------------------------
# Helper functions -- glucose metrics
# ---------------------------------------------------------------------------

def compute_tir(glucose, lo=TIR_LO, hi=TIR_HI):
    """Compute time-in-range percentage."""
    if isinstance(glucose, np.ndarray):
        valid = glucose[~np.isnan(glucose)]
    else:
        valid = glucose.dropna()
    if len(valid) == 0:
        return 0.0
    return float(np.mean((valid >= lo) & (valid <= hi)) * 100)


def compute_cv(glucose):
    """Compute coefficient of variation (%)."""
    if isinstance(glucose, np.ndarray):
        valid = glucose[~np.isnan(glucose)]
    else:
        valid = glucose.dropna().values
    if len(valid) < 10 or np.mean(valid) < 1:
        return 100.0
    return float(np.std(valid) / np.mean(valid) * 100)


def compute_grade(score):
    """Map numeric score -> letter grade."""
    if score < GRADE_D_CEIL:
        return 'D'
    if score < GRADE_C_CEIL:
        return 'C'
    if score < GRADE_B_CEIL:
        return 'B'
    return 'A'


def compute_tbr(glucose, threshold=70):
    """Compute time below range (%)."""
    if isinstance(glucose, np.ndarray):
        valid = glucose[~np.isnan(glucose)]
    else:
        valid = glucose.dropna().values
    if len(valid) == 0:
        return 0.0
    return float(np.mean(valid < threshold) * 100)


def compute_tar(glucose, threshold=180):
    """Compute time above range (%)."""
    if isinstance(glucose, np.ndarray):
        valid = glucose[~np.isnan(glucose)]
    else:
        valid = glucose.dropna().values
    if len(valid) == 0:
        return 0.0
    return float(np.mean(valid > threshold) * 100)


def compute_safety_score(tbr_l1, tbr_l2, overcorrection_rate):
    """Safety score (0-100): penalises TBR and overcorrection."""
    penalty = tbr_l1 * 10.0 + tbr_l2 * 50.0 + overcorrection_rate
    return max(0.0, min(100.0, 100.0 - penalty))


def compute_v10_score(tir, cv, overnight_tir, safety_score):
    """v10 composite score with TBR-integrated safety (0-100)."""
    score = (tir * 0.5
             + max(0, 100 - cv * 2) * 0.2
             + overnight_tir * 0.1
             + safety_score * 0.2)
    return min(100.0, max(0.0, float(score)))


def compute_v10_grade(score):
    """Map v10 score to letter grade."""
    return compute_grade(score)


def compute_overnight_tir(glucose, n):
    """TIR restricted to 00:00-06:00 windows."""
    tirs = []
    n_days = n // STEPS_PER_DAY
    for d in range(min(n_days, 180)):
        s = d * STEPS_PER_DAY
        e = s + 6 * STEPS_PER_HOUR
        if e > n:
            break
        seg = glucose[s:e]
        valid = seg[~np.isnan(seg)]
        if len(valid) >= STEPS_PER_HOUR:
            tirs.append(compute_tir(seg))
    return float(np.mean(tirs)) if tirs else 0.0


def compute_overcorrection_rate(glucose, bolus, carbs, n):
    """Fraction of correction boluses followed by hypo (<70)."""
    events = 0
    hypos = 0
    response_window = 4 * STEPS_PER_HOUR
    carb_window = STEPS_PER_HOUR
    for i in range(n):
        if bolus[i] < MIN_BOLUS_ISF or np.isnan(glucose[i]):
            continue
        c_start = max(0, i - carb_window)
        c_end = min(n, i + carb_window)
        if np.nansum(carbs[c_start:c_end]) > 2:
            continue
        events += 1
        end = min(i + response_window, n)
        post = glucose[i:end]
        valid_post = post[~np.isnan(post)]
        if len(valid_post) > 0 and np.nanmin(valid_post) < TIR_LO:
            hypos += 1
    if events == 0:
        return 0.0
    return float(hypos / events * 100)


def detect_hypo_episodes(glucose, threshold=HYPO_THRESHOLD,
                         min_consecutive=HYPO_MIN_DURATION_STEPS):
    """Detect hypo episodes. Returns list of dicts with start/end/nadir."""
    n = len(glucose)
    episodes = []
    i = 0
    while i < n:
        if np.isnan(glucose[i]) or glucose[i] >= threshold:
            i += 1
            continue
        start = i
        nadir = glucose[i]
        nadir_idx = i
        count = 1
        j = i + 1
        while j < n:
            if np.isnan(glucose[j]):
                j += 1
                continue
            if glucose[j] < threshold:
                count += 1
                if glucose[j] < nadir:
                    nadir = glucose[j]
                    nadir_idx = j
                j += 1
            else:
                break
        end = j
        if count >= min_consecutive:
            episodes.append({
                'start': start,
                'end': end,
                'duration_steps': end - start,
                'nadir': float(nadir),
                'nadir_idx': nadir_idx,
            })
        i = j
    return episodes


# ---------------------------------------------------------------------------
# Helper functions -- drift & excursion (v9)
# ---------------------------------------------------------------------------

def compute_segment_drift(glucose, bolus, carbs, day_start, h_start, h_end):
    """Compute glucose drift (mg/dL/h) for a time segment."""
    seg_start = day_start + h_start * STEPS_PER_HOUR
    seg_end = day_start + h_end * STEPS_PER_HOUR
    n = len(glucose)
    if seg_end > n or seg_start < 0:
        return np.nan
    seg_g = glucose[seg_start:seg_end].copy()
    seg_valid = ~np.isnan(seg_g)
    if seg_valid.sum() < STEPS_PER_HOUR:
        return np.nan
    lookback_bolus = 4 * STEPS_PER_HOUR
    lookback_carbs = 3 * STEPS_PER_HOUR
    check_start_b = max(0, seg_start - lookback_bolus)
    check_start_c = max(0, seg_start - lookback_carbs)
    if np.nansum(bolus[check_start_b:seg_end]) > 0.3:
        return np.nan
    if np.nansum(carbs[check_start_c:seg_end]) > 2.0:
        return np.nan
    valid_idx = np.where(seg_valid)[0]
    valid_bg = seg_g[valid_idx]
    hours = valid_idx / STEPS_PER_HOUR
    if len(valid_idx) < 3:
        return np.nan
    coeffs = np.polyfit(hours, valid_bg, 1)
    return float(coeffs[0])


def compute_overnight_drift(glucose, bolus, carbs, n_days, n):
    """Compute median absolute overnight drift across all days."""
    drifts = []
    for d in range(min(n_days, 180)):
        dr = compute_segment_drift(glucose, bolus, carbs,
                                   d * STEPS_PER_DAY, 0, 6)
        if not np.isnan(dr):
            drifts.append(abs(dr))
    return float(np.median(drifts)) if drifts else 0.0


def compute_max_excursion(glucose, carbs, n):
    """90th percentile post-meal excursion (mg/dL)."""
    excursions = []
    window = 4 * STEPS_PER_HOUR
    for i in range(n):
        if carbs[i] < 5 or np.isnan(glucose[i]):
            continue
        end = min(i + window, n)
        post = glucose[i:end]
        valid_post = post[~np.isnan(post)]
        if len(valid_post) < STEPS_PER_HOUR:
            continue
        excursion = float(np.nanmax(valid_post) - glucose[i])
        excursions.append(excursion)
    if not excursions:
        return 0.0
    return float(np.percentile(excursions, 90))


def compute_isf_ratio(glucose, bolus, carbs, n):
    """Deconfounded ISF from correction boluses >= 2 U with no nearby carbs."""
    events = []
    carb_window = STEPS_PER_HOUR
    response_window = 3 * STEPS_PER_HOUR
    for i in range(n):
        if bolus[i] < MIN_BOLUS_ISF or np.isnan(glucose[i]):
            continue
        c_start = max(0, i - carb_window)
        c_end = min(n, i + carb_window)
        if np.nansum(carbs[c_start:c_end]) > 2:
            continue
        end = min(i + response_window, n)
        post = glucose[i:end]
        valid_post = post[~np.isnan(post)]
        if len(valid_post) < response_window // 2:
            continue
        drop = glucose[i] - np.nanmin(valid_post)
        observed_isf = drop / bolus[i] if bolus[i] > 0 else 0
        events.append(observed_isf)
    if len(events) < MIN_ISF_EVENTS:
        return 1.0
    return float(np.median(events))


def compute_therapy_score(tir, drift, max_excursion, isf_ratio, cv):
    """Compute therapy score 0-100 (v9)."""
    tir_score = min(tir, 100) / 100 * SCORE_WEIGHTS['tir']
    basal_ok = 1.0 if abs(drift) < DRIFT_THRESHOLD else 0.0
    cr_ok = 1.0 if max_excursion < EXCURSION_THRESHOLD else 0.0
    isf_ok = 1.0
    cv_ok = 1.0 if cv < CV_THRESHOLD else 0.0
    return (tir_score + basal_ok * SCORE_WEIGHTS['basal']
            + cr_ok * SCORE_WEIGHTS['cr']
            + isf_ok * SCORE_WEIGHTS['isf']
            + cv_ok * SCORE_WEIGHTS['cv'])


def compute_full_assessment(glucose, bolus, carbs, n):
    """Full therapy assessment for a data slice (v9)."""
    tir = compute_tir(glucose)
    n_days = max(n // STEPS_PER_DAY, 1)
    drift = compute_overnight_drift(glucose, bolus, carbs, n_days, n)
    exc = compute_max_excursion(glucose, carbs, n)
    isf = compute_isf_ratio(glucose, bolus, carbs, n)
    cv = compute_cv(glucose)
    score = compute_therapy_score(tir, drift, exc, isf, cv)
    grade = compute_grade(score)
    return {
        'tir': round(tir, 1),
        'drift': round(drift, 2),
        'excursion': round(exc, 1),
        'isf_ratio': round(isf, 2),
        'cv': round(cv, 1),
        'score': round(score, 1),
        'grade': grade,
        'flags': {
            'basal_flag': abs(drift) >= DRIFT_THRESHOLD,
            'cr_flag': exc >= EXCURSION_THRESHOLD,
            'cv_flag': cv >= CV_THRESHOLD,
        },
    }


def generate_recommendations(assessment):
    """Generate therapy parameter recommendations from assessment."""
    recs = []
    flags = assessment.get('flags', {})
    grade = assessment.get('grade', 'B')
    if flags.get('basal_flag', False):
        drift = assessment.get('drift', 0.0)
        direction = 'increase' if drift > 0 else 'decrease'
        recs.append({'parameter': 'basal', 'direction': direction,
                     'magnitude_pct': CONSERVATIVE_BASAL_PCT,
                     'rationale': f'overnight drift {drift:+.1f} mg/dL/h'})
    if flags.get('cr_flag', False):
        adj = CR_ADJUST_GRADE_D if grade == 'D' else CR_ADJUST_STANDARD
        recs.append({'parameter': 'cr', 'direction': 'decrease',
                     'magnitude_pct': adj,
                     'rationale': f'postmeal excursion {assessment.get("excursion", 0):.0f} mg/dL'})
    if flags.get('cv_flag', False):
        recs.append({'parameter': 'isf', 'direction': 'increase',
                     'magnitude_pct': ISF_ADJUST_PCT,
                     'rationale': f'CV {assessment.get("cv", 0):.1f}% > {CV_THRESHOLD}%'})
    return recs


# ---------------------------------------------------------------------------
# Helper -- compute full v10 assessment for a glucose slice
# ---------------------------------------------------------------------------

def compute_v10_assessment(glucose, bolus, carbs, n):
    """Compute complete v10 assessment for a glucose/insulin slice."""
    tir = compute_tir(glucose)
    cv = compute_cv(glucose)
    overnight_tir_val = compute_overnight_tir(glucose, n)

    tbr_l1 = compute_tbr(glucose, threshold=TIR_LO) - compute_tbr(glucose, threshold=TBR_L1_LO)
    tbr_l2 = compute_tbr(glucose, threshold=TBR_L1_LO)
    overcorr = compute_overcorrection_rate(glucose, bolus, carbs, n)
    safety = compute_safety_score(max(0, tbr_l1), max(0, tbr_l2), overcorr)

    v10_score_val = compute_v10_score(tir, cv, overnight_tir_val, safety)
    v10_grade_val = compute_v10_grade(v10_score_val)

    total_tbr = compute_tbr(glucose, threshold=TIR_LO)
    drift_val = compute_overnight_drift(
        glucose, bolus, carbs, max(n // STEPS_PER_DAY, 1), n)
    exc_val = compute_max_excursion(glucose, carbs, n)

    return {
        'tir': round(tir, 1), 'cv': round(cv, 1),
        'overnight_tir': round(overnight_tir_val, 1),
        'tbr_l1': round(max(0, tbr_l1), 2), 'tbr_l2': round(max(0, tbr_l2), 2),
        'total_tbr': round(total_tbr, 2),
        'overcorrection_rate': round(overcorr, 1),
        'safety_score': round(safety, 1),
        'v10_score': round(v10_score_val, 1),
        'v10_grade': v10_grade_val,
        'drift': round(drift_val, 2),
        'excursion': round(exc_val, 1),
        'flags': {
            'basal_flag': abs(drift_val) >= DRIFT_THRESHOLD,
            'cr_flag': exc_val >= EXCURSION_THRESHOLD,
            'cv_flag': cv >= CV_THRESHOLD,
            'tbr_flag': total_tbr >= ADA_TBR_L1_TARGET,
        },
    }


# ===================================================================
# EXP-1501: Per-Patient Safety Protocol Impact
# ===================================================================

@register(1501, "Per-Patient Safety Protocol Impact")
def exp_1501(patients, args):
    """Simulate applying v10 safety recommendations and estimate TBR reduction."""
    results = {'per_patient': [], 'n_patients': 0}

    for pid in sorted(patients):
        p = patients[pid]
        glucose, bolus, carbs = p['glucose'], p['bolus'], p['carbs']
        iob = p['iob']
        n = len(glucose)

        total_tbr = compute_tbr(glucose, TIR_LO)
        tbr_l2 = compute_tbr(glucose, TBR_L1_LO)

        # Classify hypo episodes by cause
        episodes = detect_hypo_episodes(glucose)
        n_episodes = len(episodes)
        aid_induced = 0
        for ep in episodes:
            # AID-induced if temp_rate elevated in 2h before episode
            lookback = 2 * STEPS_PER_HOUR
            pre_start = max(0, ep['start'] - lookback)
            pre_temp = p['temp_rate'][pre_start:ep['start']]
            if len(pre_temp) > 0 and np.nanmean(pre_temp) > 0.5:
                aid_induced += 1

        aid_pct = (aid_induced / n_episodes * 100) if n_episodes > 0 else 0.0

        # Simulate safety protocol impact
        # Heuristic: "reduce aggressiveness" reduces AID-induced TBR by 40%
        # Manual hypos reduced 10% (better target ranges help somewhat)
        estimated_aid_tbr = total_tbr * (aid_pct / 100)
        estimated_manual_tbr = total_tbr - estimated_aid_tbr

        projected_tbr = estimated_manual_tbr * 0.90 + estimated_aid_tbr * 0.60
        tbr_reduction = total_tbr - projected_tbr
        projected_safe = projected_tbr < ADA_TBR_L1_TARGET

        # Estimate grade impact
        tir = compute_tir(glucose)
        cv = compute_cv(glucose)
        overnight = compute_overnight_tir(glucose, n)
        overcorr = compute_overcorrection_rate(glucose, bolus, carbs, n)

        current_safety = compute_safety_score(
            max(0, total_tbr - tbr_l2), tbr_l2, overcorr)
        projected_safety = compute_safety_score(
            max(0, projected_tbr - tbr_l2 * 0.7), tbr_l2 * 0.7,
            overcorr * 0.8)

        current_v10 = compute_v10_score(tir, cv, overnight, current_safety)
        projected_v10 = compute_v10_score(tir, cv, overnight, projected_safety)

        rec = {
            'pid': pid,
            'current_tbr': _safe_round(total_tbr, 2),
            'aid_pct': _safe_round(aid_pct, 1),
            'projected_tbr': _safe_round(projected_tbr, 2),
            'tbr_reduction': _safe_round(tbr_reduction, 2),
            'projected_safe': projected_safe,
            'current_grade': compute_v10_grade(current_v10),
            'projected_grade': compute_v10_grade(projected_v10),
            'grade_change': compute_v10_grade(projected_v10) != compute_v10_grade(current_v10),
        }
        results['per_patient'].append(rec)

        if args.detail:
            change = "↑" if rec['grade_change'] else "—"
            print(f"  {pid}: TBR={total_tbr:.2f}%→{projected_tbr:.2f}% "
                  f"(Δ={tbr_reduction:+.2f}%) AID={aid_pct:.0f}% "
                  f"grade={rec['current_grade']}→{rec['projected_grade']} {change}")

    results['n_patients'] = len(results['per_patient'])
    projected_safe_count = sum(1 for r in results['per_patient'] if r['projected_safe'])
    results['summary'] = {
        'mean_tbr_reduction': _safe_round(
            np.mean([r['tbr_reduction'] for r in results['per_patient']]), 2),
        'projected_safe_count': projected_safe_count,
        'grade_upgrades': sum(1 for r in results['per_patient'] if r['grade_change']),
    }
    return results


# ===================================================================
# EXP-1502: TBR Trajectory Analysis
# ===================================================================

@register(1502, "TBR Trajectory Analysis")
def exp_1502(patients, args):
    """Track TBR% over monthly windows and detect trends."""
    results = {'per_patient': [], 'n_patients': 0}
    MONTH_STEPS = 30 * STEPS_PER_DAY

    for pid in sorted(patients):
        p = patients[pid]
        glucose = p['glucose']
        n = len(glucose)

        # Split into monthly windows
        monthly_tbr = []
        month_idx = 0
        while month_idx * MONTH_STEPS < n:
            s = month_idx * MONTH_STEPS
            e = min(s + MONTH_STEPS, n)
            seg = glucose[s:e]
            valid = seg[~np.isnan(seg)]
            if len(valid) >= STEPS_PER_DAY * 7:
                monthly_tbr.append(compute_tbr(seg, TIR_LO))
            month_idx += 1

        if len(monthly_tbr) < 2:
            trend = 'insufficient_data'
            slope = 0.0
            p_val = 1.0
        else:
            x = np.arange(len(monthly_tbr))
            slope_val, intercept, r_val, p_val, std_err = stats.linregress(x, monthly_tbr)
            slope = float(slope_val)
            if p_val < 0.05:
                trend = 'worsening' if slope > 0 else 'improving'
            else:
                trend = 'stable'

        rec = {
            'pid': pid,
            'monthly_tbr': [_safe_round(t, 2) for t in monthly_tbr],
            'n_months': len(monthly_tbr),
            'trend': trend,
            'slope_pct_per_month': _safe_round(slope, 3),
            'p_value': _safe_round(float(p_val), 4),
        }
        results['per_patient'].append(rec)

        if args.detail:
            tbr_str = ",".join(f"{t:.1f}" for t in monthly_tbr)
            print(f"  {pid}: months={len(monthly_tbr)} TBR=[{tbr_str}] "
                  f"trend={trend} slope={slope:+.3f}%/mo p={p_val:.3f}")

    results['n_patients'] = len(results['per_patient'])
    trends = [r['trend'] for r in results['per_patient']]
    results['summary'] = {
        'improving': trends.count('improving'),
        'stable': trends.count('stable'),
        'worsening': trends.count('worsening'),
        'insufficient': trends.count('insufficient_data'),
    }
    return results


# ===================================================================
# EXP-1503: Insulin-Hypo Causal Analysis
# ===================================================================

@register(1503, "Insulin-Hypo Causal Analysis")
def exp_1503(patients, args):
    """Trace hypo episodes back to preceding insulin delivery."""
    results = {'per_patient': [], 'n_patients': 0}
    LOOKBACK_STEPS = int(DIA_DEFAULT * STEPS_PER_HOUR)

    for pid in sorted(patients):
        p = patients[pid]
        glucose, iob = p['glucose'], p['iob']
        n = len(glucose)

        # Compute IOB percentiles
        valid_iob = iob[~np.isnan(iob)]
        if len(valid_iob) < 100:
            results['per_patient'].append({
                'pid': pid, 'n_episodes': 0,
                'high_iob_fraction': 0.0, 'iob_threshold': 0.0,
            })
            continue

        iob_p75 = float(np.percentile(valid_iob[valid_iob > 0], 75)) if np.sum(valid_iob > 0) > 10 else 1.0
        iob_p50 = float(np.percentile(valid_iob[valid_iob > 0], 50)) if np.sum(valid_iob > 0) > 10 else 0.5

        episodes = detect_hypo_episodes(glucose)
        n_episodes = len(episodes)
        high_iob_count = 0
        pre_hypo_iobs = []

        for ep in episodes:
            # Look at IOB in the 2-4h window before episode start
            pre_start = max(0, ep['start'] - LOOKBACK_STEPS)
            pre_end = ep['start']
            pre_iob = iob[pre_start:pre_end]
            valid_pre = pre_iob[~np.isnan(pre_iob)]
            if len(valid_pre) > 0:
                max_pre_iob = float(np.max(valid_pre))
                pre_hypo_iobs.append(max_pre_iob)
                if max_pre_iob > iob_p75:
                    high_iob_count += 1

        high_iob_frac = (high_iob_count / n_episodes) if n_episodes > 0 else 0.0

        # Find optimal IOB threshold for hypo prediction via Youden's J
        best_threshold = iob_p75
        if pre_hypo_iobs and len(valid_iob) > 100:
            thresholds = np.linspace(0.1, float(np.percentile(valid_iob, 95)), 20)
            best_j = -1
            for thr in thresholds:
                tp = sum(1 for v in pre_hypo_iobs if v > thr)
                fn = len(pre_hypo_iobs) - tp
                # Approximate FP rate from general population IOB
                fp_rate = float(np.mean(valid_iob > thr))
                sens = tp / max(len(pre_hypo_iobs), 1)
                spec = 1 - fp_rate
                j = sens + spec - 1
                if j > best_j:
                    best_j = j
                    best_threshold = float(thr)

        rec = {
            'pid': pid,
            'n_episodes': n_episodes,
            'high_iob_fraction': _safe_round(high_iob_frac, 3),
            'iob_p75': _safe_round(iob_p75, 2),
            'optimal_threshold': _safe_round(best_threshold, 2),
            'mean_pre_hypo_iob': _safe_round(
                float(np.mean(pre_hypo_iobs)) if pre_hypo_iobs else 0.0, 2),
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: episodes={n_episodes} high_IOB={high_iob_frac:.1%} "
                  f"IOB_p75={iob_p75:.2f}U threshold={best_threshold:.2f}U "
                  f"mean_pre={rec['mean_pre_hypo_iob']:.2f}U")

    results['n_patients'] = len(results['per_patient'])
    fracs = [r['high_iob_fraction'] for r in results['per_patient'] if r['n_episodes'] > 0]
    results['summary'] = {
        'mean_high_iob_fraction': _safe_round(float(np.mean(fracs)) if fracs else 0.0, 3),
        'patients_with_high_iob_hypos': sum(1 for f in fracs if f > 0.5),
    }
    return results


# ===================================================================
# EXP-1504: Post-Meal vs Fasting Hypo Classification
# ===================================================================

@register(1504, "Post-Meal vs Fasting Hypo Classification")
def exp_1504(patients, args):
    """Classify hypos as post-meal or fasting — different root causes."""
    results = {'per_patient': [], 'n_patients': 0}
    MEAL_WINDOW = 4 * STEPS_PER_HOUR  # 4h post-meal

    for pid in sorted(patients):
        p = patients[pid]
        glucose, carbs = p['glucose'], p['carbs']
        n = len(glucose)

        episodes = detect_hypo_episodes(glucose)
        n_episodes = len(episodes)

        # Find meal timestamps (carbs > 5g)
        meal_times = np.where(carbs > 5)[0]

        post_meal = 0
        fasting = 0
        for ep in episodes:
            # Check if any meal within MEAL_WINDOW before episode start
            is_post_meal = False
            for mt in meal_times:
                if 0 < (ep['start'] - mt) <= MEAL_WINDOW:
                    is_post_meal = True
                    break
            if is_post_meal:
                post_meal += 1
            else:
                fasting += 1

        post_meal_pct = (post_meal / n_episodes * 100) if n_episodes > 0 else 0.0
        fasting_pct = (fasting / n_episodes * 100) if n_episodes > 0 else 0.0

        # Root cause inference
        if n_episodes == 0:
            primary_cause = 'none'
        elif post_meal_pct > 60:
            primary_cause = 'cr_too_aggressive'
        elif fasting_pct > 60:
            primary_cause = 'basal_too_high'
        else:
            primary_cause = 'mixed'

        rec = {
            'pid': pid,
            'n_episodes': n_episodes,
            'post_meal': post_meal,
            'fasting': fasting,
            'post_meal_pct': _safe_round(post_meal_pct, 1),
            'fasting_pct': _safe_round(fasting_pct, 1),
            'primary_cause': primary_cause,
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: episodes={n_episodes} post_meal={post_meal}({post_meal_pct:.0f}%) "
                  f"fasting={fasting}({fasting_pct:.0f}%) cause={primary_cause}")

    results['n_patients'] = len(results['per_patient'])
    causes = [r['primary_cause'] for r in results['per_patient']]
    results['summary'] = {
        'cr_too_aggressive': causes.count('cr_too_aggressive'),
        'basal_too_high': causes.count('basal_too_high'),
        'mixed': causes.count('mixed'),
        'none': causes.count('none'),
    }
    return results


# ===================================================================
# EXP-1505: TBR-Specific Recommendation Refinement
# ===================================================================

@register(1505, "TBR-Specific Recommendation Refinement")
def exp_1505(patients, args):
    """Generate specific numeric recommendations scaled by TBR severity."""
    results = {'per_patient': [], 'n_patients': 0}

    for pid in sorted(patients):
        p = patients[pid]
        glucose, bolus, carbs = p['glucose'], p['bolus'], p['carbs']
        n = len(glucose)

        total_tbr = compute_tbr(glucose, TIR_LO)
        tbr_excess = max(0, total_tbr - ADA_TBR_L1_TARGET)

        # Scale recommendations by TBR excess
        # 1% excess → 5% basal reduction; 2% → 10%; capped at 20%
        basal_reduction_pct = min(20.0, tbr_excess * 5.0)

        # ISF increase: 1% excess → +5 mg/dL/U; capped at +30
        isf_increase = min(30.0, tbr_excess * 5.0)

        # CR increase: 1% excess → +2 g/U; capped at +10
        cr_increase = min(10.0, tbr_excess * 2.0)

        # Determine which recommendations apply based on hypo classification
        episodes = detect_hypo_episodes(glucose)
        meal_times = np.where(carbs > 5)[0]
        post_meal_count = 0
        for ep in episodes:
            for mt in meal_times:
                if 0 < (ep['start'] - mt) <= 4 * STEPS_PER_HOUR:
                    post_meal_count += 1
                    break

        fasting_count = len(episodes) - post_meal_count
        fasting_ratio = fasting_count / max(len(episodes), 1)

        recs = []
        if tbr_excess > 0:
            if fasting_ratio > 0.4:
                recs.append(f"reduce_basal_{basal_reduction_pct:.0f}pct")
            if fasting_ratio < 0.6 and len(episodes) > 0:
                recs.append(f"increase_cr_{cr_increase:.0f}g_per_U")
            recs.append(f"increase_isf_{isf_increase:.0f}mg_dL_per_U")

        rec = {
            'pid': pid,
            'total_tbr': _safe_round(total_tbr, 2),
            'tbr_excess': _safe_round(tbr_excess, 2),
            'basal_reduction_pct': _safe_round(basal_reduction_pct, 1),
            'isf_increase_mg': _safe_round(isf_increase, 1),
            'cr_increase_g': _safe_round(cr_increase, 1),
            'recommendations': recs,
            'n_recs': len(recs),
        }
        results['per_patient'].append(rec)

        if args.detail:
            rec_str = ", ".join(recs) if recs else "none_needed"
            print(f"  {pid}: TBR={total_tbr:.2f}% excess={tbr_excess:.2f}% "
                  f"recs=[{rec_str}]")

    results['n_patients'] = len(results['per_patient'])
    results['summary'] = {
        'patients_needing_action': sum(1 for r in results['per_patient'] if r['n_recs'] > 0),
        'mean_basal_reduction': _safe_round(
            np.mean([r['basal_reduction_pct'] for r in results['per_patient']
                     if r['tbr_excess'] > 0]) if any(r['tbr_excess'] > 0 for r in results['per_patient']) else 0.0, 1),
    }
    return results


# ===================================================================
# EXP-1506: Hypo Cluster Analysis
# ===================================================================

@register(1506, "Hypo Cluster Analysis")
def exp_1506(patients, args):
    """Detect temporal clusters of hypos within 24h — systematic miscalibration."""
    results = {'per_patient': [], 'n_patients': 0}
    CLUSTER_WINDOW = STEPS_PER_DAY  # 24h

    for pid in sorted(patients):
        p = patients[pid]
        glucose = p['glucose']

        episodes = detect_hypo_episodes(glucose)
        n_episodes = len(episodes)

        if n_episodes < 2:
            results['per_patient'].append({
                'pid': pid, 'n_episodes': n_episodes,
                'n_clusters': 0, 'cluster_sizes': [],
                'isolated_pct': 100.0, 'systematic_flag': False,
            })
            if args.detail:
                print(f"  {pid}: episodes={n_episodes} clusters=0 isolated=100%")
            continue

        # Group episodes into clusters (within 24h of each other)
        starts = sorted([ep['start'] for ep in episodes])
        clusters = []
        current_cluster = [starts[0]]
        for s in starts[1:]:
            if s - current_cluster[-1] <= CLUSTER_WINDOW:
                current_cluster.append(s)
            else:
                clusters.append(current_cluster)
                current_cluster = [s]
        clusters.append(current_cluster)

        cluster_sizes = [len(c) for c in clusters]
        multi_clusters = [c for c in clusters if len(c) >= 2]
        isolated = sum(1 for c in clusters if len(c) == 1)
        isolated_pct = (isolated / len(clusters) * 100) if clusters else 100.0

        # Systematic flag: >30% of episodes are in multi-episode clusters
        clustered_episodes = sum(len(c) for c in multi_clusters)
        systematic_flag = (clustered_episodes / n_episodes > 0.3) if n_episodes > 0 else False

        rec = {
            'pid': pid,
            'n_episodes': n_episodes,
            'n_clusters': len(clusters),
            'n_multi_clusters': len(multi_clusters),
            'cluster_sizes': cluster_sizes[:20],  # cap output
            'mean_cluster_size': _safe_round(float(np.mean(cluster_sizes)), 1),
            'max_cluster_size': max(cluster_sizes) if cluster_sizes else 0,
            'isolated_pct': _safe_round(isolated_pct, 1),
            'systematic_flag': systematic_flag,
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: episodes={n_episodes} clusters={len(clusters)} "
                  f"multi={len(multi_clusters)} max_size={rec['max_cluster_size']} "
                  f"isolated={isolated_pct:.0f}% systematic={systematic_flag}")

    results['n_patients'] = len(results['per_patient'])
    results['summary'] = {
        'patients_systematic': sum(1 for r in results['per_patient'] if r.get('systematic_flag', False)),
        'mean_cluster_size': _safe_round(
            np.mean([r['mean_cluster_size'] for r in results['per_patient']
                     if r.get('mean_cluster_size', 0) > 0]), 1),
    }
    return results


# ===================================================================
# EXP-1507: Recovery Time vs Setting Mismatch
# ===================================================================

@register(1507, "Recovery Time vs Setting Mismatch")
def exp_1507(patients, args):
    """Correlate hypo recovery time with estimated setting mismatch severity."""
    results = {'per_patient': [], 'n_patients': 0}

    recovery_times_all = []
    mismatch_scores_all = []

    for pid in sorted(patients):
        p = patients[pid]
        glucose, bolus, carbs = p['glucose'], p['bolus'], p['carbs']
        n = len(glucose)

        episodes = detect_hypo_episodes(glucose)

        # Compute recovery time for each episode
        recovery_times = []
        for ep in episodes:
            # Find first reading ≥ 70 after episode end
            recovery_idx = ep['end']
            while recovery_idx < n:
                if not np.isnan(glucose[recovery_idx]) and glucose[recovery_idx] >= TIR_LO:
                    break
                recovery_idx += 1
            recovery_steps = recovery_idx - ep['start']
            recovery_min = recovery_steps * 5  # 5-min timesteps
            recovery_times.append(recovery_min)

        median_recovery = float(np.median(recovery_times)) if recovery_times else 0.0

        # Compute mismatch severity score (0-100)
        assessment = compute_full_assessment(glucose, bolus, carbs, n)
        n_flags = sum(1 for v in assessment['flags'].values() if v)
        tbr = compute_tbr(glucose, TIR_LO)
        mismatch_score = min(100, n_flags * 20 + tbr * 5)

        recovery_times_all.append(median_recovery)
        mismatch_scores_all.append(mismatch_score)

        rec = {
            'pid': pid,
            'n_episodes': len(episodes),
            'median_recovery_min': _safe_round(median_recovery, 1),
            'mismatch_score': _safe_round(mismatch_score, 1),
            'n_flags': n_flags,
            'tbr': _safe_round(tbr, 2),
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: episodes={len(episodes)} recovery={median_recovery:.0f}min "
                  f"mismatch={mismatch_score:.0f} flags={n_flags}")

    # Compute correlation
    if len(recovery_times_all) >= 3:
        r_val, p_val = stats.pearsonr(recovery_times_all, mismatch_scores_all)
    else:
        r_val, p_val = 0.0, 1.0

    results['n_patients'] = len(results['per_patient'])
    results['correlation'] = {
        'pearson_r': _safe_round(float(r_val), 3),
        'p_value': _safe_round(float(p_val), 4),
        'significant': float(p_val) < 0.05,
        'interpretation': ('confirmed' if float(r_val) > 0.3 and float(p_val) < 0.05
                           else 'not_significant'),
    }
    return results


# ===================================================================
# EXP-1508: Cross-Patient Safety Benchmarking
# ===================================================================

@register(1508, "Cross-Patient Safety Benchmarking")
def exp_1508(patients, args):
    """Rank patients by composite safety score and generate action plans."""
    results = {'per_patient': [], 'n_patients': 0}

    # Compute v10 assessment for all patients
    assessments = []
    for pid in sorted(patients):
        p = patients[pid]
        glucose, bolus, carbs = p['glucose'], p['bolus'], p['carbs']
        n = len(glucose)

        v10 = compute_v10_assessment(glucose, bolus, carbs, n)

        # v9 assessment for comparison
        v9 = compute_full_assessment(glucose, bolus, carbs, n)

        assessments.append({
            'pid': pid,
            'v10_score': v10['v10_score'],
            'v10_grade': v10['v10_grade'],
            'v9_score': v9['score'],
            'v9_grade': v9['grade'],
            'safety_score': v10['safety_score'],
            'total_tbr': v10['total_tbr'],
            'tir': v10['tir'],
            'flags': v10['flags'],
        })

    # Rank by v10 safety score (ascending = worst first)
    ranked = sorted(assessments, key=lambda x: x['safety_score'])

    # Generate action plans for bottom 3
    for i, a in enumerate(ranked):
        rank = i + 1
        action_plan = []
        if a['total_tbr'] >= ADA_TBR_L1_TARGET:
            action_plan.append('URGENT: Reduce AID aggressiveness (raise ISF, lower max IOB)')
        if a['flags'].get('basal_flag'):
            action_plan.append('Adjust overnight basal rate -10%')
        if a['flags'].get('cr_flag'):
            action_plan.append('Increase carb ratio (less insulin per carb)')
        if a['flags'].get('cv_flag'):
            action_plan.append('Review high variability — consider tighter targets')
        if not action_plan:
            action_plan.append('Monitor — no immediate changes needed')

        rec = {
            'pid': a['pid'],
            'safety_rank': rank,
            'safety_score': _safe_round(a['safety_score'], 1),
            'v10_grade': a['v10_grade'],
            'v9_grade': a['v9_grade'],
            'v9_v10_change': a['v10_grade'] != a['v9_grade'],
            'total_tbr': _safe_round(a['total_tbr'], 2),
            'action_plan': action_plan[:3],
            'in_bottom_3': rank <= 3,
        }
        results['per_patient'].append(rec)

        if args.detail:
            change = f" (was {a['v9_grade']})" if rec['v9_v10_change'] else ""
            plan = "; ".join(action_plan[:2])
            print(f"  #{rank} {a['pid']}: safety={a['safety_score']:.0f} "
                  f"grade={a['v10_grade']}{change} TBR={a['total_tbr']:.1f}% "
                  f"plan=[{plan}]")

    results['n_patients'] = len(results['per_patient'])
    results['summary'] = {
        'bottom_3': [r['pid'] for r in results['per_patient'] if r['in_bottom_3']],
        'grade_changes': sum(1 for r in results['per_patient'] if r['v9_v10_change']),
        'mean_safety_score': _safe_round(
            np.mean([r['safety_score'] for r in results['per_patient']]), 1),
    }
    return results


# ===================================================================
# EXP-1509: TBR Impact on Long-Term Outcomes
# ===================================================================

@register(1509, "TBR Impact on Long-Term Outcomes")
def exp_1509(patients, args):
    """Show TBR-high patients may have deceptively good A1C from lows pulling down mean."""
    results = {'per_patient': [], 'n_patients': 0}

    for pid in sorted(patients):
        p = patients[pid]
        glucose = p['glucose']
        valid_glucose = glucose[~np.isnan(glucose)]

        if len(valid_glucose) < 1000:
            continue

        mean_glucose = float(np.mean(valid_glucose))
        # eA1C formula: (mean_glucose + 46.7) / 28.7
        ea1c = (mean_glucose + 46.7) / 28.7

        # Compute A1C without lows (glucose >= 70 only)
        glucose_no_lows = valid_glucose[valid_glucose >= TIR_LO]
        mean_no_lows = float(np.mean(glucose_no_lows)) if len(glucose_no_lows) > 0 else mean_glucose
        ea1c_no_lows = (mean_no_lows + 46.7) / 28.7

        tir = compute_tir(glucose)
        tbr = compute_tbr(glucose, TIR_LO)

        # A1C distortion: how much lows pull down the estimate
        a1c_distortion = ea1c_no_lows - ea1c

        rec = {
            'pid': pid,
            'mean_glucose': _safe_round(mean_glucose, 1),
            'mean_glucose_no_lows': _safe_round(mean_no_lows, 1),
            'ea1c': _safe_round(ea1c, 2),
            'ea1c_no_lows': _safe_round(ea1c_no_lows, 2),
            'a1c_distortion': _safe_round(a1c_distortion, 2),
            'tir': _safe_round(tir, 1),
            'tbr': _safe_round(tbr, 2),
            'deceptive': a1c_distortion > 0.2 and tbr > ADA_TBR_L1_TARGET,
        }
        results['per_patient'].append(rec)

        if args.detail:
            flag = " ⚠️ DECEPTIVE" if rec['deceptive'] else ""
            print(f"  {pid}: eA1C={ea1c:.2f}% (no_lows={ea1c_no_lows:.2f}%) "
                  f"distortion={a1c_distortion:+.2f}% TBR={tbr:.1f}%{flag}")

    results['n_patients'] = len(results['per_patient'])

    # Correlation: TBR vs A1C distortion
    tbrs = [r['tbr'] for r in results['per_patient']]
    distortions = [r['a1c_distortion'] for r in results['per_patient']]
    if len(tbrs) >= 3:
        r_val, p_val = stats.pearsonr(tbrs, distortions)
    else:
        r_val, p_val = 0.0, 1.0

    results['summary'] = {
        'deceptive_count': sum(1 for r in results['per_patient'] if r['deceptive']),
        'tbr_a1c_correlation': _safe_round(float(r_val), 3),
        'tbr_a1c_p_value': _safe_round(float(p_val), 4),
        'max_distortion': _safe_round(max(distortions) if distortions else 0.0, 2),
    }
    return results


# ===================================================================
# EXP-1510: Pipeline v10 Bootstrap Stress Test
# ===================================================================

@register(1510, "Pipeline v10 Bootstrap Stress Test")
def exp_1510(patients, args):
    """Bootstrap resample days (100 iterations) to test v10 grade stability."""
    results = {'per_patient': [], 'n_patients': 0}
    rng = np.random.RandomState(RNG_SEED)

    for pid in sorted(patients):
        p = patients[pid]
        glucose, bolus, carbs = p['glucose'], p['bolus'], p['carbs']
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        if n_days < 14:
            results['per_patient'].append({
                'pid': pid, 'grade_stability': 0.0,
                'reference_grade': 'N/A', 'score_ci': [0, 0],
            })
            if args.detail:
                print(f"  {pid}: insufficient data ({n_days} days)")
            continue

        # Reference assessment on full data
        ref = compute_v10_assessment(glucose, bolus, carbs, n)
        ref_grade = ref['v10_grade']
        ref_score = ref['v10_score']

        # Bootstrap: resample days
        bootstrap_scores = []
        bootstrap_grades = []
        bootstrap_recs = []

        for _ in range(N_BOOTSTRAP_STRESS):
            # Sample n_days days with replacement
            day_indices = rng.choice(n_days, size=n_days, replace=True)
            # Reconstruct arrays from sampled days
            g_boot = np.full(n_days * STEPS_PER_DAY, np.nan)
            b_boot = np.zeros(n_days * STEPS_PER_DAY)
            c_boot = np.zeros(n_days * STEPS_PER_DAY)

            for new_d, orig_d in enumerate(day_indices):
                src_s = orig_d * STEPS_PER_DAY
                src_e = min(src_s + STEPS_PER_DAY, n)
                dst_s = new_d * STEPS_PER_DAY
                chunk = min(STEPS_PER_DAY, src_e - src_s)
                if chunk <= 0:
                    continue
                g_boot[dst_s:dst_s + chunk] = glucose[src_s:src_s + chunk]
                b_boot[dst_s:dst_s + chunk] = bolus[src_s:src_s + chunk]
                c_boot[dst_s:dst_s + chunk] = carbs[src_s:src_s + chunk]

            n_boot = len(g_boot)
            boot_assess = compute_v10_assessment(g_boot, b_boot, c_boot, n_boot)
            bootstrap_scores.append(boot_assess['v10_score'])
            bootstrap_grades.append(boot_assess['v10_grade'])

            # Track recommendation consistency
            flags = boot_assess['flags']
            rec_key = (flags.get('basal_flag', False),
                       flags.get('cr_flag', False),
                       flags.get('tbr_flag', False))
            bootstrap_recs.append(rec_key)

        # Grade stability: % same as reference
        grade_stability = sum(1 for g in bootstrap_grades if g == ref_grade) / N_BOOTSTRAP_STRESS * 100

        # Score CI
        score_ci = [float(np.percentile(bootstrap_scores, 2.5)),
                    float(np.percentile(bootstrap_scores, 97.5))]

        # Recommendation consistency: most common recommendation set
        from collections import Counter
        rec_counts = Counter(bootstrap_recs)
        most_common_rec, most_common_count = rec_counts.most_common(1)[0]
        rec_consistency = most_common_count / N_BOOTSTRAP_STRESS * 100

        rec = {
            'pid': pid,
            'reference_grade': ref_grade,
            'reference_score': _safe_round(ref_score, 1),
            'grade_stability': _safe_round(grade_stability, 1),
            'score_ci_95': [_safe_round(score_ci[0], 1), _safe_round(score_ci[1], 1)],
            'score_range': _safe_round(score_ci[1] - score_ci[0], 1),
            'rec_consistency': _safe_round(rec_consistency, 1),
        }
        results['per_patient'].append(rec)

        if args.detail:
            print(f"  {pid}: grade={ref_grade} stability={grade_stability:.0f}% "
                  f"score={ref_score:.1f} CI=[{score_ci[0]:.1f},{score_ci[1]:.1f}] "
                  f"rec_consist={rec_consistency:.0f}%")

    results['n_patients'] = len(results['per_patient'])
    stabilities = [r['grade_stability'] for r in results['per_patient']
                   if r['reference_grade'] != 'N/A']
    consistencies = [r['rec_consistency'] for r in results['per_patient']
                     if r['reference_grade'] != 'N/A']
    results['summary'] = {
        'mean_grade_stability': _safe_round(
            float(np.mean(stabilities)) if stabilities else 0.0, 1),
        'min_grade_stability': _safe_round(
            float(np.min(stabilities)) if stabilities else 0.0, 1),
        'mean_rec_consistency': _safe_round(
            float(np.mean(consistencies)) if consistencies else 0.0, 1),
        'all_stable': all(s >= 80 for s in stabilities) if stabilities else False,
    }
    return results


# ===================================================================
# Main entry point
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description='EXP-1501 to EXP-1510: v10 Pipeline Comprehensive '
                    'Validation & Safety Refinement')
    parser.add_argument('--detail', action='store_true',
                        help='Show detailed output')
    parser.add_argument('--save', action='store_true',
                        help='Save results to JSON')
    parser.add_argument('--max-patients', type=int, default=11,
                        help='Max patients to load')
    parser.add_argument('--exp', type=int, nargs='*',
                        help='Run specific experiments')
    args = parser.parse_args()

    patients = load_patients(max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    for pid, pdata in sorted(patients.items()):
        n = len(pdata['glucose'])
        n_days = n // STEPS_PER_DAY
        valid_pct = round(pdata['valid'].sum() / max(n, 1) * 100, 1)
        print(f"  {pid}: {n_days}d, CGM coverage={valid_pct:.1f}%")

    to_run = args.exp if args.exp else sorted(EXPERIMENTS.keys())
    all_results = {}

    for exp_id in to_run:
        if exp_id not in EXPERIMENTS:
            print(f"\nWARNING: EXP-{exp_id} not registered, skipping")
            continue

        title, fn = EXPERIMENTS[exp_id]
        print(f"\n{'=' * 60}")
        print(f"EXP-{exp_id}: {title}")
        print(f"{'=' * 60}")

        t0 = time.time()
        try:
            result = fn(patients, args)
            elapsed = time.time() - t0
            result['elapsed_sec'] = round(elapsed, 1)
            all_results[exp_id] = result
            print(f"  Completed in {elapsed:.1f}s")

            if args.save:
                RESULTS_DIR.mkdir(parents=True, exist_ok=True)
                outpath = RESULTS_DIR / f'exp-{exp_id}_therapy.json'
                with open(outpath, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved to {outpath}")
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  FAILED in {elapsed:.1f}s: {e}")
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print("BATCH SUMMARY")
    print(f"{'=' * 60}")
    for exp_id in to_run:
        if exp_id in all_results:
            r = all_results[exp_id]
            print(f"  EXP-{exp_id}: OK ({r.get('elapsed_sec', '?')}s, "
                  f"{r.get('n_patients', '?')} patients)")
        elif exp_id in EXPERIMENTS:
            print(f"  EXP-{exp_id}: FAILED")


if __name__ == '__main__':
    main()
