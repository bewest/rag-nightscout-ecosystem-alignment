#!/usr/bin/env python3
"""EXP-2780: Circadian Basal Rate Optimization

EXP-2779 found that 27/28 patients have significant circadian patterns
in their basal-category residuals. This means EGP varies by time-of-day.

This experiment extracts the circadian EGP profile per patient and
translates it into actionable basal rate recommendations:
- Hours where BG tends to rise → need MORE basal
- Hours where BG tends to fall → need LESS basal (or basal is too high)

The "dawn phenomenon" (rising BG at 4-8am) is the most well-known
circadian pattern. This experiment quantifies it per patient and
identifies other circadian patterns.

Approach:
  1. For each patient, compute median BG delta by hour-of-day
     during basal-category periods (no meals, no corrections)
  2. Compute the "basal adjustment factor" needed to flatten the curve:
     basal_adj[h] = 1 + residual[h] / (profile_ISF × basal_rate/12)
  3. Identify dawn phenomenon amplitude and timing
  4. Compare flat basal vs circadian basal recommendations

Success criteria (3/5 to PASS):
  H1: Dawn phenomenon (4-8am rise) present in >60% of patients
  H2: Circadian amplitude (max-min residual) >20 mg/dL for >50% of patients
  H3: Circadian basal adjustment range >±30% for >50% of patients
  H4: Nighttime (0-4am) and daytime (10-16) have opposite signs
  H5: Per-patient circadian profile has consistent shape (low inter-day variance)
"""

import json, os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

warnings.filterwarnings('ignore')

EXP_ID = "exp-2780"
TITLE = "Circadian Basal Rate Optimization"
OUT_JSON = Path("externals/experiments/exp-2780_circadian_basal.json")
OUT_VIS = Path("tools/visualizations/circadian-basal")
OUT_VIS.mkdir(parents=True, exist_ok=True)

EXCLUDE = {'odc-84181797', 'h', 'j'}
CF = 0.2

def load_grid():
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
    grid['time'] = pd.to_datetime(grid['time'])
    return grid

def identify_basal_periods(df):
    """Identify 'quiet' basal periods: no recent bolus, no carbs, no IOB spike."""
    df = df.copy()
    
    # No bolus in last 2h
    df['recent_bolus'] = df['bolus'].fillna(0).rolling(24, min_periods=1).sum()
    if 'bolus_smb' in df.columns:
        df['recent_smb'] = df['bolus_smb'].fillna(0).rolling(24, min_periods=1).sum()
    else:
        df['recent_smb'] = 0
    
    # No carbs in last 3h
    df['recent_carbs'] = df['carbs'].fillna(0).rolling(36, min_periods=1).sum()
    
    # Low IOB (below 2× scheduled basal rate in units)
    basal_rate_u = df['scheduled_basal_rate'].fillna(0) / 12.0  # per 5min
    iob_threshold = 24 * basal_rate_u  # 2h worth of basal
    
    basal_mask = (
        (df['recent_bolus'] < 0.05) & 
        (df['recent_smb'] < 0.5) &  # Allow small SMBs for Trio
        (df['recent_carbs'] < 1) &
        (df['iob'].fillna(0) < iob_threshold.clip(lower=0.5))
    )
    
    return basal_mask

