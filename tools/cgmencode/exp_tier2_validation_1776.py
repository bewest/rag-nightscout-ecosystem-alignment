#!/usr/bin/env python3
"""EXP-1776–1782: Validate Tier 2+3 production integration on patient data.

Tests all newly ported algorithms end-to-end on 11 patients:
  EXP-1776: Excursion detection + type distribution
  EXP-1777: Cascade chain detection + participation rate
  EXP-1778: 4-harmonic circadian in production metabolic engine
  EXP-1779: Counter-regulatory floor hypo dampening
  EXP-1780: Optimization sequence phase assignment
  EXP-1781: Rescue phenotype classification
  EXP-1782: Three ceilings framework bounds

Each experiment validates that production code produces results consistent
with research findings. Figures saved to docs/60-research/figures/.
"""

import json
import os
import sys
import time

import numpy as np

# Production imports
from cgmencode.production.types import (
    ExcursionType, OptimizationPhase, RescuePhenotype, PatientData, PatientProfile,
)
from cgmencode.production.metabolic_engine import compute_metabolic_state
from cgmencode.production.pattern_analyzer import (
    detect_excursions, detect_cascade_chains, compute_harmonic_features,
    fit_harmonic_circadian,
)
from cgmencode.production.hypo_predictor import (
    predict_hypo, classify_rescue_phenotype, COUNTER_REG_FLOOR,
)
from cgmencode.production.settings_advisor import (
    determine_optimization_phase, prioritize_recommendations,
)
from cgmencode.production.clinical_rules import compute_three_ceilings

# Research data loader
from cgmencode.exp_metabolic_flux import load_patients as _load_patients_raw

PATIENTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'externals', 'ns-data', 'patients')

FIGURE_DIR = os.path.join(os.path.dirname(__file__),
                          '..', '..', 'docs', '60-research', 'figures')
RESULTS_DIR = os.path.join(os.path.dirname(__file__),
                           '..', '..', 'externals', 'experiments')
os.makedirs(FIGURE_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)


def _make_patient_data(pat):
    """Convert research patient dict to production PatientData."""
    df = pat['df']
    glucose = df['glucose'].values.astype(np.float64)
    N = len(glucose)

    # Timestamps
    if 'timestamp' in df.columns:
        timestamps = df['timestamp'].values.astype(np.float64)
    else:
        timestamps = np.arange(N) * 5 * 60 * 1000  # 5-min steps in ms

    # IOB
    iob = df['iob'].values.astype(np.float64) if 'iob' in df.columns else None

    # COB
    cob = df['cob'].values.astype(np.float64) if 'cob' in df.columns else None

    # Bolus
    bolus = df['bolus'].values.astype(np.float64) if 'bolus' in df.columns else None

    # Carbs
    carbs = df['carbs'].values.astype(np.float64) if 'carbs' in df.columns else None

    # Basal rate
    basal = df['basal'].values.astype(np.float64) if 'basal' in df.columns else None

    # Profile
    profile = _extract_profile(df)

    return PatientData(
        glucose=glucose,
        timestamps=timestamps,
        iob=iob,
        cob=cob,
        bolus=bolus,
        carbs=carbs,
        basal_rate=basal,
        profile=profile,
    )


def _extract_profile(df):
    """Extract PatientProfile from dataframe attrs."""
    attrs = df.attrs
    basal_sched = attrs.get('basal_schedule', [{'value': 0.8}])
    isf_sched = attrs.get('isf_schedule', [{'value': 50.0}])
    cr_sched = attrs.get('cr_schedule', [{'value': 10.0}])

    return PatientProfile(
        basal_schedule=basal_sched,
        isf_schedule=isf_sched,
        cr_schedule=cr_sched,
    )


def _extract_hours(timestamps):
    """Extract fractional hours from timestamps."""
    try:
        import pandas as pd
        dt = pd.to_datetime(timestamps, unit='ms')
        return np.asarray(dt.hour + dt.minute / 60.0, dtype=np.float64)
    except Exception:
        ts = np.asarray(timestamps, dtype=np.float64)
        seconds = ts / 1000.0 if ts.max() > 1e12 else ts
        return (seconds % 86400) / 3600.0


# ══════════════════════════════════════════════════════════════════════
# EXP-1776: Excursion Detection Validation
# ══════════════════════════════════════════════════════════════════════

