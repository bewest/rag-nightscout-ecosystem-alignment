#!/usr/bin/env python3
"""EXP-2640: Per-Patient Dose-Dependent ISF Curves

Tests whether dose-dependent ISF is universal across patients or driven
by a few outliers. Fits individual dose-response curves per patient.

Hypotheses:
  H1: Dose-ISF slope is negative for >= 7/9 patients (universal)
  H2: Per-patient ISF ratio has <2x range at matched dose (convergence)
  H3: Non-linear (log/sqrt) fits outperform linear for >=5/9 patients
  H4: Removing the top-2 patients preserves r < -0.3 (not outlier-driven)

Methodology:
  - Uses EXP-2636 events (219 corrections, EXP-2624 gold standard)
  - Per-patient: linear fit ISF vs bolus_u (where n >= 5)
  - Cross-patient: ISF at fixed dose quantiles
  - Non-linear comparison: linear vs log(dose) vs sqrt(dose)
  - Robustness: leave-one-patient-out sensitivity
"""

import json
import os
import numpy as np
from scipy import stats
from collections import defaultdict

RESULTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'externals', 'experiments')
INPUT_FILE = os.path.join(RESULTS_DIR, 'exp-2636_dose_dependent_isf.json')
OUTPUT_FILE = os.path.join(RESULTS_DIR, 'exp-2640_per_patient_isf.json')

MIN_EVENTS = 5


def load_events():
    with open(INPUT_FILE) as f:
        return json.load(f)['events']


def per_patient_curves(events):
    """Fit dose-ISF curves per patient."""
    by_patient = defaultdict(list)
    for e in events:
        by_patient[e['patient_id']].append(e)

    curves = {}
    for pid in sorted(by_patient):
        evts = by_patient[pid]
        n = len(evts)
        boluses = np.array([e['bolus_u'] for e in evts])
        isfs = np.array([e['apparent_isf'] for e in evts])
        drops = np.array([e['drop'] for e in evts])

        # Filter out NaN/Inf values
        valid_mask = np.isfinite(boluses) & np.isfinite(isfs) & np.isfinite(drops)
        if valid_mask.sum() < 2:
            curves[pid] = {
                'n_events': n, 'n_valid': 0, 'insufficient': True,
                'data': {'bolus_u': [], 'apparent_isf': [], 'drop': []},
            }
            continue
        boluses = boluses[valid_mask]
        isfs = isfs[valid_mask]
        drops = drops[valid_mask]
        n = len(boluses)

        curve = {
            'n_events': n,
            'bolus_range': [round(float(boluses.min()), 2), round(float(boluses.max()), 2)],
            'isf_range': [round(float(isfs.min()), 1), round(float(isfs.max()), 1)],
            'mean_isf': round(float(np.mean(isfs)), 1),
            'median_isf': round(float(np.median(isfs)), 1),
            'mean_bolus': round(float(np.mean(boluses)), 2),
        }

        if n >= MIN_EVENTS and np.std(boluses) > 0.1:
            # Linear fit: ISF = a + b*dose
            slope, intercept, r, p, se = stats.linregress(boluses, isfs)
            curve['linear'] = {
                'slope': round(float(slope), 2),
                'intercept': round(float(intercept), 1),
                'r': round(float(r), 3),
                'p': round(float(p), 6),
                'r_squared': round(float(r ** 2), 3),
            }

            # Log fit: ISF = a + b*log(dose)
            log_boluses = np.log(boluses + 0.01)
            sl, ic, r_log, p_log, se_log = stats.linregress(log_boluses, isfs)
            curve['log'] = {
                'slope': round(float(sl), 2),
                'intercept': round(float(ic), 1),
                'r': round(float(r_log), 3),
                'p': round(float(p_log), 6),
                'r_squared': round(float(r_log ** 2), 3),
            }

            # Sqrt fit: ISF = a + b*sqrt(dose)
            sqrt_boluses = np.sqrt(boluses)
            sl2, ic2, r_sqrt, p_sqrt, se2 = stats.linregress(sqrt_boluses, isfs)
            curve['sqrt'] = {
                'slope': round(float(sl2), 2),
                'intercept': round(float(ic2), 1),
                'r': round(float(r_sqrt), 3),
                'p': round(float(p_sqrt), 6),
                'r_squared': round(float(r_sqrt ** 2), 3),
            }

            # Best model
            models = {'linear': abs(r), 'log': abs(r_log), 'sqrt': abs(r_sqrt)}
            curve['best_model'] = max(models, key=models.get)

            # Drop ceiling: max drop regardless of dose
            curve['max_drop'] = round(float(drops.max()), 1)
            curve['mean_drop'] = round(float(np.mean(drops)), 1)

            # Raw data for visualization
            curve['data'] = {
                'bolus_u': [round(float(b), 2) for b in boluses],
                'apparent_isf': [round(float(i), 1) for i in isfs],
                'drop': [round(float(d), 1) for d in drops],
            }
        else:
            curve['insufficient'] = True
            curve['data'] = {
                'bolus_u': [round(float(b), 2) for b in boluses],
                'apparent_isf': [round(float(i), 1) for i in isfs],
                'drop': [round(float(d), 1) for d in drops],
            }

        curves[pid] = curve

    return curves


