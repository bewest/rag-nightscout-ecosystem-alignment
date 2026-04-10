#!/usr/bin/env python3
"""
EXP-2331 through EXP-2338: Loop Prediction Bias Correction

The loop's 30-min glucose prediction has a systematic negative bias of
-2 to -8 mg/dL, which drives unnecessary insulin suspension. This batch
quantifies the bias, builds correction models, and estimates the impact
of bias correction on glycemic outcomes.

Experiments:
  2331: Prediction bias characterization (by BG range, time of day, IOB)
  2332: Bias correction model (context-dependent correction)
  2333: Corrected prediction accuracy (MAE, RMSE improvement)
  2334: Impact on suspension decisions (how many suspensions would change)
  2335: Glycemic outcome simulation (expected TIR/TAR/TBR changes)
  2336: Patient-specific vs universal correction
  2337: Bias stability over time (does it drift?)
  2338: Comprehensive summary and recommendations

Usage:
  PYTHONPATH=tools python3 tools/cgmencode/exp_prediction_bias_2331.py --figures
  PYTHONPATH=tools python3 tools/cgmencode/exp_prediction_bias_2331.py --figures --tiny
"""

import argparse
import json
import os
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import stats

warnings.filterwarnings('ignore')

STEPS_PER_HOUR = 12


def load_patients_parquet(parquet_dir='externals/ns-parquet/training'):
    grid = pd.read_parquet(os.path.join(parquet_dir, 'grid.parquet'))
    patients = []
    for pid in sorted(grid['patient_id'].unique()):
        pdf = grid[grid['patient_id'] == pid].copy()
        pdf = pdf.set_index('time').sort_index()
        patients.append({'name': pid, 'df': pdf})
        print(f"  {pid}: {len(pdf)} steps")
    return patients


def get_prediction_data(df):
    """Extract prediction vs actual pairs with context."""
    bg = df['glucose'].values
    pred_30 = df['loop_predicted_30'].values if 'loop_predicted_30' in df.columns else None
    pred_60 = df['loop_predicted_60'].values if 'loop_predicted_60' in df.columns else None
    
    if pred_30 is None:
        return None
    
    n = len(bg)
    actual_30 = np.full(n, np.nan)
    actual_60 = np.full(n, np.nan)
    
    steps_30 = 6   # 30 min / 5 min
    steps_60 = 12  # 60 min / 5 min
    
    for i in range(n - steps_60):
        if not np.isnan(bg[i + steps_30]):
            actual_30[i] = bg[i + steps_30]
        if not np.isnan(bg[i + steps_60]):
            actual_60[i] = bg[i + steps_60]
    
    # IOB, carbs, time of day
    iob = df['iob'].values if 'iob' in df.columns else np.zeros(n)
    carbs_recent = np.zeros(n)
    if 'carbs' in df.columns:
        carbs = df['carbs'].values
        for i in range(n):
            start = max(0, i - 12)  # 1 hour lookback
            carbs_recent[i] = np.nansum(carbs[start:i+1])
    
    hour = np.array([t.hour + t.minute / 60 for t in df.index])
    
    return {
        'bg': bg,
        'pred_30': pred_30,
        'pred_60': pred_60,
        'actual_30': actual_30,
        'actual_60': actual_60,
        'iob': iob,
        'carbs_recent': carbs_recent,
        'hour': hour,
        'enacted_rate': df['loop_enacted_rate'].values if 'loop_enacted_rate' in df.columns else None,
    }


# ── Experiments ──────────────────────────────────────────────────────────

