#!/usr/bin/env python3
"""EXP-2642: Retrospective Correction Dose Audit

For each of the 219 corrections, computes the "optimal dose" that would have
produced a target drop, and compares what was given vs what should have been
given under fixed vs dose-adjusted ISF models.

Hypotheses:
  H1: Fixed ISF recommends >30% over-dose for corrections >=3U
  H2: Per-patient log-ISF recommends doses within 25% of optimal for >60% of events
  H3: Over-corrections (drop >target by 50+ mg/dL) are >3x more common in >=3U bin
  H4: Log-ISF dose adjustment would have prevented >40% of over-corrections

Methodology:
  - For each correction: actual dose, actual drop, pre-BG, target=100 mg/dL
  - "Ideal dose" = (pre_bg - target) / actual_apparent_ISF (what hindsight says)
  - "Fixed dose" = (pre_bg - target) / scheduled_ISF (what the AID used)
  - "Log dose" = iteratively solve: (pre_bg - target) = f(dose) * dose
  - Classify outcomes: under-correction, appropriate, over-correction, hypo
  - Compare dose recommendations across models

Dependencies: EXP-2636, EXP-2640 results
"""

import json
import os
import numpy as np
from scipy import stats, optimize
from collections import defaultdict

RESULTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'externals', 'experiments')
EXP2636_FILE = os.path.join(RESULTS_DIR, 'exp-2636_dose_dependent_isf.json')
EXP2640_FILE = os.path.join(RESULTS_DIR, 'exp-2640_per_patient_isf.json')
OUTPUT_FILE = os.path.join(RESULTS_DIR, 'exp-2642_retrospective_audit.json')

TARGET_BG = 100.0  # mg/dL target
HYPO_THRESHOLD = 70.0  # below this is hypo
ISF_FLOOR = 5.0
POP_LOG_A = 50.0
POP_LOG_B = -28.0


def load_data():
    with open(EXP2636_FILE) as f:
        events = json.load(f)['events']
    with open(EXP2640_FILE) as f:
        r2640 = json.load(f)
        patient_curves = r2640['per_patient']
    return events, patient_curves


def compute_log_isf(dose, a=POP_LOG_A, b=POP_LOG_B):
    """Population log-ISF for a given dose."""
    return max(ISF_FLOOR, a + b * np.log(max(0.01, dose)))


def solve_log_dose(desired_drop, a=POP_LOG_A, b=POP_LOG_B, max_dose=20.0):
    """Solve: desired_drop = max(5, a + b*ln(dose)) * dose for dose."""
    def residual(d):
        isf = max(ISF_FLOOR, a + b * np.log(max(0.01, d)))
        return isf * d - desired_drop

    if desired_drop <= 0:
        return 0.0

    try:
        result = optimize.brentq(residual, 0.01, max_dose)
        return float(result)
    except ValueError:
        # No root in range — drop too large for model
        return max_dose


def classify_outcome(pre_bg, nadir_bg, target=TARGET_BG):
    """Classify the correction outcome."""
    if nadir_bg < HYPO_THRESHOLD:
        return 'hypo'
    elif nadir_bg < target - 20:
        return 'over_correction'  # went too low (below target-20)
    elif nadir_bg > target + 40:
        return 'under_correction'  # didn't come down enough
    else:
        return 'appropriate'  # within target ± reasonable margin


