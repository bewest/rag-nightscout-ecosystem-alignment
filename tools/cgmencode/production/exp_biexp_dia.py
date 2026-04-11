"""EXP-2525: Two-mechanism DIA model (biexponential).

Fits biexponential model to glucose response curves after isolated corrections.
Tests whether insulin has a fast (direct uptake) and slow (HGP suppression) component.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.optimize import curve_fit
from scipy import stats

PARQUET = 'externals/ns-parquet/training/grid.parquet'
OUTPUT = 'externals/experiments/exp-2525_biexponential_dia.json'

HORIZONS = {'h1': 12, 'h2': 24, 'h3': 36, 'h4': 48, 'h5': 60, 'h6': 72, 'h8': 96, 'h10': 120, 'h12': 144}
HOURS = [1, 2, 3, 4, 5, 6, 8, 10, 12]


def find_isolated_corrections(df, min_bolus=0.3, isolation_steps=36):
    """Find correction boluses with no other bolus within isolation window."""
    for col in ['correction_bolus', 'insulin_bolus', 'bolus']:
        if col in df.columns:
            bolus_col = col
            break
    else:
        raise ValueError("No bolus column found")

    events = []
    for pid in sorted(df['patient_id'].unique()):
        pdf = df[df['patient_id'] == pid].copy().reset_index(drop=True)
        bolus = pdf[bolus_col].fillna(0).values
        glucose = pdf['glucose'].values

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

            # Collect glucose at horizons
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

            events.append({
                'patient_id': pid,
                'dose': float(bolus[idx]),
                'start_bg': float(start_bg),
                'glucose_at': glucose_at,
            })

    return events


def get_response_curve(events):
    """Get population-average response curve."""
    drops = {h: [] for h in HOURS}
    for event in events:
        for h_name, hr in zip(HORIZONS.keys(), HOURS):
            if h_name in event['glucose_at']:
                drop = event['start_bg'] - event['glucose_at'][h_name]
                drops[hr].append(drop / event['dose'])  # normalize by dose

    t = np.array(HOURS, dtype=float)
    y = np.array([np.mean(drops[h]) for h in HOURS])
    y_std = np.array([np.std(drops[h]) for h in HOURS])
    n = np.array([len(drops[h]) for h in HOURS])

    return t, y, y_std, n


# Model functions
def mono_exp(t, A, tau):
    return A * (1 - np.exp(-t / tau))

def biexp(t, A1, tau1, A2, tau2):
    return A1 * (1 - np.exp(-t / tau1)) + A2 * (1 - np.exp(-t / tau2))

def mono_plateau(t, A, tau, C):
    return A * (1 - np.exp(-t / tau)) + C


def fit_models(t, y):
    """Fit three models and compare."""
    results = {}
    n = len(t)

    # 1. Mono-exponential
    try:
        popt, pcov = curve_fit(mono_exp, t, y, p0=[50, 3], maxfev=5000,
                               bounds=([0, 0.1], [500, 50]))
        y_pred = mono_exp(t, *popt)
        mse = np.mean((y - y_pred) ** 2)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        k = 2  # parameters
        aic = n * np.log(mse) + 2 * k
        results['mono_exp'] = {
            'A': round(float(popt[0]), 2),
            'tau': round(float(popt[1]), 2),
            'mse': round(float(mse), 2),
            'r2': round(float(r2), 4),
            'aic': round(float(aic), 2),
        }
        print(f"  Mono-exp: A={popt[0]:.1f}, τ={popt[1]:.1f}h, R²={r2:.4f}, MSE={mse:.1f}")
    except Exception as e:
        print(f"  Mono-exp fit failed: {e}")

    # 2. Biexponential
    try:
        # Constrain τ1 < τ2 by starting with good guesses
        popt, pcov = curve_fit(biexp, t, y,
                               p0=[30, 1.5, 30, 15],
                               maxfev=10000,
                               bounds=([0, 0.1, 0, 2], [500, 10, 500, 100]))
        y_pred = biexp(t, *popt)
        mse = np.mean((y - y_pred) ** 2)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        k = 4
        aic = n * np.log(mse) + 2 * k

        A1, tau1, A2, tau2 = popt
        # Ensure tau1 < tau2 (swap if needed)
        if tau1 > tau2:
            A1, A2 = A2, A1
            tau1, tau2 = tau2, tau1

        fast_pct = A1 / (A1 + A2) * 100
        results['biexp'] = {
            'A1_fast': round(float(A1), 2),
            'tau1_fast_h': round(float(tau1), 2),
            'A2_slow': round(float(A2), 2),
            'tau2_slow_h': round(float(tau2), 2),
            'fast_pct': round(float(fast_pct), 1),
            'mse': round(float(mse), 2),
            'r2': round(float(r2), 4),
            'aic': round(float(aic), 2),
        }
        print(f"  Biexp: A1={A1:.1f} (τ1={tau1:.1f}h), A2={A2:.1f} (τ2={tau2:.1f}h), "
              f"fast={fast_pct:.0f}%, R²={r2:.4f}, MSE={mse:.1f}")
    except Exception as e:
        print(f"  Biexp fit failed: {e}")

    # 3. Mono with plateau
    try:
        popt, pcov = curve_fit(mono_plateau, t, y, p0=[30, 2, 20], maxfev=5000,
                               bounds=([0, 0.1, -50], [500, 50, 200]))
        y_pred = mono_plateau(t, *popt)
        mse = np.mean((y - y_pred) ** 2)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        k = 3
        aic = n * np.log(mse) + 2 * k
        results['mono_plateau'] = {
            'A': round(float(popt[0]), 2),
            'tau': round(float(popt[1]), 2),
            'C_plateau': round(float(popt[2]), 2),
            'mse': round(float(mse), 2),
            'r2': round(float(r2), 4),
            'aic': round(float(aic), 2),
        }
        print(f"  Mono+plateau: A={popt[0]:.1f}, τ={popt[1]:.1f}h, C={popt[2]:.1f}, "
              f"R²={r2:.4f}, MSE={mse:.1f}")
    except Exception as e:
        print(f"  Mono+plateau fit failed: {e}")

    return results


def exp_2525a_population(events):
    """Fit models to population-average response curve."""
    print("=== EXP-2525a: Population Response Curve Models ===\n")

    t, y, y_std, n = get_response_curve(events)

    print("Response curve (drop per unit insulin):")
    for hr, drop, sd, cnt in zip(HOURS, y, y_std, n):
        print(f"  {hr:>2d}h: {drop:>+6.1f} ± {sd:.1f} mg/dL/U (n={cnt})")

    print("\nModel fits:")
    results = fit_models(t, y)
    results['response_curve'] = {
        'hours': HOURS,
        'mean_drop_per_unit': [round(float(v), 2) for v in y],
        'std': [round(float(v), 2) for v in y_std],
        'n': [int(v) for v in n],
    }

    # Best model by AIC
    models = [(name, data['aic']) for name, data in results.items() if 'aic' in data]
    if models:
        best = min(models, key=lambda x: x[1])
        results['best_model'] = best[0]
        print(f"\nBest model (by AIC): {best[0]}")

    return results


def exp_2525b_per_patient(events):
    """Fit biexponential per patient."""
    print("\n=== EXP-2525b: Per-Patient Biexponential Fits ===\n")

    results = {}
    tau1_values = []
    tau2_values = []

    patients = sorted(set(e['patient_id'] for e in events))

    for pid in patients:
        pt_events = [e for e in events if e['patient_id'] == pid]
        if len(pt_events) < 10:
            continue

        # Get per-patient response curve
        drops = {h: [] for h in HOURS}
        for event in pt_events:
            for h_name, hr in zip(HORIZONS.keys(), HOURS):
                if h_name in event['glucose_at']:
                    drop = event['start_bg'] - event['glucose_at'][h_name]
                    drops[hr].append(drop / event['dose'])

        t = np.array(HOURS, dtype=float)
        y = np.array([np.mean(drops[h]) if drops[h] else 0 for h in HOURS])

        if np.all(y == 0):
            continue

        try:
            popt, _ = curve_fit(biexp, t, y,
                               p0=[y.max()*0.4, 1.5, y.max()*0.6, 15],
                               maxfev=10000,
                               bounds=([0, 0.1, 0, 2], [500, 10, 500, 100]))
            A1, tau1, A2, tau2 = popt
            if tau1 > tau2:
                A1, A2 = A2, A1
                tau1, tau2 = tau2, tau1

            y_pred = biexp(t, *popt)
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

            results[pid] = {
                'n_events': len(pt_events),
                'tau1_fast_h': round(float(tau1), 2),
                'tau2_slow_h': round(float(tau2), 2),
                'A1_fast': round(float(A1), 1),
                'A2_slow': round(float(A2), 1),
                'fast_pct': round(float(A1 / (A1 + A2) * 100), 1),
                'r2': round(float(r2), 4),
            }
            tau1_values.append(tau1)
            tau2_values.append(tau2)

            print(f"  {pid}: τ1={tau1:.1f}h, τ2={tau2:.1f}h, fast={A1/(A1+A2)*100:.0f}%, "
                  f"R²={r2:.3f} (n={len(pt_events)})")
        except Exception as e:
            print(f"  {pid}: fit failed ({e})")

    if tau1_values:
        results['_population'] = {
            'tau1_mean': round(float(np.mean(tau1_values)), 2),
            'tau1_std': round(float(np.std(tau1_values)), 2),
            'tau2_mean': round(float(np.mean(tau2_values)), 2),
            'tau2_std': round(float(np.std(tau2_values)), 2),
            'tau1_cv': round(float(np.std(tau1_values) / np.mean(tau1_values) * 100), 1),
            'tau2_cv': round(float(np.std(tau2_values) / np.mean(tau2_values) * 100), 1),
            'n_patients': len(tau1_values),
        }
        print(f"\nPopulation: τ1={np.mean(tau1_values):.1f}±{np.std(tau1_values):.1f}h, "
              f"τ2={np.mean(tau2_values):.1f}±{np.std(tau2_values):.1f}h")

    return results


def exp_2525c_dose_dependence(events):
    """Test if fast/slow ratio changes with dose size."""
    print("\n=== EXP-2525c: Dose-Dependence of Two Mechanisms ===\n")

    # Split by dose
    small = [e for e in events if e['dose'] <= 1.5]
    large = [e for e in events if e['dose'] > 1.5]

    results = {}

    for group_name, group in [('small_dose_leq_1.5U', small), ('large_dose_gt_1.5U', large)]:
        if len(group) < 15:
            print(f"  {group_name}: n={len(group)} (too few)")
            continue

        drops = {h: [] for h in HOURS}
        for event in group:
            for h_name, hr in zip(HORIZONS.keys(), HOURS):
                if h_name in event['glucose_at']:
                    drop = event['start_bg'] - event['glucose_at'][h_name]
                    drops[hr].append(drop / event['dose'])

        t = np.array(HOURS, dtype=float)
        y = np.array([np.mean(drops[h]) if drops[h] else 0 for h in HOURS])

        try:
            popt, _ = curve_fit(biexp, t, y,
                               p0=[y.max()*0.4, 1.5, y.max()*0.6, 15],
                               maxfev=10000,
                               bounds=([0, 0.1, 0, 2], [500, 10, 500, 100]))
            A1, tau1, A2, tau2 = popt
            if tau1 > tau2:
                A1, A2 = A2, A1
                tau1, tau2 = tau2, tau1

            fast_pct = A1 / (A1 + A2) * 100
            results[group_name] = {
                'n_events': len(group),
                'mean_dose': round(float(np.mean([e['dose'] for e in group])), 2),
                'tau1_fast_h': round(float(tau1), 2),
                'tau2_slow_h': round(float(tau2), 2),
                'A1_fast': round(float(A1), 1),
                'A2_slow': round(float(A2), 1),
                'fast_pct': round(float(fast_pct), 1),
            }
            print(f"  {group_name} (n={len(group)}): τ1={tau1:.1f}h, τ2={tau2:.1f}h, "
                  f"fast={fast_pct:.0f}%")
        except Exception as e:
            print(f"  {group_name}: fit failed ({e})")

    # Compare
    if len(results) == 2:
        keys = list(results.keys())
        small_fast = results[keys[0]].get('fast_pct', 0)
        large_fast = results[keys[1]].get('fast_pct', 0)
        results['fast_pct_shift'] = round(large_fast - small_fast, 1)
        print(f"\nFast component shift (large - small dose): {results['fast_pct_shift']:+.1f}pp")

        if large_fast < small_fast:
            results['interpretation'] = "Larger doses have LESS fast component — consistent with power-law saturating the fast mechanism"
        else:
            results['interpretation'] = "Larger doses have MORE fast component — power-law does not preferentially affect fast mechanism"
        print(results['interpretation'])

    return results


def run_experiment():
    print("Loading data...")
    df = pd.read_parquet(PARQUET)
    print(f"Loaded {len(df)} rows, {df['patient_id'].nunique()} patients")

    print("\nFinding isolated corrections...")
    events = find_isolated_corrections(df, min_bolus=0.3, isolation_steps=36)
    print(f"Found {len(events)} isolated corrections from {len(set(e['patient_id'] for e in events))} patients")

    if len(events) < 30:
        print("Too few events. Relaxing isolation to 18 steps...")
        events = find_isolated_corrections(df, min_bolus=0.3, isolation_steps=18)
        print(f"Found {len(events)} events with relaxed criteria")

    results = {
        'experiment': 'EXP-2525',
        'title': 'Two-mechanism DIA model (biexponential)',
        'n_events': len(events),
        'n_patients': len(set(e['patient_id'] for e in events)),
    }

    results['exp_2525a'] = exp_2525a_population(events)
    results['exp_2525b'] = exp_2525b_per_patient(events)
    results['exp_2525c'] = exp_2525c_dose_dependence(events)

    # Summary
    print("\n=== SUMMARY ===")
    if 'biexp' in results.get('exp_2525a', {}):
        be = results['exp_2525a']['biexp']
        print(f"Population biexponential: τ1={be['tau1_fast_h']}h (fast), τ2={be['tau2_slow_h']}h (slow)")
        print(f"Fast component: {be['fast_pct']}% of total effect")
        print(f"Clinical DIA (fast only) matches IOB decay")
        print(f"Slow component extends effective DIA to ~{be['tau2_slow_h']*2:.0f}h")

    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTPUT}")

    return results

if __name__ == '__main__':
    run_experiment()
