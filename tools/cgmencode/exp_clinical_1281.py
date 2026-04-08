#!/usr/bin/env python3
"""EXP-1281 through EXP-1290: Therapy Detection & Recommendation.

Strategic pivot from glucose prediction (converged R²=0.496) to therapy
assessment. Uses supply/demand physics decomposition to detect basal
inadequacy, CR miscalibration, ISF drift, and AID loop compensation
patterns. Extends prior work (EXP-693/694/696/685/312/971-991) with
ML-enhanced analysis and multi-day temporal tracking.

Key innovation: The converged prediction pipeline provides a "expected"
baseline — deviations from predictions indicate therapy issues, not
model failure.
"""
import argparse, json, os, sys, time, warnings
import numpy as np
from pathlib import Path
from collections import defaultdict

warnings.filterwarnings('ignore')

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

try:
    from sklearn.linear_model import Ridge, LogisticRegression
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from cgmencode.exp_metabolic_flux import load_patients, save_results
from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_clinical_1211 import (
    prepare_patient_raw, build_enhanced_features, build_enhanced_multi_horizon,
    make_xgb_sota, split_3way, compute_r2, compute_rmse,
    GLUCOSE_SCALE, WINDOW, HORIZON, STRIDE
)

PATIENTS_DIR = str(Path(__file__).resolve().parent.parent.parent
                   / 'externals' / 'ns-data' / 'patients')

STEPS_PER_HOUR = 12   # 5-min intervals
STEPS_PER_DAY = 288


def get_supply_demand(p):
    """Get supply/demand decomposition for a patient."""
    sd = compute_supply_demand(p['df'], p['pk'])
    return sd


def get_time_blocks(n_steps):
    """Assign each timestep to a time-of-day block.
    Returns array of block indices: 0=overnight(0-6), 1=morning(6-10),
    2=midday(10-14), 3=afternoon(14-18), 4=evening(18-22), 5=night(22-24).
    """
    hours = np.arange(n_steps) % STEPS_PER_DAY / STEPS_PER_HOUR
    blocks = np.zeros(n_steps, dtype=int)
    blocks[(hours >= 6) & (hours < 10)] = 1
    blocks[(hours >= 10) & (hours < 14)] = 2
    blocks[(hours >= 14) & (hours < 18)] = 3
    blocks[(hours >= 18) & (hours < 22)] = 4
    blocks[(hours >= 22)] = 5
    return blocks


BLOCK_NAMES = ['overnight(0-6)', 'morning(6-10)', 'midday(10-14)',
               'afternoon(14-18)', 'evening(18-22)', 'night(22-24)']


# ─── EXP-1281: Time-Block Basal Adequacy ────────────────────────────
def exp_1281_timeblock_basal(patients, detail=False):
    """Assess basal adequacy per time-of-day block using supply/demand.

    Extends EXP-693 (overnight-only) to all 6 time blocks.
    Uses fasting periods (no bolus/carb activity for 2h) to isolate
    basal effects from meal effects.
    """
    results = {'name': 'EXP-1281: Time-block basal adequacy',
               'n_patients': len(patients), 'per_patient': []}

    all_block_scores = defaultdict(list)

    for p in patients:
        sd = get_supply_demand(p)
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        supply = sd['supply']
        demand = sd['demand']
        net = sd['net']
        n = len(glucose)
        blocks = get_time_blocks(n)

        # Identify fasting periods: no bolus or carbs for ±2h
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        fasting = np.ones(n, dtype=bool)
        for i in range(n):
            window_start = max(0, i - STEPS_PER_HOUR * 2)
            window_end = min(n, i + STEPS_PER_HOUR * 2)
            if np.any(bolus[window_start:window_end] > 0) or \
               np.any(carbs[window_start:window_end] > 0):
                fasting[i] = False

        valid = ~np.isnan(glucose) & fasting

        patient_blocks = {}
        for b in range(6):
            mask = valid & (blocks == b)
            if mask.sum() < 12:  # need at least 1h of data
                patient_blocks[BLOCK_NAMES[b]] = {
                    'n_steps': int(mask.sum()), 'status': 'insufficient_data'}
                continue

            block_glucose = glucose[mask]
            block_net = net[mask]
            block_supply = supply[mask]
            block_demand = demand[mask]

            mean_bg = float(np.nanmean(block_glucose))
            tir = float(np.mean((block_glucose >= 70) & (block_glucose <= 180)) * 100)
            tbr = float(np.mean(block_glucose < 70) * 100)
            tar = float(np.mean(block_glucose > 180) * 100)
            mean_net = float(np.mean(block_net))
            sd_ratio = float(np.mean(block_supply) / (np.mean(block_demand) + 1e-6))

            # Basal assessment logic
            if tbr > 5:
                assessment = 'basal_too_high'
            elif mean_bg > 200 and mean_net > 1:
                assessment = 'basal_too_low'
            elif tir > 70 and tbr < 4:
                assessment = 'basal_appropriate'
            elif mean_net < -2:
                assessment = 'basal_slightly_high'
            elif mean_net > 2:
                assessment = 'basal_slightly_low'
            elif mean_bg > 180:
                assessment = 'basal_insufficient'
            else:
                assessment = 'basal_borderline'

            # Score: 0-100, higher = better basal calibration
            tir_score = min(100, tir / 0.7)  # 70% TIR = 100
            tbr_penalty = max(0, tbr - 1) * 10  # each % TBR over 1% costs 10
            net_penalty = min(30, abs(mean_net) * 5)  # ideal net ≈ 0
            basal_score = max(0, tir_score - tbr_penalty - net_penalty)

            block_info = {
                'n_steps': int(mask.sum()),
                'n_hours': round(mask.sum() / STEPS_PER_HOUR, 1),
                'mean_bg': round(mean_bg, 1),
                'tir': round(tir, 1),
                'tbr': round(tbr, 1),
                'tar': round(tar, 1),
                'mean_net': round(mean_net, 2),
                'sd_ratio': round(sd_ratio, 3),
                'assessment': assessment,
                'basal_score': round(basal_score, 1),
            }
            patient_blocks[BLOCK_NAMES[b]] = block_info
            all_block_scores[BLOCK_NAMES[b]].append(basal_score)

        # Overall patient basal score
        scores = [v['basal_score'] for v in patient_blocks.values()
                  if isinstance(v, dict) and 'basal_score' in v]
        overall_score = np.mean(scores) if scores else 0

        # Find worst block
        worst_block = min(
            [(k, v['basal_score']) for k, v in patient_blocks.items()
             if isinstance(v, dict) and 'basal_score' in v],
            key=lambda x: x[1], default=('none', 0))

        results['per_patient'].append({
            'patient': p['name'],
            'blocks': patient_blocks,
            'overall_basal_score': round(overall_score, 1),
            'worst_block': worst_block[0],
            'worst_block_score': round(worst_block[1], 1),
        })

    # Cross-patient summary
    block_summary = {}
    for block_name in BLOCK_NAMES:
        scores = all_block_scores[block_name]
        if scores:
            block_summary[block_name] = {
                'mean_score': round(np.mean(scores), 1),
                'min_score': round(np.min(scores), 1),
                'n_patients': len(scores),
            }
    results['block_summary'] = block_summary
    results['mean_overall_score'] = round(
        np.mean([r['overall_basal_score'] for r in results['per_patient']]), 1)

    return results


