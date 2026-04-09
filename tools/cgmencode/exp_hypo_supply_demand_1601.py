#!/usr/bin/env python3
"""EXP-1601 through EXP-1606: Hypoglycemia Through the Supply-Demand Lens.

This batch analyzes hypoglycemic events using the supply × demand metabolic
framework, testing the hypothesis that the variability and unpredictability
of post-hypo glucose trajectories is driven by a confluence of factors:

  1. Pre-hypo fasting creates zero carb supply (hepatic-only)
  2. AID systems withdraw insulin, creating negative net-IOB
  3. Rescue carbs are consumed but rarely entered in the system
  4. Counter-regulatory hormones boost hepatic output beyond modeled levels
  5. The combination of low IOB + unannounced carbs + counter-reg creates
     explosive, variable rebounds

Supply-demand decomposition:
  SUPPLY(t) = hepatic_modeled(t) + carb_modeled(t)
  DEMAND(t) = insulin_modeled(t)
  dBG/dt ≈ SUPPLY - DEMAND + ε(t)

Extended decomposition (UVA/Padova-inspired):
  ε(t) = hepatic_loss(t) - sensitivity_loss(t) + noise
  where:
    hepatic_loss   = unmodeled supply (counter-reg hormones, rescue carbs)
    sensitivity_loss = unmodeled demand variation (time-varying ISF, exercise)

EXP-1601: Pre-hypo metabolic context
EXP-1602: Supply-demand phase decomposition across hypo lifecycle
EXP-1603: Rescue carb quantification via residual analysis
EXP-1604: Post-hypo rebound characterization
EXP-1605: Extended residual decomposition (hepatic_loss + sensitivity_loss)
EXP-1606: Information ceiling per decomposition level

References:
  - continuous_pk.py: compute_hepatic_production(), compute_net_metabolic_balance()
  - exp_metabolic_441.py: compute_supply_demand() — core S×D decomposition
  - exp_clinical_1491.py: detect_hypo_episodes(), TBR safety experiments
  - exp_autoresearch_601.py: +5.1 mg/dL counter-regulatory bias discovery
  - Dalla Man et al. 2007: UVA/Padova multi-compartment glucose model
"""

import sys
import os
import json
import argparse
import warnings
from pathlib import Path
from collections import defaultdict

import numpy as np
from scipy import stats

