#!/usr/bin/env python3
"""EXP-1341: Multi-Algorithm Meal Carb Estimation Survey.

Compares 4 approaches to estimating meal carbohydrate magnitude:

1. **Physics residual integral** — integrates unexplained glucose rise
   (actual delta minus modeled supply/demand net flux) over meal window.
   Converts via CR/ISF.

2. **Glucose excursion** — simple peak-minus-nadir glucose rise during
   meal window, converted to carbs via CR/ISF.

3. **Loop IRC (retrospective correction)** — computes deviation between
   actual glucose and Loop's 30-min prediction (from `predicted_30`).
   Positive deviations = "unexpected glucose rise" → carb absorption.
   Approximates Loop's IntegralRetrospectiveCorrection PID controller.

4. **oref0 deviation** — glucose rate of change minus expected BGI from
   insulin activity.  The "unexplained" positive deviation is attributed
   to carb absorption, with a min_5m_carbimpact floor.

Key insight: entered carbs are NOT ground truth — they are noisy,
often missing (76.5% UAM), and frequently inaccurate.  This is a
qualitative survey of how each algorithm perceives meal magnitude.

Builds on:
- EXP-753: physics residual integral
- EXP-441: supply/demand decomposition
- EXP-1129: proactive meal prediction (F1=0.939 meal_detector)
- Loop IRC: IntegralRetrospectiveCorrection.swift (P=1, I=2, D=2)
- oref0: determine-basal.js deviation logic
"""

import sys, os, json, time
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_metabolic_441 import compute_supply_demand

PATIENTS_DIR = os.path.join(os.path.dirname(__file__),
                            '..', '..', 'externals', 'ns-data', 'patients')

STEPS_PER_HOUR = 12    # 5-min intervals
STEPS_PER_DAY = 288
DT_HOURS = 1 / STEPS_PER_HOUR  # 5 min in hours

# Meal detection: glucose must rise ≥ this threshold
MEAL_RISE_THRESHOLD = 15  # mg/dL
# Merge meals closer than this
MEAL_MERGE_STEPS = 6      # 30 min
# Post-meal integration window
POST_MEAL_WINDOW = 36     # 3 hours (36 × 5 min)

# oref0 min_5m_carbimpact default (mg/dL per 5 min)
# oref0 profile default: 8 mg/dL per 5min (oref1/SMB mode)
# See: externals/oref0/lib/profile/index.js:35
MIN_5M_CARBIMPACT = 8.0  # mg/dL per 5 min (already per-step, no conversion needed)

# Patient therapy settings from profile data
PATIENT_SETTINGS = {
    'a': {'isf': 49, 'cr': 4},
    'b': {'isf': 95, 'cr': 12},
    'c': {'isf': 75, 'cr': 4},
    'd': {'isf': 40, 'cr': 14},
    'e': {'isf': 33, 'cr': 3},
    'f': {'isf': 20, 'cr': 5},
    'g': {'isf': 65, 'cr': 8},
    'h': {'isf': 90, 'cr': 10},
    'i': {'isf': 50, 'cr': 8},
    'j': {'isf': 40, 'cr': 6},
    'k': {'isf': 25, 'cr': 10},
}


def classify_meal_window(hour):
    """Classify hour of day into meal window."""
    if 5 <= hour < 10:
        return 'breakfast'
    elif 10 <= hour < 14:
        return 'lunch'
    elif 17 <= hour < 21:
        return 'dinner'
    else:
        return 'snack'


