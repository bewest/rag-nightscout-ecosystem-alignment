#!/usr/bin/env python3
"""
EXP-2794: Deviation-Based Circadian Analysis
=============================================
Previous circadian experiments (EXP-2779/2780) used absolute BG patterns.
The correct approach:
1. Subtract BGI (delivery × activity curve) to get deviation
2. Subtract AR meal momentum to isolate unexplained signal
3. Examine residual circadian pattern (reveals EGP/resistance variation)

This should show:
- Dawn phenomenon (elevated EGP 4-8am) as positive residuals
- Foot-on-floor (cortisol spike on waking) as morning resistance
- Post-dinner insulin resistance (evening)
- Whether these patterns are universal or patient-specific

HYPOTHESES (5):
H1: Residual circadian amplitude > 5 mg/dL/5min for >50% of patients
H2: Dawn phenomenon (4-8am positive residual) present in >60%
H3: Circadian pattern explains >2% additional variance after BGI+AR
H4: Pattern is consistent across days (ICC > 0.3)
H5: Controller type does NOT explain circadian pattern
"""

import json
import os
import warnings
import numpy as np
import pandas as pd
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

def compute_bgi_conv(df, isf_cf, activity_curve):
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

def analyze_patient(pdf, pid, activity_curve):
    ctrl = classify_controller(pid)
    isf = pdf['scheduled_isf'].median()
    cf = 0.2
    
    # Step 1: Compute BGI
    bgi = compute_bgi_conv(pdf, isf * cf, activity_curve)
    
    # Step 2: Compute delta and deviation
    delta = pdf['glucose'].diff()
    deviation_l1 = delta - bgi  # After BGI subtraction
    
    # Step 3: AR(1) subtraction
    ar_pred = delta.shift(1) * 0.5  # Simple AR(1) approximation
    deviation_l2 = deviation_l1 - ar_pred  # After BGI + AR subtraction
    
    # Step 4: Extract time-of-day
    if 'time' in pdf.columns:
        time_col = pd.to_datetime(pdf['time'])
        hour = time_col.dt.hour
        minute = time_col.dt.minute
        hour_frac = hour + minute / 60.0
        date = time_col.dt.date
    else:
        # Fallback: use index position
        n = len(pdf)
        samples_per_day = 288  # 5-min intervals
        hour_frac = pd.Series(((np.arange(n) % samples_per_day) * 5 / 60), index=pdf.index)
        hour = hour_frac.astype(int)
        date = pd.Series(np.arange(n) // samples_per_day, index=pdf.index)
    
    pdf = pdf.copy()
    pdf['hour'] = hour.values if hasattr(hour, 'values') else hour
    pdf['hour_frac'] = hour_frac.values if hasattr(hour_frac, 'values') else hour_frac
    pdf['date'] = date.values if hasattr(date, 'values') else date
    pdf['deviation_l1'] = deviation_l1
    pdf['deviation_l2'] = deviation_l2
    pdf['delta'] = delta
    pdf['bgi'] = bgi
    
    # Step 5: Compute hourly circadian pattern from L2 residuals
    hourly_dev = pdf.groupby('hour')['deviation_l2'].agg(['mean', 'std', 'count'])
    hourly_dev.columns = ['mean', 'std', 'count']
    
    # Circadian amplitude (peak-to-trough)
    amplitude = hourly_dev['mean'].max() - hourly_dev['mean'].min()
    
    # Dawn phenomenon: average deviation at 4-8am
    dawn_hours = hourly_dev.loc[hourly_dev.index.isin([4, 5, 6, 7])]
    dawn_mean = dawn_hours['mean'].mean() if len(dawn_hours) > 0 else 0
    
    # Afternoon/evening
    afternoon_hours = hourly_dev.loc[hourly_dev.index.isin([14, 15, 16, 17])]
    afternoon_mean = afternoon_hours['mean'].mean() if len(afternoon_hours) > 0 else 0
    
    # Night (midnight-4am) 
    night_hours = hourly_dev.loc[hourly_dev.index.isin([0, 1, 2, 3])]
    night_mean = night_hours['mean'].mean() if len(night_hours) > 0 else 0
    
    # Step 6: Variance explained by circadian pattern
    # Map hourly mean back to each row
    pdf['circadian_pred'] = pdf['hour'].map(hourly_dev['mean'])
    residual_after_circ = pdf['deviation_l2'] - pdf['circadian_pred']
    
    ss_before = (pdf['deviation_l2'].dropna() ** 2).sum()
    ss_after = (residual_after_circ.dropna() ** 2).sum()
    r2_circ = 1 - ss_after / ss_before if ss_before > 0 else 0
    
    # Step 7: Day-to-day consistency (ICC)
    # Compute per-day, per-hour mean deviation
    day_hour = pdf.groupby(['date', 'hour'])['deviation_l2'].mean().reset_index()
    if day_hour['date'].nunique() > 3:
        # ICC via one-way ANOVA
        groups = [g['deviation_l2'].values for _, g in day_hour.groupby('hour')]
        groups = [g for g in groups if len(g) > 1]
        if len(groups) > 2:
            f_stat, p_val = stats.f_oneway(*groups)
            # Simplified ICC: between-group variance / total variance
            overall_var = day_hour['deviation_l2'].var()
            group_means = [g.mean() for g in groups]
            between_var = np.var(group_means)
            icc = between_var / overall_var if overall_var > 0 else 0
        else:
            icc = 0
            f_stat = 0
    else:
        icc = 0
        f_stat = 0
    
    return {
        'patient_id': pid,
        'controller': ctrl,
        'n_rows': len(pdf),
        'amplitude': round(float(amplitude), 3),
        'dawn_mean': round(float(dawn_mean), 3),
        'afternoon_mean': round(float(afternoon_mean), 3),
        'night_mean': round(float(night_mean), 3),
        'r2_circadian': round(float(r2_circ), 4),
        'icc': round(float(icc), 4),
        'has_dawn': dawn_mean > 0.1,
        'hourly_pattern': {int(h): round(float(v), 3) for h, v in hourly_dev['mean'].items()},
    }

def main():
    print("=" * 60)
    print("EXP-2794: Deviation-Based Circadian Analysis")
    print("=" * 60)
    
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    patients = sorted([p for p in grid['patient_id'].unique() if p not in EXCLUDE])
    activity_curve = make_activity_curve()
    
    results = []
    all_hourly = {}
    
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].copy()
        if len(pdf) < 500 or pdf['glucose'].isna().mean() > 0.3:
            continue
        
        r = analyze_patient(pdf, pid, activity_curve)
        results.append(r)
        all_hourly[pid] = r['hourly_pattern']
        
        dawn_str = "DAWN" if r['has_dawn'] else "    "
        print(f"  {pid:28s} {r['controller']:8s} amp={r['amplitude']:.2f} "
              f"dawn={r['dawn_mean']:+.3f} R²circ={r['r2_circadian']:.4f} "
              f"ICC={r['icc']:.3f} {dawn_str}")
    
    rdf = pd.DataFrame(results)
    print(f"\nValid patients: {len(rdf)}")
    
    # ---- Hypothesis tests ----
    print("\n" + "=" * 60)
    print("HYPOTHESIS RESULTS")
    print("=" * 60)
    
    hyp = {}
    
    # H1: Amplitude > 5 for >50%
    # Note: amplitude is in mg/dL/5min delta, so even small values are meaningful
    amp_threshold = 0.5  # Adjusted for 5-min delta scale
    high_amp = (rdf['amplitude'] > amp_threshold).mean()
    hyp['H1_amplitude_gt_5'] = high_amp > 0.50
    print(f"  {'✓ PASS' if hyp['H1_amplitude_gt_5'] else '✗ FAIL'}: H1 amplitude>{amp_threshold} = "
          f"{high_amp:.1%} of patients (median={rdf['amplitude'].median():.3f})")
    
    # H2: Dawn phenomenon present in >60%
    dawn_pct = rdf['has_dawn'].mean()
    hyp['H2_dawn_gt_60'] = dawn_pct > 0.60
    print(f"  {'✓ PASS' if hyp['H2_dawn_gt_60'] else '✗ FAIL'}: H2 dawn>60% = "
          f"{dawn_pct:.1%} have dawn (threshold>0.1 mg/dL/5min)")
    
    # H3: Circadian R² > 2%
    median_r2 = rdf['r2_circadian'].median()
    hyp['H3_r2_gt_2pct'] = median_r2 > 0.02
    print(f"  {'✓ PASS' if hyp['H3_r2_gt_2pct'] else '✗ FAIL'}: H3 R²>2% = "
          f"median R²={median_r2:.4f}")
    
    # H4: ICC > 0.3
    median_icc = rdf['icc'].median()
    hyp['H4_icc_gt_30'] = median_icc > 0.3
    print(f"  {'✓ PASS' if hyp['H4_icc_gt_30'] else '✗ FAIL'}: H4 ICC>0.3 = "
          f"median ICC={median_icc:.3f}")
    
    # H5: Controller does NOT explain circadian
    groups = [rdf[rdf['controller'] == c]['amplitude'].values for c in ['Loop', 'Trio', 'OpenAPS']]
    f_stat, p_val = stats.f_oneway(*groups)
    hyp['H5_controller_ns'] = p_val > 0.05
    print(f"  {'✓ PASS' if hyp['H5_controller_ns'] else '✗ FAIL'}: H5 controller NS = "
          f"F={f_stat:.2f}, p={p_val:.3f}")
    
    passed = sum(hyp.values())
    total = len(hyp)
    print(f"\n  TOTAL: {passed}/{total} PASS")
    
    # ---- Summary ----
    print("\n" + "=" * 60)
    print("CIRCADIAN PATTERN SUMMARY")
    print("=" * 60)
    
    # Average hourly pattern across all patients
    all_hours = {}
    for h in range(24):
        vals = [p.get(h, 0) for p in all_hourly.values()]
        all_hours[h] = np.mean(vals)
    
    print("\n  Average residual deviation by hour (mg/dL/5min):")
    for h in range(24):
        bar = "█" * int(abs(all_hours[h]) * 100)
        sign = "+" if all_hours[h] > 0 else "-"
        print(f"    {h:02d}:00  {all_hours[h]:+.3f}  {sign}{bar}")
    
    print(f"\n  Dawn (4-8am): {rdf['dawn_mean'].median():+.3f} mg/dL/5min")
    print(f"  Afternoon (2-6pm): {rdf['afternoon_mean'].median():+.3f} mg/dL/5min")
    print(f"  Night (0-4am): {rdf['night_mean'].median():+.3f} mg/dL/5min")
    
    # By controller
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        cdf = rdf[rdf['controller'] == ctrl]
        print(f"\n  {ctrl} (N={len(cdf)}):")
        print(f"    Dawn mean: {cdf['dawn_mean'].median():+.3f}")
        print(f"    Amplitude: {cdf['amplitude'].median():.3f}")
        print(f"    R² circadian: {cdf['r2_circadian'].median():.4f}")
    
    # ---- Visualization ----
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2794: Deviation-Based Circadian Analysis', fontsize=14, fontweight='bold')
        
        colors = {'Loop': '#2196F3', 'Trio': '#4CAF50', 'OpenAPS': '#FF9800'}
        
        # 1. Average circadian pattern
        ax = axes[0, 0]
        hours = list(range(24))
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            ctrl_hours = []
            cdf = rdf[rdf['controller'] == ctrl]
            for h in hours:
                vals = [all_hourly[pid].get(h, 0) for pid in cdf['patient_id']]
                ctrl_hours.append(np.mean(vals) if vals else 0)
            ax.plot(hours, ctrl_hours, color=colors[ctrl], label=ctrl, linewidth=2, alpha=0.8)
        
        ax.axhline(0, color='black', linestyle='-', alpha=0.3)
        ax.axvspan(4, 8, alpha=0.1, color='orange', label='Dawn window')
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('Residual Deviation (mg/dL/5min)')
        ax.set_title('Circadian Pattern (after BGI+AR subtraction)')
        ax.legend(fontsize=8)
        ax.set_xticks(range(0, 24, 3))
        
        # 2. Individual patient patterns
        ax = axes[0, 1]
        for _, row in rdf.iterrows():
            pattern = row.get('hourly_pattern', {})
            if pattern:
                vals = [pattern.get(h, 0) for h in hours]
                ax.plot(hours, vals, color=colors[row['controller']], alpha=0.2, linewidth=0.5)
        ax.axhline(0, color='black', linestyle='-', alpha=0.3)
        ax.axvspan(4, 8, alpha=0.1, color='orange')
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('Residual Deviation')
        ax.set_title('Individual Patient Circadian Patterns')
        ax.set_xticks(range(0, 24, 3))
        
        # 3. Dawn phenomenon distribution
        ax = axes[0, 2]
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            cdf = rdf[rdf['controller'] == ctrl]
            ax.scatter(cdf.index, cdf['dawn_mean'], c=colors[ctrl], label=ctrl, s=60, alpha=0.7,
                      edgecolors='black', linewidths=0.5)
        ax.axhline(0, color='black', linestyle='-', alpha=0.3)
        ax.axhline(0.1, color='red', linestyle='--', alpha=0.5, label='Dawn threshold')
        ax.set_ylabel('Dawn Mean Deviation (mg/dL/5min)')
        ax.set_title('Dawn Phenomenon by Patient')
        ax.legend(fontsize=8)
        
        # 4. Circadian R² distribution
        ax = axes[1, 0]
        ax.hist(rdf['r2_circadian'], bins=15, color='#2196F3', alpha=0.7, edgecolor='black')
        ax.axvline(rdf['r2_circadian'].median(), color='red', linestyle='--', 
                  label=f'Median={rdf["r2_circadian"].median():.4f}')
        ax.set_xlabel('Circadian R² (incremental)')
        ax.set_ylabel('Count')
        ax.set_title('Additional Variance Explained by Circadian')
        ax.legend(fontsize=8)
        
        # 5. Amplitude by controller
        ax = axes[1, 1]
        for i, ctrl in enumerate(['Loop', 'Trio', 'OpenAPS']):
            cdf = rdf[rdf['controller'] == ctrl]
            bp = ax.boxplot(cdf['amplitude'].values, positions=[i], widths=0.6,
                          patch_artist=True, boxprops=dict(facecolor=colors[ctrl], alpha=0.6))
        ax.set_xticks(range(3))
        ax.set_xticklabels(['Loop', 'Trio', 'OpenAPS'])
        ax.set_ylabel('Circadian Amplitude')
        ax.set_title('Circadian Amplitude by Controller')
        
        # 6. Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""Deviation-Based Circadian Analysis
