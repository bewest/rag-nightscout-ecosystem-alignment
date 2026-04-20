#!/usr/bin/env python3
"""
EXP-2770: Multi-Timescale Confounding Subtraction

User asked: "at every one of these multifactored time scales we need to be
able to measure the confounding effects we know or can determine and subtract
them from the noise to see what we're trying to measure."

This implements hierarchical subtraction inspired by oref0's approach:

  LEVEL 1 (5 min): CGM sensor noise → smooth with Savitzky-Golay
  LEVEL 2 (30 min): Active insulin effect → subtract BGI (bg impact from IOB)
  LEVEL 3 (2h): Controller compensation → subtract expected correction
  LEVEL 4 (24h): Circadian pattern → subtract time-of-day baseline
  LEVEL 5 (72h): Multi-day insulin resistance → subtract 3-day trend

At each level we measure:
  - Variance of the residual after subtraction
  - Variance reduction from the subtraction
  - What signal emerges in the residual

Hypotheses:
  H1: Each level reduces variance by ≥5% (all 5 levels contribute)
  H2: Level 2 (BGI) provides the largest single reduction (≥20%)
  H3: After all subtractions, residual CV < 0.50 (less than half original)
  H4: Level 4 (circadian) reveals consistent patterns ≥80% of patients
  H5: Final residual is uncorrelated with insulin (true deconfounding)
"""

import json, sys, os, traceback
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats
from scipy.signal import savgol_filter

GRID = Path("externals/ns-parquet/training/grid.parquet")

def compute_bgi(iob, isf, cf=0.2):
    """Estimate Blood Glucose Impact from IOB change.
    BGI = ΔIOB × effective_ISF where effective_ISF = profile_ISF × CF.
    
    We use CF ≈ 0.2 because profile ISF overestimates closed-loop effect by ~5×.
    (EXP-2764: the observed correction factor is ~0.2 of profile ISF.)
    Without this correction, BGI subtraction INCREASES variance catastrophically."""
    if len(iob) < 2:
        return np.zeros(len(iob))
    bgi = np.zeros(len(iob))
    for i in range(1, len(iob)):
        if np.isnan(iob[i]) or np.isnan(iob[i-1]):
            bgi[i] = 0
        else:
            delta_iob = iob[i] - iob[i-1]
            effective_isf = (isf[i] * cf) if not np.isnan(isf[i]) else 10.0
            bgi[i] = delta_iob * effective_isf
    return bgi

