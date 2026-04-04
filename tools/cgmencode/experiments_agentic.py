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
#
# Post-EXP-238 findings:
#   - Selective masking (7-ch) eliminates overfitting: ver gap -6.3% (was +37%)
#   - Gen-2 ensemble (8f,3hr): 12.5 MAE, Gen-3 ensemble (21f,6hr): 16.6 MAE
#   - Projected IOB/COB hurts (+4.6 MAE) — keep raw future IOB/COB
#   - Longer training marginal (early stopping triggers ~100ep anyway)
#   - Hypo baseline: 14.2 MAE for <80 mg/dL timesteps

SCALE = 400.0


def _mae_from_model(model, val_ds, batch_size=64):
    """Compute MAE in mg/dL using selective masking."""
    from torch.utils.data import DataLoader
    device = get_device()
    model.eval()
    total_ae, n = 0.0, 0
    for batch in DataLoader(val_ds, batch_size=batch_size):
        x = batch_to_device(batch[0], device)
        half = x.shape[1] // 2
        x_in = x.clone()
        mask_future_channels(x_in, half)
        with torch.no_grad():
            pred = model(x_in, causal=True)
        if isinstance(pred, dict):
            pred = pred['forecast']
        ae = torch.abs(pred[:, half:, :1] - x[:, half:, :1])
        total_ae += ae.sum().item()
        n += ae.numel()
    return float(total_ae / n * SCALE) if n else float('nan')


def _ensemble_mae(models, val_ds, batch_size=64):
    """Average-ensemble MAE in mg/dL."""
    from torch.utils.data import DataLoader
    device = get_device()
    total_ae, n = 0.0, 0
    for batch in DataLoader(val_ds, batch_size=batch_size):
        x = batch_to_device(batch[0], device)
        half = x.shape[1] // 2
        x_in = x.clone()
        mask_future_channels(x_in, half)
        preds = []
        for m in models:
            m.eval()
            with torch.no_grad():
                p = m(x_in, causal=True)
            if isinstance(p, dict):
                p = p['forecast']
            preds.append(p[:, half:, :1])
        ens = torch.stack(preds).mean(0)
        ae = torch.abs(ens - x[:, half:, :1])
        total_ae += ae.sum().item()
        n += ae.numel()
    return float(total_ae / n * SCALE) if n else float('nan')


# ── EXP-239: Combined Best — Ensemble + Hypo Weighting ───────────
# Combine the two most promising techniques: 5-seed ensemble + hypo
# weighting at the best weight from EXP-235.
# Expected: ensemble ~12.3, hypo <13 (best of both worlds).
def run_combined_ensemble_hypo(args):
    """EXP-239: 5-seed ensemble where each model uses hypo-weighted loss."""
    from torch.utils.data import DataLoader
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')

    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)

    hypo_thresh = 80.0 / SCALE
    hypo_weight = 5.0  # best from EXP-235 (to be confirmed)
    seeds = [42, 123, 456, 789, 1024]
    models, individual = [], {}
    device = get_device()

    for seed in seeds:
        set_seed(seed)
        model = create_model(arch='grouped', input_dim=8, d_model=64,
                             nhead=4, num_layers=2)
        model.to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
        train_dl = DataLoader(train_ds, batch_size=32, shuffle=True)
        best_val, stale = float('inf'), 0
        save_path = os.path.join(output_dir, f'exp239_combined_s{seed}.pth')

        for ep in range(100):
            model.train()
            for b in train_dl:
                x = batch_to_device(b[0], device)
                half = x.shape[1] // 2
                x_in = x.clone()
                mask_future_channels(x_in, half)
                pred = model(x_in, causal=True)
                if isinstance(pred, dict):
                    pred = pred['forecast']
                pred_g, true_g = pred[:, half:, :1], x[:, half:, :1]
                w = torch.ones_like(true_g)
                w[true_g < hypo_thresh] = hypo_weight
                loss = (w * (pred_g - true_g) ** 2).mean()
                opt.zero_grad()
                loss.backward()
                opt.step()

            model.eval()
            vtl, vn = 0.0, 0
            with torch.no_grad():
                for b in DataLoader(val_ds, batch_size=64):
                    x = batch_to_device(b[0], device)
                    half = x.shape[1] // 2
                    x_in = x.clone()
                    mask_future_channels(x_in, half)
                    pred = model(x_in, causal=True)
                    if isinstance(pred, dict):
                        pred = pred['forecast']
                    vtl += ((pred[:, half:, :1] - x[:, half:, :1]) ** 2).mean().item() * x.shape[0]
                    vn += x.shape[0]
            vl = vtl / vn
            sched.step(vl)
            if vl < best_val:
                best_val, stale = vl, 0
                os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
                torch.save({'model_state': model.state_dict()}, save_path)
            else:
                stale += 1
            if stale >= 15:
                break

        if os.path.exists(save_path):
            ckpt = torch.load(save_path, map_location=device, weights_only=False)
            model.load_state_dict(ckpt['model_state'])

        mae = _mae_from_model(model, val_ds)
        individual[f's{seed}'] = {'mae': round(mae, 2)}
        models.append(model)
        print(f"  s{seed}: MAE={mae:.1f}")

    ens = _ensemble_mae(models, val_ds)
    result = {
        'experiment': 'EXP-239: Combined Ensemble + Hypo Weighting',
        'config': {'hypo_weight': hypo_weight, 'seeds': seeds, 'epochs': 100},
        'masking': {'channels': list(FUTURE_UNKNOWN_CHANNELS), 'type': 'selective'},
        'individual': individual,
        'ensemble_mae': round(ens, 2),
        'comparison': {'exp232_ensemble': 12.5, 'exp235_baseline_hypo': 14.2},
    }
    save_results(result, os.path.join(output_dir, 'exp239_combined_ensemble_hypo.json'))
    return result

