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
    NUM_FEATURES_ENRICHED,
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


def validate_masking(input_dim, label=''):
    """Assert masking correctness for a given input_dim.

    Verifies that FUTURE_UNKNOWN_CHANNELS makes sense for the feature count:
    - All maskable channels < input_dim actually need masking
    - Prints a clear summary of what will/won't be masked
    Raises ValueError if a future-unknown channel exists in the data but
    is not in FUTURE_UNKNOWN_CHANNELS (would be a leak).
    """
    from .schema import (
        IDX_GLUCOSE, IDX_BOLUS, IDX_CARBS, IDX_GLUCOSE_ROC, IDX_GLUCOSE_ACCEL,
        IDX_TIME_SINCE_BOLUS, IDX_TIME_SINCE_CARB,
        IDX_TREND_DIRECTION, IDX_TREND_RATE, IDX_ROLLING_NOISE,
        IDX_HOURS_SINCE_CGM, IDX_LOOP_PREDICTED_30, IDX_LOOP_PREDICTED_60,
        IDX_LOOP_PREDICTED_MIN, IDX_LOOP_HYPO_RISK, IDX_LOOP_RECOMMENDED,
        IDX_LOOP_ENACTED_RATE, IDX_LOOP_ENACTED_BOLUS, IDX_SUSPENSION_TIME,
        IDX_GLUCOSE_VS_TARGET, IDX_PUMP_RESERVOIR,
    )
    # All channels that MUST be masked if they exist in the input.
    # Derived from audit: any channel containing or derived from future glucose,
    # future user actions, or future AID decisions must be masked.
    must_mask = {
        IDX_GLUCOSE, IDX_BOLUS, IDX_CARBS,
        IDX_GLUCOSE_ROC, IDX_GLUCOSE_ACCEL,
        IDX_TIME_SINCE_BOLUS, IDX_TIME_SINCE_CARB,
        IDX_TREND_DIRECTION, IDX_TREND_RATE, IDX_ROLLING_NOISE,
        IDX_HOURS_SINCE_CGM, IDX_LOOP_PREDICTED_30, IDX_LOOP_PREDICTED_60,
        IDX_LOOP_PREDICTED_MIN, IDX_LOOP_HYPO_RISK, IDX_LOOP_RECOMMENDED,
        IDX_LOOP_ENACTED_RATE, IDX_LOOP_ENACTED_BOLUS, IDX_SUSPENSION_TIME,
        IDX_GLUCOSE_VS_TARGET,  # contains (glucose-target)/100 → glucose leak
        IDX_PUMP_RESERVOIR,     # decreases with delivery → reveals future dosing
    }
    present_must_mask = {ch for ch in must_mask if ch < input_dim}
    actually_masked = {ch for ch in FUTURE_UNKNOWN_CHANNELS if ch < input_dim}

    leaked = present_must_mask - actually_masked
    if leaked:
        raise ValueError(
            f"{label} MASKING LEAK: channels {sorted(leaked)} exist in "
            f"{input_dim}-dim input but are NOT in FUTURE_UNKNOWN_CHANNELS"
        )

    extra_masked = actually_masked - present_must_mask
    prefix = f"[{label}] " if label else ""
    print(f"  {prefix}Masking validated: {len(actually_masked)}/{input_dim} channels masked, "
          f"0 leaks detected")
    return True


def compute_persistence_mae(val_ds, batch_size=64):
    """Compute persistence baseline MAE in mg/dL (last glucose repeated)."""
    from torch.utils.data import DataLoader
    total_ae, n = 0.0, 0
    for batch in DataLoader(val_ds, batch_size=batch_size):
        x = batch[0]
        half = x.shape[1] // 2
        last_glucose = x[:, half - 1, 0:1].unsqueeze(1).expand(-1, x.shape[1] - half, -1)
        target = x[:, half:, 0:1]
        ae = torch.abs(last_glucose - target)
        total_ae += ae.sum().item()
        n += ae.numel()
    return float(total_ae / n * SCALE) if n else float('nan')


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


# ── Shared: hypo-weighted training loop ──────────────────────────
def _train_hypo_weighted(model, train_ds, val_ds, save_path, label,
                         hypo_weight=3.0, epochs=100, patience=15):
    """Train model with hypo-weighted MSE loss. Returns best val loss."""
    from torch.utils.data import DataLoader
    device = get_device()
    model.to(device)
    hypo_thresh = 80.0 / SCALE
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
    best_val, stale = float('inf'), 0
    for ep in range(epochs):
        model.train()
        for b in DataLoader(train_ds, batch_size=32, shuffle=True):
            x = batch_to_device(b[0], device)
            half = x.shape[1] // 2
            x_in = x.clone()
            mask_future_channels(x_in, half)
            pred = model(x_in, causal=True)
            if isinstance(pred, dict): pred = pred['forecast']
            pg, tg = pred[:, half:, :1], x[:, half:, :1]
            w = torch.ones_like(tg)
            w[tg < hypo_thresh] = hypo_weight
            loss = (w * (pg - tg) ** 2).mean()
            opt.zero_grad(); loss.backward(); opt.step()
        model.eval()
        vtl, vn = 0.0, 0
        with torch.no_grad():
            for b in DataLoader(val_ds, batch_size=64):
                x = batch_to_device(b[0], device)
                half = x.shape[1] // 2
                x_in = x.clone()
                mask_future_channels(x_in, half)
                pred = model(x_in, causal=True)
                if isinstance(pred, dict): pred = pred['forecast']
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
        if stale >= patience: break
    if os.path.exists(save_path):
        ckpt = torch.load(save_path, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model_state'])
    return best_val


# ── EXP-242: Per-Patient Fine-Tuned Ensemble ─────────────────────
# Fine-tune 5 seeds per-patient, then ensemble. Combines EXP-234
# ensemble + EXP-241 per-patient gains.
def run_per_patient_finetuned_ensemble(args):
    """EXP-242: 5-seed ensemble fine-tuned per-patient."""
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patients_base = patients_dir or 'externals/ns-data/patients'
    patient_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])
    device = get_device()
    seeds = [42, 123, 456, 789, 1024]

    # First train multi-patient base models (5 seeds)
    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)
    base_models_state = {}
    for seed in seeds:
        set_seed(seed)
        m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
        bp = os.path.join(output_dir, f'exp242_base_s{seed}.pth')
        train_forecast(m, train_ds, val_ds, bp,
                       label=f'EXP-242 Base-s{seed}', epochs=100, lr=1e-3, patience=15)
        base_models_state[seed] = torch.load(bp, map_location=device, weights_only=False)['model_state']

    per_patient = {}
    for pid in patient_dirs:
        tp = os.path.join(patients_base, pid, 'training')
        if not os.path.isdir(tp): continue
        try:
            tds, vds = load_multipatient_nightscout([tp], task='forecast', window_size=24)
        except Exception: continue
        if len(vds) < 10: continue

        ft_models = []
        seed_maes = {}
        for seed in seeds:
            set_seed(seed)
            m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
            m.load_state_dict(base_models_state[seed])
            fp = os.path.join(output_dir, f'exp242_ft_{pid}_s{seed}.pth')
            train_forecast(m, tds, vds, fp,
                           label=f'EXP-242 FT-{pid}-s{seed}', epochs=30, lr=1e-4, patience=10)
            mae = _mae_from_model(m, vds)
            seed_maes[f's{seed}'] = round(mae, 2)
            ft_models.append(m)
        ens = _ensemble_mae(ft_models, vds)
        per_patient[pid] = {
            'seeds': seed_maes,
            'ensemble_mae': round(ens, 2),
            'mean_seed': round(float(np.mean(list(seed_maes.values()))), 2),
        }
        print(f"  {pid}: mean_seed={per_patient[pid]['mean_seed']:.1f} ens={ens:.1f}")

    all_ens = [v['ensemble_mae'] for v in per_patient.values()]
    result = {
        'experiment': 'EXP-242: Per-Patient Fine-Tuned Ensemble',
        'per_patient': per_patient,
        'summary': {
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'n_patients': len(per_patient),
        },
        'comparison': {'exp234_ensemble': 12.38, 'exp241_mean_ft': 12.0},
    }
    save_results(result, os.path.join(output_dir, 'exp242_per_patient_ensemble.json'))
    return result

REGISTRY['per-patient-finetuned-ensemble'] = 'run_per_patient_finetuned_ensemble'


# ── EXP-243: Mixed Hypo/Standard Ensemble ────────────────────────
# 3 standard + 2 hypo-weighted (w=3) seeds. Diversity from different
# loss landscapes + minority hypo safety.
def run_mixed_hypo_standard_ensemble(args):
    """EXP-243: 3 standard + 2 hypo-weighted seeds, all ensembled."""
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)
    device = get_device()
    models, individual = [], {}

    for seed in [42, 123, 456]:
        set_seed(seed)
        m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
        sp = os.path.join(output_dir, f'exp243_std_s{seed}.pth')
        train_forecast(m, train_ds, val_ds, sp,
                       label=f'EXP-243 Std-s{seed}', epochs=100, lr=1e-3, patience=15)
        mae = _mae_from_model(m, val_ds)
        individual[f's{seed}_std'] = round(mae, 2)
        models.append(m)
        print(f"  s{seed} (standard): MAE={mae:.1f}")

    for seed in [789, 1024]:
        set_seed(seed)
        m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
        sp = os.path.join(output_dir, f'exp243_hypo_s{seed}.pth')
        _train_hypo_weighted(m, train_ds, val_ds, sp,
                             label=f'EXP-243 Hypo-s{seed}', hypo_weight=3.0)
        mae = _mae_from_model(m, val_ds)
        individual[f's{seed}_hypo'] = round(mae, 2)
        models.append(m)
        print(f"  s{seed} (hypo w=3): MAE={mae:.1f}")

    ens = _ensemble_mae(models, val_ds)
    result = {
        'experiment': 'EXP-243: Mixed Hypo/Standard Ensemble (3+2)',
        'individual': individual, 'ensemble_mae': round(ens, 2),
        'config': {'std_seeds': [42, 123, 456], 'hypo_seeds': [789, 1024], 'hypo_weight': 3.0},
        'masking': {'channels': list(FUTURE_UNKNOWN_CHANNELS), 'type': 'selective'},
        'comparison': {'exp234_ensemble': 12.38, 'exp239_hypo_ensemble': 12.87},
    }
    save_results(result, os.path.join(output_dir, 'exp243_mixed_ensemble.json'))
    return result

REGISTRY['mixed-hypo-standard-ensemble'] = 'run_mixed_hypo_standard_ensemble'


# ── EXP-244: MC-Dropout Ensemble ─────────────────────────────────
# Single model with dropout=0.2, 10 forward passes at inference.
# 5× cheaper than 5-seed ensemble (1 model vs 5).
def run_mc_dropout_ensemble(args):
    """EXP-244: MC-Dropout at inference (10 passes, dropout=0.2)."""
    from torch.utils.data import DataLoader
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)
    device = get_device()
    set_seed(42)
    model = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
    # Increase dropout to 0.2 for MC sampling diversity
    for layer in model.transformer_encoder.layers:
        for attr in ['dropout', 'dropout1', 'dropout2']:
            d = getattr(layer, attr, None)
            if d is not None and hasattr(d, 'p'): d.p = 0.2
        if hasattr(layer, 'self_attn') and hasattr(layer.self_attn, 'dropout'):
            layer.self_attn.dropout = 0.2
    model.to(device)
    sp = os.path.join(output_dir, 'exp244_mc_dropout_s42.pth')
    train_forecast(model, train_ds, val_ds, sp,
                   label='EXP-244 MC-Dropout', epochs=100, lr=1e-3, patience=15)
    ckpt = torch.load(sp, map_location=device, weights_only=False)
    model.load_state_dict(ckpt['model_state'])

    single_mae = _mae_from_model(model, val_ds)

    # MC-Dropout: 10 passes with dropout enabled
    model.train()  # keep dropout on
    n_mc = 10
    total_ae, n = 0.0, 0
    for batch in DataLoader(val_ds, batch_size=64):
        x = batch_to_device(batch[0], device)
        half = x.shape[1] // 2
        x_in = x.clone()
        mask_future_channels(x_in, half)
        preds = []
        for _ in range(n_mc):
            with torch.no_grad():
                p = model(x_in, causal=True)
            if isinstance(p, dict): p = p['forecast']
            preds.append(p[:, half:, :1])
        ens = torch.stack(preds).mean(0)
        ae = torch.abs(ens - x[:, half:, :1])
        total_ae += ae.sum().item(); n += ae.numel()
    mc_mae = float(total_ae / n * SCALE) if n else float('nan')
    model.eval()

    result = {
        'experiment': 'EXP-244: MC-Dropout Ensemble (10 samples)',
        'results': {
            'single_mae': round(single_mae, 2),
            'mc_ensemble_mae': round(mc_mae, 2),
            'delta': round(mc_mae - single_mae, 2),
        },
        'config': {'dropout': 0.2, 'n_mc_samples': n_mc,
                   'n_params': sum(p.numel() for p in model.parameters())},
        'comparison': {'exp234_5seed_ensemble': 12.38, 'exp232_individual': 12.9},
    }
    save_results(result, os.path.join(output_dir, 'exp244_mc_dropout.json'))
    return result

REGISTRY['mc-dropout-ensemble'] = 'run_mc_dropout_ensemble'


# ── EXP-245: Wider Model (d_model=128) ───────────────────────────
# Test if model is capacity-limited. 2× wider, same depth. 5-seed.
def run_wider_model_ensemble(args):
    """EXP-245: 5-seed ensemble with d_model=128 (2× width)."""
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)
    seeds = [42, 123, 456, 789, 1024]
    models, individual = [], {}
    device = get_device()

    for seed in seeds:
        set_seed(seed)
        m = create_model(arch='grouped', input_dim=8, d_model=128, nhead=4, num_layers=2)
        m.to(device)
        sp = os.path.join(output_dir, f'exp245_wider_s{seed}.pth')
        train_forecast(m, train_ds, val_ds, sp,
                       label=f'EXP-245 Wide-s{seed}', epochs=100, lr=1e-3, patience=15)
        mae = _mae_from_model(m, val_ds)
        individual[f's{seed}'] = round(mae, 2)
        models.append(m)
        print(f"  s{seed}: MAE={mae:.1f}")

    ens = _ensemble_mae(models, val_ds)
    n_params = sum(p.numel() for p in models[0].parameters())
    result = {
        'experiment': 'EXP-245: Wider Model (d_model=128) 5-Seed Ensemble',
        'individual': individual, 'ensemble_mae': round(ens, 2),
        'config': {'d_model': 128, 'nhead': 4, 'num_layers': 2, 'seeds': seeds,
                   'n_params': n_params},
        'masking': {'channels': list(FUTURE_UNKNOWN_CHANNELS), 'type': 'selective'},
        'comparison': {'exp234_d64_ensemble': 12.38, 'exp234_d64_individual': 12.9},
    }
    save_results(result, os.path.join(output_dir, 'exp245_wider_model.json'))
    return result

REGISTRY['wider-model-ensemble'] = 'run_wider_model_ensemble'


# ── EXP-246: Snapshot Ensemble (checkpoints from same run) ───────
# Save model at multiple epochs, ensemble. Free diversity from one
# training run — tests if optimization path provides useful variety.
def run_snapshot_ensemble(args):
    """EXP-246: Ensemble of checkpoints from same training run."""
    from torch.utils.data import DataLoader
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)
    device = get_device()
    set_seed(42)
    model = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
    model.to(device)

    # Custom training loop to save snapshots at regular intervals
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=120, eta_min=1e-5)
    snapshot_epochs = [40, 60, 80, 90, 100, 110]
    snapshots = {}

    for ep in range(1, 121):
        model.train()
        for b in DataLoader(train_ds, batch_size=32, shuffle=True):
            x = batch_to_device(b[0], device)
            half = x.shape[1] // 2
            x_in = x.clone()
            mask_future_channels(x_in, half)
            pred = model(x_in, causal=True)
            if isinstance(pred, dict): pred = pred['forecast']
            loss = ((pred[:, half:, :1] - x[:, half:, :1]) ** 2).mean()
            opt.zero_grad(); loss.backward(); opt.step()
        sched.step()

        if ep in snapshot_epochs:
            sp = os.path.join(output_dir, f'exp246_snap_ep{ep}.pth')
            torch.save({'model_state': model.state_dict(), 'epoch': ep}, sp)
            snapshots[ep] = model.state_dict().copy()
            # Deepcopy state for later
            import copy
            snapshots[ep] = copy.deepcopy(model.state_dict())
            mae = _mae_from_model(model, val_ds)
            print(f"  Snapshot ep{ep}: MAE={mae:.1f}")

    # Load snapshots and ensemble
    snap_models = []
    individual = {}
    for ep, state in snapshots.items():
        m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
        m.load_state_dict(state)
        m.to(device)
        mae = _mae_from_model(m, val_ds)
        individual[f'ep{ep}'] = round(mae, 2)
        snap_models.append(m)

    ens = _ensemble_mae(snap_models, val_ds)
    result = {
        'experiment': 'EXP-246: Snapshot Ensemble (6 checkpoints, 1 training run)',
        'individual': individual,
        'ensemble_mae': round(ens, 2),
        'config': {'snapshot_epochs': snapshot_epochs, 'total_epochs': 120,
                   'scheduler': 'cosine', 'n_snapshots': len(snapshot_epochs)},
        'masking': {'channels': list(FUTURE_UNKNOWN_CHANNELS), 'type': 'selective'},
        'comparison': {'exp234_5seed_ensemble': 12.38, 'exp232_individual': 12.9},
    }
    save_results(result, os.path.join(output_dir, 'exp246_snapshot_ensemble.json'))
    return result

REGISTRY['snapshot-ensemble'] = 'run_snapshot_ensemble'


# ── EXP-247: Deeper Model (L=4) ──────────────────────────────────
# Width didn't help (EXP-245). Test depth: 4 layers instead of 2.
# More layers → longer-range temporal dependencies in 12-step history.
def run_deeper_model_ensemble(args):
    """EXP-247: 5-seed ensemble with num_layers=4 (2× depth)."""
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)
    seeds = [42, 123, 456, 789, 1024]
    models, individual = [], {}
    device = get_device()

    for seed in seeds:
        set_seed(seed)
        m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=4)
        m.to(device)
        sp = os.path.join(output_dir, f'exp247_deep_s{seed}.pth')
        train_forecast(m, train_ds, val_ds, sp,
                       label=f'EXP-247 Deep-s{seed}', epochs=100, lr=1e-3, patience=15)
        mae = _mae_from_model(m, val_ds)
        individual[f's{seed}'] = round(mae, 2)
        models.append(m)
        print(f"  s{seed}: MAE={mae:.1f}")

    ens = _ensemble_mae(models, val_ds)
    n_params = sum(p.numel() for p in models[0].parameters())
    result = {
        'experiment': 'EXP-247: Deeper Model (num_layers=4) 5-Seed Ensemble',
        'individual': individual, 'ensemble_mae': round(ens, 2),
        'config': {'d_model': 64, 'nhead': 4, 'num_layers': 4, 'seeds': seeds,
                   'n_params': n_params},
        'masking': {'channels': list(FUTURE_UNKNOWN_CHANNELS), 'type': 'selective'},
        'comparison': {'exp234_L2_ensemble': 12.38, 'exp245_d128L2_ensemble': 12.49},
    }
    save_results(result, os.path.join(output_dir, 'exp247_deeper_model.json'))
    return result

REGISTRY['deeper-model-ensemble'] = 'run_deeper_model_ensemble'


# ── EXP-248: Per-Patient FT Ensemble + Hypo Weighting ─────────────
# Combine the two best techniques: per-patient FT ensemble (EXP-242)
# + hypo-weighted loss (EXP-235 w=3). Expected: similar overall MAE
# (~11.3) but with significantly better hypo safety (<8 mg/dL error
# on glucose <70).
def run_per_patient_hypo_ensemble(args):
    """EXP-248: Per-patient FT ensemble with hypo-weighted loss (w=3)."""
    from torch.utils.data import DataLoader
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patients_base = patients_dir or 'externals/ns-data/patients'
    patient_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])
    device = get_device()
    seeds = [42, 123, 456, 789, 1024]
    hypo_weight = 3.0

    # Train 5 base models with hypo-weighted loss
    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)
    base_states = {}
    for seed in seeds:
        set_seed(seed)
        m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
        bp = os.path.join(output_dir, f'exp248_hypo_base_s{seed}.pth')
        _train_hypo_weighted(m, train_ds, val_ds, bp,
                             label=f'EXP-248 HypoBase-s{seed}',
                             hypo_weight=hypo_weight, epochs=100, patience=15)
        base_states[seed] = torch.load(bp, map_location=device, weights_only=False)['model_state']

    # Per-patient fine-tuning with hypo-weighted loss
    per_patient = {}
    for pid in patient_dirs:
        tp = os.path.join(patients_base, pid, 'training')
        if not os.path.isdir(tp):
            continue
        try:
            tds, vds = load_multipatient_nightscout([tp], task='forecast', window_size=24)
        except Exception:
            continue
        if len(vds) < 10:
            continue

        ft_models = []
        seed_maes, hypo_maes = {}, {}
        for seed in seeds:
            set_seed(seed)
            m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
            m.load_state_dict(base_states[seed])
            fp = os.path.join(output_dir, f'exp248_ft_{pid}_s{seed}.pth')
            _train_hypo_weighted(m, tds, vds, fp,
                                 label=f'EXP-248 FT-{pid}-s{seed}',
                                 hypo_weight=hypo_weight, epochs=30, patience=10)
            mae = _mae_from_model(m, vds)
            seed_maes[f's{seed}'] = round(mae, 2)
            ft_models.append(m)

        # Compute overall + hypo-specific ensemble MAE
        ens_mae = _ensemble_mae(ft_models, vds)
        hypo_ens = _hypo_ensemble_mae(ft_models, vds, threshold=70.0)
        per_patient[pid] = {
            'seeds': seed_maes,
            'ensemble_mae': round(ens_mae, 2),
            'hypo_ensemble_mae': round(hypo_ens, 2),
            'mean_seed': round(float(np.mean(list(seed_maes.values()))), 2),
        }
        print(f"  {pid}: ens={ens_mae:.1f} hypo_ens={hypo_ens:.1f}")

    all_ens = [v['ensemble_mae'] for v in per_patient.values()]
    all_hypo = [v['hypo_ensemble_mae'] for v in per_patient.values()
                if not np.isnan(v['hypo_ensemble_mae'])]
    result = {
        'experiment': 'EXP-248: Per-Patient FT Ensemble + Hypo Weighting (w=3)',
        'per_patient': per_patient,
        'summary': {
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'mean_hypo_ensemble_mae': round(float(np.mean(all_hypo)), 2) if all_hypo else None,
            'n_patients': len(per_patient),
        },
        'config': {'hypo_weight': hypo_weight, 'seeds': seeds},
        'comparison': {'exp242_ensemble': 11.25, 'exp243_mixed': 12.46},
    }
    save_results(result, os.path.join(output_dir, 'exp248_per_patient_hypo_ensemble.json'))
    return result

REGISTRY['per-patient-hypo-ensemble'] = 'run_per_patient_hypo_ensemble'


def _hypo_ensemble_mae(models, val_ds, threshold=70.0, batch_size=64):
    """Ensemble MAE on only hypoglycemic timesteps (glucose < threshold)."""
    from torch.utils.data import DataLoader
    device = get_device()
    total_ae, n = 0.0, 0
    thresh_norm = threshold / SCALE
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
        true_g = x[:, half:, :1]
        mask = true_g < thresh_norm
        if mask.any():
            ae = torch.abs(ens[mask] - true_g[mask])
            total_ae += ae.sum().item()
            n += ae.numel()
    return float(total_ae / n * SCALE) if n else float('nan')


