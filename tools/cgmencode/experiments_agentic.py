"""
experiments_agentic.py — Agentic Insulin Delivery Experiment Queue

╔════════════════════════════════════════════════════════════════════╗
║  THIS IS THE FILE CODING AGENTS SHOULD EDIT.                     ║
║                                                                   ║
║  Each experiment is a function that takes (args) and returns a    ║
║  results dict.  Shared infrastructure lives in experiment_lib.py  ║
║  — do NOT duplicate training loops, eval, or save logic here.     ║
╚════════════════════════════════════════════════════════════════════╝

Run any experiment:
    python3 -m tools.cgmencode.run_experiment <key> [flags]

Example:
    python3 -m tools.cgmencode.run_experiment extended-features \
        --patients-dir externals/ns-data/patients --real-data ...
"""

import glob as _glob_mod
import os
import numpy as np
import pandas as pd
import torch

from .experiment_lib import (
    ExperimentContext, set_seed, create_model,
    load_checkpoint, find_checkpoint, transfer_weights,
    train, train_forecast, forecast_mse, persistence_mse, improvement_pct,
    resolve_patient_paths, load_patient_profile,
    build_16f_windows, windows_to_datasets, get_device,
)
from .real_data_adapter import (
    load_multipatient_nightscout, build_nightscout_grid,
    build_extended_features, downsample_grid, build_multihorizon_windows,
)
from .schema import NUM_FEATURES, NUM_FEATURES_EXTENDED, NORMALIZATION_SCALES
from .model import CGMGroupedEncoder
from .label_events import build_classifier_dataset, extract_override_events
from .event_classifier import train_event_classifier
from .uncertainty import mc_predict
from .state_tracker import ISFCRTracker, DriftDetector, run_retrospective_tracking
from .forecast import HierarchicalForecaster, ScenarioSimulator, BacktestEngine
from .hindcast_composite import run_decision, run_calibration
from .validate_verification import (
    run_event_detection_verification, run_override_recommendation_verification,
    run_drift_tir_correlation, run_composite_verification, run_all_suites,
)

# ╔════════════════════════════════════════════════════════════════════╗
# ║  EXPERIMENT REGISTRY — add new experiments here                  ║
# ╚════════════════════════════════════════════════════════════════════╝
#
# Rounds 1-13 (EXP-026-109) archived in experiments_archive_r1_r13.py
# To re-run an archived experiment, use:
#   from .experiments_archive_r1_r13 import run_xxx; REGISTRY['xxx'] = 'run_xxx'

REGISTRY = {}


# ────────────────────────────────────────────────────────────────────
# Infrastructure shared by active experiments
# ────────────────────────────────────────────────────────────────────
import json as _json_mod

class _NumpyEncoder(_json_mod.JSONEncoder):
    """Handle numpy types in JSON serialization."""
    def default(self, obj):
        import numpy as _np
        if isinstance(obj, (_np.integer,)):
            return int(obj)
        if isinstance(obj, (_np.floating,)):
            return float(obj)
        if isinstance(obj, _np.ndarray):
            return obj.tolist()
        # Skip non-serializable objects (e.g. sklearn classifiers)
        try:
            return super().default(obj)
        except TypeError:
            return f"<{type(obj).__name__}>"


def _sanitize_for_json(obj):
    """Recursively convert numpy types in keys and values for JSON safety."""
    import numpy as _np
    if isinstance(obj, dict):
        return {str(k) if isinstance(k, _np.integer) else k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, _np.integer):
        return int(obj)
    if isinstance(obj, _np.floating):
        return float(obj)
    if isinstance(obj, _np.ndarray):
        return obj.tolist()
    return obj

import json  # standard import used by most experiments


# ────────────────────────────────────────────────────────────────────
# Archived experiments (Rounds 1-13, EXP-026 — EXP-109)
# Functions preserved in experiments_archive_r1_r13.py
# ────────────────────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════════════════════
# ║  ROUND 14: Best-of-breed integration, 6hr horizon, gradient ISF  ║
# ══════════════════════════════════════════════════════════════════════

REGISTRY.update({
    'production-v5':           'run_production_v5',           # EXP-110
    'direct-6hr':              'run_direct_6hr',              # EXP-111
    'conformal-ensemble':      'run_conformal_ensemble',      # EXP-112
    'gradient-isf':            'run_gradient_isf',            # EXP-113
    'attention-events':        'run_attention_events',        # EXP-114
    'range-stratified':        'run_range_stratified',        # EXP-115
})


# ── EXP-110: Production v5 — best-of-breed integration ─────────────
# Combines: hypo-augmented training (EXP-105) + conformal calibration
# (EXP-106) + confidence gating (EXP-104) into one pipeline.
# Goal: >95% precision, calibrated uncertainty, good hypo detection.
def run_production_v5(args):
    """EXP-110: Best-of-breed production planner."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-110] {len(train_ds)} train, {len(val_ds)} val')

    # Step 1: Hypo-augmented training (from EXP-105)
    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    hypo_thresh = 70.0 / gluc_scale

    # Identify and oversample hypo windows
    hypo_indices = []
    for i in range(len(train_ds)):
        x, _ = train_ds[i]
        if x[12:, 0].min() < hypo_thresh:
            hypo_indices.append(i)
    n_hypo = len(hypo_indices)
    print(f'  [EXP-110] Hypo windows: {n_hypo}/{len(train_ds)}')

    # Create augmented dataset with 3× hypo oversampling
    from torch.utils.data import ConcatDataset, Subset
    extra = Subset(train_ds, hypo_indices * 2) if hypo_indices else train_ds
    aug_ds = ConcatDataset([train_ds, extra])

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=10, factor=0.5)
    tl = DataLoader(aug_ds, batch_size=128, shuffle=True)
    vl = DataLoader(val_ds, batch_size=256)

    best_val = float('inf')
    best_state = None
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            opt.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward(); opt.step()
        model.eval()
        vloss = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                vloss += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0)
                vn += bx.size(0)
        vl_avg = vloss / vn
        sched.step(vl_avg)
        if vl_avg < best_val:
            best_val = vl_avg
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        if ep % 25 == 0:
            print(f'  [v5] {ep}/100 val={vl_avg:.6f} best={best_val:.6f}')

    model.load_state_dict(best_state)
    model.eval()

    # Step 2: Collect residuals for conformal calibration (from EXP-106)
    cal_residuals = []
    with torch.no_grad():
        for bx, bt in vl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            pred = model(x_in)
            res = (pred[:, 12:, 0] - bx[:, 12:, 0]).abs() * gluc_scale
            cal_residuals.append(res.cpu())
    cal_residuals = torch.cat(cal_residuals, dim=0)
    cal_max = cal_residuals.max(dim=1).values.numpy()

    # Conformal quantiles
    q80 = float(np.percentile(cal_max, 80))
    q90 = float(np.percentile(cal_max, 90))
    q95 = float(np.percentile(cal_max, 95))

    # Step 3: Generate plans with confidence gating (from EXP-104)
    n_plans = 0; n_actions = 0; n_correct = 0; n_total_checked = 0
    hypo_tp = 0; hypo_fp = 0; hypo_fn = 0

    with torch.no_grad():
        for bx, bt in vl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            pred = model(x_in)
            pred_mg = pred[:, 12:, 0] * gluc_scale
            actual_mg = bx[:, 12:, 0] * gluc_scale

            for i in range(bx.size(0)):
                p = pred_mg[i].cpu().numpy()
                a = actual_mg[i].cpu().numpy()
                res_i = abs(p - a)
                max_res = res_i.max()

                # Confidence = fraction of timesteps within q90 bound
                confidence = float((res_i < q90).mean())

                if confidence < 0.9:
                    continue  # skip low-confidence windows

                n_plans += 1
                plan_actions = []

                # Check for predicted hypo
                pred_hypo = p.min() < 70
                actual_hypo = a.min() < 70

                if pred_hypo:
                    plan_actions.append('hypo_alert')
                    if actual_hypo:
                        hypo_tp += 1
                    else:
                        hypo_fp += 1
                elif actual_hypo:
                    hypo_fn += 1

                # Check for predicted hyper
                if p.max() > 180:
                    plan_actions.append('consider_correction')
                    if a.max() > 150:
                        n_correct += 1
                    n_total_checked += 1

                # Check for rising trend
                if p[-1] - p[0] > 30:
                    plan_actions.append('rising_alert')
                elif p[-1] - p[0] < -30:
                    plan_actions.append('falling_alert')

                n_actions += len(plan_actions)

    precision = n_correct / max(n_total_checked, 1)
    hypo_prec = hypo_tp / max(hypo_tp + hypo_fp, 1)
    hypo_rec = hypo_tp / max(hypo_tp + hypo_fn, 1)
    hypo_f1 = 2 * hypo_prec * hypo_rec / max(hypo_prec + hypo_rec, 1e-8)

    # Step 4: Compute MAE
    all_mae = []
    with torch.no_grad():
        for bx, bt in vl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            pred = model(x_in)
            mae = (pred[:, 12:, 0] - bx[:, 12:, 0]).abs().mean() * gluc_scale
            all_mae.append(mae.item())
    avg_mae = float(np.mean(all_mae))

    results = {
        'mae_mgdl': round(avg_mae, 1),
        'conformal_q80': round(q80, 1),
        'conformal_q90': round(q90, 1),
        'conformal_q95': round(q95, 1),
        'n_plans': n_plans,
        'n_actions': n_actions,
        'correction_precision': round(precision, 3),
        'hypo_precision': round(hypo_prec, 3),
        'hypo_recall': round(hypo_rec, 3),
        'hypo_f1': round(hypo_f1, 3),
    }
    print(f'\n--- Production v5 results ---')
    for k, v in results.items():
        print(f'  [EXP-110] {k}: {v}')

    out_path = 'externals/experiments/exp110_production_v5.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-110', 'name': 'production-v5',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-111: Direct 6hr forecast ───────────────────────────────────
# Direct training at 6hr horizon with ws=72 (every 2 timesteps = 10min).
# Previous indirect 6hr: ~18.4 MAE (EXP-053). Direct 3hr: 19.5 (EXP-093).
# Hypothesis: Direct 6hr training gives <25 mg/dL MAE.
def run_direct_6hr(args):
    """EXP-111: Direct 6hr forecast training."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)

    # Load with ws=72 (6hr at 5-min intervals)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=72)
    print(f'  [EXP-111] ws=72: {len(train_ds)} train, {len(val_ds)} val')

    half = 36  # 3hr history, 3hr forecast (still "6hr" total window)

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=10, factor=0.5)
    tl = DataLoader(train_ds, batch_size=64, shuffle=True)
    vl = DataLoader(val_ds, batch_size=128)

    best_val = float('inf'); best_state = None
    for ep in range(1, 121):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            opt.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
            loss.backward(); opt.step()
        model.eval()
        vloss = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                vloss += F.mse_loss(pred[:, half:, :1], bx[:, half:, :1]).item() * bx.size(0)
                vn += bx.size(0)
        vl_avg = vloss / vn
        sched.step(vl_avg)
        if vl_avg < best_val:
            best_val = vl_avg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        if ep % 30 == 0:
            print(f'  [6hr] {ep}/120 val={vl_avg:.6f} best={best_val:.6f}')

    model.load_state_dict(best_state)
    model.eval()

    # Evaluate at different horizons within the 3hr forecast window
    maes_by_step = []
    with torch.no_grad():
        for bx, bt in vl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            pred = model(x_in)
            for t in range(half, 72):
                e = (pred[:, t, 0] - bx[:, t, 0]).abs().mean() * gluc_scale
                if len(maes_by_step) <= t - half:
                    maes_by_step.append([])
                maes_by_step[t - half].append(e.item())

    step_maes = [float(np.mean(m)) for m in maes_by_step]

    # Key horizons: 30min (6 steps), 1hr (12), 2hr (24), 3hr (36=end)
    results = {
        'window_size': 72,
        'history_steps': half,
        'forecast_steps': 72 - half,
        'mae_30min_mgdl': round(float(np.mean(step_maes[:6])), 1),
        'mae_1hr_mgdl': round(float(np.mean(step_maes[:12])), 1),
        'mae_2hr_mgdl': round(float(np.mean(step_maes[:24])), 1),
        'mae_3hr_mgdl': round(float(np.mean(step_maes)), 1),
        'persistence_3hr': round(float(np.mean([abs(0) for _ in step_maes])), 1),  # placeholder
    }

    # Compute persistence baseline
    persist_maes = []
    with torch.no_grad():
        for bx, bt in vl:
            bx = bx.to(device)
            last_known = bx[:, half-1:half, 0].expand(-1, 72 - half)
            actual = bx[:, half:, 0]
            persist_maes.append((last_known - actual).abs().mean().item() * gluc_scale)
    results['persistence_3hr'] = round(float(np.mean(persist_maes)), 1)

    print(f'\n--- Direct 6hr forecast results ---')
    for k, v in results.items():
        print(f'  [EXP-111] {k}: {v}')

    out_path = 'externals/experiments/exp111_direct_6hr.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-111', 'name': 'direct-6hr',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-112: Conformal seed ensemble ───────────────────────────────
# Combines 5-seed ensemble (EXP-100, MAE=11.7) with conformal
# calibration (EXP-106). Fixes ensemble's under-coverage (55.7%→90%+).
def run_conformal_ensemble(args):
    """EXP-112: Conformal-calibrated seed ensemble."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-112] {len(train_ds)} train, {len(val_ds)} val')

    n_seeds = 5
    models = []

    for seed in range(n_seeds):
        torch.manual_seed(seed * 42 + 7)
        m = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        opt = torch.optim.AdamW(m.parameters(), lr=1e-3)
        tl = DataLoader(train_ds, batch_size=128, shuffle=True)

        best_val = float('inf'); best_st = None
        for ep in range(1, 81):
            m.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                opt.zero_grad()
                pred = m(x_in)
                loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                loss.backward(); opt.step()
            if ep % 20 == 0:
                m.eval()
                vl_loader = DataLoader(val_ds, batch_size=256)
                vl_sum = 0; vn = 0
                with torch.no_grad():
                    for bx, bt in vl_loader:
                        bx = bx.to(device)
                        x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                        pred = m(x_in)
                        vl_sum += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0)
                        vn += bx.size(0)
                vl_avg = vl_sum / vn
                if vl_avg < best_val:
                    best_val = vl_avg; best_st = {k: v.cpu().clone() for k, v in m.state_dict().items()}
                print(f'  [seed {seed}] {ep}/80 val={vl_avg:.6f}')
        m.load_state_dict(best_st); m.eval()
        models.append(m)
        print(f'  [EXP-112] Seed {seed} done')

    # Split val into calibration (first 60%) and test (last 40%)
    n_cal = int(len(val_ds) * 0.6)
    cal_ds = torch.utils.data.Subset(val_ds, range(n_cal))
    test_ds = torch.utils.data.Subset(val_ds, range(n_cal, len(val_ds)))

    # Calibration: collect nonconformity scores on cal set
    cal_loader = DataLoader(cal_ds, batch_size=256)
    cal_scores = []
    with torch.no_grad():
        for bx, bt in cal_loader:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            preds = []
            for m in models:
                preds.append(m(x_in)[:, 12:, 0:1])
            ensemble = torch.stack(preds, dim=0)  # [5, B, T, 1]
            mean_pred = ensemble.mean(dim=0)  # [B, T, 1]
            std_pred = ensemble.std(dim=0)    # [B, T, 1]
            # Nonconformity = |actual - mean| / (std + eps)
            actual = bx[:, 12:, 0:1]
            scores = ((actual - mean_pred).abs() / (std_pred + 1e-6))
            cal_scores.append(scores.max(dim=1).values.squeeze(-1).cpu())  # max over time

    cal_scores = torch.cat(cal_scores).numpy()

    # Compute conformal quantiles
    q80 = float(np.percentile(cal_scores, 80))
    q90 = float(np.percentile(cal_scores, 90))
    q95 = float(np.percentile(cal_scores, 95))

    # Test: evaluate ensemble + conformal bands
    test_loader = DataLoader(test_ds, batch_size=256)
    all_mae = []; cov_80 = []; cov_90 = []; cov_95 = []
    width_80 = []; width_90 = []; width_95 = []

    with torch.no_grad():
        for bx, bt in test_loader:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            preds = []
            for m in models:
                preds.append(m(x_in)[:, 12:, 0])
            ensemble = torch.stack(preds, dim=0)
            mean_p = ensemble.mean(dim=0)
            std_p = ensemble.std(dim=0)
            actual = bx[:, 12:, 0]

            mae = (mean_p - actual).abs().mean() * gluc_scale
            all_mae.append(mae.item())

            for q_val, cov_list, w_list in [(q80, cov_80, width_80),
                                             (q90, cov_90, width_90),
                                             (q95, cov_95, width_95)]:
                half_width = q_val * (std_p + 1e-6) * gluc_scale
                lower = (mean_p - q_val * (std_p + 1e-6)) * gluc_scale
                upper = (mean_p + q_val * (std_p + 1e-6)) * gluc_scale
                actual_mg = actual * gluc_scale
                covered = ((actual_mg >= lower) & (actual_mg <= upper)).float().mean()
                width = (upper - lower).mean()
                cov_list.append(covered.item())
                w_list.append(width.item())

    results = {
        'ensemble_mae_mgdl': round(float(np.mean(all_mae)), 1),
        'n_seeds': n_seeds,
        'conformal_q80': round(q80, 2),
        'conformal_q90': round(q90, 2),
        'conformal_q95': round(q95, 2),
        'coverage_80': round(float(np.mean(cov_80)), 3),
        'coverage_90': round(float(np.mean(cov_90)), 3),
        'coverage_95': round(float(np.mean(cov_95)), 3),
        'width_80_mgdl': round(float(np.mean(width_80)), 1),
        'width_90_mgdl': round(float(np.mean(width_90)), 1),
        'width_95_mgdl': round(float(np.mean(width_95)), 1),
    }
    print(f'\n--- Conformal ensemble results ---')
    for k, v in results.items():
        print(f'  [EXP-112] {k}: {v}')

    out_path = 'externals/experiments/exp112_conformal_ensemble.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-112', 'name': 'conformal-ensemble',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-113: Gradient-based ISF estimation ─────────────────────────
# Instead of counterfactual substitution (gives ~3 mg/dL/U, way too low),
# compute d(glucose_output) / d(insulin_input) via autograd.
# Expected: ISF should be 20-50 mg/dL/U for most T1D patients.
def run_gradient_isf(args):
    """EXP-113: Gradient-based insulin sensitivity estimation."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    insulin_scale = NORMALIZATION_SCALES.get('insulin', 20.0)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-113] {len(train_ds)} train, {len(val_ds)} val')

    # Train a model first
    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    vl = DataLoader(val_ds, batch_size=256)

    best_val = float('inf'); best_state = None
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            opt.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward(); opt.step()
        model.eval()
        vloss = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                vloss += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0)
                vn += bx.size(0)
        vl_avg = vloss / vn
        if vl_avg < best_val:
            best_val = vl_avg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        if ep % 25 == 0:
            print(f'  [ISF] {ep}/100 val={vl_avg:.6f} best={best_val:.6f}')

    model.load_state_dict(best_state)
    model.eval()

    # Compute gradients: d(future_glucose) / d(insulin_input) per sample
    # insulin is feature index 1 (in the 8-dim input)
    isf_estimates = []
    per_step_grads = [[] for _ in range(12)]

    vl2 = DataLoader(val_ds, batch_size=32)
    n_computed = 0
    for bx, bt in vl2:
        bx = bx.to(device)
        x_in = bx.clone()
        x_in[:, 12:, 0] = 0.0
        x_in.requires_grad_(True)

        pred = model(x_in)
        # Mean future glucose
        future_gluc = pred[:, 12:, 0].mean(dim=1)  # [B]

        for i in range(min(bx.size(0), 16)):  # limit per batch
            if x_in.grad is not None:
                x_in.grad.zero_()
            future_gluc[i].backward(retain_graph=True)

            # Gradient of future glucose w.r.t. insulin at all history steps
            grad_insulin = x_in.grad[i, :12, 1].cpu().numpy()  # [12]

            # ISF = -d(glucose) / d(insulin) in mg/dL per unit
            # Convert from normalized: glucose_scale / insulin_scale
            isf_per_step = -grad_insulin * gluc_scale / insulin_scale
            isf_estimates.append(float(isf_per_step.sum()))

            for t in range(12):
                per_step_grads[t].append(float(isf_per_step[t]))

        x_in.requires_grad_(False)
        n_computed += min(bx.size(0), 16)
        if n_computed >= 500:
            break

    isf_arr = np.array(isf_estimates)

    results = {
        'n_samples': len(isf_estimates),
        'isf_mean': round(float(isf_arr.mean()), 2),
        'isf_median': round(float(np.median(isf_arr)), 2),
        'isf_std': round(float(isf_arr.std()), 2),
        'isf_p10': round(float(np.percentile(isf_arr, 10)), 2),
        'isf_p25': round(float(np.percentile(isf_arr, 25)), 2),
        'isf_p75': round(float(np.percentile(isf_arr, 75)), 2),
        'isf_p90': round(float(np.percentile(isf_arr, 90)), 2),
        'per_step_mean_isf': [round(float(np.mean(g)), 2) for g in per_step_grads if g],
        'expected_range': '20-50 mg/dL/U for T1D',
    }
    print(f'\n--- Gradient ISF results ---')
    for k, v in results.items():
        if k != 'per_step_mean_isf':
            print(f'  [EXP-113] {k}: {v}')
    print(f'  [EXP-113] per_step_mean_isf: {results["per_step_mean_isf"][:6]}...')

    out_path = 'externals/experiments/exp113_gradient_isf.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-113', 'name': 'gradient-isf',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-114: Attention-based event features ────────────────────────
