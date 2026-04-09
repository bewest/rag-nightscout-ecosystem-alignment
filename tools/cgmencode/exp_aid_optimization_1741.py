#!/usr/bin/env python3
"""EXP-1741 through EXP-1748: AID Response Optimization & Information Ceiling.

The three-ceilings framework (EXP-1731) identified two high-value targets:
  1. Post-hypo AID behavior (31% double-dip, 61% rebound hyperglycemia)
  2. UAM response latency (805h TAR from UAM→insulin_fall chains)

This batch simulates AID algorithm modifications to quantify maximum
achievable improvement with CURRENT data, answering: "How much could a
smarter AID algorithm improve outcomes without any new sensors?"

References:
  EXP-1731–1738: Three ceilings, cascade cost, kinetics
  EXP-1691–1698: Excursion taxonomy
  EXP-1641–1648: Rescue carb detection F1=0.91
  EXP-1681–1688: Over-rescue 53%, cascade cycle r=0.791
"""

import sys
import json
import argparse
import warnings
from pathlib import Path
from collections import defaultdict

import numpy as np
from scipy import stats

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


# ── EXP-1741: Post-Hypo Insulin Suspension Duration ──────────────────

def exp_1741_post_hypo_suspension(patients):
    """How long does the AID suspend insulin after hypo, and is it enough?

    Measure IOB trajectory after hypo nadir and correlate suspension
    duration with rebound hyperglycemia risk.

    Hypothesis: Patients with shorter post-hypo insulin suspension have
    higher rates of double-dip hypos (insufficient suspension) while
    those with longer suspension have more rebound hyperglycemia
    (rescue carbs + no insulin = spike).
    """
    print("\n=== EXP-1741: Post-Hypo Insulin Suspension Duration ===")

    all_episodes = []

    for pat in patients:
        excursions, glucose, carbs, iob, sd = _get_excursions_with_context(pat)
        name = pat['name']
        N = len(glucose)

        for i, exc in enumerate(excursions):
            if exc['type'] != 'hypo_entry':
                continue

            nadir_idx = exc['end_idx']
            if nadir_idx + 72 >= N:  # need 6h post-nadir
                continue

            # IOB at nadir and post-nadir trajectory
            post_iob = iob[nadir_idx:nadir_idx+72]
            post_glucose = glucose[nadir_idx:nadir_idx+72]

            # Find how long IOB stays below nadir IOB (suspension period)
            nadir_iob = float(iob[nadir_idx]) if not np.isnan(iob[nadir_idx]) else 0
            suspension_steps = 0
            for step in range(1, len(post_iob)):
                if not np.isnan(post_iob[step]) and post_iob[step] <= nadir_iob + 0.1:
                    suspension_steps = step
                else:
                    break

            suspension_hours = suspension_steps / STEPS_PER_HOUR

            # Post-nadir outcomes
            valid_post = post_glucose[~np.isnan(post_glucose)]
            if len(valid_post) < 6:
                continue

            peak_post = float(np.max(valid_post))
            reaches_hyper = peak_post > 180
            time_to_range = 0
            for step in range(len(valid_post)):
                if valid_post[step] >= 70:
                    time_to_range = step / STEPS_PER_HOUR
                    break

            # Check for double-dip
            double_dip = False
            if time_to_range > 0:
                post_recovery = valid_post[int(time_to_range * STEPS_PER_HOUR):]
                if len(post_recovery) > 0:
                    double_dip = float(np.min(post_recovery)) < 70

            all_episodes.append({
                'patient': name,
                'nadir_bg': float(glucose[nadir_idx]) if not np.isnan(glucose[nadir_idx]) else 0,
                'nadir_iob': nadir_iob,
                'suspension_hours': suspension_hours,
                'peak_post_bg': peak_post,
                'reaches_hyper': reaches_hyper,
                'double_dip': double_dip,
                'time_to_range_hours': time_to_range,
            })

    n = len(all_episodes)
    if n == 0:
        print("  No episodes found")
        return {'experiment': 'EXP-1741', 'title': 'Post-Hypo Insulin Suspension', 'n': 0}

    suspensions = np.array([e['suspension_hours'] for e in all_episodes])
    rebound_rates = []
    double_dip_rates = []

    # Bin by suspension duration
    bins = [(0, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 4.0), (4.0, 8.0)]
    print(f"\n  {'Suspension':>12} {'n':>5} {'Rebound%':>9} {'DblDip%':>8} {'PeakBG':>7}")
    bin_results = {}
    for lo, hi in bins:
        mask = [(lo <= e['suspension_hours'] < hi) for e in all_episodes]
        group = [e for e, m in zip(all_episodes, mask) if m]
        if len(group) < 5:
            continue
        rebound_pct = 100 * sum(1 for e in group if e['reaches_hyper']) / len(group)
        dd_pct = 100 * sum(1 for e in group if e['double_dip']) / len(group)
        peak = float(np.mean([e['peak_post_bg'] for e in group]))
        bin_results[f"{lo}-{hi}h"] = {
            'n': len(group),
            'rebound_pct': round(rebound_pct, 1),
            'double_dip_pct': round(dd_pct, 1),
            'mean_peak_bg': round(peak, 1),
        }
        print(f"  {lo:.1f}-{hi:.1f}h {len(group):>5} {rebound_pct:>8.1f}% "
              f"{dd_pct:>7.1f}% {peak:>6.1f}")

    # Correlation: suspension duration vs peak post-nadir BG
    peaks = np.array([e['peak_post_bg'] for e in all_episodes])
    r, p = stats.spearmanr(suspensions, peaks)
    print(f"\n  Suspension vs peak BG: r={r:.3f} (p={p:.4f})")
    print(f"  Median suspension: {np.median(suspensions):.2f}h")
    print(f"  Overall rebound rate: {100*sum(1 for e in all_episodes if e['reaches_hyper'])/n:.1f}%")
    print(f"  Overall double-dip rate: {100*sum(1 for e in all_episodes if e['double_dip'])/n:.1f}%")

    return {
        'experiment': 'EXP-1741',
        'title': 'Post-Hypo Insulin Suspension Duration',
        'n_episodes': n,
        'median_suspension_hours': round(float(np.median(suspensions)), 2),
        'r_suspension_vs_peak': round(r, 3),
        'p_suspension_vs_peak': round(p, 4),
        'rebound_rate_pct': round(100 * sum(1 for e in all_episodes if e['reaches_hyper']) / n, 1),
        'double_dip_rate_pct': round(100 * sum(1 for e in all_episodes if e['double_dip']) / n, 1),
        'bins': bin_results,
    }


