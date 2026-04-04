"""
experiments_agentic.py — Active Experiment Queue for cgmencode

╔══════════════════════════════════════════════════════════════════╗
║  AGENTS: Add new experiments here using the template below.     ║
║  Keep this file lean. Archive experiments when done.            ║
║  Target: under 500 lines for good token economy.               ║
╚══════════════════════════════════════════════════════════════════╝

Run a single experiment:
    python3 -m tools.cgmencode.run_experiment <key> [--patients-dir ...]

Run a hyperparameter sweep (preferred for systematic exploration):
    python3 -m tools.cgmencode.run_experiments --sweep quick --name exp163

Current baselines (EXP-161/162, honest masking):
    8f  (1h forecast): 29.5 mg/dL MAE, 14% vs persistence  (SATURATED)
    21f (2h forecast): 41.5 mg/dL MAE, 15% vs persistence
    Best config: deep_narrow (d=64, L=6, dropout=0.15, wd=1e-4)

Architecture note: Gen-2 and Gen-3 produce identical forecast results.
    Semantic groups provide zero benefit at current data scale (10 patients).
    See docs/60-research/gen3-transition-report.md for details.

Archives:
    experiments_archive_r1_r13.py  — EXP-026 to EXP-109
    experiments_archive_r14_r30.py — EXP-110 to EXP-238
"""

import json
import os

import numpy as np
import torch

from .experiment_lib import (
    set_seed,
    create_model,
    train_forecast,
    forecast_mse,
    persistence_mse,
    mask_future_channels,
    batch_to_device,
    get_device,
    resolve_patient_paths,
)
from .real_data_adapter import load_multipatient_nightscout
from .schema import (
    NUM_FEATURES,
    NUM_FEATURES_EXTENDED,
    FUTURE_UNKNOWN_CHANNELS,
    IDX_GLUCOSE,
)

# ─── Shared utilities ────────────────────────────────────────────

class _NumpyEncoder(json.JSONEncoder):
    """Handle numpy/torch types in JSON serialization."""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, torch.Tensor):
            return obj.tolist()
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


def save_results(result, path):
    """Save experiment results as formatted JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(result, f, indent=2, cls=_NumpyEncoder)
    print(f"  Results -> {path}")


def compute_mae(model_mse, scale=400.0):
    """Convert normalized MSE to MAE in mg/dL.  MAE = sqrt(MSE) * scale."""
    return (model_mse ** 0.5) * scale


# ─── Experiment Registry ─────────────────────────────────────────
#
# Map experiment keys to function names in THIS file.
# run_experiment.py reads this to dispatch experiments.
#
# To restore an archived experiment:
#   from .experiments_archive_r14_r30 import run_xxx
#   REGISTRY['xxx'] = 'run_xxx'  # and add: run_xxx = run_xxx above
#
REGISTRY = {}


# ═════════════════════════════════════════════════════════════════
#  TEMPLATE — Copy this to create a new experiment
# ═════════════════════════════════════════════════════════════════
#
# def run_my_experiment(args):
#     """EXP-NNN: One-line description.
#
#     Hypothesis: What we expect to learn.
#     Baseline: What we're comparing against (e.g., EXP-162 = 29.5/41.5 mg/dL).
#     """
#     patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
#     output_dir = getattr(args, 'output_dir', 'externals/experiments')
#
#     # ── Load data ──
#     # extended_features=False -> 8 features (1h), True -> 21 features (2h)
#     train_ds, val_ds = load_multipatient_nightscout(
#         patients_dir, extended_features=False,
#     )
#
#     # ── Train ──
#     set_seed(42)
#     model = create_model(input_dim=8, d_model=64, nhead=4, num_layers=2)
#     best_val, epochs = train_forecast(
#         model, train_ds, val_ds,
#         os.path.join(output_dir, 'expNNN_name_s42.pth'),
#         label='EXP-NNN', epochs=150, lr=1e-3, patience=20,
#     )
#
#     # ── Evaluate ──
#     model_mse = forecast_mse(model, val_ds)
#     persist_mse = persistence_mse(val_ds)
#     mae = compute_mae(model_mse)
#     persist_mae = compute_mae(persist_mse)
#
#     result = {
#         'experiment': 'EXP-NNN: Description',
#         'mae_mgdl': round(mae, 1),
#         'persistence_mgdl': round(persist_mae, 1),
#         'pct_vs_persist': round((1 - mae / persist_mae) * 100, 1),
#     }
#     save_results(result, os.path.join(output_dir, 'expNNN_name.json'))
#     return result
#
# REGISTRY['my-experiment'] = 'run_my_experiment'


# ═════════════════════════════════════════════════════════════════
#  ACTIVE EXPERIMENTS — add new experiments below this line
# ═════════════════════════════════════════════════════════════════