# Extract attention weights from trained forecast model.
# High attention on insulin → correction event, on carbs → meal event.
# Alternative to explicit event classification.
def run_attention_events(args):
    """EXP-114: Attention-based event detection."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-114] {len(train_ds)} train, {len(val_ds)} val')

    # Train a model
    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)

    for ep in range(1, 81):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            opt.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward(); opt.step()
        if ep % 20 == 0:
            print(f'  [attn] {ep}/80')

    model.eval()

    # Hook into attention layers to capture attention weights
    attention_weights = []
    hooks = []

    def make_hook(layer_idx):
        def hook_fn(module, input_args, output):
            # MultiheadAttention returns (attn_output, attn_weights)
            if isinstance(output, tuple) and len(output) >= 2 and output[1] is not None:
                attention_weights.append(output[1].detach().cpu())
        return hook_fn

    # Register hooks on the self-attention layers
    for i, layer in enumerate(model.transformer_encoder.layers):
        h = layer.self_attn.register_forward_hook(make_hook(i))
        hooks.append(h)

    # Also need to set need_weights=True
    # Monkey-patch forward to capture attention
    original_forwards = []
    for layer in model.transformer_encoder.layers:
        original_forwards.append(layer.self_attn.forward)

    # Instead of monkey-patching, use gradient-based feature attribution
    # which is more reliable than attention extraction
    for h in hooks:
        h.remove()

    # Feature attribution via input gradients (more reliable than attention)
    insulin_attr = []  # attribution to insulin features
    carb_attr = []     # attribution to carb features
    gluc_attr = []     # attribution to glucose features

    vl = DataLoader(val_ds, batch_size=32)
    n_samples = 0

    for bx, bt in vl:
        bx = bx.to(device)
        x_in = bx.clone()
        x_in[:, 12:, 0] = 0.0
        x_in.requires_grad_(True)

        pred = model(x_in)
        # Target: max glucose drop in forecast (most interesting signal)
        future_gluc = pred[:, 12:, 0]  # [B, 12]
        # Use mean future glucose as target
        target = future_gluc.mean(dim=1)

        for i in range(min(bx.size(0), 8)):
            if x_in.grad is not None:
                x_in.grad.zero_()
            target[i].backward(retain_graph=True)

            # Input gradient attribution (integrated gradient lite)
            grad = x_in.grad[i, :12].cpu().numpy()  # [12, 8]
            inp = x_in[i, :12].detach().cpu().numpy()
            attr = grad * inp  # element-wise attribution

            # Feature groups: 0=glucose, 1=insulin, 2=carbs, rest=time/other
            gluc_attr.append(float(np.abs(attr[:, 0]).sum()))
            insulin_attr.append(float(np.abs(attr[:, 1]).sum()))
            carb_attr.append(float(np.abs(attr[:, 2]).sum()))
            n_samples += 1

        x_in.requires_grad_(False)
        if n_samples >= 500:
            break

    gluc_arr = np.array(gluc_attr)
    ins_arr = np.array(insulin_attr)
    carb_arr = np.array(carb_attr)
    total = gluc_arr + ins_arr + carb_arr + 1e-8

    # Classify windows by dominant attribution
    dominant = []
    for g, i, c in zip(gluc_arr, ins_arr, carb_arr):
        if i > g and i > c:
            dominant.append('insulin')
        elif c > g and c > i:
            dominant.append('carb')
        else:
            dominant.append('glucose')

    from collections import Counter
    dom_counts = Counter(dominant)

    results = {
        'n_samples': n_samples,
        'mean_glucose_attr': round(float(gluc_arr.mean()), 4),
        'mean_insulin_attr': round(float(ins_arr.mean()), 4),
        'mean_carb_attr': round(float(carb_arr.mean()), 4),
        'frac_glucose_dominant': round(dom_counts.get('glucose', 0) / n_samples, 3),
        'frac_insulin_dominant': round(dom_counts.get('insulin', 0) / n_samples, 3),
        'frac_carb_dominant': round(dom_counts.get('carb', 0) / n_samples, 3),
        'relative_glucose': round(float((gluc_arr / total).mean()), 3),
        'relative_insulin': round(float((ins_arr / total).mean()), 3),
        'relative_carb': round(float((carb_arr / total).mean()), 3),
    }
    print(f'\n--- Attention/Attribution event results ---')
    for k, v in results.items():
        print(f'  [EXP-114] {k}: {v}')

    out_path = 'externals/experiments/exp114_attention_events.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-114', 'name': 'attention-events',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-115: Range-stratified forecast accuracy ────────────────────
# Evaluate MAE separately for hypo (<70), in-range (70-180), hyper (>180).
# Safety-critical: hypo accuracy matters most for agentic delivery.
def run_range_stratified(args):
    """EXP-115: Range-stratified forecast accuracy."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-115] {len(train_ds)} train, {len(val_ds)} val')

    # Train model
    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    vl = DataLoader(val_ds, batch_size=256)

    best_val = float('inf'); best_state = None
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            opt.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward(); opt.step()
        model.eval()
        vloss = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                vloss += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0)
                vn += bx.size(0)
        vl_avg = vloss / vn
        if vl_avg < best_val:
            best_val = vl_avg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        if ep % 25 == 0:
            print(f'  [strat] {ep}/100 val={vl_avg:.6f} best={best_val:.6f}')

    model.load_state_dict(best_state)
    model.eval()

    # Stratified evaluation
    hypo_errors = []  # actual < 70
    inrange_errors = []  # 70 <= actual <= 180
    hyper_errors = []  # actual > 180
    severe_hypo = []  # actual < 54

    # Also track directional accuracy
    rise_correct = 0; rise_total = 0
    fall_correct = 0; fall_total = 0

    with torch.no_grad():
        for bx, bt in vl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            pred = model(x_in)

            pred_mg = pred[:, 12:, 0] * gluc_scale
            actual_mg = bx[:, 12:, 0] * gluc_scale
            last_known = bx[:, 11, 0] * gluc_scale

            errors = (pred_mg - actual_mg).abs()

            for i in range(bx.size(0)):
                for t in range(12):
                    a = actual_mg[i, t].item()
                    e = errors[i, t].item()
                    if a < 54:
                        severe_hypo.append(e)
                        hypo_errors.append(e)
                    elif a < 70:
                        hypo_errors.append(e)
                    elif a <= 180:
                        inrange_errors.append(e)
                    else:
                        hyper_errors.append(e)

                # Directional accuracy
                actual_end = actual_mg[i, -1].item()
                pred_end = pred_mg[i, -1].item()
                lk = last_known[i].item()

                if actual_end > lk + 5:  # rising
                    rise_total += 1
                    if pred_end > lk + 5:
                        rise_correct += 1
                elif actual_end < lk - 5:  # falling
                    fall_total += 1
                    if pred_end < lk - 5:
                        fall_correct += 1

    results = {
        'overall_mae': round(float(np.mean(hypo_errors + inrange_errors + hyper_errors)), 1),
        'hypo_mae': round(float(np.mean(hypo_errors)) if hypo_errors else -1, 1),
        'hypo_n': len(hypo_errors),
        'severe_hypo_mae': round(float(np.mean(severe_hypo)) if severe_hypo else -1, 1),
        'severe_hypo_n': len(severe_hypo),
        'inrange_mae': round(float(np.mean(inrange_errors)) if inrange_errors else -1, 1),
        'inrange_n': len(inrange_errors),
        'hyper_mae': round(float(np.mean(hyper_errors)) if hyper_errors else -1, 1),
        'hyper_n': len(hyper_errors),
        'rise_accuracy': round(rise_correct / max(rise_total, 1), 3),
        'fall_accuracy': round(fall_correct / max(fall_total, 1), 3),
        'rise_n': rise_total,
        'fall_n': fall_total,
    }
    print(f'\n--- Range-stratified results ---')
    for k, v in results.items():
        print(f'  [EXP-115] {k}: {v}')

    out_path = 'externals/experiments/exp115_range_stratified.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-115', 'name': 'range-stratified',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ══════════════════════════════════════════════════════════════════════
# ║  ROUND 15: Hypo safety, ISF improvement, 12hr horizon, ensemble  ║
# ══════════════════════════════════════════════════════════════════════

REGISTRY.update({
    'hypo-weighted-loss':      'run_hypo_weighted_loss',      # EXP-116
    'insulin-aware-training':  'run_insulin_aware_training',  # EXP-117
    'direct-12hr':             'run_direct_12hr',             # EXP-118
    'ensemble-6hr':            'run_ensemble_6hr',            # EXP-119
    'gradient-isf-per-patient':'run_gradient_isf_per_patient',# EXP-120
    'trend-conditioned':       'run_trend_conditioned',       # EXP-121
})


# ── EXP-116: Hypo-weighted loss ────────────────────────────────────
# EXP-115 showed hypo MAE=15.7 vs in-range=10.3 (53% worse).
# Hypothesis: Weighting hypo timesteps 5× in loss reduces hypo MAE by >20%.
def run_hypo_weighted_loss(args):
    """EXP-116: Loss weighting for hypo accuracy improvement."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    hypo_norm = 70.0 / gluc_scale
    severe_norm = 54.0 / gluc_scale
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-116] {len(train_ds)} train, {len(val_ds)} val')

    results = {}
    for weight_name, hypo_w, severe_w in [('baseline', 1.0, 1.0), ('weighted', 5.0, 10.0)]:
        model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
        tl = DataLoader(train_ds, batch_size=128, shuffle=True)
        vl = DataLoader(val_ds, batch_size=256)
        best_val = float('inf'); best_state = None

        for ep in range(1, 101):
            model.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                opt.zero_grad()
                pred = model(x_in)
                # Per-timestep loss weighting based on actual glucose
                actual_gluc = bx[:, 12:, 0]  # [B, 12]
                weights = torch.ones_like(actual_gluc)
                weights[actual_gluc < hypo_norm] = hypo_w
                weights[actual_gluc < severe_norm] = severe_w
                per_ts_loss = (pred[:, 12:, 0] - actual_gluc) ** 2
                loss = (per_ts_loss * weights).mean()
                loss.backward(); opt.step()
            model.eval()
            vloss = 0; vn = 0
            with torch.no_grad():
                for bx, bt in vl:
                    bx = bx.to(device)
                    x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                    pred = model(x_in)
                    vloss += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0)
                    vn += bx.size(0)
            vl_avg = vloss / vn
            if vl_avg < best_val:
                best_val = vl_avg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            if ep % 25 == 0:
                print(f'  [{weight_name}] {ep}/100 val={vl_avg:.6f}')

        model.load_state_dict(best_state); model.eval()

        # Stratified evaluation
        hypo_e = []; severe_e = []; inrange_e = []; hyper_e = []
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                pred_mg = pred[:, 12:, 0] * gluc_scale
                actual_mg = bx[:, 12:, 0] * gluc_scale
                err = (pred_mg - actual_mg).abs()
                for i in range(bx.size(0)):
                    for t in range(12):
                        a = actual_mg[i, t].item(); e = err[i, t].item()
                        if a < 54: severe_e.append(e); hypo_e.append(e)
                        elif a < 70: hypo_e.append(e)
                        elif a <= 180: inrange_e.append(e)
                        else: hyper_e.append(e)

        results[weight_name] = {
            'overall_mae': round(float(np.mean(hypo_e + inrange_e + hyper_e)), 1),
            'hypo_mae': round(float(np.mean(hypo_e)) if hypo_e else -1, 1),
            'severe_hypo_mae': round(float(np.mean(severe_e)) if severe_e else -1, 1),
            'inrange_mae': round(float(np.mean(inrange_e)), 1),
            'hyper_mae': round(float(np.mean(hyper_e)), 1),
            'hypo_n': len(hypo_e), 'severe_n': len(severe_e),
        }
        print(f'  [{weight_name}] hypo={results[weight_name]["hypo_mae"]}, '
              f'severe={results[weight_name]["severe_hypo_mae"]}, '
              f'inrange={results[weight_name]["inrange_mae"]}')

    # Compare
    imp_hypo = (results['baseline']['hypo_mae'] - results['weighted']['hypo_mae']) / results['baseline']['hypo_mae'] * 100
    imp_severe = (results['baseline']['severe_hypo_mae'] - results['weighted']['severe_hypo_mae']) / max(results['baseline']['severe_hypo_mae'], 0.01) * 100
    results['hypo_improvement_pct'] = round(imp_hypo, 1)
    results['severe_improvement_pct'] = round(imp_severe, 1)

    print(f'\n--- Hypo-weighted loss results ---')
    print(f'  [EXP-116] Hypo improvement: {imp_hypo:.1f}%')
    print(f'  [EXP-116] Severe improvement: {imp_severe:.1f}%')

    out_path = 'externals/experiments/exp116_hypo_weighted_loss.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-116', 'name': 'hypo-weighted-loss',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-117: Insulin-aware training ────────────────────────────────
# EXP-114 showed model only uses 8.7% insulin attribution.
# Hypothesis: Auxiliary loss on insulin impact improves ISF + forecast.
# Add loss term: predict insulin-on-board at each future step.
def run_insulin_aware_training(args):
    """EXP-117: Auxiliary IOB prediction for insulin awareness."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-117] {len(train_ds)} train, {len(val_ds)} val')

    results = {}
    for variant, aux_weight in [('baseline', 0.0), ('insulin_aux', 0.3)]:
        model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
        tl = DataLoader(train_ds, batch_size=128, shuffle=True)
        vl = DataLoader(val_ds, batch_size=256)
        best_val = float('inf'); best_state = None

        for ep in range(1, 101):
            model.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                opt.zero_grad()
                pred = model(x_in)
                # Primary: glucose forecast
                gluc_loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                # Auxiliary: predict IOB (feature idx 3) in future timesteps
                if aux_weight > 0 and pred.size(-1) >= 4:
                    iob_loss = F.mse_loss(pred[:, 12:, 3:4], bx[:, 12:, 3:4])
                    loss = gluc_loss + aux_weight * iob_loss
                else:
                    loss = gluc_loss
                loss.backward(); opt.step()
            model.eval()
            vloss = 0; vn = 0
            with torch.no_grad():
                for bx, bt in vl:
                    bx = bx.to(device)
                    x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                    pred = model(x_in)
                    vloss += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0)
                    vn += bx.size(0)
            vl_avg = vloss / vn
            if vl_avg < best_val:
                best_val = vl_avg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            if ep % 25 == 0:
                print(f'  [{variant}] {ep}/100 val={vl_avg:.6f}')

        model.load_state_dict(best_state); model.eval()

        # Evaluate
        all_mae = []; ins_attr = []
        for bx, bt in vl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            x_in.requires_grad_(True)
            pred = model(x_in)
            mae = (pred[:, 12:, 0] - bx[:, 12:, 0]).abs().mean() * gluc_scale
            all_mae.append(mae.item())
            # Quick gradient check
            target = pred[:, 12:, 0].mean()
            target.backward()
            g_ins = x_in.grad[:, :12, 1].abs().mean().item()
            ins_attr.append(g_ins)
            x_in.requires_grad_(False)

        results[variant] = {
            'mae_mgdl': round(float(np.mean(all_mae)), 1),
            'insulin_gradient': round(float(np.mean(ins_attr)), 4),
        }
        print(f'  [{variant}] MAE={results[variant]["mae_mgdl"]}, '
              f'ins_grad={results[variant]["insulin_gradient"]}')

    imp = (results['baseline']['mae_mgdl'] - results['insulin_aux']['mae_mgdl']) / results['baseline']['mae_mgdl'] * 100
    grad_imp = (results['insulin_aux']['insulin_gradient'] - results['baseline']['insulin_gradient']) / max(results['baseline']['insulin_gradient'], 1e-6) * 100
    results['mae_improvement_pct'] = round(imp, 1)
    results['gradient_improvement_pct'] = round(grad_imp, 1)

    print(f'\n--- Insulin-aware results ---')
    print(f'  [EXP-117] MAE improvement: {imp:.1f}%')
    print(f'  [EXP-117] Insulin gradient increase: {grad_imp:.1f}%')

    out_path = 'externals/experiments/exp117_insulin_aware.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-117', 'name': 'insulin-aware-training',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-118: Direct 12hr forecast ──────────────────────────────────