# ── EXP-1742: Simulated Extended Suspension ──────────────────────────

def exp_1742_extended_suspension(patients):
    """Simulate extending insulin suspension after hypo recovery.

    Current AID behavior: resume insulin delivery once glucose > 70.
    Proposed: maintain reduced delivery for additional 30/60/90 min.

    Simulate the glucose impact by computing how much demand reduction
    would shift the trajectory using patient-specific ISF.
    """
    print("\n=== EXP-1742: Simulated Extended Suspension ===")

    extensions = [0, 30, 60, 90, 120]  # minutes
    extension_outcomes = {ext: {'n': 0, 'prevented_hyper': 0, 'induced_hypo': 0,
                                 'mean_peak_reduction': []}
                          for ext in extensions}

    for pat in patients:
        excursions, glucose, carbs, iob, sd = _get_excursions_with_context(pat)
        isf = _extract_isf_scalar(pat['df'])
        name = pat['name']
        N = len(glucose)

        # Basal rate in U/h
        basal_schedule = pat['df'].attrs.get('basal_schedule', [{'value': 1.0}])
        basal_rate = float(basal_schedule[0]['value'])

        for exc in excursions:
            if exc['type'] != 'hypo_recovery':
                continue

            recovery_end = exc['end_idx']
            if recovery_end + 72 >= N:
                continue

            # Post-recovery glucose
            post_g = glucose[recovery_end:recovery_end+72].copy()
            valid = ~np.isnan(post_g)
            if valid.sum() < 12:
                continue

            baseline_peak = float(np.nanmax(post_g))
            baseline_hypo = float(np.nanmin(post_g[valid])) < 70

            for ext in extensions:
                ext_steps = ext // 5  # convert minutes to steps
                if ext_steps == 0:
                    extension_outcomes[ext]['n'] += 1
                    extension_outcomes[ext]['mean_peak_reduction'].append(0)
                    if baseline_peak > 180:
                        extension_outcomes[ext]['prevented_hyper'] += 0
                    continue

                # Simulate: during extension, reduce demand by basal × ISF / 12
                basal_demand_per_step = basal_rate * isf / 12.0
                # This demand reduction means glucose will be higher by this amount
                # per step during the extension, but LOWER afterward (less IOB)
                # Net effect: shift glucose down by accumulated suspension
                accumulated_reduction = 0
                simulated_g = post_g.copy()
                for step in range(min(ext_steps, len(simulated_g))):
                    if not np.isnan(simulated_g[step]):
                        # During suspension: glucose rises by basal_demand_per_step
                        # (insulin not being delivered)
                        accumulated_reduction += basal_demand_per_step
                        simulated_g[step] += accumulated_reduction
                # After suspension: the lower IOB means less glucose lowering
                # This accumulated excess gradually reduces over DIA
                dia_steps = int(5.0 * STEPS_PER_HOUR)  # 5h DIA
                for step in range(ext_steps, len(simulated_g)):
                    if not np.isnan(simulated_g[step]):
                        decay = accumulated_reduction * max(0, 1 - (step - ext_steps) / dia_steps)
                        simulated_g[step] -= decay * 0.5  # partial effect

                valid_sim = simulated_g[~np.isnan(simulated_g)]
                if len(valid_sim) < 6:
                    continue

                sim_peak = float(np.max(valid_sim))
                sim_hypo = float(np.min(valid_sim)) < 70

                extension_outcomes[ext]['n'] += 1
                extension_outcomes[ext]['mean_peak_reduction'].append(baseline_peak - sim_peak)
                if baseline_peak > 180 and sim_peak <= 180:
                    extension_outcomes[ext]['prevented_hyper'] += 1
                if not baseline_hypo and sim_hypo:
                    extension_outcomes[ext]['induced_hypo'] += 1

    print(f"  {'Extension':>10} {'n':>5} {'PrevHyper':>10} {'InducedHypo':>12} {'PeakΔ':>8}")
    results = {}
    for ext in extensions:
        eo = extension_outcomes[ext]
        n = eo['n']
        if n == 0:
            continue
        prev = eo['prevented_hyper']
        induced = eo['induced_hypo']
        peak_delta = float(np.mean(eo['mean_peak_reduction'])) if eo['mean_peak_reduction'] else 0
        results[str(ext)] = {
            'n': n,
            'prevented_hyper': prev,
            'prevented_hyper_pct': round(100 * prev / n, 1),
            'induced_hypo': induced,
            'induced_hypo_pct': round(100 * induced / n, 1),
            'mean_peak_reduction': round(peak_delta, 1),
        }
        print(f"  {ext:>8}min {n:>5} {prev:>9} ({100*prev/n:.1f}%) "
              f"{induced:>10} ({100*induced/n:.1f}%) {peak_delta:>+7.1f}")

    return {
        'experiment': 'EXP-1742',
        'title': 'Simulated Extended Suspension',
        'extensions': results,
    }


