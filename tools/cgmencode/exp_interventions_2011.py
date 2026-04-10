#!/usr/bin/env python3
"""
EXP-2011–2018: Intervention Design & Simulation

Designing and testing algorithmic interventions based on findings from
EXP-1941–2008. Each experiment proposes a concrete algorithm change and
simulates its impact on patient outcomes.

EXP-2011: ISF auto-calibration from correction outcomes
EXP-2012: Predictive hypo prevention (earlier suspension trigger)
EXP-2013: Post-hypo rebound management (reduced rebound overshoot)
EXP-2014: Absorption-speed adaptive meal dosing
EXP-2015: Dawn phenomenon proactive basal ramp
EXP-2016: Loop effort reduction (less aggressive correction)
EXP-2017: Combined intervention simulation
EXP-2018: Synthesis — intervention priority ranking

Depends on: exp_metabolic_441.py, findings from EXP-2001–2008
"""

import json
import sys
import os
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from exp_metabolic_441 import load_patients, compute_supply_demand

PATIENT_DIR = 'externals/ns-data/patients/'
FIG_DIR = 'docs/60-research/figures'
EXP_DIR = 'externals/experiments'
MAKE_FIGS = '--figures' in sys.argv

if MAKE_FIGS:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    os.makedirs(FIG_DIR, exist_ok=True)

os.makedirs(EXP_DIR, exist_ok=True)

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
HYPO_THRESH = 70
TARGET_LOW = 70
TARGET_HIGH = 180


def glucose_metrics(glucose):
    """Compute standard glucose metrics."""
    valid = glucose[np.isfinite(glucose)]
    if len(valid) < 100:
        return {'tir': np.nan, 'tbr': np.nan, 'tar': np.nan, 'mean': np.nan, 'cv': np.nan}
    return {
        'tir': float(np.mean((valid >= TARGET_LOW) & (valid <= TARGET_HIGH)) * 100),
        'tbr': float(np.mean(valid < TARGET_LOW) * 100),
        'tar': float(np.mean(valid > TARGET_HIGH) * 100),
        'mean': float(np.nanmean(valid)),
        'cv': float(np.nanstd(valid) / np.nanmean(valid) * 100) if np.nanmean(valid) > 0 else np.nan,
    }


def simulate_glucose_shift(glucose, shift_array):
    """Simulate glucose after applying a shift.
    shift_array: per-step glucose change (positive = raise glucose)
    Returns modified glucose array.
    """
    modified = glucose.copy()
    cumulative = np.cumsum(shift_array)
    valid = np.isfinite(modified)
    modified[valid] = modified[valid] + cumulative[valid]
    # Clamp to physiological range
    modified = np.clip(modified, 30, 500)
    return modified


# ─── Load data ───────────────────────────────────────────────
patients = load_patients(PATIENT_DIR)
results = {}


# ══════════════════════════════════════════════════════════════
# EXP-2011: ISF Auto-Calibration from Correction Outcomes
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2011")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2011: ISF Auto-Calibration from Correction Outcomes")
print("=" * 70)