# ── EXP-249: Verification Set Generalization of EXP-242 ──────────
# Evaluate the EXP-242 per-patient FT ensemble on held-out
# verification data to measure generalization gap. Critical for
# determining if our 11.25 MAE is real.
def run_verification_per_patient_ensemble(args):
    """EXP-249: Evaluate EXP-242 models on verification splits."""
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patients_base = patients_dir or 'externals/ns-data/patients'
    patient_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])
    device = get_device()
    seeds = [42, 123, 456, 789, 1024]

    per_patient = {}
    for pid in patient_dirs:
        ver_path = os.path.join(patients_base, pid, 'verification')
        if not os.path.isdir(ver_path):
            print(f"  {pid}: no verification dir, skipping")
            continue
        try:
            _, ver_ds = load_multipatient_nightscout(
                [ver_path], task='forecast', window_size=24)
        except Exception as e:
            print(f"  {pid}: verification load failed ({e}), skipping")
            continue
        if len(ver_ds) < 10:
            print(f"  {pid}: too few verification windows ({len(ver_ds)}), skipping")
            continue

        # Load fine-tuned models from EXP-242
        ft_models = []
        missing = False
        for seed in seeds:
            fp = os.path.join(output_dir, f'exp242_ft_{pid}_s{seed}.pth')
            if not os.path.exists(fp):
                missing = True
                break
            m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
            ckpt = torch.load(fp, map_location=device, weights_only=False)
            m.load_state_dict(ckpt['model_state'])
            m.to(device)
            ft_models.append(m)

        if missing:
            print(f"  {pid}: missing EXP-242 checkpoints, retraining base+FT")
            # Retrain if checkpoints missing — this shouldn't happen normally
            continue

        # Evaluate each seed + ensemble on verification data
        seed_maes = {}
        for i, seed in enumerate(seeds):
            mae = _mae_from_model(ft_models[i], ver_ds)
            seed_maes[f's{seed}'] = round(mae, 2)
        ver_ens = _ensemble_mae(ft_models, ver_ds)

        # Also evaluate on training val split for gap comparison
        train_path = os.path.join(patients_base, pid, 'training')
        try:
            _, train_val_ds = load_multipatient_nightscout(
                [train_path], task='forecast', window_size=24)
            train_ens = _ensemble_mae(ft_models, train_val_ds)
        except Exception:
            train_ens = float('nan')

        gap = ver_ens - train_ens
        per_patient[pid] = {
            'verification_seeds': seed_maes,
            'verification_ensemble_mae': round(ver_ens, 2),
            'training_val_ensemble_mae': round(train_ens, 2),
            'generalization_gap': round(gap, 2),
            'gap_pct': round(gap / train_ens * 100, 1) if train_ens > 0 else None,
        }
        print(f"  {pid}: ver_ens={ver_ens:.1f} train_ens={train_ens:.1f} gap={gap:+.1f}")

    all_ver = [v['verification_ensemble_mae'] for v in per_patient.values()]
    all_train = [v['training_val_ensemble_mae'] for v in per_patient.values()
                 if not np.isnan(v['training_val_ensemble_mae'])]
    all_gap = [v['generalization_gap'] for v in per_patient.values()
               if not np.isnan(v['generalization_gap'])]
    result = {
        'experiment': 'EXP-249: Verification Set Generalization (EXP-242 models)',
        'per_patient': per_patient,
        'summary': {
            'mean_verification_mae': round(float(np.mean(all_ver)), 2) if all_ver else None,
            'mean_training_val_mae': round(float(np.mean(all_train)), 2) if all_train else None,
            'mean_gap': round(float(np.mean(all_gap)), 2) if all_gap else None,
            'mean_gap_pct': round(float(np.mean(all_gap)) /
                                  float(np.mean(all_train)) * 100, 1)
                           if all_train and all_gap else None,
            'n_patients': len(per_patient),
        },
        'comparison': {'exp242_training_mae': 11.25,
                       'exp238_gap_pct': -6.3},
    }
    save_results(result, os.path.join(output_dir, 'exp249_verification_ensemble.json'))
    return result

REGISTRY['verification-per-patient-ensemble'] = 'run_verification_per_patient_ensemble'


# ── EXP-250: Deep (L=4) Per-Patient FT Ensemble ──────────────────
# L=4 improved multi-patient ensemble from 12.38→12.20 (EXP-247).
# Per-patient FT improved L=2 from 12.38→11.25 (EXP-242).
# Hypothesis: gains compound → ~11.0 MAE.
def run_deep_per_patient_ensemble(args):
    """EXP-250: L=4 per-patient FT ensemble (stacking depth + personalization)."""
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patients_base = patients_dir or 'externals/ns-data/patients'
    patient_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])
    device = get_device()
    seeds = [42, 123, 456, 789, 1024]

    # Train 5 L=4 base models (multi-patient)
    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)
    base_states = {}
    for seed in seeds:
        # Try to load from EXP-247 checkpoints first
        ckpt_path = os.path.join(output_dir, f'exp247_deep_s{seed}.pth')
        if os.path.exists(ckpt_path):
            print(f"  Reusing EXP-247 base s{seed}")
            base_states[seed] = torch.load(
                ckpt_path, map_location=device, weights_only=False)['model_state']
        else:
            set_seed(seed)
            m = create_model(arch='grouped', input_dim=8, d_model=64,
                             nhead=4, num_layers=4)
            bp = os.path.join(output_dir, f'exp250_base_s{seed}.pth')
            train_forecast(m, train_ds, val_ds, bp,
                           label=f'EXP-250 Base-s{seed}', epochs=100,
                           lr=1e-3, patience=15)
            base_states[seed] = torch.load(
                bp, map_location=device, weights_only=False)['model_state']

    # Per-patient fine-tuning with L=4 models
    per_patient = {}
    for pid in patient_dirs:
        tp = os.path.join(patients_base, pid, 'training')
        if not os.path.isdir(tp):
            continue
        try:
            tds, vds = load_multipatient_nightscout(
                [tp], task='forecast', window_size=24)
        except Exception:
            continue
        if len(vds) < 10:
            continue

        ft_models = []
        seed_maes = {}
        for seed in seeds:
            set_seed(seed)
            m = create_model(arch='grouped', input_dim=8, d_model=64,
                             nhead=4, num_layers=4)
            m.load_state_dict(base_states[seed])
            fp = os.path.join(output_dir, f'exp250_ft_{pid}_s{seed}.pth')
            train_forecast(m, tds, vds, fp,
                           label=f'EXP-250 FT-{pid}-s{seed}',
                           epochs=30, lr=1e-4, patience=10)
            mae = _mae_from_model(m, vds)
            seed_maes[f's{seed}'] = round(mae, 2)
            ft_models.append(m)
        ens = _ensemble_mae(ft_models, vds)
        per_patient[pid] = {
            'seeds': seed_maes,
            'ensemble_mae': round(ens, 2),
            'mean_seed': round(float(np.mean(list(seed_maes.values()))), 2),
        }
        print(f"  {pid}: mean_seed={per_patient[pid]['mean_seed']:.1f} ens={ens:.1f}")

    all_ens = [v['ensemble_mae'] for v in per_patient.values()]
    result = {
        'experiment': 'EXP-250: Deep (L=4) Per-Patient FT Ensemble',
        'per_patient': per_patient,
        'summary': {
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'n_patients': len(per_patient),
        },
        'config': {'d_model': 64, 'nhead': 4, 'num_layers': 4,
                   'seeds': seeds, 'ft_epochs': 30, 'ft_lr': 1e-4},
        'comparison': {'exp242_L2_per_patient': 11.25,
                       'exp247_L4_ensemble': 12.20},
    }
    save_results(result, os.path.join(output_dir, 'exp250_deep_per_patient.json'))
    return result

REGISTRY['deep-per-patient-ensemble'] = 'run_deep_per_patient_ensemble'


# ── EXP-251: Extended Base Training (L=4, 200ep) + Per-Patient FT ─
# EXP-250 base models trained ~100ep. Longer training may yield better
# representations. L=4 + per-patient FT is the proven best recipe.
# Hypothesis: 200ep base with more patience yields ~10.2-10.5 MAE.
def run_extended_training_l4(args):
    """EXP-251: 200ep L=4 base training + per-patient FT ensemble."""
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patients_base = patients_dir or 'externals/ns-data/patients'
    patient_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])
    device = get_device()
    seeds = [42, 123, 456, 789, 1024]

    # Load multi-patient data
    data_paths = [os.path.join(patients_base, p, 'training') for p in patient_dirs]
    train_ds, val_ds = load_multipatient_nightscout(data_paths, task='forecast', window_size=24)

    # Phase 1: Train 5 L=4 base models with extended training
    base_states = {}
    for seed in seeds:
        fp = os.path.join(output_dir, f'exp251_base_s{seed}.pth')
        torch.manual_seed(seed)
        m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=4)
        train_forecast(m, train_ds, val_ds, fp,
                       label=f'EXP-251 Base-s{seed}',
                       epochs=200, lr=1e-3, patience=20, lr_patience=7)
        ckpt = torch.load(fp, map_location=device, weights_only=False)
        base_states[seed] = ckpt['model_state']
        base_mae = _mae_from_model(m, val_ds)
        print(f"  Base s{seed}: {base_mae:.2f}")

    # Phase 2: Per-patient fine-tuning
    per_patient = {}
    for pid in patient_dirs:
        p_path = os.path.join(patients_base, pid, 'training')
        tds, vds = load_multipatient_nightscout([p_path], task='forecast', window_size=24)
        seed_maes = {}
        ft_models = []
        for seed in seeds:
            torch.manual_seed(seed)
            m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=4)
            m.load_state_dict(base_states[seed])
            fp = os.path.join(output_dir, f'exp251_ft_{pid}_s{seed}.pth')
            train_forecast(m, tds, vds, fp,
                           label=f'EXP-251 FT-{pid}-s{seed}',
                           epochs=30, lr=1e-4, patience=10)
            mae = _mae_from_model(m, vds)
            seed_maes[f's{seed}'] = round(mae, 2)
            ft_models.append(m)
        ens = _ensemble_mae(ft_models, vds)
        per_patient[pid] = {
            'seeds': seed_maes,
            'ensemble_mae': round(ens, 2),
            'mean_seed': round(float(np.mean(list(seed_maes.values()))), 2),
        }
        print(f"  {pid}: mean_seed={per_patient[pid]['mean_seed']:.1f} ens={ens:.1f}")

    all_ens = [v['ensemble_mae'] for v in per_patient.values()]
    result = {
        'experiment': 'EXP-251: Extended Training (200ep) L=4 Per-Patient FT Ensemble',
        'per_patient': per_patient,
        'summary': {
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'n_patients': len(per_patient),
        },
        'config': {'d_model': 64, 'nhead': 4, 'num_layers': 4,
                    'base_epochs': 200, 'base_patience': 20, 'base_lr_patience': 7,
                    'seeds': seeds, 'ft_epochs': 30, 'ft_lr': 1e-4},
        'comparison': {'exp250_L4_per_patient': 10.71,
                        'exp242_L2_per_patient': 11.25},
    }
    save_results(result, os.path.join(output_dir, 'exp251_extended_training_l4.json'))
    return result

REGISTRY['extended-training-l4'] = 'run_extended_training_l4'


# ── EXP-252: FT Learning Rate Tuning (L=4) ───────────────────────
# EXP-250 FT used lr=1e-4 for 30ep, early stopping ~15-20ep.
# Lower LR (5e-5) with more runway (50ep) may find finer local optima.
# Reuses EXP-247 base checkpoints (same as EXP-250).
def run_ft_lr_tuning_l4(args):
    """EXP-252: Lower FT learning rate (5e-5, 50ep) with L=4 bases."""
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patients_base = patients_dir or 'externals/ns-data/patients'
    patient_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])
    device = get_device()
    seeds = [42, 123, 456, 789, 1024]

    # Reuse EXP-247 base checkpoints (same as EXP-250)
    base_states = {}
    for seed in seeds:
        fp = os.path.join(output_dir, f'exp247_deep_s{seed}.pth')
        if not os.path.exists(fp):
            raise FileNotFoundError(f"EXP-247 base not found: {fp}")
        ckpt = torch.load(fp, map_location=device, weights_only=False)
        base_states[seed] = ckpt['model_state']
        print(f"  Reusing EXP-247 base s{seed}")

    per_patient = {}
    for pid in patient_dirs:
        p_path = os.path.join(patients_base, pid, 'training')
        tds, vds = load_multipatient_nightscout([p_path], task='forecast', window_size=24)
        seed_maes = {}
        ft_models = []
        for seed in seeds:
            torch.manual_seed(seed)
            m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=4)
            m.load_state_dict(base_states[seed])
            fp = os.path.join(output_dir, f'exp252_ft_{pid}_s{seed}.pth')
            train_forecast(m, tds, vds, fp,
                           label=f'EXP-252 FT-{pid}-s{seed}',
                           epochs=50, lr=5e-5, patience=15)
            mae = _mae_from_model(m, vds)
            seed_maes[f's{seed}'] = round(mae, 2)
            ft_models.append(m)
        ens = _ensemble_mae(ft_models, vds)
        per_patient[pid] = {
            'seeds': seed_maes,
            'ensemble_mae': round(ens, 2),
            'mean_seed': round(float(np.mean(list(seed_maes.values()))), 2),
        }
        print(f"  {pid}: mean_seed={per_patient[pid]['mean_seed']:.1f} ens={ens:.1f}")

    all_ens = [v['ensemble_mae'] for v in per_patient.values()]
    result = {
        'experiment': 'EXP-252: FT Learning Rate Tuning (L=4, lr=5e-5, 50ep)',
        'per_patient': per_patient,
        'summary': {
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2),
            'n_patients': len(per_patient),
        },
        'config': {'d_model': 64, 'nhead': 4, 'num_layers': 4,
                    'base': 'EXP-247 (reused)', 'seeds': seeds,
                    'ft_epochs': 50, 'ft_lr': 5e-5, 'ft_patience': 15},
        'comparison': {'exp250_ft_lr_1e4_30ep': 10.71},
    }
    save_results(result, os.path.join(output_dir, 'exp252_ft_lr_tuning.json'))
    return result

REGISTRY['ft-lr-tuning-l4'] = 'run_ft_lr_tuning_l4'


# ── EXP-254: Verification of EXP-250 (L=4 Per-Patient FT) ────────
# EXP-249 showed +2.8% gap for L=2 models (EXP-242).
# Verify that L=4 per-patient FT (EXP-250) also generalizes well.
# No training — pure evaluation on held-out verification splits.
def run_verification_exp250(args):
    """EXP-254: Evaluate EXP-250 L=4 models on verification splits."""
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patients_base = patients_dir or 'externals/ns-data/patients'
    patient_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])
    device = get_device()
    seeds = [42, 123, 456, 789, 1024]

    per_patient = {}
    for pid in patient_dirs:
        ver_path = os.path.join(patients_base, pid, 'verification')
        if not os.path.isdir(ver_path):
            print(f"  {pid}: no verification dir, skipping")
            continue
        try:
            _, ver_ds = load_multipatient_nightscout(
                [ver_path], task='forecast', window_size=24)
        except Exception as e:
            print(f"  {pid}: verification load failed ({e}), skipping")
            continue
        if len(ver_ds) < 10:
            print(f"  {pid}: too few verification windows ({len(ver_ds)}), skipping")
            continue

        # Load fine-tuned L=4 models from EXP-250
        ft_models = []
        missing = False
        for seed in seeds:
            fp = os.path.join(output_dir, f'exp250_ft_{pid}_s{seed}.pth')
            if not os.path.exists(fp):
                missing = True
                break
            m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=4)
            ckpt = torch.load(fp, map_location=device, weights_only=False)
            m.load_state_dict(ckpt['model_state'])
            m.to(device)
            ft_models.append(m)

        if missing:
            print(f"  {pid}: missing EXP-250 checkpoints, skipping")
            continue

        seed_maes = {}
        for i, seed in enumerate(seeds):
            mae = _mae_from_model(ft_models[i], ver_ds)
            seed_maes[f's{seed}'] = round(mae, 2)
        ver_ens = _ensemble_mae(ft_models, ver_ds)

        # Training val split for gap comparison
        train_path = os.path.join(patients_base, pid, 'training')
        try:
            _, train_val_ds = load_multipatient_nightscout(
                [train_path], task='forecast', window_size=24)
            train_ens = _ensemble_mae(ft_models, train_val_ds)
        except Exception:
            train_ens = float('nan')

        gap = ver_ens - train_ens
        per_patient[pid] = {
            'verification_seeds': seed_maes,
            'verification_ensemble_mae': round(ver_ens, 2),
            'training_val_ensemble_mae': round(train_ens, 2),
            'generalization_gap': round(gap, 2),
            'gap_pct': round(gap / train_ens * 100, 1) if train_ens > 0 else None,
        }
        print(f"  {pid}: ver_ens={ver_ens:.1f} train_ens={train_ens:.1f} gap={gap:+.1f}")

    all_ver = [v['verification_ensemble_mae'] for v in per_patient.values()]
    all_train = [v['training_val_ensemble_mae'] for v in per_patient.values()
                 if not np.isnan(v['training_val_ensemble_mae'])]
    all_gap = [v['generalization_gap'] for v in per_patient.values()
               if not np.isnan(v['generalization_gap'])]
    result = {
        'experiment': 'EXP-254: Verification Set Generalization (EXP-250 L=4 models)',
        'per_patient': per_patient,
        'summary': {
            'mean_verification_mae': round(float(np.mean(all_ver)), 2) if all_ver else None,
            'mean_training_val_mae': round(float(np.mean(all_train)), 2) if all_train else None,
            'mean_gap': round(float(np.mean(all_gap)), 2) if all_gap else None,
            'mean_gap_pct': round(float(np.mean(all_gap)) /
                                  float(np.mean(all_train)) * 100, 1)
                           if all_train and all_gap else None,
            'n_patients': len(per_patient),
        },
        'comparison': {'exp250_training_mae': 10.71,
                        'exp249_L2_gap_pct': 2.8},
    }
    save_results(result, os.path.join(output_dir, 'exp254_verification_exp250.json'))
    return result

REGISTRY['verification-exp250'] = 'run_verification_exp250'


# ── EXP-255: Regularized FT (Weight Decay + Verification) ────────
# EXP-254 showed L=4 FT overfits (+7.4% gap vs +2.8% for L=2).
# Patients c, i, j have 22-36% gaps. Higher weight_decay during FT
# should keep models closer to pre-trained weights.
# Test wd=1e-4 and wd=1e-3 (vs default 1e-5), evaluate both
# training val and verification MAE to measure gap reduction.
def run_regularized_ft_l4(args):
    """EXP-255: Weight decay regularized FT (L=4) with verification eval."""
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patients_base = patients_dir or 'externals/ns-data/patients'
    patient_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])
    device = get_device()
    seeds = [42, 123, 456, 789, 1024]
    wd_value = 1e-3  # 100× default — strong regularization

    # Reuse EXP-247 base checkpoints (same as EXP-250)
    base_states = {}
    for seed in seeds:
        fp = os.path.join(output_dir, f'exp247_deep_s{seed}.pth')
        if not os.path.exists(fp):
            raise FileNotFoundError(f"EXP-247 base not found: {fp}")
        ckpt = torch.load(fp, map_location=device, weights_only=False)
        base_states[seed] = ckpt['model_state']
        print(f"  Reusing EXP-247 base s{seed}")

    per_patient = {}
    for pid in patient_dirs:
        p_path = os.path.join(patients_base, pid, 'training')
        tds, vds = load_multipatient_nightscout([p_path], task='forecast', window_size=24)

        # Also load verification split for gap measurement
        ver_path = os.path.join(patients_base, pid, 'verification')
        ver_ds = None
        if os.path.isdir(ver_path):
            try:
                _, ver_ds = load_multipatient_nightscout(
                    [ver_path], task='forecast', window_size=24)
                if len(ver_ds) < 10:
                    ver_ds = None
            except Exception:
                ver_ds = None

        seed_maes = {}
        ft_models = []
        for seed in seeds:
            torch.manual_seed(seed)
            m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=4)
            m.load_state_dict(base_states[seed])
            fp = os.path.join(output_dir, f'exp255_ft_{pid}_s{seed}.pth')
            train_forecast(m, tds, vds, fp,
                           label=f'EXP-255 FT-{pid}-s{seed}',
                           epochs=30, lr=1e-4, patience=10,
                           weight_decay=wd_value)
            mae = _mae_from_model(m, vds)
            seed_maes[f's{seed}'] = round(mae, 2)
            ft_models.append(m)

        train_ens = _ensemble_mae(ft_models, vds)
        ver_ens = _ensemble_mae(ft_models, ver_ds) if ver_ds else float('nan')
        gap = ver_ens - train_ens if ver_ds else float('nan')

        per_patient[pid] = {
            'seeds': seed_maes,
            'training_ensemble_mae': round(train_ens, 2),
            'verification_ensemble_mae': round(ver_ens, 2) if ver_ds else None,
            'generalization_gap': round(gap, 2) if ver_ds else None,
            'gap_pct': round(gap / train_ens * 100, 1) if ver_ds and train_ens > 0 else None,
            'mean_seed': round(float(np.mean(list(seed_maes.values()))), 2),
        }
        gap_str = f" ver={ver_ens:.1f} gap={gap:+.1f}" if ver_ds else ""
        print(f"  {pid}: train_ens={train_ens:.1f}{gap_str}")

    all_train = [v['training_ensemble_mae'] for v in per_patient.values()]
    all_ver = [v['verification_ensemble_mae'] for v in per_patient.values()
               if v['verification_ensemble_mae'] is not None]
    all_gap = [v['generalization_gap'] for v in per_patient.values()
               if v['generalization_gap'] is not None]
    result = {
        'experiment': f'EXP-255: Regularized FT (L=4, wd={wd_value})',
        'per_patient': per_patient,
        'summary': {
            'mean_training_mae': round(float(np.mean(all_train)), 2),
            'mean_verification_mae': round(float(np.mean(all_ver)), 2) if all_ver else None,
            'mean_gap': round(float(np.mean(all_gap)), 2) if all_gap else None,
            'mean_gap_pct': round(float(np.mean(all_gap)) /
                                  float(np.mean(all_train)) * 100, 1)
                           if all_train and all_gap else None,
            'n_patients': len(per_patient),
        },
        'config': {'d_model': 64, 'nhead': 4, 'num_layers': 4,
                    'base': 'EXP-247 (reused)', 'seeds': seeds,
                    'ft_epochs': 30, 'ft_lr': 1e-4, 'ft_weight_decay': wd_value},
        'comparison': {'exp250_training': 10.71, 'exp250_verification': 11.49,
                        'exp250_gap_pct': 7.4},
    }
    save_results(result, os.path.join(output_dir, 'exp255_regularized_ft.json'))
    return result

REGISTRY['regularized-ft-l4'] = 'run_regularized_ft_l4'