# ── EXP-1743: UAM Detection Latency Impact ───────────────────────────

def exp_1743_uam_latency(patients):
    """How much TAR would be saved by detecting UAM rises earlier?

    For each UAM rise, measure:
    - Time from excursion start to crossing 180 mg/dL
    - How much earlier correction insulin could begin
    - Estimated TAR reduction from earlier bolus
    """
    print("\n=== EXP-1743: UAM Detection Latency Impact ===")

    latency_data = []

    for pat in patients:
        excursions, glucose, carbs, iob, sd = _get_excursions_with_context(pat)
        isf = _extract_isf_scalar(pat['df'])
        N = len(glucose)

        for exc in excursions:
            if exc['type'] not in ('uam_rise', 'rebound_rise'):
                continue

            seg = glucose[exc['start_idx']:exc['end_idx']+1]
            valid = seg[~np.isnan(seg)]
            if len(valid) < 3:
                continue

            peak = float(np.max(valid))
            if peak <= 180:
                continue

            # Time from start to crossing 180
            cross_step = None
            for step in range(len(valid)):
                if valid[step] > 180:
                    cross_step = step
                    break

            if cross_step is None:
                continue

            cross_time_min = cross_step * 5
            above_range_steps = sum(1 for v in valid if v > 180)
            above_range_min = above_range_steps * 5

            # Detection opportunity: if we detected UAM at +15 min, we could
            # bolus earlier. With ISF, estimate glucose reduction.
            detection_delays = [0, 10, 15, 20, 30]  # minutes
            for delay in detection_delays:
                detection_step = delay // 5
                if detection_step < len(valid):
                    detect_bg = float(valid[detection_step])
                else:
                    detect_bg = float(valid[0])

                latency_data.append({
                    'type': exc['type'],
                    'detection_delay_min': delay,
                    'cross_time_min': cross_time_min,
                    'peak_bg': peak,
                    'above_range_min': above_range_min,
                    'detect_bg': detect_bg,
                    'patient': pat['name'],
                })

    # Analyze: how early would detection need to be?
    df_list = [d for d in latency_data if d['detection_delay_min'] == 0]
    if df_list:
        cross_times = [d['cross_time_min'] for d in df_list]
        print(f"  UAM/rebound rises reaching hyperglycemia: {len(df_list)}")
        print(f"  Mean time to cross 180: {np.mean(cross_times):.1f} min")
        print(f"  Median time to cross 180: {np.median(cross_times):.1f} min")

    # Group by detection delay
    print(f"\n  {'Delay':>6} {'n_rises':>8} {'MeanAboveMin':>13} {'MeanPeak':>9}")
    results = {}
    for delay in [0, 10, 15, 20, 30]:
        group = [d for d in latency_data if d['detection_delay_min'] == delay]
        if not group:
            continue
        n = len(group)
        # Unique rises (group by cross_time to avoid double counting)
        unique_n = len(set((d['patient'], d['cross_time_min'], d['peak_bg']) for d in group))
        mean_above = float(np.mean([d['above_range_min'] for d in group]))
        mean_peak = float(np.mean([d['peak_bg'] for d in group]))
        mean_detect_bg = float(np.mean([d['detect_bg'] for d in group]))

        results[str(delay)] = {
            'n_rises': unique_n,
            'mean_above_range_min': round(mean_above, 1),
            'mean_peak_bg': round(mean_peak, 1),
            'mean_detect_bg': round(mean_detect_bg, 1),
        }
        print(f"  {delay:>4}min {unique_n:>8} {mean_above:>12.1f}m {mean_peak:>8.1f}")

    # The key question: if we could deliver correction insulin X minutes earlier,
    # how much TAR is saved? Each minute of earlier bolus saves ~ISF/DIA worth
    # of time above range.
    print(f"\n  Estimated TAR savings from earlier UAM detection:")
    if df_list:
        mean_above_range = np.mean([d['above_range_min'] for d in df_list])
        for advance_min in [5, 10, 15, 20]:
            # Each minute of earlier bolus reduces TAR by approximately
            # advance_min * fall_rate where fall_rate ≈ 1 mg/dL/min (from EXP-1731)
            pct_reduction = min(100 * advance_min / max(mean_above_range, 1), 50)
            print(f"    {advance_min}min earlier: ~{pct_reduction:.0f}% TAR reduction for UAM events")

    return {
        'experiment': 'EXP-1743',
        'title': 'UAM Detection Latency Impact',
        'n_episodes': len(df_list) if df_list else 0,
        'results': results,
    }