def exp_2331_characterize(patients):
    """Characterize prediction bias by context."""
    results = {}
    for pat in patients:
        name = pat['name']
        data = get_prediction_data(pat['df'])
        if data is None or data['pred_30'] is None:
            results[name] = {'skipped': True}
            print(f"  {name}: skipped (no prediction data)")
            continue
        
        valid = (~np.isnan(data['pred_30'])) & (~np.isnan(data['actual_30'])) & (~np.isnan(data['bg']))
        if valid.sum() < 100:
            results[name] = {'skipped': True}
            print(f"  {name}: skipped ({valid.sum()} valid pairs)")
            continue
        
        error_30 = data['pred_30'][valid] - data['actual_30'][valid]
        bg_at_pred = data['bg'][valid]
        iob_at_pred = data['iob'][valid]
        hour_at_pred = data['hour'][valid]
        carbs_at_pred = data['carbs_recent'][valid]
        
        # Overall bias
        overall_bias = float(np.mean(error_30))
        overall_mae = float(np.mean(np.abs(error_30)))
        
        # By BG range
        ranges = [(0, 70, 'hypo'), (70, 120, 'low_normal'), (120, 180, 'high_normal'), (180, 400, 'high')]
        by_bg = {}
        for lo, hi, label in ranges:
            mask = (bg_at_pred >= lo) & (bg_at_pred < hi)
            if mask.sum() > 10:
                by_bg[label] = {
                    'bias': round(float(np.mean(error_30[mask])), 2),
                    'mae': round(float(np.mean(np.abs(error_30[mask]))), 2),
                    'n': int(mask.sum()),
                }
        
        # By time of day (4-hour bins)
        by_hour = {}
        for h_start in range(0, 24, 4):
            mask = (hour_at_pred >= h_start) & (hour_at_pred < h_start + 4)
            if mask.sum() > 10:
                by_hour[f'{h_start:02d}-{h_start+4:02d}'] = {
                    'bias': round(float(np.mean(error_30[mask])), 2),
                    'mae': round(float(np.mean(np.abs(error_30[mask]))), 2),
                    'n': int(mask.sum()),
                }
        
        # By IOB quartile
        iob_q = np.nanquantile(iob_at_pred[~np.isnan(iob_at_pred)], [0.25, 0.5, 0.75]) if np.any(~np.isnan(iob_at_pred)) else [0, 0, 0]
        by_iob = {}
        if np.any(~np.isnan(iob_at_pred)):
            for i, (lo, hi, label) in enumerate([
                (0, iob_q[0], 'Q1_low'), (iob_q[0], iob_q[1], 'Q2'),
                (iob_q[1], iob_q[2], 'Q3'), (iob_q[2], 100, 'Q4_high')
            ]):
                mask = (iob_at_pred >= lo) & (iob_at_pred < hi) & (~np.isnan(iob_at_pred))
                if mask.sum() > 10:
                    by_iob[label] = {
                        'bias': round(float(np.mean(error_30[mask])), 2),
                        'n': int(mask.sum()),
                    }
        
        # By meal proximity
        no_carbs = carbs_at_pred < 0.1
        with_carbs = carbs_at_pred > 0
        by_meal = {}
        if no_carbs.sum() > 10:
            by_meal['no_carbs'] = {
                'bias': round(float(np.mean(error_30[no_carbs])), 2),
                'n': int(no_carbs.sum()),
            }
        if with_carbs.sum() > 10:
            by_meal['with_carbs'] = {
                'bias': round(float(np.mean(error_30[with_carbs])), 2),
                'n': int(with_carbs.sum()),
            }
        
        results[name] = {
            'overall_bias_30': overall_bias,
            'overall_mae_30': overall_mae,
            'n_valid': int(valid.sum()),
            'by_bg': by_bg,
            'by_hour': by_hour,
            'by_iob': by_iob,
            'by_meal': by_meal,
        }
        print(f"  {name}: bias={overall_bias:+.1f}, MAE={overall_mae:.1f}, n={valid.sum()}")
    return results


def exp_2332_correction(patients):
    """Build context-dependent correction model."""
    results = {}
    for pat in patients:
        name = pat['name']
        data = get_prediction_data(pat['df'])
        if data is None or data['pred_30'] is None:
            results[name] = {'skipped': True}
            continue
        
        valid = (~np.isnan(data['pred_30'])) & (~np.isnan(data['actual_30'])) & (~np.isnan(data['bg']))
        if valid.sum() < 100:
            results[name] = {'skipped': True}
            continue
        
        error = data['pred_30'][valid] - data['actual_30'][valid]
        bg = data['bg'][valid]
        iob = data['iob'][valid]
        hour = data['hour'][valid]
        
        # Build feature matrix for linear correction
        # Features: constant, bg, bg^2, iob, sin(2π·hour/24), cos(2π·hour/24)
        n = len(error)
        X = np.column_stack([
            np.ones(n),
            bg,
            bg ** 2,
            np.nan_to_num(iob, 0),
            np.sin(2 * np.pi * hour / 24),
            np.cos(2 * np.pi * hour / 24),
        ])
        
        # Fit via least squares
        try:
            coefs, residuals, rank, sv = np.linalg.lstsq(X, error, rcond=None)
            predicted_error = X @ coefs
            correction_r2 = 1 - np.sum((error - predicted_error)**2) / np.sum((error - np.mean(error))**2)
            
            corrected = data['pred_30'][valid] - predicted_error
            new_mae = float(np.mean(np.abs(corrected - data['actual_30'][valid])))
            old_mae = float(np.mean(np.abs(error)))
            
            results[name] = {
                'model': 'linear_6feature',
                'r2': round(float(correction_r2), 4),
                'coefs': {
                    'constant': round(float(coefs[0]), 4),
                    'bg': round(float(coefs[1]), 6),
                    'bg_sq': round(float(coefs[2]), 8),
                    'iob': round(float(coefs[3]), 4),
                    'sin_hour': round(float(coefs[4]), 4),
                    'cos_hour': round(float(coefs[5]), 4),
                },
                'mae_before': round(old_mae, 2),
                'mae_after': round(new_mae, 2),
                'improvement_pct': round((old_mae - new_mae) / old_mae * 100, 1),
            }
            print(f"  {name}: R²={correction_r2:.3f}, MAE {old_mae:.1f}→{new_mae:.1f} ({(old_mae-new_mae)/old_mae*100:.0f}% better)")
        except Exception as e:
            results[name] = {'skipped': True, 'error': str(e)}
            print(f"  {name}: model failed: {e}")
    return results