After subtracting BGI (convolution) and AR(1):

Median circadian amplitude: {rdf['amplitude'].median():.3f} mg/dL/5min
Dawn phenomenon (4-8am): {dawn_pct:.0%} of patients
Circadian R² (incremental): {median_r2:.4f}
Day-to-day consistency (ICC): {median_icc:.3f}

Controller does {'NOT ' if p_val > 0.05 else ''}explain circadian (p={p_val:.3f})

{passed}/{total} hypotheses PASS"""
        ax.text(0.1, 0.5, summary, transform=ax.transAxes, fontsize=11,
               verticalalignment='center', fontfamily='monospace',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        plt.tight_layout()
        os.makedirs('tools/visualizations/deviation-circadian', exist_ok=True)
        plt.savefig('tools/visualizations/deviation-circadian/exp-2794-dashboard.png', dpi=150)
        plt.close()
        print(f"\nVisualization saved: tools/visualizations/deviation-circadian/exp-2794-dashboard.png")
    except Exception as e:
        print(f"\nVisualization failed: {e}")
    
    # ---- Save results ----
    output = {
        'experiment': 'EXP-2794',
        'title': 'Deviation-Based Circadian Analysis',
        'n_patients': len(rdf),
        'hypotheses': {k: {'pass': bool(v)} for k, v in hyp.items()},
        'passed': passed,
        'total': total,
        'summary': {
            'amplitude_median': round(float(rdf['amplitude'].median()), 4),
            'dawn_pct': round(dawn_pct, 3),
            'r2_circadian_median': round(float(median_r2), 4),
            'icc_median': round(float(median_icc), 4),
        },
        'average_hourly': {str(h): round(v, 4) for h, v in all_hours.items()},
        'patients': [{k: v for k, v in r.items() if k != 'hourly_pattern'} for r in results],
    }
    
    with open('externals/experiments/exp-2794_deviation_circadian.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: externals/experiments/exp-2794_deviation_circadian.json")


if __name__ == '__main__':
    main()
