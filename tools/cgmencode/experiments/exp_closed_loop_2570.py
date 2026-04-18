#!/usr/bin/env python3
"""
EXP-2570: Closed-Loop Digital Twin — Add AID Loop Model to Forward Sim

HYPOTHESIS: Adding a simplified AID loop controller to the forward
simulator will:
  H1: Improve absolute TIR prediction (MAE < 0.2 vs actual, down from 0.409)
  H2: Improve patient ranking (Spearman r > 0.5 vs actual TIR)
  H3: Produce glucose dynamics closer to real CGM traces (r > 0.5 for meals)

The open-loop forward sim (EXP-2569) has MAE=0.409 vs actual TIR because
it doesn't model the AID loop's real-time basal adjustments and SMBs.

DESIGN:
  Simplified AID loop (inspired by oref0/Loop):
    - Every 5 min: check glucose and predicted glucose (15 min extrapolation)
    - If glucose > 160 and rising: deliver micro-bolus (SMB)
    - If glucose < 100 or predicted < 80: suspend basal (temp 0)
    - If glucose < 70: suspend + model liver glucose release
    - SMB size proportional to (glucose - target) / ISF, capped
    - IOB safety limit: no SMB if IOB > max_iob

  Compare closed-loop vs open-loop sim across NS patients (a-k).
  Use 50 meal windows per patient, 4-hour simulation.

RESULT: NOT SUPPORTED — Closed-loop controller barely improves sim fidelity.
  MAE improves marginally (0.409→0.380). Core issue: sim only models bolus
  insulin, not the AID loop's ongoing basal adjustments (~40-60% of total
  insulin delivery). The forward sim is fundamentally suited for MARGINAL
  analysis (counterfactuals), not absolute TIR prediction.
"""

import json
import time
import numpy as np
from pathlib import Path
from scipy import stats

import pandas as pd

from cgmencode.production.forward_simulator import (
    TherapySettings, InsulinEvent, CarbEvent, SimulationResult,
    _STEP_MINUTES, _STEPS_PER_HOUR, _FAST_FRACTION,
    _PERSISTENT_FRACTION, _PERSISTENT_WINDOW_HOURS,
    _DECAY_TARGET, _DECAY_RATE, _POWER_LAW_BETA,
    _IOB_POWER_LAW_THRESHOLD, _MIN_BG, _MAX_BG,
    _insulin_activity_curve, _carb_absorption_rate,
    forward_simulate,
)

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'
NS_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']
MAX_WINDOWS = 50

# Loop controller parameters
LOOP_TARGET = 110.0      # target glucose (mg/dL)
SMB_THRESHOLD = 150.0    # glucose above which SMBs may fire
SUSPEND_THRESHOLD = 85.0 # predicted glucose below which basal suspends
HYPO_THRESHOLD = 70.0    # glucose below which liver response modeled
SMB_CAP_FRACTION = 0.5   # max SMB per step = cap_fraction * basal_per_step * 6 (30 min equiv)
MAX_IOB_HOURS = 3.0      # max IOB = MAX_IOB_HOURS * basal_rate
LIVER_RELEASE_RATE = 4.0 # mg/dL per 5-min step during hypo


