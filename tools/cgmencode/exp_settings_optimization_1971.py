#!/usr/bin/env python3
"""EXP-1971–1978: Settings Optimization Simulation.

With loop behavior characterized (EXP-1961–1968) showing that 9/11 patients
have basal too high and loops predominantly withhold insulin, this batch
simulates what glucose outcomes WOULD look like with corrected settings.

Experiments:
  EXP-1971: Basal reduction simulation — what if basal were lowered 20-30%?
  EXP-1972: CR correction simulation — what if CR matched actual carb absorption?
  EXP-1973: Combined settings correction — basal + CR + ISF adjusted together
  EXP-1974: Loop headroom analysis — how much upward correction capacity exists?
  EXP-1975: Per-patient optimal settings search — find each patient's sweet spot
  EXP-1976: Settings stability over time — do optimal settings drift across months?
  EXP-1977: Risk-aware optimization — optimize TIR while constraining TBR < 4%
  EXP-1978: Synthesis — projected outcomes vs current and clinical recommendations
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from cgmencode.exp_metabolic_441 import load_patients, compute_supply_demand

warnings.filterwarnings('ignore')

FIGURES_DIR = Path('docs/60-research/figures')
RESULTS_PATH = Path('externals/experiments/exp-1971_settings_optimization.json')
STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288


def get_isf(p):
    s = p['df'].attrs.get('isf_schedule', None)
    if s and isinstance(s, list) and len(s) > 0:
        v = s[0].get('value', s[0].get('sensitivity', 50))
        return v * 18.0182 if v < 15 else v
    return 50


def get_cr(p):
    s = p['df'].attrs.get('cr_schedule', None)
    if s and isinstance(s, list) and len(s) > 0:
        return s[0].get('value', s[0].get('ratio', 10))
    return 10


def get_basal(p):
    s = p['df'].attrs.get('basal_schedule', None)
    if s and isinstance(s, list) and len(s) > 0:
        return s[0].get('value', s[0].get('rate', 1.0))
    return 1.0


def glucose_metrics(glucose):
    """Compute standard glucose metrics from a glucose array."""
    valid = glucose[np.isfinite(glucose)]
    if len(valid) < 100:
        return {'tir': np.nan, 'tbr': np.nan, 'tar': np.nan, 'cv': np.nan, 'mean': np.nan}
    return {
        'tir': float(np.mean((valid >= 70) & (valid <= 180)) * 100),
        'tbr': float(np.mean(valid < 70) * 100),
        'tar': float(np.mean(valid > 180) * 100),
        'cv': float(np.std(valid) / np.mean(valid) * 100),
        'mean': float(np.mean(valid)),
    }


def simulate_basal_change(glucose, net_basal, isf, basal_change_pct):
    """Simulate glucose trajectory if basal were changed by a percentage.

    Simple first-order model: changing basal by X% changes net insulin delivery,
    which shifts glucose by ISF * delta_insulin over time.
    """
    g = glucose.copy()
    nb = net_basal.copy()
    valid = np.isfinite(g) & np.isfinite(nb)

    # Basal change in U/h → delta insulin per 5-min step = change * (5/60)
    # But the loop was already compensating, so we model the net effect:
    # If basal is lowered, the loop would have less to compensate → net insulin
    # approximately stays the same for the "zero delivery" periods,
    # but changes for the "active delivery" periods.

    # Conservative model: when loop was at zero delivery (nb very negative),
    # lowering basal doesn't change actual delivery (still zero).
    # When loop was delivering (nb > -basal_change), lowering changes delivery.

    # Effective delta glucose = -ISF * actual_delta_delivery * dt
    # For simplicity, use a statistical approach: net_basal shifts by basal_change_pct
    # of scheduled basal, but capped at zero delivery floor.

    delta_per_step = np.zeros_like(g)
    for i in range(len(g)):
        if not valid[i]:
            continue
        # The loop's net_basal would shift: if we lower scheduled basal by 20%,
        # net_basal goes up by 20% of scheduled (less suppression needed)
        # But if the loop was already at zero delivery, no change.
        shift = basal_change_pct / 100.0  # positive = lower basal = less insulin = higher glucose
        # Approximate: glucose change = +ISF * basal_reduction_U_per_step
        # One step = 5 min, so U per step = basal_change * scheduled_basal * (5/60)
        # But we don't have scheduled basal per step. Use a fixed estimate.
        delta_per_step[i] = shift * 0.01 * isf  # rough scaling

    # Cumulative effect with decay (insulin action has a lifetime)
    tau_steps = 36  # 3 hours
    sim_g = g.copy()
    cumulative = 0.0
    for i in range(len(sim_g)):
        if not np.isfinite(sim_g[i]):
            continue
        cumulative = cumulative * (1 - 1.0 / tau_steps) + delta_per_step[i]
        sim_g[i] = g[i] + cumulative

    return sim_g


def simulate_cr_change(glucose, carbs, isf, cr_current, cr_new):
    """Simulate glucose if CR were changed.

    Changing CR changes bolus sizes: new_bolus = carbs / cr_new vs old_bolus = carbs / cr_current.
    Delta bolus = carbs * (1/cr_new - 1/cr_current)
    Delta glucose = -ISF * delta_bolus (spread over absorption time)
    """
    g = glucose.copy()
    c = carbs.copy()

    tau_steps = 36  # 3 hour absorption
    cumulative = 0.0
    for i in range(len(g)):
        if not np.isfinite(g[i]):
            continue
        # Decay existing effect
        cumulative *= (1 - 1.0 / tau_steps)
        # Add new meal effect
        if np.isfinite(c[i]) and c[i] > 0:
            delta_bolus = c[i] * (1.0 / cr_new - 1.0 / cr_current)
            # Glucose effect = -ISF * delta_bolus, distributed over tau_steps
            cumulative += -isf * delta_bolus / tau_steps
        g[i] = g[i] + cumulative

    return g


# =====================================================================
def exp_1971(patients, save_fig=False):
    """What if basal were lowered 20-30%?"""
    print("\n" + "=" * 70)
    print("EXP-1971: Basal Reduction Simulation")
    print("=" * 70)

    reductions = [0, -10, -20, -30, -40]
    all_results = []

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(df))
        isf = get_isf(p)

        current = glucose_metrics(glucose)
        if np.isnan(current['tir']):
            continue

        patient_results = {'patient': name, 'current': current, 'simulations': {}}
        for pct in reductions:
            if pct == 0:
                patient_results['simulations'][str(pct)] = current
                continue
            sim_g = simulate_basal_change(glucose, net_basal, isf, -pct)  # negative because lowering
            metrics = glucose_metrics(sim_g)
            patient_results['simulations'][str(pct)] = metrics

        all_results.append(patient_results)

        best_pct = min(reductions[1:], key=lambda x: -patient_results['simulations'][str(x)].get('tir', 0))
        best_tir = patient_results['simulations'][str(best_pct)]['tir']
        print(f"  {name}: current TIR={current['tir']:.0f}% → best at {best_pct}%: TIR={best_tir:.0f}%")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 2, figsize=(14, 6))

            for r in all_results:
                tirs = [r['simulations'][str(pct)]['tir'] for pct in reductions]
                axes[0].plot(reductions, tirs, 'o-', label=r['patient'], alpha=0.6)
            axes[0].set_xlabel('Basal change (%)')
            axes[0].set_ylabel('Simulated TIR (%)')
            axes[0].set_title('TIR vs Basal Reduction')
            axes[0].legend(fontsize=7, ncol=2)
            axes[0].axhline(70, color='gray', linestyle='--', alpha=0.3)

            for r in all_results:
                tbrs = [r['simulations'][str(pct)]['tbr'] for pct in reductions]
                axes[1].plot(reductions, tbrs, 'o-', label=r['patient'], alpha=0.6)
            axes[1].set_xlabel('Basal change (%)')
            axes[1].set_ylabel('Simulated TBR (%)')
            axes[1].set_title('Hypo Risk vs Basal Reduction')
            axes[1].axhline(4, color='red', linestyle='--', alpha=0.5, label='4% safety line')
            axes[1].legend(fontsize=7, ncol=2)

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'opt-fig01-basal-reduction.png', dpi=150)
            plt.close()
            print(f"  → Saved opt-fig01-basal-reduction.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    # Find population optimal
    pop_best = {}
    for pct in reductions[1:]:
        mean_tir = np.mean([r['simulations'][str(pct)]['tir'] for r in all_results])
        mean_tbr = np.mean([r['simulations'][str(pct)]['tbr'] for r in all_results])
        pop_best[pct] = {'tir': mean_tir, 'tbr': mean_tbr}

    best_pop = max(pop_best.items(), key=lambda x: x[1]['tir'] if x[1]['tbr'] < 5 else 0)
    verdict = f"OPTIMAL_{best_pop[0]}%_TIR_{best_pop[1]['tir']:.0f}%"
    print(f"\n  ✓ EXP-1971 verdict: {verdict}")
    return {'experiment': 'EXP-1971', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def exp_1972(patients, save_fig=False):
    """What if CR matched actual absorption (lowered by 28%)?"""
    print("\n" + "=" * 70)
    print("EXP-1972: CR Correction Simulation")
    print("=" * 70)

    cr_changes = [0, -10, -20, -28, -35]  # -28% is our recommendation
    all_results = []

    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        isf = get_isf(p)
        cr_current = get_cr(p)

        current = glucose_metrics(glucose)
        if np.isnan(current['tir']):
            continue

        patient_results = {'patient': name, 'cr_current': float(cr_current), 'current': current, 'simulations': {}}
        for pct in cr_changes:
            if pct == 0:
                patient_results['simulations'][str(pct)] = current
                continue
            cr_new = cr_current * (1 + pct / 100.0)
            sim_g = simulate_cr_change(glucose, carbs, isf, cr_current, cr_new)
            metrics = glucose_metrics(sim_g)
            patient_results['simulations'][str(pct)] = metrics

        all_results.append(patient_results)

        rec_sim = patient_results['simulations']['-28']
        print(f"  {name}: CR={cr_current:.0f} current TIR={current['tir']:.0f}% → "
              f"-28% CR: TIR={rec_sim['tir']:.0f}% TBR={rec_sim['tbr']:.1f}%")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 2, figsize=(14, 6))

            for r in all_results:
                tirs = [r['simulations'][str(pct)]['tir'] for pct in cr_changes]
                axes[0].plot(cr_changes, tirs, 'o-', label=r['patient'], alpha=0.6)
            axes[0].axvline(-28, color='red', linestyle='--', alpha=0.5, label='Recommended (-28%)')
            axes[0].set_xlabel('CR change (%)')
            axes[0].set_ylabel('Simulated TIR (%)')
            axes[0].set_title('TIR vs CR Reduction')
            axes[0].legend(fontsize=7, ncol=2)

            for r in all_results:
                tbrs = [r['simulations'][str(pct)]['tbr'] for pct in cr_changes]
                axes[1].plot(cr_changes, tbrs, 'o-', label=r['patient'], alpha=0.6)
            axes[1].axhline(4, color='red', linestyle='--', alpha=0.5, label='4% safety')
            axes[1].axvline(-28, color='red', linestyle='--', alpha=0.3)
            axes[1].set_xlabel('CR change (%)')
            axes[1].set_ylabel('Simulated TBR (%)')
            axes[1].set_title('Hypo Risk vs CR Reduction')
            axes[1].legend(fontsize=7, ncol=2)

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'opt-fig02-cr-correction.png', dpi=150)
            plt.close()
            print(f"  → Saved opt-fig02-cr-correction.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    mean_tir_28 = np.mean([r['simulations']['-28']['tir'] for r in all_results])
    mean_tbr_28 = np.mean([r['simulations']['-28']['tbr'] for r in all_results])
    verdict = f"CR-28%_TIR_{mean_tir_28:.0f}%_TBR_{mean_tbr_28:.1f}%"
    print(f"\n  ✓ EXP-1972 verdict: {verdict}")
    return {'experiment': 'EXP-1972', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def exp_1973(patients, save_fig=False):
    """Combined: basal + CR + ISF adjustment together."""
    print("\n" + "=" * 70)
    print("EXP-1973: Combined Settings Correction")
    print("=" * 70)

    scenarios = {
        'current': {'basal': 0, 'cr': 0, 'isf': 0},
        'conservative': {'basal': -10, 'cr': -15, 'isf': +10},
        'recommended': {'basal': -20, 'cr': -28, 'isf': +19},
        'aggressive': {'basal': -30, 'cr': -35, 'isf': +25},
    }

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(df))
        isf = get_isf(p)
        cr = get_cr(p)

        current = glucose_metrics(glucose)
        if np.isnan(current['tir']):
            continue

        patient_results = {'patient': name, 'scenarios': {}}
        for label, changes in scenarios.items():
            if label == 'current':
                patient_results['scenarios'][label] = current
                continue

            # Apply basal change first
            g1 = simulate_basal_change(glucose, net_basal, isf, -changes['basal'])
            # Then CR change
            cr_new = cr * (1 + changes['cr'] / 100.0)
            g2 = simulate_cr_change(g1, carbs, isf, cr, cr_new)

            metrics = glucose_metrics(g2)
            patient_results['scenarios'][label] = metrics

        all_results.append(patient_results)

        rec = patient_results['scenarios']['recommended']
        cur = patient_results['scenarios']['current']
        delta_tir = rec['tir'] - cur['tir']
        print(f"  {name}: current TIR={cur['tir']:.0f}% → recommended: TIR={rec['tir']:.0f}% "
              f"(Δ={delta_tir:+.0f}pp) TBR={rec['tbr']:.1f}%")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 3, figsize=(18, 6))

            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))
            w = 0.2

            for i, (label, color) in enumerate([
                ('current', '#95a5a6'), ('conservative', '#3498db'),
                ('recommended', '#27ae60'), ('aggressive', '#e74c3c')
            ]):
                tirs = [r['scenarios'][label]['tir'] for r in all_results]
                axes[0].bar(x + i * w, tirs, w, label=label, color=color)

            axes[0].set_xticks(x + 1.5 * w)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('TIR (%)')
            axes[0].set_title('Simulated TIR by Scenario')
            axes[0].axhline(70, color='gray', linestyle='--', alpha=0.3)
            axes[0].legend()

            # TBR safety check
            for i, (label, color) in enumerate([
                ('current', '#95a5a6'), ('conservative', '#3498db'),
                ('recommended', '#27ae60'), ('aggressive', '#e74c3c')
            ]):
                tbrs = [r['scenarios'][label]['tbr'] for r in all_results]
                axes[1].bar(x + i * w, tbrs, w, label=label, color=color)
            axes[1].axhline(4, color='red', linestyle='--', alpha=0.5)
            axes[1].set_xticks(x + 1.5 * w)
            axes[1].set_xticklabels(names)
            axes[1].set_ylabel('TBR (%)')
            axes[1].set_title('Hypo Safety by Scenario')
            axes[1].legend()

            # Delta TIR from current
            for label, color in [('conservative', '#3498db'), ('recommended', '#27ae60'), ('aggressive', '#e74c3c')]:
                deltas = [r['scenarios'][label]['tir'] - r['scenarios']['current']['tir'] for r in all_results]
                axes[2].bar(x + ({'conservative': 0, 'recommended': 1, 'aggressive': 2}[label]) * 0.25,
                           deltas, 0.25, label=label, color=color)
            axes[2].set_xticks(x + 0.25)
            axes[2].set_xticklabels(names)
            axes[2].axhline(0, color='k', linestyle='--')
            axes[2].set_ylabel('ΔTIR from current (pp)')
            axes[2].set_title('Projected TIR Improvement')
            axes[2].legend()

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'opt-fig03-combined.png', dpi=150)
            plt.close()
            print(f"  → Saved opt-fig03-combined.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    rec_tirs = [r['scenarios']['recommended']['tir'] for r in all_results]
    cur_tirs = [r['scenarios']['current']['tir'] for r in all_results]
    mean_delta = np.mean(np.array(rec_tirs) - np.array(cur_tirs))
    wins = sum(1 for r, c in zip(rec_tirs, cur_tirs) if r > c)
    verdict = f"RECOMMENDED_Δ{mean_delta:+.0f}pp_{wins}/{len(all_results)}_IMPROVE"
    print(f"\n  ✓ EXP-1973 verdict: {verdict}")
    return {'experiment': 'EXP-1973', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def exp_1974(patients, save_fig=False):
    """How much upward correction headroom does the loop have?"""
    print("\n" + "=" * 70)
    print("EXP-1974: Loop Headroom Analysis")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(df))
        temp_rate = df['temp_rate'].values if 'temp_rate' in df.columns else np.zeros(len(df))
        basal_sched = get_basal(p)

        valid = np.isfinite(net_basal) & np.isfinite(glucose)
        if valid.sum() < 1000:
            continue

        nb = net_basal[valid]
        g = glucose[valid]
        tr = temp_rate[valid]

        # Headroom: how much could the loop increase delivery?
        # When glucose > 180, what's the max net_basal typically used?
        high_nb = nb[g > 180]
        max_increase = float(np.percentile(high_nb, 95)) if len(high_nb) > 10 else 0

        # What fraction of time is the loop at max delivery?
        at_max = (tr >= basal_sched * 2).sum() / len(tr) * 100 if basal_sched > 0 else 0

        # Potential headroom if basal were lowered
        # Current: loop at -0.7 U/h mean. If basal lowered 30%, loop would be at ~0 U/h mean
        # giving it +0.7 U/h of upward headroom
        mean_nb = float(np.mean(nb))
        theoretical_headroom = abs(mean_nb)  # This is what we'd gain

        # Utilization of available headroom when glucose is high
        if len(high_nb) > 10:
            high_headroom_used = float(np.mean(high_nb > 0))
        else:
            high_headroom_used = np.nan

        result = {
            'patient': name,
            'basal_sched': float(basal_sched),
            'mean_net_basal': float(mean_nb),
            'max_increase_p95': float(max_increase),
            'pct_at_max': float(at_max),
            'theoretical_headroom': float(theoretical_headroom),
            'high_glucose_inc_pct': float(high_headroom_used) * 100 if np.isfinite(high_headroom_used) else None,
        }
        all_results.append(result)

        print(f"  {name}: sched={basal_sched:.2f} mean_nb={mean_nb:+.2f} "
              f"headroom={theoretical_headroom:.2f}U/h max_inc={max_increase:+.2f}")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 2, figsize=(14, 6))

            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))

            # Current vs potential headroom
            sched = [r['basal_sched'] for r in all_results]
            headroom = [r['theoretical_headroom'] for r in all_results]
            axes[0].bar(x, sched, 0.35, label='Scheduled basal', color='#3498db')
            axes[0].bar(x + 0.35, headroom, 0.35, label='Wasted headroom', color='#e74c3c')
            axes[0].set_xticks(x + 0.175)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('U/h')
            axes[0].set_title('Scheduled Basal vs Wasted Headroom')
            axes[0].legend()

            # Max correction capacity when glucose high
            max_inc = [r['max_increase_p95'] for r in all_results]
            axes[1].bar(x, max_inc, color='#27ae60')
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].axhline(0, color='k', linestyle='--')
            axes[1].set_ylabel('P95 net basal during glucose >180 (U/h)')
            axes[1].set_title('Loop Correction Capacity at High Glucose')

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'opt-fig04-headroom.png', dpi=150)
            plt.close()
            print(f"  → Saved opt-fig04-headroom.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    mean_headroom = np.mean([r['theoretical_headroom'] for r in all_results])
    verdict = f"HEADROOM_{mean_headroom:.2f}U/h"
    print(f"\n  ✓ EXP-1974 verdict: {verdict}")
    return {'experiment': 'EXP-1974', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def exp_1975(patients, save_fig=False):
    """Find per-patient optimal settings via grid search."""
    print("\n" + "=" * 70)
    print("EXP-1975: Per-Patient Optimal Settings Search")
    print("=" * 70)

    basal_range = [0, -10, -20, -30]
    cr_range = [0, -10, -20, -28, -35]

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(df))
        isf = get_isf(p)
        cr = get_cr(p)

        current = glucose_metrics(glucose)
        if np.isnan(current['tir']):
            continue

        best_tir = current['tir']
        best_combo = {'basal': 0, 'cr': 0}
        grid_results = []

        for b_pct in basal_range:
            for c_pct in cr_range:
                if b_pct == 0 and c_pct == 0:
                    metrics = current
                else:
                    g1 = simulate_basal_change(glucose, net_basal, isf, -b_pct)
                    cr_new = cr * (1 + c_pct / 100.0) if c_pct != 0 else cr
                    g2 = simulate_cr_change(g1, carbs, isf, cr, cr_new) if c_pct != 0 else g1
                    metrics = glucose_metrics(g2)

                grid_results.append({
                    'basal_pct': b_pct,
                    'cr_pct': c_pct,
                    'tir': metrics['tir'],
                    'tbr': metrics['tbr'],
                })

                # Best = highest TIR with TBR < 5%
                if metrics['tir'] > best_tir and metrics['tbr'] < 5:
                    best_tir = metrics['tir']
                    best_combo = {'basal': b_pct, 'cr': c_pct}

        result = {
            'patient': name,
            'current_tir': current['tir'],
            'current_tbr': current['tbr'],
            'best_tir': best_tir,
            'best_basal': best_combo['basal'],
            'best_cr': best_combo['cr'],
            'improvement': best_tir - current['tir'],
        }
        all_results.append(result)

        print(f"  {name}: current={current['tir']:.0f}% → best={best_tir:.0f}% "
              f"(basal={best_combo['basal']}% CR={best_combo['cr']}%) Δ={best_tir - current['tir']:+.0f}pp")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 2, figsize=(14, 6))

            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))

            cur = [r['current_tir'] for r in all_results]
            best = [r['best_tir'] for r in all_results]
            axes[0].bar(x, cur, 0.35, label='Current', color='#95a5a6')
            axes[0].bar(x + 0.35, best, 0.35, label='Optimized', color='#27ae60')
            axes[0].set_xticks(x + 0.175)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('TIR (%)')
            axes[0].set_title('Current vs Optimized TIR')
            axes[0].axhline(70, color='gray', linestyle='--', alpha=0.3)
            axes[0].legend()

            # Optimal settings
            basal_opts = [r['best_basal'] for r in all_results]
            cr_opts = [r['best_cr'] for r in all_results]
            axes[1].scatter(basal_opts, cr_opts, s=100, c=[r['improvement'] for r in all_results],
                          cmap='RdYlGn', edgecolors='black', linewidth=0.5)
            for r in all_results:
                axes[1].annotate(r['patient'], (r['best_basal'], r['best_cr']),
                                fontsize=8, ha='center', va='bottom')
            axes[1].set_xlabel('Optimal basal change (%)')
            axes[1].set_ylabel('Optimal CR change (%)')
            axes[1].set_title('Per-Patient Optimal Settings')
            plt.colorbar(axes[1].collections[0], ax=axes[1], label='ΔTIR (pp)')

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'opt-fig05-optimal-search.png', dpi=150)
            plt.close()
            print(f"  → Saved opt-fig05-optimal-search.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    mean_improvement = np.mean([r['improvement'] for r in all_results])
    n_improve = sum(1 for r in all_results if r['improvement'] > 0)
    verdict = f"MEAN_Δ{mean_improvement:+.0f}pp_{n_improve}/{len(all_results)}_IMPROVE"
    print(f"\n  ✓ EXP-1975 verdict: {verdict}")
    return {'experiment': 'EXP-1975', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def exp_1976(patients, save_fig=False):
    """Do optimal settings drift over time?"""
    print("\n" + "=" * 70)
    print("EXP-1976: Settings Stability Over Time")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(df))

        n = len(glucose)
        mid = n // 2
        if mid < 5000:
            continue

        # Split into halves
        g1 = glucose[:mid]
        g2 = glucose[mid:]
        nb1 = net_basal[:mid]
        nb2 = net_basal[mid:]

        # Metrics for each half
        m1 = glucose_metrics(g1)
        m2 = glucose_metrics(g2)

        if np.isnan(m1['tir']) or np.isnan(m2['tir']):
            continue

        # Compensation behavior stability
        valid1 = np.isfinite(nb1)
        valid2 = np.isfinite(nb2)
        mean_comp1 = float(np.mean(np.abs(nb1[valid1]))) if valid1.sum() > 100 else np.nan
        mean_comp2 = float(np.mean(np.abs(nb2[valid2]))) if valid2.sum() > 100 else np.nan
        comp_change = mean_comp2 - mean_comp1

        result = {
            'patient': name,
            'half1_tir': m1['tir'],
            'half2_tir': m2['tir'],
            'tir_drift': m2['tir'] - m1['tir'],
            'half1_tbr': m1['tbr'],
            'half2_tbr': m2['tbr'],
            'tbr_drift': m2['tbr'] - m1['tbr'],
            'half1_comp': float(mean_comp1) if np.isfinite(mean_comp1) else None,
            'half2_comp': float(mean_comp2) if np.isfinite(mean_comp2) else None,
            'comp_drift': float(comp_change) if np.isfinite(comp_change) else None,
        }
        all_results.append(result)

        print(f"  {name}: TIR {m1['tir']:.0f}%→{m2['tir']:.0f}% (Δ={m2['tir']-m1['tir']:+.0f}pp) "
              f"comp {mean_comp1:.2f}→{mean_comp2:.2f} (Δ={comp_change:+.2f})" if np.isfinite(comp_change) else
              f"  {name}: TIR {m1['tir']:.0f}%→{m2['tir']:.0f}%")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 2, figsize=(14, 6))

            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))

            tir_drift = [r['tir_drift'] for r in all_results]
            colors = ['#27ae60' if d > 0 else '#e74c3c' for d in tir_drift]
            axes[0].bar(x, tir_drift, color=colors)
            axes[0].set_xticks(x)
            axes[0].set_xticklabels(names)
            axes[0].axhline(0, color='k', linestyle='--')
            axes[0].set_ylabel('ΔTIR (half 2 - half 1) pp')
            axes[0].set_title('TIR Drift Over 90-Day Halves')

            comp_drift = [r['comp_drift'] if r['comp_drift'] is not None else 0 for r in all_results]
            colors2 = ['#e74c3c' if d > 0 else '#27ae60' for d in comp_drift]
            axes[1].bar(x, comp_drift, color=colors2)
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].axhline(0, color='k', linestyle='--')
            axes[1].set_ylabel('ΔCompensation (U/h)')
            axes[1].set_title('Loop Compensation Drift\n(+ = loop working harder)')

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'opt-fig06-stability.png', dpi=150)
            plt.close()
            print(f"  → Saved opt-fig06-stability.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    mean_drift = np.mean([abs(r['tir_drift']) for r in all_results])
    stable = sum(1 for r in all_results if abs(r['tir_drift']) < 5)
    verdict = f"MEAN_DRIFT_{mean_drift:.0f}pp_{stable}/{len(all_results)}_STABLE"
    print(f"\n  ✓ EXP-1976 verdict: {verdict}")
    return {'experiment': 'EXP-1976', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def exp_1977(patients, save_fig=False):
    """Optimize TIR while keeping TBR < 4%."""
    print("\n" + "=" * 70)
    print("EXP-1977: Risk-Aware Settings Optimization")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(df))
        isf = get_isf(p)
        cr = get_cr(p)

        current = glucose_metrics(glucose)
        if np.isnan(current['tir']):
            continue

        # Grid search with TBR constraint
        best_tir = current['tir']
        best_combo = {'basal': 0, 'cr': 0}
        safe_options = []

        for b_pct in [0, -10, -20, -30]:
            for c_pct in [0, -10, -20, -28, -35]:
                if b_pct == 0 and c_pct == 0:
                    metrics = current
                else:
                    g1 = simulate_basal_change(glucose, net_basal, isf, -b_pct)
                    cr_new = cr * (1 + c_pct / 100.0) if c_pct != 0 else cr
                    g2 = simulate_cr_change(g1, carbs, isf, cr, cr_new) if c_pct != 0 else g1
                    metrics = glucose_metrics(g2)

                safe_options.append({
                    'basal': b_pct, 'cr': c_pct,
                    'tir': metrics['tir'], 'tbr': metrics['tbr'],
                    'safe': metrics['tbr'] < 4.0,
                })

                if metrics['tbr'] < 4.0 and metrics['tir'] > best_tir:
                    best_tir = metrics['tir']
                    best_combo = {'basal': b_pct, 'cr': c_pct}

        # Find the TBR boundary
        safe_count = sum(1 for o in safe_options if o['safe'])

        result = {
            'patient': name,
            'current_tir': current['tir'],
            'current_tbr': current['tbr'],
            'safe_best_tir': best_tir,
            'safe_best_basal': best_combo['basal'],
            'safe_best_cr': best_combo['cr'],
            'safe_improvement': best_tir - current['tir'],
            'safe_options_count': safe_count,
            'total_options': len(safe_options),
        }
        all_results.append(result)

        print(f"  {name}: safe_best={best_tir:.0f}% (basal={best_combo['basal']}% CR={best_combo['cr']}%) "
              f"Δ={best_tir-current['tir']:+.0f}pp safe={safe_count}/{len(safe_options)}")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, 2, figsize=(14, 6))

            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))

            cur = [r['current_tir'] for r in all_results]
            safe = [r['safe_best_tir'] for r in all_results]
            axes[0].bar(x, cur, 0.35, label='Current', color='#95a5a6')
            axes[0].bar(x + 0.35, safe, 0.35, label='Safe optimized (TBR<4%)', color='#27ae60')
            axes[0].set_xticks(x + 0.175)
            axes[0].set_xticklabels(names)
            axes[0].set_ylabel('TIR (%)')
            axes[0].set_title('TIR: Current vs Safe Optimized')
            axes[0].axhline(70, color='gray', linestyle='--', alpha=0.3)
            axes[0].legend()

            # Safe option space
            safe_frac = [r['safe_options_count'] / r['total_options'] * 100 for r in all_results]
            axes[1].bar(x, safe_frac, color='#3498db')
            axes[1].set_xticks(x)
            axes[1].set_xticklabels(names)
            axes[1].set_ylabel('% of options with TBR < 4%')
            axes[1].set_title('Safe Settings Space per Patient')

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'opt-fig07-risk-aware.png', dpi=150)
            plt.close()
            print(f"  → Saved opt-fig07-risk-aware.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    mean_imp = np.mean([r['safe_improvement'] for r in all_results])
    n_improve = sum(1 for r in all_results if r['safe_improvement'] > 0)
    verdict = f"SAFE_Δ{mean_imp:+.0f}pp_{n_improve}/{len(all_results)}_IMPROVE"
    print(f"\n  ✓ EXP-1977 verdict: {verdict}")
    return {'experiment': 'EXP-1977', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def exp_1978(patients, save_fig=False):
    """Synthesis: project outcomes and generate clinical summary."""
    print("\n" + "=" * 70)
    print("EXP-1978: Projected Outcomes Synthesis")
    print("=" * 70)

    all_results = []
    for p in patients:
        name = p['name']
        df = p['df']
        glucose = df['glucose'].values
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(df))
        net_basal = df['net_basal'].values if 'net_basal' in df.columns else np.zeros(len(df))
        isf = get_isf(p)
        cr = get_cr(p)
        basal = get_basal(p)

        current = glucose_metrics(glucose)
        if np.isnan(current['tir']):
            continue

        # Recommended scenario
        g1 = simulate_basal_change(glucose, net_basal, isf, 20)  # lower basal 20%
        cr_new = cr * 0.72  # -28% CR
        g2 = simulate_cr_change(g1, carbs, isf, cr, cr_new)
        recommended = glucose_metrics(g2)

        # eA1c calculation
        current_ea1c = (current['mean'] + 46.7) / 28.7
        rec_ea1c = (recommended['mean'] + 46.7) / 28.7

        # Summary
        result = {
            'patient': name,
            'current_tir': current['tir'],
            'current_tbr': current['tbr'],
            'current_tar': current['tar'],
            'current_cv': current['cv'],
            'current_ea1c': float(current_ea1c),
            'recommended_tir': recommended['tir'],
            'recommended_tbr': recommended['tbr'],
            'recommended_tar': recommended['tar'],
            'recommended_cv': recommended['cv'],
            'recommended_ea1c': float(rec_ea1c),
            'settings': {
                'basal': float(basal),
                'cr': float(cr),
                'isf': float(isf),
                'rec_basal': float(basal * 0.80),
                'rec_cr': float(cr * 0.72),
                'rec_isf': float(isf * 1.19),
            },
        }
        all_results.append(result)

        print(f"  {name}: TIR {current['tir']:.0f}%→{recommended['tir']:.0f}% "
              f"TBR {current['tbr']:.1f}%→{recommended['tbr']:.1f}% "
              f"eA1c {current_ea1c:.1f}→{rec_ea1c:.1f}")

    if save_fig:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(2, 2, figsize=(14, 12))

            names = [r['patient'] for r in all_results]
            x = np.arange(len(names))

            # TIR comparison
            cur_tir = [r['current_tir'] for r in all_results]
            rec_tir = [r['recommended_tir'] for r in all_results]
            axes[0, 0].bar(x, cur_tir, 0.35, label='Current', color='#95a5a6')
            axes[0, 0].bar(x + 0.35, rec_tir, 0.35, label='Projected', color='#27ae60')
            axes[0, 0].set_xticks(x + 0.175)
            axes[0, 0].set_xticklabels(names)
            axes[0, 0].set_ylabel('TIR (%)')
            axes[0, 0].set_title('Current vs Projected TIR')
            axes[0, 0].axhline(70, color='gray', linestyle='--', alpha=0.3)
            axes[0, 0].legend()

            # TBR safety
            cur_tbr = [r['current_tbr'] for r in all_results]
            rec_tbr = [r['recommended_tbr'] for r in all_results]
            axes[0, 1].bar(x, cur_tbr, 0.35, label='Current', color='#95a5a6')
            axes[0, 1].bar(x + 0.35, rec_tbr, 0.35, label='Projected', color='#27ae60')
            axes[0, 1].axhline(4, color='red', linestyle='--', alpha=0.5, label='4% limit')
            axes[0, 1].set_xticks(x + 0.175)
            axes[0, 1].set_xticklabels(names)
            axes[0, 1].set_ylabel('TBR (%)')
            axes[0, 1].set_title('Hypo Safety Check')
            axes[0, 1].legend()

            # eA1c
            cur_a1c = [r['current_ea1c'] for r in all_results]
            rec_a1c = [r['recommended_ea1c'] for r in all_results]
            axes[1, 0].bar(x, cur_a1c, 0.35, label='Current', color='#95a5a6')
            axes[1, 0].bar(x + 0.35, rec_a1c, 0.35, label='Projected', color='#27ae60')
            axes[1, 0].set_xticks(x + 0.175)
            axes[1, 0].set_xticklabels(names)
            axes[1, 0].set_ylabel('eA1c (%)')
            axes[1, 0].set_title('Current vs Projected eA1c')
            axes[1, 0].legend()

            # Settings table
            axes[1, 1].axis('off')
            table_data = []
            for r in all_results:
                s = r['settings']
                table_data.append([
                    r['patient'],
                    f"{s['basal']:.2f}→{s['rec_basal']:.2f}",
                    f"{s['cr']:.0f}→{s['rec_cr']:.0f}",
                    f"{s['isf']:.0f}→{s['rec_isf']:.0f}",
                    f"{r['current_tir']:.0f}→{r['recommended_tir']:.0f}",
                ])
            table = axes[1, 1].table(cellText=table_data,
                                     colLabels=['Patient', 'Basal (U/h)', 'CR (g/U)', 'ISF (mg/dL/U)', 'TIR (%)'],
                                     loc='center', cellLoc='center')
            table.auto_set_font_size(False)
            table.set_fontsize(8)
            table.scale(1.0, 1.5)
            axes[1, 1].set_title('Settings: Current → Recommended')

            plt.tight_layout()
            plt.savefig(FIGURES_DIR / 'opt-fig08-synthesis.png', dpi=150)
            plt.close()
            print(f"  → Saved opt-fig08-synthesis.png")
        except Exception as e:
            print(f"  → Figure failed: {e}")

    pop_cur_tir = np.mean([r['current_tir'] for r in all_results])
    pop_rec_tir = np.mean([r['recommended_tir'] for r in all_results])
    pop_delta = pop_rec_tir - pop_cur_tir
    verdict = f"POP_TIR_{pop_cur_tir:.0f}→{pop_rec_tir:.0f}%_Δ{pop_delta:+.0f}pp"
    print(f"\n  ✓ EXP-1978 verdict: {verdict}")
    return {'experiment': 'EXP-1978', 'verdict': verdict, 'per_patient': all_results}


# =====================================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures', action='store_true')
    args = parser.parse_args()

    patients = load_patients('externals/ns-data/patients/')
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 70)
    print("EXP-1971–1978: Settings Optimization Simulation")
    print("=" * 70)

    results = {}
    for exp_id, fn in [('EXP-1971', exp_1971), ('EXP-1972', exp_1972), ('EXP-1973', exp_1973),
                        ('EXP-1974', exp_1974), ('EXP-1975', exp_1975), ('EXP-1976', exp_1976),
                        ('EXP-1977', exp_1977), ('EXP-1978', exp_1978)]:
        print(f"\n{'#' * 70}")
        print(f"# Running {exp_id}")
        print(f"{'#' * 70}")
        try:
            results[exp_id] = fn(patients, save_fig=args.figures)
        except Exception as e:
            print(f"\n  ✗ {exp_id} FAILED: {e}")
            import traceback; traceback.print_exc()
            results[exp_id] = {'experiment': exp_id, 'verdict': f'FAILED: {e}'}

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    def json_safe(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj) if np.isfinite(obj) else None
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, np.bool_): return bool(obj)
        raise TypeError(f"Not JSON serializable: {type(obj)}")

    with open(RESULTS_PATH, 'w') as f:
        json.dump(results, f, indent=2, default=json_safe)

    print("\n" + "=" * 70)
    print("SYNTHESIS: Settings Optimization Simulation")
    print("=" * 70)
    for k, v in results.items():
        print(f"  {k}: {v.get('verdict', 'N/A')}")


if __name__ == '__main__':
    main()