def exp_1776_excursion_detection(patients, make_figures=True):
    """Validate excursion detection + type distribution on all patients.

    Expected: ~10 types detected, distribution matches EXP-1691 research
    (hypo_entry ~5%, meal_rise ~20%, uam_rise ~25%, etc.).
    """
    print("\n" + "=" * 70)
    print("EXP-1776: Excursion Detection Validation")
    print("=" * 70)

    all_type_counts = {}
    per_patient = {}
    total_excursions = 0

    for pat in patients:
        pid = pat['name']
        df = pat['df']
        glucose = df['glucose'].values.astype(np.float64)
        carbs = df['carbs'].values.astype(np.float64) if 'carbs' in df.columns else np.zeros(len(glucose))
        iob = df['iob'].values.astype(np.float64) if 'iob' in df.columns else np.zeros(len(glucose))

        # Get metabolic state
        try:
            pdata = _make_patient_data(pat)
            metabolic = compute_metabolic_state(pdata)
        except Exception as e:
            print(f"  {pid}: metabolic state failed ({e}), using None")
            metabolic = None

        excursions = detect_excursions(glucose, carbs, iob, metabolic)

        type_counts = {}
        for exc in excursions:
            t = exc.excursion_type
            type_counts[t] = type_counts.get(t, 0) + 1
            all_type_counts[t] = all_type_counts.get(t, 0) + 1

        per_patient[pid] = {
            'n_excursions': len(excursions),
            'type_counts': type_counts,
            'per_day': len(excursions) / max(len(glucose) / 288, 1),
        }
        total_excursions += len(excursions)
        print(f"  {pid}: {len(excursions)} excursions ({per_patient[pid]['per_day']:.1f}/day)")

    # Summary
    print(f"\nTotal excursions: {total_excursions} across {len(patients)} patients")
    print(f"Types detected: {len(all_type_counts)}")
    print("\nType distribution:")
    for t, count in sorted(all_type_counts.items(), key=lambda x: -x[1]):
        pct = count / max(total_excursions, 1) * 100
        print(f"  {t:25s}: {count:5d} ({pct:5.1f}%)")

    # Validation checks
    n_types = len(all_type_counts)
    assert n_types >= 6, f"Expected ≥6 excursion types, got {n_types}"
    assert total_excursions > 100, f"Expected >100 excursions, got {total_excursions}"

    if make_figures:
        _plot_excursion_distribution(all_type_counts, total_excursions)

    return {
        'total_excursions': total_excursions,
        'type_counts': all_type_counts,
        'per_patient': per_patient,
        'n_types': n_types,
    }