def leave_one_out(events):
    """Leave-one-patient-out sensitivity for dose-ISF."""
    patient_ids = sorted(set(e['patient_id'] for e in events))
    results = {}
    for exclude_pid in patient_ids:
        subset = [e for e in events if e['patient_id'] != exclude_pid]
        b = np.array([e['bolus_u'] for e in subset])
        i = np.array([e['apparent_isf'] for e in subset])
        # Filter NaN/Inf
        mask = np.isfinite(b) & np.isfinite(i)
        b, i = b[mask], i[mask]
        if len(b) < 3:
            results[exclude_pid] = {'n_remaining': len(b), 'r': 0.0, 'p': 1.0}
            continue
        r, p = stats.pearsonr(b, i)
        results[exclude_pid] = {
            'n_remaining': len(b),
            'r': round(float(r), 4),
            'p': round(float(p), 8),
        }
    return results


def dose_matched_comparison(events, curves):
    """Compare ISF across patients at matched dose levels."""
    # Find common dose range where >=3 patients have data
    patients_with_fits = {pid: c for pid, c in curves.items()
                          if not c.get('insufficient', False)}

    # For each patient, predict ISF at standard doses
    standard_doses = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0]
    predictions = {}
    for dose in standard_doses:
        preds = {}
        for pid, c in patients_with_fits.items():
            lo, hi = c['bolus_range']
            if lo <= dose <= hi:
                # Use linear fit to predict ISF at this dose
                preds[pid] = round(c['linear']['intercept'] +
                                   c['linear']['slope'] * dose, 1)
        if len(preds) >= 3:
            vals = list(preds.values())
            predictions[str(dose)] = {
                'patients': preds,
                'n_patients': len(preds),
                'mean': round(float(np.mean(vals)), 1),
                'std': round(float(np.std(vals)), 1),
                'cv': round(float(np.std(vals) / np.mean(vals) * 100), 1)
                       if np.mean(vals) > 0 else None,
                'range_ratio': round(float(max(vals) / min(vals)), 2)
                               if min(vals) > 0 else None,
            }

    return predictions


def drop_ceiling_analysis(events):
    """Analyze whether glucose drop has a ceiling and its mechanism."""
    by_patient = defaultdict(list)
    for e in events:
        by_patient[e['patient_id']].append(e)

    patient_ceilings = {}
    for pid in sorted(by_patient):
        evts = by_patient[pid]
        if len(evts) < MIN_EVENTS:
            continue
        drops = np.array([e['drop'] for e in evts])
        boluses = np.array([e['bolus_u'] for e in evts])

        # Is drop linearly related to dose or does it saturate?
        r_lin, p_lin = stats.pearsonr(boluses, drops)

        # Does drop have diminishing returns with dose?
        # Fit drop = a * (1 - exp(-b * dose))  approximated by checking
        # if log(dose) fits better than dose
        log_b = np.log(boluses + 0.01)
        r_log, p_log = stats.pearsonr(log_b, drops)

        patient_ceilings[pid] = {
            'n': len(evts),
            'max_drop': round(float(drops.max()), 1),
            'mean_drop': round(float(np.mean(drops)), 1),
            'p95_drop': round(float(np.percentile(drops, 95)), 1),
            'drop_dose_r_linear': round(float(r_lin), 3),
            'drop_dose_r_log': round(float(r_log), 3),
            'saturates': abs(r_log) > abs(r_lin),
        }

    return patient_ceilings