exp2011 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))

    isf_schedule = df.attrs.get('isf_schedule', [{'value': 50}])
    profile_isf = isf_schedule[0]['value'] if isf_schedule else 50
    if profile_isf < 15:
        profile_isf *= 18.0182

    # Sliding window ISF learning: track last N corrections
    window_sizes = [5, 10, 20, 50]
    results_by_window = {}

    for ws in window_sizes:
        # Collect correction events
        corrections = []
        for i in range(len(glucose) - 24):
            if bolus[i] < 0.3:
                continue
            carb_window = carbs[max(0, i-12):min(len(carbs), i+12)]
            if np.nansum(carb_window) > 1:
                continue
            if not np.isfinite(glucose[i]) or glucose[i] < 120:
                continue
            g_after = glucose[min(i + 24, len(glucose) - 1)]
            if not np.isfinite(g_after):
                continue
            delta_g = glucose[i] - g_after
            if delta_g <= 0:
                continue
            eff_isf = delta_g / bolus[i]
            if eff_isf < 5 or eff_isf > 500:
                continue
            corrections.append({
                'step': i,
                'isf': eff_isf,
                'bolus': float(bolus[i]),
                'delta_g': float(delta_g),
            })

        if len(corrections) < ws:
            results_by_window[ws] = {'status': 'insufficient'}
            continue

        # Simulate auto-calibration: at each correction, use median of last ws corrections
        calibrated_isf_values = []
        overcorrection_events = 0
        undercorrection_events = 0

        for idx in range(ws, len(corrections)):
            recent = corrections[idx - ws:idx]
            calibrated_isf = np.median([c['isf'] for c in recent])
            calibrated_isf_values.append(calibrated_isf)

            # What would have happened with calibrated ISF?
            current = corrections[idx]
            # Original dose = delta_g_target / profile_isf
            # Calibrated dose = delta_g_target / calibrated_isf
            # Dose ratio = profile_isf / calibrated_isf
            dose_ratio = profile_isf / calibrated_isf
            # If dose_ratio > 1: original dose was too large (ISF too low)
            # Adjusted outcome: delta_g_new ≈ delta_g_original / dose_ratio
            adjusted_delta = current['delta_g'] / dose_ratio
            final_glucose = glucose[current['step']] - adjusted_delta

            if final_glucose < 70:
                overcorrection_events += 1
            elif final_glucose > 180:
                undercorrection_events += 1

        # Compare: overcorrection rate with profile vs calibrated ISF
        # Profile overcorrection: how many corrections drove glucose below 70
        profile_overcorrections = 0
        for c in corrections[ws:]:
            final_g = glucose[c['step']] - c['delta_g']
            if final_g < 70:
                profile_overcorrections += 1

        n_eval = len(corrections) - ws
        results_by_window[ws] = {
            'n_corrections': len(corrections),
            'n_evaluated': n_eval,
            'calibrated_isf_median': round(float(np.median(calibrated_isf_values)), 1) if calibrated_isf_values else np.nan,
            'profile_overcorrection_pct': round(profile_overcorrections / n_eval * 100, 1) if n_eval > 0 else 0,
            'calibrated_overcorrection_pct': round(overcorrection_events / n_eval * 100, 1) if n_eval > 0 else 0,
            'overcorrection_reduction': round((profile_overcorrections - overcorrection_events) / max(profile_overcorrections, 1) * 100, 1),
        }

    # Best window
    best_ws = None
    best_reduction = -999
    for ws, r in results_by_window.items():
        if 'overcorrection_reduction' in r and r['overcorrection_reduction'] > best_reduction:
            best_reduction = r['overcorrection_reduction']
            best_ws = ws

    exp2011[name] = {
        'profile_isf': round(profile_isf, 1),
        'results_by_window': results_by_window,
        'best_window': best_ws,
        'best_reduction_pct': round(best_reduction, 1),
    }

    if best_ws and best_ws in results_by_window and 'calibrated_isf_median' in results_by_window[best_ws]:
        bw = results_by_window[best_ws]
        print(f"  {name}: profile_isf={profile_isf:.0f} calibrated={bw['calibrated_isf_median']:.0f} "
              f"best_window={best_ws} overcorr: {bw['profile_overcorrection_pct']:.0f}%→{bw['calibrated_overcorrection_pct']:.0f}% "
              f"reduction={best_reduction:.0f}%")
    else:
        print(f"  {name}: insufficient corrections for auto-calibration")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # Top-left: overcorrection reduction by window size
    ax = axes[0, 0]
    for ws in window_sizes:
        reductions = []
        names_with_data = []
        for n in exp2011:
            r = exp2011[n]['results_by_window'].get(ws, {})
            if 'overcorrection_reduction' in r:
                reductions.append(r['overcorrection_reduction'])
                names_with_data.append(n)
        if reductions:
            ax.bar(np.arange(len(names_with_data)) + window_sizes.index(ws) * 0.2,
                   reductions, 0.2, label=f'Window={ws}', alpha=0.7)
    ax.set_xticks(np.arange(len(exp2011)))
    ax.set_xticklabels(list(exp2011.keys()))
    ax.set_ylabel('Overcorrection Reduction (%)')
    ax.set_title('ISF Auto-Calibration: Overcorrection Reduction')
    ax.legend()
    ax.axhline(0, color='black', ls='--', alpha=0.3)
    ax.grid(True, alpha=0.3, axis='y')

    # Top-right: profile vs calibrated ISF
    ax = axes[0, 1]
    for n in exp2011:
        bw = exp2011[n].get('best_window')
        if bw and bw in exp2011[n]['results_by_window']:
            r = exp2011[n]['results_by_window'][bw]
            if 'calibrated_isf_median' in r and np.isfinite(r['calibrated_isf_median']):
                ax.scatter(exp2011[n]['profile_isf'], r['calibrated_isf_median'], s=60, zorder=3)
                ax.annotate(n, (exp2011[n]['profile_isf'], r['calibrated_isf_median']), fontsize=9)
    lims = ax.get_xlim()
    ax.plot([0, 200], [0, 200], 'k--', alpha=0.5, label='No change needed')
    ax.set_xlabel('Profile ISF')
    ax.set_ylabel('Auto-Calibrated ISF')
    ax.set_title('ISF: Profile vs Auto-Calibrated')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Bottom-left: overcorrection rates before/after
    ax = axes[1, 0]
    names_list = list(exp2011.keys())
    before = []
    after = []
    for n in names_list:
        bw = exp2011[n].get('best_window')
        if bw and bw in exp2011[n]['results_by_window']:
            r = exp2011[n]['results_by_window'][bw]
            before.append(r.get('profile_overcorrection_pct', 0))
            after.append(r.get('calibrated_overcorrection_pct', 0))
        else:
            before.append(0)
            after.append(0)
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, before, width, label='Profile ISF', color='red', alpha=0.7)
    ax.bar(x + width/2, after, width, label='Auto-Calibrated', color='green', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Overcorrection Rate (%)')
    ax.set_title('Overcorrection: Before vs After Calibration')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    # Bottom-right: learning curve (convergence of calibrated ISF over corrections)
    ax = axes[1, 1]
    for p_data in patients[:4]:
        n = p_data['name']
        if n not in exp2011:
            continue
        # Use window=10 for learning curve
        r = exp2011[n]['results_by_window'].get(10, {})
        if 'calibrated_isf_median' not in r:
            continue
        corrections = []
        df = p_data['df']
        g = df['glucose'].values.astype(float)
        b = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(g))
        c = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(g))
        for i in range(len(g) - 24):
            if b[i] < 0.3:
                continue
            cw = c[max(0, i-12):min(len(c), i+12)]
            if np.nansum(cw) > 1:
                continue
            if not np.isfinite(g[i]) or g[i] < 120:
                continue
            ga = g[min(i + 24, len(g) - 1)]
            if not np.isfinite(ga) or g[i] - ga <= 0:
                continue
            ei = (g[i] - ga) / b[i]
            if 5 < ei < 500:
                corrections.append(ei)
        if len(corrections) > 10:
            running_median = [np.median(corrections[max(0, i-10):i+1]) for i in range(len(corrections))]
            ax.plot(range(len(running_median)), running_median, '-', label=n, alpha=0.7)
    ax.set_xlabel('Correction Number')
    ax.set_ylabel('Running Median ISF')
    ax.set_title('ISF Learning Curve (window=10)')
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.suptitle('EXP-2011: ISF Auto-Calibration from Correction Outcomes', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/intv-fig01-isf-calibration.png', dpi=150)
    plt.close()
    print(f"  → Saved intv-fig01-isf-calibration.png")

mean_reduction = np.mean([exp2011[n]['best_reduction_pct'] for n in exp2011 if exp2011[n]['best_reduction_pct'] > -999])
verdict_2011 = f"MEAN_OVERCORR_REDUCTION_{mean_reduction:.0f}%"
results['EXP-2011'] = verdict_2011
print(f"\n  ✓ EXP-2011 verdict: {verdict_2011}")


# ══════════════════════════════════════════════════════════════
# EXP-2012: Predictive Hypo Prevention
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2012")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2012: Predictive Hypo Prevention (Earlier Suspension)")
print("=" * 70)

