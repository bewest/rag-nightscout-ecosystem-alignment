#!/usr/bin/env python3
"""
EXP-2797: EGP-Aware Settings Extraction
=========================================
Uses the circadian EGP pattern from EXP-2794 to improve ISF/CR estimation.

Key insight: After subtracting BGI and AR, ALL residual deviations are POSITIVE
(the EGP signature). If we know EGP contributes +0.6 to +1.7 mg/dL/5min by
hour-of-day, we can subtract this from deviations for cleaner ISF/CR extraction.

Without EGP correction:
  - ISF extraction includes EGP-raising effect → ISF appears HIGHER (less sensitive)
  - CR extraction includes EGP background → CR appears HIGHER (less carb impact)

With EGP correction:
  - Subtract hour-specific EGP baseline from residuals
  - ISF and CR should be MORE ACCURATE (closer to true sensitivity)

HYPOTHESES (5):
H1: EGP-corrected ISF is lower than uncorrected (EGP inflates apparent ISF)
H2: EGP-corrected settings closer to profile settings (reduced noise)
H3: EGP-corrected predictions improve R² over uncorrected
H4: Circadian ISF variation reduces after EGP correction
H5: Settings extraction consistency improves (lower CV across time windows)
"""

import json
import os
import warnings
import numpy as np
import pandas as pd
from numpy.linalg import lstsq

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

def estimate_egp_profile(df, bgi, hour):
    """Estimate per-hour EGP as mean residual after BGI + AR(1) subtraction."""
    delta = df['glucose'].diff()
    ar1 = delta.shift(1)
    
    # Fit simple AR(1) + BGI
    X = pd.DataFrame({'bgi': bgi, 'ar1': ar1, 'const': 1.0}).dropna()
    y = delta.loc[X.index].dropna()
    valid = X.index.intersection(y.index)
    
    if len(valid) < 500:
        return pd.Series(0, index=range(24))
    
    coefs, _, _, _ = lstsq(X.loc[valid].values, y.loc[valid].values, rcond=None)
    pred = X.loc[valid].values @ coefs
    residual = y.loc[valid].values - pred
    
    # Bin residuals by hour
    h = hour.loc[valid].astype(int) % 24
    egp_by_hour = pd.Series(residual, index=valid).groupby(h.values).mean()
    
    # Fill any missing hours with global mean
    full = pd.Series(index=range(24), dtype=float)
    for hr in range(24):
        full[hr] = egp_by_hour.get(hr, egp_by_hour.mean())
    
    return full

def extract_isf(df, bgi, egp_correction, hour, label=""):
    """Extract ISF from correction events, optionally with EGP correction."""
    delta = df['glucose'].diff()
    carbs_active = df['carbs'].fillna(0).rolling(36, min_periods=1).sum() > 0
    
    # Correction events: BG > 150, no carbs, glucose dropping
    mask = (df['glucose'] > 150) & (~carbs_active) & (delta < 0)
    
    if mask.sum() < 50:
        return None
    
    corr_delta = delta[mask]
    corr_bgi = bgi[mask]
    corr_hour = hour[mask].astype(int) % 24
    
    # Deviation = observed change - predicted BGI
    deviation = corr_delta - corr_bgi
    
    if egp_correction is not None:
        # Subtract hour-specific EGP from deviation
        egp_adj = corr_hour.map(egp_correction)
        deviation = deviation - egp_adj
    
    # ISF = how much BG drops per unit excess insulin
    # In correction events, deviation should be small → ISF ≈ -delta / (excess_insulin × activity)
    # But simpler: look at deviation stats
    return {
        'median_deviation': round(float(deviation.median()), 3),
        'mean_deviation': round(float(deviation.mean()), 3),
        'std_deviation': round(float(deviation.std()), 3),
        'n_events': int(mask.sum()),
    }

