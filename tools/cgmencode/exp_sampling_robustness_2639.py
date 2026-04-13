#!/usr/bin/env python3
"""EXP-2639: Sampling Robustness Audit

Validates that our 219-correction dataset has adequate independence and
statistical power for the key findings from Rounds 1-3.

Hypotheses:
  H1: Dose-ISF (r=-0.56) survives subsampling to >72h-spaced events (N~108)
  H2: Block bootstrap (by patient) CI excludes zero for dose-ISF
  H3: Bolus autocorrelation is low enough (<0.5) to not inflate dose-ISF
  H4: 48h carb effects are underpowered (need >350 events)

Methodology:
  - Inter-correction spacing analysis per patient
  - Independence subsampling (>72h between consecutive events)
  - Block bootstrap (10,000 resamples by patient)
  - Power analysis for each finding
  - Autocorrelation of key features in consecutive corrections <48h apart

Dependencies: EXP-2636 results (events with dose, ISF, recovery data)
"""

import json
import os
import sys
import numpy as np
from scipy import stats
from collections import defaultdict

RESULTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'externals', 'experiments')
INPUT_FILE = os.path.join(RESULTS_DIR, 'exp-2636_dose_dependent_isf.json')
OUTPUT_FILE = os.path.join(RESULTS_DIR, 'exp-2639_sampling_robustness.json')


def load_events():
    with open(INPUT_FILE) as f:
        data = json.load(f)
    return data['events']


def compute_spacing(events):
    """Compute inter-correction spacing per patient."""
    by_patient = defaultdict(list)
    for e in events:
        by_patient[e['patient_id']].append(e)

    spacing_stats = {}
    all_spacings = []
    for pid in sorted(by_patient):
        evts = sorted(by_patient[pid], key=lambda x: x['index'])
        if len(evts) < 2:
            spacing_stats[pid] = {
                'n_events': len(evts), 'spacings': [],
                'mean_h': None, 'median_h': None, 'min_h': None
            }
            continue
        spacings = [(evts[j]['index'] - evts[j - 1]['index']) * 5 / 60
                     for j in range(1, len(evts))]
        all_spacings.extend(spacings)
        spacing_stats[pid] = {
            'n_events': len(evts),
            'mean_h': float(np.mean(spacings)),
            'median_h': float(np.median(spacings)),
            'min_h': float(np.min(spacings)),
            'n_lt_6h': int(np.sum(np.array(spacings) < 6)),
            'n_lt_48h': int(np.sum(np.array(spacings) < 48)),
            'n_lt_72h': int(np.sum(np.array(spacings) < 72)),
        }

    all_spacings = np.array(all_spacings)
    distribution = {}
    for thresh in [2, 4, 6, 12, 24, 48, 72, 120, 240]:
        n = int(np.sum(all_spacings < thresh))
        distribution[f'lt_{thresh}h'] = {
            'count': n, 'pct': round(n / len(all_spacings) * 100, 1)
        }

    return spacing_stats, all_spacings, distribution


def subsample_independent(events, min_spacing_h=72):
    """Keep only events with >min_spacing_h between consecutive per patient."""
    by_patient = defaultdict(list)
    for e in events:
        by_patient[e['patient_id']].append(e)

    independent = []
    for pid in sorted(by_patient):
        evts = sorted(by_patient[pid], key=lambda x: x['index'])
        last_idx = -999999
        for e in evts:
            spacing_h = (e['index'] - last_idx) * 5 / 60
            if spacing_h >= min_spacing_h:
                independent.append(e)
                last_idx = e['index']
    return independent