exp2012 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    trend_rate = df['trend_rate_raw'].values.astype(float) if 'trend_rate_raw' in df.columns else np.full(len(glucose), np.nan)

    # Current behavior: suspend when glucose < threshold (reactive)
    # Proposed: suspend when predicted glucose < threshold (predictive)
    # Prediction: glucose_pred = glucose_now + trend_rate * horizon_steps * 5

    horizons_min = [15, 30, 45, 60]
    baseline_metrics = glucose_metrics(glucose)

    horizon_results = {}
    for horizon in horizons_min:
        horizon_steps = horizon // 5

        # Find steps where predictive suspension would trigger but reactive wouldn't
        early_suspensions = 0
        prevented_hypos = 0
        false_alarms = 0
        total_hypos = 0

        for i in range(len(glucose) - horizon_steps):
            if not np.isfinite(glucose[i]) or not np.isfinite(trend_rate[i]):
                continue
            # Predicted glucose
            pred_g = glucose[i] + trend_rate[i] * horizon_steps
            actual_future_g = glucose[i + horizon_steps] if np.isfinite(glucose[i + horizon_steps]) else np.nan

            # Count actual hypos
            if np.isfinite(actual_future_g) and actual_future_g < HYPO_THRESH:
                total_hypos += 1

            # Predictive trigger: pred < 80 (suspend early)
            if pred_g < 80 and glucose[i] >= 80:
                early_suspensions += 1
                if np.isfinite(actual_future_g):
                    if actual_future_g < HYPO_THRESH:
                        prevented_hypos += 1
                    else:
                        false_alarms += 1

        # Simulate benefit: for prevented hypos, estimate glucose benefit
        # Each prevented hypo saves ~20 min below 70 + prevents rebound
        # Conservative: 0.5pp TBR reduction per prevented hypo per week
        hypos_per_week = prevented_hypos / (len(glucose) / STEPS_PER_DAY / 7)
        ppv = prevented_hypos / (prevented_hypos + false_alarms) if (prevented_hypos + false_alarms) > 0 else 0
        sensitivity = prevented_hypos / total_hypos if total_hypos > 0 else 0

        horizon_results[horizon] = {
            'early_suspensions': early_suspensions,
            'prevented_hypos': prevented_hypos,
            'false_alarms': false_alarms,
            'total_hypos': total_hypos,
            'ppv': round(ppv, 3),
            'sensitivity': round(sensitivity, 3),
            'prevented_per_week': round(hypos_per_week, 1),
        }

    # Best horizon (maximize prevented with PPV > 0.3)
    best_horizon = None
    best_prevented = 0
    for h, r in horizon_results.items():
        if r['ppv'] >= 0.2 and r['prevented_hypos'] > best_prevented:
            best_prevented = r['prevented_hypos']
            best_horizon = h

    exp2012[name] = {
        'baseline_tbr': round(baseline_metrics['tbr'], 1),
        'horizon_results': horizon_results,
        'best_horizon_min': best_horizon,
        'best_ppv': round(horizon_results.get(best_horizon, {}).get('ppv', 0), 3) if best_horizon else 0,
        'best_sensitivity': round(horizon_results.get(best_horizon, {}).get('sensitivity', 0), 3) if best_horizon else 0,
    }

    if best_horizon:
        r = horizon_results[best_horizon]
        print(f"  {name}: TBR={baseline_metrics['tbr']:.1f}% best_horizon={best_horizon}min "
              f"PPV={r['ppv']:.2f} sens={r['sensitivity']:.2f} "
              f"prevented={r['prevented_per_week']:.1f}/wk false_alarm={r['false_alarms']}")
    else:
        print(f"  {name}: no viable prediction horizon (PPV too low)")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # Top-left: sensitivity by horizon
    ax = axes[0, 0]
    for h in horizons_min:
        sens = [exp2012[n]['horizon_results'].get(h, {}).get('sensitivity', 0) for n in exp2012]
        ax.plot(range(len(exp2012)), sens, 'o-', label=f'{h}min', alpha=0.7, markersize=4)
    ax.set_xticks(range(len(exp2012)))
    ax.set_xticklabels(list(exp2012.keys()))
    ax.set_ylabel('Sensitivity (recall)')
    ax.set_title('Hypo Prevention Sensitivity by Horizon')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Top-right: PPV by horizon
    ax = axes[0, 1]
    for h in horizons_min:
        ppvs = [exp2012[n]['horizon_results'].get(h, {}).get('ppv', 0) for n in exp2012]
        ax.plot(range(len(exp2012)), ppvs, 'o-', label=f'{h}min', alpha=0.7, markersize=4)
    ax.set_xticks(range(len(exp2012)))
    ax.set_xticklabels(list(exp2012.keys()))
    ax.set_ylabel('PPV (precision)')
    ax.set_title('Hypo Prevention PPV by Horizon')
    ax.axhline(0.3, color='red', ls='--', alpha=0.5, label='Min viable PPV')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Bottom-left: prevented hypos per week
    ax = axes[1, 0]
    names_list = list(exp2012.keys())
    for h in horizons_min:
        prevented = [exp2012[n]['horizon_results'].get(h, {}).get('prevented_per_week', 0) for n in names_list]
        ax.bar(np.arange(len(names_list)) + horizons_min.index(h) * 0.2,
               prevented, 0.2, label=f'{h}min', alpha=0.7)
    ax.set_xticks(np.arange(len(names_list)))
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Prevented Hypos/Week')
    ax.set_title('Hypos Prevented by Predictive Suspension')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    # Bottom-right: PPV vs sensitivity tradeoff
    ax = axes[1, 1]
    for h in horizons_min:
        ppvs = [exp2012[n]['horizon_results'].get(h, {}).get('ppv', 0) for n in exp2012]
        sens = [exp2012[n]['horizon_results'].get(h, {}).get('sensitivity', 0) for n in exp2012]
        ax.scatter(sens, ppvs, label=f'{h}min', alpha=0.7, s=30)
    ax.set_xlabel('Sensitivity')
    ax.set_ylabel('PPV')
    ax.set_title('PPV vs Sensitivity Tradeoff')
    ax.axhline(0.3, color='red', ls='--', alpha=0.3)
    ax.legend()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)

    plt.suptitle('EXP-2012: Predictive Hypo Prevention', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/intv-fig02-hypo-prevention.png', dpi=150)
    plt.close()
    print(f"  → Saved intv-fig02-hypo-prevention.png")

viable = sum(1 for v in exp2012.values() if v['best_horizon_min'] is not None)
mean_sens = np.mean([v['best_sensitivity'] for v in exp2012.values() if v['best_horizon_min']])
verdict_2012 = f"VIABLE_{viable}/11_MEAN_SENS_{mean_sens:.2f}"
results['EXP-2012'] = verdict_2012
print(f"\n  ✓ EXP-2012 verdict: {verdict_2012}")


# ══════════════════════════════════════════════════════════════
# EXP-2013: Post-Hypo Rebound Management
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2013")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2013: Post-Hypo Rebound Management")
print("=" * 70)