# ── EXP-1744: Rescue Carb Aware AID Simulation ───────────────────────

def exp_1744_rescue_aware_aid(patients):
    """Simulate an AID that detects rescue carbs and adjusts response.

    Using EXP-1642's finding (rescue carbs detectable at 20 min, F1=0.91):
    Once rescue is detected, the AID could:
    1. Extend insulin suspension by 30 min (conservative)
    2. Deliver a proactive micro-bolus for the expected overshoot

    Simulate impact on rebound hyperglycemia rate.
    """
    print("\n=== EXP-1744: Rescue Carb Aware AID Simulation ===")

    strategies = {
        'baseline': {'description': 'Current AID behavior'},
        'extend_30': {'description': 'Extend suspension 30min after rescue detected'},
        'extend_60': {'description': 'Extend suspension 60min after rescue detected'},
        'proactive_micro': {'description': 'Micro-bolus 0.5U at rescue detection + 30min'},
    }

    for s in strategies.values():
        s.update({'n': 0, 'rebound_hyper': 0, 'double_dip': 0, 'tar_min': 0, 'tbr_min': 0})

    for pat in patients:
        excursions, glucose, carbs, iob, sd = _get_excursions_with_context(pat)
        isf = _extract_isf_scalar(pat['df'])
        basal_schedule = pat['df'].attrs.get('basal_schedule', [{'value': 1.0}])
        basal_rate = float(basal_schedule[0]['value'])
        N = len(glucose)

        for i, exc in enumerate(excursions):
            if exc['type'] != 'hypo_recovery':
                continue

            # Post-recovery window (6h)
            start = exc['end_idx']
            if start + 72 >= N:
                continue

            post_g = glucose[start:start+72]
            valid = ~np.isnan(post_g)
            if valid.sum() < 12:
                continue

            post_valid = post_g[valid]
            baseline_peak = float(np.max(post_valid))
            baseline_nadir = float(np.min(post_valid))

            # Compute TAR/TBR for each strategy
            for strat_name in strategies:
                strat = strategies[strat_name]
                strat['n'] += 1

                if strat_name == 'baseline':
                    peak = baseline_peak
                    nadir = baseline_nadir
                    tar = int(np.sum(post_valid > 180)) * 5
                    tbr = int(np.sum(post_valid < 70)) * 5
                elif strat_name == 'extend_30':
                    # Extending suspension reduces IOB, glucose rises more
                    # but then has less insulin to cause secondary hypo
                    basal_per_step = basal_rate * isf / 12.0
                    extra_rise = 6 * basal_per_step  # 30 min suspension
                    sim = post_valid.copy()
                    # Glucose rises during extra suspension
                    for step in range(min(6, len(sim))):
                        sim[step] += extra_rise * (step + 1) / 6
                    # Then less insulin later
                    for step in range(6, len(sim)):
                        sim[step] -= extra_rise * 0.3
                    peak = float(np.max(sim))
                    nadir = float(np.min(sim))
                    tar = int(np.sum(sim > 180)) * 5
                    tbr = int(np.sum(sim < 70)) * 5
                elif strat_name == 'extend_60':
                    basal_per_step = basal_rate * isf / 12.0
                    extra_rise = 12 * basal_per_step
                    sim = post_valid.copy()
                    for step in range(min(12, len(sim))):
                        sim[step] += extra_rise * (step + 1) / 12
                    for step in range(12, len(sim)):
                        sim[step] -= extra_rise * 0.3
                    peak = float(np.max(sim))
                    nadir = float(np.min(sim))
                    tar = int(np.sum(sim > 180)) * 5
                    tbr = int(np.sum(sim < 70)) * 5
                elif strat_name == 'proactive_micro':
                    # Micro-bolus at rescue detection time (20min post-nadir)
                    # Effect: reduces peak by 0.5 × ISF ≈ 20-40 mg/dL
                    correction_effect = 0.5 * isf
                    sim = post_valid.copy()
                    # Effect starts at ~30 min (step 6) and peaks at ~90 min (step 18)
                    for step in range(6, len(sim)):
                        onset_fraction = min(1.0, (step - 6) / 12.0)
                        decay_fraction = max(0, 1.0 - (step - 18) / 36.0)
                        effect = correction_effect * onset_fraction * decay_fraction
                        sim[step] -= effect
                    peak = float(np.max(sim))
                    nadir = float(np.min(sim))
                    tar = int(np.sum(sim > 180)) * 5
                    tbr = int(np.sum(sim < 70)) * 5

                if peak > 180:
                    strat['rebound_hyper'] += 1
                if nadir < 70:
                    strat['double_dip'] += 1
                strat['tar_min'] += tar
                strat['tbr_min'] += tbr

    print(f"  {'Strategy':<25} {'n':>5} {'Rebound%':>9} {'DblDip%':>8} "
          f"{'TAR(h)':>7} {'TBR(h)':>7}")
    results = {}
    for name, strat in strategies.items():
        n = strat['n']
        if n == 0:
            continue
        rb_pct = 100 * strat['rebound_hyper'] / n
        dd_pct = 100 * strat['double_dip'] / n
        tar_h = strat['tar_min'] / 60
        tbr_h = strat['tbr_min'] / 60
        results[name] = {
            'n': n,
            'rebound_hyper_pct': round(rb_pct, 1),
            'double_dip_pct': round(dd_pct, 1),
            'tar_hours': round(tar_h, 1),
            'tbr_hours': round(tbr_h, 1),
        }
        print(f"  {name:<25} {n:>5} {rb_pct:>8.1f}% {dd_pct:>7.1f}% "
              f"{tar_h:>6.1f}h {tbr_h:>6.1f}h")

    return {
        'experiment': 'EXP-1744',
        'title': 'Rescue Carb Aware AID Simulation',
        'strategies': results,
    }