def extract_settings_with_egp(pdf, activity_curve, egp_profile, hour):
    """Full settings extraction with EGP correction."""
    isf = pdf['scheduled_isf'].median()
    cr = pdf['scheduled_cr'].median()
    cf = 0.2
    
    bgi = compute_bgi(pdf, isf * cf, activity_curve)
    delta = pdf['glucose'].diff()
    
    # Categorize
    carbs_active = pdf['carbs'].fillna(0).rolling(36, min_periods=1).sum() > 0
    
    # --- ISF extraction (corrections at BG > 150) ---
    corr_mask = (pdf['glucose'] > 150) & (~carbs_active) & (delta < 0)
    
    # Without EGP correction
    dev_raw = delta - bgi
    isf_dev_raw = dev_raw[corr_mask]
    
    # With EGP correction
    egp_adj = hour.astype(int).map(lambda h: egp_profile.get(h % 24, 0))
    egp_adj = pd.Series(egp_adj.values, index=pdf.index)
    dev_corrected = delta - bgi - egp_adj
    isf_dev_corrected = dev_corrected[corr_mask]
    
    # --- CR extraction (meal events) ---
    meal_mask = carbs_active & (delta > 0)
    cr_dev_raw = dev_raw[meal_mask]
    cr_dev_corrected = dev_corrected[meal_mask]
    
    # --- Circadian ISF variation ---
    isf_by_hour_raw = {}
    isf_by_hour_corrected = {}
    for h in range(24):
        h_mask = corr_mask & (hour.astype(int) % 24 == h)
        if h_mask.sum() > 5:
            isf_by_hour_raw[h] = float(dev_raw[h_mask].mean())
            isf_by_hour_corrected[h] = float(dev_corrected[h_mask].mean())
    
    # CV of hourly ISF (lower = more consistent after EGP correction)
    if len(isf_by_hour_raw) > 6:
        cv_raw = np.std(list(isf_by_hour_raw.values())) / abs(np.mean(list(isf_by_hour_raw.values())) + 1e-6)
        cv_corrected = np.std(list(isf_by_hour_corrected.values())) / abs(np.mean(list(isf_by_hour_corrected.values())) + 1e-6)
    else:
        cv_raw = np.nan
        cv_corrected = np.nan
    
    # --- Time-window consistency ---
    n = len(pdf)
    thirds = [pdf.iloc[:n//3], pdf.iloc[n//3:2*n//3], pdf.iloc[2*n//3:]]
    isf_devs_raw = []
    isf_devs_corrected = []
    
    for third in thirds:
        t_bgi = compute_bgi(third, isf * cf, activity_curve)
        t_delta = third['glucose'].diff()
        t_carbs_active = third['carbs'].fillna(0).rolling(36, min_periods=1).sum() > 0
        t_mask = (third['glucose'] > 150) & (~t_carbs_active) & (t_delta < 0)
        
        if t_mask.sum() > 20:
            t_dev_raw = (t_delta - t_bgi)[t_mask]
            t_hour = hour.loc[third.index].astype(int)
            t_egp = t_hour.map(lambda h: egp_profile.get(h % 24, 0))
            t_egp = pd.Series(t_egp.values, index=third.index)
            t_dev_corrected = (t_delta - t_bgi - t_egp)[t_mask]
            
            isf_devs_raw.append(float(t_dev_raw.median()))
            isf_devs_corrected.append(float(t_dev_corrected.median()))
    
    window_cv_raw = np.std(isf_devs_raw) / abs(np.mean(isf_devs_raw) + 1e-6) if len(isf_devs_raw) > 1 else np.nan
    window_cv_corrected = np.std(isf_devs_corrected) / abs(np.mean(isf_devs_corrected) + 1e-6) if len(isf_devs_corrected) > 1 else np.nan
    
    # --- Prediction R² comparison ---
    ar1 = delta.shift(1)
    
    # Without EGP
    X_raw = pd.DataFrame({'bgi': bgi, 'ar1': ar1, 'const': 1.0}).dropna()
    y = delta.loc[X_raw.index].dropna()
    valid_raw = X_raw.index.intersection(y.index)
    
    if len(valid_raw) > 200:
        coefs_raw, _, _, _ = lstsq(X_raw.loc[valid_raw].values, y.loc[valid_raw].values, rcond=None)
        pred_raw = X_raw.loc[valid_raw].values @ coefs_raw
        ss_res_raw = np.sum((y.loc[valid_raw].values - pred_raw) ** 2)
        ss_tot = np.sum((y.loc[valid_raw].values - y.loc[valid_raw].mean()) ** 2)
        r2_raw = 1 - ss_res_raw / ss_tot if ss_tot > 0 else 0
    else:
        r2_raw = np.nan
    
    # With EGP
    X_egp = pd.DataFrame({'bgi': bgi, 'ar1': ar1, 'egp': egp_adj, 'const': 1.0}).dropna()
    valid_egp = X_egp.index.intersection(y.index)
    
    if len(valid_egp) > 200:
        coefs_egp, _, _, _ = lstsq(X_egp.loc[valid_egp].values, y.loc[valid_egp].values, rcond=None)
        pred_egp = X_egp.loc[valid_egp].values @ coefs_egp
        ss_res_egp = np.sum((y.loc[valid_egp].values - pred_egp) ** 2)
        ss_tot_egp = np.sum((y.loc[valid_egp].values - y.loc[valid_egp].mean()) ** 2)
        r2_egp = 1 - ss_res_egp / ss_tot_egp if ss_tot_egp > 0 else 0
    else:
        r2_egp = np.nan
    
    return {
        'isf_dev_raw_median': round(float(isf_dev_raw.median()), 3) if corr_mask.sum() > 10 else None,
        'isf_dev_corrected_median': round(float(isf_dev_corrected.median()), 3) if corr_mask.sum() > 10 else None,
        'cr_dev_raw_median': round(float(cr_dev_raw.median()), 3) if meal_mask.sum() > 10 else None,
        'cr_dev_corrected_median': round(float(cr_dev_corrected.median()), 3) if meal_mask.sum() > 10 else None,
        'n_corrections': int(corr_mask.sum()),
        'n_meals': int(meal_mask.sum()),
        'circadian_cv_raw': round(float(cv_raw), 4) if not np.isnan(cv_raw) else None,
        'circadian_cv_corrected': round(float(cv_corrected), 4) if not np.isnan(cv_corrected) else None,
        'window_cv_raw': round(float(window_cv_raw), 4) if not np.isnan(window_cv_raw) else None,
        'window_cv_corrected': round(float(window_cv_corrected), 4) if not np.isnan(window_cv_corrected) else None,
        'r2_raw': round(float(r2_raw), 4) if not np.isnan(r2_raw) else None,
        'r2_egp': round(float(r2_egp), 4) if not np.isnan(r2_egp) else None,
        'egp_range': round(float(egp_profile.max() - egp_profile.min()), 3),
        'egp_mean': round(float(egp_profile.mean()), 3),
    }

def main():
    print("=" * 60)
    print("EXP-2797: EGP-Aware Settings Extraction")
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
        isf = pdf['scheduled_isf'].median()
        cf = 0.2
        
        # Get time-of-day
        if 'time' in pdf.columns:
            hour = pd.to_datetime(pdf['time']).dt.hour + pd.to_datetime(pdf['time']).dt.minute / 60.0
        else:
            hour = ((np.arange(len(pdf)) % 288) * 5 / 60)
        hour = pd.Series(hour.values if hasattr(hour, 'values') else hour, index=pdf.index)
        
        # Step 1: Estimate EGP profile
        bgi = compute_bgi(pdf, isf * cf, activity_curve)
        egp_profile = estimate_egp_profile(pdf, bgi, hour)
        
        # Step 2: Extract settings with and without EGP correction
        settings = extract_settings_with_egp(pdf, activity_curve, egp_profile, hour)
        
        r = {
            'patient_id': pid,
            'controller': ctrl,
            **settings,
        }
        results.append(r)
        
        egp_str = f"EGP range={r['egp_range']:.2f}"
        r2_str = f"R²: {r['r2_raw']:.3f}→{r['r2_egp']:.3f}" if r['r2_raw'] and r['r2_egp'] else "R²: N/A"
        print(f"  {pid:28s} {ctrl:8s} {egp_str} {r2_str}")
    
    rdf = pd.DataFrame(results)
    print(f"\nValid patients: {len(rdf)}")
    
    # ---- Hypothesis Tests ----
    print("\n" + "=" * 60)
    print("HYPOTHESIS RESULTS")
    print("=" * 60)
    
    hyp = {}
    
    # H1: EGP-corrected ISF deviation is LOWER (more negative)
    valid_isf = rdf.dropna(subset=['isf_dev_raw_median', 'isf_dev_corrected_median'])
    if len(valid_isf) > 5:
        isf_diff = valid_isf['isf_dev_corrected_median'] - valid_isf['isf_dev_raw_median']
        pct_lower = (isf_diff < 0).mean()
        hyp['H1_isf_lower'] = pct_lower > 0.5
        print(f"  {'✓ PASS' if hyp['H1_isf_lower'] else '✗ FAIL'}: H1 EGP-corrected ISF lower = "
              f"{pct_lower:.0%} ({(isf_diff < 0).sum()}/{len(valid_isf)})")
        print(f"    Raw median: {valid_isf['isf_dev_raw_median'].median():.3f}")
        print(f"    Corrected median: {valid_isf['isf_dev_corrected_median'].median():.3f}")
    else:
        hyp['H1_isf_lower'] = False
        print("  ✗ FAIL: H1 — insufficient data")
    
    # H2: EGP-corrected settings closer to zero (less bias)
    if len(valid_isf) > 5:
        raw_bias = valid_isf['isf_dev_raw_median'].abs().median()
        corr_bias = valid_isf['isf_dev_corrected_median'].abs().median()
        hyp['H2_closer_zero'] = corr_bias < raw_bias
        print(f"  {'✓ PASS' if hyp['H2_closer_zero'] else '✗ FAIL'}: H2 closer to zero = "
              f"raw |bias|={raw_bias:.3f}, corrected |bias|={corr_bias:.3f}")
    else:
        hyp['H2_closer_zero'] = False
        print("  ✗ FAIL: H2 — insufficient data")
    
    # H3: R² improves with EGP term
    valid_r2 = rdf.dropna(subset=['r2_raw', 'r2_egp'])
    if len(valid_r2) > 5:
        r2_improves = (valid_r2['r2_egp'] > valid_r2['r2_raw']).mean()
        med_r2_raw = valid_r2['r2_raw'].median()
        med_r2_egp = valid_r2['r2_egp'].median()
        hyp['H3_r2_improves'] = r2_improves > 0.5
        print(f"  {'✓ PASS' if hyp['H3_r2_improves'] else '✗ FAIL'}: H3 R² improves = "
              f"{r2_improves:.0%} improve, median {med_r2_raw:.3f}→{med_r2_egp:.3f}")
    else:
        hyp['H3_r2_improves'] = False
        print("  ✗ FAIL: H3 — insufficient data")
    
    # H4: Circadian ISF CV reduces
    valid_cv = rdf.dropna(subset=['circadian_cv_raw', 'circadian_cv_corrected'])
    if len(valid_cv) > 5:
        cv_improves = (valid_cv['circadian_cv_corrected'] < valid_cv['circadian_cv_raw']).mean()
        hyp['H4_cv_reduces'] = cv_improves > 0.5
        print(f"  {'✓ PASS' if hyp['H4_cv_reduces'] else '✗ FAIL'}: H4 circadian CV reduces = "
              f"{cv_improves:.0%} ({(valid_cv['circadian_cv_corrected'] < valid_cv['circadian_cv_raw']).sum()}/{len(valid_cv)})")
        print(f"    Raw CV median: {valid_cv['circadian_cv_raw'].median():.3f}")
        print(f"    Corrected CV median: {valid_cv['circadian_cv_corrected'].median():.3f}")
    else:
        hyp['H4_cv_reduces'] = False
        print("  ✗ FAIL: H4 — insufficient data")
    
    # H5: Window consistency improves
    valid_wcv = rdf.dropna(subset=['window_cv_raw', 'window_cv_corrected'])
    if len(valid_wcv) > 5:
        wcv_improves = (valid_wcv['window_cv_corrected'] < valid_wcv['window_cv_raw']).mean()
        hyp['H5_window_cv'] = wcv_improves > 0.5
        print(f"  {'✓ PASS' if hyp['H5_window_cv'] else '✗ FAIL'}: H5 window CV improves = "
              f"{wcv_improves:.0%} ({(valid_wcv['window_cv_corrected'] < valid_wcv['window_cv_raw']).sum()}/{len(valid_wcv)})")
    else:
        hyp['H5_window_cv'] = False
        print("  ✗ FAIL: H5 — insufficient data")
    
    passed = sum(hyp.values())
    total = len(hyp)
    print(f"\n  TOTAL: {passed}/{total} PASS")
    
    # ---- EGP Profile Summary ----
    print("\n" + "=" * 60)
    print("EGP CORRECTION IMPACT")
    print("=" * 60)
    print(f"  Mean EGP: {rdf['egp_mean'].median():.3f} mg/dL/5min")
    print(f"  EGP range: {rdf['egp_range'].median():.3f} mg/dL/5min (circadian amplitude)")
    
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        cdf = rdf[rdf['controller'] == ctrl]
        if len(cdf) > 0:
            print(f"\n  {ctrl} (N={len(cdf)}):")
            print(f"    EGP mean: {cdf['egp_mean'].median():.3f}, range: {cdf['egp_range'].median():.3f}")
            v = cdf.dropna(subset=['r2_raw', 'r2_egp'])
            if len(v) > 0:
                print(f"    R² raw: {v['r2_raw'].median():.3f}, with EGP: {v['r2_egp'].median():.3f}")
    
    # ---- Visualization ----
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2797: EGP-Aware Settings Extraction', fontsize=14, fontweight='bold')
        
        colors = {'Loop': '#2196F3', 'Trio': '#4CAF50', 'OpenAPS': '#FF9800'}
        
        # 1. R² improvement
        ax = axes[0, 0]
        v = rdf.dropna(subset=['r2_raw', 'r2_egp'])
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            cdf = v[v['controller'] == ctrl]
            ax.scatter(cdf['r2_raw'], cdf['r2_egp'], c=colors[ctrl], label=ctrl,
                      s=60, alpha=0.7, edgecolors='black', linewidths=0.5)
        lim = max(v['r2_raw'].max(), v['r2_egp'].max()) * 1.1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3)
        ax.set_xlabel('R² without EGP')
        ax.set_ylabel('R² with EGP')
        ax.set_title('Prediction R² with EGP Correction')
        ax.legend(fontsize=8)
        
        # 2. ISF deviation: raw vs corrected
        ax = axes[0, 1]
        v = rdf.dropna(subset=['isf_dev_raw_median', 'isf_dev_corrected_median'])
        x = np.arange(len(v))
        ax.bar(x - 0.15, v['isf_dev_raw_median'].values, 0.3, label='Raw', color='#FF9800', alpha=0.6)
        ax.bar(x + 0.15, v['isf_dev_corrected_median'].values, 0.3, label='EGP-corrected', color='#4CAF50', alpha=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels([p[:6] for p in v['patient_id']], rotation=45, fontsize=6)
        ax.axhline(0, color='black', linestyle='-', linewidth=0.5)
        ax.set_ylabel('ISF Deviation (mg/dL/5min)')
        ax.set_title('ISF Deviation: Raw vs EGP-Corrected')
        ax.legend(fontsize=8)
        
        # 3. EGP range by controller
        ax = axes[0, 2]
        for i, ctrl in enumerate(['Loop', 'Trio', 'OpenAPS']):
            cdf = rdf[rdf['controller'] == ctrl]
            ax.boxplot(cdf['egp_range'].dropna().values, positions=[i],
                      widths=0.6, patch_artist=True,
                      boxprops=dict(facecolor=colors[ctrl], alpha=0.5))
        ax.set_xticks([0, 1, 2])
        ax.set_xticklabels(['Loop', 'Trio', 'OpenAPS'])
        ax.set_ylabel('EGP Circadian Range (mg/dL/5min)')
        ax.set_title('Circadian EGP Amplitude by Controller')
        
        # 4. Circadian CV comparison
        ax = axes[1, 0]
        v = rdf.dropna(subset=['circadian_cv_raw', 'circadian_cv_corrected'])
        ax.scatter(v['circadian_cv_raw'], v['circadian_cv_corrected'],
                  c=[colors[c] for c in v['controller']], s=60, alpha=0.7,
                  edgecolors='black', linewidths=0.5)
        lim = max(v['circadian_cv_raw'].max(), v['circadian_cv_corrected'].max()) * 1.1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3)
        ax.set_xlabel('Circadian CV (Raw)')
        ax.set_ylabel('Circadian CV (EGP-Corrected)')
        ax.set_title('Circadian ISF Consistency')
        
        # 5. Window consistency
        ax = axes[1, 1]
        v = rdf.dropna(subset=['window_cv_raw', 'window_cv_corrected'])
        if len(v) > 0:
            ax.scatter(v['window_cv_raw'], v['window_cv_corrected'],
                      c=[colors[c] for c in v['controller']], s=60, alpha=0.7,
                      edgecolors='black', linewidths=0.5)
            lim = max(v['window_cv_raw'].max(), v['window_cv_corrected'].max()) * 1.1
            ax.plot([0, lim], [0, lim], 'k--', alpha=0.3)
        ax.set_xlabel('Window CV (Raw)')
        ax.set_ylabel('Window CV (EGP-Corrected)')
        ax.set_title('Temporal Consistency of ISF')
        
        # 6. Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""EGP-AWARE SETTINGS EXTRACTION

EGP = Endogenous Glucose Production
The body always produces glucose.
EGP varies by time of day (circadian).

After subtracting BGI and AR, ALL
residuals are POSITIVE = EGP signature.

EGP Stats:
  Mean: {rdf['egp_mean'].median():.3f} mg/dL/5min
  Range: {rdf['egp_range'].median():.3f} (circadian)

Impact on Settings Extraction:
  R² improvement: {(rdf.dropna(subset=['r2_raw','r2_egp'])['r2_egp'] > rdf.dropna(subset=['r2_raw','r2_egp'])['r2_raw']).mean():.0%} of patients
  Circadian CV: see plot

{passed}/{total} hypotheses PASS"""
        ax.text(0.05, 0.5, summary, transform=ax.transAxes, fontsize=10,
               verticalalignment='center', fontfamily='monospace',
               bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
        
        plt.tight_layout()
        os.makedirs('tools/visualizations/egp-settings', exist_ok=True)
        plt.savefig('tools/visualizations/egp-settings/exp-2797-dashboard.png', dpi=150)
        plt.close()
        print(f"\nVisualization: tools/visualizations/egp-settings/exp-2797-dashboard.png")
    except Exception as e:
        print(f"\nVisualization failed: {e}")
    
    # ---- Save ----
    output = {
        'experiment': 'EXP-2797',
        'title': 'EGP-Aware Settings Extraction',
        'n_patients': len(rdf),
        'hypotheses': {k: {'pass': bool(v)} for k, v in hyp.items()},
        'passed': passed,
        'total': total,
        'summary': {
            'egp_mean_median': round(float(rdf['egp_mean'].median()), 4),
            'egp_range_median': round(float(rdf['egp_range'].median()), 4),
            'r2_raw_median': round(float(rdf['r2_raw'].dropna().median()), 4),
            'r2_egp_median': round(float(rdf['r2_egp'].dropna().median()), 4),
        },
        'patients': results,
    }
    
    with open('externals/experiments/exp-2797_egp_settings.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results: externals/experiments/exp-2797_egp_settings.json")


if __name__ == '__main__':
    main()
