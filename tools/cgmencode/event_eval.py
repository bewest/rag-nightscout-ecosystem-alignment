#!/usr/bin/env python3
"""
event_eval.py — Systematic model evaluation with event classification.

Runs each model through inference frames and classifies what it detects.
Outputs structured JSON for report generation.

Usage:
    python3 -m tools.cgmencode.event_eval \
        --data ../t1pal-mobile-workspace/externals/logs/ns-fixtures/90-day-history
"""

import argparse
import json
import sys
import os
import numpy as np
import pandas as pd
import torch
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .schema import (
    NORMALIZATION_SCALES, IDX_GLUCOSE, IDX_IOB, IDX_COB,
    IDX_TIME_SIN, IDX_TIME_COS, ACTION_IDX,
)
from .real_data_adapter import build_nightscout_grid
from .hindcast import (
    load_model, load_profile, run_hindcast, run_anomaly_scan,
    run_counterfactual, run_imputation, run_similarity,
    find_interesting_windows, find_loop_prediction,
    compute_physics_baseline,
)
from .physics_model import RESIDUAL_SCALE

SCALE = NORMALIZATION_SCALES

# ── Event classification heuristics ──

def classify_window(df: pd.DataFrame, center_idx: int,
                    history: int = 12, horizon: int = 12) -> List[str]:
    """Classify metabolic events in a window using heuristics."""
    start = center_idx - history
    end = center_idx + horizon
    g = df['glucose'].values[start:end]
    iob = df['iob'].values[start:end]
    carbs = df['carbs'].values[start:end]
    bolus = df['bolus'].values[start:end]

    events = []

    if np.any(np.isnan(g)):
        return ['incomplete']

    # BG dynamics
    max_rise_30m = max(g[i] - g[max(0, i-6)] for i in range(6, len(g)))
    max_drop_30m = max(g[max(0, i-6)] - g[i] for i in range(6, len(g)))
    bg_range = np.nanmax(g) - np.nanmin(g)

    # Time of day
    center_time = df.index[center_idx]
    hour = center_time.hour

    # Total actions
    total_carbs = np.sum(carbs)
    total_bolus = np.sum(bolus)
    iob_at_center = iob[history - 1] if history > 0 else iob[0]

    # UAM: big rise, no carbs, low IOB
    if max_rise_30m > 40 and total_carbs == 0 and iob_at_center < 2.0:
        events.append('uam')

    # Dawn phenomenon: early morning rise, low IOB
    if 3 <= hour <= 8 and max_rise_30m > 20 and iob_at_center < 1.5:
        events.append('dawn')

    # Exercise: big drop, low IOB
    if max_drop_30m > 30 and iob_at_center < 2.0 and total_carbs == 0:
        events.append('exercise_candidate')

    # Meal+bolus: both present
    if total_carbs > 0 and total_bolus > 0:
        events.append('meal_bolus')
    elif total_carbs > 0:
        events.append('meal_no_bolus')
    elif total_bolus > 0:
        events.append('correction')

    # High volatility
    if bg_range > 100:
        events.append('high_volatility')

    # Nocturnal
    if hour >= 22 or hour <= 5:
        events.append('nocturnal')

    # Stable
    if bg_range < 30 and max_rise_30m < 15 and max_drop_30m < 15:
        events.append('stable')

    if not events:
        events.append('other')

    return events


def find_event_windows(df: pd.DataFrame, features: np.ndarray,
                       event_type: str, n: int = 3,
                       history: int = 12, horizon: int = 12) -> List[int]:
    """Find windows matching a specific event type."""
    total_len = history + horizon
    candidates = []

    for i in range(history, len(df) - horizon, 6):
        events = classify_window(df, i, history, horizon)
        if event_type in events:
            g = df['glucose'].values[i - history:i + horizon]
            if np.any(np.isnan(g)):
                continue
            bg_range = np.nanmax(g) - np.nanmin(g)
            candidates.append((bg_range, i))

    candidates.sort(reverse=True)
    # Space them out
    selected = []
    for _, idx in candidates:
        if all(abs(idx - s) > total_len * 2 for s in selected):
            selected.append(idx)
            if len(selected) >= n:
                break
    return selected


