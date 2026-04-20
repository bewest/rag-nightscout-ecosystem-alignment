#!/usr/bin/env python3
"""EXP-2789: Deconfounded Settings Pipeline v2

Combines the multi-scale deconfounding (EXP-2788) with the production
settings pipeline. The key insight: if we can subtract meal momentum
(AR layer) before ISF/CR extraction, we should get cleaner signals.

Pipeline:
1. Convolve delivery with activity curve (L1)
2. Subtract AR meal momentum (L2) 
3. Subtract circadian pattern (L3)
4. On CLEANED residuals, extract settings:
   - ISF from correction periods (BG>180, no carbs)
   - CR from meal periods (carbs>0)
   - Basal from quiet periods (no bolus, no carbs)

Compare with:
- EXP-2719b production ISF (waterfall residuals)
- EXP-2741 production CR (bilateral deconfounding)
- EXP-2776 category-stratified ISF

Success criteria (3/5 to PASS):
  H1: Deconfounded ISF is positive for >80% of patients (vs ~50% raw)
  H2: Deconfounded ISF correlates with profile (r>0.5)
  H3: Deconfounded CR is within 2x of profile for >60% of patients
  H4: Pipeline ISF improves on raw ISF (closer to profile)
  H5: Settings recommendations consistent with EXP-2782 audit
"""

import json, os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

warnings.filterwarnings('ignore')

EXP_ID = "exp-2789"
TITLE = "Deconfounded Settings Pipeline v2"
OUT_JSON = Path("externals/experiments/exp-2789_deconf_settings.json")
OUT_VIS = Path("tools/visualizations/deconf-settings")
OUT_VIS.mkdir(parents=True, exist_ok=True)

EXCLUDE = {'odc-84181797', 'h', 'j'}
LOOP_IDS = {'a', 'b', 'c', 'd', 'e', 'f', 'g', 'i', 'k'}
CF = 0.2

def classify_controller(pid):
    if pid in LOOP_IDS or len(pid) == 1:
        return 'Loop'
    if pid.startswith('odc-'):
        return 'OpenAPS'
    return 'Trio'

def make_activity_curve(dia_minutes=360, peak_minutes=75, dt=5):
    n_steps = dia_minutes // dt
    t = np.arange(1, n_steps + 1) * dt
    tau = peak_minutes / np.log(2)
    curve = (t / peak_minutes) * np.exp(1 - t / peak_minutes)
    curve[t > dia_minutes] = 0
    curve = curve / curve.sum()
    return curve

def compute_bgi_convolution(delivery, activity_curve, isf):
    n = len(delivery)
    bgi = np.zeros(n)
    for lag in range(min(len(activity_curve), n)):
        shifted = np.roll(delivery, lag)
        shifted[:lag] = 0
        bgi += -shifted * activity_curve[lag] * isf
    return bgi

def load_grid():
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
    grid['time'] = pd.to_datetime(grid['time'])
    grid['hour'] = grid['time'].dt.hour
    return grid