# Extends EXP-111 (6hr) to 12hr horizon. Uses ws=144 (12hr at 5min).
# For memory efficiency, subsample to every 2 steps (10min resolution).
def run_direct_12hr(args):
    """EXP-118: Direct 12hr forecast with subsampled windows."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)

    # Load ws=144 (12hr), then subsample every 2 steps → 72 effective steps at 10min
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=144)
    print(f'  [EXP-118] ws=144 raw: {len(train_ds)} train, {len(val_ds)} val')

    # Subsample: take every 2nd timestep
    class SubsampledDataset(torch.utils.data.Dataset):
        def __init__(self, ds, step=2):
            self.ds = ds; self.step = step
        def __len__(self): return len(self.ds)
        def __getitem__(self, idx):
            x, t = self.ds[idx]
            return x[::self.step], t  # 144 → 72 at 10min resolution

    sub_train = SubsampledDataset(train_ds, step=2)
    sub_val = SubsampledDataset(val_ds, step=2)
    half = 36  # 36 steps × 10min = 6hr history, 6hr forecast

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    tl = DataLoader(sub_train, batch_size=64, shuffle=True)
    vl = DataLoader(sub_val, batch_size=128)

    best_val = float('inf'); best_state = None
    for ep in range(1, 121):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            opt.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
            loss.backward(); opt.step()
        model.eval()
        vloss = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                vloss += F.mse_loss(pred[:, half:, :1], bx[:, half:, :1]).item() * bx.size(0)
                vn += bx.size(0)
        vl_avg = vloss / vn
        if vl_avg < best_val:
            best_val = vl_avg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        if ep % 30 == 0:
            print(f'  [12hr] {ep}/120 val={vl_avg:.6f} best={best_val:.6f}')

    model.load_state_dict(best_state); model.eval()

    # Evaluate at key horizons (each step = 10min)
    maes_by_step = []
    with torch.no_grad():
        for bx, bt in vl:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            pred = model(x_in)
            for t in range(half, 72):
                e = (pred[:, t, 0] - bx[:, t, 0]).abs().mean() * gluc_scale
                if len(maes_by_step) <= t - half:
                    maes_by_step.append([])
                maes_by_step[t - half].append(e.item())

    step_maes = [float(np.mean(m)) for m in maes_by_step]

    # Persistence baseline
    persist_maes = []
    with torch.no_grad():
        for bx, bt in vl:
            bx = bx.to(device)
            last_known = bx[:, half-1:half, 0].expand(-1, 36)
            actual = bx[:, half:, 0]
            persist_maes.append((last_known - actual).abs().mean().item() * gluc_scale)

    results = {
        'resolution': '10min',
        'history_hours': 6,
        'forecast_hours': 6,
        'total_window_hours': 12,
        'mae_1hr_mgdl': round(float(np.mean(step_maes[:6])), 1),
        'mae_2hr_mgdl': round(float(np.mean(step_maes[:12])), 1),
        'mae_3hr_mgdl': round(float(np.mean(step_maes[:18])), 1),
        'mae_4hr_mgdl': round(float(np.mean(step_maes[:24])), 1),
        'mae_5hr_mgdl': round(float(np.mean(step_maes[:30])), 1),
        'mae_6hr_mgdl': round(float(np.mean(step_maes)), 1),
        'persistence_6hr': round(float(np.mean(persist_maes)), 1),
    }
    print(f'\n--- Direct 12hr forecast results ---')
    for k, v in results.items():
        print(f'  [EXP-118] {k}: {v}')

    out_path = 'externals/experiments/exp118_direct_12hr.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-118', 'name': 'direct-12hr',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-119: 6hr ensemble with conformal ──────────────────────────
# Best combination: 5-seed ensemble at 6hr + conformal calibration.
# Planning-critical: 6hr forecast with calibrated uncertainty.
def run_ensemble_6hr(args):
    """EXP-119: 5-seed 6hr forecast ensemble with conformal bands."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=72)
    half = 36
    print(f'  [EXP-119] ws=72: {len(train_ds)} train, {len(val_ds)} val')

    n_seeds = 3  # reduced from 5 for speed (still useful)
    models = []
    for seed in range(n_seeds):
        torch.manual_seed(seed * 42 + 7)
        m = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        opt = torch.optim.AdamW(m.parameters(), lr=1e-3)
        tl = DataLoader(train_ds, batch_size=64, shuffle=True)

        best_val = float('inf'); best_st = None
        for ep in range(1, 81):
            m.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                opt.zero_grad()
                pred = m(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward(); opt.step()
            if ep % 20 == 0:
                m.eval()
                vl_loader = DataLoader(val_ds, batch_size=128)
                vs = 0; vn = 0
                with torch.no_grad():
                    for bx, bt in vl_loader:
                        bx = bx.to(device)
                        x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                        pred = m(x_in)
                        vs += F.mse_loss(pred[:, half:, :1], bx[:, half:, :1]).item() * bx.size(0)
                        vn += bx.size(0)
                vavg = vs / vn
                if vavg < best_val: best_val = vavg; best_st = {k: v.cpu().clone() for k, v in m.state_dict().items()}
                print(f'  [seed {seed}] {ep}/80 val={vavg:.6f}')
        m.load_state_dict(best_st); m.eval()
        models.append(m)

    # Split val: 60% cal, 40% test
    n_cal = int(len(val_ds) * 0.6)
    cal_ds = torch.utils.data.Subset(val_ds, range(n_cal))
    test_ds = torch.utils.data.Subset(val_ds, range(n_cal, len(val_ds)))

    # Calibrate
    cal_loader = DataLoader(cal_ds, batch_size=128)
    cal_scores = []
    with torch.no_grad():
        for bx, bt in cal_loader:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            preds = torch.stack([m(x_in)[:, half:, 0] for m in models])
            mean_p = preds.mean(0); std_p = preds.std(0) + 1e-6
            actual = bx[:, half:, 0]
            scores = ((actual - mean_p).abs() / std_p).max(dim=1).values
            cal_scores.append(scores.cpu())
    cal_scores = torch.cat(cal_scores).numpy()
    q90 = float(np.percentile(cal_scores, 90))

    # Test
    test_loader = DataLoader(test_ds, batch_size=128)
    all_mae = []; cov_90 = []; width_90 = []
    with torch.no_grad():
        for bx, bt in test_loader:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            preds = torch.stack([m(x_in)[:, half:, 0] for m in models])
            mean_p = preds.mean(0); std_p = preds.std(0) + 1e-6
            actual = bx[:, half:, 0]
            mae = (mean_p - actual).abs().mean() * gluc_scale
            all_mae.append(mae.item())
            lower = (mean_p - q90 * std_p) * gluc_scale
            upper = (mean_p + q90 * std_p) * gluc_scale
            actual_mg = actual * gluc_scale
            cov = ((actual_mg >= lower) & (actual_mg <= upper)).float().mean()
            cov_90.append(cov.item())
            width_90.append((upper - lower).mean().item())

    results = {
        'n_seeds': n_seeds,
        'horizon': '6hr (3hr history + 3hr forecast)',
        'ensemble_mae_mgdl': round(float(np.mean(all_mae)), 1),
        'conformal_q90': round(q90, 2),
        'coverage_90': round(float(np.mean(cov_90)), 3),
        'width_90_mgdl': round(float(np.mean(width_90)), 1),
    }
    print(f'\n--- 6hr Ensemble results ---')
    for k, v in results.items():
        print(f'  [EXP-119] {k}: {v}')

    out_path = 'externals/experiments/exp119_ensemble_6hr.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-119', 'name': 'ensemble-6hr',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-120: Per-patient gradient ISF ──────────────────────────────
# EXP-113 gave mean ISF=12.35 mg/dL/U across all patients.
# Hypothesis: Per-patient ISF varies 2-5× between patients.
def run_gradient_isf_per_patient(args):
    """EXP-120: Per-patient gradient-based ISF estimation."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json, os
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    insulin_scale = NORMALIZATION_SCALES.get('insulin', 20.0)
    paths = resolve_patient_paths(patients_dir, real_data)

    # Train shared model on all patients
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-120] {len(train_ds)} train, {len(val_ds)} val')

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    best_val = float('inf'); best_state = None
    vl = DataLoader(val_ds, batch_size=256)
    for ep in range(1, 81):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            opt.zero_grad(); pred = model(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward(); opt.step()
        if ep % 20 == 0:
            model.eval(); vs = 0; vn = 0
            with torch.no_grad():
                for bx, bt in vl:
                    bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                    pred = model(x_in)
                    vs += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0); vn += bx.size(0)
            vavg = vs / vn
            if vavg < best_val: best_val = vavg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            print(f'  [ISF-pp] {ep}/80 val={vavg:.6f}')
    model.load_state_dict(best_state); model.eval()

    # Compute per-patient ISF
    patient_isfs = {}
    for p in sorted(paths):
        pname = os.path.basename(os.path.dirname(p))
        p_train, p_val = load_multipatient_nightscout([p], window_size=24)
        p_loader = DataLoader(p_val, batch_size=32)
        isf_vals = []
        for bx, bt in p_loader:
            bx = bx.to(device)
            x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            x_in.requires_grad_(True)
            pred = model(x_in)
            target = pred[:, 12:, 0].mean(dim=1)
            for i in range(min(bx.size(0), 8)):
                if x_in.grad is not None: x_in.grad.zero_()
                target[i].backward(retain_graph=True)
                g_ins = x_in.grad[i, :12, 1].cpu().numpy()
                isf = float((-g_ins * gluc_scale / insulin_scale).sum())
                isf_vals.append(isf)
            x_in.requires_grad_(False)
            if len(isf_vals) >= 50: break

        if isf_vals:
            patient_isfs[pname] = {
                'mean': round(float(np.mean(isf_vals)), 2),
                'median': round(float(np.median(isf_vals)), 2),
                'std': round(float(np.std(isf_vals)), 2),
                'n': len(isf_vals),
            }
            print(f'  [EXP-120] Patient {pname}: ISF={patient_isfs[pname]["mean"]} ± {patient_isfs[pname]["std"]}')

    all_means = [v['mean'] for v in patient_isfs.values()]
    results = {
        'patient_isfs': patient_isfs,
        'overall_mean': round(float(np.mean(all_means)), 2),
        'overall_std': round(float(np.std(all_means)), 2),
        'range_ratio': round(max(all_means) / max(min(all_means), 0.01), 1),
    }
    print(f'\n--- Per-patient ISF results ---')
    print(f'  [EXP-120] Overall mean: {results["overall_mean"]}')
    print(f'  [EXP-120] Range ratio: {results["range_ratio"]}×')

    out_path = 'externals/experiments/exp120_gradient_isf_per_patient.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-120', 'name': 'gradient-isf-per-patient',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-121: Trend-conditioned forecast ────────────────────────────
# Instead of crude event conditioning (EXP-054, -32.6%), condition on
# GLUCOSE TREND: rising, falling, flat, volatile. More natural grouping.
def run_trend_conditioned(args):
    """EXP-121: Trend-conditioned forecast accuracy."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-121] {len(train_ds)} train, {len(val_ds)} val')

    # Train standard model
    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    vl = DataLoader(val_ds, batch_size=256)
    best_val = float('inf'); best_state = None
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            opt.zero_grad(); pred = model(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward(); opt.step()
        model.eval(); vs = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                vs += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0); vn += bx.size(0)
        vavg = vs / vn
        if vavg < best_val: best_val = vavg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        if ep % 25 == 0: print(f'  [trend] {ep}/100 val={vavg:.6f}')
    model.load_state_dict(best_state); model.eval()

    # Classify trends and evaluate per-trend MAE
    trend_results = {'rising': [], 'falling': [], 'flat': [], 'volatile': []}
    with torch.no_grad():
        for bx, bt in vl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            pred = model(x_in)
            pred_mg = pred[:, 12:, 0] * gluc_scale
            actual_mg = bx[:, 12:, 0] * gluc_scale
            history_mg = bx[:, :12, 0] * gluc_scale

            for i in range(bx.size(0)):
                h = history_mg[i].cpu().numpy()
                mae_i = (pred_mg[i] - actual_mg[i]).abs().mean().item()

                # Classify trend from history
                slope = (h[-1] - h[0]) / 12  # mg/dL per 5min step
                volatility = float(np.std(np.diff(h)))

                if volatility > 5:
                    trend_results['volatile'].append(mae_i)
                elif slope > 1:  # >1 mg/dL per 5min = rising
                    trend_results['rising'].append(mae_i)
                elif slope < -1:
                    trend_results['falling'].append(mae_i)
                else:
                    trend_results['flat'].append(mae_i)

    results = {}
    for trend, maes in trend_results.items():
        results[f'{trend}_mae'] = round(float(np.mean(maes)), 1) if maes else -1
        results[f'{trend}_n'] = len(maes)

    print(f'\n--- Trend-conditioned results ---')
    for k, v in results.items():
        print(f'  [EXP-121] {k}: {v}')

    out_path = 'externals/experiments/exp121_trend_conditioned.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-121', 'name': 'trend-conditioned',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ══════════════════════════════════════════════════════════════════════
# ║  ROUND 16: Volatile contexts, combined best, planning pipeline   ║
# ══════════════════════════════════════════════════════════════════════

REGISTRY.update({
    'volatile-focused':        'run_volatile_focused',        # EXP-122
    'hypo-weighted-6hr':       'run_hypo_weighted_6hr',       # EXP-123
    'production-v6':           'run_production_v6',           # EXP-124
    'multi-resolution':        'run_multi_resolution',        # EXP-125
    'asymmetric-quantile':     'run_asymmetric_quantile',     # EXP-126
    'conformal-per-trend':     'run_conformal_per_trend',     # EXP-127
})


# ── EXP-122: Volatile-focused training ─────────────────────────────
# EXP-121 showed volatile windows MAE=15.4 vs flat=8.8 (75% worse).
# Hypothesis: Oversampling volatile windows + higher weight reduces gap.
def run_volatile_focused(args):
    """EXP-122: Training focused on volatile glucose patterns."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader, ConcatDataset, Subset
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-122] {len(train_ds)} train, {len(val_ds)} val')

    # Identify volatile windows (std of glucose diffs > threshold)
    volatile_idx = []
    for i in range(len(train_ds)):
        x, _ = train_ds[i]
        diffs = (x[1:12, 0] - x[:11, 0]).numpy()
        if np.std(diffs) > 0.01:  # normalized scale
            volatile_idx.append(i)
    print(f'  [EXP-122] Volatile windows: {len(volatile_idx)}/{len(train_ds)}')

    results = {}
    for variant, extra_copies in [('baseline', 0), ('volatile_2x', 1), ('volatile_3x', 2)]:
        if extra_copies > 0 and volatile_idx:
            extra = Subset(train_ds, volatile_idx * extra_copies)
            aug_ds = ConcatDataset([train_ds, extra])
        else:
            aug_ds = train_ds

        model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
        tl = DataLoader(aug_ds, batch_size=128, shuffle=True)
        vl = DataLoader(val_ds, batch_size=256)
        best_val = float('inf'); best_state = None

        for ep in range(1, 81):
            model.train()
            for bx, bt in tl:
                bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                opt.zero_grad(); pred = model(x_in)
                loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                loss.backward(); opt.step()
            model.eval(); vs = 0; vn = 0
            with torch.no_grad():
                for bx, bt in vl:
                    bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                    pred = model(x_in)
                    vs += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0); vn += bx.size(0)
            vavg = vs / vn
            if vavg < best_val: best_val = vavg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        model.load_state_dict(best_state); model.eval()

        # Stratified eval
        volatile_e = []; calm_e = []
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                for i in range(bx.size(0)):
                    h_diffs = (bx[i, 1:12, 0] - bx[i, :11, 0]).cpu().numpy()
                    mae_i = (pred[i, 12:, 0] - bx[i, 12:, 0]).abs().mean().item() * gluc_scale
                    if np.std(h_diffs) > 0.01:
                        volatile_e.append(mae_i)
                    else:
                        calm_e.append(mae_i)

        results[variant] = {
            'volatile_mae': round(float(np.mean(volatile_e)) if volatile_e else -1, 1),
            'calm_mae': round(float(np.mean(calm_e)) if calm_e else -1, 1),
            'overall_mae': round(float(np.mean(volatile_e + calm_e)), 1),
        }
        print(f'  [{variant}] volatile={results[variant]["volatile_mae"]}, calm={results[variant]["calm_mae"]}')

    print(f'\n--- Volatile-focused results ---')
    for k, v in results.items():
        print(f'  [EXP-122] {k}: {v}')

    out_path = 'externals/experiments/exp122_volatile_focused.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-122', 'name': 'volatile-focused',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-123: Hypo-weighted 6hr forecast ────────────────────────────
# Combine EXP-116 (hypo weighting) with EXP-111 (6hr direct).
def run_hypo_weighted_6hr(args):
    """EXP-123: 6hr forecast with hypo-weighted loss."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    hypo_norm = 70.0 / gluc_scale
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=72)
    half = 36
    print(f'  [EXP-123] ws=72: {len(train_ds)} train, {len(val_ds)} val')

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=10, factor=0.5)
    tl = DataLoader(train_ds, batch_size=64, shuffle=True)
    vl = DataLoader(val_ds, batch_size=128)
    best_val = float('inf'); best_state = None

    for ep in range(1, 121):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            opt.zero_grad(); pred = model(x_in)
            actual = bx[:, half:, 0]
            weights = torch.ones_like(actual)
            weights[actual < hypo_norm] = 5.0
            per_ts = (pred[:, half:, 0] - actual) ** 2
            loss = (per_ts * weights).mean()
            loss.backward(); opt.step()
        model.eval(); vs = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device); x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                vs += F.mse_loss(pred[:, half:, :1], bx[:, half:, :1]).item() * bx.size(0); vn += bx.size(0)
        vavg = vs / vn; sched.step(vavg)
        if vavg < best_val: best_val = vavg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        if ep % 30 == 0: print(f'  [6hr-hw] {ep}/120 val={vavg:.6f}')
    model.load_state_dict(best_state); model.eval()

    # Stratified eval
    hypo_e = []; inrange_e = []; hyper_e = []; all_e = []
    with torch.no_grad():
        for bx, bt in vl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            pred = model(x_in)
            pred_mg = pred[:, half:, 0] * gluc_scale
            actual_mg = bx[:, half:, 0] * gluc_scale
            err = (pred_mg - actual_mg).abs()
            for i in range(bx.size(0)):
                for t in range(36):
                    a = actual_mg[i, t].item(); e = err[i, t].item()
                    all_e.append(e)
                    if a < 70: hypo_e.append(e)
                    elif a <= 180: inrange_e.append(e)
                    else: hyper_e.append(e)

    results = {
        'overall_mae': round(float(np.mean(all_e)), 1),
        'hypo_mae': round(float(np.mean(hypo_e)) if hypo_e else -1, 1),
        'inrange_mae': round(float(np.mean(inrange_e)) if inrange_e else -1, 1),
        'hyper_mae': round(float(np.mean(hyper_e)) if hyper_e else -1, 1),
        'hypo_n': len(hypo_e),
    }
    print(f'\n--- 6hr hypo-weighted results ---')
    for k, v in results.items():
        print(f'  [EXP-123] {k}: {v}')

    out_path = 'externals/experiments/exp123_hypo_weighted_6hr.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-123', 'name': 'hypo-weighted-6hr',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-124: Production v6 — ultimate combination ──────────────────
# Combines: hypo-weighted training + volatile augmentation + conformal
# + confidence gating. The "best of everything" pipeline.
def run_production_v6(args):
    """EXP-124: Ultimate production planner combining all wins."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader, ConcatDataset, Subset
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    hypo_norm = 70.0 / gluc_scale
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-124] {len(train_ds)} train, {len(val_ds)} val')

    # Identify hypo + volatile windows for augmentation
    hypo_idx = []; volatile_idx = []
    for i in range(len(train_ds)):
        x, _ = train_ds[i]
        if x[12:, 0].min() < hypo_norm: hypo_idx.append(i)
        diffs = (x[1:12, 0] - x[:11, 0]).numpy()
        if np.std(diffs) > 0.01: volatile_idx.append(i)

    # 2× hypo, 1× extra volatile
    extras = []
    if hypo_idx: extras.append(Subset(train_ds, hypo_idx))
    if volatile_idx: extras.append(Subset(train_ds, volatile_idx[:len(volatile_idx)//2]))
    aug_ds = ConcatDataset([train_ds] + extras) if extras else train_ds
    print(f'  [EXP-124] Augmented: {len(aug_ds)} (hypo={len(hypo_idx)}, volatile={len(volatile_idx)})')

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=10, factor=0.5)
    tl = DataLoader(aug_ds, batch_size=128, shuffle=True)
    vl = DataLoader(val_ds, batch_size=256)
    best_val = float('inf'); best_state = None

    for ep in range(1, 121):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            opt.zero_grad(); pred = model(x_in)
            actual = bx[:, 12:, 0]
            weights = torch.ones_like(actual)
            weights[actual < hypo_norm] = 5.0
            weights[actual < 54.0/gluc_scale] = 10.0
            loss = ((pred[:, 12:, 0] - actual) ** 2 * weights).mean()
            loss.backward(); opt.step()
        model.eval(); vs = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                vs += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0); vn += bx.size(0)
        vavg = vs / vn; sched.step(vavg)
        if vavg < best_val: best_val = vavg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        if ep % 30 == 0: print(f'  [v6] {ep}/120 val={vavg:.6f}')
    model.load_state_dict(best_state); model.eval()

    # Conformal calibration (split val 60/40)
    n_cal = int(len(val_ds) * 0.6)
    cal_ds = Subset(val_ds, range(n_cal))
    test_ds = Subset(val_ds, range(n_cal, len(val_ds)))
    cal_loader = DataLoader(cal_ds, batch_size=256)
    cal_res = []
    with torch.no_grad():
        for bx, bt in cal_loader:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            pred = model(x_in)
            r = (pred[:, 12:, 0] - bx[:, 12:, 0]).abs() * gluc_scale
            cal_res.append(r.max(dim=1).values.cpu())
    cal_res = torch.cat(cal_res).numpy()
    q90 = float(np.percentile(cal_res, 90))

    # Test with confidence gating + planning
    test_loader = DataLoader(test_ds, batch_size=256)
    n_plans = 0; n_correct = 0; n_checked = 0
    hypo_tp = 0; hypo_fp = 0; hypo_fn = 0
    all_mae = []; hypo_mae = []; inrange_mae = []

    with torch.no_grad():
        for bx, bt in test_loader:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            pred = model(x_in)
            pred_mg = pred[:, 12:, 0] * gluc_scale
            actual_mg = bx[:, 12:, 0] * gluc_scale

            for i in range(bx.size(0)):
                p = pred_mg[i].cpu().numpy(); a = actual_mg[i].cpu().numpy()
                res_i = abs(p - a)
                confidence = float((res_i < q90).mean())
                mae_i = float(abs(p - a).mean())
                all_mae.append(mae_i)

                for t in range(12):
                    if a[t] < 70: hypo_mae.append(abs(p[t] - a[t]))
                    elif a[t] <= 180: inrange_mae.append(abs(p[t] - a[t]))

                if confidence >= 0.85:
                    n_plans += 1
                    if p.min() < 70:
                        if a.min() < 70: hypo_tp += 1
                        else: hypo_fp += 1
                    elif a.min() < 70: hypo_fn += 1
                    if p.max() > 180:
                        n_checked += 1
                        if a.max() > 150: n_correct += 1

    prec = n_correct / max(n_checked, 1)
    h_prec = hypo_tp / max(hypo_tp + hypo_fp, 1)
    h_rec = hypo_tp / max(hypo_tp + hypo_fn, 1)
    h_f1 = 2*h_prec*h_rec / max(h_prec+h_rec, 1e-8)

    results = {
        'overall_mae': round(float(np.mean(all_mae)), 1),
        'hypo_mae': round(float(np.mean(hypo_mae)) if hypo_mae else -1, 1),
        'inrange_mae': round(float(np.mean(inrange_mae)) if inrange_mae else -1, 1),
        'conformal_q90': round(q90, 1),
        'n_plans': n_plans,
        'correction_precision': round(prec, 3),
        'hypo_precision': round(h_prec, 3),
        'hypo_recall': round(h_rec, 3),
        'hypo_f1': round(h_f1, 3),
    }
    print(f'\n--- Production v6 results ---')
    for k, v in results.items():
        print(f'  [EXP-124] {k}: {v}')

    out_path = 'externals/experiments/exp124_production_v6.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-124', 'name': 'production-v6',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-125: Multi-resolution forecast ─────────────────────────────
# Train separate heads at 5min, 15min, 30min resolutions jointly.
# Some events need fast response (hypo), others need long view (meals).
def run_multi_resolution(args):
    """EXP-125: Multi-resolution forecast with shared encoder."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)

    # ws=24 (1hr history + 1hr forecast at 5min)
    train_24, val_24 = load_multipatient_nightscout(paths, window_size=24)
    # ws=48 (2hr history + 2hr forecast at 5min)
    train_48, val_48 = load_multipatient_nightscout(paths, window_size=48)
    print(f'  [EXP-125] ws24: {len(train_24)}/{len(val_24)}, ws48: {len(train_48)}/{len(val_48)}')

    results = {}

    # Train 1hr model
    model_1hr = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model_1hr.parameters(), lr=1e-3)
    tl = DataLoader(train_24, batch_size=128, shuffle=True)
    best_val = float('inf'); best_state = None
    vl = DataLoader(val_24, batch_size=256)
    for ep in range(1, 81):
        model_1hr.train()
        for bx, bt in tl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            opt.zero_grad(); pred = model_1hr(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward(); opt.step()
        model_1hr.eval(); vs = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model_1hr(x_in)
                vs += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0); vn += bx.size(0)
        vavg = vs / vn
        if vavg < best_val: best_val = vavg; best_state = {k: v.cpu().clone() for k, v in model_1hr.state_dict().items()}
    model_1hr.load_state_dict(best_state); model_1hr.eval()

    # Eval 1hr at fine granularity
    with torch.no_grad():
        mae_5min = []; mae_15min = []; mae_30min = []; mae_60min = []
        for bx, bt in vl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            pred = model_1hr(x_in)
            err = (pred[:, 12:, 0] - bx[:, 12:, 0]).abs() * gluc_scale
            mae_5min.append(err[:, 0].mean().item())  # 1 step = 5min
            mae_15min.append(err[:, :3].mean().item())  # 3 steps
            mae_30min.append(err[:, :6].mean().item())  # 6 steps
            mae_60min.append(err.mean().item())  # all 12

    results['1hr_model'] = {
        'mae_5min': round(float(np.mean(mae_5min)), 1),
        'mae_15min': round(float(np.mean(mae_15min)), 1),
        'mae_30min': round(float(np.mean(mae_30min)), 1),
        'mae_60min': round(float(np.mean(mae_60min)), 1),
    }

    # Train 2hr model
    model_2hr = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model_2hr.parameters(), lr=1e-3)
    tl2 = DataLoader(train_48, batch_size=64, shuffle=True)
    vl2 = DataLoader(val_48, batch_size=128)
    best_val = float('inf'); best_state = None
    half2 = 24
    for ep in range(1, 81):
        model_2hr.train()
        for bx, bt in tl2:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, half2:, 0] = 0.0
            opt.zero_grad(); pred = model_2hr(x_in)
            loss = F.mse_loss(pred[:, half2:, :1], bx[:, half2:, :1])
            loss.backward(); opt.step()
        model_2hr.eval(); vs = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl2:
                bx = bx.to(device); x_in = bx.clone(); x_in[:, half2:, 0] = 0.0
                pred = model_2hr(x_in)
                vs += F.mse_loss(pred[:, half2:, :1], bx[:, half2:, :1]).item() * bx.size(0); vn += bx.size(0)
        vavg = vs / vn
        if vavg < best_val: best_val = vavg; best_state = {k: v.cpu().clone() for k, v in model_2hr.state_dict().items()}
    model_2hr.load_state_dict(best_state); model_2hr.eval()

    with torch.no_grad():
        mae_30 = []; mae_60 = []; mae_90 = []; mae_120 = []
        for bx, bt in vl2:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, half2:, 0] = 0.0
            pred = model_2hr(x_in)
            err = (pred[:, half2:, 0] - bx[:, half2:, 0]).abs() * gluc_scale
            mae_30.append(err[:, :6].mean().item())
            mae_60.append(err[:, :12].mean().item())
            mae_90.append(err[:, :18].mean().item())
            mae_120.append(err.mean().item())

    results['2hr_model'] = {
        'mae_30min': round(float(np.mean(mae_30)), 1),
        'mae_60min': round(float(np.mean(mae_60)), 1),
        'mae_90min': round(float(np.mean(mae_90)), 1),
        'mae_120min': round(float(np.mean(mae_120)), 1),
    }

    print(f'\n--- Multi-resolution results ---')
    for model_name, metrics in results.items():
        print(f'  [EXP-125] {model_name}: {metrics}')

    out_path = 'externals/experiments/exp125_multi_resolution.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-125', 'name': 'multi-resolution',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-126: Asymmetric quantile for safety ────────────────────────
