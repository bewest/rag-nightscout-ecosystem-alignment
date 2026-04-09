#!/usr/bin/env python3
"""EXP-1751 to EXP-1758: Centering vs Dynamics Decomposition.

Follows from EXP-1745 finding that stability index doesn't predict TIR.
Hypothesis: TIR is dominated by "centering" (mean glucose placement relative
to target range), while our prior experiments focused on "dynamics" (cascade
chains, rebounds, variability). This batch decomposes glycemic control into
these two independent dimensions and identifies which interventions address
which dimension.

  EXP-1751: Centering decomposition — what fraction of TAR/TBR comes from
            static offset (mean too high/low) vs dynamic excursions?
  EXP-1752: Settings adequacy scoring — compare effective ISF/CR/basal to
            profile settings and correlate mismatch with centering error.
  EXP-1753: Natural experiment windows — do stable-settings periods show
            better information ceilings? (Tests if deficit is behavioral.)
  EXP-1754: UAM predictive features — can rate-of-change acceleration
            predict rises 5-10 min earlier than threshold crossing?
  EXP-1755: Glycogen proxy + information ceiling — does incorporating
            hepatic glucose state improve per-type prediction?
  EXP-1756: Fasting vs fed state analysis — decompose supply/demand
            behavior by metabolic context (overnight, fasting, postprandial).
  EXP-1757: Settings simulation — if we replace each patient's ISF/CR/basal
            with "optimal" values (from natural experiments), how much TIR
            improvement is centering alone?
  EXP-1758: Cross-patient information ceiling — does LOPO reveal whether
            the negative R² is patient-specific or universal?

Run: PYTHONPATH=tools python3 tools/cgmencode/exp_centering_dynamics_1751.py --figures
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from cgmencode.exp_metabolic_flux import load_patients
from exp_metabolic_441 import compute_supply_demand

PATIENTS_DIR = Path('externals/ns-data/patients')
RESULTS_DIR = Path('externals/experiments')
FIGURES_DIR = Path('docs/60-research/figures')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

# Target range
LOW = 70.0
HIGH = 180.0


def _get_isf(pat):
    """Extract mean ISF in mg/dL from patient schedule."""
    sched = pat['df'].attrs.get('isf_schedule', [])
    if not sched:
        return 50.0
    vals = [s['value'] for s in sched]
    mean_isf = np.mean(vals)
    if mean_isf < 15:
        mean_isf *= 18.0182
    return mean_isf


def _get_cr(pat):
    """Extract mean CR from patient schedule."""
    sched = pat['df'].attrs.get('cr_schedule', [])
    if not sched:
        return 10.0
    return np.mean([s['value'] for s in sched])


def _get_basal(pat):
    """Extract mean basal from patient schedule."""
    sched = pat['df'].attrs.get('basal_schedule', [])
    if not sched:
        return 1.0
    return np.mean([s['value'] for s in sched])


def exp_1751_centering_decomposition(patients):
    """Decompose TAR/TBR into centering error vs dynamic excursion error.

    Centering error: the TAR/TBR that would exist if glucose were constant
    at the patient's mean glucose (i.e., a flat line at mean BG).
    Dynamic error: the additional TAR/TBR from glucose variability around
    that mean.
    """
    print("\n=== EXP-1751: Centering vs Dynamic TAR/TBR Decomposition ===\n")

    patient_results = []
    for pat in patients:
        name = pat['name']
        glucose = pat['df']['glucose'].values.astype(float)
        valid = ~np.isnan(glucose)
        g = glucose[valid]

        if len(g) < STEPS_PER_DAY:
            continue

        mean_bg = np.mean(g)
        std_bg = np.std(g)

        # Actual TAR/TBR
        actual_tar = np.mean(g > HIGH) * 100
        actual_tbr = np.mean(g < LOW) * 100
        actual_tir = np.mean((g >= LOW) & (g <= HIGH)) * 100

        # Centering component: if glucose were constant at mean
        centering_tar = 100.0 if mean_bg > HIGH else 0.0
        centering_tbr = 100.0 if mean_bg < LOW else 0.0

        # Dynamic component: TAR/TBR beyond what centering explains
        dynamic_tar = actual_tar - centering_tar
        dynamic_tbr = actual_tbr - centering_tbr

        # More nuanced: Gaussian approximation
        # If BG ~ N(mean, std), what fraction is above HIGH?
        from scipy.stats import norm
        if std_bg > 0:
            gaussian_tar = (1 - norm.cdf(HIGH, mean_bg, std_bg)) * 100
            gaussian_tbr = norm.cdf(LOW, mean_bg, std_bg) * 100
        else:
            gaussian_tar = centering_tar
            gaussian_tbr = centering_tbr

        # Distance from ideal center (midpoint of range = 125)
        ideal_center = (LOW + HIGH) / 2  # 125 mg/dL
        centering_offset = mean_bg - ideal_center

        # How much TAR would be saved by shifting mean to ideal center?
        if std_bg > 0:
            ideal_tar = (1 - norm.cdf(HIGH, ideal_center, std_bg)) * 100
            ideal_tbr = norm.cdf(LOW, ideal_center, std_bg) * 100
        else:
            ideal_tar = 0.0
            ideal_tbr = 0.0

        centering_fixable_tar = actual_tar - ideal_tar
        centering_fixable_tbr = actual_tbr - ideal_tbr

        r = {
            'patient': name,
            'mean_bg': round(mean_bg, 1),
            'std_bg': round(std_bg, 1),
            'cv_pct': round(std_bg / mean_bg * 100, 1) if mean_bg > 0 else 0,
            'actual_tar_pct': round(actual_tar, 1),
            'actual_tbr_pct': round(actual_tbr, 1),
            'actual_tir_pct': round(actual_tir, 1),
            'centering_offset_mgdl': round(centering_offset, 1),
            'gaussian_tar_pct': round(gaussian_tar, 1),
            'gaussian_tbr_pct': round(gaussian_tbr, 1),
            'centering_fixable_tar_pct': round(max(0, centering_fixable_tar), 1),
            'centering_fixable_tbr_pct': round(max(0, centering_fixable_tbr), 1),
            'ideal_tar_pct': round(ideal_tar, 1),
            'ideal_tbr_pct': round(ideal_tbr, 1),
        }
        patient_results.append(r)

        print(f"  {name}: mean={mean_bg:.0f} (offset {centering_offset:+.0f}), "
              f"CV={std_bg/mean_bg*100:.0f}%, TAR={actual_tar:.1f}% "
              f"(centering-fixable={max(0,centering_fixable_tar):.1f}%, "
              f"irreducible={ideal_tar:.1f}%)")

    # Population summary
    offsets = [r['centering_offset_mgdl'] for r in patient_results]
    fix_tar = [r['centering_fixable_tar_pct'] for r in patient_results]
    fix_tbr = [r['centering_fixable_tbr_pct'] for r in patient_results]
    act_tar = [r['actual_tar_pct'] for r in patient_results]

    mean_fixable = np.mean(fix_tar)
    mean_actual = np.mean(act_tar)
    frac_centering = mean_fixable / mean_actual * 100 if mean_actual > 0 else 0

    print(f"\n  Population mean offset: {np.mean(offsets):+.1f} mg/dL")
    print(f"  Mean centering-fixable TAR: {mean_fixable:.1f}% of {mean_actual:.1f}% total "
          f"({frac_centering:.0f}%)")
    print(f"  Mean centering-fixable TBR: {np.mean(fix_tbr):.1f}%")

    return {
        'experiment': 'EXP-1751',
        'title': 'Centering vs Dynamic TAR/TBR Decomposition',
        'patients': patient_results,
        'population_mean_offset': round(float(np.mean(offsets)), 1),
        'centering_fixable_tar_fraction': round(frac_centering, 1),
    }


def exp_1752_settings_adequacy(patients):
    """Score settings adequacy by comparing effective vs profile values.

    Uses the supply-demand model to estimate effective ISF (from correction
    events), effective basal (from overnight stability), and compares to
    profile settings.
    """
    print("\n=== EXP-1752: Settings Adequacy Scoring ===\n")

    patient_results = []
    for pat in patients:
        name = pat['name']
        df = pat['df']
        glucose = df['glucose'].values.astype(float)
        iob = df['iob'].values.astype(float) if 'iob' in df.columns else np.zeros(len(df))
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0.0)

        valid = ~np.isnan(glucose)
        if valid.sum() < STEPS_PER_DAY:
            continue

        profile_isf = _get_isf(pat)
        profile_cr = _get_cr(pat)
        profile_basal = _get_basal(pat)

        # Estimate effective ISF from correction windows:
        # Windows where IOB > 0.5 and no carbs within ±1h
        corrections = []
        for i in range(STEPS_PER_HOUR, len(glucose) - 3 * STEPS_PER_HOUR):
            if not valid[i] or np.isnan(iob[i]):
                continue
            if iob[i] < 0.5:
                continue
            # No carbs within ±1h
            carb_window = carbs[max(0, i - STEPS_PER_HOUR):i + STEPS_PER_HOUR]
            if carb_window.sum() > 1.0:
                continue
            # Glucose must be > 120 (correction territory)
            if glucose[i] < 120:
                continue
            # Look at 2h ahead
            end = min(i + 2 * STEPS_PER_HOUR, len(glucose))
            if end - i < STEPS_PER_HOUR:
                continue
            g_start = glucose[i]
            # Use minimum glucose in the next 2h as end point
            g_window = glucose[i:end]
            g_valid = g_window[~np.isnan(g_window)]
            if len(g_valid) < STEPS_PER_HOUR:
                continue
            g_end = np.min(g_valid)
            delta_g = g_start - g_end
            if delta_g > 10:
                # Rough effective ISF: delta_g / IOB at start
                eff_isf = delta_g / iob[i]
                if 10 < eff_isf < 500:
                    corrections.append(eff_isf)

        effective_isf = float(np.median(corrections)) if len(corrections) >= 5 else profile_isf
        isf_ratio = effective_isf / profile_isf if profile_isf > 0 else 1.0

        # Estimate effective basal from overnight stability:
        # Overnight = hours 0-6, no carbs, low IOB change
        overnight_drifts = []
        for i in range(len(glucose) - STEPS_PER_HOUR):
            if not valid[i] or not valid[i + STEPS_PER_HOUR]:
                continue
            # Check time of day (use index mod STEPS_PER_DAY)
            tod = (i % STEPS_PER_DAY) / STEPS_PER_HOUR  # hours
            if not (0 <= tod <= 6):
                continue
            # No carbs in window
            c_win = carbs[i:i + STEPS_PER_HOUR]
            if c_win.sum() > 0.5:
                continue
            # Low IOB
            if not np.isnan(iob[i]) and abs(iob[i]) > 0.3:
                continue
            # Drift over 1h
            drift = glucose[i + STEPS_PER_HOUR] - glucose[i]
            if not np.isnan(drift):
                overnight_drifts.append(drift)

        mean_overnight_drift = float(np.mean(overnight_drifts)) if overnight_drifts else 0.0
        # Positive drift = basal too low, negative = basal too high
        # Ideal drift = 0
        basal_adequacy = 'adequate' if abs(mean_overnight_drift) < 5 else (
            'too_low' if mean_overnight_drift > 5 else 'too_high')

        # Centering error
        g_valid = glucose[valid]
        mean_bg = float(np.mean(g_valid))
        actual_tir = float(np.mean((g_valid >= LOW) & (g_valid <= HIGH)) * 100)

        r = {
            'patient': name,
            'profile_isf': round(profile_isf, 1),
            'effective_isf': round(effective_isf, 1),
            'isf_ratio': round(isf_ratio, 2),
            'n_corrections': len(corrections),
            'profile_basal': round(profile_basal, 3),
            'mean_overnight_drift_mgdl_h': round(mean_overnight_drift, 2),
            'basal_adequacy': basal_adequacy,
            'mean_bg': round(mean_bg, 1),
            'tir_pct': round(actual_tir, 1),
        }
        patient_results.append(r)

        print(f"  {name}: ISF {profile_isf:.0f}→{effective_isf:.0f} (×{isf_ratio:.2f}), "
              f"overnight drift {mean_overnight_drift:+.1f} mg/dL/h ({basal_adequacy}), "
              f"TIR={actual_tir:.1f}%")

    # Correlate ISF mismatch with TIR
    isf_ratios = np.array([r['isf_ratio'] for r in patient_results])
    tirs = np.array([r['tir_pct'] for r in patient_results])
    isf_mismatch = np.abs(isf_ratios - 1.0)

    from scipy.stats import pearsonr
    if len(isf_mismatch) >= 3:
        r_val, p_val = pearsonr(isf_mismatch, tirs)
        print(f"\n  ISF mismatch vs TIR: r={r_val:.3f} (p={p_val:.4f})")
    else:
        r_val, p_val = 0.0, 1.0

    return {
        'experiment': 'EXP-1752',
        'title': 'Settings Adequacy Scoring',
        'patients': patient_results,
        'isf_mismatch_vs_tir_r': round(float(r_val), 3),
        'isf_mismatch_vs_tir_p': round(float(p_val), 4),
    }


def exp_1753_natural_experiment_ceiling(patients):
    """Test information ceiling during natural experiment windows.

    Hypothesis: During stable periods (overnight fasting, low IOB,
    no recent carbs), the supply-demand model should have a BETTER
    information ceiling because confounding factors are minimized.
    If the ceiling is still negative, the limitation is fundamental
    (physiological noise), not behavioral (missing information).
    """
    print("\n=== EXP-1753: Natural Experiment Window Information Ceiling ===\n")

    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.model_selection import cross_val_score

    stable_features = []
    stable_targets = []
    unstable_features = []
    unstable_targets = []

    for pat in patients:
        name = pat['name']
        df = pat['df']
        pk = pat['pk']
        glucose = df['glucose'].values.astype(float)
        iob = df['iob'].values.astype(float) if 'iob' in df.columns else np.zeros(len(df))
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0.0)

        try:
            sd = compute_supply_demand(df, pk, calibrate=True)
            supply = sd['supply']
            demand = sd['demand']
            net_flux = sd['net']
        except Exception:
            continue

        valid = ~np.isnan(glucose)

        for i in range(2 * STEPS_PER_HOUR, len(glucose) - 2 * STEPS_PER_HOUR):
            if not valid[i]:
                continue

            # Feature vector: supply, demand, net_flux, IOB, recent delta
            feat = [
                supply[i] if i < len(supply) else 0,
                demand[i] if i < len(demand) else 0,
                net_flux[i] if i < len(net_flux) else 0,
                iob[i] if not np.isnan(iob[i]) else 0,
                glucose[i],
            ]

            # Target: glucose change over next hour
            future = glucose[i + STEPS_PER_HOUR]
            if np.isnan(future):
                continue
            target = future - glucose[i]

            # Is this a "stable" window?
            # No carbs within ±2h
            carb_window = carbs[max(0, i - 2*STEPS_PER_HOUR):i + 2*STEPS_PER_HOUR]
            iob_val = iob[i] if not np.isnan(iob[i]) else 0
            is_stable = (carb_window.sum() < 1.0) and (abs(iob_val) < 0.5)

            if is_stable:
                stable_features.append(feat)
                stable_targets.append(target)
            else:
                unstable_features.append(feat)
                unstable_targets.append(target)

    # Subsample to manageable size
    max_n = 20000
    for label, feats, tgts in [
        ('stable', stable_features, stable_targets),
        ('unstable', unstable_features, unstable_targets),
    ]:
        X = np.array(feats[:max_n])
        y = np.array(tgts[:max_n])
        if len(X) < 100:
            print(f"  {label}: too few samples ({len(X)})")
            continue

        model = GradientBoostingRegressor(
            n_estimators=100, max_depth=4, random_state=42,
            subsample=0.8
        )
        scores = cross_val_score(model, X, y, cv=5, scoring='r2')
        r2 = float(np.mean(scores))
        print(f"  {label}: n={len(X)}, R²={r2:.4f} (±{np.std(scores):.4f})")

    # Results
    X_s = np.array(stable_features[:max_n])
    y_s = np.array(stable_targets[:max_n])
    X_u = np.array(unstable_features[:max_n])
    y_u = np.array(unstable_targets[:max_n])

    model_s = GradientBoostingRegressor(n_estimators=100, max_depth=4, random_state=42, subsample=0.8)
    model_u = GradientBoostingRegressor(n_estimators=100, max_depth=4, random_state=42, subsample=0.8)

    scores_s = cross_val_score(model_s, X_s, y_s, cv=5, scoring='r2') if len(X_s) >= 100 else [0]
    scores_u = cross_val_score(model_u, X_u, y_u, cv=5, scoring='r2') if len(X_u) >= 100 else [0]

    r2_stable = float(np.mean(scores_s))
    r2_unstable = float(np.mean(scores_u))

    print(f"\n  Stable R²: {r2_stable:.4f}")
    print(f"  Unstable R²: {r2_unstable:.4f}")
    print(f"  Difference: {r2_stable - r2_unstable:+.4f}")

    return {
        'experiment': 'EXP-1753',
        'title': 'Natural Experiment Window Information Ceiling',
        'n_stable': len(stable_features),
        'n_unstable': len(unstable_features),
        'r2_stable': round(r2_stable, 4),
        'r2_unstable': round(r2_unstable, 4),
        'r2_difference': round(r2_stable - r2_unstable, 4),
    }


def exp_1754_uam_predictive_detection(patients):
    """Test whether rate-of-change acceleration can predict rises earlier.

    Current UAM detection uses threshold crossing (glucose > X or delta > Y).
    Can we detect rises 5-10 min earlier using the second derivative
    (acceleration) of glucose?
    """
    print("\n=== EXP-1754: UAM Predictive Detection via Acceleration ===\n")

    glucose_arrays = []
    carb_arrays = []
    for pat in patients:
        g = pat['df']['glucose'].values.astype(float)
        c = np.nan_to_num(pat['df']['carbs'].values.astype(float), nan=0.0)
        glucose_arrays.append(g)
        carb_arrays.append(c)

    # Define "significant rise" events: glucose increases by 30+ mg/dL over 1h
    RISE_THRESHOLD = 30  # mg/dL over 1h
    ACCEL_LOOKBACK = 3  # steps for smoothed acceleration

    all_events = []

    for g, c in zip(glucose_arrays, carb_arrays):
        valid = ~np.isnan(g)
        # First derivative (rate of change per 5 min)
        delta = np.diff(g, prepend=g[0])
        delta[~valid] = 0

        # Second derivative (acceleration)
        accel = np.diff(delta, prepend=delta[0])

        # Smoothed acceleration (3-step average)
        accel_smooth = np.convolve(accel, np.ones(ACCEL_LOOKBACK)/ACCEL_LOOKBACK, mode='same')

        for i in range(2 * STEPS_PER_HOUR, len(g) - STEPS_PER_HOUR):
            if not valid[i]:
                continue
            # Is this the start of a significant rise?
            future = g[i:i + STEPS_PER_HOUR]
            future_valid = future[~np.isnan(future)]
            if len(future_valid) < 6:
                continue
            max_rise = np.max(future_valid) - g[i]
            if max_rise < RISE_THRESHOLD:
                continue

            # When does threshold-based detection fire?
            # Simple: delta > 3 mg/dL per 5 min for 2 consecutive steps
            thresh_detect = None
            for j in range(i, min(i + STEPS_PER_HOUR, len(g) - 1)):
                if delta[j] > 3.0 and delta[j-1] > 2.0:
                    thresh_detect = j - i  # steps from start
                    break

            # When does acceleration-based detection fire?
            # Positive acceleration preceding the rise
            accel_detect = None
            for j in range(max(i - 4, 0), i + 6):
                if accel_smooth[j] > 0.5:
                    accel_detect = j - i  # negative = earlier
                    break

            # Was it announced (carbs within ±30min)?
            carb_window = c[max(0, i - 6):i + 6]
            is_announced = carb_window.sum() > 1.0

            all_events.append({
                'start_bg': g[i],
                'max_rise': max_rise,
                'thresh_detect_steps': thresh_detect,
                'accel_detect_steps': accel_detect,
                'is_announced': is_announced,
            })

    n_events = len(all_events)
    print(f"  Total significant rises (≥{RISE_THRESHOLD} mg/dL/h): {n_events}")

    # Compare detection times
    thresh_times = [e['thresh_detect_steps'] for e in all_events if e['thresh_detect_steps'] is not None]
    accel_times = [e['accel_detect_steps'] for e in all_events if e['accel_detect_steps'] is not None]

    if thresh_times:
        mean_thresh = np.mean(thresh_times) * 5  # convert to minutes
        median_thresh = np.median(thresh_times) * 5
    else:
        mean_thresh = median_thresh = float('nan')

    if accel_times:
        mean_accel = np.mean(accel_times) * 5
        median_accel = np.median(accel_times) * 5
    else:
        mean_accel = median_accel = float('nan')

    # How many events does accel detect earlier?
    earlier_count = 0
    same_count = 0
    later_count = 0
    lead_times = []
    for e in all_events:
        if e['thresh_detect_steps'] is not None and e['accel_detect_steps'] is not None:
            lead = (e['thresh_detect_steps'] - e['accel_detect_steps']) * 5  # minutes
            lead_times.append(lead)
            if lead > 0:
                earlier_count += 1
            elif lead == 0:
                same_count += 1
            else:
                later_count += 1

    announced = sum(1 for e in all_events if e['is_announced'])
    unannounced = n_events - announced

    print(f"  Announced: {announced} ({announced/n_events*100:.0f}%), "
          f"Unannounced: {unannounced} ({unannounced/n_events*100:.0f}%)")
    print(f"  Threshold detection: mean={mean_thresh:.1f}min, median={median_thresh:.1f}min")
    print(f"  Acceleration detection: mean={mean_accel:.1f}min, median={median_accel:.1f}min")
    print(f"  Accel earlier: {earlier_count} ({earlier_count/max(1,len(lead_times))*100:.0f}%)")
    print(f"  Same time: {same_count}")
    print(f"  Accel later: {later_count}")
    if lead_times:
        print(f"  Mean lead time (accel over thresh): {np.mean(lead_times):.1f}min")
        print(f"  Median lead time: {np.median(lead_times):.1f}min")

    return {
        'experiment': 'EXP-1754',
        'title': 'UAM Predictive Detection via Acceleration',
        'n_events': n_events,
        'announced_pct': round(announced / max(1, n_events) * 100, 1),
        'thresh_detect_mean_min': round(float(mean_thresh), 1),
        'thresh_detect_median_min': round(float(median_thresh), 1),
        'accel_detect_mean_min': round(float(mean_accel), 1),
        'accel_detect_median_min': round(float(median_accel), 1),
        'accel_earlier_pct': round(earlier_count / max(1, len(lead_times)) * 100, 1),
        'mean_lead_time_min': round(float(np.mean(lead_times)), 1) if lead_times else 0,
        'median_lead_time_min': round(float(np.median(lead_times)), 1) if lead_times else 0,
    }


def exp_1755_glycogen_info_ceiling(patients):
    """Test if glycogen proxy improves information ceiling.

    The glycogen proxy (from EXP-1625) estimates hepatic glucose state
    from recent glucose history. Adding it as a feature to the prediction
    model should help if hepatic state is an important hidden variable.
    """
    print("\n=== EXP-1755: Glycogen Proxy + Information Ceiling ===\n")

    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.model_selection import cross_val_score

    features_base = []
    features_glyc = []
    targets = []

    for pat in patients:
        df = pat['df']
        pk = pat['pk']
        glucose = df['glucose'].values.astype(float)
        iob = df['iob'].values.astype(float) if 'iob' in df.columns else np.zeros(len(df))
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0.0)

        try:
            sd = compute_supply_demand(df, pk, calibrate=True)
            supply = sd['supply']
            demand = sd['demand']
            net_flux = sd['net']
        except Exception:
            continue

        valid = ~np.isnan(glucose)

        # Compute glycogen proxy: rolling 24h mean glucose deviation from mean
        window = STEPS_PER_DAY  # 24h
        g_mean = np.nanmean(glucose[valid])

        # Running integral of glucose excess above mean (proxy for glycogen filling)
        glycogen = np.zeros(len(glucose))
        tau = STEPS_PER_HOUR * 6  # 6h decay
        for i in range(1, len(glucose)):
            if valid[i]:
                excess = (glucose[i] - g_mean) / g_mean  # normalized
                glycogen[i] = glycogen[i-1] * (1 - 1/tau) + excess
            else:
                glycogen[i] = glycogen[i-1] * (1 - 1/tau)

        # Also compute time-below-range in last 6h (hypoglycemia drains glycogen)
        tbr_6h = np.zeros(len(glucose))
        for i in range(STEPS_PER_HOUR * 6, len(glucose)):
            window_g = glucose[i - STEPS_PER_HOUR * 6:i]
            window_valid = window_g[~np.isnan(window_g)]
            if len(window_valid) > 0:
                tbr_6h[i] = np.mean(window_valid < LOW)

        for i in range(2 * STEPS_PER_HOUR, len(glucose) - STEPS_PER_HOUR):
            if not valid[i]:
                continue

            s_i = supply[i] if i < len(supply) else 0
            d_i = demand[i] if i < len(demand) else 0
            nf_i = net_flux[i] if i < len(net_flux) else 0
            iob_i = iob[i] if not np.isnan(iob[i]) else 0

            feat_base = [s_i, d_i, nf_i, iob_i, glucose[i]]
            feat_glyc = feat_base + [glycogen[i], tbr_6h[i]]

            future = glucose[i + STEPS_PER_HOUR]
            if np.isnan(future):
                continue

            target = future - glucose[i]
            features_base.append(feat_base)
            features_glyc.append(feat_glyc)
            targets.append(target)

    max_n = 20000
    X_base = np.array(features_base[:max_n])
    X_glyc = np.array(features_glyc[:max_n])
    y = np.array(targets[:max_n])

    model_base = GradientBoostingRegressor(n_estimators=100, max_depth=4, random_state=42, subsample=0.8)
    model_glyc = GradientBoostingRegressor(n_estimators=100, max_depth=4, random_state=42, subsample=0.8)

    scores_base = cross_val_score(model_base, X_base, y, cv=5, scoring='r2')
    scores_glyc = cross_val_score(model_glyc, X_glyc, y, cv=5, scoring='r2')

    r2_base = float(np.mean(scores_base))
    r2_glyc = float(np.mean(scores_glyc))

    print(f"  Base model (S, D, NF, IOB, BG): R²={r2_base:.4f}")
    print(f"  + Glycogen proxy:                R²={r2_glyc:.4f}")
    print(f"  Improvement:                     ΔR²={r2_glyc - r2_base:+.4f}")

    return {
        'experiment': 'EXP-1755',
        'title': 'Glycogen Proxy + Information Ceiling',
        'n_samples': len(targets),
        'r2_base': round(r2_base, 4),
        'r2_glycogen': round(r2_glyc, 4),
        'r2_improvement': round(r2_glyc - r2_base, 4),
    }


def exp_1756_metabolic_context(patients):
    """Decompose supply/demand behavior by metabolic context.

    Contexts: overnight (0-6h), morning fasting (6-9h), daytime (9-21h),
    evening (21-24h). Also split by fed/fasting state (carbs in last 2h).
    """
    print("\n=== EXP-1756: Metabolic Context Analysis ===\n")

    contexts = {
        'overnight': (0, 6),
        'morning': (6, 10),
        'daytime': (10, 18),
        'evening': (18, 24),
    }

    context_stats = {ctx: {'glucose': [], 'supply': [], 'demand': [], 'net_flux': [],
                           'tar': 0, 'tbr': 0, 'total': 0}
                     for ctx in contexts}
    fed_stats = {'fed': {'glucose': [], 'supply': [], 'demand': [], 'net_flux': [],
                         'tar': 0, 'tbr': 0, 'total': 0},
                 'fasting': {'glucose': [], 'supply': [], 'demand': [], 'net_flux': [],
                             'tar': 0, 'tbr': 0, 'total': 0}}

    for pat in patients:
        df = pat['df']
        pk = pat['pk']
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0.0)

        try:
            sd = compute_supply_demand(df, pk, calibrate=True)
            supply = sd['supply']
            demand = sd['demand']
            net_flux = sd['net']
        except Exception:
            continue

        valid = ~np.isnan(glucose)

        for i in range(len(glucose)):
            if not valid[i] or i >= len(supply):
                continue

            tod = (i % STEPS_PER_DAY) / STEPS_PER_HOUR  # hours
            g = glucose[i]

            # Determine context
            for ctx_name, (start_h, end_h) in contexts.items():
                if start_h <= tod < end_h:
                    ctx = context_stats[ctx_name]
                    ctx['glucose'].append(g)
                    ctx['supply'].append(supply[i])
                    ctx['demand'].append(demand[i])
                    ctx['net_flux'].append(net_flux[i])
                    ctx['total'] += 1
                    if g > HIGH:
                        ctx['tar'] += 1
                    if g < LOW:
                        ctx['tbr'] += 1
                    break

            # Fed vs fasting (carbs in last 2h)
            carb_window = carbs[max(0, i - 2*STEPS_PER_HOUR):i]
            is_fed = carb_window.sum() > 1.0
            fed_key = 'fed' if is_fed else 'fasting'
            fs = fed_stats[fed_key]
            fs['glucose'].append(g)
            fs['supply'].append(supply[i])
            fs['demand'].append(demand[i])
            fs['net_flux'].append(net_flux[i])
            fs['total'] += 1
            if g > HIGH:
                fs['tar'] += 1
            if g < LOW:
                fs['tbr'] += 1

    result_contexts = {}
    print(f"  {'Context':12s}  {'n':>8s}  {'Mean BG':>8s}  {'TAR%':>6s}  {'TBR%':>6s}  "
          f"{'Supply':>8s}  {'Demand':>8s}  {'Net':>8s}")
    for ctx_name in contexts:
        ctx = context_stats[ctx_name]
        n = ctx['total']
        if n == 0:
            continue
        mean_bg = float(np.mean(ctx['glucose']))
        tar_pct = ctx['tar'] / n * 100
        tbr_pct = ctx['tbr'] / n * 100
        mean_supply = float(np.mean(ctx['supply']))
        mean_demand = float(np.mean(ctx['demand']))
        mean_nf = float(np.mean(ctx['net_flux']))

        result_contexts[ctx_name] = {
            'n': n,
            'mean_bg': round(mean_bg, 1),
            'tar_pct': round(tar_pct, 1),
            'tbr_pct': round(tbr_pct, 1),
            'mean_supply': round(mean_supply, 3),
            'mean_demand': round(mean_demand, 3),
            'mean_net_flux': round(mean_nf, 3),
        }
        print(f"  {ctx_name:12s}  {n:8d}  {mean_bg:8.1f}  {tar_pct:5.1f}%  {tbr_pct:5.1f}%  "
              f"{mean_supply:8.3f}  {mean_demand:8.3f}  {mean_nf:8.3f}")

    result_fed = {}
    print()
    for fed_key in ['fasting', 'fed']:
        fs = fed_stats[fed_key]
        n = fs['total']
        if n == 0:
            continue
        mean_bg = float(np.mean(fs['glucose']))
        tar_pct = fs['tar'] / n * 100
        tbr_pct = fs['tbr'] / n * 100
        mean_supply = float(np.mean(fs['supply']))
        mean_demand = float(np.mean(fs['demand']))
        mean_nf = float(np.mean(fs['net_flux']))

        result_fed[fed_key] = {
            'n': n,
            'mean_bg': round(mean_bg, 1),
            'tar_pct': round(tar_pct, 1),
            'tbr_pct': round(tbr_pct, 1),
            'mean_supply': round(mean_supply, 3),
            'mean_demand': round(mean_demand, 3),
            'mean_net_flux': round(mean_nf, 3),
        }
        print(f"  {fed_key:12s}  {n:8d}  {mean_bg:8.1f}  {tar_pct:5.1f}%  {tbr_pct:5.1f}%  "
              f"{mean_supply:8.3f}  {mean_demand:8.3f}  {mean_nf:8.3f}")

    return {
        'experiment': 'EXP-1756',
        'title': 'Metabolic Context Analysis',
        'time_of_day_contexts': result_contexts,
        'fed_fasting': result_fed,
    }


def exp_1757_settings_simulation(patients):
    """Simulate centering correction: shift mean glucose to ideal center.

    For each patient, compute what TIR *would be* if we could shift
    their entire glucose distribution so the mean lands at 125 mg/dL
    (the midpoint of 70-180). This gives an upper bound on
    centering-only interventions.
    """
    print("\n=== EXP-1757: Settings Simulation (Centering Correction) ===\n")

    patient_results = []
    for pat in patients:
        name = pat['name']
        glucose = pat['df']['glucose'].values.astype(float)
        valid = ~np.isnan(glucose)
        g = glucose[valid]
        if len(g) < STEPS_PER_DAY:
            continue

        mean_bg = float(np.mean(g))
        ideal_center = (LOW + HIGH) / 2  # 125

        # Shift distribution
        shift = ideal_center - mean_bg
        g_shifted = g + shift

        # Original metrics
        orig_tir = float(np.mean((g >= LOW) & (g <= HIGH)) * 100)
        orig_tar = float(np.mean(g > HIGH) * 100)
        orig_tbr = float(np.mean(g < LOW) * 100)

        # Shifted metrics
        new_tir = float(np.mean((g_shifted >= LOW) & (g_shifted <= HIGH)) * 100)
        new_tar = float(np.mean(g_shifted > HIGH) * 100)
        new_tbr = float(np.mean(g_shifted < LOW) * 100)

        improvement = new_tir - orig_tir

        r = {
            'patient': name,
            'mean_bg': round(mean_bg, 1),
            'shift_mgdl': round(shift, 1),
            'orig_tir': round(orig_tir, 1),
            'new_tir': round(new_tir, 1),
            'tir_improvement': round(improvement, 1),
            'orig_tar': round(orig_tar, 1),
            'new_tar': round(new_tar, 1),
            'orig_tbr': round(orig_tbr, 1),
            'new_tbr': round(new_tbr, 1),
        }
        patient_results.append(r)

        print(f"  {name}: mean={mean_bg:.0f}, shift={shift:+.0f}, "
              f"TIR: {orig_tir:.1f}% → {new_tir:.1f}% (Δ{improvement:+.1f}%)")

    # Population summary
    improvements = [r['tir_improvement'] for r in patient_results]
    print(f"\n  Mean TIR improvement from centering: {np.mean(improvements):+.1f}%")
    print(f"  Max improvement: {np.max(improvements):+.1f}%")
    print(f"  Min improvement: {np.min(improvements):+.1f}%")

    # Patients where centering helps most
    sorted_patients = sorted(patient_results, key=lambda x: x['tir_improvement'], reverse=True)
    print(f"  Most helped: {sorted_patients[0]['patient']} (Δ{sorted_patients[0]['tir_improvement']:+.1f}%)")

    return {
        'experiment': 'EXP-1757',
        'title': 'Settings Simulation (Centering Correction)',
        'patients': patient_results,
        'mean_tir_improvement': round(float(np.mean(improvements)), 1),
        'max_tir_improvement': round(float(np.max(improvements)), 1),
    }


def exp_1758_cross_patient_ceiling(patients):
    """Leave-one-patient-out information ceiling.

    Tests whether the negative R² is patient-specific (each patient has
    unique dynamics) or universal (the model fails everywhere equally).
    If LOPO R² is much worse than within-patient R², personalization matters.
    """
    print("\n=== EXP-1758: Cross-Patient Information Ceiling (LOPO) ===\n")

    from sklearn.ensemble import GradientBoostingRegressor

    # Build per-patient feature matrices
    patient_data = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        pk = pat['pk']
        glucose = df['glucose'].values.astype(float)
        iob = df['iob'].values.astype(float) if 'iob' in df.columns else np.zeros(len(df))

        try:
            sd = compute_supply_demand(df, pk, calibrate=True)
            supply = sd['supply']
            demand = sd['demand']
            net_flux = sd['net']
        except Exception:
            continue

        valid = ~np.isnan(glucose)
        features = []
        targets = []

        for i in range(2 * STEPS_PER_HOUR, len(glucose) - STEPS_PER_HOUR):
            if not valid[i] or i >= len(supply):
                continue
            feat = [
                supply[i], demand[i], net_flux[i],
                iob[i] if not np.isnan(iob[i]) else 0,
                glucose[i],
            ]
            future = glucose[i + STEPS_PER_HOUR]
            if np.isnan(future):
                continue
            features.append(feat)
            targets.append(future - glucose[i])

        if len(features) >= 200:
            # Subsample to 3000 per patient for tractability
            idx = np.random.RandomState(42).choice(len(features), min(3000, len(features)), replace=False)
            patient_data[name] = {
                'X': np.array([features[i] for i in idx]),
                'y': np.array([targets[i] for i in idx]),
            }

    # Within-patient R² (5-fold CV)
    within_r2s = {}
    for name, data in patient_data.items():
        from sklearn.model_selection import cross_val_score
        model = GradientBoostingRegressor(n_estimators=100, max_depth=4, random_state=42, subsample=0.8)
        scores = cross_val_score(model, data['X'], data['y'], cv=5, scoring='r2')
        within_r2s[name] = float(np.mean(scores))

    # LOPO R²
    lopo_r2s = {}
    names = list(patient_data.keys())
    for test_name in names:
        train_X = np.vstack([patient_data[n]['X'] for n in names if n != test_name])
        train_y = np.concatenate([patient_data[n]['y'] for n in names if n != test_name])
        test_X = patient_data[test_name]['X']
        test_y = patient_data[test_name]['y']

        model = GradientBoostingRegressor(n_estimators=100, max_depth=4, random_state=42, subsample=0.8)
        model.fit(train_X, train_y)
        from sklearn.metrics import r2_score
        pred = model.predict(test_X)
        lopo_r2s[test_name] = float(r2_score(test_y, pred))

    print(f"  {'Patient':>8s}  {'Within R²':>10s}  {'LOPO R²':>10s}  {'Gap':>8s}")
    patient_results = []
    for name in sorted(names):
        w = within_r2s[name]
        l = lopo_r2s[name]
        gap = w - l
        print(f"  {name:>8s}  {w:10.4f}  {l:10.4f}  {gap:+8.4f}")
        patient_results.append({
            'patient': name,
            'within_r2': round(w, 4),
            'lopo_r2': round(l, 4),
            'personalization_gap': round(gap, 4),
        })

    mean_within = float(np.mean(list(within_r2s.values())))
    mean_lopo = float(np.mean(list(lopo_r2s.values())))
    print(f"\n  Mean within-patient R²: {mean_within:.4f}")
    print(f"  Mean LOPO R²: {mean_lopo:.4f}")
    print(f"  Personalization gap: {mean_within - mean_lopo:+.4f}")

    return {
        'experiment': 'EXP-1758',
        'title': 'Cross-Patient Information Ceiling (LOPO)',
        'patients': patient_results,
        'mean_within_r2': round(mean_within, 4),
        'mean_lopo_r2': round(mean_lopo, 4),
        'personalization_gap': round(mean_within - mean_lopo, 4),
    }


def generate_figures(results, patients):
    """Generate 4 figures for the report."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # Fig 1: Centering decomposition — bar chart of centering-fixable vs irreducible TAR
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1751 = results.get('EXP-1751', {})
    pats = r1751.get('patients', [])
    if pats:
        names = [p['patient'] for p in pats]
        fix_tar = [p['centering_fixable_tar_pct'] for p in pats]
        irr_tar = [p['ideal_tar_pct'] for p in pats]
        offsets = [p['centering_offset_mgdl'] for p in pats]

        x = np.arange(len(names))
        axes[0].bar(x, fix_tar, label='Centering-fixable TAR', color='coral', alpha=0.8)
        axes[0].bar(x, irr_tar, bottom=fix_tar, label='Irreducible TAR (variability)',
                    color='steelblue', alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('TAR (%)')
        axes[0].set_title('TAR Decomposition: Centering vs Variability')
        axes[0].legend()

        colors = ['green' if o < 0 else 'red' for o in offsets]
        axes[1].bar(x, offsets, color=colors, alpha=0.7)
        axes[1].axhline(0, color='black', linewidth=0.5)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('Mean BG offset from 125 mg/dL')
        axes[1].set_title('Centering Error by Patient')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'cen-fig1-centering-decomp.png', dpi=150)
    plt.close()
    print("  Saved fig1")

    # Fig 2: Settings simulation — TIR before and after centering
    fig, ax = plt.subplots(figsize=(12, 6))

    r1757 = results.get('EXP-1757', {})
    sim_pats = r1757.get('patients', [])
    if sim_pats:
        names = [p['patient'] for p in sim_pats]
        orig_tir = [p['orig_tir'] for p in sim_pats]
        new_tir = [p['new_tir'] for p in sim_pats]

        x = np.arange(len(names))
        width = 0.35
        ax.bar(x - width/2, orig_tir, width, label='Current TIR', color='steelblue', alpha=0.8)
        ax.bar(x + width/2, new_tir, width, label='Centered TIR', color='green', alpha=0.8)
        ax.axhline(70, color='gold', linewidth=2, linestyle='--', label='70% TIR target')
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel('TIR (%)')
        ax.set_title('TIR Before and After Mean-Centering Simulation')
        ax.legend()
        ax.set_ylim(0, 100)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'cen-fig2-settings-sim.png', dpi=150)
    plt.close()
    print("  Saved fig2")

    # Fig 3: Metabolic context — S/D/NF by time of day
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1756 = results.get('EXP-1756', {})
    tod_ctx = r1756.get('time_of_day_contexts', {})
    if tod_ctx:
        ctx_names = ['overnight', 'morning', 'daytime', 'evening']
        ctx_labels = [c for c in ctx_names if c in tod_ctx]
        supply_vals = [tod_ctx[c]['mean_supply'] for c in ctx_labels]
        demand_vals = [tod_ctx[c]['mean_demand'] for c in ctx_labels]
        nf_vals = [tod_ctx[c]['mean_net_flux'] for c in ctx_labels]

        x = np.arange(len(ctx_labels))
        width = 0.25
        axes[0].bar(x - width, supply_vals, width, label='Supply', color='green', alpha=0.8)
        axes[0].bar(x, demand_vals, width, label='Demand', color='red', alpha=0.8)
        axes[0].bar(x + width, nf_vals, width, label='Net flux', color='purple', alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(ctx_labels)
        axes[0].set_ylabel('mg/dL per 5 min')
        axes[0].set_title('Supply-Demand by Time of Day')
        axes[0].legend()

        tar_vals = [tod_ctx[c]['tar_pct'] for c in ctx_labels]
        tbr_vals = [tod_ctx[c]['tbr_pct'] for c in ctx_labels]
        axes[1].bar(x - width/2, tar_vals, width, label='TAR %', color='coral', alpha=0.8)
        axes[1].bar(x + width/2, tbr_vals, width, label='TBR %', color='steelblue', alpha=0.8)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(ctx_labels)
        axes[1].set_ylabel('Rate (%)')
        axes[1].set_title('TAR/TBR by Time of Day')
        axes[1].legend()

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'cen-fig3-metabolic-context.png', dpi=150)
    plt.close()
    print("  Saved fig3")

    # Fig 4: Cross-patient ceiling — within vs LOPO R² by patient
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1758 = results.get('EXP-1758', {})
    lopo_pats = r1758.get('patients', [])
    if lopo_pats:
        names = [p['patient'] for p in lopo_pats]
        within = [p['within_r2'] for p in lopo_pats]
        lopo = [p['lopo_r2'] for p in lopo_pats]

        x = np.arange(len(names))
        width = 0.35
        axes[0].bar(x - width/2, within, width, label='Within-patient R²', color='green', alpha=0.8)
        axes[0].bar(x + width/2, lopo, width, label='LOPO R²', color='red', alpha=0.8)
        axes[0].axhline(0, color='black', linewidth=0.5)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('R²')
        axes[0].set_title('Information Ceiling: Within vs Cross-Patient')
        axes[0].legend()

        gaps = [p['personalization_gap'] for p in lopo_pats]
        colors = ['green' if g > 0 else 'red' for g in gaps]
        axes[1].bar(x, gaps, color=colors, alpha=0.7)
        axes[1].axhline(0, color='black', linewidth=0.5)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('ΔR² (within - LOPO)')
        axes[1].set_title('Personalization Gap by Patient')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'cen-fig4-cross-patient.png', dpi=150)
    plt.close()
    print("  Saved fig4")

    # Fig 5: UAM predictive detection — lead time histogram
    fig, ax = plt.subplots(figsize=(10, 6))

    r1754 = results.get('EXP-1754', {})
    if r1754.get('n_events', 0) > 0:
        # We don't have the raw lead times in JSON, summarize from results
        labels = ['Threshold\n(current)', 'Acceleration\n(proposed)']
        medians = [r1754.get('thresh_detect_median_min', 0),
                   r1754.get('accel_detect_median_min', 0)]
        means = [r1754.get('thresh_detect_mean_min', 0),
                 r1754.get('accel_detect_mean_min', 0)]

        x = np.arange(len(labels))
        width = 0.35
        ax.bar(x - width/2, medians, width, label='Median', color='steelblue', alpha=0.8)
        ax.bar(x + width/2, means, width, label='Mean', color='coral', alpha=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylabel('Detection time (minutes from rise start)')
        ax.set_title(f'UAM Detection: Threshold vs Acceleration (n={r1754["n_events"]})')
        ax.legend()

        # Annotate improvement
        lead = r1754.get('median_lead_time_min', 0)
        earlier_pct = r1754.get('accel_earlier_pct', 0)
        ax.annotate(f'Accel earlier in {earlier_pct:.0f}% of events\n'
                    f'Median lead: {lead:.1f} min',
                    xy=(0.5, 0.85), xycoords='axes fraction',
                    fontsize=11, ha='center',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='lightyellow'))

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'cen-fig5-uam-detection.png', dpi=150)
    plt.close()
    print("  Saved fig5")

    # Fig 6: Natural experiment ceiling — stable vs unstable R²
    fig, ax = plt.subplots(figsize=(8, 6))

    r1753 = results.get('EXP-1753', {})
    r2_s = r1753.get('r2_stable', 0)
    r2_u = r1753.get('r2_unstable', 0)

    labels = ['Stable windows\n(no carbs, low IOB)', 'Unstable windows\n(active therapy)']
    values = [r2_s, r2_u]
    colors = ['green' if v > 0 else 'red' for v in values]
    ax.bar(labels, values, color=colors, alpha=0.7, width=0.5)
    ax.axhline(0, color='black', linewidth=1)
    ax.set_ylabel('R² (cross-validated)')
    ax.set_title('Information Ceiling: Stable vs Unstable Metabolic Windows')
    ax.annotate(f'Difference: ΔR²={r2_s - r2_u:+.4f}',
                xy=(0.5, 0.9), xycoords='axes fraction',
                fontsize=12, ha='center',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightyellow'))

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'cen-fig6-stable-ceiling.png', dpi=150)
    plt.close()
    print("  Saved fig6")


