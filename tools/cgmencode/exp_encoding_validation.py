#!/usr/bin/env python3
"""
EXP-419 through EXP-426: Representation Validation — Principle 11

Property tests that validate whether each encoding/representation respects
the correct symmetry properties at its intended time scale.

These are NOT task experiments (we don't measure F1/MAE on a downstream task).
These are **property tests** — systematic checks that the encodings we use
actually capture physiology rather than artifacts.  Think of them as
"unit tests for feature engineering."

Connection to Principle 11 (Representation Validation):
    Every encoding choice embeds an assumption about the data's symmetry.
    If we include time-of-day features, we assume circadian dependence.
    If we normalise by ISF, we assume cross-patient equivariance.
    If we use B-spline smoothing, we assume local continuity.
    These experiments test those assumptions *directly* — before we ever
    train a downstream model.

Confirmed symmetries (4/10):
    1. Time-translation invariance at 2h — EXP-349 (time_sin/cos removal → +0.9% F1)
    2. Time-translation invariance at 12h — EXP-298 (time removal → +0.224 silhouette)
    3. PK resolves DIA ambiguity at 6h — EXP-353 (Δ=−7.4 MAE)
    4. B-spline SNR improvement — EXP-331 (+15% SNR)

Untested symmetries (6/10) — validated here:
    5. Absorption reflection symmetry (EXP-420)
    6. Conservation / glucose integral (EXP-421)
    7. ISF equivariance cross-patient (EXP-422)
    8. Event recurrence regularity (EXP-426)
    9. PK equivariance deviation = signal (EXP-425)
   10. Circadian time-dependence at 24h+ (EXP-419 crossover region)

Experiment registry:
    EXP-419: Time-Translation Invariance Test (Formal Proof)
    EXP-420: Absorption Envelope Symmetry Test
    EXP-421: Glucose Conservation Test
    EXP-422: ISF Equivariance Test (Cross-Patient)
    EXP-423: Scale-Dependent Encoding Adequacy Sweep
    EXP-424: Augmentation as Symmetry Probe
    EXP-425: PK Residual Analysis (Encoding Quality Test)
    EXP-426: Event Recurrence Regularity Test
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

# Optional heavy imports — guarded so the module can be parsed anywhere
try:
    from scipy.stats import spearmanr, wilcoxon
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

# Local imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.real_data_adapter import build_nightscout_grid
from cgmencode.continuous_pk import build_continuous_pk_features

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STEPS_PER_HOUR = 12
GLUCOSE_SCALE = 400.0

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'

SCALES = {
    '2h':  24,
    '6h':  72,
    '12h': 144,
    '24h': 288,
}

QUICK_PATIENTS = 4


# ---------------------------------------------------------------------------
# Data loading (mirrors exp_treatment_planning.py)
# ---------------------------------------------------------------------------

def find_patient_dirs(patients_dir):
    """Return sorted list of patient directory Paths."""
    base = Path(patients_dir)
    return sorted([d for d in base.iterdir() if d.is_dir()])


def load_patients(patients_dir, max_patients=None, patient_filter=None,
                  verbose=True):
    """Load per-patient DataFrames + PK features.

    Parameters
    ----------
    patients_dir : str
        Root directory containing one sub-directory per patient.
    max_patients : int or None
        Cap on number of patients to load (for --quick mode).
    patient_filter : str or None
        If set, load only the patient whose directory name matches.
    verbose : bool
        Print progress.

    Returns
    -------
    list of dict
        Each dict has keys: name, df, grid (N,8), pk (N,8).
    """
    pdirs = find_patient_dirs(patients_dir)
    if patient_filter:
        pdirs = [p for p in pdirs if p.name == patient_filter]
    if max_patients:
        pdirs = pdirs[:max_patients]

    patients = []
    for pdir in pdirs:
        train_dir = str(pdir / 'training')
        try:
            result = build_nightscout_grid(train_dir, verbose=False)
            if result is None:
                continue
            df, features = result
            if df is None or len(df) < 100:
                continue
            pk = build_continuous_pk_features(df)
            if pk is None:
                continue
            n = min(len(features), len(pk))
            patients.append({
                'name': pdir.name,
                'df':   df.iloc[:n],
                'grid': features[:n],
                'pk':   pk[:n],
            })
            if verbose:
                print(f"  Loaded {pdir.name}: {n} steps")
        except Exception as exc:
            if verbose:
                print(f"  Skip {pdir.name}: {exc}")
    return patients


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def make_windows(arr, window_size, stride=None):
    """Sliding window view over first axis.

    Returns (n_windows, window_size, ...) array.
    """
    stride = stride or (window_size // 2)
    windows = []
    for start in range(0, len(arr) - window_size + 1, stride):
        windows.append(arr[start:start + window_size])
    if len(windows) == 0:
        return np.empty((0, window_size) + arr.shape[1:], dtype=arr.dtype)
    return np.stack(windows)


def compute_ema(glucose, alphas=(0.1, 0.3, 0.7)):
    """Multi-rate exponential moving average channels.

    Returns (T, len(alphas)) array.
    """
    channels = []
    for alpha in alphas:
        ema = np.zeros_like(glucose, dtype=np.float64)
        ema[0] = glucose[0] if not np.isnan(glucose[0]) else 0.0
        for t in range(1, len(glucose)):
            if np.isnan(glucose[t]):
                ema[t] = ema[t - 1]
            else:
                ema[t] = alpha * glucose[t] + (1 - alpha) * ema[t - 1]
        channels.append(ema)
    return np.stack(channels, axis=-1)


def bspline_smooth_simple(glucose_1d):
    """Lightweight B-spline smoothing (no scikit-fda dependency).

    Uses a 3rd-order uniform filter as a fast stand-in when the full FDA
    library is unavailable.  For proper basis projection, use
    ``fda_features.bspline_smooth``.
    """
    from scipy.ndimage import uniform_filter1d
    return uniform_filter1d(glucose_1d.astype(np.float64), size=7).astype(np.float32)


def cosine_similarity(a, b):
    """Cosine similarity between two 1-D vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-8 or norm_b < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def save_results(result, filename):
    """Persist experiment results as JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f'{filename}.json'
    with open(path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n  Saved: {path}")


# ---------------------------------------------------------------------------
# Event extraction (shared by EXP-419, -420, -421)
# ---------------------------------------------------------------------------

def find_isolated_events(df, min_gap_hours=3):
    """Find bolus/carb events with no other events within ±min_gap_hours.

    Parameters
    ----------
    df : pd.DataFrame
        Must have columns ``bolus`` and ``carbs``, indexed at 5-min resolution.

    Returns
    -------
    list of dict
        Each dict has: time_idx, bolus, carbs, event_type ('bolus'|'carbs'|'mixed').
    """
    min_gap_steps = min_gap_hours * STEPS_PER_HOUR
    bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
    carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))

    event_indices = np.where((bolus > 0) | (carbs > 0))[0]
    if len(event_indices) == 0:
        return []

    events = []
    for idx in event_indices:
        nearby = [j for j in event_indices
                  if j != idx and abs(j - idx) < min_gap_steps]
        if len(nearby) > 0:
            continue
        b_val = float(bolus[idx])
        c_val = float(carbs[idx])
        if b_val > 0 and c_val > 0:
            etype = 'mixed'
        elif b_val > 0:
            etype = 'bolus'
        else:
            etype = 'carbs'
        events.append({
            'time_idx': int(idx),
            'bolus': b_val,
            'carbs': c_val,
            'event_type': etype,
        })
    return events


# ═══════════════════════════════════════════════════════════════════════════
# EXP-419: Time-Translation Invariance Test
# ═══════════════════════════════════════════════════════════════════════════

def time_translation_test(events, glucose, window_steps=72):
    """Test whether similar events produce similar responses regardless of time.

    For every pair of events of the same type and similar magnitude,
    extract the glucose response curve and measure cosine similarity.
    Then compute Spearman correlation between the pair's time-of-day
    difference and their similarity.

    If r is small (|r| < 0.15), response similarity is independent of
    clock time → time features are NOT justified at this window scale.

    Parameters
    ----------
    events : list of dict
        Isolated events from ``find_isolated_events``.
    glucose : np.ndarray, shape (T,)
        Raw glucose in mg/dL.
    window_steps : int
        Response window in 5-min steps.

    Returns
    -------
    dict with spearman_r, p_value, n_pairs, time_invariant flag.
    """
    if not HAS_SCIPY:
        return {'error': 'scipy not available'}

    similarities = []
    time_diffs = []

    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            e1, e2 = events[i], events[j]

            # Same type only
            if e1['event_type'] != e2['event_type']:
                continue
            if e1['event_type'] == 'mixed':
                continue

            # Similar magnitude (within ±20%)
            mag1 = e1['bolus'] + e1['carbs']
            mag2 = e2['bolus'] + e2['carbs']
            if min(mag1, mag2) < 0.1:
                continue
            if max(mag1, mag2) / min(mag1, mag2) > 1.2:
                continue

            idx1, idx2 = e1['time_idx'], e2['time_idx']
            if idx1 + window_steps > len(glucose):
                continue
            if idx2 + window_steps > len(glucose):
                continue

            r1 = glucose[idx1:idx1 + window_steps].copy()
            r2 = glucose[idx2:idx2 + window_steps].copy()

            nan_frac = 0.1
            if np.isnan(r1).sum() > window_steps * nan_frac:
                continue
            if np.isnan(r2).sum() > window_steps * nan_frac:
                continue

            # Impute remaining NaN with linear interpolation
            for arr in (r1, r2):
                nans = np.isnan(arr)
                if nans.any():
                    arr[nans] = np.interp(
                        np.flatnonzero(nans),
                        np.flatnonzero(~nans),
                        arr[~nans],
                    )

            sim = cosine_similarity(r1, r2)

            # Circular time-of-day difference (0–12 h)
            h1 = (idx1 % 288) / STEPS_PER_HOUR
            h2 = (idx2 % 288) / STEPS_PER_HOUR
            tdiff = min(abs(h1 - h2), 24 - abs(h1 - h2))

            similarities.append(sim)
            time_diffs.append(tdiff)

    if len(similarities) < 10:
        return {'status': 'insufficient_pairs', 'n_pairs': len(similarities)}

    r, p = spearmanr(time_diffs, similarities)
    mean_sim = float(np.mean(similarities))

    if abs(r) < 0.15:
        interp = 'TIME_INVARIANT'
    elif abs(r) < 0.3:
        interp = 'WEAK_TIME_DEPENDENCE'
    else:
        interp = 'CIRCADIAN_DEPENDENT'

    return {
        'spearman_r': float(r),
        'p_value': float(p),
        'n_pairs': len(similarities),
        'mean_similarity': mean_sim,
        'time_invariant': abs(r) < 0.15,
        'interpretation': interp,
    }


def run_exp419(args):
    """EXP-419: Time-Translation Invariance — multi-scale formal proof.

    Tests the hypothesis at 2h, 6h, 12h, 24h window scales per-patient.
    Expected: invariant at ≤12h, circadian-dependent at 24h.
    """
    print("\n" + "=" * 60)
    print("EXP-419: Time-Translation Invariance (Formal Proof)")
    print("=" * 60)

    cfg = _get_config(args)
    patients = load_patients(args.patients_dir, max_patients=cfg['max_patients'],
                             patient_filter=getattr(args, 'patient', None))
    if not patients:
        return {'error': 'no patients loaded'}

    per_patient = {}
    for pat in patients:
        glucose = pat['df']['glucose'].values.astype(np.float64)
        events = find_isolated_events(pat['df'])
        if len(events) < 5:
            per_patient[pat['name']] = {'status': 'insufficient_events',
                                        'n_events': len(events)}
            continue

        per_scale = {}
        for scale_name, window_steps in SCALES.items():
            result = time_translation_test(events, glucose, window_steps)
            per_scale[scale_name] = result
            status = result.get('interpretation', result.get('status', '?'))
            print(f"  {pat['name']} @ {scale_name}: {status}"
                  f" (r={result.get('spearman_r', '?'):.3f},"
                  f" n={result.get('n_pairs', 0)})"
                  if 'spearman_r' in result
                  else f"  {pat['name']} @ {scale_name}: {status}")

        per_patient[pat['name']] = per_scale

    # Aggregate across patients per scale
    aggregate = {}
    for scale_name in SCALES:
        rs = [per_patient[p][scale_name]['spearman_r']
              for p in per_patient
              if isinstance(per_patient[p], dict)
              and scale_name in per_patient[p]
              and 'spearman_r' in per_patient[p][scale_name]]
        if rs:
            mean_r = float(np.mean(rs))
            aggregate[scale_name] = {
                'mean_spearman_r': mean_r,
                'std_spearman_r': float(np.std(rs)),
                'n_patients': len(rs),
                'time_invariant': abs(mean_r) < 0.15,
            }

    results = {
        'experiment': 'EXP-419',
        'title': 'Time-Translation Invariance (Formal Proof)',
        'principle': 'Principle 11: Representation Validation',
        'hypothesis': 'Similar physiological events produce similar glucose '
                      'responses regardless of clock time at ≤12h scales; '
                      'circadian dependence emerges at 24h.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }
    save_results(results, 'exp419_time_translation_invariance')
    return results


# ═══════════════════════════════════════════════════════════════════════════
# EXP-420: Absorption Envelope Symmetry Test
# ═══════════════════════════════════════════════════════════════════════════

def absorption_symmetry_test(events, glucose):
    """Measure reflection symmetry of glucose response around peak disturbance.

    For each isolated event, extract the glucose response window (−1h to +5h),
    find the peak deviation from pre-event baseline, and compute the ratio
    of pre-peak area to post-peak area.

    Symmetric response: ratio ≈ 0.8–1.2.
    Asymmetric (fast-rise / slow-resolution): ratio < 0.8.

    Parameters
    ----------
    events : list of dict
        Isolated events from ``find_isolated_events``.
    glucose : np.ndarray, shape (T,)
        Raw glucose in mg/dL.

    Returns
    -------
    dict with per-type statistics and all individual measurements.
    """
    results = {'bolus': [], 'carbs': [], 'mixed': []}

    for event in events:
        idx = event['time_idx']
        start = max(0, idx - STEPS_PER_HOUR)  # 1 h before
        end = min(len(glucose), idx + 5 * STEPS_PER_HOUR)  # 5 h after
        response = glucose[start:end].copy()

        if len(response) < 12:
            continue
        if np.isnan(response).sum() > len(response) * 0.1:
            continue

        # Impute sparse NaN
        nans = np.isnan(response)
        if nans.any():
            valid_idx = np.flatnonzero(~nans)
            if len(valid_idx) < 3:
                continue
            response[nans] = np.interp(
                np.flatnonzero(nans), valid_idx, response[valid_idx])

        baseline = np.mean(response[:6])  # first 30 min as baseline
        deviation = response - baseline

        peak_idx = int(np.argmax(np.abs(deviation)))
        if peak_idx < 2 or peak_idx > len(deviation) - 2:
            continue

        pre_peak = np.abs(deviation[:peak_idx])
        post_peak = np.abs(deviation[peak_idx:])

        pre_area = float(np.trapezoid(pre_peak))
        post_area = float(np.trapezoid(post_peak))

        if post_area < 1e-6:
            continue

        ratio = pre_area / post_area

        # Recovery: time from peak back to within 10% of peak magnitude
        peak_mag = abs(deviation[peak_idx])
        post_dev = np.abs(deviation[peak_idx:])
        recovery_steps = len(post_dev)
        for r_idx in range(len(post_dev)):
            if post_dev[r_idx] < peak_mag * 0.1:
                recovery_steps = r_idx
                break

        entry = {
            'symmetry_ratio': float(ratio),
            'peak_magnitude': float(peak_mag),
            'recovery_minutes': int(recovery_steps * 5),
            'time_to_peak_minutes': int(peak_idx * 5),
        }

        results[event['event_type']].append(entry)

    summary = {}
    for etype, entries in results.items():
        if len(entries) < 5:
            summary[etype] = {'status': 'insufficient', 'n': len(entries)}
            continue
        ratios = [e['symmetry_ratio'] for e in entries]
        mean_ratio = float(np.mean(ratios))
        summary[etype] = {
            'n': len(entries),
            'mean_ratio': mean_ratio,
            'std_ratio': float(np.std(ratios)),
            'median_ratio': float(np.median(ratios)),
            'mean_recovery_min': float(np.mean(
                [e['recovery_minutes'] for e in entries])),
            'mean_time_to_peak_min': float(np.mean(
                [e['time_to_peak_minutes'] for e in entries])),
            'symmetric': 0.7 < mean_ratio < 1.3,
        }

    return {'per_type': summary, 'all_events': results}


def run_exp420(args):
    """EXP-420: Absorption Envelope Symmetry Test.

    Quantifies reflection symmetry of glucose response curves around their
    peak disturbance, separated by event type (bolus / carbs / mixed).

    The DIA Valley (EXP-289) is indirect evidence — performance is worst
    when the window captures only one side of the absorption arc.  This
    test provides direct measurement of that asymmetry.
    """
    print("\n" + "=" * 60)
    print("EXP-420: Absorption Envelope Symmetry")
    print("=" * 60)

    cfg = _get_config(args)
    patients = load_patients(args.patients_dir, max_patients=cfg['max_patients'],
                             patient_filter=getattr(args, 'patient', None))
    if not patients:
        return {'error': 'no patients loaded'}

    per_patient = {}
    for pat in patients:
        glucose = pat['df']['glucose'].values.astype(np.float64)
        events = find_isolated_events(pat['df'])
        result = absorption_symmetry_test(events, glucose)
        per_patient[pat['name']] = result['per_type']

        for etype, stats in result['per_type'].items():
            if 'mean_ratio' in stats:
                sym = '✅' if stats['symmetric'] else '⚠️'
                print(f"  {pat['name']} {etype:>6s}: ratio={stats['mean_ratio']:.2f}"
                      f" ±{stats['std_ratio']:.2f}  n={stats['n']}  {sym}")

    # Aggregate across patients
    aggregate = {}
    for etype in ('bolus', 'carbs', 'mixed'):
        ratios = [per_patient[p][etype]['mean_ratio']
                  for p in per_patient
                  if etype in per_patient[p]
                  and 'mean_ratio' in per_patient[p][etype]]
        if ratios:
            mean_r = float(np.mean(ratios))
            aggregate[etype] = {
                'mean_ratio': mean_r,
                'std_ratio': float(np.std(ratios)),
                'n_patients': len(ratios),
                'symmetric': 0.7 < mean_r < 1.3,
            }

    results = {
        'experiment': 'EXP-420',
        'title': 'Absorption Envelope Symmetry',
        'principle': 'Principle 11: Representation Validation',
        'hypothesis': 'Insulin bolus responses are roughly symmetric '
                      '(ratio 0.8–1.2); carb responses are asymmetric '
                      '(fast rise, slow resolution → ratio 0.5–0.8).',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }
    save_results(results, 'exp420_absorption_symmetry')
    return results


# ═══════════════════════════════════════════════════════════════════════════
# EXP-421: Glucose Conservation Test
# ═══════════════════════════════════════════════════════════════════════════

def conservation_test(glucose_windows, iob_windows, cob_windows,
                      isf_values, cr_values):
    """Test whether the integral of glucose deviation is predicted by physics.

    Physics model: delta_bg = −delta_iob × ISF + delta_cob × (ISF / CR)

    If the physics model is complete, the integral of
    (actual_glucose − predicted_glucose) over each window should be ≈ 0.

    Systematic positive residual → unmodeled glucose rise (dawn, stress).
    Systematic negative residual → unmodeled glucose drop (exercise).

    Parameters
    ----------
    glucose_windows : list of np.ndarray
        Each element is a 1-D glucose trace (mg/dL) for one 12h window.
    iob_windows : list of np.ndarray
        Matching IOB traces (units).
    cob_windows : list of np.ndarray
        Matching COB traces (grams).
    isf_values : list of float
        Per-window ISF (mg/dL per unit).
    cr_values : list of float
        Per-window carb ratio (g per unit).

    Returns
    -------
    dict with mean_integral, conservation_holds flag, interpretation.
    """
    residual_integrals = []

    for i in range(len(glucose_windows)):
        glucose = glucose_windows[i]
        iob = iob_windows[i]
        cob = cob_windows[i]
        isf = isf_values[i]
        cr = cr_values[i]

        if np.isnan(glucose).sum() > len(glucose) * 0.1:
            continue

        predicted = np.zeros_like(glucose)
        predicted[0] = glucose[0]
        for t in range(1, len(glucose)):
            delta_iob = iob[t - 1] - iob[t]   # IOB decrease → insulin effect
            delta_cob = cob[t - 1] - cob[t]   # COB decrease → carb absorption
            insulin_effect = -delta_iob * isf
            carb_effect = delta_cob * (isf / cr) if cr > 0 else 0.0
            predicted[t] = predicted[t - 1] + insulin_effect + carb_effect

        residual = glucose - predicted
        # Integral in mg/dL · hours (5-min steps → ×5/60)
        integral = float(np.trapezoid(residual) * 5.0 / 60.0)
        residual_integrals.append(integral)

    if len(residual_integrals) < 10:
        return {'status': 'insufficient_windows',
                'n_windows': len(residual_integrals)}

    integrals = np.array(residual_integrals)
    mean_int = float(np.mean(integrals))
    std_int = float(np.std(integrals))
    se = std_int / np.sqrt(len(integrals))

    # Conservation test: is mean integral indistinguishable from 0?
    conservation_holds = abs(mean_int) < 2 * se
    if abs(mean_int) < 50:
        interp = 'CONSERVED'
    elif mean_int > 0:
        interp = 'SYSTEMATIC_UNDERPREDICTION'
    else:
        interp = 'SYSTEMATIC_OVERPREDICTION'

    return {
        'mean_integral': mean_int,
        'std_integral': std_int,
        'median_integral': float(np.median(integrals)),
        'conservation_holds': bool(conservation_holds),
        'n_windows': len(integrals),
        'fraction_positive': float((integrals > 0).mean()),
        'interpretation': interp,
    }


def _extract_isf_scalar(df):
    """Best-effort scalar ISF in mg/dL/U from DataFrame attrs or heuristic.

    Detects mmol/L profiles (ISF < 15) and converts via ×18.0182.
    """
    isf_sched = getattr(df, 'attrs', {}).get('isf_schedule', None)
    if isf_sched and len(isf_sched) > 0:
        vals = [s.get('value', s.get('sensitivity', 40))
                for s in isf_sched if isinstance(s, dict)]
        if vals:
            isf = float(np.median(vals))
            # mmol/L profiles have ISF < 15; convert to mg/dL
            if isf < 15:
                isf *= 18.0182
            return isf
    return 40.0


def _extract_cr_scalar(df):
    """Best-effort scalar CR from DataFrame attrs or heuristic."""
    cr_sched = getattr(df, 'attrs', {}).get('cr_schedule', None)
    if cr_sched and len(cr_sched) > 0:
        vals = [s.get('value', s.get('carbRatio', 10))
                for s in cr_sched if isinstance(s, dict)]
        if vals:
            return float(np.median(vals))
    return 10.0


def run_exp421(args):
    """EXP-421: Glucose Conservation Test.

    Tests whether insulin + carb physics predict the integral of glucose
    change.  If conservation fails systematically, there are unmodeled
    effects (dawn phenomenon, exercise, stress) that need encoding.
    """
    print("\n" + "=" * 60)
    print("EXP-421: Glucose Conservation Test")
    print("=" * 60)

    cfg = _get_config(args)
    patients = load_patients(args.patients_dir, max_patients=cfg['max_patients'],
                             patient_filter=getattr(args, 'patient', None))
    if not patients:
        return {'error': 'no patients loaded'}

    window_size = SCALES['12h']
    per_patient = {}

    for pat in patients:
        df = pat['df']
        glucose = df['glucose'].values.astype(np.float64)
        iob = df['iob'].values.astype(np.float64) if 'iob' in df.columns else np.zeros(len(df))
        cob = df['cob'].values.astype(np.float64) if 'cob' in df.columns else np.zeros(len(df))
        # Fill NaN — missing IOB/COB means no active insulin/carbs
        iob = np.nan_to_num(iob, nan=0.0)
        cob = np.nan_to_num(cob, nan=0.0)
        glucose = np.where(np.isnan(glucose), np.nanmean(glucose), glucose)
        isf = _extract_isf_scalar(df)
        cr = _extract_cr_scalar(df)

        g_wins = make_windows(glucose, window_size)
        i_wins = make_windows(iob, window_size)
        c_wins = make_windows(cob, window_size)

        n_wins = len(g_wins)
        isf_vals = [isf] * n_wins
        cr_vals = [cr] * n_wins

        result = conservation_test(
            list(g_wins), list(i_wins), list(c_wins),
            isf_vals, cr_vals,
        )
        per_patient[pat['name']] = result

        interp = result.get('interpretation', result.get('status', '?'))
        mean_i = result.get('mean_integral', '?')
        print(f"  {pat['name']}: {interp}  μ={mean_i}"
              f"  n={result.get('n_windows', 0)}")

    # Aggregate
    means = [per_patient[p]['mean_integral']
             for p in per_patient
             if 'mean_integral' in per_patient[p]]
    aggregate = {}
    if means:
        aggregate = {
            'mean_integral': float(np.mean(means)),
            'std_integral': float(np.std(means)),
            'n_patients': len(means),
            'conservation_holds': abs(float(np.mean(means))) < 50,
        }

    results = {
        'experiment': 'EXP-421',
        'title': 'Glucose Conservation Test',
        'principle': 'Principle 11: Representation Validation',
        'hypothesis': 'Integral of (actual − physics_predicted) glucose ≈ 0. '
                      'Systematic bias indicates unmodeled effects.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }
    save_results(results, 'exp421_glucose_conservation')
    return results


# ═══════════════════════════════════════════════════════════════════════════
# EXP-422: ISF Equivariance Test (Cross-Patient)
# ═══════════════════════════════════════════════════════════════════════════

def isf_equivariance_test(patient_events, patient_isf_values):
    """Test whether ISF-normalised responses are more similar cross-patient.

    For each pair of patients, find matched bolus events (similar magnitude)
    and compare raw vs ISF-normalised cosine similarity of the 6h response.

    If normalised similarity is significantly higher, ISF normalisation is
    a justified encoding choice.

    Parameters
    ----------
    patient_events : dict[str, list[dict]]
        Per-patient list of events.  Each event must have 'response' (1-D array).
    patient_isf_values : dict[str, float]
        Per-patient ISF scalar.

    Returns
    -------
    dict with mean_raw_similarity, mean_norm_similarity, delta, p_value.
    """
    if not HAS_SCIPY:
        return {'error': 'scipy not available'}

    raw_sims = []
    norm_sims = []

    patient_ids = list(patient_events.keys())
    for i in range(len(patient_ids)):
        for j in range(i + 1, len(patient_ids)):
            p1, p2 = patient_ids[i], patient_ids[j]
            isf1 = max(patient_isf_values[p1], 1.0)
            isf2 = max(patient_isf_values[p2], 1.0)

            for e1 in patient_events[p1]:
                for e2 in patient_events[p2]:
                    # Match by magnitude (within ±20%)
                    mag1 = e1['bolus'] + e1['carbs']
                    mag2 = e2['bolus'] + e2['carbs']
                    if min(mag1, mag2) < 0.1:
                        continue
                    if max(mag1, mag2) / min(mag1, mag2) > 1.2:
                        continue

                    r1 = e1['response']
                    r2 = e2['response']
                    if len(r1) != len(r2):
                        continue
                    if np.isnan(r1).any() or np.isnan(r2).any():
                        continue

                    raw_sim = cosine_similarity(r1, r2)
                    norm_r1 = r1 / isf1
                    norm_r2 = r2 / isf2
                    norm_sim = cosine_similarity(norm_r1, norm_r2)

                    raw_sims.append(raw_sim)
                    norm_sims.append(norm_sim)

    if len(raw_sims) < 20:
        return {'status': 'insufficient_pairs', 'n_pairs': len(raw_sims)}

    delta = float(np.mean(norm_sims) - np.mean(raw_sims))
    stat, p = wilcoxon(norm_sims, raw_sims)

    return {
        'mean_raw_similarity': float(np.mean(raw_sims)),
        'mean_norm_similarity': float(np.mean(norm_sims)),
        'delta': delta,
        'p_value': float(p),
        'n_pairs': len(raw_sims),
        'equivariance_confirmed': delta > 0 and p < 0.05,
    }


def run_exp422(args):
    """EXP-422: ISF Equivariance Test (Cross-Patient).

    Tests whether ISF-normalised glucose responses are more similar across
    patients than raw responses.  Validates ISF normalisation as an encoding.
    """
    print("\n" + "=" * 60)
    print("EXP-422: ISF Equivariance (Cross-Patient)")
    print("=" * 60)

    cfg = _get_config(args)
    patients = load_patients(args.patients_dir, max_patients=cfg['max_patients'],
                             patient_filter=getattr(args, 'patient', None))
    if len(patients) < 2:
        return {'error': 'need ≥2 patients for cross-patient test'}

    window_steps = SCALES['6h']

    patient_events = {}
    patient_isf = {}

    for pat in patients:
        glucose = pat['df']['glucose'].values.astype(np.float64)
        events = find_isolated_events(pat['df'])
        isf = _extract_isf_scalar(pat['df'])
        patient_isf[pat['name']] = isf

        enriched = []
        for e in events:
            idx = e['time_idx']
            if idx + window_steps > len(glucose):
                continue
            response = glucose[idx:idx + window_steps].copy()
            if np.isnan(response).sum() > window_steps * 0.1:
                continue
            nans = np.isnan(response)
            if nans.any():
                valid_idx = np.flatnonzero(~nans)
                if len(valid_idx) < 3:
                    continue
                response[nans] = np.interp(
                    np.flatnonzero(nans), valid_idx, response[valid_idx])
            enriched.append({**e, 'response': response})

        patient_events[pat['name']] = enriched
        print(f"  {pat['name']}: {len(enriched)} events, ISF={isf:.1f}")

    result = isf_equivariance_test(patient_events, patient_isf)
    confirmed = result.get('equivariance_confirmed', False)
    delta = result.get('delta', None)
    pval = result.get('p_value', None)
    delta_str = f"{delta:.4f}" if isinstance(delta, (int, float)) else str(delta)
    pval_str = f"{pval:.4f}" if isinstance(pval, (int, float)) else str(pval)
    print(f"\n  Delta similarity: {delta_str}"
          f"  p={pval_str}"
          f"  {'✅ CONFIRMED' if confirmed else '❌ NOT CONFIRMED'}")

    results = {
        'experiment': 'EXP-422',
        'title': 'ISF Equivariance (Cross-Patient)',
        'principle': 'Principle 11: Representation Validation',
        'hypothesis': 'ISF-normalised glucose responses are more similar '
                      'across patients than raw responses (positive Δ).',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'result': result,
        'patient_isf': {k: float(v) for k, v in patient_isf.items()},
        'n_events_per_patient': {
            k: len(v) for k, v in patient_events.items()},
    }
    save_results(results, 'exp422_isf_equivariance')
    return results


# ═══════════════════════════════════════════════════════════════════════════
# EXP-423: Scale-Dependent Encoding Adequacy Sweep
# ═══════════════════════════════════════════════════════════════════════════

def _enc_raw_glucose(g, **kw):
    return g / GLUCOSE_SCALE


def _enc_isf_normalized(g, isf=40.0, target=110.0, **kw):
    return (g - target) / max(isf, 1.0)


def _enc_z_scored(g, mean=None, std=None, **kw):
    m = mean if mean is not None else np.nanmean(g)
    s = std if std is not None else np.nanstd(g)
    return (g - m) / max(s, 1.0)


def _enc_bspline_smooth(g, **kw):
    try:
        return bspline_smooth_simple(g)
    except Exception:
        return g / GLUCOSE_SCALE


def _enc_ema_multi(g, **kw):
    flat = g.ravel() if g.ndim > 1 else g
    return compute_ema(flat, alphas=(0.1, 0.3, 0.7))


def _enc_glucodensity(g, **kw):
    flat = g.ravel() if g.ndim > 1 else g
    counts, _ = np.histogram(np.clip(flat, 40, 400), bins=8,
                             range=(40, 400))
    return counts.astype(np.float64) / max(len(flat), 1)


ENCODINGS = {
    'raw_glucose':     _enc_raw_glucose,
    'isf_normalized':  _enc_isf_normalized,
    'z_scored':        _enc_z_scored,
    'bspline_smooth':  _enc_bspline_smooth,
    'ema_multi':       _enc_ema_multi,
    'glucodensity':    _enc_glucodensity,
}


def encoding_adequacy_sweep(glucose_all, isf_per_patient=40.0,
                            patient_mean=None, patient_std=None):
    """Test each encoding at each scale via clustering quality.

    For each (encoding, scale) pair, encode sliding windows, cluster
    with k-means (k=5), and report silhouette score.  A higher
    silhouette indicates the encoding separates glucose patterns better.

    Parameters
    ----------
    glucose_all : np.ndarray, shape (T,)
        Concatenated glucose trace for one or all patients.
    isf_per_patient : float
        ISF to use for ISF-normalised encoding.
    patient_mean, patient_std : float or None
        Patient-level stats for z-scored encoding.

    Returns
    -------
    dict : scale → encoding → {silhouette, n_windows}.
    """
    if not HAS_SKLEARN:
        return {'error': 'sklearn not available'}

    sweep = {}
    for scale_name, window_size in SCALES.items():
        sweep[scale_name] = {}

        raw_windows = make_windows(glucose_all, window_size,
                                   stride=window_size // 2)
        if len(raw_windows) < 50:
            sweep[scale_name] = {
                'status': 'insufficient_windows', 'n': len(raw_windows)}
            continue

        for enc_name, enc_fn in ENCODINGS.items():
            try:
                kw = dict(isf=isf_per_patient,
                          mean=patient_mean, std=patient_std)
                encoded = np.array([enc_fn(w, **kw) for w in raw_windows])

                if encoded.ndim == 1:
                    encoded = encoded.reshape(-1, 1)
                elif encoded.ndim > 2:
                    encoded = encoded.reshape(len(encoded), -1)

                # Remove rows with NaN
                valid_mask = ~np.isnan(encoded).any(axis=1)
                encoded_clean = encoded[valid_mask]

                if len(encoded_clean) < 50:
                    sweep[scale_name][enc_name] = {
                        'status': 'insufficient', 'n': len(encoded_clean)}
                    continue

                km = KMeans(n_clusters=5, n_init=3, random_state=42)
                labels = km.fit_predict(encoded_clean)

                sil = silhouette_score(
                    encoded_clean, labels,
                    sample_size=min(1000, len(encoded_clean)),
                    random_state=42,
                )
                sweep[scale_name][enc_name] = {
                    'silhouette': float(sil),
                    'n_windows': len(encoded_clean),
                }
            except Exception as e:
                sweep[scale_name][enc_name] = {'error': str(e)}

    return sweep


def run_exp423(args):
    """EXP-423: Scale-Dependent Encoding Adequacy Sweep.

    Systematically tests whether each encoding separates glucose patterns
    at each scale.  Produces an encoding × scale silhouette matrix.
    """
    print("\n" + "=" * 60)
    print("EXP-423: Encoding Adequacy Sweep")
    print("=" * 60)

    cfg = _get_config(args)
    patients = load_patients(args.patients_dir, max_patients=cfg['max_patients'],
                             patient_filter=getattr(args, 'patient', None))
    if not patients:
        return {'error': 'no patients loaded'}

    per_patient = {}
    for pat in patients:
        glucose = pat['df']['glucose'].values.astype(np.float64)
        isf = _extract_isf_scalar(pat['df'])
        pmean = float(np.nanmean(glucose))
        pstd = float(np.nanstd(glucose))
        sweep = encoding_adequacy_sweep(glucose, isf, pmean, pstd)
        per_patient[pat['name']] = sweep

        # Print summary row
        for scale_name in SCALES:
            row = sweep.get(scale_name, {})
            if isinstance(row, dict) and 'status' in row:
                continue
            best_enc = None
            best_sil = -1
            for enc_name in ENCODINGS:
                info = row.get(enc_name, {})
                s = info.get('silhouette', -1)
                if s > best_sil:
                    best_sil = s
                    best_enc = enc_name
            if best_enc:
                print(f"  {pat['name']} @ {scale_name}: best={best_enc}"
                      f" (sil={best_sil:.3f})")

    # Aggregate: mean silhouette per (scale, encoding) across patients
    aggregate = {}
    for scale_name in SCALES:
        aggregate[scale_name] = {}
        for enc_name in ENCODINGS:
            sils = []
            for p in per_patient:
                s_data = per_patient[p]
                if isinstance(s_data, dict) and scale_name in s_data:
                    entry = s_data[scale_name]
                    if isinstance(entry, dict) and enc_name in entry:
                        val = entry[enc_name]
                        if isinstance(val, dict) and 'silhouette' in val:
                            sils.append(val['silhouette'])
            if sils:
                aggregate[scale_name][enc_name] = {
                    'mean_silhouette': float(np.mean(sils)),
                    'std_silhouette': float(np.std(sils)),
                    'n_patients': len(sils),
                }

    results = {
        'experiment': 'EXP-423',
        'title': 'Scale-Dependent Encoding Adequacy Sweep',
        'principle': 'Principle 11: Representation Validation',
        'hypothesis': 'Each encoding has a scale at which it maximises '
                      'cluster separation (silhouette); using it outside '
                      'that scale is harmful.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'encodings': list(ENCODINGS.keys()),
        'scales': {k: v for k, v in SCALES.items()},
        'per_patient': per_patient,
        'aggregate': aggregate,
    }
    save_results(results, 'exp423_encoding_adequacy')
    return results


# ═══════════════════════════════════════════════════════════════════════════
# EXP-424: Augmentation as Symmetry Probe
# ═══════════════════════════════════════════════════════════════════════════

def time_warp(x, sigma=0.05):
    """Warp the time axis by a smooth random distortion.

    Generates a cumulative random walk to create a non-linear time mapping
    and re-samples the signal onto the original time grid.
    """
    n = len(x)
    tt = np.arange(n, dtype=np.float64)
    warp = np.cumsum(np.random.normal(1.0, sigma, n))
    warp = warp / warp[-1] * (n - 1)
    return np.interp(tt, warp, x)


def augment_time_shift(x):
    """Random circular shift ±30 min (±6 steps at 5-min resolution)."""
    return np.roll(x, np.random.randint(-6, 7), axis=0)


def augment_amplitude_scale(x):
    """Scale amplitude by uniform factor in [0.8, 1.2]."""
    return x * np.random.uniform(0.8, 1.2)


def augment_time_warp(x):
    """Apply smooth random time-warping (±5%)."""
    return time_warp(x, sigma=0.05)


def augment_jitter(x):
    """Add Gaussian noise (σ = 2 mg/dL)."""
    return x + np.random.normal(0, 2, x.shape)


AUGMENTATIONS = {
    'time_shift': {
        'fn': augment_time_shift,
        'tests': 'Time-translation invariance',
        'if_helps': 'Time features are leaking info',
        'if_hurts': 'Already time-invariant',
    },
    'amplitude_scale': {
        'fn': augment_amplitude_scale,
        'tests': 'ISF equivariance',
        'if_helps': 'ISF normalisation would help',
        'if_hurts': 'ISF variation already handled',
    },
    'time_warp': {
        'fn': augment_time_warp,
        'tests': 'Absorption symmetry',
        'if_helps': 'Response shapes need alignment',
        'if_hurts': 'Shapes are consistent',
    },
    'jitter': {
        'fn': augment_jitter,
        'tests': 'Noise robustness',
        'if_helps': 'Overfitting to noise',
        'if_hurts': 'Model is robust',
    },
}


def augmentation_probe(windows, labels, aug_name, aug_fn,
                       n_augmented_copies=2, random_state=42):
    """Measure whether an augmentation improves clustering quality.

    Augmented windows are appended to the original set.  If augmented
    clustering quality (silhouette) is higher, the original encoding
    under-represents the symmetry that the augmentation tests.

    Parameters
    ----------
    windows : np.ndarray, shape (N, T)
        Original encoded windows.
    labels : np.ndarray, shape (N,)
        Cluster labels from baseline k-means.
    aug_name : str
        Name of augmentation (for logging).
    aug_fn : callable
        Augmentation function (window → augmented window).
    n_augmented_copies : int
        Number of augmented copies per original window.
    random_state : int
        Seed for reproducibility.

    Returns
    -------
    dict with baseline_silhouette, augmented_silhouette, delta.
    """
    if not HAS_SKLEARN:
        return {'error': 'sklearn not available'}

    np.random.seed(random_state)
    n = len(windows)
    aug_windows = []
    for _ in range(n_augmented_copies):
        for w in windows:
            aug_windows.append(aug_fn(w.copy()))
    aug_windows = np.array(aug_windows)

    combined = np.vstack([windows, aug_windows])
    if combined.ndim == 1:
        combined = combined.reshape(-1, 1)
    elif combined.ndim > 2:
        combined = combined.reshape(len(combined), -1)

    valid = ~np.isnan(combined).any(axis=1)
    combined_clean = combined[valid]

    if len(combined_clean) < 50:
        return {'status': 'insufficient', 'n': len(combined_clean)}

    km = KMeans(n_clusters=5, n_init=3, random_state=42)
    labels_aug = km.fit_predict(combined_clean)

    sil_aug = silhouette_score(
        combined_clean, labels_aug,
        sample_size=min(1000, len(combined_clean)),
        random_state=42,
    )

    # Baseline silhouette (original windows only)
    orig_clean = windows[~np.isnan(windows).any(axis=1)] if windows.ndim > 1 \
        else windows[~np.isnan(windows)]
    if len(orig_clean) < 50:
        return {'status': 'insufficient_baseline'}

    km_base = KMeans(n_clusters=5, n_init=3, random_state=42)
    labels_base = km_base.fit_predict(
        orig_clean.reshape(len(orig_clean), -1) if orig_clean.ndim > 1
        else orig_clean.reshape(-1, 1))
    sil_base = silhouette_score(
        orig_clean.reshape(len(orig_clean), -1) if orig_clean.ndim > 1
        else orig_clean.reshape(-1, 1),
        labels_base,
        sample_size=min(1000, len(orig_clean)),
        random_state=42,
    )

    delta = float(sil_aug - sil_base)
    return {
        'augmentation': aug_name,
        'baseline_silhouette': float(sil_base),
        'augmented_silhouette': float(sil_aug),
        'delta': delta,
        'helps': delta > 0.01,
        'n_original': n,
        'n_augmented': len(combined_clean),
    }


def run_exp424(args):
    """EXP-424: Augmentation as Symmetry Probe.

    Each augmentation tests a specific symmetry.  If it helps clustering,
    the symmetry is under-represented in the encoding.
    """
    print("\n" + "=" * 60)
    print("EXP-424: Augmentation as Symmetry Probe")
    print("=" * 60)

    cfg = _get_config(args)
    patients = load_patients(args.patients_dir, max_patients=cfg['max_patients'],
                             patient_filter=getattr(args, 'patient', None))
    if not patients:
        return {'error': 'no patients loaded'}

    window_size = SCALES['6h']
    per_patient = {}

    for pat in patients:
        glucose = pat['df']['glucose'].values.astype(np.float64)
        windows = make_windows(glucose, window_size, stride=window_size // 2)
        if len(windows) < 50:
            per_patient[pat['name']] = {'status': 'insufficient_windows'}
            continue

        # Baseline clustering
        valid_mask = ~np.isnan(windows).any(axis=1)
        valid_windows = windows[valid_mask]
        if len(valid_windows) < 50:
            per_patient[pat['name']] = {'status': 'insufficient_valid_windows'}
            continue

        km = KMeans(n_clusters=5, n_init=3, random_state=42)
        labels = km.fit_predict(valid_windows)

        pat_results = {}
        for aug_name, aug_info in AUGMENTATIONS.items():
            result = augmentation_probe(
                valid_windows, labels, aug_name, aug_info['fn'])
            pat_results[aug_name] = result
            delta = result.get('delta', '?')
            helps = result.get('helps', False)
            indicator = '↑ under-represented' if helps else '→ adequate'
            print(f"  {pat['name']} {aug_name:>16s}: Δsil={delta:+.3f}"
                  f"  {indicator}"
                  if isinstance(delta, float)
                  else f"  {pat['name']} {aug_name}: {result.get('status', '?')}")

        per_patient[pat['name']] = pat_results

    # Aggregate
    aggregate = {}
    for aug_name in AUGMENTATIONS:
        deltas = []
        for p in per_patient:
            pdata = per_patient[p]
            if isinstance(pdata, dict) and aug_name in pdata:
                d = pdata[aug_name].get('delta')
                if d is not None and isinstance(d, (int, float)):
                    deltas.append(d)
        if deltas:
            aggregate[aug_name] = {
                'mean_delta': float(np.mean(deltas)),
                'std_delta': float(np.std(deltas)),
                'n_patients': len(deltas),
                'under_represented': float(np.mean(deltas)) > 0.01,
                'tests': AUGMENTATIONS[aug_name]['tests'],
            }

    results = {
        'experiment': 'EXP-424',
        'title': 'Augmentation as Symmetry Probe',
        'principle': 'Principle 11: Representation Validation',
        'hypothesis': 'Each augmentation tests a symmetry; if augmentation '
                      'helps clustering, the symmetry is under-represented.',
        'augmentations': {
            k: {kk: vv for kk, vv in v.items() if kk != 'fn'}
            for k, v in AUGMENTATIONS.items()
        },
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }
    save_results(results, 'exp424_augmentation_probe')
    return results


# ═══════════════════════════════════════════════════════════════════════════
# EXP-425: PK Residual Analysis (Encoding Quality Test)
# ═══════════════════════════════════════════════════════════════════════════

def pk_residual_analysis(glucose, iob, cob, isf, cr):
    """Analyse PK model residuals for systematic patterns.

    Computes the residual between actual glucose and a simple physics
    model (delta_bg = −delta_iob × ISF + delta_cob × ISF/CR), then
    checks for:
      - Autocorrelation at multiple lags (unmodeled dynamics)
      - Time-of-day conditional bias (circadian effects)

    Parameters
    ----------
    glucose, iob, cob : np.ndarray, shape (T,)
        Matching time-series.
    isf : float
        Insulin sensitivity factor.
    cr : float
        Carb ratio.

    Returns
    -------
    dict with residual stats, autocorrelation, dawn/night bias.
    """
    predicted = np.zeros_like(glucose)
    predicted[0] = glucose[0]
    for t in range(1, len(glucose)):
        delta_iob = iob[t - 1] - iob[t]
        delta_cob = cob[t - 1] - cob[t]
        insulin_effect = -delta_iob * isf
        carb_effect = delta_cob * (isf / max(cr, 0.1)) if cr > 0 else 0.0
        predicted[t] = predicted[t - 1] + insulin_effect + carb_effect

    residual = glucose - predicted
    valid = ~np.isnan(residual)
    r = residual[valid]

    if len(r) < 100:
        return {'status': 'insufficient_data', 'n': len(r)}

    # Autocorrelation at multiple lags
    acf = {}
    for lag in [1, 6, 12, 24, 72]:
        if len(r) > lag + 10:
            acf[f'lag_{lag * 5}min'] = float(
                np.corrcoef(r[:-lag], r[lag:])[0, 1])

    # Time-of-day conditional analysis
    n_steps_per_day = 288
    hour_residuals = {}
    valid_indices = np.flatnonzero(valid)
    for vi, t in enumerate(valid_indices):
        hour = (t % n_steps_per_day) // STEPS_PER_HOUR
        hour_residuals.setdefault(int(hour), []).append(float(r[vi]))

    # Dawn (4–6 AM) vs night (0–3 AM) bias
    dawn_vals = [v for h in [4, 5, 6]
                 for v in hour_residuals.get(h, [])]
    night_vals = [v for h in [0, 1, 2, 3]
                  for v in hour_residuals.get(h, [])]
    dawn_bias = float(np.mean(dawn_vals)) if dawn_vals else 0.0
    night_bias = float(np.mean(night_vals)) if night_vals else 0.0

    systematic = any(abs(v) > 0.3 for v in acf.values())

    return {
        'residual_mean': float(np.mean(r)),
        'residual_std': float(np.std(r)),
        'residual_rmse': float(np.sqrt(np.mean(r ** 2))),
        'autocorrelation': acf,
        'dawn_bias': dawn_bias,
        'night_bias': night_bias,
        'systematic_pattern': systematic,
        'n_valid': len(r),
    }


def run_exp425(args):
    """EXP-425: PK Residual Analysis.

    Checks whether physics-model residuals have systematic patterns —
    autocorrelation indicates unmodeled dynamics, dawn bias indicates
    circadian effects that the encoding misses.
    """
    print("\n" + "=" * 60)
    print("EXP-425: PK Residual Analysis")
    print("=" * 60)

    cfg = _get_config(args)
    patients = load_patients(args.patients_dir, max_patients=cfg['max_patients'],
                             patient_filter=getattr(args, 'patient', None))
    if not patients:
        return {'error': 'no patients loaded'}

    per_patient = {}
    for pat in patients:
        df = pat['df']
        glucose = df['glucose'].values.astype(np.float64)
        iob = df['iob'].values.astype(np.float64) if 'iob' in df.columns else np.zeros(len(df))
        cob = df['cob'].values.astype(np.float64) if 'cob' in df.columns else np.zeros(len(df))
        iob = np.nan_to_num(iob, nan=0.0)
        cob = np.nan_to_num(cob, nan=0.0)
        glucose = np.where(np.isnan(glucose), np.nanmean(glucose), glucose)
        isf = _extract_isf_scalar(df)
        cr = _extract_cr_scalar(df)

        result = pk_residual_analysis(glucose, iob, cob, isf, cr)
        per_patient[pat['name']] = result

        rmse = result.get('residual_rmse', '?')
        dawn = result.get('dawn_bias', 0)
        systematic = result.get('systematic_pattern', False)
        flag = '⚠️ SYSTEMATIC' if systematic else '✅ clean'
        dawn_flag = f' dawn={dawn:+.1f}' if abs(dawn) > 10 else ''
        print(f"  {pat['name']}: RMSE={rmse:.1f}  {flag}{dawn_flag}"
              if isinstance(rmse, (int, float))
              else f"  {pat['name']}: {result.get('status', '?')}")

    # Aggregate
    rmses = [per_patient[p]['residual_rmse']
             for p in per_patient if 'residual_rmse' in per_patient[p]]
    dawns = [per_patient[p]['dawn_bias']
             for p in per_patient if 'dawn_bias' in per_patient[p]]
    aggregate = {}
    if rmses:
        aggregate = {
            'mean_rmse': float(np.mean(rmses)),
            'std_rmse': float(np.std(rmses)),
            'mean_dawn_bias': float(np.mean(dawns)) if dawns else 0.0,
            'n_patients': len(rmses),
        }

    results = {
        'experiment': 'EXP-425',
        'title': 'PK Residual Analysis',
        'principle': 'Principle 11: Representation Validation',
        'hypothesis': 'If PK residuals have systematic autocorrelation or '
                      'dawn bias, there are unmodeled effects that need '
                      'their own encoding channels.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }
    save_results(results, 'exp425_pk_residual')
    return results


# ═══════════════════════════════════════════════════════════════════════════
# EXP-426: Event Recurrence Regularity Test
# ═══════════════════════════════════════════════════════════════════════════

def event_regularity_test(event_times_hours, event_days_of_week=None):
    """Quantify how regular a patient's event timing is.

    Clusters events by circular hour-of-day encoding.  For each cluster
    computes the temporal tightness (std in minutes).  A cluster is
    "regular" if std < 60 min.  The overall regularity score is the
    fraction of events in regular clusters.

    This is the feasibility test for E7 (proactive meal scheduling).

    Parameters
    ----------
    event_times_hours : np.ndarray
        Hour-of-day (0–24) for each event.
    event_days_of_week : np.ndarray or None
        Day-of-week (0–6).  Not used in clustering but stored for analysis.

    Returns
    -------
    dict with best_k, regularity_score, cluster details, scheduling_feasible.
    """
    if not HAS_SKLEARN:
        return {'error': 'sklearn not available'}

    if len(event_times_hours) < 10:
        return {'status': 'insufficient_events',
                'n_events': len(event_times_hours)}

    # Circular encoding
    hours = np.asarray(event_times_hours, dtype=np.float64)
    hour_sin = np.sin(2.0 * np.pi * hours / 24.0)
    hour_cos = np.cos(2.0 * np.pi * hours / 24.0)
    X = np.column_stack([hour_sin, hour_cos])

    best_k = 3
    best_score = -1.0
    results_by_k = {}

    for k in [2, 3, 4, 5]:
        if len(X) < k * 3:
            continue
        km = KMeans(n_clusters=k, n_init=5, random_state=42)
        labels = km.fit_predict(X)

        cluster_stats = []
        for c in range(k):
            mask = labels == c
            c_hours = hours[mask]
            if len(c_hours) == 0:
                continue

            # Circular mean and std
            mean_sin = np.mean(np.sin(2 * np.pi * c_hours / 24))
            mean_cos = np.mean(np.cos(2 * np.pi * c_hours / 24))
            mean_angle = np.arctan2(mean_sin, mean_cos)
            mean_hour = float((mean_angle * 24.0 / (2 * np.pi)) % 24.0)

            # Circular deviation
            diffs = np.abs(c_hours - mean_hour)
            diffs = np.minimum(diffs, 24.0 - diffs)
            std_hours = float(np.sqrt(np.mean(diffs ** 2)))

            cluster_stats.append({
                'mean_hour': mean_hour,
                'std_minutes': std_hours * 60.0,
                'n_events': int(mask.sum()),
                'regular': std_hours * 60.0 < 60.0,
            })

        if not cluster_stats:
            continue

        regularity = (sum(c['n_events'] for c in cluster_stats if c['regular'])
                      / len(X))
        results_by_k[k] = {
            'clusters': cluster_stats,
            'regularity_score': float(regularity),
        }

        if regularity > best_score:
            best_score = regularity
            best_k = k

    return {
        'best_k': best_k,
        'best_regularity': float(best_score),
        'results_by_k': results_by_k,
        'n_events': len(hours),
        'scheduling_feasible': best_score > 0.5,
    }


def run_exp426(args):
    """EXP-426: Event Recurrence Regularity Test.

    Quantifies how regular each patient's meal/event timing is — the
    feasibility test for E7 (proactive meal scheduling).  Patients with
    >50% of events in "regular" clusters are candidates for schedule-based
    encoding.
    """
    print("\n" + "=" * 60)
    print("EXP-426: Event Recurrence Regularity")
    print("=" * 60)

    cfg = _get_config(args)
    patients = load_patients(args.patients_dir, max_patients=cfg['max_patients'],
                             patient_filter=getattr(args, 'patient', None))
    if not patients:
        return {'error': 'no patients loaded'}

    per_patient = {}
    for pat in patients:
        df = pat['df']
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(df))
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))

        event_indices = np.where((bolus > 0) | (carbs > 0))[0]
        if len(event_indices) < 10:
            per_patient[pat['name']] = {
                'status': 'insufficient_events',
                'n_events': len(event_indices),
            }
            continue

        # Convert indices to hour-of-day
        hours_of_day = (event_indices % 288) / STEPS_PER_HOUR
        days_of_week = (event_indices // 288) % 7

        result = event_regularity_test(hours_of_day, days_of_week)
        per_patient[pat['name']] = result

        reg = result.get('best_regularity', 0)
        feasible = result.get('scheduling_feasible', False)
        k = result.get('best_k', '?')
        flag = '✅ feasible' if feasible else '❌ irregular'
        print(f"  {pat['name']}: {reg:.0%} regular (k={k})  {flag}")

    # Aggregate
    regs = [per_patient[p]['best_regularity']
            for p in per_patient if 'best_regularity' in per_patient[p]]
    aggregate = {}
    if regs:
        aggregate = {
            'mean_regularity': float(np.mean(regs)),
            'std_regularity': float(np.std(regs)),
            'n_patients': len(regs),
            'fraction_feasible': float(np.mean([r > 0.5 for r in regs])),
        }

    results = {
        'experiment': 'EXP-426',
        'title': 'Event Recurrence Regularity',
        'principle': 'Principle 11: Representation Validation',
        'hypothesis': 'Most patients have >50% of meal events in regular '
                      'temporal clusters (std < 60 min), supporting '
                      'schedule-based encoding (E7).',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }
    save_results(results, 'exp426_event_regularity')
    return results


# ═══════════════════════════════════════════════════════════════════════════
# Experiment Registry & Symmetry Scorecard
# ═══════════════════════════════════════════════════════════════════════════

EXPERIMENTS = {
    '419': run_exp419,
    '420': run_exp420,
    '421': run_exp421,
    '422': run_exp422,
    '423': run_exp423,
    '424': run_exp424,
    '425': run_exp425,
    '426': run_exp426,
}


def symmetry_scorecard(all_results):
    """Print a summary scorecard of all symmetry property test results.

    Reads the result dicts returned by each run_expNNN and produces a
    table showing PASS / FAIL / WEAK for each property × scale.
    """
    lines = []
    sep = '═' * 66
    thin = '─' * 66

    lines.append(f'╔{sep}╗')
    lines.append(f'║{"ENCODING VALIDATION SCORECARD":^66s}║')
    lines.append(f'╠{sep}╣')
    lines.append(f'║ {"Property":<30s}│ {"Scale":<6s}│ {"Status":<8s}│ {"Evidence":<15s}║')
    lines.append(f'╠{"═" * 31}╪{"═" * 7}╪{"═" * 9}╪{"═" * 16}╣')

    # EXP-419: Time-Translation Invariance
    r419 = all_results.get('419', {})
    agg419 = r419.get('aggregate', {})
    for scale_name in ('2h', '6h', '12h', '24h'):
        info = agg419.get(scale_name, {})
        mean_r = info.get('mean_spearman_r')
        if mean_r is not None:
            inv = info.get('time_invariant', False)
            if inv:
                status = '✅ PASS'
            elif abs(mean_r) < 0.3:
                status = '⚠️ WEAK'
            else:
                status = '❌ FAIL'
            evidence = f'r={mean_r:.2f}'
        else:
            status = '— N/A '
            evidence = ''
        lines.append(
            f'║ {"Time-translation invariance":<30s}│ {scale_name:<6s}'
            f'│ {status:<8s}│ {evidence:<15s}║')

    lines.append(f'╟{thin}╢')

    # EXP-420: Absorption Symmetry
    r420 = all_results.get('420', {})
    agg420 = r420.get('aggregate', {})
    for etype in ('bolus', 'carbs', 'mixed'):
        info = agg420.get(etype, {})
        ratio = info.get('mean_ratio')
        if ratio is not None:
            sym = info.get('symmetric', False)
            if sym:
                status = '✅ PASS'
            elif 0.5 < ratio < 1.5:
                status = '⚠️ WEAK'
            else:
                status = '❌ FAIL'
            evidence = f'ratio={ratio:.2f}'
        else:
            status = '— N/A '
            evidence = ''
        lines.append(
            f'║ {"Absorption symmetry":<30s}│ {etype:<6s}'
            f'│ {status:<8s}│ {evidence:<15s}║')

    lines.append(f'╟{thin}╢')

    # EXP-421: Conservation
    r421 = all_results.get('421', {})
    agg421 = r421.get('aggregate', {})
    mean_int = agg421.get('mean_integral')
    if mean_int is not None:
        holds = agg421.get('conservation_holds', False)
        if holds:
            status = '✅ PASS'
        elif abs(mean_int) < 100:
            status = '⚠️ BIAS'
        else:
            status = '❌ FAIL'
        evidence = f'μ={mean_int:+.0f} mg·h'
    else:
        status = '— N/A '
        evidence = ''
    lines.append(
        f'║ {"Conservation":<30s}│ {"12h":<6s}'
        f'│ {status:<8s}│ {evidence:<15s}║')

    lines.append(f'╟{thin}╢')

    # EXP-422: ISF Equivariance
    r422 = all_results.get('422', {})
    eq_result = r422.get('result', {})
    delta = eq_result.get('delta')
    if delta is not None:
        confirmed = eq_result.get('equivariance_confirmed', False)
        status = '✅ PASS' if confirmed else '❌ FAIL'
        evidence = f'Δsim={delta:+.3f}'
    else:
        status = '— N/A '
        evidence = ''
    lines.append(
        f'║ {"ISF equivariance":<30s}│ {"cross":<6s}'
        f'│ {status:<8s}│ {evidence:<15s}║')

    lines.append(f'╟{thin}╢')

    # EXP-426: Event Regularity
    r426 = all_results.get('426', {})
    agg426 = r426.get('aggregate', {})
    mean_reg = agg426.get('mean_regularity')
    if mean_reg is not None:
        feasible = agg426.get('fraction_feasible', 0)
        if mean_reg > 0.5:
            status = '✅ PASS'
        elif mean_reg > 0.3:
            status = '⚠️ WEAK'
        else:
            status = '❌ FAIL'
        evidence = f'{mean_reg:.0%} regular'
    else:
        status = '— N/A '
        evidence = ''
    lines.append(
        f'║ {"Event regularity":<30s}│ {"meals":<6s}'
        f'│ {status:<8s}│ {evidence:<15s}║')

    lines.append(f'╟{thin}╢')

    # EXP-425: PK Residual
    r425 = all_results.get('425', {})
    agg425 = r425.get('aggregate', {})
    dawn = agg425.get('mean_dawn_bias')
    rmse = agg425.get('mean_rmse')
    if dawn is not None and rmse is not None:
        if abs(dawn) > 15:
            status = '⚠️ DAWN'
        elif rmse < 30:
            status = '✅ PASS'
        else:
            status = '⚠️ HIGH'
        evidence = f'bias={dawn:+.0f}mg'
    else:
        status = '— N/A '
        evidence = ''
    lines.append(
        f'║ {"PK residual patterns":<30s}│ {"12h":<6s}'
        f'│ {status:<8s}│ {evidence:<15s}║')

    lines.append(f'╚{sep}╝')

    scorecard = '\n'.join(lines)
    print('\n' + scorecard)
    return scorecard


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _get_config(args):
    """Return config dict driven by --quick flag."""
    if getattr(args, 'quick', False):
        return dict(max_patients=QUICK_PATIENTS)
    return dict(max_patients=None)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='EXP-419-426: Representation Validation — '
                    'Principle 11 property tests for feature engineering.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Experiments (property tests, not task metrics):
  419  Time-Translation Invariance (multi-scale formal proof)
  420  Absorption Envelope Symmetry (bolus vs carb response shape)
  421  Glucose Conservation (physics model completeness)
  422  ISF Equivariance (cross-patient normalisation test)
  423  Encoding Adequacy Sweep (scale × encoding silhouette matrix)
  424  Augmentation as Symmetry Probe (which symmetries are missing?)
  425  PK Residual Analysis (autocorrelation & dawn bias)
  426  Event Recurrence Regularity (schedule feasibility for E7)

Examples:
  python tools/cgmencode/exp_encoding_validation.py -e all --quick
  python tools/cgmencode/exp_encoding_validation.py -e 419 420 --patient patient_001
  python tools/cgmencode/exp_encoding_validation.py --summary
""")
    parser.add_argument('--experiment', '-e', nargs='+', default=['all'],
                        help='Experiment number(s) or "all" (default: all)')
    parser.add_argument('--quick', '-q', action='store_true',
                        help='Quick mode: fewer patients')
    parser.add_argument('--patient', '-p', default=None,
                        help='Run for a single patient directory name')
    parser.add_argument('--patients-dir',
                        default='externals/ns-data/patients',
                        help='Path to patient data directory')
    parser.add_argument('--summary', '-s', action='store_true',
                        help='Load saved results and print scorecard only')
    args = parser.parse_args()

    # --summary: load existing JSON results and print scorecard
    if args.summary:
        all_results = {}
        for eid in EXPERIMENTS:
            # Try to load each experiment's result file
            patterns = [
                RESULTS_DIR / f'exp{eid}_*.json',
            ]
            import glob as globmod
            for pat in patterns:
                matches = globmod.glob(str(pat))
                for m in matches:
                    try:
                        with open(m) as f:
                            all_results[eid] = json.load(f)
                    except Exception:
                        pass
        symmetry_scorecard(all_results)
        return all_results

    # Normal run
    if 'all' in args.experiment:
        exp_ids = sorted(EXPERIMENTS.keys())
    else:
        exp_ids = [e.strip() for e in args.experiment]

    print(f"Encoding Validation — {len(exp_ids)} property tests to run")
    print(f"  Quick: {args.quick}, Patient: {args.patient or 'all'}")
    t0 = time.time()

    all_results = {}
    for eid in exp_ids:
        if eid not in EXPERIMENTS:
            print(f"\n  Unknown experiment: {eid}")
            continue
        try:
            result = EXPERIMENTS[eid](args)
            all_results[eid] = result
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"\n  EXP-{eid} failed: {exc}")
            all_results[eid] = {'error': str(exc)}

    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"All done in {elapsed:.0f}s — {len(all_results)} property tests completed.")

    # Print scorecard
    symmetry_scorecard(all_results)

    return all_results


if __name__ == '__main__':
    main()