REGISTRY['combined-ensemble-hypo'] = 'run_combined_ensemble_hypo'


# ── EXP-240: Curriculum Learning — Calm→Volatile ─────────────────
# Train first on "easy" windows (low glucose variance), then add
# volatile windows. Should help the model learn basic patterns
# before confronting challenging dynamics.
def run_curriculum_calm_volatile(args):
    """EXP-240: Curriculum learning from calm to volatile windows."""
    from torch.utils.data import DataLoader, Subset
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')

    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)
    device = get_device()

    # Compute per-window glucose variance for curriculum ordering
    variances = []
    for i in range(len(train_ds)):
        x = train_ds[i][0]
        variances.append(x[:, 0].var().item())  # glucose channel variance
    variances = np.array(variances)
    sorted_idx = np.argsort(variances)
    n = len(sorted_idx)

    # Phase 1: calm 50%, Phase 2: all data
    calm_idx = sorted_idx[:n // 2].tolist()
    calm_ds = Subset(train_ds, calm_idx)

    set_seed(42)
    model = create_model(arch='grouped', input_dim=8, d_model=64,
                         nhead=4, num_layers=2)
    # Phase 1: 30 epochs on calm data
    save_p1 = os.path.join(output_dir, 'exp240_curriculum_p1.pth')
    train_forecast(model, calm_ds, val_ds, save_p1,
                   label='EXP-240 Phase1-Calm', epochs=30, lr=1e-3, patience=10)
    p1_mae = _mae_from_model(model, val_ds)
    print(f"  Phase 1 (calm 50%): MAE={p1_mae:.1f}")

    # Phase 2: full data with lower lr
    save_p2 = os.path.join(output_dir, 'exp240_curriculum_s42.pth')
    train_forecast(model, train_ds, val_ds, save_p2,
                   label='EXP-240 Phase2-Full', epochs=70, lr=3e-4, patience=15)
    p2_mae = _mae_from_model(model, val_ds)
    print(f"  Phase 2 (full): MAE={p2_mae:.1f}")

    # Baseline: standard training on full data
    set_seed(42)
    model_base = create_model(arch='grouped', input_dim=8, d_model=64,
                              nhead=4, num_layers=2)
    save_base = os.path.join(output_dir, 'exp240_baseline_s42.pth')
    train_forecast(model_base, train_ds, val_ds, save_base,
                   label='EXP-240 Baseline', epochs=100, lr=1e-3, patience=15)
    base_mae = _mae_from_model(model_base, val_ds)
    print(f"  Baseline: MAE={base_mae:.1f}")

    result = {
        'experiment': 'EXP-240: Curriculum Learning (Calm → Volatile)',
        'results': {
            'phase1_calm_mae': round(p1_mae, 2),
            'phase2_full_mae': round(p2_mae, 2),
            'baseline_mae': round(base_mae, 2),
            'delta': round(p2_mae - base_mae, 2),
        },
        'config': {'calm_fraction': 0.5, 'p1_epochs': 30, 'p2_epochs': 70},
        'comparison': {'exp232_individual': 12.9},
    }
    save_results(result, os.path.join(output_dir, 'exp240_curriculum.json'))
    return result

REGISTRY['curriculum-calm-volatile'] = 'run_curriculum_calm_volatile'


# ── EXP-241: Per-Patient Fine-Tuning from Ensemble Base ──────────
# Start from best ensemble member, fine-tune on each patient's data.
# Measures how much per-patient adaptation helps on top of the
# multi-patient base model.
def run_per_patient_finetune(args):
    """EXP-241: Per-patient fine-tuning from best multi-patient model."""
    from torch.utils.data import DataLoader
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')

    patients_base = patients_dir if patients_dir else 'externals/ns-data/patients'
    patient_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])

    # Load base model (best from EXP-232)
    base_path = os.path.join(output_dir, 'exp232_ens_s42.pth')
    if not os.path.exists(base_path):
        # Fall back to training a fresh base
        patient_paths = resolve_patient_paths(patients_dir)
        train_ds, val_ds = load_multipatient_nightscout(
            patient_paths, task='forecast', window_size=24)
        set_seed(42)
        base_model = create_model(arch='grouped', input_dim=8, d_model=64,
                                  nhead=4, num_layers=2)
        base_path = os.path.join(output_dir, 'exp241_base_s42.pth')
        train_forecast(base_model, train_ds, val_ds, base_path,
                       label='EXP-241 Base', epochs=100, lr=1e-3, patience=15)
    device = get_device()

    results = {}
    for pid in patient_dirs:
        train_path = os.path.join(patients_base, pid, 'training')
        ver_path = os.path.join(patients_base, pid, 'verification')
        if not os.path.isdir(train_path):
            continue
        try:
            train_ds_p, val_ds_p = load_multipatient_nightscout(
                [train_path], task='forecast', window_size=24)
        except Exception:
            continue
        if len(val_ds_p) < 10:
            continue

        # Evaluate base model on this patient
        set_seed(42)
        base_m = create_model(arch='grouped', input_dim=8, d_model=64,
                              nhead=4, num_layers=2)
        ckpt = torch.load(base_path, map_location=device, weights_only=False)
        base_m.load_state_dict(ckpt['model_state'])
        base_m.to(device)
        base_mae = _mae_from_model(base_m, val_ds_p)

        # Fine-tune with low lr, few epochs
        ft_model = create_model(arch='grouped', input_dim=8, d_model=64,
                                nhead=4, num_layers=2)
        ft_model.load_state_dict(ckpt['model_state'])
        ft_path = os.path.join(output_dir, f'exp241_ft_{pid}.pth')
        train_forecast(ft_model, train_ds_p, val_ds_p, ft_path,
                       label=f'EXP-241 FT-{pid}', epochs=30, lr=1e-4, patience=10)
        ft_mae = _mae_from_model(ft_model, val_ds_p)

        results[pid] = {
            'base_mae': round(base_mae, 2),
            'finetune_mae': round(ft_mae, 2),
            'delta': round(ft_mae - base_mae, 2),
            'n_train': len(train_ds_p), 'n_val': len(val_ds_p),
        }
        print(f"  {pid}: base={base_mae:.1f} ft={ft_mae:.1f} Δ={ft_mae-base_mae:+.1f}")

    mean_base = np.mean([r['base_mae'] for r in results.values()])
    mean_ft = np.mean([r['finetune_mae'] for r in results.values()])

    result = {
        'experiment': 'EXP-241: Per-Patient Fine-Tuning',
        'per_patient': results,
        'summary': {
            'mean_base_mae': round(float(mean_base), 2),
            'mean_finetune_mae': round(float(mean_ft), 2),
            'mean_delta': round(float(mean_ft - mean_base), 2),
        },
    }
    save_results(result, os.path.join(output_dir, 'exp241_per_patient_finetune.json'))
    return result

REGISTRY['per-patient-finetune'] = 'run_per_patient_finetune'