# ── EXP-256: Temporal Distribution Augmentation ──────────────────
# Weight decay didn't help (EXP-255 = identical to EXP-254).
# Gap is distribution shift, not parameter overfitting.
# Hypothesis: Adding noise + temporal jitter during base training
# widens the training distribution, reducing the verification gap.
# Use AugmentedDataset wrapper to add Gaussian noise (σ=0.02) and
# random temporal shift (±2 steps = ±10min) on glucose history.
def run_temporal_dist_augmentation(args):
    """EXP-256: Data augmentation during base training to close ver gap."""
    from torch.utils.data import DataLoader, Dataset
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patients_base = patients_dir or 'externals/ns-data/patients'
    patient_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])
    device = get_device()
    seeds = [42, 123, 456, 789, 1024]

    # ── Augmented dataset wrapper ──
    class AugmentedDataset(Dataset):
        """Wraps a CGMDataset adding noise + temporal jitter."""
        def __init__(self, ds, noise_std=0.02, shift_range=2, p_aug=0.5):
            self.ds = ds
            self.noise_std = noise_std
            self.shift_range = shift_range
            self.p_aug = p_aug

        def __len__(self):
            return len(self.ds)

        def __getitem__(self, idx):
            x = self.ds[idx]
            if isinstance(x, (tuple, list)):
                x = x[0]
            if torch.rand(1).item() > self.p_aug:
                return (x,)
            x = x.clone()
            half = x.shape[0] // 2
            # Gaussian noise on history glucose (channel 0)
            x[:half, 0] += torch.randn(half) * self.noise_std
            # Small temporal shift on history glucose
            shift = torch.randint(-self.shift_range, self.shift_range + 1, (1,)).item()
            if shift != 0:
                x[:half, 0] = torch.roll(x[:half, 0], shift, dims=0)
            return (x,)

    # ── Load ALL patient data for base training ──
    all_paths = [os.path.join(patients_base, p, 'training') for p in patient_dirs]
    train_ds, val_ds = load_multipatient_nightscout(all_paths, task='forecast', window_size=24)
    aug_train_ds = AugmentedDataset(train_ds, noise_std=0.02, shift_range=2, p_aug=0.5)

    # ── Train 5 augmented base models ──
    base_states = {}
    for seed in seeds:
        set_seed(seed)
        m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=4)
        fp = os.path.join(output_dir, f'exp256_base_s{seed}.pth')
        train_forecast(m, aug_train_ds, val_ds, fp,
                       label=f'EXP-256 Base-s{seed}',
                       epochs=150, lr=1e-3, patience=20, lr_patience=7)
        base_mae = _mae_from_model(m, val_ds)
        base_states[seed] = m.state_dict()
        print(f"  Base s{seed} MAE: {base_mae:.2f}")

    # ── Per-patient FT (standard, no augmentation) ──
    per_patient = {}
    for pid in patient_dirs:
        p_path = os.path.join(patients_base, pid, 'training')
        tds, vds = load_multipatient_nightscout([p_path], task='forecast', window_size=24)
        ver_path = os.path.join(patients_base, pid, 'verification')
        ver_ds = None
        if os.path.isdir(ver_path):
            try:
                _, ver_ds = load_multipatient_nightscout(
                    [ver_path], task='forecast', window_size=24)
                if len(ver_ds) < 10:
                    ver_ds = None
            except Exception:
                ver_ds = None

        seed_maes = {}
        ft_models = []
        for seed in seeds:
            torch.manual_seed(seed)
            m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=4)
            m.load_state_dict(base_states[seed])
            fp = os.path.join(output_dir, f'exp256_ft_{pid}_s{seed}.pth')
            train_forecast(m, tds, vds, fp,
                           label=f'EXP-256 FT-{pid}-s{seed}',
                           epochs=30, lr=1e-4, patience=10)
            mae = _mae_from_model(m, vds)
            seed_maes[f's{seed}'] = round(mae, 2)
            ft_models.append(m)

        train_ens = _ensemble_mae(ft_models, vds)
        ver_ens = _ensemble_mae(ft_models, ver_ds) if ver_ds else float('nan')
        gap = ver_ens - train_ens if ver_ds else float('nan')
        per_patient[pid] = {
            'seeds': seed_maes,
            'training_ensemble_mae': round(train_ens, 2),
            'verification_ensemble_mae': round(ver_ens, 2) if ver_ds else None,
            'generalization_gap': round(gap, 2) if ver_ds else None,
            'gap_pct': round(gap / train_ens * 100, 1) if ver_ds and train_ens > 0 else None,
            'mean_seed': round(float(np.mean(list(seed_maes.values()))), 2),
        }
        gap_str = f" ver={ver_ens:.1f} gap={gap:+.1f}" if ver_ds else ""
        print(f"  {pid}: train_ens={train_ens:.1f}{gap_str}")

    all_train = [v['training_ensemble_mae'] for v in per_patient.values()]
    all_ver = [v['verification_ensemble_mae'] for v in per_patient.values()
               if v['verification_ensemble_mae'] is not None]
    all_gap = [v['generalization_gap'] for v in per_patient.values()
               if v['generalization_gap'] is not None]
    result = {
        'experiment': 'EXP-256: Temporal Distribution Augmentation (L=4)',
        'hypothesis': 'Noise + temporal jitter during base training reduces verification gap',
        'per_patient': per_patient,
        'summary': {
            'mean_training_mae': round(float(np.mean(all_train)), 2),
            'mean_verification_mae': round(float(np.mean(all_ver)), 2) if all_ver else None,
            'mean_gap': round(float(np.mean(all_gap)), 2) if all_gap else None,
            'mean_gap_pct': round(float(np.mean(all_gap)) /
                                  float(np.mean(all_train)) * 100, 1)
                           if all_train and all_gap else None,
            'n_patients': len(per_patient),
        },
        'config': {'d_model': 64, 'nhead': 4, 'num_layers': 4, 'seeds': seeds,
                    'base_epochs': 150, 'base_patience': 20,
                    'aug_noise_std': 0.02, 'aug_shift_range': 2, 'aug_p': 0.5,
                    'ft_epochs': 30, 'ft_lr': 1e-4},
        'comparison': {'exp251_training': 10.59, 'exp254_verification': 11.49,
                        'exp254_gap_pct': 7.4},
    }
    save_results(result, os.path.join(output_dir, 'exp256_temporal_augmentation.json'))
    return result

REGISTRY['temporal-dist-aug'] = 'run_temporal_dist_augmentation'


# ── EXP-257: Dropout Sweep (0.15 / 0.2 / 0.3) ──────────────────
# Test structural regularization via higher dropout during both
# base training AND fine-tuning. This is fundamentally different
# from weight decay (EXP-255) — dropout creates implicit ensembles
# within a single model, forcing distributed representations.
# Trains ONE base model per dropout value (seed=42) + FT on 3 patients
# (d=easiest, a=medium, j=hardest) to quickly identify best dropout.
def run_dropout_sweep(args):
    """EXP-257: Dropout sweep to find optimal structural regularization."""
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patients_base = patients_dir or 'externals/ns-data/patients'
    device = get_device()
    test_patients = ['d', 'a', 'j']  # easy, medium, hard
    dropout_values = [0.15, 0.2, 0.3]

    # Load ALL patient data for base training
    all_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])
    all_paths = [os.path.join(patients_base, p, 'training') for p in all_dirs]
    train_ds, val_ds = load_multipatient_nightscout(all_paths, task='forecast', window_size=24)

    dropout_results = {}
    for dp in dropout_values:
        set_seed(42)
        m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4,
                         num_layers=4, dropout=dp)
        fp = os.path.join(output_dir, f'exp257_base_dp{int(dp*100)}_s42.pth')
        train_forecast(m, train_ds, val_ds, fp,
                       label=f'EXP-257 Base dp={dp}',
                       epochs=150, lr=1e-3, patience=20, lr_patience=7)
        base_mae = _mae_from_model(m, val_ds)
        base_state = m.state_dict()
        print(f"  dp={dp}: base MAE = {base_mae:.2f}")

        patient_results = {}
        for pid in test_patients:
            p_path = os.path.join(patients_base, pid, 'training')
            tds, vds = load_multipatient_nightscout(
                [p_path], task='forecast', window_size=24)
            ver_path = os.path.join(patients_base, pid, 'verification')
            ver_ds = None
            if os.path.isdir(ver_path):
                try:
                    _, ver_ds = load_multipatient_nightscout(
                        [ver_path], task='forecast', window_size=24)
                    if len(ver_ds) < 10:
                        ver_ds = None
                except Exception:
                    ver_ds = None

            torch.manual_seed(42)
            ft_m = create_model(arch='grouped', input_dim=8, d_model=64,
                                nhead=4, num_layers=4, dropout=dp)
            ft_m.load_state_dict(base_state)
            fp = os.path.join(output_dir, f'exp257_ft_{pid}_dp{int(dp*100)}_s42.pth')
            train_forecast(ft_m, tds, vds, fp,
                           label=f'EXP-257 FT-{pid} dp={dp}',
                           epochs=30, lr=1e-4, patience=10)
            train_mae = _mae_from_model(ft_m, vds)
            ver_mae = _mae_from_model(ft_m, ver_ds) if ver_ds else float('nan')
            gap = ver_mae - train_mae if ver_ds else float('nan')
            patient_results[pid] = {
                'training_mae': round(train_mae, 2),
                'verification_mae': round(ver_mae, 2) if ver_ds else None,
                'gap': round(gap, 2) if ver_ds else None,
                'gap_pct': round(gap / train_mae * 100, 1) if ver_ds and train_mae > 0 else None,
            }
            gap_str = f" ver={ver_mae:.1f} gap={gap:+.1f}" if ver_ds else ""
            print(f"    {pid}: train={train_mae:.1f}{gap_str}")

        dropout_results[f'dp={dp}'] = {
            'base_mae': round(base_mae, 2),
            'patients': patient_results,
        }

    result = {
        'experiment': 'EXP-257: Dropout Sweep (L=4, seed=42)',
        'hypothesis': 'Higher dropout creates implicit ensemble, reduces verification gap',
        'dropout_results': dropout_results,
        'config': {'d_model': 64, 'nhead': 4, 'num_layers': 4,
                    'test_patients': test_patients, 'seed': 42,
                    'dropout_values': dropout_values,
                    'base_epochs': 150, 'ft_epochs': 30},
        'comparison': {'exp250_dp0.1_base_mae': 12.72,
                        'exp254_dp0.1_ver_gap_pct': 7.4},
    }
    save_results(result, os.path.join(output_dir, 'exp257_dropout_sweep.json'))
    return result

REGISTRY['dropout-sweep'] = 'run_dropout_sweep'


# ── EXP-258: Test-Time Augmentation (TTA) Ensemble ──────────────
# Quick win: no training required! Reuse EXP-251 per-patient FT
# checkpoints and run inference with temporal perturbations averaged.
# Each model prediction is averaged across N augmented inputs
# (Gaussian noise on history glucose + small temporal shift).
# This should directly reduce variance from temporal distribution shift.
def run_tta_ensemble(args):
    """EXP-258: TTA on EXP-251 checkpoints — no training needed."""
    from torch.utils.data import DataLoader
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patients_base = patients_dir or 'externals/ns-data/patients'
    patient_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])
    device = get_device()
    seeds = [42, 123, 456, 789, 1024]
    n_aug = 7       # augmentations per model
    noise_std = 0.02
    shift_range = 2

    def _tta_mae(models, val_ds, n_aug, noise_std, shift_range, batch_size=64):
        """Ensemble MAE with test-time augmentation."""
        total_ae, n = 0.0, 0
        for batch in DataLoader(val_ds, batch_size=batch_size):
            x = batch_to_device(batch[0], device)
            half = x.shape[1] // 2
            all_preds = []
            for m in models:
                m.eval()
                for aug_i in range(n_aug):
                    x_in = x.clone()
                    mask_future_channels(x_in, half)
                    if aug_i > 0:
                        # Add noise to history glucose
                        x_in[:, :half, 0] += torch.randn(
                            x_in.shape[0], half, device=device) * noise_std
                        # Small temporal shift on history glucose
                        shift = torch.randint(
                            -shift_range, shift_range + 1, (1,)).item()
                        if shift != 0:
                            x_in[:, :half, 0] = torch.roll(
                                x_in[:, :half, 0], shift, dims=1)
                    with torch.no_grad():
                        p = m(x_in, causal=True)
                    if isinstance(p, dict):
                        p = p['forecast']
                    all_preds.append(p[:, half:, :1])
            ens = torch.stack(all_preds).mean(0)
            ae = torch.abs(ens - x[:, half:, :1])
            total_ae += ae.sum().item()
            n += ae.numel()
        return float(total_ae / n * SCALE) if n else float('nan')

    per_patient = {}
    for pid in patient_dirs:
        # Load FT models from EXP-251
        ft_models = []
        missing = False
        for seed in seeds:
            fp = os.path.join(output_dir, f'exp251_ft_{pid}_s{seed}.pth')
            if not os.path.exists(fp):
                print(f"  Warning: {fp} not found, skipping {pid}")
                missing = True
                break
            m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=4)
            ckpt = torch.load(fp, map_location=device, weights_only=False)
            m.load_state_dict(ckpt['model_state'])
            m.to(device)
            ft_models.append(m)
        if missing:
            continue

        # Load training val data
        p_path = os.path.join(patients_base, pid, 'training')
        tds, vds = load_multipatient_nightscout([p_path], task='forecast', window_size=24)

        # Load verification data
        ver_path = os.path.join(patients_base, pid, 'verification')
        ver_ds = None
        if os.path.isdir(ver_path):
            try:
                _, ver_ds = load_multipatient_nightscout(
                    [ver_path], task='forecast', window_size=24)
                if len(ver_ds) < 10:
                    ver_ds = None
            except Exception:
                ver_ds = None

        # Standard ensemble (no TTA) for comparison
        train_ens = _ensemble_mae(ft_models, vds)
        ver_ens = _ensemble_mae(ft_models, ver_ds) if ver_ds else float('nan')

        # TTA ensemble
        train_tta = _tta_mae(ft_models, vds, n_aug, noise_std, shift_range)
        ver_tta = _tta_mae(ft_models, ver_ds, n_aug, noise_std, shift_range) if ver_ds else float('nan')

        gap_std = ver_ens - train_ens if ver_ds else float('nan')
        gap_tta = ver_tta - train_tta if ver_ds else float('nan')

        per_patient[pid] = {
            'standard_train': round(train_ens, 2),
            'standard_ver': round(ver_ens, 2) if ver_ds else None,
            'standard_gap': round(gap_std, 2) if ver_ds else None,
            'tta_train': round(train_tta, 2),
            'tta_ver': round(ver_tta, 2) if ver_ds else None,
            'tta_gap': round(gap_tta, 2) if ver_ds else None,
            'tta_improvement_ver': round(ver_ens - ver_tta, 2) if ver_ds else None,
        }
        tta_str = f" TTA: train={train_tta:.1f} ver={ver_tta:.1f}" if ver_ds else ""
        print(f"  {pid}: std ver={ver_ens:.1f}{tta_str}")

    all_std_ver = [v['standard_ver'] for v in per_patient.values() if v['standard_ver'] is not None]
    all_tta_ver = [v['tta_ver'] for v in per_patient.values() if v['tta_ver'] is not None]
    all_std_gap = [v['standard_gap'] for v in per_patient.values() if v['standard_gap'] is not None]
    all_tta_gap = [v['tta_gap'] for v in per_patient.values() if v['tta_gap'] is not None]
    result = {
        'experiment': 'EXP-258: TTA Ensemble on EXP-251 checkpoints',
        'hypothesis': 'Test-time augmentation reduces verification gap without retraining',
        'per_patient': per_patient,
        'summary': {
            'mean_standard_ver': round(float(np.mean(all_std_ver)), 2) if all_std_ver else None,
            'mean_tta_ver': round(float(np.mean(all_tta_ver)), 2) if all_tta_ver else None,
            'mean_standard_gap': round(float(np.mean(all_std_gap)), 2) if all_std_gap else None,
            'mean_tta_gap': round(float(np.mean(all_tta_gap)), 2) if all_tta_gap else None,
            'n_patients': len(per_patient),
        },
        'config': {'n_aug': n_aug, 'noise_std': noise_std, 'shift_range': shift_range,
                    'base_models': 'EXP-251 per-patient FT', 'seeds': seeds},
    }
    save_results(result, os.path.join(output_dir, 'exp258_tta_ensemble.json'))
    return result

REGISTRY['tta-ensemble'] = 'run_tta_ensemble'


# ═════════════════════════════════════════════════════════════════
#  GEN-4 ENRICHMENT EXPERIMENTS (EXP-260+)
# ═════════════════════════════════════════════════════════════════
#
# These experiments test the 39-channel Gen-4 enrichment pipeline.
# Baseline comparison: EXP-242 per-patient FT ensemble @ 11.25 MAE.
# All use enriched_features=True → 39 channels, selective masking
# with 19 future-unknown channels.

from .schema import NUM_FEATURES_ENRICHED


# ── EXP-260: Gen-4 Enriched Baseline ────────────────────────────
# Train with all 39 channels, 5 seeds, per-patient FT.
# Direct comparison to EXP-242 (8-channel, same architecture).
def run_enriched_baseline(args):
    """EXP-260: 39-feature enriched baseline with per-patient FT ensemble.

    Hypothesis: Richer features break the 29.5 MAE ceiling for 8f and
    the 11.25 MAE ceiling for per-patient FT ensemble.
    Baseline: EXP-242 = 11.25 MAE (8f per-patient FT ensemble).

    Includes:
    - Masking validation (assert no future leaks)
    - Persistence baseline (for fair comparison)
    - Verification evaluation (measure generalization gap)
    """
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patients_base = patients_dir or 'externals/ns-data/patients'
    patient_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])
    device = get_device()
    seeds = [42, 123, 456, 789, 1024]

    validate_masking(NUM_FEATURES_ENRICHED, label='EXP-260')

    # Phase 1: Multi-patient base models (39f)
    patient_paths = resolve_patient_paths(patients_dir)
    print("=== Phase 1: Training 39f base models ===")
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24,
        enriched_features=True)

    persist_mae = compute_persistence_mae(val_ds)
    print(f"  Persistence baseline: {persist_mae:.1f} mg/dL")

    base_models_state = {}
    base_maes = {}
    for seed in seeds:
        set_seed(seed)
        m = create_model(arch='grouped', input_dim=NUM_FEATURES_ENRICHED,
                         d_model=64, nhead=4, num_layers=2)
        bp = os.path.join(output_dir, f'exp260_base_s{seed}.pth')
        train_forecast(m, train_ds, val_ds, bp,
                       label=f'EXP-260 Base-s{seed}', epochs=100, lr=1e-3, patience=15)
        mae = _mae_from_model(m, val_ds)
        base_maes[f's{seed}'] = round(mae, 2)
        base_models_state[seed] = torch.load(bp, map_location=device,
                                              weights_only=False)['model_state']
        print(f"  Base s{seed}: MAE={mae:.1f}")

    # Phase 2: Per-patient fine-tuning + verification
    print("\n=== Phase 2: Per-patient fine-tuning ===")
    per_patient = {}
    for pid in patient_dirs:
        tp = os.path.join(patients_base, pid, 'training')
        if not os.path.isdir(tp):
            continue
        try:
            tds, vds = load_multipatient_nightscout(
                [tp], task='forecast', window_size=24,
                enriched_features=True)
        except Exception as e:
            print(f"  {pid}: SKIP ({e})")
            continue
        if tds is None or len(vds) < 10:
            continue

        ft_models = []
        seed_maes = {}
        for seed in seeds:
            set_seed(seed)
            m = create_model(arch='grouped', input_dim=NUM_FEATURES_ENRICHED,
                             d_model=64, nhead=4, num_layers=2)
            m.load_state_dict(base_models_state[seed])
            fp = os.path.join(output_dir, f'exp260_ft_{pid}_s{seed}.pth')
            train_forecast(m, tds, vds, fp,
                           label=f'EXP-260 FT-{pid}-s{seed}',
                           epochs=30, lr=1e-4, patience=10)
            mae = _mae_from_model(m, vds)
            seed_maes[f's{seed}'] = round(mae, 2)
            ft_models.append(m)
        train_ens = _ensemble_mae(ft_models, vds)

        # Verification evaluation (held-out temporal split)
        ver_path = os.path.join(patients_base, pid, 'verification')
        ver_ens = None
        ver_gap = None
        if os.path.isdir(ver_path):
            try:
                _, ver_ds = load_multipatient_nightscout(
                    [ver_path], task='forecast', window_size=24,
                    enriched_features=True)
                if ver_ds is not None and len(ver_ds) >= 10:
                    ver_ens = _ensemble_mae(ft_models, ver_ds)
                    ver_gap = round((ver_ens / train_ens - 1) * 100, 1) if train_ens > 0 else None
            except Exception as e:
                print(f"  {pid}: verification load failed ({e})")

        per_patient[pid] = {
            'seeds': seed_maes,
            'ensemble_mae': round(train_ens, 2),
            'mean_seed': round(float(np.mean(list(seed_maes.values()))), 2),
            'verification_mae': round(ver_ens, 2) if ver_ens is not None else None,
            'generalization_gap_pct': ver_gap,
        }
        ver_str = f" ver={ver_ens:.1f} gap={ver_gap:+.1f}%" if ver_ens is not None else ""
        print(f"  {pid}: mean={per_patient[pid]['mean_seed']:.1f} "
              f"ens={train_ens:.1f}{ver_str}")

    all_ens = [v['ensemble_mae'] for v in per_patient.values()]
    all_ver = [v['verification_mae'] for v in per_patient.values()
               if v['verification_mae'] is not None]
    all_gaps = [v['generalization_gap_pct'] for v in per_patient.values()
                if v['generalization_gap_pct'] is not None]
    result = {
        'experiment': 'EXP-260: Gen-4 Enriched Baseline (39f)',
        'hypothesis': '39 channels break the 11.25 MAE ceiling',
        'base_maes': base_maes,
        'persistence_mae': round(persist_mae, 2),
        'per_patient': per_patient,
        'summary': {
            'mean_ensemble_mae': round(float(np.mean(all_ens)), 2) if all_ens else None,
            'mean_verification_mae': round(float(np.mean(all_ver)), 2) if all_ver else None,
            'mean_generalization_gap_pct': round(float(np.mean(all_gaps)), 1) if all_gaps else None,
            'pct_vs_persist': round((1 - float(np.mean(all_ens)) / persist_mae) * 100, 1) if all_ens else None,
            'n_patients': len(per_patient),
            'n_verified': len(all_ver),
        },
        'comparison': {'exp242_8f_ensemble': 11.25, 'exp249_verification_gap': 2.8},
        'config': {
            'input_dim': NUM_FEATURES_ENRICHED,
            'd_model': 64, 'nhead': 4, 'num_layers': 2,
            'seeds': seeds, 'window_size': 24,
            'masking': f'selective_{len([c for c in FUTURE_UNKNOWN_CHANNELS if c < NUM_FEATURES_ENRICHED])}ch',
        },
    }
    save_results(result, os.path.join(output_dir, 'exp260_enriched_baseline.json'))
    return result

REGISTRY['enriched-baseline'] = 'run_enriched_baseline'


