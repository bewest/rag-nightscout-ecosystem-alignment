#!/usr/bin/env python3
"""EXP-1731 through EXP-1738: Insulin Action Kinetics & Cascade Cost Analysis.

The excursion taxonomy (EXP-1691–1698) revealed two actionable findings:
  1. 37.8% of TAR comes from FALLING glucose (insulin tail problem)
  2. 62% of excursions participate in cascades (non-independent dynamics)

This batch quantifies:
  - How much TAR is purely a kinetics problem (unavoidable with current insulin)
  - The "cascade tax" — extra TAR/TBR caused by cascading vs isolated events
  - Chain-breaking opportunities — where interventions could stop cascades
  - Type-specific prediction improvement over global models

References:
  EXP-1691–1698: Excursion taxonomy, cascade chains, S×D signatures
  EXP-1681–1688: Hyper-rebound predicts TAR (r=0.791)
  EXP-1641–1648: Rescue carb detection-estimation disconnect
  EXP-1631–1636: Corrected S×D model, 97.6% unexplained variance
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
from scipy.optimize import curve_fit

warnings.filterwarnings('ignore', category=RuntimeWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cgmencode.exp_metabolic_flux import load_patients, _extract_isf_scalar
from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_excursion_taxonomy_1691 import detect_excursions

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

PATIENTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'ns-data' / 'patients'
RESULTS_DIR = Path(__file__).parent.parent.parent / 'externals' / 'experiments'
FIGURES_DIR = Path(__file__).parent.parent.parent / 'docs' / '60-research' / 'figures'


def _get_excursions_with_context(pat):
    """Get excursions for a patient with full context."""
    df, pk = pat['df'], pat['pk']
    sd = compute_supply_demand(df, pk, calibrate=True)
    glucose = df['glucose'].values.astype(float)
    carbs = np.nan_to_num(df['carbs'].values.astype(float), nan=0)
    iob = np.nan_to_num(df['iob'].values.astype(float), nan=0)
    excursions = detect_excursions(glucose, carbs, iob, sd)
    return excursions, glucose, carbs, iob, sd


# ── EXP-1731: Insulin Kinetics TAR Decomposition ─────────────────────

def exp_1731_kinetics_tar(patients):
    """Decompose TAR into "kinetics-unavoidable" vs "preventable".

    For each above-range excursion, compute:
    - Time from peak to 180 mg/dL crossing = "kinetics TAR" (unavoidable
      given current insulin speed)
    - Time from 180 crossing on the rise to peak = "preventable TAR"
      (could be reduced by earlier/stronger bolus)
    - Time above 180 after the fall crosses 180 = "overshoot TAR"
      (rebound after over-correction)
    """
    print("\n=== EXP-1731: Insulin Kinetics TAR Decomposition ===")

    # For each rise-fall pair, measure TAR components
    per_type = defaultdict(lambda: {
        'kinetics_tar_min': 0,
        'preventable_tar_min': 0,
        'n_events': 0,
        'peak_bgs': [],
        'fall_rates': [],
    })
    total_kinetics = 0
    total_preventable = 0
    total_tar_min = 0

    for pat in patients:
        excursions, glucose, carbs, iob, sd = _get_excursions_with_context(pat)
        N = len(glucose)

        for exc in excursions:
            seg = glucose[exc['start_idx']:exc['end_idx']+1]
            valid = seg[~np.isnan(seg)]
            if len(valid) < 3:
                continue

            tar_steps = np.sum(valid > 180)
            if tar_steps == 0:
                continue

            total_tar_min += int(tar_steps) * 5

            if exc['direction'] == 'rise':
                # For rises: all TAR is "preventable" (could have bolused earlier/more)
                preventable = int(tar_steps) * 5
                kinetics = 0
                per_type[exc['type']]['preventable_tar_min'] += preventable
                total_preventable += preventable
            else:
                # For falls: TAR is "kinetics" — glucose is coming down but still high
                kinetics = int(tar_steps) * 5
                preventable = 0
                per_type[exc['type']]['kinetics_tar_min'] += kinetics
                total_kinetics += kinetics

                # Compute fall rate through above-range zone
                above = valid[valid > 180]
                if len(above) >= 2:
                    fall_rate = (above[0] - above[-1]) / (len(above) * 5)  # mg/dL/min
                    per_type[exc['type']]['fall_rates'].append(fall_rate)

            per_type[exc['type']]['n_events'] += 1
            per_type[exc['type']]['peak_bgs'].append(float(np.max(valid)))

    # Results
    print(f"  Total TAR: {total_tar_min/60:.0f}h")
    print(f"  Kinetics TAR (falls): {total_kinetics/60:.0f}h "
          f"({100*total_kinetics/max(total_tar_min,1):.1f}%)")
    print(f"  Preventable TAR (rises): {total_preventable/60:.0f}h "
          f"({100*total_preventable/max(total_tar_min,1):.1f}%)")

    results = {}
    print(f"\n  {'Type':<25} {'KinTAR(h)':>10} {'PrevTAR(h)':>11} {'n':>6} {'FallRate':>10}")
    for etype in sorted(per_type.keys(), key=lambda t: -(per_type[t]['kinetics_tar_min'] +
                                                          per_type[t]['preventable_tar_min'])):
        td = per_type[etype]
        kin_h = td['kinetics_tar_min'] / 60
        prev_h = td['preventable_tar_min'] / 60
        fr = np.mean(td['fall_rates']) if td['fall_rates'] else 0
        results[etype] = {
            'kinetics_tar_hours': round(kin_h, 1),
            'preventable_tar_hours': round(prev_h, 1),
            'n_events': td['n_events'],
            'mean_fall_rate_mgdl_min': round(fr, 3),
            'mean_peak_bg': round(float(np.mean(td['peak_bgs'])), 1) if td['peak_bgs'] else 0,
        }
        print(f"  {etype:<25} {kin_h:>9.1f}h {prev_h:>10.1f}h {td['n_events']:>6} "
              f"{fr:>9.3f}")

    return {
        'experiment': 'EXP-1731',
        'title': 'Insulin Kinetics TAR Decomposition',
        'total_tar_hours': round(total_tar_min / 60, 1),
        'kinetics_tar_hours': round(total_kinetics / 60, 1),
        'kinetics_tar_pct': round(100 * total_kinetics / max(total_tar_min, 1), 1),
        'preventable_tar_hours': round(total_preventable / 60, 1),
        'preventable_tar_pct': round(100 * total_preventable / max(total_tar_min, 1), 1),
        'per_type': results,
    }


# ── EXP-1732: Cascade Cost Analysis ──────────────────────────────────

def exp_1732_cascade_cost(patients):
    """Quantify the 'cascade tax' — extra TAR/TBR from cascading events.

    Compare excursions that are part of cascade chains vs isolated events:
    - Do cascaded excursions have higher magnitude?
    - Do they spend more time out of range?
    - What's the total cascade penalty?
    """
    print("\n=== EXP-1732: Cascade Cost Analysis ===")

    from cgmencode.exp_excursion_taxonomy_1691 import detect_excursions

    CASCADE_TRANSITIONS = {
        ('hypo_entry', 'hypo_recovery'), ('hypo_recovery', 'rebound_rise'),
        ('hypo_recovery', 'uam_rise'), ('hypo_recovery', 'hypo_entry'),
        ('hypo_recovery', 'meal_rise'),
        ('rebound_rise', 'insulin_fall'), ('rebound_rise', 'post_rise_fall'),
        ('rebound_rise', 'natural_fall'), ('rebound_rise', 'correction_drop'),
        ('insulin_fall', 'hypo_entry'), ('post_rise_fall', 'hypo_entry'),
        ('natural_fall', 'hypo_entry'), ('correction_drop', 'hypo_entry'),
        ('meal_rise', 'correction_drop'), ('meal_rise', 'insulin_fall'),
        ('uam_rise', 'insulin_fall'), ('uam_rise', 'post_rise_fall'),
        ('uam_rise', 'correction_drop'),
    }

    isolated_stats = {'tar_min': 0, 'tbr_min': 0, 'n': 0, 'mags': [], 'durs': []}
    cascade_stats = {'tar_min': 0, 'tbr_min': 0, 'n': 0, 'mags': [], 'durs': []}
    chain_position_tar = defaultdict(lambda: {'tar_min': 0, 'n': 0})

    for pat in patients:
        excursions, glucose, carbs, iob, sd = _get_excursions_with_context(pat)

        # Identify which excursions are in chains
        in_chain = set()
        chain_positions = {}  # exc_idx → position in chain
        current_chain = [0] if excursions else []
        chain_start = 0

        for i in range(1, len(excursions)):
            prev_type = excursions[i-1]['type']
            curr_type = excursions[i]['type']
            if (prev_type, curr_type) in CASCADE_TRANSITIONS:
                current_chain.append(i)
            else:
                if len(current_chain) >= 2:
                    for pos, idx in enumerate(current_chain):
                        in_chain.add(idx)
                        chain_positions[idx] = pos
                current_chain = [i]

        if len(current_chain) >= 2:
            for pos, idx in enumerate(current_chain):
                in_chain.add(idx)
                chain_positions[idx] = pos

        for i, exc in enumerate(excursions):
            seg = glucose[exc['start_idx']:exc['end_idx']+1]
            valid = seg[~np.isnan(seg)]
            if len(valid) < 2:
                continue

            tar = int(np.sum(valid > 180)) * 5
            tbr = int(np.sum(valid < 70)) * 5

            if i in in_chain:
                cascade_stats['tar_min'] += tar
                cascade_stats['tbr_min'] += tbr
                cascade_stats['n'] += 1
                cascade_stats['mags'].append(exc['magnitude'])
                cascade_stats['durs'].append(exc['duration_hours'])

                pos = chain_positions.get(i, 0)
                pos_key = min(pos, 5)  # cap at position 5+
                chain_position_tar[pos_key]['tar_min'] += tar
                chain_position_tar[pos_key]['n'] += 1
            else:
                isolated_stats['tar_min'] += tar
                isolated_stats['tbr_min'] += tbr
                isolated_stats['n'] += 1
                isolated_stats['mags'].append(exc['magnitude'])
                isolated_stats['durs'].append(exc['duration_hours'])

    # Compare
    iso_tar_per = isolated_stats['tar_min'] / max(isolated_stats['n'], 1)
    cas_tar_per = cascade_stats['tar_min'] / max(cascade_stats['n'], 1)
    iso_tbr_per = isolated_stats['tbr_min'] / max(isolated_stats['n'], 1)
    cas_tbr_per = cascade_stats['tbr_min'] / max(cascade_stats['n'], 1)
    iso_mag = float(np.mean(isolated_stats['mags'])) if isolated_stats['mags'] else 0
    cas_mag = float(np.mean(cascade_stats['mags'])) if cascade_stats['mags'] else 0

    print(f"  Isolated: n={isolated_stats['n']}, TAR/event={iso_tar_per:.1f}min, "
          f"TBR/event={iso_tbr_per:.1f}min, mag={iso_mag:.1f}")
    print(f"  Cascade:  n={cascade_stats['n']}, TAR/event={cas_tar_per:.1f}min, "
          f"TBR/event={cas_tbr_per:.1f}min, mag={cas_mag:.1f}")
    print(f"  Cascade TAR penalty: {cas_tar_per - iso_tar_per:+.1f} min/event "
          f"({100*(cas_tar_per - iso_tar_per)/max(iso_tar_per, 0.1):+.0f}%)")
    print(f"  Cascade TBR penalty: {cas_tbr_per - iso_tbr_per:+.1f} min/event")

    # TAR by chain position
    print(f"\n  TAR by chain position:")
    print(f"  {'Pos':>4} {'TAR/event':>10} {'n':>6}")
    pos_results = {}
    for pos in sorted(chain_position_tar.keys()):
        td = chain_position_tar[pos]
        tar_per = td['tar_min'] / max(td['n'], 1)
        print(f"  {pos:>4} {tar_per:>9.1f}m {td['n']:>6}")
        pos_results[str(pos)] = {
            'tar_per_event_min': round(tar_per, 1),
            'n': td['n'],
        }

    # Cascade tax: total extra TAR from being in cascades
    cascade_tax_hours = cascade_stats['n'] * (cas_tar_per - iso_tar_per) / 60

    print(f"\n  Total cascade tax: {cascade_tax_hours:.0f}h extra TAR")

    return {
        'experiment': 'EXP-1732',
        'title': 'Cascade Cost Analysis',
        'isolated': {
            'n': isolated_stats['n'],
            'tar_per_event_min': round(iso_tar_per, 1),
            'tbr_per_event_min': round(iso_tbr_per, 1),
            'mean_magnitude': round(iso_mag, 1),
        },
        'cascade': {
            'n': cascade_stats['n'],
            'tar_per_event_min': round(cas_tar_per, 1),
            'tbr_per_event_min': round(cas_tbr_per, 1),
            'mean_magnitude': round(cas_mag, 1),
        },
        'cascade_tar_penalty_min': round(cas_tar_per - iso_tar_per, 1),
        'cascade_tar_penalty_pct': round(100 * (cas_tar_per - iso_tar_per) / max(iso_tar_per, 0.1), 0),
        'cascade_tax_hours': round(cascade_tax_hours, 1),
        'position_tar': pos_results,
    }


# ── EXP-1733: Chain-Breaking Analysis ─────────────────────────────────

def exp_1733_chain_breaking(patients):
    """Identify optimal chain-breaking points.

    For each cascade chain, find the transition where intervening would
    save the most TAR/TBR. The "break value" of a transition is the total
    TAR/TBR in downstream chain members that would be avoided.
    """
    print("\n=== EXP-1733: Chain-Breaking Analysis ===")

    CASCADE_TRANSITIONS = {
        ('hypo_entry', 'hypo_recovery'), ('hypo_recovery', 'rebound_rise'),
        ('hypo_recovery', 'uam_rise'), ('hypo_recovery', 'hypo_entry'),
        ('hypo_recovery', 'meal_rise'),
        ('rebound_rise', 'insulin_fall'), ('rebound_rise', 'post_rise_fall'),
        ('rebound_rise', 'natural_fall'), ('rebound_rise', 'correction_drop'),
        ('insulin_fall', 'hypo_entry'), ('post_rise_fall', 'hypo_entry'),
        ('natural_fall', 'hypo_entry'), ('correction_drop', 'hypo_entry'),
        ('meal_rise', 'correction_drop'), ('meal_rise', 'insulin_fall'),
        ('uam_rise', 'insulin_fall'), ('uam_rise', 'post_rise_fall'),
        ('uam_rise', 'correction_drop'),
    }

    # For each transition type, compute the downstream cost saved by breaking there
    transition_break_value = defaultdict(lambda: {
        'downstream_tar_min': 0,
        'downstream_tbr_min': 0,
        'n_breaks': 0,
    })

    for pat in patients:
        excursions, glucose, carbs, iob, sd = _get_excursions_with_context(pat)

        # Build chains
        chains = []
        current_chain = [0] if excursions else []
        for i in range(1, len(excursions)):
            prev_type = excursions[i-1]['type']
            curr_type = excursions[i]['type']
            if (prev_type, curr_type) in CASCADE_TRANSITIONS:
                current_chain.append(i)
            else:
                if len(current_chain) >= 2:
                    chains.append(current_chain)
                current_chain = [i]
        if len(current_chain) >= 2:
            chains.append(current_chain)

        # For each chain, compute break values at each transition
        for chain in chains:
            # Precompute TAR/TBR for each excursion in chain
            chain_tar = []
            chain_tbr = []
            for idx in chain:
                exc = excursions[idx]
                seg = glucose[exc['start_idx']:exc['end_idx']+1]
                valid = seg[~np.isnan(seg)]
                chain_tar.append(int(np.sum(valid > 180)) * 5 if len(valid) > 0 else 0)
                chain_tbr.append(int(np.sum(valid < 70)) * 5 if len(valid) > 0 else 0)

            # Breaking at position i means preventing excursions i+1..end
            for i in range(len(chain) - 1):
                transition = (excursions[chain[i]]['type'],
                              excursions[chain[i+1]]['type'])
                downstream_tar = sum(chain_tar[i+1:])
                downstream_tbr = sum(chain_tbr[i+1:])

                tv = transition_break_value[transition]
                tv['downstream_tar_min'] += downstream_tar
                tv['downstream_tbr_min'] += downstream_tbr
                tv['n_breaks'] += 1

    # Rank by total downstream cost saved
    ranked = []
    for transition, tv in transition_break_value.items():
        total_cost = tv['downstream_tar_min'] + tv['downstream_tbr_min']
        ranked.append({
            'transition': f"{transition[0]}→{transition[1]}",
            'downstream_tar_hours': round(tv['downstream_tar_min'] / 60, 1),
            'downstream_tbr_hours': round(tv['downstream_tbr_min'] / 60, 1),
            'n_occurrences': tv['n_breaks'],
            'avg_tar_saved_min': round(tv['downstream_tar_min'] / max(tv['n_breaks'], 1), 1),
            'avg_tbr_saved_min': round(tv['downstream_tbr_min'] / max(tv['n_breaks'], 1), 1),
            'total_cost_hours': round(total_cost / 60, 1),
        })
    ranked.sort(key=lambda x: -x['total_cost_hours'])

    print(f"  Top 10 chain-breaking opportunities:")
    print(f"  {'Transition':<45} {'TAR saved':>10} {'TBR saved':>10} {'n':>6}")
    for r in ranked[:10]:
        print(f"  {r['transition']:<45} {r['downstream_tar_hours']:>9.1f}h "
              f"{r['downstream_tbr_hours']:>9.1f}h {r['n_occurrences']:>6}")

    return {
        'experiment': 'EXP-1733',
        'title': 'Chain-Breaking Analysis',
        'top_break_points': ranked[:15],
    }


# ── EXP-1734: Insulin Speed Sensitivity ──────────────────────────────

def exp_1734_insulin_speed(patients):
    """Simulate how faster insulin would affect TAR.

    For each insulin_fall excursion, compute how much TAR would be saved
    if the fall rate were 1.5× or 2× faster. This gives a concrete
    quantification of the TAR benefit from faster-acting insulin.
    """
    print("\n=== EXP-1734: Insulin Speed Sensitivity ===")

    speedups = [1.0, 1.25, 1.5, 2.0, 3.0]
    speedup_tar = {s: 0 for s in speedups}
    total_events = 0

    for pat in patients:
        excursions, glucose, carbs, iob, sd = _get_excursions_with_context(pat)

        for exc in excursions:
            if exc['type'] not in ('insulin_fall', 'post_rise_fall', 'correction_drop'):
                continue

            seg = glucose[exc['start_idx']:exc['end_idx']+1]
            valid_mask = ~np.isnan(seg)
            if valid_mask.sum() < 3:
                continue

            # Only care about the above-range portion
            peak_bg = seg[valid_mask][0]  # start of fall
            if peak_bg <= 180:
                continue

            total_events += 1
            seg_valid = seg[valid_mask]

            for speed in speedups:
                # Simulate faster fall: compress the time axis
                if speed == 1.0:
                    simulated = seg_valid
                else:
                    # Interpolate to get glucose at compressed time points
                    orig_t = np.arange(len(seg_valid))
                    new_t = np.arange(0, len(seg_valid), speed)
                    # Fall reaches target faster, then stays there
                    simulated = np.interp(orig_t, new_t, seg_valid[:len(new_t)])
                    # After the compressed fall completes, glucose stays at end value
                    if len(new_t) < len(seg_valid):
                        end_val = seg_valid[min(len(seg_valid)-1, len(new_t))]
                        simulated[len(new_t):] = min(end_val, 180)

                tar_steps = np.sum(simulated > 180)
                speedup_tar[speed] += int(tar_steps) * 5

    print(f"  Analyzed {total_events} fall events above range")
    print(f"\n  {'Speed':>6} {'TAR(h)':>8} {'Saved(h)':>9} {'Saved%':>7}")
    baseline_tar = speedup_tar[1.0]
    results = {}
    for speed in speedups:
        tar_h = speedup_tar[speed] / 60
        saved_h = (baseline_tar - speedup_tar[speed]) / 60
        saved_pct = 100 * saved_h / max(baseline_tar / 60, 0.1)
        results[str(speed)] = {
            'tar_hours': round(tar_h, 1),
            'saved_hours': round(saved_h, 1),
            'saved_pct': round(saved_pct, 1),
        }
        print(f"  {speed:>5.2f}× {tar_h:>7.1f}h {saved_h:>8.1f}h {saved_pct:>6.1f}%")

    return {
        'experiment': 'EXP-1734',
        'title': 'Insulin Speed Sensitivity',
        'n_events': total_events,
        'speedup_results': results,
    }


# ── EXP-1735: Type-Specific Prediction ───────────────────────────────

def exp_1735_type_prediction(patients):
    """Can knowing the excursion type improve glucose prediction?

    Build simple regression models for 30-min-ahead glucose prediction:
    1. Global model (all excursions together)
    2. Type-stratified model (separate per excursion type)

    Compare R² to quantify the value of type-aware prediction.
    """
    print("\n=== EXP-1735: Type-Specific Prediction ===")

    global_X, global_y = [], []
    type_X = defaultdict(list)
    type_y = defaultdict(list)

    for pat in patients:
        excursions, glucose, carbs, iob, sd = _get_excursions_with_context(pat)
        N = len(glucose)

        for exc in excursions:
            # Predict glucose 6 steps (30 min) after excursion midpoint
            mid = (exc['start_idx'] + exc['end_idx']) // 2
            target_idx = mid + 6
            if target_idx >= N or np.isnan(glucose[target_idx]):
                continue
            if np.isnan(glucose[mid]):
                continue

            # Features: current glucose, rate, supply, demand, IOB
            features = [
                glucose[mid],
                exc['rate'] * (1 if exc['direction'] == 'rise' else -1),
                exc['supply_mean'],
                exc['demand_mean'],
                exc['iob_at_start'],
            ]

            global_X.append(features)
            global_y.append(glucose[target_idx])
            type_X[exc['type']].append(features)
            type_y[exc['type']].append(glucose[target_idx])

    global_X = np.array(global_X)
    global_y = np.array(global_y)

    # Global model
    from numpy.linalg import lstsq
    # Add intercept
    X_aug = np.column_stack([global_X, np.ones(len(global_X))])
    coeffs, _, _, _ = lstsq(X_aug, global_y, rcond=None)
    global_pred = X_aug @ coeffs
    ss_res = np.sum((global_y - global_pred) ** 2)
    ss_tot = np.sum((global_y - np.mean(global_y)) ** 2)
    global_r2 = 1 - ss_res / ss_tot

    print(f"  Global model R²: {global_r2:.4f} (n={len(global_y)})")

    # Type-stratified models
    type_r2s = {}
    type_n = {}
    weighted_ss_res = 0
    weighted_ss_tot = 0

    print(f"\n  {'Type':<25} {'R²':>8} {'n':>7} {'RMSE':>8}")
    for etype in sorted(type_X.keys()):
        Xt = np.array(type_X[etype])
        yt = np.array(type_y[etype])
        if len(Xt) < 20:
            continue

        Xt_aug = np.column_stack([Xt, np.ones(len(Xt))])
        try:
            c, _, _, _ = lstsq(Xt_aug, yt, rcond=None)
            pred = Xt_aug @ c
            ss_r = np.sum((yt - pred) ** 2)
            ss_t = np.sum((yt - np.mean(yt)) ** 2)
            r2 = 1 - ss_r / ss_t if ss_t > 0 else 0
            rmse = np.sqrt(ss_r / len(yt))
        except Exception:
            r2, rmse = 0, 0
            ss_r, ss_t = 0, 0

        type_r2s[etype] = round(r2, 4)
        type_n[etype] = len(yt)
        weighted_ss_res += ss_r
        weighted_ss_tot += ss_t

        print(f"  {etype:<25} {r2:>7.4f} {len(yt):>7} {rmse:>7.1f}")

    pooled_r2 = 1 - weighted_ss_res / max(weighted_ss_tot, 1)
    improvement = pooled_r2 - global_r2

    print(f"\n  Global R²: {global_r2:.4f}")
    print(f"  Pooled type-stratified R²: {pooled_r2:.4f}")
    print(f"  Improvement: {improvement:+.4f}")

    return {
        'experiment': 'EXP-1735',
        'title': 'Type-Specific Prediction',
        'global_r2': round(global_r2, 4),
        'pooled_stratified_r2': round(pooled_r2, 4),
        'improvement': round(improvement, 4),
        'type_r2': type_r2s,
        'type_n': type_n,
    }


# ── EXP-1736: UAM Subcategorization ──────────────────────────────────

def exp_1736_uam_subtypes(patients):
    """Subcategorize UAM rises by their metabolic signature.

    UAM rises (16.6%) are the largest single category. Can we distinguish:
    - Actual unlogged meals (high supply, sustained rise)
    - Dawn phenomenon (early morning, gradual)
    - Stress/exercise recovery (variable, no pattern)
    - Counter-regulatory (post-hypo, liver glycogen release)
    """
    print("\n=== EXP-1736: UAM Subcategorization ===")

    uam_features = []

    for pat in patients:
        excursions, glucose, carbs, iob, sd = _get_excursions_with_context(pat)
        N = len(glucose)

        for exc in excursions:
            if exc['type'] != 'uam_rise':
                continue

            # Compute features for subcategorization
            tod_hour = exc['tod_hour']
            magnitude = exc['magnitude']
            duration = exc['duration_hours']
            rate = exc['rate']
            supply = exc['supply_mean']
            demand = exc['demand_mean']
            iob_start = exc['iob_at_start']

            # Was there a recent hypo (within 2h before)?
            window_start = max(0, exc['start_idx'] - 24)  # 2h
            pre_glucose = glucose[window_start:exc['start_idx']]
            recent_hypo = float(np.nanmin(pre_glucose)) < 70 if len(pre_glucose) > 0 and not np.all(np.isnan(pre_glucose)) else False

            # Supply pattern: sustained high vs brief spike
            supply_seg = sd['supply'][exc['start_idx']:exc['end_idx']+1]
            supply_sustained = float(np.sum(supply_seg > np.mean(supply_seg))) / max(len(supply_seg), 1)

            uam_features.append({
                'tod_hour': tod_hour,
                'magnitude': magnitude,
                'duration': duration,
                'rate': rate,
                'supply': supply,
                'demand': demand,
                'iob_start': iob_start,
                'recent_hypo': recent_hypo,
                'supply_sustained': supply_sustained,
                'patient': pat['name'],
            })

    # Rule-based subcategorization
    subtypes = defaultdict(int)
    subtype_mags = defaultdict(list)
    subtype_tods = defaultdict(list)

    for f in uam_features:
        if f['recent_hypo']:
            subtype = 'counterreg_rebound'
        elif 4 <= f['tod_hour'] <= 10 and f['rate'] < 2.0 and f['magnitude'] < 50:
            subtype = 'dawn_phenomenon'
        elif f['supply'] > 4.0 and f['supply_sustained'] > 0.6:
            subtype = 'unlogged_meal'
        elif f['magnitude'] < 30 and f['duration'] < 0.8:
            subtype = 'brief_fluctuation'
        else:
            subtype = 'unknown_uam'

        subtypes[subtype] += 1
        subtype_mags[subtype].append(f['magnitude'])
        subtype_tods[subtype].append(f['tod_hour'])

    total = len(uam_features)
    print(f"  Total UAM rises: {total}")
    print(f"\n  {'Subtype':<25} {'Count':>6} {'%':>6} {'MagMean':>8} {'ToD':>6}")
    results = {}
    for subtype in sorted(subtypes.keys(), key=lambda s: -subtypes[s]):
        n = subtypes[subtype]
        pct = 100 * n / total
        mag = float(np.mean(subtype_mags[subtype]))
        tod = float(np.mean(subtype_tods[subtype]))
        results[subtype] = {
            'count': n,
            'pct': round(pct, 1),
            'mean_magnitude': round(mag, 1),
            'mean_tod_hour': round(tod, 1),
        }
        print(f"  {subtype:<25} {n:>6} {pct:>5.1f}% {mag:>7.1f} {tod:>5.1f}h")

    return {
        'experiment': 'EXP-1736',
        'title': 'UAM Subcategorization',
        'total_uam': total,
        'subtypes': results,
    }


# ── EXP-1737: Excursion Duration vs ISF/DIA ──────────────────────────

def exp_1737_duration_settings(patients):
    """Do therapy settings predict excursion behavior?

    Correlate patient-level ISF and DIA with:
    - Mean insulin_fall duration (should correlate with DIA)
    - Mean insulin_fall rate (should correlate with ISF)
    - Mean hypo_recovery duration
    """
    print("\n=== EXP-1737: Excursion Duration vs Therapy Settings ===")

    patient_data = []

    for pat in patients:
        name = pat['name']
        df, pk = pat['df'], pat['pk']
        isf = _extract_isf_scalar(df)
        dia = df.attrs.get('patient_dia', 5.0)

        excursions, glucose, carbs, iob, sd = _get_excursions_with_context(pat)

        # Collect type-specific durations and rates
        type_stats = defaultdict(lambda: {'durations': [], 'rates': [], 'mags': []})
        for exc in excursions:
            ts = type_stats[exc['type']]
            ts['durations'].append(exc['duration_hours'])
            ts['rates'].append(exc['rate'])
            ts['mags'].append(exc['magnitude'])

        entry = {
            'name': name,
            'isf': isf,
            'dia': dia,
        }

        for etype in ['insulin_fall', 'hypo_recovery', 'meal_rise', 'correction_drop']:
            ts = type_stats.get(etype, {'durations': [], 'rates': [], 'mags': []})
            if ts['durations']:
                entry[f'{etype}_dur'] = float(np.mean(ts['durations']))
                entry[f'{etype}_rate'] = float(np.mean(ts['rates']))
                entry[f'{etype}_n'] = len(ts['durations'])
            else:
                entry[f'{etype}_dur'] = np.nan
                entry[f'{etype}_rate'] = np.nan
                entry[f'{etype}_n'] = 0

        patient_data.append(entry)

    # Correlations
    correlations = {}
    pairs = [
        ('isf', 'insulin_fall_rate', 'ISF vs insulin fall rate'),
        ('dia', 'insulin_fall_dur', 'DIA vs insulin fall duration'),
        ('isf', 'hypo_recovery_dur', 'ISF vs hypo recovery duration'),
        ('isf', 'meal_rise_dur', 'ISF vs meal rise duration'),
    ]

    print(f"\n  {'Correlation':<40} {'r':>6} {'p':>8} {'n':>4}")
    for x_key, y_key, label in pairs:
        x_vals = [d[x_key] for d in patient_data if not np.isnan(d.get(y_key, np.nan))]
        y_vals = [d[y_key] for d in patient_data if not np.isnan(d.get(y_key, np.nan))]

        if len(x_vals) >= 5:
            r, p = stats.spearmanr(x_vals, y_vals)
            print(f"  {label:<40} {r:>5.3f} {p:>7.4f} {len(x_vals):>4}")
            correlations[label] = {'r': round(r, 3), 'p': round(p, 4), 'n': len(x_vals)}
        else:
            print(f"  {label:<40} insufficient data")

    return {
        'experiment': 'EXP-1737',
        'title': 'Excursion Duration vs Therapy Settings',
        'correlations': correlations,
        'patient_data': [{k: round(v, 3) if isinstance(v, float) else v
                          for k, v in d.items()} for d in patient_data],
    }


# ── EXP-1738: Hypo-Cascade Anatomy ───────────────────────────────────

def exp_1738_hypo_cascade_anatomy(patients):
    """Detailed anatomy of hypo-initiated cascades.

    For chains that START with hypo_entry, trace the full downstream cost:
    - What percentage escalate to rebound hyperglycemia?
    - What's the total glucose excursion from nadir to peak rebound?
    - How long until glucose returns to stable range (70-180)?
    - What fraction have secondary hypos (double-dip)?
    """
    print("\n=== EXP-1738: Hypo-Cascade Anatomy ===")

    CASCADE_TRANSITIONS = {
        ('hypo_entry', 'hypo_recovery'), ('hypo_recovery', 'rebound_rise'),
        ('hypo_recovery', 'uam_rise'), ('hypo_recovery', 'hypo_entry'),
        ('hypo_recovery', 'meal_rise'),
        ('rebound_rise', 'insulin_fall'), ('rebound_rise', 'post_rise_fall'),
        ('rebound_rise', 'natural_fall'), ('rebound_rise', 'correction_drop'),
        ('insulin_fall', 'hypo_entry'), ('post_rise_fall', 'hypo_entry'),
        ('natural_fall', 'hypo_entry'), ('correction_drop', 'hypo_entry'),
        ('meal_rise', 'correction_drop'), ('meal_rise', 'insulin_fall'),
        ('uam_rise', 'insulin_fall'), ('uam_rise', 'post_rise_fall'),
        ('uam_rise', 'correction_drop'),
    }

    hypo_chains = []
    non_hypo_chains = []

    for pat in patients:
        excursions, glucose, carbs, iob, sd = _get_excursions_with_context(pat)

        # Build chains
        chains = []
        current_chain = [0] if excursions else []
        for i in range(1, len(excursions)):
            prev_type = excursions[i-1]['type']
            curr_type = excursions[i]['type']
            if (prev_type, curr_type) in CASCADE_TRANSITIONS:
                current_chain.append(i)
            else:
                if len(current_chain) >= 2:
                    chains.append(current_chain)
                current_chain = [i]
        if len(current_chain) >= 2:
            chains.append(current_chain)

        for chain in chains:
            chain_types = [excursions[idx]['type'] for idx in chain]
            start_exc = excursions[chain[0]]
            end_exc = excursions[chain[-1]]

            # Get glucose trace across entire chain
            chain_start = start_exc['start_idx']
            chain_end = end_exc['end_idx']
            chain_glucose = glucose[chain_start:chain_end+1]
            valid = chain_glucose[~np.isnan(chain_glucose)]

            if len(valid) < 3:
                continue

            nadir = float(np.min(valid))
            peak = float(np.max(valid))
            total_range = peak - nadir
            duration_h = (chain_end - chain_start) / STEPS_PER_HOUR
            tar_steps = int(np.sum(valid > 180))
            tbr_steps = int(np.sum(valid < 70))

            chain_info = {
                'length': len(chain),
                'types': chain_types,
                'nadir': nadir,
                'peak': peak,
                'total_range': total_range,
                'duration_hours': duration_h,
                'tar_min': tar_steps * 5,
                'tbr_min': tbr_steps * 5,
                'has_rebound': 'rebound_rise' in chain_types or 'uam_rise' in chain_types,
                'has_double_dip': chain_types.count('hypo_entry') >= 2,
                'reaches_hyper': peak > 180,
                'patient': pat['name'],
            }

            if chain_types[0] == 'hypo_entry':
                hypo_chains.append(chain_info)
            else:
                non_hypo_chains.append(chain_info)

    # Analyze hypo-initiated chains
    n_hypo = len(hypo_chains)
    if n_hypo > 0:
        pct_rebound = 100 * sum(1 for c in hypo_chains if c['has_rebound']) / n_hypo
        pct_double = 100 * sum(1 for c in hypo_chains if c['has_double_dip']) / n_hypo
        pct_hyper = 100 * sum(1 for c in hypo_chains if c['reaches_hyper']) / n_hypo
        mean_range = float(np.mean([c['total_range'] for c in hypo_chains]))
        mean_dur = float(np.mean([c['duration_hours'] for c in hypo_chains]))
        mean_tar = float(np.mean([c['tar_min'] for c in hypo_chains]))
        mean_tbr = float(np.mean([c['tbr_min'] for c in hypo_chains]))

        print(f"  Hypo-initiated chains: {n_hypo}")
        print(f"  With rebound spike: {pct_rebound:.1f}%")
        print(f"  With double-dip hypo: {pct_double:.1f}%")
        print(f"  Reaching hyperglycemia: {pct_hyper:.1f}%")
        print(f"  Mean nadir-to-peak range: {mean_range:.1f} mg/dL")
        print(f"  Mean duration: {mean_dur:.1f}h")
        print(f"  Mean TAR per chain: {mean_tar:.1f}min")
        print(f"  Mean TBR per chain: {mean_tbr:.1f}min")

        # Chain length distribution
        lengths = [c['length'] for c in hypo_chains]
        print(f"\n  Chain length distribution:")
        for length in sorted(set(lengths)):
            n = sum(1 for l in lengths if l == length)
            pct = 100 * n / n_hypo
            print(f"    Length {length}: {n} ({pct:.1f}%)")

    # Compare hypo-initiated vs other chains
    n_other = len(non_hypo_chains)
    if n_hypo > 0 and n_other > 0:
        hypo_tar = [c['tar_min'] for c in hypo_chains]
        other_tar = [c['tar_min'] for c in non_hypo_chains]
        u_stat, u_p = stats.mannwhitneyu(hypo_tar, other_tar, alternative='greater')
        print(f"\n  Hypo-chains mean TAR: {np.mean(hypo_tar):.1f}min vs "
              f"other chains: {np.mean(other_tar):.1f}min (U-test p={u_p:.4f})")

    return {
        'experiment': 'EXP-1738',
        'title': 'Hypo-Cascade Anatomy',
        'n_hypo_chains': n_hypo,
        'n_other_chains': n_other,
        'pct_rebound': round(pct_rebound, 1) if n_hypo else 0,
        'pct_double_dip': round(pct_double, 1) if n_hypo else 0,
        'pct_reaches_hyper': round(pct_hyper, 1) if n_hypo else 0,
        'mean_range': round(mean_range, 1) if n_hypo else 0,
        'mean_duration_hours': round(mean_dur, 1) if n_hypo else 0,
        'mean_tar_min': round(mean_tar, 1) if n_hypo else 0,
        'mean_tbr_min': round(mean_tbr, 1) if n_hypo else 0,
    }


# ── Figure generation ─────────────────────────────────────────────────

def generate_figures(results, patients):
    """Generate 6 figures for the kinetics & cascade analysis."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # Fig 1: Kinetics vs Preventable TAR
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    r1731 = results.get('EXP-1731', {})
    kin_pct = r1731.get('kinetics_tar_pct', 0)
    prev_pct = r1731.get('preventable_tar_pct', 0)
    axes[0].pie([kin_pct, prev_pct],
                labels=['Kinetics\n(falls)', 'Preventable\n(rises)'],
                autopct='%1.1f%%', colors=['#ff7f7f', '#7fbfff'],
                startangle=90, textprops={'fontsize': 12})
    axes[0].set_title('TAR Decomposition:\nKinetics vs Preventable')

    per_type = r1731.get('per_type', {})
    if per_type:
        types = sorted(per_type.keys(),
                       key=lambda t: -(per_type[t]['kinetics_tar_hours'] +
                                       per_type[t]['preventable_tar_hours']))[:8]
        kin_h = [per_type[t]['kinetics_tar_hours'] for t in types]
        prev_h = [per_type[t]['preventable_tar_hours'] for t in types]
        x = np.arange(len(types))
        axes[1].barh(x, kin_h, color='#ff7f7f', alpha=0.8, label='Kinetics TAR')
        axes[1].barh(x, prev_h, left=kin_h, color='#7fbfff', alpha=0.8, label='Preventable TAR')
        axes[1].set_yticks(x)
        axes[1].set_yticklabels(types, fontsize=8)
        axes[1].set_xlabel('Hours')
        axes[1].set_title('TAR by Type (Kinetics vs Preventable)')
        axes[1].legend()

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'kin-fig1-tar-decomp.png', dpi=150)
    plt.close()
    print("  Saved fig1")

    # Fig 2: Cascade vs Isolated
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1732 = results.get('EXP-1732', {})
    iso = r1732.get('isolated', {})
    cas = r1732.get('cascade', {})
    if iso and cas:
        categories = ['TAR/event\n(min)', 'TBR/event\n(min)', 'Magnitude\n(mg/dL)']
        iso_vals = [iso['tar_per_event_min'], iso['tbr_per_event_min'], iso['mean_magnitude']]
        cas_vals = [cas['tar_per_event_min'], cas['tbr_per_event_min'], cas['mean_magnitude']]
        x = np.arange(len(categories))
        width = 0.35
        axes[0].bar(x - width/2, iso_vals, width, label=f"Isolated (n={iso['n']})",
                     color='steelblue', alpha=0.8)
        axes[0].bar(x + width/2, cas_vals, width, label=f"Cascade (n={cas['n']})",
                     color='indianred', alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(categories)
        axes[0].set_title('Isolated vs Cascade Excursions')
        axes[0].legend()

    pos_tar = r1732.get('position_tar', {})
    if pos_tar:
        positions = sorted(pos_tar.keys(), key=lambda p: int(p))
        tars = [pos_tar[p]['tar_per_event_min'] for p in positions]
        axes[1].bar(range(len(positions)), tars, color='indianred', alpha=0.8)
        axes[1].set_xlabel('Position in Chain')
        axes[1].set_ylabel('TAR per Event (min)')
        axes[1].set_title('TAR Accumulation Along Cascade Chains')
        axes[1].set_xticks(range(len(positions)))
        axes[1].set_xticklabels(positions)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'kin-fig2-cascade-cost.png', dpi=150)
    plt.close()
    print("  Saved fig2")

    # Fig 3: Chain-breaking opportunities
    fig, ax = plt.subplots(figsize=(14, 7))

    r1733 = results.get('EXP-1733', {})
    breaks = r1733.get('top_break_points', [])
    if breaks:
        transitions = [b['transition'] for b in breaks[:10]]
        tar_saved = [b['downstream_tar_hours'] for b in breaks[:10]]
        tbr_saved = [b['downstream_tbr_hours'] for b in breaks[:10]]
        x = np.arange(len(transitions))
        ax.barh(x, tar_saved, color='coral', alpha=0.8, label='TAR saved (h)')
        ax.barh(x, tbr_saved, left=tar_saved, color='steelblue', alpha=0.8,
                label='TBR saved (h)')
        ax.set_yticks(x)
        ax.set_yticklabels(transitions, fontsize=7)
        ax.set_xlabel('Hours Saved by Breaking Chain at This Transition')
        ax.set_title('Top Chain-Breaking Opportunities')
        ax.legend()

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'kin-fig3-chain-breaking.png', dpi=150)
    plt.close()
    print("  Saved fig3")

    # Fig 4: Insulin speed sensitivity
    fig, ax = plt.subplots(figsize=(10, 6))

    r1734 = results.get('EXP-1734', {})
    speedup = r1734.get('speedup_results', {})
    if speedup:
        speeds = sorted(speedup.keys(), key=float)
        tar_hours = [speedup[s]['tar_hours'] for s in speeds]
        saved_pct = [speedup[s]['saved_pct'] for s in speeds]

        ax.plot([float(s) for s in speeds], tar_hours, 'o-', color='indianred',
                linewidth=2, markersize=8)
        ax.set_xlabel('Insulin Speed Multiplier')
        ax.set_ylabel('TAR (hours)')
        ax.set_title('TAR Reduction from Faster Insulin Action')

        for s, h, pct in zip(speeds, tar_hours, saved_pct):
            if float(s) > 1.0:
                ax.annotate(f'-{pct:.0f}%', (float(s), h),
                           textcoords="offset points", xytext=(10, 5), fontsize=10)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'kin-fig4-insulin-speed.png', dpi=150)
    plt.close()
    print("  Saved fig4")

    # Fig 5: UAM subtypes
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1736 = results.get('EXP-1736', {})
    subtypes = r1736.get('subtypes', {})
    if subtypes:
        names = sorted(subtypes.keys(), key=lambda s: -subtypes[s]['count'])
        counts = [subtypes[s]['count'] for s in names]
        mags = [subtypes[s]['mean_magnitude'] for s in names]

        x = np.arange(len(names))
        axes[0].barh(x, counts, color='steelblue', alpha=0.8)
        axes[0].set_yticks(x)
        axes[0].set_yticklabels(names, fontsize=9)
        axes[0].set_xlabel('Count')
        axes[0].set_title('UAM Rise Subcategories')

        axes[1].barh(x, mags, color='coral', alpha=0.8)
        axes[1].set_yticks(x)
        axes[1].set_yticklabels(names, fontsize=9)
        axes[1].set_xlabel('Mean Magnitude (mg/dL)')
        axes[1].set_title('UAM Subtype Magnitudes')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'kin-fig5-uam-subtypes.png', dpi=150)
    plt.close()
    print("  Saved fig5")

    # Fig 6: Hypo cascade anatomy
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1738 = results.get('EXP-1738', {})
    if r1738.get('n_hypo_chains', 0) > 0:
        # Outcome pie chart
        outcomes = {
            'Rebound only': r1738['pct_rebound'] - r1738['pct_double_dip'],
            'Double-dip hypo': r1738['pct_double_dip'],
            'Simple recovery': 100 - r1738['pct_rebound'],
        }
        outcomes = {k: max(v, 0) for k, v in outcomes.items()}
        axes[0].pie(list(outcomes.values()), labels=list(outcomes.keys()),
                     autopct='%1.0f%%', colors=['coral', 'red', 'lightgreen'],
                     startangle=90, textprops={'fontsize': 10})
        axes[0].set_title('Hypo-Initiated Chain Outcomes')

        # Key metrics
        metrics = {
            'Nadir-to-peak\n(mg/dL)': r1738['mean_range'],
            'Duration\n(hours)': r1738['mean_duration_hours'],
            'TAR\n(min/chain)': r1738['mean_tar_min'],
            'TBR\n(min/chain)': r1738['mean_tbr_min'],
        }
        x = np.arange(len(metrics))
        axes[1].bar(x, list(metrics.values()), color='steelblue', alpha=0.8)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(list(metrics.keys()), fontsize=9)
        axes[1].set_title('Hypo-Cascade Average Metrics')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'kin-fig6-hypo-anatomy.png', dpi=150)
    plt.close()
    print("  Saved fig6")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EXP-1731–1738: Insulin Kinetics & Cascade Cost')
    parser.add_argument('--figures', action='store_true')
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients(PATIENTS_DIR)
    print(f"Loaded {len(patients)} patients")

    results = {}

    results['EXP-1731'] = exp_1731_kinetics_tar(patients)
    results['EXP-1732'] = exp_1732_cascade_cost(patients)
    results['EXP-1733'] = exp_1733_chain_breaking(patients)
    results['EXP-1734'] = exp_1734_insulin_speed(patients)
    results['EXP-1735'] = exp_1735_type_prediction(patients)
    results['EXP-1736'] = exp_1736_uam_subtypes(patients)
    results['EXP-1737'] = exp_1737_duration_settings(patients)
    results['EXP-1738'] = exp_1738_hypo_cascade_anatomy(patients)

    # Save JSONs
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for exp_id, result in results.items():
        fname = f"exp-{exp_id.split('-')[1]}_kinetics_cascade.json"
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
    r1731 = results.get('EXP-1731', {})
    r1732 = results.get('EXP-1732', {})
    r1733 = results.get('EXP-1733', {})
    r1734 = results.get('EXP-1734', {})
    r1735 = results.get('EXP-1735', {})
    r1738 = results.get('EXP-1738', {})

    print(f"  Kinetics TAR: {r1731.get('kinetics_tar_pct', '?')}% of total")
    print(f"  Cascade TAR penalty: {r1732.get('cascade_tar_penalty_min', '?')} min/event")
    top_break = r1733.get('top_break_points', [{}])[0] if r1733.get('top_break_points') else {}
    print(f"  Best chain-break: {top_break.get('transition', '?')} "
          f"({top_break.get('total_cost_hours', '?')}h saved)")
    speed_2x = r1734.get('speedup_results', {}).get('2.0', {})
    print(f"  2× insulin speed: {speed_2x.get('saved_pct', '?')}% TAR reduction")
    print(f"  Type-aware prediction: ΔR²={r1735.get('improvement', '?')}")
    print(f"  Hypo-cascade rebound rate: {r1738.get('pct_rebound', '?')}%")


if __name__ == '__main__':
    main()