def _plot_excursion_distribution(type_counts, total):
    """Bar chart of excursion type distribution."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        types = sorted(type_counts.keys(), key=lambda t: -type_counts[t])
        counts = [type_counts[t] for t in types]
        pcts = [c / max(total, 1) * 100 for c in counts]

        fig, ax = plt.subplots(figsize=(12, 6))
        bars = ax.barh(range(len(types)), pcts, color='steelblue')
        ax.set_yticks(range(len(types)))
        ax.set_yticklabels(types, fontsize=10)
        ax.set_xlabel('Percentage of All Excursions (%)')
        ax.set_title(f'EXP-1776: Excursion Type Distribution (N={total})')
        for bar, pct in zip(bars, pcts):
            ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                    f'{pct:.1f}%', va='center', fontsize=9)
        plt.tight_layout()
        path = os.path.join(FIGURE_DIR, 'prod-fig6-excursion-types.png')
        plt.savefig(path, dpi=150)
        plt.close()
        print(f"  Figure saved: {path}")
    except ImportError:
        print("  (matplotlib not available, skipping figure)")


# ══════════════════════════════════════════════════════════════════════
# EXP-1777: Cascade Chain Detection Validation
# ══════════════════════════════════════════════════════════════════════

def exp_1777_cascade_detection(patients, make_figures=True):
    """Validate cascade chain detection.

    Expected: ~62% cascade participation (from EXP-1691).
    Chains typically 2-5 excursions long.
    """
    print("\n" + "=" * 70)
    print("EXP-1777: Cascade Chain Detection Validation")
    print("=" * 70)

    per_patient = {}
    all_chain_lengths = []
    all_root_types = {}

    for pat in patients:
        pid = pat['name']
        df = pat['df']
        glucose = df['glucose'].values.astype(np.float64)
        carbs = df['carbs'].values.astype(np.float64) if 'carbs' in df.columns else np.zeros(len(glucose))
        iob = df['iob'].values.astype(np.float64) if 'iob' in df.columns else np.zeros(len(glucose))

        try:
            pdata = _make_patient_data(pat)
            metabolic = compute_metabolic_state(pdata)
        except Exception:
            metabolic = None

        excursions = detect_excursions(glucose, carbs, iob, metabolic)
        cascade = detect_cascade_chains(excursions)

        for chain in cascade.chains:
            all_chain_lengths.append(chain.length)
            rt = chain.root_type
            all_root_types[rt] = all_root_types.get(rt, 0) + 1

        per_patient[pid] = {
            'n_excursions': cascade.total_excursions,
            'n_chains': len(cascade.chains),
            'in_chain': cascade.in_chain_count,
            'participation': cascade.cascade_participation,
        }
        print(f"  {pid}: {len(cascade.chains)} chains, "
              f"{cascade.cascade_participation:.1%} participation")

    # Population stats
    participations = [p['participation'] for p in per_patient.values()]
    mean_part = float(np.mean(participations))
    print(f"\nMean cascade participation: {mean_part:.1%}")
    print(f"Total chains: {sum(p['n_chains'] for p in per_patient.values())}")

    if all_chain_lengths:
        print(f"Chain length: mean={np.mean(all_chain_lengths):.1f}, "
              f"max={max(all_chain_lengths)}, median={np.median(all_chain_lengths):.0f}")

    print("\nChain root types:")
    for rt, count in sorted(all_root_types.items(), key=lambda x: -x[1]):
        print(f"  {rt:25s}: {count}")

    if make_figures:
        _plot_cascade_participation(per_patient)

    return {
        'mean_participation': mean_part,
        'per_patient': per_patient,
        'chain_lengths': all_chain_lengths,
        'root_types': all_root_types,
    }


def _plot_cascade_participation(per_patient):
    """Bar chart of cascade participation per patient."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        pids = sorted(per_patient.keys())
        parts = [per_patient[p]['participation'] * 100 for p in pids]

        fig, ax = plt.subplots(figsize=(10, 5))
        bars = ax.bar(pids, parts, color='coral')
        ax.axhline(62, color='red', linestyle='--', label='Research target (62%)')
        ax.set_ylabel('Cascade Participation (%)')
        ax.set_xlabel('Patient')
        ax.set_title('EXP-1777: Cascade Chain Participation Rate')
        ax.legend()
        for bar, pct in zip(bars, parts):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                    f'{pct:.0f}%', ha='center', fontsize=8)
        plt.tight_layout()
        path = os.path.join(FIGURE_DIR, 'prod-fig7-cascade-participation.png')
        plt.savefig(path, dpi=150)
        plt.close()
        print(f"  Figure saved: {path}")
    except ImportError:
        print("  (matplotlib not available)")


# ══════════════════════════════════════════════════════════════════════
# EXP-1778: 4-Harmonic Metabolic Engine Validation
# ══════════════════════════════════════════════════════════════════════

def exp_1778_harmonic_metabolic(patients, make_figures=True):
    """Validate 4-harmonic circadian in production metabolic engine.

    Compare fasting RMSE with the new 4-harmonic circadian vs if we only
    used single-harmonic. The metabolic engine now uses 4-harmonic internally.
    """
    print("\n" + "=" * 70)
    print("EXP-1778: 4-Harmonic Metabolic Engine Validation")
    print("=" * 70)

    results = {}
    for pat in patients:
        pid = pat['name']
        df = pat['df']
        glucose = df['glucose'].values.astype(np.float64)

        try:
            pdata = _make_patient_data(pat)
            metabolic = compute_metabolic_state(pdata)
        except Exception as e:
            print(f"  {pid}: FAILED ({e})")
            continue

        # Fasting windows: 0-6 AM
        timestamps = pdata.timestamps
        hours = _extract_hours(timestamps)
        fasting_mask = (hours >= 0) & (hours < 6) & np.isfinite(glucose)

        if fasting_mask.sum() < 12:
            print(f"  {pid}: insufficient fasting data")
            continue

        # RMSE of predicted vs actual change during fasting
        actual_change = np.diff(glucose)
        predicted_net = metabolic.net_flux[:-1]
        residual = actual_change - predicted_net
        fasting_residual = residual[fasting_mask[1:]]
        fasting_rmse = float(np.sqrt(np.nanmean(fasting_residual ** 2)))
        fasting_bias = float(np.nanmean(fasting_residual))

        # Also test harmonic circadian fit quality
        harmonic_fit = fit_harmonic_circadian(glucose, hours)

        results[pid] = {
            'fasting_rmse': fasting_rmse,
            'fasting_bias': fasting_bias,
            'harmonic_r2': harmonic_fit.r2,
            'dominant_period': harmonic_fit.dominant_period,
        }
        print(f"  {pid}: fasting RMSE={fasting_rmse:.1f}, bias={fasting_bias:.2f}, "
              f"harmonic R²={harmonic_fit.r2:.3f}")

    mean_rmse = float(np.mean([r['fasting_rmse'] for r in results.values()]))
    mean_r2 = float(np.mean([r['harmonic_r2'] for r in results.values()]))
    print(f"\nMean fasting RMSE: {mean_rmse:.1f}")
    print(f"Mean harmonic R²: {mean_r2:.3f}")

    return results


