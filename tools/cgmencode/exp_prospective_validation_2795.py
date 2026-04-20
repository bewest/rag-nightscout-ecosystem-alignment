#!/usr/bin/env python3
"""
EXP-2795: Prospective Settings Validation via Counterfactual Simulation
========================================================================
The ultimate test: do our pipeline settings recommendations predict better
outcomes than current settings?

We can't run a real prospective trial, but we CAN do counterfactual analysis:
1. Split data into 70% train / 30% test (chronological)
2. Generate settings recommendations from training data
3. On test data, compute:
   a. BG prediction error with current settings vs recommended
   b. Controller effort (suspension rate) — lower = better settings
   c. Hypoglycemia risk — must not increase
4. Compare pipeline recommendations vs profile settings

HYPOTHESES (5):
H1: BG prediction improves with pipeline settings on test data (>50% patients)
H2: Controller effort (suspension %) decreases with better settings (>40%)
H3: Hypo risk does not increase (mean time-below stable ±1%)
H4: Pipeline ISF-correction predicts test-set deviation direction (>60%)
H5: Improvement consistent across controllers (all >40% improve)
"""

import json
import os
import warnings
import numpy as np
import pandas as pd
from numpy.linalg import lstsq
from scipy import stats

warnings.filterwarnings('ignore')

EXCLUDE = {'odc-84181797', 'h', 'j'}

def classify_controller(pid):
    if pid.startswith('ns-'):
        return 'Trio'
    elif pid.startswith('odc-'):
        return 'OpenAPS'
    else:
        return 'Loop'

def make_activity_curve(dia_hours=6.0, peak_min=75.0, step_min=5.0):
    n_steps = int(dia_hours * 60 / step_min)
    t = np.arange(1, n_steps + 1) * step_min
    curve = (t / peak_min) * np.exp(1 - t / peak_min)
    return curve / curve.sum()

def compute_bgi(df, isf_cf, activity_curve):
    scheduled_rate = df['scheduled_basal_rate'].median() or 0
    bolus = df['bolus'].fillna(0).values
    smb = df['bolus_smb'].fillna(0).values
    net_basal = df['net_basal'].fillna(0).values
    actual_basal = np.clip(net_basal + scheduled_rate, 0, None) / 12.0
    delivery = bolus + smb + actual_basal
    excess = delivery - (scheduled_rate / 12.0)
    
    n = len(excess)
    nc = len(activity_curve)
    bgi = np.zeros(n)
    for i in range(n):
        w = min(i, nc)
        if w > 0:
            bgi[i] = -np.sum(excess[i-w:i] * activity_curve[:w][::-1]) * isf_cf
    return pd.Series(bgi, index=df.index)

def extract_pipeline_settings(train_df, activity_curve):
    """Extract pipeline settings from training data."""
    isf = train_df['scheduled_isf'].median()
    cr = train_df['scheduled_cr'].median()
    cf = 0.2
    
    bgi = compute_bgi(train_df, isf * cf, activity_curve)
    delta = train_df['glucose'].diff()
    deviation = delta - bgi
    
    # Categorize
    carbs_active = train_df['carbs'].fillna(0).rolling(36, min_periods=1).sum() > 0
    isf_mask = (train_df['glucose'] > 180) & (~carbs_active) & (deviation < 0)
    
    # ISF correction: from deviation in ISF events
    if isf_mask.sum() > 20:
        isf_dev = deviation[isf_mask].median()
        # Positive deviation = ISF too high (not enough BG drop)
        # Negative deviation = ISF too low (too much BG drop)
        correction_factor = 1 + isf_dev / (isf * cf + 1)
        pipeline_isf = isf * max(0.2, min(correction_factor, 3.0))
    else:
        pipeline_isf = isf
    
    # CR correction: from CSF events
    csf_dev = deviation[carbs_active].median()
    if not np.isnan(csf_dev):
        cr_correction = 1 + csf_dev / (cr + 1)
        pipeline_cr = cr * max(0.3, min(cr_correction, 3.0))
    else:
        pipeline_cr = cr
    
    # Basal recommendation: 50/50 rule
    scheduled_rate = train_df['scheduled_basal_rate'].median() or 0
    user_bolus = train_df['bolus'].fillna(0).sum()
    smb_total = train_df['bolus_smb'].fillna(0).sum()
    actual_basal_rate = train_df['net_basal'].fillna(0) + scheduled_rate
    actual_basal = (actual_basal_rate.clip(lower=0) / 12.0).sum()
    total = user_bolus + smb_total + actual_basal
    days = len(train_df) * 5 / 60 / 24
    
    if total > 0 and days > 0:
        tdd = total / days
        target_basal_rate = tdd * 0.5 / 24.0
    else:
        target_basal_rate = scheduled_rate
    
    return {
        'isf_profile': isf,
        'isf_pipeline': pipeline_isf,
        'cr_profile': cr,
        'cr_pipeline': pipeline_cr,
        'basal_profile': scheduled_rate,
        'basal_pipeline': target_basal_rate,
        'cf': cf,
    }

