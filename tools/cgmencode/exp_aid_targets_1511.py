#!/usr/bin/env python3
"""EXP-1511 to EXP-1518: AID-specific TBR/CV target validation.

Hypothesis: ADA 2019 consensus targets (TBR<4%, CV<36%) were designed for
general diabetes management, not closed-loop AID systems. AID systems
(Loop, Trio, AAPS) actively create brief algorithmic lows via temp basals
then auto-suspend. We need to determine empirically whether AID-specific
thresholds are needed.

Experiments:
  EXP-1511  Hypo episode duration distribution
  EXP-1512  AID response during lows
  EXP-1513  Recovery dynamics by episode type
  EXP-1514  Duration-weighted TBR metrics
  EXP-1515  AID-specific threshold search
  EXP-1516  CV in AID context
  EXP-1517  Regrade under AID-specific targets
  EXP-1518  Brief low predictive value

Run:
    PYTHONPATH=tools python -m cgmencode.exp_aid_targets_1511 --detail --save
    PYTHONPATH=tools python -m cgmencode.exp_aid_targets_1511 --exp 1511 1514
"""

import argparse
import json
import math
import os
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from cgmencode.exp_metabolic_flux import load_patients as _load_patients

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PATIENTS_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', 'externals', 'ns-data', 'patients')
RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'

STEPS_PER_HOUR = 12          # 5-min intervals
STEP_MINUTES = 5
STEPS_PER_DAY = 24 * STEPS_PER_HOUR  # 288

HYPO_THRESHOLD = 70          # mg/dL
RECOVERY_TARGET = 80         # mg/dL
HYPER_THRESHOLD = 180        # mg/dL
TIR_LO = 70
TIR_HI = 180

# Episode duration classifications (minutes)
BRIEF_MAX = 15
MODERATE_MAX = 45

# ADA consensus targets
ADA_TBR = 4.0               # %
ADA_CV = 36.0               # %
ADA_TIR = 70.0              # %

# AID-specific proposed targets
AID_TBR_STANDARD = 4.0      # % (unchanged — real hypos still matter)
AID_TBR_SUSTAINED = 1.0     # % (only episodes >15 min)
AID_CV = 40.0               # % (relaxed for AID)
AID_TIR = 70.0              # % (unchanged)

# v10 scoring weights
SCORE_WEIGHTS = {'tir': 60, 'basal': 15, 'cr': 15, 'isf': 5, 'cv': 5}

# ---------------------------------------------------------------------------
# Experiment registry
# ---------------------------------------------------------------------------

EXPERIMENTS = {}


def register(exp_id, title):
    """Decorator to register experiment functions."""
    def decorator(fn):
        EXPERIMENTS[exp_id] = (title, fn)
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_patients(max_patients=11):
    """Load patient data with CGM + insulin channels."""
    return _load_patients(PATIENTS_DIR, max_patients=max_patients)


def _extract_channels(patient):
    """Extract numpy arrays from a patient dict."""
    df = patient['df']
    glucose = df['glucose'].values.astype(float)
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(df))
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(df))
    temp_rate = df['temp_rate'].values.astype(float) if 'temp_rate' in df.columns else np.zeros(len(df))
    iob = df['iob'].values.astype(float) if 'iob' in df.columns else np.zeros(len(df))
    cob = df['cob'].values.astype(float) if 'cob' in df.columns else np.zeros(len(df))
    return {
        'glucose': glucose,
        'bolus': bolus,
        'carbs': carbs,
        'temp_rate': temp_rate,
        'iob': iob,
        'cob': cob,
        'timestamps': df.index,
    }


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def find_hypo_episodes(glucose, threshold=HYPO_THRESHOLD):
    """Find contiguous episodes where glucose < threshold.

    Returns list of dicts:
      start_idx, end_idx, duration_min, nadir, nadir_idx
    Skips NaN regions.
    """
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
            end = i  # exclusive
            duration = (end - start) * STEP_MINUTES
            episodes.append({
                'start_idx': start,
                'end_idx': end,
                'duration_min': duration,
                'nadir': float(nadir),
                'nadir_idx': nadir_idx,
            })
        else:
            i += 1
    return episodes


def classify_episode(ep):
    """Classify episode as brief / moderate / sustained."""
    d = ep['duration_min']
    if d < BRIEF_MAX:
        return 'brief'
    elif d <= MODERATE_MAX:
        return 'moderate'
    else:
        return 'sustained'


def compute_tir(glucose, lo=TIR_LO, hi=TIR_HI):
    """Time-in-range % (ignoring NaNs)."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return 0.0
    return float(np.mean((valid >= lo) & (valid <= hi)) * 100)


def compute_tbr(glucose, threshold=HYPO_THRESHOLD):
    """Time-below-range % (ignoring NaNs)."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return 0.0
    return float(np.mean(valid < threshold) * 100)


def compute_tar(glucose, threshold=HYPER_THRESHOLD):
    """Time-above-range % (ignoring NaNs)."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return 0.0
    return float(np.mean(valid > threshold) * 100)


def compute_cv(glucose):
    """Coefficient of variation % (ignoring NaNs)."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) < 2:
        return 0.0
    m = np.mean(valid)
    if m == 0:
        return 0.0
    return float(np.std(valid) / m * 100)


def get_hour_mask(timestamps, hour_start, hour_end):
    """Boolean mask for timestamps whose hour is in [hour_start, hour_end)."""
    hours = np.array([t.hour for t in timestamps])
    if hour_start < hour_end:
        return (hours >= hour_start) & (hours < hour_end)
    else:  # wraps midnight
        return (hours >= hour_start) | (hours < hour_end)


def compute_recovery_time(glucose, nadir_idx, target=RECOVERY_TARGET, max_steps=72):
    """Steps from nadir until glucose >= target. Returns minutes or NaN."""
    for offset in range(1, max_steps + 1):
        idx = nadir_idx + offset
        if idx >= len(glucose):
            return float('nan')
        if np.isnan(glucose[idx]):
            continue
        if glucose[idx] >= target:
            return offset * STEP_MINUTES
    return float('nan')


def _safe_mean(values):
    """Mean of non-NaN values, or NaN if empty."""
    arr = np.array(values, dtype=float)
    valid = arr[~np.isnan(arr)]
    return float(np.mean(valid)) if len(valid) > 0 else float('nan')