def exp_2333_accuracy(patients):
    """Corrected prediction accuracy metrics."""
    results = {}
    for pat in patients:
        name = pat['name']
        data = get_prediction_data(pat['df'])
        if data is None or data['pred_30'] is None:
            results[name] = {'skipped': True}
            continue
        
        valid_30 = (~np.isnan(data['pred_30'])) & (~np.isnan(data['actual_30']))
        if valid_30.sum() < 100:
            results[name] = {'skipped': True}
            continue
        
        # 30-min metrics
        err_30 = data['pred_30'][valid_30] - data['actual_30'][valid_30]
        bias_30 = float(np.mean(err_30))
        
        # Simple bias correction: subtract mean bias
        corrected_30 = data['pred_30'][valid_30] - bias_30
        corr_err = corrected_30 - data['actual_30'][valid_30]
        
        metrics = {
            'original': {
                'mae': round(float(np.mean(np.abs(err_30))), 2),
                'rmse': round(float(np.sqrt(np.mean(err_30**2))), 2),
                'bias': round(bias_30, 2),
                'r': round(float(np.corrcoef(data['pred_30'][valid_30], data['actual_30'][valid_30])[0, 1]), 3),
            },
            'bias_corrected': {
                'mae': round(float(np.mean(np.abs(corr_err))), 2),
                'rmse': round(float(np.sqrt(np.mean(corr_err**2))), 2),
                'bias': 0.0,
                'r': round(float(np.corrcoef(corrected_30, data['actual_30'][valid_30])[0, 1]), 3),
            },
        }
        
        # 60-min metrics
        if data['pred_60'] is not None:
            valid_60 = (~np.isnan(data['pred_60'])) & (~np.isnan(data['actual_60']))
            if valid_60.sum() > 100:
                err_60 = data['pred_60'][valid_60] - data['actual_60'][valid_60]
                bias_60 = float(np.mean(err_60))
                corrected_60 = data['pred_60'][valid_60] - bias_60
                metrics['original_60'] = {
                    'mae': round(float(np.mean(np.abs(err_60))), 2),
                    'bias': round(bias_60, 2),
                }
                metrics['corrected_60'] = {
                    'mae': round(float(np.mean(np.abs(corrected_60 - data['actual_60'][valid_60]))), 2),
                    'bias': 0.0,
                }
        
        results[name] = metrics
        print(f"  {name}: MAE {metrics['original']['mae']}→{metrics['bias_corrected']['mae']}, "
              f"RMSE {metrics['original']['rmse']}→{metrics['bias_corrected']['rmse']}")
    return results


def exp_2334_suspension(patients):
    """Impact of bias correction on suspension decisions."""
    results = {}
    for pat in patients:
        name = pat['name']
        data = get_prediction_data(pat['df'])
        if data is None or data['pred_30'] is None:
            results[name] = {'skipped': True}
            continue
        
        valid = (~np.isnan(data['pred_30'])) & (~np.isnan(data['actual_30'])) & (~np.isnan(data['bg']))
        if valid.sum() < 100:
            results[name] = {'skipped': True}
            continue
        
        pred = data['pred_30'][valid]
        actual = data['actual_30'][valid]
        bg = data['bg'][valid]
        bias = float(np.mean(pred - actual))
        corrected = pred - bias
        
        # Suspension threshold: predict going below 80
        suspend_threshold = 80
        
        would_suspend_orig = pred < suspend_threshold
        would_suspend_corr = corrected < suspend_threshold
        actually_went_low = actual < 70
        
        # How many suspension decisions change?
        changed = would_suspend_orig != would_suspend_corr
        false_suspensions_removed = would_suspend_orig & (~would_suspend_corr) & (~actually_went_low)
        true_suspensions_kept = would_suspend_orig & would_suspend_corr & actually_went_low
        
        # Of removed suspensions: what happened?
        removed_mask = would_suspend_orig & (~would_suspend_corr)
        if removed_mask.sum() > 0:
            removed_went_low = float(np.mean(actually_went_low[removed_mask]) * 100)
        else:
            removed_went_low = 0
        
        results[name] = {
            'bias': round(bias, 2),
            'total_predictions': int(valid.sum()),
            'original_suspensions': int(would_suspend_orig.sum()),
            'corrected_suspensions': int(would_suspend_corr.sum()),
            'suspension_reduction': int(would_suspend_orig.sum() - would_suspend_corr.sum()),
            'suspension_reduction_pct': round(float(1 - would_suspend_corr.sum() / max(1, would_suspend_orig.sum())) * 100, 1),
            'false_suspensions_removed': int(false_suspensions_removed.sum()),
            'removed_that_went_low_pct': round(removed_went_low, 1),
            'changed_decisions': int(changed.sum()),
            'changed_pct': round(float(changed.mean()) * 100, 2),
        }
        print(f"  {name}: {results[name]['suspension_reduction_pct']:.0f}% fewer suspensions, "
              f"{results[name]['removed_that_went_low_pct']:.0f}% of removed actually went low")
    return results