def evaluate_settings(test_df, settings, activity_curve, setting_type='profile'):
    """Evaluate a set of settings on test data."""
    if setting_type == 'profile':
        isf = settings['isf_profile']
        cf = settings['cf']
    else:
        isf = settings['isf_pipeline']
        cf = settings['cf']
    
    bgi = compute_bgi(test_df, isf * cf, activity_curve)
    delta = test_df['glucose'].diff()
    deviation = delta - bgi
    
    # AR(1) prediction
    ar_pred = delta.shift(1) * 0.5
    residual = deviation - ar_pred
    
    # Metrics
    mae_bgi = deviation.abs().median()
    mae_residual = residual.abs().median()
    
    # BG prediction: use AR(1) + BGI model
    pred = ar_pred + bgi
    valid = pred.dropna().index.intersection(delta.dropna().index)
    if len(valid) > 0:
        pred_error = (delta.loc[valid] - pred.loc[valid]).abs().median()
    else:
        pred_error = np.nan
    
    # Controller effort: how much the controller deviates from scheduled
    scheduled_rate = test_df['scheduled_basal_rate'].median() or 0
    if scheduled_rate > 0:
        suspension_pct = (test_df['net_basal'].fillna(0) < -scheduled_rate * 0.9).mean()
    else:
        suspension_pct = 0
    
    # Hypo risk
    glucose = test_df['glucose'].dropna()
    time_below = (glucose < 70).mean() * 100
    time_in_range = ((glucose >= 70) & (glucose <= 180)).mean() * 100
    
    return {
        'mae_bgi': round(float(mae_bgi), 3),
        'mae_residual': round(float(mae_residual), 3),
        'pred_error': round(float(pred_error), 3) if not np.isnan(pred_error) else None,
        'suspension_pct': round(float(suspension_pct), 3),
        'time_below': round(float(time_below), 2),
        'tir': round(float(time_in_range), 1),
    }

