#!/usr/bin/env python3
"""EXP-2782: Controller-Specific Settings Audit

Integrates findings from the full pipeline into a comprehensive per-patient
settings audit, stratified by controller type (Loop, Trio, OpenAPS).

From prior experiments:
- EXP-2719b: ISF waterfall extraction (68% improve)
- EXP-2741: Bilateral CR deconfounding (73% improve)
- EXP-2775: Basal 50/50 rule (7/12 Trio too low)
- EXP-2773: Bilateral regression model

This experiment asks:
1. Are there SYSTEMATIC miscalibrations per controller type?
2. Which settings matter most for each controller?
3. What are the top 3 recommendations per patient?

Success criteria (3/5 to PASS):
  H1: Controller types differ in ISF miscalibration pattern (ANOVA p<0.05)
  H2: Controller types differ in basal fraction (confirmed from EXP-2775)
  H3: >70% of patients have at least one actionable recommendation
  H4: Mean TIR for patients with "good" settings > TIR for "bad" settings
  H5: Combined settings score correlates with TIR (r>0.3)
"""

import json, os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression
from scipy import stats

warnings.filterwarnings('ignore')

EXP_ID = "exp-2782"
TITLE = "Controller-Specific Settings Audit"
OUT_JSON = Path("externals/experiments/exp-2782_settings_audit.json")
OUT_VIS = Path("tools/visualizations/settings-audit")
OUT_VIS.mkdir(parents=True, exist_ok=True)

EXCLUDE = {'odc-84181797', 'h', 'j'}

# Controller classification
LOOP_IDS = {'a', 'b', 'c', 'd', 'e', 'f', 'g', 'i', 'k'}
TRIO_IDS = {p for p in [] }  # Will identify from data
OPENAPS_IDS = set()

def load_grid():
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
    grid['time'] = pd.to_datetime(grid['time'])
    return grid

def classify_controller(patient_df, pid):
    """Classify controller type from data characteristics."""
    if pid in LOOP_IDS or pid.startswith(('a', 'b', 'c', 'd', 'e', 'f', 'g', 'i', 'k')) and len(pid) == 1:
        return 'Loop'
    
    has_smb = 'bolus_smb' in patient_df.columns and patient_df['bolus_smb'].fillna(0).sum() > 0
    
    if pid.startswith('odc-'):
        return 'OpenAPS'
    
    if pid.startswith('ns-'):
        if has_smb:
            return 'Trio'
        return 'Trio'  # Most ns- patients are Trio in this dataset
    
    return 'Unknown'

def compute_tir(glucose_series, low=70, high=180):
    """Compute time in range."""
    valid = glucose_series.dropna()
    if len(valid) == 0:
        return {'tir': 0, 'below': 0, 'above': 0}
    return {
        'tir': float((valid.between(low, high)).mean() * 100),
        'below': float((valid < low).mean() * 100),
        'above': float((valid > high).mean() * 100),
    }