def main():
    print("EXP-2640: Per-Patient Dose-Dependent ISF Curves")
    print("=" * 60)

    events = load_events()
    print(f"Loaded {len(events)} events")

    # 1. Per-patient curves
    print("\n--- Per-Patient ISF Curves ---")
    curves = per_patient_curves(events)
    n_negative = 0
    n_fitted = 0
    best_model_counts = defaultdict(int)

    for pid, c in sorted(curves.items()):
        if c.get('insufficient'):
            print(f"  {pid}: n={c['n_events']} (insufficient for fit)")
            continue
        n_fitted += 1
        lin = c['linear']
        best = c['best_model']
        best_model_counts[best] += 1
        neg = lin['slope'] < 0
        if neg:
            n_negative += 1
        sig = '*' if lin['p'] < 0.05 else ''
        print(f"  {pid}: n={c['n_events']}, slope={lin['slope']:>7.1f}, "
              f"r={lin['r']:>6.3f}{sig:1s}, best={best}, "
              f"ISF range=[{c['isf_range'][0]:.0f}-{c['isf_range'][1]:.0f}]")

    print(f"\n  Negative slope: {n_negative}/{n_fitted} patients")
    print(f"  Best model: {dict(best_model_counts)}")

    # 2. Leave-one-out
    print("\n--- Leave-One-Out Sensitivity ---")
    loo = leave_one_out(events)
    r_values = [v['r'] for v in loo.values()]
    print(f"  r range: [{min(r_values):.3f}, {max(r_values):.3f}]")
    print(f"  All r < -0.3: {all(r < -0.3 for r in r_values)}")
    for pid, v in sorted(loo.items()):
        print(f"    exclude {pid}: r={v['r']:.3f} (N={v['n_remaining']})")

    # Find most influential patient
    full_r = stats.pearsonr(
        [e['bolus_u'] for e in events],
        [e['apparent_isf'] for e in events]
    )[0]
    influence = {pid: abs(v['r'] - full_r) for pid, v in loo.items()}
    most_influential = max(influence, key=influence.get)
    print(f"  Most influential: {most_influential} "
          f"(delta r={influence[most_influential]:.3f})")

    # 3. Dose-matched comparison
    print("\n--- Dose-Matched Cross-Patient Comparison ---")
    matched = dose_matched_comparison(events, curves)
    for dose, m in sorted(matched.items(), key=lambda x: float(x[0])):
        if m.get('cv') is not None:
            print(f"  At {dose}U: n={m['n_patients']} patients, "
                  f"ISF={m['mean']:.0f} +/- {m['std']:.0f} "
                  f"(CV={m['cv']:.0f}%, range_ratio={m['range_ratio']:.1f}x)")

    # 4. Drop ceiling
    print("\n--- Drop Ceiling Analysis ---")
    ceilings = drop_ceiling_analysis(events)
    n_saturating = sum(1 for c in ceilings.values() if c['saturates'])
    for pid, c in sorted(ceilings.items()):
        print(f"  {pid}: max_drop={c['max_drop']:.0f}, p95={c['p95_drop']:.0f}, "
              f"r_lin={c['drop_dose_r_linear']:.3f}, "
              f"r_log={c['drop_dose_r_log']:.3f}, "
              f"{'SATURATES' if c['saturates'] else 'linear'}")
    print(f"  Saturating: {n_saturating}/{len(ceilings)} patients")

    # 5. Hypothesis evaluation
    h1 = n_negative >= 7
    h2_range_ratios = [m['range_ratio'] for m in matched.values()
                       if m.get('range_ratio') is not None]
    h2 = all(r < 2.0 for r in h2_range_ratios) if h2_range_ratios else False
    nonlin_count = sum(1 for c in curves.values()
                       if not c.get('insufficient') and c.get('best_model') != 'linear')
    h3 = nonlin_count >= 5
    # H4: remove top-2 by event count
    top2 = sorted([(pid, len([e for e in events if e['patient_id'] == pid]))
                    for pid in set(e['patient_id'] for e in events)],
                   key=lambda x: -x[1])[:2]
    subset_no_top2 = [e for e in events
                       if e['patient_id'] not in [t[0] for t in top2]]
    if len(subset_no_top2) > 5:
        r_no_top2, _ = stats.pearsonr(
            [e['bolus_u'] for e in subset_no_top2],
            [e['apparent_isf'] for e in subset_no_top2]
        )
    else:
        r_no_top2 = 0
    h4 = r_no_top2 < -0.3

    print("\n--- Hypothesis Results ---")
    print(f"  H1 (negative slope >=7/9): {'PASS' if h1 else 'FAIL'} "
          f"({n_negative}/{n_fitted})")
    print(f"  H2 (dose-matched range <2x): {'PASS' if h2 else 'FAIL'} "
          f"(ratios: {[round(r,1) for r in h2_range_ratios]})")
    print(f"  H3 (non-linear best >=5/9): {'PASS' if h3 else 'FAIL'} "
          f"({nonlin_count}/{n_fitted})")
    print(f"  H4 (r<-0.3 without top-2): {'PASS' if h4 else 'FAIL'} "
          f"(r={r_no_top2:.3f}, excluding {[t[0] for t in top2]})")

    # Save
    def convert(obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        raise TypeError(f'{type(obj)} not serializable')

    results = {
        'experiment': 'EXP-2640',
        'title': 'Per-Patient Dose-Dependent ISF Curves',
        'n_events': len(events),
        'n_fitted_patients': n_fitted,
        'per_patient': curves,
        'leave_one_out': loo,
        'most_influential_patient': most_influential,
        'dose_matched': matched,
        'drop_ceiling': ceilings,
        'hypotheses': {
            'H1_negative_slope_universal': h1,
            'H2_dose_matched_convergence': h2,
            'H3_nonlinear_outperforms': h3,
            'H4_not_outlier_driven': h4,
        },
        'summary': {
            'n_negative_slopes': n_negative,
            'n_saturating_drop': n_saturating,
            'best_model_counts': dict(best_model_counts),
            'r_without_top2': round(float(r_no_top2), 3),
        },
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"\nResults saved to {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