def evaluate_model_forecast(model, features, df, data_path, indices,
                            history, horizon, mode, residual, isf, cr,
                            physics_level='enhanced'):
    """Run forecast/reconstruct on specific windows, return metrics."""
    results = []
    for idx in indices:
        pred, recon, phys = run_hindcast(
            model, features, idx, history, horizon, mode,
            residual=residual, isf=isf, cr=cr, physics_level=physics_level)

        actual = df['glucose'].values[idx:idx + horizon]
        events = classify_window(df, idx, history, horizon)
        loop = find_loop_prediction(data_path, df.index[idx])

        errors = [abs(pred[h] - actual[h]) for h in range(horizon)
                  if not np.isnan(actual[h])]
        ml_mae = float(np.mean(errors)) if errors else None

        loop_mae = None
        if loop:
            loop_vals = loop['values']
            loop_errors = []
            for h in range(min(horizon, len(loop_vals))):
                if not np.isnan(actual[h]):
                    loop_errors.append(abs(loop_vals[h] - actual[h]))
            if loop_errors:
                loop_mae = float(np.mean(loop_errors))

        phys_mae = None
        if phys is not None:
            phys_errors = [abs(phys[history + h] - actual[h])
                          for h in range(horizon) if not np.isnan(actual[h])]
            phys_mae = float(np.mean(phys_errors)) if phys_errors else None

        results.append({
            'time': str(df.index[idx]),
            'events': events,
            'bg_at_t': float(df['glucose'].values[idx - 1]),
            'iob_at_t': float(df['iob'].values[idx - 1]),
            'model_mae': ml_mae,
            'physics_mae': phys_mae,
            'loop_mae': loop_mae,
        })
    return results


def evaluate_model_anomaly(model, features, df, history, horizon,
                           residual, isf, cr, physics_level='enhanced',
                           top_n=20):
    """Run anomaly scan and classify each anomaly."""
    anomalies = run_anomaly_scan(
        model, features, df, history=history, horizon=horizon,
        top_n=top_n, stride=6,
        residual=residual, isf=isf, cr=cr, physics_level=physics_level)

    for a in anomalies:
        a['events'] = classify_window(df, a['center_idx'], history, horizon)
    return anomalies


def evaluate_model_counterfactual(model, features, df, indices,
                                   history, horizon,
                                   residual, isf, cr, physics_level='enhanced'):
    """Run counterfactual and measure treatment effect."""
    results = []
    for idx in indices:
        recon_real, recon_cf = run_counterfactual(
            model, features, idx, history, horizon,
            residual=residual, isf=isf, cr=cr, physics_level=physics_level)

        effect = recon_real - recon_cf
        events = classify_window(df, idx, history, horizon)
        total_len = history + horizon
        start = idx - history

        results.append({
            'time': str(df.index[idx]),
            'events': events,
            'total_bolus': float(df['bolus'].values[start:start + total_len].sum()),
            'total_carbs': float(df['carbs'].values[start:start + total_len].sum()),
            'mean_treatment_effect': float(np.mean(effect)),
            'max_treatment_effect': float(np.max(effect)),
            'min_treatment_effect': float(np.min(effect)),
            'effect_at_end': float(effect[-1]),
        })
    return results


def evaluate_model_impute(model, features, df, indices, history, horizon,
                          residual, isf, cr, physics_level='enhanced'):
    """Run imputation and measure masked vs visible accuracy."""
    results = []
    for idx in indices:
        actual, predicted, mask = run_imputation(
            model, features, idx, history, horizon, mask_fraction=0.5,
            residual=residual, isf=isf, cr=cr, physics_level=physics_level)

        masked_err = np.mean(np.abs(predicted[mask] - actual[mask]))
        visible_err = np.mean(np.abs(predicted[~mask] - actual[~mask]))
        ratio = masked_err / max(visible_err, 0.01)
        events = classify_window(df, idx, history, horizon)

        results.append({
            'time': str(df.index[idx]),
            'events': events,
            'masked_mae': float(masked_err),
            'visible_mae': float(visible_err),
            'ratio': float(ratio),
        })
    return results


def evaluate_model_similarity(model, features, df, ref_idx, history, horizon,
                               residual, isf, cr, physics_level='enhanced'):
    """Run similarity and classify matches."""
    similar = run_similarity(
        model, features, df, ref_idx, history, horizon,
        top_n=5, stride=6,
        residual=residual, isf=isf, cr=cr, physics_level=physics_level)

    ref_events = classify_window(df, ref_idx, history, horizon)
    for s in similar:
        s['events'] = classify_window(df, s['center_idx'], history, horizon)

    return {
        'reference': {
            'time': str(df.index[ref_idx]),
            'events': ref_events,
            'bg_at_center': float(df['glucose'].values[ref_idx]),
        },
        'similar': similar,
    }


# ── Model configurations ──