def analyze_patient_circadian(patient_df, pid):
    """Extract circadian glucose pattern during basal periods."""
    df = patient_df.sort_values('time').copy()
    
    profile_isf = df['scheduled_isf'].median()
    basal_rate = df['scheduled_basal_rate'].median()
    if pd.isna(profile_isf) or profile_isf <= 0 or pd.isna(basal_rate) or basal_rate <= 0:
        return None
    
    # 1h glucose delta (short window for circadian — just trend)
    df['glucose_delta_1h'] = df['glucose'].shift(-12) - df['glucose']
    df['hour'] = df['time'].dt.hour
    
    # Identify basal periods
    df['is_basal'] = identify_basal_periods(df)
    
    basal_df = df[df['is_basal']].dropna(subset=['glucose_delta_1h'])
    
    if len(basal_df) < 200:
        return None
    
    # Per-hour statistics
    hourly = {}
    for h in range(24):
        hdf = basal_df[basal_df['hour'] == h]
        if len(hdf) < 5:
            hourly[h] = {'n': 0, 'mean_delta': 0, 'sem': 0, 'mean_bg': 0}
            continue
        
        deltas = hdf['glucose_delta_1h'].values
        hourly[h] = {
            'n': len(hdf),
            'mean_delta': float(np.mean(deltas)),
            'median_delta': float(np.median(deltas)),
            'sem': float(stats.sem(deltas)),
            'mean_bg': float(hdf['glucose'].mean()),
            'std_delta': float(np.std(deltas)),
        }
    
    # Circadian profile
    hours = sorted(hourly.keys())
    profile = [hourly[h]['mean_delta'] for h in hours]
    
    # Dawn phenomenon: average delta at hours 4-8
    dawn_delta = np.mean([hourly[h]['mean_delta'] for h in range(4, 9) if hourly[h]['n'] > 0])
    
    # Night delta: hours 0-4
    night_delta = np.mean([hourly[h]['mean_delta'] for h in range(0, 4) if hourly[h]['n'] > 0])
    
    # Day delta: hours 10-16
    day_delta = np.mean([hourly[h]['mean_delta'] for h in range(10, 17) if hourly[h]['n'] > 0])
    
    # Evening delta: hours 18-23
    evening_delta = np.mean([hourly[h]['mean_delta'] for h in range(18, 24) if hourly[h]['n'] > 0])
    
    # Amplitude
    max_delta = max(profile)
    min_delta = min(profile)
    amplitude = max_delta - min_delta
    
    # Basal adjustment needed
    # If BG rises by X mg/dL/h during basal, we need additional insulin:
    # additional_insulin = X / ISF (units per hour)
    # basal_adj_factor = 1 + additional_insulin / basal_rate
    adj_factors = {}
    for h in hours:
        delta = hourly[h]['mean_delta']
        additional = delta / (profile_isf * CF)  # Use CF-adjusted ISF
        adj = 1 + additional / (basal_rate + 1e-6)
        adj_factors[h] = round(adj, 3)
    
    adj_range = max(adj_factors.values()) - min(adj_factors.values())
    
    # Dawn phenomenon: significant rise at 4-8?
    dawn_hours = [h for h in range(4, 9) if hourly[h]['n'] > 5]
    has_dawn = dawn_delta > 3  # >3 mg/dL/h rise
    
    # Inter-day consistency: coefficient of variation of deltas per hour
    consistency_cvs = []
    for h in hours:
        hdf = basal_df[basal_df['hour'] == h]
        if len(hdf) > 10:
            cv = np.std(hdf['glucose_delta_1h']) / (abs(np.mean(hdf['glucose_delta_1h'])) + 1)
            consistency_cvs.append(cv)
    
    mean_cv = np.mean(consistency_cvs) if consistency_cvs else 999
    
    return {
        'patient_id': pid,
        'n_basal_periods': len(basal_df),
        'pct_basal': round(len(basal_df) / len(df) * 100, 1),
        'profile_isf': round(profile_isf, 1),
        'basal_rate': round(basal_rate, 2),
        'circadian': {
            'dawn_delta': round(dawn_delta, 1),
            'night_delta': round(night_delta, 1),
            'day_delta': round(day_delta, 1),
            'evening_delta': round(evening_delta, 1),
            'amplitude': round(amplitude, 1),
            'max_hour': int(hours[np.argmax(profile)]),
            'min_hour': int(hours[np.argmin(profile)]),
            'has_dawn': has_dawn,
        },
        'basal_adjustment': {
            'adj_factors': adj_factors,
            'adj_range': round(adj_range, 3),
            'max_adj': round(max(adj_factors.values()), 3),
            'min_adj': round(min(adj_factors.values()), 3),
        },
        'hourly': hourly,
        'inter_day_cv': round(mean_cv, 2),
    }