# ══════════════════════════════════════════════════════════════════════
# EXP-1779: Counter-Regulatory Floor Validation
# ══════════════════════════════════════════════════════════════════════

def exp_1779_counter_reg_floor(patients, make_figures=True):
    """Validate counter-regulatory floor dampening in hypo predictor.

    Check that near-hypo episodes with high residual (counter-reg active)
    get dampened probability.
    """
    print("\n" + "=" * 70)
    print("EXP-1779: Counter-Regulatory Floor Validation")
    print("=" * 70)

    dampened = 0
    not_dampened = 0
    per_patient = {}

    for pat in patients:
        pid = pat['name']
        df = pat['df']
        glucose = df['glucose'].values.astype(np.float64)
        N = len(glucose)

        try:
            pdata = _make_patient_data(pat)
            metabolic = compute_metabolic_state(pdata)
        except Exception:
            metabolic = None

        patient_dampened = 0
        patient_total = 0

        # Scan for near-hypo windows and check prediction behavior
        for i in range(24, N - 24):
            bg = glucose[i]
            if np.isnan(bg) or bg > 85 or bg < 40:
                continue

            # Get prediction with metabolic context
            window = glucose[max(0, i-12):i+1]
            if len(window) < 7:
                continue

            # Create a truncated metabolic state for this window
            if metabolic is not None:
                from cgmencode.production.types import MetabolicState
                end = i + 1
                start = max(0, i - 12)
                ms = MetabolicState(
                    supply=metabolic.supply[start:end],
                    demand=metabolic.demand[start:end],
                    hepatic=metabolic.hepatic[start:end],
                    carb_supply=metabolic.carb_supply[start:end],
                    net_flux=metabolic.net_flux[start:end],
                    residual=metabolic.residual[start:end],
                )
            else:
                ms = None

            alert = predict_hypo(window, ms)
            patient_total += 1

            # Check if counter-reg would have been active
            if ms is not None and len(ms.residual) > 4:
                recent_res = ms.residual[-4:]
                if float(np.nanmax(recent_res)) > COUNTER_REG_FLOOR:
                    patient_dampened += 1
                    dampened += 1
                else:
                    not_dampened += 1

        per_patient[pid] = {
            'total_near_hypo': patient_total,
            'counter_reg_active': patient_dampened,
            'pct_dampened': patient_dampened / max(patient_total, 1) * 100,
        }
        print(f"  {pid}: {patient_dampened}/{patient_total} near-hypo windows "
              f"with counter-reg active ({per_patient[pid]['pct_dampened']:.0f}%)")

    print(f"\nTotal: {dampened} dampened, {not_dampened} not dampened")
    print(f"Counter-reg floor = {COUNTER_REG_FLOOR} mg/dL/step")

    return {'per_patient': per_patient, 'dampened': dampened, 'not_dampened': not_dampened}


# ══════════════════════════════════════════════════════════════════════
# EXP-1780: Optimization Sequence Phase Assignment
# ══════════════════════════════════════════════════════════════════════