def audit_patient(patient_df, pid):
    """Comprehensive settings audit for one patient."""
    df = patient_df.sort_values('time').copy()
    
    profile_isf = df['scheduled_isf'].median()
    profile_cr = df['scheduled_cr'].median() if 'scheduled_cr' in df.columns else np.nan
    basal_rate = df['scheduled_basal_rate'].median()
    
    if pd.isna(profile_isf) or profile_isf <= 0:
        return None
    
    controller = classify_controller(df, pid)
    tir_data = compute_tir(df['glucose'])
    
    # --- ISF Assessment ---
    # Use the production ISF approach: correction factor (CF) from EXP-2719b
    # ISF is "correct" if corrections from BG>180 result in target BG
    high_bg = df[df['glucose'] > 180].copy()
    if len(high_bg) > 100:
        high_bg['delta_2h'] = high_bg['glucose'].shift(-24) - high_bg['glucose']
        excess_ins = (
            high_bg['bolus'].fillna(0).rolling(24, min_periods=1).sum() +
            (high_bg['bolus_smb'].fillna(0).rolling(24, min_periods=1).sum() if 'bolus_smb' in high_bg.columns else 0) +
            (high_bg['net_basal'].fillna(0) / 12.0).rolling(24, min_periods=1).sum() if 'net_basal' in high_bg.columns else
            high_bg['bolus'].fillna(0).rolling(24, min_periods=1).sum()
        )
        high_bg['excess_insulin'] = excess_ins
        valid = high_bg.dropna(subset=['delta_2h'])
        valid = valid[valid['excess_insulin'] > 0.1]
        
        if len(valid) > 30:
            # Observed ISF from regression
            y = valid['delta_2h'].values
            X = valid[['glucose', 'excess_insulin']].values
            model = LinearRegression().fit(X, y)
            observed_isf = -model.coef_[1]
            isf_r2 = model.score(X, y)
        else:
            observed_isf = np.nan
            isf_r2 = np.nan
    else:
        observed_isf = np.nan
        isf_r2 = np.nan
    
    # ISF assessment: compare observed behavior to profile
    isf_ratio = observed_isf / (profile_isf * 0.2) if not np.isnan(observed_isf) and profile_isf > 0 else np.nan
    
    # --- CR Assessment ---
    # Look at BG rise after meals
    meals = df[df['carbs'].fillna(0) > 5].copy()
    if len(meals) > 10:
        meals['post_meal_bg'] = meals['glucose'].shift(-36)  # 3h post
        meals['bg_rise'] = meals['post_meal_bg'] - meals['glucose']
        valid_meals = meals.dropna(subset=['bg_rise', 'post_meal_bg'])
        
        if len(valid_meals) > 10:
            # Good CR → BG returns to pre-meal level (bg_rise ≈ 0)
            median_rise = valid_meals['bg_rise'].median()
            meal_sizes = valid_meals['carbs'].median()
            
            # Estimated CR from observed data
            # If BG rises by X after meal of C carbs, need X/ISF more insulin
            # Current CR gives C/CR units. Need C/CR + X/ISF units.
            # Optimal CR = C / (C/CR + X/ISF) = C × ISF × CR / (C × ISF + X × CR)
            if not np.isnan(profile_cr) and profile_cr > 0 and profile_isf > 0:
                avg_carbs = valid_meals['carbs'].mean()
                optimal_cr = avg_carbs * profile_isf * profile_cr / (avg_carbs * profile_isf + median_rise * profile_cr)
                cr_ratio = optimal_cr / profile_cr if optimal_cr > 0 else np.nan
            else:
                optimal_cr = np.nan
                cr_ratio = np.nan
        else:
            median_rise = np.nan
            cr_ratio = np.nan
            optimal_cr = np.nan
    else:
        median_rise = np.nan
        cr_ratio = np.nan
        optimal_cr = np.nan
    
    # --- Basal Assessment ---
    # 50/50 rule: basal should be ~50% of TDD
    total_bolus = df['bolus'].fillna(0).sum()
    total_smb = df['bolus_smb'].fillna(0).sum() if 'bolus_smb' in df.columns else 0
    total_basal = (df['scheduled_basal_rate'].fillna(0) / 12.0).sum()
    tdd = total_bolus + total_smb + total_basal
    
    if tdd > 0:
        basal_fraction = total_basal / tdd
        bolus_fraction = total_bolus / tdd
        smb_fraction = total_smb / tdd
    else:
        basal_fraction = np.nan
        bolus_fraction = np.nan
        smb_fraction = np.nan
    
    basal_assessment = 'OK' if 0.4 <= basal_fraction <= 0.6 else (
        'TOO LOW' if basal_fraction < 0.4 else 'TOO HIGH')
    
    # --- Recommendations ---
    recommendations = []
    
    if not np.isnan(basal_fraction) and basal_fraction < 0.4:
        needed_pct = round((0.5 / basal_fraction - 1) * 100)
        recommendations.append(f"Increase basal rate by ~{needed_pct}% (currently {basal_fraction*100:.0f}% of TDD)")
    
    if not np.isnan(median_rise) and median_rise > 30:
        recommendations.append(f"Decrease CR (more insulin per carb) — BG rises {median_rise:.0f} mg/dL post-meal")
    elif not np.isnan(median_rise) and median_rise < -30:
        recommendations.append(f"Increase CR (less insulin per carb) — BG drops {-median_rise:.0f} mg/dL post-meal")
    
    if not np.isnan(observed_isf) and observed_isf > 0:
        if observed_isf > profile_isf * 0.2 * 1.3:  # >30% above expected
            recommendations.append(f"Consider decreasing ISF (insulin is stronger than expected)")
        elif observed_isf < profile_isf * 0.2 * 0.7:
            recommendations.append(f"Consider increasing ISF (insulin is weaker than expected)")
    
    if tir_data['below'] > 4:
        recommendations.append(f"High hypo risk: {tir_data['below']:.1f}% below 70 mg/dL")
    
    if tir_data['above'] > 30:
        recommendations.append(f"Significant hyperglycemia: {tir_data['above']:.1f}% above 180 mg/dL")
    
    # Settings score (0-100)
    score = 0
    if not np.isnan(basal_fraction):
        score += max(0, 30 - abs(basal_fraction - 0.5) * 100)  # 30 pts for good basal
    if not np.isnan(median_rise):
        score += max(0, 30 - abs(median_rise) / 3)  # 30 pts for good CR
    if tir_data['tir'] > 0:
        score += tir_data['tir'] * 0.4  # 40 pts max for TIR
    
    return {
        'patient_id': pid,
        'controller': controller,
        'tir': tir_data,
        'settings': {
            'profile_isf': round(profile_isf, 1),
            'profile_cr': round(profile_cr, 1) if not np.isnan(profile_cr) else None,
            'basal_rate': round(basal_rate, 2),
        },
        'isf_audit': {
            'observed_isf': round(observed_isf, 2) if not np.isnan(observed_isf) else None,
            'isf_ratio': round(isf_ratio, 2) if not np.isnan(isf_ratio) else None,
            'r2': round(isf_r2, 4) if not np.isnan(isf_r2) else None,
        },
        'cr_audit': {
            'median_post_meal_rise': round(median_rise, 1) if not np.isnan(median_rise) else None,
            'optimal_cr': round(optimal_cr, 1) if not np.isnan(optimal_cr) else None,
            'cr_ratio': round(cr_ratio, 2) if not np.isnan(cr_ratio) else None,
        },
        'basal_audit': {
            'basal_fraction': round(basal_fraction, 3) if not np.isnan(basal_fraction) else None,
            'bolus_fraction': round(bolus_fraction, 3) if not np.isnan(bolus_fraction) else None,
            'smb_fraction': round(smb_fraction, 3) if not np.isnan(smb_fraction) else None,
            'assessment': basal_assessment,
            'tdd': round(tdd, 1),
        },
        'recommendations': recommendations,
        'n_recommendations': len(recommendations),
        'settings_score': round(score, 1),
    }