def _safe_median(values):
    """Median of non-NaN values, or NaN if empty."""
    arr = np.array(values, dtype=float)
    valid = arr[~np.isnan(arr)]
    return float(np.median(valid)) if len(valid) > 0 else float('nan')


def _safe_corr(x, y):
    """Pearson correlation, or NaN if insufficient data."""
    x = np.array(x, dtype=float)
    y = np.array(y, dtype=float)
    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask], y[mask]
    if len(x) < 3:
        return float('nan')
    sx, sy = np.std(x), np.std(y)
    if sx == 0 or sy == 0:
        return float('nan')
    return float(np.corrcoef(x, y)[0, 1])


# ---------------------------------------------------------------------------
# v10 scoring helpers
# ---------------------------------------------------------------------------

def v10_safety_penalty(tbr, cv):
    """ADA-based safety penalty for v10 scoring.

    Penalizes TBR>4% and CV>36%.
    """
    penalty = 0.0
    if tbr > ADA_TBR:
        penalty += min((tbr - ADA_TBR) * 5, 20)
    if cv > ADA_CV:
        penalty += min((cv - ADA_CV) * 2, 10)
    return penalty


def v10_aid_safety_penalty(tbr_sustained, cv):
    """AID-specific safety penalty: only sustained TBR counts."""
    penalty = 0.0
    if tbr_sustained > AID_TBR_SUSTAINED:
        penalty += min((tbr_sustained - AID_TBR_SUSTAINED) * 5, 20)
    if cv > AID_CV:
        penalty += min((cv - AID_CV) * 2, 10)
    return penalty


def compute_v10_score(tir, tbr, cv):
    """Simplified v10 score: TIR-weighted minus safety penalty."""
    base = tir * SCORE_WEIGHTS['tir'] / 100.0
    penalty = v10_safety_penalty(tbr, cv)
    return max(0, base - penalty)


def score_to_grade(score):
    """Map v10 score to letter grade."""
    if score >= 50:
        return 'A'
    elif score >= 40:
        return 'B'
    elif score >= 30:
        return 'C'
    elif score >= 20:
        return 'D'
    else:
        return 'F'


# ═══════════════════════════════════════════════════════════════════════════
# EXP-1511: Hypo Episode Duration Distribution
# ═══════════════════════════════════════════════════════════════════════════

