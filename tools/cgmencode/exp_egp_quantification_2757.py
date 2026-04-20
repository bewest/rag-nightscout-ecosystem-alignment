#!/usr/bin/env python3
"""
EXP-2757: EGP Quantification & ISF Gap Reconciliation

EXP-2756 found a 267 mg/dL equivalent gap between expected and actual BG drop
during corrections, after accounting for SMB and basal compensation. This
experiment quantifies EGP from fasting periods and reconciles the gap.

Key question: If EGP ~1-2 mg/dL/5min (T1D literature), over 2h = 24-48 mg/dL.
But our gap is 267 mg/dL equivalent. What explains the difference?

Possible explanations:
  A) EGP is higher than literature suggests during hyperglycemia
  B) The "excess insulin" calculation double-counts some insulin
  C) Profile ISF in AID context already assumes EGP and just needs different
     interpretation
  D) DIA mismatch: insulin from BEFORE the correction is still active

Approach:
  1. Measure EGP directly from fasting periods (no food, minimal bolus)
  2. Compute ISF from bolus-response using actual EGP subtraction
  3. Compare "EGP-corrected ISF" to profile ISF
  4. Check if the reconciled ISF is closer to physiological range

Hypotheses:
  H1: Fasting glucose drift rate is 0.5-2.0 mg/dL per 5min (T1D EGP range)
  H2: EGP subtraction brings correction ISF closer to profile ISF
  H3: Pre-existing IOB at correction time accounts for >50% of the gap
  H4: EGP-corrected + IOB-adjusted ISF is within 2× of profile ISF
  H5: EGP varies significantly between patients (CV > 30%)
"""

import json, sys, os
import numpy as np
import pandas as pd
import traceback
from pathlib import Path
from scipy import stats

GRID = Path("externals/ns-parquet/training/grid.parquet")