def main():
    print(f"{'='*60}")
    print(f"EXP-2782: {TITLE}")
    print(f"{'='*60}\n")
    
    grid = load_grid()
    patients = sorted(grid['patient_id'].unique())
    print(f"Patients: {len(patients)}")
    
    results = {}
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        r = audit_patient(pdf, pid)
        if r is None:
            print(f"  {pid}: skipped")
            continue
        results[pid] = r
        
        ba = r['basal_audit']
        print(f"  {pid} [{r['controller']:<7}] TIR={r['tir']['tir']:.0f}% "
              f"basal={ba['basal_fraction']*100:.0f}% [{ba['assessment']}] "
              f"recs={r['n_recommendations']} score={r['settings_score']:.0f}")
    
    if not results:
        print("ERROR: No results")
        sys.exit(1)
    
    n = len(results)
    
    # Controller-level analysis
    print(f"\n{'='*60}")
    print(f"CONTROLLER COMPARISON (N={n})")
    print(f"{'='*60}")
    
    by_controller = {}
    for controller in ['Loop', 'Trio', 'OpenAPS']:
        cr = {pid: r for pid, r in results.items() if r['controller'] == controller}
        if not cr:
            continue
        
        tirs = [r['tir']['tir'] for r in cr.values()]
        basals = [r['basal_audit']['basal_fraction'] for r in cr.values() 
                 if r['basal_audit']['basal_fraction'] is not None]
        scores = [r['settings_score'] for r in cr.values()]
        n_recs = [r['n_recommendations'] for r in cr.values()]
        
        by_controller[controller] = {
            'n': len(cr),
            'median_tir': np.median(tirs),
            'median_basal_frac': np.median(basals) if basals else None,
            'median_score': np.median(scores),
            'median_recs': np.median(n_recs),
        }
        
        print(f"\n  {controller} (N={len(cr)}):")
        print(f"    TIR: {np.median(tirs):.0f}%")
        print(f"    Basal fraction: {np.median(basals)*100:.0f}%" if basals else "    Basal: N/A")
        print(f"    Settings score: {np.median(scores):.0f}")
        print(f"    Recommendations: {np.median(n_recs):.0f} per patient")
        
        # Basal assessment
        assessments = [r['basal_audit']['assessment'] for r in cr.values()]
        for a in ['OK', 'TOO LOW', 'TOO HIGH']:
            cnt = assessments.count(a)
            if cnt > 0:
                print(f"    Basal {a}: {cnt}/{len(cr)}")
    
    # Overall statistics
    print(f"\n{'='*60}")
    print(f"OVERALL (N={n})")
    print(f"{'='*60}")
    
    all_tirs = [r['tir']['tir'] for r in results.values()]
    all_scores = [r['settings_score'] for r in results.values()]
    all_recs = [r['n_recommendations'] for r in results.values()]
    
    print(f"\nMedian TIR: {np.median(all_tirs):.0f}%")
    print(f"Median settings score: {np.median(all_scores):.0f}")
    print(f"Patients with ≥1 recommendation: {sum(1 for r in all_recs if r > 0)}/{n}")
    
    # Score vs TIR correlation
    score_tir_corr, _ = stats.pearsonr(all_scores, all_tirs)
    print(f"Score-TIR correlation: r={score_tir_corr:.3f}")
    
    # Recommendation frequency
    rec_counts = {}
    for r in results.values():
        for rec in r['recommendations']:
            key = rec.split('—')[0].strip().split('(')[0].strip()[:40]
            rec_counts[key] = rec_counts.get(key, 0) + 1
    
    print(f"\nMost common recommendations:")
    for rec, cnt in sorted(rec_counts.items(), key=lambda x: -x[1])[:5]:
        print(f"  {cnt}/{n}: {rec}")
    
    # Hypothesis testing
    # H1: ISF miscalibration differs by controller
    isf_by_ctrl = {}
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        vals = [r['isf_audit']['isf_ratio'] for r in results.values() 
               if r['controller'] == ctrl and r['isf_audit']['isf_ratio'] is not None]
        if vals:
            isf_by_ctrl[ctrl] = vals
    
    if len(isf_by_ctrl) >= 2:
        groups = list(isf_by_ctrl.values())
        if all(len(g) > 2 for g in groups):
            f_stat, p_val = stats.f_oneway(*groups)
            h1 = p_val < 0.05
        else:
            h1 = False
            p_val = 1.0
    else:
        h1 = False
        p_val = 1.0
    
    # H2: Basal fraction differs
    basal_by_ctrl = {}
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        vals = [r['basal_audit']['basal_fraction'] for r in results.values()
               if r['controller'] == ctrl and r['basal_audit']['basal_fraction'] is not None]
        if vals:
            basal_by_ctrl[ctrl] = vals
    
    if len(basal_by_ctrl) >= 2:
        groups = list(basal_by_ctrl.values())
        if all(len(g) > 2 for g in groups):
            f_stat_b, p_val_b = stats.f_oneway(*groups)
            h2 = p_val_b < 0.05
        else:
            h2 = False
            p_val_b = 1.0
    else:
        h2 = False
        p_val_b = 1.0
    
    # H3: >70% have recommendations
    pct_with_recs = sum(1 for r in results.values() if r['n_recommendations'] > 0) / n * 100
    h3 = pct_with_recs > 70
    
    # H4: Good settings → better TIR
    good = [r['tir']['tir'] for r in results.values() if r['settings_score'] > np.median(all_scores)]
    bad = [r['tir']['tir'] for r in results.values() if r['settings_score'] <= np.median(all_scores)]
    h4 = np.median(good) > np.median(bad) if good and bad else False
    
    # H5: Score correlates with TIR
    h5 = score_tir_corr > 0.3
    
    hypotheses = {
        'H1_isf_differs_by_controller': {'pass': bool(h1),
            'value': f"p={p_val:.4f}"},
        'H2_basal_differs_by_controller': {'pass': bool(h2),
            'value': f"p={p_val_b:.4f}"},
        'H3_gt70pct_have_recommendations': {'pass': bool(h3),
            'value': f"{pct_with_recs:.0f}%"},
        'H4_good_settings_better_tir': {'pass': bool(h4),
            'value': f"good={np.median(good):.0f}% vs bad={np.median(bad):.0f}%" if good and bad else "N/A"},
        'H5_score_correlates_tir': {'pass': bool(h5),
            'value': f"r={score_tir_corr:.3f}"},
    }
    
    n_pass = sum(1 for h in hypotheses.values() if h['pass'])
    
    print(f"\n{'='*60}")
    print(f"HYPOTHESIS RESULTS: {n_pass}/5 PASS")
    print(f"{'='*60}")
    for hname, hval in hypotheses.items():
        status = "✓ PASS" if hval['pass'] else "✗ FAIL"
        print(f"  {status}: {hname} = {hval['value']}")
    
    # Visualization
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f'EXP-2782: Controller-Specific Settings Audit — {n_pass}/5 PASS', fontsize=14, fontweight='bold')
        
        # Panel 1: TIR by controller
        ax = axes[0, 0]
        ctrl_data = []
        ctrl_labels = []
        ctrl_colors = {'Loop': 'steelblue', 'Trio': 'coral', 'OpenAPS': 'green'}
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            tirs = [r['tir']['tir'] for r in results.values() if r['controller'] == ctrl]
            if tirs:
                ctrl_data.append(tirs)
                ctrl_labels.append(f'{ctrl}\n(N={len(tirs)})')
        if ctrl_data:
            bp = ax.boxplot(ctrl_data, patch_artist=True)
            for i, (patch, label) in enumerate(zip(bp['boxes'], ctrl_labels)):
                ctrl_name = label.split('\n')[0]
                patch.set_facecolor(ctrl_colors.get(ctrl_name, 'gray'))
                patch.set_alpha(0.6)
            ax.set_xticklabels(ctrl_labels)
        ax.set_ylabel('Time in Range (%)')
        ax.set_title('TIR by Controller Type')
        ax.axhline(y=70, color='red', linestyle='--', alpha=0.5, label='70% target')
        ax.legend()
        
        # Panel 2: Basal fraction by controller
        ax = axes[0, 1]
        ctrl_basal_data = []
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            vals = [r['basal_audit']['basal_fraction'] * 100 for r in results.values()
                   if r['controller'] == ctrl and r['basal_audit']['basal_fraction'] is not None]
            if vals:
                ctrl_basal_data.append(vals)
        if ctrl_basal_data:
            bp = ax.boxplot(ctrl_basal_data, patch_artist=True)
            for i, (patch, label) in enumerate(zip(bp['boxes'], ctrl_labels)):
                ctrl_name = label.split('\n')[0]
                patch.set_facecolor(ctrl_colors.get(ctrl_name, 'gray'))
                patch.set_alpha(0.6)
            ax.set_xticklabels(ctrl_labels)
        ax.axhline(y=50, color='green', linestyle='--', label='50% target')
        ax.axhspan(40, 60, alpha=0.1, color='green')
        ax.set_ylabel('Basal Fraction of TDD (%)')
        ax.set_title('Basal Fraction by Controller')
        ax.legend()
        
        # Panel 3: Settings score vs TIR
        ax = axes[1, 0]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            pts = [(r['settings_score'], r['tir']['tir']) for r in results.values() 
                   if r['controller'] == ctrl]
            if pts:
                ax.scatter([p[0] for p in pts], [p[1] for p in pts],
                          label=ctrl, s=60, alpha=0.7, color=ctrl_colors.get(ctrl, 'gray'))
        ax.set_xlabel('Settings Score')
        ax.set_ylabel('TIR (%)')
        ax.set_title(f'Settings Score vs TIR (r={score_tir_corr:.2f})')
        ax.legend()
        
        # Panel 4: Recommendation counts
        ax = axes[1, 1]
        rec_types = list(rec_counts.keys())[:6]
        rec_vals = [rec_counts[r] for r in rec_types]
        ax.barh(rec_types, rec_vals, color='steelblue', alpha=0.7)
        ax.set_xlabel('Number of Patients')
        ax.set_title('Most Common Recommendations')
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2782-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2782-dashboard.png'}")
    except Exception as e:
        print(f"Visualization error: {e}")
    
    # Save
    output = {
        'experiment': EXP_ID,
        'title': TITLE,
        'n_patients': n,
        'hypotheses': hypotheses,
        'pass_count': f"{n_pass}/5",
        'by_controller': by_controller,
        'per_patient': results,
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: {OUT_JSON}")

if __name__ == '__main__':
    main()