def run_experiment():
    results = {'experiment': 'EXP-2770', 'title': 'Multi-Timescale Confounding Subtraction'}

    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())
    print(f"Loaded {len(patients)} patients")

    patient_results = {}

    # Exclude patients with insufficient insulin data (user: "patients with
    # no insulin data can't be considered")
    EXCLUDE = set()
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        n_days = len(pdf) / 288
        bolus_per_day = (pdf['bolus'].fillna(0).sum() +
                         (pdf['bolus_smb'].fillna(0).sum() if 'bolus_smb' in pdf.columns else 0)) / max(n_days, 1)
        if bolus_per_day < 3.0:  # Less than 3U bolus/day = insufficient data
            EXCLUDE.add(pid)
    if EXCLUDE:
        print(f"  Excluding {len(EXCLUDE)} patients with insufficient insulin: {EXCLUDE}")

    for pid in patients:
        if pid in EXCLUDE:
            continue
        pdf = grid[grid['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        glucose = pdf['glucose'].values.astype(float)
        iob = pdf['iob'].values.astype(float) if 'iob' in pdf.columns else np.zeros(len(pdf))
        isf = pdf['scheduled_isf'].values.astype(float) if 'scheduled_isf' in pdf.columns else np.full(len(pdf), 50.0)

        # Need sufficient data
        valid_mask = ~np.isnan(glucose)
        if np.sum(valid_mask) < 2000:
            continue

        # Original variance
        glucose_clean = glucose.copy()
        # Interpolate short gaps for analysis
        nans = np.isnan(glucose_clean)
        if nans.any():
            interp_idx = np.arange(len(glucose_clean))
            glucose_clean[nans] = np.interp(interp_idx[nans], interp_idx[~nans], glucose_clean[~nans])

        original_var = np.var(glucose_clean)
        original_std = np.std(glucose_clean)

        # ============================================================
        # LEVEL 1: CGM noise smoothing (5-min scale)
        # ============================================================
        try:
            smoothed = savgol_filter(glucose_clean, window_length=7, polyorder=2)
        except:
            smoothed = glucose_clean
        noise_removed = glucose_clean - smoothed
        level1_residual = smoothed
        level1_var_reduction = np.var(noise_removed) / original_var

        # ============================================================
        # LEVEL 2: BGI subtraction (30-min scale)
        # ============================================================
        bgi = compute_bgi(iob, isf)
        # The BGI tells us expected glucose change from insulin activity
        # Subtract cumulative BGI from glucose to get "insulin-free" glucose
        cum_bgi = np.cumsum(bgi)
        level2_residual = level1_residual - cum_bgi
        level2_var = np.var(level2_residual)
        level2_var_reduction = 1.0 - level2_var / np.var(level1_residual) if np.var(level1_residual) > 0 else 0

        # ============================================================
        # LEVEL 3: Controller compensation (2h scale)
        # ============================================================
        # Compute rolling 2h correction expectation
        # Expected correction = excess_insulin × profile_ISF / correction_factor
        bolus = pdf['bolus'].fillna(0).values
        smb = pdf['bolus_smb'].fillna(0).values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
        net_basal = pdf['net_basal'].fillna(0).values
        sched_basal = pdf['scheduled_basal_rate'].fillna(0).values
        excess_basal = (net_basal - sched_basal) * 5.0 / 60.0

        # Rolling 24-step (2h) excess insulin
        kernel = np.ones(24) / 24
        rolling_excess = np.convolve(bolus + smb + excess_basal, kernel, mode='same')
        # Expected BG impact (use effective ISF = profile × CF)
        effective_isf = np.where(np.isnan(isf), 10.0, isf * 0.2)
        expected_correction = rolling_excess * effective_isf
        level3_residual = level2_residual - expected_correction
        level3_var = np.var(level3_residual)
        level3_var_reduction = 1.0 - level3_var / level2_var if level2_var > 0 else 0

        # ============================================================
        # LEVEL 4: Circadian pattern (24h scale)
        # ============================================================
        time_vals = pd.to_datetime(pdf['time'])
        hour = time_vals.dt.hour.values + time_vals.dt.minute.values / 60.0
        # Compute hourly averages of residual
        hourly_avg = np.zeros(24)
        for h in range(24):
            mask = (hour >= h) & (hour < h + 1)
            vals = level3_residual[mask]
            valid = vals[~np.isnan(vals)]
            hourly_avg[h] = np.mean(valid) if len(valid) > 0 else 0

        # Subtract circadian pattern
        circadian_correction = np.array([hourly_avg[int(h) % 24] for h in hour])
        level4_residual = level3_residual - circadian_correction
        level4_var = np.var(level4_residual)
        level4_var_reduction = 1.0 - level4_var / level3_var if level3_var > 0 else 0

        # Circadian amplitude
        circadian_amplitude = hourly_avg.max() - hourly_avg.min()
        circadian_significant = circadian_amplitude > 10  # >10 mg/dL swing

        # ============================================================
        # LEVEL 5: Multi-day trend (72h scale)
        # ============================================================
        # Rolling 72h (864 pts) mean
        kernel_72h = np.ones(864) / 864
        if len(level4_residual) > 864:
            rolling_72h = np.convolve(level4_residual, kernel_72h, mode='same')
            level5_residual = level4_residual - rolling_72h
        else:
            level5_residual = level4_residual
            rolling_72h = np.zeros_like(level4_residual)
        level5_var = np.var(level5_residual)
        level5_var_reduction = 1.0 - level5_var / level4_var if level4_var > 0 else 0

        # Final metrics
        total_var_reduction = 1.0 - level5_var / original_var if original_var > 0 else 0

        # Check if final residual is uncorrelated with insulin
        r_final_insulin, p_final = stats.pearsonr(
            level5_residual[~np.isnan(iob)],
            iob[~np.isnan(iob)]
        ) if np.sum(~np.isnan(iob)) > 100 else (0, 1)

        patient_results[pid] = {
            'original_std': float(original_std),
            'level1_var_reduction': float(level1_var_reduction),
            'level2_var_reduction': float(level2_var_reduction),
            'level3_var_reduction': float(level3_var_reduction),
            'level4_var_reduction': float(level4_var_reduction),
            'level5_var_reduction': float(level5_var_reduction),
            'total_var_reduction': float(total_var_reduction),
            'circadian_amplitude': float(circadian_amplitude),
            'circadian_significant': bool(circadian_significant),
            'final_residual_std': float(np.std(level5_residual)),
            'r_residual_insulin': float(r_final_insulin),
            'n_points': int(np.sum(valid_mask)),
        }

    print(f"\nPatients analyzed: {len(patient_results)}")

    # Table
    print(f"\n  {'Patient':<18} {'σ_orig':>6} {'L1%':>5} {'L2%':>5} {'L3%':>5} "
          f"{'L4%':>5} {'L5%':>5} {'Total':>5} {'σ_fin':>6} {'r_ins':>6}")
    for pid in sorted(patient_results.keys()):
        pr = patient_results[pid]
        print(f"  {pid:<18} {pr['original_std']:>6.1f} "
              f"{pr['level1_var_reduction']*100:>4.1f}% "
              f"{pr['level2_var_reduction']*100:>4.1f}% "
              f"{pr['level3_var_reduction']*100:>4.1f}% "
              f"{pr['level4_var_reduction']*100:>4.1f}% "
              f"{pr['level5_var_reduction']*100:>4.1f}% "
              f"{pr['total_var_reduction']*100:>4.0f}% "
              f"{pr['final_residual_std']:>6.1f} "
              f"{pr['r_residual_insulin']:>6.3f}")

    # Hypotheses
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)

    # H1: Each level ≥5%
    level_keys = ['level1_var_reduction', 'level2_var_reduction', 'level3_var_reduction',
                  'level4_var_reduction', 'level5_var_reduction']
    level_names = ['L1-Noise', 'L2-BGI', 'L3-Controller', 'L4-Circadian', 'L5-MultiDay']
    all_levels_ge5 = True
    for lk, ln in zip(level_keys, level_names):
        med = np.median([patient_results[p][lk] for p in patient_results])
        passes = med >= 0.05
        if not passes:
            all_levels_ge5 = False
        print(f"    {ln}: median {med*100:.1f}% {'✓' if passes else '✗'}")
    h1_pass = all_levels_ge5
    print(f"  {'✓' if h1_pass else '✗'} H1: All levels ≥5%")

    # H2: BGI largest
    level_meds = {ln: np.median([patient_results[p][lk] for p in patient_results])
                  for lk, ln in zip(level_keys, level_names)}
    largest = max(level_meds, key=level_meds.get)
    h2_pass = largest == 'L2-BGI' and level_meds['L2-BGI'] >= 0.20
    print(f"  {'✓' if h2_pass else '✗'} H2: BGI largest ≥20%: largest={largest} "
          f"({level_meds[largest]*100:.1f}%)")

    # H3: Residual CV < 0.50
    orig_stds = [patient_results[p]['original_std'] for p in patient_results]
    final_stds = [patient_results[p]['final_residual_std'] for p in patient_results]
    cv_ratios = [f / o if o > 0 else 1 for f, o in zip(final_stds, orig_stds)]
    h3_pass = np.median(cv_ratios) < 0.50
    print(f"  {'✓' if h3_pass else '✗'} H3: Residual/original σ <0.50: "
          f"median {np.median(cv_ratios):.3f}")

    # H4: Circadian significant ≥80%
    circ_sig = sum(1 for p in patient_results
                   if patient_results[p]['circadian_significant'])
    h4_frac = circ_sig / len(patient_results)
    h4_pass = h4_frac >= 0.80
    print(f"  {'✓' if h4_pass else '✗'} H4: Circadian significant ≥80%: "
          f"{circ_sig}/{len(patient_results)} ({h4_frac*100:.0f}%)")

    # H5: Final residual uncorrelated with insulin
    r_finals = [patient_results[p]['r_residual_insulin'] for p in patient_results]
    med_r = np.median([abs(r) for r in r_finals])
    h5_pass = med_r < 0.10
    print(f"  {'✓' if h5_pass else '✗'} H5: |r(residual, insulin)| <0.10: "
          f"median {med_r:.3f}")

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    print(f"\n  TOTAL: {n_pass}/5 pass")

    # Total variance breakdown
    total_reds = [patient_results[p]['total_var_reduction'] for p in patient_results]
    print(f"\n  MULTI-TIMESCALE VARIANCE BREAKDOWN:")
    for ln, lk in zip(level_names, level_keys):
        med = np.median([patient_results[p][lk] for p in patient_results])
        print(f"    {ln:<20}: {med*100:.1f}% variance removed")
    print(f"    {'TOTAL':<20}: {np.median(total_reds)*100:.1f}%")
    print(f"    {'REMAINING':<20}: {(1-np.median(total_reds))*100:.1f}%")

    results['hypotheses'] = {
        'H1': {'pass': bool(h1_pass)},
        'H2': {'pass': bool(h2_pass), 'largest': largest},
        'H3': {'pass': bool(h3_pass), 'med_cv_ratio': float(np.median(cv_ratios))},
        'H4': {'pass': bool(h4_pass), 'fraction': float(h4_frac)},
        'H5': {'pass': bool(h5_pass), 'med_abs_r': float(med_r)},
        'total_pass': n_pass,
    }
    results['patients'] = patient_results
    results['level_medians'] = {ln: float(np.median([patient_results[p][lk] for p in patient_results]))
                                 for lk, ln in zip(level_keys, level_names)}

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2770: Multi-Timescale Confounding Subtraction', fontsize=16, fontweight='bold')

        pids = sorted(patient_results.keys())

        # Panel 1: Stacked variance reduction by level
        ax = axes[0, 0]
        x = np.arange(len(pids))
        bottoms = np.zeros(len(pids))
        colors = ['#2196F3', '#4CAF50', '#FF9800', '#9C27B0', '#F44336']
        for ci, (ln, lk) in enumerate(zip(level_names, level_keys)):
            vals = [patient_results[p][lk] * 100 for p in pids]
            ax.bar(x, vals, bottom=bottoms, color=colors[ci], alpha=0.7, label=ln)
            bottoms += np.array(vals)
        ax.set_xticks(x)
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Variance Reduction %')
        ax.set_title('Hierarchical Subtraction')
        ax.legend(fontsize=7)

        # Panel 2: Population level contributions (bar)
        ax = axes[0, 1]
        meds = [level_meds[ln] * 100 for ln in level_names]
        bars = ax.bar(range(5), meds, color=colors, alpha=0.7)
        ax.set_xticks(range(5))
        ax.set_xticklabels(['Noise', 'BGI', 'Controller', 'Circadian', 'Multi-day'],
                           rotation=45, fontsize=9)
        ax.set_ylabel('Median Variance Reduction %')
        ax.set_title('Contribution by Timescale')
        for bar, m in zip(bars, meds):
            ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.5,
                    f'{m:.1f}%', ha='center', fontsize=9)

        # Panel 3: Before vs after σ
        ax = axes[0, 2]
        ax.scatter(orig_stds, final_stds, s=60, alpha=0.7, c='steelblue', edgecolors='black')
        mx = max(orig_stds) * 1.1
        ax.plot([0, mx], [0, mx], 'k--', alpha=0.3, label='No change')
        ax.plot([0, mx], [0, mx * 0.5], 'r--', alpha=0.3, label='50% reduction')
        ax.set_xlabel('Original σ (mg/dL)')
        ax.set_ylabel('Final Residual σ')
        ax.set_title(f'Deconfounding Effect (med ratio={np.median(cv_ratios):.2f})')
        ax.legend()

        # Panel 4: Circadian amplitudes
        ax = axes[1, 0]
        circ_amps = [patient_results[p]['circadian_amplitude'] for p in pids]
        ax.bar(range(len(pids)), circ_amps, color='purple', alpha=0.5)
        ax.axhline(10, color='red', linestyle='--', label='Significance threshold')
        ax.set_xticks(range(len(pids)))
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Circadian Amplitude (mg/dL)')
        ax.set_title(f'Circadian Pattern ({circ_sig}/{len(patient_results)} significant)')
        ax.legend()

        # Panel 5: Residual correlation with insulin
        ax = axes[1, 1]
        ax.hist([abs(r) for r in r_finals], bins=15, color='orange', alpha=0.7, edgecolor='black')
        ax.axvline(med_r, color='red', linewidth=2, label=f'Median |r|={med_r:.3f}')
        ax.axvline(0.1, color='green', linestyle='--', label='Target <0.1')
        ax.set_xlabel('|r(residual, insulin)|')
        ax.set_ylabel('Count')
        ax.set_title('Insulin Deconfounding Check')
        ax.legend()

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary = f"""EXP-2770: Multi-Timescale Subtraction

Hypotheses: {n_pass}/5 PASS

VARIANCE REDUCTION BY LEVEL:
  L1 Noise (5min):      {level_meds['L1-Noise']*100:5.1f}%
  L2 BGI (30min):       {level_meds['L2-BGI']*100:5.1f}%
  L3 Controller (2h):   {level_meds['L3-Controller']*100:5.1f}%
  L4 Circadian (24h):   {level_meds['L4-Circadian']*100:5.1f}%
  L5 Multi-day (72h):   {level_meds['L5-MultiDay']*100:5.1f}%
  TOTAL:                {np.median(total_reds)*100:5.1f}%

Residual σ: {np.median(final_stds):.1f} mg/dL
  (from {np.median(orig_stds):.1f} → ratio {np.median(cv_ratios):.2f})

Circadian: {circ_sig}/{len(patient_results)} significant
Deconfounding: |r|={med_r:.3f}"""
        ax.text(0.05, 0.95, summary, transform=ax.transAxes,
                fontsize=10, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/multiscale-subtraction', exist_ok=True)
        plt.savefig('tools/visualizations/multiscale-subtraction/exp-2770-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/multiscale-subtraction/exp-2770-dashboard.png")
    except Exception as e:
        print(f"  Dashboard error: {e}")
        traceback.print_exc()

    class NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)): return int(obj)
            if isinstance(obj, (np.floating,)): return float(obj)
            if isinstance(obj, np.ndarray): return obj.tolist()
            if isinstance(obj, (np.bool_,)): return bool(obj)
            return super().default(obj)

    with open('externals/experiments/exp-2770_multiscale_subtraction.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2770_multiscale_subtraction.json")

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