def autocorrelation_analysis(events):
    """Check autocorrelation of key features in close (<48h) consecutive pairs."""
    by_patient = defaultdict(list)
    for e in events:
        by_patient[e['patient_id']].append(e)

    close_pairs = []
    for pid in sorted(by_patient):
        evts = sorted(by_patient[pid], key=lambda x: x['index'])
        for j in range(1, len(evts)):
            spacing_h = (evts[j]['index'] - evts[j - 1]['index']) * 5 / 60
            if spacing_h < 48:
                close_pairs.append((evts[j - 1], evts[j], spacing_h))

    if len(close_pairs) < 5:
        return {'n_pairs': len(close_pairs), 'insufficient': True}

    results = {'n_pairs': len(close_pairs)}
    for field in ['bolus_u', 'apparent_isf', 'drop']:
        x1 = [p[0][field] for p in close_pairs]
        x2 = [p[1][field] for p in close_pairs]
        r, p = stats.pearsonr(x1, x2)
        results[f'{field}_autocorr'] = {'r': round(r, 4), 'p': round(p, 6)}

    return results


def block_bootstrap(events, n_boot=10000, seed=42):
    """Block bootstrap by patient for dose-ISF correlation."""
    patient_ids = sorted(set(e['patient_id'] for e in events))
    by_patient = defaultdict(list)
    for e in events:
        by_patient[e['patient_id']].append(e)

    rng = np.random.RandomState(seed)
    bootstrap_rs = []
    for _ in range(n_boot):
        sampled_pids = rng.choice(patient_ids, size=len(patient_ids), replace=True)
        sampled = []
        for spid in sampled_pids:
            sampled.extend(by_patient[spid])
        b = np.array([e['bolus_u'] for e in sampled])
        isf = np.array([e['apparent_isf'] for e in sampled])
        if len(b) > 5 and np.std(b) > 0 and np.std(isf) > 0:
            bootstrap_rs.append(stats.pearsonr(b, isf)[0])

    bootstrap_rs = np.array(bootstrap_rs)
    return {
        'n_boot': n_boot,
        'mean': round(float(np.mean(bootstrap_rs)), 4),
        'median': round(float(np.median(bootstrap_rs)), 4),
        'ci_2_5': round(float(np.percentile(bootstrap_rs, 2.5)), 4),
        'ci_97_5': round(float(np.percentile(bootstrap_rs, 97.5)), 4),
        'p_gt_neg03': round(float(np.mean(bootstrap_rs > -0.3)), 4),
        'p_gt_0': round(float(np.mean(bootstrap_rs > 0)), 4),
        'distribution': [round(float(v), 4) for v in bootstrap_rs],
    }


def power_analysis():
    """Compute minimum detectable effects and required N for each finding."""
    from scipy.stats import norm
    z_a = norm.ppf(0.975)  # two-sided alpha=0.05
    z_b = norm.ppf(0.80)   # power=0.80

    findings = {
        'dose_isf':       {'r': 0.56, 'label': 'Dose-ISF'},
        'bolus_recovery': {'r': 0.31, 'label': 'Bolus→Recovery'},
        'carbs_48h':      {'r': 0.15, 'label': '48h Carbs→Recovery'},
        'iob_decay':      {'r': 0.07, 'label': 'IOB Decay→Recovery'},
    }

    results = {}
    for key, info in findings.items():
        r = info['r']
        n_needed = int(np.ceil((z_a + z_b) ** 2 / np.arctanh(r) ** 2)) + 3
        results[key] = {
            'label': info['label'],
            'observed_r': r,
            'n_needed_80pct': n_needed,
            'powered_at_219': n_needed <= 219,
        }

    r_min_219 = float(np.tanh(np.sqrt((z_a + z_b) ** 2 / 219)))
    r_min_108 = float(np.tanh(np.sqrt((z_a + z_b) ** 2 / 108)))
    results['min_detectable'] = {
        'N_219': round(r_min_219, 3),
        'N_108': round(r_min_108, 3),
    }
    return results