def audit_correction(event, patient_curves):
    """Audit a single correction event."""
    pre_bg = event['pre_bg']
    nadir_bg = event['nadir_bg']
    drop = event['drop']
    bolus_u = event['bolus_u']
    pid = event['patient_id']
    scheduled_isf = event.get('scheduled_isf')

    desired_drop = pre_bg - TARGET_BG
    if desired_drop <= 0:
        return None  # Already at or below target

    # Actual outcome
    outcome = classify_outcome(pre_bg, nadir_bg)
    excess_drop = drop - desired_drop  # positive = went too far

    # Model A: Fixed ISF dose recommendation
    if scheduled_isf and scheduled_isf > 0:
        fixed_dose = desired_drop / scheduled_isf
        fixed_predicted_drop = scheduled_isf * bolus_u
    else:
        fixed_dose = None
        fixed_predicted_drop = None

    # Model B: Population log-ISF dose recommendation
    pop_log_dose = solve_log_dose(desired_drop)
    pop_log_isf = compute_log_isf(bolus_u)
    pop_log_predicted_drop = pop_log_isf * bolus_u

    # Model C: Per-patient log-ISF dose recommendation
    curve = patient_curves.get(pid, {})
    log_fit = curve.get('log')
    if log_fit:
        a, b = log_fit['intercept'], log_fit['slope']
        patient_log_dose = solve_log_dose(desired_drop, a=a, b=b)
        patient_log_isf = max(ISF_FLOOR, a + b * np.log(max(0.01, bolus_u)))
        patient_log_predicted_drop = patient_log_isf * bolus_u
    else:
        patient_log_dose = pop_log_dose
        patient_log_isf = pop_log_isf
        patient_log_predicted_drop = pop_log_predicted_drop

    # Optimal dose (what hindsight says)
    actual_isf = drop / bolus_u if bolus_u > 0 else 0
    optimal_dose = desired_drop / actual_isf if actual_isf > 0 else bolus_u

    # Dose ratios (actual/optimal)
    dose_ratio_actual = bolus_u / optimal_dose if optimal_dose > 0 else 1.0
    dose_ratio_fixed = fixed_dose / optimal_dose if (fixed_dose and optimal_dose > 0) else None
    dose_ratio_pop_log = pop_log_dose / optimal_dose if optimal_dose > 0 else None
    dose_ratio_patient_log = patient_log_dose / optimal_dose if optimal_dose > 0 else None

    return {
        'patient_id': pid,
        'pre_bg': round(pre_bg, 1),
        'nadir_bg': round(nadir_bg, 1),
        'drop': round(drop, 1),
        'desired_drop': round(desired_drop, 1),
        'excess_drop': round(excess_drop, 1),
        'bolus_u': round(bolus_u, 2),
        'optimal_dose': round(optimal_dose, 2),
        'outcome': outcome,

        'fixed_dose': round(fixed_dose, 2) if fixed_dose else None,
        'pop_log_dose': round(pop_log_dose, 2),
        'patient_log_dose': round(patient_log_dose, 2),

        'dose_ratio_actual': round(dose_ratio_actual, 3),
        'dose_ratio_fixed': round(dose_ratio_fixed, 3) if dose_ratio_fixed else None,
        'dose_ratio_pop_log': round(dose_ratio_pop_log, 3) if dose_ratio_pop_log else None,
        'dose_ratio_patient_log': round(dose_ratio_patient_log, 3) if dose_ratio_patient_log else None,

        'actual_isf': round(actual_isf, 1),
        'scheduled_isf': round(scheduled_isf, 1) if scheduled_isf else None,
        'pop_log_isf': round(pop_log_isf, 1),
        'patient_log_isf': round(patient_log_isf, 1),
    }