warnings.filterwarnings('ignore', category=RuntimeWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_metabolic_441 import compute_supply_demand

# ── Constants ──────────────────────────────────────────────────────────

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
HYPO_THRESHOLD = 70        # mg/dL
SEVERE_HYPO = 54           # mg/dL
PRE_WINDOW_HOURS = 2       # hours before hypo to analyze
POST_WINDOW_HOURS = 2      # hours after nadir to analyze
MIN_EPISODE_STEPS = 3      # 15 min minimum

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'
FIGURES_DIR = Path(__file__).parent.parent.parent / 'docs' / '60-research' / 'figures'


# ── Episode Detection ──────────────────────────────────────────────────

def detect_hypo_episodes(glucose, threshold=HYPO_THRESHOLD,
                         min_steps=MIN_EPISODE_STEPS):
    """Find contiguous hypo episodes. Returns list of dicts."""
    n = len(glucose)
    episodes = []
    i = 0
    while i < n:
        if not np.isnan(glucose[i]) and glucose[i] < threshold:
            start = i
            nadir = glucose[i]
            nadir_idx = i
            i += 1
            while i < n and not np.isnan(glucose[i]) and glucose[i] < threshold:
                if glucose[i] < nadir:
                    nadir = glucose[i]
                    nadir_idx = i
                i += 1
            duration = i - start
            if duration >= min_steps:
                episodes.append({
                    'start': start, 'end': i,
                    'nadir': float(nadir), 'nadir_idx': nadir_idx,
                    'duration_steps': duration,
                    'duration_min': duration * 5,
                })
        else:
            i += 1
    return episodes


# ── Shared Helpers ─────────────────────────────────────────────────────

def _safe(arr, idx, default=np.nan):
    if 0 <= idx < len(arr) and np.isfinite(arr[idx]):
        return float(arr[idx])
    return default


def _window_mean(arr, start, end):
    seg = arr[max(0, start):min(end, len(arr))]
    valid = seg[np.isfinite(seg)]
    return float(np.mean(valid)) if len(valid) > 0 else np.nan


def _time_since_last_carbs(carbs, idx):
    """Minutes since last carb entry before idx."""
    for j in range(idx - 1, -1, -1):
        if not np.isnan(carbs[j]) and carbs[j] > 0.5:
            return (idx - j) * 5
    return np.nan  # no carbs found


def _compute_residual(glucose, net_flux):
    """Compute residual: actual dBG/dt - predicted (net_flux)."""
    n = min(len(glucose), len(net_flux))
    actual_dbg = np.full(n, np.nan)
    actual_dbg[1:] = np.diff(glucose[:n])
    residual = actual_dbg - net_flux[:n]
    return residual


# ── EXP-1601: Pre-Hypo Metabolic Context ──────────────────────────────

def exp_1601_pre_hypo_context(patients_data):
    """Characterize the metabolic state in the 2 hours before hypo onset.

    Tests hypotheses:
    - Hypos occur after long fasting (carb_supply ≈ 0)
    - AID has been withdrawing insulin (demand declining, IOB low)
    - Net flux is sustained negative (demand >> supply)
    """
    print("\n" + "─" * 60)
    print("EXP-1601: Pre-Hypo Metabolic Context")
    print("─" * 60)

    all_fasting_durations = []
    all_pre_iob = []
    all_pre_net_flux = []
    all_pre_demand_trend = []
    per_patient = []

    for pid, pdata in sorted(patients_data.items()):
        glucose = pdata['glucose']
        carbs = pdata['carbs']
        iob = pdata['iob']
        sd = pdata['sd']
        episodes = pdata['episodes']

        fasting_durations = []
        pre_iob_at_onset = []
        pre_net_flux_means = []
        pre_demand_slopes = []
        pre_supply_means = []

        lookback = PRE_WINDOW_HOURS * STEPS_PER_HOUR

        for ep in episodes:
            onset = ep['start']

            # Fasting duration
            fd = _time_since_last_carbs(carbs, onset)
            if np.isfinite(fd):
                fasting_durations.append(fd)
                all_fasting_durations.append(fd)

            # IOB at onset
            iob_val = _safe(iob, onset)
            if np.isfinite(iob_val):
                pre_iob_at_onset.append(iob_val)
                all_pre_iob.append(iob_val)

            # Pre-hypo net flux (mean over 2h before)
            pre_start = max(0, onset - lookback)
            net_mean = _window_mean(sd['net'], pre_start, onset)
            if np.isfinite(net_mean):
                pre_net_flux_means.append(net_mean)
                all_pre_net_flux.append(net_mean)

            # Demand trend (slope over 2h before)
            demand_seg = sd['demand'][pre_start:onset]
            valid_d = demand_seg[np.isfinite(demand_seg)]
            if len(valid_d) >= 6:
                x = np.arange(len(valid_d))
                slope = np.polyfit(x, valid_d, 1)[0]
                pre_demand_slopes.append(float(slope))
                all_pre_demand_trend.append(float(slope))

            # Supply mean pre-hypo
            sup_mean = _window_mean(sd['supply'], pre_start, onset)
            if np.isfinite(sup_mean):
                pre_supply_means.append(sup_mean)

        rec = {
            'pid': pid,
            'n_episodes': len(episodes),
            'median_fasting_min': float(np.median(fasting_durations)) if fasting_durations else None,
            'mean_fasting_min': float(np.mean(fasting_durations)) if fasting_durations else None,
            'pct_fasting_gt_3h': float(np.mean([f > 180 for f in fasting_durations]) * 100) if fasting_durations else None,
            'mean_iob_at_onset': float(np.mean(pre_iob_at_onset)) if pre_iob_at_onset else None,
            'mean_pre_net_flux': float(np.mean(pre_net_flux_means)) if pre_net_flux_means else None,
            'mean_pre_supply': float(np.mean(pre_supply_means)) if pre_supply_means else None,
            'mean_demand_slope': float(np.mean(pre_demand_slopes)) if pre_demand_slopes else None,
        }
        per_patient.append(rec)
        print(f"  {pid}: episodes={len(episodes)} "
              f"fasting={rec['median_fasting_min']:.0f}min "
              f"IOB={rec['mean_iob_at_onset']:.2f}U "
              f"net_flux={rec['mean_pre_net_flux']:.2f}")

    # Population baseline: what does fasting duration look like for ALL timesteps?
    # (not just pre-hypo — to test if hypos are enriched at long fasting)
    all_fasting_baseline = []
    for pid, pdata in patients_data.items():
        carbs = pdata['carbs']
        glucose = pdata['glucose']
        for i in range(0, len(glucose), 36):  # sample every 3h
            if np.isfinite(glucose[i]) and glucose[i] >= 70:
                fd = _time_since_last_carbs(carbs, i)
                if np.isfinite(fd):
                    all_fasting_baseline.append(fd)

    results = {
        'name': 'EXP-1601: Pre-Hypo Metabolic Context',
        'per_patient': per_patient,
        'population': {
            'median_fasting_before_hypo_min': float(np.median(all_fasting_durations)),
            'mean_fasting_before_hypo_min': float(np.mean(all_fasting_durations)),
            'pct_fasting_gt_3h': float(np.mean([f > 180 for f in all_fasting_durations]) * 100),
            'median_fasting_baseline_min': float(np.median(all_fasting_baseline)) if all_fasting_baseline else None,
            'mean_iob_at_onset': float(np.mean(all_pre_iob)),
            'mean_pre_net_flux': float(np.mean(all_pre_net_flux)),
            'mean_demand_slope': float(np.mean(all_pre_demand_trend)),
            'n_episodes_total': sum(len(pd['episodes']) for pd in patients_data.values()),
        },
    }
    print(f"\n  POPULATION: median fasting={results['population']['median_fasting_before_hypo_min']:.0f}min "
          f"(baseline={results['population']['median_fasting_baseline_min']:.0f}min) "
          f"IOB={results['population']['mean_iob_at_onset']:.2f}U "
          f"net_flux={results['population']['mean_pre_net_flux']:.2f}")
    return results


# ── EXP-1602: Supply-Demand Phase Decomposition ──────────────────────

def exp_1602_phase_decomposition(patients_data):
    """Decompose supply, demand, hepatic, residual across hypo lifecycle phases.

    Phases (relative to nadir):
      -2h to -1h: Pre-approach
      -1h to onset: Descent approach
      onset to nadir: Active descent
      nadir to +30min: Early recovery
      +30min to +1h: Late recovery
      +1h to +2h: Rebound zone
    """
    print("\n" + "─" * 60)
    print("EXP-1602: Supply-Demand Phase Decomposition")
    print("─" * 60)

    phase_defs = [
        ('pre_approach', -24, -12),    # -2h to -1h from nadir
        ('descent_approach', -12, -6), # -1h to -30min
        ('active_descent', -6, 0),     # -30min to nadir
        ('early_recovery', 0, 6),      # nadir to +30min
        ('late_recovery', 6, 12),      # +30min to +1h
        ('rebound_zone', 12, 24),      # +1h to +2h
    ]

    phase_data = {name: {'supply': [], 'demand': [], 'hepatic': [],
                         'carb_supply': [], 'net': [], 'residual': [],
                         'glucose': [], 'iob': []}
                  for name, _, _ in phase_defs}

    for pid, pdata in sorted(patients_data.items()):
        glucose = pdata['glucose']
        iob = pdata['iob']
        sd = pdata['sd']
        residual = pdata['residual']
        episodes = pdata['episodes']
        n = len(glucose)

        for ep in episodes:
            nadir_idx = ep['nadir_idx']

            for phase_name, rel_start, rel_end in phase_defs:
                abs_start = nadir_idx + rel_start
                abs_end = nadir_idx + rel_end
                if abs_start < 0 or abs_end > n:
                    continue

                phase_data[phase_name]['supply'].append(
                    _window_mean(sd['supply'], abs_start, abs_end))
                phase_data[phase_name]['demand'].append(
                    _window_mean(sd['demand'], abs_start, abs_end))
                phase_data[phase_name]['hepatic'].append(
                    _window_mean(sd['hepatic'], abs_start, abs_end))
                phase_data[phase_name]['carb_supply'].append(
                    _window_mean(sd['carb_supply'], abs_start, abs_end))
                phase_data[phase_name]['net'].append(
                    _window_mean(sd['net'], abs_start, abs_end))
                phase_data[phase_name]['residual'].append(
                    _window_mean(residual, abs_start, abs_end))
                phase_data[phase_name]['glucose'].append(
                    _window_mean(glucose, abs_start, abs_end))
                phase_data[phase_name]['iob'].append(
                    _window_mean(iob, abs_start, abs_end))

    results = {'name': 'EXP-1602: Supply-Demand Phase Decomposition',
               'phases': {}}

    for phase_name, _, _ in phase_defs:
        pd_phase = phase_data[phase_name]
        phase_summary = {}
        for key in pd_phase:
            vals = [v for v in pd_phase[key] if np.isfinite(v)]
            if vals:
                phase_summary[f'{key}_mean'] = round(float(np.mean(vals)), 3)
                phase_summary[f'{key}_std'] = round(float(np.std(vals)), 3)
                phase_summary[f'{key}_median'] = round(float(np.median(vals)), 3)
            else:
                phase_summary[f'{key}_mean'] = None
        phase_summary['n_episodes'] = len([v for v in pd_phase['glucose'] if np.isfinite(v)])
        results['phases'][phase_name] = phase_summary
        print(f"  {phase_name}: glucose={phase_summary['glucose_mean']:.0f} "
              f"supply={phase_summary['supply_mean']:.2f} "
              f"demand={phase_summary['demand_mean']:.2f} "
              f"net={phase_summary['net_mean']:.2f} "
              f"residual={phase_summary['residual_mean']:.2f}")

    return results


# ── EXP-1603: Rescue Carb Quantification via Residuals ────────────────

def exp_1603_rescue_carbs(patients_data):
    """Quantify unannounced rescue carbs by analyzing residuals during recovery.

    Logic: During recovery (nadir → 70 mg/dL), glucose rises faster than
    supply-demand predicts. The excess = residual = rescue carbs + counter-reg.

    We separate:
    - Episodes with entered carbs near hypo (announced rescue)
    - Episodes without entered carbs (unannounced rescue)
    - Compare residual magnitude between groups
    """
    print("\n" + "─" * 60)
    print("EXP-1603: Rescue Carb Quantification via Residuals")
    print("─" * 60)

    per_patient = []
    all_announced_resid = []
    all_unannounced_resid = []
    all_no_rescue_resid = []

    for pid, pdata in sorted(patients_data.items()):
        glucose = pdata['glucose']
        carbs = pdata['carbs']
        sd = pdata['sd']
        residual = pdata['residual']
        episodes = pdata['episodes']
        n = len(glucose)

        announced = 0
        unannounced = 0
        announced_resid = []
        unannounced_resid = []
        announced_rebound_bg = []
        unannounced_rebound_bg = []

        for ep in episodes:
            nadir_idx = ep['nadir_idx']
            # Check for carbs within -15min to +60min of nadir
            carb_window_start = max(0, nadir_idx - 3)
            carb_window_end = min(n, nadir_idx + 12)
            carb_seg = carbs[carb_window_start:carb_window_end]
            entered_carbs = np.nansum(carb_seg)

            # Recovery residual: nadir to +30min
            rec_start = nadir_idx
            rec_end = min(n, nadir_idx + 6)
            rec_resid = _window_mean(residual, rec_start, rec_end)

            # Rebound BG: glucose at nadir+60min
            rebound_idx = min(n - 1, nadir_idx + 12)
            rebound_bg = _safe(glucose, rebound_idx)

            if entered_carbs > 2:
                announced += 1
                if np.isfinite(rec_resid):
                    announced_resid.append(rec_resid)
                    all_announced_resid.append(rec_resid)
                if np.isfinite(rebound_bg):
                    announced_rebound_bg.append(rebound_bg)
            else:
                unannounced += 1
                if np.isfinite(rec_resid):
                    unannounced_resid.append(rec_resid)
                    all_unannounced_resid.append(rec_resid)
                if np.isfinite(rebound_bg):
                    unannounced_rebound_bg.append(rebound_bg)

        total = announced + unannounced
        rec = {
            'pid': pid,
            'n_episodes': total,
            'n_announced_rescue': announced,
            'n_unannounced_rescue': unannounced,
            'pct_unannounced': round(unannounced / max(total, 1) * 100, 1),
            'mean_residual_announced': round(float(np.mean(announced_resid)), 3) if announced_resid else None,
            'mean_residual_unannounced': round(float(np.mean(unannounced_resid)), 3) if unannounced_resid else None,
            'mean_rebound_bg_announced': round(float(np.mean(announced_rebound_bg)), 1) if announced_rebound_bg else None,
            'mean_rebound_bg_unannounced': round(float(np.mean(unannounced_rebound_bg)), 1) if unannounced_rebound_bg else None,
        }
        per_patient.append(rec)
        ann_r = rec['mean_residual_announced'] or 0
        unann_r = rec['mean_residual_unannounced'] or 0
        print(f"  {pid}: announced={announced} unannounced={unannounced} "
              f"({rec['pct_unannounced']:.0f}%) "
              f"resid_ann={ann_r:.2f} resid_unann={unann_r:.2f}")

    # Test: is the residual different for announced vs unannounced?
    if len(all_announced_resid) > 5 and len(all_unannounced_resid) > 5:
        t_stat, p_val = stats.ttest_ind(all_announced_resid,
                                         all_unannounced_resid)
    else:
        t_stat, p_val = np.nan, np.nan

    results = {
        'name': 'EXP-1603: Rescue Carb Quantification via Residuals',
        'per_patient': per_patient,
        'population': {
            'total_episodes': sum(r['n_episodes'] for r in per_patient),
            'total_announced': sum(r['n_announced_rescue'] for r in per_patient),
            'total_unannounced': sum(r['n_unannounced_rescue'] for r in per_patient),
            'pct_unannounced': round(
                sum(r['n_unannounced_rescue'] for r in per_patient)
                / max(sum(r['n_episodes'] for r in per_patient), 1) * 100, 1),
            'mean_residual_announced': round(float(np.mean(all_announced_resid)), 3) if all_announced_resid else None,
            'mean_residual_unannounced': round(float(np.mean(all_unannounced_resid)), 3) if all_unannounced_resid else None,
            'residual_difference_ttest_p': round(float(p_val), 4) if np.isfinite(p_val) else None,
        },
    }
    print(f"\n  POPULATION: {results['population']['pct_unannounced']:.0f}% unannounced, "
          f"resid_announced={results['population']['mean_residual_announced']}, "
          f"resid_unannounced={results['population']['mean_residual_unannounced']}, "
          f"p={results['population']['residual_difference_ttest_p']}")
    return results


# ── EXP-1604: Post-Hypo Rebound Characterization ─────────────────────

def exp_1604_rebound_characterization(patients_data):
    """Characterize post-hypo rebounds and their relationship to context.

    Tests: Does rebound magnitude correlate with:
    - Pre-hypo IOB deficit (lower IOB → less braking → bigger rebound)
    - Fasting duration (longer fast → bigger rescue meal)
    - Nadir depth (deeper → more counter-reg + more rescue)
    """
    print("\n" + "─" * 60)
    print("EXP-1604: Post-Hypo Rebound Characterization")
    print("─" * 60)

    per_patient = []
    all_rebounds = []  # (rebound_mg, pre_iob, fasting_min, nadir)

    for pid, pdata in sorted(patients_data.items()):
        glucose = pdata['glucose']
        carbs = pdata['carbs']
        iob = pdata['iob']
        episodes = pdata['episodes']
        n = len(glucose)

        rebounds = []
        for ep in episodes:
            nadir_idx = ep['nadir_idx']
            nadir_bg = ep['nadir']

            # Peak BG in 2h after nadir
            post_start = nadir_idx
            post_end = min(n, nadir_idx + POST_WINDOW_HOURS * STEPS_PER_HOUR)
            post_seg = glucose[post_start:post_end]
            valid_post = post_seg[np.isfinite(post_seg)]
            if len(valid_post) < 3:
                continue
            peak_post = float(np.max(valid_post))
            rebound_magnitude = peak_post - nadir_bg

            # Pre-hypo IOB
            pre_iob = _safe(iob, max(0, ep['start'] - 1))
            # Fasting duration
            fasting = _time_since_last_carbs(carbs, ep['start'])

            rebounds.append({
                'rebound_mg': rebound_magnitude,
                'peak_post_bg': peak_post,
                'nadir': nadir_bg,
                'pre_iob': pre_iob,
                'fasting_min': fasting,
            })
            if np.isfinite(pre_iob) and np.isfinite(fasting):
                all_rebounds.append((rebound_magnitude, pre_iob, fasting, nadir_bg))

        rebound_vals = [r['rebound_mg'] for r in rebounds]
        peaks = [r['peak_post_bg'] for r in rebounds]
        pct_rebound_above_180 = sum(1 for p in peaks if p > 180) / max(len(peaks), 1) * 100

        rec = {
            'pid': pid,
            'n_rebounds': len(rebounds),
            'mean_rebound_mg': round(float(np.mean(rebound_vals)), 1) if rebound_vals else None,
            'median_rebound_mg': round(float(np.median(rebound_vals)), 1) if rebound_vals else None,
            'max_rebound_mg': round(float(np.max(rebound_vals)), 1) if rebound_vals else None,
            'pct_rebound_above_180': round(pct_rebound_above_180, 1),
            'mean_peak_post_bg': round(float(np.mean(peaks)), 1) if peaks else None,
        }
        per_patient.append(rec)
        print(f"  {pid}: rebounds={len(rebounds)} "
              f"mean={rec['mean_rebound_mg']:.0f}mg "
              f"max={rec['max_rebound_mg']:.0f}mg "
              f">{180}={rec['pct_rebound_above_180']:.0f}%")

    # Correlations
    if len(all_rebounds) > 10:
        reb_arr = np.array(all_rebounds)
        rebound_mg = reb_arr[:, 0]
        pre_iob = reb_arr[:, 1]
        fasting = reb_arr[:, 2]
        nadir = reb_arr[:, 3]

        corr_iob = float(np.corrcoef(rebound_mg, pre_iob)[0, 1]) if np.std(pre_iob) > 0 else 0
        corr_fasting = float(np.corrcoef(rebound_mg, fasting)[0, 1]) if np.std(fasting) > 0 else 0
        corr_nadir = float(np.corrcoef(rebound_mg, nadir)[0, 1]) if np.std(nadir) > 0 else 0
    else:
        corr_iob = corr_fasting = corr_nadir = None

    results = {
        'name': 'EXP-1604: Post-Hypo Rebound Characterization',
        'per_patient': per_patient,
        'population': {
            'mean_rebound_mg': round(float(np.mean([r['mean_rebound_mg'] for r in per_patient
                                                      if r['mean_rebound_mg'] is not None])), 1),
            'pct_rebound_above_180': round(float(np.mean([r['pct_rebound_above_180'] for r in per_patient])), 1),
            'correlation_rebound_vs_iob': round(corr_iob, 3) if corr_iob is not None else None,
            'correlation_rebound_vs_fasting': round(corr_fasting, 3) if corr_fasting is not None else None,
            'correlation_rebound_vs_nadir': round(corr_nadir, 3) if corr_nadir is not None else None,
        },
    }
    print(f"\n  CORRELATIONS: rebound~IOB={corr_iob:.3f} "
          f"rebound~fasting={corr_fasting:.3f} "
          f"rebound~nadir={corr_nadir:.3f}")
    return results


# ── EXP-1605: Extended Residual Decomposition ─────────────────────────

def exp_1605_residual_decomposition(patients_data):
    """Decompose residuals into supply-side and demand-side components.

    Inspired by UVA/Padova where:
      dBG/dt = EGP + Ra - Uid - Uii - E + ...

    We approximate:
      residual(t) = actual_dBG(t) - (supply(t) - demand(t))

    Decomposition by attribution:
      1. When demand ≈ 0 and carbs ≈ 0 → residual ≈ hepatic_loss
         (unexplained supply = counter-regulatory, dawn phenomenon error)
      2. When supply ≈ hepatic_only and demand > 0 → residual ≈ -sensitivity_loss
         (unexplained demand = ISF mismatch, exercise)
      3. When both active → mixed (can't cleanly separate)

    We stratify by glucose range to see how the decomposition shifts
    during hypo vs normal range.
    """
    print("\n" + "─" * 60)
    print("EXP-1605: Extended Residual Decomposition")
    print("─" * 60)

    ranges = [
        ('severe_hypo', 0, 54),
        ('hypo', 54, 70),
        ('low_normal', 70, 100),
        ('in_range', 100, 180),
        ('high', 180, 250),
        ('very_high', 250, 500),
    ]

    # Collect residuals by range and attribution context
    range_data = {name: {
        'residual': [], 'supply': [], 'demand': [],
        'hepatic': [], 'carb_supply': [],
        'hepatic_attributed': [],   # residual when no carbs, low demand
        'sensitivity_attributed': [],  # residual when no carbs, high demand
        'mixed': [],  # residual when carbs present
    } for name, _, _ in ranges}

    for pid, pdata in sorted(patients_data.items()):
        glucose = pdata['glucose']
        sd = pdata['sd']
        residual = pdata['residual']
        n = min(len(glucose), len(residual))

        for i in range(1, n):
            bg = glucose[i]
            if not np.isfinite(bg) or not np.isfinite(residual[i]):
                continue

            for rname, lo, hi in ranges:
                if lo <= bg < hi:
                    rd = range_data[rname]
                    rd['residual'].append(residual[i])
                    rd['supply'].append(sd['supply'][i])
                    rd['demand'].append(sd['demand'][i])
                    rd['hepatic'].append(sd['hepatic'][i])
                    cs = sd['carb_supply'][i] if i < len(sd['carb_supply']) else 0
                    rd['carb_supply'].append(cs)

                    # Attribution context
                    demand_val = sd['demand'][i]
                    median_demand = np.nanmedian(sd['demand'])

                    if cs < 0.1:
                        if demand_val < median_demand * 0.3:
                            rd['hepatic_attributed'].append(residual[i])
                        else:
                            rd['sensitivity_attributed'].append(residual[i])
                    else:
                        rd['mixed'].append(residual[i])
                    break

    results = {'name': 'EXP-1605: Extended Residual Decomposition',
               'by_range': {}}

    for rname, lo, hi in ranges:
        rd = range_data[rname]
        n_points = len(rd['residual'])
        summary = {
            'n_points': n_points,
            'residual_mean': round(float(np.mean(rd['residual'])), 3) if rd['residual'] else None,
            'residual_std': round(float(np.std(rd['residual'])), 3) if rd['residual'] else None,
            'supply_mean': round(float(np.mean(rd['supply'])), 3) if rd['supply'] else None,
            'demand_mean': round(float(np.mean(rd['demand'])), 3) if rd['demand'] else None,
            'hepatic_mean': round(float(np.mean(rd['hepatic'])), 3) if rd['hepatic'] else None,
            'hepatic_attributed_mean': round(float(np.mean(rd['hepatic_attributed'])), 3) if rd['hepatic_attributed'] else None,
            'hepatic_attributed_n': len(rd['hepatic_attributed']),
            'sensitivity_attributed_mean': round(float(np.mean(rd['sensitivity_attributed'])), 3) if rd['sensitivity_attributed'] else None,
            'sensitivity_attributed_n': len(rd['sensitivity_attributed']),
            'mixed_mean': round(float(np.mean(rd['mixed'])), 3) if rd['mixed'] else None,
            'mixed_n': len(rd['mixed']),
        }
        results['by_range'][rname] = summary
        res_m = summary['residual_mean'] or 0
        hep_m = summary['hepatic_attributed_mean'] or 0
        sen_m = summary['sensitivity_attributed_mean'] or 0
        print(f"  {rname:15s}: n={n_points:>7d} residual={res_m:+.3f} "
              f"hepatic_attr={hep_m:+.3f} sensitivity_attr={sen_m:+.3f}")

    return results


# ── EXP-1606: Information Ceiling Analysis ────────────────────────────

def exp_1606_information_ceiling(patients_data):
    """Measure variance explained at each decomposition level.

    Level 0: Naive (predict dBG=0, glucose stays flat)
    Level 1: Supply - Demand (physics model)
    Level 2: Level 1 + residual AR(3) model
    Level 3: Level 2 + range-specific bias correction

    Measures R² and MAE for each level, stratified by glucose range,
    focusing on hypo vs in-range comparison.
    """
    print("\n" + "─" * 60)
    print("EXP-1606: Information Ceiling Analysis")
    print("─" * 60)

    ranges = [('hypo', 0, 70), ('in_range', 70, 180), ('high', 180, 500)]

    per_range = {}
    for rname, lo, hi in ranges:
        all_actual = []
        all_l0 = []
        all_l1 = []
        all_l2 = []
        all_l3 = []

        for pid, pdata in patients_data.items():
            glucose = pdata['glucose']
            sd = pdata['sd']
            residual = pdata['residual']
            n = min(len(glucose), len(sd['net']), len(residual))

            # Fit AR(3) on training portion
            train_end = int(n * 0.7)
            resid_train = residual[:train_end]
            valid_resid = resid_train[np.isfinite(resid_train)]

            # Simple AR(3) coefficients
            ar_coeffs = np.zeros(3)
            if len(valid_resid) > 20:
                for lag in range(1, 4):
                    x = valid_resid[:-lag] if lag < len(valid_resid) else valid_resid
                    y = valid_resid[lag:] if lag < len(valid_resid) else valid_resid
                    min_len = min(len(x), len(y))
                    if min_len > 10:
                        corr = np.corrcoef(x[:min_len], y[:min_len])[0, 1]
                        ar_coeffs[lag - 1] = corr if np.isfinite(corr) else 0

            # Range-specific bias from training data
            range_mask_train = ((glucose[:train_end] >= lo) &
                               (glucose[:train_end] < hi) &
                               np.isfinite(residual[:train_end]))
            if np.sum(range_mask_train) > 10:
                range_bias = float(np.mean(residual[:train_end][range_mask_train]))
            else:
                range_bias = 0.0

            # Evaluate on test portion
            for i in range(max(train_end, 4), n - 1):
                bg = glucose[i]
                if not (lo <= bg < hi) or not np.isfinite(bg):
                    continue
                actual_dbg = glucose[i + 1] - glucose[i] if np.isfinite(glucose[i + 1]) else np.nan
                if not np.isfinite(actual_dbg):
                    continue

                # Level 0: predict no change
                pred_l0 = 0.0
                # Level 1: physics (supply - demand)
                pred_l1 = sd['net'][i] if i < len(sd['net']) else 0.0
                # Level 2: physics + AR(3) residual correction
                ar_correction = 0.0
                for lag_idx in range(3):
                    lag = lag_idx + 1
                    if i - lag >= 0 and np.isfinite(residual[i - lag]):
                        ar_correction += ar_coeffs[lag_idx] * residual[i - lag]
                pred_l2 = pred_l1 + ar_correction * 0.3  # damped
                # Level 3: + range-specific bias
                pred_l3 = pred_l2 + range_bias

                all_actual.append(actual_dbg)
                all_l0.append(pred_l0)
                all_l1.append(pred_l1 if np.isfinite(pred_l1) else 0)
                all_l2.append(pred_l2 if np.isfinite(pred_l2) else 0)
                all_l3.append(pred_l3 if np.isfinite(pred_l3) else 0)

        if len(all_actual) < 20:
            per_range[rname] = {'n': len(all_actual), 'insufficient_data': True}
            continue

        actual = np.array(all_actual)
        ss_tot = np.sum((actual - np.mean(actual)) ** 2)

        level_results = {}
        for level_name, preds in [('L0_naive', all_l0), ('L1_physics', all_l1),
                                   ('L2_physics_ar', all_l2), ('L3_physics_ar_bias', all_l3)]:
            preds = np.array(preds)
            ss_res = np.sum((actual - preds) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
            mae = float(np.mean(np.abs(actual - preds)))
            level_results[level_name] = {
                'r2': round(float(r2), 4),
                'mae': round(mae, 3),
            }

        per_range[rname] = {'n': len(all_actual), 'levels': level_results}
        print(f"  {rname:10s} (n={len(all_actual):>6d}): "
              + " | ".join(f"{k}:R²={v['r2']:.3f},MAE={v['mae']:.2f}"
                           for k, v in level_results.items()))

    results = {
        'name': 'EXP-1606: Information Ceiling Analysis',
        'by_range': per_range,
    }
    return results


# ── Visualization Generation ──────────────────────────────────────────

def generate_figures(patients_data, results, figures_dir):
    """Generate all visualization figures."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("  matplotlib not available, skipping figures")
        return

    os.makedirs(figures_dir, exist_ok=True)

    # ── Fig 1: Supply-Demand Waterfall Around Hypo Nadir ──────────────
    print("  Generating Fig 1: Supply-demand waterfall...")
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    # Collect aligned traces: -2h to +2h around nadir (48 steps)
    window_steps = 48
    half = window_steps // 2
    traces = {'glucose': [], 'supply': [], 'demand': [], 'hepatic': [],
              'carb_supply': [], 'net': [], 'residual': [], 'iob': []}

    for pid, pdata in patients_data.items():
        glucose = pdata['glucose']
        sd = pdata['sd']
        residual = pdata['residual']
        iob = pdata['iob']
        n = len(glucose)

        for ep in pdata['episodes']:
            nadir_idx = ep['nadir_idx']
            start = nadir_idx - half
            end = nadir_idx + half
            if start < 0 or end > n:
                continue

            for key in ['supply', 'demand', 'hepatic', 'carb_supply', 'net']:
                traces[key].append(sd[key][start:end].copy())
            traces['glucose'].append(glucose[start:end].copy())
            traces['residual'].append(residual[start:end].copy())
            traces['iob'].append(iob[start:end].copy())

    time_axis = (np.arange(window_steps) - half) * 5  # minutes from nadir

    # Top panel: Glucose
    glucose_traces = np.array(traces['glucose'])
    ax = axes[0]
    mean_g = np.nanmean(glucose_traces, axis=0)
    std_g = np.nanstd(glucose_traces, axis=0)
    ax.fill_between(time_axis, mean_g - std_g, mean_g + std_g, alpha=0.2, color='tab:blue')
    ax.plot(time_axis, mean_g, 'tab:blue', lw=2, label='Glucose (mean±SD)')
    ax.axhline(70, color='red', ls='--', alpha=0.5, label='Hypo threshold (70)')
    ax.axhline(54, color='darkred', ls=':', alpha=0.5, label='Severe (54)')
    ax.axvline(0, color='gray', ls=':', alpha=0.3)
    ax.set_ylabel('Glucose (mg/dL)')
    ax.legend(fontsize=8)
    ax.set_title(f'Population Mean Hypo Episode (n={len(glucose_traces)} episodes)')

    # Middle panel: Supply vs Demand
    ax = axes[1]
    for key, color, label in [('supply', 'green', 'Supply (hepatic+carbs)'),
                               ('demand', 'red', 'Demand (insulin)'),
                               ('hepatic', 'olive', 'Hepatic only')]:
        arr = np.array(traces[key])
        mean_v = np.nanmean(arr, axis=0)
        std_v = np.nanstd(arr, axis=0)
        ax.fill_between(time_axis, mean_v - std_v, mean_v + std_v, alpha=0.1, color=color)
        ax.plot(time_axis, mean_v, color=color, lw=2, label=label)
    ax.axvline(0, color='gray', ls=':', alpha=0.3)
    ax.set_ylabel('mg/dL per 5min')
    ax.legend(fontsize=8)

    # Bottom panel: Net flux + Residual
    ax = axes[2]
    net_arr = np.array(traces['net'])
    resid_arr = np.array(traces['residual'])
    ax.fill_between(time_axis, 0, np.nanmean(net_arr, axis=0), alpha=0.3,
                     color='tab:purple', label='Net flux (supply-demand)')
    ax.plot(time_axis, np.nanmean(net_arr, axis=0), 'tab:purple', lw=2)
    ax.plot(time_axis, np.nanmean(resid_arr, axis=0), 'tab:orange', lw=2,
            label='Residual (unmodeled)')
    ax.axhline(0, color='black', ls='-', lw=0.5)
    ax.axvline(0, color='gray', ls=':', alpha=0.3)
    ax.set_ylabel('mg/dL per 5min')
    ax.set_xlabel('Minutes from nadir')
    ax.legend(fontsize=8)

    plt.tight_layout()
    fig.savefig(figures_dir / 'hypo-sd-fig1-waterfall.png', dpi=150, bbox_inches='tight')
    plt.close(fig)

    # ── Fig 2: Pre-Hypo Fasting Duration ──────────────────────────────
    print("  Generating Fig 2: Fasting duration...")
    r1601 = results['exp_1601']
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Left: Distribution of fasting durations before hypo
    fasting_data = []
    for pid, pdata in patients_data.items():
        for ep in pdata['episodes']:
            fd = _time_since_last_carbs(pdata['carbs'], ep['start'])
            if np.isfinite(fd) and fd < 1440:  # cap at 24h
                fasting_data.append(fd / 60)  # hours

    ax = axes[0]
    ax.hist(fasting_data, bins=30, alpha=0.7, color='tab:blue', edgecolor='white')
    median_fast = np.median(fasting_data) if fasting_data else 0
    ax.axvline(median_fast, color='red', ls='--', lw=2,
               label=f'Median: {median_fast:.1f}h')
    ax.set_xlabel('Hours since last carbs')
    ax.set_ylabel('Number of hypo episodes')
    ax.set_title('Fasting Duration Before Hypo Onset')
    ax.legend()

    # Right: Per-patient comparison of pre-hypo vs baseline fasting
    ax = axes[1]
    pids = sorted(patients_data.keys())
    pre_hypo_fasting = []
    baseline_fasting = []
    for pid in pids:
        pdata = patients_data[pid]
        hypo_f = []
        base_f = []
        for ep in pdata['episodes']:
            fd = _time_since_last_carbs(pdata['carbs'], ep['start'])
            if np.isfinite(fd):
                hypo_f.append(fd / 60)
        for i in range(0, len(pdata['glucose']), 36):
            if np.isfinite(pdata['glucose'][i]) and pdata['glucose'][i] >= 70:
                fd = _time_since_last_carbs(pdata['carbs'], i)
                if np.isfinite(fd):
                    base_f.append(fd / 60)
        pre_hypo_fasting.append(np.median(hypo_f) if hypo_f else 0)
        baseline_fasting.append(np.median(base_f) if base_f else 0)

    x = np.arange(len(pids))
    ax.bar(x - 0.15, pre_hypo_fasting, 0.3, label='Pre-hypo', color='tab:red', alpha=0.8)
    ax.bar(x + 0.15, baseline_fasting, 0.3, label='Baseline (in-range)', color='tab:blue', alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(pids)
    ax.set_ylabel('Median fasting duration (hours)')
    ax.set_title('Pre-Hypo vs Baseline Fasting Duration')
    ax.legend()

    plt.tight_layout()
    fig.savefig(figures_dir / 'hypo-sd-fig2-fasting.png', dpi=150, bbox_inches='tight')
    plt.close(fig)

    # ── Fig 3: IOB Trajectory Before Hypo ─────────────────────────────
    print("  Generating Fig 3: IOB trajectory...")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Left: Mean IOB trajectory -2h to nadir
    iob_traces = np.array(traces['iob'])
    pre_nadir = iob_traces[:, :half]  # -2h to nadir
    ax = axes[0]
    pre_time = time_axis[:half]
    mean_iob = np.nanmean(pre_nadir, axis=0)
    std_iob = np.nanstd(pre_nadir, axis=0)
    ax.fill_between(pre_time, mean_iob - std_iob, mean_iob + std_iob, alpha=0.2, color='tab:orange')
    ax.plot(pre_time, mean_iob, 'tab:orange', lw=2)
    ax.set_xlabel('Minutes before nadir')
    ax.set_ylabel('IOB (Units)')
    ax.set_title('IOB Trajectory Before Hypo Nadir')
    ax.axvline(0, color='gray', ls=':', alpha=0.3)

    # Right: IOB at onset per patient
    ax = axes[1]
    onset_iobs = []
    for pid in pids:
        pdata = patients_data[pid]
        patient_iobs = []
        for ep in pdata['episodes']:
            v = _safe(pdata['iob'], ep['start'])
            if np.isfinite(v):
                patient_iobs.append(v)
        onset_iobs.append(patient_iobs)

    bp = ax.boxplot(onset_iobs, labels=pids, patch_artist=True)
    for patch in bp['boxes']:
        patch.set_facecolor('tab:orange')
        patch.set_alpha(0.5)
    ax.set_ylabel('IOB at hypo onset (Units)')
    ax.set_title('IOB Distribution at Hypo Onset')

    plt.tight_layout()
    fig.savefig(figures_dir / 'hypo-sd-fig3-iob-trajectory.png', dpi=150, bbox_inches='tight')
    plt.close(fig)

    # ── Fig 4: Residual Decomposition by Range ────────────────────────
    print("  Generating Fig 4: Residual decomposition...")
    r1605 = results['exp_1605']
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    range_names = ['severe_hypo', 'hypo', 'low_normal', 'in_range', 'high', 'very_high']
    range_labels = ['<54', '54-70', '70-100', '100-180', '180-250', '>250']

    # Left: Total residual by range
    ax = axes[0]
    resid_means = []
    resid_stds = []
    for rn in range_names:
        rd = r1605['by_range'].get(rn, {})
        resid_means.append(rd.get('residual_mean', 0) or 0)
        resid_stds.append(rd.get('residual_std', 0) or 0)

    colors = ['darkred', 'red', 'gold', 'green', 'orange', 'darkred']
    x = np.arange(len(range_names))
    bars = ax.bar(x, resid_means, yerr=resid_stds, color=colors, alpha=0.7,
                  edgecolor='white', capsize=4)
    ax.set_xticks(x)
    ax.set_xticklabels(range_labels, fontsize=9)
    ax.set_xlabel('Glucose Range (mg/dL)')
    ax.set_ylabel('Mean Residual (mg/dL per 5min)')
    ax.set_title('Residual by Glucose Range\n(positive = model under-predicts rise)')
    ax.axhline(0, color='black', ls='-', lw=0.5)

    # Right: Attributed decomposition
    ax = axes[1]
    hep_attr = []
    sen_attr = []
    for rn in range_names:
        rd = r1605['by_range'].get(rn, {})
        hep_attr.append(rd.get('hepatic_attributed_mean', 0) or 0)
        sen_attr.append(rd.get('sensitivity_attributed_mean', 0) or 0)

    ax.bar(x - 0.15, hep_attr, 0.3, label='Hepatic-attributed\n(no carbs, low demand)',
           color='forestgreen', alpha=0.7)
    ax.bar(x + 0.15, sen_attr, 0.3, label='Sensitivity-attributed\n(no carbs, high demand)',
           color='steelblue', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(range_labels, fontsize=9)
    ax.set_xlabel('Glucose Range (mg/dL)')
    ax.set_ylabel('Mean Attributed Residual')
    ax.set_title('Residual Attribution:\nHepatic Loss vs Sensitivity Loss')
    ax.axhline(0, color='black', ls='-', lw=0.5)
    ax.legend(fontsize=8)

    plt.tight_layout()
    fig.savefig(figures_dir / 'hypo-sd-fig4-residual-decomposition.png', dpi=150,
                bbox_inches='tight')
    plt.close(fig)

    # ── Fig 5: Rebound Magnitude vs Context ───────────────────────────
    print("  Generating Fig 5: Rebound vs context...")
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    all_rebounds = []
    for pid, pdata in patients_data.items():
        glucose = pdata['glucose']
        for ep in pdata['episodes']:
            nadir_idx = ep['nadir_idx']
            post_end = min(len(glucose), nadir_idx + 24)
            post_seg = glucose[nadir_idx:post_end]
            valid = post_seg[np.isfinite(post_seg)]
            if len(valid) < 3:
                continue
            rebound = float(np.max(valid)) - ep['nadir']
            pre_iob = _safe(pdata['iob'], max(0, ep['start'] - 1))
            fasting = _time_since_last_carbs(pdata['carbs'], ep['start'])
            if np.isfinite(pre_iob) and np.isfinite(fasting):
                all_rebounds.append((rebound, pre_iob, fasting / 60, ep['nadir']))

    if all_rebounds:
        reb_arr = np.array(all_rebounds)

        # Rebound vs Pre-IOB
        ax = axes[0]
        ax.scatter(reb_arr[:, 1], reb_arr[:, 0], alpha=0.15, s=10, c='tab:orange')
        ax.set_xlabel('Pre-hypo IOB (Units)')
        ax.set_ylabel('Rebound magnitude (mg/dL)')
        r = np.corrcoef(reb_arr[:, 1], reb_arr[:, 0])[0, 1]
        ax.set_title(f'Rebound vs IOB (r={r:.3f})')

        # Rebound vs Fasting duration
        ax = axes[1]
        fasting_capped = np.minimum(reb_arr[:, 2], 12)
        ax.scatter(fasting_capped, reb_arr[:, 0], alpha=0.15, s=10, c='tab:blue')
        ax.set_xlabel('Fasting duration (hours, capped 12)')
        ax.set_ylabel('Rebound magnitude (mg/dL)')
        r = np.corrcoef(fasting_capped, reb_arr[:, 0])[0, 1]
        ax.set_title(f'Rebound vs Fasting (r={r:.3f})')

        # Rebound vs Nadir depth
        ax = axes[2]
        ax.scatter(reb_arr[:, 3], reb_arr[:, 0], alpha=0.15, s=10, c='tab:red')
        ax.set_xlabel('Nadir (mg/dL)')
        ax.set_ylabel('Rebound magnitude (mg/dL)')
        r = np.corrcoef(reb_arr[:, 3], reb_arr[:, 0])[0, 1]
        ax.set_title(f'Rebound vs Nadir (r={r:.3f})')

    plt.tight_layout()
    fig.savefig(figures_dir / 'hypo-sd-fig5-rebound-context.png', dpi=150,
                bbox_inches='tight')
    plt.close(fig)

    # ── Fig 6: Information Ceiling ────────────────────────────────────
    print("  Generating Fig 6: Information ceiling...")
    r1606 = results['exp_1606']
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    range_order = ['hypo', 'in_range', 'high']
    range_display = ['Hypo (<70)', 'In-Range (70-180)', 'High (>180)']
    level_names = ['L0_naive', 'L1_physics', 'L2_physics_ar', 'L3_physics_ar_bias']
    level_display = ['L0: Naive\n(dBG=0)', 'L1: Supply-\nDemand', 'L2: +AR(3)\nResidual',
                     'L3: +Range\nBias']
    level_colors = ['lightgray', 'tab:blue', 'tab:orange', 'tab:green']

    # R² comparison
    ax = axes[0]
    x = np.arange(len(range_order))
    width = 0.18
    for i, (ln, ld, lc) in enumerate(zip(level_names, level_display, level_colors)):
        r2_vals = []
        for rn in range_order:
            rd = r1606['by_range'].get(rn, {})
            if 'levels' in rd:
                r2_vals.append(rd['levels'].get(ln, {}).get('r2', 0))
            else:
                r2_vals.append(0)
        ax.bar(x + (i - 1.5) * width, r2_vals, width, label=ld, color=lc, alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(range_display, fontsize=9)
    ax.set_ylabel('R²')
    ax.set_title('Variance Explained by Decomposition Level')
    ax.legend(fontsize=7, loc='upper right')

    # MAE comparison
    ax = axes[1]
    for i, (ln, ld, lc) in enumerate(zip(level_names, level_display, level_colors)):
        mae_vals = []
        for rn in range_order:
            rd = r1606['by_range'].get(rn, {})
            if 'levels' in rd:
                mae_vals.append(rd['levels'].get(ln, {}).get('mae', 0))
            else:
                mae_vals.append(0)
        ax.bar(x + (i - 1.5) * width, mae_vals, width, label=ld, color=lc, alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(range_display, fontsize=9)
    ax.set_ylabel('MAE (mg/dL per 5min)')
    ax.set_title('Prediction Error by Decomposition Level')
    ax.legend(fontsize=7, loc='upper right')

    plt.tight_layout()
    fig.savefig(figures_dir / 'hypo-sd-fig6-information-ceiling.png', dpi=150,
                bbox_inches='tight')
    plt.close(fig)

    print("  All 6 figures generated.")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='EXP-1601 to 1606: Hypo Supply-Demand Decomposition')
    parser.add_argument('--patients-dir', default=str(PATIENTS_DIR))
    parser.add_argument('--max-patients', type=int, default=11)
    parser.add_argument('--figures', action='store_true', default=True,
                        help='Generate visualization figures')
    parser.add_argument('--no-figures', dest='figures', action='store_false')
    parser.add_argument('--output-dir', default=str(RESULTS_DIR))
    args = parser.parse_args()

    print("=" * 60)
    print("Hypoglycemia Supply-Demand Decomposition Analysis")
    print("=" * 60)

    # Load patients
    print("\nLoading patients...")
    raw_patients = load_patients(patients_dir=args.patients_dir,
                                  max_patients=args.max_patients)

    # Pre-compute supply-demand and residuals for all patients
    print("\nComputing supply-demand decomposition...")
    patients_data = {}
    for p in raw_patients:
        pid = p['name']
        df = p['df']
        pk = p['pk']
        glucose = df['glucose'].values.astype(float)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0.0)
        carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(df))

        sd = compute_supply_demand(df, pk)
        residual = _compute_residual(glucose, sd['net'])
        episodes = detect_hypo_episodes(glucose)

        patients_data[pid] = {
            'glucose': glucose,
            'iob': iob,
            'carbs': carbs,
            'sd': sd,
            'residual': residual,
            'episodes': episodes,
            'df': df,
            'pk': pk,
        }
        print(f"  {pid}: {len(episodes)} hypo episodes, "
              f"supply={np.nanmean(sd['supply']):.2f} demand={np.nanmean(sd['demand']):.2f} "
              f"residual_mean={np.nanmean(residual):.3f}")

    # Run experiments
    import time
    t0 = time.time()

    results = {}
    results['exp_1601'] = exp_1601_pre_hypo_context(patients_data)
    results['exp_1602'] = exp_1602_phase_decomposition(patients_data)
    results['exp_1603'] = exp_1603_rescue_carbs(patients_data)
    results['exp_1604'] = exp_1604_rebound_characterization(patients_data)
    results['exp_1605'] = exp_1605_residual_decomposition(patients_data)
    results['exp_1606'] = exp_1606_information_ceiling(patients_data)

    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"All experiments completed in {elapsed:.1f}s")

    # Save results
    output_dir = Path(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)
    for exp_key, exp_results in results.items():
        exp_id = exp_key.replace('exp_', '')
        outpath = output_dir / f'exp-{exp_id}_hypo_supply_demand.json'
        # Convert numpy types for JSON
        def _convert(obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj) if np.isfinite(obj) else None
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj

        with open(outpath, 'w') as f:
            json.dump(exp_results, f, indent=2, default=_convert)
        print(f"  Saved {outpath}")

    # Generate figures
    if args.figures:
        print("\nGenerating figures...")
        generate_figures(patients_data, results, FIGURES_DIR)

    print("\nDone.")
    return results


if __name__ == '__main__':
    main()