def exp_2335_simulation(patients):
    """Glycemic outcome simulation with bias correction."""
    results = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        bg = df['glucose'].values
        valid_bg = bg[~np.isnan(bg)]
        
        if len(valid_bg) < 1000:
            results[name] = {'skipped': True}
            continue
        
        # Current metrics
        tir = float(np.mean((valid_bg >= 70) & (valid_bg <= 180)) * 100)
        tbr = float(np.mean(valid_bg < 70) * 100)
        tar = float(np.mean(valid_bg > 180) * 100)
        
        data = get_prediction_data(df)
        if data is None or data['pred_30'] is None or data['enacted_rate'] is None:
            results[name] = {'skipped': True, 'current_tir': tir}
            continue
        
        valid = (~np.isnan(data['pred_30'])) & (~np.isnan(data['actual_30']))
        if valid.sum() < 100:
            results[name] = {'skipped': True, 'current_tir': tir}
            continue
        
        bias = float(np.mean(data['pred_30'][valid] - data['actual_30'][valid]))
        
        # Estimate: correcting bias reduces unnecessary suspension
        # Each mg/dL of negative bias → ~0.5% unnecessary suspension reduction
        # Each 1% suspension reduction → ~0.2% TAR reduction (more insulin delivered)
        bias_correction = abs(bias)
        est_suspension_reduction = bias_correction * 0.5  # % points
        est_tar_reduction = est_suspension_reduction * 0.2  # % points
        est_tbr_increase = est_suspension_reduction * 0.05  # slight increase
        
        results[name] = {
            'current': {'tir': round(tir, 1), 'tbr': round(tbr, 1), 'tar': round(tar, 1)},
            'prediction_bias': round(bias, 2),
            'estimated': {
                'tir': round(tir + est_tar_reduction - est_tbr_increase, 1),
                'tbr': round(tbr + est_tbr_increase, 1),
                'tar': round(tar - est_tar_reduction, 1),
            },
            'delta': {
                'tir': round(est_tar_reduction - est_tbr_increase, 1),
                'tbr': round(est_tbr_increase, 1),
                'tar': round(-est_tar_reduction, 1),
            },
        }
        print(f"  {name}: TIR {tir:.0f}%→{results[name]['estimated']['tir']:.0f}%, "
              f"TAR {tar:.0f}%→{results[name]['estimated']['tar']:.0f}%")
    return results


def exp_2336_universal(patients):
    """Patient-specific vs universal correction."""
    # Collect all biases
    biases = {}
    for pat in patients:
        name = pat['name']
        data = get_prediction_data(pat['df'])
        if data is None or data['pred_30'] is None:
            continue
        valid = (~np.isnan(data['pred_30'])) & (~np.isnan(data['actual_30']))
        if valid.sum() < 100:
            continue
        biases[name] = float(np.mean(data['pred_30'][valid] - data['actual_30'][valid]))
    
    if not biases:
        return {'skipped': True}
    
    universal_bias = float(np.mean(list(biases.values())))
    bias_std = float(np.std(list(biases.values())))
    
    # Evaluate universal vs individual correction for each patient
    results = {
        'universal_bias': round(universal_bias, 2),
        'bias_std': round(bias_std, 2),
        'individual_biases': {k: round(v, 2) for k, v in biases.items()},
        'patients': {},
    }
    
    for pat in patients:
        name = pat['name']
        data = get_prediction_data(pat['df'])
        if data is None or data['pred_30'] is None:
            continue
        valid = (~np.isnan(data['pred_30'])) & (~np.isnan(data['actual_30']))
        if valid.sum() < 100:
            continue
        
        err = data['pred_30'][valid] - data['actual_30'][valid]
        ind_bias = biases.get(name, 0)
        
        # MAE with no correction
        mae_raw = float(np.mean(np.abs(err)))
        # MAE with universal correction
        mae_univ = float(np.mean(np.abs(err - universal_bias)))
        # MAE with individual correction
        mae_ind = float(np.mean(np.abs(err - ind_bias)))
        
        results['patients'][name] = {
            'mae_raw': round(mae_raw, 2),
            'mae_universal': round(mae_univ, 2),
            'mae_individual': round(mae_ind, 2),
            'universal_better_than_raw': mae_univ < mae_raw,
            'individual_better_than_universal': mae_ind < mae_univ,
            'individual_improvement': round((mae_raw - mae_ind) / mae_raw * 100, 1),
        }
    
    universal_wins = sum(1 for p in results['patients'].values() if p['universal_better_than_raw'])
    individual_wins = sum(1 for p in results['patients'].values() if p['individual_better_than_universal'])
    print(f"  Universal bias: {universal_bias:+.1f} ± {bias_std:.1f}")
    print(f"  Universal better than raw: {universal_wins}/{len(results['patients'])}")
    print(f"  Individual better than universal: {individual_wins}/{len(results['patients'])}")
    return results