# ── EXP-1745: Glucose Stability Index ────────────────────────────────

def exp_1745_stability_index(patients):
    """Define a "glucose stability index" combining multiple excursion metrics.

    Compress the full excursion profile into a single score that predicts
    overall TIR. Components:
    - Cascade rate (chains/day)
    - Hypo rate (events/day)
    - Rebound rate (% hypos reaching hyperglycemia)
    - UAM proportion (fraction of rises without carbs)
    - Overnight drift magnitude
    """
    print("\n=== EXP-1745: Glucose Stability Index ===")

    patient_metrics = []

    for pat in patients:
        excursions, glucose, carbs, iob, sd = _get_excursions_with_context(pat)
        name = pat['name']
        N = len(glucose)
        valid_days = (~np.isnan(glucose)).sum() / STEPS_PER_DAY

        # TIR
        valid_g = glucose[~np.isnan(glucose)]
        tir = float(np.mean((valid_g >= 70) & (valid_g <= 180)))

        # Excursion rates
        type_counts = defaultdict(int)
        for exc in excursions:
            type_counts[exc['type']] += 1

        hypo_rate = type_counts.get('hypo_entry', 0) / valid_days
        uam_rate = type_counts.get('uam_rise', 0) / valid_days
        meal_rate = type_counts.get('meal_rise', 0) / valid_days
        total_rises = uam_rate + meal_rate + type_counts.get('rebound_rise', 0) / valid_days
        uam_fraction = uam_rate / max(total_rises, 0.1)

        # Cascade rate
        CASCADE_TRANSITIONS = {
            ('hypo_entry', 'hypo_recovery'), ('hypo_recovery', 'rebound_rise'),
            ('hypo_recovery', 'uam_rise'), ('hypo_recovery', 'hypo_entry'),
            ('rebound_rise', 'insulin_fall'), ('rebound_rise', 'post_rise_fall'),
            ('insulin_fall', 'hypo_entry'), ('correction_drop', 'hypo_entry'),
            ('meal_rise', 'insulin_fall'), ('uam_rise', 'insulin_fall'),
        }
        n_chains = 0
        in_chain = False
        for i in range(1, len(excursions)):
            prev_type = excursions[i-1]['type']
            curr_type = excursions[i]['type']
            if (prev_type, curr_type) in CASCADE_TRANSITIONS:
                if not in_chain:
                    n_chains += 1
                    in_chain = True
            else:
                in_chain = False
        cascade_rate = n_chains / valid_days

        # Rebound rate
        hypo_n = type_counts.get('hypo_entry', 0)
        rebound_n = 0
        for i in range(len(excursions) - 2):
            if (excursions[i]['type'] == 'hypo_entry' and
                    excursions[i+1]['type'] == 'hypo_recovery'):
                # Check if recovery leads to hyperglycemia
                rec_end = excursions[i+1]['end_idx']
                if rec_end + 24 < N:
                    post = glucose[rec_end:rec_end+24]
                    if np.nanmax(post) > 180:
                        rebound_n += 1
        rebound_rate = rebound_n / max(hypo_n, 1)

        # Overnight drift
        overnight_drifts = []
        for day_start in range(0, N - STEPS_PER_DAY, STEPS_PER_DAY):
            window = glucose[day_start:day_start+72]
            valid_w = ~np.isnan(window)
            if valid_w.sum() < 36:
                continue
            carbs_w = carbs[day_start:day_start+72]
            if np.sum(carbs_w) > 1.0:
                continue
            t = np.arange(len(window))[valid_w]
            bg = window[valid_w]
            if len(t) >= 6:
                slope = np.polyfit(t, bg, 1)[0]
                overnight_drifts.append(abs(float(slope)) * STEPS_PER_HOUR)
        overnight_drift = float(np.mean(overnight_drifts)) if overnight_drifts else 0

        patient_metrics.append({
            'name': name,
            'tir': tir,
            'hypo_rate': hypo_rate,
            'cascade_rate': cascade_rate,
            'rebound_rate': rebound_rate,
            'uam_fraction': uam_fraction,
            'overnight_drift': overnight_drift,
        })

    # Build stability index
    # Normalize each component to 0-1 and combine
    metrics_arr = np.array([[m['hypo_rate'], m['cascade_rate'], m['rebound_rate'],
                              m['uam_fraction'], m['overnight_drift']]
                             for m in patient_metrics])
    # Higher = worse for all metrics, so stability = 1 - normalized_sum
    ranges = metrics_arr.max(axis=0) - metrics_arr.min(axis=0)
    ranges[ranges == 0] = 1
    normalized = (metrics_arr - metrics_arr.min(axis=0)) / ranges
    stability_scores = 1 - normalized.mean(axis=1)

    for i, m in enumerate(patient_metrics):
        m['stability_index'] = round(float(stability_scores[i]), 3)

    # Correlate with TIR
    tirs = [m['tir'] for m in patient_metrics]
    stab = [m['stability_index'] for m in patient_metrics]
    r, p = stats.spearmanr(stab, tirs)

    print(f"  {'Patient':>8} {'TIR':>6} {'StabIdx':>8} {'HypoRate':>9} "
          f"{'CascRate':>9} {'ReboundR':>9} {'UAM%':>6}")
    for m in sorted(patient_metrics, key=lambda x: -x['stability_index']):
        print(f"  {m['name']:>8} {m['tir']:>5.1%} {m['stability_index']:>7.3f} "
              f"{m['hypo_rate']:>8.2f} {m['cascade_rate']:>8.2f} "
              f"{m['rebound_rate']:>8.2f} {m['uam_fraction']:>5.1%}")

    print(f"\n  Stability Index vs TIR: r={r:.3f} (p={p:.4f})")

    return {
        'experiment': 'EXP-1745',
        'title': 'Glucose Stability Index',
        'r_stability_tir': round(r, 3),
        'p_stability_tir': round(p, 4),
        'patient_metrics': [{k: round(v, 4) if isinstance(v, float) else v
                              for k, v in m.items()} for m in patient_metrics],
    }