def closed_loop_simulate(
    initial_glucose: float,
    settings: TherapySettings,
    duration_hours: float = 4.0,
    start_hour: float = 0.0,
    bolus_events=None,
    carb_events=None,
    initial_iob: float = 0.0,
):
    """Forward sim with simplified AID loop controller.

    Reimplements the core integration loop from forward_simulator.py
    but adds a feedback controller that adjusts insulin delivery
    at each step based on current and predicted glucose.
    """
    bolus_events = bolus_events or []
    carb_events = carb_events or []

    n_steps = int(duration_hours * _STEPS_PER_HOUR)
    glucose = np.zeros(n_steps)
    iob_trace = np.zeros(n_steps)
    cob_trace = np.zeros(n_steps)
    supply_trace = np.zeros(n_steps)
    demand_trace = np.zeros(n_steps)
    timestamps_min = np.arange(n_steps) * _STEP_MINUTES
    hours_of_day = (start_hour + timestamps_min / 60.0) % 24.0
    loop_actions = np.zeros(n_steps)  # +1=SMB, -1=suspend, 0=normal

    # Build initial insulin delivery (basal + bolus)
    insulin_per_step = np.zeros(n_steps)
    basal_per_step = np.zeros(n_steps)
    met_basal_rate = settings.basal_rate

    for i in range(n_steps):
        hour = hours_of_day[i]
        delivery = settings.basal_at_hour(hour) * _STEP_MINUTES / 60.0
        insulin_per_step[i] = delivery
        basal_per_step[i] = met_basal_rate * _STEP_MINUTES / 60.0

    for event in bolus_events:
        step_idx = int(event.time_minutes / _STEP_MINUTES)
        if 0 <= step_idx < n_steps:
            insulin_per_step[step_idx] += event.units

    # Activity curve cache
    max_lookback = min(n_steps, int(settings.dia_hours * _STEPS_PER_HOUR) + 1)
    activity_values = np.array([
        _insulin_activity_curve(k * _STEP_MINUTES, settings.dia_hours)
        for k in range(max_lookback + 1)
    ])
    absorption_fractions = -np.diff(activity_values)

    # Max IOB limit
    max_iob = MAX_IOB_HOURS * met_basal_rate

    glucose[0] = initial_glucose
    iob_trace[0] = initial_iob

    for t in range(1, n_steps):
        t_min = t * _STEP_MINUTES
        hour = hours_of_day[t]
        isf_at_t = settings.isf_at_hour(hour)
        cr_at_t = settings.cr_at_hour(hour)

        # ── LOOP CONTROLLER: adjust insulin for this step ──────────
        prev_bg = glucose[t - 1]
        bg_rate = (glucose[t - 1] - glucose[max(0, t - 4)]) / max(1, min(t, 4))  # mg/dL per step
        predicted_15 = prev_bg + bg_rate * 3  # 15-min prediction

        smb_delivered = 0.0

        # Compute current IOB
        current_iob = iob_trace[t - 1]

        if prev_bg < HYPO_THRESHOLD:
            # Hypo: suspend basal + model liver glucose release
            insulin_per_step[t] = 0.0
            loop_actions[t] = -1
        elif predicted_15 < SUSPEND_THRESHOLD:
            # Predicted low: suspend basal
            insulin_per_step[t] = 0.0
            loop_actions[t] = -1
        elif prev_bg > SMB_THRESHOLD and bg_rate > -0.5 and current_iob < max_iob:
            # High and not falling fast: deliver SMB
            correction_needed = (prev_bg - LOOP_TARGET) / isf_at_t
            max_smb = basal_per_step[t] * 6  # up to 30 min of basal
            smb = min(correction_needed * 0.3, max_smb * SMB_CAP_FRACTION)
            smb = max(0, min(smb, max_iob - current_iob))
            if smb > 0.01:
                insulin_per_step[t] += smb
                smb_delivered = smb
                loop_actions[t] = 1

        # ── Insulin absorption ─────────────────────────────────────
        total_absorption = 0.0
        basal_absorption = 0.0
        iob = 0.0

        lookback = min(t, max_lookback - 1)
        for k in range(lookback + 1):
            j = t - k
            if j >= 0:
                frac = absorption_fractions[k] if k < len(absorption_fractions) else 0.0
                total_absorption += insulin_per_step[j] * frac
                basal_absorption += basal_per_step[j] * frac
                iob += insulin_per_step[j] * activity_values[k]

        if initial_iob > 0 and t < max_lookback:
            iob += initial_iob * activity_values[t]
            if t > 0 and t < len(absorption_fractions):
                total_absorption += initial_iob * absorption_fractions[t]

        iob_trace[t] = max(iob, 0.0)

        excess_absorption = total_absorption - basal_absorption

        # ISF with power-law
        effective_isf = isf_at_t
        if settings.iob_power_law and iob > _IOB_POWER_LAW_THRESHOLD:
            dampening = (iob / _IOB_POWER_LAW_THRESHOLD) ** (-_POWER_LAW_BETA)
            effective_isf = isf_at_t * dampening

        demand_fast = excess_absorption * effective_isf * _FAST_FRACTION

        persistent_window = int(_PERSISTENT_WINDOW_HOURS * _STEPS_PER_HOUR)
        start_step = max(0, t - persistent_window)
        total_excess_12h = float(
            np.sum(insulin_per_step[start_step:t + 1])
            - np.sum(basal_per_step[start_step:t + 1])
        )
        persistent_demand = 0.0
        if total_excess_12h > 0.01:
            persistent_demand = (total_excess_12h * effective_isf
                                 / persistent_window * _PERSISTENT_FRACTION)

        total_demand = demand_fast + persistent_demand
        demand_trace[t] = total_demand

        # ── Carb absorption ────────────────────────────────────────
        carb_absorbed = 0.0
        cob = 0.0
        for event in carb_events:
            elapsed = t_min - event.time_minutes
            if elapsed < 0:
                continue
            abs_min = event.absorption_hours * 60.0
            remaining_frac = max(0.0, 1.0 - elapsed / abs_min)
            cob += event.grams * remaining_frac
            carb_absorbed += _carb_absorption_rate(
                elapsed, event.grams, event.absorption_hours,
                delay_minutes=event.delay_minutes,
            )
        cob_trace[t] = cob

        csf = settings.carb_sensitivity_at_hour(hour)
        carb_rise = carb_absorbed * csf
        supply_trace[t] = carb_rise

        # ── Decay ──────────────────────────────────────────────────
        decay = (_DECAY_TARGET - glucose[t - 1]) * _DECAY_RATE

        # ── Liver glucose release during hypo ──────────────────────
        liver_release = 0.0
        if prev_bg < HYPO_THRESHOLD:
            liver_release = LIVER_RELEASE_RATE * (HYPO_THRESHOLD - prev_bg) / 30.0

        # ── Integrate ──────────────────────────────────────────────
        dBG = -total_demand + carb_rise + decay + liver_release
        glucose[t] = np.clip(glucose[t - 1] + dBG, _MIN_BG, _MAX_BG)

    return SimulationResult(
        glucose=glucose,
        iob=iob_trace,
        cob=cob_trace,
        supply=supply_trace,
        demand=demand_trace,
        timestamps_min=timestamps_min,
        hours_of_day=hours_of_day,
    ), loop_actions