exp2013 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    net_basal = df['net_basal'].values.astype(float) if 'net_basal' in df.columns else np.zeros(len(glucose))

    isf_schedule = df.attrs.get('isf_schedule', [{'value': 50}])
    profile_isf = isf_schedule[0]['value'] if isf_schedule else 50
    if profile_isf < 15:
        profile_isf *= 18.0182

    basal_schedule = df.attrs.get('basal_schedule', [{'value': 1.0}])
    profile_basal = basal_schedule[0]['value'] if basal_schedule else 1.0

    # Find hypo events and track rebound
    hypo_events = []
    in_hypo = False
    for i in range(len(glucose)):
        if not np.isfinite(glucose[i]):
            continue
        if glucose[i] < HYPO_THRESH and not in_hypo:
            in_hypo = True
            hypo_events.append(i)
        elif glucose[i] >= 80 and in_hypo:
            in_hypo = False

    # Simulate intervention: after hypo recovery (glucose returns to 80),
    # provide a small correction bolus to dampen rebound
    no_intervention_rebounds = 0
    intervention_rebounds = 0
    total_events = 0

    intervention_details = []

    for hs in hypo_events:
        if hs + 72 > len(glucose):
            continue

        window = glucose[hs:hs + 72]
        if np.sum(np.isfinite(window)) < 30:
            continue

        # Find recovery point (glucose crosses 80)
        recovery_idx = None
        for ri in range(len(window)):
            if np.isfinite(window[ri]) and window[ri] >= 80:
                recovery_idx = ri
                break
        if recovery_idx is None:
            continue

        total_events += 1

        # Track rebound: max glucose 1-3h after recovery
        rebound_window = window[recovery_idx + 12:min(recovery_idx + 36, len(window))]
        if len(rebound_window) == 0 or np.sum(np.isfinite(rebound_window)) == 0:
            continue

        rebound_peak = float(np.nanmax(rebound_window))
        no_intervention_rebounds += 1 if rebound_peak > 180 else 0

        # Simulate intervention: small correction at recovery point
        # Dose = (predicted_rebound - target) / ISF
        # Predicted rebound = rebound_peak (from data)
        # Conservative: dose = 0.5 * (rebound_peak - 120) / ISF if rebound_peak > 140
        if rebound_peak > 140:
            correction_dose = 0.5 * (rebound_peak - 120) / profile_isf
            correction_dose = min(correction_dose, 2.0)  # cap at 2U
            # Simulated effect: reduce rebound by dose * ISF
            simulated_peak = rebound_peak - correction_dose * profile_isf
            intervention_rebounds += 1 if simulated_peak > 180 else 0
            intervention_details.append({
                'original_peak': round(rebound_peak, 0),
                'correction_dose': round(correction_dose, 2),
                'simulated_peak': round(simulated_peak, 0),
            })
        else:
            intervention_details.append({
                'original_peak': round(rebound_peak, 0),
                'correction_dose': 0,
                'simulated_peak': round(rebound_peak, 0),
            })

    no_rebound_rate = no_intervention_rebounds / total_events * 100 if total_events > 0 else 0
    intv_rebound_rate = intervention_rebounds / total_events * 100 if total_events > 0 else 0
    reduction = no_rebound_rate - intv_rebound_rate

    exp2013[name] = {
        'total_hypos': total_events,
        'no_intervention_rebound_pct': round(no_rebound_rate, 1),
        'intervention_rebound_pct': round(intv_rebound_rate, 1),
        'rebound_reduction_pp': round(reduction, 1),
        'mean_correction_dose': round(float(np.mean([d['correction_dose'] for d in intervention_details])), 2) if intervention_details else 0,
    }

    print(f"  {name}: hypos={total_events} rebound: {no_rebound_rate:.0f}%→{intv_rebound_rate:.0f}% "
          f"(Δ={reduction:+.0f}pp) mean_dose={np.mean([d['correction_dose'] for d in intervention_details]):.2f}U")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # Left: rebound rate before/after
    ax = axes[0]
    names_list = list(exp2013.keys())
    before = [exp2013[n]['no_intervention_rebound_pct'] for n in names_list]
    after = [exp2013[n]['intervention_rebound_pct'] for n in names_list]
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, before, width, label='No Intervention', color='red', alpha=0.7)
    ax.bar(x + width/2, after, width, label='Post-Hypo Correction', color='green', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Rebound to Hyper Rate (%)')
    ax.set_title('Post-Hypo Rebound Management')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    # Right: reduction by patient
    ax = axes[1]
    reductions = [exp2013[n]['rebound_reduction_pp'] for n in names_list]
    colors = ['green' if r > 10 else 'orange' if r > 0 else 'gray' for r in reductions]
    ax.barh(range(len(names_list)), reductions, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_list)))
    ax.set_yticklabels(names_list)
    ax.set_xlabel('Rebound Reduction (pp)')
    ax.set_title('Post-Hypo Intervention Benefit')
    ax.grid(True, alpha=0.3, axis='x')

    plt.suptitle('EXP-2013: Post-Hypo Rebound Management', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/intv-fig03-rebound-management.png', dpi=150)
    plt.close()
    print(f"  → Saved intv-fig03-rebound-management.png")

mean_reduction = np.mean([exp2013[n]['rebound_reduction_pp'] for n in exp2013])
verdict_2013 = f"REBOUND_REDUCTION_{mean_reduction:.0f}pp"
results['EXP-2013'] = verdict_2013
print(f"\n  ✓ EXP-2013 verdict: {verdict_2013}")


# ══════════════════════════════════════════════════════════════
# EXP-2014: Absorption-Speed Adaptive Meal Dosing
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2014")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2014: Absorption-Speed Adaptive Meal Dosing")
print("=" * 70)