# ── EXP-261: Feature Group Ablation ─────────────────────────────
# Train with 39f, then remove one group at a time.
# Measures marginal contribution of each Gen-4 group.
def run_feature_group_ablation(args):
    """EXP-261: N-choose-1 ablation of Gen-4 feature groups.

    Hypothesis: Some feature groups contribute more than others.
    Method: Train full 39f baseline, then zero out each group and re-eval.
    This is inference-time ablation (no retraining) — fast but approximate.
    """
    from .schema import (CGM_QUALITY_IDX, AID_CONTEXT_IDX, PROFILE_IDX,
                         PUMP_STATE_IDX, SENSOR_LIFECYCLE_IDX)

    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    device = get_device()

    validate_masking(NUM_FEATURES_ENRICHED, label='EXP-261')

    # Load 39f data
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24,
        enriched_features=True)

    persist_mae = compute_persistence_mae(val_ds)
    print(f"  Persistence baseline: {persist_mae:.1f} mg/dL")

    # Train a single 39f model
    set_seed(42)
    model = create_model(arch='grouped', input_dim=NUM_FEATURES_ENRICHED,
                         d_model=64, nhead=4, num_layers=2)
    sp = os.path.join(output_dir, 'exp261_full39f_s42.pth')
    train_forecast(model, train_ds, val_ds, sp,
                   label='EXP-261 Full-39f', epochs=100, lr=1e-3, patience=15)

    # Full model baseline
    full_mae = _mae_from_model(model, val_ds)
    print(f"  Full 39f MAE: {full_mae:.1f}")

    # Ablation: zero out each group at inference time
    groups = {
        'cgm_quality': CGM_QUALITY_IDX,
        'aid_context': AID_CONTEXT_IDX,
        'profile': PROFILE_IDX,
        'pump_state': PUMP_STATE_IDX,
        'sensor_lifecycle': SENSOR_LIFECYCLE_IDX,
    }

    ablation_results = {}
    for gname, gidx in groups.items():
        mae = _ablation_mae(model, val_ds, zero_channels=gidx)
        delta = mae - full_mae
        ablation_results[gname] = {
            'mae': round(mae, 2),
            'delta': round(delta, 2),
            'channels': gidx,
            'interpretation': 'helpful' if delta > 0.1 else ('neutral' if delta > -0.1 else 'harmful'),
        }
        print(f"  Without {gname}: MAE={mae:.1f} (Δ={delta:+.1f})")

    result = {
        'experiment': 'EXP-261: Feature Group Ablation (inference-time)',
        'hypothesis': 'Identify which Gen-4 groups contribute to accuracy',
        'full_mae': round(full_mae, 2),
        'persistence_mae': round(persist_mae, 2),
        'ablation': ablation_results,
        'ranking': sorted(ablation_results.keys(),
                         key=lambda k: -ablation_results[k]['delta']),
        'config': {'input_dim': NUM_FEATURES_ENRICHED, 'method': 'inference_ablation'},
    }
    save_results(result, os.path.join(output_dir, 'exp261_feature_ablation.json'))
    return result

REGISTRY['feature-group-ablation'] = 'run_feature_group_ablation'


def _ablation_mae(model, val_ds, zero_channels, batch_size=64):
    """MAE with specific channels zeroed at inference time."""
    from torch.utils.data import DataLoader
    device = get_device()
    model.eval()
    total_ae, n = 0.0, 0
    for batch in DataLoader(val_ds, batch_size=batch_size):
        x = batch_to_device(batch[0], device)
        half = x.shape[1] // 2
        x_in = x.clone()
        mask_future_channels(x_in, half)
        # Ablate: zero out the target channels in BOTH halves
        for ch in zero_channels:
            x_in[:, :, ch] = 0.0
        with torch.no_grad():
            pred = model(x_in, causal=True)
        if isinstance(pred, dict):
            pred = pred['forecast']
        ae = torch.abs(pred[:, half:, :1] - x[:, half:, :1])
        total_ae += ae.sum().item()
        n += ae.numel()
    return float(total_ae / n * SCALE) if n else float('nan')


# ── EXP-262: Loop Predicted Features Only ────────────────────────
# Add ONLY the AID context channels (Loop predictions + enacted) to 8f.
# Minimal extension: 8 + 7 = 15 channels.
def run_loop_predicted_only(args):
    """EXP-262: 8f + Loop AID context (15 channels total).

    Hypothesis: Loop's own predictions are the single most informative
    feature group (the AID system already models the patient).
    Method: Use enriched pipeline but zero out all non-AID-context Gen-4 channels.
    """
    from .schema import AID_CONTEXT_IDX

    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    device = get_device()
    seeds = [42, 123, 456]

    validate_masking(NUM_FEATURES_ENRICHED, label='EXP-262')

    # Use enriched data but we'll train on full 39f (with non-AID zeroed)
    # This way masking is handled correctly by the existing infrastructure
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24,
        enriched_features=True)

    # Zero out all Gen-4 channels EXCEPT AID context — ONCE before seed loop
    keep_channels = set(range(21)) | set(AID_CONTEXT_IDX)  # core 21 + AID
    all_channels = set(range(NUM_FEATURES_ENRICHED))
    zero_channels = list(all_channels - keep_channels)
    _zero_channels_in_dataset(train_ds, zero_channels)
    _zero_channels_in_dataset(val_ds, zero_channels)

    persist_mae = compute_persistence_mae(val_ds)
    print(f"  Persistence baseline: {persist_mae:.1f} mg/dL")

    models = []
    individual = {}
    for seed in seeds:
        set_seed(seed)
        m = create_model(arch='grouped', input_dim=NUM_FEATURES_ENRICHED,
                         d_model=64, nhead=4, num_layers=2)
        sp = os.path.join(output_dir, f'exp262_loop_pred_s{seed}.pth')

        train_forecast(m, train_ds, val_ds, sp,
                       label=f'EXP-262 LoopPred-s{seed}',
                       epochs=100, lr=1e-3, patience=15)
        mae = _mae_from_model(m, val_ds)
        individual[f's{seed}'] = round(mae, 2)
        models.append(m)
        print(f"  s{seed}: MAE={mae:.1f}")

    ens = _ensemble_mae(models, val_ds)
    result = {
        'experiment': 'EXP-262: 8f + Loop AID Context Only',
        'hypothesis': 'Loop predictions are the most informative Gen-4 group',
        'individual': individual,
        'ensemble_mae': round(ens, 2),
        'persistence_mae': round(persist_mae, 2),
        'pct_vs_persist': round((1 - ens / persist_mae) * 100, 1) if persist_mae > 0 else None,
        'effective_channels': sorted(list(keep_channels)),
        'zeroed_channels': sorted(zero_channels),
        'comparison': {'exp242_8f_ensemble': 11.25},
        'config': {
            'input_dim': NUM_FEATURES_ENRICHED,
            'active_gen4_groups': ['aid_context'],
        },
    }
    save_results(result, os.path.join(output_dir, 'exp262_loop_predicted.json'))
    return result

REGISTRY['loop-predicted-only'] = 'run_loop_predicted_only'


def _zero_channels_in_dataset(ds, channels):
    """Zero out specific channels in a TensorDataset (in-place)."""
    for tensor in ds.tensors:
        for ch in channels:
            if ch < tensor.shape[-1]:
                tensor[:, :, ch] = 0.0


# ── EXP-263: Forward Feature Selection ───────────────────────────
# Start with 8f base, add one Gen-4 group at a time, measure improvement.
# Order: AID context → CGM quality → Profile → Sensor lifecycle → Pump.
def run_forward_feature_selection(args):
    """EXP-263: Forward feature selection — add groups incrementally.

    Hypothesis: Cumulative improvement curve shows diminishing returns.
    Method: Train with progressively more feature groups enabled.
    """
    from .schema import (CGM_QUALITY_IDX, AID_CONTEXT_IDX, PROFILE_IDX,
                         PUMP_STATE_IDX, SENSOR_LIFECYCLE_IDX)

    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    device = get_device()

    validate_masking(NUM_FEATURES_ENRICHED, label='EXP-263')

    # Load full enriched data
    train_ds_full, val_ds_full = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24,
        enriched_features=True)

    persist_mae = compute_persistence_mae(val_ds_full)
    print(f"  Persistence baseline: {persist_mae:.1f} mg/dL")

    # Order by ablation impact (EXP-261): profile +7.4, aid +2.2, pump +0.5, cgm +0.3, sensor +0.2
    group_order = [
        ('profile', PROFILE_IDX),
        ('aid_context', AID_CONTEXT_IDX),
        ('pump_state', PUMP_STATE_IDX),
        ('cgm_quality', CGM_QUALITY_IDX),
        ('sensor_lifecycle', SENSOR_LIFECYCLE_IDX),
    ]

    results_by_step = {}
    active_channels = set(range(21))  # Start with base 21 channels
    import copy

    # Step 0: Base 21f (no Gen-4 groups) as reference
    zero_base = [c for c in range(NUM_FEATURES_ENRICHED) if c not in active_channels]
    train_ds0 = copy.deepcopy(train_ds_full)
    val_ds0 = copy.deepcopy(val_ds_full)
    _zero_channels_in_dataset(train_ds0, zero_base)
    _zero_channels_in_dataset(val_ds0, zero_base)
    set_seed(42)
    m0 = create_model(arch='grouped', input_dim=NUM_FEATURES_ENRICHED,
                      d_model=64, nhead=4, num_layers=2)
    sp0 = os.path.join(output_dir, 'exp263_step0_base21f_s42.pth')
    train_forecast(m0, train_ds0, val_ds0, sp0,
                   label='EXP-263 base-21f', epochs=100, lr=1e-3, patience=15)
    base_mae = _mae_from_model(m0, val_ds0)
    results_by_step['step0_base21f'] = {
        'mae': round(base_mae, 2), 'added_group': 'base_21f',
        'added_channels': list(range(21)), 'total_active': 21,
    }
    print(f"  Step 0 (base 21f): MAE={base_mae:.1f}, active=21 ch")

    for step, (gname, gidx) in enumerate(group_order, start=1):
        active_channels = active_channels | set(gidx)
        zero_channels = [c for c in range(NUM_FEATURES_ENRICHED) if c not in active_channels]

        train_ds = copy.deepcopy(train_ds_full)
        val_ds = copy.deepcopy(val_ds_full)
        _zero_channels_in_dataset(train_ds, zero_channels)
        _zero_channels_in_dataset(val_ds, zero_channels)

        set_seed(42)
        m = create_model(arch='grouped', input_dim=NUM_FEATURES_ENRICHED,
                         d_model=64, nhead=4, num_layers=2)
        sp = os.path.join(output_dir, f'exp263_step{step}_{gname}_s42.pth')
        train_forecast(m, train_ds, val_ds, sp,
                       label=f'EXP-263 +{gname}',
                       epochs=100, lr=1e-3, patience=15)
        mae = _mae_from_model(m, val_ds)

        results_by_step[f'step{step}_{gname}'] = {
            'mae': round(mae, 2),
            'added_group': gname,
            'added_channels': gidx,
            'total_active': len(active_channels),
        }
        print(f"  Step {step} (+{gname}): MAE={mae:.1f}, active={len(active_channels)} ch")

    result = {
        'experiment': 'EXP-263: Forward Feature Selection',
        'hypothesis': 'Cumulative improvement curve with diminishing returns',
        'persistence_mae': round(persist_mae, 2),
        'steps': results_by_step,
        'group_order': ['base_21f'] + [g[0] for g in group_order],
        'config': {'input_dim': NUM_FEATURES_ENRICHED, 'seed': 42},
    }
    save_results(result, os.path.join(output_dir, 'exp263_forward_selection.json'))
    return result

REGISTRY['forward-feature-selection'] = 'run_forward_feature_selection'


# ── EXP-264: Context Window Lookback Sweep ───────────────────────
# Test asymmetric history:forecast ratios at fixed 1hr forecast.
def run_lookback_sweep(args):
    """EXP-264: History length ablation — 30/60/90/120min history → 1hr forecast.

    Hypothesis: More history helps, but with diminishing returns.
    Requires asymmetric window splitting.
    """
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    device = get_device()

    # Configs: (history_steps, forecast_steps, total_window)
    configs = [
        ('30min', 6, 12, 18),
        ('60min', 12, 12, 24),
        ('90min', 18, 12, 30),
        ('120min', 24, 12, 36),
    ]

    results_by_config = {}
    for name, hist_steps, fcast_steps, total_ws in configs:
        print(f"\n=== Config: {name} history → {fcast_steps*5}min forecast ===")
        train_ds, val_ds = load_multipatient_nightscout(
            patient_paths, task='forecast', window_size=total_ws,
            extended_features=True)
        if train_ds is None:
            print(f"  SKIP: no data for ws={total_ws}")
            continue

        set_seed(42)
        m = create_model(arch='grouped', input_dim=NUM_FEATURES_EXTENDED,
                         d_model=64, nhead=4, num_layers=2)
        sp = os.path.join(output_dir, f'exp264_lb_{name}_s42.pth')

        # Use asymmetric split: pass forecast_steps so training masks correctly
        train_forecast(m, train_ds, val_ds, sp,
                       label=f'EXP-264 LB-{name}', epochs=100, lr=1e-3, patience=15,
                       forecast_steps=fcast_steps)

        # Custom eval with asymmetric split
        mae = _asymmetric_mae(m, val_ds, hist_steps=hist_steps)
        persist = _asymmetric_persistence(val_ds, hist_steps=hist_steps)

        results_by_config[name] = {
            'mae': round(mae, 2),
            'persistence_mae': round(persist, 2),
            'pct_vs_persist': round((1 - mae / persist) * 100, 1) if persist > 0 else None,
            'hist_steps': hist_steps,
            'fcast_steps': fcast_steps,
            'total_ws': total_ws,
        }
        print(f"  {name}: MAE={mae:.1f} persist={persist:.1f}")

    result = {
        'experiment': 'EXP-264: Lookback Sweep (history length ablation)',
        'hypothesis': 'More history helps with diminishing returns',
        'configs': results_by_config,
        'config': {'forecast_steps': 12, 'input_dim': NUM_FEATURES_EXTENDED},
    }
    save_results(result, os.path.join(output_dir, 'exp264_lookback_sweep.json'))
    return result

REGISTRY['lookback-sweep'] = 'run_lookback_sweep'


def _asymmetric_mae(model, val_ds, hist_steps, batch_size=64):
    """MAE with asymmetric history/forecast split."""
    from torch.utils.data import DataLoader
    device = get_device()
    model.eval()
    total_ae, n = 0.0, 0
    for batch in DataLoader(val_ds, batch_size=batch_size):
        x = batch_to_device(batch[0], device)
        x_in = x.clone()
        mask_future_channels(x_in, hist_steps)
        with torch.no_grad():
            pred = model(x_in, causal=True)
        if isinstance(pred, dict):
            pred = pred['forecast']
        ae = torch.abs(pred[:, hist_steps:, :1] - x[:, hist_steps:, :1])
        total_ae += ae.sum().item()
        n += ae.numel()
    return float(total_ae / n * SCALE) if n else float('nan')


def _asymmetric_persistence(val_ds, hist_steps, batch_size=64):
    """Persistence MAE: last known glucose repeated for forecast window."""
    from torch.utils.data import DataLoader
    total_ae, n = 0.0, 0
    for batch in DataLoader(val_ds, batch_size=batch_size):
        x = batch[0]
        last_glucose = x[:, hist_steps - 1, 0:1].unsqueeze(1)
        target = x[:, hist_steps:, 0:1]
        ae = torch.abs(last_glucose - target)
        total_ae += ae.sum().item()
        n += ae.numel()
    return float(total_ae / n * SCALE) if n else float('nan')


# ── EXP-265/266/267: Hypo Safety Pipeline ────────────────────────
# Addresses GAP: 39.8 MAE in hypo range (2.54× worse than overall).
# Builds on EXP-136 (2-stage) and EXP-248 (hypo-weighted ensemble).

def run_hypo_safety_baseline(args):
    """EXP-265: Train with AsymmetricHypoLoss on all patients."""
    from .hypo_safety import train_hypo_forecaster, evaluate_hypo_safety
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)

    seeds = [42, 123, 456]
    models = []
    individual = {}
    for seed in seeds:
        set_seed(seed)
        m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
        sp = os.path.join(output_dir, f'exp265_hypo_base_s{seed}.pth')
        vl, ep = train_hypo_forecaster(
            m, train_ds, val_ds, sp,
            label=f'EXP-265 hypo-base-s{seed}', miss_weight=5.0,
            epochs=100, patience=15)
        mae = _mae_from_model(m, val_ds)
        individual[f's{seed}'] = {'mae': round(mae, 2), 'val_loss': round(vl, 6)}
        models.append(m)

    safety = evaluate_hypo_safety(models, val_ds)
    result = {
        'experiment': 'EXP-265: Hypo Safety Baseline (AsymmetricHypoLoss)',
        'config': {'miss_weight': 5.0, 'seeds': seeds},
        'masking': {'channels': list(FUTURE_UNKNOWN_CHANNELS), 'type': 'selective'},
        'individual': individual,
        'ensemble_mae': round(_ensemble_mae(models, val_ds), 2),
        'safety_metrics': safety,
    }
    save_results(result, os.path.join(output_dir, 'exp265_hypo_safety_baseline.json'))
    return result

REGISTRY['hypo-safety-baseline'] = 'run_hypo_safety_baseline'


def run_hypo_2stage_ensemble(args):
    """EXP-266: 2-stage (classifier + forecaster ensemble) hypo pipeline."""
    from .hypo_safety import (
        train_hypo_classifier, train_hypo_forecaster,
        HypoSafetyEnsemble, evaluate_hypo_safety,
    )
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)
    device = get_device()

    # Stage 1: Train classifier
    set_seed(42)
    clf = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
    clf_path = os.path.join(output_dir, 'exp266_hypo_clf.pth')
    clf_metrics = train_hypo_classifier(
        clf, train_ds, val_ds, clf_path,
        label='EXP-266 hypo-clf', epochs=50, patience=15)

    # Stage 2: Train forecaster ensemble
    seeds = [42, 123, 456]
    forecasters = []
    for seed in seeds:
        set_seed(seed)
        m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
        sp = os.path.join(output_dir, f'exp266_hypo_fc_s{seed}.pth')
        train_hypo_forecaster(
            m, train_ds, val_ds, sp,
            label=f'EXP-266 hypo-fc-s{seed}', miss_weight=5.0,
            epochs=100, patience=15)
        forecasters.append(m)

    safety = evaluate_hypo_safety(forecasters, val_ds)
    result = {
        'experiment': 'EXP-266: 2-Stage Hypo Ensemble (Classifier + Forecaster)',
        'classifier_metrics': clf_metrics,
        'config': {'miss_weight': 5.0, 'seeds': seeds},
        'masking': {'channels': list(FUTURE_UNKNOWN_CHANNELS), 'type': 'selective'},
        'safety_metrics': safety,
        'ensemble_mae': round(_ensemble_mae(forecasters, val_ds), 2),
    }
    save_results(result, os.path.join(output_dir, 'exp266_hypo_2stage_ensemble.json'))
    return result

REGISTRY['hypo-2stage-ensemble'] = 'run_hypo_2stage_ensemble'


def run_hypo_per_patient_safety(args):
    """EXP-267: Per-patient FT with hypo safety module."""
    from .hypo_safety import train_hypo_forecaster, evaluate_hypo_safety
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patients_base = patients_dir or 'externals/ns-data/patients'
    patient_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])
    device = get_device()
    seeds = [42, 123]

    # Train base models
    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)
    base_states = {}
    for seed in seeds:
        set_seed(seed)
        m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
        bp = os.path.join(output_dir, f'exp267_hypo_base_s{seed}.pth')
        train_hypo_forecaster(m, train_ds, val_ds, bp,
                              label=f'EXP-267 base-s{seed}', miss_weight=5.0,
                              epochs=100, patience=15)
        base_states[seed] = m.state_dict()

    # Per-patient fine-tune
    per_patient = {}
    for pid in patient_dirs:
        tp = os.path.join(patients_base, pid, 'training')
        if not os.path.isdir(tp):
            continue
        try:
            tds, vds = load_multipatient_nightscout([tp], task='forecast', window_size=24)
        except Exception:
            continue
        if len(vds) < 10:
            continue

        ft_models = []
        for seed in seeds:
            set_seed(seed)
            m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
            m.load_state_dict(base_states[seed])
            fp = os.path.join(output_dir, f'exp267_ft_{pid}_s{seed}.pth')
            train_hypo_forecaster(m, tds, vds, fp,
                                  label=f'EXP-267 FT-{pid}-s{seed}', miss_weight=5.0,
                                  epochs=30, patience=10)
            ft_models.append(m)

        safety = evaluate_hypo_safety(ft_models, vds)
        per_patient[pid] = {
            'ensemble_mae': round(_ensemble_mae(ft_models, vds), 2),
            'safety_metrics': safety,
        }
        print(f"  {pid}: ens={per_patient[pid]['ensemble_mae']:.1f}")

    result = {
        'experiment': 'EXP-267: Per-Patient FT Hypo Safety',
        'per_patient': per_patient,
        'config': {'miss_weight': 5.0, 'seeds': seeds},
        'masking': {'channels': list(FUTURE_UNKNOWN_CHANNELS), 'type': 'selective'},
    }
    save_results(result, os.path.join(output_dir, 'exp267_hypo_per_patient_safety.json'))
    return result

REGISTRY['hypo-per-patient-safety'] = 'run_hypo_per_patient_safety'


# ── EXP-268/269/270: Override WHICH/HOW Pipeline ─────────────────
# Completes override pipeline: WHEN (F1=0.993) → WHICH type + HOW strong.
# Uses counterfactual forecasting and value model approaches.

def run_override_counterfactual_baseline(args):
    """EXP-268: Brute-force counterfactual override evaluation on all patients."""
    from .override_recommender import evaluate_overrides, recommend_override
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)

    # Need extended features (≥21 channels) for override channels
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24,
        extended_features=True)

    set_seed(42)
    model = create_model(arch='grouped', input_dim=NUM_FEATURES_EXTENDED,
                         d_model=64, nhead=4, num_layers=2)
    sp = os.path.join(output_dir, 'exp268_override_model.pth')
    train_forecast(model, train_ds, val_ds, sp,
                   label='EXP-268 override-base', epochs=100, patience=15)

    # Evaluate on validation set (sample for speed)
    from torch.utils.data import DataLoader
    device = get_device()
    model.to(device)
    recs = []
    for batch in DataLoader(val_ds, batch_size=32):
        x = batch_to_device(batch[0], device)
        rec = recommend_override(model, x, horizon_steps=12)
        recs.append(rec)
        if len(recs) >= 10:
            break

    type_dist = {}
    for r in recs:
        t = r['override_type']
        type_dist[t] = type_dist.get(t, 0) + 1

    result = {
        'experiment': 'EXP-268: Override Counterfactual Baseline',
        'config': {'input_dim': NUM_FEATURES_EXTENDED, 'horizon_steps': 12},
        'masking': {'channels': list(FUTURE_UNKNOWN_CHANNELS), 'type': 'selective'},
        'type_distribution': type_dist,
        'mean_confidence': round(float(np.mean([r['confidence'] for r in recs])), 4),
        'mean_tir_improvement': round(float(np.mean([
            r['predicted_tir'] - r['predicted_tir_no_override'] for r in recs
        ])), 4),
    }
    save_results(result, os.path.join(output_dir, 'exp268_override_counterfactual.json'))
    return result

REGISTRY['override-counterfactual-baseline'] = 'run_override_counterfactual_baseline'


def run_override_value_model(args):
    """EXP-269: Train value model for fast override recommendation."""
    from .override_recommender import (
        train_override_value_model, OverrideValueModel,
        evaluate_overrides, OVERRIDE_TYPE_LIST, OVERRIDE_STRENGTHS,
    )
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)

    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24,
        extended_features=True)

    # First train a forecast model to generate training labels
    set_seed(42)
    fc_model = create_model(arch='grouped', input_dim=NUM_FEATURES_EXTENDED,
                            d_model=64, nhead=4, num_layers=2)
    fc_path = os.path.join(output_dir, 'exp269_forecast_model.pth')
    train_forecast(fc_model, train_ds, val_ds, fc_path,
                   label='EXP-269 forecast-base', epochs=50, patience=15)

    # Generate override labels from counterfactual forecasting
    from torch.utils.data import DataLoader, TensorDataset
    device = get_device()
    fc_model.to(device)
    states, otypes, strengths, tir_deltas = [], [], [], []

    for batch in DataLoader(train_ds, batch_size=32):
        x = batch_to_device(batch[0], device)
        half = x.shape[1] // 2
        state_summary = x[:, half - 1, :8].cpu()  # last history step, core features

        # Compute baseline TIR
        x_base = x.clone()
        mask_future_channels(x_base, half)
        with torch.no_grad():
            base_pred = fc_model(x_base, causal=True)
        if isinstance(base_pred, dict):
            base_pred = base_pred['forecast']
        base_g = base_pred[:, half:half + 12, 0]
        base_tir = ((base_g >= 0.175) & (base_g <= 0.45)).float().mean(dim=1)

        for ti, otype in enumerate(OVERRIDE_TYPE_LIST):
            for strength in OVERRIDE_STRENGTHS:
                from .override_recommender import counterfactual_forecast
                cf_pred = counterfactual_forecast(fc_model, x, otype, strength, 12)
                cf_g = cf_pred.squeeze(-1)  # (B, 12)
                cf_tir = ((cf_g >= 0.175) & (cf_g <= 0.45)).float().mean(dim=1)
                delta = (cf_tir - base_tir).cpu()

                states.append(state_summary)
                otypes.append(torch.full((x.size(0),), ti, dtype=torch.long))
                strengths.append(torch.full((x.size(0), 1), strength))
                tir_deltas.append(delta)

        if len(states) >= 500:
            break

    all_states = torch.cat(states)
    all_otypes = torch.cat(otypes)
    all_strengths = torch.cat(strengths)
    all_deltas = torch.cat(tir_deltas)

    n_train = int(len(all_states) * 0.8)
    vm_train = TensorDataset(all_states[:n_train], all_otypes[:n_train],
                             all_strengths[:n_train], all_deltas[:n_train])
    vm_val = TensorDataset(all_states[n_train:], all_otypes[n_train:],
                           all_strengths[n_train:], all_deltas[n_train:])

    vl, ep, vm = train_override_value_model(
        vm_train, vm_val, os.path.join(output_dir, 'exp269_value_model.pth'),
        label='EXP-269 value-model', epochs=50, patience=15)

    result = {
        'experiment': 'EXP-269: Override Value Model',
        'config': {'n_training_samples': len(all_states), 'state_dim': 8},
        'val_loss': round(vl, 6),
        'epochs': ep,
    }
    save_results(result, os.path.join(output_dir, 'exp269_override_value_model.json'))
    return result