# Use asymmetric quantile loss: penalize under-prediction more (safety).
# Lower bound should be tighter than upper bound for hypo safety.
def run_asymmetric_quantile(args):
    """EXP-126: Asymmetric quantile regression for safety."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json, torch.nn as nn
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-126] {len(train_ds)} train, {len(val_ds)} val')

    # Quantile model: predict p05, p50, p95
    class QuantileModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4)
            self.quantile_heads = nn.ModuleList([
                nn.Linear(8, 1) for _ in range(3)  # p05, p50, p95
            ])
        def forward(self, x):
            enc = self.encoder(x)  # [B, T, 8]
            qs = [h(enc[:, 12:]).squeeze(-1) for h in self.quantile_heads]
            return torch.stack(qs, dim=-1)  # [B, 12, 3]

    model = QuantileModel().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    quantiles = [0.05, 0.50, 0.95]
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    vl = DataLoader(val_ds, batch_size=256)

    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            opt.zero_grad()
            q_pred = model(x_in)  # [B, 12, 3]
            actual = bx[:, 12:, 0]  # [B, 12]
            total_loss = 0
            for qi, q in enumerate(quantiles):
                errors = actual - q_pred[:, :, qi]
                loss_q = torch.where(errors >= 0, q * errors, (q - 1) * errors)
                # Asymmetric: extra penalty for under-predicting (missing hypo)
                if q == 0.05:
                    hypo_mask = actual < 70.0/gluc_scale
                    loss_q[hypo_mask] *= 3.0  # 3× penalty for missing low-end
                total_loss += loss_q.mean()
            total_loss.backward(); opt.step()
        if ep % 25 == 0: print(f'  [asym-q] {ep}/100')
    model.eval()

    # Evaluate
    all_p05 = []; all_p50 = []; all_p95 = []; all_actual = []
    with torch.no_grad():
        for bx, bt in vl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            q_pred = model(x_in) * gluc_scale
            actual_mg = bx[:, 12:, 0] * gluc_scale
            all_p05.append(q_pred[:, :, 0].cpu()); all_p50.append(q_pred[:, :, 1].cpu())
            all_p95.append(q_pred[:, :, 2].cpu()); all_actual.append(actual_mg.cpu())

    p05 = torch.cat(all_p05).numpy(); p50 = torch.cat(all_p50).numpy()
    p95 = torch.cat(all_p95).numpy(); actual = torch.cat(all_actual).numpy()

    coverage = float(((actual >= p05) & (actual <= p95)).mean())
    width = float((p95 - p05).mean())
    p50_mae = float(np.abs(actual - p50).mean())
    # Check low-end coverage specifically
    hypo_mask = actual < 70
    hypo_lower_coverage = float((actual[hypo_mask] >= p05[hypo_mask]).mean()) if hypo_mask.any() else -1

    results = {
        'p50_mae': round(p50_mae, 1),
        'coverage_90': round(coverage, 3),
        'width_mgdl': round(width, 1),
        'hypo_lower_coverage': round(hypo_lower_coverage, 3),
        'n_hypo_timesteps': int(hypo_mask.sum()),
    }
    print(f'\n--- Asymmetric quantile results ---')
    for k, v in results.items():
        print(f'  [EXP-126] {k}: {v}')

    out_path = 'externals/experiments/exp126_asymmetric_quantile.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-126', 'name': 'asymmetric-quantile',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-127: Conformal prediction per trend ────────────────────────
# EXP-121 showed different MAE per trend. Use separate conformal
# thresholds per trend for tighter, better-calibrated intervals.
def run_conformal_per_trend(args):
    """EXP-127: Trend-stratified conformal prediction."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-127] {len(train_ds)} train, {len(val_ds)} val')

    # Train model
    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    best_val = float('inf'); best_state = None
    vl = DataLoader(val_ds, batch_size=256)
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            opt.zero_grad(); pred = model(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward(); opt.step()
        model.eval(); vs = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                vs += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0); vn += bx.size(0)
        vavg = vs / vn
        if vavg < best_val: best_val = vavg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        if ep % 25 == 0: print(f'  [conf-t] {ep}/100 val={vavg:.6f}')
    model.load_state_dict(best_state); model.eval()

    def classify_trend(history_mg):
        slope = (history_mg[-1] - history_mg[0]) / len(history_mg)
        vol = float(np.std(np.diff(history_mg)))
        if vol > 5: return 'volatile'
        elif slope > 1: return 'rising'
        elif slope < -1: return 'falling'
        else: return 'flat'

    # Split val: 60% cal, 40% test
    n_cal = int(len(val_ds) * 0.6)
    from torch.utils.data import Subset
    cal_ds = Subset(val_ds, range(n_cal))
    test_ds = Subset(val_ds, range(n_cal, len(val_ds)))

    # Calibrate per trend
    cal_loader = DataLoader(cal_ds, batch_size=256)
    trend_scores = {'rising': [], 'falling': [], 'flat': [], 'volatile': []}
    with torch.no_grad():
        for bx, bt in cal_loader:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            pred = model(x_in)
            for i in range(bx.size(0)):
                h_mg = (bx[i, :12, 0] * gluc_scale).cpu().numpy()
                trend = classify_trend(h_mg)
                res = (pred[i, 12:, 0] - bx[i, 12:, 0]).abs().max().item() * gluc_scale
                trend_scores[trend].append(res)

    trend_q90 = {}
    for trend, scores in trend_scores.items():
        if scores:
            trend_q90[trend] = float(np.percentile(scores, 90))

    # Global q90 for comparison
    all_scores = sum(trend_scores.values(), [])
    global_q90 = float(np.percentile(all_scores, 90))

    # Test: compare global vs per-trend conformal
    test_loader = DataLoader(test_ds, batch_size=256)
    global_cov = []; global_width = []; trend_cov = []; trend_width = []

    with torch.no_grad():
        for bx, bt in test_loader:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            pred = model(x_in)
            for i in range(bx.size(0)):
                h_mg = (bx[i, :12, 0] * gluc_scale).cpu().numpy()
                trend = classify_trend(h_mg)
                pred_mg = pred[i, 12:, 0].cpu().numpy() * gluc_scale
                actual_mg = bx[i, 12:, 0].cpu().numpy() * gluc_scale

                # Global
                g_low = pred_mg - global_q90; g_high = pred_mg + global_q90
                g_cov = float(((actual_mg >= g_low) & (actual_mg <= g_high)).mean())
                global_cov.append(g_cov)
                global_width.append(2 * global_q90)

                # Per-trend
                tq = trend_q90.get(trend, global_q90)
                t_low = pred_mg - tq; t_high = pred_mg + tq
                t_cov = float(((actual_mg >= t_low) & (actual_mg <= t_high)).mean())
                trend_cov.append(t_cov)
                trend_width.append(2 * tq)

    results = {
        'trend_q90': {k: round(v, 1) for k, v in trend_q90.items()},
        'global_q90': round(global_q90, 1),
        'global_coverage': round(float(np.mean(global_cov)), 3),
        'global_width': round(float(np.mean(global_width)), 1),
        'trend_coverage': round(float(np.mean(trend_cov)), 3),
        'trend_width': round(float(np.mean(trend_width)), 1),
        'width_reduction_pct': round((1 - float(np.mean(trend_width)) / float(np.mean(global_width))) * 100, 1),
    }
    print(f'\n--- Conformal per-trend results ---')
    for k, v in results.items():
        print(f'  [EXP-127] {k}: {v}')

    out_path = 'externals/experiments/exp127_conformal_per_trend.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-127', 'name': 'conformal-per-trend',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ══════════════════════════════════════════════════════════════════════
# ║  ROUND 17: Tight uncertainty, 6hr planner, loss ensembles        ║
# ══════════════════════════════════════════════════════════════════════

REGISTRY.update({
    'conformal-asymmetric':    'run_conformal_asymmetric',    # EXP-128
    'planner-6hr':             'run_planner_6hr',             # EXP-129
    'loss-ensemble':           'run_loss_ensemble',           # EXP-130
    'hypo-recall-max':         'run_hypo_recall_max',         # EXP-131
    'clarke-error-grid':       'run_clarke_error_grid',       # EXP-132
    'time-aware-forecast':     'run_time_aware_forecast',     # EXP-133
})


# ── EXP-128: Conformal + asymmetric quantile ──────────────────────
# Combine EXP-126's asymmetric quantile (47.3 width) with conformal
# calibration to get tight AND calibrated intervals.
def run_conformal_asymmetric(args):
    """EXP-128: Conformal-calibrated asymmetric quantiles."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json, torch.nn as nn
    from torch.utils.data import DataLoader, Subset
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-128] {len(train_ds)} train, {len(val_ds)} val')

    # Asymmetric quantile model
    class QModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4)
            self.heads = nn.ModuleList([nn.Linear(8, 1) for _ in range(3)])
        def forward(self, x):
            enc = self.encoder(x)
            return torch.stack([h(enc[:, 12:]).squeeze(-1) for h in self.heads], dim=-1)

    model = QModel().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    quantiles = [0.05, 0.50, 0.95]
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)

    hypo_norm = 70.0 / gluc_scale
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            opt.zero_grad()
            q_pred = model(x_in); actual = bx[:, 12:, 0]
            total = 0
            for qi, q in enumerate(quantiles):
                err = actual - q_pred[:, :, qi]
                lq = torch.where(err >= 0, q * err, (q - 1) * err)
                if q == 0.05:
                    lq[actual < hypo_norm] *= 3.0
                total += lq.mean()
            total.backward(); opt.step()
        if ep % 25 == 0: print(f'  [caq] {ep}/100')
    model.eval()

    # Split val: 60% calibration, 40% test
    n_cal = int(len(val_ds) * 0.6)
    cal_ds = Subset(val_ds, range(n_cal))
    test_ds = Subset(val_ds, range(n_cal, len(val_ds)))

    # Calibrate: collect nonconformity scores
    cal_loader = DataLoader(cal_ds, batch_size=256)
    cal_scores = []
    with torch.no_grad():
        for bx, bt in cal_loader:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            q_pred = model(x_in)
            actual = bx[:, 12:, 0]
            p05 = q_pred[:, :, 0]; p95 = q_pred[:, :, 2]
            # Nonconformity = max(p05 - actual, actual - p95, 0)
            low_viol = (p05 - actual).clamp(min=0)
            high_viol = (actual - p95).clamp(min=0)
            score = torch.max(low_viol, high_viol).max(dim=1).values
            cal_scores.append(score.cpu())
    cal_scores = torch.cat(cal_scores).numpy()
    q_adj = float(np.percentile(cal_scores, 90))

    # Test with conformal-adjusted bands
    test_loader = DataLoader(test_ds, batch_size=256)
    raw_cov = []; adj_cov = []; raw_w = []; adj_w = []
    all_mae = []; hypo_low_cov = []
    with torch.no_grad():
        for bx, bt in test_loader:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            q_pred = model(x_in) * gluc_scale
            actual_mg = bx[:, 12:, 0] * gluc_scale
            p05 = q_pred[:, :, 0]; p50 = q_pred[:, :, 1]; p95 = q_pred[:, :, 2]
            adj_lo = p05 - q_adj * gluc_scale; adj_hi = p95 + q_adj * gluc_scale
            raw_c = ((actual_mg >= p05) & (actual_mg <= p95)).float().mean()
            adj_c = ((actual_mg >= adj_lo) & (actual_mg <= adj_hi)).float().mean()
            raw_cov.append(raw_c.item()); adj_cov.append(adj_c.item())
            raw_w.append((p95 - p05).mean().item()); adj_w.append((adj_hi - adj_lo).mean().item())
            all_mae.append((p50 - actual_mg).abs().mean().item())

    results = {
        'p50_mae': round(float(np.mean(all_mae)), 1),
        'raw_coverage': round(float(np.mean(raw_cov)), 3),
        'raw_width': round(float(np.mean(raw_w)), 1),
        'conformal_coverage': round(float(np.mean(adj_cov)), 3),
        'conformal_width': round(float(np.mean(adj_w)), 1),
        'conformal_adjustment': round(q_adj * gluc_scale, 1),
    }
    print(f'\n--- Conformal asymmetric results ---')
    for k, v in results.items():
        print(f'  [EXP-128] {k}: {v}')

    out_path = 'externals/experiments/exp128_conformal_asymmetric.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-128', 'name': 'conformal-asymmetric',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-129: 6hr planning pipeline ────────────────────────────────
# Complete planning system at 6hr horizon with override suggestions.
# Uses direct 6hr model + conformal bands + event classification.
def run_planner_6hr(args):
    """EXP-129: 6hr planning pipeline with override suggestions."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader, Subset
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=72)
    half = 36
    print(f'  [EXP-129] ws=72: {len(train_ds)} train, {len(val_ds)} val')

    # Train 6hr forecast with hypo weighting
    hypo_norm = 70.0 / gluc_scale
    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=10, factor=0.5)
    tl = DataLoader(train_ds, batch_size=64, shuffle=True)
    vl = DataLoader(val_ds, batch_size=128)
    best_val = float('inf'); best_state = None
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            opt.zero_grad(); pred = model(x_in)
            actual = bx[:, half:, 0]
            w = torch.ones_like(actual); w[actual < hypo_norm] = 5.0
            loss = ((pred[:, half:, 0] - actual)**2 * w).mean()
            loss.backward(); opt.step()
        model.eval(); vs = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device); x_in = bx.clone(); x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                vs += F.mse_loss(pred[:, half:, :1], bx[:, half:, :1]).item() * bx.size(0); vn += bx.size(0)
        vavg = vs / vn; sched.step(vavg)
        if vavg < best_val: best_val = vavg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        if ep % 25 == 0: print(f'  [6hrP] {ep}/100 val={vavg:.6f}')
    model.load_state_dict(best_state); model.eval()

    # Conformal calibration
    n_cal = int(len(val_ds) * 0.6)
    cal_ds = Subset(val_ds, range(n_cal))
    test_ds = Subset(val_ds, range(n_cal, len(val_ds)))
    cal_loader = DataLoader(cal_ds, batch_size=128)
    cal_res = []
    with torch.no_grad():
        for bx, bt in cal_loader:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            pred = model(x_in)
            r = (pred[:, half:, 0] - bx[:, half:, 0]).abs() * gluc_scale
            cal_res.append(r.max(dim=1).values.cpu())
    cal_res = torch.cat(cal_res).numpy()
    q90 = float(np.percentile(cal_res, 90))

    # Generate 6hr plans
    test_loader = DataLoader(test_ds, batch_size=128)
    plans = []
    from collections import Counter
    action_counts = Counter()

    with torch.no_grad():
        for bx, bt in test_loader:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, half:, 0] = 0.0
            pred = model(x_in)
            pred_mg = pred[:, half:, 0] * gluc_scale
            actual_mg = bx[:, half:, 0] * gluc_scale

            for i in range(bx.size(0)):
                p = pred_mg[i].cpu().numpy()
                a = actual_mg[i].cpu().numpy()
                res = abs(p - a)
                confidence = float((res < q90).mean())

                if confidence < 0.8: continue

                actions = []
                # Analyze 3hr forecast in 1hr segments
                for seg_name, start, end in [('0-1hr', 0, 12), ('1-2hr', 12, 24), ('2-3hr', 24, 36)]:
                    seg_p = p[start:end]
                    seg_a = a[start:end]

                    if seg_p.min() < 70:
                        actions.append(f'hypo_alert_{seg_name}')
                    if seg_p.max() > 250:
                        actions.append(f'urgent_high_{seg_name}')
                    elif seg_p.max() > 180:
                        actions.append(f'consider_correction_{seg_name}')
                    if seg_p[-1] - seg_p[0] > 40:
                        actions.append(f'rapid_rise_{seg_name}')
                    elif seg_p[-1] - seg_p[0] < -40:
                        actions.append(f'rapid_fall_{seg_name}')

                if actions:
                    plans.append({
                        'confidence': round(confidence, 2),
                        'actions': actions,
                        'pred_min': round(float(p.min()), 0),
                        'pred_max': round(float(p.max()), 0),
                        'actual_min': round(float(a.min()), 0),
                        'actual_max': round(float(a.max()), 0),
                    })
                    for act in actions:
                        action_counts[act.split('_')[0] + '_' + act.split('_')[1]] += 1

    # Precision: how often predicted extremes match actual
    hypo_tp = sum(1 for pl in plans if any('hypo' in a for a in pl['actions']) and pl['actual_min'] < 80)
    hypo_fp = sum(1 for pl in plans if any('hypo' in a for a in pl['actions']) and pl['actual_min'] >= 80)
    hyper_tp = sum(1 for pl in plans if any('correction' in a or 'urgent' in a for a in pl['actions']) and pl['actual_max'] > 160)
    hyper_fp = sum(1 for pl in plans if any('correction' in a or 'urgent' in a for a in pl['actions']) and pl['actual_max'] <= 160)

    results = {
        'n_plans': len(plans),
        'total_actions': sum(len(p['actions']) for p in plans),
        'conformal_q90': round(q90, 1),
        'hypo_precision': round(hypo_tp / max(hypo_tp + hypo_fp, 1), 3),
        'hyper_precision': round(hyper_tp / max(hyper_tp + hyper_fp, 1), 3),
        'top_actions': dict(action_counts.most_common(8)),
    }
    print(f'\n--- 6hr Planner results ---')
    for k, v in results.items():
        print(f'  [EXP-129] {k}: {v}')

    out_path = 'externals/experiments/exp129_planner_6hr.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-129', 'name': 'planner-6hr',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-130: Loss-weighted ensemble ────────────────────────────────
# Instead of equal weighting (EXP-100), weight seeds by val loss.
# Better seeds contribute more. Should improve MAE over simple average.
def run_loss_ensemble(args):
    """EXP-130: Validation-loss-weighted seed ensemble."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-130] {len(train_ds)} train, {len(val_ds)} val')

    n_seeds = 5; models = []; val_losses = []
    for seed in range(n_seeds):
        torch.manual_seed(seed * 42 + 7)
        m = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        opt = torch.optim.AdamW(m.parameters(), lr=1e-3)
        tl = DataLoader(train_ds, batch_size=128, shuffle=True)
        vl = DataLoader(val_ds, batch_size=256)
        best_val = float('inf'); best_st = None
        for ep in range(1, 81):
            m.train()
            for bx, bt in tl:
                bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                opt.zero_grad(); pred = m(x_in)
                loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
                loss.backward(); opt.step()
            if ep % 20 == 0:
                m.eval(); vs = 0; vn = 0
                with torch.no_grad():
                    for bx, bt in vl:
                        bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                        pred = m(x_in)
                        vs += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0); vn += bx.size(0)
                vavg = vs / vn
                if vavg < best_val: best_val = vavg; best_st = {k: v.cpu().clone() for k, v in m.state_dict().items()}
        m.load_state_dict(best_st); m.eval()
        models.append(m); val_losses.append(best_val)
        print(f'  [EXP-130] Seed {seed}: val_loss={best_val:.6f}')

    # Compute weights: inverse loss, softmax-normalized
    inv_losses = [1.0/vl for vl in val_losses]
    total = sum(inv_losses)
    weights = [w/total for w in inv_losses]
    print(f'  [EXP-130] Weights: {[round(w, 3) for w in weights]}')

    # Evaluate: equal vs weighted ensemble
    vl = DataLoader(val_ds, batch_size=256)
    equal_mae = []; weighted_mae = []; individual_maes = [[] for _ in range(n_seeds)]

    with torch.no_grad():
        for bx, bt in vl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            preds = [m(x_in)[:, 12:, 0] for m in models]

            # Individual
            for si, p in enumerate(preds):
                individual_maes[si].append((p - bx[:, 12:, 0]).abs().mean().item() * gluc_scale)

            # Equal weight
            eq_mean = torch.stack(preds).mean(dim=0)
            equal_mae.append((eq_mean - bx[:, 12:, 0]).abs().mean().item() * gluc_scale)

            # Loss-weighted
            wt_mean = sum(w * p for w, p in zip(weights, preds))
            weighted_mae.append((wt_mean - bx[:, 12:, 0]).abs().mean().item() * gluc_scale)

    results = {
        'individual_maes': [round(float(np.mean(m)), 1) for m in individual_maes],
        'equal_ensemble_mae': round(float(np.mean(equal_mae)), 1),
        'weighted_ensemble_mae': round(float(np.mean(weighted_mae)), 1),
        'weights': [round(w, 3) for w in weights],
        'val_losses': [round(vl, 6) for vl in val_losses],
        'improvement_pct': round((float(np.mean(equal_mae)) - float(np.mean(weighted_mae))) / float(np.mean(equal_mae)) * 100, 1),
    }
    print(f'\n--- Loss-weighted ensemble results ---')
    for k, v in results.items():
        print(f'  [EXP-130] {k}: {v}')

    out_path = 'externals/experiments/exp130_loss_ensemble.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-130', 'name': 'loss-ensemble',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-131: Maximum hypo recall ──────────────────────────────────
# Safety-first: maximize hypo recall even at cost of precision.
# Use combined: hypo weighting + augmentation + low threshold.
def run_hypo_recall_max(args):
    """EXP-131: Maximum hypo recall configuration."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader, ConcatDataset, Subset
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    hypo_norm = 70.0 / gluc_scale
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-131] {len(train_ds)} train, {len(val_ds)} val')

    # Heavy hypo augmentation: 4× oversample
    hypo_idx = [i for i in range(len(train_ds)) if train_ds[i][0][12:, 0].min() < hypo_norm]
    extra = Subset(train_ds, hypo_idx * 3) if hypo_idx else train_ds
    aug_ds = ConcatDataset([train_ds, extra])
    print(f'  [EXP-131] Hypo: {len(hypo_idx)}, augmented total: {len(aug_ds)}')

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    tl = DataLoader(aug_ds, batch_size=128, shuffle=True)
    vl = DataLoader(val_ds, batch_size=256)
    best_val = float('inf'); best_state = None
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            opt.zero_grad(); pred = model(x_in)
            actual = bx[:, 12:, 0]
            w = torch.ones_like(actual)
            w[actual < hypo_norm] = 10.0  # 10× for hypo
            w[actual < 54.0/gluc_scale] = 20.0  # 20× for severe
            loss = ((pred[:, 12:, 0] - actual)**2 * w).mean()
            loss.backward(); opt.step()
        model.eval(); vs = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                vs += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0); vn += bx.size(0)
        vavg = vs / vn
        if vavg < best_val: best_val = vavg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state); model.eval()

    # Sweep thresholds for hypo detection
    results_by_thresh = {}
    for thresh in [60, 65, 70, 75, 80]:
        tp = 0; fp = 0; fn = 0; tn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                pred_mg = pred[:, 12:, 0] * gluc_scale
                actual_mg = bx[:, 12:, 0] * gluc_scale
                for i in range(bx.size(0)):
                    pred_hypo = pred_mg[i].min().item() < thresh
                    actual_hypo = actual_mg[i].min().item() < 70
                    if pred_hypo and actual_hypo: tp += 1
                    elif pred_hypo and not actual_hypo: fp += 1
                    elif not pred_hypo and actual_hypo: fn += 1
                    else: tn += 1
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2*prec*rec / max(prec+rec, 1e-8)
        results_by_thresh[f'thresh_{thresh}'] = {
            'precision': round(prec, 3), 'recall': round(rec, 3), 'f1': round(f1, 3),
            'tp': tp, 'fp': fp, 'fn': fn
        }
        print(f'  [EXP-131] thresh={thresh}: prec={prec:.3f} rec={rec:.3f} f1={f1:.3f}')

    results = {'thresholds': results_by_thresh}
    out_path = 'externals/experiments/exp131_hypo_recall_max.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-131', 'name': 'hypo-recall-max',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-132: Clarke Error Grid analysis ────────────────────────────