def detect_meals(glucose, min_rise=MEAL_RISE_THRESHOLD, merge_gap=MEAL_MERGE_STEPS):
    """Detect meal events as sustained glucose rises.

    Returns list of dicts with:
      start: index where rise begins
      peak_idx: index of peak glucose
      pre_bg: glucose at start
      peak_bg: glucose at peak
      excursion: peak_bg - pre_bg
    """
    n = len(glucose)
    delta = np.diff(glucose, prepend=glucose[0])
    # Smooth delta with 3-step rolling mean
    kernel = np.ones(3) / 3
    delta_smooth = np.convolve(delta, kernel, mode='same')

    # Find rising segments
    rising = delta_smooth > 0.5  # slight positive threshold
    meals = []
    i = 0
    while i < n - 6:
        if rising[i]:
            # Find start of rise (local minimum before)
            start = i
            while start > 0 and glucose[start] > glucose[start - 1]:
                start -= 1

            # Find peak (local maximum after)
            j = i + 1
            # Allow brief dips (up to 2 steps negative)
            dip_count = 0
            while j < n - 1:
                if delta_smooth[j] > 0:
                    dip_count = 0
                    j += 1
                elif dip_count < 2:
                    dip_count += 1
                    j += 1
                else:
                    break
            peak_idx = start + int(np.argmax(glucose[start:j + 1]))

            pre_bg = glucose[start]
            peak_bg = glucose[peak_idx]
            excursion = peak_bg - pre_bg

            if excursion >= min_rise and not np.isnan(excursion):
                # Merge with previous if close enough
                if meals and start - meals[-1]['peak_idx'] < merge_gap:
                    if peak_bg > meals[-1]['peak_bg']:
                        meals[-1]['peak_idx'] = peak_idx
                        meals[-1]['peak_bg'] = peak_bg
                        meals[-1]['excursion'] = peak_bg - meals[-1]['pre_bg']
                else:
                    meals.append({
                        'start': start,
                        'peak_idx': peak_idx,
                        'pre_bg': float(pre_bg),
                        'peak_bg': float(peak_bg),
                        'excursion': float(excursion),
                    })
            i = max(j, i + 3)
        else:
            i += 1
    return meals


def est_physics_carbs(net_flux, glucose, start, peak_idx, isf, cr):
    """Physics residual integral: unexplained glucose rise → carbs.

    Integrates (actual_delta - net_flux) where positive, from start
    to peak + 2h (absorption window).
    """
    end = min(len(glucose), peak_idx + STEPS_PER_HOUR * 2)
    if end <= start + 2:
        return np.nan
    actual_delta = np.diff(glucose[start:end])
    model_flux = net_flux[start:start + len(actual_delta)]
    residual = actual_delta - model_flux
    # Only count positive residuals (unexplained rise)
    pos_residual = np.clip(residual, 0, None)
    integral_mg = float(np.nansum(pos_residual))  # mg/dL total rise
    carbs_g = integral_mg * cr / isf
    return round(carbs_g, 1)


def est_excursion_carbs(excursion_mg, isf, cr):
    """Simple excursion → carbs: peak-nadir rise converted via CR/ISF."""
    if np.isnan(excursion_mg) or excursion_mg <= 0:
        return np.nan
    carbs_g = excursion_mg * cr / isf
    return round(carbs_g, 1)


def est_loop_irc_carbs(glucose, predicted_30, start, peak_idx, isf, cr):
    """Loop IRC approximation: integrate retrospective prediction error.

    Loop's IntegralRetrospectiveCorrection computes:
      deviation = actual_glucose[t] - predicted_30[t - 6]
    where predicted_30 was Loop's 30-min prediction from 6 steps ago.

    Positive deviation = glucose rose more than Loop expected → carb absorption.

    We accumulate positive deviations over the meal window (start to peak + 2h)
    and convert to carb estimate via CR/ISF.
    """
    end = min(len(glucose), peak_idx + STEPS_PER_HOUR * 2)
    if end <= start + 6:
        return np.nan

    # Compute retrospective deviation: actual now vs predicted 30min ago
    retro_dev = np.full(len(glucose), np.nan)
    retro_dev[6:] = glucose[6:] - predicted_30[:-6]

    window_dev = retro_dev[start:end]
    valid = ~np.isnan(window_dev)
    if valid.sum() < 3:
        return np.nan

    # Integrate positive deviations (glucose higher than predicted)
    pos_dev = np.clip(np.nan_to_num(window_dev, nan=0), 0, None)
    # Each step's deviation represents 5-min accumulation
    # Total "unexpected rise" in mg/dL·steps → convert to mg/dL equivalent
    # IRC uses integral with forgetting (τ=60min), we simplify to sum
    integral_mg = float(np.sum(pos_dev)) / STEPS_PER_HOUR  # normalize to hourly
    carbs_g = integral_mg * cr / isf
    return round(carbs_g, 1)


