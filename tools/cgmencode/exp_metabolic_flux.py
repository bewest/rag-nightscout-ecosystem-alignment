#!/usr/bin/env python3
"""
EXP-435 through EXP-440: Metabolic Flux Channel Experiments

Insight: EXP-421 showed glucose conservation (net integral ≈ 0), meaning
insulin and carb effects balance out.  But even when NET glucose change is
zero, the ABSOLUTE metabolic activity is large — carbs absorbing and insulin
acting simultaneously.  The phase difference between carb absorption (peaks
15-30 min) and insulin action (peaks 55-90 min) creates a structural
temporal signature of meals, corrections, and metabolic events that exists
regardless of whether glucose moves.

Analogy: In an AC circuit, voltage may stay flat, but current is flowing.
Metabolic flux = |carb_effect| + |insulin_effect| — the "current" even when
the "voltage" (glucose) is stable.

Experiment registry:
    EXP-435: Metabolic Flux Signal Characterization
             Compute flux channels, characterize signal quality during
             meals vs non-meals vs corrections at multiple time scales.
    EXP-436: Phase Lag Measurement
             Measure time offset between carb_effect peak and
             insulin_effect peak for isolated events.
    EXP-437: Flux Symmetry Test
             Test if metabolic flux envelopes are more symmetric than
             raw glucose envelopes (counterpoint to EXP-420).
    EXP-438: Flux as Event Discriminator
             Test separability of meal/correction/stable states using
             flux features vs raw glucose features.
    EXP-439: Flux Signal Across Time Scales
             Test flux signal-to-noise ratio at 2h, 6h, 12h, 24h.
    EXP-440: Flux + Positional Encoding Interaction
             Test if positional encoding + flux channels together show
             better event discrimination than either alone.  Tests whether
             full DIA arcs in history improve flux utility.

Usage:
    python tools/cgmencode/exp_metabolic_flux.py -e all --quick
    python tools/cgmencode/exp_metabolic_flux.py -e 435 436
    python tools/cgmencode/exp_metabolic_flux.py --summary
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

try:
    from scipy.stats import spearmanr, mannwhitneyu
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    from sklearn.metrics import silhouette_score, roc_auc_score
    from sklearn.cluster import KMeans
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

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
# Data loading (same pattern as exp_encoding_validation.py)
# ---------------------------------------------------------------------------

def find_patient_dirs(patients_dir):
    base = Path(patients_dir)
    return sorted([d for d in base.iterdir() if d.is_dir()])


def load_patients(patients_dir, max_patients=None, patient_filter=None,
                  verbose=True):
    """Load per-patient DataFrames + PK features."""
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
    stride = stride or (window_size // 2)
    windows = []
    for start in range(0, len(arr) - window_size + 1, stride):
        windows.append(arr[start:start + window_size])
    if len(windows) == 0:
        return np.empty((0, window_size) + arr.shape[1:], dtype=arr.dtype)
    return np.stack(windows)


def save_results(results, filename):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f'{filename}.json'
    with open(path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  → Saved {path}")


def _extract_isf_scalar(df):
    """Extract scalar ISF in mg/dL/U, with mmol/L auto-detection."""
    isf_sched = df.attrs.get('isf_schedule', [])
    if isf_sched:
        vals = [entry.get('value', entry.get('sensitivity', 40))
                for entry in isf_sched]
        isf = float(np.median(vals))
    else:
        isf = 40.0
    if isf < 15:
        isf *= 18.0182
    return isf


def _extract_cr_scalar(df):
    """Extract scalar CR from schedule."""
    cr_sched = df.attrs.get('cr_schedule', [])
    if cr_sched:
        vals = [entry.get('value', entry.get('carbratio', 10))
                for entry in cr_sched]
        return float(np.median(vals))
    return 10.0


# ---------------------------------------------------------------------------
# Core: Compute metabolic flux channels
# ---------------------------------------------------------------------------

def compute_metabolic_flux(df, isf=None, cr=None):
    """Compute per-timestep metabolic flux channels from IOB/COB deltas.

    Returns dict with:
        insulin_effect: (N,) mg/dL glucose change from insulin per step
        carb_effect:    (N,) mg/dL glucose change from carbs per step
        metabolic_activity: (N,) |insulin_effect| + |carb_effect| — total flux
        net_effect:     (N,) signed net (= carb_effect + insulin_effect)
        flux_ratio:     (N,) carb_effect / (|insulin_effect| + eps) — meal signal
    """
    if isf is None:
        isf = _extract_isf_scalar(df)
    if cr is None:
        cr = _extract_cr_scalar(df)

    iob = np.nan_to_num(df['iob'].values.astype(np.float64), nan=0.0)
    cob = np.nan_to_num(df['cob'].values.astype(np.float64), nan=0.0)

    # Delta IOB/COB (same physics as EXP-421)
    delta_iob = np.zeros_like(iob)
    delta_cob = np.zeros_like(cob)
    delta_iob[1:] = iob[:-1] - iob[1:]   # positive = insulin being absorbed
    delta_cob[1:] = cob[:-1] - cob[1:]   # positive = carbs being absorbed

    # Per-step glucose effects
    insulin_effect = -delta_iob * isf          # negative = lowers glucose
    carb_effect = delta_cob * (isf / cr) if cr > 0 else np.zeros_like(delta_cob)

    # Metabolic activity: total flux regardless of direction
    metabolic_activity = np.abs(insulin_effect) + np.abs(carb_effect)

    # Net effect (signed — same as physics model step)
    net_effect = insulin_effect + carb_effect

    # Flux ratio: how much is carbs vs insulin driving things
    eps = 1e-6
    flux_ratio = np.abs(carb_effect) / (np.abs(insulin_effect) + eps)

    return {
        'insulin_effect': insulin_effect,
        'carb_effect': carb_effect,
        'metabolic_activity': metabolic_activity,
        'net_effect': net_effect,
        'flux_ratio': flux_ratio,
    }


def classify_windows_by_event(df, window_size, stride=None):
    """Label each window as 'meal', 'correction', or 'stable'.

    meal: any carb entry > 5g in window
    correction: any bolus > 0.3U in window AND no carbs > 5g
    stable: neither meal nor correction
    """
    stride = stride or (window_size // 2)
    bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
    carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

    labels = []
    for start in range(0, len(df) - window_size + 1, stride):
        w_carbs = carbs[start:start + window_size]
        w_bolus = bolus[start:start + window_size]
        has_meal = np.any(w_carbs > 5.0)
        has_correction = np.any(w_bolus > 0.3)
        if has_meal:
            labels.append('meal')
        elif has_correction:
            labels.append('correction')
        else:
            labels.append('stable')
    return labels


# ═══════════════════════════════════════════════════════════════════════════
# EXP-435: Metabolic Flux Signal Characterization
# ═══════════════════════════════════════════════════════════════════════════

def flux_signal_characterization(flux, labels, patient_name):
    """Characterize flux signal quality by event type."""
    activity = flux['metabolic_activity']
    ratio = flux['flux_ratio']
    net = flux['net_effect']

    # Per-event-type statistics
    event_stats = {}
    for etype in ('meal', 'correction', 'stable'):
        mask = np.array([l == etype for l in labels])
        if mask.sum() == 0:
            continue
        # Mean activity in windows of this type
        event_stats[etype] = {
            'n_windows': int(mask.sum()),
        }

    return event_stats


def run_exp435(args):
    """EXP-435: Metabolic Flux Signal Characterization."""
    print("\n══════ EXP-435: Metabolic Flux Signal Characterization ══════")
    cfg = _get_config(args)
    patients = load_patients(args.patients_dir, verbose=True, **cfg)

    per_patient = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        isf = _extract_isf_scalar(df)
        cr = _extract_cr_scalar(df)
        flux = compute_metabolic_flux(df, isf, cr)

        activity = flux['metabolic_activity']
        ratio = flux['flux_ratio']
        net = flux['net_effect']

        # Overall signal statistics
        stats = {
            'isf': isf, 'cr': cr,
            'activity_mean': float(np.mean(activity)),
            'activity_std': float(np.std(activity)),
            'activity_p95': float(np.percentile(activity, 95)),
            'activity_p99': float(np.percentile(activity, 99)),
            'activity_frac_nonzero': float((activity > 0.1).mean()),
            'net_mean': float(np.mean(net)),
            'net_std': float(np.std(net)),
        }

        # Per-scale analysis
        scale_stats = {}
        for scale_name, wsize in SCALES.items():
            labels = classify_windows_by_event(df, wsize)
            n_labels = len(labels)

            # Make flux windows
            act_wins = make_windows(activity, wsize)
            ratio_wins = make_windows(ratio, wsize)
            net_wins = make_windows(net, wsize)

            n_wins = min(len(act_wins), n_labels)
            act_wins = act_wins[:n_wins]
            ratio_wins = ratio_wins[:n_wins]
            net_wins = net_wins[:n_wins]
            labs = labels[:n_wins]

            # Per-event-type mean activity
            per_etype = {}
            for etype in ('meal', 'correction', 'stable'):
                mask = [i for i, l in enumerate(labs) if l == etype]
                if len(mask) < 3:
                    continue
                mask_idx = np.array(mask)
                etype_act = act_wins[mask_idx]
                etype_net = net_wins[mask_idx]
                per_etype[etype] = {
                    'n': len(mask),
                    'mean_activity': float(np.mean(etype_act)),
                    'peak_activity': float(np.mean(np.max(etype_act, axis=1))),
                    'mean_net': float(np.mean(etype_net)),
                    'std_net': float(np.std(np.mean(etype_net, axis=1))),
                }

            # Discrimination: can activity distinguish meal from stable?
            meal_mask = [i for i, l in enumerate(labs) if l == 'meal']
            stable_mask = [i for i, l in enumerate(labs) if l == 'stable']
            discrimination = None
            if len(meal_mask) >= 5 and len(stable_mask) >= 5:
                meal_mean_act = np.mean(act_wins[meal_mask], axis=1)
                stable_mean_act = np.mean(act_wins[stable_mask], axis=1)
                # Effect size (Cohen's d)
                pooled_std = np.sqrt((np.var(meal_mean_act) + np.var(stable_mean_act)) / 2)
                cohens_d = (np.mean(meal_mean_act) - np.mean(stable_mean_act)) / max(pooled_std, 1e-6)
                # Mann-Whitney U
                if HAS_SCIPY:
                    stat, pval = mannwhitneyu(meal_mean_act, stable_mean_act, alternative='greater')
                else:
                    pval = -1.0
                discrimination = {
                    'cohens_d': float(cohens_d),
                    'p_value': float(pval),
                    'meal_mean': float(np.mean(meal_mean_act)),
                    'stable_mean': float(np.mean(stable_mean_act)),
                    'meal_peak_mean': float(np.mean(np.max(act_wins[meal_mask], axis=1))),
                    'stable_peak_mean': float(np.mean(np.max(act_wins[stable_mask], axis=1))),
                }

            scale_stats[scale_name] = {
                'n_windows': n_wins,
                'event_counts': {e: len([l for l in labs if l == e]) for e in ('meal', 'correction', 'stable')},
                'per_event_type': per_etype,
                'discrimination': discrimination,
            }

        per_patient[name] = {'stats': stats, 'scales': scale_stats}
        print(f"  {name}: activity_mean={stats['activity_mean']:.2f}, "
              f"p95={stats['activity_p95']:.2f}, "
              f"frac_active={stats['activity_frac_nonzero']:.2%}")

    # Aggregate
    aggregate = {}
    for scale_name in SCALES:
        ds = [per_patient[p]['scales'].get(scale_name, {}).get('discrimination')
              for p in per_patient
              if per_patient[p]['scales'].get(scale_name, {}).get('discrimination')]
        if ds:
            aggregate[scale_name] = {
                'mean_cohens_d': float(np.mean([d['cohens_d'] for d in ds])),
                'mean_p_value': float(np.mean([d['p_value'] for d in ds])),
                'n_patients': len(ds),
                'all_significant': all(d['p_value'] < 0.05 for d in ds),
            }

    results = {
        'experiment': 'EXP-435',
        'title': 'Metabolic Flux Signal Characterization',
        'hypothesis': 'Metabolic activity (|insulin_effect| + |carb_effect|) '
                      'discriminates meal/correction/stable states even when '
                      'net glucose change ≈ 0.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }
    save_results(results, 'exp435_metabolic_flux_signal')
    return results


# ═══════════════════════════════════════════════════════════════════════════
# EXP-436: Phase Lag Measurement
# ═══════════════════════════════════════════════════════════════════════════

def run_exp436(args):
    """EXP-436: Measure phase lag between carb and insulin effects."""
    print("\n══════ EXP-436: Phase Lag Measurement ══════")
    cfg = _get_config(args)
    patients = load_patients(args.patients_dir, verbose=True, **cfg)

    per_patient = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        isf = _extract_isf_scalar(df)
        cr = _extract_cr_scalar(df)
        flux = compute_metabolic_flux(df, isf, cr)

        carb_eff = np.abs(flux['carb_effect'])
        ins_eff = np.abs(flux['insulin_effect'])
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

        # Find meal events (carbs > 10g)
        meal_idx = np.where(carbs > 10)[0]

        # Filter: need at least 6h (72 steps) after event
        meal_idx = meal_idx[meal_idx < len(df) - 72]
        # Filter: no other meal within 3h before
        filtered = []
        for idx in meal_idx:
            lookback = max(0, idx - 36)
            if not np.any(carbs[lookback:idx] > 5):
                filtered.append(idx)
        meal_idx = np.array(filtered) if filtered else np.array([], dtype=int)

        phase_lags = []
        for idx in meal_idx:
            window = slice(idx, idx + 72)  # 6h window
            c_win = carb_eff[window]
            i_win = ins_eff[window]

            if c_win.max() < 0.1 or i_win.max() < 0.1:
                continue

            # Find peak times
            carb_peak_step = np.argmax(c_win)
            ins_peak_step = np.argmax(i_win)

            # Phase lag in minutes (5 min per step)
            lag_min = (ins_peak_step - carb_peak_step) * 5
            phase_lags.append({
                'meal_idx': int(idx),
                'carb_peak_min': int(carb_peak_step * 5),
                'insulin_peak_min': int(ins_peak_step * 5),
                'lag_min': int(lag_min),
                'carb_g': float(carbs[idx]),
            })

        lag_values = [p['lag_min'] for p in phase_lags]
        patient_result = {
            'n_meals': len(phase_lags),
            'events': phase_lags[:20],  # cap for JSON size
        }
        if lag_values:
            patient_result.update({
                'mean_lag_min': float(np.mean(lag_values)),
                'median_lag_min': float(np.median(lag_values)),
                'std_lag_min': float(np.std(lag_values)),
                'min_lag_min': float(np.min(lag_values)),
                'max_lag_min': float(np.max(lag_values)),
                'frac_positive': float(np.mean([l > 0 for l in lag_values])),
            })

        per_patient[name] = patient_result
        n = len(phase_lags)
        mean_lag = np.mean(lag_values) if lag_values else float('nan')
        print(f"  {name}: {n} isolated meals, mean lag={mean_lag:.0f} min")

    # Aggregate
    all_lags = []
    for p in per_patient.values():
        all_lags.extend([e['lag_min'] for e in p.get('events', [])])

    aggregate = {}
    if all_lags:
        aggregate = {
            'total_events': len(all_lags),
            'mean_lag_min': float(np.mean(all_lags)),
            'median_lag_min': float(np.median(all_lags)),
            'std_lag_min': float(np.std(all_lags)),
            'frac_insulin_after_carb': float(np.mean([l > 0 for l in all_lags])),
            'frac_prebolus': float(np.mean([l < -10 for l in all_lags])),
        }

    results = {
        'experiment': 'EXP-436',
        'title': 'Phase Lag Measurement',
        'hypothesis': 'Carb absorption peaks 30-60 min before insulin peak '
                      'effect. This phase lag is a structural meal signature. '
                      'Pre-bolus events show negative lag.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }
    save_results(results, 'exp436_phase_lag')
    return results


# ═══════════════════════════════════════════════════════════════════════════
# EXP-437: Flux Symmetry Test
# ═══════════════════════════════════════════════════════════════════════════

def run_exp437(args):
    """EXP-437: Test if metabolic flux envelopes are more symmetric than glucose."""
    print("\n══════ EXP-437: Flux Symmetry Test ══════")
    cfg = _get_config(args)
    patients = load_patients(args.patients_dir, verbose=True, **cfg)

    per_patient = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        isf = _extract_isf_scalar(df)
        cr = _extract_cr_scalar(df)
        flux = compute_metabolic_flux(df, isf, cr)

        glucose = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=120.0)
        activity = flux['metabolic_activity']
        bolus = np.nan_to_num(df['bolus'].values.astype(np.float64), nan=0.0)
        carbs = np.nan_to_num(df['carbs'].values.astype(np.float64), nan=0.0)

        # Find isolated events (bolus or carbs, nothing within ±3h)
        events = np.where((bolus > 0.3) | (carbs > 5))[0]
        events = events[(events > 12) & (events < len(df) - 60)]

        isolated = []
        for idx in events:
            lookback = max(0, idx - 36)
            lookahead = min(len(df), idx + 36)
            others = events[(events >= lookback) & (events < lookahead) & (events != idx)]
            if len(others) == 0:
                isolated.append(idx)

        glucose_ratios = []
        flux_ratios = []

        for idx in isolated:
            # 1h before to 5h after
            start = max(0, idx - 12)
            end = min(len(df), idx + 60)

            g_win = glucose[start:end]
            a_win = activity[start:end]

            if len(g_win) < 20:
                continue

            # Glucose symmetry (same as EXP-420)
            g_baseline = np.mean(g_win[:6]) if len(g_win) >= 6 else g_win[0]
            g_dev = np.abs(g_win - g_baseline)
            g_peak = np.argmax(g_dev)
            if g_peak < 2 or g_peak > len(g_dev) - 3:
                continue
            g_pre = np.trapezoid(g_dev[:g_peak + 1])
            g_post = np.trapezoid(g_dev[g_peak:])
            if g_post > 0.1:
                glucose_ratios.append(g_pre / g_post)

            # Flux symmetry — same analysis on metabolic activity
            a_peak = np.argmax(a_win)
            if a_peak < 2 or a_peak > len(a_win) - 3:
                continue
            a_pre = np.trapezoid(a_win[:a_peak + 1])
            a_post = np.trapezoid(a_win[a_peak:])
            if a_post > 0.01:
                flux_ratios.append(a_pre / a_post)

        patient_result = {
            'n_isolated_events': len(isolated),
            'n_glucose_ratios': len(glucose_ratios),
            'n_flux_ratios': len(flux_ratios),
        }
        if glucose_ratios:
            patient_result['glucose_symmetry_ratio'] = float(np.mean(glucose_ratios))
            patient_result['glucose_symmetry_std'] = float(np.std(glucose_ratios))
        if flux_ratios:
            patient_result['flux_symmetry_ratio'] = float(np.mean(flux_ratios))
            patient_result['flux_symmetry_std'] = float(np.std(flux_ratios))

        # Is flux more symmetric? (closer to 1.0)
        if glucose_ratios and flux_ratios:
            g_dist = abs(np.mean(glucose_ratios) - 1.0)
            f_dist = abs(np.mean(flux_ratios) - 1.0)
            patient_result['flux_more_symmetric'] = bool(f_dist < g_dist)
            patient_result['symmetry_improvement'] = float(g_dist - f_dist)

        per_patient[name] = patient_result
        gr = np.mean(glucose_ratios) if glucose_ratios else float('nan')
        fr = np.mean(flux_ratios) if flux_ratios else float('nan')
        print(f"  {name}: glucose_ratio={gr:.2f}, flux_ratio={fr:.2f}, "
              f"n_events={len(isolated)}")

    # Aggregate
    g_ratios_all = [per_patient[p].get('glucose_symmetry_ratio')
                    for p in per_patient
                    if per_patient[p].get('glucose_symmetry_ratio') is not None]
    f_ratios_all = [per_patient[p].get('flux_symmetry_ratio')
                    for p in per_patient
                    if per_patient[p].get('flux_symmetry_ratio') is not None]
    improvements = [per_patient[p].get('symmetry_improvement')
                    for p in per_patient
                    if per_patient[p].get('symmetry_improvement') is not None]

    aggregate = {}
    if g_ratios_all and f_ratios_all:
        aggregate = {
            'mean_glucose_ratio': float(np.mean(g_ratios_all)),
            'mean_flux_ratio': float(np.mean(f_ratios_all)),
            'flux_more_symmetric_count': sum(1 for i in improvements if i > 0),
            'total_compared': len(improvements),
            'mean_improvement': float(np.mean(improvements)) if improvements else 0.0,
        }

    results = {
        'experiment': 'EXP-437',
        'title': 'Flux Symmetry Test',
        'hypothesis': 'Metabolic flux envelopes are more symmetric around '
                      'their peak than raw glucose envelopes, because flux '
                      'captures the metabolic process directly while glucose '
                      'shape is distorted by AID corrections (EXP-420).',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }
    save_results(results, 'exp437_flux_symmetry')
    return results


# ═══════════════════════════════════════════════════════════════════════════
# EXP-438: Flux as Event Discriminator
# ═══════════════════════════════════════════════════════════════════════════

def run_exp438(args):
    """EXP-438: Test separability of event types using flux vs glucose features."""
    print("\n══════ EXP-438: Flux as Event Discriminator ══════")
    if not HAS_SKLEARN:
        print("  SKIP: scikit-learn not available")
        return {'experiment': 'EXP-438', 'status': 'skipped'}

    cfg = _get_config(args)
    patients = load_patients(args.patients_dir, verbose=True, **cfg)

    per_patient = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        isf = _extract_isf_scalar(df)
        cr = _extract_cr_scalar(df)
        flux = compute_metabolic_flux(df, isf, cr)
        glucose = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=120.0)
        activity = flux['metabolic_activity']
        net = flux['net_effect']
        ratio = flux['flux_ratio']

        scale_results = {}
        for scale_name, wsize in SCALES.items():
            labels = classify_windows_by_event(df, wsize)

            # Build feature windows
            g_wins = make_windows(glucose / GLUCOSE_SCALE, wsize)
            act_wins = make_windows(activity, wsize)
            net_wins = make_windows(net, wsize)
            ratio_wins = make_windows(ratio, wsize)

            n_wins = min(len(g_wins), len(act_wins), len(labels))
            g_wins = g_wins[:n_wins]
            act_wins = act_wins[:n_wins]
            net_wins = net_wins[:n_wins]
            ratio_wins = ratio_wins[:n_wins]
            labs = labels[:n_wins]

            # Need at least 2 event types with ≥ 5 windows
            label_counts = {e: sum(1 for l in labs if l == e) for e in ('meal', 'correction', 'stable')}
            active_types = [e for e, c in label_counts.items() if c >= 5]
            if len(active_types) < 2:
                continue

            # Filter to active types
            mask = [i for i, l in enumerate(labs) if l in active_types]
            mask = np.array(mask)
            filtered_labs = [labs[i] for i in mask]
            label_map = {l: i for i, l in enumerate(sorted(set(filtered_labs)))}
            y = np.array([label_map[l] for l in filtered_labs])

            # Feature sets to compare
            # 1. Glucose only: summary stats per window
            g_feats = np.column_stack([
                np.mean(g_wins[mask], axis=1),
                np.std(g_wins[mask], axis=1),
                np.max(g_wins[mask], axis=1) - np.min(g_wins[mask], axis=1),
                np.diff(g_wins[mask][:, ::3], axis=1).std(axis=1),  # derivative std
            ])

            # 2. Flux features: summary stats per window
            f_feats = np.column_stack([
                np.mean(act_wins[mask], axis=1),
                np.max(act_wins[mask], axis=1),
                np.std(act_wins[mask], axis=1),
                np.mean(net_wins[mask], axis=1),
                np.mean(ratio_wins[mask], axis=1),
            ])

            # 3. Combined
            c_feats = np.column_stack([g_feats, f_feats])

            # Evaluate with silhouette score (unsupervised quality)
            def sil_score(X, y_labels):
                if len(set(y_labels)) < 2 or len(y_labels) < 10:
                    return float('nan')
                try:
                    return float(silhouette_score(X, y_labels))
                except Exception:
                    return float('nan')

            sil_glucose = sil_score(g_feats, y)
            sil_flux = sil_score(f_feats, y)
            sil_combined = sil_score(c_feats, y)

            # Binary AUC (meal vs non-meal) if possible
            auc_glucose = float('nan')
            auc_flux = float('nan')
            auc_combined = float('nan')
            binary_y = np.array([1 if l == 'meal' else 0 for l in filtered_labs])
            if binary_y.sum() >= 5 and (1 - binary_y).sum() >= 5:
                try:
                    # Use mean activity as a simple 1D score
                    auc_glucose = float(roc_auc_score(binary_y, np.mean(g_wins[mask], axis=1)))
                    auc_flux = float(roc_auc_score(binary_y, np.mean(act_wins[mask], axis=1)))
                    # Combined: mean of normalized scores
                    g_score = (np.mean(g_wins[mask], axis=1) - np.mean(g_wins[mask], axis=1).min()) / \
                              (np.mean(g_wins[mask], axis=1).max() - np.mean(g_wins[mask], axis=1).min() + 1e-8)
                    f_score = (np.mean(act_wins[mask], axis=1) - np.mean(act_wins[mask], axis=1).min()) / \
                              (np.mean(act_wins[mask], axis=1).max() - np.mean(act_wins[mask], axis=1).min() + 1e-8)
                    auc_combined = float(roc_auc_score(binary_y, g_score + f_score))
                except Exception:
                    pass

            scale_results[scale_name] = {
                'n_windows': int(len(mask)),
                'label_counts': label_counts,
                'silhouette_glucose': sil_glucose,
                'silhouette_flux': sil_flux,
                'silhouette_combined': sil_combined,
                'flux_improvement_sil': float(sil_flux - sil_glucose)
                    if not (np.isnan(sil_flux) or np.isnan(sil_glucose)) else None,
                'auc_glucose': auc_glucose,
                'auc_flux': auc_flux,
                'auc_combined': auc_combined,
            }

        per_patient[name] = scale_results
        # Print best scale
        for sc, r in scale_results.items():
            print(f"  {name}@{sc}: sil_glucose={r['silhouette_glucose']:.3f}, "
                  f"sil_flux={r['silhouette_flux']:.3f}, "
                  f"auc_flux={r['auc_flux']:.3f}")

    # Aggregate per scale
    aggregate = {}
    for scale_name in SCALES:
        sil_g = [per_patient[p][scale_name]['silhouette_glucose']
                 for p in per_patient if scale_name in per_patient[p]
                 and not np.isnan(per_patient[p][scale_name].get('silhouette_glucose', float('nan')))]
        sil_f = [per_patient[p][scale_name]['silhouette_flux']
                 for p in per_patient if scale_name in per_patient[p]
                 and not np.isnan(per_patient[p][scale_name].get('silhouette_flux', float('nan')))]
        auc_g = [per_patient[p][scale_name]['auc_glucose']
                 for p in per_patient if scale_name in per_patient[p]
                 and not np.isnan(per_patient[p][scale_name].get('auc_glucose', float('nan')))]
        auc_f = [per_patient[p][scale_name]['auc_flux']
                 for p in per_patient if scale_name in per_patient[p]
                 and not np.isnan(per_patient[p][scale_name].get('auc_flux', float('nan')))]
        if sil_g and sil_f:
            aggregate[scale_name] = {
                'mean_sil_glucose': float(np.mean(sil_g)),
                'mean_sil_flux': float(np.mean(sil_f)),
                'flux_wins_sil': int(sum(1 for g, f in zip(sil_g, sil_f) if f > g)),
                'n_patients': len(sil_g),
            }
            if auc_g and auc_f:
                aggregate[scale_name].update({
                    'mean_auc_glucose': float(np.mean(auc_g)),
                    'mean_auc_flux': float(np.mean(auc_f)),
                    'flux_wins_auc': int(sum(1 for g, f in zip(auc_g, auc_f) if f > g)),
                })

    results = {
        'experiment': 'EXP-438',
        'title': 'Flux as Event Discriminator',
        'hypothesis': 'Metabolic flux features discriminate event types '
                      '(meal/correction/stable) better than raw glucose '
                      'features, especially at scales where glucose changes '
                      'are small due to AID compensation.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }
    save_results(results, 'exp438_flux_discriminator')
    return results


# ═══════════════════════════════════════════════════════════════════════════
# EXP-439: Flux Signal Across Time Scales
# ═══════════════════════════════════════════════════════════════════════════

def run_exp439(args):
    """EXP-439: Flux signal-to-noise ratio at multiple time scales."""
    print("\n══════ EXP-439: Flux Signal Across Time Scales ══════")
    cfg = _get_config(args)
    patients = load_patients(args.patients_dir, verbose=True, **cfg)

    per_patient = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        isf = _extract_isf_scalar(df)
        cr = _extract_cr_scalar(df)
        flux = compute_metabolic_flux(df, isf, cr)

        activity = flux['metabolic_activity']
        glucose = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=120.0)

        scale_results = {}
        for scale_name, wsize in SCALES.items():
            labels = classify_windows_by_event(df, wsize)
            act_wins = make_windows(activity, wsize)
            g_wins = make_windows(glucose, wsize)

            n_wins = min(len(act_wins), len(g_wins), len(labels))
            act_wins = act_wins[:n_wins]
            g_wins = g_wins[:n_wins]
            labs = labels[:n_wins]

            # Signal: mean activity during meals
            # Noise: mean activity during stable
            meal_mask = [i for i, l in enumerate(labs) if l == 'meal']
            stable_mask = [i for i, l in enumerate(labs) if l == 'stable']

            if len(meal_mask) < 3 or len(stable_mask) < 3:
                continue

            signal_flux = np.mean([np.mean(act_wins[i]) for i in meal_mask])
            noise_flux = np.mean([np.mean(act_wins[i]) for i in stable_mask])
            snr_flux = signal_flux / max(noise_flux, 1e-6)

            # Same for glucose variability
            signal_gluc = np.mean([np.std(g_wins[i]) for i in meal_mask])
            noise_gluc = np.mean([np.std(g_wins[i]) for i in stable_mask])
            snr_gluc = signal_gluc / max(noise_gluc, 1e-6)

            # Correlation between flux and glucose rate of change
            g_roc = np.diff(glucose, prepend=glucose[0])
            roc_wins = make_windows(g_roc, wsize)[:n_wins]

            # Per-window correlation of activity with |dBG/dt|
            corrs = []
            for i in range(n_wins):
                a = act_wins[i]
                r = np.abs(roc_wins[i])
                if np.std(a) > 0 and np.std(r) > 0:
                    corrs.append(float(np.corrcoef(a, r)[0, 1]))
            mean_corr = float(np.mean(corrs)) if corrs else float('nan')

            scale_results[scale_name] = {
                'snr_flux': float(snr_flux),
                'snr_glucose': float(snr_gluc),
                'snr_advantage': float(snr_flux - snr_gluc),
                'flux_glucose_corr': mean_corr,
                'n_meal_windows': len(meal_mask),
                'n_stable_windows': len(stable_mask),
                'signal_flux': float(signal_flux),
                'noise_flux': float(noise_flux),
            }

        per_patient[name] = scale_results
        for sc, r in scale_results.items():
            print(f"  {name}@{sc}: SNR_flux={r['snr_flux']:.2f}, "
                  f"SNR_glucose={r['snr_glucose']:.2f}, "
                  f"flux_corr={r['flux_glucose_corr']:.3f}")

    # Aggregate
    aggregate = {}
    for scale_name in SCALES:
        snr_f = [per_patient[p][scale_name]['snr_flux']
                 for p in per_patient if scale_name in per_patient[p]]
        snr_g = [per_patient[p][scale_name]['snr_glucose']
                 for p in per_patient if scale_name in per_patient[p]]
        corrs = [per_patient[p][scale_name]['flux_glucose_corr']
                 for p in per_patient if scale_name in per_patient[p]
                 and not np.isnan(per_patient[p][scale_name].get('flux_glucose_corr', float('nan')))]
        if snr_f:
            aggregate[scale_name] = {
                'mean_snr_flux': float(np.mean(snr_f)),
                'mean_snr_glucose': float(np.mean(snr_g)),
                'flux_wins_snr': int(sum(1 for f, g in zip(snr_f, snr_g) if f > g)),
                'mean_flux_glucose_corr': float(np.mean(corrs)) if corrs else None,
                'n_patients': len(snr_f),
            }

    results = {
        'experiment': 'EXP-439',
        'title': 'Flux Signal Across Time Scales',
        'hypothesis': 'Metabolic flux has higher SNR than glucose variability '
                      'for detecting events, especially at short scales where '
                      'AID compensates and flattens glucose.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }
    save_results(results, 'exp439_flux_snr')
    return results


# ═══════════════════════════════════════════════════════════════════════════
# EXP-440: Flux + Positional Encoding Interaction
# ═══════════════════════════════════════════════════════════════════════════

def run_exp440(args):
    """EXP-440: Test if positional encoding + flux channels together improve
    event discrimination, especially when full DIA response arcs are visible.

    Positional encoding here = index within window / window_length,
    giving the model a sense of "where in the absorption arc" each timestep is.
    Combined with flux channels, this lets the model learn that flux peaks
    at specific phases of the DIA cycle.
    """
    print("\n══════ EXP-440: Flux + Positional Encoding Interaction ══════")
    if not HAS_SKLEARN:
        print("  SKIP: scikit-learn not available")
        return {'experiment': 'EXP-440', 'status': 'skipped'}

    cfg = _get_config(args)
    patients = load_patients(args.patients_dir, verbose=True, **cfg)

    per_patient = {}
    for pat in patients:
        name = pat['name']
        df = pat['df']
        isf = _extract_isf_scalar(df)
        cr = _extract_cr_scalar(df)
        flux = compute_metabolic_flux(df, isf, cr)

        glucose = np.nan_to_num(df['glucose'].values.astype(np.float64), nan=120.0)
        activity = flux['metabolic_activity']
        ins_eff = flux['insulin_effect']
        carb_eff = flux['carb_effect']

        # PK channels from continuous_pk
        pk = pat['pk']  # (N, 8) normalized

        scale_results = {}
        # Focus on scales where full DIA arcs are visible (≥6h)
        for scale_name in ('6h', '12h', '24h'):
            wsize = SCALES[scale_name]
            labels = classify_windows_by_event(df, wsize)

            # Build windows
            g_wins = make_windows(glucose / GLUCOSE_SCALE, wsize)
            act_wins = make_windows(activity, wsize)
            pk_wins = make_windows(pk, wsize)  # (n, wsize, 8)

            n_wins = min(len(g_wins), len(act_wins), len(pk_wins), len(labels))
            g_wins = g_wins[:n_wins]
            act_wins = act_wins[:n_wins]
            pk_wins = pk_wins[:n_wins]
            labs = labels[:n_wins]

            # Need ≥2 event types
            label_counts = {e: sum(1 for l in labs if l == e) for e in ('meal', 'correction', 'stable')}
            active_types = [e for e, c in label_counts.items() if c >= 5]
            if len(active_types) < 2:
                continue

            mask = np.array([i for i, l in enumerate(labs) if l in active_types])
            filtered_labs = [labs[i] for i in mask]
            label_map = {l: i for i, l in enumerate(sorted(set(filtered_labs)))}
            y = np.array([label_map[l] for l in filtered_labs])

            # Positional encoding: normalized position within window
            pos = np.linspace(0, 1, wsize)

            # Feature sets:
            # A. Glucose only
            feat_g = np.column_stack([
                np.mean(g_wins[mask], axis=1),
                np.std(g_wins[mask], axis=1),
                np.max(g_wins[mask], axis=1) - np.min(g_wins[mask], axis=1),
            ])

            # B. Flux only
            feat_f = np.column_stack([
                np.mean(act_wins[mask], axis=1),
                np.max(act_wins[mask], axis=1),
                np.std(act_wins[mask], axis=1),
            ])

            # C. PK summary (mean of each channel)
            feat_pk = np.mean(pk_wins[mask], axis=1)  # (n, 8)

            # D. Flux + positional: phase-weighted flux features
            # Weight flux by position in window, capturing WHERE in DIA arc
            # activity is concentrated
            pos_weighted_mean = np.array([np.average(act_wins[i], weights=pos)
                                          for i in mask])
            pos_weighted_peak_frac = np.array([
                np.argmax(act_wins[i]) / wsize for i in mask])
            # "Center of mass" of flux activity
            com = np.array([np.average(np.arange(wsize), weights=act_wins[i] + 1e-8)
                            / wsize for i in mask])

            feat_fp = np.column_stack([
                feat_f,
                pos_weighted_mean.reshape(-1, 1),
                pos_weighted_peak_frac.reshape(-1, 1),
                com.reshape(-1, 1),
            ])

            # E. All combined: glucose + flux + PK + positional
            feat_all = np.column_stack([feat_g, feat_fp, feat_pk])

            def sil(X, y_labels):
                if len(set(y_labels)) < 2 or len(y_labels) < 10:
                    return float('nan')
                try:
                    return float(silhouette_score(X, y_labels))
                except Exception:
                    return float('nan')

            results_scale = {
                'n_windows': int(len(mask)),
                'label_counts': label_counts,
                'sil_glucose': sil(feat_g, y),
                'sil_flux': sil(feat_f, y),
                'sil_pk': sil(feat_pk, y),
                'sil_flux_positional': sil(feat_fp, y),
                'sil_all_combined': sil(feat_all, y),
            }

            # Key comparison: does positional encoding + flux beat flux alone?
            sf = results_scale['sil_flux']
            sfp = results_scale['sil_flux_positional']
            if not (np.isnan(sf) or np.isnan(sfp)):
                results_scale['positional_improvement'] = float(sfp - sf)

            scale_results[scale_name] = results_scale

        per_patient[name] = scale_results
        for sc, r in scale_results.items():
            print(f"  {name}@{sc}: sil_g={r['sil_glucose']:.3f}, "
                  f"sil_f={r['sil_flux']:.3f}, "
                  f"sil_fp={r['sil_flux_positional']:.3f}, "
                  f"sil_all={r['sil_all_combined']:.3f}")

    # Aggregate
    aggregate = {}
    for scale_name in ('6h', '12h', '24h'):
        vals = {}
        for feat_name in ('sil_glucose', 'sil_flux', 'sil_pk',
                          'sil_flux_positional', 'sil_all_combined'):
            v = [per_patient[p][scale_name][feat_name]
                 for p in per_patient if scale_name in per_patient[p]
                 and not np.isnan(per_patient[p][scale_name].get(feat_name, float('nan')))]
            if v:
                vals[f'mean_{feat_name}'] = float(np.mean(v))
        if vals:
            vals['n_patients'] = len([p for p in per_patient if scale_name in per_patient[p]])
            aggregate[scale_name] = vals

    results = {
        'experiment': 'EXP-440',
        'title': 'Flux + Positional Encoding Interaction',
        'hypothesis': 'Positional encoding + flux channels together improve '
                      'event discrimination at ≥6h scales where full DIA '
                      'arcs are visible. The model can learn that flux peaks '
                      'at specific phases of the absorption cycle.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }
    save_results(results, 'exp440_flux_positional')
    return results


# ═══════════════════════════════════════════════════════════════════════════
# Experiment Registry & Summary
# ═══════════════════════════════════════════════════════════════════════════

EXPERIMENTS = {
    '435': run_exp435,
    '436': run_exp436,
    '437': run_exp437,
    '438': run_exp438,
    '439': run_exp439,
    '440': run_exp440,
}


def flux_scorecard(all_results):
    """Print summary scorecard of metabolic flux experiments."""
    lines = []
    sep = '═' * 72
    thin = '─' * 72

    lines.append(f'╔{sep}╗')
    lines.append(f'║{"METABOLIC FLUX EXPERIMENT SCORECARD":^72s}║')
    lines.append(f'╠{sep}╣')

    # EXP-435: Signal characterization
    r435 = all_results.get('435', {})
    agg435 = r435.get('aggregate', {})
    for scale in ('2h', '6h', '12h', '24h'):
        info = agg435.get(scale, {})
        d = info.get('mean_cohens_d')
        if d is not None:
            sig = '✅' if info.get('all_significant', False) else '⚠️'
            lines.append(f'║ 435 Flux signal ({scale:>3s})     │ '
                         f'd={d:.2f} {sig}  │ '
                         f'n={info.get("n_patients", 0):2d} patients             ║')

    lines.append(f'╟{thin}╢')

    # EXP-436: Phase lag
    r436 = all_results.get('436', {})
    agg436 = r436.get('aggregate', {})
    lag = agg436.get('mean_lag_min')
    if lag is not None:
        n = agg436.get('total_events', 0)
        frac = agg436.get('frac_insulin_after_carb', 0)
        lines.append(f'║ 436 Phase lag             │ '
                     f'mean={lag:+.0f} min    │ '
                     f'{frac:.0%} ins after carb, n={n}   ║')

    lines.append(f'╟{thin}╢')

    # EXP-437: Flux symmetry
    r437 = all_results.get('437', {})
    agg437 = r437.get('aggregate', {})
    gr = agg437.get('mean_glucose_ratio')
    fr = agg437.get('mean_flux_ratio')
    if gr is not None and fr is not None:
        wins = agg437.get('flux_more_symmetric_count', 0)
        total = agg437.get('total_compared', 0)
        lines.append(f'║ 437 Symmetry (glucose)    │ '
                     f'ratio={gr:.2f}       │ '
                     f'(EXP-420 baseline)              ║')
        lines.append(f'║ 437 Symmetry (flux)       │ '
                     f'ratio={fr:.2f}       │ '
                     f'flux wins {wins}/{total} patients       ║')

    lines.append(f'╟{thin}╢')

    # EXP-438: Discriminator
    r438 = all_results.get('438', {})
    agg438 = r438.get('aggregate', {})
    for scale in ('2h', '6h', '12h'):
        info = agg438.get(scale, {})
        sg = info.get('mean_sil_glucose')
        sf = info.get('mean_sil_flux')
        if sg is not None and sf is not None:
            winner = '✅ flux' if sf > sg else '❌ glucose'
            lines.append(f'║ 438 Discriminator ({scale:>3s})  │ '
                         f'g={sg:.3f} f={sf:.3f} │ '
                         f'{winner:<28s}  ║')

    lines.append(f'╟{thin}╢')

    # EXP-439: SNR
    r439 = all_results.get('439', {})
    agg439 = r439.get('aggregate', {})
    for scale in ('2h', '6h', '12h', '24h'):
        info = agg439.get(scale, {})
        sf = info.get('mean_snr_flux')
        sg = info.get('mean_snr_glucose')
        if sf is not None and sg is not None:
            winner = '✅' if sf > sg else '❌'
            lines.append(f'║ 439 SNR ({scale:>3s})             │ '
                         f'flux={sf:.2f} gluc={sg:.2f} │ '
                         f'{winner} n={info.get("n_patients", 0):2d}                      ║')

    lines.append(f'╟{thin}╢')

    # EXP-440: Positional interaction
    r440 = all_results.get('440', {})
    agg440 = r440.get('aggregate', {})
    for scale in ('6h', '12h', '24h'):
        info = agg440.get(scale, {})
        sf = info.get('mean_sil_flux')
        sfp = info.get('mean_sil_flux_positional')
        sa = info.get('mean_sil_all_combined')
        if sf is not None and sfp is not None:
            delta = sfp - sf if sfp and sf else 0
            lines.append(f'║ 440 Flux+pos ({scale:>3s})        │ '
                         f'Δsil={delta:+.3f}       │ '
                         f'all={sa:.3f} n={info.get("n_patients", 0):2d}               ║')

    lines.append(f'╚{sep}╝')

    scorecard = '\n'.join(lines)
    print('\n' + scorecard)
    return scorecard


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _get_config(args):
    if getattr(args, 'quick', False):
        return dict(max_patients=QUICK_PATIENTS)
    return dict(max_patients=None)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='EXP-435-440: Metabolic Flux Channel Experiments',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Experiments:
  435  Metabolic Flux Signal Characterization (event discrimination)
  436  Phase Lag Measurement (carb vs insulin peak timing)
  437  Flux Symmetry Test (vs EXP-420 glucose asymmetry)
  438  Flux as Event Discriminator (silhouette + AUC comparison)
  439  Flux Signal Across Time Scales (SNR analysis)
  440  Flux + Positional Encoding Interaction (DIA arc effects)

Examples:
  python tools/cgmencode/exp_metabolic_flux.py -e all --quick
  python tools/cgmencode/exp_metabolic_flux.py -e 435 436
  python tools/cgmencode/exp_metabolic_flux.py --summary
""")
    parser.add_argument('--experiment', '-e', nargs='+', default=['all'],
                        help='Experiment number(s) or "all"')
    parser.add_argument('--quick', '-q', action='store_true',
                        help='Quick mode: fewer patients')
    parser.add_argument('--patient', '-p', default=None,
                        help='Run for a single patient')
    parser.add_argument('--patients-dir',
                        default='externals/ns-data/patients',
                        help='Path to patient data directory')
    parser.add_argument('--summary', '-s', action='store_true',
                        help='Load saved results and print scorecard')
    args = parser.parse_args()

    if args.summary:
        all_results = {}
        import glob as globmod
        for eid in EXPERIMENTS:
            for m in globmod.glob(str(RESULTS_DIR / f'exp{eid}_*.json')):
                try:
                    with open(m) as f:
                        all_results[eid] = json.load(f)
                except Exception:
                    pass
        flux_scorecard(all_results)
        return all_results

    if 'all' in args.experiment:
        exp_ids = sorted(EXPERIMENTS.keys())
    else:
        exp_ids = [e.strip() for e in args.experiment]

    print(f"Metabolic Flux Experiments — {len(exp_ids)} to run")
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
            print(f"\n  EXP-{eid} FAILED: {exc}")
            traceback.print_exc()
            all_results[eid] = {'error': str(exc)}

    elapsed = time.time() - t0
    print(f"\nAll experiments complete in {elapsed:.0f}s")

    flux_scorecard(all_results)
    return all_results


if __name__ == '__main__':
    main()
