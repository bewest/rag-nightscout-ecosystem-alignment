"""EXP-2521: Power-law ISF in glucose forecasting.

Tests whether incorporating dose-dependent ISF (β=0.9) into the
physics model features improves glucose prediction accuracy.

The power-law model: ISF(dose) = ISF_base × dose^(-β)
implies total glucose drop ∝ dose^(1-β) rather than dose.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import Ridge

BETA = 0.9
PARQUET = 'externals/ns-parquet/training/grid.parquet'
OUTPUT = 'externals/experiments/exp-2521_powerlaw_forecasting.json'

STEPS_30 = 6   # 30 min / 5 min
STEPS_60 = 12  # 60 min / 5 min


def load_data():
    df = pd.read_parquet(PARQUET)
    return df


def create_targets(df):
    """Create forward-looking glucose targets per patient."""
    targets = []
    for pid, pdf in df.groupby('patient_id'):
        pdf = pdf.sort_values('time').copy()
        pdf['target_h30'] = pdf['glucose'].shift(-STEPS_30)
        pdf['target_h60'] = pdf['glucose'].shift(-STEPS_60)
        targets.append(pdf)
    return pd.concat(targets, ignore_index=True)


def create_powerlaw_features(df, beta=BETA):
    """Create power-law corrected insulin features."""
    # Power-law corrected bolus: dose^(1-β) instead of dose
    bolus = df['bolus'].fillna(0).clip(lower=0)
    df['bolus_powerlaw'] = np.where(bolus > 0, bolus ** (1 - beta), 0)
    df['bolus_flat'] = bolus

    # IOB: accumulated insulin, also subject to saturation
    iob = df['iob'].fillna(0).clip(lower=0)
    df['iob_powerlaw'] = np.where(iob > 0, iob ** (1 - beta), 0)

    return df


def run_experiment():
    """Run the full EXP-2521 experiment."""
    print("Loading data...")
    df = load_data()
    print(f"Loaded {len(df)} rows, {df['patient_id'].nunique()} patients")

    print("Creating targets (shift glucose forward)...")
    df = create_targets(df)

    print("Creating power-law features...")
    df = create_powerlaw_features(df)

    # Adapt feature names to actual schema columns
    base_features = ['glucose', 'iob', 'cob', 'time_sin', 'time_cos']

    # Feature sets to compare
    feature_sets = {
        'baseline': base_features.copy(),
        'powerlaw_replace': [f for f in base_features if f != 'iob'] + ['iob_powerlaw'],
        'powerlaw_augment': base_features + ['iob_powerlaw'],
        'baseline_with_bolus': base_features + ['bolus_flat'],
        'powerlaw_bolus': base_features + ['bolus_powerlaw'],
        'powerlaw_both': base_features + ['bolus_powerlaw', 'iob_powerlaw'],
        'full_powerlaw': [f for f in base_features if f != 'iob']
                         + ['iob_powerlaw', 'bolus_powerlaw'],
    }

    results = {}

    for horizon in ['target_h30', 'target_h60']:
        if horizon not in df.columns:
            continue

        print(f"\n{'='*50}")
        print(f"  Horizon: {horizon}")
        print(f"{'='*50}")
        results[horizon] = {}

        for name, features in feature_sets.items():
            available = [f for f in features if f in df.columns]
            if len(available) < len(features):
                missing = set(features) - set(available)
                print(f"  {name}: missing features {missing}, skipping")
                continue

            patient_r2 = {}
            patient_mae = {}

            for pid in sorted(df['patient_id'].unique()):
                pdf = df[df['patient_id'] == pid].dropna(
                    subset=available + [horizon]
                ).sort_values('time')
                if len(pdf) < 100:
                    continue

                X = pdf[available].values
                y = pdf[horizon].values

                # Temporal split: first 80% train, last 20% test
                n = len(X)
                split = int(0.8 * n)
                X_train, X_test = X[:split], X[split:]
                y_train, y_test = y[:split], y[split:]

                if len(X_test) < 20:
                    continue

                model = Ridge(alpha=1.0)
                model.fit(X_train, y_train)
                y_pred = model.predict(X_test)

                ss_res = np.sum((y_test - y_pred) ** 2)
                ss_tot = np.sum((y_test - y_test.mean()) ** 2)
                r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
                mae = np.mean(np.abs(y_test - y_pred))

                patient_r2[pid] = round(r2, 4)
                patient_mae[pid] = round(mae, 2)

            mean_r2 = (round(np.mean(list(patient_r2.values())), 4)
                       if patient_r2 else 0.0)
            mean_mae = (round(np.mean(list(patient_mae.values())), 2)
                        if patient_mae else 0.0)

            results[horizon][name] = {
                'mean_r2': mean_r2,
                'mean_mae': mean_mae,
                'n_patients': len(patient_r2),
                'per_patient_r2': patient_r2,
                'per_patient_mae': patient_mae,
                'features_used': available,
            }

            print(f"  {name:25s}: R²={mean_r2:.4f}, MAE={mean_mae:.1f}"
                  f" ({len(patient_r2)} patients)")

    # Summary comparison
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    for horizon in results:
        print(f"\n{horizon}:")
        baseline_r2 = results[horizon].get('baseline', {}).get('mean_r2', 0)
        for name, data in sorted(results[horizon].items(),
                                 key=lambda x: -x[1].get('mean_r2', 0)):
            delta = data['mean_r2'] - baseline_r2
            marker = (' <-- BASELINE' if name == 'baseline'
                      else f' (Δ={delta:+.4f})')
            print(f"  {name:25s}: R²={data['mean_r2']:.4f},"
                  f" MAE={data['mean_mae']:.1f}{marker}")

    # Per-patient wins analysis
    for horizon in results:
        h = results[horizon]
        if 'baseline' in h and 'powerlaw_augment' in h:
            base_r2 = h['baseline']['per_patient_r2']
            aug_r2 = h['powerlaw_augment']['per_patient_r2']
            common = [p for p in base_r2 if p in aug_r2]
            wins = sum(1 for p in common if aug_r2[p] > base_r2[p])
            ties = sum(1 for p in common if aug_r2[p] == base_r2[p])
            losses = len(common) - wins - ties
            print(f"\n{horizon} power-law augmented vs baseline:"
                  f" {wins}W / {ties}T / {losses}L"
                  f" across {len(common)} patients")
            # Show per-patient deltas
            deltas = {p: round(aug_r2[p] - base_r2[p], 4) for p in common}
            print(f"  Per-patient R² deltas: {deltas}")

        if 'baseline' in h and 'powerlaw_both' in h:
            base_r2 = h['baseline']['per_patient_r2']
            both_r2 = h['powerlaw_both']['per_patient_r2']
            common = [p for p in base_r2 if p in both_r2]
            wins = sum(1 for p in common if both_r2[p] > base_r2[p])
            print(f"\n{horizon} powerlaw_both vs baseline:"
                  f" {wins}/{len(common)} patients improved")

    # Save results
    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTPUT}")

    return results


if __name__ == '__main__':
    run_experiment()