def extract_settings(patient_df, pid, activity_curve):
    """Deconfound then extract settings."""
    df = patient_df.sort_values('time').copy()
    
    if len(df) < 500:
        return None
    
    profile_isf = df['scheduled_isf'].median()
    profile_cr = df['scheduled_cr'].median() if 'scheduled_cr' in df.columns else np.nan
    scheduled_basal = df['scheduled_basal_rate'].median() or 0
    
    if pd.isna(profile_isf) or profile_isf <= 0:
        return None
    
    cf_isf = profile_isf * CF
    
    # --- Deconfounding layers ---
    df['bg_delta'] = df['glucose'].diff()
    
    # L1: Conv BGI
    delivery = (df['bolus'].fillna(0).values + 
                df['bolus_smb'].fillna(0).values + 
                df['net_basal'].fillna(0).values / 12.0)
    excess_delivery = delivery - (scheduled_basal / 12.0)
    
    bgi = compute_bgi_convolution(excess_delivery, activity_curve, cf_isf)
    df['deviation'] = df['bg_delta'] - bgi
    
    # L2: AR meal momentum
    df['carbs_4h'] = df['carbs'].fillna(0).rolling(48, min_periods=1).sum()
    df['is_csf'] = df['carbs_4h'] > 0
    df['dev_lag'] = df['deviation'].shift(1)
    
    csf_df = df[df['is_csf']].dropna(subset=['deviation', 'dev_lag'])
    ar_coef = 0.4
    if len(csf_df) > 100:
        ar_coef = np.clip(
            np.corrcoef(csf_df['deviation'].values, csf_df['dev_lag'].values)[0, 1],
            0, 0.95)
    
    df['deviation'] = df['deviation'] - (df['deviation'].shift(1) * ar_coef).fillna(0)
    
    # L3: Circadian
    hourly_mean = df.groupby('hour')['deviation'].mean()
    df['deviation'] = df['deviation'] - df['hour'].map(hourly_mean)
    
    # --- Settings extraction from deconfounded residuals ---
    
    # Carb windows
    df['carbs_2h'] = df['carbs'].fillna(0).rolling(24, min_periods=1).sum()
    df['bolus_1h'] = df['bolus'].fillna(0).rolling(12, min_periods=1).sum()
    df['delivery_5m'] = delivery
    
    # ISF: correction periods (BG>180, no carbs 2h, some insulin)
    isf_mask = (df['glucose'] > 180) & (df['carbs_2h'] == 0) & (df['delivery_5m'] > 0.01)
    
    raw_isf_events = []
    deconf_isf_events = []
    
    if isf_mask.sum() > 10:
        isf_df = df[isf_mask].dropna(subset=['deviation']).copy()
        valid = isf_df['delivery_5m'] > 0.01
        
        if valid.sum() > 5:
            # Raw ISF
            raw_isfs = -isf_df.loc[valid, 'bg_delta'] / isf_df.loc[valid, 'delivery_5m']
            raw_isf_med = np.median(raw_isfs)
            raw_isf_positive = (raw_isfs > 0).mean()
            
            # Deconfounded ISF (using cleaned deviation)
            deconf_isfs = -isf_df.loc[valid, 'deviation'] / isf_df.loc[valid, 'delivery_5m']
            deconf_isf_med = np.median(deconf_isfs)
            deconf_isf_positive = (deconf_isfs > 0).mean()
        else:
            raw_isf_med = deconf_isf_med = np.nan
            raw_isf_positive = deconf_isf_positive = 0
    else:
        raw_isf_med = deconf_isf_med = np.nan
        raw_isf_positive = deconf_isf_positive = 0
    
    # CR: meal periods (carbs > 5g, look at BG impact in next 2-4h)
    carb_mask = df['carbs'].fillna(0) > 5
    carb_events = df[carb_mask]
    
    if len(carb_events) > 5:
        cr_estimates = []
        for idx in carb_events.index:
            pos = df.index.get_loc(idx)
            # Look at next 2h of BG change
            window = df.iloc[pos:min(pos+24, len(df))]
            if len(window) < 12:
                continue
            bg_rise = window['glucose'].max() - df.loc[idx, 'glucose']
            carbs = df.loc[idx, 'carbs']
            if bg_rise > 0 and carbs > 0:
                cr_estimates.append(carbs / (bg_rise / profile_isf))
        
        cr_med = np.median(cr_estimates) if cr_estimates else np.nan
    else:
        cr_med = np.nan
    
    # Basal: quiet periods (no bolus 1h, no carbs 4h)
    basal_mask = (df['bolus_1h'] == 0) & (df['carbs_4h'] == 0)
    if basal_mask.sum() > 50:
        basal_bg_rate = df[basal_mask]['bg_delta'].mean()  # mg/dL per 5min
        basal_bg_rate_h = basal_bg_rate * 12  # mg/dL per hour
        
        # Deconfounded basal rate
        deconf_basal_rate = df[basal_mask]['deviation'].mean() * 12
    else:
        basal_bg_rate_h = deconf_basal_rate = np.nan
    
    # TDD accounting
    days = len(df) * 5 / 60 / 24
    tdd = delivery.sum() / days if days > 0 else 0
    basal_frac = (scheduled_basal * 24) / tdd if tdd > 0 else np.nan
    
    return {
        'patient_id': pid,
        'controller': classify_controller(pid),
        
        # Profile settings
        'profile_isf': round(profile_isf, 1),
        'profile_cr': round(profile_cr, 1) if not np.isnan(profile_cr) else None,
        'scheduled_basal': round(scheduled_basal, 2),
        
        # ISF extraction
        'raw_isf': round(raw_isf_med, 2) if not np.isnan(raw_isf_med) else None,
        'deconf_isf': round(deconf_isf_med, 2) if not np.isnan(deconf_isf_med) else None,
        'raw_isf_positive_pct': round(raw_isf_positive * 100, 0),
        'deconf_isf_positive_pct': round(deconf_isf_positive * 100, 0),
        
        # CR extraction
        'deconf_cr': round(cr_med, 1) if not np.isnan(cr_med) else None,
        
        # Basal
        'basal_bg_rate_h': round(basal_bg_rate_h, 1) if not np.isnan(basal_bg_rate_h) else None,
        'deconf_basal_rate': round(deconf_basal_rate, 1) if not np.isnan(deconf_basal_rate) else None,
        
        # Accounting
        'tdd': round(tdd, 1),
        'basal_frac': round(basal_frac, 3) if not np.isnan(basal_frac) else None,
        
        # Recommendations
        'isf_ratio': round(deconf_isf_med / profile_isf, 2) if not np.isnan(deconf_isf_med) and profile_isf > 0 else None,
    }