def main():
    print(f"{'='*60}")
    print(f"EXP-2780: {TITLE}")
    print(f"{'='*60}\n")
    
    grid = load_grid()
    patients = sorted(grid['patient_id'].unique())
    print(f"Patients: {len(patients)}")
    
    results = {}
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        r = analyze_patient_circadian(pdf, pid)
        if r is None:
            print(f"  {pid}: skipped (insufficient basal periods)")
            continue
        
        results[pid] = r
        c = r['circadian']
        ba = r['basal_adjustment']
        dawn_str = "DAWN" if c['has_dawn'] else "    "
        print(f"  {pid}: {dawn_str} dawn={c['dawn_delta']:+.1f} amp={c['amplitude']:.0f} "
              f"adj_range={ba['adj_range']:.0f}% basal_pct={r['pct_basal']:.0f}% "
              f"n={r['n_basal_periods']}")
    
    if not results:
        print("ERROR: No results")
        sys.exit(1)
    
    n = len(results)
    
    # Aggregate
    print(f"\n{'='*60}")
    print(f"AGGREGATE (N={n})")
    print(f"{'='*60}")
    
    dawn_deltas = [r['circadian']['dawn_delta'] for r in results.values()]
    amplitudes = [r['circadian']['amplitude'] for r in results.values()]
    adj_ranges = [r['basal_adjustment']['adj_range'] for r in results.values()]
    
    print(f"\nDawn phenomenon (4-8am):")
    print(f"  Median delta: {np.median(dawn_deltas):+.1f} mg/dL/h")
    n_dawn = sum(1 for r in results.values() if r['circadian']['has_dawn'])
    print(f"  Patients with dawn (>3 mg/dL/h): {n_dawn}/{n} ({n_dawn/n*100:.0f}%)")
    
    print(f"\nCircadian amplitude (max-min):")
    print(f"  Median: {np.median(amplitudes):.0f} mg/dL/h")
    n_large = sum(1 for a in amplitudes if a > 20)
    print(f"  >20 mg/dL/h: {n_large}/{n} ({n_large/n*100:.0f}%)")
    
    print(f"\nBasal adjustment range:")
    print(f"  Median: {np.median(adj_ranges):.0f}%")
    n_wide = sum(1 for a in adj_ranges if a > 0.3)
    print(f"  >±30%: {n_wide}/{n} ({n_wide/n*100:.0f}%)")
    
    # Time-of-day pattern
    print(f"\nPeriod deltas (median across patients):")
    for period, key in [('Night (0-4)', 'night_delta'), ('Dawn (4-8)', 'dawn_delta'),
                        ('Day (10-16)', 'day_delta'), ('Evening (18-23)', 'evening_delta')]:
        vals = [r['circadian'][key] for r in results.values()]
        print(f"  {period}: {np.median(vals):+.1f} mg/dL/h")
    
    # Aggregate circadian profile
    print(f"\nHourly profile (median BG delta during basal):")
    for h in range(24):
        vals = [r['hourly'][h]['mean_delta'] for r in results.values() if r['hourly'][h]['n'] > 0]
        if vals:
            bar_len = int(abs(np.median(vals)) / 2)
            bar = '+' * bar_len if np.median(vals) > 0 else '-' * bar_len
            print(f"  {h:02d}:00  {np.median(vals):+5.1f}  {bar}")
    
    # Hypothesis testing
    h1 = n_dawn / n > 0.6
    h2 = n_large / n > 0.5
    h3 = n_wide / n > 0.5
    
    # H4: Night and day have opposite signs
    night_med = np.median([r['circadian']['night_delta'] for r in results.values()])
    day_med = np.median([r['circadian']['day_delta'] for r in results.values()])
    h4 = (night_med > 0 and day_med < 0) or (night_med < 0 and day_med > 0)
    
    # H5: Low inter-day CV (<3)
    cvs = [r['inter_day_cv'] for r in results.values()]
    h5 = np.median(cvs) < 3
    
    hypotheses = {
        'H1_dawn_gt60pct': {'pass': bool(h1),
            'value': f"{n_dawn}/{n} ({n_dawn/n*100:.0f}%)"},
        'H2_amplitude_gt20': {'pass': bool(h2),
            'value': f"{n_large}/{n} ({n_large/n*100:.0f}%), median={np.median(amplitudes):.0f}"},
        'H3_adj_range_gt30pct': {'pass': bool(h3),
            'value': f"{n_wide}/{n} ({n_wide/n*100:.0f}%), median={np.median(adj_ranges):.2f}"},
        'H4_night_day_opposite': {'pass': bool(h4),
            'value': f"night={night_med:+.1f}, day={day_med:+.1f}"},
        'H5_consistent_shape': {'pass': bool(h5),
            'value': f"median CV={np.median(cvs):.1f}"},
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
        fig.suptitle(f'EXP-2780: Circadian Basal Rate Optimization — {n_pass}/5 PASS', fontsize=14, fontweight='bold')
        
        # Panel 1: Aggregate circadian profile
        ax = axes[0, 0]
        hours = list(range(24))
        median_profile = []
        q25_profile = []
        q75_profile = []
        for h in hours:
            vals = [r['hourly'][h]['mean_delta'] for r in results.values() if r['hourly'][h]['n'] > 0]
            median_profile.append(np.median(vals) if vals else 0)
            q25_profile.append(np.percentile(vals, 25) if vals else 0)
            q75_profile.append(np.percentile(vals, 75) if vals else 0)
        
        ax.fill_between(hours, q25_profile, q75_profile, alpha=0.3, color='steelblue')
        ax.plot(hours, median_profile, 'o-', color='steelblue', linewidth=2)
        ax.axhline(y=0, color='red', linestyle='--')
        ax.axvspan(4, 8, alpha=0.1, color='orange', label='Dawn window')
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('BG Delta (mg/dL/h)')
        ax.set_title('Circadian BG Pattern (Basal Periods)')
        ax.legend()
        ax.set_xticks(range(0, 24, 3))
        
        # Panel 2: Per-patient circadian profiles
        ax = axes[0, 1]
        for r in list(results.values())[:10]:
            profile = [r['hourly'][h]['mean_delta'] for h in hours]
            ax.plot(hours, profile, alpha=0.3, linewidth=1)
        ax.axhline(y=0, color='red', linestyle='--')
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('BG Delta (mg/dL/h)')
        ax.set_title('Individual Circadian Profiles (first 10)')
        ax.set_xticks(range(0, 24, 3))
        
        # Panel 3: Dawn phenomenon distribution
        ax = axes[1, 0]
        dawn_vals = sorted([r['circadian']['dawn_delta'] for r in results.values()])
        colors = ['coral' if d > 3 else 'steelblue' for d in dawn_vals]
        ax.barh(range(len(dawn_vals)), dawn_vals, color=colors)
        ax.axvline(x=3, color='red', linestyle='--', label='Dawn threshold (3 mg/dL/h)')
        ax.axvline(x=0, color='black', linestyle='-')
        ax.set_xlabel('Dawn BG Rise (mg/dL/h)')
        ax.set_title(f'Dawn Phenomenon: {n_dawn}/{n} patients')
        ax.legend()
        
        # Panel 4: Basal adjustment factor example
        ax = axes[1, 1]
        # Show the patient with most dramatic circadian pattern
        best_pid = max(results.keys(), key=lambda p: results[p]['circadian']['amplitude'])
        adj = results[best_pid]['basal_adjustment']['adj_factors']
        vals = [adj[h] for h in range(24)]
        colors = ['coral' if v > 1 else 'steelblue' for v in vals]
        ax.bar(range(24), vals, color=colors, alpha=0.7)
        ax.axhline(y=1, color='black', linestyle='--')
        ax.set_xlabel('Hour of Day')
        ax.set_ylabel('Basal Rate Multiplier')
        ax.set_title(f'Basal Adjustment: {best_pid[:15]} (amp={results[best_pid]["circadian"]["amplitude"]:.0f})')
        ax.set_xticks(range(0, 24, 3))
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2780-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2780-dashboard.png'}")
    except Exception as e:
        print(f"Visualization error: {e}")
    
    # Save
    output = {
        'experiment': EXP_ID,
        'title': TITLE,
        'n_patients': n,
        'hypotheses': hypotheses,
        'pass_count': f"{n_pass}/5",
        'aggregate': {
            'median_dawn_delta': round(np.median(dawn_deltas), 1),
            'median_amplitude': round(np.median(amplitudes), 1),
            'n_dawn': n_dawn,
            'pct_dawn': round(n_dawn / n * 100, 1),
            'median_adj_range': round(np.median(adj_ranges), 3),
        },
        'per_patient': {pid: {k: v for k, v in r.items() if k != 'hourly'} 
                       for pid, r in results.items()},
        'aggregate_hourly_profile': {str(h): round(m, 2) for h, m in zip(hours, median_profile)}
            if 'median_profile' in dir() else {},
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: {OUT_JSON}")

if __name__ == '__main__':
    main()