def main():
    print("EXP-2642: Retrospective Correction Dose Audit")
    print("=" * 60)

    events, patient_curves = load_data()
    print(f"Loaded {len(events)} events")

    # Run audit
    audits = []
    for e in events:
        a = audit_correction(e, patient_curves)
        if a is not None:
            audits.append(a)

    print(f"Audited {len(audits)} corrections (target BG = {TARGET_BG})")

    # Outcome distribution
    outcomes = defaultdict(int)
    for a in audits:
        outcomes[a['outcome']] += 1
    print(f"\n--- Actual Outcomes ---")
    for k in ['appropriate', 'under_correction', 'over_correction', 'hypo']:
        n = outcomes.get(k, 0)
        print(f"  {k:>20s}: {n:>4} ({n/len(audits)*100:>5.1f}%)")

    # Dose analysis by bin
    print(f"\n--- Dose Appropriateness by Bolus Size ---")
    dose_bins = [(0, 1.0, '<1U'), (1.0, 2.0, '1-2U'),
                 (2.0, 3.0, '2-3U'), (3.0, 100, '>=3U')]

    for lo, hi, label in dose_bins:
        bin_events = [a for a in audits if lo <= a['bolus_u'] < hi]
        if not bin_events:
            continue
        n = len(bin_events)
        over = sum(1 for a in bin_events if a['outcome'] in ('over_correction', 'hypo'))
        under = sum(1 for a in bin_events if a['outcome'] == 'under_correction')
        hypo = sum(1 for a in bin_events if a['outcome'] == 'hypo')
        mean_excess = np.mean([a['excess_drop'] for a in bin_events])
        mean_ratio = np.mean([a['dose_ratio_actual'] for a in bin_events])
        print(f"  {label:>5s}: n={n:>3}, over={over:>3} ({over/n*100:>5.1f}%), "
              f"hypo={hypo:>2}, under={under:>3}, "
              f"mean_excess={mean_excess:>+6.1f}, dose_ratio={mean_ratio:.2f}")

    # Model dose recommendations comparison
    print(f"\n--- Model Dose Recommendations vs Optimal ---")
    for model_key, model_label in [
        ('dose_ratio_fixed', 'Fixed ISF'),
        ('dose_ratio_pop_log', 'Pop log-ISF'),
        ('dose_ratio_patient_log', 'Patient log-ISF'),
    ]:
        ratios = [a[model_key] for a in audits if a[model_key] is not None]
        if not ratios:
            continue
        ratios = np.array(ratios)
        within_25 = float(np.mean(np.abs(ratios - 1.0) < 0.25)) * 100
        over_dose = float(np.mean(ratios > 1.25)) * 100
        under_dose = float(np.mean(ratios < 0.75)) * 100
        print(f"  {model_label:>18s}: median ratio={np.median(ratios):.2f}, "
              f"within ±25%={within_25:.0f}%, "
              f"over-dose={over_dose:.0f}%, under-dose={under_dose:.0f}%")

    # Would log-ISF have prevented over-corrections?
    print(f"\n--- Prevention Analysis ---")
    over_corrections = [a for a in audits
                        if a['outcome'] in ('over_correction', 'hypo')]
    print(f"Total over-corrections/hypos: {len(over_corrections)}/{len(audits)}")

    if over_corrections:
        # For each over-correction, would log-ISF have recommended a smaller dose?
        prevented_pop = 0
        prevented_patient = 0
        for a in over_corrections:
            if a['pop_log_dose'] < a['bolus_u'] * 0.9:  # log would have dosed ≥10% less
                prevented_pop += 1
            if a['patient_log_dose'] < a['bolus_u'] * 0.9:
                prevented_patient += 1

        print(f"  Pop log-ISF would dose >=10% less in {prevented_pop}/{len(over_corrections)} "
              f"({prevented_pop/len(over_corrections)*100:.0f}%) of over-corrections")
        print(f"  Patient log-ISF would dose >=10% less in {prevented_patient}/{len(over_corrections)} "
              f"({prevented_patient/len(over_corrections)*100:.0f}%) of over-corrections")

    # Stratified prevention analysis by dose bin
    print(f"\n--- Over-Correction Prevention by Dose Bin ---")
    for lo, hi, label in dose_bins:
        bin_over = [a for a in over_corrections if lo <= a['bolus_u'] < hi]
        if not bin_over:
            continue
        pp = sum(1 for a in bin_over if a['patient_log_dose'] < a['bolus_u'] * 0.9)
        mean_reduction = np.mean([(a['bolus_u'] - a['patient_log_dose']) / a['bolus_u'] * 100
                                   for a in bin_over])
        print(f"  {label:>5s}: {len(bin_over):>3} over-corrections, "
              f"log would prevent {pp} ({pp/len(bin_over)*100:.0f}%), "
              f"mean dose reduction {mean_reduction:+.0f}%")

    # Clinical impact summary
    print(f"\n--- Clinical Impact Summary ---")
    # How many hypos could be avoided?
    hypos = [a for a in audits if a['outcome'] == 'hypo']
    hypos_prevented_patient = sum(
        1 for a in hypos if a['patient_log_dose'] < a['bolus_u'] * 0.8)
    print(f"  Hypo events: {len(hypos)}")
    if hypos:
        print(f"  Patient log-ISF would dose >=20% less: "
              f"{hypos_prevented_patient}/{len(hypos)} "
              f"({hypos_prevented_patient/len(hypos)*100:.0f}%)")

        # Mean nadir for hypos
        mean_hypo_nadir = np.mean([a['nadir_bg'] for a in hypos])
        mean_hypo_excess = np.mean([a['excess_drop'] for a in hypos])
        print(f"  Mean hypo nadir: {mean_hypo_nadir:.0f} mg/dL, "
              f"mean excess drop: {mean_hypo_excess:+.0f} mg/dL")

    # Hypothesis evaluation
    # H1: Fixed ISF recommends >30% over-dose for corrections >=3U
    large_audits = [a for a in audits if a['bolus_u'] >= 3.0 and a['dose_ratio_fixed'] is not None]
    if large_audits:
        mean_fixed_ratio_large = np.mean([a['dose_ratio_fixed'] for a in large_audits])
        h1 = mean_fixed_ratio_large > 1.3
    else:
        h1 = False
        mean_fixed_ratio_large = 0

    # H2: Per-patient log-ISF within 25% of optimal for >60%
    patient_ratios = [a['dose_ratio_patient_log'] for a in audits
                      if a['dose_ratio_patient_log'] is not None]
    h2_pct = float(np.mean(np.abs(np.array(patient_ratios) - 1.0) < 0.25)) * 100
    h2 = h2_pct > 60

    # H3: Over-corrections >3x more common in >=3U
    small_over_rate = sum(1 for a in audits if a['bolus_u'] < 2 and
                          a['outcome'] in ('over_correction', 'hypo')) / max(1, sum(1 for a in audits if a['bolus_u'] < 2))
    large_over_rate = sum(1 for a in audits if a['bolus_u'] >= 3 and
                          a['outcome'] in ('over_correction', 'hypo')) / max(1, sum(1 for a in audits if a['bolus_u'] >= 3))
    h3_ratio = large_over_rate / small_over_rate if small_over_rate > 0 else 0
    h3 = h3_ratio > 3.0

    # H4: Log-ISF prevents >40% of over-corrections
    h4_pct = prevented_patient / len(over_corrections) * 100 if over_corrections else 0
    h4 = h4_pct > 40

    print(f"\n--- Hypothesis Results ---")
    print(f"  H1 (fixed >30% over-dose at >=3U):   {'PASS' if h1 else 'FAIL'} "
          f"(mean ratio={mean_fixed_ratio_large:.2f})")
    print(f"  H2 (patient-log within ±25% >60%):   {'PASS' if h2 else 'FAIL'} "
          f"({h2_pct:.0f}%)")
    print(f"  H3 (over-corr >3x at >=3U vs <2U):   {'PASS' if h3 else 'FAIL'} "
          f"(ratio={h3_ratio:.1f}x)")
    print(f"  H4 (log prevents >40% over-corr):    {'PASS' if h4 else 'FAIL'} "
          f"({h4_pct:.0f}%)")

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
        'experiment': 'EXP-2642',
        'title': 'Retrospective Correction Dose Audit',
        'n_audited': len(audits),
        'target_bg': TARGET_BG,
        'outcomes': dict(outcomes),
        'audits': audits,
        'hypotheses': {
            'H1_fixed_overdose_large': h1,
            'H2_patient_log_within_25pct': h2,
            'H3_over_corr_rate_ratio': h3,
            'H4_log_prevents_over_corr': h4,
        },
        'summary': {
            'n_over_corrections': len(over_corrections),
            'n_hypos': len(hypos),
            'prevented_by_pop_log': prevented_pop,
            'prevented_by_patient_log': prevented_patient,
            'h3_ratio': round(h3_ratio, 2),
        }
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2, default=convert)
    print(f"\nResults saved to {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