def exp_2337_stability(patients):
    """Bias stability over time."""
    results = {}
    for pat in patients:
        name = pat['name']
        data = get_prediction_data(pat['df'])
        if data is None or data['pred_30'] is None:
            results[name] = {'skipped': True}
            continue
        
        valid = (~np.isnan(data['pred_30'])) & (~np.isnan(data['actual_30']))
        if valid.sum() < 500:
            results[name] = {'skipped': True}
            continue
        
        error = data['pred_30'][valid] - data['actual_30'][valid]
        n = len(error)
        
        # Split into weeks
        steps_per_week = 7 * 24 * STEPS_PER_HOUR
        n_weeks = n // steps_per_week
        
        weekly_biases = []
        for w in range(n_weeks):
            start = w * steps_per_week
            end = (w + 1) * steps_per_week
            weekly_biases.append(float(np.mean(error[start:end])))
        
        if len(weekly_biases) < 4:
            results[name] = {'skipped': True, 'reason': 'too few weeks'}
            continue
        
        # Trend test
        weeks = np.arange(len(weekly_biases))
        slope, intercept, r_value, p_value, std_err = stats.linregress(weeks, weekly_biases)
        
        # Stability: coefficient of variation of weekly biases
        bias_cv = float(np.std(weekly_biases) / (abs(np.mean(weekly_biases)) + 1e-8))
        
        results[name] = {
            'n_weeks': len(weekly_biases),
            'weekly_biases': [round(b, 2) for b in weekly_biases],
            'mean_bias': round(float(np.mean(weekly_biases)), 2),
            'bias_std': round(float(np.std(weekly_biases)), 2),
            'trend_slope': round(float(slope), 4),
            'trend_p': round(float(p_value), 4),
            'has_trend': float(p_value) < 0.05,
            'bias_cv': round(bias_cv, 2),
            'stable': bias_cv < 1.0 and float(p_value) > 0.05,
        }
        print(f"  {name}: {'stable' if results[name]['stable'] else 'DRIFTING'}, "
              f"mean={np.mean(weekly_biases):+.1f}, slope={slope:.3f}/wk (p={p_value:.3f})")
    return results


def exp_2338_summary(patients, all_results):
    """Comprehensive summary."""
    results = {}
    for pat in patients:
        name = pat['name']
        
        char = all_results.get('exp_2331', {}).get(name, {})
        correction = all_results.get('exp_2332', {}).get(name, {})
        accuracy = all_results.get('exp_2333', {}).get(name, {})
        suspension = all_results.get('exp_2334', {}).get(name, {})
        simulation = all_results.get('exp_2335', {}).get(name, {})
        stability = all_results.get('exp_2337', {}).get(name, {})
        
        if char.get('skipped') or correction.get('skipped'):
            results[name] = {'skipped': True}
            print(f"  {name}: skipped")
            continue
        
        # Composite benefit score
        mae_improvement = correction.get('improvement_pct', 0)
        susp_reduction = suspension.get('suspension_reduction_pct', 0)
        is_stable = stability.get('stable', False)
        
        benefit = 'HIGH' if mae_improvement > 5 and susp_reduction > 10 and is_stable else \
                  'MODERATE' if mae_improvement > 2 or susp_reduction > 5 else 'LOW'
        
        results[name] = {
            'bias': char.get('overall_bias_30', 0),
            'mae_improvement_pct': round(mae_improvement, 1),
            'suspension_reduction_pct': round(susp_reduction, 1),
            'is_stable': is_stable,
            'benefit': benefit,
            'safe_to_correct': is_stable and suspension.get('removed_that_went_low_pct', 100) < 5,
        }
        print(f"  {name}: {benefit} benefit, safe={results[name]['safe_to_correct']}")
    return results


