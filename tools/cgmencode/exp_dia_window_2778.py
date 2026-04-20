#!/usr/bin/env python3
"""EXP-2778: DIA-Matched Window ISF Extraction

EXP-2777 showed ISF is NEGATIVE at 2h windows because confounding by
indication dominates short windows — BG is still rising when we measure.

Insulin's DIA is 5-6 hours. The full glucose-lowering effect of a bolus 
takes 3-6h to manifest. By extending the measurement window to match DIA,
we should see the true negative (glucose-lowering) effect of insulin.

We also use a key refinement: require BG to be FALLING at end of window
to select true correction episodes (not meal boluses where BG keeps rising).

Approach:
  1. Try windows from 2h to 6h (12, 24, 36, 48, 60, 72 5-min steps)
  2. For each window, extract ISF via regression
  3. Compare ISF magnitudes and signs across windows
  4. The optimal window should give ISF closest to profile

Success criteria (3/5 to PASS):
  H1: Longer windows give MORE POSITIVE ISF (insulin appears to lower BG more)
  H2: 5-6h window ISF is >5x the 2h window ISF  
  H3: 5-6h window has >70% patients with positive ISF
  H4: Optimal window ISF correlates with profile ISF (r>0.5)
  H5: Adding "BG falling at end" filter further improves ISF positivity
"""

import json, os, sys, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression
from scipy import stats

warnings.filterwarnings('ignore')

EXP_ID = "exp-2778"
TITLE = "DIA-Matched Window ISF Extraction"
OUT_JSON = Path("externals/experiments/exp-2778_dia_window.json")
OUT_VIS = Path("tools/visualizations/dia-window")
OUT_VIS.mkdir(parents=True, exist_ok=True)

EXCLUDE = {'odc-84181797', 'h', 'j'}

WINDOWS = [12, 24, 36, 48, 60, 72]  # 1h, 2h, 3h, 4h, 5h, 6h
WINDOW_LABELS = ['1h', '2h', '3h', '4h', '5h', '6h']

def load_grid():
    grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
    grid['time'] = pd.to_datetime(grid['time'])
    return grid

def extract_isf_at_window(patient_df, window_steps, require_falling=False):
    """Extract ISF using a given window size."""
    df = patient_df.sort_values('time').copy()
    
    profile_isf = df['scheduled_isf'].median()
    if pd.isna(profile_isf) or profile_isf <= 0:
        return None
    
    # Glucose change over window
    df['glucose_end'] = df['glucose'].shift(-window_steps)
    df['glucose_delta'] = df['glucose_end'] - df['glucose']
    df['starting_bg'] = df['glucose']
    
    # Total excess insulin over window (all channels)
    bolus_sum = df['bolus'].fillna(0).rolling(window_steps, min_periods=1).sum()
    smb_sum = df['bolus_smb'].fillna(0).rolling(window_steps, min_periods=1).sum() if 'bolus_smb' in df.columns else 0
    nb_sum = (df['net_basal'].fillna(0) / 12.0).rolling(window_steps, min_periods=1).sum() if 'net_basal' in df.columns else 0
    
    df['excess_insulin'] = bolus_sum + smb_sum + nb_sum
    
    # Filter: BG >= 150, non-zero insulin
    valid = df.dropna(subset=['glucose_delta', 'glucose_end']).copy()
    corrections = valid[(valid['starting_bg'] >= 150) & (valid['excess_insulin'] > 0.1)]
    
    if require_falling:
        # Also require BG at end to be lower than start
        corrections = corrections[corrections['glucose_delta'] < 0]
    
    if len(corrections) < 30:
        return None
    
    y = corrections['glucose_delta'].values
    X = corrections[['starting_bg', 'excess_insulin']].values
    
    model = LinearRegression().fit(X, y)
    isf = -model.coef_[1]
    r2 = model.score(X, y)
    bg_coef = model.coef_[0]
    
    return {
        'isf': isf,
        'r2': r2,
        'bg_coef': bg_coef,
        'n_events': len(corrections),
        'profile_isf': profile_isf,
        'median_delta': float(np.median(y)),
        'pct_negative_delta': float((y < 0).mean()),
    }