def extract_meal_windows(df, patient_id, max_windows=MAX_WINDOWS):
    """Extract meal windows with carbs>10g and bolus>0.1U."""
    pdf = df[df['patient_id'] == patient_id]
    mask = (pdf['carbs'].fillna(0) > 10) & (pdf['bolus'] > 0.1)
    idxs = pdf.index[mask]

    windows = []
    for idx in idxs[:max_windows * 3]:
        pos = pdf.index.get_loc(idx)
        if pos + 48 >= len(pdf):
            continue
        w = pdf.iloc[pos:pos + 48]
        if w['glucose'].isna().sum() > 5:
            continue
        windows.append({
            'g': float(w['glucose'].iloc[0]),
            'b': float(w['bolus'].iloc[0]),
            'c': float(w['carbs'].iloc[0]),
            'iob': float(w['iob'].iloc[0]),
            'h': float(w['time'].iloc[0].hour),
            'isf': float(w['scheduled_isf'].iloc[0]),
            'cr': float(w['scheduled_cr'].iloc[0]),
            'basal': float(w['scheduled_basal_rate'].iloc[0]),
            'actual_glucose': w['glucose'].values.tolist(),
        })
        if len(windows) >= max_windows:
            break
    return windows


def main():
    t0 = time.time()
    print('=' * 70)
    print('EXP-2570: Closed-Loop Digital Twin')
    print('=' * 70)

    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')

    # Compute actual TIR per patient
    actual_metrics = {}
    for pid in NS_PATIENTS:
        pdf = df[df['patient_id'] == pid]
        glucose = pdf['glucose'].dropna()
        actual_metrics[pid] = {
            'tir': float(np.mean((glucose >= 70) & (glucose <= 180))),
            'hypo': float(np.mean(glucose < 70)),
        }

    results = {}
    for pid in NS_PATIENTS:
        windows = extract_meal_windows(df, pid)
        if len(windows) < 5:
            print(f'  {pid}: {len(windows)} windows (skip)')
            continue

        open_tirs, closed_tirs = [], []
        correlations_open, correlations_closed = [], []

        for w in windows:
            s = TherapySettings(
                isf=w['isf'], cr=w['cr'],
                basal_rate=w['basal'], dia_hours=5.0
            )

            # Open-loop sim
            r_open = forward_simulate(
                initial_glucose=w['g'], settings=s, duration_hours=4.0,
                start_hour=w['h'],
                bolus_events=[InsulinEvent(0, w['b'])],
                carb_events=[CarbEvent(0, w['c'])],
                initial_iob=w['iob'], noise_std=0, seed=42
            )
            open_tirs.append(r_open.tir)

            # Closed-loop sim
            r_closed, actions = closed_loop_simulate(
                initial_glucose=w['g'], settings=s, duration_hours=4.0,
                start_hour=w['h'],
                bolus_events=[InsulinEvent(0, w['b'])],
                carb_events=[CarbEvent(0, w['c'])],
                initial_iob=w['iob'],
            )
            closed_tirs.append(r_closed.tir)

            # Trajectory correlation with actual
            actual = np.array(w['actual_glucose'][:len(r_open.glucose)])
            valid = np.isfinite(actual)
            if valid.sum() > 10:
                sim_open = r_open.glucose[:len(actual)]
                sim_closed = r_closed.glucose[:len(actual)]
                r_o, _ = stats.pearsonr(actual[valid], sim_open[valid])
                r_c, _ = stats.pearsonr(actual[valid], sim_closed[valid])
                correlations_open.append(r_o)
                correlations_closed.append(r_c)

        actual_tir = actual_metrics[pid]['tir']
        mean_open = float(np.mean(open_tirs))
        mean_closed = float(np.mean(closed_tirs))
        mean_corr_open = float(np.mean(correlations_open)) if correlations_open else 0
        mean_corr_closed = float(np.mean(correlations_closed)) if correlations_closed else 0

        n_smb = 0
        n_suspend = 0

        print(f'  {pid}: actual={actual_tir:.3f} | open={mean_open:.3f} '
              f'(err={abs(actual_tir-mean_open):.3f}) | closed={mean_closed:.3f} '
              f'(err={abs(actual_tir-mean_closed):.3f}) | '
              f'corr open={mean_corr_open:.3f} closed={mean_corr_closed:.3f}')

        results[pid] = {
            'actual_tir': actual_tir,
            'open_loop_tir': mean_open,
            'closed_loop_tir': mean_closed,
            'open_error': abs(actual_tir - mean_open),
            'closed_error': abs(actual_tir - mean_closed),
            'open_corr': mean_corr_open,
            'closed_corr': mean_corr_closed,
            'n_windows': len(windows),
        }

    # Summary
    open_errors = [v['open_error'] for v in results.values()]
    closed_errors = [v['closed_error'] for v in results.values()]
    open_corrs = [v['open_corr'] for v in results.values()]
    closed_corrs = [v['closed_corr'] for v in results.values()]
    actual_tirs = [v['actual_tir'] for v in results.values()]
    open_tirs = [v['open_loop_tir'] for v in results.values()]
    closed_tirs = [v['closed_loop_tir'] for v in results.values()]

    # Patient ranking correlation
    rank_open, _ = stats.spearmanr(actual_tirs, open_tirs)
    rank_closed, _ = stats.spearmanr(actual_tirs, closed_tirs)

    print(f'\nSummary ({len(results)} patients):')
    print(f'  H1 - Absolute TIR MAE:')
    print(f'    Open-loop:   {np.mean(open_errors):.3f}')
    print(f'    Closed-loop: {np.mean(closed_errors):.3f}')
    print(f'    Improvement: {np.mean(open_errors) - np.mean(closed_errors):+.3f}')

    print(f'  H2 - Patient Ranking (Spearman):')
    print(f'    Open-loop:   {rank_open:.3f}')
    print(f'    Closed-loop: {rank_closed:.3f}')

    print(f'  H3 - Trajectory Correlation:')
    print(f'    Open-loop:   {np.mean(open_corrs):.3f}')
    print(f'    Closed-loop: {np.mean(closed_corrs):.3f}')

    h1 = np.mean(closed_errors) < 0.2
    h2 = rank_closed > 0.5
    h3 = np.mean(closed_corrs) > 0.5
    passed = sum([h1, h2, h3])

    if passed >= 2:
        verdict = 'SUPPORTED'
    elif passed >= 1:
        verdict = 'PARTIALLY SUPPORTED'
    else:
        verdict = 'NOT SUPPORTED'

    print(f'\n  H1 {"PASS" if h1 else "FAIL"} | H2 {"PASS" if h2 else "FAIL"} | '
          f'H3 {"PASS" if h3 else "FAIL"}')
    print(f'  VERDICT: {verdict}')
    print(f'  Runtime: {time.time() - t0:.0f}s')

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2570_closed_loop_twin.json'
    with open(out_path, 'w') as f:
        json.dump({
            'exp_id': 'EXP-2570',
            'hypothesis': 'Closed-loop sim improves TIR prediction vs open-loop',
            'verdict': verdict,
            'results': results,
            'summary': {
                'open_mae': float(np.mean(open_errors)),
                'closed_mae': float(np.mean(closed_errors)),
                'rank_open': float(rank_open),
                'rank_closed': float(rank_closed),
                'corr_open': float(np.mean(open_corrs)),
                'corr_closed': float(np.mean(closed_corrs)),
                'h1_pass': bool(h1),
                'h2_pass': bool(h2),
                'h3_pass': bool(h3),
            },
        }, f, indent=2)
    print(f'  Saved: {out_path}')


if __name__ == '__main__':
    main()