def est_oref0_carbs(glucose, iob, start, peak_idx, isf, cr):
    """oref0 deviation: unexplained glucose change after accounting for insulin.

    oref0's determine-basal computes:
      bgi = -iob_data.activity * sens * 5  (expected insulin effect per 5 min)
      deviation = 6 * (minDelta - bgi)      (projected over 30 min)
    Positive deviation → unannounced carbs.

    Note: min_5m_carbimpact is NOT used in oref0's deviation calculation
    (determine-basal.js:398-400).  It's only used in COB decay tracking
    (cob.js:189-190), which is a separate mechanism.

    Ref: externals/oref0/lib/determine-basal/determine-basal.js:398-400
    """
    end = min(len(glucose), peak_idx + STEPS_PER_HOUR * 2)
    if end <= start + 2:
        return np.nan

    actual_delta = np.diff(glucose[start:end])
    # Estimate insulin activity from IOB change (proxy for activity curve)
    iob_window = iob[start:end]
    iob_activity = -np.diff(iob_window)  # positive = insulin being used
    iob_activity = np.nan_to_num(iob_activity, nan=0)

    # BGI = expected glucose change per 5-min step from insulin absorption.
    # iob_activity is U per step; ISF is mg/dL per U.
    # oref0: bgi = -activity_U_per_min * sens * 5; since iob_activity ≈ activity*5,
    # the *5 and /5 cancel: bgi = -iob_activity * isf.
    # Ref: externals/oref0/lib/determine-basal/determine-basal.js:398
    bgi = -iob_activity * isf  # expected BG impact per step (mg/dL)
    deviation = actual_delta - bgi

    # Only count positive deviations (unexplained glucose rise → carb absorption)
    carb_impact = np.clip(deviation, 0, None)

    integral_mg = float(np.nansum(carb_impact))
    carbs_g = integral_mg * cr / isf
    return round(carbs_g, 1)


def compute_stats(values):
    """Compute summary statistics for a list of values."""
    arr = np.array([v for v in values if not np.isnan(v)])
    if len(arr) == 0:
        return {}
    return {
        'n': int(len(arr)),
        'median': round(float(np.median(arr)), 1),
        'mean': round(float(np.mean(arr)), 1),
        'p10': round(float(np.percentile(arr, 10)), 1),
        'p25': round(float(np.percentile(arr, 25)), 1),
        'p75': round(float(np.percentile(arr, 75)), 1),
        'p90': round(float(np.percentile(arr, 90)), 1),
        'std': round(float(np.std(arr)), 1),
    }


