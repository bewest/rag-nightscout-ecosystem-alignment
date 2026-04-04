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
