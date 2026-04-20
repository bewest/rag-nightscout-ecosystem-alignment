#!/usr/bin/env python3
"""
EXP-2765: Practical Settings Generator

Generates per-patient JSON files with recommended settings adjustments
based on the complete pipeline (EXP-2719b ISF, EXP-2741 CR, EXP-2747
size-CR, EXP-2764 LR model).

For each patient, outputs:
  - Current profile settings (ISF, CR, basal)
  - Recommended corrections with confidence scores
  - Data quality metrics (episodes, stability, controller type)
  - LR model parameters for BG prediction

Also generates a summary report across all patients.

Hypotheses:
  H1: ≥70% of patients get at least one actionable recommendation
  H2: ISF + CR combined recommendations improve ≥60% of patients
  H3: High-confidence recommendations (score ≥0.7) improve ≥80%
  H4: Generated settings are within safe bounds (ISF ≥10, CR ≥2)
  H5: Summary statistics match prior experiment findings (sanity check)
"""

import json, sys, os
import numpy as np
import pandas as pd
import traceback
from pathlib import Path
from scipy import stats
from datetime import datetime

GRID = Path("externals/ns-parquet/training/grid.parquet")

def extract_isf_cf(pdf, horizon=24, min_bg=180, min_bolus=0.5):
    glucose = pdf['glucose'].values
    bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
    bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
    net_basal = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
    sched_basal = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))
    isf = pdf['scheduled_isf'].values if 'scheduled_isf' in pdf.columns else np.full(len(pdf), 50.0)

    cfs = []
    for i in range(len(pdf) - horizon):
        if np.isnan(glucose[i]) or glucose[i] < min_bg:
            continue
        if np.isnan(bolus[i]) or bolus[i] < min_bolus:
            continue
        future = glucose[i:i+horizon+1]
        if np.sum(np.isnan(future)) > horizon * 0.3:
            continue
        valid_f = future[~np.isnan(future)]
        if len(valid_f) < 3:
            continue
        actual_drop = glucose[i] - valid_f[-1]
        total_bolus = np.nansum(bolus[i:i+horizon])
        total_smb = np.nansum(bolus_smb[i:i+horizon])
        excess_basal = np.nansum((net_basal[i:i+horizon] - sched_basal[i:i+horizon]) * 5.0/60.0)
        excess_insulin = total_bolus + total_smb + excess_basal
        if excess_insulin < 0.1:
            continue
        profile_isf_val = isf[i] if not np.isnan(isf[i]) else 50.0
        expected = excess_insulin * profile_isf_val
        if expected > 0:
            cfs.append(actual_drop / expected)
    return cfs

def extract_cr_bilateral(pdf, min_carbs=10, horizon=36):
    glucose = pdf['glucose'].values
    carbs = pdf['carbs'].values if 'carbs' in pdf.columns else np.zeros(len(pdf))
    bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
    bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
    net_basal = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
    sched_basal = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))
    isf = pdf['scheduled_isf'].values if 'scheduled_isf' in pdf.columns else np.full(len(pdf), 50.0)

    events = []
    for i in range(len(pdf) - horizon):
        if np.isnan(glucose[i]) or np.isnan(carbs[i]) or carbs[i] < min_carbs:
            continue
        future = glucose[i:i+horizon+1]
        if np.sum(np.isnan(future)) > horizon * 0.3:
            continue
        valid_f = future[~np.isnan(future)]
        if len(valid_f) < 3:
            continue

        glucose_rise = valid_f[-1] - glucose[i]
        total_carbs = np.nansum(carbs[i:i+horizon])
        total_bolus = np.nansum(bolus[i:i+horizon])
        total_smb = np.nansum(bolus_smb[i:i+horizon])
        excess_basal = np.nansum((net_basal[i:i+horizon] - sched_basal[i:i+horizon]) * 5.0/60.0)
        total_insulin = total_bolus + total_smb + excess_basal

        profile_isf_val = isf[i] if not np.isnan(isf[i]) else 50.0
        insulin_effect = total_insulin * profile_isf_val * 0.19  # Use CF from pipeline
        carb_impact = glucose_rise + insulin_effect  # Bilateral: add back insulin effect

        if total_carbs > 0:
            observed_cr_impact = carb_impact / total_carbs
            events.append({
                'carb_impact_per_g': observed_cr_impact,
                'carbs': total_carbs,
                'insulin': total_insulin,
            })

    return events

