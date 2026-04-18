"""EXP-2527: TIR cost of over-correcting mild highs.

Quantifies glucose volatility, time-below-range, and net TIR impact
from correcting near-homeostatic glucose (130-180 mg/dL).
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

PARQUET = 'externals/ns-parquet/training/grid.parquet'
OUTPUT = 'externals/experiments/exp-2527_overcorrection_cost.json'
WINDOW_4H = 48  # 4h in 5-min steps


def find_corrections(df, min_bolus=0.3):
    """Find correction events with before/after glucose windows."""
    for col in ['correction_bolus', 'insulin_bolus', 'bolus']:
        if col in df.columns:
            bolus_col = col
            break
    else:
        raise ValueError("No bolus column")

    events = []
    for pid in sorted(df['patient_id'].unique()):
        pdf = df[df['patient_id'] == pid].copy().reset_index(drop=True)
        bolus = pdf[bolus_col].fillna(0).values
        glucose = pdf['glucose'].values

        correction_idx = np.where(bolus > min_bolus)[0]

        for idx in correction_idx:
            if idx < WINDOW_4H or idx + WINDOW_4H >= len(glucose):
                continue

            start_bg = glucose[idx]
            if np.isnan(start_bg) or start_bg < 70:
                continue

            # Before window (4h)
            before = glucose[idx - WINDOW_4H:idx]
            before_valid = before[~np.isnan(before)]

            # After window (4h)
            after = glucose[idx:idx + WINDOW_4H]
            after_valid = after[~np.isnan(after)]

            if len(before_valid) < 20 or len(after_valid) < 20:
                continue

            # Metrics
            before_cv = np.std(before_valid) / np.mean(before_valid) * 100 if np.mean(before_valid) > 0 else 0
            after_cv = np.std(after_valid) / np.mean(after_valid) * 100 if np.mean(after_valid) > 0 else 0

            before_tir = np.mean((before_valid >= 70) & (before_valid <= 180)) * 100
            after_tir = np.mean((after_valid >= 70) & (after_valid <= 180)) * 100

            before_tbr70 = np.mean(before_valid < 70) * 100
            after_tbr70 = np.mean(after_valid < 70) * 100
            before_tbr54 = np.mean(before_valid < 54) * 100
            after_tbr54 = np.mean(after_valid < 54) * 100

            nadir = float(np.min(after_valid))

            events.append({
                'patient_id': pid,
                'dose': float(bolus[idx]),
                'start_bg': float(start_bg),
                'nadir': nadir,
                'before_cv': round(before_cv, 1),
                'after_cv': round(after_cv, 1),
                'cv_change': round(after_cv - before_cv, 1),
                'before_tir': round(before_tir, 1),
                'after_tir': round(after_tir, 1),
                'tir_change': round(after_tir - before_tir, 1),
                'before_tbr70': round(before_tbr70, 1),
                'after_tbr70': round(after_tbr70, 1),
                'tbr70_change': round(after_tbr70 - before_tbr70, 1),
                'before_tbr54': round(before_tbr54, 1),
                'after_tbr54': round(after_tbr54, 1),
                'tbr54_change': round(after_tbr54 - before_tbr54, 1),
            })

    return pd.DataFrame(events)


def exp_2527a_volatility(events):
    """Post-correction glucose volatility analysis."""
    print("=== EXP-2527a: Post-Correction Volatility ===\n")

    bins = [(130, 180), (180, 220), (220, 260), (260, 500)]
    results = {}

    for lo, hi in bins:
        bin_events = events[(events['start_bg'] >= lo) & (events['start_bg'] < hi)]
        if len(bin_events) < 10:
            continue

        mean_cv_before = bin_events['before_cv'].mean()
        mean_cv_after = bin_events['after_cv'].mean()
        mean_cv_change = bin_events['cv_change'].mean()
        pct_increased = (bin_events['cv_change'] > 0).mean() * 100

        # Paired t-test
        t_stat, p_val = stats.ttest_rel(bin_events['after_cv'], bin_events['before_cv'])

        results[f'{lo}-{hi}'] = {
            'n': int(len(bin_events)),
            'cv_before': round(float(mean_cv_before), 1),
            'cv_after': round(float(mean_cv_after), 1),
            'cv_change': round(float(mean_cv_change), 1),
            'pct_increased_volatility': round(float(pct_increased), 1),
            'p_value': round(float(p_val), 4),
        }
        direction = "↑WORSE" if mean_cv_change > 0 else "↓BETTER"
        print(f"  BG {lo}-{hi}: CV {mean_cv_before:.1f}→{mean_cv_after:.1f} ({mean_cv_change:+.1f}pp) "
              f"{direction} (p={p_val:.4f}, n={len(bin_events)})")

    return results


def exp_2527b_hypo_caused(events):
    """Time-below-range caused by corrections."""
    print("\n=== EXP-2527b: Hypo Risk by Starting BG ===\n")

    bins = [(130, 180), (180, 220), (220, 260), (260, 500)]
    results = {}

    for lo, hi in bins:
        bin_events = events[(events['start_bg'] >= lo) & (events['start_bg'] < hi)]
        if len(bin_events) < 10:
            continue

        mean_tbr70_before = bin_events['before_tbr70'].mean()
        mean_tbr70_after = bin_events['after_tbr70'].mean()
        mean_tbr54_before = bin_events['before_tbr54'].mean()
        mean_tbr54_after = bin_events['after_tbr54'].mean()

        went_below_70 = (bin_events['nadir'] < 70).mean() * 100
        went_below_54 = (bin_events['nadir'] < 54).mean() * 100

        results[f'{lo}-{hi}'] = {
            'n': int(len(bin_events)),
            'tbr70_before': round(float(mean_tbr70_before), 1),
            'tbr70_after': round(float(mean_tbr70_after), 1),
            'tbr70_change': round(float(mean_tbr70_after - mean_tbr70_before), 1),
            'tbr54_before': round(float(mean_tbr54_before), 1),
            'tbr54_after': round(float(mean_tbr54_after), 1),
            'tbr54_change': round(float(mean_tbr54_after - mean_tbr54_before), 1),
            'pct_went_below_70': round(float(went_below_70), 1),
            'pct_went_below_54': round(float(went_below_54), 1),
        }
        print(f"  BG {lo}-{hi}: TBR70 {mean_tbr70_before:.1f}→{mean_tbr70_after:.1f}% "
              f"({mean_tbr70_after-mean_tbr70_before:+.1f}), "
              f"nadir<70: {went_below_70:.1f}%, nadir<54: {went_below_54:.1f}% "
              f"(n={len(bin_events)})")

    return results


def exp_2527c_net_tir(events):
    """Net TIR impact of corrections by starting glucose."""
    print("\n=== EXP-2527c: Net TIR Impact ===\n")

    bins = [(130, 155), (155, 180), (180, 200), (200, 220), (220, 260), (260, 500)]
    results = {}

    for lo, hi in bins:
        bin_events = events[(events['start_bg'] >= lo) & (events['start_bg'] < hi)]
        if len(bin_events) < 10:
            continue

        mean_tir_change = bin_events['tir_change'].mean()
        pct_improved = (bin_events['tir_change'] > 0).mean() * 100

        # Paired test
        t_stat, p_val = stats.ttest_rel(bin_events['after_tir'], bin_events['before_tir'])

        results[f'{lo}-{hi}'] = {
            'n': int(len(bin_events)),
            'tir_before': round(float(bin_events['before_tir'].mean()), 1),
            'tir_after': round(float(bin_events['after_tir'].mean()), 1),
            'tir_change': round(float(mean_tir_change), 1),
            'pct_improved': round(float(pct_improved), 1),
            'p_value': round(float(p_val), 4),
        }
        marker = "✓ NET BENEFIT" if mean_tir_change > 0 else "✗ NET HARM"
        print(f"  BG {lo}-{hi}: TIR {bin_events['before_tir'].mean():.0f}→"
              f"{bin_events['after_tir'].mean():.0f}% ({mean_tir_change:+.1f}pp) "
              f"{marker} (p={p_val:.4f}, n={len(bin_events)})")

    # Find break-even point
    midpoints = [(lo + hi) / 2 for lo, hi in bins if f'{lo}-{hi}' in results]
    tir_changes = [results[k]['tir_change'] for k in results if '-' in k]

    if len(midpoints) >= 3:
        # Linear interpolation to find zero crossing
        for i in range(len(tir_changes) - 1):
            if tir_changes[i] < 0 and tir_changes[i+1] >= 0:
                # Interpolate
                frac = -tir_changes[i] / (tir_changes[i+1] - tir_changes[i])
                breakeven = midpoints[i] + frac * (midpoints[i+1] - midpoints[i])
                results['breakeven_bg'] = round(float(breakeven), 0)
                print(f"\n  Break-even BG ≈ {breakeven:.0f} mg/dL")
                break
        else:
            if all(t >= 0 for t in tir_changes):
                results['breakeven_bg'] = 'all_positive'
                print("\n  All corrections show net TIR benefit")
            elif all(t < 0 for t in tir_changes):
                results['breakeven_bg'] = 'all_negative'
                print("\n  All corrections show net TIR harm (unexpected)")

    return results


def exp_2527d_per_patient(events):
    """Per-patient unnecessary correction quantification."""
    print("\n=== EXP-2527d: Per-Patient Unnecessary Corrections ===\n")

    results = {}

    for pid in sorted(events['patient_id'].unique()):
        pt = events[events['patient_id'] == pid]
        if len(pt) < 10:
            continue

        total = len(pt)
        from_mild = len(pt[pt['start_bg'] < 180])
        from_high = len(pt[pt['start_bg'] >= 180])
        mild_pct = from_mild / total * 100

        # Net harm corrections: TIR decreased
        net_harm = (pt['tir_change'] < 0).sum()
        net_harm_pct = net_harm / total * 100

        # Hypo-causing corrections from mild highs
        mild_hypo = len(pt[(pt['start_bg'] < 180) & (pt['nadir'] < 70)])
        mild_hypo_pct = mild_hypo / from_mild * 100 if from_mild > 0 else 0

        # Insulin "wasted" on mild corrections
        mild_insulin = pt[pt['start_bg'] < 180]['dose'].sum()
        total_insulin = pt['dose'].sum()

        results[pid] = {
            'total_corrections': int(total),
            'from_mild_pct': round(mild_pct, 1),
            'net_harm_pct': round(net_harm_pct, 1),
            'mild_causing_hypo_pct': round(mild_hypo_pct, 1),
            'mild_insulin_units': round(float(mild_insulin), 1),
            'total_insulin_units': round(float(total_insulin), 1),
            'mild_insulin_pct': round(float(mild_insulin / total_insulin * 100) if total_insulin > 0 else 0, 1),
        }
        print(f"  {pid}: {total} corrections, {mild_pct:.0f}% from <180, "
              f"{net_harm_pct:.0f}% net harm, {mild_hypo_pct:.0f}% mild→hypo")

    # Population summary
    all_mild_pct = np.mean([r['from_mild_pct'] for r in results.values()])
    all_harm_pct = np.mean([r['net_harm_pct'] for r in results.values()])
    all_mild_hypo = np.mean([r['mild_causing_hypo_pct'] for r in results.values()])

    results['_population'] = {
        'mean_from_mild_pct': round(all_mild_pct, 1),
        'mean_net_harm_pct': round(all_harm_pct, 1),
        'mean_mild_hypo_pct': round(all_mild_hypo, 1),
        'n_patients': len(results) - 1,  # exclude _population key itself
    }

    print(f"\nPopulation: {all_mild_pct:.0f}% from <180, {all_harm_pct:.0f}% net harm, "
          f"{all_mild_hypo:.0f}% mild→hypo")

    return results


def run_experiment():
    print("Loading data...")
    df = pd.read_parquet(PARQUET)
    print(f"Loaded {len(df)} rows, {df['patient_id'].nunique()} patients")

    print("\nFinding correction events...")
    events = find_corrections(df)
    print(f"Found {len(events)} corrections with before/after windows")

    results = {
        'experiment': 'EXP-2527',
        'title': 'TIR cost of over-correcting mild highs',
        'n_events': int(len(events)),
        'n_patients': int(events['patient_id'].nunique()),
    }

    results['exp_2527a'] = exp_2527a_volatility(events)
    results['exp_2527b'] = exp_2527b_hypo_caused(events)
    results['exp_2527c'] = exp_2527c_net_tir(events)
    results['exp_2527d'] = exp_2527d_per_patient(events)

    # Save
    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTPUT}")

if __name__ == '__main__':
    run_experiment()
