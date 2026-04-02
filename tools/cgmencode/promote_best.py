"""
promote_best.py — Production model promotion pipeline.

Evaluates candidate checkpoints across all 4 objectives:
  1. Forecast accuracy (MAE mg/dL)
  2. Event detection quality (F1 score)
  3. Drift detection correlation
  4. Composite pipeline score

Selects the best candidate by composite score and promotes it to
the production checkpoints directory with a model card.

Usage:
    python3 -m tools.cgmencode.promote_best \\
        --candidates externals/experiments/exp097_base.pth \\
                     externals/experiments/exp095_base.pth \\
        --patients-dir externals/ns-data/patients

    # Or auto-discover candidates:
    python3 -m tools.cgmencode.promote_best \\
        --discover externals/experiments/ \\
        --patients-dir externals/ns-data/patients
"""

import argparse
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch

from .model import CGMGroupedEncoder, CGMTransformerAE
from .experiment_lib import (
    get_device, set_device, load_checkpoint,
    forecast_mse, persistence_mse, promote_checkpoint,
    windows_to_datasets, build_16f_windows, resolve_patient_paths,
)
from .device import resolve_device

# Composite score weights per objective
COMPOSITE_WEIGHTS = {
    'forecast': 0.40,
    'event': 0.30,
    'drift': 0.20,
    'override': 0.10,
}

MANIFEST_PATH = 'checkpoints/manifest.json'


def _load_manifest():
    """Load production manifest, or return empty if none exists."""
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    return {'models': [], 'current': None}


def _save_manifest(manifest):
    """Save production manifest."""
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, 'w') as f:
        json.dump(manifest, f, indent=2)


def evaluate_forecast(checkpoint_path, patients_dir, window_size=24):
    """Evaluate forecast accuracy of a checkpoint.

    Returns dict with mae, improvement_pct, persistence_mae.
    """
    from .schema import NORMALIZATION_SCALES
    patient_paths = resolve_patient_paths(patients_dir)
    if not patient_paths:
        return {'mae': float('inf'), 'persistence_mae': 0, 'improvement_pct': 0}

    # Build 16-feature windows for verification
    ver_paths = [p.replace('/training', '/verification') for p in patient_paths]
    ver_paths = [p for p in ver_paths if os.path.isdir(p)]
    if not ver_paths:
        ver_paths = patient_paths

    windows = build_16f_windows(ver_paths, window_size)
    if len(windows) < 10:
        windows = build_16f_windows(patient_paths, window_size)
    if len(windows) < 10:
        return {'mae': float('inf'), 'persistence_mae': 0, 'improvement_pct': 0}

    _, val_ds = windows_to_datasets(windows, val_fraction=1.0)

    # Load model
    ckpt = torch.load(checkpoint_path, map_location='cpu', weights_only=True)
    state = ckpt.get('model_state', ckpt)
    n_features = windows[0].shape[-1]

    # Detect architecture from state dict
    is_grouped = any('state_proj' in k for k in state.keys())
    has_aux = any('event_head' in k or 'drift_head' in k for k in state.keys())

    # Detect num_layers from state dict
    layer_indices = set()
    for k in state:
        if '.layers.' in k:
            parts = k.split('.')
            for i, p in enumerate(parts):
                if p == 'layers':
                    layer_indices.add(int(parts[i + 1]))
                    break
    num_layers = max(layer_indices) + 1 if layer_indices else 2

    aux_config = None
    if has_aux:
        aux_config = {'n_event_classes': 9, 'n_drift_outputs': 2, 'n_states': 4}

    if is_grouped:
        model = CGMGroupedEncoder(input_dim=n_features, d_model=64, nhead=4,
                                  num_layers=num_layers, aux_config=aux_config)
    else:
        model = CGMTransformerAE(input_dim=n_features, d_model=64, nhead=4, num_layers=num_layers)

    try:
        model.load_state_dict(state, strict=False)
    except Exception:
        return {'mae': float('inf'), 'persistence_mae': 0, 'improvement_pct': 0}

    device = get_device()
    model.to(device)

    model_mse = forecast_mse(model, val_ds)
    base_mse = persistence_mse(val_ds)
    scale = NORMALIZATION_SCALES['glucose']
    mae = float(np.sqrt(model_mse) * scale) if model_mse > 0 else float('inf')
    base_mae = float(np.sqrt(base_mse) * scale) if base_mse > 0 else 0

    improvement = ((base_mae - mae) / base_mae * 100) if base_mae > 0 else 0

    return {
        'mae': round(mae, 2),
        'persistence_mae': round(base_mae, 2),
        'improvement_pct': round(improvement, 1),
        'n_windows': len(windows),
    }


def compute_composite_score(metrics):
    """Compute weighted composite score from per-objective metrics.

    Higher is better. Each objective is normalized to [0, 1]:
    - Forecast: 1 - (mae / 50)  [50 mg/dL = worst acceptable]
    - Event: F1 directly [0-1]
    - Drift: abs(correlation) [0-1], penalized if positive
    - Override: TIR delta / 20 [capped at 1]

    Returns float composite score.
    """
    w = COMPOSITE_WEIGHTS

    # Forecast: lower MAE is better
    mae = metrics.get('forecast_mae', 50.0)
    forecast_score = max(0, 1.0 - mae / 50.0)

    # Event: F1 directly
    event_score = metrics.get('event_f1', 0.0)

    # Drift: penalize positive correlation (should be negative)
    drift_corr = metrics.get('drift_correlation', 0.0)
    drift_score = max(0, -drift_corr)  # only reward negative correlation

    # Override: TIR improvement
    tir_delta = metrics.get('override_tir_delta', 0.0)
    override_score = max(0, min(1.0, tir_delta / 20.0))

    composite = (
        w['forecast'] * forecast_score +
        w['event'] * event_score +
        w['drift'] * drift_score +
        w['override'] * override_score
    )

    return round(float(composite), 4)