# ─── EXP-1282: Per-Meal CR Scoring with Postprandial Analysis ──────
def exp_1282_meal_cr_scoring(patients, detail=False):
    """Score each detected meal event for CR effectiveness.

    Extends EXP-694 with:
    - Time-of-day stratification (breakfast/lunch/dinner)
    - Supply/demand trajectory analysis (not just peak BG)
    - Net flux area-under-curve for meal recovery quality
    """
    results = {'name': 'EXP-1282: Per-meal CR scoring',
               'n_patients': len(patients), 'per_patient': []}

    MEAL_WINDOW = STEPS_PER_HOUR * 4  # 4h post-meal analysis
    MIN_CARBS = 5  # minimum carbs to count as meal

    for p in patients:
        sd = get_supply_demand(p)
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        carbs = df['carbs'].values
        bolus = df['bolus'].values
        net = sd['net']
        supply = sd['supply']
        demand = sd['demand']
        n = len(glucose)
        blocks = get_time_blocks(n)

        # Detect meal events (carbs > MIN_CARBS with minimum 2h spacing)
        meal_indices = []
        last_meal = -STEPS_PER_HOUR * 2
        for i in range(n):
            if carbs[i] >= MIN_CARBS and (i - last_meal) >= STEPS_PER_HOUR * 2:
                meal_indices.append(i)
                last_meal = i

        meal_scores = defaultdict(list)
        all_meals = []

        for mi in meal_indices:
            if mi + MEAL_WINDOW >= n:
                continue
            window = slice(mi, mi + MEAL_WINDOW)
            win_glucose = glucose[window]
            win_net = net[window]

            if np.sum(np.isnan(win_glucose)) > MEAL_WINDOW * 0.3:
                continue

            pre_bg = glucose[max(0, mi - 6):mi]
            pre_bg = pre_bg[~np.isnan(pre_bg)]
            if len(pre_bg) == 0:
                continue
            baseline = np.mean(pre_bg)

            peak_bg = float(np.nanmax(win_glucose))
            excursion = peak_bg - baseline

            # Recovery: time to return within 20 mg/dL of baseline
            recovery_min = MEAL_WINDOW * 5  # default: never recovered
            for j in range(STEPS_PER_HOUR, MEAL_WINDOW):  # start checking after 1h
                if abs(glucose[mi + j] - baseline) < 20:
                    # Check stability: 3 consecutive within range
                    stable = True
                    for k in range(1, min(4, MEAL_WINDOW - j)):
                        if mi + j + k < n and abs(glucose[mi + j + k] - baseline) >= 30:
                            stable = False
                            break
                    if stable:
                        recovery_min = j * 5
                        break

            # Net flux AUC (positive = supply exceeded demand = insulin insufficient)
            net_auc = float(np.nansum(win_net)) * 5 / 60  # mg/dL·hours

            # Determine meal time category
            block = blocks[mi]
            if block <= 1:
                meal_time = 'breakfast'
            elif block <= 2:
                meal_time = 'lunch'
            elif block <= 4:
                meal_time = 'dinner'
            else:
                meal_time = 'snack'

            # CR score (0-100)
            time_score = max(0, min(100, (240 - recovery_min) / 200 * 100))
            peak_score = max(0, min(100, (300 - peak_bg) / 160 * 100))
            excursion_score = max(0, min(100, (150 - excursion) / 120 * 100))
            cr_score = (time_score + peak_score + excursion_score) / 3

            meal_info = {
                'index': int(mi),
                'carbs': float(carbs[mi]),
                'bolus_nearby': float(np.sum(bolus[max(0, mi-3):mi+3])),
                'baseline': round(baseline, 1),
                'peak_bg': round(peak_bg, 1),
                'excursion': round(excursion, 1),
                'recovery_min': int(recovery_min),
                'net_auc': round(net_auc, 2),
                'meal_time': meal_time,
                'cr_score': round(cr_score, 1),
            }
            all_meals.append(meal_info)
            meal_scores[meal_time].append(cr_score)

        # Summarize by meal time
        meal_summary = {}
        for mt in ['breakfast', 'lunch', 'dinner', 'snack']:
            scores = meal_scores.get(mt, [])
            if scores:
                meal_summary[mt] = {
                    'n_meals': len(scores),
                    'mean_cr_score': round(np.mean(scores), 1),
                    'worst_score': round(np.min(scores), 1),
                    'best_score': round(np.max(scores), 1),
                }

        all_scores = [m['cr_score'] for m in all_meals]
        worst_time = min(meal_summary.items(),
                        key=lambda x: x[1]['mean_cr_score'],
                        default=('none', {'mean_cr_score': 0}))

        results['per_patient'].append({
            'patient': p['name'],
            'n_meals': len(all_meals),
            'overall_cr_score': round(np.mean(all_scores), 1) if all_scores else 0,
            'meal_summary': meal_summary,
            'worst_meal_time': worst_time[0],
            'worst_meal_score': worst_time[1]['mean_cr_score'] if isinstance(worst_time[1], dict) else 0,
            'top5_worst': sorted(all_meals, key=lambda x: x['cr_score'])[:5] if detail else [],
        })

    results['mean_cr_score'] = round(
        np.mean([r['overall_cr_score'] for r in results['per_patient']]), 1)
    return results


