#!/usr/bin/env python3
"""EXP-2641: Forward Simulation with Dose-Dependent (Log) ISF

Tests whether applying the logarithmic ISF scaling discovered in EXP-2636/2640
improves forward simulator prediction accuracy for correction boluses.

Hypotheses:
  H1: Log-ISF reduces mean absolute error of predicted drop by >15% vs fixed ISF
  H2: Improvement concentrates in large corrections (>2U) where fixed ISF over-predicts
  H3: Log-ISF reduces over-prediction rate from >60% to <40%
  H4: Per-patient log-ISF outperforms population log-ISF by <10% (universal scaling viable)

Methodology:
  - Uses 219 corrections from EXP-2636 (gold standard EXP-2624 methodology)
  - For each correction, predicts glucose drop using:
    (A) Fixed ISF: scheduled ISF from patient profile
    (B) Population log-ISF: ISF = max(5, 50 - 28*ln(dose))
    (C) Per-patient log-ISF: individual a + b*ln(dose) from EXP-2640
    (D) Linear ISF: ISF = max(5, 1.87 - 0.13*dose) * scheduled_ISF (Round 3 formula)
  - Predicted drop = ISF_model × bolus_u
  - Compare vs actual drop: MAE, RMSE, bias, R², over-prediction rate
  - Also: simulate IOB-weighted drop using exponential insulin curve

Dependencies: EXP-2636, EXP-2640 results
"""

import json
import os
import numpy as np
from scipy import stats
from collections import defaultdict

RESULTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'externals', 'experiments')
EXP2636_FILE = os.path.join(RESULTS_DIR, 'exp-2636_dose_dependent_isf.json')
EXP2640_FILE = os.path.join(RESULTS_DIR, 'exp-2640_per_patient_isf.json')
OUTPUT_FILE = os.path.join(RESULTS_DIR, 'exp-2641_forward_sim_log_isf.json')

# Population log-ISF parameters (from EXP-2640)
POP_LOG_A = 50.0
POP_LOG_B = -28.0
ISF_FLOOR = 5.0

# Insulin PK parameters
DIA_MIN = 360.0   # 6 hours
PEAK_MIN = 75.0   # rapid-acting


def _exponential_iob(t_min, dia=DIA_MIN, peak=PEAK_MIN):
    """Fractional IOB remaining at t_min post-bolus."""
    if t_min <= 0:
        return 1.0
    if t_min >= dia:
        return 0.0
    tau = peak * (1 - peak / dia) / (1 - 2 * peak / dia)
    a = 2 * tau / dia
    S = 1 / (1 - a + (1 + a) * np.exp(-dia / tau))
    iob_frac = 1 - S * (1 - a) * (
        (t_min ** 2 / (tau * dia * (1 - a)) - t_min / tau - 1) * np.exp(-t_min / tau) + 1
    )
    return max(0.0, min(1.0, iob_frac))


def load_data():
    with open(EXP2636_FILE) as f:
        events = json.load(f)['events']
    with open(EXP2640_FILE) as f:
        patient_curves = json.load(f)['per_patient']
    return events, patient_curves


def predict_drop_fixed(event):
    """Model A: Fixed ISF from scheduled settings."""
    isf = event.get('scheduled_isf')
    if isf is None or isf <= 0:
        return None
    return isf * event['bolus_u']


def predict_drop_pop_log(event):
    """Model B: Population log-ISF = max(5, 50 - 28*ln(dose))."""
    dose = event['bolus_u']
    isf = max(ISF_FLOOR, POP_LOG_A + POP_LOG_B * np.log(dose))
    return isf * dose


def predict_drop_patient_log(event, patient_curves):
    """Model C: Per-patient log-ISF from individual fitted curves."""
    pid = event['patient_id']
    curve = patient_curves.get(pid, {})
    log_fit = curve.get('log')
    if log_fit is None:
        return predict_drop_pop_log(event)  # fallback to population
    dose = event['bolus_u']
    isf = max(ISF_FLOOR, log_fit['intercept'] + log_fit['slope'] * np.log(dose + 0.01))
    return isf * dose


def predict_drop_linear_ratio(event):
    """Model D: Linear ISF ratio from Round 3 = (1.87 - 0.13*dose) * scheduled_ISF."""
    isf = event.get('scheduled_isf')
    if isf is None or isf <= 0:
        return None
    dose = event['bolus_u']
    ratio = max(0.1, 1.87 - 0.13 * dose)
    return isf * ratio * dose