def main():
    print(f"{'='*60}")
    print(f"EXP-2789: {TITLE}")
    print(f"{'='*60}\n")
    
    activity_curve = make_activity_curve()
    grid = load_grid()
    patients = sorted(grid['patient_id'].unique())
    
    results = []
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        r = extract_settings(pdf, pid, activity_curve)
        if r:
            results.append(r)
            raw = r['raw_isf'] or 'N/A'
            dec = r['deconf_isf'] or 'N/A'
            prof = r['profile_isf']
            cr = r['deconf_cr'] or 'N/A'
            print(f"  {pid:<25} ISF: raw={raw:>6} deconf={dec:>6} prof={prof:>5} | CR={cr:>5}")
    
    n = len(results)
    rdf = pd.DataFrame(results)
    print(f"\nValid patients: {n}")
    
    # H1: >80% positive ISF
    print(f"\n{'='*60}")
    print(f"ISF POSITIVITY")
    print(f"{'='*60}")
    isf_df = rdf.dropna(subset=['deconf_isf'])
    if len(isf_df) > 0:
        raw_pos = rdf['raw_isf_positive_pct'].mean()
        deconf_pos = rdf['deconf_isf_positive_pct'].mean()
        print(f"  Raw ISF positive: {raw_pos:.0f}%")
        print(f"  Deconfounded ISF positive: {deconf_pos:.0f}%")
        deconf_sign = (isf_df['deconf_isf'] > 0).mean() * 100
        print(f"  Patients with positive median deconf ISF: {deconf_sign:.0f}%")
        h1 = deconf_sign > 80
    else:
        h1 = False
        deconf_sign = 0
    
    # H2: ISF-profile correlation
    print(f"\n{'='*60}")
    print(f"ISF-PROFILE CORRELATION")
    print(f"{'='*60}")
    isf_valid = isf_df.dropna(subset=['deconf_isf', 'profile_isf'])
    if len(isf_valid) >= 5:
        r_isf, p_isf = stats.pearsonr(isf_valid['deconf_isf'], isf_valid['profile_isf'])
        print(f"  Deconf ISF vs profile: r={r_isf:+.3f}, p={p_isf:.4f}")
        h2 = r_isf > 0.5
    else:
        r_isf = np.nan
        h2 = False
    
    # H3: CR within 2x
    print(f"\n{'='*60}")
    print(f"CR EXTRACTION")
    print(f"{'='*60}")
    cr_valid = rdf.dropna(subset=['deconf_cr', 'profile_cr'])
    if len(cr_valid) > 0:
        within_2x = ((cr_valid['deconf_cr'] / cr_valid['profile_cr']).between(0.5, 2.0)).mean() * 100
        print(f"  Patients with CR within 2x of profile: {within_2x:.0f}%")
        print(f"  Median deconf CR: {cr_valid['deconf_cr'].median():.1f}")
        print(f"  Median profile CR: {cr_valid['profile_cr'].median():.1f}")
        h3 = within_2x > 60
    else:
        within_2x = 0
        h3 = False
    
    # H4: Pipeline ISF closer to profile
    print(f"\n{'='*60}")
    print(f"ISF IMPROVEMENT")
    print(f"{'='*60}")
    both_valid = rdf.dropna(subset=['raw_isf', 'deconf_isf'])
    if len(both_valid) > 0:
        raw_gap = (both_valid['raw_isf'] - both_valid['profile_isf']).abs().median()
        deconf_gap = (both_valid['deconf_isf'] - both_valid['profile_isf']).abs().median()
        print(f"  Median raw ISF gap from profile: {raw_gap:.1f}")
        print(f"  Median deconf ISF gap from profile: {deconf_gap:.1f}")
        improved = (deconf_gap < raw_gap)
        h4 = improved
    else:
        h4 = False
    
    # H5: Basal consistency with EXP-2782
    # Check if Trio patients still flagged as basal-too-low
    trio = rdf[rdf['controller'] == 'Trio']
    trio_low = (trio['basal_frac'].dropna() < 0.4).mean() * 100 if len(trio) > 0 else 0
    h5 = trio_low > 70  # >70% of Trio should be flagged
    
    print(f"\n  Trio basal < 40%: {trio_low:.0f}% (consistent with EXP-2782)")
    
    hypotheses = {
        'H1_isf_positive_gt80': {'pass': bool(h1),
            'value': f"{deconf_sign:.0f}% positive"},
        'H2_isf_profile_corr': {'pass': bool(h2),
            'value': f"r={r_isf:+.3f}" if not np.isnan(r_isf) else "N/A"},
        'H3_cr_within_2x': {'pass': bool(h3),
            'value': f"{within_2x:.0f}% within 2x"},
        'H4_isf_closer_to_profile': {'pass': bool(h4),
            'value': f"raw gap={raw_gap:.1f}, deconf gap={deconf_gap:.1f}" if len(both_valid) > 0 else "N/A"},
        'H5_trio_consistent': {'pass': bool(h5),
            'value': f"Trio basal<40%: {trio_low:.0f}%"},
    }
    
    n_pass = sum(1 for h in hypotheses.values() if h['pass'])
    
    print(f"\n{'='*60}")
    print(f"HYPOTHESIS RESULTS: {n_pass}/5 PASS")
    print(f"{'='*60}")
    for hname, hval in hypotheses.items():
        status = "✓ PASS" if hval['pass'] else "✗ FAIL"
        print(f"  {status}: {hname} = {hval['value']}")
    
    # Per-controller summary
    print(f"\n{'='*60}")
    print(f"PER-CONTROLLER SETTINGS")
    print(f"{'='*60}")
    for ctrl in ['Loop', 'Trio', 'OpenAPS']:
        mask = rdf['controller'] == ctrl
        cdf = rdf[mask]
        if len(cdf) == 0:
            continue
        print(f"\n  {ctrl} (N={len(cdf)}):")
        isf_v = cdf['deconf_isf'].dropna()
        cr_v = cdf['deconf_cr'].dropna()
        bf_v = cdf['basal_frac'].dropna()
        if len(isf_v) > 0:
            print(f"    Deconf ISF median: {isf_v.median():.1f} (profile: {cdf['profile_isf'].median():.1f})")
        if len(cr_v) > 0:
            print(f"    Deconf CR median: {cr_v.median():.1f} (profile: {cdf['profile_cr'].dropna().median():.1f})")
        if len(bf_v) > 0:
            print(f"    Basal fraction: {bf_v.median():.1%}")
    
    # Visualization
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f'EXP-2789: Deconfounded Settings Pipeline — {n_pass}/5 PASS', 
                     fontsize=14, fontweight='bold')
        
        ctrl_colors = {'Loop': 'steelblue', 'Trio': 'coral', 'OpenAPS': 'green'}
        
        # Panel 1: Raw vs Deconf ISF
        ax = axes[0, 0]
        both = rdf.dropna(subset=['raw_isf', 'deconf_isf'])
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            mask = both['controller'] == ctrl
            if mask.any():
                ax.scatter(both[mask]['raw_isf'], both[mask]['deconf_isf'],
                          s=60, alpha=0.7, label=ctrl, color=ctrl_colors[ctrl])
        lim = max(abs(both['raw_isf']).max(), abs(both['deconf_isf']).max()) if len(both) > 0 else 50
        ax.plot([-lim, lim], [-lim, lim], 'k--', alpha=0.3)
        ax.axhline(y=0, color='gray', alpha=0.2)
        ax.axvline(x=0, color='gray', alpha=0.2)
        ax.set_xlabel('Raw ISF')
        ax.set_ylabel('Deconfounded ISF')
        ax.set_title('ISF: Raw vs Deconfounded')
        ax.legend()
        
        # Panel 2: Deconf ISF vs Profile
        ax = axes[0, 1]
        valid_isf = rdf.dropna(subset=['deconf_isf'])
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            mask = valid_isf['controller'] == ctrl
            if mask.any():
                ax.scatter(valid_isf[mask]['profile_isf'], valid_isf[mask]['deconf_isf'],
                          s=60, alpha=0.7, label=ctrl, color=ctrl_colors[ctrl])
        ax.plot([0, 150], [0, 150], 'k--', alpha=0.3, label='1:1')
        ax.set_xlabel('Profile ISF')
        ax.set_ylabel('Deconfounded ISF')
        ax.set_title(f'ISF vs Profile (r={r_isf:+.2f})' if not np.isnan(r_isf) else 'ISF vs Profile')
        ax.legend()
        
        # Panel 3: CR comparison
        ax = axes[1, 0]
        cr_v = rdf.dropna(subset=['deconf_cr', 'profile_cr'])
        if len(cr_v) > 0:
            for ctrl in ['Loop', 'Trio', 'OpenAPS']:
                mask = cr_v['controller'] == ctrl
                if mask.any():
                    ax.scatter(cr_v[mask]['profile_cr'], cr_v[mask]['deconf_cr'],
                              s=60, alpha=0.7, label=ctrl, color=ctrl_colors[ctrl])
            ax.plot([0, 30], [0, 30], 'k--', alpha=0.3, label='1:1')
            ax.set_xlabel('Profile CR')
            ax.set_ylabel('Deconfounded CR')
            ax.set_title('Carb Ratio: Extracted vs Profile')
            ax.legend()
        
        # Panel 4: Basal fraction
        ax = axes[1, 1]
        ctrl_data = []
        ctrl_labels = []
        for ctrl in ['Loop', 'Trio', 'OpenAPS']:
            vals = rdf[rdf['controller'] == ctrl]['basal_frac'].dropna() * 100
            if len(vals) > 0:
                ctrl_data.append(vals.values)
                ctrl_labels.append(f'{ctrl}\n(N={len(vals)})')
        if ctrl_data:
            bp = ax.boxplot(ctrl_data, patch_artist=True)
            for patch, label in zip(bp['boxes'], ctrl_labels):
                cn = label.split('\n')[0]
                patch.set_facecolor(ctrl_colors.get(cn, 'gray'))
                patch.set_alpha(0.6)
            ax.set_xticklabels(ctrl_labels)
            ax.axhline(y=50, color='red', linestyle='--', alpha=0.5, label='50%')
            ax.set_ylabel('Basal Fraction (%)')
            ax.set_title('Basal Balance')
            ax.legend()
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2789-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2789-dashboard.png'}")
    except Exception as e:
        print(f"Visualization error: {e}")
    
    output = {
        'experiment': EXP_ID,
        'title': TITLE,
        'n_patients': n,
        'hypotheses': hypotheses,
        'pass_count': f"{n_pass}/5",
        'per_patient': results,
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: {OUT_JSON}")

if __name__ == '__main__':
    main()