# ── EXP-1746: Information Ceiling by Excursion Type ──────────────────

def exp_1746_info_ceiling(patients):
    """What fraction of glucose variance is predictable per excursion type?

    For each type, use a "perfect hindsight" model (mean trajectory for
    that type from the same patient) as the prediction and measure R².
    This gives the information ceiling — the maximum predictable variance
    given perfect type classification.
    """
    print("\n=== EXP-1746: Information Ceiling by Excursion Type ===")

    type_trajectories = defaultdict(lambda: defaultdict(list))

    # Phase 1: Collect trajectories per patient per type
    for pat in patients:
        excursions, glucose, carbs, iob, sd = _get_excursions_with_context(pat)
        name = pat['name']
        N = len(glucose)

        for exc in excursions:
            # Normalize to 48-step (4h) window from start
            start = exc['start_idx']
            end = min(start + 48, N)
            seg = glucose[start:end]
            if len(seg) < 24:
                continue
            # Pad to 48 if shorter
            padded = np.full(48, np.nan)
            padded[:len(seg)] = seg
            type_trajectories[(name, exc['type'])]['trajectories'].append(padded)

    # Phase 2: Leave-one-out prediction
    type_r2 = defaultdict(lambda: {'ss_res': 0, 'ss_tot': 0, 'n': 0})
    overall_ss_res = 0
    overall_ss_tot = 0
    overall_n = 0

    for (pat_name, etype), data in type_trajectories.items():
        trajs = data['trajectories']
        if len(trajs) < 5:
            continue

        trajs_arr = np.array(trajs)

        for i in range(len(trajs)):
            actual = trajs_arr[i]
            # Mean of all OTHER trajectories = prediction
            others = np.delete(trajs_arr, i, axis=0)
            predicted = np.nanmean(others, axis=0)

            # Only compare at valid positions
            both_valid = ~np.isnan(actual) & ~np.isnan(predicted)
            if both_valid.sum() < 6:
                continue

            a = actual[both_valid]
            p = predicted[both_valid]

            ss_r = float(np.sum((a - p) ** 2))
            ss_t = float(np.sum((a - np.mean(a)) ** 2))

            type_r2[etype]['ss_res'] += ss_r
            type_r2[etype]['ss_tot'] += ss_t
            type_r2[etype]['n'] += 1
            overall_ss_res += ss_r
            overall_ss_tot += ss_t
            overall_n += 1

    print(f"  {'Type':<25} {'R² ceiling':>10} {'n':>7}")
    results = {}
    for etype in sorted(type_r2.keys(), key=lambda t: type_r2[t]['n'], reverse=True):
        td = type_r2[etype]
        r2 = 1 - td['ss_res'] / max(td['ss_tot'], 1)
        results[etype] = {
            'r2_ceiling': round(r2, 4),
            'n_trajectories': td['n'],
        }
        print(f"  {etype:<25} {r2:>9.4f} {td['n']:>7}")

    overall_r2 = 1 - overall_ss_res / max(overall_ss_tot, 1)
    print(f"\n  Overall information ceiling: R²={overall_r2:.4f} (n={overall_n})")

    return {
        'experiment': 'EXP-1746',
        'title': 'Information Ceiling by Excursion Type',
        'overall_r2_ceiling': round(overall_r2, 4),
        'type_ceilings': results,
    }