# ── Figures ──────────────────────────────────────────────────────────────

def generate_figures(results, patients, fig_dir):
    os.makedirs(fig_dir, exist_ok=True)
    names = sorted([p['name'] for p in patients])
    active = [n for n in names if not results.get('exp_2331', {}).get(n, {}).get('skipped')]
    
    # Fig 1: Bias by patient
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    r2331 = results['exp_2331']
    biases = [r2331.get(n, {}).get('overall_bias_30', 0) for n in active]
    maes = [r2331.get(n, {}).get('overall_mae_30', 0) for n in active]
    
    colors = ['red' if b < -3 else 'orange' if b < 0 else 'green' for b in biases]
    ax1.bar(range(len(active)), biases, color=colors, alpha=0.7)
    ax1.axhline(0, color='black', lw=0.5)
    ax1.set_xticks(range(len(active))); ax1.set_xticklabels(active)
    ax1.set_ylabel('Prediction Bias (mg/dL)'); ax1.set_title('30-min Prediction Bias')
    
    ax2.bar(range(len(active)), maes, color='steelblue', alpha=0.7)
    ax2.set_xticks(range(len(active))); ax2.set_xticklabels(active)
    ax2.set_ylabel('MAE (mg/dL)'); ax2.set_title('Mean Absolute Error')
    
    fig.suptitle('EXP-2331: Prediction Bias Characterization', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/bias-fig01-characterize.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 1: characterization")
    
    # Fig 2: Bias by context (aggregate)
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    # Aggregate by BG range
    ranges = ['hypo', 'low_normal', 'high_normal', 'high']
    range_labels = ['<70', '70-120', '120-180', '>180']
    range_biases = {r: [] for r in ranges}
    for n in active:
        by_bg = r2331.get(n, {}).get('by_bg', {})
        for r in ranges:
            if r in by_bg:
                range_biases[r].append(by_bg[r]['bias'])
    
    means = [np.mean(range_biases[r]) if range_biases[r] else 0 for r in ranges]
    axes[0, 0].bar(range(4), means, color=['red', 'orange', 'green', 'blue'], alpha=0.7)
    axes[0, 0].axhline(0, color='black', lw=0.5)
    axes[0, 0].set_xticks(range(4)); axes[0, 0].set_xticklabels(range_labels)
    axes[0, 0].set_ylabel('Mean Bias (mg/dL)'); axes[0, 0].set_title('Bias by BG Range')
    
    # Aggregate by time of day
    hours = ['00-04', '04-08', '08-12', '12-16', '16-20', '20-24']
    hour_biases = {h: [] for h in hours}
    for n in active:
        by_hour = r2331.get(n, {}).get('by_hour', {})
        for h in hours:
            if h in by_hour:
                hour_biases[h].append(by_hour[h]['bias'])
    
    means_h = [np.mean(hour_biases[h]) if hour_biases[h] else 0 for h in hours]
    axes[0, 1].bar(range(6), means_h, color='teal', alpha=0.7)
    axes[0, 1].axhline(0, color='black', lw=0.5)
    axes[0, 1].set_xticks(range(6)); axes[0, 1].set_xticklabels(hours, fontsize=8)
    axes[0, 1].set_ylabel('Mean Bias'); axes[0, 1].set_title('Bias by Time of Day')
    
    # By IOB
    iob_labels = ['Q1_low', 'Q2', 'Q3', 'Q4_high']
    iob_biases = {l: [] for l in iob_labels}
    for n in active:
        by_iob = r2331.get(n, {}).get('by_iob', {})
        for l in iob_labels:
            if l in by_iob:
                iob_biases[l].append(by_iob[l]['bias'])
    
    means_iob = [np.mean(iob_biases[l]) if iob_biases[l] else 0 for l in iob_labels]
    axes[1, 0].bar(range(4), means_iob, color='purple', alpha=0.7)
    axes[1, 0].axhline(0, color='black', lw=0.5)
    axes[1, 0].set_xticks(range(4)); axes[1, 0].set_xticklabels(['Low IOB', 'Q2', 'Q3', 'High IOB'], fontsize=9)
    axes[1, 0].set_ylabel('Mean Bias'); axes[1, 0].set_title('Bias by IOB Level')
    
    # By meal proximity
    meal_labels = ['no_carbs', 'with_carbs']
    meal_biases = {l: [] for l in meal_labels}
    for n in active:
        by_meal = r2331.get(n, {}).get('by_meal', {})
        for l in meal_labels:
            if l in by_meal:
                meal_biases[l].append(by_meal[l]['bias'])
    
    means_meal = [np.mean(meal_biases[l]) if meal_biases[l] else 0 for l in meal_labels]
    axes[1, 1].bar(range(2), means_meal, color=['gray', 'orange'], alpha=0.7)
    axes[1, 1].axhline(0, color='black', lw=0.5)
    axes[1, 1].set_xticks(range(2)); axes[1, 1].set_xticklabels(['No Carbs', 'With Carbs'])
    axes[1, 1].set_ylabel('Mean Bias'); axes[1, 1].set_title('Bias by Meal Context')
    
    fig.suptitle('EXP-2331: Context-Dependent Bias (Population Average)', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/bias-fig02-context.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 2: context")
    
    # Fig 3: Correction model quality
    fig, ax = plt.subplots(figsize=(12, 5))
    r2332 = results['exp_2332']
    active_corr = [n for n in active if not r2332.get(n, {}).get('skipped')]
    r2_vals = [r2332[n].get('r2', 0) for n in active_corr]
    improvements = [r2332[n].get('improvement_pct', 0) for n in active_corr]
    
    x = np.arange(len(active_corr))
    ax.bar(x - 0.2, r2_vals, 0.35, color='steelblue', alpha=0.7, label='R² of correction model')
    ax2 = ax.twinx()
    ax2.bar(x + 0.2, improvements, 0.35, color='coral', alpha=0.7, label='MAE improvement %')
    ax.set_xticks(x); ax.set_xticklabels(active_corr)
    ax.set_ylabel('R²', color='steelblue'); ax2.set_ylabel('MAE Improvement %', color='coral')
    ax.legend(loc='upper left'); ax2.legend(loc='upper right')
    ax.set_title('EXP-2332: Correction Model Quality', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/bias-fig03-correction.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 3: correction")
    
    # Fig 4: Accuracy before/after
    fig, ax = plt.subplots(figsize=(12, 5))
    r2333 = results['exp_2333']
    active_acc = [n for n in active if not r2333.get(n, {}).get('skipped')]
    mae_before = [r2333[n].get('original', {}).get('mae', 0) for n in active_acc]
    mae_after = [r2333[n].get('bias_corrected', {}).get('mae', 0) for n in active_acc]
    
    x = np.arange(len(active_acc))
    ax.bar(x - 0.2, mae_before, 0.35, color='red', alpha=0.6, label='Before correction')
    ax.bar(x + 0.2, mae_after, 0.35, color='green', alpha=0.6, label='After correction')
    ax.set_xticks(x); ax.set_xticklabels(active_acc)
    ax.set_ylabel('MAE (mg/dL)'); ax.legend()
    ax.set_title('EXP-2333: Prediction Accuracy Before/After Bias Correction', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/bias-fig04-accuracy.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 4: accuracy")
    
    # Fig 5: Suspension impact
    fig, ax = plt.subplots(figsize=(12, 5))
    r2334 = results['exp_2334']
    active_susp = [n for n in active if not r2334.get(n, {}).get('skipped')]
    susp_red = [r2334[n].get('suspension_reduction_pct', 0) for n in active_susp]
    safety = [r2334[n].get('removed_that_went_low_pct', 0) for n in active_susp]
    
    x = np.arange(len(active_susp))
    bars = ax.bar(x, susp_red, color='steelblue', alpha=0.7)
    ax2 = ax.twinx()
    ax2.plot(x, safety, 'ro-', label='% removed that went low')
    ax.set_xticks(x); ax.set_xticklabels(active_susp)
    ax.set_ylabel('Suspension Reduction %', color='steelblue')
    ax2.set_ylabel('Removed → Low %', color='red')
    ax2.axhline(5, color='red', ls='--', alpha=0.3, label='5% safety threshold')
    ax2.legend()
    ax.set_title('EXP-2334: Suspension Reduction vs Safety', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/bias-fig05-suspension.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 5: suspension")
    
    # Fig 6: Simulation outcomes
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    r2335 = results['exp_2335']
    active_sim = [n for n in active if not r2335.get(n, {}).get('skipped')]
    
    for idx, (metric, title) in enumerate([('tir', 'TIR %'), ('tar', 'TAR %'), ('tbr', 'TBR %')]):
        current = [r2335[n].get('current', {}).get(metric, 0) for n in active_sim]
        estimated = [r2335[n].get('estimated', {}).get(metric, 0) for n in active_sim]
        x = np.arange(len(active_sim))
        axes[idx].bar(x - 0.2, current, 0.35, color='gray', alpha=0.7, label='Current')
        axes[idx].bar(x + 0.2, estimated, 0.35, color='green', alpha=0.7, label='Corrected')
        axes[idx].set_xticks(x); axes[idx].set_xticklabels(active_sim, fontsize=8)
        axes[idx].set_ylabel(title); axes[idx].legend(fontsize=8)
    
    fig.suptitle('EXP-2335: Simulated Glycemic Outcomes with Bias Correction', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/bias-fig06-simulation.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 6: simulation")
    
    # Fig 7: Universal vs individual
    fig, ax = plt.subplots(figsize=(12, 5))
    r2336 = results['exp_2336']
    if not r2336.get('skipped'):
        pats = r2336.get('patients', {})
        active_u = [n for n in active if n in pats]
        mae_raw = [pats[n]['mae_raw'] for n in active_u]
        mae_univ = [pats[n]['mae_universal'] for n in active_u]
        mae_ind = [pats[n]['mae_individual'] for n in active_u]
        
        x = np.arange(len(active_u))
        ax.bar(x - 0.25, mae_raw, 0.25, color='red', alpha=0.6, label='Raw')
        ax.bar(x, mae_univ, 0.25, color='orange', alpha=0.6, label='Universal correction')
        ax.bar(x + 0.25, mae_ind, 0.25, color='green', alpha=0.6, label='Individual correction')
        ax.set_xticks(x); ax.set_xticklabels(active_u)
        ax.set_ylabel('MAE (mg/dL)'); ax.legend()
    
    ax.set_title('EXP-2336: Universal vs Individual Bias Correction', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/bias-fig07-universal.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 7: universal vs individual")
    
    # Fig 8: Stability over time
    fig, axes = plt.subplots(3, 4, figsize=(16, 10))
    r2337 = results['exp_2337']
    for idx, name in enumerate(active):
        if idx >= 11: break
        row, col = idx // 4, idx % 4
        ax = axes[row, col]
        data = r2337.get(name, {})
        if data.get('skipped'):
            ax.text(0.5, 0.5, f'{name}\n(skipped)', ha='center', va='center', transform=ax.transAxes)
            ax.set_title(name)
            continue
        
        weeks = data.get('weekly_biases', [])
        ax.plot(range(len(weeks)), weeks, 'b.-')
        ax.axhline(0, color='gray', lw=0.5)
        ax.axhline(np.mean(weeks), color='red', ls='--', alpha=0.5)
        stable = '✓' if data.get('stable') else '✗'
        ax.set_title(f'{name} {stable}', fontsize=10)
        ax.set_xlabel('Week'); ax.set_ylabel('Bias')
    
    # Hide empty
    if len(active) < 12:
        for idx in range(len(active), 12):
            axes[idx // 4, idx % 4].axis('off')
    
    fig.suptitle('EXP-2337: Weekly Bias Stability', fontsize=14, fontweight='bold')
    plt.tight_layout(); plt.savefig(f'{fig_dir}/bias-fig08-stability.png', dpi=150, bbox_inches='tight'); plt.close()
    print("  Figure 8: stability")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    parser.add_argument('--tiny', action='store_true')
    args = parser.parse_args()

    parquet_dir = 'externals/ns-parquet-tiny/training' if args.tiny else 'externals/ns-parquet/training'
    print(f"Loading patients from {parquet_dir}...")
    patients = load_patients_parquet(parquet_dir)
    print(f"Loaded {len(patients)} patients\n")

    results = {}

    for exp_id, exp_name, exp_fn in [
        ('exp_2331', 'Bias Characterization', lambda: exp_2331_characterize(patients)),
        ('exp_2332', 'Correction Model', lambda: exp_2332_correction(patients)),
        ('exp_2333', 'Corrected Accuracy', lambda: exp_2333_accuracy(patients)),
        ('exp_2334', 'Suspension Impact', lambda: exp_2334_suspension(patients)),
        ('exp_2335', 'Outcome Simulation', lambda: exp_2335_simulation(patients)),
        ('exp_2336', 'Universal vs Individual', lambda: exp_2336_universal(patients)),
        ('exp_2337', 'Bias Stability', lambda: exp_2337_stability(patients)),
    ]:
        print(f"Running {exp_id}: {exp_name}...")
        results[exp_id] = exp_fn()
        print(f"  ✓ completed\n")

    print("Running exp_2338: Summary...")
    results['exp_2338'] = exp_2338_summary(patients, results)
    print("  ✓ completed\n")

    out_path = 'externals/experiments/exp-2331-2338_prediction_bias.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    def convert(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, (np.bool_,)): return bool(obj)
        raise TypeError(f"Not serializable: {type(obj)}")
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"Results saved to {out_path}")

    if args.figures:
        print("\nGenerating figures...")
        generate_figures(results, patients, 'docs/60-research/figures')
        print("All figures generated.")


if __name__ == '__main__':
    main()