def main():
    print(f"{'='*60}")
    print(f"EXP-2778: {TITLE}")
    print(f"{'='*60}\n")
    
    grid = load_grid()
    patients = sorted(grid['patient_id'].unique())
    print(f"Patients: {len(patients)}")
    
    # Collect results per window per patient
    all_results = {}  # window_label -> {pid: result}
    all_falling = {}  # with falling filter
    
    for wi, (steps, label) in enumerate(zip(WINDOWS, WINDOW_LABELS)):
        window_results = {}
        falling_results = {}
        
        for pid in patients:
            pdf = grid[grid['patient_id'] == pid]
            
            r = extract_isf_at_window(pdf, steps, require_falling=False)
            if r:
                window_results[pid] = r
            
            rf = extract_isf_at_window(pdf, steps, require_falling=True)
            if rf:
                falling_results[pid] = rf
        
        all_results[label] = window_results
        all_falling[label] = falling_results
    
    # Summary table
    print(f"\n{'='*60}")
    print(f"WINDOW COMPARISON")
    print(f"{'='*60}")
    print(f"{'Window':<8} {'N':>4} {'Med ISF':>10} {'%Pos':>6} {'Med R²':>8} {'Med Δ':>8} {'%BG↓':>6}")
    print(f"{'-'*52}")
    
    window_summary = {}
    for label in WINDOW_LABELS:
        wr = all_results[label]
        if not wr:
            continue
        isfs = [r['isf'] for r in wr.values()]
        r2s = [r['r2'] for r in wr.values()]
        deltas = [r['median_delta'] for r in wr.values()]
        pct_pos = sum(1 for i in isfs if i > 0) / len(isfs) * 100
        
        window_summary[label] = {
            'n': len(wr),
            'median_isf': np.median(isfs),
            'pct_positive': pct_pos,
            'median_r2': np.median(r2s),
            'median_delta': np.median(deltas),
        }
        
        print(f"  {label:<6} {len(wr):>4} {np.median(isfs):>10.1f} {pct_pos:>5.0f}% {np.median(r2s):>8.3f} {np.median(deltas):>8.1f}")
    
    print(f"\nWith BG-falling filter:")
    print(f"{'Window':<8} {'N':>4} {'Med ISF':>10} {'%Pos':>6} {'Med R²':>8}")
    print(f"{'-'*38}")
    
    falling_summary = {}
    for label in WINDOW_LABELS:
        fr = all_falling[label]
        if not fr:
            continue
        isfs = [r['isf'] for r in fr.values()]
        r2s = [r['r2'] for r in fr.values()]
        pct_pos = sum(1 for i in isfs if i > 0) / len(isfs) * 100
        
        falling_summary[label] = {
            'n': len(fr),
            'median_isf': np.median(isfs),
            'pct_positive': pct_pos,
            'median_r2': np.median(r2s),
        }
        
        print(f"  {label:<6} {len(fr):>4} {np.median(isfs):>10.1f} {pct_pos:>5.0f}% {np.median(r2s):>8.3f}")
    
    # Correlation with profile at each window
    print(f"\nCorrelation with profile ISF:")
    corr_data = {}
    for label in WINDOW_LABELS:
        wr = all_results[label]
        pos_pairs = [(r['profile_isf'], r['isf']) for r in wr.values() if r['isf'] > 0]
        if len(pos_pairs) > 5:
            r_val, _ = stats.pearsonr([p[0] for p in pos_pairs], [p[1] for p in pos_pairs])
        else:
            r_val = 0
        corr_data[label] = r_val
        print(f"  {label}: r={r_val:.3f} (N_pos={len(pos_pairs)})")
    
    # Hypothesis testing
    isf_2h = window_summary.get('2h', {}).get('median_isf', 0)
    isf_5h = window_summary.get('5h', {}).get('median_isf', 0)
    isf_6h = window_summary.get('6h', {}).get('median_isf', 0)
    
    # H1: Longer windows give more positive ISF
    isf_trend = [window_summary.get(l, {}).get('median_isf', 0) for l in WINDOW_LABELS]
    # Check if ISF generally increases with window length
    h1 = isf_6h > isf_2h and isf_5h > isf_2h
    
    # H2: 5-6h ISF > 5x 2h ISF
    if isf_2h > 0:
        h2 = max(isf_5h, isf_6h) > 5 * isf_2h
    else:
        h2 = max(isf_5h, isf_6h) > 0 and isf_2h <= 0  # Better: positive vs negative
    
    # H3: 5-6h has >70% positive
    pct_5h = window_summary.get('5h', {}).get('pct_positive', 0)
    pct_6h = window_summary.get('6h', {}).get('pct_positive', 0)
    h3 = max(pct_5h, pct_6h) > 70
    
    # H4: correlation > 0.5
    best_corr = max(corr_data.values()) if corr_data else 0
    h4 = best_corr > 0.5
    
    # H5: Falling filter improves positivity
    pct_falling_5h = falling_summary.get('5h', {}).get('pct_positive', 0)
    pct_nofilt_5h = window_summary.get('5h', {}).get('pct_positive', 0)
    h5 = pct_falling_5h > pct_nofilt_5h
    
    hypotheses = {
        'H1_longer_window_more_positive': {'pass': bool(h1),
            'value': f"2h={isf_2h:.1f}, 5h={isf_5h:.1f}, 6h={isf_6h:.1f}"},
        'H2_5h_gt5x_2h': {'pass': bool(h2),
            'value': f"5h={isf_5h:.1f}, 6h={isf_6h:.1f} vs 2h={isf_2h:.1f}"},
        'H3_5h_gt70pct_positive': {'pass': bool(h3),
            'value': f"5h={pct_5h:.0f}%, 6h={pct_6h:.0f}%"},
        'H4_correlation_gt05': {'pass': bool(h4),
            'value': f"best r={best_corr:.3f}"},
        'H5_falling_filter_improves': {'pass': bool(h5),
            'value': f"falling={pct_falling_5h:.0f}% vs unfiltered={pct_nofilt_5h:.0f}%"},
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
        fig.suptitle(f'EXP-2778: DIA-Matched Window ISF — {n_pass}/5 PASS', fontsize=14, fontweight='bold')
        
        # Panel 1: ISF by window length
        ax = axes[0, 0]
        isf_vals = [window_summary.get(l, {}).get('median_isf', 0) for l in WINDOW_LABELS]
        falling_isf = [falling_summary.get(l, {}).get('median_isf', 0) for l in WINDOW_LABELS]
        x = np.arange(len(WINDOW_LABELS))
        ax.bar(x - 0.2, isf_vals, 0.4, label='All corrections', color='steelblue', alpha=0.7)
        ax.bar(x + 0.2, falling_isf, 0.4, label='BG falling only', color='coral', alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(WINDOW_LABELS)
        ax.axhline(y=0, color='red', linestyle='--')
        ax.set_xlabel('Window Length')
        ax.set_ylabel('Median ISF (mg/dL/U)')
        ax.set_title('ISF by Window Length')
        ax.legend()
        
        # Panel 2: % positive ISF by window
        ax = axes[0, 1]
        pct_vals = [window_summary.get(l, {}).get('pct_positive', 0) for l in WINDOW_LABELS]
        falling_pct = [falling_summary.get(l, {}).get('pct_positive', 0) for l in WINDOW_LABELS]
        ax.plot(WINDOW_LABELS, pct_vals, 'o-', label='All corrections', color='steelblue')
        ax.plot(WINDOW_LABELS, falling_pct, 's-', label='BG falling only', color='coral')
        ax.axhline(y=70, color='green', linestyle='--', alpha=0.5, label='70% target')
        ax.set_xlabel('Window Length')
        ax.set_ylabel('% Patients with Positive ISF')
        ax.set_title('ISF Sign Correctness by Window')
        ax.legend()
        ax.set_ylim(0, 105)
        
        # Panel 3: R² by window
        ax = axes[1, 0]
        r2_vals = [window_summary.get(l, {}).get('median_r2', 0) for l in WINDOW_LABELS]
        ax.plot(WINDOW_LABELS, r2_vals, 'o-', color='steelblue', markersize=8)
        ax.set_xlabel('Window Length')
        ax.set_ylabel('Median R²')
        ax.set_title('Model R² by Window Length')
        ax.set_ylim(0, max(r2_vals) * 1.3 if max(r2_vals) > 0 else 0.5)
        
        # Panel 4: Per-patient ISF at best window
        ax = axes[1, 1]
        best_window = '5h'  # Use 5h as default best
        bw = all_results.get(best_window, {})
        if bw:
            pids = sorted(bw.keys(), key=lambda p: bw[p]['profile_isf'])
            x = np.arange(len(pids))
            ax.bar(x - 0.2, [bw[p]['profile_isf'] for p in pids], 0.4,
                   label='Profile', color='gold', alpha=0.7)
            ax.bar(x + 0.2, [bw[p]['isf'] for p in pids], 0.4,
                   label=f'{best_window} extracted', color='steelblue', alpha=0.7)
            ax.axhline(y=0, color='red', linestyle='--')
            ax.set_xlabel('Patient')
            ax.set_ylabel('ISF (mg/dL/U)')
            ax.set_title(f'Profile vs {best_window}-Window ISF')
            ax.legend()
            ax.set_xticks([])
        
        plt.tight_layout()
        plt.savefig(OUT_VIS / 'exp-2778-dashboard.png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"\nVisualization saved: {OUT_VIS / 'exp-2778-dashboard.png'}")
    except Exception as e:
        print(f"Visualization error: {e}")
    
    # Save results
    output = {
        'experiment': EXP_ID,
        'title': TITLE,
        'n_patients': len(patients),
        'hypotheses': hypotheses,
        'pass_count': f"{n_pass}/5",
        'window_summary': {k: {kk: round(vv, 4) if isinstance(vv, float) else vv 
                               for kk, vv in v.items()} 
                          for k, v in window_summary.items()},
        'falling_summary': {k: {kk: round(vv, 4) if isinstance(vv, float) else vv 
                                for kk, vv in v.items()} 
                           for k, v in falling_summary.items()},
        'correlations': {k: round(v, 4) for k, v in corr_data.items()},
    }
    
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Results saved: {OUT_JSON}")

if __name__ == '__main__':
    main()
