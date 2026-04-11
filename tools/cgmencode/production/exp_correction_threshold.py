"""EXP-2528: Optimal correction threshold analysis.

Determines the glucose level above which corrections provide net benefit.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

PARQUET = 'externals/ns-parquet/training/grid.parquet'
OUTPUT = 'externals/experiments/exp-2528_correction_threshold.json'
WINDOW_4H = 48
WINDOW_2H = 24


def find_corrections(df, min_bolus=0.3):
    """Find corrections with before/after metrics."""
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

        # Count total rows for correction frequency
        total_rows = len(pdf)
        total_boluses = np.sum(bolus > min_bolus)

        correction_idx = np.where(bolus > min_bolus)[0]

        for idx in correction_idx:
            if idx < WINDOW_4H or idx + WINDOW_4H >= len(glucose):
                continue

            start_bg = glucose[idx]
            if np.isnan(start_bg) or start_bg < 100:
                continue

            after_2h = glucose[idx + WINDOW_2H] if not np.isnan(glucose[idx + WINDOW_2H]) else np.nan
            after_4h = glucose[idx + WINDOW_4H - 1] if not np.isnan(glucose[idx + WINDOW_4H - 1]) else np.nan

            # After window
            after = glucose[idx:idx + WINDOW_4H]
            after_valid = after[~np.isnan(after)]

            if len(after_valid) < 20 or np.isnan(after_2h) or np.isnan(after_4h):
                continue

            nadir = float(np.min(after_valid))
            drop_2h = start_bg - after_2h
            drop_4h = start_bg - after_4h
            rebound = after_4h > start_bg + 10  # rebounds if 4h glucose > start + 10
            rebound_magnitude = max(0, after_4h - start_bg)

            # TIR in 4h window
            tir_after = np.mean((after_valid >= 70) & (after_valid <= 180)) * 100
            tbr70 = np.mean(after_valid < 70) * 100

            # Before window TIR
            before = glucose[idx - WINDOW_4H:idx]
            before_valid = before[~np.isnan(before)]
            tir_before = np.mean((before_valid >= 70) & (before_valid <= 180)) * 100 if len(before_valid) > 0 else 50

            events.append({
                'patient_id': pid,
                'dose': float(bolus[idx]),
                'start_bg': float(start_bg),
                'drop_2h': round(float(drop_2h), 1),
                'drop_4h': round(float(drop_4h), 1),
                'nadir': float(nadir),
                'rebound': bool(rebound),
                'rebound_magnitude': round(float(rebound_magnitude), 1),
                'tir_before': round(float(tir_before), 1),
                'tir_after': round(float(tir_after), 1),
                'tir_change': round(float(tir_after - tir_before), 1),
                'tbr70': round(float(tbr70), 1),
                'went_below_70': bool(nadir < 70),
                'total_rows': int(total_rows),
                'total_boluses': int(total_boluses),
            })

    return pd.DataFrame(events)


def exp_2528a_benefit_curve(events):
    """Correction benefit curve by starting BG."""
    print("=== EXP-2528a: Correction Benefit Curve ===\n")

    # Fine-grained bins
    bin_edges = list(range(130, 360, 15))
    results = {'bins': []}

    print(f"{'BG Bin':>12s} | {'n':>5s} | {'Drop 2h':>8s} | {'Drop 4h':>8s} | "
          f"{'Rebound%':>9s} | {'Hypo%':>6s} | {'ΔTIR':>6s} | {'Net Benefit':>11s}")
    print("-" * 85)

    for i in range(len(bin_edges) - 1):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        bin_events = events[(events['start_bg'] >= lo) & (events['start_bg'] < hi)]

        if len(bin_events) < 10:
            continue

        mean_drop_2h = bin_events['drop_2h'].mean()
        mean_drop_4h = bin_events['drop_4h'].mean()
        rebound_pct = bin_events['rebound'].mean() * 100
        hypo_pct = bin_events['went_below_70'].mean() * 100
        tir_change = bin_events['tir_change'].mean()

        # Net benefit scoring:
        # + glucose drop (good)
        # - rebound (bad, wastes insulin)
        # - hypo risk (bad, dangerous)
        # Weight: hypo is 3x as bad as equivalent glucose excursion
        hypo_penalty = 50  # mg/dL equivalent penalty per hypo
        net_benefit = mean_drop_4h - (rebound_pct/100 * bin_events['rebound_magnitude'].mean()) - (hypo_pct/100 * hypo_penalty)

        bin_result = {
            'bg_lo': int(lo),
            'bg_hi': int(hi),
            'bg_mid': int((lo + hi) // 2),
            'n': int(len(bin_events)),
            'drop_2h': round(float(mean_drop_2h), 1),
            'drop_4h': round(float(mean_drop_4h), 1),
            'rebound_pct': round(float(rebound_pct), 1),
            'hypo_pct': round(float(hypo_pct), 1),
            'tir_change': round(float(tir_change), 1),
            'net_benefit': round(float(net_benefit), 1),
        }
        results['bins'].append(bin_result)

        marker = "✓" if net_benefit > 0 else "✗"
        print(f"  {lo}-{hi:>3d} | {len(bin_events):>5d} | {mean_drop_2h:>+8.1f} | {mean_drop_4h:>+8.1f} | "
              f"{rebound_pct:>8.1f}% | {hypo_pct:>5.1f}% | {tir_change:>+5.1f} | {net_benefit:>+10.1f} {marker}")

    # Find zero crossing
    bins_data = results['bins']
    for i in range(len(bins_data) - 1):
        if bins_data[i]['net_benefit'] < 0 and bins_data[i+1]['net_benefit'] >= 0:
            frac = -bins_data[i]['net_benefit'] / (bins_data[i+1]['net_benefit'] - bins_data[i]['net_benefit'])
            threshold = bins_data[i]['bg_mid'] + frac * (bins_data[i+1]['bg_mid'] - bins_data[i]['bg_mid'])
            results['optimal_threshold'] = round(float(threshold), 0)
            print(f"\n  Optimal correction threshold ≈ {threshold:.0f} mg/dL")
            break

    # Also find where TIR change crosses zero
    for i in range(len(bins_data) - 1):
        if bins_data[i]['tir_change'] < 0 and bins_data[i+1]['tir_change'] >= 0:
            frac = -bins_data[i]['tir_change'] / (bins_data[i+1]['tir_change'] - bins_data[i]['tir_change'])
            tir_threshold = bins_data[i]['bg_mid'] + frac * (bins_data[i+1]['bg_mid'] - bins_data[i]['bg_mid'])
            results['tir_breakeven_threshold'] = round(float(tir_threshold), 0)
            print(f"  TIR break-even threshold ≈ {tir_threshold:.0f} mg/dL")
            break

    return results


def exp_2528b_per_patient_threshold(events):
    """Find optimal correction threshold per patient."""
    print("\n=== EXP-2528b: Per-Patient Optimal Threshold ===\n")

    results = {}
    thresholds = []

    for pid in sorted(events['patient_id'].unique()):
        pt = events[events['patient_id'] == pid]
        if len(pt) < 30:
            continue

        # Find the threshold that maximizes net TIR change
        best_threshold = 130
        best_score = -999

        for threshold in range(130, 300, 10):
            above = pt[pt['start_bg'] >= threshold]
            if len(above) < 10:
                continue
            score = above['tir_change'].mean()
            if score > best_score:
                best_score = score
                best_threshold = threshold

        # Also compute rebound crossover
        for threshold in range(130, 300, 10):
            above = pt[pt['start_bg'] >= threshold]
            if len(above) < 10:
                continue
            if above['rebound'].mean() < 0.5:
                rebound_threshold = threshold
                break
        else:
            rebound_threshold = 300

        results[pid] = {
            'n_corrections': int(len(pt)),
            'tir_optimal_threshold': int(best_threshold),
            'rebound_50_threshold': int(rebound_threshold),
            'best_tir_change': round(float(best_score), 1),
            'mean_start_bg': round(float(pt['start_bg'].mean()), 1),
        }
        thresholds.append(best_threshold)
        print(f"  {pid}: TIR-optimal threshold={best_threshold}, "
              f"rebound-50%={rebound_threshold}, "
              f"best ΔTIR={best_score:+.1f}pp (n={len(pt)})")

    if thresholds:
        results['_population'] = {
            'mean_threshold': round(float(np.mean(thresholds)), 0),
            'median_threshold': round(float(np.median(thresholds)), 0),
            'std_threshold': round(float(np.std(thresholds)), 0),
            'range': [int(min(thresholds)), int(max(thresholds))],
            'n_patients': len(thresholds),
        }
        print(f"\nPopulation optimal threshold: {np.median(thresholds):.0f} mg/dL "
              f"(range {min(thresholds)}-{max(thresholds)})")

    return results


def exp_2528c_controller_comparison(events):
    """Compare correction patterns by controller type."""
    print("\n=== EXP-2528c: Controller Comparison ===\n")

    # Identify controller groups
    # NS patients: single-letter IDs (a-k)
    # ODC patients: odc-XXXXXXXX IDs
    events = events.copy()
    events['controller'] = events['patient_id'].apply(
        lambda x: 'ODC' if 'odc' in str(x) else 'NS')

    results = {}

    for ctrl in sorted(events['controller'].unique()):
        ctrl_events = events[events['controller'] == ctrl]

        results[ctrl] = {
            'n_events': int(len(ctrl_events)),
            'n_patients': int(ctrl_events['patient_id'].nunique()),
            'mean_start_bg': round(float(ctrl_events['start_bg'].mean()), 1),
            'mean_dose': round(float(ctrl_events['dose'].mean()), 2),
            'rebound_pct': round(float(ctrl_events['rebound'].mean() * 100), 1),
            'hypo_pct': round(float(ctrl_events['went_below_70'].mean() * 100), 1),
            'mean_tir_change': round(float(ctrl_events['tir_change'].mean()), 1),
            'pct_from_mild': round(float((ctrl_events['start_bg'] < 180).mean() * 100), 1),
        }
        print(f"  {ctrl}: n={len(ctrl_events)}, start BG={ctrl_events['start_bg'].mean():.0f}, "
              f"dose={ctrl_events['dose'].mean():.2f}U, rebound={ctrl_events['rebound'].mean()*100:.1f}%, "
              f"ΔTIR={ctrl_events['tir_change'].mean():+.1f}pp")

    return results


def exp_2528d_frequency_analysis(events):
    """Analyze correction frequency vs outcomes."""
    print("\n=== EXP-2528d: Correction Frequency Analysis ===\n")

    results = {}

    # Per-patient correction frequency
    patient_data = []
    for pid in sorted(events['patient_id'].unique()):
        pt = events[events['patient_id'] == pid]
        if len(pt) < 10:
            continue

        # Correction frequency: corrections per day
        total_rows = pt['total_rows'].iloc[0]
        total_boluses = pt['total_boluses'].iloc[0]
        days = total_rows / 288  # 288 5-min steps per day
        corrections_per_day = total_boluses / days if days > 0 else 0

        mean_tir_change = pt['tir_change'].mean()
        rebound_pct = pt['rebound'].mean() * 100

        patient_data.append({
            'patient_id': pid,
            'corrections_per_day': round(float(corrections_per_day), 1),
            'mean_tir_change': round(float(mean_tir_change), 1),
            'rebound_pct': round(float(rebound_pct), 1),
            'mean_start_bg': round(float(pt['start_bg'].mean()), 1),
        })

    if len(patient_data) >= 5:
        freq = [p['corrections_per_day'] for p in patient_data]
        tir = [p['mean_tir_change'] for p in patient_data]

        r, p = stats.spearmanr(freq, tir)
        results['frequency_tir_correlation'] = {
            'spearman_r': round(float(r), 4),
            'p': round(float(p), 4),
            'direction': 'more corrections → worse TIR' if r < 0 else 'more corrections → better TIR',
        }

        print(f"Correction frequency vs TIR change: r={r:.4f}, p={p:.4f}")
        print(f"  {results['frequency_tir_correlation']['direction']}")

        for p in sorted(patient_data, key=lambda x: x['corrections_per_day']):
            print(f"  {p['patient_id']}: {p['corrections_per_day']:.1f}/day, ΔTIR={p['mean_tir_change']:+.1f}pp, "
                  f"rebound={p['rebound_pct']:.0f}%")

    results['per_patient'] = patient_data
    return results


def run_experiment():
    print("Loading data...")
    df = pd.read_parquet(PARQUET)
    print(f"Loaded {len(df)} rows, {df['patient_id'].nunique()} patients")

    print("\nFinding corrections...")
    events = find_corrections(df)
    print(f"Found {len(events)} corrections")

    results = {
        'experiment': 'EXP-2528',
        'title': 'Optimal correction threshold analysis',
        'n_events': int(len(events)),
        'n_patients': int(events['patient_id'].nunique()),
    }

    results['exp_2528a'] = exp_2528a_benefit_curve(events)
    results['exp_2528b'] = exp_2528b_per_patient_threshold(events)
    results['exp_2528c'] = exp_2528c_controller_comparison(events)
    results['exp_2528d'] = exp_2528d_frequency_analysis(events)

    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTPUT}")

if __name__ == '__main__':
    run_experiment()