def run_survey(patients):
    """Run the multi-algorithm carb estimation survey."""
    t0 = time.time()
    all_meals = []
    per_patient = []
    methods = ['physics', 'excursion', 'loop_irc', 'oref0']

    for p in patients:
        name = p['name']
        df = p['df']
        pk = p['pk']
        settings = PATIENT_SETTINGS.get(name, {'isf': 50, 'cr': 8})
        isf = settings['isf']
        cr = settings['cr']

        glucose = df['glucose'].values.astype(float)
        carbs_col = df['carbs'].values.astype(float)
        bolus = df['bolus'].values.astype(float)
        iob = df['iob'].values.astype(float)
        n = len(glucose)
        n_days = n / STEPS_PER_DAY

        # Get predicted_30 for Loop IRC
        predicted_30 = df['predicted_30'].values.astype(float) if 'predicted_30' in df.columns else np.full(n, np.nan)
        pred30_coverage = np.sum(~np.isnan(predicted_30)) / n

        # Compute supply/demand for physics method
        sd = compute_supply_demand(df, pk_array=pk)
        net_flux = sd['net']

        # Detect meals
        glucose_filled = glucose.copy()
        nan_mask = np.isnan(glucose_filled)
        if nan_mask.any():
            # Simple forward fill for meal detection
            for i in range(1, len(glucose_filled)):
                if np.isnan(glucose_filled[i]):
                    glucose_filled[i] = glucose_filled[i - 1]
        meal_events = detect_meals(glucose_filled)

        # Classify each meal
        patient_meals = []
        for m in meal_events:
            start = m['start']
            peak_idx = m['peak_idx']

            # Hour of day
            hour = (start % STEPS_PER_DAY) / STEPS_PER_HOUR
            window = classify_meal_window(hour)

            # Check if announced (carbs entered within ±30 min of start)
            announce_window = slice(max(0, start - 6), min(n, start + 12))
            entered = float(np.nansum(carbs_col[announce_window]))
            announced = entered > 0

            # Estimate carbs with each method
            c_physics = est_physics_carbs(net_flux, glucose_filled, start, peak_idx, isf, cr)
            c_excursion = est_excursion_carbs(m['excursion'], isf, cr)
            c_loop = est_loop_irc_carbs(glucose_filled, predicted_30, start, peak_idx, isf, cr)
            c_oref0 = est_oref0_carbs(glucose_filled, iob, start, peak_idx, isf, cr)

            meal_rec = {
                'patient': name,
                'start': int(start),
                'peak_idx': int(peak_idx),
                'hour': round(hour, 1),
                'window': window,
                'pre_bg': m['pre_bg'],
                'peak_bg': m['peak_bg'],
                'excursion': m['excursion'],
                'announced': announced,
                'entered_carbs': round(entered, 1),
                'physics': c_physics,
                'excursion_est': c_excursion,
                'loop_irc': c_loop,
                'oref0': c_oref0,
            }
            patient_meals.append(meal_rec)

        all_meals.extend(patient_meals)

        n_announced = sum(1 for m in patient_meals if m['announced'])
        n_uam = len(patient_meals) - n_announced

        # Per-patient summary
        psummary = {
            'patient': name,
            'isf': isf,
            'cr': cr,
            'n_days': round(n_days, 1),
            'n_meals': len(patient_meals),
            'meals_per_day': round(len(patient_meals) / max(n_days, 1), 1),
            'n_announced': n_announced,
            'n_uam': n_uam,
            'pct_uam': round(100 * n_uam / max(len(patient_meals), 1), 1),
            'pred30_coverage': round(pred30_coverage * 100, 1),
        }

        for method in methods:
            key = method if method != 'excursion' else 'excursion_est'
            vals = [m[key] for m in patient_meals]
            psummary[f'{method}_stats'] = compute_stats(vals)

            # Announced vs UAM breakdown
            ann_vals = [m[key] for m in patient_meals if m['announced']]
            uam_vals = [m[key] for m in patient_meals if not m['announced']]
            psummary[f'{method}_announced'] = compute_stats(ann_vals)
            psummary[f'{method}_uam'] = compute_stats(uam_vals)

        # Entered carbs stats (announced only)
        entered_vals = [m['entered_carbs'] for m in patient_meals if m['announced'] and m['entered_carbs'] > 0]
        psummary['entered_stats'] = compute_stats(entered_vals)

        per_patient.append(psummary)

        # Print patient summary
        ps = psummary
        print(f"\nPatient {name}: {ps['n_meals']} meals in {ps['n_days']:.0f} days "
              f"({ps['meals_per_day']}/day), ISF={isf}, CR={cr}")
        print(f"  Announced: {n_announced}, UAM: {n_uam} ({ps['pct_uam']}%), "
              f"pred30 coverage: {ps['pred30_coverage']}%")
        for method in methods:
            s = psummary[f'{method}_stats']
            if s:
                print(f"  {method:12s}: median {s['median']:5.1f}g  "
                      f"(IQR {s['p25']:.0f}–{s['p75']:.0f}g)")
        if entered_vals:
            es = psummary['entered_stats']
            print(f"  {'entered':12s}: median {es['median']:5.1f}g  "
                  f"(IQR {es['p25']:.0f}–{es['p75']:.0f}g)")

    # ─── Population summary ───────────────────────────────────────────
    n_total = len(all_meals)
    n_announced = sum(1 for m in all_meals if m['announced'])
    n_uam = n_total - n_announced

    print(f"\n{'=' * 70}")
    print(f"POPULATION SUMMARY: {n_total} meals across {len(patients)} patients")
    print(f"  Announced: {n_announced}, UAM: {n_uam} ({100*n_uam/n_total:.1f}%)")

    pop_stats = {}
    for method in methods:
        key = method if method != 'excursion' else 'excursion_est'
        vals = [m[key] for m in all_meals]
        ann_vals = [m[key] for m in all_meals if m['announced']]
        uam_vals = [m[key] for m in all_meals if not m['announced']]
        pop_stats[method] = {
            'all': compute_stats(vals),
            'announced': compute_stats(ann_vals),
            'uam': compute_stats(uam_vals),
        }

    entered_vals = [m['entered_carbs'] for m in all_meals if m['announced'] and m['entered_carbs'] > 0]
    pop_stats['entered'] = compute_stats(entered_vals)

    print(f"\n  {'Method':<14s}  {'All meals':>10s}  {'Announced':>10s}  {'UAM':>10s}")
    print(f"  {'-'*50}")
    for method in methods:
        ps = pop_stats[method]
        a = ps['all']
        ann = ps['announced']
        uam = ps['uam']
        def _fmt(d, k='median'):
            v = d.get(k)
            return f"{v:.1f}" if v is not None else "—"
        print(f"  {method:<14s}  {_fmt(a):>8s}g  "
              f"{_fmt(ann):>8s}g  {_fmt(uam):>8s}g")
    es = pop_stats['entered']
    print(f"  {'(entered)':14s}  {'—':>10s}  {_fmt(es):>8s}g  {'—':>10s}")

    # By meal window
    print(f"\n  By meal window:")
    windows = ['breakfast', 'lunch', 'dinner', 'snack']
    for w in windows:
        w_meals = [m for m in all_meals if m['window'] == w]
        if not w_meals:
            continue
        n_w_uam = sum(1 for m in w_meals if not m['announced'])
        print(f"    {w:<12s}: n={len(w_meals):>4d}, {100*n_w_uam/len(w_meals):3.0f}% UAM", end='')
        for method in methods:
            key = method if method != 'excursion' else 'excursion_est'
            vals = [m[key] for m in w_meals if not np.isnan(m[key])]
            if vals:
                print(f"  | {method}: {np.median(vals):.0f}g", end='')
        print()

    # Correlation with entered carbs (announced only)
    print(f"\n  Method vs entered carbs (announced meals, n={len(entered_vals)}):")
    print(f"  {'Method':<14s}  {'Corr (r)':>10s}  {'Ratio':>8s}")
    print(f"  {'-'*40}")
    for method in methods:
        key = method if method != 'excursion' else 'excursion_est'
        pairs = [(m[key], m['entered_carbs'])
                 for m in all_meals
                 if m['announced'] and m['entered_carbs'] > 0
                 and not np.isnan(m[key])]
        if len(pairs) < 10:
            print(f"  {method:<14s}  {'N/A':>10s}  {'N/A':>8s}")
            continue
        est = np.array([p[0] for p in pairs])
        ent = np.array([p[1] for p in pairs])
        corr = float(np.corrcoef(est, ent)[0, 1])
        ratio = float(np.median(est)) / float(np.median(ent))
        print(f"  {method:<14s}  {corr:>10.3f}  {ratio:>7.2f}×")

    elapsed = time.time() - t0
    print(f"\n  Elapsed: {elapsed:.1f}s")

    # ─── Build result JSON ────────────────────────────────────────────
    result = {
        'name': 'EXP-1341: Multi-Algorithm Meal Carb Estimation Survey',
        'n_patients': len(patients),
        'n_meals': n_total,
        'n_announced': n_announced,
        'n_uam': n_uam,
        'pct_uam': round(100 * n_uam / n_total, 1),
        'population': pop_stats,
        'per_patient': per_patient,
        'elapsed_sec': round(elapsed, 1),
    }

    # Save to externals/experiments/ (git-ignored)
    out_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'externals', 'experiments')
    os.makedirs(out_dir, exist_ok=True)
    summary_path = os.path.join(out_dir, 'exp-1341_carb_survey.json')
    detail_path = os.path.join(out_dir, 'exp-1341_carb_survey_detail.json')

    with open(summary_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nSaved summary: {summary_path}")

    detail = {
        'name': 'EXP-1341: Detail — per-meal records',
        'meals': all_meals,
    }
    with open(detail_path, 'w') as f:
        json.dump(detail, f, indent=2, default=str)
    print(f"Saved detail:  {detail_path}")

    return result


if __name__ == '__main__':
    patients = load_patients(PATIENTS_DIR)
    run_survey(patients)
