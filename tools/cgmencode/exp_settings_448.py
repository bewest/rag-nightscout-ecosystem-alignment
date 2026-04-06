#!/usr/bin/env python3
"""EXP-448 through EXP-454: Settings Assessment & Encoding Validation.

Building on the metabolic flux decomposition (EXP-435–447), these experiments
test whether the supply-demand framework can assess therapy settings quality
and detect when profiles need adjustment.

Experiment registry:
    EXP-448: Hepatic-detrended meal peak detection
    EXP-449: Derivative-based rising edge detection
    EXP-450: Basal adequacy score from overnight supply/demand ratio
    EXP-451: ISF adequacy from correction bolus response
    EXP-452: CR adequacy from announced meal response
    EXP-453: Composite settings fidelity score
    EXP-454: Conservation integral as quality gate

Key insight: The supply-demand decomposition provides a natural framework for
evaluating whether therapy settings (basal rate, ISF, CR) match the patient's
actual physiology.  Deviations between expected and observed responses indicate
settings that need adjustment.

References:
    - exp_metabolic_441.py: compute_supply_demand(), compute_rolling_tdd()
    - exp_metabolic_flux.py: load_patients(), classify_windows_by_event()
    - continuous_pk.py: compute_hepatic_production(), PK channels
    - encoding-validation-report-2026-04-06.md: EXP-421 conservation test
    - metabolic-flux-report-2026-04-06.md: Full theoretical framework

Usage:
    python -m cgmencode.exp_settings_448 -e all --quick
    python -m cgmencode.exp_settings_448 -e 450 451
    python -m cgmencode.exp_settings_448 --summary
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

import numpy as np
from scipy.signal import find_peaks

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.exp_metabolic_flux import (
    load_patients, _extract_isf_scalar, _extract_cr_scalar,
    classify_windows_by_event, save_results,
)
from cgmencode.exp_metabolic_441 import compute_supply_demand, compute_rolling_tdd
from cgmencode.continuous_pk import build_continuous_pk_features

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288


# -------------------------------------------------------------------
# EXP-448: Hepatic-Detrended Meal Peak Detection
# -------------------------------------------------------------------

def run_exp448(patients, args):
    """EXP-448: Subtract hepatic baseline from supply before peak detection.

    Hypothesis: Removing the always-on hepatic production signal sharpens
    meal-specific peaks, improving detection of smaller meals that are
    currently masked by the hepatic floor (which is 17-96% of supply
    depending on patient).
    """
    print("\n=== EXP-448: Hepatic-Detrended Meal Peaks ===")
    results = {'experiment_id': 'EXP-448', 'timestamp': datetime.utcnow().isoformat()}
    per_patient = {}

    for p in patients:
        pid = p['name']
        sd = compute_supply_demand(p['df'], p['pk'])
        carb_supply = sd['carb_supply']  # supply - hepatic (already detrended)
        supply = sd['supply']
        demand = sd['demand']
        n_days = len(supply) / STEPS_PER_DAY

        # Compare: raw supply peaks vs hepatic-detrended (carb_supply) peaks
        for signal_name, signal in [('raw_supply', supply),
                                     ('carb_only', carb_supply),
                                     ('sum_flux', np.abs(carb_supply) + demand)]:
            smoothed = np.convolve(signal, np.ones(6)/6, mode='same')
            pos = smoothed[smoothed > 0]
            if len(pos) < 20:
                continue
            q75, q25 = np.percentile(pos, [75, 25])
            iqr = q75 - q25
            prominence = max(iqr * 0.5, 0.01)
            peaks, props = find_peaks(smoothed, distance=18, prominence=prominence)
            ppd = len(peaks) / n_days

            # Match against announced meals
            carbs = np.zeros(len(p['df']))
            for col in ['carbInput', 'carbs']:
                if col in p['df'].columns:
                    carbs = p['df'][col].fillna(0).values[:len(signal)]
                    break
            meal_idx = np.where(carbs > 5)[0]
            matched = 0
            used = set()
            for mi in meal_idx:
                for pi_i, pi in enumerate(peaks):
                    if pi_i not in used and abs(int(pi) - int(mi)) <= 12:
                        matched += 1
                        used.add(pi_i)
                        break
            n_meals = len(meal_idx)
            recall = matched / n_meals if n_meals > 0 else float('nan')
            precision = matched / len(peaks) if len(peaks) > 0 else float('nan')

            key = f'{pid}_{signal_name}'
            per_patient.setdefault(pid, {})[signal_name] = {
                'peaks_per_day': round(ppd, 2),
                'total_peaks': len(peaks),
                'matched': matched,
                'announced_meals': n_meals,
                'precision': round(precision, 3) if not np.isnan(precision) else None,
                'recall': round(recall, 3) if not np.isnan(recall) else None,
            }

        # Improvement: carb_only vs raw_supply
        raw = per_patient[pid].get('raw_supply', {})
        detrended = per_patient[pid].get('carb_only', {})
        flux = per_patient[pid].get('sum_flux', {})
        print(f"  {pid}: raw_supply={raw.get('peaks_per_day',0):.1f}/d  "
              f"carb_only={detrended.get('peaks_per_day',0):.1f}/d  "
              f"sum_flux={flux.get('peaks_per_day',0):.1f}/d  "
              f"(announced={raw.get('announced_meals',0)/max(len(supply)/STEPS_PER_DAY,1):.1f}/d)")

    results['per_patient'] = per_patient
    save_results(results, 'exp448_hepatic_detrended')
    return results


# -------------------------------------------------------------------
# EXP-449: Derivative-Based Rising Edge Detection
# -------------------------------------------------------------------

def run_exp449(patients, args):
    """EXP-449: Detect meals from rapid increases in throughput.

    Hypothesis: The derivative of metabolic throughput catches rising edges
    of meal events regardless of absolute magnitude, complementing peak-based
    detection for small meals below prominence thresholds.
    """
    print("\n=== EXP-449: Derivative Rising Edge Detection ===")
    results = {'experiment_id': 'EXP-449', 'timestamp': datetime.utcnow().isoformat()}
    per_patient = {}

    for p in patients:
        pid = p['name']
        sd = compute_supply_demand(p['df'], p['pk'])
        sum_flux = np.abs(sd['carb_supply']) + sd['demand']
        n_days = len(sum_flux) / STEPS_PER_DAY

        # Smooth then differentiate
        smoothed = np.convolve(sum_flux, np.ones(6)/6, mode='same')
        derivative = np.diff(smoothed, prepend=smoothed[0])

        # Positive derivative = rising throughput
        pos_deriv = np.maximum(derivative, 0)

        # Adaptive threshold on positive derivative
        pos_vals = pos_deriv[pos_deriv > 0]
        if len(pos_vals) < 20:
            per_patient[pid] = {'status': 'insufficient_data'}
            continue

        # Detect peaks in derivative (rising edges)
        p75 = np.percentile(pos_vals, 75)
        p50 = np.percentile(pos_vals, 50)

        for thresh_name, thresh in [('sensitive', p50), ('moderate', p75)]:
            edges, _ = find_peaks(pos_deriv, height=thresh, distance=18)
            epd = len(edges) / n_days

            # Match to announced meals
            carbs = np.zeros(len(p['df']))
            for col in ['carbInput', 'carbs']:
                if col in p['df'].columns:
                    carbs = p['df'][col].fillna(0).values[:len(sum_flux)]
                    break
            meal_idx = np.where(carbs > 5)[0]
            matched = 0
            used = set()
            for mi in meal_idx:
                for ei_i, ei in enumerate(edges):
                    if ei_i not in used and abs(int(ei) - int(mi)) <= 15:
                        matched += 1
                        used.add(ei_i)
                        break
            n_meals = len(meal_idx)
            recall = matched / n_meals if n_meals > 0 else float('nan')
            precision = matched / len(edges) if len(edges) > 0 else float('nan')

            per_patient.setdefault(pid, {})[thresh_name] = {
                'edges_per_day': round(epd, 2),
                'total_edges': len(edges),
                'matched': matched,
                'precision': round(precision, 3) if not np.isnan(precision) else None,
                'recall': round(recall, 3) if not np.isnan(recall) else None,
            }

        sens = per_patient[pid].get('sensitive', {})
        mod = per_patient[pid].get('moderate', {})
        print(f"  {pid}: sensitive={sens.get('edges_per_day',0):.1f}/d R={sens.get('recall','?')}  "
              f"moderate={mod.get('edges_per_day',0):.1f}/d R={mod.get('recall','?')}")

    results['per_patient'] = per_patient
    save_results(results, 'exp449_derivative_edges')
    return results


# -------------------------------------------------------------------
# EXP-450: Basal Adequacy Score
# -------------------------------------------------------------------

def run_exp450(patients, args):
    """EXP-450: Overnight supply/demand ratio as basal adequacy score.

    Hypothesis: If basal rates are correct, overnight fasting periods
    (midnight-6 AM, no meals) should show supply/demand ratio near 1.0.
    Sustained deviations indicate basal settings need adjustment.

    Score interpretation:
        > 1.1 → basal too low (supply exceeds disposal → glucose rises)
        0.9-1.1 → well-tuned
        < 0.9 → basal too high (disposal exceeds supply → glucose falls)
    """
    print("\n=== EXP-450: Basal Adequacy Score ===")
    results = {'experiment_id': 'EXP-450', 'timestamp': datetime.utcnow().isoformat()}
    per_patient = {}

    for p in patients:
        pid = p['name']
        sd = compute_supply_demand(p['df'], p['pk'])
        supply = sd['supply']
        demand = sd['demand']
        n_steps = len(supply)
        n_days = n_steps / STEPS_PER_DAY

        # Identify overnight fasting windows (midnight-6AM = steps 0-72 of each day)
        overnight_ratios = []
        overnight_glucose_changes = []

        glucose = p['df'].iloc[:n_steps]
        glucose_vals = None
        for col in ['glucose', 'sgv', 'bg']:
            if col in p['df'].columns:
                glucose_vals = p['df'][col].ffill().values[:n_steps]
                break
        if glucose_vals is None:
            glucose_vals = p['grid'][:n_steps, 0] * 400  # denormalize

        # Check for carbs during overnight to exclude non-fasting nights
        carbs = np.zeros(n_steps)
        for col in ['carbInput', 'carbs']:
            if col in p['df'].columns:
                carbs = p['df'][col].fillna(0).values[:n_steps]
                break

        for day_i in range(int(n_days)):
            # Midnight to 6 AM = steps 0-72 within day
            start = day_i * STEPS_PER_DAY
            end = start + 72  # 6 hours
            if end > n_steps:
                break

            # Skip nights with carbs (not fasting)
            if np.sum(carbs[start:end]) > 5:
                continue

            # Supply/demand ratio
            s = supply[start:end]
            d = demand[start:end]
            valid = d > 0.01  # avoid division by near-zero
            if np.sum(valid) < 36:  # need at least 3h of valid data
                continue

            ratio = np.median(s[valid] / d[valid])
            overnight_ratios.append(ratio)

            # Glucose change over the period
            g_start = glucose_vals[start:start+6]
            g_end = glucose_vals[end-6:end]
            if len(g_start) > 0 and len(g_end) > 0:
                delta = np.nanmean(g_end) - np.nanmean(g_start)
                overnight_glucose_changes.append(delta)

        if len(overnight_ratios) < 5:
            per_patient[pid] = {'status': 'insufficient_fasting_nights'}
            print(f"  {pid}: insufficient fasting nights ({len(overnight_ratios)})")
            continue

        median_ratio = float(np.median(overnight_ratios))
        mean_delta_g = float(np.mean(overnight_glucose_changes)) if overnight_glucose_changes else 0

        # Classify basal adequacy
        if median_ratio > 1.1:
            assessment = 'basal_too_low'
        elif median_ratio < 0.9:
            assessment = 'basal_too_high'
        else:
            assessment = 'well_tuned'

        # Correlation between ratio and glucose change
        if len(overnight_ratios) == len(overnight_glucose_changes) and len(overnight_ratios) > 5:
            corr = float(np.corrcoef(overnight_ratios, overnight_glucose_changes)[0, 1])
        else:
            corr = None

        per_patient[pid] = {
            'n_fasting_nights': len(overnight_ratios),
            'median_ratio': round(median_ratio, 3),
            'std_ratio': round(float(np.std(overnight_ratios)), 3),
            'mean_glucose_change_overnight': round(mean_delta_g, 1),
            'ratio_glucose_correlation': round(corr, 3) if corr is not None else None,
            'assessment': assessment,
        }
        print(f"  {pid}: ratio={median_ratio:.2f} ΔBG={mean_delta_g:+.0f} mg/dL  "
              f"→ {assessment} ({len(overnight_ratios)} nights)")

    results['per_patient'] = per_patient

    # Aggregate
    valid = [v for v in per_patient.values() if 'median_ratio' in v]
    if valid:
        results['aggregate'] = {
            'mean_ratio': round(float(np.mean([v['median_ratio'] for v in valid])), 3),
            'patients_basal_low': sum(1 for v in valid if v['assessment'] == 'basal_too_low'),
            'patients_basal_high': sum(1 for v in valid if v['assessment'] == 'basal_too_high'),
            'patients_well_tuned': sum(1 for v in valid if v['assessment'] == 'well_tuned'),
        }
        print(f"\n  Aggregate: {results['aggregate']}")

    save_results(results, 'exp450_basal_adequacy')
    return results


# -------------------------------------------------------------------
# EXP-451: ISF Adequacy from Correction Responses
# -------------------------------------------------------------------

def run_exp451(patients, args):
    """EXP-451: Compare actual correction response to ISF-predicted response.

    For isolated correction boluses (insulin without nearby carbs), the
    glucose drop should equal dose × ISF.  Systematic deviations indicate
    the ISF setting doesn't match the patient's actual sensitivity.
    """
    print("\n=== EXP-451: ISF Adequacy from Corrections ===")
    results = {'experiment_id': 'EXP-451', 'timestamp': datetime.utcnow().isoformat()}
    per_patient = {}

    for p in patients:
        pid = p['name']
        df = p['df']
        n = len(df)

        isf = _extract_isf_scalar(df)
        if isf <= 0:
            per_patient[pid] = {'status': 'no_isf'}
            print(f"  {pid}: no ISF available")
            continue

        # Find bolus events
        bolus = np.zeros(n)
        for col in ['bolus', 'bolusInput', 'insulin']:
            if col in df.columns:
                bolus = df[col].fillna(0).values[:n]
                break

        carbs = np.zeros(n)
        for col in ['carbInput', 'carbs']:
            if col in df.columns:
                carbs = df[col].fillna(0).values[:n]
                break

        glucose_vals = p['grid'][:n, 0] * 400  # denormalize

        # Find isolated corrections: bolus > 0, no carbs within ±1h
        correction_events = []
        bolus_idx = np.where(bolus > 0.3)[0]  # at least 0.3U

        for bi in bolus_idx:
            # Check no carbs within ±1h (12 steps)
            carb_window_start = max(0, bi - 12)
            carb_window_end = min(n, bi + 12)
            if np.sum(carbs[carb_window_start:carb_window_end]) > 5:
                continue  # Not a pure correction

            # Check we have 3h of glucose data after
            if bi + 36 >= n:
                continue

            dose = bolus[bi]
            expected_drop = dose * isf
            pre_glucose = np.nanmean(glucose_vals[max(0, bi-3):bi+1])
            # Find nadir in 1-3h window
            post_window = glucose_vals[bi+6:bi+36]
            if len(post_window) == 0 or np.all(np.isnan(post_window)):
                continue
            nadir = np.nanmin(post_window)
            actual_drop = pre_glucose - nadir

            if expected_drop > 5:  # meaningful correction
                ratio = actual_drop / expected_drop
                correction_events.append({
                    'dose': round(float(dose), 2),
                    'expected_drop': round(float(expected_drop), 1),
                    'actual_drop': round(float(actual_drop), 1),
                    'isf_ratio': round(float(ratio), 3),
                })

        if len(correction_events) < 3:
            per_patient[pid] = {
                'status': 'insufficient_corrections',
                'n_corrections': len(correction_events),
                'isf_profile': round(isf, 1),
            }
            print(f"  {pid}: only {len(correction_events)} isolated corrections")
            continue

        ratios = [e['isf_ratio'] for e in correction_events]
        median_ratio = float(np.median(ratios))

        if median_ratio > 1.3:
            assessment = 'isf_too_conservative'
        elif median_ratio < 0.7:
            assessment = 'isf_too_aggressive'
        else:
            assessment = 'isf_adequate'

        per_patient[pid] = {
            'n_corrections': len(correction_events),
            'isf_profile': round(isf, 1),
            'median_isf_ratio': round(median_ratio, 3),
            'std_isf_ratio': round(float(np.std(ratios)), 3),
            'isf_effective': round(isf * median_ratio, 1),
            'assessment': assessment,
        }
        print(f"  {pid}: ISF_profile={isf:.0f}  actual/expected={median_ratio:.2f}  "
              f"ISF_effective={isf*median_ratio:.0f}  → {assessment} "
              f"({len(correction_events)} corrections)")

    results['per_patient'] = per_patient
    save_results(results, 'exp451_isf_adequacy')
    return results


# -------------------------------------------------------------------
# EXP-454: Conservation Integral Quality Gate
# -------------------------------------------------------------------

def run_exp454(patients, args):
    """EXP-454: Use glucose conservation integral as analysis quality gate.

    The integral of (actual_glucose − predicted_glucose) over 12h windows
    should be near zero if the physics model and settings are adequate.
    Large systematic residuals flag patients whose settings are too far
    out of alignment for reliable analysis.

    Quality gate thresholds:
        |error| < 15 mg·h  → ✅ Settings adequate
        15-40 mg·h         → ⚠️ Marginal
        > 40 mg·h          → ❌ Settings severely misaligned
    """
    print("\n=== EXP-454: Conservation Integral Quality Gate ===")
    results = {'experiment_id': 'EXP-454', 'timestamp': datetime.utcnow().isoformat()}
    per_patient = {}

    for p in patients:
        pid = p['name']
        sd = compute_supply_demand(p['df'], p['pk'])
        net = sd['net']  # supply - demand (predicted dBG/dt)
        n = len(net)
        n_days = n / STEPS_PER_DAY

        glucose_vals = p['grid'][:n, 0] * 400  # denormalize

        # Compute 12h window integrals
        window = 144  # 12h in 5-min steps
        stride = 72   # 6h stride (overlapping)
        integrals = []
        actual_deltas = []
        predicted_deltas = []

        for start in range(0, n - window, stride):
            end = start + window

            # Actual glucose change
            g_start_vals = glucose_vals[start:start+6]
            g_end_vals = glucose_vals[end-6:end]
            if np.any(np.isnan(g_start_vals)) or np.any(np.isnan(g_end_vals)):
                continue
            actual_delta = np.nanmean(g_end_vals) - np.nanmean(g_start_vals)

            # Predicted glucose change from physics
            predicted_delta = np.sum(net[start:end]) * (5.0 / 60.0)  # convert to mg/dL·h

            # Conservation residual
            residual = actual_delta - predicted_delta
            integrals.append(residual)
            actual_deltas.append(actual_delta)
            predicted_deltas.append(predicted_delta)

        if len(integrals) < 10:
            per_patient[pid] = {'status': 'insufficient_windows'}
            continue

        mean_residual = float(np.mean(integrals))
        abs_mean = abs(mean_residual)
        std_residual = float(np.std(integrals))

        if abs_mean < 15:
            quality = 'adequate'
        elif abs_mean < 40:
            quality = 'marginal'
        else:
            quality = 'misaligned'

        # Direction: positive = actual glucose higher than predicted
        direction = 'underpredicting' if mean_residual > 0 else 'overpredicting'

        # Correlation between actual and predicted
        corr = float(np.corrcoef(actual_deltas, predicted_deltas)[0, 1])

        per_patient[pid] = {
            'n_windows': len(integrals),
            'mean_residual_mg_h': round(mean_residual, 1),
            'std_residual_mg_h': round(std_residual, 1),
            'abs_mean_residual': round(abs_mean, 1),
            'actual_predicted_correlation': round(corr, 3),
            'direction': direction,
            'quality': quality,
        }
        print(f"  {pid}: residual={mean_residual:+.1f} ± {std_residual:.1f} mg·h  "
              f"corr={corr:.2f}  → {quality} ({direction})")

    results['per_patient'] = per_patient

    # Aggregate
    valid = [v for v in per_patient.values() if 'quality' in v]
    if valid:
        results['aggregate'] = {
            'adequate': sum(1 for v in valid if v['quality'] == 'adequate'),
            'marginal': sum(1 for v in valid if v['quality'] == 'marginal'),
            'misaligned': sum(1 for v in valid if v['quality'] == 'misaligned'),
            'mean_abs_residual': round(float(np.mean([v['abs_mean_residual'] for v in valid])), 1),
            'mean_correlation': round(float(np.mean([v['actual_predicted_correlation'] for v in valid])), 3),
        }
        print(f"\n  Aggregate: {results['aggregate']}")

    save_results(results, 'exp454_conservation_quality_gate')
    return results


# -------------------------------------------------------------------
# Registry & CLI
# -------------------------------------------------------------------

EXPERIMENTS = {
    '448': ('Hepatic-detrended meal peaks', run_exp448),
    '449': ('Derivative rising edge detection', run_exp449),
    '450': ('Basal adequacy score', run_exp450),
    '451': ('ISF adequacy from corrections', run_exp451),
    '454': ('Conservation integral quality gate', run_exp454),
}


def main():
    parser = argparse.ArgumentParser(
        description='EXP-448–454: Settings Assessment & Encoding Validation')
    parser.add_argument('--experiment', '-e', nargs='+', default=['all'],
                        help='Experiment number(s) or "all"')
    parser.add_argument('--quick', action='store_true',
                        help='First 4 patients only')
    parser.add_argument('--patient', '-p', help='Single patient ID')
    parser.add_argument('--summary', action='store_true',
                        help='Print registry and exit')
    args = parser.parse_args()

    if args.summary:
        print("Settings Assessment Experiments:")
        for eid, (desc, _) in sorted(EXPERIMENTS.items()):
            print(f"  EXP-{eid}: {desc}")
        return

    repo_root = Path(__file__).resolve().parent.parent.parent
    patients_dir = str(repo_root / 'externals' / 'ns-data' / 'patients')

    max_patients = 4 if args.quick else None
    patient_filter = args.patient or None
    patients = load_patients(patients_dir, max_patients=max_patients,
                             patient_filter=patient_filter)

    exp_ids = list(EXPERIMENTS.keys()) if 'all' in args.experiment else args.experiment

    for eid in exp_ids:
        if eid in EXPERIMENTS:
            _, run_fn = EXPERIMENTS[eid]
            run_fn(patients, args)
        else:
            print(f"Unknown experiment: {eid}")


if __name__ == '__main__':
    main()
