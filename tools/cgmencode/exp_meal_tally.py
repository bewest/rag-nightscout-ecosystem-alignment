#!/usr/bin/env python3
"""EXP-447: Big Meal Tally from Metabolic Throughput Peaks.

Counts major metabolic events per day using the supply×demand product
signal.  Filters for only the largest peaks (top-quartile prominence)
to answer: "Can we see the 1-3 big meals of the day using physics-based
metabolic flux?"

This is a feasibility / smell test — we expect to see ~2-3 large events
per day for most patients, matching the typical human eating pattern,
regardless of whether meals were announced or unannounced.

Usage:
    python -m cgmencode.exp_meal_tally                 # all patients
    python -m cgmencode.exp_meal_tally --patient a     # single patient
    python -m cgmencode.exp_meal_tally --quick          # first 4 patients
    python -m cgmencode.exp_meal_tally --detail         # per-day breakdown
"""

import sys
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_metabolic_441 import compute_supply_demand

STEPS_PER_DAY = 288  # 5-min intervals
SMOOTH_WINDOW = 6    # 30-min moving average


def smooth(signal, window=SMOOTH_WINDOW):
    """Simple moving-average smoothing."""
    kernel = np.ones(window) / window
    return np.convolve(signal, kernel, mode='same')


def classify_peaks(peaks, prominences, big_pct=50):
    """Split peaks into big / medium / small by prominence percentiles.

    Args:
        big_pct: percentile threshold for "big" (default 50 = above-median).
            The product signal has huge dynamic range so top-quartile (75)
            is too aggressive; above-median captures the 2-3 real meals/day
            while still excluding noise and small corrections.
    """
    if len(prominences) == 0:
        return np.array([]), np.array([]), np.array([])
    p_big = np.percentile(prominences, big_pct)
    p_small = np.percentile(prominences, big_pct / 2)
    big   = peaks[prominences >= p_big]
    med   = peaks[(prominences >= p_small) & (prominences < p_big)]
    small = peaks[prominences < p_small]
    return big, med, small


def detect_peaks(signal, min_distance=18):
    """Find peaks with adaptive IQR-based prominence threshold.

    Args:
        signal: smoothed throughput array
        min_distance: minimum steps between peaks (default 18 = 1.5h)

    Returns:
        peaks, properties dict from scipy.signal.find_peaks
    """
    pos = signal[signal > 0]
    if len(pos) < 20:
        return np.array([]), {}
    p25 = np.percentile(pos, 25)
    return find_peaks(signal, distance=min_distance, prominence=p25)


def tally_patient(patient_dict):
    """Compute big-meal tally for one patient.

    Returns dict with per-day counts, pattern classification, and
    peak magnitude statistics.
    """
    pid = patient_dict['name']
    sd = compute_supply_demand(patient_dict['df'], patient_dict['pk'])
    product = sd['product']
    supply = sd['supply']
    carb_supply = sd['carb_supply']  # supply minus hepatic baseline
    n_steps = len(product)
    n_days = n_steps / STEPS_PER_DAY

    # Use sum_flux (carb_supply + insulin_demand) for peak detection.
    # This captures BOTH announced meals (carb absorption spike) AND
    # unannounced meals (insulin response spike), without the huge
    # dynamic range of the product signal or the hepatic floor.
    sum_flux = sd['sum_flux']  # |carb_supply| + |demand|
    if np.any(sum_flux > 0):
        detect_signal = smooth(sum_flux)
        signal_name = 'sum_flux'
    elif np.any(carb_supply > 0):
        detect_signal = smooth(carb_supply)
        signal_name = 'carb_supply'
    else:
        detect_signal = smooth(product)
        signal_name = 'product'

    # Find all peaks
    peaks, props = detect_peaks(detect_signal)
    if len(peaks) == 0:
        return {
            'patient': pid, 'days': round(n_days, 1),
            'status': 'no_peaks',
        }

    proms = props['prominences']
    big, med, small = classify_peaks(peaks, proms)

    bpd = len(big) / n_days
    mpd = len(med) / n_days
    spd = len(small) / n_days

    big_mag = float(np.median(detect_signal[big])) if len(big) > 0 else 0.0

    # Pattern classification
    if bpd >= 2.5:
        pattern = 'big_eater'
    elif bpd >= 1.5:
        pattern = '2-3_meals'
    elif bpd >= 0.8:
        pattern = '1-2_meals'
    else:
        pattern = 'light'

    # Per-day breakdown
    daily = {}
    for day_i in range(int(n_days)):
        start = day_i * STEPS_PER_DAY
        end = start + STEPS_PER_DAY
        day_big = [int(p) for p in big if start <= p < end]
        daily[f'day_{day_i}'] = len(day_big)

    daily_counts = list(daily.values())

    return {
        'patient': pid,
        'days': round(n_days, 1),
        'big_per_day': round(bpd, 2),
        'med_per_day': round(mpd, 2),
        'small_per_day': round(spd, 2),
        'big_magnitude_median': round(big_mag, 1),
        'pattern': pattern,
        'daily_big_counts': daily_counts,
        'daily_mean': round(float(np.mean(daily_counts)), 2),
        'daily_std': round(float(np.std(daily_counts)), 2),
        'total_peaks': len(peaks),
        'total_big': len(big),
    }