# ── Figure generation ─────────────────────────────────────────────────

def generate_figures(results, patients):
    """Generate 6 figures for the AID optimization analysis."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # Fig 1: Post-hypo suspension analysis
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    r1741 = results.get('EXP-1741', {})
    bins = r1741.get('bins', {})
    if bins:
        labels = list(bins.keys())
        rebound = [bins[l]['rebound_pct'] for l in labels]
        dd = [bins[l]['double_dip_pct'] for l in labels]
        x = np.arange(len(labels))
        width = 0.35
        axes[0].bar(x - width/2, rebound, width, label='Rebound %', color='coral', alpha=0.8)
        axes[0].bar(x + width/2, dd, width, label='Double-dip %', color='steelblue', alpha=0.8)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(labels, rotation=45, ha='right')
        axes[0].set_ylabel('Rate (%)')
        axes[0].set_title('Post-Hypo Outcomes by Suspension Duration')
        axes[0].legend()

    r1742 = results.get('EXP-1742', {})
    ext = r1742.get('extensions', {})
    if ext:
        strats = sorted(ext.keys(), key=int)
        prev_hyper = [ext[s]['prevented_hyper_pct'] for s in strats]
        ind_hypo = [ext[s]['induced_hypo_pct'] for s in strats]
        x = np.arange(len(strats))
        width = 0.35
        axes[1].bar(x - width/2, prev_hyper, width, label='Prevented hyper %', color='green', alpha=0.8)
        axes[1].bar(x + width/2, ind_hypo, width, label='Induced hypo %', color='red', alpha=0.8)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels([f"+{s}min" for s in strats])
        axes[1].set_ylabel('Rate (%)')
        axes[1].set_title('Extended Suspension Tradeoff')
        axes[1].legend()

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'aid-fig1-suspension.png', dpi=150)
    plt.close()
    print("  Saved fig1")

    # Fig 2: Rescue-aware AID strategies
    fig, ax = plt.subplots(figsize=(12, 6))

    r1744 = results.get('EXP-1744', {})
    strats = r1744.get('strategies', {})
    if strats:
        names = list(strats.keys())
        rb = [strats[n]['rebound_hyper_pct'] for n in names]
        dd = [strats[n]['double_dip_pct'] for n in names]
        tar = [strats[n]['tar_hours'] for n in names]

        x = np.arange(len(names))
        width = 0.25
        ax.bar(x - width, rb, width, label='Rebound %', color='coral', alpha=0.8)
        ax.bar(x, dd, width, label='Double-dip %', color='steelblue', alpha=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(names, rotation=30, ha='right', fontsize=9)
        ax.set_ylabel('Rate (%)')
        ax.set_title('Rescue-Aware AID Strategy Comparison')
        ax.legend()

        ax2 = ax.twinx()
        ax2.plot(x, tar, 'ko-', label='TAR (h)', linewidth=2)
        ax2.set_ylabel('TAR (hours)')
        ax2.legend(loc='upper right')

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'aid-fig2-rescue-aware.png', dpi=150)
    plt.close()
    print("  Saved fig2")

    # Fig 3: Stability index vs TIR
    fig, ax = plt.subplots(figsize=(10, 7))

    r1745 = results.get('EXP-1745', {})
    pm = r1745.get('patient_metrics', [])
    if pm:
        stab = [m['stability_index'] for m in pm]
        tir = [m['tir'] for m in pm]
        names = [m['name'] for m in pm]

        ax.scatter(stab, tir, s=100, alpha=0.8)
        for i, name in enumerate(names):
            ax.annotate(name, (stab[i], tir[i]), fontsize=10,
                        textcoords="offset points", xytext=(5, 5))
        ax.set_xlabel('Glucose Stability Index (higher = more stable)')
        ax.set_ylabel('Time in Range')
        r = r1745.get('r_stability_tir', 0)
        ax.set_title(f'Stability Index vs TIR (r={r:.3f})')

        # Trend line
        z = np.polyfit(stab, tir, 1)
        ax.plot(sorted(stab), np.polyval(z, sorted(stab)), 'r--', alpha=0.5)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'aid-fig3-stability.png', dpi=150)
    plt.close()
    print("  Saved fig3")

    # Fig 4: Information ceiling by type
    fig, ax = plt.subplots(figsize=(12, 6))

    r1746 = results.get('EXP-1746', {})
    ceilings = r1746.get('type_ceilings', {})
    if ceilings:
        types = sorted(ceilings.keys(), key=lambda t: -ceilings[t]['r2_ceiling'])
        r2s = [ceilings[t]['r2_ceiling'] for t in types]
        ns = [ceilings[t]['n_trajectories'] for t in types]

        x = np.arange(len(types))
        bars = ax.bar(x, r2s, color='steelblue', alpha=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(types, rotation=45, ha='right', fontsize=8)
        ax.set_ylabel('R² Information Ceiling')
        ax.set_title('Information Ceiling by Excursion Type\n(Perfect hindsight within-patient model)')
        ax.axhline(r1746.get('overall_r2_ceiling', 0), color='red', linestyle='--',
                    label=f"Overall: {r1746.get('overall_r2_ceiling', 0):.3f}")
        ax.legend()

        for i, (bar, n) in enumerate(zip(bars, ns)):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'n={n}', ha='center', va='bottom', fontsize=7)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / 'aid-fig4-info-ceiling.png', dpi=150)
    plt.close()
    print("  Saved fig4")


def main():
    parser = argparse.ArgumentParser(description='EXP-1741–1748: AID Optimization')
    parser.add_argument('--figures', action='store_true')
    args = parser.parse_args()

    print("Loading patients...")
    patients = load_patients(PATIENTS_DIR)
    print(f"Loaded {len(patients)} patients")

    results = {}

    results['EXP-1741'] = exp_1741_post_hypo_suspension(patients)
    results['EXP-1742'] = exp_1742_extended_suspension(patients)
    results['EXP-1743'] = exp_1743_uam_latency(patients)
    results['EXP-1744'] = exp_1744_rescue_aware_aid(patients)
    results['EXP-1745'] = exp_1745_stability_index(patients)
    results['EXP-1746'] = exp_1746_info_ceiling(patients)

    # Save JSONs
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for exp_id, result in results.items():
        fname = f"exp-{exp_id.split('-')[1]}_aid_optimization.json"
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
    r1741 = results.get('EXP-1741', {})
    r1744 = results.get('EXP-1744', {})
    r1745 = results.get('EXP-1745', {})
    r1746 = results.get('EXP-1746', {})

    print(f"  Median suspension: {r1741.get('median_suspension_hours', '?')}h")
    print(f"  Double-dip rate: {r1741.get('double_dip_rate_pct', '?')}%")
    baseline = r1744.get('strategies', {}).get('baseline', {})
    micro = r1744.get('strategies', {}).get('proactive_micro', {})
    print(f"  Rescue-aware: rebound {baseline.get('rebound_hyper_pct', '?')}% → "
          f"{micro.get('rebound_hyper_pct', '?')}% (proactive micro)")
    print(f"  Stability→TIR: r={r1745.get('r_stability_tir', '?')}")
    print(f"  Info ceiling: R²={r1746.get('overall_r2_ceiling', '?')}")


if __name__ == '__main__':
    main()