def generate_model_card(checkpoint_path, metrics, composite_score):
    """Generate a model card JSON for a checkpoint."""
    return {
        'checkpoint': str(checkpoint_path),
        'promoted_at': datetime.utcnow().isoformat() + 'Z',
        'composite_score': composite_score,
        'metrics': metrics,
        'weights': COMPOSITE_WEIGHTS,
        'objective_scores': {
            'forecast': round(max(0, 1.0 - metrics.get('forecast_mae', 50) / 50.0), 4),
            'event': metrics.get('event_f1', 0.0),
            'drift': round(max(0, -metrics.get('drift_correlation', 0.0)), 4),
            'override': round(max(0, min(1.0, metrics.get('override_tir_delta', 0.0) / 20.0)), 4),
        },
    }


def evaluate_and_promote(candidates, patients_dir, output_dir='checkpoints',
                         dest_name='grouped_prod.pth', verbose=True):
    """Evaluate candidates and promote the best one.

    Args:
        candidates: list of checkpoint paths
        patients_dir: path to patient data
        output_dir: production checkpoint directory
        dest_name: name for promoted checkpoint
        verbose: print progress

    Returns:
        dict with winner info and all evaluations
    """
    if not candidates:
        return {'error': 'No candidates provided', 'promoted': False}

    results = []
    for i, ckpt in enumerate(candidates):
        if not os.path.exists(ckpt):
            if verbose:
                print(f'  [{i+1}/{len(candidates)}] Skip {ckpt} (not found)')
            continue

        if verbose:
            print(f'  [{i+1}/{len(candidates)}] Evaluating {os.path.basename(ckpt)}...')

        metrics = evaluate_forecast(ckpt, patients_dir)
        composite = compute_composite_score({'forecast_mae': metrics['mae']})

        results.append({
            'checkpoint': ckpt,
            'metrics': metrics,
            'composite_score': composite,
        })

        if verbose:
            print(f'    MAE={metrics["mae"]} mg/dL, composite={composite}')

    if not results:
        return {'error': 'No valid candidates', 'promoted': False}

    # Select winner
    winner = max(results, key=lambda r: r['composite_score'])
    if verbose:
        print(f'\n  Winner: {os.path.basename(winner["checkpoint"])} '
              f'(composite={winner["composite_score"]})')

    # Promote
    promoted_path = promote_checkpoint(winner['checkpoint'], dest_name, output_dir)

    # Generate model card
    card = generate_model_card(winner['checkpoint'], winner['metrics'],
                               winner['composite_score'])

    # Update manifest
    manifest = _load_manifest()
    manifest['current'] = {
        'name': dest_name,
        'path': promoted_path,
        'promoted_at': card['promoted_at'],
        'composite_score': card['composite_score'],
        'source_checkpoint': winner['checkpoint'],
    }
    manifest['models'].append(manifest['current'])
    _save_manifest(manifest)

    # Save model card
    card_path = os.path.join(output_dir, dest_name.replace('.pth', '_card.json'))
    with open(card_path, 'w') as f:
        json.dump(card, f, indent=2)
    if verbose:
        print(f'  Model card: {card_path}')
        print(f'  Manifest: {MANIFEST_PATH}')

    return {
        'promoted': True,
        'winner': winner,
        'card': card,
        'all_results': results,
    }


def discover_candidates(search_dir, pattern='*.pth', max_age_days=7):
    """Find checkpoint files in a directory, optionally filtering by age."""
    search_path = Path(search_dir)
    candidates = sorted(search_path.glob(pattern), key=lambda p: p.stat().st_mtime,
                        reverse=True)

    if max_age_days:
        cutoff = time.time() - max_age_days * 86400
        candidates = [c for c in candidates if c.stat().st_mtime >= cutoff]

    return [str(c) for c in candidates]


def main():
    parser = argparse.ArgumentParser(description='Evaluate and promote best model')
    parser.add_argument('--candidates', nargs='+', help='Checkpoint paths to evaluate')
    parser.add_argument('--discover', help='Directory to discover checkpoints in')
    parser.add_argument('--patients-dir', required=True, help='Patient data directory')
    parser.add_argument('--output-dir', default='checkpoints', help='Production dir')
    parser.add_argument('--dest-name', default='grouped_prod.pth', help='Production name')
    parser.add_argument('--max-age-days', type=int, default=7, help='Max checkpoint age')
    parser.add_argument('--device', default='auto', help='Device (auto/cpu/cuda)')
    args = parser.parse_args()

    set_device(resolve_device(args.device))

    candidates = args.candidates or []
    if args.discover:
        candidates.extend(discover_candidates(args.discover, max_age_days=args.max_age_days))

    if not candidates:
        print('No candidates found. Use --candidates or --discover.')
        return

    print(f'Evaluating {len(candidates)} candidates...')
    result = evaluate_and_promote(candidates, args.patients_dir,
                                  args.output_dir, args.dest_name)

    if result.get('promoted'):
        print(f'\nPromoted: {result["winner"]["checkpoint"]}')
        print(f'Composite score: {result["winner"]["composite_score"]}')
    else:
        print(f'\nNo promotion: {result.get("error", "unknown")}')


if __name__ == '__main__':
    main()