MODEL_CONFIGS = [
    {
        'name': 'ae_transfer',
        'label': 'AE Transfer (raw)',
        'checkpoint': 'externals/experiments/ae_transfer.pth',
        'model_type': 'ae',
        'residual': False,
        'description': 'Real-data fine-tuned AE. Best raw reconstruction.',
    },
    {
        'name': 'ae_transfer_residual',
        'label': 'AE Transfer + Physics',
        'checkpoint': 'externals/experiments/ae_transfer.pth',
        'model_type': 'ae',
        'residual': True,
        'description': 'Same AE with enhanced physics baseline. 14.5 MAE reconstruction.',
    },
    {
        'name': 'ae_best',
        'label': 'AE Conformance',
        'checkpoint': 'checkpoints/ae_best.pth',
        'model_type': 'ae',
        'residual': False,
        'description': 'Synthetic-trained on UVA/Padova. Diverse action exposure, forecast-capable.',
    },
    {
        'name': 'grouped_residual',
        'label': 'Grouped + Physics (forecast)',
        'checkpoint': 'externals/experiments/ae_014_grouped_transfer.pth',
        'model_type': 'grouped',
        'residual': True,
        'description': 'GroupedEncoder with physics residual. 0.48 MAE walk-forward validated.',
    },
    {
        'name': 'ae_residual_enhanced',
        'label': 'AE Residual Enhanced',
        'checkpoint': 'externals/experiments/ae_residual_enhanced.pth',
        'model_type': 'ae',
        'residual': True,
        'description': 'AE trained directly on enhanced physics residuals. 0.20 MAE reconstruction in training.',
    },
    {
        'name': 'conditioned',
        'label': 'Conditioned Transformer',
        'checkpoint': 'externals/experiments/conditioned_dropout+wd.pth',
        'model_type': 'conditioned',
        'residual': False,
        'description': 'Conditioned Transformer with dropout+weight decay. Different architecture — history→future prediction.',
    },
]


def run_full_evaluation(data_path: str, output_path: str = None):
    """Run all models through all frames."""
    print('=== Loading data ===')
    df, features = build_nightscout_grid(data_path, verbose=True)
    profile = load_profile(data_path)
    isf, cr = profile['isf'], profile['cr']
    print(f'  Profile: ISF={isf}, CR={cr}, DIA={profile["dia"]}')

    history, horizon = 12, 12

    # Find event-specific windows
    print('\n=== Finding event windows ===')
    event_windows = {}
    for etype in ['uam', 'dawn', 'meal_bolus', 'correction',
                  'exercise_candidate', 'high_volatility', 'stable']:
        windows = find_event_windows(df, features, etype, n=3,
                                     history=history, horizon=horizon)
        event_windows[etype] = windows
        print(f'  {etype}: {len(windows)} windows found')

    # Also get the generic "interesting" windows
    interesting = find_interesting_windows(df, features, n=5,
                                          history=history, horizon=horizon)
    event_windows['interesting'] = interesting

    all_results = {}

    for cfg in MODEL_CONFIGS:
        name = cfg['name']
        print(f'\n{"═" * 60}')
        print(f'  Evaluating: {cfg["label"]}')
        print(f'  Checkpoint: {cfg["checkpoint"]}')
        print(f'{"═" * 60}')

        ckpt_path = cfg['checkpoint']
        if not os.path.exists(ckpt_path):
            print(f'  SKIP: checkpoint not found')
            all_results[name] = {'error': 'checkpoint not found'}
            continue

        try:
            if cfg['model_type'] == 'conditioned':
                # ConditionedTransformer has different architecture/forward signature
                # Skip for now — needs dedicated adapter
                print(f'  SKIP: ConditionedTransformer needs dedicated inference adapter')
                all_results[name] = {
                    'config': cfg,
                    'error': 'ConditionedTransformer not yet supported in hindcast',
                    'note': 'Different forward() signature: (history, actions) → glucose_pred',
                }
                continue
            model, params, meta = load_model(ckpt_path, cfg['model_type'])
        except Exception as e:
            print(f'  SKIP: load error: {e}')
            all_results[name] = {'error': str(e)}
            continue

        res_kw = dict(residual=cfg['residual'], isf=isf, cr=cr,
                      physics_level='enhanced')

        model_result = {
            'config': cfg,
            'params': params,
        }

        # 1. Forecast scan on interesting windows
        print('  [1/6] Forecast scan...')
        model_result['forecast'] = evaluate_model_forecast(
            model, features, df, data_path, interesting,
            history, horizon, 'forecast', **res_kw)

        # 2. Reconstruct scan on interesting windows
        print('  [2/6] Reconstruct scan...')
        model_result['reconstruct'] = evaluate_model_forecast(
            model, features, df, data_path, interesting,
            history, horizon, 'reconstruct', **res_kw)

        # 3. Anomaly scan (top 20)
        print('  [3/6] Anomaly scan...')
        model_result['anomaly'] = evaluate_model_anomaly(
            model, features, df, history, horizon, **res_kw, top_n=20)

        # 4. Counterfactual on event windows
        print('  [4/6] Counterfactual...')
        cf_indices = (event_windows.get('meal_bolus', [])[:2] +
                      event_windows.get('uam', [])[:2] +
                      event_windows.get('correction', [])[:1])
        if cf_indices:
            model_result['counterfactual'] = evaluate_model_counterfactual(
                model, features, df, cf_indices, history, horizon, **res_kw)

        # 5. Imputation on diverse windows
        print('  [5/6] Imputation...')
        imp_indices = (event_windows.get('meal_bolus', [])[:1] +
                       event_windows.get('uam', [])[:1] +
                       event_windows.get('stable', [])[:1])
        if imp_indices:
            model_result['imputation'] = evaluate_model_impute(
                model, features, df, imp_indices, history, horizon, **res_kw)

        # 6. Similarity on UAM and dawn windows
        print('  [6/6] Similarity...')
        sim_results = []
        for etype in ['uam', 'dawn', 'meal_bolus']:
            refs = event_windows.get(etype, [])
            if refs:
                sim = evaluate_model_similarity(
                    model, features, df, refs[0], history, horizon, **res_kw)
                sim['event_type'] = etype
                sim_results.append(sim)
        model_result['similarity'] = sim_results

        # 7. Event-specific forecast accuracy
        print('  [+] Event-specific accuracy...')
        event_accuracy = {}
        for etype in ['uam', 'dawn', 'correction', 'stable']:
            indices = event_windows.get(etype, [])
            if indices:
                event_accuracy[etype] = evaluate_model_forecast(
                    model, features, df, data_path, indices,
                    history, horizon, 'reconstruct', **res_kw)
        model_result['event_accuracy'] = event_accuracy

        all_results[name] = model_result
        print(f'  ✓ Complete')

    # Save results
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f'\n=== Results saved to {output_path} ===')

    return all_results