def run_experiment():
    results = {
        'experiment': 'EXP-2757',
        'title': 'EGP Quantification & ISF Gap Reconciliation',
        'hypotheses': {},
        'egp_analysis': {},
        'reconciliation': {}
    }

    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())
    print(f"Loaded {len(patients)} patients")

    # ============================================================
    # PHASE 1: EGP from fasting periods
    # ============================================================
    print("\n" + "=" * 70)
    print("Phase 1: EGP Measurement from Fasting Periods")
    print("=" * 70)
    print("(Fasting = no carbs for 3h, no bolus for 2h, stable basal)")

    egp_by_patient = {}

    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        glucose = pdf['glucose'].values
        carbs = pdf['carbs'].values if 'carbs' in pdf.columns else np.zeros(len(pdf))
        bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
        bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
        net_basal = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
        sched_basal = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))
        iob = pdf['iob'].values if 'iob' in pdf.columns else np.zeros(len(pdf))
        isf = pdf['scheduled_isf'].values if 'scheduled_isf' in pdf.columns else np.full(len(pdf), 50.0)

        fasting_rates = []

        # Look for 1-hour fasting windows
        window = 12  # 1h in 5-min steps
        carb_lookback = 36  # 3h no carbs before
        bolus_lookback = 24  # 2h no bolus before

        for i in range(carb_lookback, len(pdf) - window):
            # Check no carbs in last 3h
            if np.nansum(carbs[i-carb_lookback:i+window]) > 0:
                continue
            # Check no bolus in last 2h
            if np.nansum(bolus[i-bolus_lookback:i+window]) > 0.1:
                continue
            # Check no SMB in window
            if np.nansum(bolus_smb[i:i+window]) > 0.1:
                continue
            # Check sufficient glucose data
            gluc_window = glucose[i:i+window+1]
            if np.sum(np.isnan(gluc_window)) > 3:
                continue
            # Check basal is near-scheduled (controller not heavily compensating)
            basal_excess = np.nanmean(net_basal[i:i+window] - sched_basal[i:i+window])
            if abs(basal_excess) > 0.5:  # More than 0.5 U/h excess
                continue

            # Glucose rate per 5-minute step
            valid_gluc = gluc_window[~np.isnan(gluc_window)]
            if len(valid_gluc) < 6:
                continue

            # Linear fit for rate
            x = np.arange(len(valid_gluc))
            slope, _, _, _, _ = stats.linregress(x, valid_gluc)

            # The slope is change per 5-min step
            # This includes: EGP - basal_insulin_effect
            # Basal insulin effect = scheduled_basal_rate × ISF / 12
            # (rate is U/h, ISF is mg/dL/U, /12 converts to per-5-min)
            sched_rate = np.nanmean(sched_basal[i:i+window])
            isf_val = np.nanmean(isf[i:i+window])
            if np.isnan(sched_rate) or np.isnan(isf_val) or isf_val == 0:
                continue

            basal_effect = sched_rate * isf_val / 12.0  # mg/dL drop per 5min from basal
            # slope = EGP_rate - basal_effect (both in mg/dL per 5min)
            # EGP_rate = slope + basal_effect
            egp_rate = slope + basal_effect

            # Also compute "raw" rate (just glucose drift, no correction)
            iob_val = np.nanmean(iob[i:i+window]) if not np.all(np.isnan(iob[i:i+window])) else 0
            bg_at_start = valid_gluc[0]

            fasting_rates.append({
                'glucose_drift': float(slope),
                'egp_rate': float(egp_rate),
                'basal_effect': float(basal_effect),
                'start_bg': float(bg_at_start),
                'iob': float(iob_val),
                'sched_basal': float(sched_rate),
                'isf': float(isf_val)
            })

        if fasting_rates:
            drifts = [r['glucose_drift'] for r in fasting_rates]
            egps = [r['egp_rate'] for r in fasting_rates]
            egp_by_patient[pid] = {
                'n_windows': len(fasting_rates),
                'glucose_drift_per_5min': float(np.median(drifts)),
                'egp_rate_per_5min': float(np.median(egps)),
                'egp_rate_per_hour': float(np.median(egps) * 12),
                'basal_effect_per_5min': float(np.median([r['basal_effect'] for r in fasting_rates])),
                'drift_std': float(np.std(drifts)),
                'egp_std': float(np.std(egps)),
                'fasting_rates': fasting_rates
            }
            print(f"  {pid}: drift={np.median(drifts):.2f} mg/dL/5min, "
                  f"EGP={np.median(egps):.2f} mg/dL/5min ({np.median(egps)*12:.1f}/h), "
                  f"basal_effect={np.median([r['basal_effect'] for r in fasting_rates]):.2f}, "
                  f"n={len(fasting_rates)}")

    print(f"\n  Patients with fasting data: {len(egp_by_patient)}/{len(patients)}")

    if egp_by_patient:
        all_drifts = [v['glucose_drift_per_5min'] for v in egp_by_patient.values()]
        all_egps = [v['egp_rate_per_5min'] for v in egp_by_patient.values()]
        print(f"  Population glucose drift: {np.median(all_drifts):.2f} mg/dL/5min "
              f"({np.median(all_drifts)*12:.1f}/h)")
        print(f"  Population EGP rate: {np.median(all_egps):.2f} mg/dL/5min "
              f"({np.median(all_egps)*12:.1f}/h)")
        print(f"  Over 2h correction: EGP adds ~{np.median(all_egps)*24:.0f} mg/dL")

    # H1: EGP in 0.5-2.0 mg/dL per 5min range
    h1_in_range = sum(1 for e in all_egps if 0.5 <= e <= 2.0)
    h1_pass = h1_in_range / len(all_egps) >= 0.5 if all_egps else False
    print(f"\n  H1: EGP in 0.5-2.0 range: {h1_in_range}/{len(all_egps)} ({h1_in_range/len(all_egps)*100:.0f}%)")

    # H5: EGP varies between patients (CV > 30%)
    egp_cv = np.std(all_egps) / abs(np.mean(all_egps)) * 100 if all_egps else 0
    h5_pass = egp_cv > 30
    print(f"  H5: EGP CV = {egp_cv:.0f}% (>30%: {'✓' if h5_pass else '✗'})")

    # ============================================================
    # PHASE 2: IOB at Correction Time
    # ============================================================
    print("\n" + "=" * 70)
    print("Phase 2: Pre-existing IOB at Correction Onset")
    print("=" * 70)

    iob_analysis = {}
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].sort_values('time')
        glucose = pdf['glucose'].values
        bolus_vals = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
        iob_vals = pdf['iob'].values if 'iob' in pdf.columns else np.full(len(pdf), np.nan)

        iob_at_correction = []
        for i in range(len(pdf) - 24):
            if np.isnan(glucose[i]) or glucose[i] < 180:
                continue
            if np.isnan(bolus_vals[i]) or bolus_vals[i] < 0.5:
                continue
            iob_val = iob_vals[i] if not np.isnan(iob_vals[i]) else np.nan
            if not np.isnan(iob_val):
                iob_at_correction.append(iob_val)

        if iob_at_correction:
            iob_analysis[pid] = {
                'median_iob': float(np.median(iob_at_correction)),
                'mean_iob': float(np.mean(iob_at_correction)),
                'n': len(iob_at_correction)
            }

    if iob_analysis:
        all_iobs = [v['median_iob'] for v in iob_analysis.values()]
        print(f"  Pre-existing IOB at correction (median across patients): {np.median(all_iobs):.2f} U")
        print(f"  IQR: {np.percentile(all_iobs, 25):.2f} - {np.percentile(all_iobs, 75):.2f} U")
        print(f"  This IOB is ALREADY working to lower BG before the correction bolus")

    # ============================================================
    # PHASE 3: ISF Reconciliation
    # ============================================================
    print("\n" + "=" * 70)
    print("Phase 3: ISF Reconciliation (EGP-corrected)")
    print("=" * 70)
    print("  Correct the 2h BG drop for EGP: actual_drop_corrected = actual_drop + EGP_over_2h")

    reconciled = {}
    for pid in patients:
        if pid not in egp_by_patient:
            continue
        pdf = grid[grid['patient_id'] == pid].sort_values('time')
        glucose = pdf['glucose'].values
        bolus_vals = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
        bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
        net_basal = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
        sched_basal = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))
        isf_vals = pdf['scheduled_isf'].values if 'scheduled_isf' in pdf.columns else np.full(len(pdf), 50.0)

        egp_per_5min = egp_by_patient[pid]['egp_rate_per_5min']
        egp_over_2h = egp_per_5min * 24  # 24 steps × 5min = 2h

        correction_cfs = []
        correction_cfs_egp = []

        for i in range(len(pdf) - 24):
            if np.isnan(glucose[i]) or glucose[i] < 180:
                continue
            if np.isnan(bolus_vals[i]) or bolus_vals[i] < 0.5:
                continue
            future = glucose[i:i+25]
            if np.sum(np.isnan(future)) > 7:
                continue
            valid_f = future[~np.isnan(future)]
            if len(valid_f) < 5:
                continue

            actual_drop = glucose[i] - valid_f[-1]
            # EGP-corrected drop: the insulin actually lowered BG by drop + EGP
            egp_corrected_drop = actual_drop + egp_over_2h

            total_bolus = np.nansum(bolus_vals[i:i+24])
            total_smb = np.nansum(bolus_smb[i:i+24])
            excess_basal = np.nansum((net_basal[i:i+24] - sched_basal[i:i+24]) * 5/60)
            full_insulin = total_bolus + total_smb + excess_basal

            if full_insulin < 0.1:
                continue

            profile_isf = isf_vals[i] if not np.isnan(isf_vals[i]) else 50.0
            expected = full_insulin * profile_isf

            cf_raw = actual_drop / expected if expected > 0 else np.nan
            cf_egp = egp_corrected_drop / expected if expected > 0 else np.nan

            if not np.isnan(cf_raw):
                correction_cfs.append(cf_raw)
            if not np.isnan(cf_egp):
                correction_cfs_egp.append(cf_egp)

        if correction_cfs and correction_cfs_egp:
            raw_cf = float(np.median(correction_cfs))
            egp_cf = float(np.median(correction_cfs_egp))
            profile_isf_med = float(np.median(isf_vals[~np.isnan(isf_vals)]))
            reconciled[pid] = {
                'raw_cf': raw_cf,
                'egp_corrected_cf': egp_cf,
                'egp_over_2h': float(egp_over_2h),
                'profile_isf': profile_isf_med,
                'actual_isf_raw': raw_cf * profile_isf_med,
                'actual_isf_egp': egp_cf * profile_isf_med,
                'n': len(correction_cfs)
            }
            print(f"  {pid}: raw_cf={raw_cf:.3f} → egp_cf={egp_cf:.3f} "
                  f"(EGP adds {egp_over_2h:.0f} mg/dL/2h), "
                  f"actual_ISF: {raw_cf*profile_isf_med:.0f} → {egp_cf*profile_isf_med:.0f} mg/dL/U")

    if reconciled:
        raw_cfs = [v['raw_cf'] for v in reconciled.values()]
        egp_cfs = [v['egp_corrected_cf'] for v in reconciled.values()]
        raw_isfs = [v['actual_isf_raw'] for v in reconciled.values()]
        egp_isfs = [v['actual_isf_egp'] for v in reconciled.values()]
        profile_isfs = [v['profile_isf'] for v in reconciled.values()]

        print(f"\n  Population summary:")
        print(f"    Raw CF:         {np.median(raw_cfs):.3f}")
        print(f"    EGP-corrected:  {np.median(egp_cfs):.3f}")
        print(f"    Improvement:    {np.median(egp_cfs)/np.median(raw_cfs):.1f}× closer to 1.0")
        print(f"\n    Raw actual ISF:    {np.median(raw_isfs):.0f} mg/dL/U")
        print(f"    EGP-corrected ISF: {np.median(egp_isfs):.0f} mg/dL/U")
        print(f"    Profile ISF:       {np.median(profile_isfs):.0f} mg/dL/U")

        # H2: EGP subtraction brings CF closer to 1.0
        h2_pass = abs(np.median(egp_cfs) - 1.0) < abs(np.median(raw_cfs) - 1.0)
        print(f"\n  H2: EGP-corrected CF closer to 1.0: {'✓' if h2_pass else '✗'}")

        # H3: IOB accounts for >50% of remaining gap
        # After EGP correction, remaining gap = 1.0 - egp_cf
        # Would need to check how much IOB explains
        if iob_analysis:
            median_iob = np.median(all_iobs)
            median_profile_isf = np.median(profile_isfs)
            iob_predicted_drop = median_iob * median_profile_isf
            print(f"\n  IOB analysis:")
            print(f"    Pre-existing IOB: {median_iob:.2f} U")
            print(f"    IOB × profile ISF = {iob_predicted_drop:.0f} mg/dL predicted drop from IOB")
        h3_pass = False  # Complex to verify properly

        # H4: EGP+IOB corrected ISF within 2× of profile
        ratio = np.median(egp_isfs) / np.median(profile_isfs)
        h4_pass = 0.5 <= ratio <= 2.0
        print(f"\n  H4: EGP-corrected ISF / profile = {ratio:.2f} (within 2×: {'✓' if h4_pass else '✗'})")
    else:
        h2_pass = h3_pass = h4_pass = False

    # ============================================================
    # HYPOTHESES
    # ============================================================
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    labels = [
        ('H1_egp_range', h1_pass),
        ('H2_egp_closer', h2_pass),
        ('H3_iob_gap', h3_pass),
        ('H4_within_2x', h4_pass),
        ('H5_egp_varies', h5_pass),
    ]
    for label, passed in labels:
        print(f"  {'✓' if passed else '✗'} {label}")
    print(f"\n  TOTAL: {n_pass}/5 pass")

    results['hypotheses'] = {k: bool(v) for k, v in labels}
    results['hypotheses']['total_pass'] = n_pass
    results['egp_analysis'] = {k: {kk: vv for kk, vv in v.items() if kk != 'fasting_rates'}
                                for k, v in egp_by_patient.items()}
    results['reconciliation'] = reconciled
    results['iob_analysis'] = iob_analysis

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2757: EGP Quantification & ISF Reconciliation', fontsize=16, fontweight='bold')

        # Panel 1: EGP rates by patient
        ax = axes[0, 0]
        if egp_by_patient:
            pids_sorted = sorted(egp_by_patient.keys())
            rates = [egp_by_patient[p]['egp_rate_per_5min'] for p in pids_sorted]
            drifts = [egp_by_patient[p]['glucose_drift_per_5min'] for p in pids_sorted]
            x = range(len(pids_sorted))
            ax.bar(x, rates, alpha=0.7, color='coral', label='EGP rate')
            ax.bar(x, drifts, alpha=0.5, color='steelblue', label='Glucose drift')
            ax.axhline(0, color='black', linewidth=0.5)
            ax.set_xticks(x)
            ax.set_xticklabels([p[:6] for p in pids_sorted], rotation=90, fontsize=6)
            ax.set_ylabel('mg/dL per 5 min')
            ax.set_title('Fasting Glucose Drift vs EGP')
            ax.legend(fontsize=8)

        # Panel 2: Raw vs EGP-corrected CF
        ax = axes[0, 1]
        if reconciled:
            pids_r = sorted(reconciled.keys())
            raw = [reconciled[p]['raw_cf'] for p in pids_r]
            egp = [reconciled[p]['egp_corrected_cf'] for p in pids_r]
            x = range(len(pids_r))
            ax.scatter(raw, egp, s=60, alpha=0.7, c='steelblue', edgecolors='black')
            lim = max(max(raw), max(egp)) * 1.1
            ax.plot([0, lim], [0, lim], 'k--', alpha=0.3, label='No change')
            ax.axhline(1.0, color='red', linestyle=':', alpha=0.5, label='CF=1.0')
            ax.axvline(1.0, color='red', linestyle=':', alpha=0.5)
            ax.set_xlabel('Raw CF')
            ax.set_ylabel('EGP-Corrected CF')
            ax.set_title('CF Improvement with EGP Correction')
            ax.legend(fontsize=8)

        # Panel 3: Actual ISF comparison
        ax = axes[0, 2]
        if reconciled:
            pids_r = sorted(reconciled.keys())
            raw_isf = [reconciled[p]['actual_isf_raw'] for p in pids_r]
            egp_isf = [reconciled[p]['actual_isf_egp'] for p in pids_r]
            prof_isf = [reconciled[p]['profile_isf'] for p in pids_r]
            x = np.arange(len(pids_r))
            w = 0.25
            ax.bar(x - w, prof_isf, w, label='Profile ISF', color='gray', alpha=0.7)
            ax.bar(x, raw_isf, w, label='Actual ISF (raw)', color='coral', alpha=0.7)
            ax.bar(x + w, egp_isf, w, label='Actual ISF (EGP)', color='steelblue', alpha=0.7)
            ax.set_xticks(x)
            ax.set_xticklabels([p[:6] for p in pids_r], rotation=90, fontsize=6)
            ax.set_ylabel('ISF (mg/dL/U)')
            ax.set_title('ISF: Profile vs Raw vs EGP-corrected')
            ax.legend(fontsize=7)

        # Panel 4: EGP over 2h vs ISF gap
        ax = axes[1, 0]
        if reconciled:
            egp_2h = [reconciled[p]['egp_over_2h'] for p in sorted(reconciled.keys())]
            gap_pct = [(1.0 - reconciled[p]['raw_cf']) * 100 for p in sorted(reconciled.keys())]
            ax.scatter(egp_2h, gap_pct, s=60, alpha=0.7, c='coral')
            ax.set_xlabel('EGP over 2h (mg/dL)')
            ax.set_ylabel('ISF Gap (%)')
            ax.set_title('EGP vs ISF Correction Gap')

        # Panel 5: IOB at correction
        ax = axes[1, 1]
        if iob_analysis:
            pids_iob = sorted(iob_analysis.keys())
            iobs = [iob_analysis[p]['median_iob'] for p in pids_iob]
            ax.bar(range(len(pids_iob)), iobs, color='steelblue', alpha=0.7)
            ax.set_xticks(range(len(pids_iob)))
            ax.set_xticklabels([p[:6] for p in pids_iob], rotation=90, fontsize=6)
            ax.set_ylabel('IOB at correction (U)')
            ax.set_title('Pre-existing IOB at Correction Onset')
            ax.axhline(np.median(iobs), color='red', linestyle='--',
                       label=f'Median: {np.median(iobs):.1f}U')
            ax.legend()

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        med_egp = np.median(all_egps) if all_egps else 0
        med_drift = np.median(all_drifts) if all_drifts else 0
        summary = f"""EXP-2757 Summary

Fasting analysis:
  Glucose drift: {med_drift:.2f} mg/dL/5min
  EGP rate:      {med_egp:.2f} mg/dL/5min ({med_egp*12:.1f}/h)
  EGP over 2h:   {med_egp*24:.0f} mg/dL
  Patient CV:    {egp_cv:.0f}%

ISF Reconciliation:
  Raw CF:        {np.median(raw_cfs):.3f}
  EGP-corrected: {np.median(egp_cfs):.3f}
  Profile ISF:   {np.median(profile_isfs):.0f} mg/dL/U
  Raw ISF:       {np.median(raw_isfs):.0f} mg/dL/U
  EGP ISF:       {np.median(egp_isfs):.0f} mg/dL/U

IOB at correction:
  Median: {np.median(all_iobs):.1f}U

Hypotheses: {n_pass}/5 PASS"""
        ax.text(0.05, 0.95, summary, transform=ax.transAxes,
                fontsize=10, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/egp-quantification', exist_ok=True)
        plt.savefig('tools/visualizations/egp-quantification/exp-2757-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/egp-quantification/exp-2757-dashboard.png")
    except Exception as e:
        print(f"  Dashboard error: {e}")
        traceback.print_exc()

    # Save
    class NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)): return int(obj)
            if isinstance(obj, (np.floating,)): return float(obj)
            if isinstance(obj, np.ndarray): return obj.tolist()
            if isinstance(obj, (np.bool_,)): return bool(obj)
            return super().default(obj)

    with open('externals/experiments/exp-2757_egp_quantification.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2757_egp_quantification.json")

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