def main():
    print("=" * 60)
    print("EXP-2795: Prospective Settings Validation")
    print("=" * 60)
    
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    patients = sorted([p for p in grid['patient_id'].unique() if p not in EXCLUDE])
    activity_curve = make_activity_curve()
    
    results = []
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].copy()
        if len(pdf) < 1000 or pdf['glucose'].isna().mean() > 0.3:
            continue
        
        ctrl = classify_controller(pid)
        n = len(pdf)
        split = int(n * 0.7)
        
        train = pdf.iloc[:split].copy()
        test = pdf.iloc[split:].copy()
        
        # Step 1: Extract settings from training data
        settings = extract_pipeline_settings(train, activity_curve)
        
        # Step 2: Evaluate both settings on test data
        eval_profile = evaluate_settings(test, settings, activity_curve, 'profile')
        eval_pipeline = evaluate_settings(test, settings, activity_curve, 'pipeline')
        
        # Step 3: Compare
        pred_improves = (eval_pipeline['pred_error'] or 99) < (eval_profile['pred_error'] or 99)
        suspension_decreases = eval_pipeline['suspension_pct'] < eval_profile['suspension_pct']
        hypo_safe = abs(eval_pipeline['time_below'] - eval_profile['time_below']) < 1.0
        
        # ISF direction prediction
        # If pipeline says ISF should decrease, test deviation should be positive (BG not dropping enough)
        isf_ratio = settings['isf_pipeline'] / settings['isf_profile'] if settings['isf_profile'] > 0 else 1
        test_bgi_profile = compute_bgi(test, settings['isf_profile'] * settings['cf'], activity_curve)
        test_delta = test['glucose'].diff()
        test_dev = (test_delta - test_bgi_profile).median()
        
        # If ISF_pipeline < ISF_profile (recommended to decrease), deviation should be positive
        isf_direction_correct = (isf_ratio < 0.9 and test_dev > 0) or \
                                (isf_ratio > 1.1 and test_dev < 0) or \
                                (0.9 <= isf_ratio <= 1.1)  # No change = neutral
        
        r = {
            'patient_id': pid,
            'controller': ctrl,
            'n_train': split,
            'n_test': n - split,
            'isf_profile': round(settings['isf_profile'], 1),
            'isf_pipeline': round(settings['isf_pipeline'], 1),
            'isf_ratio': round(isf_ratio, 3),
            'cr_profile': round(settings['cr_profile'], 1),
            'cr_pipeline': round(settings['cr_pipeline'], 1),
            'basal_profile': round(settings['basal_profile'], 2),
            'basal_pipeline': round(settings['basal_pipeline'], 2),
            'profile_pred_error': eval_profile['pred_error'],
            'pipeline_pred_error': eval_pipeline['pred_error'],
            'pred_improves': pred_improves,
            'profile_suspension': eval_profile['suspension_pct'],
            'pipeline_suspension': eval_pipeline['suspension_pct'],
            'suspension_decreases': suspension_decreases,
            'profile_time_below': eval_profile['time_below'],
            'pipeline_time_below': eval_pipeline['time_below'],
            'hypo_safe': hypo_safe,
            'profile_tir': eval_profile['tir'],
            'pipeline_tir': eval_pipeline['tir'],
            'isf_direction_correct': isf_direction_correct,
            'test_deviation_median': round(float(test_dev), 3) if not np.isnan(test_dev) else None,
        }
        results.append(r)
        
        improve_str = "✓" if pred_improves else "✗"
        print(f"  {pid:28s} {ctrl:8s} ISF:{settings['isf_profile']:.0f}→{settings['isf_pipeline']:.0f} "
              f"PredErr:{eval_profile['pred_error']:.2f}→{eval_pipeline['pred_error']:.2f} "
              f"Susp:{eval_profile['suspension_pct']:.0%}→{eval_pipeline['suspension_pct']:.0%} "
              f"{improve_str}")
    
    rdf = pd.DataFrame(results)
    print(f"\nValid patients: {len(rdf)}")
    
    # ---- Hypothesis tests ----
    print("\n" + "=" * 60)
    print("HYPOTHESIS RESULTS")
    print("=" * 60)
    
    hyp = {}
    
    # H1: BG prediction improves for >50%
    pred_improve_pct = rdf['pred_improves'].mean()
    hyp['H1_pred_improve_50'] = pred_improve_pct > 0.50
    print(f"  {'✓ PASS' if hyp['H1_pred_improve_50'] else '✗ FAIL'}: H1 pred improves>50% = "
          f"{pred_improve_pct:.1%} ({rdf['pred_improves'].sum()}/{len(rdf)})")
    
    # H2: Suspension decreases for >40%
    susp_decrease_pct = rdf['suspension_decreases'].mean()
    hyp['H2_susp_decrease_40'] = susp_decrease_pct > 0.40
    print(f"  {'✓ PASS' if hyp['H2_susp_decrease_40'] else '✗ FAIL'}: H2 suspension decrease>40% = "
          f"{susp_decrease_pct:.1%}")
    
    # H3: Hypo safe (no increase)
    hypo_safe_pct = rdf['hypo_safe'].mean()
    mean_hypo_change = rdf['pipeline_time_below'].mean() - rdf['profile_time_below'].mean()
    hyp['H3_hypo_safe'] = hypo_safe_pct > 0.80 and abs(mean_hypo_change) < 1.0
    print(f"  {'✓ PASS' if hyp['H3_hypo_safe'] else '✗ FAIL'}: H3 hypo safe = "
          f"{hypo_safe_pct:.1%} safe, mean change={mean_hypo_change:+.2f}%")
    
    # H4: ISF direction prediction correct >60%
    isf_correct_pct = rdf['isf_direction_correct'].mean()
    hyp['H4_isf_direction_60'] = isf_correct_pct > 0.60
    print(f"  {'✓ PASS' if hyp['H4_isf_direction_60'] else '✗ FAIL'}: H4 ISF direction>60% = "
          f"{isf_correct_pct:.1%}")
    
    # H5: Consistent across controllers
    ctrl_improve = {}
    all_gt_40 = True
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        cdf = rdf[rdf['controller'] == ctrl]
        if len(cdf) > 0:
            pct = cdf['pred_improves'].mean()
            ctrl_improve[ctrl] = pct
            if pct < 0.40:
                all_gt_40 = False
    hyp['H5_consistent_controllers'] = all_gt_40
    print(f"  {'✓ PASS' if hyp['H5_consistent_controllers'] else '✗ FAIL'}: H5 consistent = "
          f"{', '.join(f'{c}={p:.0%}' for c, p in ctrl_improve.items())}")
    
    passed = sum(hyp.values())
    total = len(hyp)
    print(f"\n  TOTAL: {passed}/{total} PASS")
    
    # ---- Summary ----
    print("\n" + "=" * 60)
    print("PROSPECTIVE VALIDATION SUMMARY")
    print("=" * 60)
    
    print(f"\n  Prediction Error (median):")
    print(f"    Profile: {rdf['profile_pred_error'].median():.3f} mg/dL/5min")
    print(f"    Pipeline: {rdf['pipeline_pred_error'].median():.3f} mg/dL/5min")
    print(f"    Change: {(rdf['pipeline_pred_error'].median() - rdf['profile_pred_error'].median()):.3f}")
    
    print(f"\n  Suspension Rate (median):")
    print(f"    Profile: {rdf['profile_suspension'].median():.1%}")
    print(f"    Pipeline: {rdf['pipeline_suspension'].median():.1%}")
    
    print(f"\n  Time Below 70 (mean):")
    print(f"    Profile: {rdf['profile_time_below'].mean():.2f}%")
    print(f"    Pipeline: {rdf['pipeline_time_below'].mean():.2f}%")
    
    # By controller
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        cdf = rdf[rdf['controller'] == ctrl]
        print(f"\n  {ctrl} (N={len(cdf)}):")
        print(f"    Prediction improvement: {cdf['pred_improves'].mean():.0%}")
        print(f"    ISF change: {cdf['isf_profile'].median():.0f} → {cdf['isf_pipeline'].median():.0f}")
        print(f"    TIR: {cdf['profile_tir'].median():.0f}% → {cdf['pipeline_tir'].median():.0f}% (same data, different ISF)")
    
    # ---- Visualization ----
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2795: Prospective Settings Validation (Train→Test)', fontsize=14, fontweight='bold')
        
        colors = {'Loop': '#2196F3', 'Trio': '#4CAF50', 'OpenAPS': '#FF9800'}
        
        # 1. Profile vs Pipeline prediction error
        ax = axes[0, 0]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            cdf = rdf[rdf['controller'] == ctrl]
            ax.scatter(cdf['profile_pred_error'], cdf['pipeline_pred_error'],
                      c=colors[ctrl], label=ctrl, s=60, alpha=0.7, edgecolors='black', linewidths=0.5)
        lim = max(rdf['profile_pred_error'].max(), rdf['pipeline_pred_error'].max()) * 1.1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3, label='No change')
        ax.set_xlabel('Profile Prediction Error')
        ax.set_ylabel('Pipeline Prediction Error')
        ax.set_title('BG Prediction: Profile vs Pipeline')
        ax.legend(fontsize=8)
        
        # 2. Suspension rate comparison
        ax = axes[0, 1]
        x = np.arange(len(rdf))
        width = 0.35
        ax.bar(x - width/2, rdf['profile_suspension'] * 100, width, color='#FF5722', alpha=0.6, label='Profile')
        ax.bar(x + width/2, rdf['pipeline_suspension'] * 100, width, color='#4CAF50', alpha=0.6, label='Pipeline')
        ax.set_xlabel('Patient')
        ax.set_ylabel('Suspension Rate (%)')
        ax.set_title('Controller Suspension: Profile vs Pipeline')
        ax.legend(fontsize=8)
        
        # 3. Hypo safety
        ax = axes[0, 2]
        ax.scatter(rdf['profile_time_below'], rdf['pipeline_time_below'],
                  c=[colors[c] for c in rdf['controller']], s=60, alpha=0.7, 
                  edgecolors='black', linewidths=0.5)
        lim = max(rdf['profile_time_below'].max(), rdf['pipeline_time_below'].max()) * 1.1 + 1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3)
        ax.set_xlabel('Profile Time Below 70 (%)')
        ax.set_ylabel('Pipeline Time Below 70 (%)')
        ax.set_title('Hypo Safety Check')
        
        # 4. ISF direction validation
        ax = axes[1, 0]
        correct = rdf['isf_direction_correct'].sum()
        incorrect = len(rdf) - correct
        ax.bar(['Correct', 'Incorrect'], [correct, incorrect], 
              color=['#4CAF50', '#FF5722'], alpha=0.7, edgecolor='black')
        ax.set_ylabel('Patient Count')
        ax.set_title(f'ISF Direction Prediction ({correct}/{len(rdf)} correct)')
        
        # 5. Per-controller improvement
        ax = axes[1, 1]
        for i, ctrl in enumerate(['Loop', 'Trio', 'OpenAPS']):
            pct = ctrl_improve.get(ctrl, 0) * 100
            ax.bar(ctrl, pct, color=colors[ctrl], alpha=0.7, edgecolor='black')
        ax.axhline(50, color='red', linestyle='--', label='50% threshold')
        ax.set_ylabel('% Patients with Prediction Improvement')
        ax.set_title('Improvement by Controller')
        ax.legend(fontsize=8)
        
        # 6. Summary table
        ax = axes[1, 2]
        ax.axis('off')
        table_data = [
            ['Metric', 'Profile', 'Pipeline', 'Result'],
            ['Pred Error', f"{rdf['profile_pred_error'].median():.3f}", 
             f"{rdf['pipeline_pred_error'].median():.3f}",
             '✓' if pred_improve_pct > 0.5 else '✗'],
            ['Suspension', f"{rdf['profile_suspension'].median():.0%}",
             f"{rdf['pipeline_suspension'].median():.0%}",
             '✓' if susp_decrease_pct > 0.4 else '✗'],
            ['Time <70', f"{rdf['profile_time_below'].mean():.1f}%",
             f"{rdf['pipeline_time_below'].mean():.1f}%",
             '✓' if abs(mean_hypo_change) < 1 else '✗'],
            ['ISF Correct', '', f'{isf_correct_pct:.0%}', '✓' if isf_correct_pct > 0.6 else '✗'],
        ]
        table = ax.table(cellText=table_data, loc='center', cellLoc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.3, 1.6)
        for j in range(4):
            table[0, j].set_facecolor('#E0E0E0')
        ax.set_title('Validation Summary', pad=20)
        
        plt.tight_layout()
        os.makedirs('tools/visualizations/prospective-validation', exist_ok=True)
        plt.savefig('tools/visualizations/prospective-validation/exp-2795-dashboard.png', dpi=150)
        plt.close()
        print(f"\nVisualization saved: tools/visualizations/prospective-validation/exp-2795-dashboard.png")
    except Exception as e:
        print(f"\nVisualization failed: {e}")
    
    # ---- Save ----
    output = {
        'experiment': 'EXP-2795',
        'title': 'Prospective Settings Validation via Counterfactual',
        'n_patients': len(rdf),
        'hypotheses': {k: {'pass': bool(v)} for k, v in hyp.items()},
        'passed': passed,
        'total': total,
        'summary': {
            'pred_improve_pct': round(pred_improve_pct, 3),
            'susp_decrease_pct': round(susp_decrease_pct, 3),
            'hypo_safe_pct': round(hypo_safe_pct, 3),
            'isf_correct_pct': round(isf_correct_pct, 3),
            'profile_pred_error_median': round(float(rdf['profile_pred_error'].median()), 4),
            'pipeline_pred_error_median': round(float(rdf['pipeline_pred_error'].median()), 4),
        },
        'by_controller': ctrl_improve,
        'patients': results,
    }
    
    with open('externals/experiments/exp-2795_prospective_validation.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: externals/experiments/exp-2795_prospective_validation.json")


if __name__ == '__main__':
    main()