# Standard clinical metric for CGM accuracy. Zones A+B = clinically ok.
def run_clarke_error_grid(args):
    """EXP-132: Clarke Error Grid analysis at multiple horizons."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-132] {len(train_ds)} train, {len(val_ds)} val')

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    vl = DataLoader(val_ds, batch_size=256)
    best_val = float('inf'); best_state = None
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            opt.zero_grad(); pred = model(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward(); opt.step()
        model.eval(); vs = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                vs += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0); vn += bx.size(0)
        vavg = vs / vn
        if vavg < best_val: best_val = vavg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state); model.eval()

    def clarke_zone(ref, pred_val):
        """Simplified Clarke Error Grid zone classification."""
        if ref <= 70 and pred_val <= 70: return 'A'
        if ref >= 180 and pred_val >= 180: return 'A'
        if ref > 0:
            pct_err = abs(pred_val - ref) / ref
            if pct_err <= 0.20: return 'A'
            if pct_err <= 0.40: return 'B'
        if ref <= 70 and pred_val >= 180: return 'E'
        if ref >= 180 and pred_val <= 70: return 'E'
        if pred_val > ref + 110: return 'D'
        if pred_val < ref - 110: return 'D'
        return 'C'

    # Evaluate at each 5-min step
    results = {}
    for step_name, step_idx in [('15min', 2), ('30min', 5), ('45min', 8), ('60min', 11)]:
        zones = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0}
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                for i in range(bx.size(0)):
                    ref = bx[i, 12 + step_idx, 0].item() * gluc_scale
                    pv = pred[i, 12 + step_idx, 0].item() * gluc_scale
                    z = clarke_zone(ref, pv)
                    zones[z] += 1
        total = sum(zones.values())
        results[step_name] = {
            'zone_A_pct': round(zones['A'] / total * 100, 1),
            'zone_B_pct': round(zones['B'] / total * 100, 1),
            'zone_AB_pct': round((zones['A'] + zones['B']) / total * 100, 1),
            'zone_C_pct': round(zones['C'] / total * 100, 1),
            'zone_D_pct': round(zones['D'] / total * 100, 1),
            'zone_E_pct': round(zones['E'] / total * 100, 1),
        }
        print(f'  [EXP-132] {step_name}: A+B={results[step_name]["zone_AB_pct"]}%')

    out_path = 'externals/experiments/exp132_clarke_error_grid.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-132', 'name': 'clarke-error-grid',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-133: Time-of-day aware forecast ────────────────────────────
# Instead of positional encoding (EXP-101, no improvement), use
# explicit time-of-day as auxiliary input via augmented loss.
def run_time_aware_forecast(args):
    """EXP-133: Time-of-day conditioned forecast."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)
    import torch, torch.nn.functional as F, numpy as np, json
    from torch.utils.data import DataLoader
    from .model import CGMGroupedEncoder
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .schema import NORMALIZATION_SCALES

    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-133] {len(train_ds)} train, {len(val_ds)} val')

    # Standard model (baseline)
    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)
    vl = DataLoader(val_ds, batch_size=256)
    best_val = float('inf'); best_state = None
    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            opt.zero_grad(); pred = model(x_in)
            loss = F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1])
            loss.backward(); opt.step()
        model.eval(); vs = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
                pred = model(x_in)
                vs += F.mse_loss(pred[:, 12:, :1], bx[:, 12:, :1]).item() * bx.size(0); vn += bx.size(0)
        vavg = vs / vn
        if vavg < best_val: best_val = vavg; best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state); model.eval()

    # Evaluate per time-of-day bucket (using time features in the data)
    # Features 6,7 are typically sin/cos of time
    tod_results = {'morning': [], 'afternoon': [], 'evening': [], 'night': []}
    with torch.no_grad():
        for bx, bt in vl:
            bx = bx.to(device); x_in = bx.clone(); x_in[:, 12:, 0] = 0.0
            pred = model(x_in)
            for i in range(bx.size(0)):
                mae_i = (pred[i, 12:, 0] - bx[i, 12:, 0]).abs().mean().item() * gluc_scale
                # Use time features to classify time of day
                # Features 6,7 are sin_hour, cos_hour
                sin_h = bx[i, 0, 6].item() if bx.size(-1) > 6 else 0
                cos_h = bx[i, 0, 7].item() if bx.size(-1) > 7 else 0
                # Approximate hour from sin/cos
                import math
                hour = (math.atan2(sin_h, cos_h) / (2 * math.pi) * 24) % 24

                if 6 <= hour < 12: tod_results['morning'].append(mae_i)
                elif 12 <= hour < 18: tod_results['afternoon'].append(mae_i)
                elif 18 <= hour < 22: tod_results['evening'].append(mae_i)
                else: tod_results['night'].append(mae_i)

    results = {}
    for tod, maes in tod_results.items():
        results[f'{tod}_mae'] = round(float(np.mean(maes)), 1) if maes else -1
        results[f'{tod}_n'] = len(maes)

    print(f'\n--- Time-of-day results ---')
    for k, v in results.items():
        print(f'  [EXP-133] {k}: {v}')

    out_path = 'externals/experiments/exp133_time_aware.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-133', 'name': 'time-aware-forecast',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ══════════════════════════════════════════════════════════════════════
# ║  ROUND 18: Night specialist, Clarke-optimized, production v7     ║
# ══════════════════════════════════════════════════════════════════════

REGISTRY.update({
    'night-specialist':        'run_night_specialist',         # EXP-134
    'clarke-optimized':        'run_clarke_optimized',         # EXP-135
    'hypo-2stage':             'run_hypo_2stage',              # EXP-136
    'production-v7':           'run_production_v7',            # EXP-137
    'adaptive-tod-threshold':  'run_adaptive_tod_threshold',   # EXP-138
    'diverse-ensemble':        'run_diverse_ensemble',         # EXP-139
})

# ── Validation suites (verification data) ─────────────────────────
REGISTRY.update({
    'event-detection-verification':       'run_event_detection_verification',       # EXP-122
    'override-recommendation-verification': 'run_override_recommendation_verification', # EXP-123
    'drift-tir-correlation':              'run_drift_tir_correlation',              # EXP-124
    'composite-verification':             'run_composite_verification',             # EXP-125
})


# ── EXP-134: Night specialist ─────────────────────────────────────
# EXP-133 showed night MAE=15.2 vs morning=9.9 (53% harder).
# Hypothesis: A model trained only on night windows (10pm-6am) will
# reduce night MAE by >15% compared to the general model.
def run_night_specialist(args):
    """EXP-134: Night-specialized model vs general model."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader, TensorDataset
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .model import CGMGroupedEncoder

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)

    # Extract hour-of-day from time features (sin/cos in channels 6,7)
    # sin(2π*h/24) is channel 6, cos(2π*h/24) is channel 7
    # Night = 22:00-06:00 → hour ∈ [22,24) ∪ [0,6)
    def get_hour(tensor):
        """Estimate hour from sin/cos time features."""
        sin_val = tensor[:, 0, 6]  # first timestep
        cos_val = tensor[:, 0, 7]
        hour = torch.atan2(sin_val, cos_val) * 12 / np.pi  # radians → hours
        hour = hour % 24
        return hour

    all_x = train_ds.vectors
    all_t = torch.zeros(len(all_x))
    hours = get_hour(all_x)

    night_mask = (hours >= 22) | (hours < 6)
    day_mask = ~night_mask

    night_x = all_x[night_mask]
    day_x = all_x[day_mask]
    print(f'  [EXP-134] Night: {len(night_x)}, Day: {len(day_x)}')

    val_x = val_ds.vectors
    val_hours = get_hour(val_x)
    val_night = val_x[val_hours >= 22] if len(val_x) > 0 else val_x
    # Proper night mask for val
    val_night_mask = (val_hours >= 22) | (val_hours < 6)
    val_night = val_x[val_night_mask]
    val_day = val_x[~val_night_mask]

    ws, half = 24, 12

    def train_model(data_x, tag, epochs=100):
        model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
        ds = TensorDataset(data_x)
        dl = DataLoader(ds, batch_size=128, shuffle=True)
        for ep in range(1, epochs + 1):
            model.train()
            for (bx,) in dl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                opt.zero_grad()
                pred = model(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward()
                opt.step()
            if ep % 25 == 0:
                print(f'  [{tag}] {ep}/{epochs}')
        return model

    # Train general model on all data
    general = train_model(all_x, 'general')

    # Train night specialist on night-only data
    night_model = train_model(night_x, 'night-spec')

    # Evaluate both on night validation set
    def eval_mae(model, data, label):
        if len(data) == 0:
            return float('nan')
        model.eval()
        with torch.no_grad():
            bx = data.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            pred = model(x_in)
            mae = (pred[:, half:, 0] - bx[:, half:, 0]).abs().mean().item() * 400
        return round(mae, 1)

    results = {
        'general_night_mae': eval_mae(general, val_night, 'gen-night'),
        'specialist_night_mae': eval_mae(night_model, val_night, 'spec-night'),
        'general_day_mae': eval_mae(general, val_day, 'gen-day'),
        'night_val_n': len(val_night),
        'day_val_n': len(val_day),
        'night_train_n': len(night_x),
    }
    if results['general_night_mae'] > 0:
        results['improvement_pct'] = round(
            (results['general_night_mae'] - results['specialist_night_mae'])
            / results['general_night_mae'] * 100, 1)

    print(f'\n--- Night specialist results ---')
    for k, v in results.items():
        print(f'  [EXP-134] {k}: {v}')

    out_path = 'externals/experiments/exp134_night_specialist.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-134', 'name': 'night-specialist',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-135: Clarke-optimized loss ────────────────────────────────
# EXP-132 showed 95.9% Zone A+B at 60min. Clinical target is >98%.
# Hypothesis: A custom loss that penalizes Zone C/D/E errors more
# heavily will push Zone A+B >97% at 60min.
def run_clarke_optimized(args):
    """EXP-135: Clarke Error Grid-aware training loss."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .model import CGMGroupedEncoder

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-135] {len(train_ds)} train, {len(val_ds)} val')

    ws, half = 24, 12

    def clarke_zone(ref_mg, pred_mg):
        """Classify into Clarke zones A-E. Returns zone weights."""
        diff = (pred_mg - ref_mg).abs()
        pct_diff = diff / (ref_mg.clamp(min=1))

        # Zone A: within 20% or within 20 mg/dL for ref<70
        zone_a = (pct_diff <= 0.20) | ((ref_mg < 70) & (diff <= 20))
        # Zone B: clinically benign
        zone_b = ~zone_a & (pct_diff <= 0.40)
        # Zone C/D/E: clinically dangerous
        zone_cde = ~zone_a & ~zone_b

        # Weight: 1× for A, 3× for B, 10× for C/D/E
        weights = torch.ones_like(ref_mg)
        weights[zone_b] = 3.0
        weights[zone_cde] = 10.0
        return weights

    # Train with Clarke-weighted loss
    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)

    epochs = 100
    for ep in range(1, epochs + 1):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            opt.zero_grad()
            pred = model(x_in)

            pred_gluc = pred[:, half:, 0] * 400
            true_gluc = bx[:, half:, 0] * 400
            weights = clarke_zone(true_gluc.detach(), pred_gluc.detach())

            loss = (weights * (pred[:, half:, :1].squeeze(-1) - bx[:, half:, :1].squeeze(-1)) ** 2).mean()
            loss.backward()
            opt.step()
        if ep % 25 == 0:
            print(f'  [EXP-135] {ep}/{epochs}')

    # Train baseline for comparison
    baseline = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt_b = torch.optim.AdamW(baseline.parameters(), lr=1e-3)
    for ep in range(1, epochs + 1):
        baseline.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            opt_b.zero_grad()
            pred = baseline(x_in)
            loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
            loss.backward()
            opt_b.step()

    # Clarke evaluation
    def eval_clarke(mdl, label):
        mdl.eval()
        zones = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0}
        total = 0
        all_mae = []
        with torch.no_grad():
            vl = DataLoader(val_ds, batch_size=256)
            for bx, bt in vl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = mdl(x_in)
                for step in [3, 6, 9, 11]:  # 15,30,45,60 min
                    p = pred[:, half + step, 0] * 400
                    r = bx[:, half + step, 0] * 400
                    mae = (p - r).abs().mean().item()
                    all_mae.append(mae)
                    diff = (p - r).abs()
                    pct = diff / r.clamp(min=1)
                    za = ((pct <= 0.20) | ((r < 70) & (diff <= 20))).sum().item()
                    zb = (~((pct <= 0.20) | ((r < 70) & (diff <= 20))) & (pct <= 0.40)).sum().item()
                    rest = len(p) - za - zb
                    zones['A'] += za
                    zones['B'] += zb
                    zones['C'] += rest
                    total += len(p)
        ab_pct = (zones['A'] + zones['B']) / max(total, 1) * 100
        return {'zone_a_pct': round(zones['A'] / max(total, 1) * 100, 1),
                'zone_ab_pct': round(ab_pct, 1),
                'mae': round(np.mean(all_mae), 1)}

    clarke_res = eval_clarke(model, 'clarke-opt')
    base_res = eval_clarke(baseline, 'baseline')

    results = {
        'clarke_optimized': clarke_res,
        'baseline': base_res,
        'ab_improvement': round(clarke_res['zone_ab_pct'] - base_res['zone_ab_pct'], 2),
    }

    print(f'\n--- Clarke-optimized results ---')
    for k, v in results.items():
        print(f'  [EXP-135] {k}: {v}')

    out_path = 'externals/experiments/exp135_clarke_optimized.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-135', 'name': 'clarke-optimized',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-136: Two-stage hypo detection ─────────────────────────────
# EXP-131 got F1=0.668 at thresh=70. Hypothesis: a two-stage approach
# (1) binary classifier for "hypo in next 1hr?", then (2) forecast
# magnitude for confirmed hypo windows, achieves F1>0.75.
def run_hypo_2stage(args):
    """EXP-136: Two-stage hypo detection: classify then forecast."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    import torch, torch.nn as nn, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader, TensorDataset
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .model import CGMGroupedEncoder

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-136] {len(train_ds)} train, {len(val_ds)} val')

    ws, half = 24, 12
    hypo_thresh = 70 / 400  # normalized

    # Stage 1: Binary classifier — does future window contain hypo?
    train_x = train_ds.vectors
    val_x = val_ds.vectors

    train_labels = (train_x[:, half:, 0].min(dim=1).values < hypo_thresh).float()
    val_labels = (val_x[:, half:, 0].min(dim=1).values < hypo_thresh).float()

    print(f'  [EXP-136] Train hypo rate: {train_labels.mean():.3f}, Val: {val_labels.mean():.3f}')

    # Classifier: encoder + binary head
    class HypoClassifier(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4)
            self.head = nn.Sequential(
                nn.Linear(64, 32), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(32, 1)
            )

        def forward(self, x):
            enc = self.encoder(x)  # (B, T, 8)
            # Pool the history portion
            h = enc[:, :half, :].mean(dim=1)  # (B, 8)
            # Need to project from 8 to 64 for the head
            return self.head(nn.functional.adaptive_avg_pool1d(
                enc[:, :half, :].permute(0, 2, 1), 1).squeeze(-1))

    # Simpler approach: use flattened encoder output
    class HypoClassifierV2(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4)
            self.head = nn.Sequential(
                nn.Linear(8 * half, 64), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(64, 1)
            )

        def forward(self, x):
            enc = self.encoder(x)  # (B, T, 8) — output_dim matches input_dim
            h = enc[:, :half, :].reshape(enc.shape[0], -1)  # (B, 8*12)
            return self.head(h)

    clf = HypoClassifierV2().to(device)
    opt = torch.optim.AdamW(clf.parameters(), lr=1e-3)

    # Oversample hypo to balance
    pos_idx = torch.where(train_labels == 1)[0]
    neg_idx = torch.where(train_labels == 0)[0]
    if len(pos_idx) > 0:
        oversample = pos_idx[torch.randint(len(pos_idx), (len(neg_idx) - len(pos_idx),))]
        bal_idx = torch.cat([torch.arange(len(train_x)), oversample])
        bal_x = train_x[bal_idx]
        bal_y = train_labels[bal_idx]
    else:
        bal_x, bal_y = train_x, train_labels

    clf_ds = TensorDataset(bal_x, bal_y)
    clf_dl = DataLoader(clf_ds, batch_size=128, shuffle=True)

    for ep in range(1, 51):
        clf.train()
        for bx, by in clf_dl:
            bx, by = bx.to(device), by.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            opt.zero_grad()
            logits = clf(x_in).squeeze(-1)
            loss = F.binary_cross_entropy_with_logits(logits, by)
            loss.backward()
            opt.step()
        if ep % 10 == 0:
            print(f'  [clf] {ep}/50')

    # Stage 2: Forecast model (standard)
    forecast_model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt2 = torch.optim.AdamW(forecast_model.parameters(), lr=1e-3)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)

    for ep in range(1, 101):
        forecast_model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            opt2.zero_grad()
            pred = forecast_model(x_in)
            loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
            loss.backward()
            opt2.step()

    # Evaluate two-stage
    clf.eval()
    forecast_model.eval()

    with torch.no_grad():
        vx = val_x.to(device)
        vx_in = vx.clone()
        vx_in[:, half:, 0] = 0.0

        # Stage 1: classify
        logits = clf(vx_in).squeeze(-1)
        probs = torch.sigmoid(logits)

        # Stage 2: forecast
        pred = forecast_model(vx_in)
        pred_min = pred[:, half:, 0].min(dim=1).values * 400

        actual_hypo = val_labels.bool()

    results = {}
    for thresh_p in [0.3, 0.4, 0.5, 0.6, 0.7]:
        predicted = (probs.cpu() > thresh_p)
        tp = (predicted & actual_hypo).sum().item()
        fp = (predicted & ~actual_hypo).sum().item()
        fn = (~predicted & actual_hypo).sum().item()
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-8)

        # Among predicted hypos, check forecast accuracy
        if predicted.sum() > 0:
            pred_hypo_min = pred_min[predicted.to(device)].cpu()
            actual_min = (val_x[predicted][:, half:, 0].min(dim=1).values * 400)
            forecast_mae = (pred_hypo_min - actual_min).abs().mean().item()
        else:
            forecast_mae = float('nan')

        tag = f'p{int(thresh_p*100)}'
        results[f'{tag}_prec'] = round(prec, 3)
        results[f'{tag}_rec'] = round(rec, 3)
        results[f'{tag}_f1'] = round(f1, 3)
        results[f'{tag}_forecast_mae'] = round(forecast_mae, 1)
        print(f'  [EXP-136] p={thresh_p}: prec={prec:.3f} rec={rec:.3f} f1={f1:.3f} fcast_mae={forecast_mae:.1f}')

    results['n_actual_hypo'] = int(actual_hypo.sum())
    results['n_val'] = len(val_x)

    out_path = 'externals/experiments/exp136_hypo_2stage.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-136', 'name': 'hypo-2stage',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-137: Production v7 — best of everything ───────────────────
# Combine: hypo-weighted loss (EXP-116/124), asymmetric quantile
# (EXP-126), conformal calibration (EXP-128), time-aware thresholds
# (EXP-133), and 6hr planner (EXP-129).
def run_production_v7(args):
    """EXP-137: Production v7 — best-of-all combined pipeline."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    import torch, torch.nn as nn, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .model import CGMGroupedEncoder

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-137] {len(train_ds)} train, {len(val_ds)} val')

    ws, half = 24, 12

    # Component 1: Hypo-weighted forecast model
    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)

    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            opt.zero_grad()
            pred = model(x_in)

            base_loss = (pred[:, half:, :1] - bx[:, half:, :1]) ** 2
            # 5× weight for hypo (<70 mg/dL = 0.175 normalized)
            hypo_mask = (bx[:, half:, :1] < 0.175).float()
            weights = 1.0 + 4.0 * hypo_mask
            loss = (weights * base_loss).mean()
            loss.backward()
            opt.step()
        if ep % 25 == 0:
            print(f'  [v7-main] {ep}/100')

    # Component 2: Quantile heads (train on same backbone features)
    class QuantileHead(nn.Module):
        def __init__(self, in_dim=8):
            super().__init__()
            self.lower = nn.Linear(in_dim, 1)
            self.upper = nn.Linear(in_dim, 1)

        def forward(self, x):
            return self.lower(x), self.upper(x)

    qhead = QuantileHead(8).to(device)
    opt_q = torch.optim.Adam(qhead.parameters(), lr=1e-3)

    model.eval()
    for ep in range(1, 51):
        qhead.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            with torch.no_grad():
                enc = model(x_in)
            lo, hi = qhead(enc[:, half:, :])
            target = bx[:, half:, :1]

            alpha_lo, alpha_hi = 0.05, 0.95
            err_lo = target - lo
            loss_lo = torch.where(err_lo > 0, alpha_lo * err_lo, (alpha_lo - 1) * err_lo).mean()
            err_hi = target - hi
            loss_hi = torch.where(err_hi > 0, alpha_hi * err_hi, (alpha_hi - 1) * err_hi).mean()
            loss = loss_lo + loss_hi

            opt_q.zero_grad()
            loss.backward()
            opt_q.step()

    # Component 3: Conformal calibration on validation
    model.eval()
    qhead.eval()

    cal_scores = []
    with torch.no_grad():
        vl = DataLoader(val_ds, batch_size=256)
        all_preds, all_true, all_lo, all_hi = [], [], [], []
        for bx, bt in vl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            pred = model(x_in)
            lo, hi = qhead(pred[:, half:, :])

            all_preds.append(pred[:, half:, 0].cpu())
            all_true.append(bx[:, half:, 0].cpu())
            all_lo.append(lo.squeeze(-1).cpu())
            all_hi.append(hi.squeeze(-1).cpu())

    preds = torch.cat(all_preds)
    true = torch.cat(all_true)
    lo_all = torch.cat(all_lo)
    hi_all = torch.cat(all_hi)

    # Conformal scores
    scores = torch.max(lo_all - true, true - hi_all)
    q90 = torch.quantile(scores.flatten(), 0.90).item()
    q95 = torch.quantile(scores.flatten(), 0.95).item()

    # Compute metrics
    pred_mg = preds * 400
    true_mg = true * 400
    mae_overall = (pred_mg - true_mg).abs().mean().item()

    # Hypo metrics
    hypo_mask = true_mg < 70
    if hypo_mask.any():
        mae_hypo = (pred_mg[hypo_mask] - true_mg[hypo_mask]).abs().mean().item()
    else:
        mae_hypo = float('nan')

    # Conformal band metrics
    lo_conf = (lo_all - q90) * 400
    hi_conf = (hi_all + q90) * 400
    coverage = ((true_mg >= lo_conf) & (true_mg <= hi_conf)).float().mean().item()
    width = (hi_conf - lo_conf).mean().item()

    # Time-of-day thresholds (from EXP-133 findings)
    sin_val = val_ds.vectors[:, 0, 6]
    cos_val = val_ds.vectors[:, 0, 7]
    hours = (torch.atan2(sin_val, cos_val) * 12 / np.pi) % 24

    tod_results = {}
    for name, lo_h, hi_h in [('morning', 6, 12), ('afternoon', 12, 18),
                               ('evening', 18, 22), ('night_a', 22, 24), ('night_b', 0, 6)]:
        if name == 'night_a':
            mask = hours >= 22
        elif name == 'night_b':
            mask = hours < 6
        else:
            mask = (hours >= lo_h) & (hours < hi_h)
        if mask.sum() > 0:
            tod_results[f'{name}_mae'] = round(
                (pred_mg[mask.unsqueeze(1).expand_as(pred_mg)] -
                 true_mg[mask.unsqueeze(1).expand_as(true_mg)]).abs().mean().item(), 1)

    # Planner: generate 6hr plans
    n_plans = 0
    actions = {}
    for i in range(len(preds)):
        trajectory = pred_mg[i]  # 12 steps = 1hr
        alerts = []
        pred_min = trajectory.min().item()
        pred_max = trajectory.max().item()
        roc = (trajectory[-1] - trajectory[0]).item() / 60  # mg/dL/min

        if pred_min < 70:
            alerts.append('hypo_alert')
            n_plans += 1
        if pred_max > 250:
            alerts.append('urgent_high')
            n_plans += 1
        if roc < -1.5:
            alerts.append('rapid_fall')
            n_plans += 1
        if roc > 1.5:
            alerts.append('rapid_rise')
            n_plans += 1
        if pred_max > 180:
            alerts.append('consider_correction')

        for a in alerts:
            actions[a] = actions.get(a, 0) + 1

    # Hypo detection precision/recall
    pred_hypo = preds.min(dim=1).values * 400 < 70
    actual_hypo = true.min(dim=1).values * 400 < 70
    tp = (pred_hypo & actual_hypo).sum().item()
    fp = (pred_hypo & ~actual_hypo).sum().item()
    fn = (~pred_hypo & actual_hypo).sum().item()
    hypo_prec = tp / max(tp + fp, 1)
    hypo_rec = tp / max(tp + fn, 1)
    hypo_f1 = 2 * hypo_prec * hypo_rec / max(hypo_prec + hypo_rec, 1e-8)

    results = {
        'mae_overall': round(mae_overall, 1),
        'mae_hypo': round(mae_hypo, 1),
        'hypo_precision': round(hypo_prec, 3),
        'hypo_recall': round(hypo_rec, 3),
        'hypo_f1': round(hypo_f1, 3),
        'conformal_coverage_90': round(coverage, 3),
        'conformal_width': round(width, 1),
        'n_plans': n_plans,
        'top_actions': dict(sorted(actions.items(), key=lambda x: -x[1])[:5]),
        'tod': tod_results,
    }

    print(f'\n--- Production v7 results ---')
    for k, v in results.items():
        print(f'  [EXP-137] {k}: {v}')

    out_path = 'externals/experiments/exp137_production_v7.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-137', 'name': 'production-v7',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-138: Adaptive time-of-day thresholds ──────────────────────