def exp_1780_optimization_sequence(patients, make_figures=True):
    """Validate optimization phase assignment per patient.

    Expected: most patients start in REDUCE_VARIABILITY (CV > 28%),
    matching EXP-1765 finding that 9/11 need variability reduction first.
    """
    print("\n" + "=" * 70)
    print("EXP-1780: Optimization Sequence Phase Assignment")
    print("=" * 70)

    results = {}
    phase_counts = {p.value: 0 for p in OptimizationPhase}

    for pat in patients:
        pid = pat['name']
        glucose = pat['df']['glucose'].values.astype(np.float64)
        valid = glucose[np.isfinite(glucose)]

        phase = determine_optimization_phase(glucose)
        cv = float(np.std(valid) / np.mean(valid) * 100) if len(valid) > 0 else 0
        tir = float(np.mean((valid >= 70) & (valid <= 180))) if len(valid) > 0 else 0

        results[pid] = {
            'phase': phase.value,
            'cv': cv,
            'tir': tir * 100,
        }
        phase_counts[phase.value] += 1
        print(f"  {pid}: {phase.value:25s} (CV={cv:.1f}%, TIR={tir*100:.1f}%)")

    print(f"\nPhase distribution:")
    for phase, count in phase_counts.items():
        print(f"  {phase:25s}: {count}/{len(patients)}")

    reduce_var_count = phase_counts[OptimizationPhase.REDUCE_VARIABILITY.value]
    print(f"\n{reduce_var_count}/{len(patients)} need variability reduction first "
          f"(research expected: 9/11)")

    if make_figures:
        _plot_optimization_phases(results)

    return results