# ─── EXP-1283: ISF Effective Estimation from Correction Responses ──
def exp_1283_isf_estimation(patients, detail=False):
    """Estimate effective ISF from correction bolus responses.

    Uses supply/demand decomposition to isolate insulin effect from
    concurrent carb absorption. Compares to profile ISF.
    """
    results = {'name': 'EXP-1283: ISF effective estimation',
               'n_patients': len(patients), 'per_patient': []}

    DIA_STEPS = STEPS_PER_HOUR * 5  # 5h DIA

    for p in patients:
        sd = get_supply_demand(p)
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        demand = sd['demand']
        pk = p['pk']
        n = len(glucose)

        # Profile ISF from PK channel 7
        isf_profile = pk[:, 7] * 200.0  # denormalize

        # Find correction boluses: bolus with no carbs within ±30min
        corrections = []
        for i in range(n):
            if bolus[i] <= 0.1:
                continue
            carb_window = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[carb_window]) > 2:
                continue  # has carbs nearby → meal bolus
            if i + DIA_STEPS >= n:
                continue
            # Also skip if another bolus within DIA
            future_bolus = bolus[i + 1:i + DIA_STEPS]
            if np.sum(future_bolus) > 0.5:
                continue

            pre_bg = glucose[max(0, i - 3):i + 1]
            pre_bg = pre_bg[~np.isnan(pre_bg)]
            if len(pre_bg) == 0:
                continue
            start_bg = np.mean(pre_bg)

            # Find nadir in DIA window
            future_bg = glucose[i:i + DIA_STEPS]
            valid_future = ~np.isnan(future_bg)
            if valid_future.sum() < DIA_STEPS * 0.5:
                continue
            nadir_idx = np.nanargmin(future_bg)
            nadir_bg = future_bg[nadir_idx]

            delta_bg = start_bg - nadir_bg
            insulin_amount = float(bolus[i])

            if insulin_amount > 0.3 and delta_bg > 10:
                isf_effective = delta_bg / insulin_amount
                isf_from_profile = float(np.mean(isf_profile[i:i + DIA_STEPS]))

                corrections.append({
                    'index': int(i),
                    'bolus': round(insulin_amount, 2),
                    'start_bg': round(start_bg, 1),
                    'nadir_bg': round(nadir_bg, 1),
                    'delta_bg': round(delta_bg, 1),
                    'isf_effective': round(isf_effective, 1),
                    'isf_profile': round(isf_from_profile, 1),
                    'isf_ratio': round(isf_effective / (isf_from_profile + 1e-6), 2),
                    'nadir_time_min': int(nadir_idx * 5),
                })

        if corrections:
            isf_effs = [c['isf_effective'] for c in corrections]
            isf_profs = [c['isf_profile'] for c in corrections]
            isf_ratios = [c['isf_ratio'] for c in corrections]
            results['per_patient'].append({
                'patient': p['name'],
                'n_corrections': len(corrections),
                'mean_isf_effective': round(np.mean(isf_effs), 1),
                'std_isf_effective': round(np.std(isf_effs), 1),
                'mean_isf_profile': round(np.mean(isf_profs), 1),
                'mean_ratio': round(np.mean(isf_ratios), 2),
                'median_ratio': round(np.median(isf_ratios), 2),
                'isf_calibration': ('accurate' if 0.8 <= np.median(isf_ratios) <= 1.2
                                    else 'too_sensitive' if np.median(isf_ratios) > 1.2
                                    else 'too_resistant'),
                'mean_nadir_min': round(np.mean([c['nadir_time_min'] for c in corrections]), 0),
                'corrections': corrections[:10] if detail else [],
            })
        else:
            results['per_patient'].append({
                'patient': p['name'],
                'n_corrections': 0,
                'note': 'No isolated correction boluses found',
            })

    n_with_data = sum(1 for r in results['per_patient'] if r['n_corrections'] > 0)
    results['n_patients_with_corrections'] = n_with_data
    if n_with_data > 0:
        results['mean_isf_ratio'] = round(np.mean(
            [r['mean_ratio'] for r in results['per_patient'] if r['n_corrections'] > 0]), 2)
    return results


