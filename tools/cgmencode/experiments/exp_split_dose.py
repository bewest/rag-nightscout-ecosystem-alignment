"""EXP-2522: Split-dose vs single bolus simulation.

Tests the hypothesis that splitting large corrections into smaller
doses is more effective under power-law ISF (β=0.9).
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

BETA = 0.9
PARQUET = 'externals/ns-parquet/training/grid.parquet'
OUTPUT = 'externals/experiments/exp-2522_split_dose_simulation.json'


def exp_2522a_theoretical():
    """Theoretical split-dose advantage under power-law ISF."""
    print("=== EXP-2522a: Theoretical Split-Dose Advantage ===")

    beta = BETA
    results = {}

    # Table: total_dose × n_splits
    total_doses = [1.0, 1.5, 2.0, 3.0, 4.0, 5.0]
    n_splits = [1, 2, 3, 4, 5, 10]

    print(f"\nPower-law β = {beta}")
    print(f"Split advantage ratio = k^β (k = number of splits)")
    print()

    header = f"{'Dose (U)':>10s} | " + " | ".join(f"{k}-split" for k in n_splits)
    print(header)
    print("-" * len(header))

    for dose in total_doses:
        row_data = {}
        row_str = f"{dose:>10.1f} | "
        for k in n_splits:
            # Single: ISF_base × dose^(1-β)
            drop_single = dose ** (1 - beta)
            # Split k ways: k × ISF_base × (dose/k)^(1-β)
            drop_split = k * (dose / k) ** (1 - beta)
            ratio = drop_split / drop_single  # = k^β
            row_data[str(k)] = round(ratio, 3)
            row_str += f" {ratio:>6.2f}× | "
        results[str(dose)] = row_data
        print(row_str)

    # Key insight: the advantage depends ONLY on k, not on dose
    print(f"\nKey: split advantage = k^β = k^{beta}")
    print(f"2-split: {2**beta:.2f}× | 3-split: {3**beta:.2f}× | "
          f"5-split: {5**beta:.2f}× | 10-split: {10**beta:.2f}×")

    return {'theoretical_table': results, 'beta': beta,
            'insight': f'Split advantage = k^beta = k^{beta}, independent of dose'}


def exp_2522b_empirical(df):
    """Empirical: compare single vs split correction outcomes."""
    print("\n=== EXP-2522b: Empirical Single vs Split Corrections ===")

    # Find bolus column
    for col in ['correction_bolus', 'insulin_bolus', 'bolus']:
        if col in df.columns:
            bolus_col = col
            break
    else:
        print("No bolus column found!")
        return {}

    results = {'by_patient': {}, 'population': {}}
    all_single = []
    all_split = []

    for pid in sorted(df['patient_id'].unique()):
        pdf = df[df['patient_id'] == pid].copy()
        pdf = pdf.sort_values('glucose').reset_index(drop=True)

        # Re-sort by index (time order) for temporal analysis
        pdf = df[df['patient_id'] == pid].copy().reset_index(drop=True)

        bolus = pdf[bolus_col].fillna(0).values
        glucose = pdf['glucose'].fillna(0).values

        # Find correction events (bolus > 0.3U)
        correction_idx = np.where(bolus > 0.3)[0]
        if len(correction_idx) < 10:
            continue

        # For each correction, measure glucose drop over next 2 hours (24 steps × 5min)
        STEPS_AHEAD = 24  # 2 hours

        single_events = []  # (dose, glucose_drop, starting_glucose)

        for idx in correction_idx:
            if idx + STEPS_AHEAD >= len(glucose):
                continue

            dose = bolus[idx]
            start_bg = glucose[idx]
            end_bg = glucose[idx + STEPS_AHEAD]

            if np.isnan(start_bg) or np.isnan(end_bg) or start_bg < 150:
                continue

            drop = start_bg - end_bg  # positive = glucose decreased

            # Check if there's another bolus within the 2h window
            window_boluses = bolus[idx+1:idx+STEPS_AHEAD]
            total_window_dose = bolus[idx] + np.sum(window_boluses[window_boluses > 0.3])
            n_boluses = 1 + np.sum(window_boluses > 0.3)

            event = {
                'dose': float(dose),
                'total_dose': float(total_window_dose),
                'n_boluses': int(n_boluses),
                'start_bg': float(start_bg),
                'end_bg': float(end_bg),
                'drop': float(drop),
                'drop_per_unit': float(drop / total_window_dose) if total_window_dose > 0 else 0,
            }

            if n_boluses == 1 and dose >= 1.5:
                single_events.append(event)
                all_single.append(event)
            elif n_boluses >= 2:
                all_split.append(event)

        if single_events:
            results['by_patient'][pid] = {
                'n_single': len(single_events),
                'mean_dose': round(np.mean([e['dose'] for e in single_events]), 2),
                'mean_drop_per_unit': round(np.mean([e['drop_per_unit'] for e in single_events]), 2),
            }

    # Population comparison
    if all_single and all_split:
        # Match by total dose range
        for dose_range, lo, hi in [('1.5-2.5U', 1.5, 2.5), ('2.5-4U', 2.5, 4.0), ('4U+', 4.0, 20.0)]:
            singles = [e for e in all_single if lo <= e['total_dose'] < hi]
            splits = [e for e in all_split if lo <= e['total_dose'] < hi]

            if singles and splits:
                single_eff = np.mean([e['drop_per_unit'] for e in singles])
                split_eff = np.mean([e['drop_per_unit'] for e in splits])
                ratio = split_eff / single_eff if single_eff > 0 else 0

                results['population'][dose_range] = {
                    'n_single': len(singles),
                    'n_split': len(splits),
                    'single_drop_per_unit': round(float(single_eff), 2),
                    'split_drop_per_unit': round(float(split_eff), 2),
                    'ratio': round(float(ratio), 3),
                }
                print(f"  {dose_range}: single={single_eff:.1f} mg/dL/U (n={len(singles)}) "
                      f"vs split={split_eff:.1f} mg/dL/U (n={len(splits)}) "
                      f"→ ratio={ratio:.2f}×")

    print(f"\nTotal events: {len(all_single)} single, {len(all_split)} split")
    return results


def exp_2522c_smb_advantage(df):
    """Compare insulin efficiency for SMB-like vs conventional dosing patterns."""
    print("\n=== EXP-2522c: SMB Advantage Quantification ===")

    for col in ['correction_bolus', 'insulin_bolus', 'bolus']:
        if col in df.columns:
            bolus_col = col
            break
    else:
        return {}

    results = {}

    for pid in sorted(df['patient_id'].unique()):
        pdf = df[df['patient_id'] == pid].copy().reset_index(drop=True)
        bolus = pdf[bolus_col].fillna(0).values
        glucose = pdf['glucose'].fillna(0).values

        # Characterize dosing pattern
        active_boluses = bolus[bolus > 0.1]
        if len(active_boluses) < 20:
            continue

        median_dose = float(np.median(active_boluses))
        n_small = int(np.sum(active_boluses < 0.5))  # SMB-like
        n_large = int(np.sum(active_boluses >= 1.5))  # Conventional
        pct_small = n_small / len(active_boluses) * 100

        # Classify dosing pattern
        if pct_small > 50:
            pattern = 'smb_dominant'
        elif n_large > n_small:
            pattern = 'conventional'
        else:
            pattern = 'mixed'

        # Measure overall insulin efficiency: glucose drop per unit
        STEPS_AHEAD = 24
        drops = []
        for i in range(len(bolus) - STEPS_AHEAD):
            if bolus[i] > 0.1 and glucose[i] > 150 and not np.isnan(glucose[i + STEPS_AHEAD]):
                drop = glucose[i] - glucose[i + STEPS_AHEAD]
                drops.append(drop / bolus[i])

        if drops:
            results[pid] = {
                'pattern': pattern,
                'median_dose': round(median_dose, 2),
                'pct_small_doses': round(pct_small, 1),
                'n_boluses': len(active_boluses),
                'n_small': n_small,
                'n_large': n_large,
                'mean_efficiency': round(float(np.mean(drops)), 2),
                'median_efficiency': round(float(np.median(drops)), 2),
            }
            print(f"  {pid}: pattern={pattern}, median_dose={median_dose:.2f}U, "
                  f"efficiency={np.median(drops):.1f} mg/dL/U")

    # Compare groups
    smb_eff = [r['median_efficiency'] for r in results.values() if isinstance(r, dict) and r.get('pattern') == 'smb_dominant']
    conv_eff = [r['median_efficiency'] for r in results.values() if isinstance(r, dict) and r.get('pattern') == 'conventional']

    if smb_eff and conv_eff:
        print(f"\nSMB-dominant ({len(smb_eff)} patients): "
              f"median efficiency = {np.median(smb_eff):.1f} mg/dL/U")
        print(f"Conventional ({len(conv_eff)} patients): "
              f"median efficiency = {np.median(conv_eff):.1f} mg/dL/U")
        ratio = np.median(smb_eff) / np.median(conv_eff) if np.median(conv_eff) > 0 else 0
        print(f"Ratio: {ratio:.2f}×")
        results['_group_comparison'] = {
            'smb_median_eff': round(float(np.median(smb_eff)), 2),
            'conv_median_eff': round(float(np.median(conv_eff)), 2),
            'ratio': round(float(ratio), 3),
            'n_smb': len(smb_eff),
            'n_conv': len(conv_eff),
        }

    return results


def run_experiment():
    """Run all EXP-2522 sub-experiments."""
    print("Loading data...")
    df = pd.read_parquet(PARQUET)
    print(f"Loaded {len(df)} rows, {df['patient_id'].nunique()} patients")
    print(f"Columns: {list(df.columns)}")

    # Check bolus columns
    for col in ['correction_bolus', 'insulin_bolus', 'bolus']:
        if col in df.columns:
            active = (df[col] > 0.1).sum()
            print(f"  {col}: {active} active rows")

    results = {
        'experiment': 'EXP-2522',
        'title': 'Split-dose vs single bolus simulation',
        'beta': BETA,
        'n_patients': int(df['patient_id'].nunique()),
        'n_rows': int(len(df)),
    }

    results['exp_2522a'] = exp_2522a_theoretical()
    results['exp_2522b'] = exp_2522b_empirical(df)
    results['exp_2522c'] = exp_2522c_smb_advantage(df)

    # Save
    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTPUT}")

    return results


if __name__ == '__main__':
    run_experiment()