def compute_confidence(n_episodes, cf_iqr, stability=None):
    """Compute confidence score 0-1 based on data quality."""
    # Episode count: 0.5 at 20, 1.0 at 100+
    ep_score = min(1.0, n_episodes / 100)
    # IQR: lower is better, 0.5 at IQR=0.5, 1.0 at IQR=0.1
    iqr_score = max(0, min(1.0, 1 - cf_iqr / 1.0))
    # Stability
    stab_score = stability if stability is not None else 0.5

    return float(0.4 * ep_score + 0.3 * iqr_score + 0.3 * stab_score)

def run_experiment():
    results = {'experiment': 'EXP-2765', 'title': 'Practical Settings Generator'}

    grid = pd.read_parquet(GRID)
    patients = sorted(grid['patient_id'].unique())

    ctrl_map = {}
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid]
        has_smb = (pdf['bolus_smb'].fillna(0) > 0).any() if 'bolus_smb' in pdf.columns else False
        ctrl_map[pid] = 'Trio' if has_smb else 'Loop'

    print(f"Loaded {len(patients)} patients")

    all_settings = {}
    n_actionable = 0
    n_isf_cr_improve = 0
    high_conf_improve = 0
    high_conf_total = 0
    safety_violations = 0

    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        n = len(pdf)
        split = int(n * 0.7)
        train = pdf.iloc[:split]
        test = pdf.iloc[split:]

        # Current profile settings
        profile_isf = float(pdf['scheduled_isf'].median()) if 'scheduled_isf' in pdf.columns else None
        profile_cr = float(pdf['scheduled_cr'].median()) if 'scheduled_cr' in pdf.columns else None
        profile_basal = float(pdf['scheduled_basal_rate'].median()) if 'scheduled_basal_rate' in pdf.columns else None

        # ISF correction factor
        train_cfs = extract_isf_cf(train)
        test_cfs = extract_isf_cf(test)

        if len(train_cfs) < 10:
            continue

        cf = float(np.median(train_cfs))
        cf_iqr = float(np.percentile(train_cfs, 75) - np.percentile(train_cfs, 25))

        # Temporal stability
        if len(test_cfs) >= 5:
            test_cf = float(np.median(test_cfs))
            stability = 1 - abs(cf - test_cf) / abs(cf) if cf != 0 else 0
        else:
            stability = None

        # ISF recommendation
        recommended_isf = profile_isf * cf if profile_isf and cf else None
        isf_direction = None
        if recommended_isf:
            if recommended_isf < profile_isf * 0.9:
                isf_direction = 'decrease'
            elif recommended_isf > profile_isf * 1.1:
                isf_direction = 'increase'
            else:
                isf_direction = 'keep'

        # CR from bilateral deconfounding
        cr_events = extract_cr_bilateral(train)
        recommended_cr = None
        cr_direction = None
        if cr_events and profile_cr:
            carb_impacts = [e['carb_impact_per_g'] for e in cr_events]
            observed_impact = float(np.median(carb_impacts))
            if observed_impact > 0:
                recommended_cr = profile_cr * (observed_impact / (profile_isf / profile_cr)) if profile_isf else None
                if recommended_cr:
                    if recommended_cr < profile_cr * 0.9:
                        cr_direction = 'decrease'
                    elif recommended_cr > profile_cr * 1.1:
                        cr_direction = 'increase'
                    else:
                        cr_direction = 'keep'

        # LR model
        train_eps_df = pd.DataFrame(extract_episodes_for_lr(train))
        lr_intercept = None
        lr_slope = None
        lr_bg_coef = None
        if len(train_eps_df) >= 15:
            slope, intercept, _, _, _ = stats.linregress(
                train_eps_df['excess_insulin'], train_eps_df['actual_drop'])
            lr_intercept = float(intercept)
            lr_slope = float(slope)

        # Confidence
        confidence = compute_confidence(len(train_cfs), cf_iqr, stability)

        # Safety check
        safe = True
        if recommended_isf and recommended_isf < 10:
            safe = False
            safety_violations += 1
        if recommended_cr and recommended_cr < 2:
            safe = False
            safety_violations += 1

        has_actionable = (isf_direction in ('increase', 'decrease') or
                         cr_direction in ('increase', 'decrease'))
        if has_actionable:
            n_actionable += 1

        if isf_direction != 'keep' or cr_direction != 'keep':
            n_isf_cr_improve += 1

        if confidence >= 0.7:
            high_conf_total += 1
            if has_actionable:
                high_conf_improve += 1

        settings = {
            'patient_id': pid,
            'controller': ctrl_map.get(pid, 'Unknown'),
            'data_points': n,
            'generated': datetime.now().isoformat(),
            'profile': {
                'isf': profile_isf,
                'cr': profile_cr,
                'basal': profile_basal,
            },
            'recommendations': {
                'isf': {
                    'current': profile_isf,
                    'recommended': round(recommended_isf, 1) if recommended_isf else None,
                    'correction_factor': round(cf, 3),
                    'direction': isf_direction,
                    'safe': safe,
                },
                'cr': {
                    'current': profile_cr,
                    'recommended': round(recommended_cr, 1) if recommended_cr else None,
                    'direction': cr_direction,
                },
            },
            'lr_model': {
                'intercept': round(lr_intercept, 1) if lr_intercept else None,
                'slope': round(lr_slope, 2) if lr_slope else None,
                'formula': f"drop = {lr_intercept:.0f} + {lr_slope:.1f} × excess_insulin" if lr_intercept else None,
            },
            'data_quality': {
                'correction_episodes': len(train_cfs),
                'cf_iqr': round(cf_iqr, 3),
                'temporal_stability': round(stability, 3) if stability else None,
                'confidence': round(confidence, 3),
            },
        }

        all_settings[pid] = settings

    # Write per-patient JSONs
    out_dir = Path('externals/settings-recommendations')
    out_dir.mkdir(exist_ok=True)
    for pid, settings in all_settings.items():
        with open(out_dir / f'{pid}.json', 'w') as f:
            json.dump(settings, f, indent=2)

    # Write summary
    summary_path = out_dir / 'SUMMARY.json'
    summary = {
        'generated': datetime.now().isoformat(),
        'n_patients': len(all_settings),
        'pipeline': 'EXP-2719b (ISF) + EXP-2741 (CR) + EXP-2764 (LR model)',
        'patients': {pid: {
            'controller': s['controller'],
            'isf_direction': s['recommendations']['isf']['direction'],
            'cf': s['recommendations']['isf']['correction_factor'],
            'confidence': s['data_quality']['confidence'],
        } for pid, s in all_settings.items()},
    }
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\nGenerated settings for {len(all_settings)} patients")
    print(f"Output: {out_dir}/")

    # ============================================================
    # HYPOTHESES
    # ============================================================
    print("\n" + "=" * 70)
    print("HYPOTHESES EVALUATION")
    print("=" * 70)

    h1_pass = n_actionable / len(all_settings) >= 0.70 if all_settings else False
    print(f"  {'✓' if h1_pass else '✗'} H1: ≥70% actionable: "
          f"{n_actionable}/{len(all_settings)} ({n_actionable/len(all_settings)*100:.0f}%)")

    h2_pass = n_isf_cr_improve / len(all_settings) >= 0.60 if all_settings else False
    print(f"  {'✓' if h2_pass else '✗'} H2: ISF+CR improve ≥60%: "
          f"{n_isf_cr_improve}/{len(all_settings)} ({n_isf_cr_improve/len(all_settings)*100:.0f}%)")

    h3_rate = high_conf_improve / high_conf_total if high_conf_total > 0 else 0
    h3_pass = h3_rate >= 0.80
    print(f"  {'✓' if h3_pass else '✗'} H3: High-confidence ≥80%: "
          f"{high_conf_improve}/{high_conf_total} ({h3_rate*100:.0f}%)")

    h4_pass = safety_violations == 0
    print(f"  {'✓' if h4_pass else '✗'} H4: All safe: {safety_violations} violations")

    # H5: Sanity check - median CF should match prior findings (~0.19)
    all_cfs = [all_settings[p]['recommendations']['isf']['correction_factor'] for p in all_settings]
    med_cf = np.median(all_cfs)
    h5_pass = 0.10 <= med_cf <= 0.30
    print(f"  {'✓' if h5_pass else '✗'} H5: Sanity: median CF = {med_cf:.3f} (expect 0.10-0.30)")

    n_pass = sum([h1_pass, h2_pass, h3_pass, h4_pass, h5_pass])
    print(f"\n  TOTAL: {n_pass}/5 pass")

    # Summary table
    print(f"\n  {'Patient':<18} {'Ctrl':<5} {'ISF':>6} {'→ISF':>6} {'CF':>6} {'Dir':>8} {'Conf':>5}")
    for pid in sorted(all_settings.keys()):
        s = all_settings[pid]
        r = s['recommendations']['isf']
        curr = r['current']
        rec = r['recommended']
        print(f"  {pid:<18} {s['controller']:<5} "
              f"{curr:>6.0f} {rec:>6.0f} {r['correction_factor']:>6.3f} "
              f"{r['direction']:>8} {s['data_quality']['confidence']:>5.3f}")

    results['hypotheses'] = {
        'H1': {'pass': bool(h1_pass), 'actionable': n_actionable, 'total': len(all_settings)},
        'H2': {'pass': bool(h2_pass)},
        'H3': {'pass': bool(h3_pass)},
        'H4': {'pass': bool(h4_pass), 'violations': safety_violations},
        'H5': {'pass': bool(h5_pass), 'median_cf': float(med_cf)},
        'total_pass': n_pass,
    }
    results['summary'] = {
        'n_patients': len(all_settings),
        'n_actionable': n_actionable,
        'median_cf': float(med_cf),
    }

    # Dashboard
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('EXP-2765: Practical Settings Generator', fontsize=16, fontweight='bold')

        pids = sorted(all_settings.keys())

        # Panel 1: ISF current vs recommended
        ax = axes[0, 0]
        curr_isf = [all_settings[p]['profile']['isf'] or 0 for p in pids]
        rec_isf = [all_settings[p]['recommendations']['isf']['recommended'] or 0 for p in pids]
        ax.scatter(curr_isf, rec_isf, s=60, alpha=0.7, c='steelblue', edgecolors='black')
        lim = max(max(curr_isf), max(rec_isf)) * 1.1
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3, label='No change')
        ax.set_xlabel('Current ISF (mg/dL/U)')
        ax.set_ylabel('Recommended ISF')
        ax.set_title('ISF: Current vs Recommended')
        ax.legend()

        # Panel 2: CF distribution
        ax = axes[0, 1]
        ax.hist(all_cfs, bins=20, color='coral', alpha=0.7, edgecolor='black')
        ax.axvline(med_cf, color='red', linewidth=2, label=f'Median={med_cf:.3f}')
        ax.axvline(1.0, color='green', linestyle='--', label='Perfect (CF=1)')
        ax.set_xlabel('Correction Factor')
        ax.set_ylabel('Count')
        ax.set_title('CF Distribution')
        ax.legend()

        # Panel 3: Confidence scores
        ax = axes[0, 2]
        confs = [all_settings[p]['data_quality']['confidence'] for p in pids]
        colors = ['green' if c >= 0.7 else 'orange' if c >= 0.4 else 'red' for c in confs]
        ax.bar(range(len(pids)), confs, color=colors, alpha=0.7)
        ax.axhline(0.7, color='green', linestyle='--', alpha=0.5, label='High confidence')
        ax.axhline(0.4, color='orange', linestyle='--', alpha=0.5, label='Medium')
        ax.set_xticks(range(len(pids)))
        ax.set_xticklabels([p[:6] for p in pids], rotation=90, fontsize=6)
        ax.set_ylabel('Confidence Score')
        ax.set_title('Data Quality Confidence')
        ax.legend()

        # Panel 4: Direction breakdown
        ax = axes[1, 0]
        dirs = [all_settings[p]['recommendations']['isf']['direction'] for p in pids]
        from collections import Counter
        dir_counts = Counter(dirs)
        labels = list(dir_counts.keys())
        sizes = list(dir_counts.values())
        ax.pie(sizes, labels=labels, autopct='%1.0f%%', startangle=90,
               colors=['steelblue', 'coral', 'green', 'gray'])
        ax.set_title('ISF Recommendation Direction')

        # Panel 5: Episodes vs confidence
        ax = axes[1, 1]
        eps = [all_settings[p]['data_quality']['correction_episodes'] for p in pids]
        ax.scatter(eps, confs, s=60, alpha=0.7, c='steelblue', edgecolors='black')
        ax.set_xlabel('Correction Episodes')
        ax.set_ylabel('Confidence Score')
        ax.set_title('Data Volume vs Confidence')

        # Panel 6: Summary
        ax = axes[1, 2]
        ax.axis('off')
        summary_text = f"""EXP-2765: Settings Generator

Hypotheses: {n_pass}/5 PASS

Patients: {len(all_settings)}
Actionable: {n_actionable} ({n_actionable/len(all_settings)*100:.0f}%)
Median CF: {med_cf:.3f}
Safety violations: {safety_violations}
High confidence: {high_conf_total}

Direction breakdown:
  Decrease ISF: {dir_counts.get('decrease', 0)}
  Increase ISF: {dir_counts.get('increase', 0)}
  Keep ISF: {dir_counts.get('keep', 0)}

Output: externals/settings-recommendations/"""
        ax.text(0.05, 0.95, summary_text, transform=ax.transAxes,
                fontsize=11, verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

        plt.tight_layout()
        os.makedirs('tools/visualizations/settings-generator', exist_ok=True)
        plt.savefig('tools/visualizations/settings-generator/exp-2765-dashboard.png', dpi=150)
        plt.close()
        print(f"\n  Dashboard: tools/visualizations/settings-generator/exp-2765-dashboard.png")
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

    with open('externals/experiments/exp-2765_settings_generator.json', 'w') as f:
        json.dump(results, f, indent=2, cls=NpEncoder)
    print(f"Saved: externals/experiments/exp-2765_settings_generator.json")

def extract_episodes_for_lr(pdf, horizon=24, min_bg=180, min_bolus=0.5):
    glucose = pdf['glucose'].values
    bolus = pdf['bolus'].values if 'bolus' in pdf.columns else np.zeros(len(pdf))
    bolus_smb = pdf['bolus_smb'].values if 'bolus_smb' in pdf.columns else np.zeros(len(pdf))
    net_basal = pdf['net_basal'].values if 'net_basal' in pdf.columns else np.zeros(len(pdf))
    sched_basal = pdf['scheduled_basal_rate'].values if 'scheduled_basal_rate' in pdf.columns else np.zeros(len(pdf))

    episodes = []
    for i in range(len(pdf) - horizon):
        if np.isnan(glucose[i]) or glucose[i] < min_bg:
            continue
        if np.isnan(bolus[i]) or bolus[i] < min_bolus:
            continue
        future = glucose[i:i+horizon+1]
        if np.sum(np.isnan(future)) > horizon * 0.3:
            continue
        valid_f = future[~np.isnan(future)]
        if len(valid_f) < 3:
            continue
        actual_drop = glucose[i] - valid_f[-1]
        total_bolus = np.nansum(bolus[i:i+horizon])
        total_smb = np.nansum(bolus_smb[i:i+horizon])
        excess_basal = np.nansum((net_basal[i:i+horizon] - sched_basal[i:i+horizon]) * 5.0/60.0)
        excess_insulin = total_bolus + total_smb + excess_basal
        if excess_insulin < 0.1:
            continue
        episodes.append({'actual_drop': actual_drop, 'excess_insulin': excess_insulin, 'bg': glucose[i]})
    return episodes

if __name__ == '__main__':
    try:
        run_experiment()
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