@register(1511, "Hypo Episode Duration Distribution")
def exp_1511(patients, args):
    """Classify hypo episodes by duration and measure TBR contribution."""
    per_patient = {}
    agg_categories = defaultdict(lambda: {'count': 0, 'total_min': 0})

    for pat in patients:
        ch = _extract_channels(pat)
        glucose = ch['glucose']
        name = pat['name']
        episodes = find_hypo_episodes(glucose)

        cats = {'brief': [], 'moderate': [], 'sustained': []}
        for ep in episodes:
            cat = classify_episode(ep)
            cats[cat].append(ep)

        total_tbr_min = sum(ep['duration_min'] for ep in episodes)
        total_valid = int(np.sum(~np.isnan(glucose)))

        cat_stats = {}
        for cat_name, eps in cats.items():
            cat_min = sum(e['duration_min'] for e in eps)
            pct_of_tbr = (cat_min / total_tbr_min * 100) if total_tbr_min > 0 else 0
            nadirs = [e['nadir'] for e in eps]
            cat_stats[cat_name] = {
                'count': len(eps),
                'total_minutes': cat_min,
                'pct_of_tbr': round(pct_of_tbr, 1),
                'mean_duration': round(cat_min / len(eps), 1) if eps else 0,
                'mean_nadir': round(_safe_mean(nadirs), 1) if nadirs else None,
                'min_nadir': round(min(nadirs), 1) if nadirs else None,
            }
            agg_categories[cat_name]['count'] += len(eps)
            agg_categories[cat_name]['total_min'] += cat_min

        std_tbr = compute_tbr(glucose)
        per_patient[name] = {
            'total_episodes': len(episodes),
            'total_tbr_pct': round(std_tbr, 2),
            'total_tbr_minutes': total_tbr_min,
            'total_valid_steps': total_valid,
            'categories': cat_stats,
        }

        if args.detail:
            print(f"\n  {name}: {len(episodes)} episodes, TBR={std_tbr:.2f}%")
            for cn, cs in cat_stats.items():
                print(f"    {cn:>10s}: {cs['count']:3d} episodes, "
                      f"{cs['total_minutes']:5d} min ({cs['pct_of_tbr']:5.1f}% of TBR)")

    # Aggregate
    agg_total = sum(v['total_min'] for v in agg_categories.values())
    aggregate = {}
    for cat_name, vals in agg_categories.items():
        aggregate[cat_name] = {
            'total_episodes': vals['count'],
            'total_minutes': vals['total_min'],
            'pct_of_all_tbr': round(vals['total_min'] / agg_total * 100, 1) if agg_total > 0 else 0,
        }

    print(f"\n  Aggregate across {len(patients)} patients:")
    print(f"    Total hypo time: {agg_total} minutes")
    for cn, cs in aggregate.items():
        print(f"    {cn:>10s}: {cs['total_episodes']:4d} episodes, "
              f"{cs['total_minutes']:6d} min ({cs['pct_of_all_tbr']:5.1f}%)")

    return {
        'experiment': 'EXP-1511',
        'title': 'Hypo Episode Duration Distribution',
        'hypothesis': 'Most TBR in AID users comes from brief algorithmic dips, not sustained lows.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }


# ═══════════════════════════════════════════════════════════════════════════
# EXP-1512: AID Response During Lows
# ═══════════════════════════════════════════════════════════════════════════

@register(1512, "AID Response During Lows")
def exp_1512(patients, args):
    """Determine what fraction of lows the AID system is actively handling."""
    per_patient = {}

    for pat in patients:
        ch = _extract_channels(pat)
        glucose, temp_rate, iob = ch['glucose'], ch['temp_rate'], ch['iob']
        name = pat['name']

        # Patient-level median temp_rate (baseline)
        valid_tr = temp_rate[~np.isnan(temp_rate)]
        median_tr = float(np.median(valid_tr)) if len(valid_tr) > 0 else 0.0

        episodes = find_hypo_episodes(glucose)
        managed = []
        unmanaged = []

        for ep in episodes:
            s, e = ep['start_idx'], ep['end_idx']
            ep_tr = temp_rate[s:e]
            ep_iob = iob[s:e]
            ep_tr_valid = ep_tr[~np.isnan(ep_tr)]

            # AID managing = temp_rate below median (insulin reduced/suspended)
            tr_below_median = (np.mean(ep_tr_valid < median_tr) > 0.5) if len(ep_tr_valid) > 0 else False

            # IOB decreasing = system responding
            iob_valid = ep_iob[~np.isnan(ep_iob)]
            iob_decreasing = False
            if len(iob_valid) >= 2:
                iob_decreasing = iob_valid[-1] < iob_valid[0]

            ep_info = dict(ep)
            ep_info['mean_temp_rate'] = float(np.nanmean(ep_tr)) if len(ep_tr_valid) > 0 else None
            ep_info['iob_decreasing'] = bool(iob_decreasing)
            ep_info['aid_managing'] = bool(tr_below_median or iob_decreasing)

            if tr_below_median or iob_decreasing:
                managed.append(ep_info)
            else:
                unmanaged.append(ep_info)

        managed_min = sum(e['duration_min'] for e in managed)
        unmanaged_min = sum(e['duration_min'] for e in unmanaged)
        total_min = managed_min + unmanaged_min
        managed_frac = managed_min / total_min if total_min > 0 else 0

        per_patient[name] = {
            'median_temp_rate': round(median_tr, 3),
            'total_episodes': len(episodes),
            'managed_count': len(managed),
            'unmanaged_count': len(unmanaged),
            'managed_minutes': managed_min,
            'unmanaged_minutes': unmanaged_min,
            'managed_fraction': round(managed_frac, 3),
            'managed_mean_duration': round(_safe_mean([e['duration_min'] for e in managed]), 1),
            'unmanaged_mean_duration': round(_safe_mean([e['duration_min'] for e in unmanaged]), 1),
        }

        if args.detail:
            print(f"\n  {name}: {len(managed)}/{len(episodes)} managed "
                  f"({managed_frac*100:.1f}%), median_tr={median_tr:.3f}")

    # Aggregate
    all_managed_frac = [p['managed_fraction'] for p in per_patient.values()]
    aggregate = {
        'mean_managed_fraction': round(_safe_mean(all_managed_frac), 3),
        'median_managed_fraction': round(_safe_median(all_managed_frac), 3),
        'n_patients': len(per_patient),
    }
    print(f"\n  Aggregate: {aggregate['mean_managed_fraction']*100:.1f}% of hypo time "
          f"is AID-managed (median {aggregate['median_managed_fraction']*100:.1f}%)")

    return {
        'experiment': 'EXP-1512',
        'title': 'AID Response During Lows',
        'hypothesis': 'Most lows in AID users are actively managed by the system.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }


# ═══════════════════════════════════════════════════════════════════════════
# EXP-1513: Recovery Dynamics by Episode Type
# ═══════════════════════════════════════════════════════════════════════════

@register(1513, "Recovery Dynamics by Episode Type")
def exp_1513(patients, args):
    """Measure recovery time from nadir back to >=80 by episode type and AID response."""
    per_patient = {}
    agg_recovery = defaultdict(list)

    for pat in patients:
        ch = _extract_channels(pat)
        glucose, temp_rate, iob = ch['glucose'], ch['temp_rate'], ch['iob']
        name = pat['name']

        valid_tr = temp_rate[~np.isnan(temp_rate)]
        median_tr = float(np.median(valid_tr)) if len(valid_tr) > 0 else 0.0
        episodes = find_hypo_episodes(glucose)

        recovery_by_cat = defaultdict(list)
        recovery_by_mgmt = {'managed': [], 'unmanaged': []}

        for ep in episodes:
            cat = classify_episode(ep)
            rec_min = compute_recovery_time(glucose, ep['nadir_idx'])

            # Determine if AID-managed
            s, e = ep['start_idx'], ep['end_idx']
            ep_tr = temp_rate[s:e]
            ep_tr_valid = ep_tr[~np.isnan(ep_tr)]
            tr_below = (np.mean(ep_tr_valid < median_tr) > 0.5) if len(ep_tr_valid) > 0 else False
            ep_iob = iob[s:e]
            iob_valid = ep_iob[~np.isnan(ep_iob)]
            iob_dec = (iob_valid[-1] < iob_valid[0]) if len(iob_valid) >= 2 else False
            is_managed = tr_below or iob_dec

            recovery_by_cat[cat].append(rec_min)
            mgmt_key = 'managed' if is_managed else 'unmanaged'
            recovery_by_mgmt[mgmt_key].append(rec_min)

            agg_recovery[f"{cat}_{mgmt_key}"].append(rec_min)

        cat_recovery = {}
        for cat_name in ['brief', 'moderate', 'sustained']:
            vals = recovery_by_cat.get(cat_name, [])
            cat_recovery[cat_name] = {
                'count': len(vals),
                'mean_recovery_min': round(_safe_mean(vals), 1),
                'median_recovery_min': round(_safe_median(vals), 1),
            }

        mgmt_recovery = {}
        for key in ['managed', 'unmanaged']:
            vals = recovery_by_mgmt[key]
            mgmt_recovery[key] = {
                'count': len(vals),
                'mean_recovery_min': round(_safe_mean(vals), 1),
                'median_recovery_min': round(_safe_median(vals), 1),
            }

        per_patient[name] = {
            'by_category': cat_recovery,
            'by_management': mgmt_recovery,
        }

        if args.detail:
            print(f"\n  {name}:")
            for cn in ['brief', 'moderate', 'sustained']:
                cs = cat_recovery[cn]
                print(f"    {cn:>10s}: n={cs['count']:3d}, "
                      f"mean={cs['mean_recovery_min']:5.1f}min, "
                      f"median={cs['median_recovery_min']:5.1f}min")

    # Aggregate
    aggregate = {}
    for key, vals in agg_recovery.items():
        aggregate[key] = {
            'count': len(vals),
            'mean_recovery_min': round(_safe_mean(vals), 1),
            'median_recovery_min': round(_safe_median(vals), 1),
        }

    print(f"\n  Recovery dynamics across {len(patients)} patients:")
    for key in sorted(aggregate.keys()):
        s = aggregate[key]
        print(f"    {key:>25s}: n={s['count']:4d}, "
              f"mean={s['mean_recovery_min']:5.1f}min")

    return {
        'experiment': 'EXP-1513',
        'title': 'Recovery Dynamics by Episode Type',
        'hypothesis': 'AID-managed lows recover faster, confirming they are less dangerous.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }


# ═══════════════════════════════════════════════════════════════════════════
# EXP-1514: Duration-Weighted TBR Metrics
# ═══════════════════════════════════════════════════════════════════════════

@register(1514, "Duration-Weighted TBR Metrics")
def exp_1514(patients, args):
    """Compute standard, duration-weighted, severity-weighted, and combined TBR."""
    per_patient = {}

    for pat in patients:
        ch = _extract_channels(pat)
        glucose = ch['glucose']
        name = pat['name']
        valid_glucose = glucose[~np.isnan(glucose)]
        n_valid = len(valid_glucose)

        episodes = find_hypo_episodes(glucose)
        std_tbr = compute_tbr(glucose)

        # Duration-weighted: weight = (duration/5)^2
        # A 5-min dip = 1, 30-min = 36, 60-min = 144
        dur_weighted_sum = 0.0
        sev_weighted_sum = 0.0
        combined_sum = 0.0

        for ep in episodes:
            steps = ep['duration_min'] // STEP_MINUTES
            dur_weight = (ep['duration_min'] / STEP_MINUTES) ** 2
            dur_weighted_sum += dur_weight

            # Severity: for each step in episode, weight = (70 - glucose)^2 / 100
            s, e = ep['start_idx'], ep['end_idx']
            ep_glucose = glucose[s:e]
            for g in ep_glucose:
                if not np.isnan(g) and g < HYPO_THRESHOLD:
                    sev = (HYPO_THRESHOLD - g) ** 2 / 100.0
                    sev_weighted_sum += sev

            # Combined: duration_weight * mean_severity
            ep_below = ep_glucose[~np.isnan(ep_glucose) & (ep_glucose < HYPO_THRESHOLD)]
            if len(ep_below) > 0:
                mean_sev = np.mean((HYPO_THRESHOLD - ep_below) ** 2 / 100.0)
                combined_sum += dur_weight * mean_sev

        # Normalize: divide by total valid steps to get comparable %
        dur_weighted_tbr = dur_weighted_sum / n_valid * 100 if n_valid > 0 else 0
        sev_weighted_tbr = sev_weighted_sum / n_valid * 100 if n_valid > 0 else 0
        combined_tbr = combined_sum / n_valid * 100 if n_valid > 0 else 0

        per_patient[name] = {
            'standard_tbr': round(std_tbr, 3),
            'duration_weighted_tbr': round(dur_weighted_tbr, 4),
            'severity_weighted_tbr': round(sev_weighted_tbr, 4),
            'combined_tbr': round(combined_tbr, 4),
            'n_episodes': len(episodes),
            'n_valid': n_valid,
        }

        if args.detail:
            print(f"\n  {name}: std={std_tbr:.2f}%, dur_w={dur_weighted_tbr:.4f}, "
                  f"sev_w={sev_weighted_tbr:.4f}, comb={combined_tbr:.4f}")

    # Rank patients by each metric
    names = list(per_patient.keys())
    rank_std = sorted(names, key=lambda n: per_patient[n]['standard_tbr'], reverse=True)
    rank_dur = sorted(names, key=lambda n: per_patient[n]['duration_weighted_tbr'], reverse=True)
    rank_sev = sorted(names, key=lambda n: per_patient[n]['severity_weighted_tbr'], reverse=True)
    rank_comb = sorted(names, key=lambda n: per_patient[n]['combined_tbr'], reverse=True)

    # Compute rank changes
    rank_changes = {}
    for name in names:
        std_rank = rank_std.index(name) + 1
        dur_rank = rank_dur.index(name) + 1
        sev_rank = rank_sev.index(name) + 1
        comb_rank = rank_comb.index(name) + 1
        rank_changes[name] = {
            'standard_rank': std_rank,
            'duration_rank': dur_rank,
            'severity_rank': sev_rank,
            'combined_rank': comb_rank,
            'max_rank_change': max(abs(std_rank - dur_rank),
                                   abs(std_rank - sev_rank),
                                   abs(std_rank - comb_rank)),
        }

    print(f"\n  Risk ranking comparison:")
    print(f"    {'Patient':>10s}  {'Std':>4s}  {'Dur':>4s}  {'Sev':>4s}  {'Comb':>4s}  {'MaxΔ':>5s}")
    for name in rank_std:
        rc = rank_changes[name]
        print(f"    {name:>10s}  {rc['standard_rank']:4d}  {rc['duration_rank']:4d}  "
              f"{rc['severity_rank']:4d}  {rc['combined_rank']:4d}  {rc['max_rank_change']:5d}")

    rankings_changed = sum(1 for r in rank_changes.values() if r['max_rank_change'] > 0)
    aggregate = {
        'n_patients': len(names),
        'rankings_changed': rankings_changed,
        'rank_changes': rank_changes,
    }

    return {
        'experiment': 'EXP-1514',
        'title': 'Duration-Weighted TBR Metrics',
        'hypothesis': 'Weighted metrics change patient risk ranking vs standard TBR.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }


# ═══════════════════════════════════════════════════════════════════════════
# EXP-1515: AID-Specific Threshold Search
# ═══════════════════════════════════════════════════════════════════════════

@register(1515, "AID-Specific Threshold Search")
def exp_1515(patients, args):
    """Search for natural TBR threshold that separates good vs needs-adjustment."""
    thresholds = [round(t * 0.5, 1) for t in range(2, 21)]  # 1.0% to 10.0%

    # Pre-compute per-patient metrics
    patient_metrics = {}
    for pat in patients:
        ch = _extract_channels(pat)
        glucose = ch['glucose']
        name = pat['name']
        n_valid = int(np.sum(~np.isnan(glucose)))

        episodes = find_hypo_episodes(glucose)
        std_tbr = compute_tbr(glucose)

        # Duration-weighted TBR
        dur_sum = sum((ep['duration_min'] / STEP_MINUTES) ** 2 for ep in episodes)
        dur_tbr = dur_sum / n_valid * 100 if n_valid > 0 else 0

        # Severity-weighted TBR
        sev_sum = 0.0
        for ep in episodes:
            s, e = ep['start_idx'], ep['end_idx']
            eg = glucose[s:e]
            for g in eg:
                if not np.isnan(g) and g < HYPO_THRESHOLD:
                    sev_sum += (HYPO_THRESHOLD - g) ** 2 / 100.0
        sev_tbr = sev_sum / n_valid * 100 if n_valid > 0 else 0

        # Sustained-only TBR (episodes > 15 min)
        sustained_min = sum(ep['duration_min'] for ep in episodes
                           if ep['duration_min'] >= BRIEF_MAX)
        total_min = n_valid * STEP_MINUTES
        sustained_tbr = sustained_min / total_min * 100 if total_min > 0 else 0

        # Overnight TBR (0:00-6:00)
        ts = ch['timestamps']
        overnight_mask = get_hour_mask(ts, 0, 6)
        overnight_glucose = glucose[overnight_mask]
        overnight_tbr = compute_tbr(overnight_glucose)

        patient_metrics[name] = {
            'standard_tbr': std_tbr,
            'duration_weighted_tbr': dur_tbr,
            'severity_weighted_tbr': sev_tbr,
            'sustained_tbr': sustained_tbr,
            'overnight_tbr': overnight_tbr,
        }

    # Threshold sweep
    threshold_results = []
    for thresh in thresholds:
        exceed_std = sum(1 for m in patient_metrics.values() if m['standard_tbr'] > thresh)
        exceed_dur = sum(1 for m in patient_metrics.values() if m['duration_weighted_tbr'] > thresh)
        exceed_sev = sum(1 for m in patient_metrics.values() if m['severity_weighted_tbr'] > thresh)
        exceed_sus = sum(1 for m in patient_metrics.values() if m['sustained_tbr'] > thresh)
        exceed_night = sum(1 for m in patient_metrics.values() if m['overnight_tbr'] > thresh)

        threshold_results.append({
            'threshold': thresh,
            'exceed_standard': exceed_std,
            'exceed_duration_weighted': exceed_dur,
            'exceed_severity_weighted': exceed_sev,
            'exceed_sustained': exceed_sus,
            'exceed_overnight': exceed_night,
        })

    # Find natural breaks: where the biggest drop in exceedance count occurs
    std_counts = [r['exceed_standard'] for r in threshold_results]
    max_drop = 0
    natural_break = thresholds[0]
    for i in range(1, len(std_counts)):
        drop = std_counts[i - 1] - std_counts[i]
        if drop > max_drop:
            max_drop = drop
            natural_break = thresholds[i]

    print(f"\n  Threshold sweep ({len(thresholds)} thresholds, {len(patients)} patients):")
    print(f"    {'Thresh':>6s}  {'Std':>4s}  {'DurW':>4s}  {'SevW':>4s}  {'Sust':>4s}  {'Night':>5s}")
    for r in threshold_results:
        print(f"    {r['threshold']:6.1f}%  {r['exceed_standard']:4d}  "
              f"{r['exceed_duration_weighted']:4d}  {r['exceed_severity_weighted']:4d}  "
              f"{r['exceed_sustained']:4d}  {r['exceed_overnight']:5d}")
    print(f"\n  Natural break at {natural_break:.1f}% (max drop = {max_drop})")

    return {
        'experiment': 'EXP-1515',
        'title': 'AID-Specific Threshold Search',
        'hypothesis': 'There exists a natural threshold separating good AID control from needs-adjustment.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': {k: {kk: round(vv, 4) for kk, vv in v.items()}
                        for k, v in patient_metrics.items()},
        'threshold_sweep': threshold_results,
        'natural_break_pct': natural_break,
        'aggregate': {
            'n_patients': len(patients),
            'natural_break': natural_break,
            'max_drop': max_drop,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# EXP-1516: CV in AID Context
# ═══════════════════════════════════════════════════════════════════════════

@register(1516, "CV in AID Context")
def exp_1516(patients, args):
    """Assess whether 36% CV threshold is appropriate for AID users."""
    per_patient = {}

    for pat in patients:
        ch = _extract_channels(pat)
        glucose = ch['glucose']
        ts = ch['timestamps']
        carbs = ch['carbs']
        name = pat['name']

        overall_cv = compute_cv(glucose)

        # Overnight CV (0:00-6:00)
        overnight_mask = get_hour_mask(ts, 0, 6)
        overnight_cv = compute_cv(glucose[overnight_mask])

        # Fasting daytime CV (6:00-22:00 with no carbs in prior 3h window)
        daytime_mask = get_hour_mask(ts, 6, 22)
        fasting_mask = np.zeros(len(glucose), dtype=bool)
        lookback_steps = 3 * STEPS_PER_HOUR  # 3 hours
        for i in range(len(glucose)):
            if not daytime_mask[i]:
                continue
            start = max(0, i - lookback_steps)
            carb_window = carbs[start:i + 1]
            if np.nansum(carb_window) == 0:
                fasting_mask[i] = True
        fasting_cv = compute_cv(glucose[fasting_mask]) if np.any(fasting_mask) else float('nan')

        # Post-meal CV (2h windows after carb entries > 5g)
        postmeal_values = []
        carb_indices = np.where(~np.isnan(carbs) & (carbs > 5))[0]
        window = 2 * STEPS_PER_HOUR  # 2 hours
        for ci in carb_indices:
            end = min(ci + window, len(glucose))
            segment = glucose[ci:end]
            valid = segment[~np.isnan(segment)]
            if len(valid) >= 6:
                postmeal_values.extend(valid.tolist())
        postmeal_cv = float('nan')
        if len(postmeal_values) >= 10:
            pm_arr = np.array(postmeal_values)
            m = np.mean(pm_arr)
            postmeal_cv = float(np.std(pm_arr) / m * 100) if m > 0 else 0.0

        # Correlation with outcomes
        tbr = compute_tbr(glucose)
        tar = compute_tar(glucose)
        tir = compute_tir(glucose)

        per_patient[name] = {
            'overall_cv': round(overall_cv, 2),
            'overnight_cv': round(overnight_cv, 2),
            'fasting_cv': round(fasting_cv, 2) if not np.isnan(fasting_cv) else None,
            'postmeal_cv': round(postmeal_cv, 2) if not np.isnan(postmeal_cv) else None,
            'tbr': round(tbr, 2),
            'tar': round(tar, 2),
            'tir': round(tir, 2),
            'exceeds_ada_cv': overall_cv > ADA_CV,
            'exceeds_aid_cv': overall_cv > AID_CV,
        }

        if args.detail:
            print(f"\n  {name}: overall={overall_cv:.1f}%, overnight={overnight_cv:.1f}%, "
                  f"fasting={fasting_cv:.1f}%, postmeal={postmeal_cv:.1f}%")

    # Correlations across patients
    names = list(per_patient.keys())
    cvs = [per_patient[n]['overall_cv'] for n in names]
    tbrs = [per_patient[n]['tbr'] for n in names]
    tars = [per_patient[n]['tar'] for n in names]

    cv_tbr_corr = _safe_corr(cvs, tbrs)
    cv_tar_corr = _safe_corr(cvs, tars)

    n_exceed_ada = sum(1 for p in per_patient.values() if p['exceeds_ada_cv'])
    n_exceed_aid = sum(1 for p in per_patient.values() if p['exceeds_aid_cv'])

    aggregate = {
        'n_patients': len(names),
        'mean_overall_cv': round(_safe_mean(cvs), 2),
        'mean_overnight_cv': round(_safe_mean(
            [per_patient[n]['overnight_cv'] for n in names]), 2),
        'cv_vs_tbr_correlation': round(cv_tbr_corr, 3),
        'cv_vs_tar_correlation': round(cv_tar_corr, 3),
        'n_exceed_ada_36': n_exceed_ada,
        'n_exceed_aid_40': n_exceed_aid,
    }

    print(f"\n  CV analysis across {len(names)} patients:")
    print(f"    Mean overall CV: {aggregate['mean_overall_cv']:.1f}%")
    print(f"    Mean overnight CV: {aggregate['mean_overnight_cv']:.1f}%")
    print(f"    CV↔TBR correlation: {cv_tbr_corr:.3f}")
    print(f"    CV↔TAR correlation: {cv_tar_corr:.3f}")
    print(f"    Exceed ADA 36%: {n_exceed_ada}/{len(names)}")
    print(f"    Exceed AID 40%: {n_exceed_aid}/{len(names)}")

    return {
        'experiment': 'EXP-1516',
        'title': 'CV in AID Context',
        'hypothesis': '36% CV threshold may be too strict for AID users.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }


# ═══════════════════════════════════════════════════════════════════════════
# EXP-1517: Regrade Under AID-Specific Targets
# ═══════════════════════════════════════════════════════════════════════════

@register(1517, "Regrade Under AID-Specific Targets")
def exp_1517(patients, args):
    """Compare v10 grades using ADA vs AID-specific safety scoring."""
    per_patient = {}

    for pat in patients:
        ch = _extract_channels(pat)
        glucose = ch['glucose']
        name = pat['name']

        tir = compute_tir(glucose)
        tbr = compute_tbr(glucose)
        tar = compute_tar(glucose)
        cv = compute_cv(glucose)

        # Sustained TBR: only episodes > 15 min
        episodes = find_hypo_episodes(glucose)
        sustained_min = sum(ep['duration_min'] for ep in episodes
                           if ep['duration_min'] >= BRIEF_MAX)
        n_valid = int(np.sum(~np.isnan(glucose)))
        total_min = n_valid * STEP_MINUTES
        sustained_tbr = sustained_min / total_min * 100 if total_min > 0 else 0

        # ADA scoring
        ada_penalty = v10_safety_penalty(tbr, cv)
        ada_base = tir * SCORE_WEIGHTS['tir'] / 100.0
        ada_score = max(0, ada_base - ada_penalty)
        ada_grade = score_to_grade(ada_score)

        # AID-specific scoring
        aid_penalty = v10_aid_safety_penalty(sustained_tbr, cv)
        aid_score = max(0, ada_base - aid_penalty)
        aid_grade = score_to_grade(aid_score)

        grade_changed = ada_grade != aid_grade

        per_patient[name] = {
            'tir': round(tir, 2),
            'tbr': round(tbr, 2),
            'sustained_tbr': round(sustained_tbr, 2),
            'tar': round(tar, 2),
            'cv': round(cv, 2),
            'ada_penalty': round(ada_penalty, 2),
            'ada_score': round(ada_score, 2),
            'ada_grade': ada_grade,
            'aid_penalty': round(aid_penalty, 2),
            'aid_score': round(aid_score, 2),
            'aid_grade': aid_grade,
            'grade_changed': grade_changed,
        }

    # Summary
    changed = [n for n, p in per_patient.items() if p['grade_changed']]
    improved = [n for n in changed
                if ord(per_patient[n]['aid_grade']) < ord(per_patient[n]['ada_grade'])]

    print(f"\n  Regrade comparison ({len(per_patient)} patients):")
    print(f"    {'Patient':>10s}  {'TIR':>5s}  {'TBR':>5s}  {'susTBR':>6s}  {'CV':>5s}  "
          f"{'ADA':>4s} {'AID':>4s}  {'Change':>6s}")
    for name in sorted(per_patient.keys()):
        p = per_patient[name]
        ch_str = f"{p['ada_grade']}→{p['aid_grade']}" if p['grade_changed'] else '  -  '
        print(f"    {name:>10s}  {p['tir']:5.1f}  {p['tbr']:5.2f}  {p['sustained_tbr']:6.2f}  "
              f"{p['cv']:5.1f}  {p['ada_grade']:>4s} {p['aid_grade']:>4s}  {ch_str:>6s}")

    aggregate = {
        'n_patients': len(per_patient),
        'n_changed': len(changed),
        'n_improved': len(improved),
        'changed_patients': changed,
        'improved_patients': improved,
    }
    print(f"\n  {len(changed)} patients changed grade, {len(improved)} improved")

    return {
        'experiment': 'EXP-1517',
        'title': 'Regrade Under AID-Specific Targets',
        'hypothesis': 'AID-specific scoring improves grades for patients with brief algorithmic lows.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }


# ═══════════════════════════════════════════════════════════════════════════
# EXP-1518: Brief Low Predictive Value
# ═══════════════════════════════════════════════════════════════════════════

@register(1518, "Brief Low Predictive Value")
def exp_1518(patients, args):
    """Test whether brief lows predict sustained lows (warning signal vs noise)."""
    per_patient = {}

    for pat in patients:
        ch = _extract_channels(pat)
        glucose = ch['glucose']
        ts = ch['timestamps']
        name = pat['name']

        episodes = find_hypo_episodes(glucose)
        if not episodes:
            per_patient[name] = {
                'total_episodes': 0,
                'brief_count': 0,
                'sustained_count': 0,
                'correlation': None,
                'weekly_data': [],
            }
            continue

        # Classify
        brief_count = sum(1 for ep in episodes if classify_episode(ep) == 'brief')
        moderate_count = sum(1 for ep in episodes if classify_episode(ep) == 'moderate')
        sustained_count = sum(1 for ep in episodes if classify_episode(ep) == 'sustained')

        # Weekly breakdown: bin episodes into 7-day windows
        steps_per_week = 7 * STEPS_PER_DAY
        n_weeks = max(1, len(glucose) // steps_per_week)

        weekly_brief = []
        weekly_sustained = []
        for w in range(n_weeks):
            ws = w * steps_per_week
            we = min((w + 1) * steps_per_week, len(glucose))
            w_brief = 0
            w_sustained = 0
            for ep in episodes:
                # Episode falls in this week if its start is within the window
                if ws <= ep['start_idx'] < we:
                    cat = classify_episode(ep)
                    if cat == 'brief':
                        w_brief += 1
                    elif cat == 'sustained':
                        w_sustained += 1
            weekly_brief.append(w_brief)
            weekly_sustained.append(w_sustained)

        # Same-week correlation
        same_week_corr = _safe_corr(weekly_brief, weekly_sustained)

        # Lagged correlation: brief in week N vs sustained in week N+1
        lagged_corr = float('nan')
        if n_weeks >= 3:
            lagged_corr = _safe_corr(weekly_brief[:-1], weekly_sustained[1:])

        per_patient[name] = {
            'total_episodes': len(episodes),
            'brief_count': brief_count,
            'moderate_count': moderate_count,
            'sustained_count': sustained_count,
            'n_weeks': n_weeks,
            'same_week_correlation': round(same_week_corr, 3) if not np.isnan(same_week_corr) else None,
            'lagged_correlation': round(lagged_corr, 3) if not np.isnan(lagged_corr) else None,
            'weekly_brief': weekly_brief,
            'weekly_sustained': weekly_sustained,
        }

        if args.detail:
            print(f"\n  {name}: brief={brief_count}, sustained={sustained_count}, "
                  f"same_corr={same_week_corr:.3f}, lag_corr={lagged_corr:.3f}")

    # Aggregate: cross-patient correlation
    briefs = [per_patient[n]['brief_count'] for n in per_patient]
    sustaineds = [per_patient[n]['sustained_count'] for n in per_patient]
    cross_patient_corr = _safe_corr(briefs, sustaineds)

    same_week_corrs = [per_patient[n]['same_week_correlation'] for n in per_patient
                       if per_patient[n]['same_week_correlation'] is not None]
    lagged_corrs = [per_patient[n]['lagged_correlation'] for n in per_patient
                    if per_patient[n]['lagged_correlation'] is not None]

    aggregate = {
        'n_patients': len(per_patient),
        'cross_patient_brief_vs_sustained_corr': round(cross_patient_corr, 3)
            if not np.isnan(cross_patient_corr) else None,
        'mean_same_week_corr': round(_safe_mean(same_week_corrs), 3),
        'mean_lagged_corr': round(_safe_mean(lagged_corrs), 3),
    }

    print(f"\n  Predictive value analysis ({len(per_patient)} patients):")
    print(f"    Cross-patient brief↔sustained: {cross_patient_corr:.3f}")
    print(f"    Mean same-week correlation: {_safe_mean(same_week_corrs):.3f}")
    print(f"    Mean lagged (N→N+1) correlation: {_safe_mean(lagged_corrs):.3f}")

    # Interpretation
    if not np.isnan(cross_patient_corr) and cross_patient_corr > 0.5:
        conclusion = "Brief lows ARE predictive of sustained lows — they may be a warning signal."
    elif not np.isnan(cross_patient_corr) and cross_patient_corr < 0.2:
        conclusion = "Brief lows are NOT predictive — likely benign algorithmic noise."
    else:
        conclusion = "Weak/moderate association — further investigation needed."
    aggregate['conclusion'] = conclusion
    print(f"    Conclusion: {conclusion}")

    return {
        'experiment': 'EXP-1518',
        'title': 'Brief Low Predictive Value',
        'hypothesis': 'Brief algorithmic lows may be benign noise rather than warning signals.',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'per_patient': per_patient,
        'aggregate': aggregate,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Summary table
# ═══════════════════════════════════════════════════════════════════════════

def print_summary_table(all_results, patients):
    """Print a comparison table: standard vs AID-specific metrics per patient."""
    print("\n" + "=" * 100)
    print("SUMMARY: Standard vs AID-Specific Metrics")
    print("=" * 100)

    # Collect per-patient data from experiments 1511, 1514, 1516, 1517
    r1511 = all_results.get(1511, {}).get('per_patient', {})
    r1514 = all_results.get(1514, {}).get('per_patient', {})
    r1516 = all_results.get(1516, {}).get('per_patient', {})
    r1517 = all_results.get(1517, {}).get('per_patient', {})
    r1512 = all_results.get(1512, {}).get('per_patient', {})

    names = sorted(set(list(r1511.keys()) + list(r1514.keys())
                       + list(r1516.keys()) + list(r1517.keys())))

    if not names:
        print("  No patient data available for summary.")
        return

    # Header
    print(f"\n  {'Patient':>10s}  {'TIR%':>5s}  {'TBR%':>5s}  {'sTBR%':>5s}  "
          f"{'CV%':>5s}  {'ADA':>4s}  {'AID':>4s}  {'Δ':>2s}  "
          f"{'Brief':>5s}  {'Sust':>5s}  {'Mgd%':>5s}  {'DurW':>8s}")
    print(f"  {'':->10s}  {'':->5s}  {'':->5s}  {'':->5s}  "
          f"{'':->5s}  {'':->4s}  {'':->4s}  {'':->2s}  "
          f"{'':->5s}  {'':->5s}  {'':->5s}  {'':->8s}")

    for name in names:
        p17 = r1517.get(name, {})
        p11 = r1511.get(name, {})
        p14 = r1514.get(name, {})
        p12 = r1512.get(name, {})

        tir = p17.get('tir', 0)
        tbr = p17.get('tbr', 0)
        stbr = p17.get('sustained_tbr', 0)
        cv = p17.get('cv', 0)
        ada = p17.get('ada_grade', '-')
        aid = p17.get('aid_grade', '-')
        changed = '↑' if p17.get('grade_changed', False) and ord(aid) < ord(ada) else \
                  '↓' if p17.get('grade_changed', False) else ' '

        cats = p11.get('categories', {})
        n_brief = cats.get('brief', {}).get('count', 0)
        n_sust = cats.get('sustained', {}).get('count', 0)

        mgd_frac = p12.get('managed_fraction', 0)
        dur_w = p14.get('duration_weighted_tbr', 0)

        print(f"  {name:>10s}  {tir:5.1f}  {tbr:5.2f}  {stbr:5.2f}  "
              f"{cv:5.1f}  {ada:>4s}  {aid:>4s}  {changed:>2s}  "
              f"{n_brief:5d}  {n_sust:5d}  {mgd_frac*100:5.1f}  {dur_w:8.4f}")

    # Key takeaways
    if r1517:
        n_changed = sum(1 for p in r1517.values() if p.get('grade_changed', False))
        n_improved = sum(1 for p in r1517.values()
                         if p.get('grade_changed', False)
                         and ord(p.get('aid_grade', 'Z')) < ord(p.get('ada_grade', 'A')))
        print(f"\n  Grade changes: {n_changed}/{len(r1517)} patients "
              f"({n_improved} improved under AID targets)")

    # Check patient k specifically
    pk = r1517.get('k', {})
    if pk:
        print(f"\n  Patient k (key case): TIR={pk.get('tir',0):.1f}%, "
              f"TBR={pk.get('tbr',0):.2f}%, sustained_TBR={pk.get('sustained_tbr',0):.2f}%, "
              f"ADA={pk.get('ada_grade','-')} → AID={pk.get('aid_grade','-')}")

    # ADA vs AID threshold summary
    if r1516:
        agg16 = all_results.get(1516, {}).get('aggregate', {})
        print(f"\n  CV threshold impact: {agg16.get('n_exceed_ada_36',0)} exceed ADA 36%, "
              f"{agg16.get('n_exceed_aid_40',0)} exceed AID 40%")

    print("=" * 100)


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='EXP-1511 to EXP-1518: AID-specific TBR/CV target validation')
    parser.add_argument('--detail', action='store_true',
                        help='Show detailed per-patient output')
    parser.add_argument('--save', action='store_true',
                        help='Save results to JSON')
    parser.add_argument('--max-patients', type=int, default=11,
                        help='Max patients to load')
    parser.add_argument('--exp', type=int, nargs='*',
                        help='Run specific experiment IDs (e.g. --exp 1511 1514)')
    args = parser.parse_args()

    print("=" * 70)
    print("AID-Specific TBR/CV Target Validation")
    print("EXP-1511 through EXP-1518")
    print("=" * 70)

    # Load data
    t0 = time.time()
    print(f"\nLoading patients (max={args.max_patients})...")
    patients = load_patients(max_patients=args.max_patients)
    load_time = time.time() - t0
    print(f"  Loaded {len(patients)} patients in {load_time:.1f}s")

    if not patients:
        print("ERROR: No patient data loaded. Check PATIENTS_DIR.")
        sys.exit(1)

    # Determine which experiments to run
    to_run = args.exp if args.exp else sorted(EXPERIMENTS.keys())

    all_results = {}
    total_t0 = time.time()

    for exp_id in to_run:
        if exp_id not in EXPERIMENTS:
            print(f"\nWARNING: EXP-{exp_id} not registered, skipping")
            continue

        title, fn = EXPERIMENTS[exp_id]
        print(f"\n{'═' * 60}")
        print(f"EXP-{exp_id}: {title}")
        print(f"{'═' * 60}")

        t0 = time.time()
        try:
            result = fn(patients, args)
            elapsed = time.time() - t0
            result['elapsed_sec'] = round(elapsed, 1)
            all_results[exp_id] = result
            print(f"\n  ✓ Completed in {elapsed:.1f}s")

            if args.save:
                RESULTS_DIR.mkdir(parents=True, exist_ok=True)
                outpath = RESULTS_DIR / f'exp-{exp_id}_aid_targets.json'
                with open(outpath, 'w') as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  → Saved {outpath}")

        except Exception as e:
            elapsed = time.time() - t0
            print(f"\n  ✗ FAILED in {elapsed:.1f}s: {e}")
            traceback.print_exc()
            all_results[exp_id] = {
                'experiment': f'EXP-{exp_id}',
                'error': str(e),
                'elapsed_sec': round(elapsed, 1),
            }

    total_elapsed = time.time() - total_t0

    # Summary table
    print_summary_table(all_results, patients)

    print(f"\nTotal runtime: {total_elapsed:.1f}s "
          f"({len(all_results)}/{len(to_run)} experiments completed)")

    # Save combined results
    if args.save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        combined_path = RESULTS_DIR / 'exp-1511_1518_aid_targets_combined.json'
        combined = {
            'title': 'AID-Specific TBR/CV Target Validation',
            'experiments': {str(k): v for k, v in all_results.items()},
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'total_elapsed_sec': round(total_elapsed, 1),
        }
        with open(combined_path, 'w') as f:
            json.dump(combined, f, indent=2, default=str)
        print(f"  → Saved combined results to {combined_path}")


if __name__ == '__main__':
    main()