def test_on_subset(events, label):
    """Compute dose-ISF and bolus→recovery on a subset."""
    boluses = np.array([e['bolus_u'] for e in events])
    isfs = np.array([e['apparent_isf'] for e in events])
    r_isf, p_isf = stats.pearsonr(boluses, isfs)

    valid_rec = [(e['bolus_u'], e['recovery_slope'])
                 for e in events if e.get('recovery_slope') is not None]
    if len(valid_rec) >= 5:
        rb = np.array([v[0] for v in valid_rec])
        rs = np.array([v[1] for v in valid_rec])
        r_rec, p_rec = stats.pearsonr(rb, rs)
    else:
        r_rec, p_rec = None, None

    # Dose-response bins
    dose_bins = []
    for lo, hi, label_bin in [(0, 1.0, '<1U'), (1.0, 2.0, '1-2U'),
                               (2.0, 3.0, '2-3U'), (3.0, 100, '>=3U')]:
        mask = (boluses >= lo) & (boluses < hi)
        n = int(mask.sum())
        if n >= 2:
            dose_bins.append({
                'bin': label_bin, 'n': n,
                'mean_isf': round(float(np.mean(isfs[mask])), 1),
                'std_isf': round(float(np.std(isfs[mask])), 1),
            })

    return {
        'label': label,
        'n_events': len(events),
        'dose_isf_r': round(float(r_isf), 4),
        'dose_isf_p': round(float(p_isf), 8),
        'bolus_recovery_r': round(float(r_rec), 4) if r_rec is not None else None,
        'bolus_recovery_p': round(float(p_rec), 8) if p_rec is not None else None,
        'dose_bins': dose_bins,
    }


