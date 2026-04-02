"""
hindcast_composite.py — Composite evaluation modes for hindcast.

Extends hindcast.py with modes that compose multiple agentic modules into
end-to-end evaluations:

  decision      Full agentic chain: detect → track → forecast → simulate → bound
  drift-scan    Rank windows by Kalman ISF/CR drift, cross-ref with anomaly
  calibration   MC-dropout coverage at multiple confidence levels

These reuse hindcast's data loading, model loading, and window selection.
The modes are dispatched from hindcast.py main() but the logic lives here
to keep hindcast.py from growing past 2K lines.

Usage (via hindcast CLI):
    python3 -m tools.cgmencode.hindcast --mode decision \\
        --data path/to/ns-data --checkpoint grouped_best.pth

    python3 -m tools.cgmencode.hindcast --mode drift-scan \\
        --data path/to/ns-data --checkpoint grouped_best.pth --top 10

    python3 -m tools.cgmencode.hindcast --mode calibration \\
        --data path/to/ns-data --checkpoint grouped_best.pth
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch

from .schema import (
    NORMALIZATION_SCALES, IDX_GLUCOSE, IDX_IOB, IDX_COB,
    IDX_BOLUS, IDX_CARBS, NUM_FEATURES,
)
from .hindcast import (
    load_model, load_profile, _model_tensor,
    run_hindcast, run_anomaly_scan, find_interesting_windows,
    compute_physics_baseline, make_residual_input, format_glucose, sparkline,
)
from .real_data_adapter import build_nightscout_grid
from .state_tracker import ISFCRTracker, DriftDetector, PatternStateMachine
from .uncertainty import mc_predict, hypo_probability, hyper_probability, prediction_interval
from .forecast import HierarchicalForecaster, ScenarioSimulator
from .evaluate import clinical_summary, override_accuracy

GLUCOSE_SCALE = NORMALIZATION_SCALES['glucose']


# =============================================================================
# 1. Decision Mode — Full agentic chain on a window
# =============================================================================

def run_decision(model, features, df, center_idx, history=12, horizon=12,
                 profile=None, residual=False, isf=40.0, cr=10.0,
                 physics_level='enhanced', n_mc_samples=50,
                 classifier_model=None, classifier_features=None):
    """Run the full agentic decision chain on a single window.

    Pipeline:
        1. Event classification (if classifier available)
        2. ISF/CR drift tracking via Kalman filter
        3. Multi-resolution forecast via HierarchicalForecaster
        4. Scenario simulation for top detected events
        5. MC-Dropout uncertainty bounds
        6. Clinical metrics on forecasted glucose
        7. Score against what actually happened

    Args:
        model: trained cgmencode model (AE/Grouped)
        features: (N, F) normalized feature array
        df: DataFrame with columns including 'glucose'
        center_idx: index into features/df for the target window
        history: history steps (default 12 = 60 min)
        horizon: prediction horizon steps (default 12 = 60 min)
        profile: dict with 'isf', 'cr' keys (or uses defaults)
        residual: whether model operates on physics residuals
        isf: ISF in mg/dL per unit
        cr: CR in grams per unit
        physics_level: 'simple' or 'enhanced'
        n_mc_samples: MC-Dropout sample count
        classifier_model: optional trained XGBoost classifier
        classifier_features: optional (N, F_tab) tabular features for classifier

    Returns:
        dict with keys for each pipeline stage
    """
    result = {
        'center_idx': center_idx,
        'time': str(df.index[center_idx]) if center_idx < len(df) else None,
        'history_steps': history,
        'horizon_steps': horizon,
    }
    _isf = profile['isf'] if profile else isf
    _cr = profile['cr'] if profile else cr

    start = center_idx - history
    end = center_idx + horizon
    if start < 0 or end > len(features):
        result['error'] = 'Window out of bounds'
        return result

    window = features[start:end]

    # --- Actual glucose for scoring ---
    actual_glucose_norm = window[:, IDX_GLUCOSE]
    actual_glucose_mgdl = actual_glucose_norm * GLUCOSE_SCALE
    future_glucose_mgdl = actual_glucose_mgdl[history:]

    # --- 1. Event classification ---
    event_result = {'status': 'skipped'}
    if classifier_model is not None and classifier_features is not None:
        try:
            from .event_classifier import predict_events
            # Use tabular features around the center index
            if center_idx < len(classifier_features):
                row = classifier_features[center_idx:center_idx + 1]
                events = predict_events(classifier_model, row, threshold=0.3)
                event_result = {
                    'status': 'ok',
                    'detected_events': events,
                    'n_events': len(events),
                }
            else:
                event_result = {'status': 'index_out_of_range'}
        except Exception as e:
            event_result = {'status': 'error', 'message': str(e)}
    result['event_classification'] = event_result

    # --- 2. ISF/CR drift tracking ---
    drift_result = _run_drift_for_window(
        features, df, center_idx, history, _isf, _cr, physics_level)
    result['drift_tracking'] = drift_result

    # --- 3. Forecast ---
    forecast_result = {}
    try:
        forecaster = HierarchicalForecaster(short_model=model)
        x = _model_tensor(window[:history].copy(), model).unsqueeze(0)
        if residual:
            phys = compute_physics_baseline(
                window[:history], _isf, _cr, physics_level)
            res_input = make_residual_input(window[:history], phys)
            x = _model_tensor(res_input, model).unsqueeze(0)

        segments = forecaster.forecast(x, horizon_hours=horizon * 5 / 60, causal=True)
        # Extract short-term forecast glucose
        if 'short' in segments:
            fg = np.asarray(segments['short']['glucose_mgdl']).flatten()
            # Trim to horizon length
            fg = fg[:horizon] if len(fg) > horizon else fg
            forecast_result = {
                'glucose_mgdl': fg.tolist(),
                'n_steps': len(fg),
            }
            # Forecast MAE vs actual
            compare_len = min(len(fg), len(future_glucose_mgdl))
            if compare_len > 0:
                forecast_mae = float(np.mean(
                    np.abs(fg[:compare_len] - future_glucose_mgdl[:compare_len])))
                forecast_result['mae_mgdl'] = round(forecast_mae, 2)
        else:
            forecast_result = {'status': 'no_short_segment'}
    except Exception as e:
        forecast_result = {'status': 'error', 'message': str(e)}
    result['forecast'] = forecast_result

    # --- 4. Scenario simulation ---
    scenario_result = {'status': 'skipped'}
    try:
        forecaster = HierarchicalForecaster(short_model=model)
        sim = ScenarioSimulator(forecaster)
        x_full = _model_tensor(window.copy(), model).unsqueeze(0)

        scenarios_to_test = ['meal_small', 'meal_medium', 'exercise_light']
        scenario_outcomes = []
        for sname in scenarios_to_test:
            try:
                sr = sim.simulate_scenario(x_full, sname, horizon_hours=1.0)
                scenario_outcomes.append({
                    'name': sname,
                    'mean_impact_mgdl': round(sr['mean_impact_mgdl'], 1),
                    'max_impact_mgdl': round(sr['max_impact_mgdl'], 1),
                })
            except Exception:
                continue
        scenario_result = {'status': 'ok', 'scenarios': scenario_outcomes}
    except Exception as e:
        scenario_result = {'status': 'error', 'message': str(e)}
    result['scenario_simulation'] = scenario_result

    # --- 5. Uncertainty (MC-Dropout) ---
    uncertainty_result = {}
    try:
        x_unc = _model_tensor(window.copy(), model).unsqueeze(0)
        mean, std, _ = mc_predict(model, x_unc, n_samples=n_mc_samples, causal=True)

        # Future-only glucose uncertainty (in mg/dL)
        mean_g = mean[0, history:, IDX_GLUCOSE] * GLUCOSE_SCALE
        std_g = std[0, history:, IDX_GLUCOSE] * GLUCOSE_SCALE

        # P(hypo) and P(hyper)
        p_hypo = hypo_probability(mean_g.unsqueeze(0), std_g.unsqueeze(0))
        p_hyper = hyper_probability(mean_g.unsqueeze(0), std_g.unsqueeze(0))

        # 95% prediction interval
        lo, hi = prediction_interval(mean_g, std_g, confidence=0.95)

        uncertainty_result = {
            'mean_glucose_mgdl': round(float(mean_g.mean()), 1),
            'mean_std_mgdl': round(float(std_g.mean()), 1),
            'max_p_hypo': round(float(p_hypo.max()), 4),
            'max_p_hyper': round(float(p_hyper.max()), 4),
            'pi_95_low_mgdl': round(float(lo.min()), 1),
            'pi_95_high_mgdl': round(float(hi.max()), 1),
            'n_mc_samples': n_mc_samples,
        }
    except Exception as e:
        uncertainty_result = {'status': 'error', 'message': str(e)}
    result['uncertainty'] = uncertainty_result

    # --- 6. Clinical metrics on actual future glucose ---
    if len(future_glucose_mgdl) > 0:
        result['clinical_actual'] = clinical_summary(future_glucose_mgdl)

    return result


def _run_drift_for_window(features, df, center_idx, lookback_windows,
                          isf, cr, physics_level):
    """Run ISF/CR drift tracker over recent windows leading up to center_idx."""
    try:
        tracker = ISFCRTracker(nominal_isf=isf, nominal_cr=cr)
        detector = DriftDetector(tracker)

        # Feed tracker with recent data (up to 24 hours before center)
        n_recent = min(center_idx, 288)  # up to 288 steps = 24hr
        stride = 6  # every 30 min
        trajectory = []

        for i in range(max(0, center_idx - n_recent), center_idx, stride):
            if i + 1 >= len(features):
                break
            glucose_actual = features[i, IDX_GLUCOSE] * GLUCOSE_SCALE
            glucose_prev = features[max(0, i - 1), IDX_GLUCOSE] * GLUCOSE_SCALE
            iob_delta = float((features[i, IDX_IOB] - features[max(0, i - 1), IDX_IOB])
                              * NORMALIZATION_SCALES['iob'])
            cob_delta = float((features[i, IDX_COB] - features[max(0, i - 1), IDX_COB])
                              * NORMALIZATION_SCALES['cob'])

            # Physics prediction for this step
            glucose_expected = glucose_prev - iob_delta * isf + cob_delta * isf / cr
            residual = glucose_actual - glucose_expected

            ts = str(df.index[i]) if i < len(df) else None
            state = tracker.update(residual, iob_delta, cob_delta, timestamp=ts)
            trajectory.append(state)

        classification = detector.classify()
        override = detector.suggested_override()

        return {
            'classification': classification,
            'suggested_override': override,
            'n_observations': len(trajectory),
            'final_isf_drift_pct': trajectory[-1]['isf_drift_pct'] if trajectory else 0.0,
            'final_cr_drift_pct': trajectory[-1]['cr_drift_pct'] if trajectory else 0.0,
        }
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


# =============================================================================
# 2. Drift-Scan Mode — Rank windows by ISF/CR drift
# =============================================================================

def run_drift_scan(model, features, df, profile=None,
                   isf=40.0, cr=10.0, physics_level='enhanced',
                   history=12, horizon=12, top_n=10, stride=6,
                   residual=False):
    """Scan all windows and rank by ISF/CR drift magnitude.

    Cross-references drift with model reconstruction anomaly score to find
    windows where physiological drift and model surprise co-occur.

    Args:
        model: trained model for anomaly scoring
        features: (N, F) normalized features
        df: DataFrame
        profile: dict with 'isf', 'cr'
        isf, cr: fallback ISF/CR values
        physics_level: physics model level
        history, horizon: window geometry
        top_n: number of top results to return
        stride: step stride for scanning
        residual: whether model uses residual inputs

    Returns:
        list of dicts sorted by drift magnitude, with anomaly cross-ref
    """
    _isf = profile['isf'] if profile else isf
    _cr = profile['cr'] if profile else cr

    # Step 1: Run anomaly scan to get per-window reconstruction error
    res_kw = dict(residual=residual, isf=_isf, cr=_cr, physics_level=physics_level)
    anomaly_results = run_anomaly_scan(
        model, features, df,
        history=history, horizon=horizon,
        top_n=len(features),  # score all windows
        stride=stride, **res_kw)

    # Build lookup: center_idx → anomaly MAE
    anomaly_by_idx = {}
    for ar in anomaly_results:
        anomaly_by_idx[ar['center_idx']] = ar.get('glucose_mae', 0.0)

    # Step 2: Run drift tracker across all windows
    tracker = ISFCRTracker(nominal_isf=_isf, nominal_cr=_cr)
    drift_results = []

    total_needed = history + horizon
    for center_idx in range(history, len(features) - horizon, stride):
        # Feed a single observation to tracker
        i = center_idx
        glucose_actual = features[i, IDX_GLUCOSE] * GLUCOSE_SCALE
        glucose_prev = features[max(0, i - 1), IDX_GLUCOSE] * GLUCOSE_SCALE
        iob_delta = float((features[i, IDX_IOB] - features[max(0, i - 1), IDX_IOB])
                          * NORMALIZATION_SCALES['iob'])
        cob_delta = float((features[i, IDX_COB] - features[max(0, i - 1), IDX_COB])
                          * NORMALIZATION_SCALES['cob'])

        glucose_expected = glucose_prev - iob_delta * _isf + cob_delta * _isf / _cr
        residual_val = glucose_actual - glucose_expected

        ts = str(df.index[i]) if i < len(df) else None
        state = tracker.update(residual_val, iob_delta, cob_delta, timestamp=ts)

        drift_mag = abs(state['isf_drift_pct']) + abs(state['cr_drift_pct'])
        anomaly_mae = anomaly_by_idx.get(center_idx, None)

        drift_results.append({
            'center_idx': center_idx,
            'time': str(df.index[center_idx]) if center_idx < len(df) else None,
            'isf_drift_pct': round(state['isf_drift_pct'], 1),
            'cr_drift_pct': round(state['cr_drift_pct'], 1),
            'drift_magnitude': round(drift_mag, 1),
            'isf_estimate': round(state['isf'], 1),
            'cr_estimate': round(state['cr'], 1),
            'anomaly_mae': round(anomaly_mae, 2) if anomaly_mae is not None else None,
            'co_occurrence': (drift_mag > 15 and anomaly_mae is not None
                              and anomaly_mae > np.median([a.get('glucose_mae', 0)
                                                           for a in anomaly_results])
                              if anomaly_mae is not None else False),
        })

    # Sort by drift magnitude, return top_n
    drift_results.sort(key=lambda r: -r['drift_magnitude'])
    return drift_results[:top_n]


# =============================================================================
# 3. Calibration Mode — MC-Dropout coverage analysis
# =============================================================================

def run_calibration(model, features, history=12, horizon=12,
                    stride=6, n_samples_sweep=None,
                    confidence_levels=None):
    """Evaluate MC-Dropout prediction interval calibration.

    For each confidence level and MC sample count, measures how often
    the actual glucose falls within the predicted interval.

    Args:
        model: trained model with dropout layers
        features: (N, F) normalized features
        history: history steps
        horizon: horizon steps
        stride: step stride for evaluation windows
        n_samples_sweep: list of MC sample counts (default [10, 20, 50, 100])
        confidence_levels: list of confidence levels (default [0.5, 0.8, 0.9, 0.95, 0.99])

    Returns:
        dict with calibration results per (n_samples, confidence) pair
    """
    if n_samples_sweep is None:
        n_samples_sweep = [10, 20, 50, 100]
    if confidence_levels is None:
        confidence_levels = [0.50, 0.80, 0.90, 0.95, 0.99]

    total_needed = history + horizon
    results = {}

    for n_s in n_samples_sweep:
        level_results = {}

        # Collect predictions across windows
        all_coverages = {cl: [] for cl in confidence_levels}
        all_widths = {cl: [] for cl in confidence_levels}
        n_windows = 0

        for center_idx in range(history, len(features) - horizon, stride):
            window = features[center_idx - history:center_idx + horizon]
            if np.isnan(window).any():
                continue

            x = torch.tensor(window, dtype=torch.float32).unsqueeze(0)
            try:
                mean, std, _ = mc_predict(model, x, n_samples=n_s, causal=True)
            except Exception:
                continue

            # Future-only glucose
            actual = x[0, history:, IDX_GLUCOSE]
            mean_future = mean[0, history:, IDX_GLUCOSE]
            std_future = std[0, history:, IDX_GLUCOSE]

            for cl in confidence_levels:
                lo, hi = prediction_interval(mean_future, std_future, confidence=cl)
                covered = ((actual >= lo) & (actual <= hi)).float()
                width_mgdl = (hi - lo) * GLUCOSE_SCALE

                all_coverages[cl].append(float(covered.mean()))
                all_widths[cl].append(float(width_mgdl.mean()))

            n_windows += 1

        if n_windows == 0:
            results[n_s] = {'status': 'no_valid_windows'}
            continue

        for cl in confidence_levels:
            actual_cov = float(np.mean(all_coverages[cl]))
            mean_width = float(np.mean(all_widths[cl]))
            cal_gap = abs(actual_cov - cl)

            level_results[str(cl)] = {
                'nominal_coverage': cl,
                'actual_coverage': round(actual_cov, 4),
                'calibration_gap': round(cal_gap, 4),
                'mean_width_mgdl': round(mean_width, 1),
                'n_windows': n_windows,
            }

        results[n_s] = level_results

    # Find best n_samples (smallest gap at 95%)
    best_n = None
    best_gap = float('inf')
    for n_s, levels in results.items():
        if isinstance(levels, dict) and '0.95' in levels:
            gap = levels['0.95']['calibration_gap']
            if gap < best_gap:
                best_gap = gap
                best_n = n_s

    return {
        'calibration': results,
        'best_n_samples': best_n,
        'best_95_gap': round(best_gap, 4) if best_gap < float('inf') else None,
        'confidence_levels': confidence_levels,
        'n_samples_sweep': n_samples_sweep,
    }


# =============================================================================
# Display Functions
# =============================================================================

def display_decision(result, model_name='grouped', checkpoint_name='', quiet=False):
    """Display full decision chain results as ASCII summary."""
    time_str = result.get('time', '?')
    print(f'\n{"═" * 78}')
    print(f'  DECISION ANALYSIS @ {time_str}')
    print(f'  Model: {model_name} ({checkpoint_name})')
    print(f'{"═" * 78}')

    # Event classification
    ev = result.get('event_classification', {})
    status = ev.get('status', 'unknown')
    if status == 'ok':
        events = ev.get('detected_events', [])
        if events:
            print(f'\n  ▸ Events detected: {len(events)}')
            for e in events[:3]:
                print(f'    {e.get("event_type", "?")} '
                      f'(p={e.get("probability", 0):.2f})')
        else:
            print(f'\n  ▸ Events detected: none')
    else:
        print(f'\n  ▸ Event classification: {status}')

    # Drift tracking
    drift = result.get('drift_tracking', {})
    if 'classification' in drift:
        cls = drift['classification']
        state = cls.get('state', '?') if isinstance(cls, dict) else str(cls)
        isf_d = drift.get('final_isf_drift_pct', 0)
        cr_d = drift.get('final_cr_drift_pct', 0)
        print(f'\n  ▸ Drift state: {state}')
        print(f'    ISF drift: {isf_d:+.1f}%  CR drift: {cr_d:+.1f}%')
        ovr = drift.get('suggested_override')
        if ovr:
            print(f'    Override suggestion: {ovr.get("type", "?")} '
                  f'(confidence={ovr.get("confidence", 0):.2f})')
    elif drift.get('status') == 'error':
        print(f'\n  ▸ Drift tracking: error — {drift.get("message", "?")}')

    # Forecast
    fc = result.get('forecast', {})
    if 'mae_mgdl' in fc:
        n_steps = fc.get('n_steps', 0)
        glucose_vals = fc.get('glucose_mgdl', [])
        print(f'\n  ▸ Forecast: {n_steps} steps, MAE={fc["mae_mgdl"]:.1f} mg/dL')
        if glucose_vals:
            vals = glucose_vals[:12]
            print(f'    {sparkline(vals, width=min(len(vals), 20))} '
                  f'({format_glucose(vals[0])} → {format_glucose(vals[-1])})')
    elif fc.get('status') == 'error':
        print(f'\n  ▸ Forecast: error — {fc.get("message", "?")}')

    # Scenarios
    sc = result.get('scenario_simulation', {})
    if sc.get('status') == 'ok':
        scenarios = sc.get('scenarios', [])
        if scenarios:
            print(f'\n  ▸ Scenario simulation ({len(scenarios)} scenarios):')
            for s in scenarios:
                delta = s.get('mean_impact_mgdl', 0)
                arrow = '↑' if delta > 0 else '↓' if delta < 0 else '→'
                print(f'    {s["name"]:20s}  {arrow} {delta:+.1f} mg/dL mean')

    # Uncertainty
    unc = result.get('uncertainty', {})
    if 'mean_std_mgdl' in unc:
        print(f'\n  ▸ Uncertainty (MC-Dropout, n={unc.get("n_mc_samples", "?")}):')
        print(f'    Mean ± std: {unc["mean_glucose_mgdl"]:.0f} '
              f'± {unc["mean_std_mgdl"]:.1f} mg/dL')
        print(f'    95% PI: [{unc["pi_95_low_mgdl"]:.0f}, '
              f'{unc["pi_95_high_mgdl"]:.0f}] mg/dL')
        print(f'    P(hypo<70): {unc["max_p_hypo"]:.3f}  '
              f'P(hyper>180): {unc["max_p_hyper"]:.3f}')

    # Clinical metrics on actual
    clin = result.get('clinical_actual', {})
    if clin:
        print(f'\n  ▸ Actual clinical (future window):')
        print(f'    TIR: {clin.get("tir", 0):.0f}%  '
              f'GRI: {clin.get("gri", 0):.1f}  '
              f'Hypo events: {clin.get("hypo_events", 0)}')
        print(f'    Mean: {clin.get("mean", 0):.0f} mg/dL  '
              f'CV: {clin.get("cv", 0):.1f}%')

    print(f'\n{"═" * 78}')
    return result


def display_drift_scan(results, model_name='grouped', checkpoint_name=''):
    """Display drift-scan results as ranked table."""
    print(f'\n{"═" * 78}')
    print(f'  DRIFT SCAN — Top {len(results)} windows by ISF/CR drift')
    print(f'  Model: {model_name} ({checkpoint_name})')
    print(f'{"═" * 78}')

    if not results:
        print('  No windows analyzed.')
        return

    print(f'\n  {"#":>3}  {"Time":>20}  {"ISF Δ%":>7}  {"CR Δ%":>7}  '
          f'{"Drift":>6}  {"Anom MAE":>9}  {"Co-occur":>8}')
    print(f'  {"─" * 3}  {"─" * 20}  {"─" * 7}  {"─" * 7}  '
          f'{"─" * 6}  {"─" * 9}  {"─" * 8}')

    for rank, r in enumerate(results, 1):
        time_str = r.get('time', '?')
        if len(time_str) > 20:
            time_str = time_str[:20]
        anom = f'{r["anomaly_mae"]:.1f}' if r.get('anomaly_mae') is not None else '—'
        co = '  ✓' if r.get('co_occurrence') else ''
        print(f'  {rank:3d}  {time_str:>20}  {r["isf_drift_pct"]:+6.1f}%  '
              f'{r["cr_drift_pct"]:+6.1f}%  {r["drift_magnitude"]:5.1f}  '
              f'{anom:>9}  {co:>8}')

    # Summary
    co_count = sum(1 for r in results if r.get('co_occurrence'))
    if co_count:
        print(f'\n  ⚠ {co_count}/{len(results)} windows show drift + anomaly co-occurrence')
    print(f'{"═" * 78}')


def display_calibration(result, model_name='grouped', checkpoint_name=''):
    """Display calibration results as coverage table."""
    print(f'\n{"═" * 78}')
    print(f'  UNCERTAINTY CALIBRATION REPORT')
    print(f'  Model: {model_name} ({checkpoint_name})')
    print(f'{"═" * 78}')

    cal = result.get('calibration', {})
    if not cal:
        print('  No calibration results.')
        return

    n_samples_sweep = result.get('n_samples_sweep', sorted(cal.keys()))

    for n_s in n_samples_sweep:
        levels = cal.get(n_s, cal.get(str(n_s), {}))
        if isinstance(levels, dict) and 'status' in levels:
            print(f'\n  MC samples = {n_s}: {levels["status"]}')
            continue

        print(f'\n  MC samples = {n_s}:')
        print(f'  {"Nominal":>9}  {"Actual":>9}  {"Gap":>7}  {"Width (mg/dL)":>14}')
        print(f'  {"─" * 9}  {"─" * 9}  {"─" * 7}  {"─" * 14}')

        for cl_key in sorted(levels.keys(), key=lambda k: float(k)):
            entry = levels[cl_key]
            if not isinstance(entry, dict):
                continue
            nominal = entry.get('nominal_coverage', float(cl_key))
            actual = entry.get('actual_coverage', 0)
            gap = entry.get('calibration_gap', 0)
            width = entry.get('mean_width_mgdl', 0)
            # Mark good calibration
            marker = '  ✓' if gap < 0.05 else '  ✗' if gap > 0.15 else ''
            print(f'  {nominal:8.0%}  {actual:8.1%}  {gap:6.3f}  '
                  f'{width:13.1f}{marker}')

    best_n = result.get('best_n_samples')
    best_gap = result.get('best_95_gap')
    if best_n is not None:
        print(f'\n  Best n_samples at 95%: {best_n} (gap={best_gap:.4f})')
        calibrated = best_gap < 0.05
        print(f'  Calibrated: {"✓ YES" if calibrated else "✗ NO (gap > 5%)"}')

    print(f'{"═" * 78}')