def predict_drop_iob_weighted(event):
    """Model E: IOB-weighted fixed ISF — accounts for insulin absorbed by nadir."""
    isf = event.get('scheduled_isf')
    if isf is None or isf <= 0:
        return None
    nadir_time_min = event['nadir_time_h'] * 60
    iob_delivered = 1.0 - _exponential_iob(nadir_time_min)
    return isf * event['bolus_u'] * iob_delivered


def predict_drop_iob_log(event):
    """Model F: IOB-weighted log-ISF — both dose adjustment AND delivery fraction."""
    dose = event['bolus_u']
    isf = max(ISF_FLOOR, POP_LOG_A + POP_LOG_B * np.log(dose))
    nadir_time_min = event['nadir_time_h'] * 60
    iob_delivered = 1.0 - _exponential_iob(nadir_time_min)
    return isf * dose * iob_delivered


def evaluate_model(events, predict_fn, patient_curves=None):
    """Evaluate a prediction model across all events."""
    actual = []
    predicted = []
    residuals = []
    per_patient = defaultdict(lambda: {'actual': [], 'predicted': []})

    for e in events:
        if patient_curves is not None:
            pred = predict_fn(e, patient_curves)
        else:
            pred = predict_fn(e)
        if pred is None:
            continue
        act = e['drop']
        actual.append(act)
        predicted.append(pred)
        residuals.append(pred - act)
        per_patient[e['patient_id']]['actual'].append(act)
        per_patient[e['patient_id']]['predicted'].append(pred)

    actual = np.array(actual)
    predicted = np.array(predicted)
    residuals = np.array(residuals)

    if len(actual) < 5:
        return None

    mae = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(np.mean(residuals ** 2)))
    bias = float(np.mean(residuals))
    r_val, p_val = stats.pearsonr(actual, predicted)
    ss_res = np.sum(residuals ** 2)
    ss_tot = np.sum((actual - np.mean(actual)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    over_pred_rate = float(np.mean(residuals > 0))
    under_pred_rate = float(np.mean(residuals < 0))

    # Dose-stratified analysis
    dose_bins = {}
    boluses = np.array([e['bolus_u'] for e in events if predict_fn(e) is not None]
                       if patient_curves is None else
                       [e['bolus_u'] for e in events
                        if predict_fn(e, patient_curves) is not None])
    for lo, hi, label in [(0, 1.0, '<1U'), (1.0, 2.0, '1-2U'),
                          (2.0, 3.0, '2-3U'), (3.0, 100, '>=3U')]:
        mask = (boluses >= lo) & (boluses < hi)
        n = int(mask.sum())
        if n >= 3:
            dose_bins[label] = {
                'n': n,
                'mae': round(float(np.mean(np.abs(residuals[mask]))), 1),
                'bias': round(float(np.mean(residuals[mask])), 1),
                'over_pred_pct': round(float(np.mean(residuals[mask] > 0)) * 100, 1),
            }

    # Per-patient metrics
    patient_maes = {}
    for pid, data in per_patient.items():
        a, p = np.array(data['actual']), np.array(data['predicted'])
        if len(a) >= 3:
            patient_maes[pid] = round(float(np.mean(np.abs(p - a))), 1)

    return {
        'n': len(actual),
        'mae': round(mae, 1),
        'rmse': round(rmse, 1),
        'bias': round(bias, 1),
        'r': round(float(r_val), 3),
        'r_squared': round(float(r_squared), 3),
        'over_pred_pct': round(over_pred_rate * 100, 1),
        'under_pred_pct': round(under_pred_rate * 100, 1),
        'dose_bins': dose_bins,
        'patient_maes': patient_maes,
        'predicted': [round(float(p), 1) for p in predicted],
        'actual': [round(float(a), 1) for a in actual],
        'residuals': [round(float(r), 1) for r in residuals],
    }


def main():
    print("EXP-2641: Forward Simulation with Dose-Dependent (Log) ISF")
    print("=" * 65)

    events, patient_curves = load_data()
    print(f"Loaded {len(events)} events, {len(patient_curves)} patient curves")

    models = {
        'A_fixed_isf': ('Fixed ISF (scheduled)', lambda e: predict_drop_fixed(e)),
        'B_pop_log_isf': ('Population log-ISF', lambda e: predict_drop_pop_log(e)),
        'C_patient_log_isf': ('Per-patient log-ISF', None),  # needs patient_curves
        'D_linear_ratio': ('Linear ISF ratio (Rd3)', lambda e: predict_drop_linear_ratio(e)),
        'E_iob_weighted': ('IOB-weighted fixed', lambda e: predict_drop_iob_weighted(e)),
        'F_iob_log': ('IOB-weighted log-ISF', lambda e: predict_drop_iob_log(e)),
    }

    results = {}
    for key, (label, fn) in models.items():
        print(f"\n--- {label} ---")
        if key == 'C_patient_log_isf':
            result = evaluate_model(events, predict_drop_patient_log, patient_curves)
        else:
            result = evaluate_model(events, fn)

        if result is None:
            print("  Insufficient data")
            continue

        results[key] = result
        results[key]['label'] = label
        print(f"  N={result['n']}, MAE={result['mae']:.1f}, RMSE={result['rmse']:.1f}, "
              f"Bias={result['bias']:.1f}")
        print(f"  r={result['r']:.3f}, R²={result['r_squared']:.3f}, "
              f"Over-predict={result['over_pred_pct']:.0f}%")

        if result['dose_bins']:
            for bin_label, db in sorted(result['dose_bins'].items()):
                print(f"    {bin_label:>5s}: n={db['n']:>3}, MAE={db['mae']:>6.1f}, "
                      f"bias={db['bias']:>7.1f}, over={db['over_pred_pct']:>5.1f}%")

    # Comparison summary
    print("\n" + "=" * 65)
    print("MODEL COMPARISON SUMMARY")
    print("=" * 65)
    print(f"{'Model':>25s} {'MAE':>6s} {'RMSE':>6s} {'Bias':>7s} {'R²':>6s} {'Over%':>6s}")
    print("-" * 65)

    baseline_mae = results.get('A_fixed_isf', {}).get('mae', 999)
    for key in ['A_fixed_isf', 'B_pop_log_isf', 'C_patient_log_isf',
                'D_linear_ratio', 'E_iob_weighted', 'F_iob_log']:
        r = results.get(key)
        if r is None:
            continue
        improvement = (1 - r['mae'] / baseline_mae) * 100 if baseline_mae > 0 else 0
        marker = ' <-- best' if r['mae'] == min(
            v['mae'] for v in results.values()) else ''
        print(f"  {r['label']:>23s} {r['mae']:>6.1f} {r['rmse']:>6.1f} "
              f"{r['bias']:>7.1f} {r['r_squared']:>6.3f} {r['over_pred_pct']:>5.0f}%"
              f"  ({improvement:+.0f}%){marker}")

    # Hypothesis evaluation
    best_log = results.get('B_pop_log_isf', {})
    best_patient = results.get('C_patient_log_isf', {})
    baseline = results.get('A_fixed_isf', {})

    h1 = (baseline.get('mae', 0) - best_log.get('mae', 999)) / baseline.get('mae', 1) > 0.15
    h2_base_large = baseline.get('dose_bins', {}).get('>=3U', {}).get('mae', 0)
    h2_log_large = best_log.get('dose_bins', {}).get('>=3U', {}).get('mae', 999)
    h2 = h2_log_large < h2_base_large if h2_base_large > 0 else False
    h3 = best_log.get('over_pred_pct', 100) < 40
    h4_diff = abs(best_log.get('mae', 0) - best_patient.get('mae', 0))
    h4_pct = h4_diff / best_log.get('mae', 1) * 100 if best_log.get('mae', 0) > 0 else 999
    h4 = h4_pct < 10

    print(f"\n--- Hypothesis Results ---")
    print(f"  H1 (log-ISF MAE >15% better):       {'PASS' if h1 else 'FAIL'} "
          f"(improvement: {(1-best_log.get('mae',0)/baseline.get('mae',1))*100:.1f}%)")
    print(f"  H2 (improvement in >=3U):            {'PASS' if h2 else 'FAIL'} "
          f"(fixed={h2_base_large:.0f} vs log={h2_log_large:.0f})")
    print(f"  H3 (over-prediction <40%):           {'PASS' if h3 else 'FAIL'} "
          f"(log={best_log.get('over_pred_pct',0):.0f}%)")
    print(f"  H4 (per-patient <10% better):        {'PASS' if h4 else 'FAIL'} "
          f"(diff={h4_pct:.1f}%)")

    # Save
    def convert(obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        raise TypeError(f'{type(obj)} not serializable')

    output = {
        'experiment': 'EXP-2641',
        'title': 'Forward Simulation with Dose-Dependent (Log) ISF',
        'n_events': len(events),
        'models': {k: {kk: vv for kk, vv in v.items()
                        if kk not in ('predicted', 'actual', 'residuals')}
                   for k, v in results.items()},
        'hypotheses': {
            'H1_log_isf_15pct_better': h1,
            'H2_large_dose_improvement': h2,
            'H3_over_prediction_below_40': h3,
            'H4_universal_scaling_viable': h4,
        },
        'predictions': {k: {'predicted': v['predicted'],
                             'actual': v['actual'],
                             'residuals': v['residuals']}
                        for k, v in results.items()},
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2, default=convert)
    print(f"\nResults saved to {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