def main():
    print("EXP-2639: Sampling Robustness Audit")
    print("=" * 60)

    events = load_events()
    print(f"Loaded {len(events)} correction events from EXP-2636")

    # 1. Spacing analysis
    print("\n--- Inter-Correction Spacing ---")
    spacing_stats, all_spacings, distribution = compute_spacing(events)
    for pid, s in spacing_stats.items():
        if s.get('mean_h') is not None:
            print(f"  {pid}: n={s['n_events']}, mean={s['mean_h']:.1f}h, "
                  f"med={s['median_h']:.1f}h, min={s['min_h']:.1f}h, "
                  f"<6h={s['n_lt_6h']}, <48h={s['n_lt_48h']}")
        else:
            print(f"  {pid}: n={s['n_events']} (too few for spacing)")

    print(f"\n  Insulin overlap (<6h): "
          f"{distribution['lt_6h']['count']}/{len(all_spacings)} "
          f"({distribution['lt_6h']['pct']}%)")
    print(f"  Carb context overlap (<48h): "
          f"{distribution['lt_48h']['count']}/{len(all_spacings)} "
          f"({distribution['lt_48h']['pct']}%)")
    print(f"  Fully independent (>72h): "
          f"{len(all_spacings) - distribution['lt_72h']['count']}/{len(all_spacings)} "
          f"({100 - distribution['lt_72h']['pct']:.1f}%)")

    # 2. Autocorrelation
    print("\n--- Autocorrelation (consecutive pairs <48h) ---")
    autocorr = autocorrelation_analysis(events)
    for field in ['bolus_u', 'apparent_isf', 'drop']:
        ac = autocorr[f'{field}_autocorr']
        print(f"  {field}: r={ac['r']:.3f} (p={ac['p']:.4f})")

    # 3. Full dataset results
    print("\n--- Full Dataset (N=219) ---")
    full = test_on_subset(events, 'full')
    print(f"  Dose-ISF r={full['dose_isf_r']:.3f} (p={full['dose_isf_p']:.2e})")
    print(f"  Bolus→Recovery r={full['bolus_recovery_r']:.3f} (p={full['bolus_recovery_p']:.4f})")

    # 4. Independent subset (>72h)
    print("\n--- Independent Subset (>72h spacing) ---")
    independent = subsample_independent(events, 72)
    indep = test_on_subset(independent, 'independent_72h')
    print(f"  N={indep['n_events']}")
    print(f"  Dose-ISF r={indep['dose_isf_r']:.3f} (p={indep['dose_isf_p']:.2e})")
    if indep['bolus_recovery_r'] is not None:
        print(f"  Bolus→Recovery r={indep['bolus_recovery_r']:.3f} (p={indep['bolus_recovery_p']:.4f})")

    # 5. Aggressive subset (>120h)
    independent_120 = subsample_independent(events, 120)
    indep120 = test_on_subset(independent_120, 'independent_120h')
    print(f"\n--- Aggressive Subset (>120h spacing, N={indep120['n_events']}) ---")
    print(f"  Dose-ISF r={indep120['dose_isf_r']:.3f} (p={indep120['dose_isf_p']:.2e})")

    # 6. Block bootstrap
    print("\n--- Block Bootstrap (10,000 resamples by patient) ---")
    bootstrap = block_bootstrap(events)
    print(f"  Dose-ISF 95% CI: [{bootstrap['ci_2_5']:.3f}, {bootstrap['ci_97_5']:.3f}]")
    print(f"  Mean: {bootstrap['mean']:.3f}, Median: {bootstrap['median']:.3f}")
    print(f"  P(r > -0.3): {bootstrap['p_gt_neg03'] * 100:.1f}%")
    print(f"  P(r > 0): {bootstrap['p_gt_0'] * 100:.1f}%")

    # 7. Power analysis
    print("\n--- Power Analysis (alpha=0.05, power=0.80) ---")
    power = power_analysis()
    for key in ['dose_isf', 'bolus_recovery', 'carbs_48h', 'iob_decay']:
        p = power[key]
        status = "POWERED" if p['powered_at_219'] else "UNDERPOWERED"
        print(f"  {p['label']:25s} |r|={p['observed_r']:.2f}  "
              f"N_needed={p['n_needed_80pct']:>5}  {status}")
    print(f"  Min detectable at N=219: r={power['min_detectable']['N_219']:.3f}")
    print(f"  Min detectable at N=108: r={power['min_detectable']['N_108']:.3f}")

    # 8. Hypothesis evaluation
    h1 = abs(indep['dose_isf_r']) >= 0.4 and indep['dose_isf_p'] < 0.001
    h2 = bootstrap['ci_97_5'] < 0
    h3 = abs(autocorr['bolus_u_autocorr']['r']) < 0.5
    h4 = not power['carbs_48h']['powered_at_219']

    print("\n--- Hypothesis Results ---")
    print(f"  H1 (dose-ISF survives >72h subsample):  {'PASS' if h1 else 'FAIL'} "
          f"(r={indep['dose_isf_r']:.3f})")
    print(f"  H2 (bootstrap CI excludes zero):        {'PASS' if h2 else 'FAIL'} "
          f"(CI=[{bootstrap['ci_2_5']:.3f}, {bootstrap['ci_97_5']:.3f}])")
    print(f"  H3 (bolus autocorr < 0.5):              {'PASS' if h3 else 'FAIL'} "
          f"(r={autocorr['bolus_u_autocorr']['r']:.3f})")
    print(f"  H4 (48h carbs underpowered):             {'PASS' if h4 else 'FAIL'} "
          f"(need {power['carbs_48h']['n_needed_80pct']}, have 219)")

    # Save results (exclude bootstrap distribution to keep file small)
    bootstrap_summary = {k: v for k, v in bootstrap.items() if k != 'distribution'}
    results = {
        'experiment': 'EXP-2639',
        'title': 'Sampling Robustness Audit',
        'n_events': len(events),
        'spacing': {
            'per_patient': spacing_stats,
            'distribution': distribution,
        },
        'autocorrelation': autocorr,
        'full_dataset': full,
        'independent_72h': indep,
        'independent_120h': indep120,
        'block_bootstrap': bootstrap_summary,
        'power_analysis': power,
        'hypotheses': {
            'H1_subsample_survives': h1,
            'H2_bootstrap_excludes_zero': h2,
            'H3_bolus_autocorr_low': h3,
            'H4_carbs_underpowered': h4,
        },
        'all_pass': all([h1, h2, h3, h4]),
    }

    def convert(obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        raise TypeError(f'{type(obj)} not serializable')

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=convert)
    print(f"\nResults saved to {OUTPUT_FILE}")

    return results


if __name__ == '__main__':
    main()
