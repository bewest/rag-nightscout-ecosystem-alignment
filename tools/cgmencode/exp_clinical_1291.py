#!/usr/bin/env python3
"""EXP-1291 through EXP-1300: AID-Deconfounded Therapy Assessment.

Builds on EXP-1281-1290 findings:
1. ISF is 2.66x profile due to AID loop amplification — deconfound it
2. 10/11 patients have basal too high — quantify exact reduction needed
3. Settings recommendations need simulation validation

Key innovation: Account for the AID loop's basal adjustments when measuring
correction/meal responses. Total insulin = correction_bolus + integral(basal_deviation).
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
    from sklearn.linear_model import Ridge
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

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288


# ─── Precondition Framework ────────────────────────────────────────
def assess_preconditions(p):
    """Assess data quality preconditions for each analysis type.

    Returns a dict of {analysis_name: {met: bool, reason: str, metrics: dict}}
    describing which analyses are valid for this patient's data.

    Preconditions:
    1. CGM coverage: % of timesteps with valid glucose
    2. Insulin telemetry: % of timesteps with pump data (temp_rate > 0 or bolus > 0)
    3. Therapy fidelity: how closely does delivery match a physiological model?
       Measured by: % time loop is in nominal range (not heavily compensating)
    4. Sufficient volume: minimum days of data
    5. Isolated events: enough correction boluses, fasting periods, meals
    """
    df = p['df']
    pk = p['pk']
    glucose = df['glucose'].values.astype(float)
    bolus = df['bolus'].values
    carbs = df['carbs'].values
    temp_rate = df['temp_rate'].values
    basal_ratio = pk[:, 2] * 2.0
    n = len(glucose)

    # Core data quality metrics
    cgm_coverage = float(np.mean(~np.isnan(glucose)) * 100)
    insulin_telemetry = float(np.mean(
        (temp_rate > 0) | (bolus > 0) | (df['iob'].values > 0)) * 100)
    n_days = n / STEPS_PER_DAY

    # Therapy fidelity: how often is basal within 50% of scheduled?
    valid_ratio = basal_ratio[~np.isnan(glucose)]
    pct_nominal = float(((valid_ratio >= 0.5) & (valid_ratio <= 1.5)).mean() * 100) if len(valid_ratio) > 0 else 0
    pct_suspended = float((valid_ratio < 0.1).mean() * 100) if len(valid_ratio) > 0 else 0

    # Count isolated events
    n_corrections = 0
    n_fasting_hours = 0
    n_meals = 0

    # Corrections: bolus > 0.3 with no carbs ±30min
    for i in range(n):
        if bolus[i] >= 0.3:
            cw = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[cw]) < 2:
                n_corrections += 1

    # Fasting hours: no bolus/carbs for ±2h
    fasting_steps = 0
    for i in range(0, n, STEPS_PER_HOUR):  # sample hourly to save time
        ws = max(0, i - STEPS_PER_HOUR * 2)
        we = min(n, i + STEPS_PER_HOUR * 2)
        if np.sum(bolus[ws:we]) < 0.1 and np.sum(carbs[ws:we]) < 1:
            fasting_steps += STEPS_PER_HOUR
    n_fasting_hours = fasting_steps / STEPS_PER_HOUR

    # Meals: carbs >= 5
    last_meal = -STEPS_PER_HOUR * 3
    for i in range(n):
        if carbs[i] >= 5 and (i - last_meal) >= STEPS_PER_HOUR * 2:
            n_meals += 1
            last_meal = i

    # Bolused meals: carbs >= 5 AND bolus within ±15min
    n_bolused_meals = 0
    last_meal = -STEPS_PER_HOUR * 3
    for i in range(n):
        if carbs[i] >= 5 and (i - last_meal) >= STEPS_PER_HOUR * 2:
            bw = slice(max(0, i - 3), min(n, i + 3))
            if np.sum(bolus[bw]) > 0.1:
                n_bolused_meals += 1
            last_meal = i

    metrics = {
        'cgm_coverage_pct': round(cgm_coverage, 1),
        'insulin_telemetry_pct': round(insulin_telemetry, 1),
        'n_days': round(n_days, 1),
        'pct_nominal_basal': round(pct_nominal, 1),
        'pct_suspended': round(pct_suspended, 1),
        'n_corrections': n_corrections,
        'n_fasting_hours': round(n_fasting_hours, 1),
        'n_meals': n_meals,
        'n_bolused_meals': n_bolused_meals,
    }

    # Physics fidelity: how well does the glucose conservation law hold?
    # ΔBG/Δt ≈ net_flux (supply - demand). Residual = ΔBG/Δt - net_flux.
    # High fidelity = physics model explains observed glucose changes.
    # Low fidelity = unmodeled events (missed meals, exercise, compression).
    sd = compute_supply_demand(df, pk)
    net_flux = sd['net']
    # Observed glucose rate of change (mg/dL per 5-min step)
    dg = np.diff(glucose)
    dg = np.append(dg, 0)
    valid_both = ~np.isnan(glucose) & ~np.isnan(dg) & (np.abs(dg) < 50)  # exclude spikes
    if valid_both.sum() > 100:
        residual = dg[valid_both] - net_flux[valid_both]
        fidelity_rmse = float(np.sqrt(np.mean(residual**2)))
        # Correlation between predicted and observed rate of change
        corr = float(np.corrcoef(net_flux[valid_both], dg[valid_both])[0, 1])
        # R² of conservation law
        ss_res = np.sum(residual**2)
        ss_tot = np.sum((dg[valid_both] - np.mean(dg[valid_both]))**2)
        fidelity_r2 = float(1 - ss_res / (ss_tot + 1e-10))
        # Fraction of timesteps where conservation holds within ±5 mg/dL
        pct_conserved = float(np.mean(np.abs(residual) < 5) * 100)
    else:
        fidelity_rmse = 999.0
        corr = 0.0
        fidelity_r2 = -1.0
        pct_conserved = 0.0

    fidelity_corr = corr

    metrics['fidelity_rmse'] = round(fidelity_rmse, 2)
    metrics['fidelity_corr'] = round(corr, 3)
    metrics['fidelity_r2'] = round(fidelity_r2, 3)
    metrics['pct_conserved'] = round(pct_conserved, 1)

    # Quality classification from EXP-492 thresholds
    # RMSE < 3 = good, 3-10 = marginal, >10 = poor
    if fidelity_rmse < 3:
        rmse_quality = 'good'
    elif fidelity_rmse < 10:
        rmse_quality = 'marginal'
    else:
        rmse_quality = 'poor'
    metrics['rmse_quality'] = rmse_quality

    # Residual quality score (EXP-492 formula)
    residual_score = max(0, min(100, 100 - (fidelity_rmse - 2) * 12))
    metrics['residual_score'] = round(residual_score, 1)

    # Conservation integral (EXP-454): |∫net_flux dt| over full dataset
    # < 15 mg·h = adequate, 15-40 = marginal, >40 = poor
    if valid_both.sum() > 100:
        conservation_integral = float(np.abs(np.sum(net_flux[valid_both])) * 5 / 60)  # mg·h
    else:
        conservation_integral = 999.0
    metrics['conservation_integral_mgh'] = round(conservation_integral / n_days, 2)  # per day

    # Assess each analysis type
    preconditions = {}

    # Basal assessment: needs fasting periods + CGM + insulin telemetry + fidelity
    preconditions['basal_assessment'] = {
        'met': (cgm_coverage > 70 and insulin_telemetry > 50
                and n_fasting_hours > 24 and n_days > 7
                and fidelity_r2 > -0.5),
        'reason': _precond_reason(cgm_coverage > 70, 'CGM coverage >70%',
                                   insulin_telemetry > 50, 'insulin telemetry >50%',
                                   n_fasting_hours > 24, 'fasting hours >24',
                                   n_days > 7, 'data >7 days',
                                   fidelity_r2 > -0.5, f'fidelity R²>-0.5 (have {fidelity_r2:.2f})'),
    }

    # ISF estimation: needs isolated corrections + good fidelity during corrections
    preconditions['isf_estimation'] = {
        'met': (cgm_coverage > 70 and insulin_telemetry > 50
                and n_corrections >= 5 and fidelity_corr > 0),
        'reason': _precond_reason(cgm_coverage > 70, 'CGM coverage >70%',
                                   insulin_telemetry > 50, 'insulin telemetry >50%',
                                   n_corrections >= 5, f'corrections ≥5 (have {n_corrections})',
                                   fidelity_corr > 0, f'fidelity corr>0 (have {corr:.2f})'),
    }

    # CR assessment: needs bolused meals + fidelity
    preconditions['cr_assessment'] = {
        'met': (cgm_coverage > 70 and n_bolused_meals >= 10
                and fidelity_r2 > -1.0),
        'reason': _precond_reason(cgm_coverage > 70, 'CGM coverage >70%',
                                   n_bolused_meals >= 10, f'bolused meals ≥10 (have {n_bolused_meals})',
                                   fidelity_r2 > -1.0, f'fidelity R²>-1 (have {fidelity_r2:.2f})'),
    }

    # Therapy fidelity itself: is the physics model working for this patient?
    # This is a meta-precondition — if fidelity is very low, all supply/demand
    # based analyses are unreliable.
    preconditions['physics_model_valid'] = {
        'met': (fidelity_r2 > -0.5 and pct_conserved > 30 and corr > 0),
        'reason': _precond_reason(
            fidelity_r2 > -0.5, f'conservation R²>-0.5 (have {fidelity_r2:.2f})',
            pct_conserved > 30, f'conserved >30% of time (have {pct_conserved:.0f}%)',
            corr > 0, f'flux-dBG correlation >0 (have {corr:.2f})'),
    }

    # Multi-day tracking: needs sufficient duration + some fidelity
    preconditions['multiday_tracking'] = {
        'met': n_days >= 14 and cgm_coverage > 60 and fidelity_r2 > -1.0,
        'reason': _precond_reason(n_days >= 14, f'data ≥14 days (have {n_days:.0f})',
                                   cgm_coverage > 60, 'CGM coverage >60%',
                                   fidelity_r2 > -1.0, f'fidelity R²>-1 (have {fidelity_r2:.2f})'),
    }

    # Correction validation: needs corrections from high BG + fidelity
    high_corrections = 0
    for i in range(n):
        if bolus[i] >= 0.3 and glucose[i] > 150 and not np.isnan(glucose[i]):
            cw = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[cw]) < 2:
                high_corrections += 1
    preconditions['correction_validation'] = {
        'met': (high_corrections >= 5 and fidelity_corr > 0),
        'reason': _precond_reason(high_corrections >= 5,
                                   f'high-BG corrections ≥5 (have {high_corrections})',
                                   fidelity_corr > 0, f'fidelity corr>0 (have {corr:.2f})'),
    }

    return {'preconditions': preconditions, 'metrics': metrics}


def _precond_reason(*args):
    """Build reason string from (condition, label) pairs."""
    pairs = [(args[i], args[i+1]) for i in range(0, len(args), 2)]
    failed = [label for cond, label in pairs if not cond]
    if not failed:
        return 'all preconditions met'
    return 'FAILED: ' + ', '.join(failed)


def get_time_blocks(n_steps):
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


def check_precondition(p, preconditions, required_precond):
    """Check if a patient meets a required precondition.
    Returns (met: bool, reason: str or None).
    """
    if not preconditions or p['name'] not in preconditions:
        return True, None
    pc = preconditions[p['name']]['preconditions']
    entry = pc.get(required_precond, {})
    if not entry.get('met', True):
        return False, entry.get('reason', 'precondition not met')
    return True, None


def get_fidelity_metrics(p, preconditions):
    """Get fidelity metrics for a patient from precondition assessment."""
    if preconditions and p['name'] in preconditions:
        m = preconditions[p['name']]['metrics']
        return {
            'fidelity_r2': m.get('fidelity_r2'),
            'fidelity_corr': m.get('fidelity_corr'),
            'pct_conserved': m.get('pct_conserved'),
        }
    return {}


def get_scheduled_basal_rate(p):
    """Estimate scheduled basal rate from temp_rate and basal_ratio.

    PK channel 2 (basal_ratio) = actual/scheduled. When basal_ratio ≈ 1,
    temp_rate ≈ scheduled_rate. Use these moments to estimate scheduled rate.
    """
    pk = p['pk']
    df = p['df']
    basal_ratio = pk[:, 2] * 2.0
    temp_rate = df['temp_rate'].values

    # Near-nominal moments: ratio between 0.95 and 1.05
    nominal_mask = (basal_ratio >= 0.95) & (basal_ratio <= 1.05) & (temp_rate > 0)
    if nominal_mask.sum() > 10:
        return float(np.median(temp_rate[nominal_mask]))
    else:
        # Fallback: use median of all non-zero rates
        nonzero = temp_rate[temp_rate > 0]
        if len(nonzero) > 0:
            return float(np.median(nonzero))
        return 1.0  # default


# ─── EXP-1291: AID-Deconfounded ISF ────────────────────────────────
def exp_1291_deconfounded_isf(patients, detail=False, preconditions=None):
    """Measure true ISF by accounting for total insulin during corrections.

    Key insight: When a correction bolus is given, the AID loop also adjusts
    basal delivery. True ISF = ΔBG / (correction_bolus + basal_deviation_integral).

    Preconditions: isf_estimation, physics_model_valid
    """
    results = {'name': 'EXP-1291: AID-deconfounded ISF',
               'n_patients': len(patients), 'per_patient': [],
               'precondition_filter': 'isf_estimation'}

    DIA_STEPS = STEPS_PER_HOUR * 5  # 5h DIA

    for p in patients:
        # Check preconditions
        if preconditions and p['name'] in preconditions:
            pc = preconditions[p['name']]['preconditions']
            if not pc.get('isf_estimation', {}).get('met', True):
                results['per_patient'].append({
                    'patient': p['name'], 'n_corrections': 0,
                    'skipped': True,
                    'reason': pc['isf_estimation']['reason']})
                continue
            if not pc.get('physics_model_valid', {}).get('met', True):
                results['per_patient'].append({
                    'patient': p['name'], 'n_corrections': 0,
                    'skipped': True,
                    'reason': pc['physics_model_valid']['reason']})
                continue

        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        temp_rate = df['temp_rate'].values
        basal_ratio = pk[:, 2] * 2.0
        isf_profile = pk[:, 7] * 200.0
        n = len(glucose)

        scheduled_rate = get_scheduled_basal_rate(p)

        corrections = []
        for i in range(n):
            if bolus[i] < 0.3:
                continue
            carb_window = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[carb_window]) > 2:
                continue
            if i + DIA_STEPS >= n:
                continue
            future_bolus = bolus[i + 1:i + DIA_STEPS]
            if np.sum(future_bolus) > 0.5:
                continue

            pre_bg = glucose[max(0, i - 3):i + 1]
            pre_bg = pre_bg[~np.isnan(pre_bg)]
            if len(pre_bg) == 0:
                continue
            start_bg = np.mean(pre_bg)

            future_bg = glucose[i:i + DIA_STEPS]
            valid_future = ~np.isnan(future_bg)
            if valid_future.sum() < DIA_STEPS * 0.5:
                continue
            nadir_idx = np.nanargmin(future_bg)
            nadir_bg = future_bg[nadir_idx]
            delta_bg = start_bg - nadir_bg
            if delta_bg < 10:
                continue

            # Compute total insulin during DIA window
            bolus_amount = float(bolus[i])

            # Basal deviation integral: (actual_rate - scheduled_rate) * dt
            # Each step is 5 minutes = 5/60 hours
            window_rates = temp_rate[i:i + DIA_STEPS]
            # Sum of (actual - scheduled) * 5/60 hours = total extra/less basal insulin
            basal_deviation = float(np.sum(window_rates - scheduled_rate) * (5.0 / 60.0))

            total_insulin = bolus_amount + basal_deviation
            total_insulin_raw = bolus_amount  # without deconfounding

            if total_insulin > 0.1:
                isf_deconfounded = delta_bg / total_insulin
            else:
                isf_deconfounded = None  # net negative insulin? skip

            isf_raw = delta_bg / bolus_amount
            isf_from_profile = float(np.mean(isf_profile[i:i + DIA_STEPS]))

            corr = {
                'index': int(i),
                'bolus': round(bolus_amount, 2),
                'basal_deviation_u': round(basal_deviation, 3),
                'total_insulin': round(total_insulin, 3) if total_insulin else None,
                'delta_bg': round(delta_bg, 1),
                'isf_raw': round(isf_raw, 1),
                'isf_deconfounded': round(isf_deconfounded, 1) if isf_deconfounded else None,
                'isf_profile': round(isf_from_profile, 1),
            }
            corrections.append(corr)

        if corrections:
            raw_ratios = [c['isf_raw'] / (c['isf_profile'] + 1e-6) for c in corrections]
            deconf_ratios = [c['isf_deconfounded'] / (c['isf_profile'] + 1e-6)
                           for c in corrections if c['isf_deconfounded'] is not None]
            deconf_isfs = [c['isf_deconfounded'] for c in corrections
                          if c['isf_deconfounded'] is not None]
            raw_isfs = [c['isf_raw'] for c in corrections]
            basal_devs = [c['basal_deviation_u'] for c in corrections]

            results['per_patient'].append({
                'patient': p['name'],
                'scheduled_rate': round(scheduled_rate, 3),
                'n_corrections': len(corrections),
                'n_deconfounded': len(deconf_ratios),
                'mean_isf_raw': round(np.mean(raw_isfs), 1),
                'mean_isf_deconfounded': round(np.mean(deconf_isfs), 1) if deconf_isfs else None,
                'mean_isf_profile': round(np.mean([c['isf_profile'] for c in corrections]), 1),
                'raw_ratio': round(np.mean(raw_ratios), 2),
                'deconfounded_ratio': round(np.mean(deconf_ratios), 2) if deconf_ratios else None,
                'mean_basal_deviation_u': round(np.mean(basal_devs), 3),
                'deconfound_improvement': round(
                    np.mean(raw_ratios) - np.mean(deconf_ratios), 2) if deconf_ratios else None,
                'corrections': corrections[:5] if detail else [],
            })
        else:
            results['per_patient'].append({
                'patient': p['name'], 'n_corrections': 0,
                'note': 'No isolated corrections found'})

    with_data = [r for r in results['per_patient'] if r['n_corrections'] > 0]
    results['n_patients_with_data'] = len(with_data)
    if with_data:
        results['mean_raw_ratio'] = round(np.mean([r['raw_ratio'] for r in with_data]), 2)
        deconf = [r['deconfounded_ratio'] for r in with_data if r.get('deconfounded_ratio')]
        results['mean_deconfounded_ratio'] = round(np.mean(deconf), 2) if deconf else None
        results['deconfound_delta'] = round(
            results['mean_raw_ratio'] - (results['mean_deconfounded_ratio'] or 0), 2)
    return results


# ─── EXP-1292: Quantified Basal Recommendations ───────────────────
def exp_1292_basal_quantification(patients, detail=False, preconditions=None):
    """Compute specific basal rate changes needed per time block.

    Uses overnight/fasting net flux to estimate the basal rate that
    would achieve net flux ≈ 0 (supply = demand balance).
    """
    results = {'name': 'EXP-1292: Quantified basal recommendations',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        net = sd['net']
        demand = sd['demand']
        supply = sd['supply']
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        temp_rate = df['temp_rate'].values
        pk = p['pk']
        basal_ratio = pk[:, 2] * 2.0
        n = len(glucose)
        blocks = get_time_blocks(n)

        scheduled_rate = get_scheduled_basal_rate(p)

        # Fasting filter
        fasting = np.ones(n, dtype=bool)
        for i in range(n):
            ws = max(0, i - STEPS_PER_HOUR * 2)
            we = min(n, i + STEPS_PER_HOUR * 2)
            if np.any(bolus[ws:we] > 0) or np.any(carbs[ws:we] > 0):
                fasting[i] = False
        valid = ~np.isnan(glucose) & fasting

        block_recommendations = {}
        for b in range(6):
            mask = valid & (blocks == b)
            if mask.sum() < STEPS_PER_HOUR:  # need at least 1h
                continue

            block_net = net[mask]
            block_demand = demand[mask]
            block_supply = supply[mask]
            block_bg = glucose[mask]
            block_rates = temp_rate[mask]

            mean_net = float(np.mean(block_net))
            mean_demand = float(np.mean(block_demand))
            mean_supply = float(np.mean(block_supply))
            mean_actual_rate = float(np.mean(block_rates))
            tir = float(np.mean((block_bg >= 70) & (block_bg <= 180)) * 100)
            tbr = float(np.mean(block_bg < 70) * 100)

            # Target: net flux ≈ 0 during fasting
            # net = supply - demand, and demand ∝ basal_rate
            # If net < 0 (demand > supply), basal is too high
            # Reduction needed: proportional to net / demand
            if mean_demand > 0.01:
                # Fractional change needed: if net = -3 and demand = 10,
                # we need to reduce demand by 3/10 = 30%
                optimal_change_frac = -mean_net / (mean_demand + 1e-6)
                # Clamp to reasonable range
                optimal_change_frac = max(-0.5, min(0.5, optimal_change_frac))
                optimal_rate = mean_actual_rate * (1 + optimal_change_frac)
            else:
                optimal_change_frac = 0
                optimal_rate = mean_actual_rate

            # Safety check: if TBR > 5%, always recommend decrease
            if tbr > 5 and optimal_change_frac >= 0:
                optimal_change_frac = -0.1 * (tbr / 5)  # scale with TBR severity
                optimal_rate = mean_actual_rate * (1 + optimal_change_frac)

            block_recommendations[BLOCK_NAMES[b]] = {
                'mean_net': round(mean_net, 2),
                'mean_demand': round(mean_demand, 3),
                'mean_supply': round(mean_supply, 3),
                'mean_actual_rate': round(mean_actual_rate, 3),
                'tir': round(tir, 1),
                'tbr': round(tbr, 1),
                'optimal_change_pct': round(optimal_change_frac * 100, 1),
                'suggested_rate': round(optimal_rate, 3),
                'confidence': ('high' if mask.sum() > STEPS_PER_HOUR * 10 else
                              'medium' if mask.sum() > STEPS_PER_HOUR * 3 else 'low'),
            }

        # Overall recommendation
        all_changes = [v['optimal_change_pct'] for v in block_recommendations.values()]
        mean_change = np.mean(all_changes) if all_changes else 0

        results['per_patient'].append({
            'patient': p['name'],
            'scheduled_rate': round(scheduled_rate, 3),
            'block_recommendations': block_recommendations,
            'mean_change_pct': round(mean_change, 1),
            'overall_direction': ('decrease' if mean_change < -5 else
                                  'increase' if mean_change > 5 else 'maintain'),
        })

    results['mean_change_pct'] = round(np.mean(
        [r['mean_change_pct'] for r in results['per_patient']]), 1)
    results['direction_distribution'] = {
        d: sum(1 for r in results['per_patient'] if r['overall_direction'] == d)
        for d in ['decrease', 'increase', 'maintain']
    }
    return results


# ─── EXP-1293: Supply/Demand Balance Simulation ───────────────────
def exp_1293_balance_simulation(patients, detail=False, preconditions=None):
    """Simulate TIR impact of basal adjustments using supply/demand model.

    For each patient, apply hypothetical basal changes (-30%, -20%, -10%,
    +10%, +20%) and estimate new glucose trajectory from net flux changes.
    """
    results = {'name': 'EXP-1293: Balance simulation',
               'n_patients': len(patients), 'per_patient': []}

    ADJUSTMENTS = [-0.3, -0.2, -0.1, 0.0, 0.1, 0.2]

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        net = sd['net']
        demand = sd['demand']
        supply = sd['supply']
        n = len(glucose)
        valid = ~np.isnan(glucose)

        # Current metrics
        g = glucose[valid]
        current_tir = float(np.mean((g >= 70) & (g <= 180)) * 100)
        current_tbr = float(np.mean(g < 70) * 100)
        current_tar = float(np.mean(g > 180) * 100)

        sim_results = {}
        for adj in ADJUSTMENTS:
            # Simulate: if demand changed by adj fraction, what happens to glucose?
            # New net = supply - demand * (1 + adj)
            new_demand = demand * (1 + adj)
            new_net = supply - new_demand
            delta_net = new_net - net  # change in net flux

            # Glucose change: cumulative effect of net flux change
            # Each step's delta_net adds to glucose. But glucose has feedback
            # (higher glucose → more insulin effect), so we dampen.
            # Simple model: new_glucose = glucose + cumsum(delta_net) * damping
            damping = 0.3  # accounts for feedback effects
            cum_delta = np.cumsum(delta_net) * damping

            # Cap cumulative effect (physiology limits)
            cum_delta = np.clip(cum_delta, -100, 100)

            simulated_glucose = glucose + cum_delta
            sim_valid = valid & ~np.isnan(simulated_glucose)
            sim_g = simulated_glucose[sim_valid]

            if len(sim_g) > 100:
                sim_tir = float(np.mean((sim_g >= 70) & (sim_g <= 180)) * 100)
                sim_tbr = float(np.mean(sim_g < 70) * 100)
                sim_tar = float(np.mean(sim_g > 180) * 100)
            else:
                sim_tir = sim_tbr = sim_tar = 0

            label = f"{adj*100:+.0f}%"
            sim_results[label] = {
                'tir': round(sim_tir, 1),
                'tbr': round(sim_tbr, 1),
                'tar': round(sim_tar, 1),
                'delta_tir': round(sim_tir - current_tir, 1),
            }

        # Find optimal adjustment
        best_adj = max(sim_results.items(),
                      key=lambda x: x[1]['tir'] - max(0, x[1]['tbr'] - 4) * 10)

        results['per_patient'].append({
            'patient': p['name'],
            'current': {'tir': round(current_tir, 1), 'tbr': round(current_tbr, 1),
                       'tar': round(current_tar, 1)},
            'simulations': sim_results,
            'optimal_adjustment': best_adj[0],
            'optimal_tir': best_adj[1]['tir'],
        })

    results['mean_optimal_adjustment'] = np.mean(
        [float(r['optimal_adjustment'].replace('%', '').replace('+', ''))
         for r in results['per_patient']])
    return results


# ─── EXP-1294: Per-Time-Block ISF Estimation ──────────────────────
def exp_1294_timeblock_isf(patients, detail=False, preconditions=None):
    """Estimate deconfounded ISF per time-of-day block.

    Detects dawn phenomenon, afternoon sensitivity shifts, etc.
    Uses actual glucose response to corrections, not profile ISF.
    """
    results = {'name': 'EXP-1294: Per-time-block ISF estimation',
               'n_patients': len(patients), 'per_patient': []}

    DIA_STEPS = STEPS_PER_HOUR * 5

    for p in patients:
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        temp_rate = df['temp_rate'].values
        isf_profile = pk[:, 7] * 200.0
        n = len(glucose)
        blocks = get_time_blocks(n)
        scheduled_rate = get_scheduled_basal_rate(p)

        block_isfs = defaultdict(list)

        for i in range(n):
            if bolus[i] < 0.3:
                continue
            carb_window = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[carb_window]) > 2:
                continue
            if i + DIA_STEPS >= n:
                continue
            if np.sum(bolus[i + 1:i + DIA_STEPS]) > 0.5:
                continue

            pre_bg = glucose[max(0, i - 3):i + 1]
            pre_bg = pre_bg[~np.isnan(pre_bg)]
            if len(pre_bg) == 0:
                continue
            start_bg = np.mean(pre_bg)

            future_bg = glucose[i:i + DIA_STEPS]
            if np.sum(~np.isnan(future_bg)) < DIA_STEPS * 0.5:
                continue
            nadir_bg = float(np.nanmin(future_bg))
            delta_bg = start_bg - nadir_bg
            if delta_bg < 10:
                continue

            # Total insulin (deconfounded)
            bolus_amount = float(bolus[i])
            basal_dev = float(np.sum(temp_rate[i:i + DIA_STEPS] - scheduled_rate) * (5/60))
            total_insulin = bolus_amount + basal_dev

            if total_insulin > 0.1:
                isf = delta_bg / total_insulin
                block = blocks[i]
                block_isfs[block].append(isf)

        block_summary = {}
        for b in range(6):
            isfs = block_isfs.get(b, [])
            if len(isfs) >= 2:
                block_summary[BLOCK_NAMES[b]] = {
                    'n': len(isfs),
                    'mean_isf': round(np.mean(isfs), 1),
                    'median_isf': round(np.median(isfs), 1),
                    'std_isf': round(np.std(isfs), 1),
                    'mean_profile_isf': round(float(np.mean(
                        isf_profile[(blocks == b) & ~np.isnan(glucose)])), 1),
                }

        # Dawn phenomenon: compare morning ISF to overnight ISF
        overnight = block_isfs.get(0, [])
        morning = block_isfs.get(1, [])
        dawn_detected = False
        dawn_ratio = None
        if len(overnight) >= 2 and len(morning) >= 2:
            dawn_ratio = np.mean(morning) / (np.mean(overnight) + 1e-6)
            # If morning ISF < overnight ISF by >20%, dawn phenomenon
            dawn_detected = dawn_ratio < 0.8

        results['per_patient'].append({
            'patient': p['name'],
            'n_total_corrections': sum(len(v) for v in block_isfs.values()),
            'block_isf': block_summary,
            'dawn_phenomenon': dawn_detected,
            'dawn_ratio': round(dawn_ratio, 2) if dawn_ratio else None,
        })

    results['n_dawn_detected'] = sum(
        1 for r in results['per_patient'] if r['dawn_phenomenon'])
    return results


# ─── EXP-1295: Meal Bolus Timing Analysis ─────────────────────────
def exp_1295_bolus_timing(patients, detail=False, preconditions=None):
    """Analyze timing of meal boluses relative to carb absorption.

    Late bolusing → higher peaks, longer recovery. Pre-bolusing → better control.
    Measures the gap between carb entry and bolus delivery.
    """
    results = {'name': 'EXP-1295: Meal bolus timing analysis',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        pk = p['pk']
        carb_rate = pk[:, 3] * 0.5  # denormalize carb absorption rate
        n = len(glucose)

        # Detect meal events
        meal_events = []
        last_meal = -STEPS_PER_HOUR * 2
        for i in range(n):
            if carbs[i] >= 5 and (i - last_meal) >= STEPS_PER_HOUR * 2:
                meal_events.append(i)
                last_meal = i

        timing_data = []
        for mi in meal_events:
            if mi + STEPS_PER_HOUR * 4 >= n or mi < STEPS_PER_HOUR:
                continue

            # Find nearest bolus within ±30 minutes
            search_start = max(0, mi - 6)
            search_end = min(n, mi + 6)
            bolus_window = bolus[search_start:search_end]
            if np.sum(bolus_window) < 0.1:
                continue  # no bolus near meal

            # Find bolus relative to carb entry
            bolus_indices = np.where(bolus_window > 0.1)[0]
            if len(bolus_indices) == 0:
                continue
            # Earliest bolus relative to carb entry
            first_bolus_offset = int(bolus_indices[0]) - (mi - search_start)
            timing_min = first_bolus_offset * 5  # positive = after carbs, negative = pre-bolus

            # Post-meal response
            post_glucose = glucose[mi:mi + STEPS_PER_HOUR * 4]
            if np.sum(np.isnan(post_glucose)) > len(post_glucose) * 0.3:
                continue
            pre_bg = glucose[max(0, mi - 3):mi]
            pre_bg = pre_bg[~np.isnan(pre_bg)]
            if len(pre_bg) == 0:
                continue
            baseline = np.mean(pre_bg)
            peak_bg = float(np.nanmax(post_glucose))
            excursion = peak_bg - baseline

            timing_data.append({
                'timing_min': timing_min,
                'excursion': round(excursion, 1),
                'peak_bg': round(peak_bg, 1),
                'carbs': float(carbs[mi]),
                'bolus': float(np.sum(bolus_window)),
            })

        if timing_data:
            timings = [t['timing_min'] for t in timing_data]
            excursions = [t['excursion'] for t in timing_data]

            # Split by pre-bolus vs post-bolus
            pre_bolus = [t for t in timing_data if t['timing_min'] < -5]
            on_time = [t for t in timing_data if -5 <= t['timing_min'] <= 5]
            late = [t for t in timing_data if t['timing_min'] > 5]

            timing_comparison = {}
            for label, group in [('pre_bolus', pre_bolus), ('on_time', on_time), ('late', late)]:
                if group:
                    timing_comparison[label] = {
                        'n': len(group),
                        'mean_excursion': round(np.mean([t['excursion'] for t in group]), 1),
                        'mean_peak': round(np.mean([t['peak_bg'] for t in group]), 1),
                    }

            results['per_patient'].append({
                'patient': p['name'],
                'n_meals': len(timing_data),
                'mean_timing_min': round(np.mean(timings), 1),
                'pct_pre_bolus': round(len(pre_bolus) / len(timing_data) * 100, 1),
                'pct_late': round(len(late) / len(timing_data) * 100, 1),
                'timing_comparison': timing_comparison,
                'timing_excursion_corr': round(float(np.corrcoef(timings, excursions)[0, 1]), 3)
                    if len(timings) > 5 else None,
            })
        else:
            results['per_patient'].append({
                'patient': p['name'], 'n_meals': 0})

    with_data = [r for r in results['per_patient'] if r['n_meals'] > 0]
    if with_data:
        results['mean_timing'] = round(np.mean([r['mean_timing_min'] for r in with_data]), 1)
        results['mean_pct_pre_bolus'] = round(np.mean([r['pct_pre_bolus'] for r in with_data]), 1)
    return results


# ─── EXP-1296: Fasting Glucose Trend Analysis ─────────────────────
def exp_1296_fasting_trends(patients, detail=False, preconditions=None):
    """Analyze overnight fasting glucose trends to detect basal issues.

    Rising overnight = basal too low. Falling overnight = basal too high.
    Measure slope of glucose during 0-6 AM fasting periods.
    """
    results = {'name': 'EXP-1296: Fasting glucose trend analysis',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        n = len(glucose)
        n_days = n // STEPS_PER_DAY

        night_slopes = []
        for d in range(n_days):
            # 0-6 AM = first 72 steps of day
            start = d * STEPS_PER_DAY
            end = start + STEPS_PER_HOUR * 6
            if end > n:
                break

            night_g = glucose[start:end]
            night_bolus = bolus[start:end]
            night_carbs = carbs[start:end]

            # Skip if any bolus/carbs during overnight
            if np.sum(night_bolus) > 0.1 or np.sum(night_carbs) > 1:
                continue
            # Need sufficient data
            valid = ~np.isnan(night_g)
            if valid.sum() < STEPS_PER_HOUR * 3:  # at least 3h
                continue

            # Fit linear slope (mg/dL per hour)
            x = np.arange(len(night_g))[valid] * (5.0 / 60.0)  # hours
            y = night_g[valid]
            if len(x) < 10:
                continue
            slope = float(np.polyfit(x, y, 1)[0])
            night_slopes.append({
                'day': d,
                'slope': round(slope, 2),
                'start_bg': round(float(y[0]), 1),
                'end_bg': round(float(y[-1]), 1),
                'delta': round(float(y[-1] - y[0]), 1),
            })

        if night_slopes:
            slopes = [ns['slope'] for ns in night_slopes]
            results['per_patient'].append({
                'patient': p['name'],
                'n_nights': len(night_slopes),
                'mean_slope': round(np.mean(slopes), 2),
                'median_slope': round(np.median(slopes), 2),
                'std_slope': round(np.std(slopes), 2),
                'pct_rising': round(np.mean(np.array(slopes) > 3) * 100, 1),
                'pct_falling': round(np.mean(np.array(slopes) < -3) * 100, 1),
                'pct_stable': round(np.mean(np.abs(np.array(slopes)) <= 3) * 100, 1),
                'assessment': ('basal_appropriate' if abs(np.median(slopes)) <= 3 else
                              'basal_too_low' if np.median(slopes) > 3 else
                              'basal_too_high'),
                'nights': night_slopes[:5] if detail else [],
            })
        else:
            results['per_patient'].append({
                'patient': p['name'], 'n_nights': 0,
                'note': 'No clean fasting nights found'})

    assessed = [r for r in results['per_patient'] if r['n_nights'] > 0]
    if assessed:
        results['assessment_distribution'] = {
            a: sum(1 for r in assessed if r.get('assessment') == a)
            for a in ['basal_too_low', 'basal_too_high', 'basal_appropriate']
        }
        results['mean_slope'] = round(np.mean([r['mean_slope'] for r in assessed]), 2)
    return results


# ─── EXP-1297: Weekly Therapy Report Card ──────────────────────────
def exp_1297_weekly_report(patients, detail=False, preconditions=None):
    """Generate weekly therapy report cards combining all metrics.

    Each week gets scores for: TIR, lows risk, highs risk, variability,
    basal calibration, meal response quality.
    """
    results = {'name': 'EXP-1297: Weekly therapy report card',
               'n_patients': len(patients), 'per_patient': []}

    STEPS_PER_WEEK = STEPS_PER_DAY * 7

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        net = sd['net']
        supply = sd['supply']
        demand = sd['demand']
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        pk = p['pk']
        basal_ratio = pk[:, 2] * 2.0
        n = len(glucose)
        n_weeks = n // STEPS_PER_WEEK

        weekly_cards = []
        for w in range(n_weeks):
            start = w * STEPS_PER_WEEK
            end = start + STEPS_PER_WEEK
            wg = glucose[start:end]
            valid = ~np.isnan(wg)
            if valid.sum() < STEPS_PER_WEEK * 0.5:
                continue

            g = wg[valid]
            tir = float(np.mean((g >= 70) & (g <= 180)) * 100)
            tbr = float(np.mean(g < 70) * 100)
            tar = float(np.mean(g > 180) * 100)
            cv = float(np.std(g) / (np.mean(g) + 1e-6) * 100)
            mean_bg = float(np.mean(g))

            # Basal calibration score
            br = basal_ratio[start:end][valid]
            pct_nominal = float(((br >= 0.9) & (br <= 1.1)).mean() * 100)
            pct_suspended = float((br < 0.1).mean() * 100)

            # Net balance
            w_net = net[start:end]
            mean_net = float(np.mean(w_net))

            # Composite scores
            tir_score = min(100, tir / 0.7)
            lows_score = max(0, 100 - tbr * 15)
            highs_score = max(0, 100 - tar * 2)
            variability_score = max(0, 100 - (cv - 20) * 3) if cv > 20 else 100
            basal_score = min(100, pct_nominal * 5)  # 20% nominal = 100

            composite = (tir_score * 3 + lows_score * 3 + highs_score * 2 +
                        variability_score * 1 + basal_score * 1) / 10

            card = {
                'week': w + 1,
                'tir': round(tir, 1), 'tbr': round(tbr, 1), 'tar': round(tar, 1),
                'cv': round(cv, 1), 'mean_bg': round(mean_bg, 0),
                'tir_score': round(tir_score, 0),
                'lows_score': round(lows_score, 0),
                'highs_score': round(highs_score, 0),
                'variability_score': round(variability_score, 0),
                'basal_score': round(basal_score, 0),
                'composite': round(composite, 1),
                'pct_nominal': round(pct_nominal, 1),
            }
            weekly_cards.append(card)

        if weekly_cards:
            composites = [c['composite'] for c in weekly_cards]
            # Trend: first half vs second half
            mid = len(composites) // 2
            if mid > 0:
                trend = np.mean(composites[mid:]) - np.mean(composites[:mid])
            else:
                trend = 0

            results['per_patient'].append({
                'patient': p['name'],
                'n_weeks': len(weekly_cards),
                'mean_composite': round(np.mean(composites), 1),
                'best_week': max(weekly_cards, key=lambda c: c['composite']),
                'worst_week': min(weekly_cards, key=lambda c: c['composite']),
                'trend': round(trend, 1),
                'weekly_cards': weekly_cards if detail else
                    [weekly_cards[0], weekly_cards[-1]],
            })

    results['mean_composite'] = round(np.mean(
        [r['mean_composite'] for r in results['per_patient'] if 'mean_composite' in r]), 1)
    return results


# ─── EXP-1298: Correction Factor Validation ───────────────────────
def exp_1298_correction_validation(patients, detail=False, preconditions=None):
    """Validate how well correction boluses achieve target BG.

    Measures the gap between intended correction outcome and actual result.
    A well-calibrated ISF should bring BG to ~100-120 mg/dL from highs.
    """
    results = {'name': 'EXP-1298: Correction factor validation',
               'n_patients': len(patients), 'per_patient': []}

    DIA_STEPS = STEPS_PER_HOUR * 5
    TARGET_BG = 110  # typical correction target

    for p in patients:
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs = df['carbs'].values
        pk = p['pk']
        isf_profile = pk[:, 7] * 200.0
        n = len(glucose)

        corrections = []
        for i in range(n):
            if bolus[i] < 0.3 or glucose[i] < 150:
                continue  # only high corrections
            carb_window = slice(max(0, i - 6), min(n, i + 6))
            if np.sum(carbs[carb_window]) > 2:
                continue
            if i + DIA_STEPS >= n:
                continue
            if np.sum(bolus[i + 1:i + DIA_STEPS]) > 0.5:
                continue

            start_bg = float(glucose[i])
            isf = float(isf_profile[i])
            expected_drop = float(bolus[i]) * isf
            expected_bg = start_bg - expected_drop

            # Actual BG at DIA endpoint
            dia_bg = glucose[i + DIA_STEPS - 6:i + DIA_STEPS + 6]
            dia_bg = dia_bg[~np.isnan(dia_bg)]
            if len(dia_bg) == 0:
                continue
            actual_bg = float(np.mean(dia_bg))

            # How close to target?
            overshoot = expected_bg - actual_bg  # positive = corrected more than expected
            target_error = actual_bg - TARGET_BG  # positive = still above target

            corrections.append({
                'start_bg': round(start_bg, 1),
                'bolus': round(float(bolus[i]), 2),
                'isf': round(isf, 1),
                'expected_bg': round(expected_bg, 1),
                'actual_bg': round(actual_bg, 1),
                'overshoot': round(overshoot, 1),
                'target_error': round(target_error, 1),
                'reached_target': actual_bg <= TARGET_BG + 20,
            })

        if corrections:
            overshoots = [c['overshoot'] for c in corrections]
            target_errors = [c['target_error'] for c in corrections]

            results['per_patient'].append({
                'patient': p['name'],
                'n_corrections': len(corrections),
                'mean_overshoot': round(np.mean(overshoots), 1),
                'mean_target_error': round(np.mean(target_errors), 1),
                'pct_reached_target': round(np.mean(
                    [c['reached_target'] for c in corrections]) * 100, 1),
                'pct_overcorrected': round(np.mean(
                    [c['actual_bg'] < 70 for c in corrections]) * 100, 1),
                'assessment': ('too_aggressive' if np.mean(overshoots) > 20 else
                              'too_conservative' if np.mean(target_errors) > 40 else
                              'well_calibrated'),
                'corrections': corrections[:5] if detail else [],
            })
        else:
            results['per_patient'].append({
                'patient': p['name'], 'n_corrections': 0})

    assessed = [r for r in results['per_patient'] if r['n_corrections'] > 0]
    if assessed:
        results['assessment_distribution'] = {
            a: sum(1 for r in assessed if r.get('assessment') == a)
            for a in ['too_aggressive', 'too_conservative', 'well_calibrated']
        }
    return results


# ─── EXP-1299: Insulin-to-Carb Ratio per Meal Size ────────────────
def exp_1299_icr_by_meal_size(patients, detail=False, preconditions=None):
    """Analyze how well ICR works for different meal sizes.

    Small meals may need different CR than large meals. Detects
    non-linear carb response patterns.
    """
    results = {'name': 'EXP-1299: ICR by meal size',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        bolus = df['bolus'].values
        carbs_arr = df['carbs'].values
        n = len(glucose)

        meals = []
        last_meal = -STEPS_PER_HOUR * 3
        for i in range(n):
            if carbs_arr[i] < 5 or (i - last_meal) < STEPS_PER_HOUR * 3:
                continue
            last_meal = i
            if i + STEPS_PER_HOUR * 4 >= n:
                continue

            # Get bolus within ±15 min
            b_start = max(0, i - 3)
            b_end = min(n, i + 3)
            total_bolus = float(np.sum(bolus[b_start:b_end]))
            if total_bolus < 0.1:
                continue

            carb_amount = float(carbs_arr[i])
            actual_cr = carb_amount / total_bolus  # g/U

            # Post-meal metrics
            post_g = glucose[i:i + STEPS_PER_HOUR * 4]
            pre_bg = glucose[max(0, i - 3):i]
            pre_bg = pre_bg[~np.isnan(pre_bg)]
            if len(pre_bg) == 0 or np.sum(np.isnan(post_g)) > len(post_g) * 0.3:
                continue

            baseline = float(np.mean(pre_bg))
            peak = float(np.nanmax(post_g))
            excursion = peak - baseline

            # Categorize meal size
            if carb_amount <= 20:
                size = 'small'
            elif carb_amount <= 40:
                size = 'medium'
            else:
                size = 'large'

            meals.append({
                'carbs': carb_amount,
                'bolus': total_bolus,
                'cr': round(actual_cr, 1),
                'excursion': round(excursion, 1),
                'peak': round(peak, 1),
                'size': size,
            })

        if meals:
            size_analysis = {}
            for size in ['small', 'medium', 'large']:
                group = [m for m in meals if m['size'] == size]
                if len(group) >= 3:
                    size_analysis[size] = {
                        'n': len(group),
                        'mean_cr': round(np.mean([m['cr'] for m in group]), 1),
                        'mean_excursion': round(np.mean([m['excursion'] for m in group]), 1),
                        'mean_carbs': round(np.mean([m['carbs'] for m in group]), 1),
                        'pct_good': round(np.mean(
                            [m['excursion'] < 60 for m in group]) * 100, 1),
                    }

            results['per_patient'].append({
                'patient': p['name'],
                'n_meals': len(meals),
                'size_analysis': size_analysis,
                'mean_cr': round(np.mean([m['cr'] for m in meals]), 1),
                'mean_excursion': round(np.mean([m['excursion'] for m in meals]), 1),
            })
        else:
            results['per_patient'].append({
                'patient': p['name'], 'n_meals': 0})

    return results


# ─── EXP-1300: Integrated Therapy Assessment Score ─────────────────
def exp_1300_integrated_assessment(patients, detail=False, preconditions=None):
    """Compute an integrated therapy assessment combining all dimensions.

    Produces a single "therapy calibration score" per patient from:
    - Basal adequacy (fasting trends, loop compensation)
    - ISF accuracy (correction outcomes)
    - CR effectiveness (meal responses)
    - Stability (week-to-week consistency)
    """
    results = {'name': 'EXP-1300: Integrated therapy assessment',
               'n_patients': len(patients), 'per_patient': []}

    for p in patients:
        sd = compute_supply_demand(p['df'], p['pk'])
        df = p['df']
        glucose = df['glucose'].values.astype(float)
        net = sd['net']
        supply = sd['supply']
        demand = sd['demand']
        bolus_arr = df['bolus'].values
        carbs_arr = df['carbs'].values
        pk = p['pk']
        basal_ratio = pk[:, 2] * 2.0
        temp_rate = df['temp_rate'].values
        n = len(glucose)
        valid = ~np.isnan(glucose)
        g = glucose[valid]

        # 1. TIR score (0-100)
        tir = float(np.mean((g >= 70) & (g <= 180)) * 100)
        tbr = float(np.mean(g < 70) * 100)
        tir_score = min(100, tir / 0.7) - max(0, tbr - 1) * 10

        # 2. Basal calibration score (0-100)
        br = basal_ratio[valid]
        pct_nominal = float(((br >= 0.9) & (br <= 1.1)).mean() * 100)
        pct_suspended = float((br < 0.1).mean() * 100)
        basal_score = min(100, pct_nominal * 3) if pct_suspended < 50 else max(0, 50 - pct_suspended)

        # 3. Variability score (0-100)
        cv = float(np.std(g) / (np.mean(g) + 1e-6) * 100)
        var_score = max(0, 100 - max(0, cv - 20) * 3)

        # 4. Net balance score (0-100): closer to 0 is better
        mean_net = float(np.mean(net[valid]))
        balance_score = max(0, 100 - abs(mean_net) * 10)

        # 5. Meal response score
        meal_excursions = []
        for i in range(n):
            if carbs_arr[i] >= 10 and i + STEPS_PER_HOUR * 3 < n:
                post = glucose[i:i + STEPS_PER_HOUR * 3]
                pre = glucose[max(0, i - 3):i]
                pre = pre[~np.isnan(pre)]
                if len(pre) > 0:
                    exc = float(np.nanmax(post)) - float(np.mean(pre))
                    meal_excursions.append(exc)
        if meal_excursions:
            mean_exc = np.mean(meal_excursions)
            meal_score = max(0, 100 - max(0, mean_exc - 30) * 0.8)
        else:
            meal_score = 50  # no meals = neutral

        # Composite
        composite = (tir_score * 3 + basal_score * 2 + var_score * 1 +
                    balance_score * 2 + meal_score * 2) / 10

        # Overall assessment
        if composite >= 70:
            assessment = 'well_calibrated'
        elif composite >= 50:
            assessment = 'needs_tuning'
        elif composite >= 30:
            assessment = 'significantly_miscalibrated'
        else:
            assessment = 'critically_miscalibrated'

        # Identify primary issue
        scores = {'basal': basal_score, 'meals': meal_score,
                  'balance': balance_score, 'tir': tir_score, 'variability': var_score}
        primary_issue = min(scores, key=scores.get)

        results['per_patient'].append({
            'patient': p['name'],
            'composite_score': round(composite, 1),
            'assessment': assessment,
            'primary_issue': primary_issue,
            'scores': {k: round(v, 1) for k, v in scores.items()},
            'metrics': {
                'tir': round(tir, 1), 'tbr': round(tbr, 1), 'cv': round(cv, 1),
                'mean_net': round(mean_net, 2), 'pct_nominal': round(pct_nominal, 1),
                'pct_suspended': round(pct_suspended, 1),
                'mean_excursion': round(np.mean(meal_excursions), 1) if meal_excursions else None,
            },
        })

    # Sort by composite
    results['per_patient'].sort(key=lambda r: r['composite_score'], reverse=True)
    results['mean_composite'] = round(np.mean(
        [r['composite_score'] for r in results['per_patient']]), 1)
    results['assessment_distribution'] = {
        a: sum(1 for r in results['per_patient'] if r['assessment'] == a)
        for a in ['well_calibrated', 'needs_tuning',
                  'significantly_miscalibrated', 'critically_miscalibrated']
    }
    return results


# ─── Main Runner ────────────────────────────────────────────────────
EXPERIMENTS = {
    1291: ('AID-deconfounded ISF', exp_1291_deconfounded_isf),
    1292: ('Quantified basal recommendations', exp_1292_basal_quantification),
    1293: ('Balance simulation', exp_1293_balance_simulation),
    1294: ('Per-time-block ISF', exp_1294_timeblock_isf),
    1295: ('Meal bolus timing', exp_1295_bolus_timing),
    1296: ('Fasting glucose trends', exp_1296_fasting_trends),
    1297: ('Weekly therapy report', exp_1297_weekly_report),
    1298: ('Correction factor validation', exp_1298_correction_validation),
    1299: ('ICR by meal size', exp_1299_icr_by_meal_size),
    1300: ('Integrated therapy assessment', exp_1300_integrated_assessment),
}


def main():
    parser = argparse.ArgumentParser(description='EXP-1291-1300: AID-Deconfounded Therapy')
    parser.add_argument('--exp', type=int, help='Run single experiment')
    parser.add_argument('--detail', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--max-patients', type=int, default=11)
    args = parser.parse_args()

    print(f"Loading patients (max={args.max_patients})...")
    patients = load_patients(PATIENTS_DIR, max_patients=args.max_patients)
    print(f"Loaded {len(patients)} patients")

    # ── Precondition Assessment (always runs first) ──────────────
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
        print(f"  {p['name']}: {met}/{total} preconditions met | "
              f"CGM={m['cgm_coverage_pct']}% insulin={m['insulin_telemetry_pct']}% "
              f"fidelity_R²={m['fidelity_r2']} conserved={m['pct_conserved']}% "
              f"corr={m.get('n_corrections',0)} meals={m.get('n_bolused_meals',0)}")
        for pname, pdata in pc['preconditions'].items():
            if not pdata['met']:
                print(f"    ✗ {pname}: {pdata['reason']}")

    if args.save:
        with open('preconditions.json', 'w') as f:
            json.dump(precond_results, f, indent=2, default=str)
        print(f"\n  Saved: preconditions.json")

    # ── Run Experiments ──────────────────────────────────────────
    exps_to_run = [args.exp] if args.exp else sorted(EXPERIMENTS.keys())

    all_results = {}
    for eid in exps_to_run:
        name, func = EXPERIMENTS[eid]
        print(f"\n{'='*60}")
        print(f"EXP-{eid}: {name}")
        print(f"{'='*60}")
        t0 = time.time()
        try:
            result = func(patients, detail=args.detail,
                         preconditions=precond_results)
            elapsed = time.time() - t0
            result['elapsed_sec'] = round(elapsed, 1)
            all_results[eid] = result

            print(f"  Completed in {elapsed:.1f}s")
            for k, v in result.items():
                if k not in ('per_patient', 'elapsed_sec', 'name',
                             'normative_ranges', 'block_summary', 'weekly_cards'):
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

    print(f"\n{'='*60}")
    print("THERAPY ASSESSMENT SUMMARY")
    print(f"{'='*60}")
    for eid, result in all_results.items():
        name = EXPERIMENTS[eid][0]
        if 'error' in result:
            print(f"  EXP-{eid} {name}: FAILED - {result['error']}")
        else:
            key_metrics = {
                1291: f"raw_ratio={result.get('mean_raw_ratio','?')}, deconf={result.get('mean_deconfounded_ratio','?')}",
                1292: f"mean_change={result.get('mean_change_pct','?')}%, dist={result.get('direction_distribution','?')}",
                1293: f"optimal_adj={result.get('mean_optimal_adjustment','?')}%",
                1294: f"dawn={result.get('n_dawn_detected','?')}/11",
                1295: f"timing={result.get('mean_timing','?')}min, pre-bolus={result.get('mean_pct_pre_bolus','?')}%",
                1296: f"slope={result.get('mean_slope','?')} mg/dL/h, {result.get('assessment_distribution','?')}",
                1297: f"composite={result.get('mean_composite','?')}",
                1298: f"calibration={result.get('assessment_distribution','?')}",
                1299: f"n_patients={len([r for r in result.get('per_patient',[]) if r.get('n_meals',0)>0])}",
                1300: f"composite={result.get('mean_composite','?')}, {result.get('assessment_distribution','?')}",
            }
            print(f"  EXP-{eid} {name}: {key_metrics.get(eid, 'done')}")

    return all_results

    return all_results


if __name__ == '__main__':
    main()