def main():
    parser = argparse.ArgumentParser(description='EXP-1751–1758: Centering vs Dynamics')
    parser.add_argument('--figures', action='store_true')
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients(PATIENTS_DIR)
    print(f"Loaded {len(patients)} patients")

    results = {}

    results['EXP-1751'] = exp_1751_centering_decomposition(patients)
    results['EXP-1752'] = exp_1752_settings_adequacy(patients)
    results['EXP-1753'] = exp_1753_natural_experiment_ceiling(patients)
    results['EXP-1754'] = exp_1754_uam_predictive_detection(patients)
    results['EXP-1755'] = exp_1755_glycogen_info_ceiling(patients)
    results['EXP-1756'] = exp_1756_metabolic_context(patients)
    results['EXP-1757'] = exp_1757_settings_simulation(patients)
    results['EXP-1758'] = exp_1758_cross_patient_ceiling(patients)

    # Save JSONs
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for exp_id, result in results.items():
        fname = f"exp-{exp_id.split('-')[1]}_centering_dynamics.json"
        out = {}
        for k, v in result.items():
            if isinstance(v, (dict, list, str, int, float, bool, type(None))):
                out[k] = v
        with open(RESULTS_DIR / fname, 'w') as f:
            json.dump(out, f, indent=2, default=str)
    print(f"\nSaved {len(results)} experiment JSONs")

    if args.figures:
        print("\nGenerating figures...")
        generate_figures(results, patients)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    r1751 = results.get('EXP-1751', {})
    r1753 = results.get('EXP-1753', {})
    r1754 = results.get('EXP-1754', {})
    r1755 = results.get('EXP-1755', {})
    r1757 = results.get('EXP-1757', {})
    r1758 = results.get('EXP-1758', {})

    print(f"  Centering-fixable TAR: {r1751.get('centering_fixable_tar_fraction', '?')}% of total TAR")
    print(f"  Stable window R²: {r1753.get('r2_stable', '?')} vs unstable: {r1753.get('r2_unstable', '?')}")
    print(f"  Accel detection earlier in {r1754.get('accel_earlier_pct', '?')}% of events, "
          f"lead time {r1754.get('median_lead_time_min', '?')}min")
    print(f"  Glycogen proxy ΔR²: {r1755.get('r2_improvement', '?')}")
    print(f"  Mean centering TIR improvement: {r1757.get('mean_tir_improvement', '?')}%")
    print(f"  Personalization gap: {r1758.get('personalization_gap', '?')}")


if __name__ == '__main__':
    main()