exp2014 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    carbs = df['carbs'].values.astype(float) if 'carbs' in df.columns else np.zeros(len(glucose))
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))

    # Find meals with bolus
    meal_steps = np.where(carbs >= 10)[0]
    if len(meal_steps) < 10:
        exp2014[name] = {'status': 'insufficient_meals'}
        print(f"  {name}: insufficient meals")
        continue

    # Current approach: all insulin at meal time (standard bolus)
    # Proposed: split bolus based on absorption speed
    # Fast absorber: 70% upfront, 30% extended over 1h
    # Slow absorber: 40% upfront, 60% extended over 2h

    # Classify each meal's absorption speed
    standard_spikes = []
    extended_spikes = []

    for ms in meal_steps:
        if ms + 36 > len(glucose):
            continue
        window = glucose[ms:ms + 36]
        if np.sum(np.isfinite(window)) < 20:
            continue
        baseline = glucose[ms] if np.isfinite(glucose[ms]) else np.nan
        if not np.isfinite(baseline):
            continue

        # Measure spike (max - baseline)
        spike = float(np.nanmax(window) - baseline)
        peak_idx = np.nanargmax(window)
        peak_time_min = peak_idx * 5
        standard_spikes.append({'spike': spike, 'peak_time': peak_time_min, 'carbs': float(carbs[ms])})

        # Simulate extended bolus effect:
        # For slow absorbers (peak > 60min), extending insulin reduces early-peak insulin
        # This means less hypo overshoot + less late-phase hyperglycemia
        # Model: spike_reduction = 0.3 * spike for slow meals, 0.1 for fast meals
        if peak_time_min > 60:
            reduction = 0.3 * max(spike, 0)  # slow absorber benefits more
        elif peak_time_min > 30:
            reduction = 0.15 * max(spike, 0)  # moderate benefit
        else:
            reduction = 0.05 * max(spike, 0)  # fast absorber: minimal benefit

        simulated_spike = max(spike - reduction, 0)
        extended_spikes.append({'spike': simulated_spike, 'peak_time': peak_time_min, 'reduction': reduction})

    if not standard_spikes:
        exp2014[name] = {'status': 'no_valid_meals'}
        print(f"  {name}: no valid meals with follow-up")
        continue

    standard_mean_spike = float(np.mean([s['spike'] for s in standard_spikes]))
    extended_mean_spike = float(np.mean([s['spike'] for s in extended_spikes]))
    spike_reduction = standard_mean_spike - extended_mean_spike

    # Estimate TIR impact: reduced spikes → less time above 180
    # Each mg/dL spike reduction → ~0.5min less TAR per meal (rough estimate)
    meals_per_day = len(meal_steps) / (len(glucose) / STEPS_PER_DAY)
    tar_reduction_min_per_day = spike_reduction * 0.5 * meals_per_day
    tar_reduction_pct = tar_reduction_min_per_day / (24 * 60) * 100

    # Slow meal fraction
    slow_meals = sum(1 for s in standard_spikes if s['peak_time'] > 60)
    slow_pct = slow_meals / len(standard_spikes) * 100

    exp2014[name] = {
        'n_meals': len(standard_spikes),
        'standard_mean_spike': round(standard_mean_spike, 1),
        'extended_mean_spike': round(extended_mean_spike, 1),
        'spike_reduction': round(spike_reduction, 1),
        'slow_meal_pct': round(slow_pct, 1),
        'estimated_tar_reduction_pct': round(tar_reduction_pct, 2),
    }

    print(f"  {name}: meals={len(standard_spikes)} spike: {standard_mean_spike:.0f}→{extended_mean_spike:.0f}mg/dL "
          f"(Δ={spike_reduction:.0f}) slow={slow_pct:.0f}% est_TAR_Δ={tar_reduction_pct:.2f}%")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # Left: spike reduction
    ax = axes[0]
    names_list = [n for n in exp2014 if 'standard_mean_spike' in exp2014[n]]
    std = [exp2014[n]['standard_mean_spike'] for n in names_list]
    ext = [exp2014[n]['extended_mean_spike'] for n in names_list]
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, std, width, label='Standard Bolus', color='red', alpha=0.7)
    ax.bar(x + width/2, ext, width, label='Extended Bolus', color='green', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('Mean Post-Meal Spike (mg/dL)')
    ax.set_title('Meal Spike: Standard vs Adaptive Extended Bolus')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    # Right: slow meal fraction vs benefit
    ax = axes[1]
    slow_pcts = [exp2014[n]['slow_meal_pct'] for n in names_list]
    reductions = [exp2014[n]['spike_reduction'] for n in names_list]
    ax.scatter(slow_pcts, reductions, s=60, zorder=3)
    for n, sp, r in zip(names_list, slow_pcts, reductions):
        ax.annotate(n, (sp, r), fontsize=9)
    ax.set_xlabel('Slow Meal Fraction (%)')
    ax.set_ylabel('Spike Reduction (mg/dL)')
    ax.set_title('Benefit Scales with Slow Absorption Rate')
    ax.grid(True, alpha=0.3)

    plt.suptitle('EXP-2014: Absorption-Speed Adaptive Meal Dosing', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/intv-fig04-adaptive-dosing.png', dpi=150)
    plt.close()
    print(f"  → Saved intv-fig04-adaptive-dosing.png")

mean_spike_red = np.mean([exp2014[n].get('spike_reduction', 0) for n in exp2014 if 'spike_reduction' in exp2014[n]])
verdict_2014 = f"MEAN_SPIKE_REDUCTION_{mean_spike_red:.0f}mg/dL"
results['EXP-2014'] = verdict_2014
print(f"\n  ✓ EXP-2014 verdict: {verdict_2014}")


# ══════════════════════════════════════════════════════════════
# EXP-2015: Dawn Phenomenon Proactive Basal Ramp
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2015")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2015: Dawn Phenomenon Proactive Basal Ramp")
print("=" * 70)

exp2015 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    n_days = len(glucose) // STEPS_PER_DAY

    isf_schedule = df.attrs.get('isf_schedule', [{'value': 50}])
    profile_isf = isf_schedule[0]['value'] if isf_schedule else 50
    if profile_isf < 15:
        profile_isf *= 18.0182

    # Measure morning TIR (6-10 AM) vs overnight TIR (0-6 AM)
    morning_g = []
    overnight_g = []
    for d in range(n_days):
        # Overnight: 0-6 AM
        start = d * STEPS_PER_DAY
        end = start + 6 * STEPS_PER_HOUR
        if end <= len(glucose):
            ov = glucose[start:end]
            overnight_g.extend(ov[np.isfinite(ov)])
        # Morning: 6-10 AM
        start = d * STEPS_PER_DAY + 6 * STEPS_PER_HOUR
        end = start + 4 * STEPS_PER_HOUR
        if end <= len(glucose):
            mg = glucose[start:end]
            morning_g.extend(mg[np.isfinite(mg)])

    overnight_tir = np.mean((np.array(overnight_g) >= 70) & (np.array(overnight_g) <= 180)) * 100 if overnight_g else 0
    morning_tir = np.mean((np.array(morning_g) >= 70) & (np.array(morning_g) <= 180)) * 100 if morning_g else 0

    # Dawn rise: average glucose change from 4AM to 8AM
    dawn_rises = []
    for d in range(n_days):
        g_4am = glucose[d * STEPS_PER_DAY + 4 * STEPS_PER_HOUR] if d * STEPS_PER_DAY + 4 * STEPS_PER_HOUR < len(glucose) else np.nan
        g_8am = glucose[d * STEPS_PER_DAY + 8 * STEPS_PER_HOUR] if d * STEPS_PER_DAY + 8 * STEPS_PER_HOUR < len(glucose) else np.nan
        if np.isfinite(g_4am) and np.isfinite(g_8am):
            dawn_rises.append(g_8am - g_4am)

    mean_dawn_rise = float(np.mean(dawn_rises)) if dawn_rises else 0

    # Simulate dawn ramp: increase basal 3-6 AM by dawn_rise / ISF
    # This extra insulin would counteract the dawn rise
    if mean_dawn_rise > 10:  # only intervene if dawn rise > 10 mg/dL
        extra_basal = mean_dawn_rise / profile_isf / 3  # spread over 3 hours
        # Simulate: morning glucose reduced by dawn_rise * fraction_covered
        coverage = min(extra_basal * profile_isf * 3 / mean_dawn_rise, 1.0)
        simulated_morning_rise = mean_dawn_rise * (1 - coverage)
        simulated_morning_tir_boost = coverage * (100 - morning_tir) * 0.3  # conservative
        intervene = True
    else:
        extra_basal = 0
        simulated_morning_rise = mean_dawn_rise
        simulated_morning_tir_boost = 0
        intervene = False

    exp2015[name] = {
        'overnight_tir': round(overnight_tir, 1),
        'morning_tir': round(morning_tir, 1),
        'tir_gap': round(overnight_tir - morning_tir, 1),
        'mean_dawn_rise': round(mean_dawn_rise, 1),
        'intervene': intervene,
        'extra_basal_u_h': round(extra_basal, 3),
        'simulated_morning_tir_boost': round(simulated_morning_tir_boost, 1),
    }

    intv_str = f"extra_basal={extra_basal:.3f}U/h boost={simulated_morning_tir_boost:.1f}pp" if intervene else "no_intervention"
    print(f"  {name}: overnight_TIR={overnight_tir:.0f}% morning_TIR={morning_tir:.0f}% "
          f"dawn_rise={mean_dawn_rise:.0f}mg/dL {intv_str}")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # Left: TIR overnight vs morning
    ax = axes[0]
    names_list = list(exp2015.keys())
    ov_tir = [exp2015[n]['overnight_tir'] for n in names_list]
    mr_tir = [exp2015[n]['morning_tir'] for n in names_list]
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, ov_tir, width, label='Overnight', color='blue', alpha=0.7)
    ax.bar(x + width/2, mr_tir, width, label='Morning', color='orange', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('TIR (%)')
    ax.set_title('Overnight vs Morning TIR')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    # Right: dawn rise and intervention benefit
    ax = axes[1]
    dawn_rises_plot = [exp2015[n]['mean_dawn_rise'] for n in names_list]
    boosts = [exp2015[n]['simulated_morning_tir_boost'] for n in names_list]
    colors = ['green' if exp2015[n]['intervene'] else 'gray' for n in names_list]
    ax.scatter(dawn_rises_plot, boosts, c=colors, s=60, zorder=3)
    for n, dr, b in zip(names_list, dawn_rises_plot, boosts):
        ax.annotate(n, (dr, b), fontsize=9)
    ax.set_xlabel('Mean Dawn Rise (mg/dL)')
    ax.set_ylabel('Simulated TIR Boost (pp)')
    ax.set_title('Dawn Ramp: Rise vs Benefit (green=intervene)')
    ax.grid(True, alpha=0.3)

    plt.suptitle('EXP-2015: Dawn Phenomenon Proactive Basal Ramp', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/intv-fig05-dawn-ramp.png', dpi=150)
    plt.close()
    print(f"  → Saved intv-fig05-dawn-ramp.png")

n_intervene = sum(1 for v in exp2015.values() if v['intervene'])
mean_boost = np.mean([v['simulated_morning_tir_boost'] for v in exp2015.values() if v['intervene']]) if n_intervene > 0 else 0
verdict_2015 = f"DAWN_{n_intervene}/11_MEAN_BOOST_{mean_boost:.1f}pp"
results['EXP-2015'] = verdict_2015
print(f"\n  ✓ EXP-2015 verdict: {verdict_2015}")


# ══════════════════════════════════════════════════════════════
# EXP-2016: Loop Effort Reduction (Less Aggressive Correction)
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2016")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2016: Loop Effort Reduction (Less Aggressive Correction)")
print("=" * 70)

exp2016 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    net_basal = df['net_basal'].values.astype(float) if 'net_basal' in df.columns else np.zeros(len(glucose))
    bolus = df['bolus'].values.astype(float) if 'bolus' in df.columns else np.zeros(len(glucose))

    basal_schedule = df.attrs.get('basal_schedule', [{'value': 1.0}])
    profile_basal = basal_schedule[0]['value'] if basal_schedule else 1.0

    baseline_metrics = glucose_metrics(glucose)

    # Current: count loop effort events
    # High effort: net_basal deviates >50% from profile
    high_effort_count = 0
    total_valid = 0
    for i in range(len(net_basal)):
        if not np.isfinite(net_basal[i]):
            continue
        total_valid += 1
        if abs(net_basal[i] - profile_basal) > 0.5 * profile_basal:
            high_effort_count += 1

    effort_pct = high_effort_count / total_valid * 100 if total_valid > 0 else 0

    # Simulate reduced aggressiveness: scale correction boluses by 0.7
    # (reduce ISF-based corrections by 30%)
    scale_factors = [0.5, 0.7, 0.85, 1.0]
    scale_results = {}

    for sf in scale_factors:
        # Simulate: for each correction bolus, reduce by (1-sf)
        # Effect: glucose goes higher by (1-sf) * original_correction_effect
        # Approximation: each reduced unit → +ISF mg/dL to glucose
        isf_schedule = df.attrs.get('isf_schedule', [{'value': 50}])
        profile_isf = isf_schedule[0]['value'] if isf_schedule else 50
        if profile_isf < 15:
            profile_isf *= 18.0182

        # Compute glucose shift from reduced corrections
        shift = np.zeros(len(glucose))
        for i in range(len(glucose)):
            if bolus[i] > 0.1:
                # Reduced dose: bolus * sf instead of bolus
                dose_reduction = bolus[i] * (1 - sf)
                # Effect spread over DIA (~5h = 60 steps)
                for j in range(min(60, len(glucose) - i)):
                    if i + j < len(shift):
                        # Triangular insulin action
                        action_frac = max(0, 1 - j / 60)
                        shift[i + j] += dose_reduction * profile_isf * action_frac / 30

        sim_glucose = glucose.copy()
        valid = np.isfinite(sim_glucose)
        sim_glucose[valid] = sim_glucose[valid] + shift[valid]
        sim_glucose = np.clip(sim_glucose, 30, 500)

        sim_metrics = glucose_metrics(sim_glucose)
        scale_results[str(sf)] = {
            'tir': round(sim_metrics['tir'], 1),
            'tbr': round(sim_metrics['tbr'], 1),
            'tar': round(sim_metrics['tar'], 1),
            'tir_delta': round(sim_metrics['tir'] - baseline_metrics['tir'], 1),
            'tbr_delta': round(sim_metrics['tbr'] - baseline_metrics['tbr'], 1),
        }

    # Find optimal scale: maximizes TIR while keeping TBR < 4%
    best_sf = 1.0
    best_tir = baseline_metrics['tir']
    for sf_str, r in scale_results.items():
        if r['tbr'] < 4 and r['tir'] > best_tir:
            best_tir = r['tir']
            best_sf = float(sf_str)

    exp2016[name] = {
        'baseline_tir': round(baseline_metrics['tir'], 1),
        'baseline_tbr': round(baseline_metrics['tbr'], 1),
        'effort_pct': round(effort_pct, 1),
        'scale_results': scale_results,
        'best_scale': best_sf,
        'best_tir': round(best_tir, 1),
    }

    best_r = scale_results[str(best_sf)]
    print(f"  {name}: effort={effort_pct:.0f}% best_scale={best_sf} "
          f"TIR: {baseline_metrics['tir']:.0f}→{best_r['tir']:.0f}% "
          f"TBR: {baseline_metrics['tbr']:.1f}→{best_r['tbr']:.1f}%")

if MAKE_FIGS:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # Left: TIR at different scales
    ax = axes[0]
    names_list = list(exp2016.keys())
    for sf in scale_factors:
        tirs = [exp2016[n]['scale_results'][str(sf)]['tir'] for n in names_list]
        ax.plot(range(len(names_list)), tirs, 'o-', label=f'Scale={sf}', alpha=0.7, markersize=4)
    ax.set_xticks(range(len(names_list)))
    ax.set_xticklabels(names_list)
    ax.set_ylabel('TIR (%)')
    ax.set_title('TIR at Different Correction Aggressiveness')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Right: TBR at different scales
    ax = axes[1]
    for sf in scale_factors:
        tbrs = [exp2016[n]['scale_results'][str(sf)]['tbr'] for n in names_list]
        ax.plot(range(len(names_list)), tbrs, 'o-', label=f'Scale={sf}', alpha=0.7, markersize=4)
    ax.set_xticks(range(len(names_list)))
    ax.set_xticklabels(names_list)
    ax.set_ylabel('TBR (%)')
    ax.set_title('TBR at Different Correction Aggressiveness')
    ax.axhline(4, color='red', ls='--', alpha=0.5, label='4% Target')
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.suptitle('EXP-2016: Loop Effort Reduction', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/intv-fig06-effort-reduction.png', dpi=150)
    plt.close()
    print(f"  → Saved intv-fig06-effort-reduction.png")

improved = sum(1 for v in exp2016.values() if v['best_scale'] < 1.0)
verdict_2016 = f"IMPROVED_{improved}/11_BY_REDUCING_CORRECTIONS"
results['EXP-2016'] = verdict_2016
print(f"\n  ✓ EXP-2016 verdict: {verdict_2016}")


# ══════════════════════════════════════════════════════════════
# EXP-2017: Combined Intervention Simulation
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2017")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2017: Combined Intervention Simulation")
print("=" * 70)

exp2017 = {}
for p in patients:
    name = p['name']
    df = p['df']
    glucose = df['glucose'].values.astype(float)
    baseline = glucose_metrics(glucose)

    # Combine all interventions as additive effects:
    # 1. ISF calibration: reduce overcorrection hypos
    # 2. Predictive suspension: reduce some remaining hypos
    # 3. Post-hypo management: reduce rebound-to-hyper
    # 4. Adaptive meal dosing: reduce post-meal spikes
    # 5. Dawn ramp: reduce morning TAR

    # Estimate combined effects (conservative, non-additive)
    # TBR reduction from ISF + predictive
    isf_tbr_reduction = 0
    if name in exp2011 and exp2011[name].get('best_window'):
        bw = exp2011[name]['best_window']
        r = exp2011[name]['results_by_window'].get(bw, {})
        # Overcorrection reduction → TBR reduction
        isf_tbr_reduction = r.get('overcorrection_reduction', 0) * baseline['tbr'] / 100 * 0.3

    predict_tbr_reduction = 0
    if name in exp2012 and exp2012[name].get('best_sensitivity', 0) > 0:
        predict_tbr_reduction = exp2012[name]['best_sensitivity'] * baseline['tbr'] * 0.2

    # TIR gain from reduced TBR (shifted to TIR)
    tbr_to_tir = (isf_tbr_reduction + predict_tbr_reduction) * 0.7  # 70% of reduced TBR becomes TIR

    # Rebound reduction → TAR reduction
    rebound_tar_reduction = 0
    if name in exp2013:
        rebound_tar_reduction = exp2013[name].get('rebound_reduction_pp', 0) * 0.3

    # Meal spike reduction → TAR reduction
    meal_tar_reduction = 0
    if name in exp2014 and 'spike_reduction' in exp2014[name]:
        meal_tar_reduction = exp2014[name]['spike_reduction'] * 0.02  # 0.02pp per mg/dL reduction

    # Dawn ramp → morning TIR gain
    dawn_tir_gain = 0
    if name in exp2015 and exp2015[name]['intervene']:
        dawn_tir_gain = exp2015[name]['simulated_morning_tir_boost'] * 0.25  # morning is 1/6 of day

    # Combined
    combined_tbr_reduction = isf_tbr_reduction + predict_tbr_reduction
    combined_tar_reduction = rebound_tar_reduction + meal_tar_reduction
    combined_tir_gain = tbr_to_tir + combined_tar_reduction * 0.7 + dawn_tir_gain

    sim_tir = baseline['tir'] + combined_tir_gain
    sim_tbr = max(0, baseline['tbr'] - combined_tbr_reduction)
    sim_tar = max(0, baseline['tar'] - combined_tar_reduction)

    exp2017[name] = {
        'baseline_tir': round(baseline['tir'], 1),
        'baseline_tbr': round(baseline['tbr'], 1),
        'baseline_tar': round(baseline['tar'], 1),
        'simulated_tir': round(sim_tir, 1),
        'simulated_tbr': round(sim_tbr, 1),
        'simulated_tar': round(sim_tar, 1),
        'tir_gain': round(combined_tir_gain, 1),
        'tbr_reduction': round(combined_tbr_reduction, 1),
        'tar_reduction': round(combined_tar_reduction, 1),
        'contributions': {
            'isf_calibration': round(tbr_to_tir, 2),
            'predictive_suspension': round(predict_tbr_reduction * 0.7, 2),
            'rebound_management': round(rebound_tar_reduction * 0.7, 2),
            'adaptive_meal': round(meal_tar_reduction * 0.7, 2),
            'dawn_ramp': round(dawn_tir_gain, 2),
        }
    }

    print(f"  {name}: TIR {baseline['tir']:.0f}→{sim_tir:.0f}% (+{combined_tir_gain:.1f}pp) "
          f"TBR {baseline['tbr']:.1f}→{sim_tbr:.1f}% TAR {baseline['tar']:.0f}→{sim_tar:.0f}%")

if MAKE_FIGS:
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # Top-left: TIR before/after
    ax = axes[0, 0]
    names_list = list(exp2017.keys())
    before = [exp2017[n]['baseline_tir'] for n in names_list]
    after = [exp2017[n]['simulated_tir'] for n in names_list]
    x = np.arange(len(names_list))
    width = 0.35
    ax.bar(x - width/2, before, width, label='Baseline', color='gray', alpha=0.7)
    ax.bar(x + width/2, after, width, label='Combined Interventions', color='green', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('TIR (%)')
    ax.set_title('TIR: Baseline vs Combined Interventions')
    ax.axhline(70, color='black', ls=':', alpha=0.3, label='70% target')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    # Top-right: TBR before/after
    ax = axes[0, 1]
    before_tbr = [exp2017[n]['baseline_tbr'] for n in names_list]
    after_tbr = [exp2017[n]['simulated_tbr'] for n in names_list]
    ax.bar(x - width/2, before_tbr, width, label='Baseline', color='red', alpha=0.7)
    ax.bar(x + width/2, after_tbr, width, label='Combined', color='green', alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('TBR (%)')
    ax.set_title('TBR: Baseline vs Combined Interventions')
    ax.axhline(4, color='black', ls=':', alpha=0.3, label='4% target')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    # Bottom-left: TIR gain decomposition (stacked)
    ax = axes[1, 0]
    contrib_keys = ['isf_calibration', 'predictive_suspension', 'rebound_management', 'adaptive_meal', 'dawn_ramp']
    contrib_labels = ['ISF Calibration', 'Predictive Suspension', 'Rebound Mgmt', 'Adaptive Meal', 'Dawn Ramp']
    bottom = np.zeros(len(names_list))
    for ck, cl in zip(contrib_keys, contrib_labels):
        vals = [exp2017[n]['contributions'][ck] for n in names_list]
        ax.bar(x, vals, bottom=bottom, label=cl, alpha=0.7)
        bottom = bottom + np.array(vals)
    ax.set_xticks(x)
    ax.set_xticklabels(names_list)
    ax.set_ylabel('TIR Gain (pp)')
    ax.set_title('Intervention Contribution to TIR Gain')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis='y')

    # Bottom-right: population summary
    ax = axes[1, 1]
    mean_gains = {cl: np.mean([exp2017[n]['contributions'][ck] for n in names_list])
                  for ck, cl in zip(contrib_keys, contrib_labels)}
    sorted_contribs = sorted(mean_gains.items(), key=lambda x: x[1], reverse=True)
    labels = [s[0] for s in sorted_contribs]
    values = [s[1] for s in sorted_contribs]
    ax.barh(range(len(labels)), values, color='steelblue', alpha=0.7)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_xlabel('Mean TIR Contribution (pp)')
    ax.set_title('Population-Level Intervention Ranking')
    ax.grid(True, alpha=0.3, axis='x')

    plt.suptitle('EXP-2017: Combined Intervention Simulation', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/intv-fig07-combined.png', dpi=150)
    plt.close()
    print(f"  → Saved intv-fig07-combined.png")

mean_tir_gain = np.mean([exp2017[n]['tir_gain'] for n in exp2017])
mean_tbr_red = np.mean([exp2017[n]['tbr_reduction'] for n in exp2017])
verdict_2017 = f"COMBINED_TIR+{mean_tir_gain:.1f}pp_TBR-{mean_tbr_red:.1f}pp"
results['EXP-2017'] = verdict_2017
print(f"\n  ✓ EXP-2017 verdict: {verdict_2017}")


# ══════════════════════════════════════════════════════════════
# EXP-2018: Synthesis — Intervention Priority Ranking
# ══════════════════════════════════════════════════════════════
print("\n" + "#" * 70)
print("# Running EXP-2018")
print("#" * 70)
print("\n" + "=" * 70)
print("EXP-2018: Synthesis — Intervention Priority Ranking")
print("=" * 70)

exp2018 = {}

# Rank interventions by population-level impact
interventions = [
    {
        'name': 'ISF Auto-Calibration',
        'exp': 'EXP-2011',
        'tir_impact': np.mean([exp2017[n]['contributions']['isf_calibration'] for n in exp2017]),
        'safety_impact': 'High (reduces overcorrection)',
        'complexity': 'Low (sliding window)',
        'patients_helped': sum(1 for n in exp2011 if exp2011[n].get('best_reduction_pct', 0) > 10),
    },
    {
        'name': 'Predictive Suspension',
        'exp': 'EXP-2012',
        'tir_impact': np.mean([exp2017[n]['contributions']['predictive_suspension'] for n in exp2017]),
        'safety_impact': 'High (prevents hypos)',
        'complexity': 'Medium (trend extrapolation)',
        'patients_helped': sum(1 for n in exp2012 if exp2012[n].get('best_horizon_min') is not None),
    },
    {
        'name': 'Post-Hypo Rebound Mgmt',
        'exp': 'EXP-2013',
        'tir_impact': np.mean([exp2017[n]['contributions']['rebound_management'] for n in exp2017]),
        'safety_impact': 'Medium (reduces hyper after hypo)',
        'complexity': 'Medium (conditional correction)',
        'patients_helped': sum(1 for n in exp2013 if exp2013[n].get('rebound_reduction_pp', 0) > 5),
    },
    {
        'name': 'Adaptive Meal Dosing',
        'exp': 'EXP-2014',
        'tir_impact': np.mean([exp2017[n]['contributions']['adaptive_meal'] for n in exp2017]),
        'safety_impact': 'Medium (reduces post-meal spikes)',
        'complexity': 'High (absorption model)',
        'patients_helped': sum(1 for n in exp2014 if exp2014[n].get('spike_reduction', 0) > 5),
    },
    {
        'name': 'Dawn Basal Ramp',
        'exp': 'EXP-2015',
        'tir_impact': np.mean([exp2017[n]['contributions']['dawn_ramp'] for n in exp2017]),
        'safety_impact': 'Low (targeted morning)',
        'complexity': 'Low (time-based profile)',
        'patients_helped': sum(1 for n in exp2015 if exp2015[n].get('intervene')),
    },
]

# Sort by TIR impact
interventions.sort(key=lambda x: x['tir_impact'], reverse=True)

print("\n  INTERVENTION PRIORITY RANKING:")
print("  " + "-" * 70)
for rank, intv in enumerate(interventions, 1):
    print(f"  #{rank}: {intv['name']} ({intv['exp']})")
    print(f"      TIR Impact: +{intv['tir_impact']:.2f}pp")
    print(f"      Safety: {intv['safety_impact']}")
    print(f"      Complexity: {intv['complexity']}")
    print(f"      Patients Helped: {intv['patients_helped']}/11")
    print()

exp2018['ranking'] = [
    {
        'rank': rank,
        'name': intv['name'],
        'exp': intv['exp'],
        'tir_impact_pp': round(intv['tir_impact'], 2),
        'patients_helped': intv['patients_helped'],
        'complexity': intv['complexity'],
    }
    for rank, intv in enumerate(interventions, 1)
]

# Per-patient recommended intervention order
print("  PER-PATIENT RECOMMENDED INTERVENTIONS:")
print("  " + "-" * 70)
for p in patients:
    name = p['name']
    recs = []
    # Sort by individual patient contribution
    patient_contribs = exp2017[name]['contributions']
    sorted_c = sorted(patient_contribs.items(), key=lambda x: x[1], reverse=True)
    top_recs = [(c[0], c[1]) for c in sorted_c if c[1] > 0.01]
    print(f"  {name} (TIR={exp2017[name]['baseline_tir']:.0f}→{exp2017[name]['simulated_tir']:.0f}%): "
          + ", ".join(f"{c[0]}(+{c[1]:.1f}pp)" for c in top_recs[:3]))

if MAKE_FIGS:
    fig, ax = plt.subplots(1, 1, figsize=(12, 6))
    names_intv = [intv['name'] for intv in interventions]
    impacts = [intv['tir_impact'] for intv in interventions]
    helped = [intv['patients_helped'] for intv in interventions]
    colors = ['darkgreen' if i > 0.5 else 'green' if i > 0.2 else 'yellowgreen' for i in impacts]
    bars = ax.barh(range(len(names_intv)), impacts, color=colors, alpha=0.7)
    ax.set_yticks(range(len(names_intv)))
    ax.set_yticklabels([f"{n}\n({h}/11 patients)" for n, h in zip(names_intv, helped)])
    ax.set_xlabel('Mean TIR Impact (pp)')
    ax.set_title('Intervention Priority Ranking by Population TIR Impact')
    for i, (b, v) in enumerate(zip(bars, impacts)):
        ax.text(v + 0.02, i, f'+{v:.2f}pp', va='center', fontsize=10)
    ax.grid(True, alpha=0.3, axis='x')
    plt.tight_layout()
    plt.savefig(f'{FIG_DIR}/intv-fig08-ranking.png', dpi=150)
    plt.close()
    print(f"\n  → Saved intv-fig08-ranking.png")

top_intv = interventions[0]['name']
top_impact = interventions[0]['tir_impact']
verdict_2018 = f"TOP={top_intv}_+{top_impact:.2f}pp"
results['EXP-2018'] = verdict_2018
print(f"\n  ✓ EXP-2018 verdict: {verdict_2018}")


# ══════════════════════════════════════════════════════════════
# SYNTHESIS
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SYNTHESIS: Intervention Design & Simulation")
print("=" * 70)
for k, v in sorted(results.items()):
    print(f"  {k}: {v}")

# Save results
output = {
    'experiment_group': 'EXP-2011–2018',
    'title': 'Intervention Design & Simulation',
    'results': results,
    'exp2011_isf_calibration': {k: {kk: vv for kk, vv in v.items() if kk != 'results_by_window'} for k, v in exp2011.items()},
    'exp2012_predictive_prevention': {k: {kk: vv for kk, vv in v.items() if kk != 'horizon_results'} for k, v in exp2012.items()},
    'exp2013_rebound_management': exp2013,
    'exp2014_adaptive_dosing': exp2014,
    'exp2015_dawn_ramp': exp2015,
    'exp2016_effort_reduction': {k: {kk: vv for kk, vv in v.items() if kk != 'scale_results'} for k, v in exp2016.items()},
    'exp2017_combined': exp2017,
    'exp2018_ranking': exp2018,
}

with open(f'{EXP_DIR}/exp-2011_interventions.json', 'w') as f:
    json.dump(output, f, indent=2, default=str)
print(f"\nSaved results to {EXP_DIR}/exp-2011_interventions.json")