def print_summary(results: Dict):
    """Print condensed summary of all model evaluations."""
    print(f'\n{"═" * 70}')
    print(f'  MODEL INFERENCE CAPABILITIES SUMMARY')
    print(f'{"═" * 70}')

    for name, data in results.items():
        if 'error' in data:
            continue

        cfg = data['config']
        print(f'\n  {cfg["label"]}')
        print(f'  {"─" * 50}')

        # Forecast summary
        fc = data.get('forecast', [])
        if fc:
            maes = [r['model_mae'] for r in fc if r['model_mae'] is not None]
            if maes:
                print(f'    Forecast:       MAE={np.mean(maes):5.1f} mg/dL ({len(maes)} windows)')

        # Reconstruct summary
        rc = data.get('reconstruct', [])
        if rc:
            maes = [r['model_mae'] for r in rc if r['model_mae'] is not None]
            if maes:
                print(f'    Reconstruct:    MAE={np.mean(maes):5.1f} mg/dL ({len(maes)} windows)')

        # Anomaly event breakdown
        an = data.get('anomaly', [])
        if an:
            event_counts = {}
            for a in an:
                for e in a.get('events', []):
                    event_counts[e] = event_counts.get(e, 0) + 1
            top_events = sorted(event_counts.items(), key=lambda x: -x[1])[:5]
            print(f'    Anomaly top:    {", ".join(f"{e}({c})" for e, c in top_events)}')

        # Counterfactual
        cf = data.get('counterfactual', [])
        if cf:
            effects = [r['mean_treatment_effect'] for r in cf]
            print(f'    Counterfactual: mean effect {np.mean(effects):+.1f} mg/dL')

        # Imputation
        imp = data.get('imputation', [])
        if imp:
            ratios = [r['ratio'] for r in imp]
            print(f'    Imputation:     masked/visible ratio {np.mean(ratios):.1f}x '
                  f'(1.0=causal, >3=copying)')

        # Event-specific accuracy
        ea = data.get('event_accuracy', {})
        for etype, results_list in ea.items():
            maes = [r['model_mae'] for r in results_list if r['model_mae'] is not None]
            if maes:
                print(f'    {etype:<16s} MAE={np.mean(maes):5.1f} mg/dL')

    print(f'\n{"═" * 70}')


def main():
    parser = argparse.ArgumentParser(
        description='Systematic model evaluation with event classification')
    parser.add_argument('--data', required=True,
                        help='Path to Nightscout fixture directory')
    parser.add_argument('--output', default=None,
                        help='Output JSON path (default: stdout summary only)')
    args = parser.parse_args()

    results = run_full_evaluation(args.data, args.output)
    print_summary(results)


if __name__ == '__main__':
    main()