# ─── EXP-1284: AID Loop Compensation Profiling ─────────────────────
def exp_1284_loop_compensation(patients, detail=False):
    """Profile AID loop compensation patterns using temp basal analysis.

    Quantifies how much the loop deviates from scheduled basal,
    revealing whether settings are calibrated or the loop is
    doing all the work.
    """
    results = {'name': 'EXP-1284: AID loop compensation profiling',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        pk = p['pk']
        temp_rate = df['temp_rate'].values
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else None
        glucose = df['glucose'].values.astype(float)
        n = len(glucose)
        blocks = get_time_blocks(n)

        # Basal ratio from PK channel 2
        basal_ratio = pk[:, 2] * 2.0  # denormalize

        valid = ~np.isnan(glucose)

        # Classification: suspended (<5%), nominal (90-110%), increased (>150%)
        suspended = (temp_rate < 0.05) & valid
        nominal = (temp_rate > 0) & valid  # any non-zero
        # Use basal_ratio for more precise classification
        ratio_suspended = (basal_ratio < 0.1) & valid
        ratio_nominal = (basal_ratio >= 0.9) & (basal_ratio <= 1.1) & valid
        ratio_high = (basal_ratio > 1.5) & valid
        ratio_low = (basal_ratio > 0.1) & (basal_ratio < 0.9) & valid

        overall = {
            'pct_suspended': round(ratio_suspended.mean() * 100, 1),
            'pct_nominal': round(ratio_nominal.mean() * 100, 1),
            'pct_increased': round(ratio_high.mean() * 100, 1),
            'pct_decreased': round(ratio_low.mean() * 100, 1),
            'mean_basal_ratio': round(float(np.mean(basal_ratio[valid])), 3),
            'std_basal_ratio': round(float(np.std(basal_ratio[valid])), 3),
        }

        # Per-block analysis
        block_profiles = {}
        for b in range(6):
            mask = valid & (blocks == b)
            if mask.sum() < 12:
                continue
            br = basal_ratio[mask]
            bg = glucose[mask]
            block_profiles[BLOCK_NAMES[b]] = {
                'mean_ratio': round(float(np.mean(br)), 3),
                'pct_suspended': round(float((br < 0.1).mean() * 100), 1),
                'pct_nominal': round(float(((br >= 0.9) & (br <= 1.1)).mean() * 100), 1),
                'pct_high': round(float((br > 1.5).mean() * 100), 1),
                'mean_bg': round(float(np.nanmean(bg)), 1),
            }

        # Loop aggressiveness score (0-100, 100 = loop doing everything)
        deviation = np.abs(basal_ratio[valid] - 1.0)
        aggressiveness = float(np.mean(deviation > 0.3) * 100)

        # Compensation phenotype
        if overall['pct_suspended'] > 40:
            phenotype = 'suspension-dominant'
        elif overall['pct_increased'] > 30:
            phenotype = 'increase-dominant'
        elif overall['pct_nominal'] > 40:
            phenotype = 'well-calibrated'
        else:
            phenotype = 'bidirectional'

        results['per_patient'].append({
            'patient': p['name'],
            'overall': overall,
            'block_profiles': block_profiles,
            'aggressiveness': round(aggressiveness, 1),
            'phenotype': phenotype,
        })

    # Summary
    phenotypes = [r['phenotype'] for r in results['per_patient']]
    results['phenotype_distribution'] = {
        ph: phenotypes.count(ph) for ph in set(phenotypes)}
    results['mean_aggressiveness'] = round(
        np.mean([r['aggressiveness'] for r in results['per_patient']]), 1)

    return results


# ─── EXP-1285: Multi-Day Therapy Tracking ──────────────────────────
def exp_1285_multiday_tracking(patients, detail=False):
    """Track therapy effectiveness over rolling multi-day windows.

    Computes 3-day and 7-day rolling therapy scores to detect
    trends and settings drift.
    """
    results = {'name': 'EXP-1285: Multi-day therapy tracking',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        sd = get_supply_demand(p)
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        net = sd['net']
        supply = sd['supply']
        demand = sd['demand']
        n = len(glucose)

        n_days = n // STEPS_PER_DAY

        # Daily metrics
        daily = []
        for d in range(n_days):
            start = d * STEPS_PER_DAY
            end = start + STEPS_PER_DAY
            g = glucose[start:end]
            valid_g = g[~np.isnan(g)]
            if len(valid_g) < STEPS_PER_DAY * 0.5:
                continue
            tir = float(np.mean((valid_g >= 70) & (valid_g <= 180)) * 100)
            tbr = float(np.mean(valid_g < 70) * 100)
            tar = float(np.mean(valid_g > 180) * 100)
            mean_net = float(np.mean(net[start:end]))
            sd_ratio = float(np.mean(supply[start:end]) /
                           (np.mean(demand[start:end]) + 1e-6))
            cv = float(np.std(valid_g) / (np.mean(valid_g) + 1e-6) * 100)
            daily.append({
                'day': d, 'tir': tir, 'tbr': tbr, 'tar': tar,
                'mean_net': mean_net, 'sd_ratio': sd_ratio, 'cv': cv,
                'mean_bg': float(np.mean(valid_g)),
            })

        if len(daily) < 7:
            results['per_patient'].append({
                'patient': p['name'], 'note': 'insufficient days'})
            continue

        # Rolling windows
        def rolling_score(daily_list, window):
            scores = []
            for i in range(len(daily_list) - window + 1):
                w = daily_list[i:i + window]
                tir_avg = np.mean([d['tir'] for d in w])
                tbr_avg = np.mean([d['tbr'] for d in w])
                cv_avg = np.mean([d['cv'] for d in w])
                net_avg = np.mean([d['mean_net'] for d in w])
                # Composite score
                score = min(100, tir_avg) - max(0, tbr_avg - 1) * 10 - abs(net_avg) * 3
                scores.append({
                    'start_day': w[0]['day'],
                    'tir': round(tir_avg, 1),
                    'tbr': round(tbr_avg, 1),
                    'cv': round(cv_avg, 1),
                    'net': round(net_avg, 2),
                    'score': round(max(0, score), 1),
                })
            return scores

        scores_3d = rolling_score(daily, 3)
        scores_7d = rolling_score(daily, 7)

        # Trend detection: is therapy improving or degrading?
        if len(scores_7d) >= 4:
            first_half = np.mean([s['score'] for s in scores_7d[:len(scores_7d)//2]])
            second_half = np.mean([s['score'] for s in scores_7d[len(scores_7d)//2:]])
            trend = second_half - first_half
            trend_label = ('improving' if trend > 3 else
                          'degrading' if trend < -3 else 'stable')
        else:
            trend = 0
            trend_label = 'insufficient_data'

        # Detect significant drops (settings may have changed)
        drops_7d = []
        for i in range(1, len(scores_7d)):
            delta = scores_7d[i]['score'] - scores_7d[i-1]['score']
            if delta < -10:
                drops_7d.append({
                    'day': scores_7d[i]['start_day'],
                    'delta': round(delta, 1),
                    'score_before': scores_7d[i-1]['score'],
                    'score_after': scores_7d[i]['score'],
                })

        results['per_patient'].append({
            'patient': p['name'],
            'n_days': len(daily),
            'mean_daily_tir': round(np.mean([d['tir'] for d in daily]), 1),
            'mean_7d_score': round(np.mean([s['score'] for s in scores_7d]), 1) if scores_7d else 0,
            'score_trend': round(trend, 1),
            'trend_label': trend_label,
            'n_significant_drops': len(drops_7d),
            'drops': drops_7d,
            'scores_3d': scores_3d if detail else
                        [scores_3d[0], scores_3d[-1]] if scores_3d else [],
            'scores_7d': scores_7d if detail else
                        [scores_7d[0], scores_7d[-1]] if scores_7d else [],
        })

    results['mean_trend'] = round(np.mean(
        [r['score_trend'] for r in results['per_patient']
         if 'score_trend' in r]), 1)
    results['trend_distribution'] = {
        label: sum(1 for r in results['per_patient']
                   if r.get('trend_label') == label)
        for label in ['improving', 'degrading', 'stable', 'insufficient_data']
    }
    return results


# ─── EXP-1286: Prediction Error as Therapy Signal ──────────────────
def exp_1286_prediction_error_signal(patients, detail=False):
    """Use prediction model errors to detect therapy issues.

    When the converged model (R²=0.496) makes large errors, it signals
    unmodeled events: missed meals, exercise, site failures, compression.
    Classify error patterns into therapy-actionable categories.
    """
    results = {'name': 'EXP-1286: Prediction error as therapy signal',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        glucose_raw, physics = prepare_patient_raw(p)
        X, y, _ = build_enhanced_features(p, glucose_raw, physics)
        if len(X) < 100:
            continue

        # Train production model
        n = len(X)
        train_end = int(n * 0.7)
        X_train, X_test = X[:train_end], X[train_end:]
        y_train, y_test = y[:train_end], y[train_end:]

        model = xgb.XGBRegressor(
            n_estimators=300, max_depth=2, learning_rate=0.03,
            tree_method='hist', device='cuda',
            subsample=0.8, colsample_bytree=0.8)
        model.fit(X_train, y_train, verbose=False)
        y_pred = model.predict(X_test)
        residuals = (y_test - y_pred) * GLUCOSE_SCALE

        rmse = float(np.sqrt(np.mean(residuals**2)))
        r2 = compute_r2(y_test, y_pred)

        # Classify error magnitudes
        abs_err = np.abs(residuals)
        large_error_mask = abs_err > 2 * rmse  # >2σ errors
        n_large = int(large_error_mask.sum())

        # Analyze large errors: are they systematic?
        if n_large > 5:
            large_indices = np.where(large_error_mask)[0]
            # Check if large errors cluster (run-length analysis)
            clusters = []
            current_cluster = [large_indices[0]]
            for i in range(1, len(large_indices)):
                if large_indices[i] - large_indices[i-1] <= 6:  # within 30min
                    current_cluster.append(large_indices[i])
                else:
                    if len(current_cluster) >= 3:
                        clusters.append({
                            'start': int(current_cluster[0]),
                            'length': len(current_cluster),
                            'mean_error': round(float(np.mean(residuals[current_cluster])), 1),
                            'direction': 'under' if np.mean(residuals[current_cluster]) > 0 else 'over',
                        })
                    current_cluster = [large_indices[i]]
            if len(current_cluster) >= 3:
                clusters.append({
                    'start': int(current_cluster[0]),
                    'length': len(current_cluster),
                    'mean_error': round(float(np.mean(residuals[current_cluster])), 1),
                    'direction': 'under' if np.mean(residuals[current_cluster]) > 0 else 'over',
                })
        else:
            clusters = []

        # Error direction analysis
        under_pred = float(np.mean(residuals[residuals > 0]))  # model too low
        over_pred = float(np.mean(residuals[residuals < 0]))  # model too high
        bias = float(np.mean(residuals))

        # Systematic error by glucose level
        df = p['df']
        test_glucose = df['glucose'].values[train_end + WINDOW + HORIZON - 1:
                                             train_end + WINDOW + HORIZON - 1 + len(y_test)]
        if len(test_glucose) == len(residuals):
            test_g = test_glucose  # already in mg/dL
            low_mask = test_g < 100
            normal_mask = (test_g >= 100) & (test_g <= 180)
            high_mask = test_g > 180
            level_errors = {
                'low_rmse': round(float(np.sqrt(np.mean(residuals[low_mask]**2))), 1) if low_mask.sum() > 10 else None,
                'normal_rmse': round(float(np.sqrt(np.mean(residuals[normal_mask]**2))), 1) if normal_mask.sum() > 10 else None,
                'high_rmse': round(float(np.sqrt(np.mean(residuals[high_mask]**2))), 1) if high_mask.sum() > 10 else None,
            }
        else:
            level_errors = {}

        results['per_patient'].append({
            'patient': p['name'],
            'r2': round(r2, 4),
            'rmse': round(rmse, 1),
            'bias': round(bias, 1),
            'n_large_errors': n_large,
            'pct_large_errors': round(n_large / len(residuals) * 100, 1),
            'n_error_clusters': len(clusters),
            'clusters': clusters[:5] if detail else [],
            'under_prediction_mean': round(under_pred, 1),
            'over_prediction_mean': round(over_pred, 1),
            'level_errors': level_errors,
        })

    results['mean_pct_large_errors'] = round(np.mean(
        [r['pct_large_errors'] for r in results['per_patient']]), 1)
    results['mean_clusters'] = round(np.mean(
        [r['n_error_clusters'] for r in results['per_patient']]), 1)
    return results


# ─── EXP-1287: Settings Recommendation Engine ──────────────────────
def exp_1287_settings_recommendations(patients, detail=False):
    """Generate specific therapy settings recommendations.

    Combines supply/demand analysis, basal adequacy, CR scoring,
    and ISF estimation to produce actionable recommendations.
    """
    results = {'name': 'EXP-1287: Settings recommendation engine',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        sd = get_supply_demand(p)
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        net = sd['net']
        supply = sd['supply']
        demand = sd['demand']
        pk = p['pk']
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        blocks = get_time_blocks(n)

        valid = ~np.isnan(glucose)
        recommendations = []
        evidence = {}

        # 1. Basal assessment per block
        for b in range(6):
            mask = valid & (blocks == b)
            # Fasting filter
            fasting = np.ones(n, dtype=bool)
            for i in np.where(mask)[0]:
                ws = max(0, i - STEPS_PER_HOUR * 2)
                we = min(n, i + STEPS_PER_HOUR * 2)
                if np.any(bolus[ws:we] > 0) or np.any(carbs[ws:we] > 0):
                    fasting[i] = False
            fmask = mask & fasting
            if fmask.sum() < 12:
                continue

            bg = glucose[fmask]
            n_flux = net[fmask]
            mean_bg = float(np.nanmean(bg))
            mean_net = float(np.mean(n_flux))
            tir = float(np.mean((bg >= 70) & (bg <= 180)) * 100)
            tbr = float(np.mean(bg < 70) * 100)

            if tbr > 5:
                pct_change = round(-10 - (tbr - 5) * 3, 0)
                recommendations.append({
                    'type': 'decrease_basal',
                    'block': BLOCK_NAMES[b],
                    'reason': f'TBR={tbr:.1f}% during {BLOCK_NAMES[b]}',
                    'suggested_change_pct': pct_change,
                    'confidence': 'high',
                })
            elif mean_bg > 180 and mean_net > 1:
                pct_change = round(5 + mean_net * 3, 0)
                recommendations.append({
                    'type': 'increase_basal',
                    'block': BLOCK_NAMES[b],
                    'reason': f'Mean BG={mean_bg:.0f}, net flux={mean_net:.1f} during fasting',
                    'suggested_change_pct': pct_change,
                    'confidence': 'medium',
                })

        # 2. CR assessment by meal time
        meal_blocks = {1: 'breakfast', 2: 'lunch', 3: 'dinner', 4: 'dinner'}
        for b, meal_name in meal_blocks.items():
            mask = valid & (blocks == b)
            if mask.sum() < 12:
                continue
            # Look for post-meal excursions
            meal_mask = mask & (carbs > 3)
            if meal_mask.sum() < 3:
                continue

            post_meal_bgs = []
            for i in np.where(meal_mask)[0]:
                if i + STEPS_PER_HOUR * 3 < n:
                    pm = glucose[i:i + STEPS_PER_HOUR * 3]
                    pm = pm[~np.isnan(pm)]
                    if len(pm) > 0:
                        post_meal_bgs.append(float(np.max(pm)))

            if post_meal_bgs:
                mean_peak = np.mean(post_meal_bgs)
                if mean_peak > 250:
                    recommendations.append({
                        'type': 'decrease_cr',
                        'meal': meal_name,
                        'reason': f'Mean post-meal peak={mean_peak:.0f} mg/dL at {meal_name}',
                        'suggested_change': 'Decrease CR by 1-2 g/U',
                        'confidence': 'medium',
                    })
                elif mean_peak < 140:
                    recommendations.append({
                        'type': 'increase_cr',
                        'meal': meal_name,
                        'reason': f'Mean post-meal peak only {mean_peak:.0f} mg/dL at {meal_name}',
                        'suggested_change': 'Increase CR by 1-2 g/U',
                        'confidence': 'low',
                    })

        # 3. Loop compensation check
        basal_ratio = pk[:, 2] * 2.0
        br_valid = basal_ratio[valid]
        pct_suspended = float((br_valid < 0.1).mean() * 100)
        pct_high = float((br_valid > 1.5).mean() * 100)

        if pct_suspended > 40:
            recommendations.append({
                'type': 'reduce_all_basal',
                'reason': f'Loop suspends {pct_suspended:.0f}% of time — basal rates too high',
                'suggested_change': 'Reduce all basal rates by 15-25%',
                'confidence': 'high',
            })
        elif pct_high > 40:
            recommendations.append({
                'type': 'increase_all_basal',
                'reason': f'Loop increases >150% for {pct_high:.0f}% of time — basal rates too low',
                'suggested_change': 'Increase all basal rates by 10-20%',
                'confidence': 'high',
            })

        # 4. Overall TIR
        all_bg = glucose[valid]
        overall_tir = float(np.mean((all_bg >= 70) & (all_bg <= 180)) * 100)
        overall_tbr = float(np.mean(all_bg < 70) * 100)
        overall_tar = float(np.mean(all_bg > 180) * 100)

        if overall_tir > 70 and overall_tbr < 4:
            evidence['overall_status'] = 'good_control'
        elif overall_tbr > 5:
            evidence['overall_status'] = 'excessive_lows'
        else:
            evidence['overall_status'] = 'needs_improvement'

        evidence['tir'] = round(overall_tir, 1)
        evidence['tbr'] = round(overall_tbr, 1)
        evidence['tar'] = round(overall_tar, 1)

        # Prioritize recommendations
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        recommendations.sort(key=lambda r: priority_order.get(r.get('confidence', 'low'), 2))

        results['per_patient'].append({
            'patient': p['name'],
            'n_recommendations': len(recommendations),
            'recommendations': recommendations,
            'evidence': evidence,
        })

    results['recommendation_types'] = defaultdict(int)
    for r in results['per_patient']:
        for rec in r['recommendations']:
            results['recommendation_types'][rec['type']] += 1
    results['recommendation_types'] = dict(results['recommendation_types'])
    results['mean_recommendations'] = round(np.mean(
        [r['n_recommendations'] for r in results['per_patient']]), 1)

    return results


# ─── EXP-1288: DIA Adequacy Assessment ─────────────────────────────
def exp_1288_dia_adequacy(patients, detail=False):
    """Assess whether DIA (Duration of Insulin Action) is appropriate.

    Analyzes insulin absorption completion by checking if BG has
    stabilized by DIA endpoint. If BG is still changing at DIA,
    the DIA setting may be too short.
    """
    results = {'name': 'EXP-1288: DIA adequacy assessment',
               'n_patients': len(patients), 'per_patient': []}

    DIA_HOURS = [3, 4, 5, 6, 7]  # test multiple DIA values

    for p in patients:
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        pk = p['pk']
        n = len(glucose)

        # Find isolated boluses (corrections only, no carbs)
        corrections = []
        for i in range(n):
            if bolus[i] < 0.5:
                continue
            carb_window = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[carb_window]) > 2:
                continue
            max_dia_steps = max(DIA_HOURS) * STEPS_PER_HOUR
            if i + max_dia_steps >= n:
                continue
            future_bolus = bolus[i + 1:i + max_dia_steps]
            if np.sum(future_bolus) > 0.5:
                continue
            corrections.append(i)

        if len(corrections) < 3:
            results['per_patient'].append({
                'patient': p['name'],
                'note': f'Only {len(corrections)} isolated corrections found'})
            continue

        # For each DIA value, check residual BG rate of change at DIA endpoint
        dia_scores = {}
        for dia_h in DIA_HOURS:
            dia_steps = dia_h * STEPS_PER_HOUR
            residual_rates = []
            for ci in corrections:
                # Rate of change at DIA endpoint (±15 min window)
                end_start = ci + dia_steps - 3
                end_stop = ci + dia_steps + 3
                if end_stop >= n:
                    continue
                end_bg = glucose[end_start:end_stop]
                end_bg = end_bg[~np.isnan(end_bg)]
                if len(end_bg) < 4:
                    continue
                # Rate in mg/dL per hour
                rate = (end_bg[-1] - end_bg[0]) / (len(end_bg) * 5 / 60)
                residual_rates.append(rate)

            if residual_rates:
                mean_rate = float(np.mean(np.abs(residual_rates)))
                dia_scores[dia_h] = {
                    'n_events': len(residual_rates),
                    'mean_abs_rate': round(mean_rate, 2),
                    'median_abs_rate': round(float(np.median(np.abs(residual_rates))), 2),
                    'pct_stable': round(float(np.mean(np.array(np.abs(residual_rates)) < 10) * 100), 1),
                }

        # Find optimal DIA: first one where >80% are stable
        optimal_dia = None
        for dia_h in DIA_HOURS:
            if dia_h in dia_scores and dia_scores[dia_h]['pct_stable'] >= 80:
                optimal_dia = dia_h
                break
        if optimal_dia is None and dia_scores:
            optimal_dia = max(dia_scores, key=lambda h: dia_scores[h]['pct_stable'])

        results['per_patient'].append({
            'patient': p['name'],
            'n_corrections': len(corrections),
            'dia_analysis': dia_scores,
            'suggested_dia': optimal_dia,
            'current_assessment': ('adequate' if optimal_dia and optimal_dia <= 5
                                  else 'may_need_increase' if optimal_dia and optimal_dia > 5
                                  else 'inconclusive'),
        })

    n_assessed = sum(1 for r in results['per_patient'] if 'dia_analysis' in r)
    results['n_patients_assessed'] = n_assessed
    if n_assessed > 0:
        dias = [r['suggested_dia'] for r in results['per_patient']
                if r.get('suggested_dia') is not None]
        results['mean_suggested_dia'] = round(np.mean(dias), 1) if dias else None
    return results


# ─── EXP-1289: Temporal ISF Profiling ──────────────────────────────
def exp_1289_temporal_isf(patients, detail=False):
    """Profile ISF variation across time of day (circadian pattern).

    Detects dawn phenomenon and other time-varying insulin sensitivity
    patterns using supply/demand decomposition.
    """
    results = {'name': 'EXP-1289: Temporal ISF profiling',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        sd = get_supply_demand(p)
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        pk = p['pk']
        demand = sd['demand']
        supply = sd['supply']
        net = sd['net']
        n = len(glucose)

        # ISF from PK channel 7
        isf_profile = pk[:, 7] * 200.0

        # Hourly aggregation
        hours = np.arange(n) % STEPS_PER_DAY / STEPS_PER_HOUR
        hourly_isf = {}
        hourly_demand = {}
        hourly_net = {}

        for h in range(24):
            mask = (hours >= h) & (hours < h + 1) & ~np.isnan(glucose)
            if mask.sum() < 12:
                continue

            isf_vals = isf_profile[mask]
            demand_vals = demand[mask]
            net_vals = net[mask]
            bg_vals = glucose[mask]

            # Effective demand-to-bg-change ratio (proxy for ISF)
            # Higher demand with less BG drop = more resistant (lower ISF)
            hourly_isf[h] = {
                'mean_isf': round(float(np.mean(isf_vals)), 1),
                'mean_demand': round(float(np.mean(demand_vals)), 3),
                'mean_net': round(float(np.mean(net_vals)), 2),
                'mean_bg': round(float(np.nanmean(bg_vals)), 1),
            }

        # Dawn phenomenon detection
        # Compare 4-7 AM ISF/demand to 10 PM - midnight
        dawn_hours = [4, 5, 6]
        night_hours = [22, 23]
        dawn_demand = np.mean([hourly_isf[h]['mean_demand']
                              for h in dawn_hours if h in hourly_isf]) if all(h in hourly_isf for h in dawn_hours) else None
        night_demand = np.mean([hourly_isf[h]['mean_demand']
                               for h in night_hours if h in hourly_isf]) if all(h in hourly_isf for h in night_hours) else None

        dawn_net = np.mean([hourly_isf[h]['mean_net']
                           for h in dawn_hours if h in hourly_isf]) if all(h in hourly_isf for h in dawn_hours) else None

        if dawn_demand is not None and night_demand is not None:
            dawn_ratio = dawn_demand / (night_demand + 1e-6)
            dawn_phenomenon = dawn_ratio > 1.2 or (dawn_net is not None and dawn_net > 2)
        else:
            dawn_ratio = None
            dawn_phenomenon = None

        # ISF variability across day
        isf_values = [hourly_isf[h]['mean_isf'] for h in sorted(hourly_isf)]
        if isf_values:
            isf_cv = float(np.std(isf_values) / (np.mean(isf_values) + 1e-6) * 100)
            isf_range = float(max(isf_values) - min(isf_values))
            peak_hour = sorted(hourly_isf, key=lambda h: hourly_isf[h]['mean_isf'])[-1]
            trough_hour = sorted(hourly_isf, key=lambda h: hourly_isf[h]['mean_isf'])[0]
        else:
            isf_cv = isf_range = 0
            peak_hour = trough_hour = 0

        results['per_patient'].append({
            'patient': p['name'],
            'hourly_profile': hourly_isf if detail else {},
            'isf_cv_pct': round(isf_cv, 1),
            'isf_range': round(isf_range, 1),
            'most_sensitive_hour': int(peak_hour),
            'most_resistant_hour': int(trough_hour),
            'dawn_phenomenon_detected': dawn_phenomenon,
            'dawn_ratio': round(dawn_ratio, 2) if dawn_ratio else None,
        })

    # Summary
    dawn_count = sum(1 for r in results['per_patient']
                     if r.get('dawn_phenomenon_detected') is True)
    results['dawn_phenomenon_count'] = dawn_count
    results['mean_isf_cv'] = round(np.mean(
        [r['isf_cv_pct'] for r in results['per_patient']]), 1)
    return results


# ─── EXP-1290: Cross-Patient Therapy Benchmarking ──────────────────
def exp_1290_cross_patient_benchmark(patients, detail=False):
    """Benchmark therapy metrics across all patients to establish norms.

    Creates percentile rankings for each therapy dimension,
    identifying which patients are outliers and in which domains.
    """
    results = {'name': 'EXP-1290: Cross-patient therapy benchmarking',
               'n_patients': len(patients), 'per_patient': []}

    # Compute all metrics for each patient
    patient_metrics = []
    for p in patients:
        sd = get_supply_demand(p)
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        net = sd['net']
        supply = sd['supply']
        demand = sd['demand']
        pk = p['pk']
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)

        valid = ~np.isnan(glucose)
        g = glucose[valid]

        basal_ratio = pk[:, 2] * 2.0
        br = basal_ratio[valid]

        metrics = {
            'patient': p['name'],
            'tir': float(np.mean((g >= 70) & (g <= 180)) * 100),
            'tbr': float(np.mean(g < 70) * 100),
            'tar': float(np.mean(g > 180) * 100),
            'mean_bg': float(np.mean(g)),
            'cv': float(np.std(g) / (np.mean(g) + 1e-6) * 100),
            'gmi': round(3.31 + 0.02392 * float(np.mean(g)), 1),  # GMI formula
            'mean_net': float(np.mean(net[valid])),
            'sd_ratio': float(np.mean(supply[valid]) / (np.mean(demand[valid]) + 1e-6)),
            'pct_loop_suspended': float((br < 0.1).mean() * 100),
            'pct_loop_high': float((br > 1.5).mean() * 100),
            'pct_loop_nominal': float(((br >= 0.9) & (br <= 1.1)).mean() * 100),
            'daily_bolus_u': float(np.sum(bolus) / (n / STEPS_PER_DAY)),
            'daily_carbs_g': float(np.sum(carbs) / (n / STEPS_PER_DAY)),
            'n_days': n / STEPS_PER_DAY,
        }
        patient_metrics.append(metrics)

    # Compute percentiles for each metric
    metric_keys = ['tir', 'tbr', 'tar', 'mean_bg', 'cv', 'mean_net',
                   'pct_loop_suspended', 'pct_loop_nominal',
                   'daily_bolus_u', 'daily_carbs_g']

    for pm in patient_metrics:
        percentiles = {}
        for k in metric_keys:
            values = sorted([m[k] for m in patient_metrics])
            rank = values.index(pm[k])
            pct = round(rank / (len(values) - 1) * 100, 0) if len(values) > 1 else 50
            # For TBR and TAR, lower is better → invert
            if k in ['tbr', 'tar', 'mean_bg', 'cv', 'pct_loop_suspended']:
                pct = 100 - pct
            percentiles[k] = int(pct)
        pm['percentiles'] = percentiles

        # Identify strengths and weaknesses
        strengths = [k for k, v in percentiles.items() if v >= 75]
        weaknesses = [k for k, v in percentiles.items() if v <= 25]
        pm['strengths'] = strengths
        pm['weaknesses'] = weaknesses

        # Composite therapy score (weighted average of percentiles)
        weights = {'tir': 3, 'tbr': 2, 'tar': 2, 'cv': 1,
                   'pct_loop_nominal': 1, 'pct_loop_suspended': 1}
        weighted_sum = sum(percentiles.get(k, 50) * w for k, w in weights.items())
        total_weight = sum(weights.values())
        pm['composite_score'] = round(weighted_sum / total_weight, 1)

        # Round numeric values
        for k in ['tir', 'tbr', 'tar', 'mean_bg', 'cv', 'mean_net', 'sd_ratio',
                  'pct_loop_suspended', 'pct_loop_high', 'pct_loop_nominal',
                  'daily_bolus_u', 'daily_carbs_g', 'n_days']:
            pm[k] = round(pm[k], 1)

    # Sort by composite score
    patient_metrics.sort(key=lambda x: x['composite_score'], reverse=True)
    results['per_patient'] = patient_metrics

    # Normative ranges
    norms = {}
    for k in metric_keys:
        values = [m[k] for m in patient_metrics]
        norms[k] = {
            'mean': round(np.mean(values), 1),
            'std': round(np.std(values), 1),
            'p25': round(np.percentile(values, 25), 1),
            'p50': round(np.percentile(values, 50), 1),
            'p75': round(np.percentile(values, 75), 1),
        }
    results['normative_ranges'] = norms
    results['mean_composite_score'] = round(
        np.mean([m['composite_score'] for m in patient_metrics]), 1)

    return results


# ─── Main Runner ────────────────────────────────────────────────────
EXPERIMENTS = {
    1281: ('Time-block basal adequacy', exp_1281_timeblock_basal),
    1282: ('Per-meal CR scoring', exp_1282_meal_cr_scoring),
    1283: ('ISF effective estimation', exp_1283_isf_estimation),
    1284: ('AID loop compensation', exp_1284_loop_compensation),
    1285: ('Multi-day therapy tracking', exp_1285_multiday_tracking),
    1286: ('Prediction error as therapy signal', exp_1286_prediction_error_signal),
    1287: ('Settings recommendations', exp_1287_settings_recommendations),
    1288: ('DIA adequacy assessment', exp_1288_dia_adequacy),
    1289: ('Temporal ISF profiling', exp_1289_temporal_isf),
    1290: ('Cross-patient benchmarking', exp_1290_cross_patient_benchmark),
}


def main():
    parser = argparse.ArgumentParser(description='EXP-1281-1290: Therapy Detection')
    parser.add_argument('--exp', type=int, help='Run single experiment')
    parser.add_argument('--detail', action='store_true', help='Include detailed per-event data')
    parser.add_argument('--save', action='store_true', help='Save results to JSON')
    parser.add_argument('--max-patients', type=int, default=11)
    args = parser.parse_args()

    print(f"Loading patients (max={args.max_patients})...")
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    exps_to_run = [args.exp] if args.exp else sorted(EXPERIMENTS.keys())

    all_results = {}
    for eid in exps_to_run:
        name, func = EXPERIMENTS[eid]
        print(f"\n{'='*60}")
        print(f"EXP-{eid}: {name}")
        print(f"{'='*60}")
        t0 = time.time()
        try:
            result = func(patients, detail=args.detail)
            elapsed = time.time() - t0
            result['elapsed_sec'] = round(elapsed, 1)
            all_results[eid] = result

            # Print summary
            print(f"  Completed in {elapsed:.1f}s")
            for k, v in result.items():
                if k not in ('per_patient', 'elapsed_sec', 'name',
                             'normative_ranges', 'block_summary'):
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

    # Print final summary
    print(f"\n{'='*60}")
    print("THERAPY DETECTION SUMMARY")
    print(f"{'='*60}")
    for eid, result in all_results.items():
        name = EXPERIMENTS[eid][0]
        if 'error' in result:
            print(f"  EXP-{eid} {name}: FAILED - {result['error']}")
        else:
            # Extract key metric
            key_metrics = {
                1281: f"mean_score={result.get('mean_overall_score', '?')}",
                1282: f"mean_cr={result.get('mean_cr_score', '?')}",
                1283: f"isf_ratio={result.get('mean_isf_ratio', '?')}",
                1284: f"aggressiveness={result.get('mean_aggressiveness', '?')}%",
                1285: f"trend={result.get('trend_distribution', '?')}",
                1286: f"large_errors={result.get('mean_pct_large_errors', '?')}%",
                1287: f"mean_recs={result.get('mean_recommendations', '?')}",
                1288: f"mean_dia={result.get('mean_suggested_dia', '?')}h",
                1289: f"dawn={result.get('dawn_phenomenon_count', '?')}/{result.get('n_patients', '?')}",
                1290: f"composite={result.get('mean_composite_score', '?')}",
            }
            print(f"  EXP-{eid} {name}: {key_metrics.get(eid, 'done')}")

    return all_results


if __name__ == '__main__':
    main()