def print_table(results):
    """Print summary table to stdout."""
    print()
    print('BIG metabolic events: above-median sum_flux (carb_supply + demand) peaks')
    print('(Announced OR unannounced — physics sees all meals)')
    print()
    print(f'{"Pat":>3} {"Days":>4} {"Big/d":>5} {"Med/d":>5} '
          f'{"Snk/d":>5} {"BigMag":>7} {"Pattern":>12}')
    print('-' * 55)

    big_rates = []
    for r in results:
        pid = r['patient']
        if r.get('status') == 'no_peaks':
            print(f'{pid:>3} {r["days"]:4.0f}  no peaks')
            continue
        bpd = r['big_per_day']
        mpd = r['med_per_day']
        spd = r['small_per_day']
        bmag = r['big_magnitude_median']
        pat = r['pattern']
        big_rates.append(bpd)
        print(f'{pid:>3} {r["days"]:4.0f} {bpd:5.1f} {mpd:5.1f} '
              f'{spd:7.1f} {bmag:7.1f} {pat:>12}')

    print('-' * 55)
    if big_rates:
        arr = np.array(big_rates)
        print(f'Mean big events/day: {arr.mean():.1f} ± {arr.std():.1f}')
        print(f'Range: {arr.min():.1f} - {arr.max():.1f}')


def print_detail(results):
    """Print per-day breakdown for each patient."""
    print()
    print('=== Per-day big-meal counts ===')
    for r in results:
        if r.get('status') == 'no_peaks':
            continue
        pid = r['patient']
        counts = r['daily_big_counts']
        hist = {}
        for c in counts:
            hist[c] = hist.get(c, 0) + 1
        hist_str = ' '.join(f'{k}meals:{v}d' for k, v in sorted(hist.items()))
        print(f'  {pid}: mean={r["daily_mean"]:.1f}±{r["daily_std"]:.1f}  '
              f'[{hist_str}]')


def save_results(results, output_path):
    """Save JSON results."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump({
            'experiment': 'EXP-447',
            'description': 'Big meal tally from metabolic throughput peaks',
            'method': 'top-quartile prominence on supply×demand product',
            'per_patient': {r['patient']: r for r in results},
            'summary': {
                'n_patients': len(results),
                'mean_big_per_day': round(float(np.mean([
                    r['big_per_day'] for r in results
                    if 'big_per_day' in r
                ])), 2),
            },
        }, f, indent=2)
    print(f'\nSaved: {output_path}')


def main():
    parser = argparse.ArgumentParser(
        description='EXP-447: Big meal tally from metabolic throughput peaks')
    parser.add_argument('--patient', '-p', help='Single patient ID')
    parser.add_argument('--quick', action='store_true',
                        help='First 4 patients only')
    parser.add_argument('--detail', action='store_true',
                        help='Per-day breakdown')
    parser.add_argument('--save', action='store_true',
                        help='Save results JSON')
    # Resolve default relative to repo root, not cwd
    repo_root = Path(__file__).resolve().parent.parent.parent
    default_patients = str(repo_root / 'externals' / 'ns-data' / 'patients')
    parser.add_argument('--patients-dir', default=default_patients,
                        help='Path to patient data')
    args = parser.parse_args()

    max_patients = 4 if args.quick else None
    patient_filter = args.patient or None

    patients = load_patients(
        args.patients_dir,
        max_patients=max_patients,
        patient_filter=patient_filter,
    )

    results = []
    for p in patients:
        r = tally_patient(p)
        results.append(r)

    print_table(results)

    if args.detail:
        print_detail(results)

    if args.save:
        save_results(results, 'externals/experiments/exp447_big_meal_tally.json')


if __name__ == '__main__':
    main()
