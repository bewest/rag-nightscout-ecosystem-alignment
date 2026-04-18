"""EXP-2526: Rebound Mechanism Investigation.

Investigates why 53% of corrections rebound above starting glucose,
and why this is NOT correlated with going hypo.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

PARQUET = 'externals/ns-parquet/training/grid.parquet'
OUTPUT = 'externals/experiments/exp-2526_rebound_mechanism.json'
HORIZONS = {'h1': 12, 'h2': 24, 'h3': 36, 'h4': 48, 'h5': 60, 'h6': 72, 'h8': 96, 'h10': 120, 'h12': 144}


def find_correction_events(df, min_bolus=0.3, isolation_steps=36):
    """Find correction events with full context."""
    for col in ['correction_bolus', 'insulin_bolus', 'bolus']:
        if col in df.columns:
            bolus_col = col
            break
    else:
        raise ValueError("No bolus column found")

    has_carbs = 'carbs' in df.columns

    # Use time_sin/time_cos if hour_sin/hour_cos not available
    hour_sin_col = 'hour_sin' if 'hour_sin' in df.columns else ('time_sin' if 'time_sin' in df.columns else None)
    hour_cos_col = 'hour_cos' if 'hour_cos' in df.columns else ('time_cos' if 'time_cos' in df.columns else None)

    events = []
    for pid in sorted(df['patient_id'].unique()):
        pdf = df[df['patient_id'] == pid].copy().reset_index(drop=True)
        bolus = pdf[bolus_col].fillna(0).values
        glucose = pdf['glucose'].values
        iob = pdf['iob'].fillna(0).values if 'iob' in pdf.columns else np.zeros(len(pdf))
        cob = pdf['cob'].fillna(0).values if 'cob' in pdf.columns else np.zeros(len(pdf))
        carbs = pdf['carbs'].fillna(0).values if has_carbs else np.zeros(len(pdf))
        hour_sin = pdf[hour_sin_col].values if hour_sin_col else np.zeros(len(pdf))
        hour_cos = pdf[hour_cos_col].values if hour_cos_col else np.zeros(len(pdf))

        correction_idx = np.where(bolus > min_bolus)[0]

        for idx in correction_idx:
            if idx + 144 >= len(glucose) or idx < isolation_steps:
                continue

            # Check isolation
            before = bolus[max(0, idx - isolation_steps):idx]
            after = bolus[idx + 1:idx + isolation_steps]
            if np.any(before > 0.3) or np.any(after > 0.3):
                continue

            start_bg = glucose[idx]
            if np.isnan(start_bg) or start_bg < 130:
                continue

            # Glucose at horizons
            glucose_at = {}
            valid = True
            for name, steps in HORIZONS.items():
                if idx + steps < len(glucose) and not np.isnan(glucose[idx + steps]):
                    glucose_at[name] = float(glucose[idx + steps])
                else:
                    valid = False
                    break
            if not valid:
                continue

            # Find nadir
            glucose_window = glucose[idx:idx + 144]
            valid_window = glucose_window[~np.isnan(glucose_window)]
            nadir = float(np.min(valid_window)) if len(valid_window) > 0 else start_bg

            # Glucose trend before correction
            trend = float(glucose[idx] - glucose[idx - 2]) if idx >= 2 else 0

            # Carbs in 6h window after correction
            carbs_after_6h = float(np.sum(carbs[idx:idx + 72]))  # 6h = 72 steps
            carbs_after_3h = float(np.sum(carbs[idx:idx + 36]))  # 3h = 36 steps

            # COB at correction time
            cob_at = float(cob[idx])

            # Time of day (recover from sin/cos)
            hour = float(np.arctan2(hour_sin[idx], hour_cos[idx]) * 12 / np.pi) % 24

            # Detect rebound: glucose > start + 10 in 4-12h window
            rebound = False
            rebound_magnitude = 0
            for h in ['h4', 'h5', 'h6', 'h8', 'h10', 'h12']:
                if h in glucose_at:
                    overshoot = glucose_at[h] - start_bg
                    if overshoot > 10:
                        rebound = True
                        rebound_magnitude = max(rebound_magnitude, overshoot)

            events.append({
                'patient_id': pid,
                'dose': float(bolus[idx]),
                'start_bg': float(start_bg),
                'nadir': nadir,
                'drop_to_nadir': float(start_bg - nadir),
                'went_below_70': nadir < 70,
                'iob': float(iob[idx]),
                'cob': float(cob_at),
                'hour': round(hour, 1),
                'trend': trend,
                'carbs_after_3h': carbs_after_3h,
                'carbs_after_6h': carbs_after_6h,
                'rebound': rebound,
                'rebound_magnitude': round(rebound_magnitude, 1),
                'glucose_at': glucose_at,
            })

    return pd.DataFrame(events)


def exp_2526a_meal_proximity(events):
    """Test if rebounds are meal-driven."""
    print("=== EXP-2526a: Meal Proximity Analysis ===\n")

    results = {}

    # Check if carbs data is meaningful
    has_any_carbs = events['carbs_after_6h'].sum() > 0
    if not has_any_carbs:
        print("No carb data available in dataset — skipping meal analysis")
        results['status'] = 'no_carb_data'
        return results

    # Split by whether carbs were consumed after correction
    carb_threshold = 5.0  # at least 5g

    for window, col in [('3h', 'carbs_after_3h'), ('6h', 'carbs_after_6h')]:
        with_carbs = events[events[col] >= carb_threshold]
        without_carbs = events[events[col] < carb_threshold]

        if len(with_carbs) > 0 and len(without_carbs) > 0:
            rebound_with = with_carbs['rebound'].mean() * 100
            rebound_without = without_carbs['rebound'].mean() * 100

            # Fisher's exact test
            a = with_carbs['rebound'].sum()
            b = len(with_carbs) - a
            c = without_carbs['rebound'].sum()
            d = len(without_carbs) - c
            odds_ratio, p_value = stats.fisher_exact([[a, b], [c, d]])

            results[window] = {
                'n_with_carbs': int(len(with_carbs)),
                'n_without_carbs': int(len(without_carbs)),
                'rebound_pct_with_carbs': round(rebound_with, 1),
                'rebound_pct_without_carbs': round(rebound_without, 1),
                'odds_ratio': round(float(odds_ratio), 3),
                'p_value': round(float(p_value), 6),
            }
            print(f"  {window} window: with carbs {rebound_with:.1f}% rebound (n={len(with_carbs)}) "
                  f"vs without {rebound_without:.1f}% (n={len(without_carbs)}), "
                  f"OR={odds_ratio:.2f}, p={p_value:.4f}")

    return results


def exp_2526b_time_of_day(events):
    """Test if rebounds are circadian."""
    print("\n=== EXP-2526b: Time-of-Day Analysis ===\n")

    periods = [
        ('overnight', 0, 6),
        ('morning', 6, 12),
        ('afternoon', 12, 18),
        ('evening', 18, 24),
    ]

    results = {}

    for name, start, end in periods:
        period_events = events[(events['hour'] >= start) & (events['hour'] < end)]
        if len(period_events) < 10:
            continue

        rebound_pct = period_events['rebound'].mean() * 100
        mean_magnitude = period_events[period_events['rebound']]['rebound_magnitude'].mean() if period_events['rebound'].any() else 0

        results[name] = {
            'n_events': int(len(period_events)),
            'rebound_pct': round(rebound_pct, 1),
            'mean_rebound_magnitude': round(float(mean_magnitude), 1),
            'mean_start_bg': round(float(period_events['start_bg'].mean()), 1),
            'mean_dose': round(float(period_events['dose'].mean()), 2),
        }
        print(f"  {name:>10s} ({start:02d}-{end:02d}): {rebound_pct:.1f}% rebound "
              f"(n={len(period_events)}, mean BG={period_events['start_bg'].mean():.0f})")

    # Chi-squared test for independence
    counts = []
    for name in ['overnight', 'morning', 'afternoon', 'evening']:
        if name in results:
            n = results[name]['n_events']
            r = int(n * results[name]['rebound_pct'] / 100)
            counts.append([r, n - r])

    if len(counts) >= 2:
        chi2, p, dof, expected = stats.chi2_contingency(counts)
        results['chi2_test'] = {
            'chi2': round(float(chi2), 2),
            'p': round(float(p), 4),
            'significant': p < 0.05,
        }
        print(f"\nChi-squared test for period independence: χ²={chi2:.2f}, p={p:.4f}")

    return results


def exp_2526c_starting_glucose(events):
    """Analyze rebound by starting glucose level."""
    print("\n=== EXP-2526c: Starting Glucose and Rebound ===\n")

    bins = [(130, 180), (180, 220), (220, 260), (260, 400)]
    results = {}

    for lo, hi in bins:
        bin_events = events[(events['start_bg'] >= lo) & (events['start_bg'] < hi)]
        if len(bin_events) < 10:
            continue

        rebound_pct = bin_events['rebound'].mean() * 100
        mean_magnitude = bin_events[bin_events['rebound']]['rebound_magnitude'].mean() if bin_events['rebound'].any() else 0
        mean_drop = bin_events['drop_to_nadir'].mean()

        results[f'{lo}-{hi}'] = {
            'n_events': int(len(bin_events)),
            'rebound_pct': round(rebound_pct, 1),
            'mean_rebound_magnitude': round(float(mean_magnitude), 1),
            'mean_drop_to_nadir': round(float(mean_drop), 1),
            'mean_dose': round(float(bin_events['dose'].mean()), 2),
        }
        print(f"  BG {lo}-{hi}: {rebound_pct:.1f}% rebound, mean magnitude +{mean_magnitude:.0f}, "
              f"drop to nadir {mean_drop:.0f} (n={len(bin_events)})")

    # Trend test
    bg_midpoints = [(lo + hi) / 2 for lo, hi in bins if f'{lo}-{hi}' in results]
    rebound_pcts = [results[k]['rebound_pct'] for k in results if '-' in k]

    if len(bg_midpoints) >= 3:
        r, p = stats.spearmanr(bg_midpoints, rebound_pcts)
        results['bg_rebound_trend'] = {
            'spearman_r': round(float(r), 4),
            'p': round(float(p), 4),
            'direction': 'higher BG → more rebound' if r > 0 else 'higher BG → less rebound',
        }
        print(f"\nTrend: r={r:.4f}, p={p:.4f} — {results['bg_rebound_trend']['direction']}")

    return results


def exp_2526d_prediction_model(events):
    """Build rebound prediction model."""
    print("\n=== EXP-2526d: Rebound Prediction Model ===\n")

    features = ['dose', 'start_bg', 'iob', 'cob', 'hour', 'trend', 'drop_to_nadir']
    available = [f for f in features if f in events.columns]

    X = events[available].values
    y = events['rebound'].astype(int).values

    # Remove NaN
    valid = ~np.isnan(X).any(axis=1)
    X = X[valid]
    y = y[valid]

    if len(X) < 50:
        return {'error': 'Too few events'}

    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Logistic regression
    model = LogisticRegression(max_iter=1000, random_state=42)
    model.fit(X_scaled, y)

    # Feature importances (coefficients)
    coefs = dict(zip(available, [round(float(c), 4) for c in model.coef_[0]]))

    # Sort by absolute importance
    sorted_features = sorted(coefs.items(), key=lambda x: abs(x[1]), reverse=True)

    # Accuracy
    y_pred = model.predict(X_scaled)
    accuracy = np.mean(y_pred == y)

    # AUC
    from sklearn.metrics import roc_auc_score
    y_prob = model.predict_proba(X_scaled)[:, 1]
    auc = roc_auc_score(y, y_prob)

    results = {
        'accuracy': round(float(accuracy), 4),
        'auc': round(float(auc), 4),
        'coefficients': coefs,
        'feature_ranking': [(name, coef) for name, coef in sorted_features],
        'n_samples': int(len(X)),
        'rebound_rate': round(float(y.mean()), 4),
    }

    print(f"Accuracy: {accuracy:.3f}, AUC: {auc:.3f}")
    print(f"Rebound rate: {y.mean():.3f}")
    print("\nFeature importance (logistic regression coefficients):")
    for name, coef in sorted_features:
        direction = "↑ rebound" if coef > 0 else "↓ rebound"
        print(f"  {name:>15s}: {coef:+.4f} ({direction})")

    return results


def run_experiment():
    print("Loading data...")
    df = pd.read_parquet(PARQUET)
    print(f"Loaded {len(df)} rows, {df['patient_id'].nunique()} patients")

    print("\nExtracting correction events...")
    events = find_correction_events(df, min_bolus=0.3, isolation_steps=36)
    print(f"Found {len(events)} isolated corrections")

    if len(events) < 50:
        events = find_correction_events(df, min_bolus=0.3, isolation_steps=18)
        print(f"Relaxed: {len(events)} events")

    n_rebound = events['rebound'].sum()
    print(f"Rebounds: {n_rebound}/{len(events)} ({n_rebound/len(events)*100:.1f}%)")

    results = {
        'experiment': 'EXP-2526',
        'title': 'Rebound Mechanism Investigation',
        'n_events': int(len(events)),
        'n_rebounds': int(n_rebound),
        'rebound_pct': round(float(n_rebound / len(events) * 100), 1),
    }

    results['exp_2526a'] = exp_2526a_meal_proximity(events)
    results['exp_2526b'] = exp_2526b_time_of_day(events)
    results['exp_2526c'] = exp_2526c_starting_glucose(events)
    results['exp_2526d'] = exp_2526d_prediction_model(events)

    # Summary
    print("\n=== SUMMARY ===")
    top_predictor = results['exp_2526d'].get('feature_ranking', [('unknown', 0)])[0]
    print(f"Top rebound predictor: {top_predictor[0]} (coef={top_predictor[1]:+.4f})")
    print(f"AUC: {results['exp_2526d'].get('auc', 0):.3f}")

    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTPUT}")

if __name__ == '__main__':
    run_experiment()
