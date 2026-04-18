#!/usr/bin/env python3
"""
EXP-2361–2368: DIA Discrepancy Mechanism Investigation

Research question: WHY does the glucose response DIA (5-20h) differ from
the IOB decay DIA (2.8-3.8h) by 3-5×?

Hypotheses to test:
  H1: Counter-regulatory rebound — glucose rebounds AFTER insulin effect
      due to glucagon/cortisol release, extending apparent DIA
  H2: Hepatic glucose output — liver increases production as insulin wanes,
      creating a secondary rise that looks like extended insulin effect
  H3: AID loop confounding — the loop adjusts basal during correction,
      making it appear insulin works longer than it actually does
  H4: Fat/protein delayed absorption — meals with high fat/protein cause
      delayed glucose rise that overlaps with correction response

Approach:
  2361: Decompose correction bolus glucose response into phases
  2362: Measure rebound magnitude and timing after corrections
  2363: Compare overnight (fasting) DIA vs daytime (meal-confounded) DIA
  2364: Isolate loop contribution by comparing basal adjustment vs bolus effect
  2365: Test if rebound correlates with bolus size (dose-response)
  2366: Compare DIA in high vs low carb contexts
  2367: Circadian DIA variation (is the discrepancy worse at certain times?)
  2368: Population summary and mechanism attribution

Usage:
    PYTHONPATH=tools python tools/cgmencode/production/exp_dia_mechanism.py
    PYTHONPATH=tools python tools/cgmencode/production/exp_dia_mechanism.py --tiny
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal
from scipy.optimize import curve_fit

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

STEPS_PER_HOUR = 12  # 5-min steps
STEPS_PER_DAY = 288


# ── Data Loading ──────────────────────────────────────────────────────

def load_patients(tiny: bool = False) -> dict:
    """Load patient data from parquet."""
    if tiny:
        path = PROJECT_ROOT / "externals" / "ns-parquet-tiny" / "training" / "grid.parquet"
    else:
        path = PROJECT_ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"

    print(f"Loading {path}...")
    t0 = time.time()
    df = pd.read_parquet(path)
    print(f"  {len(df)} rows in {time.time()-t0:.1f}s")

    patients = {}
    for pid, g in df.groupby('patient_id'):
        g = g.sort_values('time').reset_index(drop=True)
        if len(g) < STEPS_PER_DAY * 3:  # Need >= 3 days
            continue
        patients[str(pid)] = g

    print(f"  {len(patients)} patients loaded")
    return patients


# ── Correction Bolus Detection ────────────────────────────────────────

def find_correction_boluses(df: pd.DataFrame,
                            min_bolus: float = 0.5,
                            min_pre_bg: float = 130.0,
                            carb_window: int = 6,  # 30 min
                            ) -> list:
    """Find correction boluses (no nearby carbs, glucose > threshold).

    A correction bolus is defined as:
    - bolus >= min_bolus Units
    - glucose >= min_pre_bg at bolus time
    - no carbs within ±carb_window steps (30 min)
    - sufficient glucose data after bolus (>= 4 hours)

    Returns list of dicts with bolus details and response window.
    """
    glucose = df['glucose'].values
    bolus = df['bolus'].values
    carbs = df['carbs'].values
    iob = df['iob'].values
    time_col = pd.to_datetime(df['time'])

    corrections = []
    n = len(df)

    for i in range(carb_window, n - STEPS_PER_HOUR * 6):
        if bolus[i] < min_bolus:
            continue
        if np.isnan(glucose[i]) or glucose[i] < min_pre_bg:
            continue

        # Check no carbs nearby
        carb_window_start = max(0, i - carb_window)
        carb_window_end = min(n, i + carb_window + 1)
        nearby_carbs = np.nansum(carbs[carb_window_start:carb_window_end])
        if nearby_carbs > 1.0:
            continue

        # Check sufficient glucose coverage in response window (6h)
        response_window = glucose[i:i + STEPS_PER_HOUR * 6]
        if np.isnan(response_window).mean() > 0.3:
            continue

        # Extract response
        pre_bg = float(glucose[i])
        response_bg = np.nan_to_num(response_window, nan=pre_bg)

        # Find nadir
        nadir_idx = np.argmin(response_bg)
        nadir_bg = float(response_bg[nadir_idx])
        nadir_minutes = nadir_idx * 5

        # Find rebound (max after nadir)
        post_nadir = response_bg[nadir_idx:]
        if len(post_nadir) > 6:
            rebound_idx = nadir_idx + np.argmax(post_nadir)
            rebound_bg = float(response_bg[rebound_idx])
            rebound_minutes = rebound_idx * 5
        else:
            rebound_idx = nadir_idx
            rebound_bg = nadir_bg
            rebound_minutes = nadir_minutes

        hour = time_col.iloc[i].hour + time_col.iloc[i].minute / 60.0

        corrections.append({
            'index': i,
            'bolus_units': float(bolus[i]),
            'pre_bg': pre_bg,
            'nadir_bg': nadir_bg,
            'nadir_minutes': nadir_minutes,
            'drop_mg': pre_bg - nadir_bg,
            'rebound_bg': rebound_bg,
            'rebound_minutes': rebound_minutes,
            'rebound_rise': rebound_bg - nadir_bg,
            'net_change_6h': float(response_bg[-1]) - pre_bg,
            'response_bg': response_bg,
            'iob_at_bolus': float(iob[i]) if not np.isnan(iob[i]) else 0.0,
            'hour': hour,
            'is_overnight': hour >= 22 or hour < 6,
        })

    return corrections


# ── EXP-2361: Phase Decomposition ────────────────────────────────────

def exp_2361_phase_decomposition(patients: dict) -> dict:
    """Decompose correction response into descent, nadir, and rebound phases.

    Three phases:
    1. DESCENT: from bolus to nadir (insulin dominant)
    2. NADIR: lowest point ±15 min (equilibrium)
    3. REBOUND: from nadir to 6h (counter-regulatory)
    """
    print("\n" + "="*60)
    print("EXP-2361: Correction Response Phase Decomposition")
    print("="*60)

    results = {}
    for pid, df in sorted(patients.items()):
        corrections = find_correction_boluses(df)
        if len(corrections) < 3:
            continue

        descents = [c['nadir_minutes'] for c in corrections]
        drops = [c['drop_mg'] for c in corrections]
        rebounds = [c['rebound_rise'] for c in corrections]
        rebound_times = [c['rebound_minutes'] - c['nadir_minutes']
                         for c in corrections]
        net_6h = [c['net_change_6h'] for c in corrections]

        # Phase duration statistics
        results[pid] = {
            'n_corrections': len(corrections),
            'descent_minutes': {
                'mean': float(np.mean(descents)),
                'median': float(np.median(descents)),
                'std': float(np.std(descents)),
            },
            'drop_mg': {
                'mean': float(np.mean(drops)),
                'median': float(np.median(drops)),
            },
            'rebound_rise_mg': {
                'mean': float(np.mean(rebounds)),
                'median': float(np.median(rebounds)),
            },
            'rebound_duration_min': {
                'mean': float(np.mean(rebound_times)),
                'median': float(np.median(rebound_times)),
            },
            'net_6h_change': {
                'mean': float(np.mean(net_6h)),
                'median': float(np.median(net_6h)),
            },
            'rebound_fraction': float(np.mean([
                r / d if d > 10 else 0
                for r, d in zip(rebounds, drops)
            ])),
        }

        r = results[pid]
        print(f"  {pid}: {r['n_corrections']} corrections, "
              f"descent {r['descent_minutes']['median']:.0f} min, "
              f"drop {r['drop_mg']['median']:.0f} mg/dL, "
              f"rebound {r['rebound_rise_mg']['median']:.0f} mg/dL "
              f"({r['rebound_fraction']*100:.0f}% of drop)")

    return results


# ── EXP-2362: Rebound Magnitude ─────────────────────────────────────

def exp_2362_rebound_analysis(patients: dict) -> dict:
    """Quantify counter-regulatory rebound after corrections.

    Key question: how much of the glucose response "tail" is rebound
    vs simply returning to baseline?
    """
    print("\n" + "="*60)
    print("EXP-2362: Counter-Regulatory Rebound Analysis")
    print("="*60)

    results = {}
    for pid, df in sorted(patients.items()):
        corrections = find_correction_boluses(df)
        if len(corrections) < 3:
            continue

        # Classify rebounds
        significant_rebounds = 0
        hyper_rebounds = 0
        no_rebounds = 0

        for c in corrections:
            rebound = c['rebound_rise']
            if rebound > 30:
                significant_rebounds += 1
                if c['rebound_bg'] > 180:
                    hyper_rebounds += 1
            else:
                no_rebounds += 1

        total = len(corrections)
        results[pid] = {
            'n_corrections': total,
            'significant_rebound_pct': significant_rebounds / total * 100,
            'hyper_rebound_pct': hyper_rebounds / total * 100,
            'no_rebound_pct': no_rebounds / total * 100,
            'mean_rebound_mg': float(np.mean([c['rebound_rise']
                                               for c in corrections])),
            'mean_rebound_time_min': float(np.mean([
                c['rebound_minutes'] - c['nadir_minutes']
                for c in corrections])),
        }

        r = results[pid]
        print(f"  {pid}: {r['significant_rebound_pct']:.0f}% significant rebounds, "
              f"{r['hyper_rebound_pct']:.0f}% go hyper, "
              f"mean rebound {r['mean_rebound_mg']:.0f} mg/dL")

    return results


# ── EXP-2363: Overnight vs Daytime DIA ───────────────────────────────

def _exp_decay(t, amplitude, tau):
    """Exponential decay: amplitude * exp(-t/tau)."""
    return amplitude * np.exp(-t / tau)


def fit_glucose_dia(response_bg: np.ndarray, pre_bg: float) -> dict:
    """Fit exponential decay to glucose drop to estimate DIA.

    BG(t) = BG_start - amplitude * (1 - exp(-t/τ))

    Returns dict with tau, dia_hours (5τ), amplitude, r_squared.
    """
    drop = pre_bg - response_bg
    t = np.arange(len(drop)) * 5.0 / 60.0  # hours

    # Find where drop is still increasing (descent phase)
    max_drop_idx = np.argmax(drop)
    if max_drop_idx < 3:
        return None

    try:
        popt, _ = curve_fit(
            _exp_decay,
            t[:max_drop_idx + 1],
            drop[:max_drop_idx + 1],
            p0=[max(drop), 1.0],
            bounds=([0, 0.1], [500, 10]),
            maxfev=1000,
        )
        amplitude, tau = popt

        # R² on full response
        predicted = _exp_decay(t[:max_drop_idx + 1], amplitude, tau)
        actual = drop[:max_drop_idx + 1]
        ss_res = np.sum((actual - predicted) ** 2)
        ss_tot = np.sum((actual - np.mean(actual)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        return {
            'tau_hours': float(tau),
            'dia_hours': float(tau * 5),  # 5τ ≈ 99.3% decay
            'amplitude': float(amplitude),
            'r_squared': float(r2),
        }
    except (RuntimeError, ValueError):
        return None


def exp_2363_overnight_vs_daytime(patients: dict) -> dict:
    """Compare DIA estimates for overnight vs daytime corrections.

    If DIA is longer during day, suggests meal/activity confounding.
    If DIA is longer overnight, suggests true physiological mechanism.
    """
    print("\n" + "="*60)
    print("EXP-2363: Overnight vs Daytime DIA Comparison")
    print("="*60)

    results = {}
    for pid, df in sorted(patients.items()):
        corrections = find_correction_boluses(df)
        if len(corrections) < 5:
            continue

        overnight_dias = []
        daytime_dias = []

        for c in corrections:
            fit = fit_glucose_dia(c['response_bg'], c['pre_bg'])
            if fit and fit['r_squared'] > 0.3:
                if c['is_overnight']:
                    overnight_dias.append(fit['dia_hours'])
                else:
                    daytime_dias.append(fit['dia_hours'])

        if len(overnight_dias) < 2 or len(daytime_dias) < 2:
            continue

        overnight_mean = float(np.mean(overnight_dias))
        daytime_mean = float(np.mean(daytime_dias))
        ratio = overnight_mean / daytime_mean if daytime_mean > 0 else 1.0

        results[pid] = {
            'n_overnight': len(overnight_dias),
            'n_daytime': len(daytime_dias),
            'overnight_dia_hours': overnight_mean,
            'daytime_dia_hours': daytime_mean,
            'ratio': ratio,
            'interpretation': (
                "overnight_longer" if ratio > 1.2 else
                "daytime_longer" if ratio < 0.8 else
                "similar"
            ),
        }

        r = results[pid]
        print(f"  {pid}: overnight DIA={r['overnight_dia_hours']:.1f}h "
              f"vs daytime={r['daytime_dia_hours']:.1f}h "
              f"(ratio={r['ratio']:.2f}×, {r['interpretation']})")

    return results


# ── EXP-2364: Loop Contribution ──────────────────────────────────────

def exp_2364_loop_contribution(patients: dict) -> dict:
    """Estimate how much the AID loop extends apparent DIA.

    During correction, the loop typically REDUCES basal to prevent
    overshoot. This sustained basal reduction extends the glucose drop
    beyond what the bolus alone would achieve.

    Measure: basal deviation from scheduled during correction windows.
    """
    print("\n" + "="*60)
    print("EXP-2364: Loop Contribution to DIA Extension")
    print("="*60)

    results = {}
    for pid, df in sorted(patients.items()):
        corrections = find_correction_boluses(df)
        if len(corrections) < 3:
            continue

        if 'actual_basal_rate' not in df.columns or 'scheduled_basal_rate' not in df.columns:
            continue

        actual = df['actual_basal_rate'].values
        scheduled = df['scheduled_basal_rate'].values

        suspension_fracs = []
        basal_reductions = []
        reduction_durations = []

        for c in corrections:
            idx = c['index']
            window_end = min(len(actual), idx + STEPS_PER_HOUR * 6)
            a_window = actual[idx:window_end]
            s_window = scheduled[idx:window_end]

            if len(a_window) < STEPS_PER_HOUR:
                continue

            valid = np.isfinite(a_window) & np.isfinite(s_window)
            if valid.sum() < STEPS_PER_HOUR:
                continue

            a_valid = a_window[valid]
            s_valid = s_window[valid]

            # Fraction of time at zero (suspension)
            susp = float(np.mean(a_valid == 0))
            suspension_fracs.append(susp)

            # Mean basal reduction (negative = reduced)
            reduction = float(np.mean(a_valid - s_valid))
            basal_reductions.append(reduction)

            # Duration of reduced basal (how long is basal below scheduled?)
            below = a_valid < s_valid * 0.9
            if np.any(below):
                # Find contiguous run from start
                first_above = np.argmax(~below[np.argmax(below):]) + np.argmax(below)
                reduction_durations.append(first_above * 5)
            else:
                reduction_durations.append(0)

        if not suspension_fracs:
            continue

        # Estimate insulin "saved" by suspension/reduction
        mean_scheduled = float(np.nanmedian(scheduled[np.isfinite(scheduled)]))
        mean_suspension = float(np.mean(suspension_fracs))
        saved_u_per_h = mean_scheduled * mean_suspension

        results[pid] = {
            'n_corrections': len(suspension_fracs),
            'mean_suspension_pct': mean_suspension * 100,
            'mean_basal_reduction': float(np.mean(basal_reductions)),
            'mean_reduction_duration_min': float(np.mean(reduction_durations)),
            'insulin_saved_per_correction': saved_u_per_h * 3,  # ~3h avg
            'loop_extends_dia': mean_suspension > 0.20,
        }

        r = results[pid]
        print(f"  {pid}: {r['mean_suspension_pct']:.0f}% suspended during corrections, "
              f"reduction duration {r['mean_reduction_duration_min']:.0f} min, "
              f"{'YES' if r['loop_extends_dia'] else 'NO'} loop extends DIA")

    return results


# ── EXP-2365: Dose-Response for Rebound ──────────────────────────────

def exp_2365_dose_response(patients: dict) -> dict:
    """Test if rebound magnitude correlates with bolus size.

    If rebound is dose-dependent, supports counter-regulatory hypothesis.
    If dose-independent, suggests non-insulin mechanism.
    """
    print("\n" + "="*60)
    print("EXP-2365: Dose-Response Relationship for Rebound")
    print("="*60)

    results = {}
    for pid, df in sorted(patients.items()):
        corrections = find_correction_boluses(df)
        if len(corrections) < 5:
            continue

        doses = np.array([c['bolus_units'] for c in corrections])
        drops = np.array([c['drop_mg'] for c in corrections])
        rebounds = np.array([c['rebound_rise'] for c in corrections])

        # Correlations
        if len(doses) > 3 and np.std(doses) > 0.1:
            from scipy.stats import pearsonr
            r_dose_drop, p_dose_drop = pearsonr(doses, drops)
            r_dose_rebound, p_dose_rebound = pearsonr(doses, rebounds)
            r_drop_rebound, p_drop_rebound = pearsonr(drops, rebounds)
        else:
            r_dose_drop = r_dose_rebound = r_drop_rebound = 0
            p_dose_drop = p_dose_rebound = p_drop_rebound = 1

        results[pid] = {
            'n_corrections': len(corrections),
            'dose_vs_drop': {
                'r': float(r_dose_drop),
                'p': float(p_dose_drop),
            },
            'dose_vs_rebound': {
                'r': float(r_dose_rebound),
                'p': float(p_dose_rebound),
            },
            'drop_vs_rebound': {
                'r': float(r_drop_rebound),
                'p': float(p_drop_rebound),
            },
            'supports_counter_regulatory': (
                r_dose_rebound > 0.3 or r_drop_rebound > 0.3
            ),
        }

        r = results[pid]
        print(f"  {pid}: dose→drop r={r['dose_vs_drop']['r']:.2f}, "
              f"dose→rebound r={r['dose_vs_rebound']['r']:.2f}, "
              f"drop→rebound r={r['drop_vs_rebound']['r']:.2f} "
              f"({'SUPPORTS' if r['supports_counter_regulatory'] else 'does not support'} "
              f"counter-regulatory)")

    return results


# ── EXP-2366: Carb Context Effect ────────────────────────────────────

def exp_2366_carb_context(patients: dict) -> dict:
    """Compare DIA in high-carb vs low-carb contexts.

    If recent carbs extend apparent DIA, suggests delayed absorption
    confounding rather than true DIA extension.
    """
    print("\n" + "="*60)
    print("EXP-2366: Carb Context Effect on DIA")
    print("="*60)

    results = {}
    for pid, df in sorted(patients.items()):
        glucose = df['glucose'].values
        bolus_arr = df['bolus'].values
        carbs = df['carbs'].values

        # Find correction boluses with wider carb context (2h before)
        corrections_carb = []
        corrections_fasting = []

        for i in range(STEPS_PER_HOUR * 2, len(df) - STEPS_PER_HOUR * 6):
            if bolus_arr[i] < 0.5:
                continue
            if np.isnan(glucose[i]) or glucose[i] < 130:
                continue

            response = glucose[i:i + STEPS_PER_HOUR * 6]
            if np.isnan(response).mean() > 0.3:
                continue

            # No carbs within ±30 min (still a correction)
            if np.nansum(carbs[max(0,i-6):i+7]) > 1.0:
                continue

            # Check carbs in previous 2h
            recent_carbs = np.nansum(carbs[max(0, i - STEPS_PER_HOUR * 2):i])

            response_clean = np.nan_to_num(response, nan=float(glucose[i]))
            fit = fit_glucose_dia(response_clean, float(glucose[i]))
            if fit is None or fit['r_squared'] < 0.2:
                continue

            if recent_carbs > 5:
                corrections_carb.append(fit['dia_hours'])
            else:
                corrections_fasting.append(fit['dia_hours'])

        if len(corrections_carb) < 2 or len(corrections_fasting) < 2:
            continue

        carb_dia = float(np.mean(corrections_carb))
        fast_dia = float(np.mean(corrections_fasting))
        ratio = carb_dia / fast_dia if fast_dia > 0 else 1.0

        results[pid] = {
            'n_post_carb': len(corrections_carb),
            'n_fasting': len(corrections_fasting),
            'dia_post_carb_hours': carb_dia,
            'dia_fasting_hours': fast_dia,
            'ratio': ratio,
            'carbs_extend_dia': ratio > 1.3,
        }

        r = results[pid]
        print(f"  {pid}: post-carb DIA={r['dia_post_carb_hours']:.1f}h "
              f"vs fasting DIA={r['dia_fasting_hours']:.1f}h "
              f"(ratio={r['ratio']:.2f}×)")

    return results


# ── EXP-2367: Circadian DIA Variation ────────────────────────────────

def exp_2367_circadian_dia(patients: dict) -> dict:
    """Test if DIA discrepancy varies by time of day.

    Compare morning, afternoon, evening, overnight DIA estimates.
    """
    print("\n" + "="*60)
    print("EXP-2367: Circadian DIA Variation")
    print("="*60)

    periods = [
        ('overnight', 22, 6),
        ('morning', 6, 12),
        ('afternoon', 12, 18),
        ('evening', 18, 22),
    ]

    results = {}
    for pid, df in sorted(patients.items()):
        corrections = find_correction_boluses(df)
        if len(corrections) < 5:
            continue

        period_dias = {name: [] for name, _, _ in periods}

        for c in corrections:
            fit = fit_glucose_dia(c['response_bg'], c['pre_bg'])
            if fit is None or fit['r_squared'] < 0.3:
                continue

            hour = c['hour']
            for name, h_start, h_end in periods:
                if h_start < h_end:
                    if h_start <= hour < h_end:
                        period_dias[name].append(fit['dia_hours'])
                        break
                else:  # overnight wraps
                    if hour >= h_start or hour < h_end:
                        period_dias[name].append(fit['dia_hours'])
                        break

        valid_periods = {name: dias for name, dias in period_dias.items()
                        if len(dias) >= 2}
        if len(valid_periods) < 2:
            continue

        period_stats = {}
        for name, dias in valid_periods.items():
            period_stats[name] = {
                'n': len(dias),
                'mean_dia': float(np.mean(dias)),
                'std_dia': float(np.std(dias)),
            }

        all_means = [s['mean_dia'] for s in period_stats.values()]
        variation = (max(all_means) - min(all_means)) / np.mean(all_means) * 100

        results[pid] = {
            'periods': period_stats,
            'variation_pct': float(variation),
            'longest_period': max(period_stats, key=lambda k: period_stats[k]['mean_dia']),
            'shortest_period': min(period_stats, key=lambda k: period_stats[k]['mean_dia']),
        }

        r = results[pid]
        parts = [f"{name}={s['mean_dia']:.1f}h" for name, s in sorted(period_stats.items())]
        print(f"  {pid}: {', '.join(parts)} "
              f"(variation {r['variation_pct']:.0f}%)")

    return results


# ── EXP-2368: Population Summary ─────────────────────────────────────

def exp_2368_summary(all_results: dict) -> dict:
    """Summarize mechanism attribution across all experiments."""
    print("\n" + "="*60)
    print("EXP-2368: DIA Discrepancy Mechanism Summary")
    print("="*60)

    # H1: Counter-regulatory rebound
    exp2362 = all_results.get('exp_2362', {})
    rebounds = [r['significant_rebound_pct'] for r in exp2362.values()]
    h1_support = float(np.mean(rebounds)) if rebounds else 0

    # H2: Hepatic (indirectly measured via fasting DIA being long)
    exp2363 = all_results.get('exp_2363', {})
    overnight_longer = sum(1 for r in exp2363.values()
                          if r['interpretation'] == 'overnight_longer')
    h2_support = overnight_longer / len(exp2363) * 100 if exp2363 else 0

    # H3: Loop extends DIA
    exp2364 = all_results.get('exp_2364', {})
    loop_extends = sum(1 for r in exp2364.values() if r['loop_extends_dia'])
    h3_support = loop_extends / len(exp2364) * 100 if exp2364 else 0

    # H4: Carb context
    exp2366 = all_results.get('exp_2366', {})
    carbs_extend = sum(1 for r in exp2366.values() if r['carbs_extend_dia'])
    h4_support = carbs_extend / len(exp2366) * 100 if exp2366 else 0

    # H5: Dose-response for counter-regulatory
    exp2365 = all_results.get('exp_2365', {})
    dose_resp = sum(1 for r in exp2365.values()
                   if r['supports_counter_regulatory'])
    h5_support = dose_resp / len(exp2365) * 100 if exp2365 else 0

    summary = {
        'H1_counter_regulatory_rebound': {
            'support_pct': h1_support,
            'mean_rebound_pct_of_corrections': h1_support,
            'interpretation': (
                f"{h1_support:.0f}% of corrections show significant rebound "
                f"(>30 mg/dL rise after nadir)"
            ),
        },
        'H2_hepatic_glucose_output': {
            'support_pct': h2_support,
            'overnight_longer_than_day': overnight_longer,
            'interpretation': (
                f"{h2_support:.0f}% of patients show longer overnight DIA, "
                f"suggesting hepatic contribution independent of meals"
            ),
        },
        'H3_loop_extends_dia': {
            'support_pct': h3_support,
            'n_patients_affected': loop_extends,
            'interpretation': (
                f"{h3_support:.0f}% of patients show significant basal suspension "
                f"during corrections, extending apparent DIA"
            ),
        },
        'H4_carb_confounding': {
            'support_pct': h4_support,
            'n_patients_affected': carbs_extend,
            'interpretation': (
                f"{h4_support:.0f}% of patients show longer DIA with "
                f"recent carbs, suggesting absorption confounding"
            ),
        },
        'H5_dose_dependent_rebound': {
            'support_pct': h5_support,
            'n_patients_affected': dose_resp,
            'interpretation': (
                f"{h5_support:.0f}% of patients show dose-dependent rebound, "
                f"supporting counter-regulatory mechanism"
            ),
        },
    }

    print("\n  Mechanism Attribution:")
    for hname, data in summary.items():
        print(f"    {hname}: {data['support_pct']:.0f}% support — "
              f"{data['interpretation']}")

    # Determine dominant mechanism
    supports = {
        'counter_regulatory': (h1_support + h5_support) / 2,
        'hepatic': h2_support,
        'loop_confounding': h3_support,
        'carb_confounding': h4_support,
    }
    dominant = max(supports, key=supports.get)
    summary['dominant_mechanism'] = dominant
    summary['mechanism_ranking'] = dict(sorted(supports.items(),
                                               key=lambda x: -x[1]))

    print(f"\n  Dominant mechanism: {dominant}")
    print(f"  Ranking: {summary['mechanism_ranking']}")

    return summary


# ── Visualization ─────────────────────────────────────────────────────

def generate_figures(all_results: dict, output_dir: Path):
    """Generate visualization figures for the report."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)

    # Figure 1: Phase decomposition - average correction response curve
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    exp2361 = all_results.get('exp_2361', {})
    if exp2361:
        patients_sorted = sorted(exp2361.keys())
        descents = [exp2361[p]['descent_minutes']['median'] for p in patients_sorted]
        rebound_fracs = [exp2361[p]['rebound_fraction'] * 100 for p in patients_sorted]

        ax = axes[0]
        ax.barh(patients_sorted, descents, color='steelblue', alpha=0.8)
        ax.set_xlabel('Time to Nadir (minutes)')
        ax.set_title('EXP-2361: Descent Duration')
        ax.axvline(np.mean(descents), color='red', linestyle='--',
                   label=f'Mean: {np.mean(descents):.0f} min')
        ax.legend()

        ax = axes[1]
        ax.barh(patients_sorted, rebound_fracs, color='coral', alpha=0.8)
        ax.set_xlabel('Rebound as % of Drop')
        ax.set_title('EXP-2361: Rebound Fraction')
        ax.axvline(np.mean(rebound_fracs), color='red', linestyle='--',
                   label=f'Mean: {np.mean(rebound_fracs):.0f}%')
        ax.legend()

    plt.tight_layout()
    plt.savefig(output_dir / 'fig1_phase_decomposition.png', dpi=150)
    plt.close()

    # Figure 2: Overnight vs Daytime DIA
    exp2363 = all_results.get('exp_2363', {})
    if exp2363:
        fig, ax = plt.subplots(figsize=(8, 6))
        patients_sorted = sorted(exp2363.keys())
        overnight = [exp2363[p]['overnight_dia_hours'] for p in patients_sorted]
        daytime = [exp2363[p]['daytime_dia_hours'] for p in patients_sorted]

        x = np.arange(len(patients_sorted))
        width = 0.35
        ax.bar(x - width/2, overnight, width, label='Overnight', color='navy', alpha=0.8)
        ax.bar(x + width/2, daytime, width, label='Daytime', color='gold', alpha=0.8)
        ax.set_xlabel('Patient')
        ax.set_ylabel('DIA (hours)')
        ax.set_title('EXP-2363: Overnight vs Daytime DIA')
        ax.set_xticks(x)
        ax.set_xticklabels(patients_sorted)
        ax.legend()
        ax.axhline(5, color='gray', linestyle=':', label='Profile DIA (5h)')

        plt.tight_layout()
        plt.savefig(output_dir / 'fig2_overnight_vs_daytime.png', dpi=150)
        plt.close()

    # Figure 3: Mechanism support summary
    exp2368 = all_results.get('exp_2368', {})
    if exp2368 and 'mechanism_ranking' in exp2368:
        fig, ax = plt.subplots(figsize=(8, 5))
        mechanisms = list(exp2368['mechanism_ranking'].keys())
        supports = list(exp2368['mechanism_ranking'].values())

        colors = ['#e74c3c', '#2ecc71', '#3498db', '#f39c12']
        ax.barh(mechanisms, supports, color=colors[:len(mechanisms)], alpha=0.8)
        ax.set_xlabel('Support (%)')
        ax.set_title('EXP-2368: DIA Discrepancy Mechanism Attribution')
        ax.set_xlim(0, 100)

        for i, (m, s) in enumerate(zip(mechanisms, supports)):
            ax.text(s + 2, i, f'{s:.0f}%', va='center')

        plt.tight_layout()
        plt.savefig(output_dir / 'fig3_mechanism_attribution.png', dpi=150)
        plt.close()

    # Figure 4: Dose-response scatter
    exp2365 = all_results.get('exp_2365', {})
    if exp2365:
        fig, ax = plt.subplots(figsize=(8, 6))
        patients_sorted = sorted(exp2365.keys())
        dose_r = [exp2365[p]['dose_vs_rebound']['r'] for p in patients_sorted]
        drop_r = [exp2365[p]['drop_vs_rebound']['r'] for p in patients_sorted]

        x = np.arange(len(patients_sorted))
        width = 0.35
        ax.bar(x - width/2, dose_r, width, label='Dose → Rebound', color='purple', alpha=0.7)
        ax.bar(x + width/2, drop_r, width, label='Drop → Rebound', color='teal', alpha=0.7)
        ax.set_xlabel('Patient')
        ax.set_ylabel('Correlation (r)')
        ax.set_title('EXP-2365: Dose-Response for Rebound')
        ax.set_xticks(x)
        ax.set_xticklabels(patients_sorted)
        ax.legend()
        ax.axhline(0, color='gray', linestyle='-', linewidth=0.5)
        ax.axhline(0.3, color='red', linestyle=':', label='Significance threshold')

        plt.tight_layout()
        plt.savefig(output_dir / 'fig4_dose_response.png', dpi=150)
        plt.close()

    print(f"\n  Figures saved to {output_dir}")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tiny', action='store_true')
    parser.add_argument('--output', default=str(
        PROJECT_ROOT / 'externals' / 'experiments' / 'exp-2361-2368_dia_mechanism.json'))
    args = parser.parse_args()

    patients = load_patients(tiny=args.tiny)
    if not patients:
        print("ERROR: No patients loaded")
        sys.exit(1)

    all_results = {}

    # Run all experiments
    all_results['exp_2361'] = exp_2361_phase_decomposition(patients)
    all_results['exp_2362'] = exp_2362_rebound_analysis(patients)
    all_results['exp_2363'] = exp_2363_overnight_vs_daytime(patients)
    all_results['exp_2364'] = exp_2364_loop_contribution(patients)
    all_results['exp_2365'] = exp_2365_dose_response(patients)
    all_results['exp_2366'] = exp_2366_carb_context(patients)
    all_results['exp_2367'] = exp_2367_circadian_dia(patients)
    all_results['exp_2368'] = exp_2368_summary(all_results)

    # Generate visualizations
    fig_dir = PROJECT_ROOT / 'visualizations' / 'dia-mechanism'
    generate_figures(all_results, fig_dir)

    # Save results
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w') as f:
        # Make numpy-safe
        def convert(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, (np.float64, np.float32)):
                return float(obj)
            if isinstance(obj, (np.int64, np.int32)):
                return int(obj)
            if isinstance(obj, (np.bool_,)):
                return bool(obj)
            raise TypeError(f"Cannot serialize {type(obj)}")

        json.dump(all_results, f, indent=2, default=convert)
    print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
