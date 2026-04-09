#!/usr/bin/env python3
"""EXP-1691 through EXP-1698: Glycemic Excursion Taxonomy & Variability Decomposition.

Expanding beyond hypoglycemia to classify ALL glucose excursions and decompose
glycemic variability into actionable components. The cascade finding (EXP-1687:
hyper-rebound rate predicts TAR, r=0.791) motivates asking: what fraction of
overall glucose variability comes from cascades vs meals vs corrections vs drift?

Key questions:
  1. Can we classify all excursions into a taxonomy? (hypo, meal, correction, drift)
  2. How many excursions are part of cascade chains?
  3. What fraction of glucose variability comes from each excursion type?
  4. Do different excursion types have distinct supply-demand signatures?
  5. Which excursion type is the biggest driver of TAR/TBR?
  6. Is overnight glucose the cleanest therapy calibration context?
  7. Do patients cluster by excursion profile?
  8. Which excursion type offers the most actionable improvement potential?

References:
  EXP-1681–1688: Personalized hypo-recovery, cascade cycle (r=0.791)
  EXP-1641–1648: Rescue carb inference, detection-estimation disconnect
  EXP-1631–1636: Corrected supply-demand model
  EXP-1611–1616: Natural experiment deconfounding
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
from scipy.signal import savgol_filter

warnings.filterwarnings('ignore', category=RuntimeWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.exp_metabolic_flux import load_patients, _extract_isf_scalar
from cgmencode.exp_metabolic_441 import compute_supply_demand

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'
FIGURES_DIR = Path(__file__).parent.parent.parent / 'docs' / '60-research' / 'figures'


# ── Excursion detection and classification ─────────────────────────────

def detect_excursions(glucose, carbs, iob, sd_dict, min_excursion=15):
    """Detect and classify all glucose excursions.

    An excursion is a contiguous rise or fall of >= min_excursion mg/dL.

    Classification logic:
      - hypo_entry: glucose crosses below 70 mg/dL
      - hypo_recovery: rising from below 70 mg/dL
      - meal_rise: carbs announced within ±30 min of rise onset
      - correction_drop: significant IOB increase precedes the drop
      - uam_rise: unannounced rise (no carbs, IOB not increasing)
      - drift_rise / drift_fall: slow, small excursions without clear trigger
      - rebound_rise: rise immediately following a hypo or correction drop
    """
    N = len(glucose)
    excursions = []

    # Smooth glucose for excursion detection
    g = glucose.copy()
    # Forward-fill NaN for continuity
    for i in range(1, N):
        if np.isnan(g[i]) and not np.isnan(g[i-1]):
            g[i] = g[i-1]

    # Find local extrema using smoothed derivative
    dbg = np.zeros(N)
    for i in range(1, N):
        if not np.isnan(g[i]) and not np.isnan(g[i-1]):
            dbg[i] = g[i] - g[i-1]

    # State machine: track rises and falls
    i = 0
    while i < N - 2:
        if np.isnan(g[i]):
            i += 1
            continue

        # Look for start of an excursion
        start_idx = i
        start_bg = g[i]

        # Scan forward to find the excursion end
        peak_bg = start_bg
        trough_bg = start_bg
        peak_idx = i
        trough_idx = i

        j = i + 1
        direction = None  # 'rise' or 'fall'
        while j < N:
            if np.isnan(g[j]):
                j += 1
                continue

            if g[j] > peak_bg:
                peak_bg = g[j]
                peak_idx = j
            if g[j] < trough_bg:
                trough_bg = g[j]
                trough_idx = j

            # Determine direction from first significant movement
            if direction is None:
                if g[j] - start_bg >= min_excursion:
                    direction = 'rise'
                elif start_bg - g[j] >= min_excursion:
                    direction = 'fall'

            # End condition: reversal from peak/trough by min_excursion
            if direction == 'rise' and peak_bg - g[j] >= min_excursion:
                break
            elif direction == 'fall' and g[j] - trough_bg >= min_excursion:
                break

            j += 1

        if direction is None:
            i = j
            continue

        if direction == 'rise':
            end_idx = peak_idx
            end_bg = peak_bg
            magnitude = peak_bg - start_bg
        else:
            end_idx = trough_idx
            end_bg = trough_bg
            magnitude = start_bg - trough_bg

        duration_steps = end_idx - start_idx
        if duration_steps < 1:
            i = j
            continue

        rate = magnitude / duration_steps  # mg/dL per step

        # Classify
        supply_mean = float(np.nanmean(sd_dict['supply'][start_idx:end_idx+1]))
        demand_mean = float(np.nanmean(sd_dict['demand'][start_idx:end_idx+1]))
        net_mean = float(np.nanmean(sd_dict['net'][start_idx:end_idx+1]))

        # Context windows for classification
        carb_window = carbs[max(0, start_idx-6):min(N, end_idx+6)]
        has_carbs = float(np.nansum(carb_window)) > 1.0
        carb_amount = float(np.nansum(carb_window))

        iob_at_start = float(iob[start_idx]) if not np.isnan(iob[start_idx]) else 0
        iob_at_end = float(iob[end_idx]) if not np.isnan(iob[end_idx]) else 0
        iob_delta = iob_at_end - iob_at_start

        # Time of day
        tod_hour = (start_idx % STEPS_PER_DAY) / STEPS_PER_HOUR

        # Classification — priority-ordered rules
        if direction == 'fall' and end_bg < 70:
            exc_type = 'hypo_entry'
        elif direction == 'rise' and start_bg < 70:
            exc_type = 'hypo_recovery'
        elif direction == 'rise' and has_carbs:
            exc_type = 'meal_rise'
        elif direction == 'fall' and iob_delta > 0.5:
            exc_type = 'correction_drop'
        elif direction == 'rise' and not has_carbs:
            # Check if preceded by a fall (rebound)
            pre_bg = glucose[max(0, start_idx-12):start_idx+1]
            valid_pre = ~np.isnan(pre_bg)
            if valid_pre.sum() >= 2:
                pre_change = float(pre_bg[valid_pre][-1] - pre_bg[valid_pre][0])
                if pre_change < -20:
                    exc_type = 'rebound_rise'
                else:
                    exc_type = 'uam_rise'
            else:
                exc_type = 'uam_rise'
        elif direction == 'fall' and rate < 1.0:
            exc_type = 'drift_fall'
        elif direction == 'fall':
            # Subcategorize the falls that would otherwise be "unclassified":
            # - insulin_fall: demand > supply (active insulin driving glucose down)
            # - post_meal_fall: preceded by a rise (return to range after meal/spike)
            # - natural_fall: supply ≈ demand, drifting down
            pre_bg = glucose[max(0, start_idx-18):start_idx+1]
            valid_pre = ~np.isnan(pre_bg)
            if demand_mean > supply_mean * 0.8 and demand_mean > 2.0:
                exc_type = 'insulin_fall'
            elif valid_pre.sum() >= 2 and float(pre_bg[valid_pre][-1] - pre_bg[valid_pre][0]) > 15:
                exc_type = 'post_rise_fall'
            else:
                exc_type = 'natural_fall'
        else:
            exc_type = f'unclassified_{"rise" if direction == "rise" else "fall"}'

        excursions.append({
            'start_idx': start_idx,
            'end_idx': end_idx,
            'start_bg': float(start_bg),
            'end_bg': float(end_bg),
            'direction': direction,
            'magnitude': float(magnitude),
            'duration_steps': duration_steps,
            'duration_hours': duration_steps / STEPS_PER_HOUR,
            'rate': float(rate),
            'type': exc_type,
            'has_carbs': has_carbs,
            'carb_amount': carb_amount,
            'iob_at_start': iob_at_start,
            'iob_delta': iob_delta,
            'supply_mean': supply_mean,
            'demand_mean': demand_mean,
            'net_mean': net_mean,
            'tod_hour': tod_hour,
        })

        i = end_idx + 1

    return excursions


# ── EXP-1691: Excursion Taxonomy ──────────────────────────────────────

def exp_1691_excursion_taxonomy(patients):
    """Classify all glucose excursions across 11 patients."""
    print("\n=== EXP-1691: Glycemic Excursion Taxonomy ===")

    all_excursions = []
    per_patient = {}

    for pat in patients:
        name = pat['name']
        df, pk = pat['df'], pat['pk']
        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        excursions = detect_excursions(glucose, carbs, iob, sd)

        type_counts = defaultdict(int)
        type_magnitudes = defaultdict(list)
        for exc in excursions:
            exc['patient'] = name
            all_excursions.append(exc)
            type_counts[exc['type']] += 1
            type_magnitudes[exc['type']].append(exc['magnitude'])

        valid_days = (~np.isnan(glucose)).sum() / STEPS_PER_DAY
        per_patient[name] = {
            'n_excursions': len(excursions),
            'excursions_per_day': round(len(excursions) / valid_days, 1),
            'type_counts': dict(type_counts),
        }

        print(f"  {name}: {len(excursions)} excursions ({len(excursions)/valid_days:.1f}/day)")

    # Population summary
    type_totals = defaultdict(int)
    type_mags = defaultdict(list)
    type_durations = defaultdict(list)
    for exc in all_excursions:
        type_totals[exc['type']] += 1
        type_mags[exc['type']].append(exc['magnitude'])
        type_durations[exc['type']].append(exc['duration_hours'])

    total = len(all_excursions)
    print(f"\n  Population excursion distribution (n={total}):")
    taxonomy = {}
    for etype, count in sorted(type_totals.items(), key=lambda x: -x[1]):
        pct = 100 * count / total
        mean_mag = np.mean(type_mags[etype])
        mean_dur = np.mean(type_durations[etype])
        taxonomy[etype] = {
            'count': count,
            'pct': round(pct, 1),
            'mean_magnitude': round(mean_mag, 1),
            'mean_duration_hours': round(mean_dur, 2),
        }
        print(f"    {etype}: {count} ({pct:.1f}%) mag={mean_mag:.1f} dur={mean_dur:.1f}h")

    return {
        'experiment': 'EXP-1691',
        'title': 'Glycemic Excursion Taxonomy',
        'total_excursions': total,
        'taxonomy': taxonomy,
        'per_patient': per_patient,
    }


# ── EXP-1692: Cascade Chain Tracing ──────────────────────────────────

def exp_1692_cascade_chains(patients):
    """Trace cascade chains: sequences of excursions linked by triggered transitions.

    Since excursions are contiguous by construction (no gap between them), we
    define cascades by TYPE TRANSITION — a cascade is a sequence where each
    excursion's type triggers the next in a pathological pattern:
      - hypo_entry → hypo_recovery (rescue)
      - hypo_recovery → rebound_rise (over-rescue)
      - hypo_recovery → hypo_entry (recurrent hypo)
      - rebound_rise → unclassified_fall (return-to-range after over-rescue)
      - meal_rise → unclassified_fall → hypo_entry (post-meal crash)
      - unclassified_fall → hypo_entry (falling into hypo)

    A chain breaks when the transition is NOT in the triggered set (e.g.,
    an isolated UAM rise or meal rise starts a new independent excursion).
    """
    print("\n=== EXP-1692: Cascade Chain Tracing ===")

    # Pathological cascade transitions: transitions where one excursion
    # plausibly triggers the next
    CASCADE_TRANSITIONS = {
        ('hypo_entry', 'hypo_recovery'),     # nadir → rescue
        ('hypo_recovery', 'rebound_rise'),   # over-rescue → spike
        ('hypo_recovery', 'uam_rise'),       # over-rescue → unannounced spike
        ('hypo_recovery', 'hypo_entry'),     # recurrent hypo
        ('hypo_recovery', 'meal_rise'),      # rescue + meal stacking
        ('rebound_rise', 'insulin_fall'),    # return to range after spike
        ('rebound_rise', 'post_rise_fall'),  # return to range after spike
        ('rebound_rise', 'natural_fall'),    # return to range after spike
        ('rebound_rise', 'correction_drop'), # correction after rebound
        ('insulin_fall', 'hypo_entry'),      # insulin-driven fall into hypo
        ('post_rise_fall', 'hypo_entry'),    # post-rise fall into hypo
        ('natural_fall', 'hypo_entry'),      # drifting into hypo
        ('correction_drop', 'hypo_entry'),   # over-correction → hypo
        ('meal_rise', 'correction_drop'),    # meal → correction
        ('meal_rise', 'insulin_fall'),       # meal → insulin response
        ('uam_rise', 'insulin_fall'),        # UAM → insulin response
        ('uam_rise', 'post_rise_fall'),      # UAM subsiding
        ('uam_rise', 'correction_drop'),     # UAM → correction
    }

    all_chains = []
    chain_lengths = []
    per_patient = {}

    for pat in patients:
        name = pat['name']
        df, pk = pat['df'], pat['pk']
        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        excursions = detect_excursions(glucose, carbs, iob, sd)

        # Build chains using triggered transitions
        chains = []
        current_chain = [excursions[0]] if excursions else []

        for i in range(1, len(excursions)):
            prev_type = excursions[i-1]['type']
            curr_type = excursions[i]['type']
            if (prev_type, curr_type) in CASCADE_TRANSITIONS:
                current_chain.append(excursions[i])
            else:
                if len(current_chain) >= 2:
                    chains.append(current_chain)
                    chain_lengths.append(len(current_chain))
                current_chain = [excursions[i]]

        if len(current_chain) >= 2:
            chains.append(current_chain)
            chain_lengths.append(len(current_chain))

        # Count excursions in chains vs isolated
        in_chain = sum(len(c) for c in chains)
        isolated = len(excursions) - in_chain

        valid_days = (~np.isnan(glucose)).sum() / STEPS_PER_DAY
        per_patient[name] = {
            'n_excursions': len(excursions),
            'n_chains': len(chains),
            'in_chain_pct': round(100 * in_chain / len(excursions), 1) if excursions else 0,
            'mean_chain_length': round(float(np.mean([len(c) for c in chains])), 1) if chains else 0,
            'chains_per_day': round(len(chains) / valid_days, 1),
            'isolated_pct': round(100 * isolated / len(excursions), 1) if excursions else 100,
        }
        all_chains.extend(chains)

        print(f"  {name}: {len(chains)} chains ({100*in_chain/len(excursions):.0f}% in chains, "
              f"mean_len={np.mean([len(c) for c in chains]):.1f})" if chains else f"  {name}: no chains")

    # Population analysis
    if chain_lengths:
        print(f"\n  Population chain statistics:")
        print(f"    Total chains: {len(all_chains)}")
        print(f"    Mean chain length: {np.mean(chain_lengths):.1f}")
        print(f"    Max chain length: {max(chain_lengths)}")
        print(f"    Chains of length ≥3: {sum(1 for l in chain_lengths if l >= 3)} "
              f"({100*sum(1 for l in chain_lengths if l >= 3)/len(chain_lengths):.1f}%)")

    # Common cascade patterns
    all_patterns = defaultdict(int)
    for chain in all_chains:
        types = [e['type'] for e in chain]
        for i in range(len(types) - 1):
            pair = f"{types[i]}→{types[i+1]}"
            all_patterns[pair] += 1

    print(f"\n  Top 10 cascade transitions:")
    for pattern, count in sorted(all_patterns.items(), key=lambda x: -x[1])[:10]:
        print(f"    {pattern}: {count}")

    return {
        'experiment': 'EXP-1692',
        'title': 'Cascade Chain Tracing',
        'total_chains': len(all_chains),
        'chain_length_distribution': {
            'mean': round(float(np.mean(chain_lengths)), 2) if chain_lengths else 0,
            'median': round(float(np.median(chain_lengths)), 1) if chain_lengths else 0,
            'max': int(max(chain_lengths)) if chain_lengths else 0,
        },
        'top_transitions': dict(sorted(all_patterns.items(), key=lambda x: -x[1])[:15]),
        'per_patient': per_patient,
    }


# ── EXP-1693: Glycemic Variability Decomposition ─────────────────────

def exp_1693_variability_decomposition(patients):
    """Decompose total glucose variability by excursion type.

    For each excursion type, compute its contribution to:
    - Total glucose variance (mg/dL²)
    - Time above range (>180 mg/dL)
    - Time below range (<70 mg/dL)
    - Coefficient of variation
    """
    print("\n=== EXP-1693: Glycemic Variability Decomposition ===")

    type_contributions = defaultdict(lambda: {'variance': 0, 'tar_steps': 0,
                                               'tbr_steps': 0, 'total_steps': 0,
                                               'excursion_count': 0})
    total_var = 0
    total_tar = 0
    total_tbr = 0
    total_steps = 0

    for pat in patients:
        name = pat['name']
        df, pk = pat['df'], pat['pk']
        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        excursions = detect_excursions(glucose, carbs, iob, sd)

        mean_bg = float(np.nanmean(glucose))

        for exc in excursions:
            seg = glucose[exc['start_idx']:exc['end_idx']+1]
            valid = ~np.isnan(seg)
            if valid.sum() < 2:
                continue

            # Variance contribution: sum of (bg - mean)² for this segment
            var_contrib = float(np.sum((seg[valid] - mean_bg) ** 2))
            tar_steps = int(np.sum(seg[valid] > 180))
            tbr_steps = int(np.sum(seg[valid] < 70))

            tc = type_contributions[exc['type']]
            tc['variance'] += var_contrib
            tc['tar_steps'] += tar_steps
            tc['tbr_steps'] += tbr_steps
            tc['total_steps'] += int(valid.sum())
            tc['excursion_count'] += 1

        # Overall stats for this patient
        valid_g = glucose[~np.isnan(glucose)]
        total_var += float(np.sum((valid_g - mean_bg) ** 2))
        total_tar += int(np.sum(valid_g > 180))
        total_tbr += int(np.sum(valid_g < 70))
        total_steps += len(valid_g)

    # Compute fractions
    results = {}
    print(f"  {'Type':<25} {'Var%':>7} {'TAR%':>7} {'TBR%':>7} {'Steps%':>7} {'Count':>7}")
    for etype, tc in sorted(type_contributions.items(), key=lambda x: -x[1]['variance']):
        var_pct = 100 * tc['variance'] / total_var if total_var > 0 else 0
        tar_pct = 100 * tc['tar_steps'] / total_tar if total_tar > 0 else 0
        tbr_pct = 100 * tc['tbr_steps'] / total_tbr if total_tbr > 0 else 0
        steps_pct = 100 * tc['total_steps'] / total_steps if total_steps > 0 else 0

        results[etype] = {
            'variance_pct': round(var_pct, 1),
            'tar_pct': round(tar_pct, 1),
            'tbr_pct': round(tbr_pct, 1),
            'time_pct': round(steps_pct, 1),
            'count': tc['excursion_count'],
        }
        print(f"  {etype:<25} {var_pct:>6.1f}% {tar_pct:>6.1f}% {tbr_pct:>6.1f}% "
              f"{steps_pct:>6.1f}% {tc['excursion_count']:>7}")

    # Unaccounted time (between excursions)
    accounted_steps = sum(tc['total_steps'] for tc in type_contributions.values())
    unaccounted_pct = 100 * (total_steps - accounted_steps) / total_steps
    print(f"\n  Time between excursions: {unaccounted_pct:.1f}%")

    return {
        'experiment': 'EXP-1693',
        'title': 'Glycemic Variability Decomposition',
        'decomposition': results,
        'total_variance': round(total_var, 0),
        'unaccounted_time_pct': round(unaccounted_pct, 1),
    }


# ── EXP-1694: Supply-Demand Signatures by Excursion Type ─────────────

def exp_1694_sd_signatures(patients):
    """Characterize the supply-demand profile for each excursion type.

    Question: do different excursion types have distinct metabolic signatures?
    """
    print("\n=== EXP-1694: Supply-Demand Signatures by Excursion Type ===")

    type_signatures = defaultdict(lambda: {'supply': [], 'demand': [], 'net': [],
                                            'iob_start': [], 'iob_delta': []})

    for pat in patients:
        name = pat['name']
        df, pk = pat['df'], pat['pk']
        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        excursions = detect_excursions(glucose, carbs, iob, sd)

        for exc in excursions:
            sig = type_signatures[exc['type']]
            sig['supply'].append(exc['supply_mean'])
            sig['demand'].append(exc['demand_mean'])
            sig['net'].append(exc['net_mean'])
            sig['iob_start'].append(exc['iob_at_start'])
            sig['iob_delta'].append(exc['iob_delta'])

    # Compute signatures
    results = {}
    print(f"  {'Type':<25} {'Supply':>8} {'Demand':>8} {'Net':>8} {'IOB_s':>8} {'IOB_Δ':>8} {'n':>6}")
    for etype in sorted(type_signatures.keys()):
        sig = type_signatures[etype]
        n = len(sig['supply'])
        if n < 5:
            continue
        entry = {
            'n': n,
            'supply_mean': round(float(np.mean(sig['supply'])), 3),
            'demand_mean': round(float(np.mean(sig['demand'])), 3),
            'net_mean': round(float(np.mean(sig['net'])), 3),
            'iob_start_mean': round(float(np.mean(sig['iob_start'])), 3),
            'iob_delta_mean': round(float(np.mean(sig['iob_delta'])), 3),
        }
        results[etype] = entry
        print(f"  {etype:<25} {entry['supply_mean']:>8.3f} {entry['demand_mean']:>8.3f} "
              f"{entry['net_mean']:>8.3f} {entry['iob_start_mean']:>8.3f} "
              f"{entry['iob_delta_mean']:>8.3f} {n:>6}")

    # Test: are signatures statistically different?
    types_with_enough = [t for t, s in type_signatures.items() if len(s['net']) >= 20]
    if len(types_with_enough) >= 2:
        # Kruskal-Wallis test on net flux across types
        groups = [type_signatures[t]['net'] for t in types_with_enough]
        h_stat, h_p = stats.kruskal(*groups)
        print(f"\n  Kruskal-Wallis test (net flux across types): H={h_stat:.1f} p={h_p:.2e}")
    else:
        h_stat, h_p = 0, 1

    return {
        'experiment': 'EXP-1694',
        'title': 'Supply-Demand Signatures by Excursion Type',
        'signatures': results,
        'kruskal_wallis_h': round(h_stat, 2),
        'kruskal_wallis_p': float(h_p),
    }


# ── EXP-1695: Time-in-Range Contribution ─────────────────────────────

def exp_1695_tir_contribution(patients):
    """Which excursion types are the biggest drivers of TAR and TBR?

    Computes an "improvement potential" — if we could perfectly manage
    each excursion type, how much would TIR improve?
    """
    print("\n=== EXP-1695: Time-in-Range Contribution ===")

    type_stats = defaultdict(lambda: {'tar_minutes': 0, 'tbr_minutes': 0,
                                       'total_minutes': 0, 'n': 0})
    total_tar_min = 0
    total_tbr_min = 0
    total_min = 0

    for pat in patients:
        df, pk = pat['df'], pat['pk']
        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        excursions = detect_excursions(glucose, carbs, iob, sd)

        for exc in excursions:
            seg = glucose[exc['start_idx']:exc['end_idx']+1]
            valid = seg[~np.isnan(seg)]
            tar = np.sum(valid > 180) * 5  # minutes
            tbr = np.sum(valid < 70) * 5
            total = len(valid) * 5

            ts = type_stats[exc['type']]
            ts['tar_minutes'] += int(tar)
            ts['tbr_minutes'] += int(tbr)
            ts['total_minutes'] += int(total)
            ts['n'] += 1

        valid_g = glucose[~np.isnan(glucose)]
        total_tar_min += int(np.sum(valid_g > 180) * 5)
        total_tbr_min += int(np.sum(valid_g < 70) * 5)
        total_min += len(valid_g) * 5

    # Improvement potential: if this type were perfectly in-range
    print(f"  Overall: TAR={total_tar_min/60:.0f}h TBR={total_tbr_min/60:.0f}h "
          f"Total={total_min/60:.0f}h")
    print(f"\n  {'Type':<25} {'TAR(h)':>7} {'TBR(h)':>7} {'TAR%':>6} {'TBR%':>6} {'n':>6}")

    results = {}
    for etype, ts in sorted(type_stats.items(), key=lambda x: -x[1]['tar_minutes']):
        tar_pct = 100 * ts['tar_minutes'] / total_tar_min if total_tar_min else 0
        tbr_pct = 100 * ts['tbr_minutes'] / total_tbr_min if total_tbr_min else 0
        results[etype] = {
            'tar_hours': round(ts['tar_minutes'] / 60, 1),
            'tbr_hours': round(ts['tbr_minutes'] / 60, 1),
            'tar_contribution_pct': round(tar_pct, 1),
            'tbr_contribution_pct': round(tbr_pct, 1),
            'count': ts['n'],
        }
        print(f"  {etype:<25} {ts['tar_minutes']/60:>6.0f}h {ts['tbr_minutes']/60:>6.0f}h "
              f"{tar_pct:>5.1f}% {tbr_pct:>5.1f}% {ts['n']:>6}")

    return {
        'experiment': 'EXP-1695',
        'title': 'Time-in-Range Contribution',
        'total_tar_hours': round(total_tar_min / 60, 1),
        'total_tbr_hours': round(total_tbr_min / 60, 1),
        'contributions': results,
    }


# ── EXP-1696: Overnight as Therapy Calibrator ────────────────────────

def exp_1696_overnight_calibrator(patients):
    """Use overnight glucose (0–6 AM, no meals) as the cleanest context
    for therapy calibration.

    Hypothesis: overnight drift direction and magnitude reflect basal rate
    adequacy without meal/carb confounds.
    """
    print("\n=== EXP-1696: Overnight as Therapy Calibrator ===")

    per_patient = {}

    for pat in patients:
        name = pat['name']
        df, pk = pat['df'], pat['pk']
        isf = _extract_isf_scalar(df)
        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        # Extract overnight windows (0-6 AM)
        N = len(glucose)
        overnight_drifts = []
        overnight_net_means = []
        overnight_sd_imbalances = []

        for day_start in range(0, N - STEPS_PER_DAY, STEPS_PER_DAY):
            # 0-6 AM = steps 0-72 within the day
            window_start = day_start
            window_end = min(day_start + 72, N)  # 6h

            g = glucose[window_start:window_end]
            valid = ~np.isnan(g)
            if valid.sum() < 36:  # need at least 3h of data
                continue

            # Skip nights with meals (any carbs in window)
            carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
            if np.sum(carbs[window_start:window_end]) > 1.0:
                continue

            # Compute drift (linear slope)
            t = np.arange(len(g))[valid]
            bg = g[valid]
            if len(t) >= 6:
                slope = np.polyfit(t, bg, 1)[0]  # mg/dL per step
                overnight_drifts.append(float(slope))

                # S×D imbalance during this window
                net_window = sd['net'][window_start:window_end]
                net_mean = float(np.nanmean(net_window))
                overnight_net_means.append(net_mean)

                supply_w = float(np.nanmean(sd['supply'][window_start:window_end]))
                demand_w = float(np.nanmean(sd['demand'][window_start:window_end]))
                overnight_sd_imbalances.append(supply_w - demand_w)

        if len(overnight_drifts) < 5:
            continue

        drift_arr = np.array(overnight_drifts)
        mean_drift = float(np.mean(drift_arr))
        drift_per_hour = mean_drift * STEPS_PER_HOUR

        # Classify basal adequacy
        if abs(drift_per_hour) < 3:
            basal_assessment = 'adequate'
        elif drift_per_hour > 3:
            basal_assessment = 'too_low'  # glucose rising → not enough insulin
        else:
            basal_assessment = 'too_high'  # glucose falling → too much insulin

        per_patient[name] = {
            'n_nights': len(overnight_drifts),
            'mean_drift_per_hour': round(drift_per_hour, 2),
            'drift_std': round(float(np.std(drift_arr)) * STEPS_PER_HOUR, 2),
            'mean_net_flux': round(float(np.mean(overnight_net_means)), 3),
            'mean_sd_imbalance': round(float(np.mean(overnight_sd_imbalances)), 3),
            'basal_assessment': basal_assessment,
            'pct_rising': round(100 * np.mean(drift_arr > 0), 1),
            'pct_falling': round(100 * np.mean(drift_arr < 0), 1),
        }

        print(f"  {name}: drift={drift_per_hour:+.2f} mg/dL/h ({basal_assessment}) "
              f"n={len(overnight_drifts)} nights")

    # Population summary
    assessments = defaultdict(int)
    for p in per_patient.values():
        assessments[p['basal_assessment']] += 1
    print(f"\n  Basal adequacy: {dict(assessments)}")

    # Correlation: overnight drift vs overall TIR
    drifts_clean = []
    tirs_clean = []
    for pat in patients:
        name = pat['name']
        if name not in per_patient:
            continue
        g = pat['df']['glucose'].values.astype(float)
        tir = float(np.nanmean((g >= 70) & (g <= 180)))
        drifts_clean.append(abs(per_patient[name]['mean_drift_per_hour']))
        tirs_clean.append(tir)

    if len(drifts_clean) >= 5:
        r_drift_tir = stats.spearmanr(drifts_clean, tirs_clean)
        print(f"  |Overnight drift| vs TIR: r={r_drift_tir.statistic:.3f} (p={r_drift_tir.pvalue:.3f})")
    else:
        r_drift_tir = type('obj', (object,), {'statistic': float('nan'), 'pvalue': float('nan')})()

    return {
        'experiment': 'EXP-1696',
        'title': 'Overnight as Therapy Calibrator',
        'per_patient': per_patient,
        'basal_adequacy': dict(assessments),
        'r_drift_tir': round(r_drift_tir.statistic, 3),
    }


# ── EXP-1697: Cross-Patient Excursion Profiles ───────────────────────

def exp_1697_excursion_profiles(patients):
    """Do patients cluster by their excursion type distribution?

    Each patient gets a "excursion fingerprint" — the distribution across
    excursion types. Patients with similar fingerprints may benefit from
    similar therapy adjustments.
    """
    print("\n=== EXP-1697: Cross-Patient Excursion Profiles ===")

    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    all_types = set()
    patient_profiles = {}

    for pat in patients:
        name = pat['name']
        df, pk = pat['df'], pat['pk']
        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        excursions = detect_excursions(glucose, carbs, iob, sd)
        valid_days = (~np.isnan(glucose)).sum() / STEPS_PER_DAY

        type_rates = defaultdict(float)
        for exc in excursions:
            type_rates[exc['type']] += 1 / valid_days
            all_types.add(exc['type'])

        patient_profiles[name] = dict(type_rates)

    # Build feature matrix
    type_list = sorted(all_types)
    names = sorted(patient_profiles.keys())
    X = np.array([[patient_profiles[n].get(t, 0) for t in type_list] for n in names])

    # Print profiles
    print(f"  Excursion types: {len(type_list)}")
    print(f"  {'Pat':<5}", end='')
    for t in type_list:
        short = t[:12]
        print(f" {short:>12}", end='')
    print()
    for i, name in enumerate(names):
        print(f"  {name:<5}", end='')
        for j in range(len(type_list)):
            print(f" {X[i,j]:>12.2f}", end='')
        print()

    # Cluster patients
    if len(names) >= 4:
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        best_k, best_sil = 2, -1
        for k in range(2, min(5, len(names) - 1)):
            km = KMeans(n_clusters=k, n_init=10, random_state=42)
            labels = km.fit_predict(X_scaled)
            sil = silhouette_score(X_scaled, labels)
            if sil > best_sil:
                best_sil = sil
                best_k = k

        km = KMeans(n_clusters=best_k, n_init=10, random_state=42)
        labels = km.fit_predict(X_scaled)

        print(f"\n  Optimal clusters: k={best_k} (silhouette={best_sil:.3f})")
        for c in range(best_k):
            members = [names[i] for i in range(len(names)) if labels[i] == c]
            print(f"    Cluster {c}: {', '.join(members)}")
    else:
        best_k, best_sil = 0, 0
        labels = []

    return {
        'experiment': 'EXP-1697',
        'title': 'Cross-Patient Excursion Profiles',
        'excursion_types': type_list,
        'profiles': {n: patient_profiles[n] for n in names},
        'optimal_k': best_k,
        'silhouette': round(best_sil, 3),
        'cluster_labels': {names[i]: int(labels[i]) for i in range(len(names))} if len(labels) > 0 else {},
    }


# ── EXP-1698: Actionability Ranking ──────────────────────────────────

def exp_1698_actionability(patients):
    """Rank excursion types by actionability — which offers the most
    room for improvement if managed better?

    Score = TAR/TBR contribution × (1 - predictability)
    High score = large impact, currently unpredictable = most room to improve
    """
    print("\n=== EXP-1698: Actionability Ranking ===")

    type_data = defaultdict(lambda: {
        'tar_minutes': 0, 'tbr_minutes': 0, 'count': 0,
        'magnitudes': [], 'durations': [], 'rebounds': []
    })
    total_tar = 0
    total_tbr = 0

    for pat in patients:
        df, pk = pat['df'], pat['pk']
        sd = compute_supply_demand(df, pk, calibrate=True)
        glucose = df['glucose'].values.astype(float)
        carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
        iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)

        excursions = detect_excursions(glucose, carbs, iob, sd)

        for exc in excursions:
            seg = glucose[exc['start_idx']:exc['end_idx']+1]
            valid = seg[~np.isnan(seg)]
            tar = int(np.sum(valid > 180)) * 5
            tbr = int(np.sum(valid < 70)) * 5

            td = type_data[exc['type']]
            td['tar_minutes'] += tar
            td['tbr_minutes'] += tbr
            td['count'] += 1
            td['magnitudes'].append(exc['magnitude'])
            td['durations'].append(exc['duration_hours'])

        valid_g = glucose[~np.isnan(glucose)]
        total_tar += int(np.sum(valid_g > 180)) * 5
        total_tbr += int(np.sum(valid_g < 70)) * 5

    # Compute actionability scores
    results = []
    for etype, td in type_data.items():
        if td['count'] < 10:
            continue

        tar_impact = td['tar_minutes'] / max(total_tar, 1)
        tbr_impact = td['tbr_minutes'] / max(total_tbr, 1)

        # Variability in magnitude (higher = harder to predict = more room for improvement)
        mag_cv = float(np.std(td['magnitudes']) / max(np.mean(td['magnitudes']), 1))

        # Overall impact score (weighted)
        impact = tar_impact + tbr_impact
        actionability = impact * (1 + mag_cv)  # higher variability = more potential

        results.append({
            'type': etype,
            'count': td['count'],
            'tar_impact_pct': round(100 * tar_impact, 1),
            'tbr_impact_pct': round(100 * tbr_impact, 1),
            'mean_magnitude': round(float(np.mean(td['magnitudes'])), 1),
            'magnitude_cv': round(mag_cv, 2),
            'actionability_score': round(actionability, 4),
        })

    results.sort(key=lambda x: -x['actionability_score'])

    print(f"\n  {'Type':<25} {'TAR%':>6} {'TBR%':>6} {'MagCV':>6} {'Score':>8} {'Count':>6}")
    for r in results[:10]:
        print(f"  {r['type']:<25} {r['tar_impact_pct']:>5.1f}% {r['tbr_impact_pct']:>5.1f}% "
              f"{r['magnitude_cv']:>6.2f} {r['actionability_score']:>8.4f} {r['count']:>6}")

    return {
        'experiment': 'EXP-1698',
        'title': 'Actionability Ranking',
        'rankings': results[:10],
    }


# ── Figure generation ─────────────────────────────────────────────────

def generate_figures(results, patients):
    """Generate 6 figures for the excursion analysis."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # Fig 1: Excursion taxonomy distribution
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    r1691 = results.get('EXP-1691', {})
    taxonomy = r1691.get('taxonomy', {})
    if taxonomy:
        types = sorted(taxonomy.keys(), key=lambda t: -taxonomy[t]['count'])
        counts = [taxonomy[t]['count'] for t in types]
        mags = [taxonomy[t]['mean_magnitude'] for t in types]

        x = np.arange(len(types))
        axes[0].barh(x, counts, color='steelblue', alpha=0.8)
        axes[0].set_yticks(x)
        axes[0].set_yticklabels(types, fontsize=8)
        axes[0].set_xlabel('Count')
        axes[0].set_title('Excursion Type Distribution')

        axes[1].barh(x, mags, color='coral', alpha=0.8)
        axes[1].set_yticks(x)
        axes[1].set_yticklabels(types, fontsize=8)
        axes[1].set_xlabel('Mean Magnitude (mg/dL)')
        axes[1].set_title('Mean Excursion Magnitude by Type')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'exc-fig1-taxonomy.png', dpi=150)
    plt.close()
    print("  Saved fig1")

    # Fig 2: Cascade chains
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1692 = results.get('EXP-1692', {})
    transitions = r1692.get('top_transitions', {})
    if transitions:
        pairs = list(transitions.keys())[:10]
        counts = [transitions[p] for p in pairs]
        x = np.arange(len(pairs))
        axes[0].barh(x, counts, color='indianred', alpha=0.8)
        axes[0].set_yticks(x)
        axes[0].set_yticklabels(pairs, fontsize=7)
        axes[0].set_xlabel('Count')
        axes[0].set_title('Top Cascade Transitions')

    per_pat = r1692.get('per_patient', {})
    if per_pat:
        names = sorted(per_pat.keys())
        chain_pcts = [per_pat[n]['in_chain_pct'] for n in names]
        x = np.arange(len(names))
        axes[1].bar(x, chain_pcts, color='steelblue', alpha=0.8)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(names)
        axes[1].set_ylabel('% of Excursions in Chains')
        axes[1].set_title('Cascade Involvement per Patient')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'exc-fig2-cascades.png', dpi=150)
    plt.close()
    print("  Saved fig2")

    # Fig 3: Variability decomposition (stacked bar)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1693 = results.get('EXP-1693', {})
    decomp = r1693.get('decomposition', {})
    if decomp:
        types = sorted(decomp.keys(), key=lambda t: -decomp[t]['variance_pct'])[:8]
        var_pcts = [decomp[t]['variance_pct'] for t in types]
        tar_pcts = [decomp[t]['tar_pct'] for t in types]

        x = np.arange(len(types))
        width = 0.35
        axes[0].bar(x - width/2, var_pcts, width, label='Variance %', color='steelblue', alpha=0.8)
        axes[0].bar(x + width/2, tar_pcts, width, label='TAR %', color='coral', alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(types, rotation=45, ha='right', fontsize=8)
        axes[0].set_ylabel('Contribution (%)')
        axes[0].set_title('Variance & TAR by Excursion Type')
        axes[0].legend()

        # Pie chart of variance
        axes[1].pie(var_pcts, labels=types, autopct='%1.0f%%', startangle=90,
                     textprops={'fontsize': 7})
        axes[1].set_title('Variance Decomposition')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'exc-fig3-variability.png', dpi=150)
    plt.close()
    print("  Saved fig3")

    # Fig 4: S×D signatures
    fig, ax = plt.subplots(figsize=(10, 8))

    r1694 = results.get('EXP-1694', {})
    sigs = r1694.get('signatures', {})
    if sigs:
        for etype, sig in sigs.items():
            ax.scatter(sig['supply_mean'], sig['demand_mean'],
                       s=sig['n'] / 2, alpha=0.7, label=f"{etype} (n={sig['n']})")
        ax.set_xlabel('Mean Supply')
        ax.set_ylabel('Mean Demand')
        ax.set_title('Supply-Demand Signatures by Excursion Type')
        # Add diagonal (equilibrium line)
        lim = max(ax.get_xlim()[1], ax.get_ylim()[1])
        ax.plot([0, lim], [0, lim], 'k--', alpha=0.3, label='Equilibrium')
        ax.legend(fontsize=7, loc='best')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'exc-fig4-sd-signatures.png', dpi=150)
    plt.close()
    print("  Saved fig4")

    # Fig 5: Overnight calibration
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1696 = results.get('EXP-1696', {})
    overnight = r1696.get('per_patient', {})
    if overnight:
        names = sorted(overnight.keys())
        drifts = [overnight[n]['mean_drift_per_hour'] for n in names]
        colors = ['green' if abs(d) < 3 else 'red' if d < -3 else 'orange' for d in drifts]

        x = np.arange(len(names))
        axes[0].bar(x, drifts, color=colors, alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(names)
        axes[0].set_ylabel('Drift (mg/dL/h)')
        axes[0].set_title('Overnight Glucose Drift (Basal Adequacy)')
        axes[0].axhline(3, color='orange', linestyle='--', alpha=0.5)
        axes[0].axhline(-3, color='red', linestyle='--', alpha=0.5)
        axes[0].axhline(0, color='green', linestyle='-', alpha=0.3)

        # Drift vs S×D imbalance
        imbalances = [overnight[n]['mean_sd_imbalance'] for n in names]
        axes[1].scatter(imbalances, drifts, s=80, alpha=0.8)
        for i, name in enumerate(names):
            axes[1].annotate(name, (imbalances[i], drifts[i]), fontsize=9)
        axes[1].set_xlabel('S×D Imbalance (supply - demand)')
        axes[1].set_ylabel('Glucose Drift (mg/dL/h)')
        axes[1].set_title('Overnight Drift vs S×D Imbalance')
        r = stats.spearmanr(imbalances, drifts)
        axes[1].set_title(f'Overnight Drift vs S×D Imbalance (r={r.statistic:.2f})')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'exc-fig5-overnight.png', dpi=150)
    plt.close()
    print("  Saved fig5")

    # Fig 6: Actionability ranking
    fig, ax = plt.subplots(figsize=(12, 6))

    r1698 = results.get('EXP-1698', {})
    rankings = r1698.get('rankings', [])
    if rankings:
        types = [r['type'] for r in rankings[:8]]
        scores = [r['actionability_score'] for r in rankings[:8]]
        tar_pcts = [r['tar_impact_pct'] for r in rankings[:8]]

        x = np.arange(len(types))
        bars = ax.bar(x, scores, color='steelblue', alpha=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(types, rotation=45, ha='right', fontsize=8)
        ax.set_ylabel('Actionability Score')
        ax.set_title('Excursion Types Ranked by Improvement Potential')

        # Add TAR% as text on bars
        for i, (bar, tar) in enumerate(zip(bars, tar_pcts)):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'TAR:{tar:.0f}%', ha='center', va='bottom', fontsize=8)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'exc-fig6-actionability.png', dpi=150)
    plt.close()
    print("  Saved fig6")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-1691–1698: Excursion Taxonomy')
    parser.add_argument('--figures', action='store_true')
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients(PATIENTS_DIR)
    print(f"Loaded {len(patients)} patients")

    results = {}

    results['EXP-1691'] = exp_1691_excursion_taxonomy(patients)
    results['EXP-1692'] = exp_1692_cascade_chains(patients)
    results['EXP-1693'] = exp_1693_variability_decomposition(patients)
    results['EXP-1694'] = exp_1694_sd_signatures(patients)
    results['EXP-1695'] = exp_1695_tir_contribution(patients)
    results['EXP-1696'] = exp_1696_overnight_calibrator(patients)
    results['EXP-1697'] = exp_1697_excursion_profiles(patients)
    results['EXP-1698'] = exp_1698_actionability(patients)

    # Save JSONs
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for exp_id, result in results.items():
        fname = f"exp-{exp_id.split('-')[1]}_excursion_taxonomy.json"
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
    r1691 = results.get('EXP-1691', {})
    r1692 = results.get('EXP-1692', {})
    r1693 = results.get('EXP-1693', {})
    r1696 = results.get('EXP-1696', {})
    r1698 = results.get('EXP-1698', {})

    print(f"  Total excursions: {r1691.get('total_excursions', '?')}")
    print(f"  Total cascades: {r1692.get('total_chains', '?')}")
    print(f"  Unaccounted time: {r1693.get('unaccounted_time_pct', '?')}%")
    print(f"  Overnight drift→TIR: r={r1696.get('r_drift_tir', '?')}")
    top = r1698.get('rankings', [{}])[0] if r1698.get('rankings') else {}
    print(f"  Most actionable: {top.get('type', '?')} (score={top.get('actionability_score', '?')})")


if __name__ == '__main__':
    main()