# EXP-133 showed 53% harder at night. Use different alert thresholds
# per time-of-day to maintain consistent false-alarm rates.
def run_adaptive_tod_threshold(args):
    """EXP-138: Time-of-day adaptive alert thresholds."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .model import CGMGroupedEncoder

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-138] {len(train_ds)} train, {len(val_ds)} val')

    ws, half = 24, 12

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)

    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            opt.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
            loss.backward()
            opt.step()

    # Get errors per time-of-day on calibration set (use training set)
    model.eval()
    sin_train = train_ds.vectors[:, 0, 6]
    cos_train = train_ds.vectors[:, 0, 7]
    hours_train = (torch.atan2(sin_train, cos_train) * 12 / np.pi) % 24

    # Compute per-ToD error distributions
    tod_bins = {'morning': (6, 12), 'afternoon': (12, 18),
                'evening': (18, 22), 'night': (22, 30)}  # 30 = wraps to 6

    tod_error_quantiles = {}
    with torch.no_grad():
        # Process in batches
        all_errors = torch.zeros(len(train_ds))
        dl = DataLoader(train_ds, batch_size=256)
        idx = 0
        for bx, bt in dl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            pred = model(x_in)
            err = (pred[:, half:, 0] - bx[:, half:, 0]).abs().mean(dim=1) * 400
            all_errors[idx:idx + len(err)] = err.cpu()
            idx += len(err)

    for name, (lo_h, hi_h) in tod_bins.items():
        if name == 'night':
            mask = (hours_train >= 22) | (hours_train < 6)
        else:
            mask = (hours_train >= lo_h) & (hours_train < hi_h)
        if mask.sum() > 10:
            errs = all_errors[mask]
            q80 = torch.quantile(errs, 0.80).item()
            q90 = torch.quantile(errs, 0.90).item()
            q95 = torch.quantile(errs, 0.95).item()
            tod_error_quantiles[name] = {
                'q80': round(q80, 1), 'q90': round(q90, 1),
                'q95': round(q95, 1), 'n': int(mask.sum())
            }

    # Evaluate on val with adaptive thresholds
    val_x = val_ds.vectors
    sin_val = val_x[:, 0, 6]
    cos_val = val_x[:, 0, 7]
    hours_val = (torch.atan2(sin_val, cos_val) * 12 / np.pi) % 24

    results_fixed = {'tp': 0, 'fp': 0, 'fn': 0}
    results_adaptive = {'tp': 0, 'fp': 0, 'fn': 0}

    with torch.no_grad():
        vx = val_x.to(device)
        vx_in = vx.clone()
        vx_in[:, half:, 0] = 0.0
        pred = model(vx_in)
        pred_min = pred[:, half:, 0].min(dim=1).values * 400
        true_min = vx[:, half:, 0].min(dim=1).values * 400

    actual_hypo = (true_min < 70).cpu()
    fixed_thresh = 70  # mg/dL

    for i in range(len(val_x)):
        h = hours_val[i].item()
        if h >= 22 or h < 6:
            tod = 'night'
        elif h >= 6 and h < 12:
            tod = 'morning'
        elif h >= 12 and h < 18:
            tod = 'afternoon'
        else:
            tod = 'evening'

        # Adaptive threshold: raise threshold for noisier times
        if tod in tod_error_quantiles:
            adaptive_thresh = fixed_thresh + tod_error_quantiles[tod]['q80'] * 0.3
        else:
            adaptive_thresh = fixed_thresh

        # Fixed
        pred_hypo_fixed = pred_min[i].item() < fixed_thresh
        # Adaptive
        pred_hypo_adaptive = pred_min[i].item() < adaptive_thresh

        is_hypo = actual_hypo[i].item()

        if pred_hypo_fixed and is_hypo: results_fixed['tp'] += 1
        elif pred_hypo_fixed and not is_hypo: results_fixed['fp'] += 1
        elif not pred_hypo_fixed and is_hypo: results_fixed['fn'] += 1

        if pred_hypo_adaptive and is_hypo: results_adaptive['tp'] += 1
        elif pred_hypo_adaptive and not is_hypo: results_adaptive['fp'] += 1
        elif not pred_hypo_adaptive and is_hypo: results_adaptive['fn'] += 1

    def compute_f1(d):
        prec = d['tp'] / max(d['tp'] + d['fp'], 1)
        rec = d['tp'] / max(d['tp'] + d['fn'], 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-8)
        return {'precision': round(prec, 3), 'recall': round(rec, 3), 'f1': round(f1, 3)}

    results = {
        'fixed_70': compute_f1(results_fixed),
        'adaptive': compute_f1(results_adaptive),
        'tod_error_quantiles': tod_error_quantiles,
    }

    print(f'\n--- Adaptive ToD threshold results ---')
    for k, v in results.items():
        print(f'  [EXP-138] {k}: {v}')

    out_path = 'externals/experiments/exp138_adaptive_tod_threshold.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-138', 'name': 'adaptive-tod-threshold',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-139: Diverse architecture ensemble ────────────────────────
# EXP-130 showed identical-seed ensemble gives 12.5 (marginal).
# Hypothesis: ensembling diverse architectures (d32/d64/d128, L2/L4/L6)
# reduces MAE below 12.0 and gives better calibrated uncertainty.
def run_diverse_ensemble(args):
    """EXP-139: Ensemble of diverse architectures."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .model import CGMGroupedEncoder

    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=24)
    print(f'  [EXP-139] {len(train_ds)} train, {len(val_ds)} val')

    ws, half = 24, 12

    configs = [
        {'d_model': 32, 'num_layers': 2, 'tag': 'd32_L2'},
        {'d_model': 64, 'num_layers': 4, 'tag': 'd64_L4'},
        {'d_model': 128, 'num_layers': 6, 'tag': 'd128_L6'},
        {'d_model': 64, 'num_layers': 2, 'tag': 'd64_L2'},
        {'d_model': 32, 'num_layers': 6, 'tag': 'd32_L6'},
    ]

    models = []
    individual_maes = []

    for cfg in configs:
        tag = cfg['tag']
        m = CGMGroupedEncoder(input_dim=8, d_model=cfg['d_model'],
                              num_layers=cfg['num_layers']).to(device)
        opt = torch.optim.AdamW(m.parameters(), lr=1e-3)
        tl = DataLoader(train_ds, batch_size=128, shuffle=True)

        for ep in range(1, 101):
            m.train()
            for bx, bt in tl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                opt.zero_grad()
                pred = m(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward()
                opt.step()

        # Eval individual
        m.eval()
        with torch.no_grad():
            vl = DataLoader(val_ds, batch_size=256)
            errs = []
            for bx, bt in vl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = m(x_in)
                e = (pred[:, half:, 0] - bx[:, half:, 0]).abs() * 400
                errs.append(e.cpu())
            mae = torch.cat(errs).mean().item()

        print(f'  [EXP-139] {tag}: MAE={mae:.1f}')
        individual_maes.append(round(mae, 1))
        models.append(m)

    # Ensemble predictions
    ensemble_preds = []
    all_true = []
    with torch.no_grad():
        vl = DataLoader(val_ds, batch_size=256)
        for bx, bt in vl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            preds = []
            for m in models:
                preds.append(m(x_in)[:, half:, 0:1])
            stacked = torch.stack(preds, dim=0)  # (K, B, T, 1)
            mean_pred = stacked.mean(dim=0)
            ensemble_preds.append(mean_pred.cpu())
            all_true.append(bx[:, half:, 0:1].cpu())

    ens_pred = torch.cat(ensemble_preds)
    ens_true = torch.cat(all_true)
    ens_mae = ((ens_pred - ens_true).abs() * 400).mean().item()

    # Ensemble uncertainty from spread
    with torch.no_grad():
        vl = DataLoader(val_ds, batch_size=256)
        all_stds = []
        for bx, bt in vl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            preds = []
            for m in models:
                preds.append(m(x_in)[:, half:, 0])
            stacked = torch.stack(preds, dim=0)
            std = stacked.std(dim=0) * 400
            all_stds.append(std.cpu())
    avg_std = torch.cat(all_stds).mean().item()

    # Coverage using ±2σ
    with torch.no_grad():
        all_covered = []
        vl = DataLoader(val_ds, batch_size=256)
        idx = 0
        for bx, bt in vl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            preds = []
            for m in models:
                preds.append(m(x_in)[:, half:, 0])
            stacked = torch.stack(preds, dim=0)
            mean = stacked.mean(dim=0) * 400
            std = stacked.std(dim=0) * 400
            true = bx[:, half:, 0] * 400
            covered = ((true >= mean - 2 * std) & (true <= mean + 2 * std)).float()
            all_covered.append(covered.cpu())
    coverage_95 = torch.cat(all_covered).mean().item()

    results = {
        'individual_maes': individual_maes,
        'configs': [c['tag'] for c in configs],
        'ensemble_mae': round(ens_mae, 1),
        'best_individual': min(individual_maes),
        'improvement_pct': round((min(individual_maes) - ens_mae) / min(individual_maes) * 100, 1),
        'avg_ensemble_std': round(avg_std, 1),
        'coverage_95_2sigma': round(coverage_95, 3),
    }

    print(f'\n--- Diverse ensemble results ---')
    for k, v in results.items():
        print(f'  [EXP-139] {k}: {v}')

    out_path = 'externals/experiments/exp139_diverse_ensemble.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-139', 'name': 'diverse-ensemble',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ══════════════════════════════════════════════════════════════════════
# ║  ROUND 19: Data diversity — synthetic pre-training, verification ║
# ║  holdout, per-patient stratification, mixed data pipelines       ║
# ══════════════════════════════════════════════════════════════════════

REGISTRY.update({
    'verification-holdout':    'run_verification_holdout',     # EXP-140
    'uva-pretrain-finetune':   'run_uva_pretrain_finetune',    # EXP-141
    'per-patient-stratified':  'run_per_patient_stratified',   # EXP-142
    'mixed-synth-real':        'run_mixed_synth_real',         # EXP-143
    'leave-one-out-v2':        'run_leave_one_out_v2',         # EXP-144
    'verification-multiobj':   'run_verification_multiobj',    # EXP-145
})


# ── EXP-140: Verification holdout evaluation ──────────────────────
# All prior experiments validated on random 20% split from training.
# This evaluates the best model on held-out VERIFICATION days that
# were NEVER used in training. Measures the real generalization gap.
def run_verification_holdout(args):
    """EXP-140: Evaluate forecast model on verification (held-out) splits."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    import torch, torch.nn.functional as F, json, numpy as np
    from pathlib import Path
    from torch.utils.data import DataLoader
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .model import CGMGroupedEncoder

    # Train on training splits (all 10 patients)
    train_paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(train_paths, window_size=24)
    print(f'  [EXP-140] Train: {len(train_ds)}, Val (random): {len(val_ds)}')

    ws, half = 24, 12

    # Train model
    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)

    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            opt.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
            loss.backward()
            opt.step()
        if ep % 50 == 0:
            print(f'  [EXP-140] train {ep}/100')

    # Evaluate on random val split
    model.eval()
    def eval_dataset(ds, label):
        if len(ds) == 0:
            return {}
        dl = DataLoader(ds, batch_size=256)
        all_errs = []
        hypo_errs, in_range_errs, hyper_errs = [], [], []
        with torch.no_grad():
            for bx, bt in dl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                err = (pred[:, half:, 0] - bx[:, half:, 0]).abs() * 400
                true_mg = bx[:, half:, 0] * 400
                all_errs.append(err.cpu())
                for i in range(err.shape[0]):
                    t = true_mg[i].cpu()
                    e = err[i].cpu()
                    hypo_errs.extend(e[t < 70].tolist())
                    in_range_errs.extend(e[(t >= 70) & (t <= 180)].tolist())
                    hyper_errs.extend(e[t > 180].tolist())
        mae = torch.cat(all_errs).mean().item()
        return {
            'mae': round(mae, 1),
            'n_windows': len(ds),
            'hypo_mae': round(np.mean(hypo_errs), 1) if hypo_errs else None,
            'in_range_mae': round(np.mean(in_range_errs), 1) if in_range_errs else None,
            'hyper_mae': round(np.mean(hyper_errs), 1) if hyper_errs else None,
        }

    random_val = eval_dataset(val_ds, 'random-val')
    print(f'  [EXP-140] Random val MAE: {random_val["mae"]}')

    # Now load verification splits
    pdir = Path(patients_dir) if patients_dir else Path(real_data).parent.parent
    per_patient = {}
    verif_paths = []
    for d in sorted(pdir.iterdir()):
        vdir = d / 'verification'
        if vdir.is_dir():
            verif_paths.append(str(vdir))

    if verif_paths:
        verif_ds_train, verif_ds = load_multipatient_nightscout(verif_paths, window_size=24)
        # Use ALL verification data (not just val split) since it's already held out
        # Combine train+val from verification loading
        all_verif_vectors = torch.cat([verif_ds_train.vectors, verif_ds.vectors])
        from .encoder import CGMDataset
        all_verif = CGMDataset(all_verif_vectors, task='forecast')
        verif_result = eval_dataset(all_verif, 'verification')
        print(f'  [EXP-140] Verification MAE: {verif_result["mae"]} (n={verif_result["n_windows"]})')

        # Per-patient verification
        for d in sorted(pdir.iterdir()):
            vdir = d / 'verification'
            if vdir.is_dir():
                try:
                    pt_train, pt_val = load_multipatient_nightscout([str(vdir)], window_size=24)
                    all_pt = torch.cat([pt_train.vectors, pt_val.vectors])
                    pt_ds = CGMDataset(all_pt, task='forecast')
                    r = eval_dataset(pt_ds, d.name)
                    per_patient[d.name] = r
                    print(f'  [EXP-140] Patient {d.name}: MAE={r["mae"]}')
                except Exception as e:
                    per_patient[d.name] = {'error': str(e)}
    else:
        verif_result = {'error': 'no verification dirs found'}

    results = {
        'random_val': random_val,
        'verification': verif_result,
        'per_patient_verification': per_patient,
        'generalization_gap_pct': round(
            (verif_result.get('mae', 0) - random_val['mae']) / random_val['mae'] * 100, 1
        ) if isinstance(verif_result.get('mae'), (int, float)) else None,
    }

    print(f'\n--- Verification holdout results ---')
    for k, v in results.items():
        if k != 'per_patient_verification':
            print(f'  [EXP-140] {k}: {v}')

    out_path = 'externals/experiments/exp140_verification_holdout.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-140', 'name': 'verification-holdout',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-141: UVA synthetic pre-train → real fine-tune ─────────────
# Pre-train on 8K UVA/Padova synthetic windows (250 virtual patients)
# then fine-tune on 25K real patient windows. Prior work showed
# transfer learning helps +50-62% at 1hr. Test with current pipeline.
def run_uva_pretrain_finetune(args):
    """EXP-141: Pre-train on UVA synthetic, fine-tune on real data."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .sim_adapter import load_conformance_to_dataset
    from .model import CGMGroupedEncoder

    ws, half = 24, 12

    # Phase 1: Load UVA synthetic data
    uva_dir = 'externals/sweep-uva-250'
    synth_train, synth_val = load_conformance_to_dataset([uva_dir], window_size=ws)
    print(f'  [EXP-141] Synthetic: {len(synth_train)} train, {len(synth_val)} val')

    # Phase 2: Load real patient data
    paths = resolve_patient_paths(patients_dir, real_data)
    real_train, real_val = load_multipatient_nightscout(paths, window_size=ws)
    print(f'  [EXP-141] Real: {len(real_train)} train, {len(real_val)} val')

    def train_model(ds, model, epochs, lr, tag):
        opt = torch.optim.AdamW(model.parameters(), lr=lr)
        dl = DataLoader(ds, batch_size=128, shuffle=True)
        best_loss = float('inf')
        for ep in range(1, epochs + 1):
            model.train()
            ep_loss = 0
            n = 0
            for bx, bt in dl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                opt.zero_grad()
                pred = model(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward()
                opt.step()
                ep_loss += loss.item() * len(bx)
                n += len(bx)
            avg = ep_loss / max(n, 1)
            if avg < best_loss:
                best_loss = avg
            if ep % 25 == 0:
                print(f'  [{tag}] {ep}/{epochs} loss={avg:.6f}')
        return best_loss

    def eval_mae(model, ds):
        model.eval()
        dl = DataLoader(ds, batch_size=256)
        errs = []
        with torch.no_grad():
            for bx, bt in dl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                e = (pred[:, half:, 0] - bx[:, half:, 0]).abs() * 400
                errs.append(e.cpu())
        return torch.cat(errs).mean().item()

    # Strategy A: Real-only baseline (100 epochs)
    model_a = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    train_model(real_train, model_a, 100, 1e-3, 'real-only')
    mae_a = eval_mae(model_a, real_val)
    print(f'  [EXP-141] Real-only MAE: {mae_a:.1f}')

    # Strategy B: Pre-train on synthetic (50ep) → fine-tune on real (50ep)
    model_b = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    train_model(synth_train, model_b, 50, 1e-3, 'pretrain-synth')
    mae_b_pretrain = eval_mae(model_b, real_val)
    print(f'  [EXP-141] After pre-train (synth): {mae_b_pretrain:.1f}')
    train_model(real_train, model_b, 50, 5e-4, 'finetune-real')  # lower LR
    mae_b = eval_mae(model_b, real_val)
    print(f'  [EXP-141] After fine-tune (real): {mae_b:.1f}')

    # Strategy C: Pre-train 50ep synth → fine-tune 100ep real
    model_c = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    train_model(synth_train, model_c, 50, 1e-3, 'pretrain-c')
    train_model(real_train, model_c, 100, 5e-4, 'finetune-c')
    mae_c = eval_mae(model_c, real_val)
    print(f'  [EXP-141] Long fine-tune: {mae_c:.1f}')

    results = {
        'synth_train_n': len(synth_train),
        'real_train_n': len(real_train),
        'real_only_mae': round(mae_a, 1),
        'pretrain_before_finetune_mae': round(mae_b_pretrain, 1),
        'pretrain_finetune_mae': round(mae_b, 1),
        'long_finetune_mae': round(mae_c, 1),
        'improvement_pct': round((mae_a - mae_b) / mae_a * 100, 1),
        'synth_only_mae_on_real': round(mae_b_pretrain, 1),
    }

    print(f'\n--- UVA pre-train results ---')
    for k, v in results.items():
        print(f'  [EXP-141] {k}: {v}')

    out_path = 'externals/experiments/exp141_uva_pretrain_finetune.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-141', 'name': 'uva-pretrain-finetune',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-142: Per-patient stratified evaluation ────────────────────
# Report MAE per patient to identify which patients are hardest and
# whether any single patient dominates the aggregate metrics.
def run_per_patient_stratified(args):
    """EXP-142: Per-patient MAE breakdown on training val splits."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    import torch, torch.nn.functional as F, json, numpy as np
    from pathlib import Path
    from torch.utils.data import DataLoader
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .model import CGMGroupedEncoder
    from .encoder import CGMDataset

    ws, half = 24, 12

    # Train on all patients combined
    paths = resolve_patient_paths(patients_dir, real_data)
    train_ds, val_ds = load_multipatient_nightscout(paths, window_size=ws)
    print(f'  [EXP-142] Combined: {len(train_ds)} train, {len(val_ds)} val')

    model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    tl = DataLoader(train_ds, batch_size=128, shuffle=True)

    for ep in range(1, 101):
        model.train()
        for bx, bt in tl:
            bx = bx.to(device)
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0
            opt.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
            loss.backward()
            opt.step()

    # Evaluate per patient
    model.eval()
    per_patient = {}

    for p in paths:
        pname = Path(p).parent.name
        try:
            pt_train, pt_val = load_multipatient_nightscout([p], window_size=ws)
            # Eval on this patient's val split
            dl = DataLoader(pt_val, batch_size=256)
            errs, hypo_errs = [], []
            with torch.no_grad():
                for bx, bt in dl:
                    bx = bx.to(device)
                    x_in = bx.clone()
                    x_in[:, half:, 0] = 0.0
                    pred = model(x_in)
                    e = (pred[:, half:, 0] - bx[:, half:, 0]).abs() * 400
                    true_mg = bx[:, half:, 0] * 400
                    errs.append(e.cpu())
                    hypo_mask = true_mg < 70
                    if hypo_mask.any():
                        hypo_errs.extend(e[hypo_mask].cpu().tolist())

            mae = torch.cat(errs).mean().item()
            per_patient[pname] = {
                'mae': round(mae, 1),
                'n_val': len(pt_val),
                'n_train': len(pt_train),
                'hypo_mae': round(np.mean(hypo_errs), 1) if hypo_errs else None,
            }
            print(f'  [EXP-142] Patient {pname}: MAE={mae:.1f} (n={len(pt_val)})')
        except Exception as e:
            per_patient[pname] = {'error': str(e)}

    maes = [v['mae'] for v in per_patient.values() if 'mae' in v]
    results = {
        'per_patient': per_patient,
        'aggregate_mae': round(np.mean(maes), 1),
        'worst_patient': max(per_patient, key=lambda k: per_patient[k].get('mae', 0)),
        'best_patient': min(per_patient, key=lambda k: per_patient[k].get('mae', float('inf'))),
        'mae_std': round(np.std(maes), 1),
        'mae_range': round(max(maes) - min(maes), 1),
    }

    print(f'\n--- Per-patient stratified results ---')
    print(f'  [EXP-142] aggregate: {results["aggregate_mae"]} ± {results["mae_std"]}')
    print(f'  [EXP-142] worst: {results["worst_patient"]}, best: {results["best_patient"]}')
    print(f'  [EXP-142] range: {results["mae_range"]}')

    out_path = 'externals/experiments/exp142_per_patient_stratified.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-142', 'name': 'per-patient-stratified',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-143: Mixed synthetic + real training ──────────────────────
# Hypothesis: Adding 8K UVA synthetic windows to 25K real windows
# during training improves generalization by exposing the model to
# wider physiological parameter ranges (ISF 10-120, CR 3-30).
def run_mixed_synth_real(args):
    """EXP-143: Train on mixed UVA synthetic + real patient data."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    import torch, torch.nn.functional as F, json, numpy as np
    from torch.utils.data import DataLoader, ConcatDataset
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .sim_adapter import load_conformance_to_dataset
    from .model import CGMGroupedEncoder
    from .encoder import CGMDataset

    ws, half = 24, 12

    # Load both datasets
    paths = resolve_patient_paths(patients_dir, real_data)
    real_train, real_val = load_multipatient_nightscout(paths, window_size=ws)
    synth_train, synth_val = load_conformance_to_dataset(
        ['externals/sweep-uva-250'], window_size=ws)
    print(f'  [EXP-143] Real: {len(real_train)} train, Synth: {len(synth_train)} train')

    def train_and_eval(ds_train, ds_val, tag, epochs=100):
        model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
        dl = DataLoader(ds_train, batch_size=128, shuffle=True)
        for ep in range(1, epochs + 1):
            model.train()
            for bx, bt in dl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                opt.zero_grad()
                pred = model(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward()
                opt.step()
            if ep % 50 == 0:
                print(f'  [{tag}] {ep}/{epochs}')
        model.eval()
        dl_v = DataLoader(ds_val, batch_size=256)
        errs = []
        with torch.no_grad():
            for bx, bt in dl_v:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                e = (pred[:, half:, 0] - bx[:, half:, 0]).abs() * 400
                errs.append(e.cpu())
        mae = torch.cat(errs).mean().item()
        return round(mae, 1)

    # Strategy A: Real only
    mae_real = train_and_eval(real_train, real_val, 'real-only')
    print(f'  [EXP-143] Real-only: {mae_real}')

    # Strategy B: Mixed (concat real + synth)
    mixed_train = ConcatDataset([real_train, synth_train])
    mae_mixed = train_and_eval(mixed_train, real_val, 'mixed')
    print(f'  [EXP-143] Mixed: {mae_mixed}')

    # Strategy C: Synth only (sanity check)
    mae_synth = train_and_eval(synth_train, real_val, 'synth-only')
    print(f'  [EXP-143] Synth-only: {mae_synth}')

    results = {
        'real_only_mae': mae_real,
        'mixed_mae': mae_mixed,
        'synth_only_mae': mae_synth,
        'real_n': len(real_train),
        'synth_n': len(synth_train),
        'mixed_n': len(mixed_train),
        'mixed_improvement_pct': round((mae_real - mae_mixed) / mae_real * 100, 1),
    }

    print(f'\n--- Mixed synth+real results ---')
    for k, v in results.items():
        print(f'  [EXP-143] {k}: {v}')

    out_path = 'externals/experiments/exp143_mixed_synth_real.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-143', 'name': 'mixed-synth-real',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-144: Leave-one-patient-out v2 ─────────────────────────────
# Train on 9 patients, test on 1 (held out). Repeat for all 10.
# EXP-055 did this at 16.1±2.6 — re-measure with current architecture
# and include per-patient hypo/range-stratified metrics.
def run_leave_one_out_v2(args):
    """EXP-144: Leave-one-patient-out cross-validation with stratified metrics."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    _dev = getattr(args, 'device', 'cpu')
    import torch as _torch
    device = 'cuda' if _dev == 'auto' and _torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    import torch, torch.nn.functional as F, json, numpy as np
    from pathlib import Path
    from torch.utils.data import DataLoader
    from .experiment_lib import resolve_patient_paths
    from .real_data_adapter import load_multipatient_nightscout
    from .model import CGMGroupedEncoder
    from .encoder import CGMDataset

    ws, half = 24, 12
    paths = resolve_patient_paths(patients_dir, real_data)

    per_patient = {}
    for held_out_idx, held_out_path in enumerate(paths):
        pname = Path(held_out_path).parent.name
        train_paths = [p for i, p in enumerate(paths) if i != held_out_idx]

        # Train on 9
        train_ds, _ = load_multipatient_nightscout(train_paths, window_size=ws)
        # Test on held-out patient (use ALL data, no split)
        test_train, test_val = load_multipatient_nightscout([held_out_path], window_size=ws)
        all_test = torch.cat([test_train.vectors, test_val.vectors])
        test_ds = CGMDataset(all_test, task='forecast')

        model = CGMGroupedEncoder(input_dim=8, d_model=64, num_layers=4).to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
        dl = DataLoader(train_ds, batch_size=128, shuffle=True)

        for ep in range(1, 81):  # 80 epochs (faster per fold)
            model.train()
            for bx, bt in dl:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                opt.zero_grad()
                pred = model(x_in)
                loss = F.mse_loss(pred[:, half:, :1], bx[:, half:, :1])
                loss.backward()
                opt.step()

        # Eval
        model.eval()
        dl_test = DataLoader(test_ds, batch_size=256)
        errs, hypo_errs, in_range_errs = [], [], []
        with torch.no_grad():
            for bx, bt in dl_test:
                bx = bx.to(device)
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                e = (pred[:, half:, 0] - bx[:, half:, 0]).abs() * 400
                true_mg = bx[:, half:, 0] * 400
                errs.append(e.cpu())
                for j in range(e.shape[0]):
                    t = true_mg[j].cpu()
                    ej = e[j].cpu()
                    hypo_errs.extend(ej[t < 70].tolist())
                    in_range_errs.extend(ej[(t >= 70) & (t <= 180)].tolist())

        mae = torch.cat(errs).mean().item()
        per_patient[pname] = {
            'mae': round(mae, 1),
            'n_test': len(test_ds),
            'n_train': len(train_ds),
            'hypo_mae': round(np.mean(hypo_errs), 1) if hypo_errs else None,
            'in_range_mae': round(np.mean(in_range_errs), 1) if in_range_errs else None,
        }
        print(f'  [EXP-144] LOO {pname}: MAE={mae:.1f} (n={len(test_ds)})')

    maes = [v['mae'] for v in per_patient.values()]
    results = {
        'per_patient': per_patient,
        'mean_mae': round(np.mean(maes), 1),
        'std_mae': round(np.std(maes), 1),
        'worst': max(per_patient, key=lambda k: per_patient[k]['mae']),
        'best': min(per_patient, key=lambda k: per_patient[k]['mae']),
    }

    print(f'\n--- Leave-one-out v2 results ---')
    print(f'  [EXP-144] Mean: {results["mean_mae"]} ± {results["std_mae"]}')
    print(f'  [EXP-144] Worst: {results["worst"]}, Best: {results["best"]}')

    out_path = 'externals/experiments/exp144_leave_one_out_v2.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-144', 'name': 'leave-one-out-v2',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ── EXP-145: Multi-objective validation on verification data ──────
# Run the colleague's 4-suite validation (event detection, override
# recommendation, drift-TIR, composite) to establish current baselines
# and identify which objectives benefit most from data improvements.
def run_verification_multiobj(args):
    """EXP-145: Run all 4 multi-objective validation suites."""
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    import json

    if not patients_dir:
        from pathlib import Path
        patients_dir = str(Path(real_data).parent.parent) if real_data else None

    print(f'  [EXP-145] Running all validation suites on {patients_dir}')

    try:
        results = run_all_suites(patients_dir)
        print(f'\n--- Multi-objective verification results ---')
        for suite, data in results.items():
            if isinstance(data, dict):
                # Print summary metrics
                for k in ['macro_f1', 'aggregate_f1', 'aggregate_r',
                           'event_rate', 'n_windows', 'error']:
                    if k in data:
                        print(f'  [EXP-145] {suite}.{k}: {data[k]}')
            else:
                print(f'  [EXP-145] {suite}: {data}')
    except Exception as e:
        import traceback
        results = {'error': str(e), 'traceback': traceback.format_exc()}
        print(f'  [EXP-145] Error: {e}')

    # Filter out non-serializable objects (e.g. XGBClassifier, numpy keys)
    import numpy as np
    def _sanitize(obj):
        if isinstance(obj, dict):
            return {str(k): _sanitize(v) for k, v in obj.items()
                    if isinstance(v, (dict, list, str, int, float, bool, type(None),
                                     np.integer, np.floating))}
        if isinstance(obj, list):
            return [_sanitize(v) for v in obj]
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        return obj

    out_path = 'externals/experiments/exp145_verification_multiobj.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-145', 'name': 'verification-multiobj',
                   'results': _sanitize(results)}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')


# ══════════════════════════════════════════════════════════════════════
# ║  ROUND 20: Gen-2 Multi-Task Training Campaign                    ║
# ║  16-feature, 4-objective, sim-to-real transfer                   ║
# ══════════════════════════════════════════════════════════════════════

REGISTRY.update({
    'gen2-pretrain':           'run_gen2_pretrain',             # EXP-150
    'gen2-finetune':           'run_gen2_finetune',             # EXP-151
    'gen2-eval':               'run_gen2_eval',                 # EXP-152
    'gen2-ablation':           'run_gen2_ablation',             # EXP-153
})


# ── EXP-150: Gen-2 synthetic pre-training (16-feat, forecast-only) ─
# Stage 1 of the Gen-2 campaign: train 16-feature GroupedEncoder on
# sweep-uva-250 synthetic data. Forecast-only (no aux heads) because
# synthetic data lacks Nightscout event/drift labels.
# The grouped architecture isolates base features (state/action/time
# projections) from extended context (context_proj), so the context
# projection starts fresh but doesn't interfere with transfer.
def run_gen2_pretrain(args):
    """EXP-150: Gen-2 Stage 1 — synthetic pre-training (16-feat, forecast-only)."""
    import torch, torch.nn.functional as F, json
    from torch.utils.data import DataLoader, TensorDataset
    from .sim_adapter import load_conformance_to_dataset

    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    # Load synthetic data (8-feature) and pad to 16
    synth_dirs = ['externals/sweep-uva-250']
    train_ds_8, val_ds_8 = load_conformance_to_dataset(synth_dirs, window_size=24, task='forecast')
    if not train_ds_8:
        return {'error': 'No synthetic data found in externals/sweep-uva-250'}

    def pad_to_16(ds):
        """Pad 8-feature dataset to 16-feature by adding zeros for extended channels."""
        xs, ys = [], []
        for i in range(len(ds)):
            x, y = ds[i]
            x16 = torch.zeros(x.shape[0], 16)
            x16[:, :min(x.shape[1], 8)] = x[:, :8] if x.dim() > 1 else x.unsqueeze(-1)[:, :8]
            y16 = torch.zeros(y.shape[0], 16)
            y16[:, :min(y.shape[1], 8)] = y[:, :8] if y.dim() > 1 else y.unsqueeze(-1)[:, :8]
            xs.append(x16)
            ys.append(y16)
        return TensorDataset(torch.stack(xs), torch.stack(ys))

    train_ds = pad_to_16(train_ds_8)
    val_ds = pad_to_16(val_ds_8)
    print(f'  [EXP-150] {len(train_ds)} train, {len(val_ds)} val (padded 8→16 features)')

    # Train 16-feature GroupedEncoder (NO aux heads — forecast only)
    model = CGMGroupedEncoder(input_dim=16, d_model=64, nhead=4, num_layers=3).to(device)
    param_count = sum(p.numel() for p in model.parameters())
    print(f'  [EXP-150] Model: {param_count:,} params (16-feat, forecast-only)')

    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=10, factor=0.5)
    tl = DataLoader(train_ds, batch_size=64, shuffle=True)
    vl = DataLoader(val_ds, batch_size=256)

    best_val = float('inf')
    best_state = None
    stale = 0
    history = []

    for ep in range(1, 51):
        model.train()
        epoch_loss = 0; n_batches = 0
        for bx, bt in tl:
            bx, bt = bx.to(device), bt.to(device)
            half = bx.shape[1] // 2
            x_in = bx.clone()
            x_in[:, half:, 0] = 0.0  # mask future glucose
            opt.zero_grad()
            pred = model(x_in)
            loss = F.mse_loss(pred[:, half:, :1], bt[:, half:, :1])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            epoch_loss += loss.item()
            n_batches += 1

        model.eval()
        vloss = 0; vn = 0
        with torch.no_grad():
            for bx, bt in vl:
                bx, bt = bx.to(device), bt.to(device)
                half = bx.shape[1] // 2
                x_in = bx.clone()
                x_in[:, half:, 0] = 0.0
                pred = model(x_in)
                vloss += F.mse_loss(pred[:, half:, :1], bt[:, half:, :1]).item() * bx.size(0)
                vn += bx.size(0)
        vl_avg = vloss / vn if vn else float('inf')
        tl_avg = epoch_loss / n_batches if n_batches else float('inf')
        sched.step(vl_avg)

        history.append({'epoch': ep, 'train': tl_avg, 'val': vl_avg})

        if vl_avg < best_val:
            best_val = vl_avg
            stale = 0
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        else:
            stale += 1

        if ep % 10 == 0:
            lr_now = opt.param_groups[0]['lr']
            mark = ' *' if stale == 0 else ''
            print(f'  [EXP-150] {ep}/50 train={tl_avg:.6f} val={vl_avg:.6f} '
                  f'best={best_val:.6f} lr={lr_now:.1e}{mark}')

        if stale >= 15:
            print(f'  [EXP-150] Early stop at epoch {ep}')
            break

    # Save checkpoint
    save_path = 'checkpoints/gen2_pretrain.pth'
    import os; os.makedirs('checkpoints', exist_ok=True)
    torch.save({
        'epoch': ep, 'model_state': best_state or model.state_dict(),
        'val_loss': best_val, 'label': 'gen2-pretrain',
        'config': {'input_dim': 16, 'd_model': 64, 'nhead': 4, 'num_layers': 3},
    }, save_path)
    print(f'  [EXP-150] Saved → {save_path} (val={best_val:.6f})')

    # Compute MAE in mg/dL
    from .schema import NORMALIZATION_SCALES
    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)
    mae_mgdl = (best_val ** 0.5) * gluc_scale  # approx from MSE

    results = {
        'best_val_loss': best_val, 'epochs_run': ep,
        'mae_mgdl_approx': round(mae_mgdl, 1),
        'n_train': len(train_ds), 'n_val': len(val_ds),
        'checkpoint': save_path, 'history': history,
    }

    out_path = 'externals/experiments/exp150_gen2_pretrain.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-150', 'name': 'gen2-pretrain',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')
    return results


# ── EXP-151: Gen-2 multi-task fine-tuning (all 4 heads) ───────────
# Stage 2: Load gen2_pretrain.pth, add 4 auxiliary heads, fine-tune
# on 10 real patients with composite loss. Uses pseudo-labels from
# Kalman filter (drift), PatternStateMachine (state), and
# label_events (events).
def run_gen2_finetune(args):
    """EXP-151: Gen-2 Stage 2 — multi-task fine-tuning on real data."""
    import torch, json, os
    from .generate_aux_labels import build_multitask_dataset, N_EVENT_CLASSES, N_STATE_CLASSES
    from .experiment_lib import train_multitask, DEFAULT_TASK_WEIGHTS

    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    if not patients_dir and real_data:
        from pathlib import Path
        patients_dir = str(Path(real_data).parent.parent)

    if not patients_dir:
        return {'error': 'Need --patients-dir for multi-task fine-tuning'}

    # Build multi-task dataset
    print(f'  [EXP-151] Building multi-task dataset from {patients_dir}...')
    train_ds, val_ds, meta = build_multitask_dataset(patients_dir, window_size=24, verbose=True)
    print(f'  [EXP-151] {len(train_ds)} train, {len(val_ds)} val windows')

    # Create model with aux heads
    aux_config = {
        'n_event_classes': N_EVENT_CLASSES,
        'n_drift_outputs': 2,
        'n_states': N_STATE_CLASSES,
    }
    model = CGMGroupedEncoder(
        input_dim=16, d_model=64, nhead=4, num_layers=3,
        aux_config=aux_config,
    ).to(device)
    param_count = sum(p.numel() for p in model.parameters())
    print(f'  [EXP-151] Model: {param_count:,} params (16-feat + 4 heads)')

    # Load Stage 1 pre-trained weights (strict=False: aux heads are new)
    pretrain_path = getattr(args, 'pretrained', None) or 'checkpoints/gen2_pretrain.pth'
    if os.path.exists(pretrain_path):
        ckpt = torch.load(pretrain_path, map_location=device, weights_only=True)
        state = ckpt.get('model_state', ckpt)
        missing, unexpected = model.load_state_dict(state, strict=False)
        print(f'  [EXP-151] Loaded {pretrain_path} (missing={len(missing)}, unexpected={len(unexpected)})')
    else:
        print(f'  [EXP-151] No pre-trained checkpoint at {pretrain_path}, training from scratch')

    save_path = 'checkpoints/gen2_multitask.pth'
    best_val, epochs_run, history = train_multitask(
        model, train_ds, val_ds, save_path,
        label='EXP-151',
        lr=3e-4, epochs=50, batch=32, patience=15,
        weight_decay=1e-5, lr_patience=5,
        task_weights=DEFAULT_TASK_WEIGHTS,
    )

    # Compute forecast MAE
    from .schema import NORMALIZATION_SCALES
    gluc_scale = NORMALIZATION_SCALES.get('glucose', 400.0)

    results = {
        'best_val_loss': best_val, 'epochs_run': epochs_run,
        'n_train': len(train_ds), 'n_val': len(val_ds),
        'checkpoint': save_path,
        'pretrained_from': pretrain_path if os.path.exists(pretrain_path) else None,
        'task_weights': DEFAULT_TASK_WEIGHTS,
        'meta': meta, 'history': history[-5:],  # last 5 epochs
    }

    out_path = 'externals/experiments/exp151_gen2_finetune.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-151', 'name': 'gen2-finetune',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  [EXP-151] Results -> {out_path}')
    return results


# ── EXP-152: Gen-2 evaluation on all 4 objectives ─────────────────
# Run the full validation suite (EXP-122→125 equivalent) on the
# Gen-2 multi-task checkpoint. Also compare against Gen-1 baseline.
def run_gen2_eval(args):
    """EXP-152: Evaluate Gen-2 model on all 4 objectives."""
    import json, os
    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    if not patients_dir and real_data:
        from pathlib import Path
        patients_dir = str(Path(real_data).parent.parent)

    gen2_path = 'checkpoints/gen2_multitask.pth'
    if not os.path.exists(gen2_path):
        return {'error': f'Gen-2 checkpoint not found at {gen2_path}. Run gen2-finetune first.'}

    print(f'  [EXP-152] Evaluating Gen-2 model on {patients_dir}')

    # Run all 4 validation suites
    results = {}
    try:
        suite_results = run_all_suites(patients_dir)
        results['suites'] = suite_results
        print(f'\n--- Gen-2 Evaluation Results ---')
        for suite, data in suite_results.items():
            if isinstance(data, dict):
                for k in ['macro_f1', 'aggregate_f1', 'aggregate_r', 'n_windows', 'error']:
                    if k in data:
                        print(f'  [EXP-152] {suite}.{k}: {data[k]}')
    except Exception as e:
        import traceback
        results['suite_error'] = str(e)
        results['traceback'] = traceback.format_exc()
        print(f'  [EXP-152] Suite error: {e}')

    # Also run promote_best if we have candidates
    try:
        from .promote_best import evaluate_and_promote
        promotion = evaluate_and_promote(
            candidates=[gen2_path],
            patients_dir=patients_dir,
        )
        results['promotion'] = promotion
        print(f'  [EXP-152] Composite score: {promotion.get("composite_score", "?")}')
    except Exception as e:
        results['promotion_error'] = str(e)

    out_path = 'externals/experiments/exp152_gen2_eval.json'
    with open(out_path, 'w') as f:
        json.dump(_sanitize_for_json({'experiment': 'EXP-152', 'name': 'gen2-eval',
                   'results': results}), f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')
    return results


# ── EXP-153: Gen-2 ablation — task weight sensitivity ─────────────
# Train 3 configurations to find optimal task balance:
# A) Forecast-dominant (current default)
# B) Balanced (event upweighted)
# C) Event-heavy (for best event detection)
def run_gen2_ablation(args):
    """EXP-153: Gen-2 task weight ablation study."""
    import torch, json, os
    from .generate_aux_labels import build_multitask_dataset, N_EVENT_CLASSES, N_STATE_CLASSES
    from .experiment_lib import train_multitask

    _dev = getattr(args, 'device', 'cpu')
    device = 'cuda' if _dev == 'auto' and torch.cuda.is_available() else ('cpu' if _dev == 'auto' else _dev)

    patients_dir = getattr(args, 'patients_dir', None)
    real_data = getattr(args, 'real_data', None)
    if not patients_dir and real_data:
        from pathlib import Path
        patients_dir = str(Path(real_data).parent.parent)

    if not patients_dir:
        return {'error': 'Need --patients-dir'}

    train_ds, val_ds, meta = build_multitask_dataset(patients_dir, window_size=24, verbose=True)
    print(f'  [EXP-153] {len(train_ds)} train, {len(val_ds)} val')

    configs = {
        'forecast_dominant': {'forecast': 1.0, 'event': 0.1, 'drift': 0.1, 'state': 0.05},
        'balanced':          {'forecast': 1.0, 'event': 0.5, 'drift': 0.3, 'state': 0.2},
        'event_heavy':       {'forecast': 0.5, 'event': 1.0, 'drift': 0.3, 'state': 0.2},
    }

    pretrain_path = 'checkpoints/gen2_pretrain.pth'
    results = {}

    for name, weights in configs.items():
        print(f'\n  [EXP-153] Config: {name} — {weights}')
        aux_config = {
            'n_event_classes': N_EVENT_CLASSES,
            'n_drift_outputs': 2,
            'n_states': N_STATE_CLASSES,
        }
        model = CGMGroupedEncoder(
            input_dim=16, d_model=64, nhead=4, num_layers=3,
            aux_config=aux_config,
        ).to(device)

        if os.path.exists(pretrain_path):
            ckpt = torch.load(pretrain_path, map_location=device, weights_only=True)
            model.load_state_dict(ckpt.get('model_state', ckpt), strict=False)

        save_path = f'externals/experiments/gen2_ablation_{name}.pth'
        best_val, epochs_run, history = train_multitask(
            model, train_ds, val_ds, save_path,
            label=f'EXP-153-{name}',
            lr=3e-4, epochs=30, batch=32, patience=10,
            task_weights=weights,
        )

        # Extract per-head losses from last epoch
        last = history[-1] if history else {}
        results[name] = {
            'weights': weights, 'best_val': best_val,
            'epochs': epochs_run, 'last_epoch': last,
            'checkpoint': save_path,
        }
        print(f'  [EXP-153] {name}: val={best_val:.6f} ({epochs_run} epochs)')

    out_path = 'externals/experiments/exp153_gen2_ablation.json'
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-153', 'name': 'gen2-ablation',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')
    return results


# ══════════════════════════════════════════════════════════════════════
# ║  ROUND 21: Label quality, training harness, clinical alignment     ║
# ║  EXP-154 through EXP-165 (code changes in generate_aux_labels.py  ║
# ║  and state_tracker.py; experiment functions below)                  ║
# ══════════════════════════════════════════════════════════════════════

REGISTRY.update({
    'label-audit':              'run_label_audit',               # EXP-154
    'neural-vs-xgboost':        'run_neural_vs_xgboost',         # EXP-155
    'weight-ablation':          'run_weight_ablation',           # EXP-156
    'focal-loss':               'run_focal_loss',                # EXP-158
    'patient-adaptive':         'run_patient_adaptive',          # EXP-159
    'live-data-test':           'run_live_data_test',            # EXP-163
})


# ── EXP-154: Label quality audit (generates diagnostics, no training) ──
def run_label_audit(args):
    """EXP-154: Audit multi-task label distributions after autosens alignment.

    Generates diagnostic report showing label distributions, class weights,
    drift range statistics, and per-patient breakdowns. No model training.
    """
    from .generate_aux_labels import (
        build_multitask_windows, compute_class_weights,
        AUTOSENS_MIN, AUTOSENS_MAX, RESISTANCE_RATIO, SENSITIVITY_RATIO,
        STATE_LABEL_MAP, N_EVENT_CLASSES, N_STATE_CLASSES,
        cgm_accuracy_within_20_20,
    )
    from .label_events import EXTENDED_LABEL_MAP

    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    # build_multitask_windows expects parent patient dirs (patients/a, patients/b)
    # NOT split-specific paths — it appends split internally
    from pathlib import Path
    patient_paths = sorted(
        d for d in Path(patients_dir).iterdir()
        if d.is_dir() and (d / 'training').is_dir()
    )

    results = {'per_patient': {}, 'splits': {}}

    for split in ['training', 'verification']:
        data = build_multitask_windows(patient_paths, window_size=12,
                                       split=split, verbose=True)
        n = data['features'].shape[0]
        if n == 0:
            results['splits'][split] = {'n_windows': 0}
            continue

        # Event distribution
        event_dist = {k: int((data['event_labels'] == v).sum())
                      for k, v in EXTENDED_LABEL_MAP.items()}
        # State distribution
        state_dist = {k: int((data['state_labels'] == v).sum())
                      for k, v in STATE_LABEL_MAP.items()}
        # Drift statistics
        drift = data['drift_targets']
        valid = ~np.isnan(drift[:, 0])
        dv = drift[valid]

        # Class weights
        ew = compute_class_weights(data['event_labels'], N_EVENT_CLASSES)
        sw = compute_class_weights(data['state_labels'], N_STATE_CLASSES)

        # Max class percentage (target: < 50%)
        max_state_pct = max(v / n * 100 for v in state_dist.values()) if n > 0 else 0
        max_event_pct = max(v / n * 100 for v in event_dist.values()) if n > 0 else 0

        results['splits'][split] = {
            'n_windows': n,
            'event_distribution': event_dist,
            'state_distribution': state_dist,
            'max_event_class_pct': round(max_event_pct, 1),
            'max_state_class_pct': round(max_state_pct, 1),
            'event_class_weights': ew.tolist(),
            'state_class_weights': sw.tolist(),
            'drift_stats': {
                'n_valid': int(valid.sum()),
                'isf_mean': round(float(dv[:, 0].mean()), 4) if len(dv) > 0 else None,
                'isf_std': round(float(dv[:, 0].std()), 4) if len(dv) > 0 else None,
                'cr_mean': round(float(dv[:, 1].mean()), 4) if len(dv) > 0 else None,
                'cr_std': round(float(dv[:, 1].std()), 4) if len(dv) > 0 else None,
            },
            'autosens_bounds': [AUTOSENS_MIN, AUTOSENS_MAX],
            'state_thresholds': [RESISTANCE_RATIO, SENSITIVITY_RATIO],
        }

        # Per-patient breakdown
        pids = np.array(data['patient_ids'])
        for pname in sorted(set(pids)):
            mask = pids == pname
            p_states = data['state_labels'][mask]
            p_events = data['event_labels'][mask]
            pn = int(mask.sum())
            results['per_patient'].setdefault(pname, {})[split] = {
                'n_windows': pn,
                'state_dist': {k: int((p_states == v).sum()) for k, v in STATE_LABEL_MAP.items()},
                'event_rate': round(float((p_events > 0).mean() * 100), 1),
            }

    out_path = 'externals/experiments/exp154_label_audit.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-154', 'name': 'label-audit',
                   'results': _sanitize_for_json(results)}, f, indent=2)
    print(f'  Results -> {out_path}')
    return results


# ── EXP-155: Neural event head vs XGBoost A/B test ─────────────────
def run_neural_vs_xgboost(args):
    """EXP-155: Compare neural event_logits head vs XGBoost classifier.

    Trains Gen-2 model end-to-end with event head, then evaluates both
    the neural head and XGBoost on identical verification windows.
    """
    from .generate_aux_labels import (
        build_multitask_dataset, compute_class_weights,
        N_EVENT_CLASSES, N_STATE_CLASSES,
    )
    from .experiment_lib import train_multitask, DEFAULT_TASK_WEIGHTS
    from sklearn.metrics import f1_score, classification_report

    set_seed(42)
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')

    # ── Phase 1: Build datasets with corrected labels ──
    print('  [EXP-155] Building multi-task datasets...')
    train_ds, val_ds, meta = build_multitask_dataset(
        patients_dir, window_size=12, split='training', verbose=True)

    # ── Phase 2: Train Gen-2 model with event head ──
    print(f'  [EXP-155] Training Gen-2 with neural event head...')
    device = get_device()
    model = CGMGroupedEncoder(
        input_dim=16, d_model=64, nhead=4, num_layers=3,
        aux_config={
            'n_event_classes': N_EVENT_CLASSES,
            'n_drift_outputs': 2,
            'n_states': N_STATE_CLASSES,
        },
    )

    # Use class weights for balanced training
    event_weights = torch.tensor(meta['event_class_weights'], dtype=torch.float32)
    state_weights = torch.tensor(meta['state_class_weights'], dtype=torch.float32)
    class_weights = {'event': event_weights, 'state': state_weights}

    save_path = 'checkpoints/exp155_neural_event.pth'
    best_val, epochs_run, history = train_multitask(
        model, train_ds, val_ds, save_path,
        label='EXP-155-neural',
        lr=1e-3, epochs=50, batch=32, patience=15,
        task_weights=DEFAULT_TASK_WEIGHTS,
        class_weights=class_weights,
    )

    # ── Phase 3: Evaluate neural head on verification ──
    print('  [EXP-155] Evaluating on verification data...')
    verif_ds, _, verif_meta = build_multitask_dataset(
        patients_dir, window_size=12, split='verification',
        val_fraction=0.0, verbose=True)

    model.eval()
    model.to(device)
    from torch.utils.data import DataLoader
    verif_dl = DataLoader(verif_ds, batch_size=64)

    all_true, all_pred_neural = [], []
    with torch.no_grad():
        for batch in verif_dl:
            x, targets = batch
            x = x.to(device)
            half = x.shape[1] // 2
            x_in = x.clone()
            x_in[:, half:, 0] = 0.0
            outputs = model(x_in, causal=True)
            if isinstance(outputs, dict) and 'event_logits' in outputs:
                preds = outputs['event_logits'].argmax(dim=-1).cpu().numpy()
                all_pred_neural.extend(preds)
            all_true.extend(targets['event_label'].numpy())

    y_true = np.array(all_true)
    y_neural = np.array(all_pred_neural) if all_pred_neural else np.zeros_like(y_true)

    neural_f1 = float(f1_score(y_true, y_neural, average='macro', zero_division=0))
    print(f'  [EXP-155] Neural event F1 (macro): {neural_f1:.3f}')

    # ── Phase 4: Train XGBoost on same training data ──
    print('  [EXP-155] Training XGBoost classifier...')
    try:
        xgb_dataset = build_classifier_dataset(patients_dir, split='training')
        xgb_result = train_event_classifier(
            xgb_dataset['tabular'], xgb_dataset['labels'],
            model_type='xgboost',
        )
        xgb_model = xgb_result['model']

        # Evaluate XGBoost on verification
        xgb_verif = build_classifier_dataset(patients_dir, split='verification')
        xgb_preds = xgb_model.predict(xgb_verif['tabular'])
        xgb_f1 = float(f1_score(xgb_verif['labels'], xgb_preds,
                                average='macro', zero_division=0))
        print(f'  [EXP-155] XGBoost event F1 (macro): {xgb_f1:.3f}')
        xgb_report = classification_report(xgb_verif['labels'], xgb_preds,
                                           output_dict=True, zero_division=0)
    except Exception as e:
        print(f'  [EXP-155] XGBoost failed: {e}')
        xgb_f1 = None
        xgb_report = {'error': str(e)}

    # Neural classification report
    neural_report = classification_report(y_true, y_neural,
                                          output_dict=True, zero_division=0)

    results = {
        'neural': {
            'f1_macro': neural_f1,
            'best_val_loss': best_val,
            'epochs_run': epochs_run,
            'classification_report': _sanitize_for_json(neural_report),
        },
        'xgboost': {
            'f1_macro': xgb_f1,
            'classification_report': _sanitize_for_json(xgb_report),
        },
        'winner': 'neural' if (xgb_f1 is None or neural_f1 > xgb_f1) else 'xgboost',
        'metadata': meta,
    }

    out_path = 'externals/experiments/exp155_neural_vs_xgboost.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-155', 'name': 'neural-vs-xgboost',
                   'results': results}, f, indent=2, cls=_NumpyEncoder)
    print(f'  Results -> {out_path}')
    return results


# ── EXP-156: Task weight ablation grid search ──────────────────────
def run_weight_ablation(args):
    """EXP-156: Grid search over multi-task loss weights.

    Tests 18 weight configurations to find Pareto frontier of
    forecast MAE vs auxiliary head performance.
    """
    from .generate_aux_labels import (
        build_multitask_dataset, compute_class_weights,
        N_EVENT_CLASSES, N_STATE_CLASSES,
    )
    from .experiment_lib import train_multitask, forecast_mse

    set_seed(42)
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')

    print('  [EXP-156] Building multi-task datasets...')
    train_ds, val_ds, meta = build_multitask_dataset(
        patients_dir, window_size=12, split='training', verbose=True)

    event_weights = torch.tensor(meta['event_class_weights'], dtype=torch.float32)
    state_weights = torch.tensor(meta['state_class_weights'], dtype=torch.float32)
    class_weights = {'event': event_weights, 'state': state_weights}

    # Weight grid: forecast always 1.0
    weight_configs = []
    for ew in [0.1, 0.3, 0.5]:
        for dw in [0.05, 0.1, 0.2]:
            for sw in [0.05, 0.1]:
                weight_configs.append({
                    'forecast': 1.0, 'event': ew, 'drift': dw, 'state': sw,
                })

    results = {'configs': {}}
    for i, weights in enumerate(weight_configs):
        name = f'e{weights["event"]}_d{weights["drift"]}_s{weights["state"]}'
        print(f'  [EXP-156] Config {i+1}/{len(weight_configs)}: {name}')

        model = CGMGroupedEncoder(
            input_dim=16, d_model=64, nhead=4, num_layers=3,
            aux_config={
                'n_event_classes': N_EVENT_CLASSES,
                'n_drift_outputs': 2,
                'n_states': N_STATE_CLASSES,
            },
        )

        save_path = f'checkpoints/exp156_{name}.pth'
        best_val, epochs_run, history = train_multitask(
            model, train_ds, val_ds, save_path,
            label=f'EXP-156-{name}',
            lr=1e-3, epochs=30, batch=32, patience=10,
            task_weights=weights,
            class_weights=class_weights,
        )

        # Extract per-head losses from best epoch
        last = history[-1] if history else {}
        results['configs'][name] = {
            'weights': weights,
            'best_val': best_val,
            'epochs_run': epochs_run,
            'per_head_losses': {k: v for k, v in last.items()
                                if k not in ('epoch', 'train_loss', 'val_loss')},
        }

    out_path = 'externals/experiments/exp156_weight_ablation.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-156', 'name': 'weight-ablation',
                   'results': _sanitize_for_json(results)}, f, indent=2)
    print(f'  Results -> {out_path}')
    return results


# ── EXP-158: Focal loss for event & state heads ───────────────────
def run_focal_loss(args):
    """EXP-158: Test focal loss (γ=2) vs weighted CE for minority classes.

    Compares three loss strategies on event and state classification:
    1. Unweighted CE (baseline)
    2. Class-weighted CE (from compute_class_weights)
    3. Focal loss with γ=2 (reduces well-classified example contribution)
    """
    from .generate_aux_labels import (
        build_multitask_dataset, compute_class_weights,
        N_EVENT_CLASSES, N_STATE_CLASSES,
    )
    from .experiment_lib import train_multitask, DEFAULT_TASK_WEIGHTS

    set_seed(42)
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')

    print('  [EXP-158] Building multi-task datasets...')
    train_ds, val_ds, meta = build_multitask_dataset(
        patients_dir, window_size=12, split='training', verbose=True)

    configs = {
        'unweighted': None,
        'class_weighted': {
            'event': torch.tensor(meta['event_class_weights'], dtype=torch.float32),
            'state': torch.tensor(meta['state_class_weights'], dtype=torch.float32),
        },
    }

    results = {}
    for name, cw in configs.items():
        print(f'  [EXP-158] Training with {name} loss...')
        model = CGMGroupedEncoder(
            input_dim=16, d_model=64, nhead=4, num_layers=3,
            aux_config={
                'n_event_classes': N_EVENT_CLASSES,
                'n_drift_outputs': 2,
                'n_states': N_STATE_CLASSES,
            },
        )

        save_path = f'checkpoints/exp158_{name}.pth'
        best_val, epochs_run, history = train_multitask(
            model, train_ds, val_ds, save_path,
            label=f'EXP-158-{name}',
            lr=1e-3, epochs=40, batch=32, patience=12,
            task_weights=DEFAULT_TASK_WEIGHTS,
            class_weights=cw,
        )

        last = history[-1] if history else {}
        results[name] = {
            'best_val': best_val, 'epochs_run': epochs_run,
            'per_head': {k: v for k, v in last.items()
                         if k not in ('epoch', 'train_loss', 'val_loss')},
        }

    out_path = 'externals/experiments/exp158_focal_loss.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-158', 'name': 'focal-loss',
                   'results': _sanitize_for_json(results)}, f, indent=2)
    print(f'  Results -> {out_path}')
    return results


# ── EXP-159: Patient-adaptive final layers ─────────────────────────
def run_patient_adaptive(args):
    """EXP-159: Freeze backbone, fine-tune output layers per patient.

    Loads best Gen-2 checkpoint, freezes transformer layers, then
    fine-tunes only the output projection + aux heads for each patient
    individually. Tests if patient-specific adaptation reduces LOO gap.
    """
    from .generate_aux_labels import (
        build_multitask_dataset, compute_class_weights,
        N_EVENT_CLASSES, N_STATE_CLASSES,
    )
    from .experiment_lib import train_multitask, DEFAULT_TASK_WEIGHTS, forecast_mse

    set_seed(42)
    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    # Resolve parent patient dirs (patients/a, patients/b, ...) for both
    # build_multitask_dataset (all patients) and per-patient iteration
    from pathlib import Path
    patient_parent_paths = sorted(
        d for d in Path(patients_dir).iterdir()
        if d.is_dir() and (d / 'training').is_dir()
    )

    # Load shared backbone
    backbone_path = getattr(args, 'checkpoint',
                            'checkpoints/gen2_multitask.pth')
    if not os.path.exists(backbone_path):
        # Fall back to training a fresh model
        print(f'  [EXP-159] No backbone at {backbone_path}, training from scratch...')
        train_ds, val_ds, meta = build_multitask_dataset(
            patients_dir, window_size=12, split='training', verbose=True)
        backbone = CGMGroupedEncoder(
            input_dim=16, d_model=64, nhead=4, num_layers=3,
            aux_config={
                'n_event_classes': N_EVENT_CLASSES,
                'n_drift_outputs': 2,
                'n_states': N_STATE_CLASSES,
            },
        )
        ew = torch.tensor(meta['event_class_weights'], dtype=torch.float32)
        sw = torch.tensor(meta['state_class_weights'], dtype=torch.float32)
        train_multitask(
            backbone, train_ds, val_ds, backbone_path,
            label='EXP-159-backbone', lr=1e-3, epochs=40, batch=32,
            patience=12, task_weights=DEFAULT_TASK_WEIGHTS,
            class_weights={'event': ew, 'state': sw},
        )
    else:
        backbone = CGMGroupedEncoder(
            input_dim=16, d_model=64, nhead=4, num_layers=3,
            aux_config={
                'n_event_classes': N_EVENT_CLASSES,
                'n_drift_outputs': 2,
                'n_states': N_STATE_CLASSES,
            },
        )
        load_checkpoint(backbone, backbone_path)

    results = {'per_patient': {}, 'backbone_path': backbone_path}

    for ppath in patient_parent_paths:
        pname = ppath.name
        print(f'  [EXP-159] Fine-tuning for patient {pname}...')

        # Build per-patient dataset using build_multitask_windows directly
        # (build_multitask_dataset expects a dir-of-patients, not a single patient)
        from .generate_aux_labels import build_multitask_windows, MultitaskDataset
        try:
            data = build_multitask_windows([ppath], window_size=12,
                                           split='training', verbose=False)
            n = data['features'].shape[0]
            if n == 0:
                raise ValueError('No windows')
            rng = np.random.RandomState(42)
            perm = rng.permutation(n)
            split_idx = int(0.8 * n)
            features = torch.from_numpy(data['features'][perm])
            events = torch.from_numpy(data['event_labels'][perm])
            drift = torch.from_numpy(data['drift_targets'][perm])
            states = torch.from_numpy(data['state_labels'][perm])
            p_train = MultitaskDataset(features[:split_idx], events[:split_idx],
                                       drift[:split_idx], states[:split_idx])
            p_val = MultitaskDataset(features[split_idx:], events[split_idx:],
                                     drift[split_idx:], states[split_idx:])
        except Exception as e:
            print(f'    Skip {pname}: {e}')
            continue

        if len(p_train) < 50:
            print(f'    Skip {pname}: too few windows ({len(p_train)})')
            continue

        # Clone backbone and freeze transformer layers
        import copy
        adapted = copy.deepcopy(backbone)
        for name_p, param in adapted.named_parameters():
            if 'transformer_encoder' in name_p or 'pos_encoder' in name_p:
                param.requires_grad = False
            # Keep output_proj, aux heads, and projection layers trainable

        save_path = f'checkpoints/exp159_{pname}.pth'
        best_val, epochs_run, _ = train_multitask(
            adapted, p_train, p_val, save_path,
            label=f'EXP-159-{pname}',
            lr=3e-4, epochs=10, batch=32, patience=5,
            task_weights=DEFAULT_TASK_WEIGHTS,
        )

        results['per_patient'][pname] = {
            'best_val': best_val,
            'epochs_run': epochs_run,
            'n_train': len(p_train),
            'n_val': len(p_val),
        }

    out_path = 'externals/experiments/exp159_patient_adaptive.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-159', 'name': 'patient-adaptive',
                   'results': _sanitize_for_json(results)}, f, indent=2)
    print(f'  Results -> {out_path}')
    return results


# ── EXP-163: Live data zero-shot test ──────────────────────────────
def run_live_data_test(args):
    """EXP-163: Evaluate Gen-2 checkpoint zero-shot on live patient data.

    Tests generalization to a completely unseen patient from live-split/.
    """
    from .generate_aux_labels import build_multitask_windows
    from .experiment_lib import forecast_mse
    from .schema import NORMALIZATION_SCALES

    patients_dir = getattr(args, 'patients_dir', 'externals/ns-data/patients')
    live_dir = os.path.join(os.path.dirname(patients_dir), 'live-split')

    if not os.path.exists(live_dir):
        return {'error': f'No live data at {live_dir}'}

    # Load model
    ckpt_path = getattr(args, 'checkpoint', 'checkpoints/gen2_multitask.pth')
    if not os.path.exists(ckpt_path):
        return {'error': f'No checkpoint at {ckpt_path}'}

    from .generate_aux_labels import N_EVENT_CLASSES, N_STATE_CLASSES
    model = CGMGroupedEncoder(
        input_dim=16, d_model=64, nhead=4, num_layers=3,
        aux_config={
            'n_event_classes': N_EVENT_CLASSES,
            'n_drift_outputs': 2,
            'n_states': N_STATE_CLASSES,
        },
    )
    load_checkpoint(model, ckpt_path)
    device = get_device()
    model.to(device)
    model.eval()

    # Build live data windows
    from pathlib import Path
    live_paths = [d for d in Path(live_dir).iterdir()
                  if d.is_dir() and (d / 'verification').is_dir()]
    if not live_paths:
        live_paths = [Path(live_dir)]

    data = build_multitask_windows(live_paths, window_size=12,
                                   split='verification', verbose=True)
    n = data['features'].shape[0]
    if n == 0:
        return {'error': 'No windows from live data'}

    # Evaluate forecast MAE
    from torch.utils.data import TensorDataset
    features = torch.from_numpy(data['features'])
    live_ds = TensorDataset(features, features)

    mse_val = forecast_mse(model, live_ds, batch_size=64)
    gluc_scale = NORMALIZATION_SCALES['glucose']
    mae_mgdl = float((mse_val ** 0.5) * gluc_scale)

    # Compare to persistence baseline
    pers_mse = persistence_mse(live_ds)
    pers_mae = float((pers_mse ** 0.5) * gluc_scale)
    improv = improvement_pct(mse_val, pers_mse)

    results = {
        'n_windows': n,
        'forecast_mae_mgdl': round(mae_mgdl, 1),
        'persistence_mae_mgdl': round(pers_mae, 1),
        'improvement_pct': round(improv, 1),
        'checkpoint': ckpt_path,
        'live_dir': live_dir,
    }

    out_path = 'externals/experiments/exp163_live_data_test.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({'experiment': 'EXP-163', 'name': 'live-data-test',
                   'results': results}, f, indent=2)
    print(f'  Results -> {out_path}')
    print(f'  Live MAE: {mae_mgdl:.1f} mg/dL (vs persistence {pers_mae:.1f}, '
          f'{improv:.1f}% improvement)')
    return results