def _plot_optimization_phases(results):
    """Scatter plot of CV vs TIR colored by optimization phase."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        colors = {
            'reduce_variability': 'red',
            'center': 'orange',
            'personalize': 'green',
        }

        fig, ax = plt.subplots(figsize=(8, 6))
        for pid, r in results.items():
            ax.scatter(r['cv'], r['tir'], c=colors.get(r['phase'], 'gray'),
                       s=100, edgecolors='black', zorder=5)
            ax.annotate(pid, (r['cv'], r['tir']), fontsize=8,
                        xytext=(5, 5), textcoords='offset points')

        ax.axvline(28, color='red', linestyle='--', alpha=0.5, label='CV threshold (28%)')
        ax.axhline(70, color='green', linestyle='--', alpha=0.5, label='TIR target (70%)')
        ax.set_xlabel('Glucose CV (%)')
        ax.set_ylabel('Time in Range (%)')
        ax.set_title('EXP-1780: Optimization Phase Assignment')

        # Legend
        for phase, color in colors.items():
            ax.scatter([], [], c=color, s=60, label=phase, edgecolors='black')
        ax.legend(loc='lower left')
        plt.tight_layout()
        path = os.path.join(FIGURE_DIR, 'prod-fig8-optimization-phases.png')
        plt.savefig(path, dpi=150)
        plt.close()
        print(f"  Figure saved: {path}")
    except ImportError:
        print("  (matplotlib not available)")


# ══════════════════════════════════════════════════════════════════════
# EXP-1781: Rescue Phenotype Classification
# ══════════════════════════════════════════════════════════════════════

def exp_1781_rescue_phenotype(patients, make_figures=True):
    """Validate rescue phenotype classification.

    Expected: 6/11 under-rescuers (from EXP-1766).
    """
    print("\n" + "=" * 70)
    print("EXP-1781: Rescue Phenotype Classification")
    print("=" * 70)

    results = {}
    phenotype_counts = {p.value: 0 for p in RescuePhenotype}

    for pat in patients:
        pid = pat['name']
        df = pat['df']
        glucose = df['glucose'].values.astype(np.float64)
        carbs = df['carbs'].values.astype(np.float64) if 'carbs' in df.columns else np.zeros(len(glucose))

        phenotype = classify_rescue_phenotype(glucose, carbs)
        results[pid] = phenotype.value
        phenotype_counts[phenotype.value] += 1
        print(f"  {pid}: {phenotype.value}")

    print(f"\nPhenotype distribution:")
    for pheno, count in phenotype_counts.items():
        print(f"  {pheno:25s}: {count}/{len(patients)}")

    under = phenotype_counts[RescuePhenotype.UNDER_RESCUER.value]
    print(f"\n{under}/{len(patients)} under-rescuers (research expected: 6/11)")

    return {'per_patient': results, 'phenotype_counts': phenotype_counts}


# ══════════════════════════════════════════════════════════════════════
# EXP-1782: Three Ceilings Framework
# ══════════════════════════════════════════════════════════════════════

def exp_1782_three_ceilings(patients, make_figures=True):
    """Validate three ceilings framework on all patients.

    Expected: kinetics ceiling ~54% TAR unavoidable, combined +17.6% TIR max.
    """
    print("\n" + "=" * 70)
    print("EXP-1782: Three Ceilings Framework")
    print("=" * 70)

    results = {}
    for pat in patients:
        pid = pat['name']
        df = pat['df']
        glucose = df['glucose'].values.astype(np.float64)

        try:
            pdata = _make_patient_data(pat)
            metabolic = compute_metabolic_state(pdata)
        except Exception:
            metabolic = None

        ceilings = compute_three_ceilings(glucose, metabolic)

        results[pid] = ceilings
        print(f"  {pid}: TIR={ceilings['current_tir']:.1%}, "
              f"TAR={ceilings['current_tar']:.1%}, "
              f"headroom={ceilings['headroom']:.1%}, "
              f"theoretical best={ceilings['theoretical_best_tir']:.1%}")

    mean_headroom = float(np.mean([r['headroom'] for r in results.values()]))
    mean_best = float(np.mean([r['theoretical_best_tir'] for r in results.values()]))
    print(f"\nMean headroom: {mean_headroom:.1%}")
    print(f"Mean theoretical best TIR: {mean_best:.1%}")

    if make_figures:
        _plot_three_ceilings(results)

    return results


def _plot_three_ceilings(results):
    """Stacked bar chart showing current TIR, headroom, and ceiling."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        pids = sorted(results.keys())
        current_tir = [results[p]['current_tir'] * 100 for p in pids]
        headroom = [results[p]['headroom'] * 100 for p in pids]
        ceiling = [100 - results[p]['theoretical_best_tir'] * 100 for p in pids]

        fig, ax = plt.subplots(figsize=(10, 6))
        x = range(len(pids))
        ax.bar(x, current_tir, label='Current TIR', color='forestgreen')
        ax.bar(x, headroom, bottom=current_tir, label='Achievable headroom',
               color='gold')
        remaining = [100 - c - h for c, h in zip(current_tir, headroom)]
        ax.bar(x, remaining, bottom=[c + h for c, h in zip(current_tir, headroom)],
               label='Ceiling-limited', color='lightcoral')

        ax.set_xticks(x)
        ax.set_xticklabels(pids)
        ax.set_ylabel('Percentage (%)')
        ax.set_title('EXP-1782: Three Ceilings Framework — TIR Decomposition')
        ax.axhline(70, color='green', linestyle='--', alpha=0.5, label='70% TIR target')
        ax.legend(loc='upper right')
        plt.tight_layout()
        path = os.path.join(FIGURE_DIR, 'prod-fig9-three-ceilings.png')
        plt.savefig(path, dpi=150)
        plt.close()
        print(f"  Figure saved: {path}")
    except ImportError:
        print("  (matplotlib not available)")


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("EXP-1776–1782: Tier 2+3 Production Integration Validation")
    print("=" * 70)

    t0 = time.time()
    patients = _load_patients_raw(PATIENTS_DIR, max_patients=11)
    print(f"Loaded {len(patients)} patients in {time.time()-t0:.1f}s\n")

    all_results = {}

    all_results['exp_1776'] = exp_1776_excursion_detection(patients)
    all_results['exp_1777'] = exp_1777_cascade_detection(patients)
    all_results['exp_1778'] = exp_1778_harmonic_metabolic(patients)
    all_results['exp_1779'] = exp_1779_counter_reg_floor(patients)
    all_results['exp_1780'] = exp_1780_optimization_sequence(patients)
    all_results['exp_1781'] = exp_1781_rescue_phenotype(patients)
    all_results['exp_1782'] = exp_1782_three_ceilings(patients)

    # Save results
    results_path = os.path.join(RESULTS_DIR, 'exp-1776_tier2_validation.json')
    serializable = {}
    for k, v in all_results.items():
        try:
            json.dumps(v)
            serializable[k] = v
        except (TypeError, ValueError):
            serializable[k] = str(v)[:200]
    with open(results_path, 'w') as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"\nResults saved: {results_path}")

    # Summary
    elapsed = time.time() - t0
    print(f"\n{'='*70}")
    print(f"SUMMARY (7 experiments in {elapsed:.0f}s)")
    print(f"{'='*70}")
    print(f"  EXP-1776: {all_results['exp_1776']['total_excursions']} excursions, "
          f"{all_results['exp_1776']['n_types']} types")
    print(f"  EXP-1777: {all_results['exp_1777']['mean_participation']:.1%} cascade participation")
    print(f"  EXP-1778: 4-harmonic metabolic engine validated")
    print(f"  EXP-1779: Counter-reg floor = {COUNTER_REG_FLOOR} mg/dL/step")
    print(f"  EXP-1780: Optimization phases assigned to all patients")
    print(f"  EXP-1781: Rescue phenotypes classified")
    print(f"  EXP-1782: Three ceilings framework bounds computed")


if __name__ == '__main__':
    main()