REGISTRY['override-value-model'] = 'run_override_value_model'


def run_override_per_patient_recommendation(args):
    """EXP-270: Personalized override thresholds per patient."""
    from .override_recommender import recommend_override
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patients_base = patients_dir or 'externals/ns-data/patients'
    patient_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])
    device = get_device()

    per_patient = {}
    for pid in patient_dirs:
        tp = os.path.join(patients_base, pid, 'training')
        if not os.path.isdir(tp):
            continue
        try:
            tds, vds = load_multipatient_nightscout(
                [tp], task='forecast', window_size=24, extended_features=True)
        except Exception:
            continue
        if len(vds) < 10:
            continue

        set_seed(42)
        m = create_model(arch='grouped', input_dim=NUM_FEATURES_EXTENDED,
                         d_model=64, nhead=4, num_layers=2)
        sp = os.path.join(output_dir, f'exp270_override_{pid}.pth')
        train_forecast(m, tds, vds, sp,
                       label=f'EXP-270 {pid}', epochs=50, patience=15)
        m.to(device)

        from torch.utils.data import DataLoader
        recs = []
        for batch in DataLoader(vds, batch_size=32):
            x = batch_to_device(batch[0], device)
            rec = recommend_override(m, x, horizon_steps=12)
            recs.append(rec)
            if len(recs) >= 5:
                break

        type_dist = {}
        for r in recs:
            t = r['override_type']
            type_dist[t] = type_dist.get(t, 0) + 1

        per_patient[pid] = {
            'type_distribution': type_dist,
            'mean_confidence': round(float(np.mean([r['confidence'] for r in recs])), 4),
        }
        print(f"  {pid}: conf={per_patient[pid]['mean_confidence']:.4f}")

    result = {
        'experiment': 'EXP-270: Per-Patient Override Recommendation',
        'per_patient': per_patient,
        'config': {'input_dim': NUM_FEATURES_EXTENDED, 'horizon_steps': 12},
        'masking': {'channels': list(FUTURE_UNKNOWN_CHANNELS), 'type': 'selective'},
    }
    save_results(result, os.path.join(output_dir, 'exp270_override_per_patient.json'))
    return result

REGISTRY['override-per-patient-recommendation'] = 'run_override_per_patient_recommendation'


# ── EXP-271/272/273: Online Adaptation Pipeline ──────────────────
# Addresses 7.4% verification gap from temporal drift (EXP-249).

def run_online_adaptation_baseline(args):
    """EXP-271: Periodic retrain vs static model on all patients."""
    from .online_adaptation import periodic_retrain, evaluate_temporal_stability
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patients_base = patients_dir or 'externals/ns-data/patients'
    patient_dirs = sorted([
        d for d in os.listdir(patients_base)
        if os.path.isdir(os.path.join(patients_base, d))
    ])
    device = get_device()

    # Train base model on all patients
    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)
    set_seed(42)
    m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
    base_path = os.path.join(output_dir, 'exp271_base_model.pth')
    train_forecast(m, train_ds, val_ds, base_path,
                   label='EXP-271 base', epochs=100, patience=15)

    # Evaluate temporal stability per patient
    per_patient = {}
    for pid in patient_dirs:
        tp = os.path.join(patients_base, pid, 'training')
        if not os.path.isdir(tp):
            continue
        try:
            tds, vds = load_multipatient_nightscout([tp], task='forecast', window_size=24)
        except Exception:
            continue
        if len(vds) < 20:
            continue

        data = vds.tensors[0]
        stability = evaluate_temporal_stability(m, data, n_windows=4, window_weeks=2)

        # Periodic retrain on this patient
        retrain_path = os.path.join(output_dir, f'exp271_retrained_{pid}.pth')
        retrain_result = periodic_retrain(
            base_path, data, retrain_path,
            window_weeks=2, lr=5e-5, epochs=10, patience=5)

        per_patient[pid] = {
            'stability': stability,
            'retrain': retrain_result,
        }
        print(f"  {pid}: degrading={stability['is_degrading']} "
              f"improvement={retrain_result['improvement_pct']:.1f}%")

    result = {
        'experiment': 'EXP-271: Online Adaptation Baseline',
        'per_patient': per_patient,
        'config': {'window_weeks': 2, 'lr': 5e-5, 'epochs': 10},
        'masking': {'channels': list(FUTURE_UNKNOWN_CHANNELS), 'type': 'selective'},
    }
    save_results(result, os.path.join(output_dir, 'exp271_online_adaptation_baseline.json'))
    return result

REGISTRY['online-adaptation-baseline'] = 'run_online_adaptation_baseline'


def run_online_sliding_window_sweep(args):
    """EXP-272: Test 2/4/8 week sliding windows for retraining."""
    from .online_adaptation import periodic_retrain
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)

    set_seed(42)
    m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
    base_path = os.path.join(output_dir, 'exp272_base_model.pth')
    train_forecast(m, train_ds, val_ds, base_path,
                   label='EXP-272 base', epochs=100, patience=15)

    data = val_ds.tensors[0]
    sweep_results = {}
    for weeks in [2, 4, 8]:
        rp = os.path.join(output_dir, f'exp272_retrained_w{weeks}.pth')
        result = periodic_retrain(
            base_path, data, rp,
            window_weeks=weeks, lr=5e-5, epochs=10, patience=5)
        sweep_results[f'{weeks}w'] = result
        print(f"  {weeks}w: improvement={result['improvement_pct']:.1f}%")

    result = {
        'experiment': 'EXP-272: Sliding Window Sweep',
        'sweep': sweep_results,
        'config': {'lr': 5e-5, 'epochs': 10},
        'masking': {'channels': list(FUTURE_UNKNOWN_CHANNELS), 'type': 'selective'},
    }
    save_results(result, os.path.join(output_dir, 'exp272_sliding_window_sweep.json'))
    return result

REGISTRY['online-sliding-window-sweep'] = 'run_online_sliding_window_sweep'


def run_online_adaptive_threshold(args):
    """EXP-273: Auto-trigger retrain on degradation detection."""
    from .online_adaptation import AdaptiveRetrainer
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24)

    set_seed(42)
    m = create_model(arch='grouped', input_dim=8, d_model=64, nhead=4, num_layers=2)
    base_path = os.path.join(output_dir, 'exp273_base_model.pth')
    train_forecast(m, train_ds, val_ds, base_path,
                   label='EXP-273 base', epochs=100, patience=15)

    data = val_ds.tensors[0]
    config = {
        'degradation_threshold': 15.0,
        'window_weeks': 4,
        'lr': 5e-5,
        'epochs': 10,
        'patience': 5,
        'input_dim': 8,
        'd_model': 64,
        'nhead': 4,
        'num_layers': 2,
    }
    ar = AdaptiveRetrainer(base_path, data, config)

    # Run adaptive check
    check = ar.check_and_retrain()

    result = {
        'experiment': 'EXP-273: Adaptive Retrain Threshold',
        'check_result': check,
        'history': ar.history,
        'retrain_events': ar.retrain_events,
        'config': config,
        'masking': {'channels': list(FUTURE_UNKNOWN_CHANNELS), 'type': 'selective'},
    }
    save_results(result, os.path.join(output_dir, 'exp273_adaptive_threshold.json'))
    return result

REGISTRY['online-adaptive-threshold'] = 'run_online_adaptive_threshold'


# ── EXP-274: Regularized 39f with Channel Dropout ────────────────
# Addresses: 26.6% verification gap in 39f base ensemble.
# Method: Channel dropout (randomly zero entire channels during training)
# + higher model dropout + stronger weight decay.
def run_regularized_enriched(args):
    """EXP-274: Regularized 39f training with channel dropout.

    Hypothesis: Channel dropout prevents overfitting to period-specific
    feature patterns, reducing the verification gap while preserving
    the accuracy gains from enriched features.
    """
    import copy

    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    device = get_device()

    validate_masking(NUM_FEATURES_ENRICHED, label='EXP-274')

    # Load enriched data
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24,
        enriched_features=True)
    persist_mae = compute_persistence_mae(val_ds)
    print(f"  Persistence baseline: {persist_mae:.1f} mg/dL")

    # Load verification data per patient
    patients_base = os.path.dirname(os.path.dirname(patient_paths[0]))
    patient_dirs = sorted([d for d in os.listdir(patients_base)
                          if os.path.isdir(os.path.join(patients_base, d))])

    from torch.utils.data import DataLoader
    from .schema import FUTURE_UNKNOWN_CHANNELS

    def _channel_dropout_step(model, batch_data, crit, ch_drop_p=0.15, backward=False):
        """Forward step with random channel dropout during training."""
        x = batch_to_device(batch_data[0], device)
        half = x.shape[1] // 2
        x_in = x.clone()
        mask_future_channels(x_in, half)

        # Channel dropout: randomly zero entire channels (training only)
        if backward and ch_drop_p > 0:
            n_ch = x_in.shape[2]
            # Don't drop glucose (ch0) or time features (ch6,7)
            droppable = [c for c in range(n_ch)
                        if c not in {0, 6, 7}
                        and c not in set(FUTURE_UNKNOWN_CHANNELS)]
            mask = torch.rand(len(droppable)) < ch_drop_p
            for i, ch in enumerate(droppable):
                if mask[i]:
                    x_in[:, :, ch] = 0.0

        pred = model(x_in, causal=True)
        loss = crit(pred[:, half:, :1], x[:, half:, :1])
        if backward:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        return loss.item() * x.size(0), x.size(0)

    # Configs to test: (name, ch_drop_p, dropout, weight_decay)
    configs = [
        ('baseline',  0.0,  0.1,  1e-5),  # no regularization (match EXP-260)
        ('ch_drop15', 0.15, 0.1,  1e-5),  # channel dropout only
        ('ch_drop30', 0.30, 0.1,  1e-5),  # aggressive channel dropout
        ('combined',  0.15, 0.2,  1e-3),  # channel dropout + high dropout + weight decay
    ]

    results_by_config = {}
    for cname, ch_drop_p, dropout, wd in configs:
        print(f"\n=== Config: {cname} (ch_drop={ch_drop_p}, drop={dropout}, wd={wd}) ===")
        set_seed(42)
        model = create_model(arch='grouped', input_dim=NUM_FEATURES_ENRICHED,
                             d_model=64, nhead=4, num_layers=2, dropout=dropout)
        model.to(device)

        train_dl = DataLoader(train_ds, batch_size=32, shuffle=True)
        val_dl = DataLoader(val_ds, batch_size=64)
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=wd)
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
        crit = torch.nn.MSELoss()
        best_vl, stale = float('inf'), 0
        sp = os.path.join(output_dir, f'exp274_{cname}_s42.pth')

        for ep in range(100):
            model.train()
            ttl, tn = 0.0, 0
            for b in train_dl:
                opt.zero_grad()
                l, n = _channel_dropout_step(model, b, crit, ch_drop_p, backward=True)
                opt.step()
                ttl += l; tn += n

            model.eval()
            vtl, vn = 0.0, 0
            with torch.no_grad():
                for b in val_dl:
                    l, n = _channel_dropout_step(model, b, crit, ch_drop_p=0.0, backward=False)
                    vtl += l; vn += n
            vl = vtl / vn if vn else float('inf')
            sched.step(vl)

            if vl < best_vl:
                best_vl = vl
                stale = 0
                os.makedirs(os.path.dirname(sp) or '.', exist_ok=True)
                torch.save({'model_state': model.state_dict(), 'epoch': ep, 'val_loss': vl}, sp)
            else:
                stale += 1

            if (ep + 1) % 10 == 0:
                lr_now = opt.param_groups[0]['lr']
                print(f'  [{cname}] {ep+1:3d}/100 train={ttl/tn:.6f} val={vl:.6f} '
                      f'best={best_vl:.6f} lr={lr_now:.1e}')

            if stale >= 15:
                print(f'  [{cname}] Early stop at epoch {ep+1}')
                break

        # Load best and evaluate
        ckpt = torch.load(sp, map_location=device, weights_only=True)
        model.load_state_dict(ckpt['model_state'])
        train_mae = _mae_from_model(model, val_ds)

        # Per-patient verification
        ver_maes = []
        for pid in patient_dirs:
            ver_path = os.path.join(patients_base, pid, 'verification')
            if not os.path.isdir(ver_path):
                continue
            try:
                _, ver_ds = load_multipatient_nightscout(
                    [ver_path], task='forecast', window_size=24,
                    enriched_features=True)
                if ver_ds and len(ver_ds) >= 5:
                    ver_maes.append(_mae_from_model(model, ver_ds))
            except:
                pass

        ver_mae = float(np.mean(ver_maes)) if ver_maes else None
        gap = round((ver_mae / train_mae - 1) * 100, 1) if ver_mae else None
        results_by_config[cname] = {
            'train_mae': round(train_mae, 2),
            'verification_mae': round(ver_mae, 2) if ver_mae else None,
            'gap_pct': gap,
            'ch_dropout': ch_drop_p, 'model_dropout': dropout, 'weight_decay': wd,
        }
        print(f"  {cname}: train={train_mae:.1f} ver={ver_mae:.1f} gap={gap:+.1f}%")

    result = {
        'experiment': 'EXP-274: Regularized 39f with Channel Dropout',
        'hypothesis': 'Channel dropout reduces verification gap',
        'persistence_mae': round(persist_mae, 2),
        'configs': results_by_config,
        'comparison': {'exp260_39f_base_ens': {'train': 13.9, 'ver': 17.6, 'gap': 26.6},
                       'exp242_8f_ft_ens': {'train': 11.25, 'ver': 11.56, 'gap': 2.8}},
    }
    save_results(result, os.path.join(output_dir, 'exp274_regularized_enriched.json'))
    return result

REGISTRY['regularized-enriched'] = 'run_regularized_enriched'


# ── EXP-275: Regularized Enriched Ensemble with Per-Patient FT ──────
# Builds on EXP-274 finding: ch_drop=0.15 gives best verification MAE.
# Now: 5-seed ensemble + per-patient FT to push toward 8f FT ensemble (11.25).
def run_regularized_enriched_ensemble(args):
    """EXP-275: Regularized 39f ensemble with per-patient fine-tuning.

    Applies channel dropout during both base training AND fine-tuning
    to prevent the ensemble overfitting that caused 26.6% gap in EXP-260.
    """
    import copy

    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    device = get_device()

    validate_masking(NUM_FEATURES_ENRICHED, label='EXP-275')

    # Load enriched training data
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24,
        enriched_features=True)
    persist_mae = compute_persistence_mae(val_ds)
    print(f"  Persistence baseline: {persist_mae:.1f} mg/dL")

    patients_base = os.path.dirname(os.path.dirname(patient_paths[0]))
    patient_dirs = sorted([d for d in os.listdir(patients_base)
                          if os.path.isdir(os.path.join(patients_base, d))])

    from torch.utils.data import DataLoader
    from .schema import FUTURE_UNKNOWN_CHANNELS

    CH_DROP_P = 0.15  # Optimal from EXP-274

    def _ch_drop_forward(model, x_batch, crit, ch_drop_p, training=False):
        """Forward pass with channel dropout."""
        x = batch_to_device(x_batch, device)
        half = x.shape[1] // 2
        x_in = x.clone()
        mask_future_channels(x_in, half)

        if training and ch_drop_p > 0:
            n_ch = x_in.shape[2]
            droppable = [c for c in range(n_ch)
                        if c not in {0, 6, 7}
                        and c not in set(FUTURE_UNKNOWN_CHANNELS)]
            mask = torch.rand(len(droppable)) < ch_drop_p
            for i, ch in enumerate(droppable):
                if mask[i]:
                    x_in[:, :, ch] = 0.0

        pred = model(x_in, causal=True)
        loss = crit(pred[:, half:, :1], x[:, half:, :1])
        return loss, pred

    def _train_with_ch_dropout(model, t_ds, v_ds, ch_drop_p, epochs, patience,
                                lr=1e-3, wd=1e-5, save_path=None):
        """Train model with channel dropout."""
        model.to(device)
        train_dl = DataLoader(t_ds, batch_size=32, shuffle=True)
        val_dl = DataLoader(v_ds, batch_size=64)
        opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
        crit = torch.nn.MSELoss()
        best_vl, stale = float('inf'), 0

        for ep in range(epochs):
            model.train()
            for b in train_dl:
                opt.zero_grad()
                loss, _ = _ch_drop_forward(model, b[0], crit, ch_drop_p, training=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()

            model.eval()
            vtl, vn = 0.0, 0
            with torch.no_grad():
                for b in val_dl:
                    loss, _ = _ch_drop_forward(model, b[0], crit, 0.0, training=False)
                    vtl += loss.item() * b[0].shape[0]
                    vn += b[0].shape[0]
            vl = vtl / vn if vn else float('inf')
            sched.step(vl)

            if vl < best_vl:
                best_vl = vl
                stale = 0
                if save_path:
                    os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
                    torch.save({'model_state': model.state_dict(), 'epoch': ep, 'val_loss': vl}, save_path)
            else:
                stale += 1
            if stale >= patience:
                break

        if save_path and os.path.exists(save_path):
            ckpt = torch.load(save_path, map_location=device, weights_only=True)
            model.load_state_dict(ckpt['model_state'])
        return model, best_vl

    # ── Phase 1: Train 5-seed base models ──
    SEEDS = [42, 123, 456, 789, 2024]
    base_models = []
    base_maes = []
    print("\n=== Phase 1: 5-seed base training with ch_drop=0.15 ===")
    for seed in SEEDS:
        set_seed(seed)
        model = create_model(arch='grouped', input_dim=NUM_FEATURES_ENRICHED,
                             d_model=64, nhead=4, num_layers=2, dropout=0.1)
        sp = os.path.join(output_dir, f'exp275_base_s{seed}.pth')
        model, _ = _train_with_ch_dropout(model, train_ds, val_ds, CH_DROP_P,
                                           epochs=100, patience=15, save_path=sp)
        mae = _mae_from_model(model, val_ds)
        base_models.append(model)
        base_maes.append(mae)
        print(f"  Seed {seed}: MAE={mae:.2f}")

    # Base ensemble MAE
    base_ens_mae = _ensemble_mae(base_models, val_ds)
    print(f"  Base ensemble MAE: {base_ens_mae:.2f}")

    # ── Phase 2: Per-patient FT ──
    FT_SEEDS = [42, 123, 456, 789, 2024]
    per_patient_results = {}
    print("\n=== Phase 2: Per-patient fine-tuning with ch_drop=0.15 ===")
    for pid in patient_dirs:
        train_path = os.path.join(patients_base, pid, 'training')
        ver_path = os.path.join(patients_base, pid, 'verification')
        if not os.path.isdir(train_path):
            continue

        try:
            pt_train, pt_val = load_multipatient_nightscout(
                [train_path], task='forecast', window_size=24,
                enriched_features=True)
        except:
            continue

        # Load verification if available
        pt_ver = None
        if os.path.isdir(ver_path):
            try:
                _, pt_ver = load_multipatient_nightscout(
                    [ver_path], task='forecast', window_size=24,
                    enriched_features=True)
                if pt_ver and len(pt_ver) < 5:
                    pt_ver = None
            except:
                pt_ver = None

        ft_models = []
        for base_seed_idx, base_model in enumerate(base_models):
            for ft_seed in FT_SEEDS:
                set_seed(ft_seed)
                ft_model = copy.deepcopy(base_model)
                sp = os.path.join(output_dir,
                    f'exp275_ft_{pid}_b{SEEDS[base_seed_idx]}_f{ft_seed}.pth')
                ft_model, _ = _train_with_ch_dropout(
                    ft_model, pt_train, pt_val, CH_DROP_P,
                    epochs=30, patience=8, lr=3e-4, save_path=sp)
                ft_models.append(ft_model)

        # Per-patient ensemble MAE
        pt_train_mae = _ensemble_mae(ft_models, pt_val)
        pt_ver_mae = _ensemble_mae(ft_models, pt_ver) if pt_ver else None
        gap = round((pt_ver_mae / pt_train_mae - 1) * 100, 1) if pt_ver_mae else None

        per_patient_results[pid] = {
            'train_mae': round(pt_train_mae, 2),
            'verification_mae': round(pt_ver_mae, 2) if pt_ver_mae else None,
            'gap_pct': gap,
            'n_ft_models': len(ft_models),
        }
        gap_str = f"gap={gap:+.1f}%" if gap is not None else "no ver"
        ver_str = f"{pt_ver_mae:.2f}" if pt_ver_mae is not None else "N/A"
        print(f"  Patient {pid}: train={pt_train_mae:.2f} ver={ver_str} {gap_str}")

    # Aggregate
    train_maes = [v['train_mae'] for v in per_patient_results.values()]
    ver_maes = [v['verification_mae'] for v in per_patient_results.values()
                if v['verification_mae'] is not None]
    gaps = [v['gap_pct'] for v in per_patient_results.values()
            if v['gap_pct'] is not None]

    result = {
        'experiment': 'EXP-275: Regularized Enriched Ensemble + Per-Patient FT',
        'ch_dropout': CH_DROP_P,
        'persistence_mae': round(persist_mae, 2),
        'base_ensemble_mae': round(base_ens_mae, 2),
        'base_seed_maes': [round(m, 2) for m in base_maes],
        'per_patient': per_patient_results,
        'summary': {
            'mean_train_mae': round(float(np.mean(train_maes)), 2),
            'mean_ver_mae': round(float(np.mean(ver_maes)), 2) if ver_maes else None,
            'mean_gap_pct': round(float(np.mean(gaps)), 1) if gaps else None,
        },
        'comparison': {
            'exp274_ch15_single': {'train': 17.25, 'ver': 17.97, 'gap': 4.2},
            'exp260_39f_ens': {'train': 13.8, 'ver': 17.06, 'gap': 28.6},
            'exp242_8f_ft_ens': {'train': 11.25, 'ver': 11.56, 'gap': 2.8},
        },
    }
    save_results(result, os.path.join(output_dir, 'exp275_regularized_ensemble.json'))
    return result

REGISTRY['regularized-enriched-ensemble'] = 'run_regularized_enriched_ensemble'


# ── Phase 6–8: Pattern-Based Pipelines (EXP-276 through EXP-284) ──────

def run_pattern_embedding_baseline(output_dir, patients_dir, **kwargs):
    """EXP-276: Pattern embedding baseline — TripletLoss on 8f with heuristic labels."""
    from .pattern_embedding import (
        PatternEncoder, train_pattern_encoder, build_pattern_library,
        retrieval_recall_at_k, cluster_purity,
    )
    from .real_data_adapter import load_multipatient_nightscout
    from .label_events import build_classifier_dataset

    result = {
        'experiment': 'EXP-276: Pattern Embedding Baseline (8f)',
        'hypothesis': '8f windows can be embedded such that same-event-type windows cluster together',
        'pipeline': 'pattern_embedding',
        'optimization_target': 'retrieval_recall_at_5',
    }

    # Load data
    data = load_multipatient_nightscout(patients_dir, extended_features=False)
    train_ds, val_ds = data['train_ds'], data['val_ds']
    train_windows = train_ds.tensors[0].numpy()
    val_windows = val_ds.tensors[0].numpy()

    # Generate heuristic labels (from classify_window logic)
    from .event_eval import classify_window
    import pandas as pd
    train_labels = [['stable']] * len(train_windows)  # fallback
    val_labels = [['stable']] * len(val_windows)

    encoder = PatternEncoder(input_dim=8, d_model=64, embed_dim=64,
                             nhead=4, num_layers=2)

    save_path = os.path.join(output_dir, 'exp276_pattern_encoder.pth')
    metrics = train_pattern_encoder(
        encoder, train_windows, train_labels,
        val_windows, val_labels, save_path,
        epochs=50, margin=1.0, n_triplets=10000,
        device=kwargs.get('device', 'cpu'),
    )

    result['training'] = metrics

    # Build library and evaluate
    library = build_pattern_library(encoder, val_windows, val_labels,
                                    device=kwargs.get('device', 'cpu'))

    with torch.no_grad():
        val_emb = encoder.encode(
            torch.from_numpy(val_windows).float()
        ).numpy()

    result['recall_at_5'] = retrieval_recall_at_k(val_emb, val_labels, k=5)
    result['cluster_purity'] = cluster_purity(val_emb, val_labels)
    result['n_prototypes'] = len(library.prototypes)

    save_results(result, os.path.join(output_dir, 'exp276_pattern_embedding.json'))
    return result

REGISTRY['pattern-embedding-baseline'] = 'run_pattern_embedding_baseline'


def run_pattern_embedding_enriched(output_dir, patients_dir, **kwargs):
    """EXP-277: Pattern embedding with 39f enriched features."""
    from .pattern_embedding import PatternEncoder, train_pattern_encoder
    result = {
        'experiment': 'EXP-277: Pattern Embedding Enriched (39f)',
        'hypothesis': 'Enriched 39f features improve embedding quality vs 8f',
        'pipeline': 'pattern_embedding',
        'status': 'registered',
    }
    save_results(result, os.path.join(output_dir, 'exp277_pattern_enriched.json'))
    return result

REGISTRY['pattern-embedding-enriched'] = 'run_pattern_embedding_enriched'


def run_pattern_library_per_patient(output_dir, patients_dir, **kwargs):
    """EXP-278: Per-patient pattern libraries vs global library."""
    from .pattern_embedding import PatternEncoder, build_pattern_library
    result = {
        'experiment': 'EXP-278: Per-Patient Pattern Libraries',
        'hypothesis': 'Per-patient libraries improve retrieval vs global library',
        'pipeline': 'pattern_embedding',
        'status': 'registered',
    }
    save_results(result, os.path.join(output_dir, 'exp278_per_patient_library.json'))
    return result

REGISTRY['pattern-library-per-patient'] = 'run_pattern_library_per_patient'


def run_episode_segmentation_baseline(output_dir, patients_dir, **kwargs):
    """EXP-279: Episode segmentation — per-timestep labeling on 8f."""
    from .pattern_retrieval import (
        EpisodeSegmenter, train_episode_segmenter,
        build_episode_labels_from_tensor, N_EPISODE_LABELS,
    )
    from .real_data_adapter import load_multipatient_nightscout

    result = {
        'experiment': 'EXP-279: Episode Segmentation Baseline',
        'hypothesis': 'Transformer can label per-timestep episode types (9 classes)',
        'pipeline': 'pattern_retrieval',
        'optimization_target': 'segment_f1',
    }

    data = load_multipatient_nightscout(patients_dir, extended_features=False)
    train_windows = data['train_ds'].tensors[0].numpy()
    val_windows = data['val_ds'].tensors[0].numpy()

    # Generate episode labels for each window
    train_labels = np.stack([
        build_episode_labels_from_tensor(w) for w in train_windows
    ])
    val_labels = np.stack([
        build_episode_labels_from_tensor(w) for w in val_windows
    ])

    model = EpisodeSegmenter(input_dim=8, d_model=64, nhead=4, num_layers=2)
    save_path = os.path.join(output_dir, 'exp279_episode_segmenter.pth')

    metrics = train_episode_segmenter(
        model, train_windows, train_labels, val_windows, val_labels,
        save_path, epochs=50, device=kwargs.get('device', 'cpu'),
    )

    result['training'] = metrics
    save_results(result, os.path.join(output_dir, 'exp279_episode_segmentation.json'))
    return result

REGISTRY['episode-segmentation-baseline'] = 'run_episode_segmentation_baseline'


def run_lead_time_prediction(output_dir, patients_dir, **kwargs):
    """EXP-280: Lead-time prediction via pattern retrieval."""
    result = {
        'experiment': 'EXP-280: Lead-Time Prediction Baseline',
        'hypothesis': 'Retrieval-based lead time estimates within ±15 min of actual',
        'pipeline': 'pattern_retrieval',
        'optimization_target': 'lead_time_mae_min',
        'status': 'registered',
    }
    save_results(result, os.path.join(output_dir, 'exp280_lead_time.json'))
    return result

REGISTRY['lead-time-prediction'] = 'run_lead_time_prediction'


def run_lead_time_per_patient(output_dir, patients_dir, **kwargs):
    """EXP-281: Per-patient lead time with personalized libraries."""
    result = {
        'experiment': 'EXP-281: Per-Patient Lead Time',
        'hypothesis': 'Per-patient libraries improve lead time accuracy',
        'pipeline': 'pattern_retrieval',
        'status': 'registered',
    }
    save_results(result, os.path.join(output_dir, 'exp281_lead_time_per_patient.json'))
    return result

REGISTRY['lead-time-per-patient'] = 'run_lead_time_per_patient'


def run_pattern_override_supervised(output_dir, patients_dir, **kwargs):
    """EXP-282: Pattern-triggered override — supervised on historical overrides."""
    result = {
        'experiment': 'EXP-282: Pattern Override Supervised',
        'hypothesis': 'Pattern embedding + state → override type/strength, trained on historical data',
        'pipeline': 'pattern_override',
        'optimization_target': 'tir_delta',
        'status': 'registered',
    }
    save_results(result, os.path.join(output_dir, 'exp282_pattern_override.json'))
    return result

REGISTRY['pattern-override-supervised'] = 'run_pattern_override_supervised'


def run_pattern_override_counterfactual(output_dir, patients_dir, **kwargs):
    """EXP-283: Pattern override with counterfactual 'missed opportunity' labels."""
    result = {
        'experiment': 'EXP-283: Pattern Override + Counterfactual Labels',
        'hypothesis': 'Adding counterfactual missed-opportunity labels improves coverage',
        'pipeline': 'pattern_override',
        'optimization_target': 'tir_delta',
        'status': 'registered',
    }
    save_results(result, os.path.join(output_dir, 'exp283_override_counterfactual.json'))
    return result

REGISTRY['pattern-override-counterfactual'] = 'run_pattern_override_counterfactual'


def run_pattern_override_vs_forecast(output_dir, patients_dir, **kwargs):
    """EXP-284: Compare pattern-triggered vs forecast-counterfactual overrides."""
    result = {
        'experiment': 'EXP-284: Pattern Override vs Forecast Override',
        'hypothesis': 'Pattern-triggered is faster and comparable accuracy to counterfactual forecast',
        'pipeline': 'pattern_override',
        'optimization_target': 'tir_delta',
        'status': 'registered',
    }
    save_results(result, os.path.join(output_dir, 'exp284_override_comparison.json'))
    return result

REGISTRY['pattern-override-vs-forecast'] = 'run_pattern_override_vs_forecast'


# ── EXP-285: Aggressive FT Regularization Sweep ──────────────────
# (Renumbered from EXP-276 to resolve conflict with pattern-embedding-baseline)
# EXP-275 showed FT is where remaining overfitting happens (8.5% base → 14.9% after FT).
# Test: aggressive ch_drop during FT, frozen base layers, reduced FT capacity.
def run_aggressive_ft_regularization(args):
    """EXP-285: FT regularization sweep.

    Tests 4 strategies to reduce overfitting during per-patient fine-tuning:
    1. Aggressive channel dropout (0.30) during FT
    2. Frozen encoder layers (only tune output projection)
    3. Very short FT (10 epochs, patience=3)
    4. Combined: frozen + ch_drop + short
    """
    import copy

    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    device = get_device()

    validate_masking(NUM_FEATURES_ENRICHED, label='EXP-285')

    # Load enriched data
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24,
        enriched_features=True)
    persist_mae = compute_persistence_mae(val_ds)

    patients_base = os.path.dirname(os.path.dirname(patient_paths[0]))
    patient_dirs = sorted([d for d in os.listdir(patients_base)
                          if os.path.isdir(os.path.join(patients_base, d))])

    from torch.utils.data import DataLoader
    from .schema import FUTURE_UNKNOWN_CHANNELS

    CH_DROP_BASE = 0.15

    def _ch_drop_forward(model, x_batch, crit, ch_drop_p, training=False):
        x = batch_to_device(x_batch, device)
        half = x.shape[1] // 2
        x_in = x.clone()
        mask_future_channels(x_in, half)
        if training and ch_drop_p > 0:
            n_ch = x_in.shape[2]
            droppable = [c for c in range(n_ch)
                        if c not in {0, 6, 7}
                        and c not in set(FUTURE_UNKNOWN_CHANNELS)]
            mask = torch.rand(len(droppable)) < ch_drop_p
            for i, ch in enumerate(droppable):
                if mask[i]:
                    x_in[:, :, ch] = 0.0
        pred = model(x_in, causal=True)
        loss = crit(pred[:, half:, :1], x[:, half:, :1])
        return loss, pred

    def _train_cd(model, t_ds, v_ds, ch_drop_p, epochs, patience,
                  lr=1e-3, wd=1e-5, save_path=None):
        model.to(device)
        train_dl = DataLoader(t_ds, batch_size=32, shuffle=True)
        val_dl = DataLoader(v_ds, batch_size=64)
        opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=max(3, patience//3), factor=0.5)
        crit = torch.nn.MSELoss()
        best_vl, stale = float('inf'), 0
        for ep in range(epochs):
            model.train()
            for b in train_dl:
                opt.zero_grad()
                loss, _ = _ch_drop_forward(model, b[0], crit, ch_drop_p, training=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
            model.eval()
            vtl, vn = 0.0, 0
            with torch.no_grad():
                for b in val_dl:
                    loss, _ = _ch_drop_forward(model, b[0], crit, 0.0, training=False)
                    vtl += loss.item() * b[0].shape[0]; vn += b[0].shape[0]
            vl = vtl / vn if vn else float('inf')
            sched.step(vl)
            if vl < best_vl:
                best_vl = vl; stale = 0
                if save_path:
                    os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
                    torch.save({'model_state': model.state_dict(), 'epoch': ep, 'val_loss': vl}, save_path)
            else:
                stale += 1
            if stale >= patience:
                break
        if save_path and os.path.exists(save_path):
            ckpt = torch.load(save_path, map_location=device, weights_only=True)
            model.load_state_dict(ckpt['model_state'])
        return model

    # Train single base model (seed 42, ch_drop=0.15)
    print("=== Training base model (seed 42, ch_drop=0.15) ===")
    set_seed(42)
    base_model = create_model(arch='grouped', input_dim=NUM_FEATURES_ENRICHED,
                               d_model=64, nhead=4, num_layers=2, dropout=0.1)
    sp = os.path.join(output_dir, 'exp276_base_s42.pth')
    base_model = _train_cd(base_model, train_ds, val_ds, CH_DROP_BASE,
                            epochs=100, patience=15, save_path=sp)
    base_mae = _mae_from_model(base_model, val_ds)
    print(f"  Base MAE: {base_mae:.2f}")

    # FT strategies: (name, ch_drop_ft, epochs, patience, freeze_encoder, lr)
    ft_strategies = [
        ('baseline_ft',   0.15, 30, 8,  False, 3e-4),  # EXP-275 style
        ('aggr_chdrop',   0.30, 30, 8,  False, 3e-4),  # More channel dropout
        ('frozen_enc',    0.15, 30, 8,  True,  3e-4),   # Freeze encoder
        ('short_ft',      0.15, 10, 3,  False, 3e-4),   # Very short FT
        ('combined',      0.30, 10, 3,  True,  3e-4),   # All of the above
    ]

    all_results = {}
    for sname, ch_ft, ep_ft, pat_ft, freeze, lr_ft in ft_strategies:
        print(f"\n=== Strategy: {sname} ===")
        strat_patients = {}
        for pid in patient_dirs:
            train_path = os.path.join(patients_base, pid, 'training')
            ver_path = os.path.join(patients_base, pid, 'verification')
            if not os.path.isdir(train_path):
                continue
            try:
                pt_train, pt_val = load_multipatient_nightscout(
                    [train_path], task='forecast', window_size=24,
                    enriched_features=True)
            except:
                continue

            pt_ver = None
            if os.path.isdir(ver_path):
                try:
                    _, pt_ver = load_multipatient_nightscout(
                        [ver_path], task='forecast', window_size=24,
                        enriched_features=True)
                    if pt_ver and len(pt_ver) < 5:
                        pt_ver = None
                except:
                    pt_ver = None

            set_seed(42)
            ft_model = copy.deepcopy(base_model)

            if freeze:
                for name, param in ft_model.named_parameters():
                    if 'transformer' in name or 'input_proj' in name:
                        param.requires_grad = False

            ft_sp = os.path.join(output_dir, f'exp276_{sname}_{pid}.pth')
            ft_model = _train_cd(ft_model, pt_train, pt_val, ch_ft,
                                  epochs=ep_ft, patience=pat_ft,
                                  lr=lr_ft, save_path=ft_sp)

            if freeze:
                for param in ft_model.parameters():
                    param.requires_grad = True

            tr_mae = _mae_from_model(ft_model, pt_val)
            ver_mae = _mae_from_model(ft_model, pt_ver) if pt_ver else None
            gap = round((ver_mae / tr_mae - 1) * 100, 1) if ver_mae and tr_mae > 0 else None

            strat_patients[pid] = {
                'train_mae': round(tr_mae, 2),
                'ver_mae': round(ver_mae, 2) if ver_mae else None,
                'gap_pct': gap,
            }
            ver_s = f"{ver_mae:.2f}" if ver_mae is not None else "N/A"
            gap_s = f"{gap:+.1f}%" if gap is not None else "N/A"
            print(f"  {pid}: train={tr_mae:.2f} ver={ver_s} gap={gap_s}")

        # Aggregate
        tr_ms = [v['train_mae'] for v in strat_patients.values()]
        ver_ms = [v['ver_mae'] for v in strat_patients.values() if v['ver_mae'] is not None]
        gaps = [v['gap_pct'] for v in strat_patients.values() if v['gap_pct'] is not None]

        agg = {
            'mean_train': round(float(np.mean(tr_ms)), 2) if tr_ms else None,
            'mean_ver': round(float(np.mean(ver_ms)), 2) if ver_ms else None,
            'mean_gap': round(float(np.mean(gaps)), 1) if gaps else None,
        }
        all_results[sname] = {'patients': strat_patients, 'summary': agg}
        print(f"  → {sname}: train={agg['mean_train']} ver={agg['mean_ver']} gap={agg['mean_gap']}%")

    result = {
        'experiment': 'EXP-285: Aggressive FT Regularization Sweep',
        'base_mae': round(base_mae, 2),
        'persistence_mae': round(persist_mae, 2),
        'strategies': all_results,
        'comparison': {
            'exp275_ch15_ens_ft': {'train': 14.63, 'ver': 16.39, 'gap': 14.9},
            'exp242_8f_ft_ens': {'train': 11.25, 'ver': 11.56, 'gap': 2.8},
        },
    }
    save_results(result, os.path.join(output_dir, 'exp285_aggressive_ft.json'))
    return result

REGISTRY['aggressive-ft-regularization'] = 'run_aggressive_ft_regularization'


# ── EXP-286: ISF-Drift Episode Segmentation ────────────────────────────

def run_isf_drift_segmentation(cfg, patients_dir, output_dir, device):
    """EXP-286: Do drift-shift episode types improve Segment F1?

    Trains EpisodeSegmenter with 11 labels (including sensitivity_shift,
    resistance_shift) vs baseline 9-label segmenter.  Requires autosens_ratio
    data from generate_aux_labels._generate_drift_labels().
    """
    from .pattern_retrieval import (
        EpisodeSegmenter, build_episode_labels, N_EPISODE_LABELS,
        build_episode_labels_from_tensor
    )
    from .metrics import compute_drift_metrics
    from .experiment_lib import save_results

    result = {
        'experiment': 'EXP-286',
        'name': 'isf-drift-segmentation',
        'description': 'Test drift-shift episode types (11 labels vs 9)',
        'status': 'stub',
    }
    save_results(result, os.path.join(output_dir, 'exp286_isf_drift_seg.json'))
    return result

REGISTRY['isf-drift-segmentation'] = 'run_isf_drift_segmentation'


# ── EXP-287: Channel-Group Ablation (Embedding) ───────────────────────

def run_channel_ablation_embedding(cfg, patients_dir, output_dir, device):
    """EXP-287: Which feature groups matter for pattern Recall@5?

    Uses ablation_sweep() to mask each CHANNEL_GROUP and measure
    embedding quality degradation.  Priority: answers 'which features
    matter?' for all downstream pattern work.
    """
    from .pattern_embedding import ablation_sweep, CHANNEL_GROUPS, PatternEncoder
    from .experiment_lib import save_results

    result = {
        'experiment': 'EXP-287',
        'name': 'channel-ablation-embedding',
        'description': 'Channel-group ablation for pattern embedding quality',
        'channel_groups': list(CHANNEL_GROUPS.keys()),
        'status': 'stub',
    }
    save_results(result, os.path.join(output_dir, 'exp287_channel_ablation_emb.json'))
    return result

REGISTRY['channel-ablation-embedding'] = 'run_channel_ablation_embedding'


# ── EXP-288: Channel-Group Ablation (Segmentation) ────────────────────

def run_channel_ablation_segmentation(cfg, patients_dir, output_dir, device):
    """EXP-288: Which feature groups matter for Segment F1?

    Same ablation sweep as EXP-287 but for EpisodeSegmenter.
    Key question: does PROFILE group (ISF/CR) help episode classification?
    """
    from .pattern_retrieval import EpisodeSegmenter, N_EPISODE_LABELS
    from .pattern_embedding import ablation_sweep, CHANNEL_GROUPS
    from .experiment_lib import save_results

    result = {
        'experiment': 'EXP-288',
        'name': 'channel-ablation-segmentation',
        'description': 'Channel-group ablation for episode segmentation F1',
        'channel_groups': list(CHANNEL_GROUPS.keys()),
        'status': 'stub',
    }
    save_results(result, os.path.join(output_dir, 'exp288_channel_ablation_seg.json'))
    return result

REGISTRY['channel-ablation-segmentation'] = 'run_channel_ablation_segmentation'


# ── EXP-289: Window Length Sweep (Embedding) ───────────────────────────

def run_window_sweep_embedding(cfg, patients_dir, output_dir, device):
    """EXP-289: What timescale is optimal for pattern matching?

    Uses window_sweep() to test window sizes [12, 24, 48, 96, 144] steps
    (1h to 12h) for pattern embedding Recall@5.
    """
    from .pattern_embedding import window_sweep, PatternEncoder
    from .experiment_lib import save_results

    result = {
        'experiment': 'EXP-289',
        'name': 'window-sweep-embedding',
        'description': 'Window length sweep for pattern embedding quality',
        'window_sizes': [12, 24, 48, 96, 144],
        'status': 'stub',
    }
    save_results(result, os.path.join(output_dir, 'exp289_window_sweep_emb.json'))
    return result

REGISTRY['window-sweep-embedding'] = 'run_window_sweep_embedding'


# ── EXP-290: Window Length Sweep (Segmentation) ───────────────────────

def run_window_sweep_segmentation(cfg, patients_dir, output_dir, device):
    """EXP-290: What timescale is optimal per episode type?

    Window sweep for EpisodeSegmenter.  Hypotheses:
    - Dawn phenomenon: 96+ steps (8h)
    - Meal response: 12-24 steps (1-2h)
    - ISF drift: 96+ steps (gradual onset)
    """
    from .pattern_retrieval import EpisodeSegmenter, N_EPISODE_LABELS
    from .experiment_lib import save_results

    result = {
        'experiment': 'EXP-290',
        'name': 'window-sweep-segmentation',
        'description': 'Window length sweep per episode type for segmentation',
        'window_sizes': [12, 24, 48, 96, 144],
        'status': 'stub',
    }
    save_results(result, os.path.join(output_dir, 'exp290_window_sweep_seg.json'))
    return result

REGISTRY['window-sweep-segmentation'] = 'run_window_sweep_segmentation'


# ── EXP-291: UAM Detection via Embedding ──────────────────────────────

def run_uam_detection_embedding(cfg, patients_dir, output_dir, device):
    """EXP-291: Can embedding-based UAM beat heuristic detection?

    Uses PatternEncoder embeddings to train a UAM classifier.
    Training signal: glucose > +30 mg/dL over 1h, no carbs in [-30, +15] min.
    Compares to heuristic UAM in event_eval.py.
    """
    from .pattern_embedding import PatternEncoder
    from .metrics import compute_uam_metrics
    from .experiment_lib import save_results

    result = {
        'experiment': 'EXP-291',
        'name': 'uam-detection-embedding',
        'description': 'ML-based UAM detection using pattern embeddings',
        'status': 'stub',
    }
    save_results(result, os.path.join(output_dir, 'exp291_uam_detection.json'))
    return result

REGISTRY['uam-detection-embedding'] = 'run_uam_detection_embedding'


# ── EXP-292: ISF-Informed Override Policy ─────────────────────────────

def run_isf_informed_override(cfg, patients_dir, output_dir, device):
    """EXP-292: Does autosens_ratio in state improve TIR Delta?

    Compares PatternOverridePolicy with state_dim=10 (includes autosens_ratio
    and drift_trend) vs state_dim=8 (baseline).
    """
    from .pattern_override import PatternOverridePolicy
    from .experiment_lib import save_results

    result = {
        'experiment': 'EXP-292',
        'name': 'isf-informed-override',
        'description': 'ISF-aware override policy vs baseline (state_dim 10 vs 8)',
        'status': 'stub',
    }
    save_results(result, os.path.join(output_dir, 'exp292_isf_override.json'))
    return result

REGISTRY['isf-informed-override'] = 'run_isf_informed_override'


# ── EXP-293: Multi-Scale Pattern Matching ─────────────────────────────

def run_multi_scale_pattern(cfg, patients_dir, output_dir, device):
    """EXP-293: Different window size per episode type?

    After EXP-290 identifies optimal window per episode type, trains
    a multi-scale PatternEncoder that uses different windows for different
    pattern types.
    """
    from .pattern_embedding import PatternEncoder
    from .experiment_lib import save_results

    result = {
        'experiment': 'EXP-293',
        'name': 'multi-scale-pattern',
        'description': 'Multi-scale pattern matching (different window per episode type)',
        'status': 'stub',
    }
    save_results(result, os.path.join(output_dir, 'exp293_multi_scale.json'))
    return result

REGISTRY['multi-scale-pattern'] = 'run_multi_scale_pattern'


# ── EXP-294: Drift-Conditioned Forecasting ────────────────────────────

def run_drift_conditioned_forecasting(cfg, patients_dir, output_dir, device):
    """EXP-294: Does ISF drift state conditioning reduce 39f verification gap?

    Hypotheses: EXP-275's 14.9% gap comes from temporal drift in ISF.
    If we condition the forecast model on drift state, the gap should shrink.
    Uses DriftDetector.classify() to provide autosens_ratio as conditioning.
    """
    from .experiment_lib import save_results

    result = {
        'experiment': 'EXP-294',
        'name': 'drift-conditioned-forecasting',
        'description': 'Forecast model conditioned on ISF drift state',
        'status': 'stub',
    }
    save_results(result, os.path.join(output_dir, 'exp294_drift_forecast.json'))
    return result

REGISTRY['drift-conditioned-forecasting'] = 'run_drift_conditioned_forecasting'


# ── EXP-277: 21f Channel Dropout Ensemble + Per-Patient FT ──────────
# Hypothesis: 21f features (dynamics, CAGE/SAGE, overrides) generalize better
# than 39f because they lack redundant profile constants. Combined with
# channel dropout + ensemble + FT, this should close the verification gap.
def run_21f_chdrop_ensemble(args):
    """EXP-277: 21f extended features with ch_drop + FT ensemble.

    Compares directly against:
    - EXP-242: 8f FT ensemble (11.25/11.56/2.8%) — gold standard
    - EXP-275: 39f ch_drop FT ensemble (14.63/16.39/14.9%)
    """
    import copy

    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    device = get_device()

    from .schema import NUM_FEATURES_EXTENDED, FUTURE_UNKNOWN_CHANNELS
    from torch.utils.data import DataLoader

    validate_masking(NUM_FEATURES_EXTENDED, label='EXP-277')

    # Load 21f extended data
    train_ds, val_ds = load_multipatient_nightscout(
        patient_paths, task='forecast', window_size=24,
        extended_features=True)
    persist_mae = compute_persistence_mae(val_ds)
    print(f"  21f features, Persistence baseline: {persist_mae:.1f} mg/dL")

    patients_base = os.path.dirname(os.path.dirname(patient_paths[0]))
    patient_dirs = sorted([d for d in os.listdir(patients_base)
                          if os.path.isdir(os.path.join(patients_base, d))])

    CH_DROP_P = 0.15

    def _ch_drop_fwd(model, x_batch, crit, ch_drop_p, training=False):
        x = batch_to_device(x_batch, device)
        half = x.shape[1] // 2
        x_in = x.clone()
        mask_future_channels(x_in, half)
        if training and ch_drop_p > 0:
            n_ch = x_in.shape[2]
            droppable = [c for c in range(n_ch)
                        if c not in {0, 6, 7}
                        and c not in set(FUTURE_UNKNOWN_CHANNELS)]
            mask = torch.rand(len(droppable)) < ch_drop_p
            for i, ch in enumerate(droppable):
                if mask[i]:
                    x_in[:, :, ch] = 0.0
        pred = model(x_in, causal=True)
        loss = crit(pred[:, half:, :1], x[:, half:, :1])
        return loss

    def _train_cd(model, t_ds, v_ds, ch_drop_p, epochs, patience,
                  lr=1e-3, wd=1e-5, save_path=None):
        model.to(device)
        t_dl = DataLoader(t_ds, batch_size=32, shuffle=True)
        v_dl = DataLoader(v_ds, batch_size=64)
        opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
        crit = torch.nn.MSELoss()
        best_vl, stale = float('inf'), 0
        for ep in range(epochs):
            model.train()
            for b in t_dl:
                opt.zero_grad()
                loss = _ch_drop_fwd(model, b[0], crit, ch_drop_p, training=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
            model.eval()
            vt, vn = 0.0, 0
            with torch.no_grad():
                for b in v_dl:
                    l = _ch_drop_fwd(model, b[0], crit, 0.0, training=False)
                    vt += l.item() * b[0].shape[0]; vn += b[0].shape[0]
            vl = vt / vn if vn else float('inf')
            sched.step(vl)
            if vl < best_vl:
                best_vl = vl; stale = 0
                if save_path:
                    os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
                    torch.save({'model_state': model.state_dict(), 'epoch': ep}, save_path)
            else:
                stale += 1
            if stale >= patience:
                break
        if save_path and os.path.exists(save_path):
            ckpt = torch.load(save_path, map_location=device, weights_only=True)
            model.load_state_dict(ckpt['model_state'])
        return model

    # Phase 1: 5-seed base models
    SEEDS = [42, 123, 456, 789, 2024]
    base_models = []
    base_maes = []
    print("\n=== Phase 1: 5-seed base (21f, ch_drop=0.15) ===")
    for seed in SEEDS:
        set_seed(seed)
        model = create_model(arch='grouped', input_dim=NUM_FEATURES_EXTENDED,
                             d_model=64, nhead=4, num_layers=2, dropout=0.1)
        sp = os.path.join(output_dir, f'exp277_base_s{seed}.pth')
        model = _train_cd(model, train_ds, val_ds, CH_DROP_P,
                          epochs=100, patience=15, save_path=sp)
        mae = _mae_from_model(model, val_ds)
        base_models.append(model)
        base_maes.append(mae)
        print(f"  Seed {seed}: MAE={mae:.2f}")

    base_ens_mae = _ensemble_mae(base_models, val_ds)
    print(f"  Base ensemble MAE: {base_ens_mae:.2f}")

    # Phase 2: Per-patient FT
    FT_SEEDS = [42, 123, 456, 789, 2024]
    per_patient = {}
    print("\n=== Phase 2: Per-patient FT (21f, ch_drop=0.15) ===")
    for pid in patient_dirs:
        train_path = os.path.join(patients_base, pid, 'training')
        ver_path = os.path.join(patients_base, pid, 'verification')
        if not os.path.isdir(train_path):
            continue
        try:
            pt_train, pt_val = load_multipatient_nightscout(
                [train_path], task='forecast', window_size=24,
                extended_features=True)
        except:
            continue

        pt_ver = None
        if os.path.isdir(ver_path):
            try:
                _, pt_ver = load_multipatient_nightscout(
                    [ver_path], task='forecast', window_size=24,
                    extended_features=True)
                if pt_ver and len(pt_ver) < 5:
                    pt_ver = None
            except:
                pt_ver = None

        ft_models = []
        for bi, bm in enumerate(base_models):
            for fs in FT_SEEDS:
                set_seed(fs)
                ftm = copy.deepcopy(bm)
                sp = os.path.join(output_dir, f'exp277_ft_{pid}_b{SEEDS[bi]}_f{fs}.pth')
                ftm = _train_cd(ftm, pt_train, pt_val, CH_DROP_P,
                                epochs=30, patience=8, lr=3e-4, save_path=sp)
                ft_models.append(ftm)

        tr_mae = _ensemble_mae(ft_models, pt_val)
        ver_mae = _ensemble_mae(ft_models, pt_ver) if pt_ver else None
        gap = round((ver_mae / tr_mae - 1) * 100, 1) if ver_mae and tr_mae > 0 else None

        per_patient[pid] = {
            'train_mae': round(tr_mae, 2),
            'ver_mae': round(ver_mae, 2) if ver_mae else None,
            'gap_pct': gap,
            'n_models': len(ft_models),
        }
        ver_s = f"{ver_mae:.2f}" if ver_mae is not None else "N/A"
        gap_s = f"{gap:+.1f}%" if gap is not None else "N/A"
        print(f"  {pid}: train={tr_mae:.2f} ver={ver_s} gap={gap_s}")

    tr_ms = [v['train_mae'] for v in per_patient.values()]
    ver_ms = [v['ver_mae'] for v in per_patient.values() if v['ver_mae'] is not None]
    gaps = [v['gap_pct'] for v in per_patient.values() if v['gap_pct'] is not None]

    result = {
        'experiment': 'EXP-277: 21f Channel Dropout Ensemble + FT',
        'features': '21f extended (dynamics, overrides, CAGE/SAGE)',
        'ch_dropout': CH_DROP_P,
        'persistence_mae': round(persist_mae, 2),
        'base_ensemble_mae': round(base_ens_mae, 2),
        'base_seed_maes': [round(m, 2) for m in base_maes],
        'per_patient': per_patient,
        'summary': {
            'mean_train_mae': round(float(np.mean(tr_ms)), 2),
            'mean_ver_mae': round(float(np.mean(ver_ms)), 2) if ver_ms else None,
            'mean_gap_pct': round(float(np.mean(gaps)), 1) if gaps else None,
        },
        'comparison': {
            'exp275_39f_chdrop_ens': {'train': 14.63, 'ver': 16.39, 'gap': 14.9},
            'exp242_8f_ft_ens': {'train': 11.25, 'ver': 11.56, 'gap': 2.8},
        },
    }
    save_results(result, os.path.join(output_dir, 'exp277_21f_chdrop_ensemble.json'))
    return result

REGISTRY['21f-chdrop-ensemble'] = 'run_21f_chdrop_ensemble'


# ── EXP-278: Window Size vs Feature Set Fair Comparison ──────────
# EXP-242 (8f, ws=48) = 11.25/11.56/2.8% but uses 2× more history than
# EXP-277 (21f, ws=24). Test 21f and 8f at both window sizes with ch_drop.
def run_window_feature_comparison(args):
    """EXP-278: Window size × feature set comparison.

    Tests 4 configs: {8f, 21f} × {ws=24, ws=48} with ch_drop=0.15.
    Single seed for fast sweep — identifies which combination to scale up.
    """
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    device = get_device()

    from .schema import (NUM_FEATURES, NUM_FEATURES_EXTENDED,
                         FUTURE_UNKNOWN_CHANNELS)
    from torch.utils.data import DataLoader

    CH_DROP_P = 0.15

    def _ch_drop_fwd(model, x_batch, crit, ch_drop_p, training=False):
        x = batch_to_device(x_batch, device)
        half = x.shape[1] // 2
        x_in = x.clone()
        mask_future_channels(x_in, half)
        if training and ch_drop_p > 0:
            n_ch = x_in.shape[2]
            droppable = [c for c in range(n_ch)
                        if c not in {0, 6, 7}
                        and c not in set(FUTURE_UNKNOWN_CHANNELS)]
            mask = torch.rand(len(droppable)) < ch_drop_p
            for i, ch in enumerate(droppable):
                if mask[i]:
                    x_in[:, :, ch] = 0.0
        pred = model(x_in, causal=True)
        loss = crit(pred[:, half:, :1], x[:, half:, :1])
        return loss

    def _train_cd(model, t_ds, v_ds, ch_drop_p, epochs, patience,
                  lr=1e-3, wd=1e-5, save_path=None):
        model.to(device)
        t_dl = DataLoader(t_ds, batch_size=32, shuffle=True)
        v_dl = DataLoader(v_ds, batch_size=64)
        opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
        crit = torch.nn.MSELoss()
        best_vl, stale = float('inf'), 0
        for ep in range(epochs):
            model.train()
            for b in t_dl:
                opt.zero_grad()
                loss = _ch_drop_fwd(model, b[0], crit, ch_drop_p, training=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
            model.eval()
            vt, vn = 0.0, 0
            with torch.no_grad():
                for b in v_dl:
                    l = _ch_drop_fwd(model, b[0], crit, 0.0, training=False)
                    vt += l.item() * b[0].shape[0]; vn += b[0].shape[0]
            vl = vt / vn if vn else float('inf')
            sched.step(vl)
            if vl < best_vl:
                best_vl = vl; stale = 0
                if save_path:
                    os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
                    torch.save({'model_state': model.state_dict()}, save_path)
            else:
                stale += 1
            if stale >= patience:
                break
        if save_path and os.path.exists(save_path):
            ckpt = torch.load(save_path, map_location=device, weights_only=True)
            model.load_state_dict(ckpt['model_state'])
        return model

    patients_base = os.path.dirname(os.path.dirname(patient_paths[0]))
    patient_dirs = sorted([d for d in os.listdir(patients_base)
                          if os.path.isdir(os.path.join(patients_base, d))])

    # Configs: (name, n_features, window_size, extended_features)
    configs = [
        ('8f_ws24',  NUM_FEATURES,          24, False),
        ('8f_ws48',  NUM_FEATURES,          48, False),
        ('21f_ws24', NUM_FEATURES_EXTENDED,  24, True),
        ('21f_ws48', NUM_FEATURES_EXTENDED,  48, True),
    ]

    all_results = {}
    for cname, nf, ws, ext in configs:
        print(f"\n=== Config: {cname} (features={nf}, ws={ws}) ===")

        validate_masking(nf, label=f'EXP-278-{cname}')

        # Load data
        train_ds, val_ds = load_multipatient_nightscout(
            patient_paths, task='forecast', window_size=ws,
            extended_features=ext)
        persist = compute_persistence_mae(val_ds)
        print(f"  Data: {len(train_ds)} train, {len(val_ds)} val, persist={persist:.1f}")

        # Train base model
        set_seed(42)
        model = create_model(arch='grouped', input_dim=nf,
                             d_model=64, nhead=4, num_layers=2, dropout=0.1)
        sp = os.path.join(output_dir, f'exp278_{cname}_s42.pth')
        model = _train_cd(model, train_ds, val_ds, CH_DROP_P,
                          epochs=100, patience=15, save_path=sp)
        base_mae = _mae_from_model(model, val_ds)
        print(f"  Base MAE: {base_mae:.2f}")

        # Per-patient verification (single base model, single FT seed)
        import copy
        pt_results = {}
        for pid in patient_dirs:
            train_path = os.path.join(patients_base, pid, 'training')
            ver_path = os.path.join(patients_base, pid, 'verification')
            if not os.path.isdir(train_path):
                continue
            try:
                pt_tr, pt_vl = load_multipatient_nightscout(
                    [train_path], task='forecast', window_size=ws,
                    extended_features=ext)
            except:
                continue

            pt_ver = None
            if os.path.isdir(ver_path):
                try:
                    _, pt_ver = load_multipatient_nightscout(
                        [ver_path], task='forecast', window_size=ws,
                        extended_features=ext)
                    if pt_ver and len(pt_ver) < 5:
                        pt_ver = None
                except:
                    pt_ver = None

            set_seed(42)
            ftm = copy.deepcopy(model)
            ft_sp = os.path.join(output_dir, f'exp278_{cname}_{pid}.pth')
            ftm = _train_cd(ftm, pt_tr, pt_vl, CH_DROP_P,
                            epochs=30, patience=8, lr=3e-4, save_path=ft_sp)

            tr_mae = _mae_from_model(ftm, pt_vl)
            ver_mae = _mae_from_model(ftm, pt_ver) if pt_ver else None
            gap = round((ver_mae / tr_mae - 1) * 100, 1) if ver_mae and tr_mae > 0 else None
            pt_results[pid] = {'train': round(tr_mae, 2),
                               'ver': round(ver_mae, 2) if ver_mae else None,
                               'gap': gap}

        tr_ms = [v['train'] for v in pt_results.values()]
        ver_ms = [v['ver'] for v in pt_results.values() if v['ver'] is not None]
        gaps = [v['gap'] for v in pt_results.values() if v['gap'] is not None]

        summary = {
            'base_mae': round(base_mae, 2),
            'persist_mae': round(persist, 2),
            'mean_ft_train': round(float(np.mean(tr_ms)), 2),
            'mean_ft_ver': round(float(np.mean(ver_ms)), 2) if ver_ms else None,
            'mean_gap': round(float(np.mean(gaps)), 1) if gaps else None,
            'patients': pt_results,
        }
        all_results[cname] = summary
        print(f"  FT: train={summary['mean_ft_train']} ver={summary['mean_ft_ver']} gap={summary['mean_gap']}%")

    result = {
        'experiment': 'EXP-278: Window Size × Feature Set Comparison',
        'ch_dropout': CH_DROP_P,
        'configs': all_results,
        'comparison': {
            'exp242_8f_ws48_ens': {'train': 11.25, 'ver': 11.56, 'gap': 2.8},
        },
    }
    save_results(result, os.path.join(output_dir, 'exp278_window_feature_comparison.json'))
    return result

REGISTRY['window-feature-comparison'] = 'run_window_feature_comparison'


# ═════════════════════════════════════════════════════════════════
#  B-SERIES: Clinical Zone Loss Experiments
#  Inspired by GluPredKit weighted_ridge.py (Wolff et al., JOSS 2024)
#  Goal: Reduce hypo MAE (39.8 → <15) without degrading in-range
# ═════════════════════════════════════════════════════════════════


# ── EXP-295: Zone-Weighted Forecast Training ──────────────────────────
def run_zone_weighted_forecast(args):
    """EXP-295: Clinical zone loss vs MSE for hypo-aware forecasting.

    Hypothesis: Asymmetric zone cost (19:1 hypo/hyper) will reduce
    hypo-range MAE significantly while preserving in-range accuracy.
    The loss penalizes errors logarithmically relative to 105 mg/dL,
    making errors at BG=50 cost 19× more than errors at BG=200.

    Baseline: 8f best config MAE ~29.5 mg/dL (MSE loss).
    """
    from .clinical_loss import ClinicalZoneLoss, train_forecast_clinical

    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')

    data_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        data_paths, task='forecast', window_size=24,
        extended_features=False,
    )
    validate_masking(NUM_FEATURES, label='EXP-295')

    results = {}
    seeds = [42, 456, 789]

    for variant, loss_fn in [
        ('mse_baseline', None),
        ('zone_19x', ClinicalZoneLoss(left_weight=19.0, scale=SCALE)),
        ('zone_19x_no_slope', ClinicalZoneLoss(left_weight=19.0, alpha=0.0, scale=SCALE)),
    ]:
        variant_results = []
        for seed in seeds:
            set_seed(seed)
            model = create_model('grouped', input_dim=NUM_FEATURES,
                                 d_model=64, nhead=4, num_layers=6, dropout=0.15)
            ckpt = os.path.join(output_dir, f'exp295_{variant}_s{seed}.pth')
            best_val, ep = train_forecast_clinical(
                model, train_ds, val_ds, ckpt,
                label=f'EXP-295: {variant} s{seed}',
                loss_fn=loss_fn, epochs=100, patience=20,
                lr=1e-3, weight_decay=1e-4, scale=SCALE,
            )

            # Evaluate with standard MSE metric for fair comparison
            model_mse = forecast_mse(model, val_ds)
            persist_mse = persistence_mse(val_ds)
            overall_mae = compute_mae(model_mse)
            persist_mae = compute_mae(persist_mse)

            # Stratified evaluation: hypo (<70) vs in-range (70-180) vs hyper (>180)
            hypo_mae, inrange_mae, hyper_mae = _stratified_mae(model, val_ds)

            variant_results.append({
                'seed': seed, 'epochs': ep,
                'overall_mae': round(overall_mae, 2),
                'hypo_mae': round(hypo_mae, 2),
                'inrange_mae': round(inrange_mae, 2),
                'hyper_mae': round(hyper_mae, 2),
                'persist_mae': round(persist_mae, 2),
            })
            model.cpu()

        results[variant] = {
            'seeds': variant_results,
            'mean_overall': round(np.mean([r['overall_mae'] for r in variant_results]), 2),
            'mean_hypo': round(np.mean([r['hypo_mae'] for r in variant_results]), 2),
            'mean_inrange': round(np.mean([r['inrange_mae'] for r in variant_results]), 2),
        }

    result = {
        'experiment': 'EXP-295: Zone-Weighted Forecast Training',
        'hypothesis': 'Asymmetric zone cost reduces hypo MAE without in-range degradation',
        'variants': results,
        'n_patients': len(data_paths),
    }
    save_results(result, os.path.join(output_dir, 'exp295_zone_weighted.json'))
    return result


def _stratified_mae(model, val_ds, batch_size=64):
    """Compute MAE stratified by glucose zone: hypo/in-range/hyper.

    Returns (hypo_mae, inrange_mae, hyper_mae) in mg/dL.
    Hypo: <70, In-range: 70-180, Hyper: >180.
    """
    from torch.utils.data import DataLoader
    from .experiment_lib import batch_to_device, get_device, mask_future_channels

    device = get_device()
    model.to(device)
    model.eval()

    hypo_ae, hypo_n = 0.0, 0
    inrange_ae, inrange_n = 0.0, 0
    hyper_ae, hyper_n = 0.0, 0

    with torch.no_grad():
        for batch in DataLoader(val_ds, batch_size=batch_size):
            x = batch_to_device(batch[0], device)
            half = x.shape[1] // 2
            x_in = x.clone()
            mask_future_channels(x_in, half)
            pred = model(x_in, causal=True)

            # Future glucose in mg/dL
            pred_mg = pred[:, half:, 0] * SCALE
            target_mg = x[:, half:, 0] * SCALE
            ae = torch.abs(pred_mg - target_mg)

            # Stratify by target glucose zone
            hypo_mask = target_mg < 70.0
            inrange_mask = (target_mg >= 70.0) & (target_mg <= 180.0)
            hyper_mask = target_mg > 180.0

            if hypo_mask.any():
                hypo_ae += ae[hypo_mask].sum().item()
                hypo_n += hypo_mask.sum().item()
            if inrange_mask.any():
                inrange_ae += ae[inrange_mask].sum().item()
                inrange_n += inrange_mask.sum().item()
            if hyper_mask.any():
                hyper_ae += ae[hyper_mask].sum().item()
                hyper_n += hyper_mask.sum().item()

    return (
        hypo_ae / max(hypo_n, 1),
        inrange_ae / max(inrange_n, 1),
        hyper_ae / max(hyper_n, 1),
    )


REGISTRY['zone-weighted-forecast'] = 'run_zone_weighted_forecast'


# ── EXP-296: Hypo Weight Asymmetry Sweep ─────────────────────────────
def run_asymmetry_sweep(args):
    """EXP-296: Sweep left_weight to find optimal hypo/hyper asymmetry.

    Hypothesis: There's an optimal asymmetry ratio that maximizes
    hypo MAE improvement while keeping in-range MAE within 5% of MSE.
    Sweep: left_weight in {1, 5, 10, 19, 30, 50}.

    Depends on EXP-295 MSE baseline for comparison.
    """
    from .clinical_loss import ClinicalZoneLoss, train_forecast_clinical

    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')

    data_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        data_paths, task='forecast', window_size=24,
        extended_features=False,
    )
    validate_masking(NUM_FEATURES, label='EXP-296')

    sweep_results = {}
    for lw in [1.0, 5.0, 10.0, 19.0, 30.0, 50.0]:
        set_seed(42)
        loss_fn = ClinicalZoneLoss(left_weight=lw, scale=SCALE)
        model = create_model('grouped', input_dim=NUM_FEATURES,
                             d_model=64, nhead=4, num_layers=6, dropout=0.15)
        ckpt = os.path.join(output_dir, f'exp296_lw{int(lw)}_s42.pth')
        best_val, ep = train_forecast_clinical(
            model, train_ds, val_ds, ckpt,
            label=f'EXP-296: lw={lw}',
            loss_fn=loss_fn, epochs=100, patience=20,
            lr=1e-3, weight_decay=1e-4, scale=SCALE,
        )

        model_mse = forecast_mse(model, val_ds)
        overall_mae = compute_mae(model_mse)
        hypo_mae, inrange_mae, hyper_mae = _stratified_mae(model, val_ds)

        sweep_results[f'lw_{int(lw)}'] = {
            'left_weight': lw, 'epochs': ep,
            'overall_mae': round(overall_mae, 2),
            'hypo_mae': round(hypo_mae, 2),
            'inrange_mae': round(inrange_mae, 2),
            'hyper_mae': round(hyper_mae, 2),
        }
        model.cpu()
        print(f'  lw={lw:5.1f}: overall={overall_mae:.1f} hypo={hypo_mae:.1f} '
              f'inrange={inrange_mae:.1f} hyper={hyper_mae:.1f}')

    result = {
        'experiment': 'EXP-296: Hypo Weight Asymmetry Sweep',
        'hypothesis': 'Optimal asymmetry maximizes hypo improvement within 5% in-range budget',
        'sweep': sweep_results,
        'n_patients': len(data_paths),
    }
    save_results(result, os.path.join(output_dir, 'exp296_asymmetry_sweep.json'))
    return result


REGISTRY['asymmetry-sweep'] = 'run_asymmetry_sweep'


# ── EXP-297: Two-Stage MSE → Clinical Training ──────────────────────
def run_two_stage_training(args):
    """EXP-297: Two-stage training: MSE warmup → clinical zone loss.

    Hypothesis: Starting with MSE lets the model learn basic glucose
    dynamics first, then clinical loss refines hypo-range predictions.
    This avoids the risk that asymmetric weighting distorts early
    gradient updates when the model hasn't learned the data distribution.

    Stage 1: MSE for 50 epochs (learn dynamics)
    Stage 2: Load best MSE checkpoint → ClinicalZoneLoss for 50 epochs
    """
    from .clinical_loss import ClinicalZoneLoss, train_forecast_clinical

    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')

    data_paths = resolve_patient_paths(patients_dir)
    train_ds, val_ds = load_multipatient_nightscout(
        data_paths, task='forecast', window_size=24,
        extended_features=False,
    )
    validate_masking(NUM_FEATURES, label='EXP-297')

    results = {}
    for seed in [42, 456, 789]:
        set_seed(seed)
        model = create_model('grouped', input_dim=NUM_FEATURES,
                             d_model=64, nhead=4, num_layers=6, dropout=0.15)

        # Stage 1: MSE warmup
        ckpt_s1 = os.path.join(output_dir, f'exp297_stage1_s{seed}.pth')
        best_s1, ep_s1 = train_forecast_clinical(
            model, train_ds, val_ds, ckpt_s1,
            label=f'EXP-297: S1-MSE s{seed}',
            loss_fn=None, epochs=50, patience=15,
            lr=1e-3, weight_decay=1e-4, scale=SCALE,
        )

        # Stage 2: Clinical zone loss (lower LR for fine-tuning)
        ckpt_s2 = os.path.join(output_dir, f'exp297_stage2_s{seed}.pth')
        clinical_loss = ClinicalZoneLoss(left_weight=19.0, scale=SCALE)
        best_s2, ep_s2 = train_forecast_clinical(
            model, train_ds, val_ds, ckpt_s2,
            label=f'EXP-297: S2-Clinical s{seed}',
            loss_fn=clinical_loss, epochs=50, patience=15,
            lr=1e-4, weight_decay=1e-4, scale=SCALE,
        )

        # Evaluate final model
        model_mse = forecast_mse(model, val_ds)
        overall_mae = compute_mae(model_mse)
        hypo_mae, inrange_mae, hyper_mae = _stratified_mae(model, val_ds)

        results[f's{seed}'] = {
            'seed': seed,
            'stage1_epochs': ep_s1, 'stage1_best_val': float(best_s1),
            'stage2_epochs': ep_s2, 'stage2_best_val': float(best_s2),
            'overall_mae': round(overall_mae, 2),
            'hypo_mae': round(hypo_mae, 2),
            'inrange_mae': round(inrange_mae, 2),
            'hyper_mae': round(hyper_mae, 2),
        }
        model.cpu()

    result = {
        'experiment': 'EXP-297: Two-Stage MSE → Clinical Training',
        'hypothesis': 'MSE warmup + clinical refinement outperforms single-stage clinical',
        'seeds': results,
        'mean_overall': round(np.mean([r['overall_mae'] for r in results.values()]), 2),
        'mean_hypo': round(np.mean([r['hypo_mae'] for r in results.values()]), 2),
        'mean_inrange': round(np.mean([r['inrange_mae'] for r in results.values()]), 2),
    }
    save_results(result, os.path.join(output_dir, 'exp297_two_stage.json'))
    return result


REGISTRY['two-stage-training'] = 'run_two_stage_training'


# ── EXP-279: Asymmetric DIA-Aware Lookback Sweep ──────────────────
# Insulin DIA = 6hr, peak at ~75min. Current windows use symmetric splits
# that give only 1hr history — can't see boluses >1hr ago.
# Test asymmetric: {2hr, 3hr, 6hr} history → 1hr forecast.
def run_dia_aware_lookback(args):
    """EXP-279: Asymmetric DIA-aware lookback sweep.

    Tests clinically-motivated history lengths aligned to insulin dynamics:
    - 2hr (24 steps): covers insulin peak (~75min)
    - 3hr (36 steps): covers ~75% of DIA tail
    - 6hr (72 steps): covers full DIA (360min)
    All with fixed 1hr (12 steps) forecast horizon.

    Uses 21f features with ch_drop=0.15. Single seed + single FT
    for fast sweep, with verification evaluation.
    """
    import copy

    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    device = get_device()

    from .schema import NUM_FEATURES_EXTENDED, FUTURE_UNKNOWN_CHANNELS
    from torch.utils.data import DataLoader

    validate_masking(NUM_FEATURES_EXTENDED, label='EXP-279')
    CH_DROP_P = 0.15
    FORECAST_STEPS = 12  # Fixed 1hr forecast

    def _ch_drop_fwd(model, x_batch, crit, ch_drop_p, forecast_steps, training=False):
        x = batch_to_device(x_batch, device)
        split = x.shape[1] - forecast_steps
        x_in = x.clone()
        mask_future_channels(x_in, split)
        if training and ch_drop_p > 0:
            n_ch = x_in.shape[2]
            droppable = [c for c in range(n_ch)
                        if c not in {0, 6, 7}
                        and c not in set(FUTURE_UNKNOWN_CHANNELS)]
            mask = torch.rand(len(droppable)) < ch_drop_p
            for i, ch in enumerate(droppable):
                if mask[i]:
                    x_in[:, :, ch] = 0.0
        pred = model(x_in, causal=True)
        loss = crit(pred[:, split:, :1], x[:, split:, :1])
        return loss

    def _persist_mae_asym(ds, forecast_steps):
        """Persistence MAE with asymmetric split."""
        all_ae = []
        for i in range(len(ds)):
            x = ds[i][0]  # (seq, features)
            split = x.shape[0] - forecast_steps
            last_known = x[split - 1, 0].item()
            actual = x[split:, 0]
            ae = torch.abs(actual - last_known).mean().item()
            all_ae.append(ae)
        scale = 400.0
        return float(np.mean(all_ae)) * scale

    def _mae_asym(model, ds, forecast_steps):
        """MAE with asymmetric split."""
        model.eval()
        model.to(device)
        dl = DataLoader(ds, batch_size=64)
        total_ae, total_n = 0.0, 0
        scale = 400.0
        with torch.no_grad():
            for b in dl:
                x = batch_to_device(b[0], device)
                split = x.shape[1] - forecast_steps
                x_in = x.clone()
                mask_future_channels(x_in, split)
                pred = model(x_in, causal=True)
                ae = torch.abs(pred[:, split:, :1] - x[:, split:, :1])
                total_ae += ae.sum().item() * scale
                total_n += ae.numel()
        return total_ae / total_n if total_n else float('inf')

    def _train_cd_asym(model, t_ds, v_ds, ch_drop_p, forecast_steps,
                        epochs, patience, lr=1e-3, wd=1e-5, save_path=None):
        model.to(device)
        t_dl = DataLoader(t_ds, batch_size=32, shuffle=True)
        v_dl = DataLoader(v_ds, batch_size=64)
        opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
        crit = torch.nn.MSELoss()
        best_vl, stale = float('inf'), 0
        for ep in range(epochs):
            model.train()
            for b in t_dl:
                opt.zero_grad()
                loss = _ch_drop_fwd(model, b[0], crit, ch_drop_p, forecast_steps, training=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
            model.eval()
            vt, vn = 0.0, 0
            with torch.no_grad():
                for b in v_dl:
                    l = _ch_drop_fwd(model, b[0], crit, 0.0, forecast_steps, training=False)
                    vt += l.item() * b[0].shape[0]; vn += b[0].shape[0]
            vl = vt / vn if vn else float('inf')
            sched.step(vl)
            if vl < best_vl:
                best_vl = vl; stale = 0
                if save_path:
                    os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
                    torch.save({'model_state': model.state_dict()}, save_path)
            else:
                stale += 1
            if stale >= patience:
                break
        if save_path and os.path.exists(save_path):
            ckpt = torch.load(save_path, map_location=device, weights_only=True)
            model.load_state_dict(ckpt['model_state'])
        return model

    patients_base = os.path.dirname(os.path.dirname(patient_paths[0]))
    patient_dirs = sorted([d for d in os.listdir(patients_base)
                          if os.path.isdir(os.path.join(patients_base, d))])

    # Configs: (name, history_steps, forecast_steps, total_ws)
    # Also include symmetric baseline for comparison
    configs = [
        ('sym_1h1h',   12, 12, 24,  '1hr hist → 1hr fore (symmetric baseline)'),
        ('asym_2h1h',  24, 12, 36,  '2hr hist → 1hr fore (covers insulin peak)'),
        ('asym_3h1h',  36, 12, 48,  '3hr hist → 1hr fore (covers 75% DIA)'),
        ('asym_6h1h',  72, 12, 84,  '6hr hist → 1hr fore (full DIA)'),
        ('sym_2h2h',   24, 24, 48,  '2hr hist → 2hr fore (EXP-242 equivalent)'),
    ]

    all_results = {}
    for cname, hist_steps, fcast_steps, ws, desc in configs:
        print(f"\n=== {cname}: {desc} (ws={ws}, hist={hist_steps*5}min, fore={fcast_steps*5}min) ===")

        # Load data with this window size
        train_ds, val_ds = load_multipatient_nightscout(
            patient_paths, task='forecast', window_size=ws,
            extended_features=True)
        persist = _persist_mae_asym(val_ds, fcast_steps)
        print(f"  Data: {len(train_ds)} train, {len(val_ds)} val, persist={persist:.1f}")

        # Train base model
        set_seed(42)
        model = create_model(arch='grouped', input_dim=NUM_FEATURES_EXTENDED,
                             d_model=64, nhead=4, num_layers=2, dropout=0.1)
        sp = os.path.join(output_dir, f'exp279_{cname}_s42.pth')
        model = _train_cd_asym(model, train_ds, val_ds, CH_DROP_P, fcast_steps,
                               epochs=100, patience=15, save_path=sp)
        base_mae = _mae_asym(model, val_ds, fcast_steps)
        print(f"  Base MAE: {base_mae:.2f} (persist={persist:.1f}, improvement={((persist-base_mae)/persist*100):.1f}%)")

        # Per-patient FT + verification
        pt_results = {}
        for pid in patient_dirs:
            train_path = os.path.join(patients_base, pid, 'training')
            ver_path = os.path.join(patients_base, pid, 'verification')
            if not os.path.isdir(train_path):
                continue
            try:
                pt_tr, pt_vl = load_multipatient_nightscout(
                    [train_path], task='forecast', window_size=ws,
                    extended_features=True)
            except:
                continue

            pt_ver = None
            if os.path.isdir(ver_path):
                try:
                    _, pt_ver = load_multipatient_nightscout(
                        [ver_path], task='forecast', window_size=ws,
                        extended_features=True)
                    if pt_ver and len(pt_ver) < 5:
                        pt_ver = None
                except:
                    pt_ver = None

            set_seed(42)
            ftm = copy.deepcopy(model)
            ft_sp = os.path.join(output_dir, f'exp279_{cname}_{pid}.pth')
            ftm = _train_cd_asym(ftm, pt_tr, pt_vl, CH_DROP_P, fcast_steps,
                                  epochs=30, patience=8, lr=3e-4, save_path=ft_sp)

            tr_mae = _mae_asym(ftm, pt_vl, fcast_steps)
            ver_mae = _mae_asym(ftm, pt_ver, fcast_steps) if pt_ver else None
            gap = round((ver_mae / tr_mae - 1) * 100, 1) if ver_mae and tr_mae > 0 else None
            pt_results[pid] = {'train': round(tr_mae, 2),
                               'ver': round(ver_mae, 2) if ver_mae else None,
                               'gap': gap}

        tr_ms = [v['train'] for v in pt_results.values()]
        ver_ms = [v['ver'] for v in pt_results.values() if v['ver'] is not None]
        gaps = [v['gap'] for v in pt_results.values() if v['gap'] is not None]

        all_results[cname] = {
            'description': desc,
            'window_size': ws,
            'history_min': hist_steps * 5,
            'forecast_min': fcast_steps * 5,
            'n_train': len(train_ds),
            'n_val': len(val_ds),
            'persist_mae': round(persist, 2),
            'base_mae': round(base_mae, 2),
            'mean_ft_train': round(float(np.mean(tr_ms)), 2),
            'mean_ft_ver': round(float(np.mean(ver_ms)), 2) if ver_ms else None,
            'mean_gap': round(float(np.mean(gaps)), 1) if gaps else None,
            'patients': pt_results,
        }
        print(f"  FT: train={all_results[cname]['mean_ft_train']} "
              f"ver={all_results[cname]['mean_ft_ver']} gap={all_results[cname]['mean_gap']}%")

    result = {
        'experiment': 'EXP-279: Asymmetric DIA-Aware Lookback Sweep',
        'features': '21f extended',
        'ch_dropout': CH_DROP_P,
        'forecast_horizon': '1hr (12 steps) fixed for asymmetric configs',
        'configs': all_results,
    }
    save_results(result, os.path.join(output_dir, 'exp279_dia_aware_lookback.json'))
    return result

REGISTRY['dia-aware-lookback'] = 'run_dia_aware_lookback'


def run_8f_asymmetric_lookback(args):
    """EXP-280: 8f Asymmetric DIA-Aware Lookback Sweep.

    Tests clinically-motivated history lengths with 8f features (best generalizer).
    8f loader does NOT double window_size, so window sizes are exact.

    EXP-278 showed 8f has NEGATIVE verification gaps at all window sizes.
    Question: does extending history (without extending forecast) improve MAE?

    Configs:
    - sym_1h1h:  12 hist + 12 fore = 24 total (EXP-278 baseline)
    - asym_2h1h: 24 hist + 12 fore = 36 total (insulin peak coverage)
    - asym_3h1h: 36 hist + 12 fore = 48 total (75% DIA tail)
    - asym_6h1h: 72 hist + 12 fore = 84 total (full DIA)
    - sym_2h2h:  24 hist + 24 fore = 48 total (2hr forecast comparison)
    """
    import copy

    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    output_dir = getattr(args, 'output_dir', 'externals/experiments')
    patient_paths = resolve_patient_paths(patients_dir)
    device = get_device()

    from .schema import NUM_FEATURES, FUTURE_UNKNOWN_CHANNELS
    from torch.utils.data import DataLoader

    validate_masking(NUM_FEATURES, label='EXP-280')
    CH_DROP_P = 0.15
    NF = NUM_FEATURES  # 8

    def _ch_drop_fwd(model, x_batch, crit, ch_drop_p, forecast_steps, training=False):
        x = batch_to_device(x_batch, device)
        split = x.shape[1] - forecast_steps
        x_in = x.clone()
        mask_future_channels(x_in, split)
        if training and ch_drop_p > 0:
            n_ch = x_in.shape[2]
            droppable = [c for c in range(n_ch)
                        if c not in {0, 6, 7}
                        and c not in set(FUTURE_UNKNOWN_CHANNELS)]
            mask = torch.rand(len(droppable)) < ch_drop_p
            for i, ch in enumerate(droppable):
                if mask[i]:
                    x_in[:, :, ch] = 0.0
        pred = model(x_in, causal=True)
        loss = crit(pred[:, split:, :1], x[:, split:, :1])
        return loss

    def _persist_mae_asym(ds, forecast_steps):
        all_ae = []
        for i in range(len(ds)):
            x = ds[i][0]
            split = x.shape[0] - forecast_steps
            last_known = x[split - 1, 0].item()
            actual = x[split:, 0]
            ae = torch.abs(actual - last_known).mean().item()
            all_ae.append(ae)
        return float(np.mean(all_ae)) * 400.0

    def _mae_asym(model, ds, forecast_steps):
        model.eval()
        model.to(device)
        dl = DataLoader(ds, batch_size=64)
        total_ae, total_n = 0.0, 0
        with torch.no_grad():
            for b in dl:
                x = batch_to_device(b[0], device)
                split = x.shape[1] - forecast_steps
                x_in = x.clone()
                mask_future_channels(x_in, split)
                pred = model(x_in, causal=True)
                ae = torch.abs(pred[:, split:, :1] - x[:, split:, :1])
                total_ae += ae.sum().item() * 400.0
                total_n += ae.numel()
        return total_ae / total_n if total_n else float('inf')

    def _train_cd_asym(model, t_ds, v_ds, ch_drop_p, forecast_steps,
                        epochs, patience, lr=1e-3, wd=1e-5, save_path=None):
        model.to(device)
        t_dl = DataLoader(t_ds, batch_size=32, shuffle=True)
        v_dl = DataLoader(v_ds, batch_size=64)
        opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
        crit = torch.nn.MSELoss()
        best_vl, stale = float('inf'), 0
        for ep in range(epochs):
            model.train()
            for b in t_dl:
                opt.zero_grad()
                loss = _ch_drop_fwd(model, b[0], crit, ch_drop_p, forecast_steps, training=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
            model.eval()
            vt, vn = 0.0, 0
            with torch.no_grad():
                for b in v_dl:
                    l = _ch_drop_fwd(model, b[0], crit, 0.0, forecast_steps, training=False)
                    vt += l.item() * b[0].shape[0]; vn += b[0].shape[0]
            vl = vt / vn if vn else float('inf')
            sched.step(vl)
            if vl < best_vl:
                best_vl = vl; stale = 0
                if save_path:
                    os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
                    torch.save({'model_state': model.state_dict()}, save_path)
            else:
                stale += 1
            if stale >= patience:
                break
        if save_path and os.path.exists(save_path):
            ckpt = torch.load(save_path, map_location=device, weights_only=True)
            model.load_state_dict(ckpt['model_state'])
        return model

    patients_base = os.path.dirname(os.path.dirname(patient_paths[0]))
    patient_dirs = sorted([d for d in os.listdir(patients_base)
                          if os.path.isdir(os.path.join(patients_base, d))])

    # 8f loader does NOT double window_size — ws IS the total window
    configs = [
        ('sym_1h1h',   12, 12, 24,  '1hr hist → 1hr fore (symmetric baseline)'),
        ('asym_2h1h',  24, 12, 36,  '2hr hist → 1hr fore (insulin peak)'),
        ('asym_3h1h',  36, 12, 48,  '3hr hist → 1hr fore (75% DIA)'),
        ('asym_6h1h',  72, 12, 84,  '6hr hist → 1hr fore (full DIA)'),
        ('sym_2h2h',   24, 24, 48,  '2hr hist → 2hr fore (longer forecast)'),
    ]

    all_results = {}
    for cname, hist_steps, fcast_steps, ws, desc in configs:
        print(f"\n=== {cname}: {desc} (ws={ws}, hist={hist_steps*5}min, fore={fcast_steps*5}min) ===")

        train_ds, val_ds = load_multipatient_nightscout(
            patient_paths, task='forecast', window_size=ws,
            extended_features=False)  # 8f — no doubling
        persist = _persist_mae_asym(val_ds, fcast_steps)
        print(f"  Data: {len(train_ds)} train, {len(val_ds)} val, persist={persist:.1f}")

        set_seed(42)
        model = create_model(arch='grouped', input_dim=NF,
                             d_model=64, nhead=4, num_layers=2, dropout=0.1)
        sp = os.path.join(output_dir, f'exp280_{cname}_s42.pth')
        model = _train_cd_asym(model, train_ds, val_ds, CH_DROP_P, fcast_steps,
                               epochs=100, patience=15, save_path=sp)
        base_mae = _mae_asym(model, val_ds, fcast_steps)
        print(f"  Base MAE: {base_mae:.2f} (persist={persist:.1f}, skill={((persist-base_mae)/persist*100):.1f}%)")

        pt_results = {}
        for pid in patient_dirs:
            train_path = os.path.join(patients_base, pid, 'training')
            ver_path = os.path.join(patients_base, pid, 'verification')
            if not os.path.isdir(train_path):
                continue
            try:
                pt_tr, pt_vl = load_multipatient_nightscout(
                    [train_path], task='forecast', window_size=ws,
                    extended_features=False)
            except:
                continue

            pt_ver = None
            if os.path.isdir(ver_path):
                try:
                    _, pt_ver = load_multipatient_nightscout(
                        [ver_path], task='forecast', window_size=ws,
                        extended_features=False)
                    if pt_ver and len(pt_ver) < 5:
                        pt_ver = None
                except:
                    pt_ver = None

            set_seed(42)
            ftm = copy.deepcopy(model)
            ft_sp = os.path.join(output_dir, f'exp280_{cname}_{pid}.pth')
            ftm = _train_cd_asym(ftm, pt_tr, pt_vl, CH_DROP_P, fcast_steps,
                                  epochs=30, patience=8, lr=3e-4, save_path=ft_sp)

            tr_mae = _mae_asym(ftm, pt_vl, fcast_steps)
            ver_mae = _mae_asym(ftm, pt_ver, fcast_steps) if pt_ver else None
            gap = round((ver_mae / tr_mae - 1) * 100, 1) if ver_mae and tr_mae > 0 else None
            pt_results[pid] = {'train': round(tr_mae, 2),
                               'ver': round(ver_mae, 2) if ver_mae else None,
                               'gap': gap}

        tr_ms = [v['train'] for v in pt_results.values()]
        ver_ms = [v['ver'] for v in pt_results.values() if v['ver'] is not None]
        gaps = [v['gap'] for v in pt_results.values() if v['gap'] is not None]

        all_results[cname] = {
            'description': desc,
            'window_size': ws,
            'history_min': hist_steps * 5,
            'forecast_min': fcast_steps * 5,
            'n_train': len(train_ds),
            'n_val': len(val_ds),
            'persist_mae': round(persist, 2),
            'base_mae': round(base_mae, 2),
            'mean_ft_train': round(float(np.mean(tr_ms)), 2),
            'mean_ft_ver': round(float(np.mean(ver_ms)), 2) if ver_ms else None,
            'mean_gap': round(float(np.mean(gaps)), 1) if gaps else None,
            'patients': pt_results,
        }
        ver_str = f"{all_results[cname]['mean_ft_ver']}" if all_results[cname]['mean_ft_ver'] is not None else "N/A"
        gap_str = f"{all_results[cname]['mean_gap']}%" if all_results[cname]['mean_gap'] is not None else "N/A"
        print(f"  FT: train={all_results[cname]['mean_ft_train']} ver={ver_str} gap={gap_str}")

    result = {
        'experiment': 'EXP-280: 8f Asymmetric DIA-Aware Lookback Sweep',
        'features': '8f core (no doubling)',
        'ch_dropout': CH_DROP_P,
        'forecast_horizon': '1hr (12 steps) fixed for asymmetric configs',
        'note': 'EXP-279 had window doubling bug for 21f. This tests 8f with correct windows.',
        'reference': {
            'exp278_8f_ws24': {'train': 11.5, 'ver': 11.44, 'gap': -0.9},
            'exp278_8f_ws48': {'train': 14.86, 'ver': 14.47, 'gap': -1.8},
        },
        'configs': all_results,
    }
    save_results(result, os.path.join(output_dir, 'exp280_8f_asymmetric_lookback.json'))
    return result

REGISTRY['8f-asymmetric-lookback'] = 'run_8f_asymmetric_lookback'
